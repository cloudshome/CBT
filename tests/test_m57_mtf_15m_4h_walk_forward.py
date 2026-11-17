"""tests/test_m57_mtf_15m_4h_walk_forward.py
=========================================
Milestone 57: Multi-Timeframe (15m Tactical Day vs. 4h Structural Swing)
Walk-Forward Backtest & Cross-Horizon Regime Synthesis Test Suite.

Mandatory Gates:
1. test_smt_regime_timeframe_staleness_scaling
2. test_smt_regime_15m_macro_window_scaling
3. test_15m_tactical_day_a_plus_filter_rejects_micro_stops_and_counter_trend
4. test_4h_structural_swing_evaluation_and_ratchet
5. test_m57_eth_oos_non_negative_across_all_timeframes
6. test_m57_unified_multi_horizon_cp2_certification
7. test_real_capital_permanently_disabled
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.quantitative_validation import REAL_CAPITAL_ENABLED
from data.backtester import _evaluate
from engine.smt_regime import (
    precompute_eth_btc_regime_table,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def _make_dummy_mtf_series(
    symbol: str,
    n: int,
    start_price: float,
    timeframe: str = "1h",
    trend: float = 0.0,
) -> pd.DataFrame:
    base_ts = 1600000000000
    tf_ms = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}.get(
        timeframe, 3_600_000
    )
    rows = []
    p = start_price
    for i in range(n):
        ts = base_ts + i * tf_ms
        p = p * (1.0 + trend + (0.001 if i % 2 == 0 else -0.001))
        h = p * 1.003
        l = p * 0.997
        rows.append(
            {
                "ts": ts,
                "open": p,
                "high": h,
                "low": l,
                "close": p,
                "volume": 1000.0,
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["symbol"] = symbol
    df.attrs["timeframe"] = timeframe
    return df


def test_smt_regime_timeframe_staleness_scaling():
    """Gate 1: Verifies that precompute_eth_btc_regime_table accepts normal 4h spacing

    (14,400,000 ms) without false staleness error, while raising ValueError when
    reference data is genuinely stale (> max_staleness_ms = 12h on 4h).
    """
    n = 40
    eth_4h = _make_dummy_mtf_series("ETHUSDT", n, 2000.0, timeframe="4h")
    btc_4h = _make_dummy_mtf_series("BTCUSDT", n, 30000.0, timeframe="4h")

    # Normal 4h spacing (14.4M ms between bars) must succeed without error
    tbl = precompute_eth_btc_regime_table(eth_4h, btc_4h, timeframe="4h")
    assert len(tbl) == n

    for ts, snap in tbl.items():
        assert snap.eth_ts == ts
        assert snap.btc_ts <= snap.eth_ts
        assert (snap.eth_ts - snap.btc_ts) <= 14_400_000

    # Stale 4h reference series (> 12h lag across entire series) must raise ValueError
    stale_btc_4h = btc_4h.copy()
    stale_btc_4h["ts"] = stale_btc_4h["ts"] - (100 * 14_400_000)  # Reference series entirely stale
    with pytest.raises(ValueError, match="Reference BTC candle is stale"):
        precompute_eth_btc_regime_table(eth_4h, stale_btc_4h, timeframe="4h")


def test_smt_regime_15m_macro_window_scaling():
    """Gate 2: Verifies that precompute_eth_btc_regime_table on 15m scales macro windows

    (80/200/800 EMAs, 96 ROC, 192 Z-score) causally without lookahead.
    """
    n = 260
    eth_15m = _make_dummy_mtf_series("ETHUSDT", n, 2000.0, timeframe="15m")
    btc_15m = _make_dummy_mtf_series("BTCUSDT", n, 30000.0, timeframe="15m")

    tbl = precompute_eth_btc_regime_table(eth_15m, btc_15m, timeframe="15m")
    assert len(tbl) == n

    for ts, snap in tbl.items():
        assert snap.eth_ts == ts
        assert snap.btc_ts <= snap.eth_ts
        assert (snap.eth_ts - snap.btc_ts) <= 900_000
        assert snap.regime in (
            "ETH_OUTPERFORMING",
            "ETH_UNDERPERFORMING",
            "ETH_NEUTRAL",
        )


def test_15m_tactical_day_a_plus_filter_rejects_micro_stops_and_counter_trend():
    """Gate 3: Verifies that 15m strict_a_plus_only filters reject micro-stops

    (< 45 bps for BTC/SOL/PAXG, < 55 bps for ETH), reject market chasing
    Immediate Buy/Sell, and reject counter-trend chop.
    """
    n = 260
    df_15m = _make_dummy_mtf_series("BTCUSDT", n, 50000.0, timeframe="15m")

    # Plan with tiny stop (20 bps = 0.0020 < 0.0045 floor)
    plan_micro_sl = {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "entry": 50000.0,
        "stop_loss": 49900.0,  # 100/50000 = 0.0020
        "take_profit": 50500.0,
        "confidence": 75,
        "riskRewardRatio": 5.0,
        "status": "waiting",
        "type": "Buy Pullback",
    }
    gp_micro = _evaluate(
        plan_micro_sl,
        df_15m,
        i=100,
        horizon_bars=12,
        strict_a_plus_only=True,
    )
    assert gp_micro.outcome == "NOT_TRIGGERED"

    # Plan with Immediate Buy (market chasing)
    plan_imm = {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "entry": 50000.0,
        "stop_loss": 49600.0,  # 400/50000 = 0.0080 (stop is wide enough)
        "take_profit": 51200.0,
        "confidence": 75,
        "riskRewardRatio": 4.0,
        "status": "waiting",
        "type": "Immediate Buy",
    }
    gp_imm = _evaluate(
        plan_imm,
        df_15m,
        i=100,
        horizon_bars=12,
        strict_a_plus_only=True,
    )
    assert gp_imm.outcome == "NOT_TRIGGERED"

    # Counter-trend BUY plan where close < ema_200
    ind_df = df_15m.copy()
    ind_df["ema_50"] = 49000.0
    ind_df["ema_200"] = 51000.0  # close=50000 is BELOW ema_200
    ind_df["adx"] = 25.0

    plan_counter = {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "entry": 50000.0,
        "stop_loss": 49600.0,
        "take_profit": 51200.0,
        "confidence": 75,
        "riskRewardRatio": 4.0,
        "status": "waiting",
        "type": "Buy Pullback",
    }
    gp_counter = _evaluate(
        plan_counter,
        df_15m,
        i=100,
        horizon_bars=12,
        strict_a_plus_only=True,
        ind=ind_df,
    )
    assert gp_counter.outcome == "NOT_TRIGGERED"


def test_4h_structural_swing_evaluation_and_ratchet():
    """Gate 4: Verifies 4h structural swing trade evaluation with M47 progressive

    ratchet under EXECUTION_MODEL='impact'.
    """
    n = 60
    df_4h = _make_dummy_mtf_series("BTCUSDT", n, 50000.0, timeframe="4h")
    # Simulate upward rally in future bars
    for k in range(21, 28):
        df_4h.loc[k, "high"] = 52500.0
        df_4h.loc[k, "close"] = 52000.0

    plan_4h = {
        "action": "BUY",
        "symbol": "BTCUSDT",
        "entry": 50000.0,
        "stop_loss": 49000.0,  # risk = 1000
        "take_profit": 52000.0,  # TP1 = 2R = 52000
        "tp1": 52000.0,
        "tp2": 53000.0,
        "confidence": 75,
        "riskRewardRatio": 3.0,
        "status": "waiting",
        "type": "Buy Pullback",
    }

    gp = _evaluate(
        plan_4h,
        df_4h,
        i=20,
        horizon_bars=6,
        strict_a_plus_only=True,
        progressive_ratchet=True,
        enable_stage1=True,
        ratchet_mode="m47",
    )
    assert gp.outcome in ("FULL_WIN", "PARTIAL_WIN")
    assert gp.rr_net > 0.0


def test_m57_eth_oos_non_negative_across_all_timeframes():
    """Gate 5: Verifies that ETHUSDT Sealed OOS expectancy is non-negative

    (E[R_net] >= 0.0) across all three timeframes: 15m, 1h, and 4h.
    """
    results_path = ROOT_DIR / "research" / "m57_mtf_15m_1h_4h_walk_forward_results.json"
    if not results_path.exists():
        pytest.skip("m57_mtf_15m_1h_4h_walk_forward_results.json not yet generated.")

    data = json.loads(results_path.read_text(encoding="utf-8"))
    eth_mtf = data.get("eth_multi_timeframe_oos_summary", {})
    assert eth_mtf, "ETH multi-timeframe OOS summary missing from results."

    assert eth_mtf.get("15m", {}).get("expectancy_net", -1.0) >= 0.0
    assert eth_mtf.get("1h", {}).get("expectancy_net", -1.0) >= 0.0
    assert eth_mtf.get("4h", {}).get("expectancy_net", -1.0) >= 0.0


def test_m57_unified_multi_horizon_cp2_certification():
    """Gate 6: Verifies that all 5 M57 Hurdles pass on Sealed OOS:

    - Hurdle M57-1: 15m Tactical Day Pooled OOS E[R_net] >= 0.1500, PF >= 1.2500
    - Hurdle M57-2: 4h Structural Swing Pooled OOS E[R_net] >= 0.1500, PF >= 1.2500
    - Hurdle M57-3: ETHUSDT Multi-Timeframe OOS Protection >= 0.000R across 15m, 1h, 4h
    - Hurdle M57-4: Combined Multi-Horizon OOS N >= 350
    - Hurdle M57-5: Combined Multi-Horizon CP-2 (E[R] >= 0.25, PF >= 1.45, DSR >= 0.95, CPCV Sharpe >= 1.0)
    """
    results_path = ROOT_DIR / "research" / "m57_mtf_15m_1h_4h_walk_forward_results.json"
    if not results_path.exists():
        pytest.skip("m57_mtf_15m_1h_4h_walk_forward_results.json not yet generated.")

    data = json.loads(results_path.read_text(encoding="utf-8"))
    hurdles = data.get("hurdles", {})

    assert hurdles.get("hurdle_m57_1_passed") is True, "Hurdle M57-1 failed"
    assert hurdles.get("hurdle_m57_2_passed") is True, "Hurdle M57-2 failed"
    assert hurdles.get("hurdle_m57_3_passed") is True, "Hurdle M57-3 failed"
    assert hurdles.get("hurdle_m57_4_passed") is True, "Hurdle M57-4 failed"
    assert hurdles.get("hurdle_m57_5_passed") is True, "Hurdle M57-5 failed"
    assert data.get("all_hurdles_passed") is True
    assert data.get("certification_status") == "CERTIFIED_PASS"


def test_real_capital_permanently_disabled():
    """Gate 7: Verifies that REAL_CAPITAL_ENABLED is permanently False."""
    assert REAL_CAPITAL_ENABLED is False, "FATAL: REAL_CAPITAL_ENABLED must NEVER be set to True!"
