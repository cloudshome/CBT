"""
core/autonomous_research/storage/retrieval_cache.py
===================================================
Transparent Retrieval and Adaptive Smart Cache for SKY 15-TB Architecture.
Implements Sections 11 & 12:
- Checks HOT -> WARM -> Local Cache -> Google Drive.
- On cache miss: streams from Google Drive, verifies SHA-256 hash, populates local cache.
- Updates access count and timestamps, promoting frequently referenced items to WARM/HOT.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from core.autonomous_research.storage.archive_policy import (
    ArchivePolicyEngine,
    archive_policy_engine,
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

logger = logging.getLogger("ai_quant_sentinel.storage.retrieval_cache")


class RetrievalCacheManager:
    """Manages transparent source retrieval, cache hydration, and thermal promotion."""

    def __init__(
        self,
        backend: DriveBackendProtocol | None = None,
        manifest: StorageManifest | None = None,
        policy: ArchivePolicyEngine | None = None,
        cache_dir: Path | None = None,
    ):
        self.backend = backend or get_default_drive_backend()
        self.manifest = manifest or storage_manifest
        self.policy = policy or archive_policy_engine
        base_cache = cache_dir or Path(os.getenv("DATA_DIR", "data")) / "cache" / "research"
        self.cache_dir = Path(base_cache).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def retrieve_source(self, source_id: str) -> Path:
        """
        Retrieves a research source by source_id.
        Resolves via local storage if present; otherwise fetches from Google Drive,
        verifies SHA-256, populates local cache, and updates access statistics.
        """
        start_ts = time.time()
        record = self.manifest.get_by_source_id(source_id)
        if not record:
            raise FileNotFoundError(f"Source ID not registered in manifest: {source_id}")

        # 1. Check if local copy exists
        if record.local_path and Path(record.local_path).exists():
            self.manifest.touch_access(source_id)
            self._re_evaluate_tier(record)
            return Path(record.local_path)

        # 2. Check local cache directory
        cached_file = self.cache_dir / f"{source_id}_{record.content_hash[:8]}.bin"
        if cached_file.exists():
            # Quick verification
            hash_res = content_hasher.hash_file_stream(cached_file)
            if hash_res.content_hash == record.content_hash:
                self.manifest.touch_access(source_id)
                self.manifest.update_status(
                    source_id, archive_status="VERIFIED", local_path=str(cached_file)
                )
                self._re_evaluate_tier(record)
                return cached_file
            else:
                logger.warning(
                    f"Corrupted cache file detected for {source_id}; re-fetching from Drive."
                )
                cached_file.unlink()

        # 3. Cache Miss: Retrieve from Google Drive
        if not record.drive_file_id:
            raise FileNotFoundError(
                f"Source {source_id} is evicted locally but has no remote drive_file_id."
            )

        logger.info(
            f"Cache miss for {source_id}. Fetching from Google Drive ({record.drive_file_id})..."
        )
        temp_dest = self.cache_dir / f"{source_id}_download.tmp"
        download_success = self.backend.download_file(
            drive_file_id=record.drive_file_id,
            dest_path=temp_dest,
        )

        if not download_success or not temp_dest.exists():
            raise ConnectionError(f"Failed downloading {source_id} from Google Drive backend.")

        # 4. Verify SHA-256 Content Hash before trusting restored cache
        verify_hash = content_hasher.hash_file_stream(temp_dest)
        if verify_hash.content_hash != record.content_hash:
            temp_dest.unlink()
            raise ValueError(
                f"Cryptographic hash mismatch for retrieved source {source_id}: "
                f"expected {record.content_hash}, got {verify_hash.content_hash}"
            )

        # 5. Commit into local cache
        temp_dest.rename(cached_file)
        self.manifest.update_status(
            source_id=source_id,
            archive_status="VERIFIED",
            local_path=str(cached_file),
        )
        self.manifest.touch_access(source_id)
        self._re_evaluate_tier(record)

        self.manifest.log_operation(
            StorageOperationLog(
                operation_id=f"restore_{source_id}_{int(time.time())}",
                source_id=source_id,
                operation_type="CACHE_RESTORED",
                result="SUCCESS",
                worker="retrieval_cache",
                source_hash=record.content_hash,
                destination=str(cached_file),
                duration_ms=round((time.time() - start_ts) * 1000, 2),
            )
        )
        logger.info(f"Successfully restored {source_id} from Google Drive to local cache.")
        return cached_file

    def _re_evaluate_tier(self, record: ArchiveManifestRecord) -> None:
        """Promotes cold records to warm/hot if recently and frequently accessed."""
        tier, _ = self.policy.calculate_temperature(record)
        if tier != record.storage_tier:
            self.manifest.update_storage_tier(record.source_id, tier)
            logger.info(
                f"Thermal tier adjusted for {record.source_id}: {record.storage_tier} -> {tier}"
            )


retrieval_cache_manager = RetrievalCacheManager()
