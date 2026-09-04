"""
Tests for Layer 7, 8, 9: Net EV Engine, Conservative Kelly, and Adversarial Debate Council.
"""

from core.conservative_kelly import conservative_kelly
from core.data_streamer import data_streamer
from core.debate_committee import debate_committee
from core.ev_engine import ev_engine
from core.market_state import market_state_compiler
from core.portfolio_risk_matrix import portfolio_risk_matrix
from core.uncertainty_engine import UncertaintyBudget


def test_ev_engine_hurdle_rule():
    """Verify master rule: Net EV <= +0.25R forces NO_TRADE."""
    # Create low probability scenario where EV < +0.25R
    u_budget = UncertaintyBudget(
        composite_uncertainty_u=0.45,
        data_quality_uncertainty=0.10,
        analogue_sample_uncertainty=0.15,
        model_disagreement_entropy=0.10,
        regime_transition_uncertainty=0.10,
        event_shock_uncertainty=0.0,
        penalty_factor=0.55,
        uncertainty_level="MODERATE",
    )

    ev_low = ev_engine.calculate_net_ev(
        entry_price=88500.0,
        take_profit_price=89500.0,
        stop_loss_price=88000.0,
        calibrated_win_prob=0.42,  # Low probability
        uncertainty=u_budget,
    )

    assert ev_low.net_ev_r < 0.25
    assert not ev_low.is_tradable
    assert ev_low.decision_verdict == "DECISION_NO_TRADE"


def test_conservative_kelly_multi_factor_discount():
    """Verify Kelly fraction is discounted by uncertainty and capped at 1.5% max risk."""
    u_budget = UncertaintyBudget(
        composite_uncertainty_u=0.20,
        data_quality_uncertainty=0.0,
        analogue_sample_uncertainty=0.05,
        model_disagreement_entropy=0.05,
        regime_transition_uncertainty=0.10,
        event_shock_uncertainty=0.0,
        penalty_factor=0.80,
        uncertainty_level="LOW",
    )
    ev_high = ev_engine.calculate_net_ev(
        entry_price=88500.0,
        take_profit_price=92000.0,
        stop_loss_price=87000.0,
        calibrated_win_prob=0.68,
        uncertainty=u_budget,
    )

    alloc = conservative_kelly.calculate_allocation(
        account_equity=100000.0,
        entry_price=88500.0,
        stop_loss_price=87000.0,
        ev_result=ev_high,
        uncertainty=u_budget,
    )

    assert alloc.conservative_fraction <= 0.015  # Max 1.5% ceiling
    assert alloc.is_allocated
    assert alloc.allocated_risk_usd <= 1500.0


def test_adversarial_council_voting_and_skeptic_veto():
    """Verify Bull, Bear, and Skeptic council with default NO_TRADE bias."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=50)
    state = market_state_compiler.compile_state("BTC/USDT", candles_by_tf={"15m": candles})

    u_budget = UncertaintyBudget(
        composite_uncertainty_u=0.65,
        data_quality_uncertainty=0.2,
        analogue_sample_uncertainty=0.2,
        model_disagreement_entropy=0.15,
        regime_transition_uncertainty=0.1,
        event_shock_uncertainty=0.0,
        penalty_factor=0.35,
        uncertainty_level="ELEVATED",
    )
    ev_sub = ev_engine.calculate_net_ev(88500.0, 89500.0, 88000.0, 0.50, u_budget)

    decision = debate_committee.convene_council("BTC/USDT", state, ev_sub, u_budget)
    assert decision.final_decision == "NO_TRADE"
    assert decision.skeptic_argument.stance == "NO_TRADE"


def test_portfolio_heat_cap_ceiling():
    """Verify total portfolio heat cannot exceed 6.0%."""
    matrix = portfolio_risk_matrix.evaluate_portfolio_heat(
        account_equity=100000.0,
        open_positions=[
            {"entry_price": 88000, "stop_loss": 86500, "size": 1.0},  # risk $1500
            {"entry_price": 3000, "stop_loss": 2880, "size": 10.0},  # risk $1200
            {"entry_price": 2680, "stop_loss": 2670, "size": 100.0},  # risk $1000
        ],
    )
    assert round(matrix.total_open_risk_pct * 100, 1) == 3.7
    assert not matrix.is_heat_exceeded
    assert matrix.can_open_new_position
