"""
core/youtube/__init__.py
========================
YouTube Research Intelligence V5 — Autonomous Channel & Playlist Explorer package.
"""

from core.youtube.agent import YouTubeExplorationAgent, youtube_agent
from core.youtube.deconstruction import (
    HYPE_REGEX,
    SETUP_PATTERNS,
    YouTubeDeconstructor,
    youtube_deconstructor,
)
from core.youtube.discovery import (
    DEFAULT_EXPLORE_LIMIT,
    YOUTUBE_MAX_EXPLORE_VIDEOS,
    YouTubeDiscoveryEngine,
    youtube_discovery,
)
from core.youtube.models import (
    CreatorProfile,
    DiscoveredVideo,
    RuleContradiction,
    StrategyEvolutionStep,
    VideoRelevance,
    VideoResearchAtom,
    YouTubeExplorationResult,
    YouTubeSource,
    YouTubeSourceType,
)
from core.youtube.synthesis import CrossVideoSynthesizer, cross_video_synthesizer

__all__ = [
    "DEFAULT_EXPLORE_LIMIT",
    "HYPE_REGEX",
    "SETUP_PATTERNS",
    "YOUTUBE_MAX_EXPLORE_VIDEOS",
    "CreatorProfile",
    "CrossVideoSynthesizer",
    "DiscoveredVideo",
    "RuleContradiction",
    "StrategyEvolutionStep",
    "VideoRelevance",
    "VideoResearchAtom",
    "YouTubeDeconstructor",
    "YouTubeDiscoveryEngine",
    "YouTubeExplorationAgent",
    "YouTubeExplorationResult",
    "YouTubeSource",
    "YouTubeSourceType",
    "cross_video_synthesizer",
    "youtube_agent",
    "youtube_deconstructor",
    "youtube_discovery",
]
