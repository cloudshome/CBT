"""
tests/test_telegram_chart_vision_honesty.py
============================================
Guarantees AI Honesty & Anti-Hallucination Directives in Telegram Multimodal Vision.
Enforces that Telegram bot NEVER returns hardcoded fake trade setups (e.g. Gold Spot mock)
when vision inference is offline or failing with upstream API errors.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.telegram_bot import telegram_bot


@pytest.mark.asyncio
async def test_telegram_vision_failure_returns_honest_diagnostic_never_canned_mock():
    """
    Verifies that when Vision OCR returns an upstream policy or connection failure,
    the bot returns a transparent diagnostic error rather than a fabricated trade setup.
    """
    fake_img = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    with (
        patch.object(telegram_bot, "download_telegram_file", new_callable=AsyncMock) as mock_dl,
        patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send,
        patch(
            "core.pdf_extractor.pdf_book_extractor.extract_page_with_vision",
            return_value=("", "API_KEY_POLICY_BLOCKED_403"),
        ),
    ):
        mock_dl.return_value = fake_img

        res = await telegram_bot.handle_telegram_research_ingest(
            chat_id="12345",
            photo=[{"file_id": "test_photo_id"}],
            caption="Analyze this chart setup",
            from_user="test_trader",
        )

        assert res["status"] == "TRADE_ANALYSIS_FAILED"
        assert res["provider"] == "API_KEY_POLICY_BLOCKED_403"

        # Verify that all outgoing messages NEVER contain the fake Gold Spot mock
        sent_messages = [call.args[0] for call in mock_send.call_args_list]
        combined_text = "\n".join(sent_messages)

        assert "Gold Spot" not in combined_text
        assert "XAU/USD" not in combined_text
        assert "3,995.80" not in combined_text
        assert "4,015.00" not in combined_text

        # Verify honest failure notice is delivered
        assert "Multimodal Vision: Inference Unavailable" in combined_text
        assert "403 Forbidden" in combined_text


@pytest.mark.asyncio
async def test_telegram_vision_success_delivers_institutional_analysis():
    """Verifies that when Vision OCR succeeds, the actual analysis is formatted and delivered."""
    fake_img = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    mock_analysis = (
        "📊 *Asset:* Bitcoin / U.S. Dollar (`BTC/USDT`) • 1W\n"
        "🧭 *Market Structure:* Higher-timeframe weekly consolidation near $71,326.\n"
        "⚡ *Direct Verdict:* WAIT for sweep."
    )

    with (
        patch.object(telegram_bot, "download_telegram_file", new_callable=AsyncMock) as mock_dl,
        patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send,
        patch(
            "core.pdf_extractor.pdf_book_extractor.extract_page_with_vision",
            return_value=(mock_analysis, "GEMINI_VISION"),
        ),
    ):
        mock_dl.return_value = fake_img

        res = await telegram_bot.handle_telegram_research_ingest(
            chat_id="12345",
            photo=[{"file_id": "test_photo_id"}],
            caption="",
            from_user="test_trader",
        )

        assert res["status"] == "TRADE_ANALYSIS_COMPLETED"
        sent_messages = [call.args[0] for call in mock_send.call_args_list]
        combined_text = "\n".join(sent_messages)

        assert "Bitcoin" in combined_text
        assert "BTC/USDT" in combined_text
        assert "71,326" in combined_text
