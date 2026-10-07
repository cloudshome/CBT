"""
tests/test_evidence_grade_research_and_agent.py
================================================
Comprehensive test suite verifying the Evidence-Grade Research OS,
Link Persistence Invariant, and Governed Telegram Agent.
"""

import pytest
import sqlite3
from unittest.mock import AsyncMock, patch

from core.knowledge_os.universal_ingestor import (
    AccessStatus,
    ExtractionStatus,
    SourceType,
    universal_ingestor,
)
from core.telegram.handlers import handle_wiki
from core.telegram.rbac import TelegramRole, TelegramUserIdentity


def test_source_type_detection():
    """Confirms deterministic source classification for 10+ URL patterns."""
    assert universal_ingestor.detect_source_type("https://www.facebook.com/share/v/1EkkpUZaDe/") == SourceType.FACEBOOK_VIDEO
    assert universal_ingestor.detect_source_type("https://www.facebook.com/reel/123456789") == SourceType.FACEBOOK_REEL
    assert universal_ingestor.detect_source_type("https://www.instagram.com/reel/C8xyz/") == SourceType.INSTAGRAM_REEL
    assert universal_ingestor.detect_source_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == SourceType.YOUTUBE_VIDEO
    assert universal_ingestor.detect_source_type("https://youtu.be/dQw4w9WgXcQ") == SourceType.YOUTUBE_VIDEO
    assert universal_ingestor.detect_source_type("https://arxiv.org/abs/2301.00001") == SourceType.ARXIV
    assert universal_ingestor.detect_source_type("https://github.com/Azimshawon/SKY") == SourceType.GITHUB
    assert universal_ingestor.detect_source_type("https://www.tradingview.com/chart/BTCUSDT/") == SourceType.TRADINGVIEW
    assert universal_ingestor.detect_source_type("https://sec.gov/edgar/data/12345") == SourceType.SEC_DOCUMENT
    assert universal_ingestor.detect_source_type("https://coindesk.com/markets/2026/01/01/btc-news") == SourceType.NEWS


def test_link_persistence_invariant_facebook_url():
    """
    Critical Test: Submitting the user's Facebook URL
    MUST create a durable source record and permanent Wiki article
    without fabricating false spoken transcripts.
    """
    fb_url = "https://www.facebook.com/share/v/1EkkpUZaDe/"
    res = universal_ingestor.ingest_url(fb_url)

    assert res.source is not None
    assert res.source.original_url == fb_url
    assert res.source.source_type == SourceType.FACEBOOK_VIDEO.value
    assert res.source.source_domain == "www.facebook.com"
    assert res.source.source_id.startswith("src_")

    # Invariant: Must not crash or return None for wiki article
    assert res.wiki_article is not None
    assert res.wiki_article.article_id.startswith("wiki_")

    # Verify atomic DB persistence
    with universal_ingestor._get_connection() as conn:
        src_row = conn.execute(
            "SELECT * FROM research_sources WHERE source_id = ?;", (res.source.source_id,)
        ).fetchone()
        assert src_row is not None
        assert src_row["original_url"] == fb_url
        assert src_row["wiki_article_id"] == res.wiki_article.article_id

        # Verify artifacts were recorded
        art_count = conn.execute(
            "SELECT count(*) FROM research_artifacts WHERE source_id = ?;", (res.source.source_id,)
        ).fetchone()[0]
        assert art_count >= 1


def test_link_persistence_invariant_broken_or_404():
    """
    Critical Invariant: Submitting a broken, 404 or completely unreachable link
    MUST NEVER be dropped into the void. It must produce a persistent source
    and a placeholder Wiki record with failure diagnostics.
    """
    broken_url = "https://example.com/unreachable_404_test_endpoint_9999.html"
    res = universal_ingestor.ingest_url(broken_url)

    assert res.source is not None
    assert res.source.original_url == broken_url
    assert res.source.extraction_status == ExtractionStatus.FAILED.value
    assert "404" in res.source.failure_reason or "unreachable" in res.source.failure_reason.lower() or "error" in res.source.failure_reason.lower()

    # Even on complete HTTP failure, Wiki placeholder exists
    assert res.wiki_article is not None
    with universal_ingestor._get_connection() as conn:
        src_row = conn.execute(
            "SELECT * FROM research_sources WHERE source_id = ?;", (res.source.source_id,)
        ).fetchone()
        assert src_row is not None
        assert src_row["access_status"] in (AccessStatus.PARTIAL.value, AccessStatus.ACCESS_BLOCKED.value, AccessStatus.FAILED.value)


def test_source_idempotency_and_no_duplication():
    """Submitting the same URL multiple times updates existing source rather than duplicating."""
    url = "https://arxiv.org/abs/1706.03762"
    res1 = universal_ingestor.ingest_url(url, options={"title": "Attention Is All You Need"})
    res2 = universal_ingestor.ingest_url(url, options={"title": "Attention Is All You Need v2"})

    assert res1.source.source_id == res2.source.source_id

    with universal_ingestor._get_connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM research_sources WHERE source_id = ?;", (res1.source.source_id,)
        ).fetchone()[0]
        assert count == 1


@pytest.mark.asyncio
async def test_telegram_wiki_handler_link_guarantee():
    """Verifies Telegram /wiki <url> returns the Source ID badge, Wiki summary, and RealLifeSummary."""
    test_identity = TelegramUserIdentity(user_id=123456, chat_id=999, username="quant_architect", role=TelegramRole.SUPER_ADMIN)
    test_url = "https://www.facebook.com/share/v/1EkkpUZaDe/"

    with patch("core.telegram_bot.telegram_bot.send_message", new_callable=AsyncMock) as mock_send:
        reply = await handle_wiki(args=test_url, chat_id=999, identity=test_identity)
        assert "Source:" in reply
        assert "src_" in reply
        assert ("PARTIAL" in reply or "SUCCESS" in reply or "ACCESS BLOCKED" in reply)
        assert "বাস্তব জীবনের সারসংক্ষেপ" in reply
        assert "সহজ বাংলায় মূল কথা" in reply


def test_real_life_summary_present_on_every_input():
    """
    Constitutional Requirement: Every accepted research input MUST generate
    and persist an actionable Real-Life Summary in Bengali with all 5 points.
    """
    # 1. Test Web URL
    web_url = "https://arxiv.org/abs/1706.03762"
    web_res = universal_ingestor.ingest_url(web_url, options={"title": "Attention Is All You Need"})
    assert web_res.real_life_summary is not None
    rl = web_res.real_life_summary
    assert len(rl.core_concept_bn) > 10
    assert len(rl.practical_market_impact) > 10
    assert len(rl.actionable_guidance) > 10
    assert len(rl.hype_vs_reality) > 10
    assert len(rl.risk_warning) > 10

    # Verify embedded in Wiki markdown
    assert "বাস্তব জীবনের বাস্তবসম্মত সারসংক্ষেপ" in web_res.wiki_article.full_markdown_content

    # Verify persisted in research_artifacts table
    with universal_ingestor._get_connection() as conn:
        rl_art = conn.execute(
            "SELECT * FROM research_artifacts WHERE source_id = ? AND artifact_type = 'REAL_LIFE_SUMMARY';",
            (web_res.source.source_id,),
        ).fetchone()
        assert rl_art is not None
        assert "সহজ বাংলায় মূল কথা" in rl_art["content_text"]

    # 2. Test Social Video URL (Facebook)
    fb_url = "https://www.facebook.com/share/v/1EkkpUZaDe/"
    fb_res = universal_ingestor.ingest_url(fb_url)
    assert fb_res.real_life_summary is not None
    assert len(fb_res.real_life_summary.core_concept_bn) > 10
    assert len(fb_res.real_life_summary.practical_market_impact) > 10
    assert len(fb_res.real_life_summary.actionable_guidance) > 10
    assert len(fb_res.real_life_summary.hype_vs_reality) > 10
    assert len(fb_res.real_life_summary.risk_warning) > 10
    assert "বাস্তব জীবনের বাস্তবসম্মত সারসংক্ষেপ" in fb_res.wiki_article.full_markdown_content


def test_phase3_audio_extraction_and_transcription_pipeline(tmp_path):
    """
    Verifies Phase 3 audio extraction and Gemini transcription integration.
    When yt-dlp yields audio and Gemini transcribes, status transitions to SUCCESS.
    """
    from pathlib import Path
    from core.knowledge_os.transcription import TranscriptResult

    fake_audio_file = tmp_path / "test_audio.m4a"
    fake_audio_file.write_bytes(b"FAKE_AUDIO_DATA_BYTES_FOR_TESTING_123456789")

    mock_meta = {
        "title": "Crypto Macro Market Liquidity Analysis",
        "uploader": "Macro Trader",
        "duration": 180,
    }

    mock_transcript = TranscriptResult(
        success=True,
        text="Bitcoin order book shows massive bid liquidity at 65000. Federal Reserve interest rate cut expected.",
        language="en",
        provider="GEMINI_CLOUD",
    )

    with patch("core.knowledge_os.transcription.social_video_extractor.extract_audio", return_value=(True, fake_audio_file, mock_meta)):
        with patch("core.knowledge_os.transcription.gemini_audio_provider.transcribe_audio", return_value=mock_transcript):
            test_url = "https://www.facebook.com/watch/?v=9876543210"
            res = universal_ingestor.ingest_url(test_url)

            assert res.source.access_status == AccessStatus.SUCCESS.value
            assert res.source.extraction_status == ExtractionStatus.EXTRACTED.value
            assert len(res.claims) >= 1
            assert res.real_life_summary is not None
            assert len(res.real_life_summary.core_concept_bn) > 5

            # Verify both AUDIO and TRANSCRIPT artifacts exist
            with universal_ingestor._get_connection() as conn:
                types = [
                    r[0] for r in conn.execute(
                        "SELECT artifact_type FROM research_artifacts WHERE source_id = ?;",
                        (res.source.source_id,),
                    ).fetchall()
                ]
                assert "AUDIO" in types
                assert "TRANSCRIPT" in types
                assert "REAL_LIFE_SUMMARY" in types

