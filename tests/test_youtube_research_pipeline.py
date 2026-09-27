"""
tests/test_youtube_research_pipeline.py
========================================
Comprehensive Verification Suite for the 10/10 YouTube Research Ingestion Pipeline.

Validates the 12-point research ladder:
1. Video ID parsing across all YouTube URL variations and raw IDs.
2. MM:SS timecode formatting and seconds bi-directional mapping.
3. Chronological transcript segmentation with start/end bounds.
4. Detection of qualitative author hype phrases ("100% win rate", "never lose", etc.).
5. Zero-Fabrication Anti-Hype Epistemic Firewall (Article I, Section 1.4):
   - Epistemic status set to UNVERIFIED.
   - Assumed alpha set to 0.0.
   - Candidate strategy stage set to UNTESTED.
6. Temporal grounding of atomic claims with timestamp badges and deep links (&t={sec}s).
7. End-to-end ingestion pipeline via UniversalIngestor.
8. Database persistence in brain_memory research_claims table.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.database import db_manager
from core.knowledge_graph_engine import knowledge_graph_engine
from core.universal_ingestor import universal_ingestor
from core.youtube_extractor import (
    YouTubeResearchExtractor,
    format_timecode,
    parse_video_id,
    timecode_to_seconds,
    youtube_extractor,
)


class TestYouTubeExtractorBasics:
    """Tests URL parsing, timecode formatting, and segmentation."""

    def test_parse_video_id_variants(self):
        # Standard watch URL
        assert parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        # Watch URL with time query param
        assert parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s") == "dQw4w9WgXcQ"
        # Short youtu.be URL
        assert parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert parse_video_id("https://youtu.be/dQw4w9WgXcQ?t=45") == "dQw4w9WgXcQ"
        # Embed URL
        assert parse_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        # Shorts URL
        assert parse_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        # Live URL
        assert parse_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        # Raw 11-character video ID
        assert parse_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        # Invalid inputs
        assert parse_video_id("not_a_valid_youtube_url") is None
        assert parse_video_id("") is None

    def test_timecode_conversions(self):
        # Seconds to MM:SS
        assert format_timecode(0.0) == "00:00"
        assert format_timecode(45.0) == "00:45"
        assert format_timecode(75.0) == "01:15"
        assert format_timecode(1122.0) == "18:42"
        # Hours formatting
        assert format_timecode(3665.0) == "01:01:05"

        # MM:SS back to seconds
        assert timecode_to_seconds("00:00") == 0.0
        assert timecode_to_seconds("00:45") == 45.0
        assert timecode_to_seconds("01:15") == 75.0
        assert timecode_to_seconds("18:42") == 1122.0
        assert timecode_to_seconds("01:01:05") == 3665.0

    def test_segment_transcript(self):
        extractor = YouTubeResearchExtractor()
        raw_snippets = [
            {"text": "Welcome back to the channel.", "start": 0.0, "duration": 5.0},
            {
                "text": "Today we are looking at the 15-minute BTC chart.",
                "start": 5.0,
                "duration": 10.0,
            },
            {
                "text": "Notice this massive liquidity sweep below the Asian session low.",
                "start": 15.0,
                "duration": 20.0,
            },
            {
                "text": "Once price creates a market structure shift, we look for the FVG entry.",
                "start": 35.0,
                "duration": 25.0,
            },
            {
                "text": "Target the opposing high for a clean 2 to 1 risk reward ratio.",
                "start": 60.0,
                "duration": 20.0,
            },
        ]

        segments = extractor.segment_transcript(raw_snippets, target_chunk_sec=45.0)
        assert len(segments) >= 2

        # Verify first chunk attributes
        chunk1 = segments[0]
        assert "Welcome back" in chunk1["text"]
        assert chunk1["start_sec"] == 0.0
        assert chunk1["timestamp_start"] == "00:00"
        assert chunk1["end_sec"] >= 45.0

        # Verify second chunk attributes
        chunk2 = segments[1]
        assert "Target the opposing high" in chunk2["text"]
        assert chunk2["start_sec"] >= 45.0

    def test_detect_hype_markers(self):
        extractor = YouTubeResearchExtractor()
        clean_text = "This setup seeks a 1.5R expectancy during London open liquidity sweeps."
        assert len(extractor.detect_hype_markers(clean_text)) == 0

        hyped_text = "This secret strategy has a 100% win rate, you will never lose, it is the holy grail of trading!"
        markers = extractor.detect_hype_markers(hyped_text)
        assert len(markers) >= 3


class TestEpistemicFirewallAndPipeline:
    """Verifies Zero-Fabrication Anti-Hype Epistemic Firewall and End-to-End Ingestion."""

    @pytest.mark.asyncio
    async def test_youtube_ingestion_end_to_end_with_temporal_grounding(self):
        mock_payload = {
            "success": True,
            "video_id": "test_vid_123",
            "video_url": "https://www.youtube.com/watch?v=test_vid_123",
            "title": "Institutional Order Flow Masterclass",
            "author_creator": "AlphaQuant Research",
            "duration": 120,
            "duration_formatted": "02:00",
            "description": "Educational breakdown of session liquidity sweeps.",
            "has_transcript": True,
            "segment_count": 2,
            "segments": [
                {
                    "text": "Hello traders. Let's analyze the algorithmic liquidity delivery. When BTC sweeps the previous day high and leaves an unmitigated fair value gap, we enter short.",
                    "start_sec": 10.0,
                    "end_sec": 55.0,
                    "timestamp_start": "00:10",
                    "timestamp_end": "00:55",
                },
                {
                    "text": "This guaranteed secret indicator gives you a 100% win rate and you will never lose! Exit strictly at the opposing liquidity pool with half-kelly risk management.",
                    "start_sec": 60.0,
                    "end_sec": 120.0,
                    "timestamp_start": "01:00",
                    "timestamp_end": "02:00",
                },
            ],
            "full_transcript": "Hello traders. Let's analyze the algorithmic liquidity delivery. When BTC sweeps the previous day high and leaves an unmitigated fair value gap, we enter short. This guaranteed secret indicator gives you a 100% win rate and you will never lose! Exit strictly at the opposing liquidity pool with half-kelly risk management.",
            "hype_markers_detected": ["100% win rate", "never lose"],
            "is_hyped": True,
        }

        with patch.object(
            youtube_extractor, "extract_full_video_research", return_value=mock_payload
        ):
            result = await universal_ingestor.ingest(
                content="https://www.youtube.com/watch?v=test_vid_123",
                mode="RESEARCH",
            )

        # 1. Verify Top-Level Metadata
        assert result["source_id"].startswith("S-")
        assert result["source"]["title"] == "Institutional Order Flow Masterclass"
        assert result["source"]["author_creator"] == "AlphaQuant Research"
        assert result["source"]["source_type"] == "YOUTUBE"

        # 2. Verify Claims Extraction and Temporal Grounding
        claims = result["claims"]
        assert len(claims) == 2

        claim_1 = claims[0]
        assert claim_1["timestamp_start"] == "00:10"
        assert claim_1["timestamp_end"] == "00:55"
        assert claim_1["timestamp_start_sec"] == 10.0
        assert claim_1["timestamp_end_sec"] == 55.0
        assert "&t=10s" in claim_1["video_url"]
        assert claim_1["author_creator"] == "AlphaQuant Research"
        assert claim_1["epistemic_status"] == "UNVERIFIED"

        claim_2 = claims[1]
        assert claim_2["timestamp_start"] == "01:00"
        assert claim_2["timestamp_end"] == "02:00"
        assert "&t=60s" in claim_2["video_url"]
        assert claim_2["hype_detected"] is True
        assert any("100% win rate" in h for h in claim_2["hype_markers"])

        # 3. Constitutional Epistemic Firewall (Article I, Section 1.4)
        # Even with hyped claims, confidence must be 0.0 (zero assumed alpha)
        for cl in claims:
            assert cl["confidence_score"] == 0.0
            assert cl["epistemic_status"] == "UNVERIFIED"

        # 4. Candidate Strategy Stage Must Be Strictly UNTESTED
        candidates = result["strategy_candidates"]
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand["validation_stage"] == "UNTESTED"
        assert cand["zero_alpha_assumption"] is True
        assert cand["requires_deterministic_backtest"] is True
        assert len(cand["supporting_claims"]) > 0

        # 5. Database Persistence & Graph Query
        graph_payload = knowledge_graph_engine.get_full_graph_payload()
        db_claims = graph_payload["nodes"]["claims"]
        persisted_claim_ids = [c["claim_id"] for c in db_claims]
        assert claim_1["claim_id"] in persisted_claim_ids

        # Verify DB row has timestamp columns populated
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT * FROM research_claims WHERE claim_id = ?",
                (claim_1["claim_id"],),
            ).fetchone()
            assert row is not None
            assert row["timestamp_start"] == "00:10"
            assert row["timestamp_end"] == "00:55"
            assert row["timestamp_start_sec"] == 10.0
            assert row["timestamp_end_sec"] == 55.0
            assert row["video_url"] == claim_1["video_url"]
            assert row["author_creator"] == "AlphaQuant Research"
            assert row["epistemic_status"] == "UNVERIFIED"
