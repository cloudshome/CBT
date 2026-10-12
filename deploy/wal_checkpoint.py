#!/usr/bin/env python3
"""
deploy/wal_checkpoint.py
========================
SKY / CBT — SQLite WAL Checkpoint Utility

Runs PRAGMA wal_checkpoint(TRUNCATE) on all 4 production SQLite databases.
This prevents WAL files from growing unbounded during 24/7 continuous trading.

The trading_logs.db-wal file was already 4MB — left unchecked during high-write
periods this can reach hundreds of MB.

Run schedule (via crontab_ubuntu.sh):
    Daily at 04:00 UTC:  python3 deploy/wal_checkpoint.py

Safe to run while the stack is live — TRUNCATE checkpoint mode completes
atomically once all readers have finished, never blocking active writes.
"""

import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WAL-CHECKPOINT] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger(__name__)

# Resolve data directory relative to this script
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT_DIR / "data"))

DATABASES = [
    "market_data.db",
    "brain_memory.db",
    "trading_logs.db",
    "experiment_store.db",
]


def checkpoint_db(db_path: Path) -> dict:
    """
    Run PRAGMA wal_checkpoint(TRUNCATE) on a single SQLite database.

    Returns a dict with:
        busy    - number of frames in the WAL not yet checkpointed
        log     - total number of frames in WAL
        checkpointed - frames successfully written to the database file
    """
    result = {"db": db_path.name, "status": "ok", "busy": 0, "log": 0, "checkpointed": 0}
    if not db_path.exists():
        result["status"] = "skipped (not found)"
        return result

    wal_path = db_path.with_suffix(".db-wal")
    wal_size_before = wal_path.stat().st_size if wal_path.exists() else 0

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        # TRUNCATE mode: checkpoint and zero-out the WAL file
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        conn.close()

        if row:
            result["busy"] = row[0]
            result["log"] = row[1]
            result["checkpointed"] = row[2]

        wal_size_after = wal_path.stat().st_size if wal_path.exists() else 0
        saved_mb = (wal_size_before - wal_size_after) / (1024 * 1024)

        log.info(
            f"✓ {db_path.name}: "
            f"log={result['log']} frames, "
            f"checkpointed={result['checkpointed']}, "
            f"busy={result['busy']}, "
            f"WAL {wal_size_before/1024:.1f}KB → {wal_size_after/1024:.1f}KB "
            f"(saved {saved_mb:.2f}MB)"
        )
    except sqlite3.OperationalError as exc:
        result["status"] = f"error: {exc}"
        log.error(f"✗ {db_path.name}: {exc}")

    return result


def main():
    log.info("=" * 60)
    log.info(f"SKY / CBT WAL Checkpoint — {datetime.now(UTC).isoformat()}")
    log.info(f"Data directory: {DATA_DIR}")
    log.info("=" * 60)

    results = []
    for db_name in DATABASES:
        db_path = DATA_DIR / db_name
        r = checkpoint_db(db_path)
        results.append(r)
        time.sleep(0.5)  # small pause between databases to avoid I/O spike

    errors = [r for r in results if "error" in r["status"]]
    log.info("=" * 60)
    if errors:
        log.warning(f"Checkpoint completed with {len(errors)} error(s).")
        for e in errors:
            log.warning(f"  - {e['db']}: {e['status']}")
    else:
        log.info("All WAL checkpoints completed successfully.")
    log.info("=" * 60)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
