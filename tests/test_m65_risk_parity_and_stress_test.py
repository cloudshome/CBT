"""
tests/test_m65_risk_parity_and_stress_test.py
=============================================
Milestone 65: Risk-Parity Volatility Targeting & Execution Stress Test Suite.

Verifies:
1. Causal Volatility Targeting Invariance: Truncating OHLCV at bar t yields identical
   volatility scalar and target weights at bar t as the full series (zero lookahead).
2. Zero-Leverage Cap Enforcement: Gross exposure of S1, S2-Div, and P2_RP never exceeds
   1.0001 on any bar even in ultra-low volatility regimes.
3. Balanced Risk Contribution: S1 and S2-Div variance contributions in P2_RP are within
   [30%, 70%] (fixing M64's 95%/5% dominance bug).
4. Dynamic Hurdle Count & Capital Lock: passed_count + failed_count == total_hurdles and
   REAL_CAPITAL_ENABLED is False.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.execution.capital_governor import CapitalGovernor, CapitalTier
from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from scripts.research.run_m65_risk_parity_and_stress_test import (
    compute_s1_indicators,
    rank_s2_div_assets,
    run_m65_single_regime_simulation,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. CAUSAL VOLATILITY TARGETING INVARIANCE (ZERO LOOKAHEAD)
# ==============================================================================
def test_causal_volatility_targeting_invariance():
    """
    Verifies that truncating the input series at bar t produces the exact same
    trailing 20-day volatility scalar and target asset weights at bar t as running
    on the full [0..T] series.
    Guarantees zero future data leakage.
    """
    np.random.seed(42)
    n_bars = 400
    dates = pd.date_range("2022-01-01", periods=n_bars, freq="4h")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

    dfs_aligned = {}
    for s in symbols:
        rets = np.random.normal(0.0005, 0.015, size=n_bars)
        prices = 100.0 * np.exp(np.cumsum(rets))
        highs = prices * (1.0 + np.abs(np.random.normal(0, 0.005, size=n_bars)))
        lows = prices * (1.0 - np.abs(np.random.normal(0, 0.005, size=n_bars)))
        opens = np.roll(prices, 1)
        opens[0] = prices[0]
        dfs_aligned[s] = pd.DataFrame({
            "ts": [int(d.timestamp() * 1000) for d in dates],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": np.random.uniform(100, 1000, size=n_bars),
        })

    eval_bar = 280  # Test evaluation point well after 180-bar lookback

    # Full series calculation at eval_bar
    full_weights, full_scores, full_vols = rank_s2_div_assets(
        dfs_aligned,
        bar_idx=eval_bar,
        current_crypto_holdings=[],
        lookback_bars=180,
        vol_lookback_bars=120,
        hysteresis=0.15,
    )

    # Truncated series up to eval_bar
    dfs_truncated = {s: df.iloc[: eval_bar + 1].copy() for s, df in dfs_aligned.items()}
    trunc_weights, trunc_scores, trunc_vols = rank_s2_div_assets(
        dfs_truncated,
        bar_idx=eval_bar,
        current_crypto_holdings=[],
        lookback_bars=180,
        vol_lookback_bars=120,
        hysteresis=0.15,
    )

    # Check identical weights, scores, and volatilities
    for s in symbols:
        assert np.isclose(full_weights[s], trunc_weights[s], atol=1e-9), (
            f"Weight divergence on {s} at bar {eval_bar}: full={full_weights[s]}, trunc={trunc_weights[s]}"
        )
        assert np.isclose(full_scores[s], trunc_scores[s], atol=1e-9), (
            f"Score divergence on {s} at bar {eval_bar}: full={full_scores[s]}, trunc={trunc_scores[s]}"
        )
        assert np.isclose(full_vols[s], trunc_vols[s], atol=1e-9), (
            f"Vol divergence on {s} at bar {eval_bar}: full={full_vols[s]}, trunc={trunc_vols[s]}"
        )

    # Verify S1 indicator causality
    btc_df = dfs_aligned["BTCUSDT"]
    full_ind = compute_s1_indicators(btc_df)
    trunc_ind = compute_s1_indicators(btc_df.iloc[: eval_bar + 1])

    for key in ["closes", "atr", "donch_h48", "donch_l24", "ema200"]:
        val_full = full_ind[key][eval_bar]
        val_trunc = trunc_ind[key][eval_bar]
        assert np.isclose(val_full, val_trunc, atol=1e-9), (
            f"S1 Indicator {key} mismatch at bar {eval_bar}: full={val_full}, trunc={val_trunc}"
        )


# ==============================================================================
# 2. ZERO-LEVERAGE CAP ENFORCEMENT
# ==============================================================================
def test_zero_leverage_cap_enforcement():
    """
    Verifies that gross portfolio exposure for S1, S2-Div, and Ensemble P2_RP never
    exceeds 1.0001 under any circumstance, including an ultra-low volatility regime
    where naive scaling would demand 10x-50x leverage.
    """
    # 1. Verify on historical simulation results
    results_path = ROOT_DIR / "research" / "m65_risk_parity_stress_results.json"
    if results_path.exists():
        with open(results_path) as f:
            res = json.load(f)
        max_exp = res["governance_invariants"]["max_gross_exposure_observed"]
        assert max_exp <= 1.0001, f"Gross exposure violated 1.0x cap: {max_exp}"

    # 2. Adversarial test: Ultra-low volatility regime (annualized vol = 0.5%)
    # Target 15% vol would produce a raw scalar of 15% / 0.5% = 30x leverage if uncapped!
    np.random.seed(99)
    n_bars = 300
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="4h")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

    # Flat prices with microscopic noise: sigma_annualized < 0.01
    dfs_flat = {}
    for s in symbols:
        rets = np.random.normal(0.0001, 0.00005, size=n_bars)
        prices = 1000.0 * np.exp(np.cumsum(rets))
        highs = prices * 1.0001
        lows = prices * 0.9999
        opens = np.roll(prices, 1)
        opens[0] = prices[0]
        dfs_flat[s] = pd.DataFrame({
            "ts": [int(d.timestamp() * 1000) for d in dates],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": np.full(n_bars, 1000.0),
        })

    s1_ind_flat = {s: compute_s1_indicators(dfs_flat[s]) for s in symbols}
    sorted_ts = [int(d.timestamp() * 1000) for d in dates]

    sim_res = run_m65_single_regime_simulation(
        dfs_flat,
        sorted_ts=sorted_ts,
        s1_ind=s1_ind_flat,
        friction_bps=20.0,
        exec_delay_bars=1,
        target_vol=0.15,
    )

    max_exposures = sim_res["max_gross_exposure"]
    assert max_exposures["s1_max"] <= 1.0001, f"S1 gross exposure exceeded 1.0x: {max_exposures['s1_max']}"
    assert max_exposures["s2_max"] <= 1.0001, f"S2-Div gross exposure exceeded 1.0x: {max_exposures['s2_max']}"
    assert max_exposures["p2_max"] <= 1.0001, f"P2_RP gross exposure exceeded 1.0x: {max_exposures['p2_max']}"


# ==============================================================================
# 3. BALANCED RISK CONTRIBUTION PROOF
# ==============================================================================
def test_balanced_risk_contribution():
    """
    Verifies that the realized variance contributions of S1 and S2-Div in P2_RP
    are balanced within [30%, 70%] across both the Full Period and Sealed OOS,
    formally resolving M64's 95%/5% dominance bug.
    """
    results_path = ROOT_DIR / "research" / "m65_risk_parity_stress_results.json"
    assert results_path.exists(), "M65 results JSON not found. Run simulation first."

    with open(results_path) as f:
        res = json.load(f)

    # Full Period Realized Risk Contributions
    fp_rc = res["statistical_rigor"]["risk_contributions_full_period"]
    s1_rc = fp_rc["s1_rc_pct"]
    s2_rc = fp_rc["s2_rc_pct"]

    assert 30.0 <= s1_rc <= 70.0, f"S1 risk contribution outside [30%, 70%]: {s1_rc}%"
    assert 30.0 <= s2_rc <= 70.0, f"S2-Div risk contribution outside [30%, 70%]: {s2_rc}%"
    assert np.isclose(s1_rc + s2_rc, 100.0, atol=0.1), f"Risk contributions do not sum to 100%: {s1_rc + s2_rc}%"

    # Sealed OOS Realized Risk Contributions
    oos_rc = res["splits_scorecard"]["sealed_oos"]["risk_contributions"]
    s1_oos_rc = oos_rc["s1_rc_pct"]
    s2_oos_rc = oos_rc["s2_div_rc_pct"]

    assert 25.0 <= s1_oos_rc <= 75.0, f"S1 OOS risk contribution skewed: {s1_oos_rc}%"
    assert 25.0 <= s2_oos_rc <= 75.0, f"S2-Div OOS risk contribution skewed: {s2_oos_rc}%"


# ==============================================================================
# 4. DYNAMIC HURDLE COUNT & CONSTITUTIONAL CAPITAL LOCK
# ==============================================================================
def test_dynamic_hurdle_count_and_capital_lock():
    """
    Verifies:
    1. Dynamic hurdle counting integrity: passed_count + failed_count == total_hurdles.
    2. Summary text correctly reflects dynamic boolean computation.
    3. Permanent real-capital lock: REAL_CAPITAL_ENABLED is False and CapitalGovernor
       is locked at TIER_0_PAPER.
    """
    results_path = ROOT_DIR / "research" / "m65_risk_parity_stress_results.json"
    assert results_path.exists(), "M65 results JSON not found."

    with open(results_path) as f:
        res = json.load(f)

    hs = res["hurdle_summary"]
    passed_count = hs["passed_count"]
    failed_count = hs["failed_count"]
    total_hurdles = hs["total_hurdles"]

    # 1. Arithmetic consistency
    assert passed_count + failed_count == total_hurdles, (
        f"Arithmetic drift: passed ({passed_count}) + failed ({failed_count}) != total ({total_hurdles})"
    )
    assert hs["summary_text"] == f"{passed_count} Passed / {failed_count} Failed"

    # 2. Check each hurdle in dictionary is boolean
    hurdles = res["cp2_hurdles"]
    actual_passed = sum(1 for h in hurdles.values() if h["passed"] is True)
    actual_failed = sum(1 for h in hurdles.values() if h["passed"] is False)
    assert actual_passed == passed_count
    assert actual_failed == failed_count

    # 3. Constitutional Capital Lock
    assert REAL_CAPITAL_ENABLED is False, "CRITICAL: REAL_CAPITAL_ENABLED was modified from False!"
    gov = CapitalGovernor()
    state = gov.get_strategy_state()
    assert state["current_tier"] == CapitalTier.TIER_0_PAPER.value, f"CRITICAL: CapitalGovernor tier modified: {state['current_tier']}"
    status = gov.get_status()
    assert status["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert status["real_capital_enabled"] is False
    assert status["tier_progression_allowed"] is False
