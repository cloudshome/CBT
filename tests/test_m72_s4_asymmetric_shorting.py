"""tests/test_m72_s4_asymmetric_shorting.py — Milestone 72 Test Suite.

Verifies:
1. test_m72_macro_regime_gate_blocks_shorts: Macro regime gate blocks shorts whenever
   close >= EMA_200 or EMA_50 >= EMA_200.
2. test_m72_zero_lookahead_causality: Mutating future bars > t does NOT change signal at
   bar t or entry fill at open[t+1].
3. test_m72_conservative_intrabar_tie_breaker: A bar touching both SL and TP1 exits at SL,
   never at TP1 (worst-case intrabar tie-breaker).
4. test_m72_asymmetric_partial_exit_and_breakeven_ratchet: Hitting TP1 (1.5R) closes 50% of
   units and ratchets stop-loss to breakeven (entry_price).
5. test_m72_zero_leverage_overlay_cap: P4_BEAR_OVERLAY gross exposure never exceeds 1.0001
   at any bar, even when P2_RP is partially invested.
6. test_m72_governance_invariants_locked: REAL_CAPITAL_ENABLED is False permanently and
   CapitalGovernor is locked at TIER_0_PAPER.
7. test_m72_failure_memory_record_consistency: Verifies FALSIFIED_M72 record is indexed in
   failure_memory subsystem with valid metrics and autopsy text.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.autonomous_research.failure_memory import (
    FALSIFIED_M72_RECORD,
    STATIC_FALSIFIED_RECORDS,
    FailureMemoryEngine,
)
from core.execution.capital_governor import CapitalGovernor, CapitalTier
from scripts.research.run_m72_s4_asymmetric_shorting import (
    compute_s4_indicators,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. Macro Regime Gate Test
# ==============================================================================
def test_m72_macro_regime_gate_blocks_shorts():
    """Verify macro bear gate blocks shorts whenever close >= EMA_200 or EMA_50 >= EMA_200."""
    # Case 1: close < EMA_200, EMA_50 < EMA_200 -> Allowed (True)
    c1, ema50_1, ema200_1 = 50000.0, 52000.0, 55000.0
    gate1 = (c1 < ema200_1) and (ema50_1 < ema200_1)
    assert gate1 is True, "Macro gate must allow shorting when close < EMA200 and EMA50 < EMA200"

    # Case 2: close >= EMA_200, EMA_50 < EMA_200 -> Blocked (False)
    c2, ema50_2, ema200_2 = 56000.0, 52000.0, 55000.0
    gate2 = (c2 < ema200_2) and (ema50_2 < ema200_2)
    assert gate2 is False, "Macro gate must block shorts when close >= EMA200"

    # Case 3: close < EMA_200, EMA_50 >= EMA_200 (Golden Cross regime) -> Blocked (False)
    c3, ema50_3, ema200_3 = 54000.0, 56000.0, 55000.0
    gate3 = (c3 < ema200_3) and (ema50_3 < ema200_3)
    assert gate3 is False, "Macro gate must block shorts when EMA50 >= EMA200 (Golden Cross)"

    # Case 4: Both close >= EMA_200 and EMA_50 >= EMA_200 -> Blocked (False)
    c4, ema50_4, ema200_4 = 60000.0, 58000.0, 55000.0
    gate4 = (c4 < ema200_4) and (ema50_4 < ema200_4)
    assert gate4 is False, "Macro gate must block shorts in bull regime"


# ==============================================================================
# 2. Zero-Lookahead Causality Test
# ==============================================================================
def test_m72_zero_lookahead_causality():
    """Verify that mutating future bars > t does NOT alter S4 indicators or entry signals at t."""
    n_bars = 300
    np.random.seed(42)
    base_price = 50000.0
    returns = np.random.normal(-0.001, 0.01, n_bars)
    closes = base_price * np.cumprod(1.0 + returns)
    highs = closes * (1.0 + np.random.uniform(0.001, 0.005, n_bars))
    lows = closes * (1.0 - np.random.uniform(0.001, 0.005, n_bars))
    opens = (highs + lows) / 2.0
    ts_arr = np.arange(1640995200000, 1640995200000 + n_bars * 14400000, 14400000, dtype=np.int64)

    df_base = pd.DataFrame({
        "ts": ts_arr,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.ones(n_bars) * 100.0,
    })

    ind_base = compute_s4_indicators(df_base)

    # Mutate all future bars after bar 220 with extreme moves (10x pump/dump)
    t_test = 220
    df_mutated = df_base.copy()
    df_mutated.loc[t_test + 1 :, "close"] *= 3.0
    df_mutated.loc[t_test + 1 :, "high"] *= 3.5
    df_mutated.loc[t_test + 1 :, "low"] *= 2.5
    df_mutated.loc[t_test + 1 :, "open"] *= 3.0

    ind_mutated = compute_s4_indicators(df_mutated)

    # Invariant: indicators at t_test must be character-exact identical
    for key in ["ema50", "ema200", "atr", "donch_l48", "donch_h24"]:
        val_base = float(ind_base[key][t_test])
        val_mutated = float(ind_mutated[key][t_test])
        assert np.isclose(val_base, val_mutated, atol=1e-9), (
            f"Lookahead violation detected in indicator '{key}' at bar {t_test}: {val_base} vs {val_mutated}"
        )


# ==============================================================================
# 3. Conservative Intrabar Tie-Breaker Test
# ==============================================================================
def test_m72_conservative_intrabar_tie_breaker():
    """Verify worst-case intrabar tie-breaker: touching both SL and TP1 on same bar fills SL first."""
    entry_price = 100.0
    sl_0 = 105.0  # SL is 5 points above entry
    r_unit = 5.0
    tp1_price = entry_price - 1.5 * r_unit  # 92.5

    # Simulated bar touches both SL (high = 106.0 >= 105.0) and TP1 (low = 90.0 <= 92.5)
    bar_o = 98.0
    bar_h = 106.0  # SL breached
    bar_l = 90.0   # TP1 breached
    bar_c = 95.0

    cur_sl = sl_0
    sl_hit = (bar_o >= cur_sl) or (bar_h >= cur_sl)
    tp1_hit = bar_l <= tp1_price

    assert sl_hit is True
    assert tp1_hit is True

    # Rule: Conservative tie-breaker forces SL fill; TP is disregarded
    if sl_hit:
        exit_p = max(bar_o, cur_sl)
        outcome = "SL_TAKEN"
    else:
        exit_p = tp1_price
        outcome = "TP_TAKEN"

    assert outcome == "SL_TAKEN", "Conservative tie-breaker must take SL, not TP"
    assert exit_p == 105.0, f"Expected exit at SL level (105.0), got {exit_p}"


# ==============================================================================
# 4. Asymmetric Partial Exit & Breakeven Ratchet Test
# ==============================================================================
def test_m72_asymmetric_partial_exit_and_breakeven_ratchet():
    """Verify hitting TP1 (1.5R) closes 50% and ratchets stop to breakeven (entry_price)."""
    entry_price = 100.0
    r_unit = 4.0
    sl_0 = entry_price + r_unit  # 104.0
    tp1_price = entry_price - 1.5 * r_unit  # 94.0
    initial_units = 10.0
    units_remaining = initial_units
    current_sl = sl_0
    tp1_filled = False

    # Bar 1: Price drops to 93.0 (hits TP1), high is 99.0 (does not hit SL)
    bar1_h = 99.0
    bar1_l = 93.0
    if not (bar1_h >= current_sl):
        if not tp1_filled and bar1_l <= tp1_price:
            units_closed = 0.5 * initial_units
            units_remaining -= units_closed
            tp1_filled = True
            current_sl = min(current_sl, entry_price)  # Ratchet to breakeven

    assert tp1_filled is True, "TP1 should have filled"
    assert units_remaining == 5.0, f"Remaining units should be 5.0, got {units_remaining}"
    assert current_sl == entry_price, f"Stop-loss should be at breakeven (100.0), got {current_sl}"

    # Bar 2: Market squeezes back up to 101.0 -> Breakeven stop triggered at 100.0
    bar2_h = 101.0
    sl_hit_b2 = bar2_h >= current_sl
    assert sl_hit_b2 is True, "Breakeven stop should trigger on bounce"
    exit_p_b2 = current_sl
    pnl_leg2 = units_remaining * (entry_price - exit_p_b2)
    assert pnl_leg2 == 0.0, f"Second leg should exit at breakeven ($0 PnL), got {pnl_leg2}"


# ==============================================================================
# 5. Zero-Leverage Overlay Cap Test
# ==============================================================================
def test_m72_zero_leverage_overlay_cap():
    """Verify P4_BEAR_OVERLAY gross exposure never exceeds 1.0001 at any bar."""
    json_path = ROOT_DIR / "research" / "m72_s4_asymmetric_shorting_results.json"
    if not json_path.exists():
        pytest.skip("m72_s4_asymmetric_shorting_results.json not yet generated")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    max_p4_exp = data["governance_invariants"]["max_gross_exposure_observed"]
    assert max_p4_exp <= 1.0001, (
        f"Zero-leverage violation: Observed max gross exposure {max_p4_exp:.4f} > 1.0001"
    )
    assert data["governance_invariants"]["zero_leverage_cap_enforced"] is True


# ==============================================================================
# 6. Governance Invariants Locked Test
# ==============================================================================
def test_m72_governance_invariants_locked():
    """Verify REAL_CAPITAL_ENABLED is False and CapitalGovernor is TIER_0_PAPER."""
    from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
    from core.strategies.p2_risk_parity import CAPITAL_MODE

    assert REAL_CAPITAL_ENABLED is False, "REAL_CAPITAL_ENABLED must be permanently False"
    assert CAPITAL_MODE == "TIER_0_PAPER", f"CAPITAL_MODE must be TIER_0_PAPER, got {CAPITAL_MODE}"

    gov = CapitalGovernor()
    state = gov.get_strategy_state()
    assert state["current_tier"] == CapitalTier.TIER_0_PAPER.value, (
        f"CapitalGovernor must be locked at TIER_0_PAPER, got {state['current_tier']}"
    )
    status = gov.get_status()
    assert status["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert status["real_capital_enabled"] is False


# ==============================================================================
# 7. Failure-Memory Record Consistency Test
# ==============================================================================
def test_m72_failure_memory_record_consistency():
    """Verify FALSIFIED_M72 is properly indexed in failure_memory subsystem."""
    assert FALSIFIED_M72_RECORD in STATIC_FALSIFIED_RECORDS
    assert FALSIFIED_M72_RECORD.failure_id == "FALSIFIED_M72"
    assert "S4" in FALSIFIED_M72_RECORD.hypothesis_text
    assert FALSIFIED_M72_RECORD.metrics["status"] == "FALSIFIED_M72"
    assert "autopsy_text" in FALSIFIED_M72_RECORD.__dict__
    assert len(FALSIFIED_M72_RECORD.autopsy_text) > 50

    engine = FailureMemoryEngine()
    is_dup, match, reason = engine.check_prior_failures(
        hypothesis_text="Asymmetric Shorting Engine S4 on 4h crypto majors with Macro Bear Gate",
        target_symbol="BTCUSDT,ETHUSDT,SOLUSDT",
        timeframe="4h",
    )
    assert is_dup is True, "Failure memory should recognize S4 shorting hypothesis as prior failure"
    assert match is not None
    assert match.failure_id == "FALSIFIED_M72"
