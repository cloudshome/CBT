#!/usr/bin/env python3
"""
SKY / CTB — SQLite Database Maintenance, Vacuum & Growth Management Tool.

Performs:
- SQLite WAL truncate, VACUUM, and PRAGMA optimize on active databases.
- Re-indexes B-Tree tables for query latency reduction.
- Reclaims unused storage space and generates storage footprint report.
- Prunes raw upload files older than retention TTL (14 days).
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_db_maintenance")


def get_db_files(data_dir: Path) -> list[Path]:
    """Finds all primary SQLite database files."""
    if not data_dir.exists():
        return []
    db_extensions = {".db", ".sqlite", ".sqlite3"}
    return [
        p
        for p in data_dir.glob("*")
        if p.suffix in db_extensions and not p.name.endswith("-wal") and not p.name.endswith("-shm")
    ]


def _is_file_recorded(file_path: Path, data_dir: Path) -> bool:
    """Checks whether file SHA-256 hash, filename, or source_id exists in provenance/vault databases."""
    import hashlib

    try:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        file_sha256 = hasher.hexdigest()
    except Exception:
        file_sha256 = None

    filename = file_path.name
    stem = file_path.stem

    for db_name in ("brain_memory.db", "trading_logs.db"):
        db_file = data_dir / db_name
        if not db_file.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_file), timeout=5.0)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}

            # 1. immutable_sources: content_hash, source_id, source_uri
            if "immutable_sources" in tables:
                if file_sha256:
                    cur.execute(
                        "SELECT 1 FROM immutable_sources WHERE content_hash = ? OR source_id = ? OR source_uri LIKE ? LIMIT 1;",
                        (file_sha256, stem, f"%{filename}%"),
                    )
                    if cur.fetchone():
                        conn.close()
                        return True

            # 2. research_provenance_sources: source_id, source_uri
            if "research_provenance_sources" in tables:
                cur.execute(
                    "SELECT 1 FROM research_provenance_sources WHERE source_id = ? OR source_uri LIKE ? LIMIT 1;",
                    (stem, f"%{filename}%"),
                )
                if cur.fetchone():
                    conn.close()
                    return True

            # 3. research_provenance_ledger: knowledge_id, source_uri
            if "research_provenance_ledger" in tables:
                cur.execute(
                    "SELECT 1 FROM research_provenance_ledger WHERE source_uri LIKE ? OR knowledge_id = ? LIMIT 1;",
                    (f"%{filename}%", stem),
                )
                if cur.fetchone():
                    conn.close()
                    return True

            # 4. semantic_vectors: metadata_json
            if "semantic_vectors" in tables:
                cur.execute(
                    "SELECT 1 FROM semantic_vectors WHERE metadata_json LIKE ? LIMIT 1;",
                    (f"%{filename}%",),
                )
                if cur.fetchone():
                    conn.close()
                    return True

            conn.close()
        except Exception:
            pass

    return False


def prune_old_uploads(
    uploads_dir: Path, max_age_days: int = 14, require_provenance: bool = False
) -> dict[str, Any]:
    """
    Deletes raw upload files older than max_age_days whose text and embeddings
    are safely extracted and indexed in semantic_vectors / knowledge vault.
    When require_provenance=True or when provenance databases exist alongside uploads,
    verifies content hash or filename is recorded before unlinking.
    """
    if not uploads_dir.exists():
        return {"pruned_count": 0, "reclaimed_kb": 0.0}

    now = time.time()
    cutoff_sec = max_age_days * 86400.0
    pruned_count = 0
    reclaimed_bytes = 0
    data_dir = uploads_dir.parent

    # Determine if provenance verification is active:
    has_dbs = any((data_dir / db).exists() for db in ("brain_memory.db", "trading_logs.db"))
    check_provenance = require_provenance or has_dbs

    for file_path in uploads_dir.glob("**/*"):
        if file_path.is_file():
            try:
                mtime = file_path.stat().st_mtime
                if (now - mtime) > cutoff_sec:
                    if check_provenance and not _is_file_recorded(file_path, data_dir):
                        logger.debug(f"Skipping unverified upload {file_path.name}")
                        continue
                    fsize = file_path.stat().st_size
                    file_path.unlink()
                    pruned_count += 1
                    reclaimed_bytes += fsize
            except Exception as e:
                logger.warning(f"Could not prune upload {file_path.name}: {e}")

    reclaimed_kb = round(reclaimed_bytes / 1024, 2)
    logger.info(
        f"Upload TTL pruning: removed {pruned_count} files older than {max_age_days}d (Reclaimed {reclaimed_kb} KB)"
    )
    return {"pruned_count": pruned_count, "reclaimed_kb": reclaimed_kb}


def optimize_database(db_path: Path, vacuum_threshold_mb: float = 500.0) -> dict[str, Any]:
    """Performs WAL truncate, integrity check, reindex, optimize, and conditional vacuum."""
    size_before_bytes = db_path.stat().st_size
    size_after_bytes = size_before_bytes
    try:
        conn = sqlite3.connect(str(db_path), timeout=60.0)
        conn.execute("PRAGMA busy_timeout = 5000;")

        # 1. Truncate WAL checkpoint
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception as e:
            logger.debug(f"wal_checkpoint note on {db_path.name}: {e}")

        # 2. Quick Integrity check
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        row = cursor.fetchone()
        integrity = row[0] if row else "unknown"

        # 3. Re-index
        conn.execute("REINDEX;")

        # 4. Optimize query planner statistics
        conn.execute("PRAGMA optimize;")

        # 5. Reclaim unallocated disk space if size exceeds threshold
        vacuum_executed = False
        if (size_before_bytes / (1024 * 1024)) >= vacuum_threshold_mb:
            conn.execute("VACUUM;")
            vacuum_executed = True

        conn.close()

        size_after_bytes = db_path.stat().st_size if db_path.exists() else size_before_bytes
        reclaimed_kb = max(0.0, round((size_before_bytes - size_after_bytes) / 1024, 2))

        logger.info(
            f"Optimized {db_path.name}: {round(size_before_bytes/1024, 1)} KB -> {round(size_after_bytes/1024, 1)} KB (Reclaimed {reclaimed_kb} KB, vacuum={vacuum_executed})"
        )
        return {
            "database": db_path.name,
            "status": "OPTIMIZED",
            "integrity": integrity,
            "vacuum_executed": vacuum_executed,
            "size_before_kb": round(size_before_bytes / 1024, 2),
            "size_after_kb": round(size_after_bytes / 1024, 2),
            "reclaimed_kb": reclaimed_kb,
        }
    except Exception as e:
        logger.error(f"Maintenance failed on {db_path.name}: {e}")
        size_after_bytes = db_path.stat().st_size if db_path.exists() else size_before_bytes
        return {
            "database": db_path.name,
            "status": "FAILED",
            "error": str(e),
            "size_before_kb": round(size_before_bytes / 1024, 2),
            "size_after_kb": round(size_after_bytes / 1024, 2),
            "reclaimed_kb": 0.0,
        }


def run_maintenance(
    data_dir: Path, vacuum_threshold_mb: float = 500.0, upload_ttl_days: int = 14
) -> dict[str, Any]:
    """Executes full maintenance routine on all database files and upload pruning."""
    upload_stats = prune_old_uploads(data_dir / "uploads", max_age_days=upload_ttl_days)

    db_files = get_db_files(data_dir)
    if not db_files:
        return {"status": "EMPTY", "databases": [], "upload_stats": upload_stats}

    results = []
    total_reclaimed_kb = upload_stats.get("reclaimed_kb", 0.0)

    for db_path in db_files:
        res = optimize_database(db_path, vacuum_threshold_mb=vacuum_threshold_mb)
        results.append(res)
        total_reclaimed_kb += res.get("reclaimed_kb", 0.0)

    return {
        "status": "SUCCESS",
        "total_databases": len(db_files),
        "total_reclaimed_kb": round(total_reclaimed_kb, 2),
        "upload_stats": upload_stats,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="SKY / CTB Database Growth Management & Vacuum Tool")
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "data"), help="Path to data directory")
    parser.add_argument(
        "--vacuum-threshold-mb",
        type=float,
        default=500.0,
        help="Minimum DB size in MB to trigger full VACUUM",
    )
    parser.add_argument(
        "--upload-ttl-days",
        type=int,
        default=14,
        help="Retention period in days for raw upload files",
    )
    args = parser.parse_args()

    res = run_maintenance(
        Path(args.data_dir),
        vacuum_threshold_mb=args.vacuum_threshold_mb,
        upload_ttl_days=args.upload_ttl_days,
    )
    if res["status"] in ("SUCCESS", "EMPTY"):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
