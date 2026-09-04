"""
Unit Tests for Institutional Market Data Provider Abstraction Layer.
Validates Binance, Bybit, SQLite Cache, Synthetic stochastic simulation, and Composite Gateway.
"""

import pytest

from core.market_providers import (
    TIMEFRAME_TO_MS,
    BinanceMarketDataProvider,
    BybitMarketDataProvider,
    CompositeMarketDataGateway,
    SyntheticMarketProvider,
)


def test_timeframe_constants():
    assert "1m" in TIMEFRAME_TO_MS
    assert "15m" in TIMEFRAME_TO_MS
    assert "1h" in TIMEFRAME_TO_MS
    assert "1d" in TIMEFRAME_TO_MS
    assert TIMEFRAME_TO_MS["15m"] == 15 * 60 * 1000


def test_binance_provider_symbol_normalization():
    provider = BinanceMarketDataProvider()
    assert provider.provider_name == "BINANCE_REST"
    assert provider._normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert provider._normalize_symbol("ETH/USDT") == "ETHUSDT"
    assert provider._normalize_symbol("XAU/USD") == "PAXGUSDT"


def test_bybit_provider_symbol_normalization():
    provider = BybitMarketDataProvider()
    assert provider.provider_name == "BYBIT_V5"
    assert provider._normalize_symbol("BTC/USDT") == "BTCUSDT"
    assert provider._normalize_symbol("ETH/USDT") == "ETHUSDT"
    assert provider._normalize_symbol("XAU/USD") == "XAUUSDT"


@pytest.mark.asyncio
async def test_synthetic_provider_ohlcv():
    provider = SyntheticMarketProvider()
    assert provider.provider_name == "SYNTHETIC_STOCHASTIC"

    candles = await provider.fetch_historical_ohlcv("BTC/USDT", "15m", limit=30)
    assert candles is not None
    assert len(candles) == 30
    for c in candles:
        assert "timestamp" in c
        assert "open" in c
        assert "high" in c
        assert "low" in c
        assert "close" in c
        assert "volume" in c
        assert c["high"] >= max(c["open"], c["close"])
        assert c["low"] <= min(c["open"], c["close"])


@pytest.mark.asyncio
async def test_synthetic_provider_live_ticker():
    provider = SyntheticMarketProvider()
    ticker = await provider.fetch_live_ticker("ETH/USDT")
    assert ticker is not None
    assert ticker["symbol"] == "ETH/USDT"
    assert ticker["price"] > 1000.0
    assert ticker["source"] == "SYNTHETIC_STOCHASTIC"


@pytest.mark.asyncio
async def test_synthetic_provider_order_book():
    provider = SyntheticMarketProvider()
    ob = await provider.fetch_order_book_depth("BTC/USDT", limit=8)
    assert ob is not None
    assert len(ob["asks"]) == 8
    assert len(ob["bids"]) == 8
    assert ob["asks"][0]["price"] > ob["bids"][0]["price"]


@pytest.mark.asyncio
async def test_composite_market_gateway():
    gateway = CompositeMarketDataGateway()

    # 1. Fetch OHLCV
    ohlcv = await gateway.get_ohlcv("BTC/USDT", "15m", limit=20)
    assert len(ohlcv) >= 20

    # 2. Fetch Ticker
    ticker = await gateway.get_ticker("BTC/USDT")
    assert "price" in ticker
    assert ticker["price"] > 0

    # 3. Fetch Order Book
    ob = await gateway.get_order_book("BTC/USDT", limit=6)
    assert "asks" in ob
    assert "bids" in ob
    assert len(ob["asks"]) > 0

    # 4. Check Health
    health = gateway.get_provider_health()
    assert "active_provider" in health
    assert "providers" in health
    assert len(health["providers"]) >= 4
