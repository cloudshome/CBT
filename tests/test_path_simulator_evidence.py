"""
Evidence-grade regression tests for the tri-model path simulator.

The simulator used to substitute a random return series when it had fewer than
30 candles, and gave no sign of it in its output. Its model-agreement spread then
fed the uncertainty budget, so noise could report *low* uncertainty.

These tests pin the contract that replaced that behaviour:

1. A cone built from generated returns, or from synthetic / untagged candles, is
   graded FABRICATED.
2. A cone built from empirical candles is SIMULATED, and never better. Model output
   is not observation, so a simulation can never be tradeable-grade.
3. One contaminated bar contaminates the cone (weakest link).
4. A FABRICATED cone cannot lower the uncertainty budget.
"""

import numpy as np

from core.analogue_engine import AnalogueDistribution
from core.data_quality_gate import QualityCheckResult
from core.event_shock_engine import EventRiskState
from core.evidence_integrity import EvidenceGrade, stamp_records
from core.path_simulator import (
    MIN_CANDLES_FOR_OBSERVED_RETURNS,
    SimulationCone,
    TriModelPathSimulator,
)
from core.regime_transition import MarketRegime, RegimeClassificationResult, StructuralTransition
from core.uncertainty_engine import uncertainty_engine


def _candles(n: int, grade: EvidenceGrade | None = None) -> list[dict]:
    rng = np.random.default_rng(7)
    closes = 100.0 + np.cumsum(rng.normal(0.0, 0.4, n))
    records = [{"close": float(c)} for c in closes]
    if grade is not None:
        stamp_records(records, grade)
    return records


def _simulate(candles: list[dict]) -> SimulationCone:
    np.random.seed(11)
    sim = TriModelPathSimulator(num_paths=300, horizon_steps=12)
    price = candles[-1]["close"] if candles else 100.0
    return sim.simulate_paths(price, candles, price * 1.05, price * 0.97)


def test_too_few_candles_is_fabricated():
    for n in (0, 10, MIN_CANDLES_FOR_OBSERVED_RETURNS - 1):
        cone = _simulate(_candles(n, EvidenceGrade.EMPIRICAL))
        assert cone.evidence_grade == EvidenceGrade.FABRICATED.label
        assert cone.observed_return_count == 0


def test_untagged_candles_are_fabricated():
    """Untagged data is untrusted data: a provider that forgets to stamp gets no credit."""
    cone = _simulate(_candles(80))
    assert cone.evidence_grade == EvidenceGrade.FABRICATED.label
    assert cone.observed_return_count == 0


def test_synthetic_candles_are_fabricated():
    cone = _simulate(_candles(80, EvidenceGrade.FABRICATED))
    assert cone.evidence_grade == EvidenceGrade.FABRICATED.label


def test_empirical_candles_give_simulated_never_empirical():
    cone = _simulate(_candles(80, EvidenceGrade.EMPIRICAL))
    assert cone.evidence_grade == EvidenceGrade.SIMULATED.label
    assert cone.observed_return_count == 79
    assert not EvidenceGrade[cone.evidence_grade].is_tradeable


def test_one_fabricated_bar_contaminates_the_cone():
    candles = _candles(80, EvidenceGrade.EMPIRICAL)
    candles[40]["evidence_grade"] = EvidenceGrade.FABRICATED.label
    candles[40]["is_synthetic"] = 1
    assert _simulate(candles).evidence_grade == EvidenceGrade.FABRICATED.label


def test_hand_built_cone_defaults_to_simulated_not_empirical():
    cone = SimulationCone([1], [1.0], [1.0], [1.0], [1.0], [1.0], 0.5, 0.04, 0.5, 0.5, 0.5, 10)
    assert cone.evidence_grade == EvidenceGrade.SIMULATED.label


def _budget_inputs():
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
    reg = RegimeClassificationResult(
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
    ev = EventRiskState(
        is_event_risk_active=False,
        nearest_event=None,
        minutes_until_event=999.0,
        ev_hurdle_multiplier=1.0,
        position_size_multiplier=1.0,
        slippage_multiplier=1.0,
        mode_name="NORMAL",
        trading_lockout=False,
    )
    return dq, ad, reg, ev


def _cone(grade: EvidenceGrade) -> SimulationCone:
    return SimulationCone(
        steps=[1, 2, 3],
        p10_path=[77000, 76800, 76500],
        p25_path=[77200, 77100, 77000],
        p50_median_path=[77500, 77700, 78000],
        p75_path=[77800, 78200, 78600],
        p90_path=[78200, 78800, 79500],
        p_tp_before_sl=0.60,
        tp_sl_uncertainty_spread=0.04,  # models "agree": would normally mean low uncertainty
        model_a_p_win=0.61,
        model_b_p_win=0.59,
        model_c_p_win=0.60,
        simulated_paths_count=10000,
        evidence_grade=grade.label,
    )


def test_fabricated_cone_cannot_lower_the_uncertainty_budget():
    dq, ad, reg, ev = _budget_inputs()
    honest = uncertainty_engine.compute_budget(dq, ad, _cone(EvidenceGrade.SIMULATED), reg, ev)
    fake = uncertainty_engine.compute_budget(dq, ad, _cone(EvidenceGrade.FABRICATED), reg, ev)

    assert honest.model_disagreement_entropy < 0.2
    assert fake.model_disagreement_entropy == 1.0
    assert fake.composite_uncertainty_u > honest.composite_uncertainty_u
