"""
core/database_migrations.py
===========================
Deterministic SQLite Database Migration Engine for SKY / CBT.
Provides transactional schema evolution, cryptographic checksum verification,
tamper detection, duplicate execution prevention, and WAL checkpoint coordination.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.database_migrations")


class MigrationError(Exception):
    """Base exception for database migration errors."""


class MigrationTamperingError(MigrationError):
    """Raised when an already applied migration's checksum does not match its current definition."""


class MigrationSequenceError(MigrationError):
    """Raised when migration sequence numbers are non-monotonic or duplicated."""


class MigrationExecutionError(MigrationError):
    """Raised when a migration statement fails during execution."""


@dataclass(frozen=True)
class MigrationDefinition:
    """Immutable definition of a database schema migration."""

    migration_id: str
    sequence: int
    description: str
    up_sql: str
    verify_sql: str | None = None

    def compute_checksum(self) -> str:
        """Computes the deterministic SHA-256 checksum of the migration payload."""
        payload = f"{self.sequence}:{self.migration_id}:{self.up_sql.strip()}".encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class MigrationRecord:
    """Record of an applied database schema migration."""

    migration_id: str
    sequence: int
    description: str
    sha256_checksum: str
    applied_at: str
    execution_duration_ms: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "sequence": self.sequence,
            "description": self.description,
            "sha256_checksum": self.sha256_checksum,
            "applied_at": self.applied_at,
            "execution_duration_ms": self.execution_duration_ms,
            "status": self.status,
        }


class DatabaseMigrationEngine:
    """
    Authoritative migration engine governing SQLite schema evolution.
    """

    MIGRATIONS_TABLE = "_schema_migrations"

    @classmethod
    def ensure_ledger(cls, conn: sqlite3.Connection) -> None:
        """Ensures the migration ledger table exists in the target database."""
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.MIGRATIONS_TABLE} (
                migration_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL,
                description TEXT NOT NULL,
                sha256_checksum TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                execution_duration_ms REAL NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_migration_seq ON {cls.MIGRATIONS_TABLE}(sequence);"
        )
        conn.commit()

    @classmethod
    def get_applied_migrations(cls, conn: sqlite3.Connection) -> list[MigrationRecord]:
        """Retrieves all applied migrations ordered by sequence."""
        cls.ensure_ledger(conn)
        cursor = conn.execute(
            f"""
            SELECT migration_id, sequence, description, sha256_checksum,
                   applied_at, execution_duration_ms, status
            FROM {cls.MIGRATIONS_TABLE}
            ORDER BY sequence ASC;
            """
        )
        records = []
        for r in cursor.fetchall():
            records.append(
                MigrationRecord(
                    migration_id=r[0],
                    sequence=int(r[1]),
                    description=r[2],
                    sha256_checksum=r[3],
                    applied_at=str(r[4]),
                    execution_duration_ms=float(r[5]),
                    status=r[6],
                )
            )
        return records

    @classmethod
    def verify_checksums(
        cls, conn: sqlite3.Connection, migrations: list[MigrationDefinition]
    ) -> None:
        """
        Verifies that previously applied migrations have not been altered or tampered with.
        Fails closed on any SHA-256 mismatch.
        """
        applied_map = {m.migration_id: m for m in cls.get_applied_migrations(conn)}
        for m in migrations:
            if m.migration_id in applied_map:
                applied = applied_map[m.migration_id]
                expected_sha = m.compute_checksum()
                if applied.sha256_checksum != expected_sha:
                    msg = (
                        f"MIGRATION_TAMPERING_DETECTED: Checksum mismatch for migration '{m.migration_id}' "
                        f"(sequence {m.sequence}). Applied={applied.sha256_checksum[:12]} vs Current={expected_sha[:12]}. "
                        f"Database schema definition has been modified after execution."
                    )
                    logger.critical(msg)
                    raise MigrationTamperingError(msg)

    @classmethod
    def validate_migration_sequence(cls, migrations: list[MigrationDefinition]) -> None:
        """Validates that candidate migrations have strictly monotonic, unique sequence numbers."""
        seen_seqs: set[int] = set()
        seen_ids: set[str] = set()
        last_seq = 0

        for m in sorted(migrations, key=lambda x: x.sequence):
            if m.sequence in seen_seqs:
                raise MigrationSequenceError(
                    f"Duplicate migration sequence number {m.sequence} in '{m.migration_id}'."
                )
            if m.migration_id in seen_ids:
                raise MigrationSequenceError(f"Duplicate migration identifier '{m.migration_id}'.")
            if m.sequence <= last_seq:
                raise MigrationSequenceError(
                    f"Non-monotonic sequence: {m.sequence} <= {last_seq} in '{m.migration_id}'."
                )
            seen_seqs.add(m.sequence)
            seen_ids.add(m.migration_id)
            last_seq = m.sequence

    @classmethod
    def checkpoint_wal(cls, conn: sqlite3.Connection, mode: str = "PASSIVE") -> dict[str, int]:
        """
        Executes safe SQLite WAL checkpointing.
        Modes: PASSIVE, FULL, RESTART, TRUNCATE.
        """
        clean_mode = mode.upper().strip()
        if clean_mode not in ("PASSIVE", "FULL", "RESTART", "TRUNCATE"):
            clean_mode = "PASSIVE"
        try:
            cursor = conn.execute(f"PRAGMA wal_checkpoint({clean_mode});")
            row = cursor.fetchone()
            if row:
                return {"busy": row[0], "log": row[1], "checkpointed": row[2]}
        except Exception as e:
            logger.warning(f"WAL checkpoint ({clean_mode}) notice: {e}")
        return {"busy": 0, "log": 0, "checkpointed": 0}

    @classmethod
    def _split_sql_statements(cls, script: str) -> list[str]:
        """Splits an SQL script into discrete statements using SQLite's native tokenizer."""
        stmts = []
        accum = []
        for line in script.splitlines(True):
            accum.append(line)
            candidate = "".join(accum)
            if sqlite3.complete_statement(candidate):
                s = candidate.strip()
                if s:
                    stmts.append(s)
                accum = []
        if accum:
            s = "".join(accum).strip()
            if s:
                stmts.append(s)
        return stmts

    @classmethod
    def apply_single_migration(
        cls, conn: sqlite3.Connection, migration: MigrationDefinition
    ) -> MigrationRecord:
        """
        Executes a single migration within an atomic transaction.
        Updates user_version and records into ledger on success; rolls back on error.
        """
        cls.ensure_ledger(conn)
        checksum = migration.compute_checksum()
        t_start = time.perf_counter()

        try:
            # Atomic transaction boundary
            conn.execute("BEGIN IMMEDIATE;")

            # Execute migration DDL/DML statements individually within the transaction
            # (executescript() issues an implicit COMMIT which defeats transaction rollback)
            for stmt in cls._split_sql_statements(migration.up_sql):
                conn.execute(stmt)

            # Optional post-migration verification query
            if migration.verify_sql:
                for verify_stmt in cls._split_sql_statements(migration.verify_sql):
                    conn.execute(verify_stmt)

            duration_ms = (time.perf_counter() - t_start) * 1000.0

            # Record into ledger
            conn.execute(
                f"""
                INSERT INTO {cls.MIGRATIONS_TABLE} (
                    migration_id, sequence, description, sha256_checksum,
                    execution_duration_ms, status
                ) VALUES (?, ?, ?, ?, ?, 'SUCCESS');
                """,
                (
                    migration.migration_id,
                    migration.sequence,
                    migration.description,
                    checksum,
                    duration_ms,
                ),
            )

            # Update SQLite user_version to reflect the latest migration sequence
            conn.execute(f"PRAGMA user_version = {migration.sequence};")
            conn.commit()

            logger.info(
                f"Applied migration '{migration.migration_id}' (seq {migration.sequence}) in {duration_ms:.2f}ms"
            )
            return MigrationRecord(
                migration_id=migration.migration_id,
                sequence=migration.sequence,
                description=migration.description,
                sha256_checksum=checksum,
                applied_at=str(time.time()),
                execution_duration_ms=duration_ms,
                status="SUCCESS",
            )
        except Exception as exc:
            conn.rollback()
            msg = f"MigrationExecutionError in '{migration.migration_id}' (sequence {migration.sequence}): {exc}"
            logger.critical(msg)
            raise MigrationExecutionError(msg) from exc

    @classmethod
    def run_migrations(
        cls,
        db_path_or_conn: Path | str | sqlite3.Connection,
        migrations: list[MigrationDefinition],
        auto_checkpoint: bool = True,
    ) -> list[MigrationRecord]:
        """
        Executes all unapplied candidate migrations in deterministic sequential order.
        """
        cls.validate_migration_sequence(migrations)

        should_close = False
        if isinstance(db_path_or_conn, sqlite3.Connection):
            conn = db_path_or_conn
        else:
            db_path = Path(db_path_or_conn)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), timeout=15.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA foreign_keys=ON;")
            should_close = True

        try:
            # 1. Verify tamper integrity on already applied migrations
            cls.verify_checksums(conn, migrations)

            # 2. Identify unapplied migrations
            applied_ids = {m.migration_id for m in cls.get_applied_migrations(conn)}
            sorted_candidates = sorted(migrations, key=lambda x: x.sequence)
            pending = [m for m in sorted_candidates if m.migration_id not in applied_ids]

            if not pending:
                logger.debug("Database is already up to date. Zero pending migrations.")
                return []

            # 3. Apply pending migrations sequentially
            applied_records: list[MigrationRecord] = []
            for migration in pending:
                record = cls.apply_single_migration(conn, migration)
                applied_records.append(record)

            # 4. Checkpoint WAL upon completion
            if auto_checkpoint:
                cls.checkpoint_wal(conn, mode="PASSIVE")

            return applied_records
        finally:
            if should_close:
                conn.close()
