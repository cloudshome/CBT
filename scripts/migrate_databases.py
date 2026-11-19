#!/usr/bin/env python3
"""
scripts/migrate_databases.py
============================
Authoritative CLI Tool for Deterministic SQLite Database Migrations in SKY / CBT.
Audits, verifies checksums, and applies schema migrations across production SQLite databases.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.database_migrations import (
    DatabaseMigrationEngine,
    MigrationDefinition,
    MigrationTamperingError,
)

# Standard Institutional Schema Migrations for SKY Trading Logs Database
TRADING_LOGS_MIGRATIONS: list[MigrationDefinition] = [
    MigrationDefinition(
        migration_id="001_core_trading_ledgers",
        sequence=1,
        description="Foundational shadow positions and audit events schemas",
        up_sql="""
        CREATE TABLE IF NOT EXISTS shadow_positions (
            position_id TEXT PRIMARY KEY,
            opened_at INTEGER NOT NULL,
            closed_at INTEGER,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            size REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            unrealized_pnl REAL DEFAULT 0.0,
            realized_pnl REAL DEFAULT 0.0,
            status TEXT DEFAULT 'OPEN',
            trailing_stop REAL,
            breakeven_triggered INTEGER DEFAULT 0,
            entry_reason TEXT,
            exit_reason TEXT,
            book_id TEXT DEFAULT 'MAIN_SOVEREIGN',
            initial_stop_loss REAL,
            fee_usd REAL DEFAULT 0.0,
            correlation_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_pos_status ON shadow_positions(status);
        CREATE INDEX IF NOT EXISTS idx_shadow_pos_sym ON shadow_positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_shadow_pos_cid ON shadow_positions(correlation_id);
        """,
        verify_sql="SELECT COUNT(*) FROM shadow_positions;",
    ),
    MigrationDefinition(
        migration_id="002_audit_event_ledger",
        sequence=2,
        description="Immutable system audit events table with correlation index",
        up_sql="""
        CREATE TABLE IF NOT EXISTS system_audit_events (
            event_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            severity TEXT NOT NULL,
            reason TEXT NOT NULL,
            details_json TEXT,
            software_version TEXT NOT NULL,
            correlation_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_audit_type ON system_audit_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_sym ON system_audit_events(symbol);
        CREATE INDEX IF NOT EXISTS idx_audit_cid ON system_audit_events(correlation_id);
        """,
        verify_sql="SELECT COUNT(*) FROM system_audit_events;",
    ),
]


def audit_and_migrate(
    db_path: Path, migrations: list[MigrationDefinition], check_only: bool = False
) -> bool:
    """Audits or applies migrations to a database file."""
    print(f"\n[*] Inspecting database: {db_path.name}")
    if not db_path.exists():
        print(f"    Notice: Database file does not exist yet at {db_path}.")
        if check_only:
            return True

    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        applied = DatabaseMigrationEngine.get_applied_migrations(conn)
        applied_map = {m.migration_id: m for m in applied}
        print(f"    Applied migrations count: {len(applied)}")

        # Verify integrity of already applied migrations
        DatabaseMigrationEngine.verify_checksums(conn, migrations)
        print("    [PASS] All existing migration checksums match cryptographic signatures.")

        pending = [m for m in migrations if m.migration_id not in applied_map]
        print(f"    Pending migrations count: {len(pending)}")
        for p in pending:
            print(f"      - Seq {p.sequence}: {p.migration_id} ({p.description})")

        if check_only:
            conn.close()
            return True

        if pending:
            print("    [*] Applying pending migrations...")
            applied_records = DatabaseMigrationEngine.run_migrations(conn, migrations)
            print(f"    [SUCCESS] Successfully applied {len(applied_records)} migration(s).")
        else:
            print(
                "    [UP TO DATE] Database schema is fully aligned with current code definitions."
            )

        conn.close()
        return True
    except MigrationTamperingError as e:
        print(f"    [CRITICAL FAIL] Checksum tamper detected: {e}")
        return False
    except Exception as e:
        print(f"    [FAIL] Error migrating {db_path.name}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="SKY / CBT SQLite Database Migration CLI")
    parser.add_argument(
        "--data-dir", default=os.getenv("DATA_DIR", "data"), help="Path to data directory"
    )
    parser.add_argument(
        "--check-only", action="store_true", help="Audit and verify checksums without applying"
    )
    parser.add_argument(
        "--checkpoint", action="store_true", help="Execute SQLite WAL checkpoint on all databases"
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    trading_db = Path(os.getenv("TRADING_LOGS_DB_PATH", str(data_dir / "trading_logs.db")))

    success = audit_and_migrate(trading_db, TRADING_LOGS_MIGRATIONS, check_only=args.check_only)
    if not success:
        sys.exit(1)

    print("\n[✓] Database migration audit complete.")


if __name__ == "__main__":
    main()
