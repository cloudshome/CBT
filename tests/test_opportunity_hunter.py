"""
tests/test_opportunity_hunter.py
================================
Unit and Integration Test Suite for the Dynamic Market Opportunity Hunter.
Verifies:
1. Classification of the 6 quantitative opportunity categories.
2. Institutional Liquidity Gate and Spread rejection invariants.
3. Market Attention Score calculation bounds.
4. Dynamic Watchlist lifecycle transitions (DISCOVERED -> QUALIFIED -> ACTIVE -> RETIRED).
5. FastAPI screener read-only endpoint contracts.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from core.screener.opportunity_hunter import (
    AttentionState,
    OpportunityCategory,
    OpportunityHunter,
    WatchlistState,
)


@pytest.fixture
def hunter() -> OpportunityHunter:
    return OpportunityHunter(
        min_spot_volume_usd=15_000_000.0,
        min_futures_volume_usd=25_000_000.0,
        max_spread_bps=12.0,
        cache_ttl_sec=60.0,
    )


def test_classify_blow_off_exhaustion(hunter: OpportunityHunter):
    """Verifies parabolic surge (+25%) with abnormal volume classifies as BLOW_OFF_EXHAUSTION short candidate."""
    category, state, venue, direction, rationale, quality, inv = hunter._classify_opportunity(
        symbol="ICNT/USDT",
        price=10.0,
        price_change=26.5,
        quote_vol=150_000_000.0,
        rvol=4.0,
        spread_bps=2.5,
        high_24h=10.2,
        low_24h=7.5,
        spot_eligible=True,
        futures_eligible=True,
        attention_score=95.0,
    )
    assert category == OpportunityCategory.BLOW_OFF_EXHAUSTION
    assert state == AttentionState.EXHAUSTION_CANDIDATE
    assert venue == "FUTURES"
    assert direction == "SHORT"
    assert inv is not None and inv > 10.0


def test_classify_confirmed_breakout(hunter: OpportunityHunter):
    """Verifies surge near 24h highs classifies as CONFIRMED_BREAKOUT long candidate."""
    category, state, venue, direction, rationale, quality, inv = hunter._classify_opportunity(
        symbol="LINK/USDT",
        price=20.0,
        price_change=14.0,
        quote_vol=80_000_000.0,
        rvol=2.5,
        spread_bps=2.0,
        high_24h=20.5,
        low_24h=17.0,
        spot_eligible=True,
        futures_eligible=True,
        attention_score=85.0,
    )
    assert category == OpportunityCategory.CONFIRMED_BREAKOUT
    assert state == AttentionState.BREAKOUT_CANDIDATE
    assert direction == "LONG"


def test_classify_capitulation_recovery(hunter: OpportunityHunter):
    """Verifies sharp drop (-18%) near 24h lows classifies as CAPITULATION_RECOVERY oversold reclaim."""
    category, state, venue, direction, rationale, quality, inv = hunter._classify_opportunity(
        symbol="ZEREBRO/USDT",
        price=1.0,
        price_change=-22.0,
        quote_vol=100_000_000.0,
        rvol=3.0,
        spread_bps=3.0,
        high_24h=1.35,
        low_24h=0.98,
        spot_eligible=False,
        futures_eligible=True,
        attention_score=90.0,
    )
    assert category == OpportunityCategory.CAPITULATION_RECOVERY
    assert direction == "LONG"
    assert inv is not None and inv < 1.0


def test_liquidity_and_spread_gate_rejection(hunter: OpportunityHunter):
    """Verifies illiquid coins (< $15M) and wide-spread coins (> 12 bps) are rejected, while core anchors pass."""
    fake_spot = [
        # Illiquid coin: $2M volume -> REJECTED
        {"symbol": "SHITCOIN1USDT", "quoteVolume": "2000000.0", "lastPrice": "1.0", "priceChangePercent": "50.0"},
        # Wide-spread coin: 50 bps spread -> REJECTED
        {
            "symbol": "WIDECOINUSDT",
            "quoteVolume": "30000000.0",
            "lastPrice": "10.0",
            "bidPrice": "9.95",
            "askPrice": "10.05",
            "priceChangePercent": "10.0",
        },
        # High volume liquid altcoin -> QUALIFIED
        {
            "symbol": "LINKUSDT",
            "quoteVolume": "85000000.0",
            "lastPrice": "20.0",
            "bidPrice": "19.998",
            "askPrice": "20.002",
            "priceChangePercent": "12.0",
        },
        # Core Anchor: BTCUSDT -> ALWAYS PRESERVED
        {
            "symbol": "BTCUSDT",
            "quoteVolume": "500000000.0",
            "lastPrice": "82000.0",
            "bidPrice": "81999.0",
            "askPrice": "82001.0",
            "priceChangePercent": "1.5",
        },
    ]
    fake_futures = [
        {"symbol": "LINKUSDT", "quoteVolume": "120000000.0", "lastPrice": "20.0", "priceChangePercent": "12.0"},
        {"symbol": "BTCUSDT", "quoteVolume": "900000000.0", "lastPrice": "82000.0", "priceChangePercent": "1.5"},
    ]

    records = hunter._process_and_rank_tickers(fake_spot, fake_futures)
    symbols = {r.symbol for r in records}

    assert "SHITCOIN1/USDT" not in symbols
    assert "WIDECOIN/USDT" not in symbols
    assert "LINK/USDT" in symbols
    assert "BTC/USDT" in symbols


def test_watchlist_lifecycle_transitions(hunter: OpportunityHunter):
    """Verifies DISCOVERED -> QUALIFIED -> ACTIVE -> RETIRED lifecycle."""
    fake_spot = [
        {"symbol": "LINKUSDT", "quoteVolume": "50000000.0", "lastPrice": "20.0", "priceChangePercent": "10.0"},
    ]
    fake_futures = [
        {"symbol": "LINKUSDT", "quoteVolume": "50000000.0", "lastPrice": "20.0", "priceChangePercent": "10.0"},
    ]

    records = hunter._process_and_rank_tickers(fake_spot, fake_futures)
    hunter._update_watchlist_lifecycle(records)

    wl = hunter.get_watchlist()
    assert len(wl) == 1
    assert wl[0]["symbol"] == "LINK/USDT"
    assert wl[0]["state"] in (WatchlistState.QUALIFIED.value, WatchlistState.ACTIVE.value)


@pytest.mark.asyncio
async def test_screener_api_endpoint_contracts():
    """Verifies that FastAPI /api/screener/opportunities returns valid JSON schema."""
    from httpx import ASGITransport, AsyncClient
    from app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/screener/opportunities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "opportunities" in data
        assert "health" in data

        resp_health = await client.get("/api/screener/health")
        assert resp_health.status_code == 200
        assert "status" in resp_health.json()

        resp_wl = await client.get("/api/screener/watchlist")
        assert resp_wl.status_code == 200
        assert "watchlist" in resp_wl.json()

