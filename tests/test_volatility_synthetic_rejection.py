"""
Tests verifying that synthetic / fabricated ticker fallbacks NEVER trigger
volatility expansion alerts or corrupt last known empirical prices.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.evidence_integrity import EvidenceGrade
from core.telegram_bot import SmartBrainNotificationEngine


@pytest.mark.asyncio
async def test_volatility_ignores_synthetic_fallback():
    """
    Verifies that if market gateway returns a synthetic / fabricated ticker
    (e.g., during an upstream outage), check_volatility_expansion rejects it
    and does NOT fire an alert to Telegram.
    """
    mock_bot = AsyncMock()
    engine = SmartBrainNotificationEngine(mock_bot)
    # Seed baseline real price
    engine._last_price_tracker["BTC/USDT"] = 79000.0

    # Fabricated payload mimicking upstream outage fallback
    synthetic_payload = {
        "symbol": "BTC/USDT",
        "price": 88450.0,  # 11.9% deviation
        "evidence_grade": EvidenceGrade.FABRICATED.label,
        "is_synthetic": 1,
        "data_unavailable": True,
        "source": "UNAVAILABLE_SENTINEL",
    }

    with patch(
        "core.data_streamer.data_streamer.get_live_ticker_payload",
        new=AsyncMock(return_value=synthetic_payload),
    ):
        await engine.check_volatility_expansion()

    # The alert must NOT have been sent!
    assert mock_bot.send_message.call_count == 0
    # The reference price must NOT have been updated to the synthetic value
    assert engine._last_price_tracker["BTC/USDT"] == 79000.0


@pytest.mark.asyncio
async def test_volatility_fires_on_genuine_empirical_surge():
    """
    Verifies that genuine EMPIRICAL ticks with >= 2.0% change trigger the alert.
    """
    mock_bot = AsyncMock()
    engine = SmartBrainNotificationEngine(mock_bot)
    engine._last_price_tracker["BTC/USDT"] = 79000.0

    # Real empirical payload with a 3.0% price surge
    empirical_payload = {
        "symbol": "BTC/USDT",
        "price": 81370.0,  # +3.0%
        "evidence_grade": EvidenceGrade.EMPIRICAL.label,
        "is_synthetic": 0,
        "data_unavailable": False,
        "source": "BINANCE_REST",
    }

    with patch(
        "core.data_streamer.data_streamer.get_live_ticker_payload",
        new=AsyncMock(return_value=empirical_payload),
    ):
        await engine.check_volatility_expansion()

    # The alert MUST fire for authentic market surge
    assert mock_bot.send_message.call_count == 1
    sent_msg = mock_bot.send_message.call_args[0][0]
    assert "MARKET VOLATILITY EXPANSION" in sent_msg
    assert "BULLISH SURGE" in sent_msg
    assert "$81,370.00" in sent_msg


@pytest.mark.asyncio
async def test_data_streamer_preserves_empirical_price_during_outage():
    """
    Verifies that data_streamer.get_live_ticker preserves the last empirical price
    and does not contaminate _last_known_prices when a synthetic tick arrives.
    """
    from core.data_streamer import data_streamer

    data_streamer._last_known_prices["BTC/USDT"] = 79350.0

    synthetic_payload = {
        "symbol": "BTC/USDT",
        "price": 79000.0,
        "evidence_grade": EvidenceGrade.FABRICATED.label,
        "is_synthetic": 1,
        "data_unavailable": True,
        "source": "UNAVAILABLE_SENTINEL",
    }

    with patch(
        "core.market_providers.market_gateway.get_ticker",
        new=AsyncMock(return_value=synthetic_payload),
    ):
        price = await data_streamer.get_live_ticker("BTC/USDT")
        # Should return the preserved last known empirical price
        assert price == 79350.0
        # The stored empirical price is unchanged
        assert data_streamer._last_known_prices["BTC/USDT"] == 79350.0
