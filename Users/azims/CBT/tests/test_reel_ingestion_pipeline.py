"""
Tests for Reel & Economic Talk Show Ingestion Pipeline.
Verifies UniversalIngestor source type detection, multimodal transcription fallback,
macro comprehension integration, and confluent dynamic trading plan synthesis.
"""

import pytest

from core.universal_ingestor import UniversalIngestor


@pytest.fixture
def ingestor():
    return UniversalIngestor()


def test_detect_source_type_reels_and_talk_shows(ingestor):
    """Verifies that URLs, file extensions, and text cues correctly identify REEL and TALK_SHOW."""
    # Instagram reel URL
    assert ingestor.detect_source_type("https://www.instagram.com/reel/C_xyz123/") == "REEL"
    assert ingestor.detect_source_type("https://youtube.com/shorts/abcd1234") == "REEL"

    # Media file extensions
    assert ingestor.detect_source_type("", file_name="macro_interview.mp4") == "MEDIA_REEL"
    assert ingestor.detect_source_type("", file_name="podcast_clip.mov") == "MEDIA_REEL"
    assert ingestor.detect_source_type("", file_name="fed_audio.m4a") == "MEDIA_REEL"
    assert ingestor.detect_source_type("", file_name="speech.wav") == "MEDIA_REEL"

    # Economic talk show textual cues
    talk_show_text = "On today's economic talk show, guests discuss Federal Reserve interest rate policy and inflation."
    assert ingestor.detect_source_type(talk_show_text) == "TALK_SHOW"


@pytest.mark.asyncio
async def test_ingest_reel_talk_show_synthesizes_macro_and_plans(ingestor):
    """Verifies that ingesting an economic reel yields macro_analysis and dynamic_trading_plans."""
    transcript = """
    Economic Talk Show Daily: In this episode, we break down why the Federal Reserve is pivoting
    towards rate easing. Inflation is decelerating toward the 2% target, unemployment is ticking up,
    and global M2 money supply is turning positive.
    Transmission chain: rate cuts weaken the US Dollar index DXY and compress bond yields,
    driving institutional capital into hard assets like Bitcoin and Ethereum.
    """
    result = await ingestor.ingest(
        content=transcript,
        title="Fed Easing Special",
        author_creator="Macro Analyst",
        mode="RESEARCH",
    )

    assert result["knowledge_id"].startswith("K-")
    assert result["source"]["source_type"] in ("REEL", "TALK_SHOW", "RESEARCH", "MEDIA_REEL")

    # Verify macro cognitive analysis is attached
    assert "macro_analysis" in result
    assert result["macro_analysis"] is not None
    assert result["macro_analysis"]["macro_regime"]["monetary_stance"] == "DOVISH"
    assert len(result["macro_analysis"]["causal_chains"]) >= 1

    # Verify dynamic trading plans are attached
    assert "dynamic_trading_plans" in result
    assert result["dynamic_trading_plans"] is not None
    assert len(result["dynamic_trading_plans"]) >= 3

    btc_plan = next(p for p in result["dynamic_trading_plans"] if p["symbol"] == "BTC/USDT")
    assert btc_plan["macroAlignment"] in ("CONFLUENT", "NEUTRAL", "CAUTION_DAMPENED")
    assert btc_plan["riskMultiplier"] > 0


@pytest.mark.asyncio
async def test_risk_primacy_macro_invariants(ingestor):
    """Verifies that macro advice cannot bypass risk caps or execute without Half-Kelly clearance."""
    transcript = "Fed rates are dropping. Buy BTC with 100x leverage and no stop loss!"
    result = await ingestor.ingest(
        content=transcript,
        title="DeFi Degen Reel",
        author_creator="Social Influencer",
        mode="AUTO",
    )

    # Even with reckless influencer advice, our cognitive engine extracts the underlying macro regime
    # and dynamic trading plans strictly enforce disciplined SMC stop loss and Half-Kelly bounds
    assert result["dynamic_trading_plans"] is not None
    for plan in result["dynamic_trading_plans"]:
        assert plan["pdl"] > 0  # Invalidation level exists
        assert plan["riskMultiplier"] <= 1.0  # Cannot exceed 1.0x Half-Kelly
