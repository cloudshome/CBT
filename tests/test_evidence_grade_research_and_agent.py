"""
tests/test_evidence_grade_research_and_agent.py
================================================
Comprehensive test suite verifying the Evidence-Grade Research OS,
Link Persistence Invariant, and Governed Telegram Agent.
"""

import pytest
import sqlite3
import time
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


@pytest.mark.asyncio
async def test_tool_gateway_class_d_permanently_blocked():
    """
    Constitutional Invariant: Class D (Live Capital / Real Execution)
    MUST be permanently blocked with zero bypass.
    """
    from core.telegram.tool_gateway import ToolClass, telegram_tool_gateway

    identity = TelegramUserIdentity(
        user_id=123,
        chat_id=456,
        username="admin",
        role=TelegramRole.SUPER_ADMIN,
    )
    res = await telegram_tool_gateway.execute_tool(
        tool_name="execute_live_order",
        arguments={"symbol": "BTC/USDT", "size": 1.0},
        identity=identity,
    )
    assert res.success is False
    assert res.tool_class == ToolClass.CLASS_D_LIVE_BLOCKED
    assert "CONSTITUTIONAL VIOLATION" in res.output_text
    assert "REAL_CAPITAL_ENABLED = False" in res.output_text


@pytest.mark.asyncio
async def test_tool_gateway_two_phase_confirmation_lifecycle():
    """
    Verifies Class C simulation action lifecycle:
    1. Plan trade -> Generates pending confirmation token.
    2. Confirm action -> Commits paper position atomically into portfolio.
    """
    from core.telegram.tool_gateway import ToolClass, telegram_tool_gateway
    from core.portfolio_shadow import portfolio_shadow

    identity = TelegramUserIdentity(
        user_id=789,
        chat_id=101,
        username="trader",
        role=TelegramRole.TRADER,
    )

    # Phase 1: Plan
    plan_res = await telegram_tool_gateway.execute_tool(
        tool_name="plan_trade_signal",
        arguments={"symbol": "BTC/USDT"},
        identity=identity,
    )
    assert plan_res.success is True
    assert plan_res.requires_confirmation is True
    assert plan_res.confirmation_token.startswith("CONF_")
    assert "PROPOSED PAPER TRADE PLAN" in plan_res.output_text

    # Phase 2: Confirm
    confirm_res = await telegram_tool_gateway.execute_tool(
        tool_name="confirm_action",
        arguments={"token": plan_res.confirmation_token},
        identity=identity,
    )
    assert confirm_res.success is True
    assert "PAPER POSITION OPENED" in confirm_res.output_text
    assert "Position ID" in confirm_res.output_text


@pytest.mark.asyncio
async def test_agent_planner_intent_resolution_and_bengali_routing():
    """
    Verifies natural language intent resolution in Bengali, English, and Banglish.
    """
    from core.telegram.agent_planner import telegram_agent_planner

    # 1. Ask positions in Bengali
    d1 = telegram_agent_planner.resolve_intent("আমার খোলা পজিশন কি আছে?", user_id=999)
    assert d1.intent == "GET_POSITIONS"
    assert d1.tool_name == "get_open_positions"

    # 2. Ask signal in Bengali
    d2 = telegram_agent_planner.resolve_intent("বিটিসির জন্য সিগন্যাল দাও", user_id=999)
    assert d2.intent == "PLAN_SIGNAL"
    assert d2.tool_name == "plan_trade_signal"

    # 3. What AI learned today in Bengali
    d3 = telegram_agent_planner.resolve_intent("আজকে কি শিখলে?", user_id=999)
    assert d3.intent == "GET_LEARNED"
    assert d3.tool_name == "get_ai_learned_today"

    # 4. Ingest Link
    d4 = telegram_agent_planner.resolve_intent("এই লিংকটা রিসার্চ ল্যাবে রাখো https://arxiv.org/abs/1706.03762", user_id=999)
    assert d4.intent == "INGEST_URL"
    assert d4.tool_name == "ingest_research_url"

    # 5. Project status in English
    d5 = telegram_agent_planner.resolve_intent("what is terminal status?", user_id=999)
    assert d5.intent == "GET_STATUS"
    assert d5.tool_name == "get_project_status"


@pytest.mark.asyncio
async def test_agent_planner_end_to_end_user_message():
    """
    Verifies that calling handle_user_message on conversational inputs
    dispatches tools cleanly and returns rich, grounded replies.
    """
    from core.telegram.agent_planner import telegram_agent_planner

    identity = TelegramUserIdentity(
        user_id=888,
        chat_id=888,
        username="quant_analyst",
        role=TelegramRole.SUPER_ADMIN,
    )

    # Position query
    pos_reply = await telegram_agent_planner.handle_user_message(
        message="আমার পজিশন কি আছে?",
        chat_id=888,
        identity=identity,
    )
    assert "PAPER DESK" in pos_reply or "ACTIVE PAPER" in pos_reply

    # Terminal status query
    status_reply = await telegram_agent_planner.handle_user_message(
        message="টার্মিনাল অবস্থা কি?",
        chat_id=888,
        identity=identity,
    )
    assert "CBT / SKY QUANTITATIVE DESK STATUS" in status_reply
    assert "Virtual Equity" in status_reply


def test_claim_verifier_corroboration_and_contradiction():
    """
    Milestone 4 Test: Verifies that ClaimVerifier detects empirical corroboration
    and contradiction against macro event releases and writes to research_evidence.
    """
    from core.knowledge_os.claim_verifier import claim_verifier
    from core.knowledge_os.universal_ingestor import universal_ingestor

    now_ms = int(time.time() * 1000)
    cid_cool = f"src_test_cpi_cool_C-01"
    cid_surge = f"src_test_cpi_surge_C-02"

    with universal_ingestor._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, source_id, wiki_article_id, speaker_claim,
                claim_type, speaker, timestamp_marker, time_period,
                confidence_score, verification_status, cross_verification_evidence,
                empirical_dataset_reference, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                cid_cool,
                "src_test_cpi_cool",
                "wiki_test_cpi_cool",
                "US CPI inflation is cooling rapidly below forecast levels, triggering market liquidity expansion.",
                "HYPOTHESIS",
                "Macro Analyst",
                "",
                "",
                0.60,
                "HYPOTHESIS",
                "",
                "US BLS",
                now_ms,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, source_id, wiki_article_id, speaker_claim,
                claim_type, speaker, timestamp_marker, time_period,
                confidence_score, verification_status, cross_verification_evidence,
                empirical_dataset_reference, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                cid_surge,
                "src_test_cpi_surge",
                "wiki_test_cpi_surge",
                "Inflation is surging out of control with a 100% chance guarantee of fed rate hikes.",
                "HYPOTHESIS",
                "Permabear Blogger",
                "",
                "",
                0.70,
                "HYPOTHESIS",
                "",
                "Blog Post",
                now_ms,
            ),
        )
        conn.commit()

    # 1. Verify cooling claim
    res_cool = claim_verifier.verify_claim(cid_cool)
    assert res_cool is not None
    assert res_cool.claim_id == cid_cool
    assert res_cool.confidence_score >= 0.70
    assert len(res_cool.corroborating_evidence) >= 1
    assert any(e.evidence_type == "EMPIRICAL_BENCHMARK" for e in res_cool.corroborating_evidence)

    # 2. Verify surge claim (should detect contradiction / constitutional violation)
    res_surge = claim_verifier.verify_claim(cid_surge)
    assert res_surge is not None
    assert res_surge.claim_id == cid_surge
    assert len(res_surge.contradictions_detected) >= 1
    assert res_surge.new_status in ("CONTRADICTED", "REFUTED")

    # 3. Verify durable persistence in research_evidence
    with universal_ingestor._get_connection() as conn:
        ev_count = conn.execute(
            "SELECT count(*) FROM research_evidence WHERE claim_id IN (?, ?);",
            (cid_cool, cid_surge),
        ).fetchone()[0]
        assert ev_count >= 2


def test_evidence_timeline_generation_and_narrative_drift():
    """
    Milestone 4 Test: Verifies chronological timeline assembly and narrative drift detection.
    """
    from core.knowledge_os.evidence_timeline import evidence_timeline_engine
    from core.knowledge_os.universal_ingestor import universal_ingestor

    now_ms = int(time.time() * 1000)
    with universal_ingestor._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, source_id, wiki_article_id, speaker_claim,
                claim_type, speaker, timestamp_marker, time_period,
                confidence_score, verification_status, cross_verification_evidence,
                empirical_dataset_reference, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "claim_timeline_cpi_01",
                "src_timeline_cpi",
                "wiki_timeline_cpi",
                "CPI headline inflation print confirms structural disinflation trajectory.",
                "FACT",
                "Chief Economist",
                "",
                "",
                0.88,
                "EMPIRICALLY_SUPPORTED",
                "Confirmed by Bureau of Labor Statistics",
                "BLS CPI",
                now_ms,
            ),
        )
        conn.commit()

    timeline = evidence_timeline_engine.build_timeline(topic="CPI", limit=20)
    assert timeline is not None
    assert timeline.total_events >= 1
    assert timeline.narrative_trend in ("STABLE_CONSENSUS", "SHIFTING_BULLISH", "SHIFTING_BEARISH", "HIGHLY_CONTESTED", "INSUFFICIENT_DATA")

    # Verify Markdown export
    md = timeline.to_markdown()
    assert "# Evidence Timeline:" in md
    assert "Chronological Evolution" in md


def test_knowledge_graph_entities_and_relations():
    """
    Milestone 5 Test: Verifies entity retrieval, text extraction, and subgraph expansion.
    """
    from core.knowledge_os.knowledge_graph import knowledge_graph_engine

    # 1. Canonical entity grounding
    btc_ent = knowledge_graph_engine.get_entity("Bitcoin")
    assert btc_ent is not None
    assert btc_ent.entity_id == "ent_btc"
    assert "btc" in btc_ent.aliases

    dxy_ent = knowledge_graph_engine.get_entity("dxy")
    assert dxy_ent is not None
    assert dxy_ent.entity_id == "ent_dxy"

    # 2. Subgraph expansion
    subgraph = knowledge_graph_engine.get_subgraph("Bitcoin")
    assert len(subgraph["nodes"]) >= 2
    assert len(subgraph["edges"]) >= 1

    # 3. Free-text entity extraction
    sample_text = "The Federal Reserve decision on interest rates pushed DXY higher while Bitcoin reacted to FVG."
    extracted = knowledge_graph_engine.extract_entities_from_text(sample_text)
    extracted_names = [e.name for e in extracted]
    assert "Federal Reserve" in extracted_names
    assert "US Dollar Index" in extracted_names
    assert "Bitcoin" in extracted_names
    assert "Fair Value Gap" in extracted_names

    # 4. Add dynamic relation
    rel = knowledge_graph_engine.add_relation(
        source_name_or_id="Bitcoin",
        target_name_or_id="Ethereum",
        relation_type="CORRELATED_WITH",
        weight=0.91,
        description="High daily rolling beta correlation",
    )
    assert rel is not None
    assert rel.relation_type == "CORRELATED_WITH"


def test_thesis_engine_lifecycle_and_auto_clustering():
    """
    Milestone 5 Test: Verifies institutional thesis creation, claim linking,
    confidence re-weighting, and auto-clustering.
    """
    from core.knowledge_os.thesis_engine import thesis_engine

    # 1. Verify pre-seeded canonical theses
    theses = thesis_engine.list_theses(asset_class="CRYPTO")
    assert len(theses) >= 1
    m2_thesis = next(t for t in theses if t["thesis_id"] == "thesis_liquidity_m2")
    assert m2_thesis["status"] in ("SUPPORTED", "EMERGING")

    # 2. Dynamic creation
    t_new = thesis_engine.create_thesis(
        thesis_id="thesis_test_sol_momentum",
        title="Solana High-Throughput DEX Momentum",
        description="DEX velocity on Solana drives structural spot demand.",
        asset_class="CRYPTO",
    )
    assert t_new.status == "NEW"
    assert t_new.confidence_score == 0.50

    # 3. Auto-clustering
    clusters = thesis_engine.auto_cluster_claim_to_theses(
        claim_id="src_test_cpi_cool_C-01",
        claim_text="Global liquidity M2 expansion is accelerating Bitcoin inflows.",
    )
    assert "thesis_liquidity_m2" in clusters

    # 4. Dossier retrieval
    dossier = thesis_engine.get_thesis_dossier("thesis_liquidity_m2")
    assert dossier is not None
    assert "thesis" in dossier
    assert "supporting_claims" in dossier


@pytest.mark.asyncio
async def test_telegram_agent_routing_for_theses_timeline_graph():
    """
    Verifies that Telegram Agent correctly identifies and executes intents
    for Theses, Evidence Timeline, Knowledge Graph, and Claim Verification.
    """
    from core.telegram.agent_planner import telegram_agent_planner

    identity = TelegramUserIdentity(
        user_id=777,
        chat_id=777,
        username="quant_lead",
        role=TelegramRole.SUPER_ADMIN,
    )

    # 1. Theses Query in Bengali
    d1 = telegram_agent_planner.resolve_intent("আমাদের কী কী ম্যাক্রো থিসিস আছে?", user_id=777)
    assert d1.intent == "QUERY_THESES"
    assert d1.tool_name == "query_theses"
    resp1 = await telegram_agent_planner.handle_user_message("কী কী থিসিস আছে?", 777, identity)
    assert "INSTITUTIONAL MACRO & QUANTITATIVE THESES" in resp1

    # 2. Evidence Timeline in Bengali
    d2 = telegram_agent_planner.resolve_intent("সিপিআই এভিডেন্স টাইমলাইন দেখাও", user_id=777)
    assert d2.intent == "GET_TIMELINE"
    assert d2.tool_name == "get_evidence_timeline"
    resp2 = await telegram_agent_planner.handle_user_message("এভিডেন্স টাইমলাইন দেখাও", 777, identity)
    assert "EVIDENCE TIMELINE" in resp2

    # 3. Knowledge Graph in Bengali
    d3 = telegram_agent_planner.resolve_intent("বিটকয়েনের সাথে কিসের সম্পর্ক? নলেজ গ্রাফ দেখাও", user_id=777)
    assert d3.intent == "QUERY_GRAPH"
    assert d3.tool_name == "query_knowledge_graph"
    resp3 = await telegram_agent_planner.handle_user_message("বিটকয়েনের গ্রাফ দেখাও", 777, identity)
    assert "KNOWLEDGE GRAPH SUBGRAPH" in resp3

    # 4. Claim Verification
    d4 = telegram_agent_planner.resolve_intent("দাবিগুলো ভেরিফাই করো", user_id=777)
    assert d4.intent == "VERIFY_CLAIMS"
    assert d4.tool_name == "verify_claims"


def test_strategy_bridge_synthesis():
    """
    Verifies that StrategyBridge compiles falsifiable StrategyCandidateRecord
    with causal firewalls, parameter completeness, and registers into both
    strategy_candidates and hypothesis_queue.
    """
    from core.knowledge_os.strategy_bridge import strategy_bridge

    # 1. Synthesize from raw hypothesis text
    cand = strategy_bridge.synthesize_from_text(
        claim_text="When RSI drops below 30 and MACD histogram crosses above zero, buy BTC with 1.5% Half-Kelly risk.",
        claim_id="claim_test_99",
        source_id="src_test_99",
        symbol="BTC/USDT",
        timeframe="15m",
    )

    assert cand.candidate_id.startswith("CAND_")
    assert cand.knowledge_id == "claim_test_99"
    assert "RSI" in cand.required_indicators or "MACD" in cand.required_indicators
    assert cand.validation_stage == "QUEUED_FOR_BACKTEST"
    assert "invalidation" in cand.exit_rules
    assert "risk_budget" in cand.parameter_bounds
    assert cand.parameter_bounds["risk_budget"]["max_kelly_fraction"] <= 0.025

    # 2. Check DB persistence in strategy_candidates
    from core.database import db_manager

    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_candidates WHERE candidate_id = ?;", (cand.candidate_id,)
        ).fetchone()
        assert row is not None
        assert row["strategy_name"] == cand.strategy_name

        hyp_row = conn.execute(
            "SELECT * FROM hypothesis_queue WHERE claim_id = ?;", (cand.knowledge_id,)
        ).fetchone()
        assert hyp_row is not None


def test_backtest_queue_bidirectional_feedback():
    """
    Verifies that BacktestQueue executes simulation on closed bars, evaluates 3-tier costs,
    and updates both strategy_candidates AND research_evidence / research_claims (bidirectional feedback).
    """
    from core.knowledge_os.backtest_queue import backtest_queue_manager
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine
    from core.knowledge_os.strategy_bridge import strategy_bridge

    # 1. Seed a claim in research_claims
    cid = "claim_bt_test_1"
    now_ms = int(time.time() * 1000)
    with research_wikipedia_engine._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, source_id, wiki_article_id, speaker_claim, claim_type,
                speaker, confidence_score, verification_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                cid,
                "src_test",
                "wiki_test",
                "RSI oversold bounces yield positive alpha on 15m timeframes.",
                "STRATEGY_CLAIM",
                "Test Analyst",
                0.50,
                "UNVERIFIED",
                now_ms,
            ),
        )
        conn.commit()

    # 2. Synthesize candidate from this claim
    cand = strategy_bridge.synthesize_strategy_from_claim(cid)
    assert cand is not None
    assert cand.knowledge_id == cid

    # 3. Execute backtest
    result = backtest_queue_manager.execute_backtest(cand.candidate_id, bars_count=100)
    assert result is not None
    assert result.candidate_id == cand.candidate_id
    assert result.validation_stage in ("WALK_FORWARD_TESTED", "REJECTED")
    assert result.evidence_recorded is True

    # 4. Verify bidirectional update in research_claims & research_evidence
    with research_wikipedia_engine._get_connection() as conn:
        claim_after = conn.execute(
            "SELECT verification_status, confidence_score FROM research_claims WHERE claim_id = ?;",
            (cid,),
        ).fetchone()
        assert claim_after["verification_status"] in ("EMPIRICALLY_SUPPORTED", "CONTRADICTED", "REFUTED")

        ev_row = conn.execute(
            "SELECT * FROM research_evidence WHERE claim_id = ?;", (cid,)
        ).fetchone()
        assert ev_row is not None
        assert "Walk-forward backtest" in ev_row["citation_text"]


@pytest.mark.asyncio
async def test_telegram_agent_routing_for_strategy_and_backtest():
    """
    Verifies that Telegram Agent planner and tool gateway correctly route
    natural language requests for strategy synthesis and candidate backtests.
    """
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine
    from core.telegram.agent_planner import telegram_agent_planner
    from core.telegram.tool_gateway import telegram_tool_gateway

    identity = TelegramUserIdentity(
        user_id=777,
        chat_id=777,
        username="quant_lead",
        role=TelegramRole.SUPER_ADMIN,
    )

    # 1. Strategy Synthesis Intent
    d1 = telegram_agent_planner.resolve_intent("এই ক্লেইম থেকে স্ট্র্যাটেজি বানাও C-05", user_id=777)
    assert d1.intent == "SYNTHESIZE_STRATEGY"
    assert d1.tool_name == "synthesize_strategy_from_claim"
    assert d1.tool_args["claim_id"] == "C-05"

    # Seed claim for tool execution
    now_ms = int(time.time() * 1000)
    with research_wikipedia_engine._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_claims (
                claim_id, source_id, wiki_article_id, speaker_claim, claim_type,
                speaker, confidence_score, verification_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "C-05",
                "src_test",
                "wiki_test",
                "Buy when price sweeps previous day low and forms a 15m bullish FVG.",
                "STRATEGY_CLAIM",
                "ICT Analyst",
                0.80,
                "UNVERIFIED",
                now_ms,
            ),
        )
        conn.commit()

    resp1 = await telegram_agent_planner.handle_user_message("এই ক্লেইম থেকে স্ট্র্যাটেজি বানাও C-05", 777, identity)
    assert "SYNTHESIZED STRATEGY CANDIDATE" in resp1

    # 2. Backtest Intent
    # Find candidate id
    cand_match = resp1.split("`CAND_")[1].split("`")[0]
    cand_id = f"CAND_{cand_match}"

    d2 = telegram_agent_planner.resolve_intent(f"এই ক্যান্ডিডেট ব্যাকটেস্ট করো {cand_id}", user_id=777)
    assert d2.intent == "RUN_BACKTEST"
    assert d2.tool_name == "run_candidate_backtest"
    assert d2.tool_args["candidate_id"] == cand_id

    resp2 = await telegram_agent_planner.handle_user_message(f"এই ক্যান্ডিডেট ব্যাকটেস্ট করো {cand_id}", 777, identity)
    assert "WALK-FORWARD STRATEGY VALIDATION REPORT" in resp2




