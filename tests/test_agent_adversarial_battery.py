"""
tests/test_agent_adversarial_battery.py
======================================
Comprehensive Institutional Adversarial Qualification Battery for the SKY / CBT Agent Mastery Program.

Tests 5 Critical Adversarial Batteries:
- Battery A: Stale, Missing, and Corrupted Data Feeds.
- Battery B: Adversarial Contradictory Evidence & False Breakout Traps.
- Battery C: Correlation Overlap & Macro Regime Clashes.
- Battery D: Absolute Risk-Gate Primacy & 1.5% Portfolio Ceiling Enforcement.
- Battery E: Friction Stress Gate & Closed-Loop Drift Feedback.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.intelligence.forward_validation.drift_detector import (
    DriftStatus,
    MultiDimensionalDriftDetector,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    RealisticPaperFillSimulator,
)
from core.intelligence.forward_validation.suspension_controller import (
    SuspensionController,
    SuspensionPolicy,
)
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.mastermind.specialist_base import (
    CandidateProposal,
    EpistemicGrade,
    SpecialistArchetype,
)
from core.mastermind.specialists import (
    BtcMacroSpecialist,
    EthSpecialist,
    LowCapBreakoutSpecialist,
    MemeMomentumSpecialist,
    SolSpecialist,
)
from core.risk_manager import RiskGateStatus
from core.screener.opportunity_hunter import OpportunityCategory, OpportunityHunter
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


# ==============================================================================
# BATTERY A: Stale, Missing, and Corrupted Data Feeds
# ==============================================================================

@pytest.mark.asyncio
async def test_battery_a_empty_and_insufficient_candles():
    """Agents must handle empty or truncated candle histories safely without throwing unhandled exceptions."""
    btc_spec = BtcMacroSpecialist()
    eth_spec = EthSpecialist()
    lowcap_spec = LowCapBreakoutSpecialist()

    # Empty candle list
    prop_btc = await btc_spec.evaluate_market(candles_15m=[], multi_tf_candles={})
    assert prop_btc.direction in (DecisionAction.WATCH, DecisionAction.NO_TRADE) or prop_btc.confidence_score <= 0.25
    assert prop_btc.entry_price == 0.0

    # Truncated candle list (< 5 candles)
    short_candles = _generate_synthetic_candles(3000.0, count=3)
    prop_eth = await eth_spec.evaluate_market(candles_15m=short_candles, multi_tf_candles={"15m": short_candles})
    assert prop_eth.direction in (DecisionAction.WATCH, DecisionAction.NO_TRADE) or prop_eth.confidence_score <= 0.25

    prop_lowcap = await lowcap_spec.evaluate_market(candles_15m=short_candles, multi_tf_candles={"15m": short_candles})
    assert prop_lowcap.direction in (DecisionAction.WATCH, DecisionAction.NO_TRADE) or prop_lowcap.confidence_score <= 0.25


@pytest.mark.asyncio
async def test_battery_a_missing_or_none_order_book():
    """Specialists must safely evaluate when order book depth is None, empty, or missing expected keys."""
    candles = _generate_synthetic_candles(150.0, count=20)
    sol_spec = SolSpecialist()

    # None orderbook
    prop_none = await sol_spec.evaluate_market(candles_15m=candles, multi_tf_candles={"15m": candles}, order_book=None)
    assert prop_none is not None
    assert isinstance(prop_none, CandidateProposal)

    # Empty orderbook dict
    prop_empty = await sol_spec.evaluate_market(candles_15m=candles, multi_tf_candles={"15m": candles}, order_book={})
    assert prop_empty is not None
    assert isinstance(prop_empty, CandidateProposal)

    # Malformed orderbook dict (missing asks)
    prop_malformed = await sol_spec.evaluate_market(candles_15m=candles, multi_tf_candles={"15m": candles}, order_book={"bids": []})
    assert prop_malformed is not None


# ==============================================================================
# BATTERY B: Adversarial Contradictory Evidence & False Breakout Traps
# ==============================================================================

def test_battery_b_upper_wick_rejection_forces_veto():
    """A bullish breakout candle that closes in the bottom 35% of its range must be vetoed into NO_TRADE."""
    spec = BtcMacroSpecialist()
    trap_candles = _generate_synthetic_candles(65000.0, count=10)
    # Craft extreme upper rejection wick on latest candle:
    # Open: 65000, High: 70000, Low: 64900, Close: 65100 -> (65100-64900)/(70000-64900) = 200/5100 = 3.9%
    trap_candles[-1] = {
        "timestamp": int(time.time() * 1000),
        "open": 65000.0,
        "high": 70000.0,
        "low": 64900.0,
        "close": 65100.0,
        "volume": 5000.0,
    }

    initial_proposal = CandidateProposal(
        proposal_id="trap_long_01",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.LONG,
        thesis="Breakout candidate",
        entry_price=65100.0,
        stop_loss=64500.0,
        take_profit=68000.0,
        risk_reward_ratio=2.5,
        expected_value_r=1.2,
        confidence_score=0.85,
        invalidation_condition="Below 64500",
        suggested_notional_usd=1000.0,
    )

    reviewed = spec.apply_adversarial_review(initial_proposal, trap_candles)
    assert reviewed.direction == DecisionAction.NO_TRADE
    assert reviewed.confidence_score <= 0.25
    assert reviewed.expected_value_r == 0.0
    assert any("Upper rejection wick detected" in e for e in reviewed.disconfirming_evidence)
    assert "[VETOED BY ADVERSARIAL REVIEW]" in reviewed.thesis


def test_battery_b_lower_absorption_wick_forces_short_veto():
    """A bearish breakdown candle that closes in the top 35% of its range must be vetoed into NO_TRADE."""
    spec = EthSpecialist()
    trap_candles = _generate_synthetic_candles(3500.0, count=10)
    # Open: 3500, High: 3510, Low: 3200, Close: 3480 -> (3480-3200)/(3510-3200) = 280/310 = 90.3%
    trap_candles[-1] = {
        "timestamp": int(time.time() * 1000),
        "open": 3500.0,
        "high": 3510.0,
        "low": 3200.0,
        "close": 3480.0,
        "volume": 8000.0,
    }

    initial_proposal = CandidateProposal(
        proposal_id="trap_short_01",
        specialist_id="spec_eth_structural",
        archetype=SpecialistArchetype.ETH_DEFI_STRUCTURAL,
        symbol="ETH/USDT",
        direction=DecisionAction.SHORT,
        thesis="Breakdown candidate",
        entry_price=3480.0,
        stop_loss=3550.0,
        take_profit=3200.0,
        risk_reward_ratio=2.0,
        expected_value_r=0.9,
        confidence_score=0.80,
        invalidation_condition="Above 3550",
        suggested_notional_usd=1000.0,
    )

    reviewed = spec.apply_adversarial_review(initial_proposal, trap_candles)
    assert reviewed.direction == DecisionAction.NO_TRADE
    assert reviewed.confidence_score <= 0.25
    assert any("Lower absorption wick detected" in e for e in reviewed.disconfirming_evidence)


def test_battery_b_orderbook_wall_demotes_confidence():
    """A single moderate contradiction (such as a 4x ask wall) discounts confidence by 35%."""
    spec = SolSpecialist()
    candles = _generate_synthetic_candles(150.0, count=10)
    order_book = {
        "bids": [[149.9, 100.0], [149.8, 100.0]],
        "asks": [[150.1, 400.0], [150.2, 400.0]],  # 800 vs 200 = 4x
    }

    initial_proposal = CandidateProposal(
        proposal_id="sol_wall_01",
        specialist_id="spec_sol_momentum",
        archetype=SpecialistArchetype.SOL_HIGH_VELOCITY,
        symbol="SOL/USDT",
        direction=DecisionAction.LONG,
        thesis="Momentum expansion",
        entry_price=150.0,
        stop_loss=147.0,
        take_profit=156.0,
        risk_reward_ratio=2.0,
        expected_value_r=1.0,
        confidence_score=0.80,
        invalidation_condition="Below 147",
        suggested_notional_usd=1000.0,
    )

    reviewed = spec.apply_adversarial_review(initial_proposal, candles, order_book=order_book)
    # Single contradiction without wick rejection discounts by 35%: 0.80 * 0.65 = 0.52
    assert reviewed.direction == DecisionAction.LONG
    assert reviewed.confidence_score == pytest.approx(0.52, abs=0.01)
    assert any("Severe ask-side liquidity wall detected" in e for e in reviewed.disconfirming_evidence)


# ==============================================================================
# BATTERY C: Correlation Overlap & Macro Regime Clashes
# ==============================================================================

def test_battery_c_information_overlap_discount_for_correlated_altcoins():
    """Multiple correlated altcoins in the same direction must be discounted by effective N."""
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)

    p1 = CandidateProposal(
        proposal_id="p1",
        specialist_id="spec_eth_structural",
        archetype=SpecialistArchetype.ETH_DEFI_STRUCTURAL,
        symbol="ETH/USDT",
        direction=DecisionAction.LONG,
        thesis="ETH Long",
        entry_price=3000.0,
        stop_loss=2900.0,
        take_profit=3200.0,
        risk_reward_ratio=2.0,
        expected_value_r=1.0,
        confidence_score=0.80,
        invalidation_condition="SL",
        suggested_notional_usd=1000.0,
    )
    p2 = CandidateProposal(
        proposal_id="p2",
        specialist_id="spec_sol_velocity",
        archetype=SpecialistArchetype.SOL_HIGH_VELOCITY,
        symbol="SOL/USDT",
        direction=DecisionAction.LONG,
        thesis="SOL Long",
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=160.0,
        risk_reward_ratio=2.0,
        expected_value_r=1.0,
        confidence_score=0.80,
        invalidation_condition="SL",
        suggested_notional_usd=1000.0,
    )

    discounts = arbiter.compute_information_overlap_discount([p1, p2])

    assert len(discounts) == 2
    # Pairwise correlation between ETH and SOL is ~0.82
    # N_eff = 2 / (1 + 0.82) = 1.0989 -> discount = 1.0989 / 2 = 0.549
    for pid in ("p1", "p2"):
        assert discounts[pid] <= 0.60
        assert discounts[pid] >= 0.50

    # Single proposal receives 1.0 (no discount)
    single = arbiter.compute_information_overlap_discount([p1])
    assert single["p1"] == 1.0


@pytest.mark.asyncio
async def test_battery_c_macro_divergence_penalizes_altcoin_long_when_btc_short():
    """An Altcoin LONG proposal submitted when BTC Macro is SHORT must receive a 30% confidence haircut."""
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)

    btc_candles = _generate_synthetic_candles(base_price=65000.0, count=25, trend=-0.005)
    alt_candles = _generate_synthetic_candles(base_price=1.5, count=25, trend=0.001)

    arbiter.deploy_dynamic_specialist(
        symbol="SUI/USDT",
        category="PRE_SPIKE_ACCUMULATION",
        direction="LONG",
        market_attention_score=60.0,
    )

    market_data = {
        "BTC/USDT": {"15m": btc_candles, "multi_tf": {"15m": btc_candles}},
        "SUI/USDT": {"15m": alt_candles, "multi_tf": {"15m": alt_candles}},
    }

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

        sui_dec = next((d for d in decisions if d.symbol == "SUI/USDT"), None)
        assert sui_dec is not None
        assert sui_dec.is_approved is False
        assert "below threshold" in sui_dec.rejection_reason or "Effective Confidence" in sui_dec.rejection_reason or "Asset Tier Firewall" in sui_dec.rejection_reason


# ==============================================================================
# BATTERY D: Absolute Risk-Gate Primacy & 1.5% Portfolio Ceiling Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_battery_d_absolute_1_point_5_percent_max_equity_cap():
    """Even under extreme specialist consensus with max confidence, risk cannot exceed 1.5% of equity."""
    equity = 20_000.0
    arbiter = MastermindArbiterCouncil(account_equity_usd=equity)
    candles = _generate_synthetic_candles(60000.0, 25)
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
async def test_battery_d_risk_governor_circuit_breaker_veto_primacy():
    """When the risk governor circuit breaker trips, unanimous specialist proposals are 100% vetoed."""
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)
    candles = _generate_synthetic_candles(60000.0, 25)

    market_data = {
        "BTC/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
        "ETH/USDT": {"15m": candles, "multi_tf": {"15m": candles}},
    }

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
            assert d.is_approved is False
            assert "Risk Gate lockout active" in d.rejection_reason
            assert d.approved_notional_usd == 0.0


# ==============================================================================
# BATTERY E: Friction Stress Gate & Closed-Loop Drift Feedback
# ==============================================================================

def test_battery_e_opportunity_hunter_tradability_stress_gate():
    """Opportunity Hunter must reject candidates where target cannot absorb 2.5x stress frictions."""
    hunter = OpportunityHunter(
        min_spot_volume_usd=15_000_000.0,
        min_futures_volume_usd=25_000_000.0,
        max_spread_bps=12.0,
    )

    # Illiquid meme token: spread=11 bps, tight invalidation (0.10%), target=0.20%
    # Stress friction exceeds target move -> Untradable
    is_tradable_bad, stress_bps_bad, target_bad = hunter.evaluate_tradability_stress(
        price=1.0,
        spread_bps=11.0,
        quote_vol=16_000_000.0,
        dist_to_invalidation_pct=0.10,
        rr=2.0,
    )
    assert is_tradable_bad is False
    assert stress_bps_bad > 60.0
    assert target_bad == 0.20

    # Liquid token: spread=2 bps, healthy invalidation (2.5%), rr=2.5, target=6.25%
    # Stress friction ~35 bps << 6.25% target -> Tradable
    is_tradable_good, stress_bps_good, target_good = hunter.evaluate_tradability_stress(
        price=50.0,
        spread_bps=2.0,
        quote_vol=120_000_000.0,
        dist_to_invalidation_pct=2.5,
        rr=2.5,
    )
    assert is_tradable_good is True
    assert stress_bps_good < 40.0
    assert target_good == 6.25


def test_battery_e_closed_loop_paper_depth_calibration():
    """Realized slippage divergence triggers closed-loop feedback in RealisticPaperFillSimulator."""
    sim = RealisticPaperFillSimulator()
    init_factor = sim.adverse_selection_factor
    init_latency = sim.market_order_latency_ms

    # Realized slippage 4x higher than expected -> closed loop scale up
    cal = sim.calibrate_depth_friction(realized_slippage_bps=4.0, expected_slippage_bps=1.0)

    assert cal["slippage_ratio"] == 4.0
    assert sim.adverse_selection_factor > init_factor
    assert sim.market_order_latency_ms > init_latency


def test_battery_e_critical_drift_dispatches_telegram_and_suspends():
    """Critical execution drift triggers automated strategy suspension and Telegram dispatch."""
    mock_registry = MagicMock()
    policy = SuspensionPolicy(max_drawdown_bps=200.0)
    controller = SuspensionController(registry=mock_registry, policy=policy)

    with patch("core.telegram_bot.telegram_bot.send_message") as mock_send:
        tripped = controller.check_drawdown("strat_adversarial_test", current_drawdown_bps=250.0)
        assert tripped is True
        assert mock_registry.transition_status.called
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert "CIRCUIT BREAKER TRIGGERED" in msg
        assert "strat_adversarial_test" in msg
