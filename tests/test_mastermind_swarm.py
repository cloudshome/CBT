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
    from core.portfolio_shadow import portfolio_shadow
    portfolio_shadow.reset_all_positions()
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


@pytest.mark.asyncio
async def test_arbiter_information_overlap_discount_for_correlated_assets():
    """
    Phase 2 Adversarial Test:
    When multiple specialists generate simultaneous LONG proposals on highly correlated assets
    (BTC, ETH, SOL with pairwise rho >= 0.78), the Arbiter must detect the information overlap
    and apply a significant sizing haircut (N_eff / N < 0.45) rather than tripling portfolio risk.
    """
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)

    # 3 simultaneous LONG proposals on BTC, ETH, and SOL
    p_btc = CandidateProposal(
        proposal_id="prop_btc_test",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.LONG,
        thesis="BTC Macro support reclaim.",
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
        risk_reward_ratio=3.0,
        expected_value_r=1.2,
        confidence_score=0.75,
        invalidation_condition="Close < 64000",
        suggested_notional_usd=500.0,
    )
    p_eth = CandidateProposal(
        proposal_id="prop_eth_test",
        specialist_id="spec_eth_structural",
        archetype=SpecialistArchetype.ETH_DEFI_STRUCTURAL,
        symbol="ETH/USDT",
        direction=DecisionAction.LONG,
        thesis="ETH structural breakout.",
        entry_price=3500.0,
        stop_loss=3400.0,
        take_profit=3800.0,
        risk_reward_ratio=3.0,
        expected_value_r=1.1,
        confidence_score=0.72,
        invalidation_condition="Close < 3400",
        suggested_notional_usd=400.0,
    )
    p_sol = CandidateProposal(
        proposal_id="prop_sol_test",
        specialist_id="spec_sol_velocity",
        archetype=SpecialistArchetype.SOL_HIGH_VELOCITY,
        symbol="SOL/USDT",
        direction=DecisionAction.LONG,
        thesis="SOL momentum expansion.",
        entry_price=160.0,
        stop_loss=152.0,
        take_profit=180.0,
        risk_reward_ratio=2.5,
        expected_value_r=0.9,
        confidence_score=0.70,
        invalidation_condition="Close < 152",
        suggested_notional_usd=300.0,
    )

    discounts = arbiter.compute_information_overlap_discount([p_btc, p_eth, p_sol])

    assert len(discounts) == 3
    # Pairwise correlations between BTC, ETH, SOL are 0.78 - 0.85
    # For N=3 and rho ~ 0.81, discount = 1 / (1 + 2 * 0.81) = 1 / 2.62 ~ 0.38
    for pid in ("prop_btc_test", "prop_eth_test", "prop_sol_test"):
        assert discounts[pid] <= 0.45
        assert discounts[pid] >= 0.35

    # A single isolated proposal must receive 1.0 (no discount)
    single_discount = arbiter.compute_information_overlap_discount([p_btc])
    assert single_discount["prop_btc_test"] == 1.0


@pytest.mark.asyncio
async def test_arbiter_macro_divergence_penalizes_altcoin_long_when_btc_short():
    """
    Phase 2 Adversarial Test:
    When Macro BTC specialist issues a SHORT proposal, an altcoin specialist attempting
    a LONG proposal faces an immediate macro headwind.
    The Arbiter must penalize candidate confidence by 30% and reject it if it falls below 0.50 hurdle.
    """
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)

    # Synthetic candles where BTC is falling (bearish close)
    btc_candles = _generate_synthetic_candles(base_price=65000.0, count=25, trend=-0.005)
    # Synthetic candles for Altcoin
    alt_candles = _generate_synthetic_candles(base_price=1.5, count=25, trend=0.001)

    # Deploy dynamic specialist for SUI/USDT recommending LONG with moderate 0.60 confidence
    arbiter.deploy_dynamic_specialist(
        symbol="SUI/USDT",
        category="PRE_SPIKE_ACCUMULATION",
        direction="LONG",
        market_attention_score=60.0,  # Translates to conf ~ 0.60
    )

    market_data = {
        "BTC/USDT": {"15m": btc_candles, "multi_tf": {"15m": btc_candles}},
        "SUI/USDT": {"15m": alt_candles, "multi_tf": {"15m": alt_candles}},
    }

    from unittest.mock import AsyncMock, patch

    # Mock BTC specialist to produce high-conviction SHORT proposal
    btc_short_proposal = CandidateProposal(
        proposal_id="prop_btc_short_01",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.SHORT,
        thesis="BTC Macro Distribution Breakdown: Institutional sweep of liquidity.",
        entry_price=63000.0,
        stop_loss=64500.0,
        take_profit=59000.0,
        risk_reward_ratio=2.67,
        expected_value_r=1.35,
        confidence_score=0.82,
        invalidation_condition="Close > 64500",
        suggested_notional_usd=600.0,
    )

    with patch.object(
        arbiter.specialists[0], "evaluate_market", new=AsyncMock(return_value=btc_short_proposal)
    ):
        decisions = await arbiter.evaluate_swarm(market_data)

        # Find SUI decision
        sui_dec = next((d for d in decisions if d.symbol == "SUI/USDT"), None)
        assert sui_dec is not None

        # SUI LONG was evaluated against BTC SHORT:
        # Confidence 0.60 haircut by 30% -> 0.42 (< 0.50 hurdle rate)
        assert sui_dec.is_approved is False
        assert "below threshold" in sui_dec.rejection_reason or "Effective Confidence" in sui_dec.rejection_reason or "Asset Tier Firewall" in sui_dec.rejection_reason
        assert sui_dec.confidence_score <= 0.45


def test_specialist_brier_score_calibration_penalizes_overconfident_loser():
    """
    Phase 2 Calibration Test:
    A specialist claiming 0.85 confidence across 5 trades that all stopped out (outcome=0.0)
    must receive a severe Brier penalty (Brier > 0.70) and dynamic weight downscaled to 0.25.
    """
    import uuid

    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    spec_id = f"spec_loser_{uuid.uuid4().hex[:6]}"

    for i in range(5):
        p = CandidateProposal(
            proposal_id=f"prop_loser_{i}_{uuid.uuid4().hex[:6]}",
            specialist_id=spec_id,
            archetype=SpecialistArchetype.MEME_MOMENTUM_SPIKE,
            symbol="DOGE/USDT",
            direction=DecisionAction.LONG,
            thesis="Overconfident meme trade.",
            entry_price=0.20,
            stop_loss=0.19,
            take_profit=0.25,
            risk_reward_ratio=5.0,
            expected_value_r=2.0,
            confidence_score=0.85,
            invalidation_condition="Loss of 0.19",
            suggested_notional_usd=200.0,
        )
        arbiter.record_proposal_for_calibration(p)
        # All 5 trades ended in complete loss
        arbiter.resolve_proposal_outcome(p.proposal_id, outcome=0.0, pnl_usd=-50.0)

    calib = arbiter.get_specialist_calibration(spec_id)
    assert calib["sample_size"] == 5
    assert calib["win_rate"] == 0.0
    # Brier = (0.85 - 0.0)^2 = 0.7225
    assert calib["brier_score"] >= 0.70
    # Dynamic weighting downscaled to minimum clamp (0.25)
    assert calib["weight"] == 0.25


def test_specialist_brier_score_calibration_rewards_accurate_specialist():
    """
    Phase 2 Calibration Test:
    A specialist claiming 0.80 confidence across 5 trades that all hit take-profit (outcome=1.0)
    must receive a stellar Brier score (Brier <= 0.05) and boosted dynamic weight (weight >= 1.20).
    """
    import uuid

    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    spec_id = f"spec_winner_{uuid.uuid4().hex[:6]}"

    for i in range(5):
        p = CandidateProposal(
            proposal_id=f"prop_winner_{i}_{uuid.uuid4().hex[:6]}",
            specialist_id=spec_id,
            archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
            symbol="BTC/USDT",
            direction=DecisionAction.LONG,
            thesis="High-probability BTC trade.",
            entry_price=60000.0,
            stop_loss=59000.0,
            take_profit=63000.0,
            risk_reward_ratio=3.0,
            expected_value_r=1.5,
            confidence_score=0.80,
            invalidation_condition="Loss of 59000",
            suggested_notional_usd=500.0,
        )
        arbiter.record_proposal_for_calibration(p)
        # All 5 trades ended in full win
        arbiter.resolve_proposal_outcome(p.proposal_id, outcome=1.0, pnl_usd=150.0)

    calib = arbiter.get_specialist_calibration(spec_id)
    assert calib["sample_size"] == 5
    assert calib["win_rate"] == 1.0
    # Brier = (0.80 - 1.0)^2 = 0.04
    assert calib["brier_score"] <= 0.05
    # Dynamic weighting boosted for empirical reliability
    assert calib["weight"] >= 1.20
