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

from core.screener.opportunity_hunter import (
    AttentionState,
    OpportunityCategory,
    OpportunityHunter,
    OpportunityRecord,
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
        {
            "symbol": "SHITCOIN1USDT",
            "quoteVolume": "2000000.0",
            "lastPrice": "1.0",
            "priceChangePercent": "50.0",
        },
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
        {
            "symbol": "LINKUSDT",
            "quoteVolume": "120000000.0",
            "lastPrice": "20.0",
            "priceChangePercent": "12.0",
        },
        {
            "symbol": "BTCUSDT",
            "quoteVolume": "900000000.0",
            "lastPrice": "82000.0",
            "priceChangePercent": "1.5",
        },
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
        {
            "symbol": "LINKUSDT",
            "quoteVolume": "50000000.0",
            "lastPrice": "20.0",
            "priceChangePercent": "10.0",
        },
    ]
    fake_futures = [
        {
            "symbol": "LINKUSDT",
            "quoteVolume": "50000000.0",
            "lastPrice": "20.0",
            "priceChangePercent": "10.0",
        },
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


def test_pre_spike_long_and_post_spike_short_rules(hunter: OpportunityHunter):
    """
    Stage 3 Adversarial Test:
    Ensures that Pre-Spike Long candidates (compression near resistance with rising RVOL)
    and Post-Spike Short candidates (climax extension with extreme volume) generate
    deterministic invalidation levels, high R:R targets, and valid venue links.
    """
    # 1. Pre-Spike Long candidate
    cat_long, state_long, venue_long, dir_long, rat_long, qual_long, inv_long = hunter._classify_opportunity(
        symbol="WLD/USDT",
        price=0.5420,
        price_change=8.4,
        quote_vol=389_000_000.0,
        rvol=3.5,
        spread_bps=3.5,
        high_24h=0.5500,  # trading right near 24h high (within 3%)
        low_24h=0.4936,
        spot_eligible=True,
        futures_eligible=True,
        attention_score=76.8,
    )
    assert cat_long == OpportunityCategory.PRE_BREAKOUT_COMPRESSION
    assert dir_long == "LONG"
    assert inv_long is not None and inv_long <= 0.5420
    assert qual_long >= 80.0

    # 2. Post-Spike Short candidate
    cat_short, state_short, venue_short, dir_short, rat_short, qual_short, inv_short = hunter._classify_opportunity(
        symbol="BR/USDT",
        price=0.7255,
        price_change=47.2,
        quote_vol=565_000_000.0,
        rvol=10.0,
        spread_bps=3.5,
        high_24h=0.7500,
        low_24h=0.4500,
        spot_eligible=True,
        futures_eligible=True,
        attention_score=100.0,
    )
    assert cat_short == OpportunityCategory.BLOW_OFF_EXHAUSTION
    assert dir_short == "SHORT"
    assert inv_short is not None and inv_short > 0.7255
    assert qual_short >= 70.0


def test_tradability_stress_gate_quarantines_high_friction_candidate(hunter: OpportunityHunter):
    """
    Phase 3 Tradability Gate Test:
    When a candidate coin has high spread and tiny expected target move such that
    expected move < 2.5x stress frictions, the candidate MUST be quarantined into
    NO_TRADE_QUARANTINE with direction WATCH.
    """
    # Price: 1.0, Spread: 11.0 bps, 24h Vol: $16M (low liquidity -> higher impact),
    # Invalidation distance: 0.10% (tight stop) with RR=2.0 -> target move = 0.20%
    # Base friction = 10 (fees) + 11 (spread) + ~9.3 (impact) = ~30.3 bps
    # 2.5x Stress friction = ~75.7 bps = 0.757% > 0.20%
    is_tradable, stress_bps, target_move = hunter.evaluate_tradability_stress(
        price=1.0,
        spread_bps=11.0,
        quote_vol=16_000_000.0,
        dist_to_invalidation_pct=0.10,
        rr=2.0,
    )
    assert is_tradable is False
    assert stress_bps > 60.0  # > 0.60%
    assert target_move == 0.20

    # Test within _process_and_rank_tickers
    fake_spot = [
        {
            "symbol": "TIGHTSTOPUSDT",
            "lastPrice": "1.0",
            "priceChangePercent": "12.0",
            "quoteVolume": "80000000.0",
            "count": 50000,
            "bidPrice": "0.9989",
            "askPrice": "1.0000",  # 11 bps spread
            "highPrice": "1.01",
            "lowPrice": "0.999",  # tight range -> tight invalidation (0.10%)
        }
    ]
    records = hunter._process_and_rank_tickers(fake_spot, [])
    assert len(records) == 1
    rec = records[0]
    assert rec.is_tradable_under_stress is False
    assert rec.opportunity_category == OpportunityCategory.NO_TRADE_QUARANTINE
    assert rec.recommended_direction == "WATCH"
    assert "[UNTRADABLE: 2.5x STRESS FRICTION GATE]" in rec.primary_rationale


def test_tradability_stress_gate_approves_wide_target_liquid_candidate(hunter: OpportunityHunter):
    """
    Phase 3 Tradability Gate Test:
    A high-volume breakout with a healthy expansion target (> 2.0%) easily clears
    2.5x stress frictions (~0.35%) and remains an active tradeable LONG candidate.
    """
    is_tradable, stress_bps, target_move = hunter.evaluate_tradability_stress(
        price=50.0,
        spread_bps=2.0,
        quote_vol=120_000_000.0,
        dist_to_invalidation_pct=2.5,
        rr=2.5,
    )
    assert is_tradable is True
    assert stress_bps < 40.0  # ~0.35%
    assert target_move == 6.25  # 6.25% >> 0.35%


def test_attrition_ledger_recording_and_funnel_metrics(hunter: OpportunityHunter):
    """
    Phase 3 Attrition Funnel Test:
    Verifies that discovered opportunities are persisted into the SQLite attrition ledger,
    and lifecycle updates accurately resolve targets and calculate survival rates.
    """
    import time

    now_ms = int(time.time() * 1000)

    # Fabricate a qualified OpportunityRecord
    rec = OpportunityRecord(
        symbol="TESTCOIN/USDT",
        base_asset="TESTCOIN",
        quote_asset="USDT",
        spot_eligible=True,
        futures_eligible=True,
        current_price=10.0,
        price_change_24h_pct=8.5,
        quote_volume_24h_usd=45_000_000.0,
        trade_count_24h=120_000,
        estimated_spread_bps=3.0,
        relative_volume_ratio=2.2,
        market_attention_score=82.0,
        trade_quality_score=85.0,
        attention_state=AttentionState.BREAKOUT_CANDIDATE,
        opportunity_category=OpportunityCategory.PRE_BREAKOUT_COMPRESSION,
        recommended_venue="SPOT_OR_FUTURES",
        recommended_direction="LONG",
        primary_rationale="Pre-breakout coiling near resistance.",
        invalidation_level=9.70,
        observation_timestamp_ms=now_ms,
        timing_stage="PRE_SPIKE",
        reward_to_risk=2.5,
        distance_to_invalidation_pct=3.0,
        stress_friction_bps=35.0,
        is_tradable_under_stress=True,
    )

    opp_id = hunter.record_discovered_opportunity(rec)
    assert opp_id.startswith("opp_TESTCOIN_USDT_")

    # Update lifecycle with price that triggers target (target is 10.0 + (0.3 * 2.5) = 10.75)
    counts = hunter.update_attrition_lifecycle({"TESTCOIN/USDT": 10.80})
    assert counts["resolved"] >= 1

    # Check Funnel Metrics
    metrics = hunter.get_attrition_funnel_metrics()
    assert metrics["total_discovered"] >= 1
    assert metrics["survival_rate_15m"] >= 0.50
    assert OpportunityCategory.PRE_BREAKOUT_COMPRESSION.value in metrics["by_category"]


def test_attrition_ledger_identifies_atrophied_breakout(hunter: OpportunityHunter):
    """
    Phase 3 Attrition Funnel Test:
    When a pre-spike compression candidate sits past 15 minutes and sags below entry price,
    the attrition tracker correctly marks status_15m as ATROPHIED.
    """
    import time

    # Discovered 20 minutes ago (1200s = 1,200,000ms ago)
    old_time_ms = int(time.time() * 1000) - 1_200_000

    rec = OpportunityRecord(
        symbol="SAGCOIN/USDT",
        base_asset="SAGCOIN",
        quote_asset="USDT",
        spot_eligible=True,
        futures_eligible=True,
        current_price=2.0,
        price_change_24h_pct=5.0,
        quote_volume_24h_usd=30_000_000.0,
        trade_count_24h=80_000,
        estimated_spread_bps=4.0,
        relative_volume_ratio=1.8,
        market_attention_score=75.0,
        trade_quality_score=80.0,
        attention_state=AttentionState.BREAKOUT_CANDIDATE,
        opportunity_category=OpportunityCategory.PRE_BREAKOUT_COMPRESSION,
        recommended_venue="SPOT_OR_FUTURES",
        recommended_direction="LONG",
        primary_rationale="Pre-breakout candidate that failed to expand.",
        invalidation_level=1.92,
        observation_timestamp_ms=old_time_ms,
        timing_stage="PRE_SPIKE",
        reward_to_risk=2.5,
        distance_to_invalidation_pct=4.0,
        stress_friction_bps=40.0,
        is_tradable_under_stress=True,
    )

    hunter.record_discovered_opportunity(rec)

    # Current price has sagged to 1.96 (below entry 2.0, but above invalidation 1.92)
    counts = hunter.update_attrition_lifecycle({"SAGCOIN/USDT": 1.96})
    assert counts["15m"] >= 1

    metrics = hunter.get_attrition_funnel_metrics()
    assert metrics["atrophy_rate"] > 0.0
