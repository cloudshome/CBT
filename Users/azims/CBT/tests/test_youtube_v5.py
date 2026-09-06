"""
tests/test_youtube_v5.py
========================
Comprehensive Unit & Invariant Test Suite for YouTube Research Intelligence V5:
Autonomous Channel & Playlist Explorer.

Constitutional Mandate & Invariant Verifications:
1. URL Canonicalization & Normalization (video, playlist, channel, @handle).
2. Strict Discovery Cap Bounding (default 10, max 50).
3. SQLite Deduplication Sentinel (youtube_crawl_history & research_provenance_ledger).
4. Timestamped Setup Extraction & Anti-Hype Epistemic Isolation.
5. Cross-Video Synthesis: Concept Consolidation, Contradiction Engine, Strategy Evolution.
6. Absolute Epistemic Invariant: Confidence == 0.0, Stage == UNTESTED.
7. Background Agent Execution & Job Management.
8. Telegram /explore & /playlist command handlers.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.database import db_manager
from core.telegram.handlers import handle_explore
from core.telegram.jobs import job_manager
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


class TestYouTubeV5DiscoveryAndNormalization:
    """Tests URL parsing, handle canonicalization, and hard bounding."""

    def test_normalize_handle(self):
        engine = YouTubeDiscoveryEngine()
        src = engine.normalize_source("@TraderTom", limit=10)
        assert src.source_type == YouTubeSourceType.CHANNEL
        assert src.channel_handle == "@TraderTom"
        assert src.canonical_url == "https://www.youtube.com/@TraderTom/videos"
        assert src.requested_limit == 10

    def test_normalize_playlist_url(self):
        engine = YouTubeDiscoveryEngine()
        src = engine.normalize_source("https://www.youtube.com/playlist?list=PLxyz12345", limit=20)
        assert src.source_type == YouTubeSourceType.PLAYLIST
        assert src.playlist_id == "PLxyz12345"
        assert src.canonical_url == "https://www.youtube.com/playlist?list=PLxyz12345"
        assert src.requested_limit == 20

    def test_normalize_single_video_url(self):
        engine = YouTubeDiscoveryEngine()
        src = engine.normalize_source("https://youtu.be/dQw4w9WgXcQ")
        assert src.source_type == YouTubeSourceType.VIDEO
        assert src.video_id == "dQw4w9WgXcQ"
        assert src.requested_limit == 1

    def test_discovery_cap_bounding(self):
        engine = YouTubeDiscoveryEngine()
        # Requesting limit of 150 must clamp to max allowed (50)
        src_over = engine.normalize_source("@AlphaSeeker", limit=150)
        assert src_over.requested_limit == YOUTUBE_MAX_EXPLORE_VIDEOS
        assert src_over.requested_limit <= 50

        # Requesting 0 or negative limit clamps to 1
        src_under = engine.normalize_source("@AlphaSeeker", limit=-5)
        assert src_under.requested_limit == 1


class TestYouTubeV5DeduplicationSentinel:
    """Tests SQLite crawl memory and deduplication logic."""

    def test_filter_unprocessed_and_deduplication(self):
        engine = YouTubeDiscoveryEngine()
        v1 = DiscoveredVideo(
            video_id="test_vid_001",
            canonical_url="https://www.youtube.com/watch?v=test_vid_001",
            title="Video 1: SMC Basics",
            duration_seconds=300,
        )
        v2 = DiscoveredVideo(
            video_id="test_vid_002",
            canonical_url="https://www.youtube.com/watch?v=test_vid_002",
            title="Video 2: Advanced Order Blocks",
            duration_seconds=450,
        )

        # Mark v1 as INGESTED
        engine.mark_video_status("test_vid_001", status="INGESTED")

        # Partition videos
        to_process, skipped = engine.filter_unprocessed([v1, v2], force_refresh=False)
        assert len(to_process) == 1
        assert to_process[0].video_id == "test_vid_002"
        assert len(skipped) == 1
        assert skipped[0].video_id == "test_vid_001"

        # Force refresh bypasses deduplication
        to_process_forced, skipped_forced = engine.filter_unprocessed([v1, v2], force_refresh=True)
        assert len(to_process_forced) == 2
        assert len(skipped_forced) == 0


class TestYouTubeV5DeconstructionAndAntiHype:
    """Tests setup identification, timestamp formatting, and hype claim quarantine."""

    def test_hype_detection_firewall(self):
        hype_text = "This secret strategy has a 100% win rate and you will never lose! Guaranteed profits."
        matches = HYPE_REGEX.findall(hype_text)
        assert len(matches) >= 2

        normal_text = "Wait for a market structure shift and fair value gap confluence before entering."
        assert len(HYPE_REGEX.findall(normal_text)) == 0

    def test_deconstruction_setups_and_rules(self):
        deconstructor = YouTubeDeconstructor()
        raw_snippets = [
            {"text": "Welcome to the trading session.", "start": 0.0, "duration": 10.0},
            {"text": "Notice price formed a clear Fair Value Gap after the liquidity sweep.", "start": 10.0, "duration": 25.0},
            {"text": "Enter when 15m candle closes confirming displacement through the order block.", "start": 35.0, "duration": 20.0},
            {"text": "Stop loss is below the swing low wick and take profit is toward opposing highs.", "start": 55.0, "duration": 20.0},
            {"text": "This guarantees easy money and 100% win rate!", "start": 75.0, "duration": 15.0},
        ]

        with patch.object(deconstructor, "fetch_subtitles", return_value=(raw_snippets, "MANUAL_CAPTION")):
            video = DiscoveredVideo(
                video_id="smc_master_1",
                canonical_url="https://www.youtube.com/watch?v=smc_master_1",
                title="SMC Strategy Masterclass",
                channel_name="ProTrader",
                duration_seconds=90,
            )
            atom = deconstructor.deconstruct_video(video)

            assert atom.has_transcript is True
            assert atom.transcript_method == "MANUAL_CAPTION"
            assert atom.is_hyped is True
            assert any("100% win rate" in h.lower() for h in atom.hype_markers)

            # Check extracted setups
            setup_types = [s["setup_type"] for s in atom.setups]
            assert "FAIR_VALUE_GAP" in setup_types
            assert "LIQUIDITY_SWEEP" in setup_types
            assert "ORDER_BLOCK" in setup_types

            # Check rules extracted
            assert len(atom.rules) >= 1
            # Check promotional claims quarantined
            assert len(atom.claims) >= 1
            assert atom.claims[0]["classification"] == "PROMOTIONAL / UNVERIFIED"


class TestYouTubeV5SynthesisAndEpistemicInvariants:
    """Verifies concept consolidation, contradiction engine, and epistemic quarantine."""

    def test_cross_video_synthesis_and_epistemic_invariants(self):
        synthesizer = CrossVideoSynthesizer()

        # Create two video atoms simulating creator uploading over time
        atom1 = VideoResearchAtom(
            video_id="vid_early",
            title="Session 1: Sweep Strategy",
            canonical_url="https://youtube.com/watch?v=vid_early",
            author_creator="TraderJoe",
            duration_seconds=600,
            relevance=VideoRelevance.RESEARCH_RELEVANT,
            has_transcript=True,
            transcript_method="MANUAL_CAPTION",
            segment_count=10,
            setups=[
                {"setup_type": "LIQUIDITY_SWEEP", "timestamp": "02:15", "context": "Sweep of the previous day low", "video_id": "vid_early"},
                {"setup_type": "FAIR_VALUE_GAP", "timestamp": "04:30", "context": "Enter at the FVG immediately", "video_id": "vid_early"},
            ],
            rules=[
                {"rule_text": "enter when liquidity sweeps below the previous day low", "timestamp": "02:15", "video_id": "vid_early"},
            ],
            claims=[],
            ingested_at=time.time() - 86400,
        )

        atom2 = VideoResearchAtom(
            video_id="vid_late",
            title="Session 2: Updated Sweep Model",
            canonical_url="https://youtube.com/watch?v=vid_late",
            author_creator="TraderJoe",
            duration_seconds=750,
            relevance=VideoRelevance.RESEARCH_RELEVANT,
            has_transcript=True,
            transcript_method="MANUAL_CAPTION",
            segment_count=12,
            setups=[
                {"setup_type": "LIQUIDITY_SWEEP", "timestamp": "03:10", "context": "Sweep of key liquidity level", "video_id": "vid_late"},
                {"setup_type": "ORDER_BLOCK", "timestamp": "05:40", "context": "Order block mitigation confirmation", "video_id": "vid_late"},
            ],
            rules=[
                {"rule_text": "enter when liquidity sweeps and wait for HTF displacement confirmation", "timestamp": "03:10", "video_id": "vid_late"},
            ],
            claims=[],
            ingested_at=time.time(),
        )

        atoms = [atom1, atom2]

        # 1. Concept Consolidation
        concepts = synthesizer.consolidate_concepts(atoms)
        assert len(concepts) >= 2
        sweep_concept = next(c for c in concepts if c["concept_name"] == "LIQUIDITY_SWEEP")
        assert sweep_concept["appearance_count"] == 2
        assert len(sweep_concept["video_citations"]) == 2

        # 2. Contradiction Detection
        contradictions = synthesizer.detect_contradictions(atoms)
        assert len(contradictions) >= 1
        cont = contradictions[0]
        assert cont.rule_name == "Liquidity Sweep Entry Condition"
        assert cont.earlier_video_id == "vid_early"
        assert cont.later_video_id == "vid_late"
        assert cont.severity == "CONDITIONAL_REFINEMENT"
        assert "UNTESTED" in cont.epistemic_warning

        # 3. Strategy Evolution Tracking
        evolutions = synthesizer.track_strategy_evolution(atoms)
        assert len(evolutions) >= 1
        assert evolutions[0].version == "v2.0"

        # 4. Creator Profile Assembly
        profile = synthesizer.build_creator_profile(atoms, channel_name="TraderJoe")
        assert profile.channel_name == "TraderJoe"
        assert profile.videos_analyzed_count == 2
        assert profile.contradictions_count >= 1

        # 5. Formulate Candidates & ABSOLUTE EPISTEMIC INVARIANT CHECK
        candidates = synthesizer.formulate_candidates(atoms, profile)
        assert len(candidates) >= 1

        for cand in candidates:
            # STRICT LEVEL 1 CONSTITUTIONAL INVARIANTS:
            assert cand["confidence_score"] == 0.0, "Epistemic violation: confidence must be strictly 0.0!"
            assert cand["validation_stage"] == "UNTESTED", "Epistemic violation: stage must be UNTESTED!"
            assert "Awaiting Walk-Forward" in cand["empirical_evidence"]
            assert cand["creator_repetition_count"] >= 1
            assert len(cand["source_citations"]) >= 1


class TestYouTubeV5AgentAndTelegramCommand:
    """Tests end-to-end background orchestration and Telegram commands."""

    @pytest.mark.asyncio
    async def test_agent_explore_execution(self):
        agent = YouTubeExplorationAgent()
        mock_discovered = [
            DiscoveredVideo(
                video_id="mock_vid_1",
                canonical_url="https://youtube.com/watch?v=mock_vid_1",
                title="Mock Trading Video 1",
                channel_name="QuantMaster",
                duration_seconds=360,
                duration_formatted="06:00",
            ),
        ]

        with patch.object(youtube_discovery, "discover_videos", return_value=mock_discovered), \
             patch.object(youtube_deconstructor, "fetch_subtitles", return_value=([
                 {"text": "Look for Fair Value Gap after Market Structure Shift", "start": 10.0, "duration": 20.0}
             ], "MANUAL_CAPTION")), \
             patch("core.youtube.agent.universal_ingestor.ingest", new_callable=AsyncMock) as mock_ingest:

            result = await agent.explore(
                source_url_or_handle="@QuantMaster",
                limit=5,
                requested_by="test_suite",
            )

            assert isinstance(result, YouTubeExplorationResult)
            assert result.status == "COMPLETED"
            assert result.videos_discovered == 1
            assert result.videos_processed == 1
            assert result.creator_profile is not None
            assert len(result.executive_digest) > 50
            assert "YouTube Research Dossier" in result.executive_digest

    @pytest.mark.asyncio
    async def test_telegram_explore_command_dispatch(self):
        with patch("core.telegram_bot.telegram_bot.send_message", new_callable=AsyncMock) as mock_send, \
             patch("core.youtube.agent.youtube_agent.start_background_exploration", return_value="JOB-MOCK-123"):
            # 1. Empty arguments -> returns help guidance
            res_help = await handle_explore("", chat_id="123456")
            assert "YOUTUBE RESEARCH INTELLIGENCE V5" in res_help
            assert mock_send.called

            # 2. Valid handle and limit -> dispatches job receipt
            res_dispatch = await handle_explore("@TraderTom 10", chat_id="123456")
            assert "YOUTUBE RESEARCH EXPLORATION DISPATCHED" in res_dispatch
            assert "Job ID:" in res_dispatch
            assert "JOB-MOCK-123" in res_dispatch
            assert "Extraction Cap:" in res_dispatch
            assert "10 videos" in res_dispatch

    def test_youtube_rest_endpoints(self):
        from fastapi.testclient import TestClient
        from app import app

        client = TestClient(app)

        with patch.object(youtube_agent, "explore", new_callable=AsyncMock):
            res = client.post(
                "/api/research/youtube/explore",
                json={"source_url_or_handle": "@TraderTom", "limit": 5},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ACCEPTED"
            assert "job_id" in data
            job_id = data["job_id"]

            res_list = client.get("/api/research/youtube/jobs")
            assert res_list.status_code == 200
            jobs = res_list.json()["jobs"]
            assert any(j["job_id"] == job_id for j in jobs)

            res_job = client.get(f"/api/research/youtube/jobs/{job_id}")
            assert res_job.status_code == 200
            assert res_job.json()["job_id"] == job_id


