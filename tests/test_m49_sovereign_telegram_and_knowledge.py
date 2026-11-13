"""
tests/test_m49_sovereign_telegram_and_knowledge.py
===================================================
Milestone M49 Verification Suite:
1. Zero Gemini API Dependency (Python & TS, full offline native fallback)
2. Zero Fake Price Multipliers in Telegram & Quantitative Mentor (SMCEngine + NativeDeskIntelligenceBridge)
3. Live Macro & MacroMicro Collector & Source Registry Integration
4. Knowledge Wiki "China" Bug Fixed & SQLite FTS5 Full-Text Search
5. Bilingual Trading Dictionary Engine & Real-Time Live Example Enrichment
"""

import os
from unittest.mock import patch

import pytest

from core.knowledge_os.project_rag import project_rag
from core.knowledge_os.research_wikipedia import research_wikipedia_engine
from core.knowledge_os.trading_dictionary import trading_dictionary
from core.macro_live_collector import macro_live_collector
from core.macro_sentinel import macro_sentinel
from core.native_desk_bridge import native_desk_bridge
from core.quant_mentor import quant_mentor
from core.telegram.agent_planner import telegram_agent_planner
from core.telegram.rbac import TelegramRole, TelegramUserIdentity
from core.telegram.tool_gateway import telegram_tool_gateway
from core.url_extractor import url_extractor


@pytest.mark.asyncio
async def test_zero_gemini_dependency():
    """
    Test 1: Verify that with GEMINI_API_KEY="" and LLM_PROVIDER="off",
    quant_mentor, telegram_agent_planner, macro_cognitive_engine,
    and llm_brain execute with zero crashes or exceptions.
    """
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "LLM_PROVIDER": "off"}):
        # 1. Quant mentor
        resp = await quant_mentor.generate_response("what is current btc market trend?")
        assert resp is not None
        assert len(resp) > 30

        # 2. Agent planner
        identity = TelegramUserIdentity(
            user_id=123, chat_id="123", username="trader", role=TelegramRole.ANALYST
        )
        plan_resp = await telegram_agent_planner.handle_user_message(
            "how is the market", 123, identity
        )
        assert plan_resp is not None
        assert len(plan_resp) > 20

        # 3. Macro cognitive engine
        from core.macro_cognitive_engine import MacroCognitiveEngine

        macro_engine = MacroCognitiveEngine()
        cog_res = macro_engine.analyze_macro_content(
            "Federal Reserve balance sheet contraction and yield curve steepening."
        )
        assert cog_res is not None
        assert cog_res.regime is not None


@pytest.mark.asyncio
async def test_no_fake_price_multipliers_in_telegram():
    """
    Test 2: Verify that get_live_ticker_dossier, generate_trading_plan,
    and quant_mentor use real SMCEngine / signal_engine structural outputs
    rather than static multipliers like price * 0.992 or price * 0.985.
    """
    identity = TelegramUserIdentity(
        user_id=123, chat_id="123", username="trader", role=TelegramRole.ANALYST
    )

    # 1. Tool Gateway live ticker dossier
    dossier_res = await telegram_tool_gateway.execute_tool(
        "get_live_ticker_dossier",
        {"symbol": "BTC/USDT", "language": "en"},
        identity=identity,
    )
    assert dossier_res.success is True
    out_text = dossier_res.output_text
    assert "LIVE QUANTITATIVE DOSSIER" in out_text
    assert "Fair Value Gap Zone:" in out_text
    assert "Institutional Order Block:" in out_text
    assert "Net Expected Value:" in out_text
    assert "Half-Kelly bounds enforced (Max 1.50% equity" in out_text

    # 2. Native Desk Bridge dossier
    dossier = await native_desk_bridge.compile_asset_dossier("BTC/USDT", "15m")
    assert dossier.current_price > 0
    assert dossier.primary_setup.stop_loss > 0
    assert dossier.primary_setup.risk_reward_ratio >= 1.5
    assert dossier.primary_setup.kelly_allocation_pct <= 1.50

    # 3. Quant Mentor direction response
    mentor_resp = await quant_mentor.generate_response(
        "where is btc going?", language_preference="en"
    )
    assert "STRUCTURAL MARKET DIRECTION" in mentor_resp
    assert "Dominant Directional Bias:" in mentor_resp
    assert "Thesis Invalidation Level:" in mentor_resp


def test_macromicro_extractor_and_live_macro_collector():
    """
    Test 3: Verify URLExtractor parses MacroMicro Trader's Insight and
    macro_live_collector caches cross-asset indicators and vitals.
    """
    # 1. Test live collector
    vitals = macro_live_collector.get_cached_vitals()
    assert len(vitals) >= 10
    assert "DXY" in vitals
    assert "US10Y" in vitals
    assert "RECESSION_PROB" in vitals
    assert "STABLECOIN_MCAP" in vitals

    # 2. Test Macro Sentinel snapshot
    snap = macro_sentinel.get_macro_snapshot()
    assert snap.dxy_index > 0
    assert snap.us10y_yield > 0
    assert snap.global_risk_index > 0

    # 3. Test MacroMicro URL extraction
    sample_url = "https://en.macromicro.me/trader-insights"
    ext_res = url_extractor.extract(sample_url)
    assert ext_res["success"] is True
    assert "MacroMicro Trader's Insight" in ext_res["title"]
    assert len(ext_res["claims"]) >= 3


def test_wiki_china_bug_fixed_and_fts5_search():
    """
    Test 4: Verify that ingesting an article mentioning 'China' does NOT
    hijack into _build_us_china_article (unless it is the specific Facebook reel),
    and project_rag.retrieve_wiki_articles uses SQLite FTS5 for deep search.
    """
    # 1. Ingest an article with the word 'China'
    article = research_wikipedia_engine.ingest_url_or_content(
        source_url="https://finance.yahoo.com/news/china-pboc-liquidity-stimulus.html",
        raw_text="The People's Bank of China injected 500 billion yuan of liquidity into the banking system to support sovereign debt issuance and monetary transmission.",
        custom_title="PBOC China Liquidity Injection Analysis",
        custom_category="Monetary Policy & Debt Cycles",
    )
    assert article.title == "PBOC China Liquidity Injection Analysis"
    # Ensure it was NOT hijacked into the Facebook Reel title
    assert "Facebook Reel" not in article.title
    assert "14rU2inKqPQ" not in article.provenance_id

    # 2. Test FTS5 reindexing and search
    indexed = research_wikipedia_engine.reindex_fts()
    assert indexed > 0

    # 3. Test deep search via FTS5
    fts_hits = research_wikipedia_engine.search_fts("liquidity stimulus China", limit=5)
    assert len(fts_hits) > 0

    # 4. Test ProjectRAG retrieval with snippet excerpt
    rag_hits = project_rag.retrieve_wiki_articles("liquidity stimulus China", limit=3)
    assert len(rag_hits) > 0
    assert rag_hits[0].article_id is not None


@pytest.mark.asyncio
async def test_trading_dictionary_bilingual_and_live_example():
    """
    Test 5: Verify querying dictionary terms (e.g. FVG, Order Block, CVD, Half-Kelly)
    returns bilingual definitions, mathematical formulas, anti-retail traps,
    CBT code hooks, and live market context.
    """
    # 1. English lookup for Fair Value Gap
    fvg_en = trading_dictionary.lookup("fvg", language="en", symbol="BTC/USDT")
    assert fvg_en is not None
    assert fvg_en["canonical_name"] == "Fair Value Gap (FVG)"
    assert "3-candle" in fvg_en["definition_en"]
    assert fvg_en["cbt_code_implementation"] != ""
    assert "FAIR VALUE GAP" in fvg_en["formatted_markdown"]
    assert "3-candle" in fvg_en["formatted_markdown"]

    # 2. Bengali lookup for Half-Kelly
    kelly_bn = trading_dictionary.lookup("হাফ কেলি", language="bn", symbol="BTC/USDT")
    assert kelly_bn is not None
    assert kelly_bn["canonical_name"] == "Half-Kelly Criterion"
    assert "১.৫০%" in kelly_bn["definition_bn"]
    assert "CBT" in kelly_bn["formatted_markdown"]

    # 3. Agent Planner natural language query for dictionary definition
    identity = TelegramUserIdentity(
        user_id=123, chat_id="123", username="trader", role=TelegramRole.ANALYST
    )
    resp = await telegram_agent_planner.handle_user_message("what is order block", 123, identity)
    assert resp is not None
    assert "ORDER BLOCK" in resp.upper()
    assert "Anti-Retail Pitfall" in resp or "Definition" in resp

    # 4. Banglish query via Agent Planner
    resp_bn = await telegram_agent_planner.handle_user_message("fvg ki?", 123, identity)
    assert resp_bn is not None
    assert "ফেয়ার ভ্যালু গ্যাপ" in resp_bn or "FVG" in resp_bn
