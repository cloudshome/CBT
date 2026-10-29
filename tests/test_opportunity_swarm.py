"""
tests/test_opportunity_swarm.py
===============================
Adversarial and functional test suite for the Mastermind Opportunity Hunter
and Dynamic Long/Short Opportunity Specialist Swarm integration.

Verifies:
1. Pre-breakout compression, confirmed breakout, and blow-off exhaustion classification.
2. Verified multi-venue link generation (TradingView, Binance, Bybit).
3. DynamicOpportunitySpecialist candidate proposal generation for LONG and SHORT regimes.
4. Arbiter dynamic specialist registration and evaluation with deterministic risk gates.
5. End-to-end API contracts for opportunity signals and specialist deployment.
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.mastermind.specialist_base import SpecialistArchetype
from core.mastermind.specialists import (
    DynamicOpportunitySpecialist,
)
from core.screener.opportunity_hunter import (
    AttentionState,
    OpportunityCategory,
    OpportunityHunter,
    TimingStage,
    build_binance_url,
    build_bybit_url,
    build_tradingview_url,
)
from core.sky_intelligence.types import DecisionAction


def _generate_synthetic_candles(base_price=10.0, count=25, trend=0.001):
    candles = []
    ts = int(time.time() * 1000) - (count * 15 * 60 * 1000)
    price = base_price
    for i in range(count):
        price = price * (1.0 + trend)
        candles.append(
            {
                "timestamp": ts + (i * 15 * 60 * 1000),
                "open": price * 0.998,
                "high": price * 1.003,
                "low": price * 0.997,
                "close": price,
                "volume": 2500.0,
            }
        )
    return candles


def test_venue_url_builders():
    """Verifies TradingView, Binance, and Bybit URL generation across spot and futures."""
    # TradingView
    tv_fut = build_tradingview_url("ARIA", "USDT", is_futures=True)
    assert tv_fut == "https://www.tradingview.com/chart/?symbol=BINANCE:ARIAUSDT.P"
    tv_spot = build_tradingview_url("BTC", "USDT", is_futures=False)
    assert tv_spot == "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT"

    # Binance
    bin_fut = build_binance_url("ARIA", "USDT", is_futures=True)
    assert bin_fut == "https://www.binance.com/en/futures/ARIAUSDT"
    bin_spot = build_binance_url("ETH", "USDT", is_futures=False)
    assert bin_spot == "https://www.binance.com/en/trade/ETH_USDT"

    # Bybit
    byb = build_bybit_url("KORU", "USDT")
    assert byb == "https://www.bybit.com/trade/usdt/KORUUSDT"


def test_classify_pre_breakout_compression():
    """Verifies coiling price near resistance with rising RVOL classifies as PRE_BREAKOUT_COMPRESSION."""
    hunter = OpportunityHunter()
    cat, state, venue, direction, rationale, quality, inv = hunter._classify_opportunity(
        symbol="COIL/USDT",
        price=9.85,
        price_change=3.5,
        quote_vol=45_000_000.0,
        rvol=1.8,
        spread_bps=3.0,
        high_24h=10.0,  # price is within 1.5% of high
        low_24h=9.2,
        spot_eligible=True,
        futures_eligible=True,
        attention_score=78.0,
    )
    assert cat == OpportunityCategory.PRE_BREAKOUT_COMPRESSION
    assert state == AttentionState.BREAKOUT_CANDIDATE
    assert direction == "LONG"
    assert quality >= 80.0
    assert inv is not None and inv < 9.85


@pytest.mark.asyncio
async def test_dynamic_opportunity_specialist_long_proposal():
    """Verifies DynamicOpportunitySpecialist produces a structured LONG candidate proposal."""
    spec = DynamicOpportunitySpecialist(
        target_symbol="KORU/USDT",
        category="CONFIRMED_BREAKOUT",
        recommended_direction="LONG",
        invalidation_level=9.50,
        primary_rationale="High-volume breakout near 24h highs",
        market_attention_score=85.0,
        timing_stage=TimingStage.EARLY.value,
    )
    assert spec.archetype == SpecialistArchetype.DYNAMIC_OPPORTUNITY_HUNTER
    assert spec.specialist_id == "spec_opp_koru_usdt"

    candles = _generate_synthetic_candles(base_price=10.50, count=20)
    tf_map = {"15m": candles}
    proposal = await spec.evaluate_market(candles, tf_map)

    assert proposal.symbol == "KORU/USDT"
    assert proposal.direction == DecisionAction.LONG
    assert proposal.entry_price > 0
    assert proposal.stop_loss < proposal.entry_price
    assert proposal.take_profit > proposal.entry_price
    assert proposal.risk_reward_ratio >= 2.0
    assert proposal.expected_value_r >= 0.25
    assert proposal.confidence_score >= 0.55
    assert "CONFIRMED_BREAKOUT" in proposal.thesis


@pytest.mark.asyncio
async def test_dynamic_opportunity_specialist_short_proposal():
    """Verifies DynamicOpportunitySpecialist produces a structured SHORT candidate proposal."""
    spec = DynamicOpportunitySpecialist(
        target_symbol="ARIA/USDT",
        category="BLOW_OFF_EXHAUSTION",
        recommended_direction="SHORT",
        invalidation_level=0.065,
        primary_rationale="Parabolic expansion (+25.1%) with 4.4x RVOL",
        market_attention_score=95.0,
        timing_stage=TimingStage.EXHAUSTED.value,
    )
    assert spec.archetype == SpecialistArchetype.DYNAMIC_OPPORTUNITY_HUNTER

    candles = _generate_synthetic_candles(base_price=0.052, count=20)
    tf_map = {"15m": candles}
    proposal = await spec.evaluate_market(candles, tf_map)

    assert proposal.symbol == "ARIA/USDT"
    assert proposal.direction == DecisionAction.SHORT
    assert proposal.entry_price > 0
    assert proposal.stop_loss > proposal.entry_price  # Short stop loss above entry
    assert proposal.take_profit < proposal.entry_price  # Short take profit below entry
    assert proposal.risk_reward_ratio >= 2.0
    assert proposal.expected_value_r >= 0.25
    assert proposal.confidence_score >= 0.55
    assert "BLOW_OFF_EXHAUSTION" in proposal.thesis


@pytest.mark.asyncio
async def test_arbiter_dynamic_specialist_deployment_and_evaluation():
    """Verifies MastermindArbiterCouncil registers dynamic specialists and evaluates proposals."""
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    initial_count = len(arbiter.get_all_specialists())

    # Deploy dynamic specialist
    spec = arbiter.deploy_dynamic_specialist(
        symbol="Q/USDT",
        category="BLOW_OFF_EXHAUSTION",
        direction="SHORT",
        invalidation_level=0.170,
        primary_rationale="Parabolic expansion (+54.9%) with 10.0x RVOL",
        market_attention_score=100.0,
        timing_stage="EXHAUSTED",
    )
    assert len(arbiter.get_all_specialists()) == initial_count + 1
    assert "Q/USDT" in arbiter.dynamic_specialists

    # Evaluate swarm with Q/USDT data
    candles = _generate_synthetic_candles(base_price=0.160, count=25)
    market_data = {
        "Q/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
    }
    decisions = await arbiter.evaluate_swarm(market_data)
    q_decisions = [d for d in decisions if d.symbol == "Q/USDT"]
    assert len(q_decisions) >= 1
    assert q_decisions[0].direction == "SHORT"
    assert q_decisions[0].expected_value_r >= 0.20


@pytest.mark.asyncio
async def test_api_mastermind_opportunity_signals_and_deploy():
    """Verifies FastAPI endpoints for opportunity signals and specialist deployment."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test signals endpoint
        res = await client.get("/api/mastermind/opportunities/signals")
        assert res.status_code == 200
        data = res.json()
        assert "opportunities" in data
        assert "health" in data

        # 2. Test deploy specialist endpoint
        payload = {
            "symbol": "SOXL/USDT",
            "category": "CONFIRMED_BREAKOUT",
            "direction": "LONG",
            "invalidation_level": 88.50,
            "primary_rationale": "High-volume breakout near 24h highs",
            "market_attention_score": 79.1,
            "timing_stage": "ACTIVE",
        }
        dep_res = await client.post("/api/mastermind/specialists/deploy", json=payload)
        assert dep_res.status_code == 200
        dep_data = dep_res.json()
        assert dep_data["status"] == "DEPLOYED"
        assert dep_data["symbol"] == "SOXL/USDT"
        assert dep_data["direction"] == "LONG"

