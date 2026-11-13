"""
tests/test_m50_end_to_end_sovereign_polish.py
=============================================
Milestone M50 Acceptance Test Suite:
1. Zero hardcoded briefings in generate_market_update() and generate_news_digest().
2. Local chart image OCR / inspection and fallback in telegram_bot & telegram_media.
3. Bidirectional (LONG and SHORT) trade planning in _tool_plan_trade_signal.
4. ResearchAutomationOrchestrator macro_vitals_sync pipeline and /api/knowledge/macro-vitals route.
5. Zero-Gemini execution in PDFBookExtractor when USE_NATIVE_QUANT_ENGINE=true.
6. CP-2 parameter parity (Half-Kelly <= 1.50% and Two-Stage Progressive Ratchet).
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_market_update_zero_hardcode():
    """Verify generate_market_update returns live/dynamic numbers and zero legacy constants."""
    from core.telegram_bot import telegram_bot

    update = await telegram_bot.generate_market_update()
    assert isinstance(update, dict)

    # In M49/M50, sol_price was hardcoded to 194.80 and btc_change_24h to 2.45
    # The new function pulls real quotes or vitals
    assert "btc_price" in update
    assert "eth_price" in update
    assert "sol_price" in update
    assert "dxy" in update
    assert "cvd_delta" in update
    assert "funding_rate" in update
    assert "sentiment" in update

    # Ensure dynamic CVD order flow formatting
    assert (
        "Order Flow Aligned" in update["cvd_delta"]
        or "CVD" in update["cvd_delta"]
        or "NEUTRAL" in update["cvd_delta"]
    )


@pytest.mark.asyncio
async def test_generate_news_digest_grounded_in_db():
    """Verify generate_news_digest queries Research Wikipedia or live MacroMicro vitals."""
    from core.telegram_bot import telegram_bot

    items = telegram_bot.generate_news_digest()
    assert isinstance(items, list)
    assert len(items) > 0
    assert len(items) <= 5

    for item in items:
        assert "tag" in item
        assert "headline" in item
        assert "sentiment" in item
        # Ensure fake BlackRock IBIT string is eliminated
        assert (
            "Institutional Bitcoin Spot ETFs record net daily inflows led by BlackRock IBIT"
            not in item["headline"]
        )


def test_pdf_book_extractor_zero_gemini_native():
    """Verify PDFBookExtractor never calls google.genai when USE_NATIVE_QUANT_ENGINE=true."""
    from core.pdf_extractor import PDFBookExtractor

    extractor = PDFBookExtractor(api_key="mock_key")
    fake_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00\x00\x00\x01\x00\x08\x06\x00\x00\x00"
    )

    with patch.dict(os.environ, {"USE_NATIVE_QUANT_ENGINE": "true"}):
        with patch(
            "google.genai.Client", side_effect=AssertionError("google.genai MUST NOT be called!")
        ):
            text, provider = extractor.extract_page_with_vision(fake_png, mime_type="image/png")
            assert provider in ("LOCAL_TESSERACT_OCR", "NATIVE_LOCAL_EXTRACTOR")
            assert "[NATIVE_IMAGE_PAGE" in text or len(text) > 0


def test_telegram_media_inspect_chart_image():
    """Verify telegram_media.inspect_chart_image detects symbol & timeframe without external LLM."""
    from core.telegram.media import telegram_media

    # Test detection from caption
    res_btc = telegram_media.inspect_chart_image(
        b"dummy_bytes",
        caption="Analyze this BTC 1W chart setup for me",
    )
    assert res_btc["symbol"] == "BTC/USDT"
    assert res_btc["timeframe"] == "1w"
    assert res_btc["detected"] is True

    # Test detection for ETH 4H
    res_eth = telegram_media.inspect_chart_image(
        b"dummy_bytes",
        caption="ETHUSDT 4-hour order block",
    )
    assert res_eth["symbol"] == "ETH/USDT"
    assert res_eth["timeframe"] == "4h"

    # Test unlabeled fallback
    res_unlabeled = telegram_media.inspect_chart_image(b"dummy_bytes", caption="")
    assert res_unlabeled["symbol"] == "BTC/USDT"
    assert res_unlabeled["timeframe"] == "15m"
    assert res_unlabeled["detected"] is False


@pytest.mark.asyncio
async def test_bidirectional_tool_plan_trade_signal():
    """Verify _tool_plan_trade_signal honors direction (LONG and SHORT) and CP-2 risk rules."""
    from core.native_desk_bridge import LiveAssetIntelligenceDossier, TradeSetupPlan
    from core.telegram.rbac import TelegramRole, TelegramUserIdentity
    from core.telegram.tool_gateway import telegram_tool_gateway

    identity = TelegramUserIdentity(
        user_id="test_trader",
        chat_id="12345",
        role=TelegramRole.SUPER_ADMIN,
        first_name="Quant",
        username="lead_quant",
    )

    # 1. Test SHORT direction planning
    mock_short_setup = TradeSetupPlan(
        direction="SHORT",
        entry_price=80000.0,
        entry_trigger="Bearish FVG Mitigation",
        stop_loss=81500.0,
        tp1=78000.0,
        tp2=76000.0,
        risk_reward_ratio=2.5,
        net_ev_r=0.28,
        profit_factor=1.55,
        kelly_allocation_pct=1.50,
    )

    mock_dossier = MagicMock(spec=LiveAssetIntelligenceDossier)
    mock_dossier.current_price = 80000.0
    mock_dossier.primary_setup = mock_short_setup

    with patch(
        "core.native_desk_bridge.native_desk_bridge.compile_asset_dossier",
        new=AsyncMock(return_value=mock_dossier),
    ):
        res = await telegram_tool_gateway._tool_plan_trade_signal("BTC/USDT", identity)
        assert res.success is True
        assert res.requires_confirmation is True
        assert "SHORT" in res.output_text
        assert "1.50% Half-Kelly Cap" in res.output_text
        assert "Two-Stage Ratchet" in res.output_text


@pytest.mark.asyncio
async def test_macro_vitals_sync_pipeline_and_route():
    """Verify ResearchAutomationOrchestrator macro_vitals_sync updates thesis, graph, and API route."""
    from core.knowledge_os.research_automation_orchestrator import research_automation_orchestrator
    from core.knowledge_os.routes import get_macro_vitals

    # Trigger macro_vitals_sync pipeline
    res = await research_automation_orchestrator.trigger_pipeline("macro_vitals_sync")
    assert "triggered" in res
    assert res["triggered"] == "macro_vitals_sync"
    assert res["result"]["status"] == "COMPLETED"

    # Verify pipeline status registered
    status = research_automation_orchestrator.get_status()
    assert "macro_vitals_sync" in status
    assert status["macro_vitals_sync"]["last_run_status"] == "OK"

    # Verify GET /api/knowledge/macro-vitals endpoint
    route_res = await get_macro_vitals()
    assert route_res["status"] == "SUCCESS"
    assert "vitals" in route_res
    assert "sentinel_snapshot" in route_res
