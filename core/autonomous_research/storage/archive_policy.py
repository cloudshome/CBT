"""
core/autonomous_research/storage/archive_policy.py
==================================================
Thermal classification and retention policy engine for SKY 15-TB Architecture.
Implements:
- Section 10: HOT / WARM / COLD / CRITICAL Temperature Calculation
- Section 20: Retention Policy (Default: RETAIN_PERMANENT, Invariant 1: Zero Silent Loss)
- Configurable quotas: HOT_MAX_GB, HOT_MAX_FILES, HOT_MAX_CACHE_AGE_DAYS
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import ClassVar

from core.autonomous_research.storage.storage_manifest import ArchiveManifestRecord

logger = logging.getLogger("ai_quant_sentinel.storage.policy")


@dataclass
class StorageQuotas:
    hot_max_gb: float = 10.0
    warm_max_gb: float = 30.0
    hot_max_files: int = 5000
    hot_max_cache_age_days: int = 14
    warning_percent: float = 75.0
    critical_percent: float = 85.0
    emergency_percent: float = 92.0


class ArchivePolicyEngine:
    """Calculates object temperature, eviction eligibility, and destination directory."""

    # Folder routing map for Google Drive (Section 6)
    TYPE_FOLDER_ROUTING: ClassVar[dict[str, str]] = {
        "BOOK": "SKY/01_RAW_SOURCES/BOOKS",
        "PDF_BOOK": "SKY/01_RAW_SOURCES/BOOKS",
        "PDF": "SKY/01_RAW_SOURCES/PDF",
        "YOUTUBE": "SKY/01_RAW_SOURCES/YOUTUBE",
        "WEB": "SKY/01_RAW_SOURCES/WEB",
        "ARTICLE": "SKY/01_RAW_SOURCES/WEB",
        "GITHUB": "SKY/01_RAW_SOURCES/GITHUB",
        "NOTES": "SKY/01_RAW_SOURCES/NOTES",
        "IMAGE": "SKY/01_RAW_SOURCES/IMAGES",
        "IMAGES": "SKY/01_RAW_SOURCES/IMAGES",
        "RESEARCH": "SKY/01_RAW_SOURCES/RESEARCH",
        "CODE": "SKY/01_RAW_SOURCES/RESEARCH",
        "TRANSCRIPT": "SKY/02_EXTRACTED/TRANSCRIPTS",
        "OCR": "SKY/02_EXTRACTED/OCR",
        "EXPERIMENT": "SKY/05_EXPERIMENTS/BACKTESTS",
        "MARKET_DATA": "SKY/08_MARKET_DATA/BTC",
        "SNAPSHOT": "SKY/10_SYSTEM_SNAPSHOTS",
    }

    def __init__(self, quotas: StorageQuotas | None = None):
        self.quotas = quotas or StorageQuotas(
            hot_max_gb=float(os.getenv("HOT_MAX_GB", "10.0")),
            warm_max_gb=float(os.getenv("WARM_MAX_GB", "30.0")),
            hot_max_files=int(os.getenv("HOT_MAX_FILES", "5000")),
            hot_max_cache_age_days=int(os.getenv("HOT_MAX_CACHE_AGE_DAYS", "14")),
            warning_percent=float(os.getenv("STORAGE_WARNING_PERCENT", "75.0")),
            critical_percent=float(os.getenv("STORAGE_CRITICAL_PERCENT", "85.0")),
            emergency_percent=float(os.getenv("STORAGE_EMERGENCY_PERCENT", "92.0")),
        )

    def route_drive_folder(self, source_type: str, filename: str | None = None) -> str:
        """Determines target Google Drive directory based on source type and name."""
        upper_type = source_type.upper()
        if upper_type in self.TYPE_FOLDER_ROUTING:
            return self.TYPE_FOLDER_ROUTING[upper_type]

        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext == ".pdf":
                return "SKY/01_RAW_SOURCES/PDF"
            elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
                return "SKY/01_RAW_SOURCES/IMAGES"
            elif ext in [".py", ".pine", ".mq4", ".mq5"]:
                return "SKY/01_RAW_SOURCES/RESEARCH"
            elif ext in [".csv", ".parquet"]:
                return "SKY/08_MARKET_DATA/OTHER"

        return "SKY/01_RAW_SOURCES/RESEARCH"

    def calculate_temperature(
        self,
        record: ArchiveManifestRecord,
        is_active_hypothesis: bool = False,
        is_active_candidate: bool = False,
        is_current_market_data: bool = False,
    ) -> tuple[str, float]:
        """
        Calculates thermal score [0.0 to 100.0] and assigns tier: HOT, WARM, COLD, or CRITICAL.
        Enforces Section 10: Critical active research is NEVER classified as evictable.
        """
        # Critical items are protected from eviction
        if is_active_hypothesis or is_active_candidate or is_current_market_data:
            return "CRITICAL", 100.0

        now = int(time.time() * 1000)
        age_days = (now - record.last_accessed) / (1000 * 86400)

        # 1. Recency Score (0 - 40 points)
        # Drops linearly over 14 days
        recency_score = max(0.0, 40.0 * (1.0 - (age_days / self.quotas.hot_max_cache_age_days)))

        # 2. Frequency Score (0 - 30 points)
        # Log-scaled access count
        import math

        freq_score = min(30.0, 10.0 * math.log1p(record.access_count))

        # 3. Knowledge Significance (0 - 30 points)
        significance_score = 15.0
        if record.retention_class == "RETAIN_PERMANENT":
            significance_score += 10.0
        if record.metadata.get("has_validated_evidence"):
            significance_score += 5.0

        total_score = recency_score + freq_score + significance_score

        if total_score >= 65.0:
            tier = "HOT"
        elif total_score >= 35.0:
            tier = "WARM"
        else:
            tier = "COLD"

        return tier, round(total_score, 2)

    def is_eviction_eligible(
        self,
        record: ArchiveManifestRecord,
        is_critical: bool = False,
    ) -> bool:
        """
        Enforces Invariant 4: A local file is strictly NOT eligible for eviction
        unless its archive status is 'VERIFIED' and it is not a protected CRITICAL item.
        """
        if is_critical:
            return False

        # Invariant 4: NEVER evict before successful archive verification
        if record.archive_status != "VERIFIED":
            return False

        if not record.drive_file_id:
            return False

        # If it has no local file anyway, cannot evict
        if not record.local_path:
            return False

        return True


archive_policy_engine = ArchivePolicyEngine()
