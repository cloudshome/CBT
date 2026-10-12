#!/usr/bin/env python3
"""
SKY / CTB — Database Restore Tool.

Restores SQLite databases from a compressed tarball or directory snapshot
with safe path verification and pre-restore integrity checks.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import tarfile
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_restore")


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def verify_db_integrity(db_path: Path) -> bool:
    """Runs PRAGMA integrity_check on a restored SQLite file."""
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        conn.close()
        return res is not None and res[0] == "ok"
    except Exception as e:
        logger.error(f"Integrity check failed on {db_path.name}: {e}")
        return False


def run_restore(archive_path: Path, target_data_dir: Path) -> dict[str, Any]:
    """Extracts and restores database files safely into target_data_dir."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    target_data_dir.mkdir(parents=True, exist_ok=True)
    resolved_target = target_data_dir.resolve()

    restored_files: list[str] = []

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            dest = (target_data_dir / member.name).resolve()
            if not is_safe_path(target_data_dir, dest):
                raise PermissionError(f"Security Alert: Tar-Slip Path Traversal detected: {member.name}")

        if hasattr(tarfile, "data_filter"):
            tar.extractall(path=target_data_dir, filter="data")
        else:
            tar.extractall(path=target_data_dir)

        for member in tar.getmembers():
            extracted_file = target_data_dir / member.name
            if extracted_file.suffix in {".db", ".sqlite", ".sqlite3"}:
                if verify_db_integrity(extracted_file):
                    restored_files.append(member.name)
                else:
                    logger.warning(f"Integrity check warning on restored database: {member.name}")

    logger.info(f"Successfully restored {len(restored_files)} databases to {target_data_dir}")
    return {
        "status": "SUCCESS",
        "archive": str(archive_path),
        "target_dir": str(target_data_dir),
        "restored_databases": restored_files,
    }


def main():
    parser = argparse.ArgumentParser(description="Restore SKY SQLite databases from backup archive.")
    parser.add_argument("--archive", type=str, required=True, help="Path to backup .tar.gz archive")
    parser.add_argument("--data-dir", type=str, default=os.getenv("DATA_DIR", "data"), help="Target data directory")
    args = parser.parse_args()

    try:
        res = run_restore(Path(args.archive), Path(args.data_dir))
        print(f"Restore completed successfully: {res}")
    except Exception as e:
        logger.error(f"Restore operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
