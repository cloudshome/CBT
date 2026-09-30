"""
core/autonomous_research/storage/__init__.py
============================================
SKY 15-TB Knowledge Storage & Auto-Archiving Engine.
Tier 1 (Hot Local) + Tier 2 (Warm Cache) + Tier 3 (Cold Google Drive Archive).
"""

from __future__ import annotations

from core.autonomous_research.storage.archive_manager import (
    ArchiveManager,
    ArchiveResult,
    archive_manager,
)
from core.autonomous_research.storage.archive_policy import (
    ArchivePolicyEngine,
    StorageQuotas,
    archive_policy_engine,
)
from core.autonomous_research.storage.archive_verifier import (
    ArchiveVerifier,
    archive_verifier,
)
from core.autonomous_research.storage.backup_manager import (
    CloudBackupManager,
    CloudBackupResult,
    DisasterRecoveryResult,
    cloud_backup_manager,
)
from core.autonomous_research.storage.content_hasher import (
    ContentHasher,
    ContentHashResult,
    content_hasher,
)
from core.autonomous_research.storage.deduplication import (
    DeduplicationManager,
    DeduplicationResult,
    VersionLineage,
    deduplication_manager,
)
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    DriveFileMetadata,
    GoogleDriveAPIBackend,
    SimulatedDriveBackend,
    VerificationResult,
    get_default_drive_backend,
)
from core.autonomous_research.storage.research_storage import (
    AutonomousTaskRecord,
    ConflictRecord,
    FailureMemoryRecord,
    ImmutableSourceRecord,
    KnowledgeVersionRecord,
    MultipleTestingRecord,
    PracticeSessionRecord,
    ResearchStorage,
    research_storage,
)
from core.autonomous_research.storage.retention_manager import (
    RetentionManager,
    retention_manager,
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
from core.autonomous_research.storage.storage_manager import (
    IngestArchiveResult,
    StorageManager,
    storage_manager,
)
from core.autonomous_research.storage.storage_manifest import (
    ArchiveManifestRecord,
    KnowledgeSnapshotRecord,
    StorageManifest,
    StorageOperationLog,
    storage_manifest,
)
from core.autonomous_research.storage.storage_pressure import (
    EvictionSummary,
    PressureReport,
    StoragePressureManager,
    storage_pressure_manager,
)

__all__ = [
    "ArchiveManager",
    "ArchiveManifestRecord",
    "ArchivePolicyEngine",
    "ArchiveResult",
    "ArchiveVerifier",
    "AutonomousTaskRecord",
    "CloudBackupManager",
    "CloudBackupResult",
    "ConflictRecord",
    "ContentHashResult",
    "ContentHasher",
    "DeduplicationManager",
    "DeduplicationResult",
    "DisasterRecoveryResult",
    "DriveBackendProtocol",
    "DriveFileMetadata",
    "EvictionSummary",
    "FailureMemoryRecord",
    "GoogleDriveAPIBackend",
    "ImmutableSourceRecord",
    "IngestArchiveResult",
    "KnowledgeSnapshotRecord",
    "KnowledgeVersionRecord",
    "MultipleTestingRecord",
    "OrphanReport",
    "PracticeSessionRecord",
    "PressureReport",
    "ReconciliationReport",
    "ResearchStorage",
    "RetentionManager",
    "RetrievalCacheManager",
    "SimulatedDriveBackend",
    "StorageMaintenanceEngine",
    "StorageManager",
    "StorageManifest",
    "StorageOperationLog",
    "StoragePressureManager",
    "StorageQuotas",
    "VerificationResult",
    "VersionLineage",
    "archive_manager",
    "archive_policy_engine",
    "archive_verifier",
    "cloud_backup_manager",
    "content_hasher",
    "deduplication_manager",
    "get_default_drive_backend",
    "research_storage",
    "retention_manager",
    "retrieval_cache_manager",
    "storage_maintenance_engine",
    "storage_manager",
    "storage_manifest",
    "storage_pressure_manager",
]
