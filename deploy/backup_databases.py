#!/usr/bin/env python3
"""
SKY / CTB — Online Non-Blocking SQLite Database Backup Tool.

Uses the official SQLite Online Backup API (sqlite3.connect().backup())
to safely snapshot all production databases while the trading engine is actively running
without thread lockups or database corruption.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import logging
import os
import shutil
import sqlite3
import sys
import tarfile
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_backup")


def get_db_files(data_dir: Path) -> List[Path]:
    """Finds all SQLite database files in the data directory."""
    if not data_dir.exists():
        return []
    
    # Common SQLite filenames in SKY
    db_extensions = {".db", ".sqlite", ".sqlite3"}
    db_files = [p for p in data_dir.glob("*") if p.suffix in db_extensions and not p.name.endswith("-wal") and not p.name.endswith("-shm")]
    return db_files


def backup_single_database(source_path: Path, dest_path: Path) -> bool:
    """Performs non-blocking online backup of a single SQLite database."""
    try:
        source_conn = sqlite3.connect(str(source_path), timeout=30.0)
        dest_conn = sqlite3.connect(str(dest_path))
        
        with dest_conn:
            source_conn.backup(dest_conn, pages=100, sleep=0.01)
        
        dest_conn.close()
        source_conn.close()
        logger.info(f"Successfully backed up {source_path.name} -> {dest_path.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to backup {source_path.name}: {e}")
        return False


def run_backup(data_dir: Path, backup_root: Path, retention_days: int = 14) -> Dict[str, Any]:
    """Executes full online database backup and creates timestamped compressed archive."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_root.mkdir(parents=True, exist_ok=True)
    temp_dir = backup_root / f"temp_{timestamp}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    db_files = get_db_files(data_dir)
    if not db_files:
        logger.warning(f"No SQLite database files found in {data_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"status": "EMPTY", "databases_backed_up": 0}

    backed_up_count = 0
    for db_path in db_files:
        dest_db = temp_dir / db_path.name
        if backup_single_database(db_path, dest_db):
            backed_up_count += 1

    archive_path = backup_root / f"cbt_backup_{timestamp}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in temp_dir.glob("*"):
            tar.add(file_path, arcname=file_path.name)

    shutil.rmtree(temp_dir, ignore_errors=True)
    archive_size_kb = round(archive_path.stat().st_size / 1024, 2)
    logger.info(f"Compressed archive created: {archive_path.name} ({archive_size_kb} KB)")

    # Prune old backups
    pruned_count = 0
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=retention_days)

    for old_archive in backup_root.glob("cbt_backup_*.tar.gz"):
        mtime = datetime.datetime.fromtimestamp(old_archive.stat().st_mtime, tz=datetime.timezone.utc)
        if mtime < cutoff:
            old_archive.unlink()
            pruned_count += 1
            logger.info(f"Pruned expired backup: {old_archive.name}")

    return {
        "status": "SUCCESS",
        "archive_file": str(archive_path),
        "archive_size_kb": archive_size_kb,
        "databases_backed_up": backed_up_count,
        "databases_total": len(db_files),
        "pruned_archives": pruned_count,
        "timestamp": timestamp,
    }


def main():
    parser = argparse.ArgumentParser(description="SKY / CTB SQLite Online Database Backup Tool")
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "data"), help="Path to data directory")
    parser.add_argument("--backup-dir", default=None, help="Path to backup storage directory")
    parser.add_argument("--retention-days", type=int, default=14, help="Days to retain historical backups")
    args = parser.parse_args()

    data_path = Path(args.data_dir)
    backup_path = Path(args.backup_dir) if args.backup_dir else data_path / "backups"

    res = run_backup(data_path, backup_path, args.retention_days)
    if res["status"] == "SUCCESS":
        sys.exit(0)
    sys.exit(1 if res["databases_total"] > 0 else 0)


if __name__ == "__main__":
    main()
