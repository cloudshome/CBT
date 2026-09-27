"""
core/autonomous_research/storage/storage_manager.py
==================================================
Master Unified Storage Facade for SKY 15-TB Knowledge Storage & Archive Engine.
Coordinates:
- Tier 1 (Hot Local SQLite/RAM)
- Tier 2 (Warm Extracted Research Cache)
- Tier 3 (Cold Google Drive Immutable Archive)
Enforces all 15 Non-Negotiable Invariants and provides seamless integration
with UniversalIngestor, AutonomousResearchPipeline, and FastAPI telemetry routers.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.archive_manager import (
    ArchiveManager,
    ArchiveResult,
    archive_manager,
)
from core.autonomous_research.storage.archive_policy import (
    ArchivePolicyEngine,
    archive_policy_engine,
)
from core.autonomous_research.storage.backup_manager import (
    CloudBackupManager,
    CloudBackupResult,
    DisasterRecoveryResult,
    cloud_backup_manager,
)
from core.autonomous_research.storage.content_hasher import (
    content_hasher,
)
from core.autonomous_research.storage.deduplication import (
    DeduplicationManager,
    deduplication_manager,
)
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)
from core.autonomous_research.storage.retrieval_cache import (
    RetrievalCacheManager,
    retrieval_cache_manager,
)
from core.autonomous_research.storage.storage_maintenance import (
    OrphanReport,
    ReconciliationReport,
    StorageMaintenanceEngine,
    storage_maintenance_engine,
)
from core.autonomous_research.storage.storage_manifest import (
    KnowledgeSnapshotRecord,
    StorageManifest,
    storage_manifest,
)
from core.autonomous_research.storage.storage_pressure import (
    PressureReport,
    StoragePressureManager,
    storage_pressure_manager,
)

logger = logging.getLogger("ai_quant_sentinel.storage.manager")


@dataclass
class IngestArchiveResult:
    source_id: str
    content_hash: str
    file_size: int
    mime_type: str
    archive_status: str  # VERIFIED, LOCAL_PENDING_ARCHIVE, DUPLICATE, FAILED
    drive_file_id: str | None
    drive_path: str | None
    local_path: str | None
    is_verified: bool
    is_duplicate: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StorageManager:
    """Master Quantitative Storage Architect Facade for SKY."""

    def __init__(
        self,
        backend: DriveBackendProtocol | None = None,
        manifest: StorageManifest | None = None,
        arch_mgr: ArchiveManager | None = None,
        cache_mgr: RetrievalCacheManager | None = None,
        dedup_mgr: DeduplicationManager | None = None,
        pressure_mgr: StoragePressureManager | None = None,
        maintenance_eng: StorageMaintenanceEngine | None = None,
        backup_mgr: CloudBackupManager | None = None,
        policy: ArchivePolicyEngine | None = None,
    ):
        self.backend = backend or get_default_drive_backend()
        self.manifest = manifest or storage_manifest
        self.arch_mgr = arch_mgr or archive_manager
        self.cache_mgr = cache_mgr or retrieval_cache_manager
        self.dedup_mgr = dedup_mgr or deduplication_manager
        self.pressure_mgr = pressure_mgr or storage_pressure_manager
        self.maintenance = maintenance_eng or storage_maintenance_engine
        self.backup = backup_mgr or cloud_backup_manager
        self.policy = policy or archive_policy_engine

    def ingest_and_archive(
        self,
        file_path_or_bytes: Path | str | bytes,
        source_type: str = "RESEARCH",
        filename: str | None = None,
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestArchiveResult:
        """
        Complete Entrypoint for Raw Knowledge Ingestion & Archival:
        1. Streaming SHA-256 hash & MIME identification (zero RAM bloat)
        2. Content-addressable deduplication check
        3. Transaction-safe Google Drive upload
        4. Cryptographic remote verification (size, hash, existence)
        5. Manifest registration and observability logging
        """
        meta = metadata or {}
        local_path: Path

        # Handle bytes vs file path
        if isinstance(file_path_or_bytes, bytes):
            fname = filename or f"doc_{int(time.time())}.bin"
            clean_name = content_hasher.sanitize_filename(fname)
            temp_dir = Path(os.getenv("DATA_DIR", "data")) / "uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_path = temp_dir / clean_name
            with open(local_path, "wb") as f:
                f.write(file_path_or_bytes)
        else:
            local_path = Path(file_path_or_bytes).resolve()

        # Archive file through transaction safety pipeline
        res: ArchiveResult = self.arch_mgr.archive_file(
            local_path=local_path,
            source_type=source_type,
            source_id=source_id,
            custom_metadata=meta,
        )

        manifest_rec = self.manifest.get_by_source_id(res.source_id)
        file_size = manifest_rec.file_size if manifest_rec else res.file_size
        mime_type = manifest_rec.mime_type if manifest_rec else "application/octet-stream"

        return IngestArchiveResult(
            source_id=res.source_id,
            content_hash=res.content_hash,
            file_size=file_size,
            mime_type=mime_type,
            archive_status=res.archive_status,
            drive_file_id=res.drive_file_id,
            drive_path=res.drive_path,
            local_path=res.local_path,
            is_verified=res.is_verified,
            is_duplicate=res.is_duplicate,
            error=res.error,
        )

    def retrieve_source(self, source_id: str) -> Path:
        """Transparently resolves source from local hot cache or fetches from Google Drive."""
        return self.cache_mgr.retrieve_source(source_id)

    def evict_source(self, source_id: str, is_critical: bool = False) -> bool:
        """Safely evicts local copy of a verified cloud archive object."""
        return self.arch_mgr.evict_local_copy(source_id=source_id, is_critical=is_critical)

    def check_pressure(self) -> PressureReport:
        """Returns real-time host disk capacity and storage tier metrics."""
        return self.pressure_mgr.inspect_pressure()

    def relieve_pressure(self) -> dict[str, Any]:
        """Triggers verification-gated LRU cache eviction under disk pressure."""
        summary = self.pressure_mgr.relieve_pressure()
        return asdict(summary)

    def run_reconciliation(self) -> ReconciliationReport:
        """Executes 3-way reconciliation across database, manifest, and Google Drive."""
        return self.maintenance.run_reconciliation()

    def detect_orphans(self) -> OrphanReport:
        """Scans for unindexed or broken provenance files."""
        return self.maintenance.detect_orphans()

    def create_snapshot(self, tag: str | None = None) -> KnowledgeSnapshotRecord:
        """Generates point-in-time knowledge snapshot and backs up to Drive."""
        return self.backup.create_knowledge_snapshot(snapshot_tag=tag)

    def create_db_backup(self) -> CloudBackupResult:
        """Creates encrypted database snapshot and uploads to Google Drive."""
        return self.backup.create_cloud_database_backup()

    def restore_system(self, backup_path: Path | str) -> DisasterRecoveryResult:
        """Restores complete SKY database suite from an encrypted backup."""
        return self.backup.reconstruct_from_backup(backup_path)

    def get_telemetry_dashboard(self) -> dict[str, Any]:
        """
        Section 28 Storage Dashboard Telemetry:
        Returns local storage, Google Drive status, manifest tiers, and knowledge metrics.
        """
        pressure = self.check_pressure()
        stats = self.manifest.get_stats()
        is_online = self.backend.check_connectivity()

        health_status = "HEALTHY"
        if pressure.level in ["CRITICAL", "EMERGENCY"] or not is_online:
            health_status = "WARNING" if is_online else "DEGRADED"

        return {
            "health_status": health_status,
            "drive_online": is_online,
            "host_storage": {
                "total_bytes": pressure.total_bytes,
                "used_bytes": pressure.used_bytes,
                "free_bytes": pressure.free_bytes,
                "used_percent": pressure.used_percent,
                "pressure_level": pressure.level,
            },
            "manifest_tiers": stats.get("tier_breakdown", {}),
            "archive_status": stats.get("status_breakdown", {}),
            "total_archived_sources": stats.get("total_manifest_sources", 0),
            "total_archived_bytes": stats.get("total_manifest_bytes", 0),
            "failed_operations": stats.get("failed_operations", 0),
            "timestamp": int(time.time() * 1000),
        }


storage_manager = StorageManager()
