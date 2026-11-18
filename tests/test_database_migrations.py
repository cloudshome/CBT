"""
tests/test_database_migrations.py
=================================
Automated Institutional Test Suite for SQLite Database Migration Engine.
Verifies:
1. Fresh database schema migration from scratch
2. Sequential database upgrades
3. Idempotent re-execution safety
4. Cryptographic checksum tamper detection (fail-closed)
5. Atomic rollback on failure
6. WAL checkpoint coordination
7. Sequence monotonicity validation
"""

from __future__ import annotations

import sqlite3

import pytest

from core.database_migrations import (
    DatabaseMigrationEngine,
    MigrationDefinition,
    MigrationExecutionError,
    MigrationSequenceError,
    MigrationTamperingError,
)


@pytest.fixture
def sandbox_db(tmp_path):
    """Provides a fresh isolated SQLite WAL database path for each test."""
    db_file = tmp_path / "sandbox_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()
    return db_file


class TestDatabaseMigrationEngine:
    """Verifies core invariants of DatabaseMigrationEngine."""

    def test_fresh_database_migration(self, sandbox_db):
        migrations = [
            MigrationDefinition(
                migration_id="001_initial_tables",
                sequence=1,
                description="Create users and orders tables",
                up_sql="""
                CREATE TABLE test_users (id INTEGER PRIMARY KEY, username TEXT);
                CREATE TABLE test_orders (order_id TEXT PRIMARY KEY, user_id INTEGER);
                """,
            ),
            MigrationDefinition(
                migration_id="002_add_index",
                sequence=2,
                description="Add index on test_orders",
                up_sql="CREATE INDEX idx_user_orders ON test_orders(user_id);",
                verify_sql="SELECT COUNT(*) FROM test_orders;",
            ),
        ]

        records = DatabaseMigrationEngine.run_migrations(sandbox_db, migrations)
        assert len(records) == 2
        assert records[0].migration_id == "001_initial_tables"
        assert records[1].migration_id == "002_add_index"

        # Verify tables exist and user_version updated
        conn = sqlite3.connect(str(sandbox_db))
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        assert cursor.fetchone()[0] == 2

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cursor.fetchall()}
        assert "test_users" in tables
        assert "test_orders" in tables
        assert "_schema_migrations" in tables

        applied = DatabaseMigrationEngine.get_applied_migrations(conn)
        assert len(applied) == 2
        assert applied[0].status == "SUCCESS"
        conn.close()

    def test_idempotent_rerun_does_not_reapply(self, sandbox_db):
        migrations = [
            MigrationDefinition(
                migration_id="001_test",
                sequence=1,
                description="Create table",
                up_sql="CREATE TABLE t1 (id INT);",
            )
        ]

        # First run: 1 migration applied
        r1 = DatabaseMigrationEngine.run_migrations(sandbox_db, migrations)
        assert len(r1) == 1

        # Second run: 0 migrations applied
        r2 = DatabaseMigrationEngine.run_migrations(sandbox_db, migrations)
        assert len(r2) == 0

    def test_sequential_upgrade_only_applies_new(self, sandbox_db):
        m1 = MigrationDefinition(
            migration_id="001_v1",
            sequence=1,
            description="Table v1",
            up_sql="CREATE TABLE v1 (col1 TEXT);",
        )
        DatabaseMigrationEngine.run_migrations(sandbox_db, [m1])

        m2 = MigrationDefinition(
            migration_id="002_v2",
            sequence=2,
            description="Table v2",
            up_sql="CREATE TABLE v2 (col2 TEXT);",
        )
        records = DatabaseMigrationEngine.run_migrations(sandbox_db, [m1, m2])
        assert len(records) == 1
        assert records[0].migration_id == "002_v2"

    def test_tampering_detection_fails_closed(self, sandbox_db):
        original_m1 = MigrationDefinition(
            migration_id="001_tamper_test",
            sequence=1,
            description="Original statement",
            up_sql="CREATE TABLE tamper_table (id INT);",
        )
        DatabaseMigrationEngine.run_migrations(sandbox_db, [original_m1])

        # Tampered migration definition (changed up_sql after application)
        tampered_m1 = MigrationDefinition(
            migration_id="001_tamper_test",
            sequence=1,
            description="Original statement",
            up_sql="CREATE TABLE tamper_table (id INT, modified_col TEXT);",
        )

        with pytest.raises(MigrationTamperingError) as exc_info:
            DatabaseMigrationEngine.run_migrations(sandbox_db, [tampered_m1])

        assert "MIGRATION_TAMPERING_DETECTED" in str(exc_info.value)

    def test_atomic_rollback_on_failed_migration(self, sandbox_db):
        failing_migration = MigrationDefinition(
            migration_id="001_fail_test",
            sequence=1,
            description="Intentionally invalid statement",
            up_sql="""
            CREATE TABLE should_not_persist (id INT);
            THIS IS INVALID SQL STATEMENT THAT RAISES SYNTAX ERROR;
            """,
        )

        with pytest.raises(MigrationExecutionError):
            DatabaseMigrationEngine.run_migrations(sandbox_db, [failing_migration])

        # Verify transaction was completely rolled back
        conn = sqlite3.connect(str(sandbox_db))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cursor.fetchall()}
        assert "should_not_persist" not in tables

        applied = DatabaseMigrationEngine.get_applied_migrations(conn)
        assert len(applied) == 0
        conn.close()

    def test_migration_sequence_validation(self, sandbox_db):
        # Duplicate sequence numbers
        invalid_migrations = [
            MigrationDefinition("m1", 1, "d1", "CREATE TABLE a (id INT);"),
            MigrationDefinition("m2", 1, "d2", "CREATE TABLE b (id INT);"),
        ]
        with pytest.raises(MigrationSequenceError):
            DatabaseMigrationEngine.run_migrations(sandbox_db, invalid_migrations)

    def test_wal_checkpoint_coordination(self, sandbox_db):
        conn = sqlite3.connect(str(sandbox_db))
        res = DatabaseMigrationEngine.checkpoint_wal(conn, mode="PASSIVE")
        assert "busy" in res
        assert "log" in res
        assert "checkpointed" in res
        conn.close()
