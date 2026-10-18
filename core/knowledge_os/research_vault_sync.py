"""
core/knowledge_os/research_vault_sync.py
========================================
Automated Git-Native Synchronization Engine for CBT Research Vault.

Zero-Touch Architecture:
- Automatically mirrors all Research Wikipedia articles, epistemic claims,
  source provenance ledgers, and uploaded PDFs/documents into `data/research/vault/`.
- Whitelisted in `.gitignore` so Git naturally commits and syncs everything across
  Ubuntu, Windows, and remote nodes.
- When CBT starts or when `git pull` brings new papers, `auto_rehydrate_from_git_vault()`
  detects them and instantly updates local SQLite ledgers in milliseconds.
- ZERO MANUAL TERMINAL COMMANDS REQUIRED BY THE USER.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.research_vault_sync")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))

VAULT_DIR = DATA_DIR / "research" / "vault"
VAULT_MANIFEST = VAULT_DIR / "vault_manifest.json"
VAULT_ARTICLES_DIR = VAULT_DIR / "articles"
VAULT_DOCS_DIR = VAULT_DIR / "documents"


def export_to_git_vault(
    wiki_db_path: Path | None = None,
    articles_dir: Path | None = None,
    uploads_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Serializes local SQLite research databases and uploaded documents into
    the Git-tracked `data/research/vault/` folder.
    """
    wiki_db = wiki_db_path or (DATA_DIR / "research_wiki.db")
    src_articles = articles_dir or (DATA_DIR / "research_wiki" / "articles")
    src_uploads = uploads_dir or (DATA_DIR / "uploads")

    if not wiki_db.exists():
        return {"status": "SKIPPED", "reason": "wiki_db_not_found"}

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(wiki_db), timeout=5.0)
        conn.row_factory = sqlite3.Row

        # 1. Fetch articles
        articles_rows = []
        try:
            articles_rows = [
                dict(r) for r in conn.execute("SELECT * FROM wiki_articles").fetchall()
            ]
        except sqlite3.OperationalError:
            pass

        # 2. Fetch sources
        sources_rows = []
        try:
            sources_rows = [
                dict(r) for r in conn.execute("SELECT * FROM research_sources").fetchall()
            ]
        except sqlite3.OperationalError:
            pass

        # 3. Fetch claims
        claims_rows = []
        try:
            claims_rows = [
                dict(r) for r in conn.execute("SELECT * FROM research_claims").fetchall()
            ]
        except sqlite3.OperationalError:
            pass

        conn.close()

        # Write manifest
        manifest = {
            "version": "1.0",
            "updated_at": int(time.time() * 1000),
            "stats": {
                "articles_count": len(articles_rows),
                "sources_count": len(sources_rows),
                "claims_count": len(claims_rows),
            },
            "articles": articles_rows,
            "sources": sources_rows,
            "claims": claims_rows,
        }

        with open(VAULT_MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 4. Mirror markdown articles
        if src_articles.exists():
            for f in src_articles.glob("*.md"):
                if f.is_file():
                    shutil.copy2(f, VAULT_ARTICLES_DIR / f.name)

        # 5. Mirror uploaded files (PDFs, docs)
        docs_copied = 0
        if src_uploads.exists():
            for f in src_uploads.glob("*"):
                if f.is_file() and not f.name.startswith("."):
                    # Git safety: skip files > 45MB to avoid GitHub large file push warnings
                    if f.stat().st_size > 45 * 1024 * 1024:
                        continue
                    target = VAULT_DOCS_DIR / f.name
                    if not target.exists() or target.stat().st_size != f.stat().st_size:
                        shutil.copy2(f, target)
                    docs_copied += 1

        logger.info(
            f"[Vault Sync] Exported {len(articles_rows)} articles, {len(sources_rows)} sources, {docs_copied} docs to Git Vault."
        )
        return {
            "status": "SUCCESS",
            "articles_count": len(articles_rows),
            "sources_count": len(sources_rows),
            "claims_count": len(claims_rows),
            "docs_copied": docs_copied,
        }
    except Exception as e:
        logger.warning(f"[Vault Sync] Export to Git Vault failed: {e}")
        return {"status": "ERROR", "error": str(e)}


def auto_rehydrate_from_git_vault(
    wiki_db_path: Path | None = None,
    articles_dir: Path | None = None,
    uploads_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Automatically called on CBT startup.
    Checks `data/research/vault/` (synced via `git pull`) and seamlessly
    rehydrates SQLite tables and uploads folder with any newly arrived research.
    """
    if not VAULT_MANIFEST.exists():
        return {"status": "SKIPPED", "reason": "no_vault_manifest"}

    wiki_db = wiki_db_path or (DATA_DIR / "research_wiki.db")
    dest_articles = articles_dir or (DATA_DIR / "research_wiki" / "articles")
    dest_uploads = uploads_dir or (DATA_DIR / "uploads")

    dest_articles.mkdir(parents=True, exist_ok=True)
    dest_uploads.mkdir(parents=True, exist_ok=True)

    try:
        with open(VAULT_MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)

        conn = sqlite3.connect(str(wiki_db), timeout=10.0)
        conn.row_factory = sqlite3.Row

        # 1. Rehydrate sources
        sources = manifest.get("sources", [])
        new_sources = 0
        for s in sources:
            existing = conn.execute(
                "SELECT source_id FROM research_sources WHERE source_id = ?",
                (s["source_id"],),
            ).fetchone()
            if not existing:
                cols = list(s.keys())
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT OR IGNORE INTO research_sources ({', '.join(cols)}) VALUES ({placeholders})"
                conn.execute(sql, list(s.values()))
                new_sources += 1

        # 2. Rehydrate articles
        articles = manifest.get("articles", [])
        new_articles = 0
        for a in articles:
            existing = conn.execute(
                "SELECT article_id FROM wiki_articles WHERE article_id = ?",
                (a["article_id"],),
            ).fetchone()
            if not existing:
                cols = list(a.keys())
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT OR IGNORE INTO wiki_articles ({', '.join(cols)}) VALUES ({placeholders})"
                conn.execute(sql, list(a.values()))
                new_articles += 1

        # 3. Rehydrate claims
        claims = manifest.get("claims", [])
        new_claims = 0
        for c in claims:
            existing = conn.execute(
                "SELECT claim_id FROM research_claims WHERE claim_id = ?",
                (c["claim_id"],),
            ).fetchone()
            if not existing:
                cols = list(c.keys())
                placeholders = ", ".join(["?"] * len(cols))
                sql = f"INSERT OR IGNORE INTO research_claims ({', '.join(cols)}) VALUES ({placeholders})"
                conn.execute(sql, list(c.values()))
                new_claims += 1

        conn.commit()
        conn.close()

        # 4. Copy markdown articles
        if VAULT_ARTICLES_DIR.exists():
            for f in VAULT_ARTICLES_DIR.glob("*.md"):
                if f.is_file():
                    target = dest_articles / f.name
                    if not target.exists():
                        shutil.copy2(f, target)

        # 5. Copy uploaded PDFs / documents into data/uploads
        docs_rehydrated = 0
        if VAULT_DOCS_DIR.exists():
            for f in VAULT_DOCS_DIR.glob("*"):
                if f.is_file() and not f.name.startswith("."):
                    target = dest_uploads / f.name
                    if not target.exists() or target.stat().st_size != f.stat().st_size:
                        shutil.copy2(f, target)
                        docs_rehydrated += 1

        if new_sources > 0 or new_articles > 0 or docs_rehydrated > 0:
            logger.info(
                f"[Auto Rehydrate] Added {new_sources} sources, {new_articles} articles, {docs_rehydrated} documents from Git Vault!"
            )

        return {
            "status": "SUCCESS",
            "new_sources": new_sources,
            "new_articles": new_articles,
            "new_claims": new_claims,
            "docs_rehydrated": docs_rehydrated,
        }
    except Exception as e:
        logger.warning(f"[Auto Rehydrate] Failed: {e}")
        return {"status": "ERROR", "error": str(e)}
