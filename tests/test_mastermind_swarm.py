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
from core.mastermind.specialist_base import (
    CandidateProposal,
    EpistemicGrade,
    SpecialistArchetype,
)
from core.mastermind.specialists import (
    BtcMacroSpecialist,
    DynamicOpportunitySpecialist,
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


@pytest.mark.asyncio
async def test_specialist_adversarial_review_detects_upper_wick_rejection():
    """
    Phase 1 Adversarial Test:
    A setup where a breakout candle creates a severe upper rejection wick
    (closing in the lower 35% of its high-low range) indicates trapped longs.
    The adversarial self-review MUST demote the proposal to NO_TRADE and flag disconfirming evidence.
    """
    candles = _generate_synthetic_candles(base_price=100.0, count=25)
    candles[-1]["open"] = 102.0
    candles[-1]["high"] = 120.0
    candles[-1]["low"] = 100.0
    candles[-1]["close"] = 103.5
    candles[-1]["volume"] = 1000.0

    spec = MemeMomentumSpecialist("DOGE/USDT")
    prop = await spec.evaluate_market(candles, {"15m": candles})

    assert prop.direction == DecisionAction.NO_TRADE
    assert len(prop.disconfirming_evidence) >= 1
    assert any("Upper rejection wick" in e for e in prop.disconfirming_evidence)
    assert "[VETOED BY ADVERSARIAL REVIEW]" in prop.thesis
    assert prop.confidence_score <= 0.25


@pytest.mark.asyncio
async def test_specialist_adversarial_review_detects_orderbook_wall():
    """
    Phase 1 Adversarial Test:
    When an orderbook ask-side liquidity wall > 2.5x bid depth stands right ahead,
    a LONG proposal's confidence must be penalized and disconfirming evidence recorded.
    """
    candles = _generate_synthetic_candles(base_price=100.0, count=25)
    candles[-1]["open"] = 100.0
    candles[-1]["high"] = 105.0
    candles[-1]["low"] = 99.5
    candles[-1]["close"] = 104.5
    candles[-1]["volume"] = 1000.0

    order_book = {
        "bids": [[104.4, 300.0], [104.3, 200.0]],
        "asks": [[104.6, 2000.0], [104.7, 1000.0]],
    }

    spec = MemeMomentumSpecialist("DOGE/USDT")
    prop = await spec.evaluate_market(candles, {"15m": candles}, order_book=order_book)

    assert len(prop.disconfirming_evidence) >= 1
    assert any("ask-side liquidity wall" in e for e in prop.disconfirming_evidence)
    assert prop.confidence_score < 0.68


@pytest.mark.asyncio
async def test_specialist_adversarial_review_detects_lower_absorption_wick_on_short():
    """
    Phase 1 Adversarial Test:
    When DynamicOpportunitySpecialist recommends a SHORT, but the bar ends with an
    absorption wick (closing in the upper 35% of the range), it indicates trapped shorts.
    The adversarial self-review MUST veto the SHORT to NO_TRADE.
    """
    candles = _generate_synthetic_candles(base_price=50.0, count=25)
    candles[-1]["open"] = 49.0
    candles[-1]["high"] = 52.0
    candles[-1]["low"] = 45.0
    candles[-1]["close"] = 51.5
    candles[-1]["volume"] = 500.0

    spec = DynamicOpportunitySpecialist(
        target_symbol="SUI/USDT",
        category="BLOW_OFF_EXHAUSTION",
        recommended_direction="SHORT",
        market_attention_score=85.0,
    )
    prop = await spec.evaluate_market(candles, {"15m": candles})

    assert prop.direction == DecisionAction.NO_TRADE
    assert len(prop.disconfirming_evidence) >= 1
    assert any("absorption wick" in e for e in prop.disconfirming_evidence)
    assert "[VETOED BY ADVERSARIAL REVIEW]" in prop.thesis


def test_candidate_proposal_epistemic_grade_serialization():
    """
    Phase 1 Epistemic Taxonomy Test:
    CandidateProposal must support EpistemicGrade classification and serialize
    cleanly to dict without enum leakage.
    """
    prop = CandidateProposal(
        proposal_id="prop_test_001",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.LONG,
        thesis="BTC testing key support confluence.",
        entry_price=64000.0,
        stop_loss=63000.0,
        take_profit=66500.0,
        risk_reward_ratio=2.5,
        expected_value_r=0.85,
        confidence_score=0.72,
        invalidation_condition="Loss of 63000 support level.",
        suggested_notional_usd=500.0,
        epistemic_grade=EpistemicGrade.HYPOTHESIS,
        disconfirming_evidence=["High funding rate"],
        falsification_conditions=["1h candle close below $63,000"],
    )

    d = prop.to_dict()
    assert d["epistemic_grade"] == "HYPOTHESIS"
    assert d["archetype"] == "BTC_MACRO_MICROSTRUCTURE"
    assert d["direction"] == "LONG"
    assert d["disconfirming_evidence"] == ["High funding rate"]
    assert d["falsification_conditions"] == ["1h candle close below $63,000"]
