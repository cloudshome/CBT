#!/usr/bin/env python3
"""
SKY / CTB — SQLite Database Maintenance, Vacuum & Growth Management Tool.

Performs:
- SQLite VACUUM and PRAGMA optimize on active databases.
- Re-indexes B-Tree tables for query latency reduction.
- Reclaims unused storage space and generates storage footprint report.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_db_maintenance")


def get_db_files(data_dir: Path) -> List[Path]:
    """Finds all primary SQLite database files."""
    if not data_dir.exists():
        return []
    db_extensions = {".db", ".sqlite", ".sqlite3"}
    return [p for p in data_dir.glob("*") if p.suffix in db_extensions and not p.name.endswith("-wal") and not p.name.endswith("-shm")]


def optimize_database(db_path: Path) -> Dict[str, Any]:
    """Performs integrity check, reindex, and vacuum on a single SQLite database."""
    size_before_bytes = db_path.stat().st_size
    try:
        conn = sqlite3.connect(str(db_path), timeout=60.0)
        conn.execute("PRAGMA busy_timeout = 5000;")
        
        # 1. Quick Integrity check
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        integrity = cursor.fetchone()[0]
        
        # 2. Re-index
        conn.execute("REINDEX;")
        
        # 3. Optimize query planner statistics
        conn.execute("PRAGMA optimize;")
        
        # 4. Reclaim unallocated disk space
        conn.execute("VACUUM;")
        
        conn.close()
        
        size_after_bytes = db_path.stat().st_size
        reclaimed_kb = max(0.0, round((size_before_bytes - size_after_bytes) / 1024, 2))
        
        logger.info(f"Optimized {db_path.name}: {round(size_before_bytes/1024, 1)} KB -> {round(size_after_bytes/1024, 1)} KB (Reclaimed {reclaimed_kb} KB)")
        return {
            "database": db_path.name,
            "status": "OPTIMIZED",
            "integrity": integrity,
            "size_before_kb": round(size_before_bytes / 1024, 2),
            "size_after_kb": round(size_after_bytes / 1024, 2),
            "reclaimed_kb": reclaimed_kb,
        }
    except Exception as e:
        logger.error(f"Maintenance failed on {db_path.name}: {e}")
        return {
            "database": db_path.name,
            "status": "FAILED",
            "error": str(e),
            "size_before_kb": round(size_before_bytes / 1024, 2),
            "size_after_kb": round(size_before_bytes / 1024, 2),
            "reclaimed_kb": 0.0,
        }


def run_maintenance(data_dir: Path) -> Dict[str, Any]:
    """Executes full maintenance routine on all database files."""
    db_files = get_db_files(data_dir)
    if not db_files:
        return {"status": "EMPTY", "databases": []}

    results = []
    total_reclaimed_kb = 0.0

    for db_path in db_files:
        res = optimize_database(db_path)
        results.append(res)
        total_reclaimed_kb += res.get("reclaimed_kb", 0.0)

    return {
        "status": "SUCCESS",
        "total_databases": len(db_files),
        "total_reclaimed_kb": round(total_reclaimed_kb, 2),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="SKY / CTB Database Growth Management & Vacuum Tool")
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "data"), help="Path to data directory")
    args = parser.parse_args()

    res = run_maintenance(Path(args.data_dir))
    if res["status"] in ("SUCCESS", "EMPTY"):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
