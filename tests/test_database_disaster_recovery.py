"""
Unit and Adversarial Test Suite for SQLite Disaster Recovery Engine & Backup Verification.
Guarantees:
- Safe inspection without path traversal vulnerabilities.
- PRAGMA integrity_check and PRAGMA foreign_key_check fail-closed audits.
- Atomic staged restoration preventing partial writes.
- Deterministic RTO (<= 30s) and RPO (<= 1s) measurements during DR drills.
- 100% test isolation via tmp_path fixtures.
"""

from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.database_recovery import (
    BackupCorruptionError,
    DisasterRecoveryEngine,
)


def create_sample_db(db_path: Path, with_fks: bool = True, break_fk: bool = False) -> None:
    """Helper to create a well-formed SQLite database with optional foreign keys."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 42;")

    if with_fks:
        cursor.execute("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            );
        """)
        cursor.execute("INSERT INTO accounts (id, name) VALUES (1, 'Treasury');")
        cursor.execute("INSERT INTO accounts (id, name) VALUES (2, 'ShadowFund');")

        if break_fk:
            # Foreign keys are OFF by default in SQLite, allowing inserting an orphaned row
            cursor.execute(
                "INSERT INTO orders (id, account_id, symbol) VALUES (101, 999, 'BTCUSDT');"
            )
        else:
            cursor.execute(
                "INSERT INTO orders (id, account_id, symbol) VALUES (101, 1, 'BTCUSDT');"
            )
            cursor.execute(
                "INSERT INTO orders (id, account_id, symbol) VALUES (102, 2, 'ETHUSDT');"
            )
    else:
        cursor.execute("CREATE TABLE simple_log (id INTEGER PRIMARY KEY, msg TEXT);")
        cursor.execute("INSERT INTO simple_log (msg) VALUES ('test entry');")

    conn.commit()
    conn.close()


def package_tar_gz(source_files: list[Path], archive_path: Path) -> Path:
    """Helper to package database files into a .tar.gz archive."""
    with tarfile.open(archive_path, "w:gz") as tar:
        for f in source_files:
            tar.add(f, arcname=f.name)
    return archive_path


class TestDisasterRecoveryArchiveSafety:
    """Tests archive format, hashing, and defense against malicious structures."""

    def test_inspect_clean_archive_metadata(self, tmp_path: Path) -> None:
        db1 = tmp_path / "trading_logs.db"
        create_sample_db(db1)
        archive = package_tar_gz([db1], tmp_path / "backup_20261119.tar.gz")

        engine = DisasterRecoveryEngine()
        meta = engine.inspect_archive(archive)

        assert meta.archive_path == str(archive)
        assert len(meta.sha256) == 64
        assert meta.size_bytes > 0
        assert "trading_logs.db" in meta.contained_files

    def test_path_traversal_detection_in_tar(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "evil_backup.tar.gz"
        payload = b"FAKE DATABASE CONTENT"

        # Create a malicious tarball with ../ path escape
        with tarfile.open(archive_path, "w:gz") as tar:
            info = tarfile.TarInfo(name="../etc/evil.db")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

        engine = DisasterRecoveryEngine()
        with pytest.raises(BackupCorruptionError, match="Path traversal"):
            engine.inspect_archive(archive_path)

    def test_corrupted_or_truncated_archive_rejected(self, tmp_path: Path) -> None:
        corrupt_archive = tmp_path / "truncated.tar.gz"
        corrupt_archive.write_bytes(b"\x1f\x8b\x08\x00corrupted_garbage_bytes")

        engine = DisasterRecoveryEngine()
        with pytest.raises(BackupCorruptionError, match="Corrupt or invalid tar archive"):
            engine.inspect_archive(corrupt_archive)


class TestDatabaseIntegrityAudits:
    """Tests PRAGMA integrity_check, foreign keys, and corrupt page handling."""

    def test_clean_database_integrity_audit(self, tmp_path: Path) -> None:
        db = tmp_path / "clean.db"
        create_sample_db(db, with_fks=True, break_fk=False)

        engine = DisasterRecoveryEngine()
        report = engine.verify_database_integrity(db)

        assert report.integrity_check_passed is True
        assert report.integrity_check_output == "ok"
        assert report.foreign_keys_passed is True
        assert len(report.foreign_key_violations) == 0
        assert report.user_version == 42
        assert report.tables["accounts"] == 2
        assert report.tables["orders"] == 2

    def test_foreign_key_violation_caught(self, tmp_path: Path) -> None:
        db = tmp_path / "broken_fk.db"
        create_sample_db(db, with_fks=True, break_fk=True)

        engine = DisasterRecoveryEngine()
        report = engine.verify_database_integrity(db)

        assert report.integrity_check_passed is True  # standard sqlite integrity passes
        assert report.foreign_keys_passed is False  # FK check catches orphaned order
        assert len(report.foreign_key_violations) == 1
        assert report.foreign_key_violations[0]["table"] == "orders"
        assert report.foreign_key_violations[0]["parent_table"] == "accounts"

    def test_corrupted_sqlite_page_fails_audit(self, tmp_path: Path) -> None:
        db = tmp_path / "corrupted_page.db"
        create_sample_db(db)

        # Overwrite file header to simulate severe disk/page corruption
        raw = bytearray(db.read_bytes())
        raw[:16] = b"CORRUPTED_DISK!!"
        db.write_bytes(bytes(raw))

        engine = DisasterRecoveryEngine()
        report = engine.verify_database_integrity(db)
        assert report.integrity_check_passed is False


class TestStagedRestorationAndDisasterRecoveryDrill:
    """Tests atomic restore and institutional disaster recovery drills."""

    def test_dry_run_restoration_leaves_target_empty(self, tmp_path: Path) -> None:
        db = tmp_path / "source.db"
        create_sample_db(db)
        archive = package_tar_gz([db], tmp_path / "backup.tar.gz")

        target_dir = tmp_path / "target_store"
        target_dir.mkdir()

        engine = DisasterRecoveryEngine()
        result = engine.restore_from_archive(archive, target_dir=target_dir, dry_run=True)

        assert result.success is True
        # Target directory should remain untouched in dry_run
        assert list(target_dir.iterdir()) == []

    def test_broken_foreign_key_aborts_restoration_and_protects_target(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "bad.db"
        create_sample_db(db, break_fk=True)
        archive = package_tar_gz([db], tmp_path / "bad_backup.tar.gz")

        target_dir = tmp_path / "target_live"
        target_dir.mkdir()
        sentinel_file = target_dir / "live_existing.txt"
        sentinel_file.write_text("live production state")

        engine = DisasterRecoveryEngine()
        result = engine.restore_from_archive(archive, target_dir=target_dir, dry_run=False)

        assert result.success is False
        assert "Foreign key violations" in (result.error or "")
        # Live state preserved
        assert sentinel_file.exists()
        assert not (target_dir / "bad.db").exists()

    def test_successful_atomic_restoration(self, tmp_path: Path) -> None:
        db1 = tmp_path / "trading_logs.db"
        db2 = tmp_path / "market_cache.db"
        create_sample_db(db1)
        create_sample_db(db2, with_fks=False)
        archive = package_tar_gz([db1, db2], tmp_path / "cbt_backup_valid.tar.gz")

        target_dir = tmp_path / "restored_production"
        engine = DisasterRecoveryEngine()
        result = engine.restore_from_archive(archive, target_dir=target_dir)

        assert result.success is True
        assert (target_dir / "trading_logs.db").exists()
        assert (target_dir / "market_cache.db").exists()
        assert len(result.integrity_reports) == 2
        assert all(
            r.integrity_check_passed and r.foreign_keys_passed for r in result.integrity_reports
        )

    def test_disaster_recovery_drill_with_rto_and_rpo_targets(self, tmp_path: Path) -> None:
        db = tmp_path / "active_trading.db"
        create_sample_db(db)
        archive = package_tar_gz([db], tmp_path / "cbt_backup_drill.tar.gz")

        target_dir = tmp_path / "dr_recovery_zone"
        engine = DisasterRecoveryEngine()

        # Simulate snapshot taken 0.2s before archive timestamp
        mtime = datetime.fromtimestamp(archive.stat().st_mtime, tz=UTC)
        simulated_snapshot = mtime - timedelta(milliseconds=200)

        report = engine.run_disaster_recovery_drill(
            backup_archive=archive,
            isolated_recovery_target=target_dir,
            rto_target_seconds=30.0,
            rpo_target_seconds=1.0,
            simulated_snapshot_timestamp=simulated_snapshot,
        )

        assert report.success is True
        assert report.all_integrity_passed is True
        assert report.databases_verified == 1
        assert report.rto_pass is True
        assert report.rto_seconds < 5.0  # Well within the 30s institutional SLA
        assert report.rpo_pass is True
        assert report.rpo_seconds <= 1.0  # Within 1s RPO window


class TestDisasterRecoveryCLI:
    """Verifies that the CLI interface works properly."""

    def test_cli_verify_only_clean_archive(self, tmp_path: Path) -> None:
        db = tmp_path / "cli_test.db"
        create_sample_db(db)
        archive = package_tar_gz([db], tmp_path / "cli_backup.tar.gz")

        env = {"PYTHONPATH": ".", **os.environ}
        res = subprocess.run(
            [sys.executable, "scripts/verify_and_restore_backup.py", "--verify-only", str(archive)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert res.returncode == 0
        assert '"integrity_passed": true' in res.stdout

    def test_cli_drill_mode_pass(self, tmp_path: Path) -> None:
        db = tmp_path / "drill_test.db"
        create_sample_db(db)
        archive = package_tar_gz([db], tmp_path / "drill_backup.tar.gz")
        target = tmp_path / "dr_drill_sandbox"

        env = {"PYTHONPATH": ".", **os.environ}
        res = subprocess.run(
            [
                sys.executable,
                "scripts/verify_and_restore_backup.py",
                "--drill",
                str(archive),
                "--target",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert res.returncode == 0
        assert '"rto_pass": true' in res.stdout
        assert '"success": true' in res.stdout
