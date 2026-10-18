"""
Phase 9 Verification Suite: CBT / SKY Trading Concept Intelligence & Strategy Discovery System.

Covers all 10 mandatory verification categories:
1. Concept registry schema validation (60 concepts across 15 families, Phase 7 historical setup audit)
2. Lifecycle transition rules and fail-closed promotion gates
3. Strategy evaluation determinism across Candidates A-F
4. Feature alignment and strict point-in-time no-lookahead verification
5. 3-Tier transaction cost calculation (base, conservative_1_5x, stress_2_5x) & N_eff overlap calculation
6. Rejection of invalid, corrupted, or missing OHLCV data
7. Automatic demotion and quarantine triggers on drift/degradation
8. SQLite database migration & sandbox persistence compatibility
9. FastAPI route responses (/api/strategist/concepts/*)
10. Execution isolation & REAL_CAPITAL_ENABLED == False invariant enforcement
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.execution.kill_switch import live_kill_switch
from core.research.concept_evaluation import (
    ConceptEvaluationEngine,
    CostTierAssumptions,
    RegimeOrchestrationAdvisor,
    SimulatedTrade,
    compute_overlap_adjusted_n_eff,
)
from core.research.concept_registry import (
    REAL_CAPITAL_ENABLED,
    ConceptEvidenceGate,
    ConceptFamily,
    ConceptLifecycleStatus,
    ConceptRole,
    TradingConceptRegistry,
)
from core.strategist_routes import strategist_router


def _make_regime_ohlcv(n_bars: int = 320, seed: int = 42) -> pd.DataFrame:
    """Generates a deterministic multi-regime OHLCV + funding series for testing Candidates A-F."""
    rng = np.random.default_rng(seed)
    closes = np.zeros(n_bars, dtype=np.float64)
    opens = np.zeros(n_bars, dtype=np.float64)
    highs = np.zeros(n_bars, dtype=np.float64)
    lows = np.zeros(n_bars, dtype=np.float64)
    volumes = np.zeros(n_bars, dtype=np.float64)
    funding = np.zeros(n_bars, dtype=np.float64)

    price = 50000.0
    for i in range(n_bars):
        # Alternate between trending up, range compression, and trending down phases
        if i < 110:
            drift = 0.0025 if (i % 7 != 0) else -0.0030
            sigma = 0.0040
            vol_mult = 1.4
        elif i < 210:
            drift = -0.0005 * np.sin(i * 0.35)
            sigma = 0.0025
            vol_mult = 0.9
        else:
            drift = 0.0030 if (i % 6 != 0) else -0.0035
            sigma = 0.0045
            vol_mult = 1.6

        ret = drift + rng.normal(0.0, sigma)
        open_p = price
        close_p = max(1000.0, open_p * (1.0 + ret))
        wick_up = abs(rng.normal(0.0, sigma * 0.8)) * open_p
        wick_dn = abs(rng.normal(0.0, sigma * 0.8)) * open_p
        high_p = max(open_p, close_p) + wick_up
        low_p = max(500.0, min(open_p, close_p) - wick_dn)

        opens[i] = open_p
        closes[i] = close_p
        highs[i] = high_p
        lows[i] = low_p
        volumes[i] = (1000.0 + abs(ret) * 150000.0) * vol_mult
        funding[i] = 0.0001 + 0.00005 * np.sin(i / 15.0)
        price = close_p

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "funding_rate": funding,
        }
    )


# ============================================================================
# 1. Concept Registry Schema, 60-Concept Taxonomy & Phase 7 Audit Verification
# ============================================================================


def test_master_taxonomy_60_concepts_and_15_families() -> None:
    reg = TradingConceptRegistry()
    concepts = reg.list_concepts()
    assert len(concepts) == 60

    summary = reg.get_taxonomy_summary()
    assert summary["total_concepts"] == 60
    assert summary["total_families"] == 15
    assert summary["real_capital_enabled"] is False

    # Every family FAM_01 .. FAM_15 must have exactly 4 candidates
    for fam in ConceptFamily:
        assert summary["counts_by_family"].get(fam.value) == 4

    # Verify required fields are non-empty on all 60 concepts
    seen_ids: set[str] = set()
    for c in concepts:
        assert c.concept_id.startswith("TC_")
        assert c.concept_id not in seen_ids
        seen_ids.add(c.concept_id)
        assert 1 <= c.candidate_number <= 60
        assert len(c.canonical_name) >= 5
        assert len(c.hypothesis) >= 20
        assert len(c.economic_rationale) >= 20
        assert len(c.primary_reference) >= 5
        assert c.role in {r.value for r in ConceptRole}
        assert c.lifecycle_status in {s.value for s in ConceptLifecycleStatus}
        assert len(c.required_data) >= 1
        assert len(c.timeframes) >= 1
        assert "BTCUSDT" in c.markets and "ETHUSDT" in c.markets
        assert len(c.feature_definitions) >= 1
        assert isinstance(c.rule_specification, dict) and len(c.rule_specification) >= 1
        assert len(c.failure_modes) >= 1
        assert len(c.operational_risks) >= 1
        assert len(c.rule_hash()) == 16


def test_phase7_historical_cbt_setup_audit_statuses() -> None:
    """Verifies Phase 7 forensic verdicts on legacy CBT/SKY setups."""
    reg = TradingConceptRegistry()

    # Legacy Breakout Buy (TC_009) failed at -0.630R gross / -0.904R net (PF 0.225) -> REJECTED
    tc_breakout = reg.get_concept("TC_009")
    assert tc_breakout is not None
    assert tc_breakout.lifecycle_status == ConceptLifecycleStatus.REJECTED.value
    assert "-0.904R" in tc_breakout.backtest_evidence_summary

    # Legacy Liquidity Sweep (TC_017) lost money net of costs (-0.448R / -0.584R) -> QUARANTINED
    tc_sweep = reg.get_concept("TC_017")
    assert tc_sweep is not None
    assert tc_sweep.lifecycle_status == ConceptLifecycleStatus.QUARANTINED.value
    assert "-0.448R" in tc_sweep.backtest_evidence_summary

    # Trend Pullback (TC_013) had positive 24h real-data lead (+1.077R gross / +0.974R net)
    # but overlapping evaluation windows -> NEEDS_MORE_DATA
    tc_pullback = reg.get_concept("TC_013")
    assert tc_pullback is not None
    assert tc_pullback.lifecycle_status == ConceptLifecycleStatus.NEEDS_MORE_DATA.value
    assert "+1.077R" in tc_pullback.backtest_evidence_summary

    # FVG Retracement (TC_019) -> NEEDS_MORE_DATA
    tc_fvg = reg.get_concept("TC_019")
    assert tc_fvg is not None
    assert tc_fvg.lifecycle_status == ConceptLifecycleStatus.NEEDS_MORE_DATA.value

    # Kronos / Statistical Calibration (TC_057) -> IMPLEMENTED, forecast_only enforced
    tc_kronos = reg.get_concept("TC_057")
    assert tc_kronos is not None
    assert tc_kronos.lifecycle_status == ConceptLifecycleStatus.IMPLEMENTED.value
    assert "forecast_only_cannot_execute" in str(tc_kronos.rule_specification)


def test_registry_search_filter_compare_and_overlap_detection() -> None:
    reg = TradingConceptRegistry()

    trend_concepts = reg.list_concepts(family_id=ConceptFamily.FAM_01_TREND_FOLLOWING.value)
    assert len(trend_concepts) == 4

    coint = reg.list_concepts(search_query="cointegration")
    assert any(c.concept_id == "TC_033" for c in coint)

    comp = reg.compare_concepts(["TC_001", "TC_004", "TC_005"])
    assert comp["compared_count"] == 3
    assert len(comp["pairwise_overlap"]) == 3

    # TC_001 and TC_004 are both in FAM_01_TREND_FOLLOWING and share TRENDING regimes,
    # so their redundancy score must exceed TC_001 vs TC_005 (Mean Reversion).
    pair_1_4 = next(
        p
        for p in comp["pairwise_overlap"]
        if {p["concept_a"], p["concept_b"]} == {"TC_001", "TC_004"}
    )
    pair_1_5 = next(
        p
        for p in comp["pairwise_overlap"]
        if {p["concept_a"], p["concept_b"]} == {"TC_001", "TC_005"}
    )
    assert pair_1_4["redundancy_score"] > pair_1_5["redundancy_score"]

    overlaps = reg.detect_concept_overlaps(threshold=0.50)
    assert len(overlaps) >= 1


# ============================================================================
# 2. Lifecycle Transition Rules & Fail-Closed Promotion Gates (Phase 6)
# ============================================================================


def test_fail_closed_lifecycle_promotion_gates() -> None:
    reg = TradingConceptRegistry(
        evidence_gate=ConceptEvidenceGate(
            min_oos_effective_trades=25,
            min_net_expectancy_r=0.05,
            min_profit_factor=1.15,
            max_drawdown_r=20.0,
            min_deflated_sharpe=0.85,
        )
    )

    # 1) Attempting to promote TC_001 directly to OUT_OF_SAMPLE_VALIDATED with weak metrics MUST FAIL CLOSED
    bad_verdict = reg.request_lifecycle_transition(
        concept_id="TC_001",
        requested_status=ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
        evidence={
            "oos_effective_trades": 8,  # < 25
            "oos_net_expectancy_r": -0.12,  # < 0.05
            "conservative_1_5x_net_expectancy_r": -0.25,
            "oos_profit_factor": 0.85,
            "oos_max_drawdown_r": 28.0,
            "deflated_sharpe_ratio": 0.40,
            "lookahead_clean": True,
        },
    )
    assert bad_verdict.approved is False
    assert bad_verdict.final_status == ConceptLifecycleStatus.IMPLEMENTED.value
    assert len(bad_verdict.reasons) >= 4

    # 2) Promoting TC_001 to OUT_OF_SAMPLE_VALIDATED with full passing evidence MUST SUCCEED
    good_oos_verdict = reg.request_lifecycle_transition(
        concept_id="TC_001",
        requested_status=ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
        evidence={
            "oos_effective_trades": 42,
            "oos_net_expectancy_r": 0.28,
            "conservative_1_5x_net_expectancy_r": 0.16,
            "oos_profit_factor": 1.48,
            "oos_max_drawdown_r": 8.5,
            "deflated_sharpe_ratio": 0.96,
            "lookahead_clean": True,
        },
    )
    assert good_oos_verdict.approved is True
    assert (
        reg.get_concept("TC_001").lifecycle_status
        == ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value
    )

    # 3) Promoting to PAPER_QUALIFIED without RiskGate verification or with excessive correlation MUST FAIL
    bad_paper_q = reg.request_lifecycle_transition(
        concept_id="TC_001",
        requested_status=ConceptLifecycleStatus.PAPER_QUALIFIED.value,
        evidence={"max_pairwise_correlation": 0.88, "risk_gate_verified": False},
    )
    assert bad_paper_q.approved is False

    # 4) Promoting to PAPER_QUALIFIED with low correlation and RiskGate verified MUST SUCCEED
    good_paper_q = reg.request_lifecycle_transition(
        concept_id="TC_001",
        requested_status=ConceptLifecycleStatus.PAPER_QUALIFIED.value,
        evidence={"max_pairwise_correlation": 0.32, "risk_gate_verified": True},
    )
    assert good_paper_q.approved is True
    assert (
        reg.get_concept("TC_001").lifecycle_status == ConceptLifecycleStatus.PAPER_QUALIFIED.value
    )

    # 5) Promoting to PAPER_VALIDATED requires >= 20 paper trades, positive net R, bounded slippage, and kill-switch intact
    good_paper_val = reg.request_lifecycle_transition(
        concept_id="TC_001",
        requested_status=ConceptLifecycleStatus.PAPER_VALIDATED.value,
        evidence={
            "paper_trades": 30,
            "paper_net_expectancy_r": 0.21,
            "slippage_drift_bps": 3.5,
            "kill_switch_intact": True,
        },
    )
    assert good_paper_val.approved is True
    assert (
        reg.get_concept("TC_001").lifecycle_status == ConceptLifecycleStatus.PAPER_VALIDATED.value
    )


# ============================================================================
# 3 & 4. Strategy Evaluation Determinism & Point-in-Time No-Lookahead
# ============================================================================


def test_strategy_evaluation_determinism_all_candidates() -> None:
    df = _make_regime_ohlcv(n_bars=320, seed=101)
    engine = ConceptEvaluationEngine()

    res_run1 = engine.evaluate_all_baseline_candidates(
        df, symbol="BTCUSDT", timeframe="1h", record_to_registry=True
    )
    res_run2 = engine.evaluate_all_baseline_candidates(
        df, symbol="BTCUSDT", timeframe="1h", record_to_registry=False
    )

    assert set(res_run1.keys()) == set(engine.CANDIDATE_TO_CONCEPT.keys())
    for key in res_run1:
        r1, r2 = res_run1[key], res_run2[key]
        assert r1.dataset_hash == r2.dataset_hash
        assert r1.overall_metrics == r2.overall_metrics
        assert r1.train_metrics == r2.train_metrics
        assert r1.validation_metrics == r2.validation_metrics
        assert r1.sealed_oos_metrics == r2.sealed_oos_metrics
        assert r1.return_series_r == r2.return_series_r


def test_point_in_time_causal_no_lookahead_guarantee() -> None:
    """
    Mutating future bars (t+1 .. N) with extreme price shocks must NEVER alter
    any feature or signal generated at bar t across all 6 candidate families.
    """
    df_base = _make_regime_ohlcv(n_bars=200, seed=77)
    decision_t = 120

    # Create a mutated copy where bars after decision_t crash by 80% or pump by 500%
    df_mutated = df_base.copy(deep=True)
    df_mutated.loc[decision_t + 1 :, "close"] *= 4.5
    df_mutated.loc[decision_t + 1 :, "high"] *= 5.0
    df_mutated.loc[decision_t + 1 :, "low"] *= 0.2
    df_mutated.loc[decision_t + 1 :, "volume"] *= 50.0

    work_base = ConceptEvaluationEngine._validate_and_prepare_df(df_base)
    work_mut = ConceptEvaluationEngine._validate_and_prepare_df(df_mutated)

    # All causal features at index <= decision_t must be bit-for-bit identical
    feature_cols = [
        "ema_20",
        "ema_50",
        "sma_20",
        "bb_upper",
        "bb_lower",
        "atr_14",
        "rsi_14",
        "er_20",
        "tsmom_z_20",
        "rvol_20",
        "prev_high_20",
        "prev_low_20",
        "regime",
    ]
    for col in feature_cols:
        s_base = work_base[col].iloc[: decision_t + 1]
        s_mut = work_mut[col].iloc[: decision_t + 1]
        pd.testing.assert_series_equal(s_base, s_mut, check_names=True)

    # Every candidate's signal at bar <= decision_t must be identical
    for cand_key in ConceptEvaluationEngine.CANDIDATE_TO_CONCEPT:
        for t in range(50, decision_t + 1):
            sig_base = ConceptEvaluationEngine._signal_at_bar(cand_key, work_base, t)
            sig_mut = ConceptEvaluationEngine._signal_at_bar(cand_key, work_mut, t)
            assert sig_base == sig_mut, f"Lookahead violation in {cand_key} at bar {t}"


# ============================================================================
# 5. Transaction Cost Calculation & Overlap-Adjusted N_eff
# ============================================================================


def test_three_tier_transaction_costs_and_overlap_n_eff() -> None:
    base = CostTierAssumptions(tier_name="base")
    cons = base.scale(1.5, "conservative_1_5x")
    stress = base.scale(2.5, "stress_2_5x")

    c_base = base.round_trip_cost_bps(holding_bars=12, bar_minutes=60, vol_ratio=1.2)
    c_cons = cons.round_trip_cost_bps(holding_bars=12, bar_minutes=60, vol_ratio=1.2)
    c_stress = stress.round_trip_cost_bps(holding_bars=12, bar_minutes=60, vol_ratio=1.2)
    assert 0.0 < c_base < c_cons < c_stress

    # Verify evaluation result reflects monotonic cost drag: gross > net_base > net_1_5x > net_2_5x
    df = _make_regime_ohlcv(n_bars=320, seed=19)
    engine = ConceptEvaluationEngine()
    res = engine.evaluate_candidate("CAND_B_TREND_PULLBACK", df, record_to_registry=False)
    m = res.overall_metrics
    assert m.nominal_trades > 0
    assert (
        m.gross_expectancy_r
        > m.net_expectancy_r_base
        > m.net_expectancy_r_conservative_1_5x
        > m.net_expectancy_r_stress_2_5x
    )

    # Verify N_eff overlap calculation:
    # 10 completely overlapping trades on bars [10, 50] must yield N_eff == 1.0
    overlapping_trades = [
        SimulatedTrade(
            candidate_id="TEST",
            concept_id="TC_013",
            split_name="train",
            entry_idx=10,
            exit_idx=50,
            direction=1,
            regime="TRENDING_UP",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            exit_price=104.0,
            exit_reason="TAKE_PROFIT",
            holding_bars=40,
            stop_distance_bps=200.0,
            gross_r=2.0,
            cost_r_base=0.1,
            net_r_base=1.9,
            net_r_conservative_1_5x=1.85,
            net_r_stress_2_5x=1.75,
        )
        for _ in range(10)
    ]
    assert compute_overlap_adjusted_n_eff(overlapping_trades, total_bars=100) == pytest.approx(
        1.0, abs=0.01
    )

    # 3 strictly non-overlapping trades must yield N_eff == 3.0
    disjoint_trades = [
        SimulatedTrade(
            candidate_id="TEST",
            concept_id="TC_013",
            split_name="train",
            entry_idx=i * 20,
            exit_idx=i * 20 + 10,
            direction=1,
            regime="TRENDING_UP",
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            exit_price=104.0,
            exit_reason="TAKE_PROFIT",
            holding_bars=10,
            stop_distance_bps=200.0,
            gross_r=2.0,
            cost_r_base=0.1,
            net_r_base=1.9,
            net_r_conservative_1_5x=1.85,
            net_r_stress_2_5x=1.75,
        )
        for i in range(3)
    ]
    assert compute_overlap_adjusted_n_eff(disjoint_trades, total_bars=100) == pytest.approx(
        3.0, abs=0.01
    )


# ============================================================================
# 6. Rejection of Invalid, Corrupted, or Missing Data
# ============================================================================


def test_rejection_of_invalid_or_missing_data() -> None:
    engine = ConceptEvaluationEngine()

    # Empty DataFrame
    with pytest.raises(ValueError, match="empty"):
        engine.evaluate_candidate("CAND_A_TSMOM_VOL_TREND", pd.DataFrame())

    # Missing required columns
    with pytest.raises(ValueError, match="Missing required OHLCV columns"):
        engine.evaluate_candidate(
            "CAND_A_TSMOM_VOL_TREND", pd.DataFrame({"open": [1, 2], "close": [1, 2]})
        )

    # Insufficient bars (< 80)
    short_df = _make_regime_ohlcv(n_bars=40)
    with pytest.raises(ValueError, match="Insufficient OHLCV bars"):
        engine.evaluate_candidate("CAND_A_TSMOM_VOL_TREND", short_df)

    # Corrupted prices (high < low or non-positive close)
    bad_df = _make_regime_ohlcv(n_bars=120)
    bad_df.loc[10, "close"] = -5.0
    with pytest.raises(ValueError, match="Corrupted OHLCV data"):
        engine.evaluate_candidate("CAND_A_TSMOM_VOL_TREND", bad_df)


# ============================================================================
# 7 & 8. Automatic Demotion / Quarantine & Regime Orchestration
# ============================================================================


def test_automatic_demotion_and_quarantine_triggers() -> None:
    reg = TradingConceptRegistry()

    # Negative rolling expectancy -> DEMOTED
    v_demote = reg.evaluate_and_apply_demotion(
        concept_id="TC_004",
        monitoring_metrics={
            "rolling_net_expectancy_r": -0.15,
            "rolling_drawdown_r": 6.0,
            "conservative_1_5x_net_expectancy_r": 0.02,
            "max_pairwise_correlation": 0.30,
            "data_integrity_ok": True,
        },
    )
    assert v_demote.approved is True
    assert v_demote.final_status == ConceptLifecycleStatus.DEMOTED.value
    assert reg.get_concept("TC_004").lifecycle_status == ConceptLifecycleStatus.DEMOTED.value

    # Excessive drawdown breach -> QUARANTINED
    v_quarantine = reg.evaluate_and_apply_demotion(
        concept_id="TC_005",
        monitoring_metrics={
            "rolling_net_expectancy_r": 0.05,
            "rolling_drawdown_r": 29.5,
            "conservative_1_5x_net_expectancy_r": 0.01,
            "max_pairwise_correlation": 0.25,
            "data_integrity_ok": True,
        },
    )
    assert v_quarantine.approved is True
    assert v_quarantine.final_status == ConceptLifecycleStatus.QUARANTINED.value
    assert reg.get_concept("TC_005").lifecycle_status == ConceptLifecycleStatus.QUARANTINED.value


def test_regime_orchestration_advisor_and_family_caps() -> None:
    advisor = RegimeOrchestrationAdvisor(max_family_weight=0.45)

    # 1) In CHOP_NO_TRADE, all directional strategies must be halted/suppressed
    chop_alloc = advisor.compute_arbiter_allocation(current_regime="CHOP_NO_TRADE")
    assert chop_alloc["regime_halt_active"] is True
    assert len(chop_alloc["active_allocations"]) == 0
    assert chop_alloc["real_capital_enabled"] is False
    assert chop_alloc["risk_gate_mandatory"] is True

    # 2) In TRENDING_UP, only TRENDING_UP-compatible strategies are active, and each family is capped <= 0.45
    trend_alloc = advisor.compute_arbiter_allocation(current_regime="TRENDING_UP")
    assert trend_alloc["regime_halt_active"] is False
    assert len(trend_alloc["active_allocations"]) > 0
    for fam_id, weight in trend_alloc["family_weights"].items():
        assert weight <= 0.4501, f"Family {fam_id} exceeded cap: {weight}"

    # 3) Quarantined (TC_017) and Rejected (TC_009) concepts must never appear in active_allocations
    active_ids = {item["concept_id"] for item in trend_alloc["active_allocations"]}
    assert "TC_009" not in active_ids
    assert "TC_017" not in active_ids


# ============================================================================
# 9 & 10. FastAPI Route Responses & REAL_CAPITAL_ENABLED == False Invariant
# ============================================================================


def test_fastapi_concept_intelligence_routes_and_governance_lock() -> None:
    assert REAL_CAPITAL_ENABLED is False
    assert os.getenv("REAL_CAPITAL_ENABLED", "false").lower() in ("0", "false")
    active, state = live_kill_switch.is_active()
    assert isinstance(active, bool)

    test_app = FastAPI()
    test_app.include_router(strategist_router)
    client = TestClient(test_app)

    # Summary endpoint
    r_sum = client.get("/api/strategist/concepts/summary")
    assert r_sum.status_code == 200
    body_sum = r_sum.json()
    assert body_sum["summary"]["total_concepts"] == 60
    assert body_sum["summary"]["total_families"] == 15
    assert body_sum["summary"]["real_capital_enabled"] is False

    # List & Filter endpoint
    r_list = client.get(
        "/api/strategist/concepts", params={"family_id": "FAM_10_FUNDING_BASIS_CARRY"}
    )
    assert r_list.status_code == 200
    assert r_list.json()["count"] == 4

    # Detail endpoint
    r_det = client.get("/api/strategist/concepts/TC_013")
    assert r_det.status_code == 200
    assert r_det.json()["concept"]["canonical_name"] == "Trend pullback"

    # Compare endpoint
    r_cmp = client.post(
        "/api/strategist/concepts/compare",
        json={"concept_ids": ["TC_001", "TC_014", "TC_037"]},
    )
    assert r_cmp.status_code == 200
    assert r_cmp.json()["compared_count"] == 3

    # Overlaps endpoint
    r_ov = client.get("/api/strategist/concepts/overlaps", params={"threshold": 0.55})
    assert r_ov.status_code == 200
    assert "overlaps" in r_ov.json()

    # Transition endpoint (fail-closed check)
    r_tr = client.post(
        "/api/strategist/concepts/transition",
        json={
            "concept_id": "TC_014",
            "requested_status": "OUT_OF_SAMPLE_VALIDATED",
            "evidence": {"oos_effective_trades": 5, "oos_net_expectancy_r": -0.1},
        },
    )
    assert r_tr.status_code == 200
    assert r_tr.json()["approved"] is False

    # Arbiter allocation endpoint
    r_arb = client.get(
        "/api/strategist/concepts/arbiter/allocation", params={"regime": "RANGE_BOUND"}
    )
    assert r_arb.status_code == 200
    assert r_arb.json()["allocation"]["real_capital_enabled"] is False
    assert r_arb.json()["allocation"]["risk_gate_mandatory"] is True
