"""
core/autonomous_research/storage/retention_manager.py
====================================================
Retention Policy Governor for SKY 15-TB Architecture.
Implements Section 20 & Invariant 1 (NEVER silently delete research):
- Default: RETAIN_PERMANENT (sources, claims, hypotheses, evidence, autopsies).
- Explicit lifecycle pruning only for TEMPORARY, CACHE, and DISPOSABLE artifacts.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import ClassVar

from core.autonomous_research.storage.storage_manifest import (
    StorageManifest,
    storage_manifest,
)

logger = logging.getLogger("ai_quant_sentinel.storage.retention")


class RetentionManager:
    """Enforces permanent retention invariants and handles disposable cache hygiene."""

    PERMANENT_CLASSES: ClassVar[set[str]] = {"RETAIN_PERMANENT", "IMMUTABLE_SOURCE", "EVIDENCE"}
    PRUNABLE_CLASSES: ClassVar[set[str]] = {"TEMPORARY", "CACHE", "DISPOSABLE"}

    def __init__(self, manifest: StorageManifest | None = None):
        self.manifest = manifest or storage_manifest

    def audit_retention_distribution(self) -> dict[str, int]:
        """Returns tally of records per retention classification."""
        records = self.manifest.list_records(limit=10000)
        tally: dict[str, int] = {}
        for r in records:
            cls_name = r.retention_class
            tally[cls_name] = tally.get(cls_name, 0) + 1
        return tally

    def cleanup_disposable_artifacts(self, max_age_days: int = 7) -> int:
        """
        Safely prunes ONLY local files marked as TEMPORARY or DISPOSABLE.
        Enforces Invariant 1: Records in RETAIN_PERMANENT are strictly IMMUTABLE.
        """
        now = int(time.time() * 1000)
        cutoff_ms = now - (max_age_days * 86400 * 1000)
        records = self.manifest.list_records(limit=1000)

        pruned_count = 0
        for r in records:
            if r.retention_class not in self.PRUNABLE_CLASSES:
                # Permanent: never delete
                continue

            if r.last_accessed > cutoff_ms:
                # Recently accessed
                continue

            if r.local_path and Path(r.local_path).exists():
                try:
                    Path(r.local_path).unlink()
                    self.manifest.update_status(
                        r.source_id, archive_status="PRUNED", local_path=None
                    )
                    pruned_count += 1
                except Exception as e:
                    logger.warning(f"Could not prune disposable file {r.local_path}: {e}")

        logger.info(f"Retention manager pruned {pruned_count} disposable cache files.")
        return pruned_count


retention_manager = RetentionManager()
