"""
core/autonomous_research/storage/storage_pressure.py
====================================================
Storage pressure monitoring and verification-gated auto-eviction for SKY.
Implements Section 9:
- WARNING (75%): Report status, prepare archival candidates
- CRITICAL (85%): Archive eligible WARM data, evict verified local cache
- EMERGENCY (92%): Protect DB & active research; evict all verified disposable cache
Enforces Invariant 4: Local files are NEVER deleted unless verified on Google Drive.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.autonomous_research.storage.archive_manager import (
    ArchiveManager,
    archive_manager,
)
from core.autonomous_research.storage.archive_policy import (
    ArchivePolicyEngine,
    archive_policy_engine,
)
from core.autonomous_research.storage.storage_manifest import (
    StorageManifest,
    storage_manifest,
)

logger = logging.getLogger("ai_quant_sentinel.storage.pressure")


@dataclass
class PressureReport:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    level: str  # NORMAL, WARNING, CRITICAL, EMERGENCY
    hot_storage_bytes: int
    warm_storage_bytes: int
    cold_storage_bytes: int
    eviction_candidate_count: int
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class EvictionSummary:
    files_evicted: int
    bytes_freed: int
    remaining_used_percent: float
    status: str  # OK, THRESHOLD_MET, INSUFFICIENT_VERIFIED_CANDIDATES


class StoragePressureManager:
    """Monitors host filesystem capacity and triggers verification-gated eviction."""

    def __init__(
        self,
        manifest: StorageManifest | None = None,
        arch_mgr: ArchiveManager | None = None,
        policy: ArchivePolicyEngine | None = None,
        data_dir: Path | None = None,
    ):
        self.manifest = manifest or storage_manifest
        self.arch_mgr = arch_mgr or archive_manager
        self.policy = policy or archive_policy_engine
        self.data_dir = data_dir or Path(os.getenv("DATA_DIR", "data")).resolve()

    def inspect_pressure(self) -> PressureReport:
        """Calculates current host disk metrics and manifest storage tiers."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        total, used, free = shutil.disk_usage(self.data_dir)
        used_pct = round((used / total) * 100.0, 2) if total > 0 else 0.0

        quotas = self.policy.quotas
        if used_pct >= quotas.emergency_percent:
            level = "EMERGENCY"
        elif used_pct >= quotas.critical_percent:
            level = "CRITICAL"
        elif used_pct >= quotas.warning_percent:
            level = "WARNING"
        else:
            level = "NORMAL"

        stats = self.manifest.get_stats()
        tier_breakdown = stats.get("tier_breakdown", {})
        hot_b = tier_breakdown.get("HOT", {}).get("bytes", 0)
        warm_b = tier_breakdown.get("WARM", {}).get("bytes", 0)
        cold_b = tier_breakdown.get("COLD", {}).get("bytes", 0)

        # Count verified records eligible for eviction
        verified_candidates = self.manifest.list_records(archive_status="VERIFIED", limit=500)
        eviction_eligible = [
            r
            for r in verified_candidates
            if r.local_path and Path(r.local_path).exists() and self.policy.is_eviction_eligible(r)
        ]

        return PressureReport(
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            used_percent=used_pct,
            level=level,
            hot_storage_bytes=hot_b,
            warm_storage_bytes=warm_b,
            cold_storage_bytes=cold_b,
            eviction_candidate_count=len(eviction_eligible),
        )

    def relieve_pressure(
        self, target_free_percent: float | None = None, force_level: str | None = None
    ) -> EvictionSummary:
        """
        Executes pressure relief: evicts verified local caches in LRU order
        until disk pressure drops below target or all verified candidates are exhausted.
        """
        report = self.inspect_pressure()
        level = force_level or report.level

        if level == "NORMAL" and target_free_percent is None:
            return EvictionSummary(
                files_evicted=0,
                bytes_freed=0,
                remaining_used_percent=report.used_percent,
                status="OK",
            )

        target_used = 100.0 - (target_free_percent or (100.0 - self.policy.quotas.warning_percent))

        logger.info(
            f"Storage Pressure relief initiated: Level={level}, Used={report.used_percent}% (Target <= {target_used}%)"
        )

        # Query verified records ordered by last accessed ascending (LRU)
        candidates = self.manifest.list_records(archive_status="VERIFIED", limit=1000)
        # Sort by access time (oldest first)
        candidates.sort(key=lambda r: r.last_accessed)

        freed_bytes = 0
        evicted_count = 0

        for r in candidates:
            # Check current usage
            total, used, _ = shutil.disk_usage(self.data_dir)
            current_pct = (used / total) * 100.0
            if current_pct <= target_used and level != "EMERGENCY":
                break

            if not r.local_path or not Path(r.local_path).exists():
                continue

            # Evict verified copy
            success = self.arch_mgr.evict_local_copy(r.source_id)
            if success:
                evicted_count += 1
                freed_bytes += r.file_size

        total, used, _ = shutil.disk_usage(self.data_dir)
        final_pct = round((used / total) * 100.0, 2)
        status = "THRESHOLD_MET" if final_pct <= target_used else "INSUFFICIENT_VERIFIED_CANDIDATES"

        logger.info(
            f"Pressure relief completed: {evicted_count} files evicted, {freed_bytes} bytes freed. Final usage: {final_pct}%"
        )
        return EvictionSummary(
            files_evicted=evicted_count,
            bytes_freed=freed_bytes,
            remaining_used_percent=final_pct,
            status=status,
        )


storage_pressure_manager = StoragePressureManager()
