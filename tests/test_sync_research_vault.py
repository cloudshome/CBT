"""
tests/test_sync_research_vault.py
=================================
Automated verification tests for the Research Vault synchronization utility.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
import pytest

from scripts.sync_research_vault import (
    compute_sha256,
    export_vault,
    inspect_bundle,
    import_vault,
    get_sqlite_table_count,
)


@pytest.fixture
def sandbox_env(monkeypatch):
    """Creates an isolated temporary CBT data environment."""
    with tempfile.TemporaryDirectory(prefix="test_vault_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        sandbox_data = tmp_path / "data"
        sandbox_data.mkdir(parents=True, exist_ok=True)

        wiki_db = sandbox_data / "research_wiki.db"
        brain_db = sandbox_data / "brain_memory.db"
        uploads = sandbox_data / "uploads"
        articles = sandbox_data / "research_wiki" / "articles"

        uploads.mkdir(parents=True, exist_ok=True)
        articles.mkdir(parents=True, exist_ok=True)

        # Create dummy databases
        conn1 = sqlite3.connect(str(wiki_db))
        conn1.execute("CREATE TABLE wiki_articles (id TEXT PRIMARY KEY, title TEXT);")
        conn1.execute("INSERT INTO wiki_articles VALUES ('art_001', 'Order Flow Analysis');")
        conn1.execute("CREATE TABLE research_sources (id TEXT PRIMARY KEY);")
        conn1.execute("INSERT INTO research_sources VALUES ('src_001');")
        conn1.execute("CREATE TABLE research_claims (id TEXT PRIMARY KEY);")
        conn1.commit()
        conn1.close()

        conn2 = sqlite3.connect(str(brain_db))
        conn2.execute("CREATE TABLE research_provenance_ledger (id TEXT PRIMARY KEY);")
        conn2.execute("INSERT INTO research_provenance_ledger VALUES ('prov_001');")
        conn2.execute("CREATE TABLE strategy_candidates (id TEXT PRIMARY KEY);")
        conn2.commit()
        conn2.close()

        # Create dummy sample PDF and markdown
        dummy_pdf = uploads / "test_quant_paper.pdf"
        dummy_pdf.write_bytes(b"%PDF-1.4 sample research content for quant trading")

        dummy_md = articles / "order_flow_analysis.md"
        dummy_md.write_text("# Order Flow Analysis\nDetailed content.", encoding="utf-8")

        # Monkeypatch paths
        import scripts.sync_research_vault as srv
        monkeypatch.setattr(srv, "DATA_DIR", sandbox_data)
        monkeypatch.setattr(srv, "WIKI_DB_PATH", wiki_db)
        monkeypatch.setattr(srv, "BRAIN_DB_PATH", brain_db)
        monkeypatch.setattr(srv, "UPLOADS_DIR", uploads)
        monkeypatch.setattr(srv, "ARTICLES_DIR", articles)

        yield {
            "root": tmp_path,
            "data": sandbox_data,
            "wiki_db": wiki_db,
            "brain_db": brain_db,
            "uploads": uploads,
            "articles": articles,
        }


def test_export_and_inspect_bundle(sandbox_env):
    """Verifies exporting creates a valid bundle with verified manifest."""
    bundle_target = sandbox_env["root"] / "test_bundle.tar.gz"
    res_bundle = export_vault(output_path=bundle_target)

    assert res_bundle.exists()
    assert res_bundle.stat().st_size > 0

    manifest = inspect_bundle(res_bundle)
    assert manifest["version"] == "1.0"
    assert manifest["stats"]["wiki_articles_rows"] == 1
    assert manifest["stats"]["uploads_count"] == 1
    assert "research_wiki.db" in manifest["files"]
    assert "brain_memory.db" in manifest["files"]


def test_import_bundle_into_fresh_environment(sandbox_env, monkeypatch):
    """Verifies bundle imports cleanly and restores database rows and files."""
    bundle_target = sandbox_env["root"] / "test_bundle.tar.gz"
    export_vault(output_path=bundle_target)

    # Now create a second fresh environment
    second_data = sandbox_env["root"] / "target_data"
    second_wiki = second_data / "research_wiki.db"
    second_brain = second_data / "brain_memory.db"
    second_uploads = second_data / "uploads"
    second_articles = second_data / "research_wiki" / "articles"

    import scripts.sync_research_vault as srv
    monkeypatch.setattr(srv, "DATA_DIR", second_data)
    monkeypatch.setattr(srv, "WIKI_DB_PATH", second_wiki)
    monkeypatch.setattr(srv, "BRAIN_DB_PATH", second_brain)
    monkeypatch.setattr(srv, "UPLOADS_DIR", second_uploads)
    monkeypatch.setattr(srv, "ARTICLES_DIR", second_articles)

    import_vault(bundle_target)

    assert second_wiki.exists()
    assert second_brain.exists()
    assert (second_uploads / "test_quant_paper.pdf").exists()
    assert (second_articles / "order_flow_analysis.md").exists()

    # Check database rows
    count = get_sqlite_table_count(second_wiki, "wiki_articles")
    assert count == 1
