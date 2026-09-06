"""
core/youtube/models.py
======================
Strongly typed domain models and data contracts for YouTube Research Intelligence V5.
Governed by Level 1 Constitution & Epistemic Typology:
- Repetition of creator claims is strictly classified as repetition, never independent empirical evidence.
- Formulated strategy candidates remain quarantined at confidence = 0.0 and stage = UNTESTED.
"""

from __future__ import annotations

import enum
import time
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional


class YouTubeSourceType(str, enum.Enum):
    VIDEO = "VIDEO"
    PLAYLIST = "PLAYLIST"
    CHANNEL = "CHANNEL"


class VideoRelevance(str, enum.Enum):
    RESEARCH_RELEVANT = "RESEARCH_RELEVANT"
    LOW_SIGNAL = "LOW_SIGNAL"
    PROMOTIONAL = "PROMOTIONAL"
    NO_TRANSCRIPT = "NO_TRANSCRIPT"
    TOO_SHORT = "TOO_SHORT"
    NON_TRADING = "NON_TRADING"


@dataclass
class YouTubeSource:
    """Normalized, canonicalized YouTube research source representation."""
    source_type: YouTubeSourceType
    canonical_url: str
    channel_id: str = ""
    channel_handle: str = ""
    channel_name: str = ""
    playlist_id: str = ""
    video_id: str = ""
    requested_limit: int = 10
    requested_sort: str = "recent"  # "recent", "popular", "oldest", "playlist_order"
    requested_at: float = field(default_factory=time.time)
    requested_by: str = "operator"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveredVideo:
    """Metadata-only capture of an enumerated YouTube video from a channel/playlist."""
    video_id: str
    canonical_url: str
    title: str
    channel_id: str = ""
    channel_name: str = ""
    upload_date: str = ""
    duration_seconds: int = 0
    duration_formatted: str = ""
    view_count: int = 0
    like_count: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)
    playlist_position: int | None = None
    thumbnail_url: str = ""
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoResearchAtom:
    """Structured extraction payload from a single video transcript."""
    video_id: str
    title: str
    canonical_url: str
    author_creator: str
    duration_seconds: int
    relevance: VideoRelevance
    has_transcript: bool
    transcript_method: str  # "MANUAL_CAPTION", "AUTO_CAPTION", "ASR", "NONE"
    segment_count: int
    facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    setups: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    hype_markers: list[str] = field(default_factory=list)
    is_hyped: bool = False
    skip_reason: str = ""
    ingested_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyEvolutionStep:
    """Tracks how a specific rule or setup condition evolved across creator uploads."""
    concept_name: str
    version: str  # "v1", "v2", "v3"
    earlier_video_id: str
    earlier_upload_date: str
    earlier_condition: str
    later_video_id: str
    later_upload_date: str
    later_condition: str
    evolution_type: str  # "CONDITION_ADDED", "CONDITION_REMOVED", "INVALIDATION_TIGHTENED"
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuleContradiction:
    """Identifies conflicting instructions across videos from the same creator."""
    rule_name: str
    earlier_video_id: str
    earlier_upload_date: str
    earlier_statement: str
    later_video_id: str
    later_upload_date: str
    later_statement: str
    severity: str  # "DIRECT_CONFLICT", "CONDITIONAL_REFINEMENT"
    epistemic_warning: str = "Internal contradiction detected. Unverified until empirical validation."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CreatorProfile:
    """Longitudinal research profile describing a creator's methodology."""
    channel_id: str
    channel_name: str
    channel_handle: str
    videos_analyzed_count: int
    primary_worldviews: list[str] = field(default_factory=list)
    recurring_concepts: list[dict[str, Any]] = field(default_factory=list)
    recurring_rules: list[dict[str, Any]] = field(default_factory=list)
    common_claims: list[str] = field(default_factory=list)
    hype_frequency_pct: float = 0.0
    contradictions_count: int = 0
    strategy_evolutions: list[StrategyEvolutionStep] = field(default_factory=list)
    profile_summary: str = ""
    epistemic_disclaimer: str = (
        "This profile describes the creator's qualitative content. It does NOT constitute empirical validation or endorsement."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class YouTubeExplorationResult:
    """Comprehensive multi-video synthesis and discovery report."""
    job_id: str
    source: YouTubeSource
    status: str  # "COMPLETED", "PARTIAL", "FAILED"
    started_at: float
    completed_at: float | None = None
    videos_discovered: int = 0
    videos_new: int = 0
    videos_skipped: int = 0
    videos_processed: int = 0
    videos_failed: int = 0
    video_inventory: list[DiscoveredVideo] = field(default_factory=list)
    per_video_research: list[VideoResearchAtom] = field(default_factory=list)
    recurring_concepts: list[dict[str, Any]] = field(default_factory=list)
    synthesized_candidates: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[RuleContradiction] = field(default_factory=list)
    strategy_evolutions: list[StrategyEvolutionStep] = field(default_factory=list)
    creator_profile: CreatorProfile | None = None
    executive_digest: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.source:
            d["source"] = self.source.to_dict()
        if self.creator_profile:
            d["creator_profile"] = self.creator_profile.to_dict()
        return d
