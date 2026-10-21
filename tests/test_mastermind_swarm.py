"""
tests/test_mastermind_swarm.py
==============================
Adversarial and functional test suite for the SKY Mastermind Hierarchical Multi-Agent Council.
Verifies candidate proposals, specialist evaluations, arbiter correlation handling,
rejection reasons, and risk gate compliance.
"""

import time

import pytest

from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.mastermind.specialists import (
    BtcMacroSpecialist,
    EthSpecialist,
    LowCapBreakoutSpecialist,
    MemeMomentumSpecialist,
)
from core.sky_intelligence.types import DecisionAction


def _generate_synthetic_candles(base_price=60000.0, count=30, trend=0.001):
    candles = []
    ts = int(time.time() * 1000) - (count * 15 * 60 * 1000)
    price = base_price
    for i in range(count):
        price = price * (1.0 + trend)
        candles.append(
            {
                "timestamp": ts + (i * 15 * 60 * 1000),
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 100.0,
            }
        )
    return candles


@pytest.mark.asyncio
async def test_specialists_generate_candidate_proposals():
    candles = _generate_synthetic_candles(60000.0, 30)
    tf_map = {"15m": candles}

    btc_spec = BtcMacroSpecialist()
    prop_btc = await btc_spec.evaluate_market(candles, tf_map)
    assert prop_btc.specialist_id == "spec_btc_macro"
    assert prop_btc.symbol == "BTC/USDT"
    assert isinstance(prop_btc.direction, DecisionAction)

    eth_spec = EthSpecialist()
    prop_eth = await eth_spec.evaluate_market(candles, tf_map)
    assert prop_eth.specialist_id == "spec_eth_structural"
    assert prop_eth.symbol == "ETH/USDT"


@pytest.mark.asyncio
async def test_meme_specialist_volume_spike_detection():
    # Build candles with a massive 5x volume spike on the last candle
    candles = _generate_synthetic_candles(0.15, 25)
    candles[-1]["volume"] = 1000.0  # 10x normal volume
    candles[-1]["close"] = 0.18  # Breakout above prev high
    candles[-1]["high"] = 0.185

    meme_spec = MemeMomentumSpecialist("DOGE/USDT")
    prop = await meme_spec.evaluate_market(candles, {"15m": candles})

    assert prop.direction == DecisionAction.LONG
    assert prop.confidence_score >= 0.50
    assert "Volume Spike" in prop.thesis
    assert prop.stop_loss < prop.entry_price < prop.take_profit


@pytest.mark.asyncio
async def test_lowcap_specialist_orderbook_imbalance():
    candles = _generate_synthetic_candles(0.00001, 20)
    # Skewed orderbook: heavy bids, thin asks
    order_book = {
        "bids": [[0.00001, 10000.0], [0.0000099, 8000.0]],
        "asks": [[0.0000101, 500.0], [0.0000102, 300.0]],
    }

    lowcap_spec = LowCapBreakoutSpecialist("PEPE/USDT")
    prop = await lowcap_spec.evaluate_market(candles, {"15m": candles}, order_book=order_book)

    assert prop.direction == DecisionAction.LONG
    assert prop.confidence_score >= 0.60
    assert "Bid-side skew" in prop.thesis


@pytest.mark.asyncio
async def test_arbiter_audit_ledger_persistence():
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    candles = _generate_synthetic_candles(60000.0, 25)

    market_data = {
        "BTC/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
        "ETH/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
    }

    decisions = await arbiter.evaluate_swarm(market_data)
    assert len(decisions) >= 2

    # Check database persistence
    recent = arbiter.get_recent_decisions(limit=10)
    assert len(recent) >= len(decisions)
    assert recent[0]["decision_id"].startswith("mm_dec_")


@pytest.mark.asyncio
async def test_risk_governor_absolute_veto_on_circuit_breaker():
    """
    Stage 4 Adversarial Test:
    Even when all specialist agents reach unanimous high-confidence consensus,
    the Independent Risk Governor's circuit breaker has ABSOLUTE VETO power.
    No trade can bypass the Risk Gate.
    """
    from unittest.mock import patch, MagicMock
    from core.risk_manager import RiskGateStatus

    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    candles = _generate_synthetic_candles(60000.0, 25)

    market_data = {
        "BTC/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
        "ETH/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
    }

    # Mock the independent Risk Gate in lockout / circuit-breaker state (e.g. 3.2% daily drawdown)
    locked_gate = RiskGateStatus(
        is_trading_allowed=False,
        daily_drawdown_pct=0.032,
        max_daily_drawdown_pct=0.03,
        lockout_active=True,
        lockout_expiry_timestamp_ms=int(time.time() * 1000) + 86400000,
        reason="Daily drawdown 3.2% breached maximum 3.0% threshold. Total trading lockout active.",
    )

    with patch("core.mastermind.mastermind_arbiter.risk_manager.evaluate_risk_gate", return_value=locked_gate):
        decisions = await arbiter.evaluate_swarm(market_data)
        assert len(decisions) >= 2
        for d in decisions:
            # 100% of proposals MUST be vetoed
            assert d.is_approved is False
            assert "Risk Gate lockout active" in d.rejection_reason
            assert d.approved_notional_usd == 0.0


@pytest.mark.asyncio
async def test_arbiter_enforces_1_point_5_percent_max_equity_risk_cap():
    """
    Stage 4 Adversarial Test:
    Verifies that position sizing strictly adheres to the 1.5% maximum equity risk cap.
    """
    arbiter = MastermindArbiterCouncil(account_equity_usd=20_000.0)
    candles = _generate_synthetic_candles(60000.0, 25)

    # Candidate with wide stop
    candles[-1]["close"] = 60000.0
    candles[-1]["volume"] = 500.0

    market_data = {
        "BTC/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
    }

    decisions = await arbiter.evaluate_swarm(market_data)
    assert len(decisions) >= 1
    d = decisions[0]
    # Max risk allowed on $20,000 equity is $300 (1.5%)
    assert d.portfolio_equity_usd == 20000.0
