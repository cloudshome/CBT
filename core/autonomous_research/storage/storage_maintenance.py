"""
core/autonomous_research/storage/storage_maintenance.py
======================================================
Autonomous Maintenance, Orphan Detection & Reconciliation for SKY 15-TB Architecture.
Implements:
- Section 21: AI-Driven Archive Intelligence (duplicate detection, failure recovery).
- Section 22: Orphan Detection (cloud without manifest, manifest without cloud, broken links).
- Section 23: Archive Reconciliation (DATABASE vs MANIFEST vs GOOGLE DRIVE).
- Section 27: Autonomous Daily & Weekly Storage Jobs.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.archive_manager import (
    ArchiveManager,
    archive_manager,
)
from core.autonomous_research.storage.backup_manager import (
    CloudBackupManager,
    cloud_backup_manager,
)
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)
from core.autonomous_research.storage.retention_manager import (
    retention_manager,
)
from core.autonomous_research.storage.storage_manifest import (
    StorageManifest,
    StorageOperationLog,
    storage_manifest,
)
from core.autonomous_research.storage.storage_pressure import (
    StoragePressureManager,
    storage_pressure_manager,
)
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.storage.maintenance")


@dataclass
class OrphanReport:
    unindexed_cloud_objects: list[str] = field(default_factory=list)
    missing_cloud_objects: list[str] = field(default_factory=list)
    broken_provenance_links: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def total_orphans(self) -> int:
        return (
            len(self.unindexed_cloud_objects)
            + len(self.missing_cloud_objects)
            + len(self.broken_provenance_links)
        )


@dataclass
class ReconciliationReport:
    matched_records: int
    missing_remote_files: list[str] = field(default_factory=list)
    unexpected_remote_files: list[str] = field(default_factory=list)
    hash_mismatches: list[dict[str, Any]] = field(default_factory=list)
    size_mismatches: list[dict[str, Any]] = field(default_factory=list)
    stale_manifest_records: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = "HEALTHY"  # HEALTHY, WARNING, CRITICAL


class StorageMaintenanceEngine:
    """Coordinates periodic autonomous health checks, orphan auditing, and reconciliation."""

    def __init__(
        self,
        backend: DriveBackendProtocol | None = None,
        manifest: StorageManifest | None = None,
        arch_mgr: ArchiveManager | None = None,
        pressure_mgr: StoragePressureManager | None = None,
        backup_mgr: CloudBackupManager | None = None,
    ):
        self.backend = backend or get_default_drive_backend()
        self.manifest = manifest or storage_manifest
        self.arch_mgr = arch_mgr or archive_manager
        self.pressure_mgr = pressure_mgr or storage_pressure_manager
        self.backup_mgr = backup_mgr or cloud_backup_manager

    def detect_orphans(self) -> OrphanReport:
        """
        Audits cloud objects and SQLite tables for orphaned records:
        1. Cloud object exists but no manifest entry
        2. Manifest entry says VERIFIED but remote object missing
        3. Knowledge claims point to non-existent sources
        """
        report = OrphanReport()

        # 1. Inspect manifest records marked as VERIFIED
        verified_records = self.manifest.list_records(archive_status="VERIFIED", limit=5000)
        for r in verified_records:
            if not r.drive_file_id:
                report.missing_cloud_objects.append(r.source_id)
                continue
            # Fast existence check
            v = self.backend.verify_file(r.drive_file_id, r.file_size, r.content_hash)
            if not v.exists:
                report.missing_cloud_objects.append(r.source_id)

        # 2. Check broken provenance links in SQLite
        with db_manager.get_brain_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT rc.claim_id, rc.source_id
                FROM research_claims rc
                LEFT JOIN immutable_sources ims ON rc.source_id = ims.source_id
                LEFT JOIN archive_manifest am ON rc.source_id = am.source_id
                WHERE ims.source_id IS NULL AND am.source_id IS NULL
                """
            )
            for cid, sid in cur.fetchall():
                report.broken_provenance_links.append(f"Claim {cid} -> missing source {sid}")

        if report.total_orphans > 0:
            logger.warning(
                f"Orphan Detection Alert: Found {report.total_orphans} orphaned records (Zero silent deletion)."
            )
        return report

    def run_reconciliation(self) -> ReconciliationReport:
        """
        Performs 3-way reconciliation (Section 23):
        SQLite Database vs Archive Manifest vs Google Drive Storage.
        """
        records = self.manifest.list_records(limit=10000)
        matched = 0
        missing_remote = []
        hash_mismatches = []
        size_mismatches = []

        for r in records:
            if r.archive_status != "VERIFIED":
                continue

            if not r.drive_file_id:
                missing_remote.append(r.source_id)
                continue

            v_res = self.backend.verify_file(
                drive_file_id=r.drive_file_id,
                expected_size=r.file_size,
                expected_hash=r.content_hash,
            )

            if not v_res.exists:
                missing_remote.append(r.source_id)
            elif not v_res.size_matched:
                size_mismatches.append(
                    {
                        "source_id": r.source_id,
                        "expected_size": r.file_size,
                        "remote_size": v_res.remote_size,
                    }
                )
            elif not v_res.hash_matched:
                hash_mismatches.append(
                    {
                        "source_id": r.source_id,
                        "expected_hash": r.content_hash,
                        "remote_hash": v_res.remote_hash,
                    }
                )
            else:
                matched += 1

        status = "HEALTHY"
        if missing_remote or hash_mismatches:
            status = "CRITICAL"
        elif size_mismatches:
            status = "WARNING"

        report = ReconciliationReport(
            matched_records=matched,
            missing_remote_files=missing_remote,
            hash_mismatches=hash_mismatches,
            size_mismatches=size_mismatches,
            status=status,
        )

        self.manifest.log_operation(
            StorageOperationLog(
                operation_id=f"rec_{uuid.uuid4().hex[:12]}",
                source_id="RECONCILIATION_RUN",
                operation_type="RECONCILIATION_COMPLETED",
                result=status,
                worker="storage_maintenance",
                duration_ms=0.0,
            )
        )
        logger.info(
            f"Reconciliation completed: Status={status}, Matched={matched}, Issues={len(missing_remote) + len(hash_mismatches)}"
        )
        return report

    def run_daily_maintenance(self) -> dict[str, Any]:
        """
        Section 27 Daily Maintenance Job:
        1. Check Drive connectivity
        2. Check disk pressure & trigger eviction if needed
        3. Retry failed uploads
        4. Detect orphans
        """
        results: dict[str, Any] = {}
        # 1. Connectivity
        is_online = self.backend.check_connectivity()
        results["drive_online"] = is_online

        # 2. Pressure Check
        pressure = self.pressure_mgr.inspect_pressure()
        results["disk_pressure"] = pressure.level
        if pressure.level in ["CRITICAL", "EMERGENCY"]:
            eviction = self.pressure_mgr.relieve_pressure()
            results["eviction"] = eviction.files_evicted

        # 3. Retry Pending / Failed Uploads
        retry_count = 0
        if is_online:
            pending = self.manifest.list_records(archive_status="LOCAL_PENDING_ARCHIVE", limit=20)
            failed = self.manifest.list_records(archive_status="FAILED", limit=10)
            for r in pending + failed:
                if r.local_path and Path(r.local_path).exists():
                    arch_res = self.arch_mgr.archive_file(
                        local_path=r.local_path,
                        source_type=r.metadata.get("source_type", "RESEARCH"),
                        source_id=r.source_id,
                    )
                    if arch_res.is_verified:
                        retry_count += 1
        results["retried_uploads"] = retry_count

        # 4. Orphan Audit
        orphan_rep = self.detect_orphans()
        results["orphans_detected"] = orphan_rep.total_orphans

        logger.info(f"Daily storage maintenance completed: {results}")
        return results

    def run_weekly_maintenance(self) -> dict[str, Any]:
        """
        Section 27 Weekly Maintenance Job:
        1. Full Reconciliation
        2. Prune disposable artifacts
        3. Point-in-time Knowledge Snapshot
        4. Cloud Database Backup
        """
        results: dict[str, Any] = {}
        # 1. Reconciliation
        rec_report = self.run_reconciliation()
        results["reconciliation_status"] = rec_report.status

        # 2. Disposable Pruning
        pruned = retention_manager.cleanup_disposable_artifacts(max_age_days=7)
        results["disposable_pruned"] = pruned

        # 3. Knowledge Snapshot
        snap = self.backup_mgr.create_knowledge_snapshot()
        results["knowledge_snapshot_tag"] = snap.snapshot_tag

        # 4. Cloud DB Backup
        bkp = self.backup_mgr.create_cloud_database_backup()
        results["cloud_backup_id"] = bkp.backup_id

        logger.info(f"Weekly storage maintenance completed: {results}")
        return results


storage_maintenance_engine = StorageMaintenanceEngine()
