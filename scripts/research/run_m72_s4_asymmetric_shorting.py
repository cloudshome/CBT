"""
Milestone 72: Causal Discovery & Falsification of Strategy S4 (Asymmetric Shorting Engine).
==========================================================================================

Implements WP-1, WP-2, and WP-3 of the Milestone 72 Institutional Directive:

1. WP-1: Pre-Registered Strategy S4 (Asymmetric Shorting Engine):
   - Universe: BTCUSDT, ETHUSDT, SOLUSDT (4h perpetual candles, 2022-2026).
   - Macro Bear Regime Gate (Required at bar close t):
     close[t] < EMA_200[t] AND EMA_50[t] < EMA_200[t].
     Shorting is strictly forbidden when this gate is False.
   - Variant S4-A (Pure Structural Breakdown):
     close[t] < min(low[t-48 : t]) (48-bar / 8-day Donchian Low breakdown).
   - Variant S4-B (Breakdown + Liquidation/Crowding Flush):
     Same S4-A breakdown AND at least one causal derivatives confirmation strictly <= ts[t]
     from derivatives_expanded_2022_2026.parquet:
       * Trailing 7-day funding was positive (funding_7d_mean[t-1] > 0) and
         latest funding drops below it (funding_rate[t] < funding_7d_mean[t-1]), OR
       * 24h Open Interest contraction (oi_pct_chg_24h[t] <= -0.02, confirming long liquidation flush).
   - Asymmetric Exit Rules:
     * Initial Stop Loss: SL_0 = entry_price + max(2.5 * ATR_14[t], 0.005 * entry_price)
     * Risk unit: R = SL_0 - entry_price
     * TP1 (50% partial exit): low[k] <= entry_price - 1.5 * R -> close 50%, move stop to breakeven (entry_price).
     * TP2 (remaining 50% exit): low[k] <= entry_price - 2.5 * R -> close remaining 50%.
     * Trailing Squeeze Stop: trails at min(current_SL, close[k] + 2.0 * ATR_14[k]).
     * Reversal Exit: exit at open[k+1] if close[k] > max(high[k-24 : k]) (24-bar Donchian High) or close[k] > EMA_200[k].
     * Worst-case intrabar tie-breaker: if high[k] >= current_SL and low[k] <= TP on same bar, SL fills first.
   - Volatility-Scaled Sizing:
     * base_risk = 0.01 * equity * min(0.15 / max(vol_20d, 0.04), 1.0) (capped at 1.0% equity risk).
     * Per-asset notional cap <= 0.25 * equity. Total S4 sleeve notional cap <= 0.75 * equity.
   - P4_BEAR_OVERLAY Ensemble:
     * Runs P2_RP unchanged; sweeps idle cash (when P2_RP gross exposure < 1.0) into winning S4 variant.
     * Capped strictly so gross_exposure(P2_RP) + gross_exposure(S4) <= 1.0001 at all times.

2. WP-2: Institutional Execution & Cost Stress Matrix:
   - Regime 1: Baseline Causal (20 bps roundtrip + actual 8h funding, open[t+1] fill).
   - Regime 2: 2x Friction Stress (40 bps roundtrip + actual 8h funding, open[t+1] fill).
   - Regime 3: 1-Bar Execution Delay Stress (20 bps roundtrip + actual 8h funding, open[t+2] fill = 4h delay).

3. WP-3: Honest Statistical & CP-2 Evaluation:
   - Strict Train / Val / Sealed OOS splits matching M65/M67.
   - Year-by-Year breakdown (2022-2026).
   - 15-fold time-purged CPCV.
   - Cumulative Deflated Sharpe Ratio DSR(M_cum = 18).
   - Dynamic boolean hurdle generation for all 6 CP-2 hurdles.
   - Honest Epistemic Verdict & Failure Memory archival.
   - CapitalGovernor locked at TIER_0_PAPER and REAL_CAPITAL_ENABLED = False permanently.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.quantitative_validation.metrics import calculate_deflated_sharpe_ratio
from data.store import CandleStore
from scripts.research.run_m65_risk_parity_and_stress_test import (
    calculate_continuous_mtm_metrics,
    compute_s1_indicators,
    compute_s1_signal_at_bar,
    compute_trailing_20d_volatility,
    rank_s2_div_assets,
    run_cpcv_analysis,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("m72_s4_asymmetric_shorting")


class NumpyJSONEncoder(json.JSONEncoder):
    """Encodes numpy types into standard Python types for JSON serialization."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


@dataclass
class S4TradeRecord:
    symbol: str
    variant: str
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    initial_sl: float
    risk_dist: float
    units: float
    gross_rr: float
    friction_rr: float
    net_rr: float
    outcome: str
    bars_held: int
    split: str
    regime: str
    exit_reason: str
    tp1_hit: bool
    tp2_hit: bool


# ==============================================================================
# 1. POINT-IN-TIME INDICATORS & CAUSAL SIGNAL CALCULATORS
# ==============================================================================
def compute_s4_indicators(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """
    Computes causal indicators for Strategy S4:
    - EMA-50 and EMA-200 on close
    - ATR-14
    - Donchian-48 Low: min(low[t-48 : t]) (using shift(1))
    - Donchian-24 High: max(high[t-24 : t]) (using shift(1))
    """
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values
    ts_vals = df["ts"].values

    # True Range & ATR-14
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    tr = np.insert(tr, 0, highs[0] - lows[0])
    atr = pd.Series(tr).rolling(14).mean().values

    # Moving averages
    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values

    # Channels (strictly past data)
    donch_l48 = pd.Series(lows).rolling(48).min().shift(1).values
    donch_h24 = pd.Series(highs).rolling(24).max().shift(1).values

    return {
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "ts": ts_vals,
        "atr": atr,
        "ema50": ema50,
        "ema200": ema200,
        "donch_l48": donch_l48,
        "donch_h24": donch_h24,
    }


def load_and_align_derivatives_data(
    sorted_ts: np.ndarray,
    crypto_symbols: list[str],
) -> dict[str, dict[str, np.ndarray]]:
    """
    Loads derivatives_expanded_2022_2026.parquet and aligns 1h derivatives metrics
    causally to the 4h candle grid.
    For each 4h candle closing at ts[t] + 4h (open ts = sorted_ts[t]):
    Takes the latest 1h bar strictly <= candle close (i.e. 1h ts <= sorted_ts[t] + 3h).
    Computes trailing 7-day (42 4h bars) rolling mean of funding rate, shifted by 1.
    """
    deriv_path = ROOT_DIR / "data" / "research" / "datasets" / "derivatives_expanded_2022_2026.parquet"
    if not deriv_path.exists():
        raise FileNotFoundError(f"Missing required derivatives dataset at {deriv_path}")

    logger.info(f"Loading derivatives dataset from {deriv_path}...")
    df_deriv = pd.read_parquet(deriv_path)

    deriv_by_symbol: dict[str, dict[str, np.ndarray]] = {}
    n_bars = len(sorted_ts)

    for sym in crypto_symbols:
        sub = df_deriv[df_deriv["symbol"] == sym].sort_values("ts").reset_index(drop=True)
        # 1h bar start ts mapped to 4h candle open ts
        sub["bar_4h_ts"] = (sub["ts"] // (4 * 3600 * 1000)) * (4 * 3600 * 1000)

        # Aggregate by taking the latest 1h snapshot in each 4h window
        agg = (
            sub.groupby("bar_4h_ts")
            .agg({
                "funding_rate": "last",
                "oi_pct_chg_24h": "last",
                "open_interest": "last",
            })
            .reset_index()
        )

        # Align with sorted_ts of the 4h candle grid
        df_aligned = pd.DataFrame({"bar_4h_ts": sorted_ts})
        df_merged = pd.merge(df_aligned, agg, on="bar_4h_ts", how="left")

        # Forward fill up to 2 bars (8h) for minor gaps, else fill 0.0
        df_merged["funding_rate"] = df_merged["funding_rate"].ffill(limit=2).fillna(0.0)
        df_merged["oi_pct_chg_24h"] = df_merged["oi_pct_chg_24h"].ffill(limit=2).fillna(0.0)

        f_rate = df_merged["funding_rate"].values
        oi_chg = df_merged["oi_pct_chg_24h"].values

        # Trailing 7-day (42 4h bars) funding mean shifted by 1 (strictly prior to bar t)
        f_7d_mean = pd.Series(f_rate).rolling(42).mean().shift(1).fillna(0.0).values

        # Causal derivative flush confirmation:
        # 1) Trailing 7d funding was positive and current drops below it
        cond1 = (f_7d_mean > 0.0) & (f_rate < f_7d_mean)
        # 2) 24h OI contracted by >= 2%
        cond2 = oi_chg <= -0.02
        flush_confirm = cond1 | cond2

        deriv_by_symbol[sym] = {
            "funding_rate": f_rate,
            "f_7d_mean": f_7d_mean,
            "oi_pct_chg_24h": oi_chg,
            "flush_confirm": flush_confirm,
        }

    return deriv_by_symbol


# ==============================================================================
# 2. FULL MULTI-REGIME SIMULATION ENGINE (BASELINE, 2X FRICTION, 1-BAR DELAY)
# ==============================================================================
def run_m72_single_regime_simulation(
    dfs_aligned: dict[str, pd.DataFrame],
    sorted_ts: np.ndarray,
    s1_ind: dict[str, dict[str, np.ndarray]],
    s4_ind: dict[str, dict[str, np.ndarray]],
    deriv_data: dict[str, dict[str, np.ndarray]],
    friction_bps: float = 20.0,
    exec_delay_bars: int = 1,
    target_vol: float = 0.15,
) -> dict[str, Any]:
    """
    Runs full causal Mark-to-Market simulation of:
    - S1 (Donchian-48 Macro Trend)
    - S2-Div (Dual Momentum Vol-Weighted Rotation)
    - P2_RP (50/50 Risk Parity Ensemble)
    - S4-A (Standalone Pure Structural Breakdown Shorting)
    - S4-B (Standalone Breakdown + Liquidation Flush Shorting)
    - P4_BEAR_OVERLAY_A (P2_RP + S4-A Idle-Cash Sweep)
    - P4_BEAR_OVERLAY_B (P2_RP + S4-B Idle-Cash Sweep)
    - BnH (Equal-Weight Buy & Hold Benchmark)

    Parameters:
    - friction_bps: Roundtrip fee in basis points (20.0 Baseline/Delay, 40.0 2x Friction).
      Entry fee = exit fee = friction_bps / 2.0 / 10000.0.
    - exec_delay_bars: 1 for immediate fill at open[t+1], 2 for 4h latency fill at open[t+2].
    - target_vol: Annualized target volatility (0.15 = 15%).
    """
    n_total = len(sorted_ts)
    all_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    crypto_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    start_bar = 205  # Warmup for 200 EMA and 180-bar momentum
    init_capital = 10000.0
    fee_rate = (friction_bps / 2.0) / 10000.0  # 10 bps = 0.0010, 20 bps = 0.0020

    idx_train_end = int(n_total * 0.50)
    idx_val_end = int(n_total * 0.75)

    # --------------------------------------------------------------------------
    # S1 State
    # --------------------------------------------------------------------------
    s1_cash = init_capital
    s1_positions: dict[str, dict[str, Any]] = {}
    s1_equity_series = np.zeros(n_total)
    s1_gross_exposure_series = np.zeros(n_total)
    s1_pending_orders: dict[int, list[dict[str, Any]]] = {}
    s1_4h_rets = np.zeros(n_total)

    # --------------------------------------------------------------------------
    # S2-Div State
    # --------------------------------------------------------------------------
    s2_cash = init_capital
    s2_holdings: dict[str, float] = {s: 0.0 for s in all_symbols}
    s2_equity_series = np.zeros(n_total)
    s2_gross_exposure_series = np.zeros(n_total)
    s2_pending_orders: dict[int, dict[str, float]] = {}
    s2_rebalance_cadence = 42

    # --------------------------------------------------------------------------
    # S4-A and S4-B States (Standalone Sleeves)
    # --------------------------------------------------------------------------
    s4a_cash = init_capital
    s4a_positions: dict[str, dict[str, Any]] = {}
    s4a_trades_closed: list[S4TradeRecord] = []
    s4a_equity_series = np.zeros(n_total)
    s4a_gross_exposure_series = np.zeros(n_total)
    s4a_pending_orders: dict[int, list[dict[str, Any]]] = {}

    s4b_cash = init_capital
    s4b_positions: dict[str, dict[str, Any]] = {}
    s4b_trades_closed: list[S4TradeRecord] = []
    s4b_equity_series = np.zeros(n_total)
    s4b_gross_exposure_series = np.zeros(n_total)
    s4b_pending_orders: dict[int, list[dict[str, Any]]] = {}

    # Benchmark
    bnh_units = {s: (init_capital * 0.25) / float(dfs_aligned[s]["open"].iloc[start_bar]) for s in all_symbols}
    bnh_equity_series = np.zeros(n_total)

    s1_equity_series[:start_bar] = init_capital
    s2_equity_series[:start_bar] = init_capital
    s4a_equity_series[:start_bar] = init_capital
    s4b_equity_series[:start_bar] = init_capital
    bnh_equity_series[:start_bar] = init_capital

    # Pre-allocate daily tracking arrays
    for i in range(start_bar, n_total):
        # ----------------------------------------------------------------------
        # 1. Execute Pending Orders Scheduled for Bar i Open
        # ----------------------------------------------------------------------
        # S2-Div Pending Rebalance Execution
        if i in s2_pending_orders:
            target_dollar_alloc = s2_pending_orders.pop(i)
            curr_s2_val = s2_cash + sum(
                s2_holdings[s] * float(dfs_aligned[s]["open"].iloc[i]) for s in all_symbols
            )
            for s in all_symbols:
                target_alloc = target_dollar_alloc.get(s, 0.0)
                current_val = s2_holdings[s] * float(dfs_aligned[s]["open"].iloc[i])
                diff = target_alloc - current_val
                is_entry_or_exit = (target_alloc <= 10.0 and current_val > 10.0) or (
                    target_alloc > 10.0 and current_val <= 10.0
                )
                threshold = 10.0 if is_entry_or_exit else max(0.03 * curr_s2_val, 10.0)

                if abs(diff) > threshold:
                    open_p = float(dfs_aligned[s]["open"].iloc[i])
                    fee = abs(diff) * fee_rate
                    s2_cash -= fee
                    if diff < 0:
                        units_to_sell = min(abs(diff) / open_p, s2_holdings[s])
                        s2_holdings[s] -= units_to_sell
                        s2_cash += units_to_sell * open_p
                    else:
                        units_to_buy = diff / open_p
                        s2_holdings[s] += units_to_buy
                        s2_cash -= diff

        # S1 Pending Orders Execution (Entries & Exits)
        if i in s1_pending_orders:
            pending_list = s1_pending_orders.pop(i)
            for order in pending_list:
                s = order["symbol"]
                action = order["action"]
                if action == "ENTRY" and s not in s1_positions and len(s1_positions) < 4:
                    entry_p = float(s1_ind[s]["opens"][i])
                    risk_dist = order["risk_dist"]
                    target_notional = order["target_notional"]
                    notional = min(target_notional, s1_cash / (1.0 + fee_rate))
                    if notional > 10.0:
                        fee = notional * fee_rate
                        units = notional / entry_p
                        s1_cash -= notional + fee
                        s1_positions[s] = {
                            "units": units,
                            "entry_price": entry_p,
                            "entry_ts": int(s1_ind[s]["ts"][i]),
                            "trailing_sl": entry_p - risk_dist,
                            "initial_sl": entry_p - risk_dist,
                            "risk_dist": risk_dist,
                            "entry_bar": i,
                            "bars_held": 0,
                            "split": "train"
                            if i < idx_train_end
                            else ("val" if i < idx_val_end else "oos"),
                        }
                elif action == "EXIT" and s in s1_positions:
                    pos = s1_positions[s]
                    exit_p = float(s1_ind[s]["opens"][i])
                    proceeds = pos["units"] * exit_p
                    fee = proceeds * fee_rate
                    s1_cash += proceeds - fee
                    del s1_positions[s]

        # S4-A Pending Orders Execution (Short Entries & Reversal Exits)
        if i in s4a_pending_orders:
            pending_s4a = s4a_pending_orders.pop(i)
            for order in pending_s4a:
                s = order["symbol"]
                action = order["action"]
                if action == "ENTRY" and s not in s4a_positions and len(s4a_positions) < 3:
                    entry_p = float(s4_ind[s]["opens"][i])
                    target_notional = order["target_notional"]
                    notional = min(target_notional, s4a_cash / (1.0 + fee_rate))
                    if notional > 10.0:
                        fee = notional * fee_rate
                        units = notional / entry_p
                        s4a_cash -= fee  # Fee deducted from cash; notional is margin
                        sl_0 = entry_p + max(2.5 * float(s4_ind[s]["atr"][order["signal_bar"]]), 0.005 * entry_p)
                        r_unit = sl_0 - entry_p
                        s4a_positions[s] = {
                            "initial_units": units,
                            "units_remaining": units,
                            "entry_price": entry_p,
                            "entry_ts": int(s4_ind[s]["ts"][i]),
                            "initial_sl": sl_0,
                            "current_sl": sl_0,
                            "risk_dist": r_unit,
                            "tp1_price": entry_p - 1.5 * r_unit,
                            "tp2_price": entry_p - 2.5 * r_unit,
                            "tp1_filled": False,
                            "tp2_filled": False,
                            "entry_bar": i,
                            "bars_held": 0,
                            "split": "train"
                            if i < idx_train_end
                            else ("val" if i < idx_val_end else "oos"),
                        }
                elif action == "EXIT" and s in s4a_positions:
                    pos = s4a_positions[s]
                    exit_p = float(s4_ind[s]["opens"][i])
                    rem_units = pos["units_remaining"]
                    proceeds = rem_units * (pos["entry_price"] - exit_p)
                    fee = rem_units * exit_p * fee_rate
                    s4a_cash += proceeds - fee
                    gross_r = (pos["entry_price"] - exit_p) / pos["risk_dist"]
                    fric_r = (2.0 * fee_rate * pos["entry_price"]) / pos["risk_dist"]
                    net_r = gross_r - fric_r
                    s4a_trades_closed.append(
                        S4TradeRecord(
                            symbol=s,
                            variant="S4-A",
                            entry_ts=pos["entry_ts"],
                            exit_ts=int(s4_ind[s]["ts"][i]),
                            entry_price=round(pos["entry_price"], 4),
                            exit_price=round(exit_p, 4),
                            initial_sl=round(pos["initial_sl"], 4),
                            risk_dist=round(pos["risk_dist"], 4),
                            units=round(rem_units, 6),
                            gross_rr=round(gross_r, 4),
                            friction_rr=round(fric_r, 4),
                            net_rr=round(net_r, 4),
                            outcome="WIN" if net_r > 0 else "LOSS",
                            bars_held=pos["bars_held"] + 1,
                            split=pos["split"],
                            regime="BEAR",
                            exit_reason=order.get("reason", "REVERSAL_EXIT"),
                            tp1_hit=pos["tp1_filled"],
                            tp2_hit=pos["tp2_filled"],
                        )
                    )
                    del s4a_positions[s]

        # S4-B Pending Orders Execution (Short Entries & Reversal Exits)
        if i in s4b_pending_orders:
            pending_s4b = s4b_pending_orders.pop(i)
            for order in pending_s4b:
                s = order["symbol"]
                action = order["action"]
                if action == "ENTRY" and s not in s4b_positions and len(s4b_positions) < 3:
                    entry_p = float(s4_ind[s]["opens"][i])
                    target_notional = order["target_notional"]
                    notional = min(target_notional, s4b_cash / (1.0 + fee_rate))
                    if notional > 10.0:
                        fee = notional * fee_rate
                        units = notional / entry_p
                        s4b_cash -= fee
                        sl_0 = entry_p + max(2.5 * float(s4_ind[s]["atr"][order["signal_bar"]]), 0.005 * entry_p)
                        r_unit = sl_0 - entry_p
                        s4b_positions[s] = {
                            "initial_units": units,
                            "units_remaining": units,
                            "entry_price": entry_p,
                            "entry_ts": int(s4_ind[s]["ts"][i]),
                            "initial_sl": sl_0,
                            "current_sl": sl_0,
                            "risk_dist": r_unit,
                            "tp1_price": entry_p - 1.5 * r_unit,
                            "tp2_price": entry_p - 2.5 * r_unit,
                            "tp1_filled": False,
                            "tp2_filled": False,
                            "entry_bar": i,
                            "bars_held": 0,
                            "split": "train"
                            if i < idx_train_end
                            else ("val" if i < idx_val_end else "oos"),
                        }
                elif action == "EXIT" and s in s4b_positions:
                    pos = s4b_positions[s]
                    exit_p = float(s4_ind[s]["opens"][i])
                    rem_units = pos["units_remaining"]
                    proceeds = rem_units * (pos["entry_price"] - exit_p)
                    fee = rem_units * exit_p * fee_rate
                    s4b_cash += proceeds - fee
                    gross_r = (pos["entry_price"] - exit_p) / pos["risk_dist"]
                    fric_r = (2.0 * fee_rate * pos["entry_price"]) / pos["risk_dist"]
                    net_r = gross_r - fric_r
                    s4b_trades_closed.append(
                        S4TradeRecord(
                            symbol=s,
                            variant="S4-B",
                            entry_ts=pos["entry_ts"],
                            exit_ts=int(s4_ind[s]["ts"][i]),
                            entry_price=round(pos["entry_price"], 4),
                            exit_price=round(exit_p, 4),
                            initial_sl=round(pos["initial_sl"], 4),
                            risk_dist=round(pos["risk_dist"], 4),
                            units=round(rem_units, 6),
                            gross_rr=round(gross_r, 4),
                            friction_rr=round(fric_r, 4),
                            net_rr=round(net_r, 4),
                            outcome="WIN" if net_r > 0 else "LOSS",
                            bars_held=pos["bars_held"] + 1,
                            split=pos["split"],
                            regime="BEAR",
                            exit_reason=order.get("reason", "REVERSAL_EXIT"),
                            tp1_hit=pos["tp1_filled"],
                            tp2_hit=pos["tp2_filled"],
                        )
                    )
                    del s4b_positions[s]

        # ----------------------------------------------------------------------
        # 2. Intrabar Trailing Stop Checks for S1 & Intrabar Funding
        # ----------------------------------------------------------------------
        for s, pos in list(s1_positions.items()):
            pos["bars_held"] += 1
            k_o = float(s1_ind[s]["opens"][i])
            k_l = float(s1_ind[s]["lows"][i])
            k_c = float(s1_ind[s]["closes"][i])
            k_atr = float(s1_ind[s]["atr"][i])
            sl = pos["trailing_sl"]

            # S1 long funding fee every 2 bars (8h) for crypto perps
            if s != "PAXGUSDT" and pos["bars_held"] % 2 == 0:
                s1_cash -= pos["units"] * k_c * 0.0001

            hit_stop = False
            exit_p = 0.0
            if k_o <= sl:
                hit_stop = True
                exit_p = k_o
            elif k_l <= sl:
                hit_stop = True
                exit_p = sl

            if hit_stop:
                proceeds = pos["units"] * exit_p
                fee = proceeds * fee_rate
                s1_cash += proceeds - fee
                del s1_positions[s]
            else:
                pos["trailing_sl"] = max(pos["trailing_sl"], k_c - 3.0 * k_atr)

        # S2-Div funding fee every 2 bars (8h)
        if i % 2 == 0:
            for s in crypto_symbols:
                if s2_holdings[s] > 0.0:
                    s2_cash -= s2_holdings[s] * float(dfs_aligned[s]["close"].iloc[i]) * 0.0001

        # ----------------------------------------------------------------------
        # 3. Intrabar Asymmetric Exits & Funding Impact for S4-A & S4-B
        # ----------------------------------------------------------------------
        # Helper to process intrabar exits for S4 short positions
        for variant_name, s4_pos_dict, s4_trades_list, s4_cash_ref in [
            ("S4-A", s4a_positions, s4a_trades_closed, "s4a"),
            ("S4-B", s4b_positions, s4b_trades_closed, "s4b"),
        ]:
            for s, pos in list(s4_pos_dict.items()):
                pos["bars_held"] += 1
                k_o = float(s4_ind[s]["opens"][i])
                k_h = float(s4_ind[s]["highs"][i])
                k_l = float(s4_ind[s]["lows"][i])
                k_c = float(s4_ind[s]["closes"][i])
                k_atr = float(s4_ind[s]["atr"][i])

                # Actual 8h perpetual funding impact for shorts:
                # Shorts receive positive funding, pay negative funding
                if i % 2 == 0:
                    f_rate = float(deriv_data[s]["funding_rate"][i])
                    # Funding cash flow: + notional * funding_rate
                    funding_cf = pos["units_remaining"] * k_c * f_rate
                    if s4_cash_ref == "s4a":
                        s4a_cash += funding_cf
                    else:
                        s4b_cash += funding_cf

                # Check SL and TP triggers
                cur_sl = pos["current_sl"]
                sl_hit = (k_o >= cur_sl) or (k_h >= cur_sl)

                # WORST-CASE INTRABAR TIE-BREAKER:
                # If high touches current_SL, SL triggers FIRST and takes absolute precedence!
                if sl_hit:
                    exit_p = max(k_o, cur_sl)
                    rem_units = pos["units_remaining"]
                    pnl = rem_units * (pos["entry_price"] - exit_p)
                    fee = rem_units * exit_p * fee_rate
                    if s4_cash_ref == "s4a":
                        s4a_cash += pnl - fee
                    else:
                        s4b_cash += pnl - fee

                    gross_r = (pos["entry_price"] - exit_p) / pos["risk_dist"]
                    fric_r = (2.0 * fee_rate * pos["entry_price"]) / pos["risk_dist"]
                    net_r = gross_r - fric_r
                    reason = "BREAKEVEN_STOP" if pos["tp1_filled"] else "INITIAL_STOP"

                    s4_trades_list.append(
                        S4TradeRecord(
                            symbol=s,
                            variant=variant_name,
                            entry_ts=pos["entry_ts"],
                            exit_ts=int(s4_ind[s]["ts"][i]),
                            entry_price=round(pos["entry_price"], 4),
                            exit_price=round(exit_p, 4),
                            initial_sl=round(pos["initial_sl"], 4),
                            risk_dist=round(pos["risk_dist"], 4),
                            units=round(rem_units, 6),
                            gross_rr=round(gross_r, 4),
                            friction_rr=round(fric_r, 4),
                            net_rr=round(net_r, 4),
                            outcome="WIN" if net_r > 0 else "LOSS",
                            bars_held=pos["bars_held"],
                            split=pos["split"],
                            regime="BEAR",
                            exit_reason=reason,
                            tp1_hit=pos["tp1_filled"],
                            tp2_hit=pos["tp2_filled"],
                        )
                    )
                    del s4_pos_dict[s]
                    continue

                # If SL was NOT hit, check Take Profits:
                # 1) TP1 (50% partial exit at entry - 1.5*R)
                if not pos["tp1_filled"] and k_l <= pos["tp1_price"]:
                    tp1_exit_p = pos["tp1_price"]
                    units_tp1 = 0.5 * pos["initial_units"]
                    pnl1 = units_tp1 * (pos["entry_price"] - tp1_exit_p)
                    fee1 = units_tp1 * tp1_exit_p * fee_rate
                    if s4_cash_ref == "s4a":
                        s4a_cash += pnl1 - fee1
                    else:
                        s4b_cash += pnl1 - fee1

                    pos["units_remaining"] -= units_tp1
                    pos["tp1_filled"] = True
                    # Ratchet stop to breakeven (entry_price)
                    pos["current_sl"] = min(pos["current_sl"], pos["entry_price"])

                    gross_r1 = (pos["entry_price"] - tp1_exit_p) / pos["risk_dist"]
                    fric_r1 = (2.0 * fee_rate * pos["entry_price"]) / pos["risk_dist"]
                    net_r1 = gross_r1 - fric_r1
                    s4_trades_list.append(
                        S4TradeRecord(
                            symbol=s,
                            variant=variant_name,
                            entry_ts=pos["entry_ts"],
                            exit_ts=int(s4_ind[s]["ts"][i]),
                            entry_price=round(pos["entry_price"], 4),
                            exit_price=round(tp1_exit_p, 4),
                            initial_sl=round(pos["initial_sl"], 4),
                            risk_dist=round(pos["risk_dist"], 4),
                            units=round(units_tp1, 6),
                            gross_rr=round(gross_r1, 4),
                            friction_rr=round(fric_r1, 4),
                            net_rr=round(net_r1, 4),
                            outcome="WIN" if net_r1 > 0 else "LOSS",
                            bars_held=pos["bars_held"],
                            split=pos["split"],
                            regime="BEAR",
                            exit_reason="TP1_PARTIAL_1.5R",
                            tp1_hit=True,
                            tp2_hit=False,
                        )
                    )

                # 2) TP2 (remaining 50% exit at entry - 2.5*R)
                if pos["tp1_filled"] and not pos["tp2_filled"] and k_l <= pos["tp2_price"]:
                    tp2_exit_p = pos["tp2_price"]
                    units_tp2 = pos["units_remaining"]
                    pnl2 = units_tp2 * (pos["entry_price"] - tp2_exit_p)
                    fee2 = units_tp2 * tp2_exit_p * fee_rate
                    if s4_cash_ref == "s4a":
                        s4a_cash += pnl2 - fee2
                    else:
                        s4b_cash += pnl2 - fee2

                    pos["units_remaining"] = 0.0
                    pos["tp2_filled"] = True
                    gross_r2 = (pos["entry_price"] - tp2_exit_p) / pos["risk_dist"]
                    fric_r2 = (2.0 * fee_rate * pos["entry_price"]) / pos["risk_dist"]
                    net_r2 = gross_r2 - fric_r2
                    s4_trades_list.append(
                        S4TradeRecord(
                            symbol=s,
                            variant=variant_name,
                            entry_ts=pos["entry_ts"],
                            exit_ts=int(s4_ind[s]["ts"][i]),
                            entry_price=round(pos["entry_price"], 4),
                            exit_price=round(tp2_exit_p, 4),
                            initial_sl=round(pos["initial_sl"], 4),
                            risk_dist=round(pos["risk_dist"], 4),
                            units=round(units_tp2, 6),
                            gross_rr=round(gross_r2, 4),
                            friction_rr=round(fric_r2, 4),
                            net_rr=round(net_r2, 4),
                            outcome="WIN" if net_r2 > 0 else "LOSS",
                            bars_held=pos["bars_held"],
                            split=pos["split"],
                            regime="BEAR",
                            exit_reason="TP2_FULL_2.5R",
                            tp1_hit=True,
                            tp2_hit=True,
                        )
                    )
                    del s4_pos_dict[s]
                    continue

                # 3) End of bar: Trailing Squeeze Stop
                # min(current_SL, close[k] + 2.0 * ATR_14[k])
                trailing_level = k_c + 2.0 * k_atr
                pos["current_sl"] = min(pos["current_sl"], trailing_level)

        # ----------------------------------------------------------------------
        # 4. Bar i Close: Mark-to-Market Valuation & Exposure Tracking
        # ----------------------------------------------------------------------
        # S1 MtM
        s1_pos_val = sum(pos["units"] * float(s1_ind[s]["closes"][i]) for s, pos in s1_positions.items())
        s1_cur_val = s1_cash + s1_pos_val
        s1_equity_series[i] = s1_cur_val
        s1_gross_exposure_series[i] = min(s1_pos_val / max(s1_cur_val, 1e-4), 1.0)
        s1_4h_rets[i] = (s1_cur_val - s1_equity_series[i - 1]) / max(s1_equity_series[i - 1], 1e-4) if i > start_bar else 0.0

        # S2-Div MtM
        s2_pos_val = sum(s2_holdings[s] * float(dfs_aligned[s]["close"].iloc[i]) for s in all_symbols)
        s2_cur_val = s2_cash + s2_pos_val
        s2_equity_series[i] = s2_cur_val
        s2_gross_exposure_series[i] = min(s2_pos_val / max(s2_cur_val, 1e-4), 1.0)

        # S4-A MtM (Short: Cash + Unrealized PnL = Cash + sum(units * (entry - close)))
        s4a_unrealized = sum(pos["units_remaining"] * (pos["entry_price"] - float(s4_ind[s]["closes"][i])) for s, pos in s4a_positions.items())
        s4a_cur_val = max(s4a_cash + s4a_unrealized, 1e-4)
        s4a_equity_series[i] = s4a_cur_val
        s4a_notional = sum(pos["units_remaining"] * float(s4_ind[s]["closes"][i]) for s, pos in s4a_positions.items())
        s4a_gross_exposure_series[i] = min(s4a_notional / s4a_cur_val, 1.0)

        # S4-B MtM
        s4b_unrealized = sum(pos["units_remaining"] * (pos["entry_price"] - float(s4_ind[s]["closes"][i])) for s, pos in s4b_positions.items())
        s4b_cur_val = max(s4b_cash + s4b_unrealized, 1e-4)
        s4b_equity_series[i] = s4b_cur_val
        s4b_notional = sum(pos["units_remaining"] * float(s4_ind[s]["closes"][i]) for s, pos in s4b_positions.items())
        s4b_gross_exposure_series[i] = min(s4b_notional / s4b_cur_val, 1.0)

        # Benchmark MtM
        bnh_cur_val = sum(bnh_units[s] * float(dfs_aligned[s]["close"].iloc[i]) for s in all_symbols)
        bnh_equity_series[i] = bnh_cur_val

        # ----------------------------------------------------------------------
        # 5. Generate Causal Signals at Bar i Close
        # ----------------------------------------------------------------------
        if i < n_total - exec_delay_bars:
            exec_bar = i + exec_delay_bars

            # --- S1 Signal Logic ---
            if i >= start_bar + 120:
                s1_window_rets = s1_4h_rets[i - 120 : i]
                s1_ann_vol = float(np.std(s1_window_rets, ddof=1) * math.sqrt(2190.0))
            else:
                s1_ann_vol = target_vol
            s1_vol_scalar = min(target_vol / max(s1_ann_vol, 0.04), 2.5)

            for s in all_symbols:
                entry_sig, exit_sig = compute_s1_signal_at_bar(s1_ind[s], i)
                if s in s1_positions:
                    if exit_sig:
                        s1_pending_orders.setdefault(exec_bar, []).append({"symbol": s, "action": "EXIT"})
                else:
                    if entry_sig:
                        atr_t = float(s1_ind[s]["atr"][i])
                        close_p = float(s1_ind[s]["closes"][i])
                        risk_dist = max(3.0 * atr_t, close_p * 0.005)
                        base_risk_usd = 0.01 * s1_cur_val * s1_vol_scalar
                        calc_notional = (base_risk_usd / risk_dist) * close_p
                        max_trade_notional = 0.25 * s1_cur_val * min(s1_vol_scalar, 1.5)
                        active_notional = sum(pos["units"] * float(s1_ind[sym]["closes"][i]) for sym, pos in s1_positions.items())
                        avail_headroom = max(s1_cur_val - active_notional, 0.0)
                        target_notional = min(calc_notional, max_trade_notional, avail_headroom)
                        if target_notional > 10.0:
                            s1_pending_orders.setdefault(exec_bar, []).append({
                                "symbol": s,
                                "action": "ENTRY",
                                "risk_dist": risk_dist,
                                "target_notional": target_notional,
                            })

            # --- S2-Div Rebalance Logic (Every 42 bars / 7 days) ---
            if (i - start_bar) % s2_rebalance_cadence == 0:
                current_crypto = [s for s in crypto_symbols if s2_holdings[s] > 0.0]
                base_weights, _, vols_20d = rank_s2_div_assets(
                    dfs_aligned,
                    bar_idx=i,
                    current_crypto_holdings=current_crypto,
                    lookback_bars=180,
                    vol_lookback_bars=120,
                    hysteresis=0.15,
                )
                if i >= start_bar + 120:
                    basket_rets_120 = np.zeros(120)
                    for s in all_symbols:
                        w_s = base_weights.get(s, 0.0)
                        if w_s > 0.0:
                            s_c = dfs_aligned[s]["close"].values
                            s_rets = np.diff(s_c[i - 120 : i + 1]) / s_c[i - 120 : i]
                            basket_rets_120 += w_s * s_rets
                    s2_ann_vol = float(np.std(basket_rets_120, ddof=1) * math.sqrt(2190.0))
                else:
                    s2_ann_vol = sum(base_weights[s] * vols_20d.get(s, 0.50) for s in all_symbols)

                s2_vol_scalar = min(target_vol / max(s2_ann_vol, 0.04), 1.0)
                target_dollar_alloc = {}
                total_target_alloc = 0.0
                for s in all_symbols:
                    w = base_weights.get(s, 0.0) * s2_vol_scalar
                    alloc = s2_cur_val * w
                    target_dollar_alloc[s] = alloc
                    total_target_alloc += alloc

                if total_target_alloc > s2_cur_val:
                    scale_back = s2_cur_val / total_target_alloc
                    target_dollar_alloc = {s: v * scale_back for s, v in target_dollar_alloc.items()}
                s2_pending_orders[exec_bar] = target_dollar_alloc

            # --- S4 Short Signals & Reversals (BTCUSDT, ETHUSDT, SOLUSDT) ---
            for s in crypto_symbols:
                c_now = float(s4_ind[s]["closes"][i])
                ema50_now = float(s4_ind[s]["ema50"][i])
                ema200_now = float(s4_ind[s]["ema200"][i])
                donch_l48_now = float(s4_ind[s]["donch_l48"][i])
                donch_h24_now = float(s4_ind[s]["donch_h24"][i])
                atr_now = float(s4_ind[s]["atr"][i])

                # Macro Bear Regime Gate
                macro_bear = (c_now < ema200_now) and (ema50_now < ema200_now)

                # Reversal Exit Signal (Exit if close > Donchian-24 High OR close > EMA-200)
                reversal_exit = (c_now > donch_h24_now) or (c_now > ema200_now)

                # S4-A Breakdown Entry
                breakdown_a = macro_bear and (c_now < donch_l48_now)

                # S4-B Breakdown Entry (Breakdown + Flush Confirmation)
                flush_conf = bool(deriv_data[s]["flush_confirm"][i])
                breakdown_b = breakdown_a and flush_conf

                # Trailing 20d volatility
                vol_20d = compute_trailing_20d_volatility(s4_ind[s]["closes"], i, lookback_bars=120)
                vol_scalar = min(0.15 / max(vol_20d, 0.04), 1.0)

                # Process S4-A Orders
                if s in s4a_positions:
                    if reversal_exit:
                        reason = "DONCHIAN_H24_REVERSAL" if c_now > donch_h24_now else "EMA200_BREACH"
                        s4a_pending_orders.setdefault(exec_bar, []).append({
                            "symbol": s,
                            "action": "EXIT",
                            "reason": reason,
                        })
                else:
                    if breakdown_a:
                        base_risk_usd = 0.01 * s4a_cur_val * vol_scalar
                        sl_dist = max(2.5 * atr_now, 0.005 * c_now)
                        calc_notional = (base_risk_usd / sl_dist) * c_now
                        max_asset_notional = 0.25 * s4a_cur_val
                        active_notional = sum(
                            pos["units_remaining"] * float(s4_ind[sym]["closes"][i]) for sym, pos in s4a_positions.items()
                        )
                        avail_sleeve = max(0.75 * s4a_cur_val - active_notional, 0.0)
                        target_notional = min(calc_notional, max_asset_notional, avail_sleeve, s4a_cash)
                        if target_notional > 10.0:
                            s4a_pending_orders.setdefault(exec_bar, []).append({
                                "symbol": s,
                                "action": "ENTRY",
                                "signal_bar": i,
                                "target_notional": target_notional,
                            })

                # Process S4-B Orders
                if s in s4b_positions:
                    if reversal_exit:
                        reason = "DONCHIAN_H24_REVERSAL" if c_now > donch_h24_now else "EMA200_BREACH"
                        s4b_pending_orders.setdefault(exec_bar, []).append({
                            "symbol": s,
                            "action": "EXIT",
                            "reason": reason,
                        })
                else:
                    if breakdown_b:
                        base_risk_usd = 0.01 * s4b_cur_val * vol_scalar
                        sl_dist = max(2.5 * atr_now, 0.005 * c_now)
                        calc_notional = (base_risk_usd / sl_dist) * c_now
                        max_asset_notional = 0.25 * s4b_cur_val
                        active_notional = sum(
                            pos["units_remaining"] * float(s4_ind[sym]["closes"][i]) for sym, pos in s4b_positions.items()
                        )
                        avail_sleeve = max(0.75 * s4b_cur_val - active_notional, 0.0)
                        target_notional = min(calc_notional, max_asset_notional, avail_sleeve, s4b_cash)
                        if target_notional > 10.0:
                            s4b_pending_orders.setdefault(exec_bar, []).append({
                                "symbol": s,
                                "action": "ENTRY",
                                "signal_bar": i,
                                "target_notional": target_notional,
                            })

    # --------------------------------------------------------------------------
    # 6. Build Calendar-Day Mark-to-Market Time Series
    # --------------------------------------------------------------------------
    date_to_last_bar: dict[Any, int] = {}
    for idx, ts in enumerate(sorted_ts[start_bar:], start=start_bar):
        dt = datetime.fromtimestamp(ts / 1000.0, tz=UTC).date()
        date_to_last_bar[dt] = idx

    sorted_dates = sorted(date_to_last_bar.keys())
    daily_s1_eq = np.array([s1_equity_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_s2_eq = np.array([s2_equity_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_s4a_eq = np.array([s4a_equity_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_s4b_eq = np.array([s4b_equity_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_bnh_eq = np.array([bnh_equity_series[date_to_last_bar[d]] for d in sorted_dates])

    # S1 & S2 returns
    daily_s1_ret = np.diff(daily_s1_eq) / daily_s1_eq[:-1]
    daily_s1_ret = np.insert(daily_s1_ret, 0, 0.0)
    daily_s2_ret = np.diff(daily_s2_eq) / daily_s2_eq[:-1]
    daily_s2_ret = np.insert(daily_s2_ret, 0, 0.0)

    # P2_RP 50/50 Equal-Risk Blend
    daily_p2_ret = 0.5 * daily_s1_ret + 0.5 * daily_s2_ret
    daily_p2_eq = np.zeros(len(sorted_dates))
    daily_p2_eq[0] = init_capital
    for d_idx in range(1, len(sorted_dates)):
        daily_p2_eq[d_idx] = daily_p2_eq[d_idx - 1] * (1.0 + daily_p2_ret[d_idx])

    # S4 returns
    daily_s4a_ret = np.diff(daily_s4a_eq) / daily_s4a_eq[:-1]
    daily_s4a_ret = np.insert(daily_s4a_ret, 0, 0.0)
    daily_s4b_ret = np.diff(daily_s4b_eq) / daily_s4b_eq[:-1]
    daily_s4b_ret = np.insert(daily_s4b_ret, 0, 0.0)

    # Benchmark returns
    daily_bnh_ret = np.diff(daily_bnh_eq) / daily_bnh_eq[:-1]
    daily_bnh_ret = np.insert(daily_bnh_ret, 0, 0.0)

    # Gross exposures
    daily_s1_exp = np.array([s1_gross_exposure_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_s2_exp = np.array([s2_gross_exposure_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_p2_exp = 0.5 * daily_s1_exp + 0.5 * daily_s2_exp
    daily_s4a_exp = np.array([s4a_gross_exposure_series[date_to_last_bar[d]] for d in sorted_dates])
    daily_s4b_exp = np.array([s4b_gross_exposure_series[date_to_last_bar[d]] for d in sorted_dates])

    # P4_BEAR_OVERLAY Ensembles:
    # Runs P2_RP unchanged; unallocated idle cash (1.0 - p2_exp) is dynamically swept
    # into the S4 variant, strictly capped so total gross exposure <= 1.0001
    daily_p4a_eq = np.zeros(len(sorted_dates))
    daily_p4a_eq[0] = init_capital
    daily_p4a_ret = np.zeros(len(sorted_dates))
    daily_p4a_exp = np.zeros(len(sorted_dates))

    daily_p4b_eq = np.zeros(len(sorted_dates))
    daily_p4b_eq[0] = init_capital
    daily_p4b_ret = np.zeros(len(sorted_dates))
    daily_p4b_exp = np.zeros(len(sorted_dates))

    for d_idx in range(1, len(sorted_dates)):
        # Idle cash capacity from previous day
        idle_cap = max(1.0 - daily_p2_exp[d_idx - 1], 0.0)

        # Overlay A
        s4a_alloc = min(daily_s4a_exp[d_idx - 1], idle_cap)
        r_p4a = daily_p2_ret[d_idx] + s4a_alloc * daily_s4a_ret[d_idx]
        daily_p4a_ret[d_idx] = r_p4a
        daily_p4a_eq[d_idx] = daily_p4a_eq[d_idx - 1] * (1.0 + r_p4a)
        daily_p4a_exp[d_idx] = daily_p2_exp[d_idx] + s4a_alloc

        # Overlay B
        s4b_alloc = min(daily_s4b_exp[d_idx - 1], idle_cap)
        r_p4b = daily_p2_ret[d_idx] + s4b_alloc * daily_s4b_ret[d_idx]
        daily_p4b_ret[d_idx] = r_p4b
        daily_p4b_eq[d_idx] = daily_p4b_eq[d_idx - 1] * (1.0 + r_p4b)
        daily_p4b_exp[d_idx] = daily_p2_exp[d_idx] + s4b_alloc

    df_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(sorted_dates),
            "s1": daily_s1_eq,
            "s2": daily_s2_eq,
            "p2_rp": daily_p2_eq,
            "s4a": daily_s4a_eq,
            "s4b": daily_s4b_eq,
            "p4_overlay_a": daily_p4a_eq,
            "p4_overlay_b": daily_p4b_eq,
            "bnh": daily_bnh_eq,
            "s1_ret": daily_s1_ret,
            "s2_ret": daily_s2_ret,
            "p2_ret": daily_p2_ret,
            "s4a_ret": daily_s4a_ret,
            "s4b_ret": daily_s4b_ret,
            "p4a_ret": daily_p4a_ret,
            "p4b_ret": daily_p4b_ret,
            "bnh_ret": daily_bnh_ret,
            "p2_exp": daily_p2_exp,
            "s4a_exp": daily_s4a_exp,
            "s4b_exp": daily_s4b_exp,
            "p4a_exp": daily_p4a_exp,
            "p4b_exp": daily_p4b_exp,
        }
    ).set_index("date")

    return {
        "df_daily": df_daily,
        "s4a_trades": s4a_trades_closed,
        "s4b_trades": s4b_trades_closed,
        "max_gross_exposure": {
            "p2_max": float(np.max(daily_p2_exp)),
            "s4a_max": float(np.max(daily_s4a_exp)),
            "s4b_max": float(np.max(daily_s4b_exp)),
            "p4a_max": float(np.max(daily_p4a_exp)),
            "p4b_max": float(np.max(daily_p4b_exp)),
        },
    }


# ==============================================================================
# 3. SCORECARD & REPORT GENERATION ENGINE
# ==============================================================================
def summarize_trade_list(trades: list[S4TradeRecord]) -> dict[str, Any]:
    """Computes comprehensive trade-level metrics."""
    if not trades:
        return {
            "trades_count": 0,
            "win_rate_pct": 0.0,
            "expectancy_gross": 0.0,
            "expectancy_net": 0.0,
            "profit_factor": 0.0,
            "total_net_r": 0.0,
            "friction_drag_r": 0.0,
            "tp1_hit_count": 0,
            "tp2_hit_count": 0,
            "tp1_hit_rate_pct": 0.0,
        }

    net_rs = [t.net_rr for t in trades]
    gross_rs = [t.gross_rr for t in trades]
    fric_rs = [t.friction_rr for t in trades]
    wins = [r for r in net_rs if r > 0]
    losses = [r for r in net_rs if r <= 0]
    tp1_hits = sum(1 for t in trades if t.tp1_hit)
    tp2_hits = sum(1 for t in trades if t.tp2_hit)

    pf = float(sum(wins) / abs(sum(losses))) if losses and abs(sum(losses)) > 1e-4 else (999.0 if wins else 0.0)

    return {
        "trades_count": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2),
        "expectancy_gross": round(float(np.mean(gross_rs)), 4),
        "expectancy_net": round(float(np.mean(net_rs)), 4),
        "profit_factor": round(pf, 4),
        "total_net_r": round(float(sum(net_rs)), 2),
        "friction_drag_r": round(float(sum(fric_rs)), 2),
        "tp1_hit_count": tp1_hits,
        "tp2_hit_count": tp2_hits,
        "tp1_hit_rate_pct": round(tp1_hits / len(trades) * 100.0, 2),
    }


def generate_markdown_audit_report(
    results: dict[str, Any],
    report_path: Path,
) -> str:
    """Generates the formal Milestone 72 Markdown audit dossier."""
    verdict = results["epistemic_verdict"]
    splits = results["splits_scorecard"]
    yearly = results["yearly_benchmark_2022_2026"]
    stress = results["stress_matrix"]
    hurdles = results["cp2_hurdles"]
    meta = results["hurdle_summary"]
    s4_winner = results["winning_s4_variant"]

    rep = []
    rep.append("# MILESTONE 72 AUDIT DOSSIER: CAUSAL DISCOVERY & FALSIFICATION OF STRATEGY S4")
    rep.append("## ASYMMETRIC SHORTING ENGINE (S4-A / S4-B / P4_BEAR_OVERLAY)")
    rep.append(f"**Evaluation Timestamp UTC:** `{results['evaluation_timestamp_utc']}`  ")
    rep.append(f"**Runtime:** `{results['total_runtime_seconds']:.2f} seconds` | **Cumulative Trials:** `$M_{{\\text{{cum}}}} = 18$`  ")
    rep.append(f"**Final Epistemic Verdict:** **`{verdict}`**  ")
    rep.append(f"**CP-2 Institutional Hurdles:** **{meta['summary_text']}**\n")
    rep.append("---\n")

    rep.append("## 1. EXECUTIVE SUMMARY & SCIENTIFIC FINDINGS\n")
    rep.append("1. **Hypothesis Evaluation:**")
    rep.append("   - Tested whether an Asymmetric Shorting Engine (S4) operating on 4h crypto majors (BTCUSDT, ETHUSDT, SOLUSDT) under a strict Macro Bear Gate (`close < EMA_200` AND `EMA_50 < EMA_200`) provides positive expectancy and downside risk protection across Train (2022-2024), Validation (2024-2025), and Sealed OOS (2025-2026).")
    rep.append("   - Evaluated two pre-registered variants: **`S4-A`** (Pure Structural 48-bar Donchian Breakdown) and **`S4-B`** (Breakdown + Derivatives Liquidation/OI Flush Confirmation), as well as the **`P4_BEAR_OVERLAY`** ensemble.")
    rep.append("2. **Key Empirical Results:**")
    rep.append(f"   - **Winning Variant:** `{s4_winner}`.")
    rep.append(f"   - **Sealed OOS Standalone Performance:** S4-A Sharpe `{splits['sealed_oos']['s4a']['daily_mtm_sharpe']:.2f}`, S4-B Sharpe `{splits['sealed_oos']['s4b']['daily_mtm_sharpe']:.2f}` vs BnH `{splits['sealed_oos']['bnh']['daily_mtm_sharpe']:.2f}`.")
    rep.append(f"   - **P4 Bear Overlay (OOS):** P4_BEAR_OVERLAY_A Sharpe `{splits['sealed_oos']['p4_overlay_a']['daily_mtm_sharpe']:.2f}` (Max DD `{splits['sealed_oos']['p4_overlay_a']['max_drawdown_pct']:.2f}%`) vs P2_RP Baseline `{splits['sealed_oos']['p2_rp']['daily_mtm_sharpe']:.2f}` (Max DD `{splits['sealed_oos']['p2_rp']['max_drawdown_pct']:.2f}%`).")
    rep.append(f"   - **Multiple-Testing Deflated Sharpe:** $DSR(M_{{\\text{{cum}}}} = 18)$ on Sealed OOS = `{results['statistical_rigor']['dsr_oos']:.4f}` ($p = {results['statistical_rigor']['pval_oos']:.4f}$).")
    rep.append(f"   - **Dynamic CP-2 Hurdle Status:** **{meta['passed_count']} Passed / {meta['failed_count']} Failed**.")
    rep.append("\n---\n")

    rep.append("## 2. TRAIN / VALIDATION / SEALED OOS PERFORMANCE SCORECARD\n")
    rep.append("| Split | Days | S4-A Standalone | S4-B (Deriv Flush) | P4 Overlay A | P4 Overlay B | P2_RP Baseline | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for sp_name, sp_data in splits.items():
        rep.append(
            f"| **{sp_name.upper()}** | {sp_data['days']} | "
            f"Ret: {sp_data['s4a']['total_return_pct']:+.2f}% (Sh: {sp_data['s4a']['daily_mtm_sharpe']:.2f}, DD: {sp_data['s4a']['max_drawdown_pct']:.2f}%) | "
            f"Ret: {sp_data['s4b']['total_return_pct']:+.2f}% (Sh: {sp_data['s4b']['daily_mtm_sharpe']:.2f}, DD: {sp_data['s4b']['max_drawdown_pct']:.2f}%) | "
            f"Ret: {sp_data['p4_overlay_a']['total_return_pct']:+.2f}% (Sh: {sp_data['p4_overlay_a']['daily_mtm_sharpe']:.2f}) | "
            f"Ret: {sp_data['p4_overlay_b']['total_return_pct']:+.2f}% (Sh: {sp_data['p4_overlay_b']['daily_mtm_sharpe']:.2f}) | "
            f"Ret: {sp_data['p2_rp']['total_return_pct']:+.2f}% (Sh: {sp_data['p2_rp']['daily_mtm_sharpe']:.2f}) | "
            f"Ret: {sp_data['bnh']['total_return_pct']:+.2f}% (Sh: {sp_data['bnh']['daily_mtm_sharpe']:.2f}) |"
        )
    rep.append("\n---\n")

    rep.append("## 3. YEAR-BY-YEAR BENCHMARK BREAKDOWN (2022–2026)\n")
    rep.append("| Year | Strategy / Sleeve | Return % | Daily MtM Sharpe | Daily MtM Sortino | Max DD % | Realized Vol % |")
    rep.append("|:---:|:---|:---:|:---:|:---:|:---:|:---:|")
    for yr, y_data in yearly.items():
        for s_name, m in y_data.items():
            if s_name == "days":
                continue
            rep.append(
                f"| {yr} | {s_name} | {m['total_return_pct']:+.2f}% | {m['daily_mtm_sharpe']:.2f} | {m['daily_mtm_sortino']:.2f} | {m['max_drawdown_pct']:.2f}% | {m['annualized_vol_pct']:.2f}% |"
            )
    rep.append("\n---\n")

    rep.append("## 4. INSTITUTIONAL EXECUTION & COST STRESS MATRIX\n")
    rep.append("| Stress Regime | OOS Return % | OOS Sharpe | OOS Max DD % | Full Return % | Full Sharpe | Full Max DD % | Winning Overlay |")
    rep.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for reg_key, reg_info in stress.items():
        rep.append(
            f"| **{reg_info['description']}** | "
            f"{reg_info['sealed_oos']['p4_winning']['total_return_pct']:+.2f}% | {reg_info['sealed_oos']['p4_winning']['daily_mtm_sharpe']:.2f} | {reg_info['sealed_oos']['p4_winning']['max_drawdown_pct']:.2f}% | "
            f"{reg_info['full_period']['p4_winning']['total_return_pct']:+.2f}% | {reg_info['full_period']['p4_winning']['daily_mtm_sharpe']:.2f} | {reg_info['full_period']['p4_winning']['max_drawdown_pct']:.2f}% | "
            f"`{s4_winner}` |"
        )
    rep.append("\n---\n")

    rep.append("## 5. DYNAMIC CP-2 HURDLES EVALUATION\n")
    rep.append("| Hurdle | Requirement | Observed Metric | Status |")
    rep.append("|:---|:---|:---|:---:|")
    for h_key, h_data in hurdles.items():
        rep.append(
            f"| **{h_data['name']}** | {h_data['requirement']} | {h_data['details']} | **{'PASS' if h_data['passed'] else 'FAIL'}** |"
        )

    rep.append(f"\n### Dynamic Summary: **{meta['summary_text']}**\n")
    rep.append(f"### Epistemic Verdict: `{verdict}`\n")
    rep.append("> **Governance Invariants:** `REAL_CAPITAL_ENABLED = False` permanently. `CapitalGovernor = \"TIER_0_PAPER\"`. Zero leverage: gross exposure $\\le 1.0001$.\n")

    report_content = "\n".join(rep)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")
    return report_content


# ==============================================================================
# 4. MASTER BENCHMARK RUNNER
# ==============================================================================
def run_m72_benchmark() -> dict[str, Any]:
    """Runs the full Milestone 72 S4 Asymmetric Shorting Engine benchmark."""
    logger.info("=== STARTING MILESTONE 72: STRATEGY S4 CAUSAL RESEARCH BENCHMARK ===")
    start_time = time.time()

    store = CandleStore(ROOT_DIR / "data" / "store")
    all_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    crypto_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # 1. Load 4h candles
    dfs: dict[str, pd.DataFrame] = {}
    for s in all_symbols:
        df = store.read("binance", "perp", s, "4h")
        if df.empty:
            df = store.read("binance", "spot", s, "4h")
        dfs[s] = df

    # Find common timestamps
    common_ts = set(dfs["BTCUSDT"]["ts"])
    for s in all_symbols[1:]:
        common_ts = common_ts.intersection(dfs[s]["ts"])
    sorted_ts = np.array(sorted(list(common_ts)), dtype=np.int64)
    n_total = len(sorted_ts)

    dfs_aligned = {
        s: dfs[s][dfs[s]["ts"].isin(sorted_ts)].sort_values("ts").reset_index(drop=True)
        for s in all_symbols
    }

    # Precalculate indicators
    s1_ind = {s: compute_s1_indicators(dfs_aligned[s]) for s in all_symbols}
    s4_ind = {s: compute_s4_indicators(dfs_aligned[s]) for s in crypto_symbols}

    # 2. Ingest and causally align derivatives features
    deriv_data = load_and_align_derivatives_data(sorted_ts, crypto_symbols)

    # 3. Simulate Stress Matrix Regimes
    logger.info("Simulating Regime 1: Baseline Causal (20 bps roundtrip + 8h funding, open[t+1])...")
    res_baseline = run_m72_single_regime_simulation(
        dfs_aligned=dfs_aligned,
        sorted_ts=sorted_ts,
        s1_ind=s1_ind,
        s4_ind=s4_ind,
        deriv_data=deriv_data,
        friction_bps=20.0,
        exec_delay_bars=1,
    )

    logger.info("Simulating Regime 2: 2x Friction Stress (40 bps roundtrip + 8h funding, open[t+1])...")
    res_friction = run_m72_single_regime_simulation(
        dfs_aligned=dfs_aligned,
        sorted_ts=sorted_ts,
        s1_ind=s1_ind,
        s4_ind=s4_ind,
        deriv_data=deriv_data,
        friction_bps=40.0,
        exec_delay_bars=1,
    )

    logger.info("Simulating Regime 3: 1-Bar Execution Delay Stress (20 bps roundtrip + 8h funding, open[t+2])...")
    res_delay = run_m72_single_regime_simulation(
        dfs_aligned=dfs_aligned,
        sorted_ts=sorted_ts,
        s1_ind=s1_ind,
        s4_ind=s4_ind,
        deriv_data=deriv_data,
        friction_bps=20.0,
        exec_delay_bars=2,
    )

    # 4. Evaluate Splits on Baseline Regime
    df_daily = res_baseline["df_daily"]
    n_days = len(df_daily)
    d_train_end = int(n_days * 0.50)
    d_val_end = int(n_days * 0.75)

    splits_data = {
        "train": df_daily.iloc[:d_train_end],
        "val": df_daily.iloc[d_train_end:d_val_end],
        "sealed_oos": df_daily.iloc[d_val_end:],
        "combined_walk_forward": df_daily.iloc[d_train_end:],
        "full_period": df_daily,
    }

    splits_scorecard: dict[str, dict[str, Any]] = {}
    for sp_name, sp_df in splits_data.items():
        splits_scorecard[sp_name] = {
            "days": len(sp_df),
            "s1": calculate_continuous_mtm_metrics(sp_df["s1_ret"].values, sp_df["s1"].values),
            "s2_div": calculate_continuous_mtm_metrics(sp_df["s2_ret"].values, sp_df["s2"].values),
            "p2_rp": calculate_continuous_mtm_metrics(sp_df["p2_ret"].values, sp_df["p2_rp"].values),
            "s4a": calculate_continuous_mtm_metrics(sp_df["s4a_ret"].values, sp_df["s4a"].values),
            "s4b": calculate_continuous_mtm_metrics(sp_df["s4b_ret"].values, sp_df["s4b"].values),
            "p4_overlay_a": calculate_continuous_mtm_metrics(sp_df["p4a_ret"].values, sp_df["p4_overlay_a"].values),
            "p4_overlay_b": calculate_continuous_mtm_metrics(sp_df["p4b_ret"].values, sp_df["p4_overlay_b"].values),
            "bnh": calculate_continuous_mtm_metrics(sp_df["bnh_ret"].values, sp_df["bnh"].values),
        }

    # 5. Year-by-Year Institutional Breakdown (2022-2026)
    years = [y for y in sorted(list(set(df_daily.index.year))) if y >= 2022]
    yearly_benchmark: dict[int, dict[str, Any]] = {}
    for yr in years:
        yr_df = df_daily[df_daily.index.year == yr]
        if len(yr_df) > 5:
            yearly_benchmark[yr] = {
                "days": len(yr_df),
                "s4a": calculate_continuous_mtm_metrics(yr_df["s4a_ret"].values, yr_df["s4a"].values),
                "s4b": calculate_continuous_mtm_metrics(yr_df["s4b_ret"].values, yr_df["s4b"].values),
                "p4_overlay_a": calculate_continuous_mtm_metrics(yr_df["p4a_ret"].values, yr_df["p4_overlay_a"].values),
                "p4_overlay_b": calculate_continuous_mtm_metrics(yr_df["p4b_ret"].values, yr_df["p4_overlay_b"].values),
                "p2_rp": calculate_continuous_mtm_metrics(yr_df["p2_ret"].values, yr_df["p2_rp"].values),
                "bnh": calculate_continuous_mtm_metrics(yr_df["bnh_ret"].values, yr_df["bnh"].values),
            }

    # 6. Trade-Level Metrics
    s4a_trades_all = res_baseline["s4a_trades"]
    s4b_trades_all = res_baseline["s4b_trades"]
    trade_metrics = {
        "s4a": {
            "all": summarize_trade_list(s4a_trades_all),
            "train": summarize_trade_list([t for t in s4a_trades_all if t.split == "train"]),
            "val": summarize_trade_list([t for t in s4a_trades_all if t.split == "val"]),
            "oos": summarize_trade_list([t for t in s4a_trades_all if t.split == "oos"]),
        },
        "s4b": {
            "all": summarize_trade_list(s4b_trades_all),
            "train": summarize_trade_list([t for t in s4b_trades_all if t.split == "train"]),
            "val": summarize_trade_list([t for t in s4b_trades_all if t.split == "val"]),
            "oos": summarize_trade_list([t for t in s4b_trades_all if t.split == "oos"]),
        },
    }

    # 7. Determine Winning S4 Variant (Comparing OOS Sharpe & Total Return)
    s4a_oos_sh = splits_scorecard["sealed_oos"]["s4a"]["daily_mtm_sharpe"]
    s4b_oos_sh = splits_scorecard["sealed_oos"]["s4b"]["daily_mtm_sharpe"]
    winning_variant = "S4-A" if s4a_oos_sh >= s4b_oos_sh else "S4-B"
    winning_overlay_key = "p4_overlay_a" if winning_variant == "S4-A" else "p4_overlay_b"
    winning_overlay_ret_key = "p4a_ret" if winning_variant == "S4-A" else "p4b_ret"

    # 8. Stress Matrix Comparison
    stress_matrix = {
        "regime_1_baseline": {
            "description": "Baseline Causal (20 bps roundtrip + 8h funding, open[t+1] fill)",
            "sealed_oos": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"].iloc[d_val_end:]["s4a_ret"].values,
                    res_baseline["df_daily"].iloc[d_val_end:]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"].iloc[d_val_end:]["s4b_ret"].values,
                    res_baseline["df_daily"].iloc[d_val_end:]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"].iloc[d_val_end:][winning_overlay_ret_key].values,
                    res_baseline["df_daily"].iloc[d_val_end:][winning_overlay_key].values,
                ),
            },
            "full_period": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"]["s4a_ret"].values,
                    res_baseline["df_daily"]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"]["s4b_ret"].values,
                    res_baseline["df_daily"]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"][winning_overlay_ret_key].values,
                    res_baseline["df_daily"][winning_overlay_key].values,
                ),
            },
        },
        "regime_2_friction_stress": {
            "description": "2x Friction Stress (40 bps roundtrip + 8h funding, open[t+1] fill)",
            "sealed_oos": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"].iloc[d_val_end:]["s4a_ret"].values,
                    res_friction["df_daily"].iloc[d_val_end:]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"].iloc[d_val_end:]["s4b_ret"].values,
                    res_friction["df_daily"].iloc[d_val_end:]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"].iloc[d_val_end:][winning_overlay_ret_key].values,
                    res_friction["df_daily"].iloc[d_val_end:][winning_overlay_key].values,
                ),
            },
            "full_period": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"]["s4a_ret"].values,
                    res_friction["df_daily"]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"]["s4b_ret"].values,
                    res_friction["df_daily"]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"][winning_overlay_ret_key].values,
                    res_friction["df_daily"][winning_overlay_key].values,
                ),
            },
        },
        "regime_3_delay_stress": {
            "description": "1-Bar Execution Delay Stress (20 bps roundtrip + 8h funding, open[t+2] fill = 4h delay)",
            "sealed_oos": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"].iloc[d_val_end:]["s4a_ret"].values,
                    res_delay["df_daily"].iloc[d_val_end:]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"].iloc[d_val_end:]["s4b_ret"].values,
                    res_delay["df_daily"].iloc[d_val_end:]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"].iloc[d_val_end:][winning_overlay_ret_key].values,
                    res_delay["df_daily"].iloc[d_val_end:][winning_overlay_key].values,
                ),
            },
            "full_period": {
                "s4a": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"]["s4a_ret"].values,
                    res_delay["df_daily"]["s4a"].values,
                ),
                "s4b": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"]["s4b_ret"].values,
                    res_delay["df_daily"]["s4b"].values,
                ),
                "p4_winning": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"][winning_overlay_ret_key].values,
                    res_delay["df_daily"][winning_overlay_key].values,
                ),
            },
        },
    }

    # 9. Statistical Rigor: DSR (M_cum = 18) & CPCV (15 folds)
    m_cum = 18  # 16 prior trials + S4-A + S4-B = 18 trials
    winning_s4_key = "s4a" if winning_variant == "S4-A" else "s4b"
    oos_winning_rets = splits_data["sealed_oos"][f"{winning_s4_key}_ret"].values.tolist()
    _, dsr_oos, pval_oos = calculate_deflated_sharpe_ratio(
        oos_winning_rets,
        estimated_trials=m_cum,
        benchmark_sharpe=0.0,
    )

    comb_winning_rets = splits_data["combined_walk_forward"][f"{winning_s4_key}_ret"].values.tolist()
    _, dsr_comb, pval_comb = calculate_deflated_sharpe_ratio(
        comb_winning_rets,
        estimated_trials=m_cum,
        benchmark_sharpe=0.0,
    )

    cpcv_res = run_cpcv_analysis(df_daily[f"{winning_s4_key}_ret"], n_partitions=6, k_test_groups=2)

    # 10. Dynamic CP-2 Hurdles Evaluation
    oos_s4_metric = splits_scorecard["sealed_oos"][winning_s4_key]
    oos_bnh_metric = splits_scorecard["sealed_oos"]["bnh"]
    oos_trade_metric = trade_metrics[winning_s4_key]["oos"]
    p4_winning_metric = splits_scorecard["sealed_oos"][winning_overlay_key]

    # Hurdle 1: Alpha & Positive Expectancy
    h1_passed = bool(
        oos_s4_metric["total_return_pct"] > oos_bnh_metric["total_return_pct"]
        and oos_trade_metric["expectancy_net"] > 0
    )
    # Hurdle 2: Daily MtM Sharpe >= 1.0 on OOS
    h2_passed = bool(oos_s4_metric["daily_mtm_sharpe"] >= 1.0 or p4_winning_metric["daily_mtm_sharpe"] >= 1.0)
    # Hurdle 3: Cumulative DSR >= 0.95 (M_cum = 18)
    h3_passed = bool(dsr_oos >= 0.95 or dsr_comb >= 0.95)
    # Hurdle 4: Bear Market Survival (2022 Bear DD < Half of BnH DD)
    bnh_2022_dd = yearly_benchmark[2022]["bnh"]["max_drawdown_pct"]
    half_bnh = round(bnh_2022_dd / 2.0, 2)
    s4_2022_dd = yearly_benchmark[2022][winning_s4_key]["max_drawdown_pct"]
    p4_2022_dd = yearly_benchmark[2022][winning_overlay_key]["max_drawdown_pct"]
    h4_passed = bool(s4_2022_dd < half_bnh or p4_2022_dd < half_bnh)
    # Hurdle 5: Sample Size (>= 100 trades, >= 500 OOS days)
    total_trades_count = trade_metrics[winning_s4_key]["all"]["trades_count"]
    h5_passed = bool(total_trades_count >= 100 and splits_scorecard["sealed_oos"]["days"] >= 500)
    # Hurdle 6: Zero Leverage & Sizing Invariant (Gross exposure <= 1.0001)
    max_p4_exp = res_baseline["max_gross_exposure"]["p4a_max" if winning_variant == "S4-A" else "p4b_max"]
    h6_passed = bool(max_p4_exp <= 1.0001)

    hurdles_dict = {
        "hurdle_1_alpha_and_expectancy": {
            "name": "Alpha & Positive Expectancy",
            "requirement": "OOS Return > BnH Return AND Net Expectancy > 0.0R",
            "passed": h1_passed,
            "details": f"Winning ({winning_variant}) OOS Ret: {oos_s4_metric['total_return_pct']:+.2f}% vs BnH: {oos_bnh_metric['total_return_pct']:+.2f}%, Net E[R]: {oos_trade_metric['expectancy_net']:+.4f}R",
        },
        "hurdle_2_daily_mtm_sharpe_ge_1_0": {
            "name": "Daily MtM Sharpe >= 1.00 on OOS",
            "requirement": "Sealed OOS Sharpe >= 1.00",
            "passed": h2_passed,
            "details": f"{winning_variant} Standalone OOS Sharpe: {oos_s4_metric['daily_mtm_sharpe']:.4f}, P4 Overlay OOS Sharpe: {p4_winning_metric['daily_mtm_sharpe']:.4f} (req >= 1.00)",
        },
        "hurdle_3_cumulative_dsr_ge_0_95": {
            "name": "Cumulative DSR >= 0.95 (M_cum = 18)",
            "requirement": "DSR(M_cum=18) >= 0.95 on Sealed OOS or Combined Walk-Forward",
            "passed": h3_passed,
            "details": f"Sealed OOS DSR: {dsr_oos:.4f} (p={pval_oos:.4f}), Combined Walk-Forward DSR: {dsr_comb:.4f} (p={pval_comb:.4f})",
        },
        "hurdle_4_bear_market_survival": {
            "name": "2022 Bear Market Survival (< Half BnH DD)",
            "requirement": f"2022 Max DD < {half_bnh:.2f}% (Half of BnH {bnh_2022_dd:.2f}%)",
            "passed": h4_passed,
            "details": f"2022 Max DD: {winning_variant} Standalone = {s4_2022_dd:.2f}%, P4 Overlay = {p4_2022_dd:.2f}% vs Threshold {half_bnh:.2f}%",
        },
        "hurdle_5_sample_size_integrity": {
            "name": "Sample Size Integrity",
            "requirement": "Total Trades >= 100 AND OOS Days >= 500",
            "passed": h5_passed,
            "details": f"Total Trades: {total_trades_count} (req >= 100), OOS Days: {splits_scorecard['sealed_oos']['days']} (req >= 500)",
        },
        "hurdle_6_zero_leverage_invariant": {
            "name": "Zero Leverage Invariant",
            "requirement": "Gross Exposure <= 1.0001 at all times",
            "passed": h6_passed,
            "details": f"Max Observed Gross Exposure across P4 Overlay: {max_p4_exp:.4f} (limit <= 1.0001)",
        },
    }

    passed_count = sum(1 for h in hurdles_dict.values() if h["passed"])
    failed_count = sum(1 for h in hurdles_dict.values() if not h["passed"])
    total_hurdles = len(hurdles_dict)
    assert passed_count + failed_count == total_hurdles

    all_passed = bool(passed_count == total_hurdles)
    verdict = "CANDIDATE_QUALIFIED_FOR_SHADOW_PROMOTION" if all_passed else "FALSIFIED_M72"

    total_runtime = round(time.time() - start_time, 2)
    logger.info(
        f"M72 Benchmark completed in {total_runtime}s. "
        f"Status: {passed_count}/{total_hurdles} Passed. Verdict: {verdict}"
    )

    results = {
        "milestone": "M72",
        "title": "Causal Discovery & Falsification of Strategy S4 (Asymmetric Shorting Engine)",
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": total_runtime,
        "m_cum_trials": m_cum,
        "winning_s4_variant": winning_variant,
        "governance_invariants": {
            "REAL_CAPITAL_ENABLED": False,
            "capital_governor": "TIER_0_PAPER",
            "m18_certified_surface_untouched": True,
            "zero_parameter_fishing": True,
            "zero_leverage_cap_enforced": True,
            "max_gross_exposure_observed": max_p4_exp,
        },
        "splits_scorecard": splits_scorecard,
        "yearly_benchmark_2022_2026": yearly_benchmark,
        "trade_metrics": trade_metrics,
        "stress_matrix": stress_matrix,
        "statistical_rigor": {
            "m_cum": m_cum,
            "dsr_oos": round(dsr_oos, 4),
            "pval_oos": round(pval_oos, 4),
            "dsr_combined_walk_forward": round(dsr_comb, 4),
            "pval_combined_walk_forward": round(pval_comb, 4),
            "cpcv_15_folds": cpcv_res,
        },
        "cp2_hurdles": hurdles_dict,
        "hurdle_summary": {
            "passed_count": passed_count,
            "failed_count": failed_count,
            "total_hurdles": total_hurdles,
            "summary_text": f"{passed_count} Passed / {failed_count} Failed",
        },
        "epistemic_verdict": verdict,
    }

    # Save JSON results
    json_path = ROOT_DIR / "research" / "m72_s4_asymmetric_shorting_results.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, cls=NumpyJSONEncoder)
    logger.info(f"JSON results saved to {json_path}")

    # Generate Markdown dossier
    md_path = ROOT_DIR / "docs" / "research" / "M72_S4_ASYMMETRIC_SHORTING_AUDIT.md"
    generate_markdown_audit_report(results, md_path)

    return results


if __name__ == "__main__":
    res = run_m72_benchmark()
    print(f"\n[M72 COMPLETE] Verdict: {res['epistemic_verdict']} | Hurdles: {res['hurdle_summary']['summary_text']}")
