"""
tests/test_m64_structural_alpha_synthesis.py
============================================
Milestone 64: Low-Turnover Structural Alpha Synthesis & Benchmark Proof Test Suite.

Verifies:
1. Zero Lookahead Proof: Truncating input OHLCV at bar t produces the exact same signal
   at bar t as running on the full [0..T] series (strict point-in-time causality for S1 and S2).
2. Turnover Cost Accounting Proof: Holding the same asset across a rebalance boundary incurs
   0 trading fees; switching incurs 20 bps roundtrip cost on switched notional.
3. Bear-Market Cash Shield Proof: Synthetic declining market (negative 30-day return across all assets)
   forces S2 allocation strictly to 100% CASH (0% market exposure).
4. Constitutional Lock Proof: REAL_CAPITAL_ENABLED is permanently False, and CapitalGovernor
   remains locked at TIER_0_PAPER.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.execution.capital_governor import CapitalGovernor, CapitalTier
from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from scripts.research.run_m64_structural_alpha_synthesis import (
    calculate_rebalance_fee,
    compute_s1_indicators,
    compute_s1_signal_at_bar,
    rank_s2_assets,
)


# ==============================================================================
# 1. ZERO LOOKAHEAD PROOF (POINT-IN-TIME CAUSALITY)
# ==============================================================================
def test_zero_lookahead_point_in_time_signal_invariance():
    """
    Verifies that truncating input series at bar t produces the exact same indicators
    and trading signals at bar t as running on the full [0..T] series.
    Guarantees zero future data leakage.
    """
    np.random.seed(42)
    n_bars = 400
    dates = pd.date_range("2022-01-01", periods=n_bars, freq="4h")
    # Generate synthetic random walk with drift
    returns = np.random.normal(0.0005, 0.015, size=n_bars)
    prices = 100.0 * np.exp(np.cumsum(returns))

    highs = prices * (1.0 + np.abs(np.random.normal(0, 0.005, size=n_bars)))
    lows = prices * (1.0 - np.abs(np.random.normal(0, 0.005, size=n_bars)))
    opens = np.roll(prices, 1)
    opens[0] = prices[0]

    df_full = pd.DataFrame({
        "ts": [int(d.timestamp() * 1000) for d in dates],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": np.random.uniform(100, 1000, size=n_bars),
    })

    ind_full = compute_s1_indicators(df_full)

    # Test multiple arbitrary cutoff bars t well past warmup (e.g. 210, 250, 320)
    for t in [210, 250, 320, 380]:
        df_truncated = df_full.iloc[: t + 1].copy()
        ind_truncated = compute_s1_indicators(df_truncated)

        # Truncated last index is t
        full_entry, full_exit = compute_s1_signal_at_bar(ind_full, t)
        trunc_entry, trunc_exit = compute_s1_signal_at_bar(ind_truncated, t)

        assert full_entry == trunc_entry, f"S1 entry signal mismatch at bar {t}"
        assert full_exit == trunc_exit, f"S1 exit signal mismatch at bar {t}"

        # Indicators at bar t must match to machine precision
        np.testing.assert_allclose(ind_full["dh48"][t], ind_truncated["dh48"][t], rtol=1e-7)
        np.testing.assert_allclose(ind_full["dl24"][t], ind_truncated["dl24"][t], rtol=1e-7)
        np.testing.assert_allclose(ind_full["ema200"][t], ind_truncated["ema200"][t], rtol=1e-7)
        np.testing.assert_allclose(ind_full["atr"][t], ind_truncated["atr"][t], rtol=1e-7)

    # Test S2 point-in-time ranking invariance
    dfs_full = {}
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    for s_idx, s in enumerate(symbols):
        s_rets = np.random.normal(0.0003 * (s_idx + 1), 0.015, size=n_bars)
        s_closes = 100.0 * np.exp(np.cumsum(s_rets))
        dfs_full[s] = pd.DataFrame({
            "ts": [int(d.timestamp() * 1000) for d in dates],
            "open": s_closes,
            "high": s_closes * 1.01,
            "low": s_closes * 0.99,
            "close": s_closes,
            "volume": 1000.0,
        })

    for t in [210, 260, 350]:
        dfs_truncated = {s: dfs_full[s].iloc[: t + 1].copy() for s in symbols}

        target_full, scores_full, ret30_full = rank_s2_assets(dfs_full, bar_idx=t, current_holding="CASH")
        target_trunc, scores_trunc, ret30_trunc = rank_s2_assets(dfs_truncated, bar_idx=t, current_holding="CASH")

        assert target_full == target_trunc, f"S2 target mismatch at bar {t}: {target_full} vs {target_trunc}"
        for s in symbols:
            np.testing.assert_allclose(scores_full[s], scores_trunc[s], rtol=1e-7)
            np.testing.assert_allclose(ret30_full[s], ret30_trunc[s], rtol=1e-7)


# ==============================================================================
# 2. TURNOVER COST ACCOUNTING PROOF
# ==============================================================================
def test_turnover_delta_fee_accounting():
    """
    Verifies that:
    1. Unchanged holdings across a rebalance cadence incur exactly 0 trading fees.
    2. Switching between crypto assets incurs exactly 20 bps on the switched capital.
    3. Exiting to CASH or entering from CASH incurs exactly 10 bps (single leg).
    """
    equity = 10000.0

    # Unchanged holding -> 0 fees
    fee_unchanged_btc = calculate_rebalance_fee("BTCUSDT", "BTCUSDT", equity)
    assert fee_unchanged_btc == 0.0, f"Expected 0 fee on unchanged holding, got {fee_unchanged_btc}"

    fee_unchanged_cash = calculate_rebalance_fee("CASH", "CASH", equity)
    assert fee_unchanged_cash == 0.0, f"Expected 0 fee on unchanged CASH, got {fee_unchanged_cash}"

    # Asset switch (e.g. BTC -> ETH) -> 20 bps roundtrip (10 bps exit + 10 bps entry)
    fee_switch = calculate_rebalance_fee("BTCUSDT", "ETHUSDT", equity)
    expected_switch_fee = equity * 0.0020  # $20.00 on $10,000
    assert abs(fee_switch - expected_switch_fee) < 1e-6, f"Expected {expected_switch_fee}, got {fee_switch}"

    # Single leg: Asset -> CASH (10 bps exit)
    fee_to_cash = calculate_rebalance_fee("BTCUSDT", "CASH", equity)
    expected_cash_fee = equity * 0.0010  # $10.00 on $10,000
    assert abs(fee_to_cash - expected_cash_fee) < 1e-6, f"Expected {expected_cash_fee}, got {fee_to_cash}"

    # Single leg: CASH -> Asset (10 bps entry)
    fee_from_cash = calculate_rebalance_fee("CASH", "SOLUSDT", equity)
    assert abs(fee_from_cash - expected_cash_fee) < 1e-6, f"Expected {expected_cash_fee}, got {fee_from_cash}"


# ==============================================================================
# 3. BEAR-MARKET CASH SHIELD PROOF
# ==============================================================================
def test_bear_market_cash_shield():
    """
    Verifies that when all crypto majors and safe havens experience a structural decline
    (trailing 30-day return < 0), the absolute momentum gate forces Strategy S2
    to allocate strictly to 100% CASH (0% market exposure).
    """
    n_bars = 250
    dates = pd.date_range("2022-01-01", periods=n_bars, freq="4h")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]

    dfs_declining = {}
    for s in symbols:
        # Declining price from 100 down to 40 over 250 bars
        t_arr = np.linspace(0, 1, n_bars)
        price_curve = 100.0 * np.exp(-0.8 * t_arr)  # monotonic downward trend
        dfs_declining[s] = pd.DataFrame({
            "ts": [int(d.timestamp() * 1000) for d in dates],
            "open": price_curve,
            "high": price_curve * 1.002,
            "low": price_curve * 0.998,
            "close": price_curve,
            "volume": 1000.0,
        })

    # Evaluate at bar 200 (well past 180-bar 30-day lookback)
    target_asset, scores, ret_30ds = rank_s2_assets(
        dfs_declining, bar_idx=200, current_holding="BTCUSDT"
    )

    # Assert all assets have strictly negative 30-day returns
    for s in symbols:
        assert ret_30ds[s] < 0.0, f"Expected negative 30d return for {s}, got {ret_30ds[s]}"

    # Assert forced 100% CASH shield
    assert target_asset == "CASH", f"Expected CASH shield in bear market, got {target_asset}"


# ==============================================================================
# 4. CONSTITUTIONAL LOCK & CAPITAL GOVERNOR VERIFICATION
# ==============================================================================
def test_constitutional_capital_lock():
    """
    Verifies Level 1 Constitutional invariants:
    1. REAL_CAPITAL_ENABLED is immutable and False.
    2. CapitalGovernor remains locked at TIER_0_PAPER.
    3. Independent CP-2 verification fails closed without human auditor promotion.
    """
    assert REAL_CAPITAL_ENABLED is False, "CRITICAL: REAL_CAPITAL_ENABLED must permanently be False!"

    gov = CapitalGovernor()
    state = gov.get_strategy_state()
    assert state["current_tier"] == CapitalTier.TIER_0_PAPER.value, "CapitalGovernor must be locked at TIER_0_PAPER"

    # Status must report TIER_0_PAPER and real_capital_enabled False
    status = gov.get_status()
    assert status["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert status["real_capital_enabled"] is False
    assert status["tier_progression_allowed"] is False

    # CP-2 edge verification fails closed under M62 audit revocation
    cp2_passed, cp2_reason = gov.verify_checkpoint_2_edge(gov.default_strategy_id, {})
    assert cp2_passed is False, "verify_checkpoint_2_edge must fail closed pending independent audit"
    assert "FAILED_REAUDIT" in cp2_reason or "revoked" in cp2_reason.lower() or "audit" in cp2_reason.lower()
