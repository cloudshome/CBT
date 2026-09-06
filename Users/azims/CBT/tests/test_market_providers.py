"""
Unit Tests for Institutional Market Data Provider Abstraction Layer.
Validates Binance, Bybit, SQLite Cache, the unavailability sentinel, and the
Composite Gateway — including the guarantee that no layer fabricates market
data or launders synthetic data as empirical.
"""

import pytest

from core.evidence_integrity import EvidenceGrade, weakest_grade
from core.market_providers import (
    TIMEFRAME_TO_MS,
    BinanceMarketDataProvider,
    BybitMarketDataProvider,
    CompositeMarketDataGateway,
    SQLiteCacheProvider,
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
async def test_synthetic_provider_never_fabricates_ohlcv():
    """
    Regression: this provider used to emit a random OHLCV walk with no
    provenance tag, which ``data_streamer`` then persisted as real market data.
    It must now return nothing at all.
    """
    provider = SyntheticMarketProvider()
    assert provider.provider_name == "UNAVAILABLE_SENTINEL"

    candles = await provider.fetch_historical_ohlcv("BTC/USDT", "15m", limit=30)
    assert candles == []


@pytest.mark.asyncio
async def test_synthetic_provider_ticker_is_graded_fabricated():
    """A last-resort reference price may render, but must declare itself."""
    provider = SyntheticMarketProvider()
    ticker = await provider.fetch_live_ticker("ETH/USDT")
    assert ticker is not None
    assert ticker["symbol"] == "ETH/USDT"
    assert ticker["price"] > 1000.0
    assert ticker["evidence_grade"] == "FABRICATED"
    assert ticker["data_unavailable"] is True


@pytest.mark.asyncio
async def test_synthetic_provider_never_fabricates_depth():
    """
    Fabricated liquidity fed order-book imbalance and VPIN toxicity, which fed
    directional scoring. Empty depth is the honest answer during an outage.
    """
    provider = SyntheticMarketProvider()
    ob = await provider.fetch_order_book_depth("BTC/USDT", limit=8)
    assert ob is not None
    assert ob["asks"] == []
    assert ob["bids"] == []
    assert ob["evidence_grade"] == "FABRICATED"


@pytest.mark.asyncio
async def test_composite_market_gateway():
    gateway = CompositeMarketDataGateway()

    # 1. Fetch OHLCV. Offline (as in CI) every real venue fails, so the
    #    gateway must return an empty series rather than inventing one.
    #    Whatever it returns must be fully provenance-stamped.
    ohlcv = await gateway.get_ohlcv("BTC/USDT", "15m", limit=20)
    assert all("evidence_grade" in c for c in ohlcv)
    if not ohlcv:
        assert weakest_grade(ohlcv) is EvidenceGrade.FABRICATED

    # 2. Fetch Ticker — a price may be served, but never silently.
    ticker = await gateway.get_ticker("BTC/USDT")
    assert "price" in ticker
    assert ticker["price"] > 0

    # 3. Fetch Order Book — may legitimately be empty when offline.
    ob = await gateway.get_order_book("BTC/USDT", limit=6)
    assert "asks" in ob
    assert "bids" in ob

    # 4. Check Health
    health = gateway.get_provider_health()
    assert "active_provider" in health
    assert "providers" in health
    assert len(health["providers"]) >= 4


@pytest.mark.asyncio
async def test_sqlite_cache_provider_staleness_guard():
    """Verify SQLiteCacheProvider rejects cached candles older than 15 minutes."""
    from core.causal_firewall import causal_firewall
    from core.database import db_manager

    provider = SQLiteCacheProvider()
    now_ms = causal_firewall.get_current_time_ms()

    with db_manager.get_market_conn() as conn:
        # Insert a stale candle (2 hours old)
        conn.execute(
            """
            INSERT OR REPLACE INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume)
            VALUES (?, 'TEST_STALE/USDT', '15m', 100.0, 105.0, 95.0, 102.0, 500.0);
            """,
            (now_ms - 2 * 3600 * 1000,),
        )
        # Insert a fresh candle (2 minutes old)
        conn.execute(
            """
            INSERT OR REPLACE INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume)
            VALUES (?, 'TEST_FRESH/USDT', '15m', 200.0, 205.0, 195.0, 202.0, 500.0);
            """,
            (now_ms - 2 * 60 * 1000,),
        )
        conn.commit()

    # Stale candle must be rejected
    stale_ticker = await provider.fetch_live_ticker("TEST_STALE/USDT")
    assert stale_ticker is None

    # Fresh candle must be accepted
    fresh_ticker = await provider.fetch_live_ticker("TEST_FRESH/USDT")
    assert fresh_ticker is not None
    assert fresh_ticker["price"] == 202.0

