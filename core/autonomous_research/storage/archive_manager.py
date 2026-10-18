"""
core/autonomous_research/storage/archive_manager.py
==================================================
10-Step Transaction-Safe Archival State Machine for SKY 15-TB Architecture.
Enforces:
- Section 8: Archive Transaction Safety (NEVER upload -> delete local).
- Invariant 4: Google Drive archival failure NEVER destroys local source.
- Invariant 1: NEVER silently delete research.
- Section 30: Google Drive Outage / Failure Mode resilience.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.archive_policy import (
    ArchivePolicyEngine,
    archive_policy_engine,
)
from core.autonomous_research.storage.archive_verifier import (
    ArchiveVerifier,
    archive_verifier,
)
from core.autonomous_research.storage.content_hasher import (
    content_hasher,
)
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)
from core.autonomous_research.storage.storage_manifest import (
    ArchiveManifestRecord,
    StorageManifest,
    StorageOperationLog,
    storage_manifest,
)

logger = logging.getLogger("ai_quant_sentinel.storage.archive_manager")


@dataclass
class ArchiveResult:
    source_id: str
    content_hash: str
    archive_status: str  # VERIFIED, LOCAL_PENDING_ARCHIVE, FAILED, DUPLICATE
    drive_file_id: str | None
    drive_path: str | None
    local_path: str | None
    file_size: int
    is_verified: bool
    is_duplicate: bool = False
    error: str | None = None


class ArchiveManager:
    """Coordinates transaction-safe archival between local disk and remote cloud storage."""

    def __init__(
        self,
        backend: DriveBackendProtocol | None = None,
        manifest: StorageManifest | None = None,
        verifier: ArchiveVerifier | None = None,
        policy: ArchivePolicyEngine | None = None,
    ):
        self.backend = backend or get_default_drive_backend()
        self.manifest = manifest or storage_manifest
        self.verifier = verifier or archive_verifier
        self.policy = policy or archive_policy_engine

    def archive_file(
        self,
        local_path: Path | str,
        source_type: str = "RESEARCH",
        source_id: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> ArchiveResult:
        """
        Executes the mandatory 10-step transaction-safe archival workflow:
        1. Identify source
        2. Calculate SHA-256 (streaming)
        3. Check deduplication
        4. Write local manifest (PENDING)
        5. Upload to Drive (UPLOADING)
        6. Receive Drive object ID
        7. Verify object exists
        8. Verify file size
        9. Verify SHA-256 hash match
        10. Mark archive VERIFIED (local eviction permitted only after this point)
        """
        start_ts = time.time()
        op_id = f"op_arch_{uuid.uuid4().hex[:12]}"
        path = Path(local_path).resolve()

        if not path.exists():
            return ArchiveResult(
                source_id=source_id or "UNKNOWN",
                content_hash="",
                archive_status="FAILED",
                drive_file_id=None,
                drive_path=None,
                local_path=str(path),
                file_size=0,
                is_verified=False,
                error=f"Local file does not exist: {path}",
            )

        # Step 1 & 2: Hash source file in bounded chunks
        hash_res = content_hasher.hash_file_stream(path)
        content_hash = hash_res.content_hash
        file_size = hash_res.file_size
        mime_type = hash_res.mime_type

        sid = source_id or f"SRC-{content_hash[:12]}"

        # Step 3: Check Deduplication (Section 4)
        existing = self.manifest.get_by_content_hash(content_hash)
        if existing and existing.archive_status == "VERIFIED":
            logger.info(
                f"Deduplication hit: {path.name} matches existing source {existing.source_id} ({content_hash[:12]}...)"
            )
            self.manifest.touch_access(existing.source_id)
            self._log_op(
                op_id=op_id,
                source_id=existing.source_id,
                op_type="DUPLICATE_DETECTED",
                result="SUCCESS",
                hash_val=content_hash,
                dest=existing.drive_path,
                dur_ms=(time.time() - start_ts) * 1000,
            )
            return ArchiveResult(
                source_id=existing.source_id,
                content_hash=content_hash,
                archive_status="VERIFIED",
                drive_file_id=existing.drive_file_id,
                drive_path=existing.drive_path,
                local_path=existing.local_path or str(path),
                file_size=file_size,
                is_verified=True,
                is_duplicate=True,
            )

        # Step 4: Write local metadata entry (status: PENDING)
        target_folder = self.policy.route_drive_folder(source_type, path.name)
        record = ArchiveManifestRecord(
            source_id=sid,
            content_hash=content_hash,
            file_size=file_size,
            mime_type=mime_type,
            local_path=str(path),
            storage_tier="HOT",
            archive_status="PENDING",
            metadata=custom_metadata or {},
        )
        self.manifest.save_record(record)
        self._log_op(
            op_id=op_id,
            source_id=sid,
            op_type="ARCHIVE_STARTED",
            result="PENDING",
            hash_val=content_hash,
            dest=target_folder,
            dur_ms=(time.time() - start_ts) * 1000,
        )

        # Check Cloud Connectivity (Section 30: Failure Mode Resilience)
        if not self.backend.check_connectivity():
            logger.warning(
                f"Google Drive is OFFLINE. Preserving local copy for {sid} as LOCAL_PENDING_ARCHIVE."
            )
            self.manifest.update_status(
                source_id=sid,
                archive_status="LOCAL_PENDING_ARCHIVE",
                local_path=str(path),
            )
            return ArchiveResult(
                source_id=sid,
                content_hash=content_hash,
                archive_status="LOCAL_PENDING_ARCHIVE",
                drive_file_id=None,
                drive_path=None,
                local_path=str(path),
                file_size=file_size,
                is_verified=False,
                error="Drive offline; preserved in LOCAL_PENDING_ARCHIVE queue.",
            )

        # Step 5: Upload to Drive (status: UPLOADING)
        self.manifest.update_status(source_id=sid, archive_status="UPLOADING")
        drive_meta = None
        try:
            drive_meta = self.backend.upload_file(
                local_path=path,
                drive_folder=target_folder,
                filename=f"{sid}_{path.name}",
                resumable=True,
            )
        except Exception as e:
            logger.error(
                f"Upload failed for {sid}: {e}. Local copy strictly PRESERVED (Invariant 4)."
            )
            self.manifest.update_status(source_id=sid, archive_status="FAILED")
            self._log_op(
                op_id=f"fail_{op_id}",
                source_id=sid,
                op_type="ARCHIVE_FAILED",
                result="FAILED",
                hash_val=content_hash,
                dest=target_folder,
                dur_ms=(time.time() - start_ts) * 1000,
                error=str(e),
            )
            return ArchiveResult(
                source_id=sid,
                content_hash=content_hash,
                archive_status="FAILED",
                drive_file_id=None,
                drive_path=None,
                local_path=str(path),
                file_size=file_size,
                is_verified=False,
                error=f"Upload error: {e}",
            )

        # Step 6: Record remote Object ID
        record.drive_file_id = drive_meta.drive_file_id
        record.drive_path = drive_meta.drive_path
        record.upload_timestamp = int(time.time() * 1000)
        self.manifest.save_record(record)

        # Step 7, 8, 9: Verify existence, size, and hash
        v_res = self.verifier.verify_record(record, self.backend)

        if v_res.is_valid:
            self._log_op(
                op_id=f"ver_{op_id}",
                source_id=sid,
                op_type="ARCHIVE_COMPLETED",
                result="SUCCESS",
                hash_val=content_hash,
                dest=drive_meta.drive_path,
                dur_ms=(time.time() - start_ts) * 1000,
            )
            return ArchiveResult(
                source_id=sid,
                content_hash=content_hash,
                archive_status="VERIFIED",
                drive_file_id=drive_meta.drive_file_id,
                drive_path=drive_meta.drive_path,
                local_path=str(path),
                file_size=file_size,
                is_verified=True,
            )
        else:
            logger.warning(
                f"Verification failed for {sid}: {v_res.error_message}. Local file preserved."
            )
            return ArchiveResult(
                source_id=sid,
                content_hash=content_hash,
                archive_status="FAILED",
                drive_file_id=drive_meta.drive_file_id,
                drive_path=drive_meta.drive_path,
                local_path=str(path),
                file_size=file_size,
                is_verified=False,
                error=v_res.error_message,
            )

    def evict_local_copy(self, source_id: str, is_critical: bool = False) -> bool:
        """
        Step 10: Verification-Gated Local Eviction.
        Enforces Invariant 4: Local file is strictly DELETED ONLY IF remote copy is VERIFIED.
        """
        record = self.manifest.get_by_source_id(source_id)
        if not record:
            logger.error(f"Cannot evict unknown source: {source_id}")
            return False

        if not self.policy.is_eviction_eligible(record, is_critical=is_critical):
            logger.warning(
                f"Eviction rejected: {source_id} is not verified or is protected as critical research."
            )
            return False

        local_path = Path(record.local_path) if record.local_path else None
        if not local_path or not local_path.exists():
            # Already evicted
            self.manifest.update_status(
                source_id=source_id,
                archive_status="EVICTED",
                local_path=None,
            )
            return True

        try:
            local_path.unlink()
            self.manifest.update_status(
                source_id=source_id,
                archive_status="EVICTED",
                local_path=None,
            )
            self.manifest.update_storage_tier(source_id=source_id, tier="COLD")
            self._log_op(
                op_id=f"evict_{uuid.uuid4().hex[:12]}",
                source_id=source_id,
                op_type="CACHE_EVICTED",
                result="SUCCESS",
                hash_val=record.content_hash,
                dest="COLD_ARCHIVE",
                dur_ms=0.0,
            )
            logger.info(f"Local copy evicted for verified source: {source_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to evict local file {local_path}: {e}")
            return False

    def _log_op(
        self,
        op_id: str,
        source_id: str,
        op_type: str,
        result: str,
        hash_val: str | None,
        dest: str | None,
        dur_ms: float,
        error: str | None = None,
    ) -> None:
        self.manifest.log_operation(
            StorageOperationLog(
                operation_id=op_id,
                source_id=source_id,
                operation_type=op_type,
                result=result,
                worker="archive_manager",
                source_hash=hash_val,
                destination=dest,
                duration_ms=round(dur_ms, 2),
                error=error,
            )
        )


archive_manager = ArchiveManager()
