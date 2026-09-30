"""
core/autonomous_research/storage/archive_verifier.py
====================================================
Cryptographic verification engine for SKY 15-TB Archival Pipeline.
Enforces Invariant 4 & Section 8 (Archive Transaction Safety):
1. Verifies cloud object exists
2. Verifies exact byte size match
3. Verifies SHA-256 hash match
Only after all 3 checks pass can an object transition to VERIFIED.
"""

from __future__ import annotations

import logging
import time
import uuid

from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    VerificationResult,
)
from core.autonomous_research.storage.storage_manifest import (
    ArchiveManifestRecord,
    StorageOperationLog,
    storage_manifest,
)

logger = logging.getLogger("ai_quant_sentinel.storage.verifier")


class ArchiveVerifier:
    """Performs rigorous verification of cloud archive objects against manifest specifications."""

    def __init__(self, manifest=None):
        self.manifest = manifest or storage_manifest

    def verify_record(
        self,
        record: ArchiveManifestRecord,
        backend: DriveBackendProtocol,
    ) -> VerificationResult:
        """
        Executes complete verification gate on a single manifest record.
        Updates manifest status to VERIFIED or FAILED and records observability log.
        """
        start_time = time.time()
        op_id = f"op_verify_{uuid.uuid4().hex[:12]}"

        if not record.drive_file_id:
            res = VerificationResult(
                is_valid=False,
                exists=False,
                size_matched=False,
                hash_matched=False,
                remote_size=0,
                remote_hash=None,
                error_message="Manifest record has no drive_file_id assigned.",
            )
            self._log_verification(record, op_id, res, (time.time() - start_time) * 1000)
            return res

        # Call backend verifier
        result = backend.verify_file(
            drive_file_id=record.drive_file_id,
            expected_size=record.file_size,
            expected_hash=record.content_hash,
        )

        now = int(time.time() * 1000)
        duration_ms = (time.time() - start_time) * 1000

        if result.is_valid:
            self.manifest.update_status(
                source_id=record.source_id,
                archive_status="VERIFIED",
                verification_hash=result.remote_hash or record.content_hash,
                verification_timestamp=now,
            )
            logger.info(
                f"Archive VERIFIED: {record.source_id} (hash: {record.content_hash[:12]}..., size: {record.file_size} B)"
            )
        else:
            self.manifest.update_status(
                source_id=record.source_id,
                archive_status="FAILED",
            )
            logger.warning(
                f"Archive VERIFICATION FAILED: {record.source_id} -> {result.error_message}"
            )

        self._log_verification(record, op_id, result, duration_ms)
        return result

    def _log_verification(
        self,
        record: ArchiveManifestRecord,
        op_id: str,
        res: VerificationResult,
        duration_ms: float,
    ) -> None:
        self.manifest.log_operation(
            StorageOperationLog(
                operation_id=op_id,
                source_id=record.source_id,
                operation_type="ARCHIVE_VERIFIED" if res.is_valid else "ARCHIVE_FAILED",
                result="VERIFIED" if res.is_valid else "FAILED",
                worker="archive_verifier",
                source_hash=record.content_hash,
                destination=record.drive_path,
                duration_ms=round(duration_ms, 2),
                error=res.error_message,
            )
        )


archive_verifier = ArchiveVerifier()
