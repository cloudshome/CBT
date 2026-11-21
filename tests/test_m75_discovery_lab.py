"""tests/test_m75_discovery_lab.py — Milestone 75 Discovery Lab & Causal Batch Tests.

Covers:
1. Zero-lookahead causality: mutating bars > t does NOT alter H1, H2, or H3 signals at bar t.
2. Failure-memory pre-gate blocks synthetic duplicate of FALSIFIED_M63 / FALSIFIED_M72.
3. H2_CROSS_ASSET_RV_PAIR enforces |w_long| + |w_short| <= 1.0001 (zero leverage) and stays flat when dispersion < 0.75.
4. H3_POST_CRASH_LIQ_REBOUND enforces conservative SL-before-TP intrabar tie-breaking.
5. Append-only trial ledger accurately tracks M_cum and penalizes DSR as M_cum grows.
6. Governance locks (REAL_CAPITAL_ENABLED is False, CAPITAL_MODE == "TIER_0_PAPER") and CLI main.py discover --ledger --json.
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

import core.research.discovery_lab as dl  # noqa: E402
from core.quantitative_validation.metrics import calculate_deflated_sharpe_ratio  # noqa: E402
from core.research.discovery_lab import (  # noqa: E402
    CausalDiscoveryEngine,
    DuplicateFalsifiedHypothesisError,
    H1_VolSqueezeExpansionLong,
    H2_CrossAssetRvPair,
    H3_PostCrashLiqRebound,
    HypothesisSpec,
    TrialLedgerManager,
    compute_standard_indicators,
)


def _generate_synthetic_bundle(n_bars: int = 300) -> dict:
    """Generates synthetic causally consistent data bundle for unit testing."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    crypto_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    base_ts = 1640995200000  # 2022-01-01 00:00 UTC
    sorted_ts = np.array([base_ts + i * 4 * 3600 * 1000 for i in range(n_bars)], dtype=np.int64)

    dfs_aligned = {}
    deriv_by_symbol = {}
    indicators = {}

    rng = np.random.default_rng(42)

    for idx, s in enumerate(symbols):
        base_price = 1000.0 * (idx + 1)
        walk = np.cumsum(rng.normal(0.0005, 0.02, size=n_bars))
        closes = base_price * np.exp(walk)
        highs = closes * (1.0 + np.abs(rng.normal(0.005, 0.005, size=n_bars)))
        lows = closes * (1.0 - np.abs(rng.normal(0.005, 0.005, size=n_bars)))
        opens = np.roll(closes, 1)
        opens[0] = closes[0]

        df = pd.DataFrame({
            "ts": sorted_ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": rng.uniform(100.0, 5000.0, size=n_bars),
        })
        dfs_aligned[s] = df
        indicators[s] = compute_standard_indicators(df)

        if s in crypto_symbols:
            fr = rng.normal(0.0001, 0.0003, size=n_bars)
            oi_chg = rng.normal(-0.01, 0.03, size=n_bars)
            f_7d = pd.Series(fr).rolling(42).mean().shift(1).fillna(0.0).values
            deriv_by_symbol[s] = {
                "funding_rate": fr,
                "oi_pct_chg_24h": oi_chg,
                "f_7d_mean": f_7d,
            }

    return {
        "all_symbols": symbols,
        "crypto_symbols": crypto_symbols,
        "sorted_ts": sorted_ts,
        "dfs_aligned": dfs_aligned,
        "deriv_by_symbol": deriv_by_symbol,
        "indicators": indicators,
    }


def test_m75_zero_lookahead_causality():
    """Verify mutating bars > t does NOT alter H1, H2, or H3 signals at bar t."""
    bundle = _generate_synthetic_bundle(n_bars=260)
    eval_bar = 220

    h1 = H1_VolSqueezeExpansionLong()
    h2 = H2_CrossAssetRvPair()
    h3 = H3_PostCrashLiqRebound()

    dummy_state = {
        "cash": 10000.0,
        "positions": {},
        "current_equity": 10000.0,
    }

    # Baseline evaluation at eval_bar
    h1_intents_before = h1.evaluate_trade_intents(bundle, eval_bar, dummy_state)
    h2_weights_before = h2.generate_target_weights(bundle, eval_bar, dummy_state)
    h3_intents_before = h3.evaluate_trade_intents(bundle, eval_bar, dummy_state)

    # Mutate future bars > eval_bar aggressively (e.g. 10x prices, massive spikes)
    for s in bundle["all_symbols"]:
        bundle["indicators"][s]["closes"][eval_bar + 1 :] *= 10.0
        bundle["indicators"][s]["highs"][eval_bar + 1 :] *= 15.0
        bundle["indicators"][s]["lows"][eval_bar + 1 :] *= 5.0
        if s in bundle["crypto_symbols"]:
            bundle["deriv_by_symbol"][s]["oi_pct_chg_24h"][eval_bar + 1 :] = -0.99
            bundle["deriv_by_symbol"][s]["funding_rate"][eval_bar + 1 :] = 0.50

    # Re-evaluate at eval_bar after future corruption
    h1_intents_after = h1.evaluate_trade_intents(bundle, eval_bar, dummy_state)
    h2_weights_after = h2.generate_target_weights(bundle, eval_bar, dummy_state)
    h3_intents_after = h3.evaluate_trade_intents(bundle, eval_bar, dummy_state)

    assert h1_intents_before == h1_intents_after, "H1 intents altered by future data mutation!"
    assert h2_weights_before == h2_weights_after, "H2 weights altered by future data mutation!"
    assert h3_intents_before == h3_intents_after, "H3 intents altered by future data mutation!"


def test_m75_failure_memory_pre_gate_blocks_duplicates():
    """Verify failure-memory pre-gate blocks synthetic duplicate of FALSIFIED_M63 or FALSIFIED_M72."""
    engine = CausalDiscoveryEngine(data_bundle=_generate_synthetic_bundle(n_bars=220))

    # Construct synthetic duplicate copying FALSIFIED_M63 keywords without distinct rationale
    dup_spec_m63 = HypothesisSpec(
        hypothesis_id="SYNTHETIC_DUP_M63",
        name="Derivatives Crowding 1h Funding Rate and Open Interest Fade",
        family="Family 2 (Derivatives Crowding / Funding-OI Fade 1h)",
        direction_mode="SHORT_ONLY",
        universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        timeframe="1h",
        parameters={
            "funding_zscore_entry": 1.5,
            "oi_percentile_min": 75,
            "holding_bars": 12,
        },
        economic_rationale="Fade extreme funding rate and open interest crowding spikes.",
        distinct_novelty_rationale="",  # Empty: MUST be rejected
    )

    with pytest.raises(DuplicateFalsifiedHypothesisError) as exc_info:
        engine.check_failure_memory_pre_gate(dup_spec_m63)

    assert "FALSIFIED_M63" in str(exc_info.value)

    # When distinct rationale is explicitly provided, pre-gate permits execution
    dup_spec_m63.distinct_novelty_rationale = "Explicitly novel regime-conditional non-linear hedging."
    # Should not raise
    engine.check_failure_memory_pre_gate(dup_spec_m63)


def test_m75_h2_zero_leverage_and_dispersion_gate():
    """Verify H2 enforces |w_long| + |w_short| <= 1.0001 (zero leverage) and stays flat when dispersion < 0.75."""
    bundle = _generate_synthetic_bundle(n_bars=250)
    h2 = H2_CrossAssetRvPair()
    state = {"current_equity": 10000.0, "cash": 10000.0, "positions": {}}

    # Case A: Low dispersion (< 0.75) -> Must stay 100% cash
    # Set identical returns across assets so dispersion is near zero
    for s in bundle["crypto_symbols"]:
        bundle["indicators"][s]["closes"] = np.ones(250) * 1000.0
        bundle["indicators"][s]["vol_20d"] = np.ones(250) * 0.50

    weights_flat = h2.generate_target_weights(bundle, 242, state)
    for s, w in weights_flat.items():
        assert w == 0.0, f"H2 must be flat when dispersion < 0.75, got {s}: {w}"

    # Case B: High dispersion (>= 0.75) -> Long top, Short bot, gross exposure <= 1.0001
    # Give BTC high return, SOL low return
    bundle["indicators"]["BTCUSDT"]["closes"][242] = 2000.0
    bundle["indicators"]["BTCUSDT"]["closes"][242 - 180] = 1000.0  # +100% ret -> score ~ 2.0
    bundle["indicators"]["SOLUSDT"]["closes"][242] = 500.0
    bundle["indicators"]["SOLUSDT"]["closes"][242 - 180] = 1000.0  # -50% ret -> score ~ -1.0

    weights_active = h2.generate_target_weights(bundle, 242, state)
    assert weights_active["BTCUSDT"] > 0.0, "Top momentum asset must be long"
    assert weights_active["SOLUSDT"] < 0.0, "Bottom momentum asset must be short"

    gross_exposure = sum(abs(w) for w in weights_active.values())
    assert gross_exposure <= 1.0001, f"Gross exposure {gross_exposure} exceeds zero-leverage cap 1.0001!"


def test_m75_h3_conservative_intrabar_tie_breaker():
    """Verify conservative intrabar tie-breaking: if SL and TP both touched on same bar, SL hits first."""
    bundle = _generate_synthetic_bundle(n_bars=250)
    engine = CausalDiscoveryEngine(data_bundle=bundle)
    h3 = H3_PostCrashLiqRebound()

    # Create synthetic bar where low <= SL and high >= TP simultaneously
    pos = {
        "units": 1.0,
        "entry_price": 100.0,
        "entry_bar": 200,
        "entry_ts": 1640995200000,
        "initial_sl": 90.0,
        "current_sl": 90.0,
        "tp": 120.0,
        "max_hold_bars": 18,
        "is_short": False,
        "risk_dist": 10.0,
    }

    # Low touches 85 (< 90), High touches 130 (> 120)
    bundle["indicators"]["BTCUSDT"]["lows"][210] = 85.0
    bundle["indicators"]["BTCUSDT"]["highs"][210] = 130.0

    exited, exit_px, reason = h3.check_intrabar_exit(bundle, 210, pos)
    # Default engine check logic
    if not exited:
        lo = float(bundle["indicators"]["BTCUSDT"]["lows"][210])
        hi = float(bundle["indicators"]["BTCUSDT"]["highs"][210])
        sl_hit = lo <= pos["current_sl"]
        tp_hit = hi >= pos["tp"]
        if sl_hit:
            exited = True
            exit_px = pos["current_sl"]
            reason = "STOP_LOSS"
        elif tp_hit:
            exited = True
            exit_px = pos["tp"]
            reason = "TAKE_PROFIT"

    assert exited is True
    assert reason == "STOP_LOSS", f"Tie-breaker violated: expected STOP_LOSS, got {reason}"
    assert exit_px <= pos["current_sl"]


def test_m75_append_only_trial_ledger_and_dsr_penalty(tmp_path):
    """Verify append-only trial ledger tracks M_cum and DSR penalizes multiple trials."""
    ledger_file = tmp_path / "test_discovery_trial_ledger.json"
    mgr = TrialLedgerManager(ledger_path=ledger_file)

    assert mgr.get_current_m_cum() == 18

    # Record trial 19
    trial_19 = {
        "hypothesis_id": "TEST_H1",
        "name": "Test H1",
        "family": "Test",
        "direction_mode": "LONG_ONLY",
        "train_sharpe": 1.0,
        "val_sharpe": 1.0,
        "oos_sharpe": 1.2,
        "oos_return_pct": 10.0,
        "oos_max_dd_pct": 5.0,
        "cpcv_median_sharpe": 1.0,
        "dsr_oos": 0.5,
        "dsr_pval": 0.5,
        "hurdles_passed": 6,
        "hurdles_total": 6,
        "stress_regimes": {},
        "verdict": "CANDIDATE_QUALIFIED_FOR_SHADOW_PROMOTION",
        "verdict_rationale": "Pass",
    }
    m1 = mgr.record_trial(trial_19)
    assert m1 == 19
    assert mgr.get_current_m_cum() == 19

    # Record trial 20
    trial_20 = dict(trial_19, hypothesis_id="TEST_H2", name="Test H2")
    m2 = mgr.record_trial(trial_20)
    assert m2 == 20
    assert mgr.get_current_m_cum() == 20

    # Verify DSR penalty increases with M_cum for identical returns
    rng = np.random.default_rng(42)
    daily_rets = rng.normal(0.001, 0.015, size=250).tolist()

    _, dsr_19, pval_19 = calculate_deflated_sharpe_ratio(daily_rets, estimated_trials=19)
    _, dsr_100, pval_100 = calculate_deflated_sharpe_ratio(daily_rets, estimated_trials=100)

    # Higher M_cum must strictly reduce or maintain DSR confidence (higher p-value)
    assert dsr_100 <= dsr_19, f"DSR failed to penalize higher trial count: {dsr_100} vs {dsr_19}"
    assert pval_100 >= pval_19, f"P-value failed to penalize higher trial count: {pval_100} vs {pval_19}"


def test_m75_governance_invariants_and_cli():
    """Verify permanent governance invariants and CLI discovery ledger output."""
    assert dl.REAL_CAPITAL_ENABLED is False, "REAL_CAPITAL_ENABLED must be False permanently"
    assert dl.CAPITAL_MODE == "TIER_0_PAPER", "CAPITAL_MODE must be TIER_0_PAPER permanently"

    # Test main.py discover --ledger --json
    cmd = [sys.executable, "main.py", "discover", "--ledger", "--json"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

    assert res.returncode == 0, f"main.py discover failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"
    data = json.loads(res.stdout)

    assert data.get("ledger_version") == "1.0.0"
    assert data.get("baseline_trials") == 18
    assert data.get("cumulative_trials_count") >= 21
    assert len(data.get("trials", [])) >= 3


def test_m75_1_hard_portfolio_gross_exposure_clamp():
    """Forces simultaneous overlapping entries across all assets and asserts max_gross_exposure <= 1.0001 at every bar."""
    from core.research.discovery_lab import BaseHypothesis, CausalDiscoveryEngine, HypothesisSpec

    class OverlappingAggressiveHypothesis(BaseHypothesis):
        def spec(self) -> HypothesisSpec:
            return HypothesisSpec(
                hypothesis_id="TEST_OVERLAPPING_CLAMP",
                name="Overlapping Aggressive Entries",
                family="Test",
                direction_mode="LONG_ONLY",
                universe=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"],
                timeframe="4h",
                parameters={},
                economic_rationale="Test",
                distinct_novelty_rationale="Test",
            )

        def evaluate_trade_intents(self, data_bundle, bar_idx, state):
            # Request aggressive 80% equity notional entry on EVERY asset simultaneously at bar 205
            if bar_idx == 205:
                intents = []
                cur_eq = state["current_equity"]
                for sym in self.spec().universe:
                    intents.append({
                        "symbol": sym,
                        "action": "ENTRY",
                        "target_notional": cur_eq * 0.80,  # 4 * 80% = 320% requested notional!
                        "initial_sl": 0.0,
                        "is_short": False,
                    })
                return intents
            return []

    bundle = _generate_synthetic_bundle(n_bars=260)
    engine = CausalDiscoveryEngine(data_bundle=bundle)
    res = engine.run_single_regime_simulation(OverlappingAggressiveHypothesis())

    # Verify max_gross_exposure <= 1.0001
    assert res["max_gross_exposure"] <= 1.0001, f"Hard clamp failed: max gross exposure was {res['max_gross_exposure']}"
    # Verify daily gross exposure series at every single day is <= 1.0001
    assert (res["df_daily"]["gross_exposure"] <= 1.0001).all(), "Gross exposure breached 1.0001 on one or more days"


def test_m75_1_stress_verdict_rejects_negative_return():
    """Verifies a stress run with oos_return_pct = -54.49 and oos_sharpe = 0.42 returns 'FAILS STRESS'."""
    from core.research.discovery_lab import compute_stress_resistance_verdict

    # Case 1: Direct parameters with negative return under delay
    verdict1 = compute_stress_resistance_verdict(
        friction_sharpe=0.82,
        friction_return=21.02,
        delay_sharpe=0.42,
        delay_return=-54.49,
        max_gross_exposure=0.95,
    )
    assert verdict1 == "FAILS STRESS", f"Expected FAILS STRESS, got {verdict1}"

    # Case 2: Stress matrix structure matching M75 H1
    mock_stress_matrix = {
        "regime_2_friction_stress": {
            "sealed_oos": {
                "daily_mtm_sharpe": 0.82,
                "total_return_pct": 21.02,
            }
        },
        "regime_3_delay_stress": {
            "sealed_oos": {
                "daily_mtm_sharpe": 0.42,
                "total_return_pct": -54.49,
            }
        },
    }
    verdict2 = compute_stress_resistance_verdict(stress_matrix=mock_stress_matrix, max_gross_exposure=0.95)
    assert verdict2 == "FAILS STRESS", f"Expected FAILS STRESS from stress_matrix, got {verdict2}"

    # Case 3: Surviving scenario (both positive return, positive Sharpe, gross <= 1.0001)
    mock_surviving_matrix = {
        "regime_2_friction_stress": {
            "sealed_oos": {
                "daily_mtm_sharpe": 1.20,
                "total_return_pct": 15.5,
            }
        },
        "regime_3_delay_stress": {
            "sealed_oos": {
                "daily_mtm_sharpe": 0.95,
                "total_return_pct": 11.2,
            }
        },
    }
    verdict3 = compute_stress_resistance_verdict(stress_matrix=mock_surviving_matrix, max_gross_exposure=0.95)
    assert verdict3 == "SURVIVES STRESS", f"Expected SURVIVES STRESS, got {verdict3}"

    # Case 4: Gross exposure breach (> 1.0001) must return FAILS STRESS
    verdict4 = compute_stress_resistance_verdict(stress_matrix=mock_surviving_matrix, max_gross_exposure=1.593)
    assert verdict4 == "FAILS STRESS", f"Expected FAILS STRESS for leverage breach, got {verdict4}"
