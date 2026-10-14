"""
tests/test_research_vault_sync.py
=================================
Verifies automated Git-native research vault export and rehydration.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
import pytest

from core.knowledge_os.research_vault_sync import (
    export_to_git_vault,
    auto_rehydrate_from_git_vault,
)


@pytest.fixture
def sandbox_vault_env(monkeypatch):
    """Sets up an isolated test sandbox for Git-native vault sync."""
    with tempfile.TemporaryDirectory(prefix="test_git_vault_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        data_dir = tmp_path / "data"
        vault_dir = data_dir / "research" / "vault"
        vault_manifest = vault_dir / "vault_manifest.json"
        vault_articles = vault_dir / "articles"
        vault_docs = vault_dir / "documents"

        wiki_db = data_dir / "research_wiki.db"
        articles_dir = data_dir / "research_wiki" / "articles"
        uploads_dir = data_dir / "uploads"

        data_dir.mkdir(parents=True, exist_ok=True)
        articles_dir.mkdir(parents=True, exist_ok=True)
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Monkeypatch paths
        import core.knowledge_os.research_vault_sync as rvs
        monkeypatch.setattr(rvs, "DATA_DIR", data_dir)
        monkeypatch.setattr(rvs, "VAULT_DIR", vault_dir)
        monkeypatch.setattr(rvs, "VAULT_MANIFEST", vault_manifest)
        monkeypatch.setattr(rvs, "VAULT_ARTICLES_DIR", vault_articles)
        monkeypatch.setattr(rvs, "VAULT_DOCS_DIR", vault_docs)

        # Initialize SQLite DB
        conn = sqlite3.connect(str(wiki_db))
        conn.execute(
            """
            CREATE TABLE wiki_articles (
                article_id TEXT PRIMARY KEY,
                title TEXT,
                category TEXT,
                source_url TEXT,
                source_type TEXT,
                created_at INTEGER
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE research_sources (
                source_id TEXT PRIMARY KEY,
                original_url TEXT,
                source_domain TEXT,
                source_type TEXT,
                created_at INTEGER
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE research_claims (
                claim_id TEXT PRIMARY KEY,
                source_id TEXT,
                speaker_claim TEXT,
                claim_type TEXT,
                created_at INTEGER
            );
            """
        )

        conn.execute(
            "INSERT INTO wiki_articles VALUES ('art_test_1', 'Order Flow Tox', 'Market Structure', 'http://a.com', 'PDF', 1000);"
        )
        conn.execute(
            "INSERT INTO research_sources VALUES ('src_test_1', 'http://a.com/doc.pdf', 'a.com', 'PDF', 1000);"
        )
        conn.execute(
            "INSERT INTO research_claims VALUES ('clm_test_1', 'src_test_1', 'CVD divergence predicts drop', 'HYPOTHESIS', 1000);"
        )
        conn.commit()
        conn.close()

        # Dummy file and markdown
        (articles_dir / "art_test_1.md").write_text("# Order Flow Tox\nContent.", encoding="utf-8")
        (uploads_dir / "doc.pdf").write_bytes(b"%PDF-1.4 dummy pdf content")

        yield {
            "root": tmp_path,
            "data_dir": data_dir,
            "wiki_db": wiki_db,
            "articles_dir": articles_dir,
            "uploads_dir": uploads_dir,
            "vault_dir": vault_dir,
            "vault_manifest": vault_manifest,
            "vault_docs": vault_docs,
        }


def test_export_and_rehydrate_git_vault(sandbox_vault_env):
    """Verifies seamless export to Git Vault and rehydration into empty database."""
    # 1. Export
    exp_res = export_to_git_vault(
        wiki_db_path=sandbox_vault_env["wiki_db"],
        articles_dir=sandbox_vault_env["articles_dir"],
        uploads_dir=sandbox_vault_env["uploads_dir"],
    )
    assert exp_res["status"] == "SUCCESS"
    assert exp_res["articles_count"] == 1
    assert exp_res["sources_count"] == 1
    assert exp_res["docs_copied"] == 1

    assert sandbox_vault_env["vault_manifest"].exists()
    assert (sandbox_vault_env["vault_docs"] / "doc.pdf").exists()

    # 2. Rehydrate into a new second clean environment
    target_data = sandbox_vault_env["root"] / "target_data"
    target_wiki = target_data / "research_wiki.db"
    target_articles = target_data / "research_wiki" / "articles"
    target_uploads = target_data / "uploads"

    target_data.mkdir(parents=True, exist_ok=True)
    target_articles.mkdir(parents=True, exist_ok=True)
    target_uploads.mkdir(parents=True, exist_ok=True)

    # Initialize empty tables in target DB
    conn = sqlite3.connect(str(target_wiki))
    conn.execute("CREATE TABLE wiki_articles (article_id TEXT PRIMARY KEY, title TEXT, category TEXT, source_url TEXT, source_type TEXT, created_at INTEGER);")
    conn.execute("CREATE TABLE research_sources (source_id TEXT PRIMARY KEY, original_url TEXT, source_domain TEXT, source_type TEXT, created_at INTEGER);")
    conn.execute("CREATE TABLE research_claims (claim_id TEXT PRIMARY KEY, source_id TEXT, speaker_claim TEXT, claim_type TEXT, created_at INTEGER);")
    conn.commit()
    conn.close()

    reh_res = auto_rehydrate_from_git_vault(
        wiki_db_path=target_wiki,
        articles_dir=target_articles,
        uploads_dir=target_uploads,
    )

    assert reh_res["status"] == "SUCCESS"
    assert reh_res["new_articles"] == 1
    assert reh_res["new_sources"] == 1
    assert reh_res["docs_rehydrated"] == 1

    # Verify target has the files
    assert (target_uploads / "doc.pdf").exists()
    assert (target_articles / "art_test_1.md").exists()
