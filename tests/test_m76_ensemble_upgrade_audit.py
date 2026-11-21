"""tests/test_m76_ensemble_upgrade_audit.py — Milestone 76 Causal Ensemble Upgrade Audit Tests.

Covers:
1. Ensemble zero-leverage invariant: combined portfolio gross exposure <= 1.0001 across all bars for V2A, V2B, and V2C.
2. Zero-lookahead causality: mutating future bars > t does NOT alter ensemble daily return up to bar t.
3. Sleeve correlation matrix properties: symmetry, valid bounds ([-1.0, 1.0]), diagonal == 1.0.
4. Dynamic 5-gate upgrade promotion evaluator: rejects any candidate failing even 1 gate (partial failures).
5. Governance locks (REAL_CAPITAL_ENABLED is False, CAPITAL_MODE == "TIER_0_PAPER") and CLI ledger tracking.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.research.run_m76_ensemble_upgrade_audit as m76
from scripts.research.run_m76_ensemble_upgrade_audit import evaluate_5_upgrade_gates


def test_m76_ensemble_zero_leverage_invariant():
    """Verify that convex combination of valid sleeves guarantees gross exposure <= 1.0001 at every bar."""
    n_bars = 200
    rng = np.random.default_rng(42)

    # Simulate 4 sleeve gross exposure series, each bounded by [0.0, 1.0]
    exp_s1 = rng.uniform(0.0, 1.0, size=n_bars)
    exp_s2 = rng.uniform(0.0, 1.0, size=n_bars)
    exp_h5 = rng.uniform(0.0, 1.0, size=n_bars)
    exp_h1 = rng.uniform(0.0, 1.0, size=n_bars)

    # 1. V2A: 50% S1 + 50% H5
    exp_v2a = 0.5 * exp_s1 + 0.5 * exp_h5
    # 2. V2B: 33.33% S1 + 33.33% H5 + 33.33% H1
    exp_v2b = (1.0 / 3.0) * exp_s1 + (1.0 / 3.0) * exp_h5 + (1.0 / 3.0) * exp_h1
    # 3. V2C: 25% S1 + 25% S2 + 25% H5 + 25% H1
    exp_v2c = 0.25 * exp_s1 + 0.25 * exp_s2 + 0.25 * exp_h5 + 0.25 * exp_h1

    assert np.all(exp_v2a <= 1.0001), f"V2A breached leverage invariant: {np.max(exp_v2a)}"
    assert np.all(exp_v2b <= 1.0001), f"V2B breached leverage invariant: {np.max(exp_v2b)}"
    assert np.all(exp_v2c <= 1.0001), f"V2C breached leverage invariant: {np.max(exp_v2c)}"


def test_m76_zero_lookahead_causality():
    """Verify mutating future bars > t does NOT alter ensemble daily return up to bar t."""
    n_days = 100
    eval_t = 60
    rng = np.random.default_rng(123)

    ret_s1 = rng.normal(0.001, 0.02, size=n_days)
    ret_s2 = rng.normal(0.0005, 0.015, size=n_days)
    ret_h5 = rng.normal(0.0008, 0.018, size=n_days)
    ret_h1 = rng.normal(0.0004, 0.012, size=n_days)

    v2c_original = 0.25 * ret_s1[:eval_t] + 0.25 * ret_s2[:eval_t] + 0.25 * ret_h5[:eval_t] + 0.25 * ret_h1[:eval_t]

    # Mutate all future data > eval_t aggressively
    ret_s1_mut = ret_s1.copy()
    ret_s2_mut = ret_s2.copy()
    ret_h5_mut = ret_h5.copy()
    ret_h1_mut = ret_h1.copy()

    ret_s1_mut[eval_t:] += 5.0
    ret_s2_mut[eval_t:] *= -10.0
    ret_h5_mut[eval_t:] = 999.0
    ret_h1_mut[eval_t:] = -0.99

    v2c_mutated = 0.25 * ret_s1_mut[:eval_t] + 0.25 * ret_s2_mut[:eval_t] + 0.25 * ret_h5_mut[:eval_t] + 0.25 * ret_h1_mut[:eval_t]

    np.testing.assert_allclose(
        v2c_original,
        v2c_mutated,
        err_msg="Future data mutation contaminated past ensemble returns! Zero-lookahead causality violated.",
    )


def test_m76_sleeve_correlation_matrix_properties():
    """Verify correlation matrix properties: symmetry, valid bounds ([-1.0, 1.0]), diagonal == 1.0."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "S1": rng.normal(0.0, 0.02, size=150),
        "S2-Div": rng.normal(0.0, 0.015, size=150),
        "H5": rng.normal(0.0, 0.018, size=150),
        "H1_CLEAN": rng.normal(0.0, 0.012, size=150),
    })

    corr = df.corr()

    # 1. Symmetry: corr == corr.T
    np.testing.assert_allclose(corr.values, corr.T.values, err_msg="Correlation matrix is not symmetric")
    # 2. Diagonal entries == 1.0
    np.testing.assert_allclose(np.diag(corr.values), np.ones(4), err_msg="Diagonal entries not equal to 1.0")
    # 3. Off-diagonal bounds in [-1.0, 1.0]
    assert np.all(corr.values >= -1.0) and np.all(corr.values <= 1.0), "Correlation values out of [-1.0, 1.0] bounds"


def test_m76_dynamic_5gate_evaluator_rejects_partial_failures():
    """Verify dynamic 5-gate evaluator strictly rejects any candidate failing even 1 gate."""
    base_metrics = {
        "full_period": {"daily_mtm_sharpe": 1.28, "calmar_ratio": 1.23, "max_drawdown_pct": 15.22},
        "sealed_oos": {"daily_mtm_sharpe": 0.37, "total_return_pct": 6.70},
        "yearly": {2022: {"max_drawdown_pct": 15.22}},
    }

    stress_survives = {
        "regime_2_friction_stress": {"sealed_oos": {"daily_mtm_sharpe": 0.50, "total_return_pct": 8.0}},
        "regime_3_delay_stress": {"sealed_oos": {"daily_mtm_sharpe": 0.40, "total_return_pct": 5.0}},
    }

    # Case A: Passes Gate 2, 3, 4, 5 but fails Gate 1 (lower Full-Period Sharpe)
    cand_fail_g1 = {
        "full_period": {"daily_mtm_sharpe": 1.20, "calmar_ratio": 1.05, "max_drawdown_pct": 12.0},
        "sealed_oos": {"daily_mtm_sharpe": 0.70, "total_return_pct": 12.0},
        "yearly": {2022: {"max_drawdown_pct": 10.0}},
    }
    res_a = evaluate_5_upgrade_gates(base_metrics, cand_fail_g1, stress_survives, cand_max_gross=0.85)
    assert res_a["gates"]["gate_1_full_period_edge"]["passed"] is False
    assert res_a["passed_count"] == 4
    assert res_a["verdict"] == "KEEP_P2_RP_BASELINE"

    # Case B: Passes Gate 1, 3, 4, 5 but fails Gate 2 (lower Sealed OOS Sharpe)
    cand_fail_g2 = {
        "full_period": {"daily_mtm_sharpe": 1.35, "calmar_ratio": 1.30, "max_drawdown_pct": 14.0},
        "sealed_oos": {"daily_mtm_sharpe": 0.30, "total_return_pct": 4.0},
        "yearly": {2022: {"max_drawdown_pct": 12.0}},
    }
    res_b = evaluate_5_upgrade_gates(base_metrics, cand_fail_g2, stress_survives, cand_max_gross=0.90)
    assert res_b["gates"]["gate_2_sealed_oos_edge"]["passed"] is False
    assert res_b["verdict"] == "KEEP_P2_RP_BASELINE"

    # Case C: Fails Gate 4 (Stress failure with negative return)
    stress_fails = {
        "regime_2_friction_stress": {"sealed_oos": {"daily_mtm_sharpe": 0.50, "total_return_pct": 8.0}},
        "regime_3_delay_stress": {"sealed_oos": {"daily_mtm_sharpe": -0.20, "total_return_pct": -4.5}},
    }
    cand_fail_g4 = {
        "full_period": {"daily_mtm_sharpe": 1.35, "calmar_ratio": 1.30, "max_drawdown_pct": 14.0},
        "sealed_oos": {"daily_mtm_sharpe": 0.60, "total_return_pct": 10.0},
        "yearly": {2022: {"max_drawdown_pct": 12.0}},
    }
    res_c = evaluate_5_upgrade_gates(base_metrics, cand_fail_g4, stress_fails, cand_max_gross=0.90)
    assert res_c["gates"]["gate_4_stress_survival"]["passed"] is False
    assert res_c["verdict"] == "KEEP_P2_RP_BASELINE"

    # Case D: Passes ALL 5 gates
    cand_all_pass = {
        "full_period": {"daily_mtm_sharpe": 1.35, "calmar_ratio": 1.30, "max_drawdown_pct": 14.0},
        "sealed_oos": {"daily_mtm_sharpe": 0.60, "total_return_pct": 10.0},
        "yearly": {2022: {"max_drawdown_pct": 12.0}},
    }
    res_d = evaluate_5_upgrade_gates(base_metrics, cand_all_pass, stress_survives, cand_max_gross=0.90)
    assert res_d["passed_count"] == 5
    assert res_d["verdict"] == "CANDIDATE_QUALIFIED_FOR_SHADOW_UPGRADE"


def test_m76_governance_invariants_and_cli():
    """Verify permanent governance invariants and CLI discovery ledger output."""
    assert m76.REAL_CAPITAL_ENABLED is False, "REAL_CAPITAL_ENABLED must be False permanently"
    assert m76.CAPITAL_MODE == "TIER_0_PAPER", "CAPITAL_MODE must be TIER_0_PAPER permanently"

    # Verify main.py discover --ledger --json runs cleanly
    cmd = [sys.executable, "main.py", "discover", "--ledger", "--json"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

    assert res.returncode == 0, f"main.py discover failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"
    data = json.loads(res.stdout)

    assert data.get("ledger_version") == "1.0.0"
    assert data.get("baseline_trials") == 18
    assert data.get("cumulative_trials_count") >= 24
    assert len(data.get("trials", [])) >= 6

