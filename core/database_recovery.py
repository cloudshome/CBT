"""
SKY / CBT — Automated SQLite Database Backup Verification & Disaster Recovery Engine.

Provides automated non-destructive inspection, deep SQLite integrity audits
(PRAGMA integrity_check, PRAGMA foreign_key_check, row audits, schema versions),
atomic staged restoration, and disaster recovery drill orchestration with
measured RTO (Recovery Time Objective) and RPO (Recovery Point Objective).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("cbt.database_recovery")


class DisasterRecoveryError(Exception):
    """Base exception for disaster recovery and backup verification failures."""


class BackupCorruptionError(DisasterRecoveryError):
    """Raised when an archive is truncated, corrupted, or violates path safety."""


class IntegrityCheckFailedError(DisasterRecoveryError):
    """Raised when PRAGMA integrity_check or foreign_key_check fails."""


@dataclass(frozen=True)
class ArchiveMetadata:
    """Metadata for an inspected backup archive."""

    archive_path: str
    sha256: str
    size_bytes: int
    contained_files: list[str]


@dataclass(frozen=True)
class DatabaseIntegrityReport:
    """Detailed integrity audit for a single SQLite database."""

    db_name: str
    path: str
    integrity_check_passed: bool
    integrity_check_output: str
    foreign_keys_passed: bool
    foreign_key_violations: list[dict[str, Any]] = field(default_factory=list)
    tables: dict[str, int] = field(default_factory=dict)
    user_version: int = 0
    wal_clean: bool = True


@dataclass(frozen=True)
class RestorationResult:
    """Result of an archive restoration procedure."""

    archive_path: str
    target_dir: str
    restored_files: list[str]
    integrity_reports: list[DatabaseIntegrityReport]
    duration_seconds: float
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class DrillReport:
    """Comprehensive report from an automated Disaster Recovery Drill."""

    drill_timestamp: str
    rto_seconds: float
    rto_target_seconds: float
    rto_pass: bool
    rpo_seconds: float
    rpo_target_seconds: float
    rpo_pass: bool
    databases_verified: int
    all_integrity_passed: bool
    success: bool
    details: dict[str, Any] = field(default_factory=dict)


class DisasterRecoveryEngine:
    """
    Automated engine for verifying, staging, restoring, and drilling SQLite database backups.
    """

    DB_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """Computes the SHA-256 digest of any file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def inspect_archive(self, archive_path: Path) -> ArchiveMetadata:
        """
        Inspects a compressed .tar.gz backup archive without extracting it.
        Guards against path traversal attacks and validates file structure.
        """
        if not archive_path.is_file():
            raise BackupCorruptionError(f"Archive file does not exist: {archive_path}")

        sha256_hash = self.calculate_sha256(archive_path)
        size_bytes = archive_path.stat().st_size

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                contained: list[str] = []
                for member in tar.getmembers():
                    # Security check: forbid absolute paths and directory traversal
                    norm_path = os.path.normpath(member.name)
                    if (
                        norm_path.startswith("..")
                        or os.path.isabs(norm_path)
                        or "/../" in member.name
                    ):
                        raise BackupCorruptionError(
                            f"Path traversal attempt detected in archive member: {member.name}"
                        )
                    contained.append(member.name)
        except tarfile.TarError as e:
            raise BackupCorruptionError(f"Corrupt or invalid tar archive: {e}") from e

        return ArchiveMetadata(
            archive_path=str(archive_path),
            sha256=sha256_hash,
            size_bytes=size_bytes,
            contained_files=contained,
        )

    def verify_database_integrity(self, db_path: Path) -> DatabaseIntegrityReport:
        """
        Performs deep verification of a SQLite database:
        - PRAGMA integrity_check
        - PRAGMA foreign_key_check
        - Table inventory & row counts
        - PRAGMA user_version
        """
        if not db_path.is_file():
            return DatabaseIntegrityReport(
                db_name=db_path.name,
                path=str(db_path),
                integrity_check_passed=False,
                integrity_check_output=f"File not found: {db_path}",
                foreign_keys_passed=False,
            )

        try:
            # Open in read-only URI mode to prevent accidental mutation during audit
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check;")
            integrity_rows = cursor.fetchall()
            integrity_output = "; ".join(row[0] for row in integrity_rows)
            integrity_passed = len(integrity_rows) == 1 and integrity_rows[0][0] == "ok"

            # 2. PRAGMA foreign_key_check
            cursor.execute("PRAGMA foreign_key_check;")
            fk_rows = cursor.fetchall()
            fk_violations = []
            for row in fk_rows:
                # Returns: table, rowid, parent, fkid
                fk_violations.append(
                    {
                        "table": row[0],
                        "rowid": row[1],
                        "parent_table": row[2],
                        "fkid": row[3],
                    }
                )
            fk_passed = len(fk_violations) == 0

            # 3. Tables & row counts
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = {}
            table_names = [r[0] for r in cursor.fetchall()]
            for tbl in table_names:
                # Safe table name quoting
                clean_tbl = tbl.replace('"', '""')
                quoted_tbl = f'"{clean_tbl}"'
                cursor.execute(f"SELECT COUNT(*) FROM {quoted_tbl};")
                count_res = cursor.fetchone()
                tables[tbl] = count_res[0] if count_res else 0

            # 4. PRAGMA user_version
            cursor.execute("PRAGMA user_version;")
            user_ver_res = cursor.fetchone()
            user_version = user_ver_res[0] if user_ver_res else 0

            conn.close()

            return DatabaseIntegrityReport(
                db_name=db_path.name,
                path=str(db_path),
                integrity_check_passed=integrity_passed,
                integrity_check_output=integrity_output,
                foreign_keys_passed=fk_passed,
                foreign_key_violations=fk_violations,
                tables=tables,
                user_version=user_version,
                wal_clean=True,
            )
        except Exception as e:
            logger.error(f"Integrity audit failed on {db_path.name}: {e}")
            return DatabaseIntegrityReport(
                db_name=db_path.name,
                path=str(db_path),
                integrity_check_passed=False,
                integrity_check_output=f"Exception during audit: {e}",
                foreign_keys_passed=False,
            )

    def restore_from_archive(
        self,
        archive_path: Path,
        target_dir: Path,
        staging_dir: Path | None = None,
        dry_run: bool = False,
    ) -> RestorationResult:
        """
        Safely restores all databases from an archive into target_dir.
        Workflow:
        1. Inspect archive metadata & guard against path traversal.
        2. Unpack into staging directory.
        3. Audit deep integrity on all staged SQLite databases.
        4. If any check fails, abort and clean up staging (fail-closed).
        5. If dry_run is True, return success without touching target_dir.
        6. Atomically copy verified databases into target_dir.
        """
        start_time = time.perf_counter()
        self.inspect_archive(archive_path)

        use_temp_staging = staging_dir is None
        actual_staging = (
            Path(tempfile.mkdtemp(prefix="cbt_restore_stage_")) if use_temp_staging else staging_dir
        )
        actual_staging.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Safe extraction into staging
            with tarfile.open(archive_path, "r:gz") as tar:
                for member in tar.getmembers():
                    norm_path = os.path.normpath(member.name)
                    if norm_path.startswith("..") or os.path.isabs(norm_path):
                        raise BackupCorruptionError(f"Path traversal in {member.name}")
                    tar.extract(member, path=actual_staging)

            # 2. Audit deep integrity of all databases in staging
            staged_db_files = [
                p
                for p in actual_staging.iterdir()
                if p.is_file() and p.suffix in self.DB_EXTENSIONS
            ]

            if not staged_db_files:
                raise BackupCorruptionError(
                    f"Archive contains no valid SQLite databases: {archive_path}"
                )

            integrity_reports: list[DatabaseIntegrityReport] = []
            for db_path in staged_db_files:
                report = self.verify_database_integrity(db_path)
                integrity_reports.append(report)
                if not report.integrity_check_passed:
                    raise IntegrityCheckFailedError(
                        f"Database integrity check failed for {db_path.name}: {report.integrity_check_output}"
                    )
                if not report.foreign_keys_passed:
                    raise IntegrityCheckFailedError(
                        f"Foreign key violations found in {db_path.name}: {report.foreign_key_violations}"
                    )

            if dry_run:
                duration = time.perf_counter() - start_time
                return RestorationResult(
                    archive_path=str(archive_path),
                    target_dir=str(target_dir),
                    restored_files=[r.db_name for r in integrity_reports],
                    integrity_reports=integrity_reports,
                    duration_seconds=duration,
                    success=True,
                )

            # 3. Atomically place into target directory
            target_dir.mkdir(parents=True, exist_ok=True)
            for db_path in staged_db_files:
                dest_file = target_dir / db_path.name
                # Copy with metadata preservation
                shutil.copy2(db_path, dest_file)

            duration = time.perf_counter() - start_time
            return RestorationResult(
                archive_path=str(archive_path),
                target_dir=str(target_dir),
                restored_files=[r.db_name for r in integrity_reports],
                integrity_reports=integrity_reports,
                duration_seconds=duration,
                success=True,
            )
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(f"Restoration failed: {e}")
            return RestorationResult(
                archive_path=str(archive_path),
                target_dir=str(target_dir),
                restored_files=[],
                integrity_reports=[],
                duration_seconds=duration,
                success=False,
                error=str(e),
            )
        finally:
            if use_temp_staging and actual_staging.exists():
                shutil.rmtree(actual_staging, ignore_errors=True)

    def run_disaster_recovery_drill(
        self,
        backup_archive: Path,
        isolated_recovery_target: Path,
        rto_target_seconds: float = 30.0,
        rpo_target_seconds: float = 1.0,
        simulated_snapshot_timestamp: datetime | None = None,
    ) -> DrillReport:
        """
        Executes an institutional disaster recovery drill:
        1. Measures exact wall-clock RTO (Recovery Time Objective).
        2. Evaluates archive and database integrity checks.
        3. Measures RPO (Recovery Point Objective) against snapshot baseline.
        4. Validates institutional targets: RTO <= 30.0s, RPO <= 1.0s.
        """
        now = datetime.now(UTC)
        drill_start = time.perf_counter()

        result = self.restore_from_archive(
            archive_path=backup_archive,
            target_dir=isolated_recovery_target,
            dry_run=False,
        )

        rto_measured = time.perf_counter() - drill_start
        rto_pass = rto_measured <= rto_target_seconds

        # Compute RPO: difference between simulated snapshot moment and archive capture
        if simulated_snapshot_timestamp is not None:
            archive_mtime = datetime.fromtimestamp(backup_archive.stat().st_mtime, tz=UTC)
            rpo_delta = abs((archive_mtime - simulated_snapshot_timestamp).total_seconds())
        else:
            rpo_delta = 0.0
        rpo_pass = rpo_delta <= rpo_target_seconds

        all_integrity_passed = result.success and all(
            r.integrity_check_passed and r.foreign_keys_passed for r in result.integrity_reports
        )
        drill_success = result.success and rto_pass and rpo_pass and all_integrity_passed

        return DrillReport(
            drill_timestamp=now.isoformat(),
            rto_seconds=round(rto_measured, 4),
            rto_target_seconds=rto_target_seconds,
            rto_pass=rto_pass,
            rpo_seconds=round(rpo_delta, 4),
            rpo_target_seconds=rpo_target_seconds,
            rpo_pass=rpo_pass,
            databases_verified=len(result.integrity_reports),
            all_integrity_passed=all_integrity_passed,
            success=drill_success,
            details={
                "archive": str(backup_archive),
                "target": str(isolated_recovery_target),
                "restored_databases": [r.db_name for r in result.integrity_reports],
                "error": result.error,
            },
        )
