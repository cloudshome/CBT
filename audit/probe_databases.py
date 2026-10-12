"""
audit/probe_databases.py
========================
Forensic database inspection script for SQLite databases in data/.
Measures page sizes, pragmas, journal modes, WAL checkpoints, table row counts, and schema stats.
"""

import sqlite3
from pathlib import Path

DATA_DIR = Path("data")

def probe_db(db_path: Path):
    print(f"\n{'='*70}")
    print(f"DATABASE: {db_path.name} ({db_path.stat().st_size:,} bytes)")
    wal_path = db_path.with_name(db_path.name + "-wal")
    shm_path = db_path.with_name(db_path.name + "-shm")
    print(f"  WAL file: {wal_path.name} -> {wal_path.stat().st_size if wal_path.exists() else 0:,} bytes")
    print(f"  SHM file: {shm_path.name} -> {shm_path.stat().st_size if shm_path.exists() else 0:,} bytes")

    conn = sqlite3.connect(str(db_path), timeout=5.0)
    cursor = conn.cursor()

    pragmas = [
        "page_size",
        "page_count",
        "journal_mode",
        "synchronous",
        "busy_timeout",
        "wal_autocheckpoint",
        "foreign_keys",
        "auto_vacuum",
        "cache_size",
        "user_version",
    ]

    print("\n--- PRAGMAS ---")
    for p in pragmas:
        cursor.execute(f"PRAGMA {p};")
        val = cursor.fetchone()
        print(f"  {p:20s}: {val[0] if val else 'N/A'}")

    print("\n--- TABLES & ROW COUNTS ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cursor.fetchall()]
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM \"{t}\";")
            count = cursor.fetchone()[0]
            # Check indices
            cursor.execute(f"PRAGMA index_list(\"{t}\");")
            indices = [idx[1] for idx in cursor.fetchall()]
            print(f"  Table: {t:30s} | Rows: {count:10,d} | Indices: {len(indices)} ({', '.join(indices[:3])})")
        except Exception as e:
            print(f"  Table: {t:30s} | Error: {e}")

    conn.close()

def main():
    db_files = list(DATA_DIR.glob("*.db"))
    for db in db_files:
        probe_db(db)

if __name__ == "__main__":
    main()
