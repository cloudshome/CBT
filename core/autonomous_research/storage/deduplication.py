"""
core/autonomous_research/storage/deduplication.py
=================================================
Content-Addressable Deduplication & Source Versioning for SKY 15-TB Architecture.
Implements:
- Section 4: Zero Duplicate Storage (SHA-256 pre-check and multi-reference tracking).
- Section 5: Immutable Source Versioning (SOURCE-1847-V2, parent lineage, change reason).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from core.autonomous_research.storage.storage_manifest import (
    ArchiveManifestRecord,
    StorageManifest,
    storage_manifest,
)

logger = logging.getLogger("ai_quant_sentinel.storage.deduplication")


@dataclass
class DeduplicationResult:
    is_duplicate: bool
    source_id: str
    content_hash: str
    existing_record: ArchiveManifestRecord | None
    reference_count: int


@dataclass
class VersionLineage:
    source_id: str
    version: int
    parent_source_id: str | None
    previous_hash: str | None
    new_hash: str
    change_reason: str
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))


class DeduplicationManager:
    """Manages SHA-256 content deduplication and semantic source versioning."""

    def __init__(self, manifest: StorageManifest | None = None):
        self.manifest = manifest or storage_manifest

    def check_deduplication(
        self, content_hash: str, reference_uri: str | None = None
    ) -> DeduplicationResult:
        """
        Queries manifest for identical content hash.
        If found, increments reference counter and returns existing record.
        """
        existing = self.manifest.get_by_content_hash(content_hash)
        if not existing:
            return DeduplicationResult(
                is_duplicate=False,
                source_id=f"SRC-{content_hash[:12]}",
                content_hash=content_hash,
                existing_record=None,
                reference_count=1,
            )

        # Increment reference count and update access
        self.manifest.touch_access(existing.source_id)
        if reference_uri:
            refs = existing.metadata.get("source_references", [])
            if reference_uri not in refs:
                refs.append(reference_uri)
                existing.metadata["source_references"] = refs
                self.manifest.save_record(existing)

        ref_cnt = len(existing.metadata.get("source_references", [])) + existing.access_count
        logger.info(
            f"Deduplication: Content {content_hash[:12]}... mapped to existing {existing.source_id} (Refs: {ref_cnt})"
        )
        return DeduplicationResult(
            is_duplicate=True,
            source_id=existing.source_id,
            content_hash=content_hash,
            existing_record=existing,
            reference_count=ref_cnt,
        )

    def create_new_version(
        self,
        base_source_id: str,
        new_content_hash: str,
        change_reason: str,
        file_size: int,
        mime_type: str,
        local_path: str | None = None,
    ) -> ArchiveManifestRecord:
        """
        Creates a child version (e.g. SOURCE-1847-V2) when content is modified.
        Preserves original parent source unchanged (Section 5: Never overwrite historical sources).
        """
        parent = self.manifest.get_by_source_id(base_source_id)
        parent_version = parent.version if parent else 1
        new_version_num = parent_version + 1
        new_source_id = f"{base_source_id}-V{new_version_num}"

        version_meta = {
            "parent_source_id": base_source_id,
            "previous_hash": parent.content_hash if parent else None,
            "new_hash": new_content_hash,
            "change_reason": change_reason,
            "version": new_version_num,
        }

        record = ArchiveManifestRecord(
            source_id=new_source_id,
            content_hash=new_content_hash,
            file_size=file_size,
            mime_type=mime_type,
            local_path=local_path,
            storage_tier="HOT",
            archive_status="PENDING",
            version=new_version_num,
            parent_source_id=base_source_id,
            metadata=version_meta,
        )
        self.manifest.save_record(record)
        logger.info(
            f"Created new source version: {new_source_id} (parent: {base_source_id}, reason: '{change_reason}')"
        )
        return record


deduplication_manager = DeduplicationManager()
