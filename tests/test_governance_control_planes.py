"""
Unit Test Suite for the 4 Cross-Cutting Governance Control Planes:
1. Research Firewall & Experiment Registry (core/research_firewall.py)
2. Model Ensemble Governor (core/model_governor.py)
3. Strategy Selection-Bias Guard (core/strategy_selection_guard.py)
4. Meta-Uncertainty Range Honesty (core/uncertainty_engine.py)
"""

import pytest

from core.analogue_engine import AnalogueDistribution
from core.data_quality_gate import QualityCheckResult
from core.event_shock_engine import EventRiskState
from core.model_governor import model_ensemble_governor
from core.path_simulator import SimulationCone
from core.regime_transition import MarketRegime, RegimeClassificationResult, StructuralTransition
from core.research_firewall import (
    ResearchFirewallViolation,
    research_firewall,
)
from core.strategy_selection_guard import strategy_selection_guard
from core.uncertainty_engine import uncertainty_engine


def test_research_firewall_lifecycle():
    """Verify Research Firewall enforces lock before OOS evaluation and caps trials."""
    exp = research_firewall.register_experiment(
        hypothesis_name="SMC_FVG_Reversion_Alpha",
        asset="BTCUSDT",
        parameters={"fvg_threshold_bps": 8.0, "stop_atr_mult": 1.5},
        feature_set=["fvg_size", "cvd_delta", "mvrv_z"],
        train_sharpe=2.45,
        validation_sharpe=1.85,
    )
    assert exp.experiment_id.startswith("EXP_")
    assert not exp.is_parameters_locked

    # 1. Attempting OOS access BEFORE lock must raise ResearchFirewallViolation
    with pytest.raises(ResearchFirewallViolation) as exc_info:
        research_firewall.request_oos_clearance(exp.experiment_id)
    assert "must be locked" in str(exc_info.value)

    # 2. Lock parameters
    research_firewall.lock_experiment(exp.experiment_id)
    assert exp.is_parameters_locked

    # 3. Grant OOS access up to limit (3 times)
    assert research_firewall.request_oos_clearance(exp.experiment_id) is True
    assert research_firewall.request_oos_clearance(exp.experiment_id) is True
    assert research_firewall.request_oos_clearance(exp.experiment_id) is True

    # 4. 4th attempt must be BLOCKED due to budget exhaustion
    with pytest.raises(ResearchFirewallViolation) as exc_info_exhaust:
        research_firewall.request_oos_clearance(exp.experiment_id)
    assert "exhausted its OOS evaluation budget" in str(exc_info_exhaust.value)


def test_model_ensemble_governor_regime_weighting():
    """Verify Model Governor dynamically weights models by regime and computes disagreement entropy."""
    # Scenario: Trending Bull market
    forecast = model_ensemble_governor.synthesize_forecast(
        active_regime="TRENDING_BULL",
        analogue_p_win=0.68,
        scenario_p_win=0.62,
        bootstrap_p_win=0.55,
        orderflow_p_win=0.74,
        smc_p_win=0.70,
    )
    assert 0.60 <= forecast.consensus_p_win <= 0.72
    assert forecast.p_min_range == 0.55
    assert forecast.p_max_range == 0.74
    assert forecast.is_consensus_clear is True
    assert (
        forecast.confidence_interval_95[0]
        < forecast.consensus_p_win
        < forecast.confidence_interval_95[1]
    )

    # Scenario: Severe Model Disagreement in High Volatility
    disagree_forecast = model_ensemble_governor.synthesize_forecast(
        active_regime="HIGH_VOLATILITY",
        analogue_p_win=0.85,
        scenario_p_win=0.25,
        bootstrap_p_win=0.50,
        orderflow_p_win=0.80,
        smc_p_win=0.20,
    )
    assert disagree_forecast.disagreement_entropy > 0.40
    assert disagree_forecast.is_consensus_clear is False


def test_strategy_selection_bias_guard():
    """Verify Deflated Sharpe Ratio penalizes multiple testing trial counts."""
    returns = [0.012, -0.005, 0.018, 0.004, -0.002, 0.015, -0.008, 0.020] * 10

    # 1. Single Trial (N = 1, Sharpe = 2.1) -> Passes easily
    rep_single = strategy_selection_guard.evaluate_strategy(
        strategy_id="STRAT_001",
        observed_returns=returns,
        annualized_sharpe=2.10,
        trials_count=1,
    )
    assert rep_single.is_statistically_significant is True
    assert rep_single.verdict == "PROMOTION_AUTHORIZED"

    # 2. Heavy Data Mining (N = 5,000 trials, Marginal Sharpe = 1.35) -> Rejected by Selection Guard
    rep_mined = strategy_selection_guard.evaluate_strategy(
        strategy_id="STRAT_MINED",
        observed_returns=returns,
        annualized_sharpe=1.35,
        trials_count=5000,
    )
    assert rep_mined.is_statistically_significant is False
    assert rep_mined.verdict == "SELECTION_BIAS_REJECTED"
    assert rep_mined.expected_max_null_sharpe > 1.35


def test_uncertainty_budget_probability_ranges():
    """Verify Meta-Uncertainty Budget emits honest probability intervals [P_low, P_high]."""
    dq = QualityCheckResult(
        is_valid=True,
        quality_score=0.98,
        reason="Nominal feed performance",
        metrics={"tick_jitter_ms": 12.0, "missing_bars_count": 0, "clock_drift_ms": 1.5},
    )
    ad = AnalogueDistribution(
        query_asset="BTCUSDT",
        k_samples_found=45,
        sample_adequacy_score=1.0,
        p_tp_hit=0.62,
        p_sl_hit=0.38,
        median_mae_pct=0.8,
        median_mfe_pct=2.4,
        expected_r_multiple=1.4,
        avg_bars_to_target=8.5,
        top_matches=[],
        uncertainty_penalty=0.05,
    )
    cone = SimulationCone(
        steps=[1, 2, 3],
        p10_path=[77000, 76800, 76500],
        p25_path=[77200, 77100, 77000],
        p50_median_path=[77500, 77700, 78000],
        p75_path=[77800, 78200, 78600],
        p90_path=[78200, 78800, 79500],
        p_tp_before_sl=0.60,
        tp_sl_uncertainty_spread=0.04,
        model_a_p_win=0.61,
        model_b_p_win=0.59,
        model_c_p_win=0.60,
        simulated_paths_count=10000,
    )
    reg_res = RegimeClassificationResult(
        current_regime=MarketRegime.TRENDING_BULL,
        active_transition=StructuralTransition.NONE,
        confidence=0.92,
        trend_strength=0.85,
        volatility_state="NORMAL",
        adx_value=32.0,
        atr_percentile=55.0,
        bb_squeeze=False,
        summary="Bullish trend formation",
    )
    event_st = EventRiskState(
        is_event_risk_active=False,
        nearest_event=None,
        minutes_until_event=999.0,
        ev_hurdle_multiplier=1.0,
        position_size_multiplier=1.0,
        slippage_multiplier=1.0,
        mode_name="NORMAL",
        trading_lockout=False,
    )

    budget = uncertainty_engine.compute_budget(dq, ad, cone, reg_res, event_st, base_p_win=0.62)
    assert budget.uncertainty_level == "LOW"
    assert "% - " in budget.p_range_string
    assert budget.composite_uncertainty_u < 0.25
