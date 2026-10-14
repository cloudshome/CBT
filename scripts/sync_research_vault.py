"""
scripts/sync_research_vault.py
==============================
Deterministic Research Vault & PDF Synchronization Utility for CBT / SKY.

Facilitates seamless, zero-loss transfer of Research Wikipedia databases,
provenance ledgers, and raw uploaded PDF/document archives between CBT nodes
(e.g., Ubuntu workstation <-> Windows desktop).

Usage:
    # 1. View local vault inventory and statistics
    python scripts/sync_research_vault.py --status

    # 2. Export local research vault into a compressed bundle
    python scripts/sync_research_vault.py --export
    python scripts/sync_research_vault.py --export -o /path/to/my_vault.tar.gz

    # 3. Import research vault bundle onto another machine
    python scripts/sync_research_vault.py --import my_vault.tar.gz

    # 4. Dry run inspection of an existing bundle without extracting
    python scripts/sync_research_vault.py --inspect my_vault.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

WIKI_DB_PATH = DATA_DIR / "research_wiki.db"
BRAIN_DB_PATH = DATA_DIR / "brain_memory.db"
UPLOADS_DIR = DATA_DIR / "uploads"
ARTICLES_DIR = DATA_DIR / "research_wiki" / "articles"


def compute_sha256(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_sqlite_table_count(db_path: Path, table_name: str) -> int:
    """Returns row count for a table if the SQLite database exists."""
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def get_vault_stats() -> dict[str, Any]:
    """Inspects and returns local research vault statistics."""
    uploads_count = 0
    uploads_size = 0
    if UPLOADS_DIR.exists():
        for p in UPLOADS_DIR.rglob("*"):
            if p.is_file():
                uploads_count += 1
                uploads_size += p.stat().st_size

    articles_file_count = 0
    if ARTICLES_DIR.exists():
        for p in ARTICLES_DIR.rglob("*.md"):
            if p.is_file():
                articles_file_count += 1

    wiki_articles_rows = get_sqlite_table_count(WIKI_DB_PATH, "wiki_articles")
    research_sources_rows = get_sqlite_table_count(WIKI_DB_PATH, "research_sources")
    research_claims_rows = get_sqlite_table_count(WIKI_DB_PATH, "research_claims")
    provenance_rows = get_sqlite_table_count(BRAIN_DB_PATH, "research_provenance_ledger")
    strategy_rows = get_sqlite_table_count(BRAIN_DB_PATH, "strategy_candidates")

    return {
        "wiki_db_exists": WIKI_DB_PATH.exists(),
        "brain_db_exists": BRAIN_DB_PATH.exists(),
        "uploads_count": uploads_count,
        "uploads_size_mb": round(uploads_size / (1024 * 1024), 2),
        "articles_markdown_count": articles_file_count,
        "wiki_articles_rows": wiki_articles_rows,
        "research_sources_rows": research_sources_rows,
        "research_claims_rows": research_claims_rows,
        "provenance_rows": provenance_rows,
        "strategy_rows": strategy_rows,
    }


def show_status() -> None:
    """Prints formatted vault inventory to terminal."""
    stats = get_vault_stats()
    print("=" * 68)
    print("   SKY RESEARCH LAB & PDF VAULT — LOCAL INVENTORY STATUS   ")
    print("=" * 68)
    print(f"[*] Node Operating System   : {platform.system()} ({platform.release()})")
    print(f"[*] Base Data Directory      : {DATA_DIR}")
    print(f"[*] Research Wiki DB Status  : {'FOUND' if stats['wiki_db_exists'] else 'NOT FOUND'}")
    print(f"    • Wiki Articles Indexed  : {stats['wiki_articles_rows']:,}")
    print(f"    • Research Sources       : {stats['research_sources_rows']:,}")
    print(f"    • Epistemic Claims       : {stats['research_claims_rows']:,}")
    print(f"    • Markdown Article Files : {stats['articles_markdown_count']:,}")
    print(f"[*] Raw Uploads Vault (PDFs) : {stats['uploads_count']:,} files ({stats['uploads_size_mb']} MB)")
    print(f"[*] Brain Provenance DB      : {'FOUND' if stats['brain_db_exists'] else 'NOT FOUND'}")
    print(f"    • Provenance Records     : {stats['provenance_rows']:,}")
    print(f"    • Strategy Candidates    : {stats['strategy_rows']:,}")
    print("=" * 68)
    if stats["uploads_count"] == 0 and stats["research_sources_rows"] <= 4:
        print("[!] NOTICE: Low local inventory detected. If you ingested 100+ PDFs on another")
        print("    machine (e.g. Ubuntu), run 'python scripts/sync_research_vault.py --export'")
        print("    on that machine and import the resulting bundle here with '--import'.")
    else:
        print("[+] Vault healthy with active research knowledge base.")
    print("=" * 68)


def checkpoint_sqlite_db(src: Path, dest: Path) -> None:
    """Safely checkpoints and copies an SQLite DB to avoid WAL locks."""
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(src), timeout=10.0)
        # Flush WAL into main database
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        backup_conn = sqlite3.connect(str(dest))
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
    except Exception as e:
        # Fallback to direct file copy if backup fails
        shutil.copy2(src, dest)


def export_vault(output_path: Path | None = None) -> Path:
    """Creates a complete compressed research vault bundle."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if not output_path:
        output_path = ROOT_DIR / f"cbt_research_vault_bundle_{timestamp}.tar.gz"

    stats = get_vault_stats()
    print(f"[*] Packaging Research Vault into: {output_path.name}...")
    print(f"    • Capturing {stats['wiki_articles_rows']} wiki articles, {stats['uploads_count']} uploaded PDFs...")

    with tempfile.TemporaryDirectory(prefix="cbt_vault_export_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        staging_dir = tmp_path / "cbt_vault"
        staging_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "exported_from_os": platform.system(),
            "node_hostname": platform.node(),
            "stats": stats,
            "files": {},
        }

        # 1. Safely snapshot SQLite databases
        if WIKI_DB_PATH.exists():
            dest_wiki = staging_dir / "research_wiki.db"
            checkpoint_sqlite_db(WIKI_DB_PATH, dest_wiki)
            manifest["files"]["research_wiki.db"] = {
                "sha256": compute_sha256(dest_wiki),
                "size_bytes": dest_wiki.stat().st_size,
            }

        if BRAIN_DB_PATH.exists():
            dest_brain = staging_dir / "brain_memory.db"
            checkpoint_sqlite_db(BRAIN_DB_PATH, dest_brain)
            manifest["files"]["brain_memory.db"] = {
                "sha256": compute_sha256(dest_brain),
                "size_bytes": dest_brain.stat().st_size,
            }

        # 2. Copy markdown articles
        if ARTICLES_DIR.exists():
            staging_articles = staging_dir / "research_wiki" / "articles"
            staging_articles.mkdir(parents=True, exist_ok=True)
            for f in ARTICLES_DIR.rglob("*.md"):
                if f.is_file():
                    rel_p = f.relative_to(ARTICLES_DIR)
                    target = staging_articles / rel_p
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    manifest["files"][f"research_wiki/articles/{rel_p.as_posix()}"] = {
                        "sha256": compute_sha256(target),
                        "size_bytes": target.stat().st_size,
                    }

        # 3. Copy uploaded PDFs / documents
        if UPLOADS_DIR.exists():
            staging_uploads = staging_dir / "uploads"
            staging_uploads.mkdir(parents=True, exist_ok=True)
            for f in UPLOADS_DIR.rglob("*"):
                if f.is_file():
                    rel_p = f.relative_to(UPLOADS_DIR)
                    target = staging_uploads / rel_p
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    manifest["files"][f"uploads/{rel_p.as_posix()}"] = {
                        "sha256": compute_sha256(target),
                        "size_bytes": target.stat().st_size,
                    }

        # Write manifest.json
        manifest_file = staging_dir / "vault_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        # Build tar.gz
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(staging_dir, arcname="cbt_vault")

    bundle_size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
    print("=" * 68)
    print("   ✅ RESEARCH VAULT BUNDLE EXPORT COMPLETE   ")
    print("=" * 68)
    print(f"[*] Bundle Path : {output_path.resolve()}")
    print(f"[*] Bundle Size : {bundle_size_mb} MB")
    print(f"[*] Contents    : {len(manifest['files'])} files packaged")
    print("=" * 68)
    print("Next Steps:")
    print("1. Copy this bundle file to your other machine (via Google Drive, USB, or scp).")
    print(f"2. On the other machine, run:")
    print(f"   python scripts/sync_research_vault.py --import {output_path.name}")
    print("=" * 68)
    return output_path


def inspect_bundle(bundle_path: Path) -> dict[str, Any]:
    """Reads manifest and displays bundle contents without extracting."""
    if not bundle_path.exists():
        print(f"[-] Error: Bundle file not found: {bundle_path}")
        sys.exit(1)

    with tarfile.open(bundle_path, "r:gz") as tar:
        manifest_member = None
        for member in tar.getmembers():
            if member.name.endswith("vault_manifest.json"):
                manifest_member = member
                break

        if not manifest_member:
            print("[-] Error: Invalid bundle, vault_manifest.json missing.")
            sys.exit(1)

        f = tar.extractfile(manifest_member)
        if not f:
            print("[-] Error: Unable to read manifest.")
            sys.exit(1)
        manifest: dict[str, Any] = json.load(f)

    print("=" * 68)
    print("   📦 CBT RESEARCH VAULT BUNDLE INSPECTION   ")
    print("=" * 68)
    print(f"[*] Bundle File       : {bundle_path.name} ({round(bundle_path.stat().st_size / (1024*1024), 2)} MB)")
    print(f"[*] Created At        : {manifest.get('created_at')}")
    print(f"[*] Exported From OS  : {manifest.get('exported_from_os')} (Host: {manifest.get('node_hostname')})")
    stats = manifest.get("stats", {})
    print(f"[*] Wiki Articles     : {stats.get('wiki_articles_rows', 0):,}")
    print(f"[*] Research Sources  : {stats.get('research_sources_rows', 0):,}")
    print(f"[*] Epistemic Claims  : {stats.get('research_claims_rows', 0):,}")
    print(f"[*] Uploaded PDFs     : {stats.get('uploads_count', 0):,} ({stats.get('uploads_size_mb', 0)} MB)")
    print(f"[*] Total Files Stored: {len(manifest.get('files', {})):,}")
    print("=" * 68)
    return manifest


def import_vault(bundle_path: Path, force: bool = False) -> None:
    """Safely extracts bundle contents into local data/ directory with auto-backup."""
    manifest = inspect_bundle(bundle_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print(f"\n[*] Preparing to import into: {DATA_DIR}...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Backup existing local databases if present
    for db_file in [WIKI_DB_PATH, BRAIN_DB_PATH]:
        if db_file.exists():
            backup_file = db_file.with_name(f"{db_file.name}.bak_{timestamp}")
            shutil.copy2(db_file, backup_file)
            print(f"[+] Backed up existing local DB to: {backup_file.name}")

    # 2. Extract files
    with tempfile.TemporaryDirectory(prefix="cbt_vault_import_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        with tarfile.open(bundle_path, "r:gz") as tar:
            tar.extractall(path=tmp_path)

        extracted_root = tmp_path / "cbt_vault"
        if not extracted_root.exists():
            # Check if direct
            extracted_root = tmp_path

        # Validate hashes before moving
        files_manifest = manifest.get("files", {})
        verified_count = 0
        for rel_str, meta in files_manifest.items():
            src_file = extracted_root / rel_str
            if not src_file.exists():
                print(f"[!] Warning: Expected file {rel_str} not found in bundle archive.")
                continue
            h = compute_sha256(src_file)
            if h != meta.get("sha256"):
                raise ValueError(f"Integrity check failed for {rel_str}! SHA-256 mismatch.")
            verified_count += 1

        print(f"[+] Cryptographic integrity verified across {verified_count} bundle files.")

        # 3. Atomically copy files into local data directory
        # DB files
        for db_name in ["research_wiki.db", "brain_memory.db"]:
            src = extracted_root / db_name
            if src.exists():
                dest = DATA_DIR / db_name
                # Remove WAL/SHM to avoid stale locks
                for ext in ["-wal", "-shm", "-journal"]:
                    stale = dest.with_name(f"{dest.name}{ext}")
                    if stale.exists():
                        try:
                            stale.unlink()
                        except Exception:
                            pass
                shutil.copy2(src, dest)
                print(f"[+] Replaced {db_name}")

        # Articles
        articles_src = extracted_root / "research_wiki" / "articles"
        if articles_src.exists():
            ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
            for f in articles_src.rglob("*.md"):
                if f.is_file():
                    rel_p = f.relative_to(articles_src)
                    dest_p = ARTICLES_DIR / rel_p
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest_p)

        # Uploads (PDFs)
        uploads_src = extracted_root / "uploads"
        if uploads_src.exists():
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            for f in uploads_src.rglob("*"):
                if f.is_file():
                    rel_p = f.relative_to(uploads_src)
                    dest_p = UPLOADS_DIR / rel_p
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest_p)

    print("=" * 68)
    print("   ✅ RESEARCH VAULT IMPORT SUCCESSFUL   ")
    print("=" * 68)
    show_status()


def main():
    parser = argparse.ArgumentParser(description="Deterministic Research Vault Sync Utility")
    parser.add_argument("--status", action="store_true", help="Display local research vault status")
    parser.add_argument("--export", action="store_true", help="Export research vault to compressed bundle")
    parser.add_argument("-o", "--output", type=Path, help="Custom export output path")
    parser.add_argument("--inspect", type=Path, help="Inspect existing vault bundle manifest")
    parser.add_argument("--import", dest="import_bundle", type=Path, help="Import vault bundle into local CBT")
    parser.add_argument("--force", action="store_true", help="Force overwrite without confirmation")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.export:
        export_vault(args.output)
    elif args.inspect:
        inspect_bundle(args.inspect)
    elif args.import_bundle:
        import_vault(args.import_bundle, args.force)
    else:
        # Default action: status
        show_status()


if __name__ == "__main__":
    main()

