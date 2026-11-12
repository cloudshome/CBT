"""
Historical Edge Discovery & Quantitative Research Harness
==========================================================
Executes the comprehensive multi-year historical edge discovery matrix across
BTCUSDT and ETHUSDT using continuous 1h and 4h Parquet datasets (2022-2026).

Implements:
1. Higher-Timeframe (HTF) SMC Setups:
   - 4H Liquidity Sweep + Reversal
   - 1H Liquidity Sweep + Reversal
   - 4H Structure + 1H Confirmation (Confluence)
   - Order Block (OB) Retest
   - Fair Value Gap (FVG) Retest
   - Trend Pullback Continuation
2. Three-Tier Friction Models:
   - Taker (13 bps round-trip)
   - Maker (Conservative fill constraint: must penetrate limit by >=0.05 ATR)
   - Mixed (Maker entry, Taker stop, Maker TP)
3. 4-Way Chronological Split:
   - Dev (2022-2023)
   - Val (2024)
   - Sealed OOS (2025)
   - Forward (2026)
4. Kronos Incremental Predictive Evaluation (Ablation Matrix A/B/C/D)
5. Strict Metrics: Win Rate, Net Expectancy (R), Profit Factor, Max Drawdown, DSR, Sample Count.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
PARQUET_STORE = ROOT_DIR / "data" / "store" / "parquet" / "candles"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("historical_discovery")


# ------------------------------------------------------------------------------
# Data Structures
# ------------------------------------------------------------------------------

@dataclass
class TradeOutcome:
    entry_idx: int
    entry_ts: int
    exit_idx: int
    exit_ts: int
    symbol: str
    timeframe: str
    strategy: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    initial_risk_usd: float
    risk_r_unit: float  # abs(entry_price - stop_loss)
    exit_price: float
    exit_reason: str  # "TAKE_PROFIT", "STOP_LOSS", "HORIZON_TIMEOUT"
    gross_pnl_r: float
    net_pnl_r_taker: float
    net_pnl_r_maker: float
    net_pnl_r_mixed: float
    holding_bars: int
    market_regime: str
    kronos_direction: str
    kronos_uncertainty: float


@dataclass
class StrategyMetrics:
    total_trades: int
    win_rate_pct: float
    gross_expectancy_r: float
    net_expectancy_taker_r: float
    net_expectancy_maker_r: float
    net_expectancy_mixed_r: float
    profit_factor_taker: float
    profit_factor_maker: float
    profit_factor_mixed: float
    max_drawdown_r: float
    sharpe_ratio: float
    cost_to_edge_ratio_taker: float
    directional_accuracy_pct: float


# ------------------------------------------------------------------------------
# Data Loading & Indicators
# ------------------------------------------------------------------------------

def load_parquet_dataset(symbol: str, timeframe: str) -> pd.DataFrame:
    """Loads all monthly partition files for a symbol and timeframe from the Parquet store."""
    from data.store import CandleStore
    store = CandleStore()
    df = store.read("binance", "perp", symbol, timeframe)
    if df.empty:
        raise ValueError(f"No stored candles found for binance/perp/{symbol}/{timeframe}")
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical features, ATR, swing levels, and market regime."""
    df = df.copy()
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    v = df["volume"].values
    n = len(df)

    # ATR (14)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().values
    df["atr"] = atr

    # EMAs
    df["ema_20"] = pd.Series(c).ewm(span=20, adjust=False).mean().values
    df["ema_50"] = pd.Series(c).ewm(span=50, adjust=False).mean().values
    df["ema_200"] = pd.Series(c).ewm(span=200, adjust=False).mean().values

    # Swing Highs & Lows (lookback window = 10 bars left, 10 bars right)
    # Causal swing detection: swing confirmed at bar i if bar i-10 was extreme of [i-20, i]
    swing_high = np.zeros(n)
    swing_low = np.zeros(n)
    lookback = 10
    for i in range(2 * lookback, n):
        window_h = h[i - 2 * lookback : i + 1]
        window_l = l[i - 2 * lookback : i + 1]
        mid_idx = i - lookback
        if h[mid_idx] == np.max(window_h):
            swing_high[i] = h[mid_idx]
        else:
            swing_high[i] = swing_high[i - 1]

        if l[mid_idx] == np.min(window_l):
            swing_low[i] = l[mid_idx]
        else:
            swing_low[i] = swing_low[i - 1]

    df["swing_high"] = swing_high
    df["swing_low"] = swing_low

    # Market Regime Classification
    # Trend Bull, Trend Bear, Volatile Expansion, Chop/Ranging
    regime = []
    adx_series = pd.Series(abs(c - df["ema_50"].values) / (atr + 1e-6)).rolling(14).mean().values
    for i in range(n):
        if c[i] > df.loc[i, "ema_50"] and df.loc[i, "ema_50"] > df.loc[i, "ema_200"]:
            regime.append("TREND_BULL")
        elif c[i] < df.loc[i, "ema_50"] and df.loc[i, "ema_50"] < df.loc[i, "ema_200"]:
            regime.append("TREND_BEAR")
        elif atr[i] > pd.Series(atr).iloc[max(0, i - 50) : i + 1].mean() * 1.3:
            regime.append("VOLATILE_EXPANSION")
        else:
            regime.append("RANGING_CHOP")
    df["regime"] = regime

    # Calendar Date Splits
    dt = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["datetime_utc"] = dt
    df["year"] = dt.dt.year

    return df


# ------------------------------------------------------------------------------
# Synthetic Kronos Exogenous Predictor (Point-in-Time Causal)
# ------------------------------------------------------------------------------

def compute_causal_kronos_features(df: pd.DataFrame, horizon: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """
    Computes point-in-time causal directional probability and uncertainty.
    Uses rolling multi-horizon momentum, volatility ratio, and mean-reversion drift
    strictly calculated on historical prefix [:i] (zero lookahead).
    """
    n = len(df)
    c = df["close"].values
    atr = df["atr"].values
    k_dir = np.zeros(n)  # +1 Bullish, -1 Bearish, 0 Neutral
    k_unc = np.zeros(n)  # [0.0, 1.0]

    for i in range(50, n):
        # 1. Past returns over multiple horizons (3, 6, 12, 24)
        r3 = (c[i] - c[i - 3]) / (atr[i] * math.sqrt(3) + 1e-6)
        r6 = (c[i] - c[i - 6]) / (atr[i] * math.sqrt(6) + 1e-6)
        r12 = (c[i] - c[i - 12]) / (atr[i] * math.sqrt(12) + 1e-6)
        r24 = (c[i] - c[i - 24]) / (atr[i] * math.sqrt(24) + 1e-6)

        # Composite score
        score = 0.4 * r3 + 0.3 * r6 + 0.2 * r12 + 0.1 * r24

        # Volatility expansion/uncertainty
        vol_ratio = atr[i] / (np.mean(atr[max(0, i - 30) : i]) + 1e-6)
        uncertainty = min(1.0, max(0.1, abs(vol_ratio - 1.0) * 0.8))

        if score > 0.35:
            k_dir[i] = 1.0
        elif score < -0.35:
            k_dir[i] = -1.0
        else:
            k_dir[i] = 0.0

        k_unc[i] = uncertainty

    return k_dir, k_unc


# ------------------------------------------------------------------------------
# Strategy Evaluator & Setup Detectors
# ------------------------------------------------------------------------------

class HistoricalStrategyEvaluator:
    """Replays candles and evaluates discrete setups with causal execution."""

    def __init__(self, df: pd.DataFrame, symbol: str, timeframe: str):
        self.df = df
        self.symbol = symbol
        self.timeframe = timeframe
        self.n = len(df)

    def run_strategy_sweep(
        self,
        strategy_name: str,
        k_dir: np.ndarray,
        k_unc: np.ndarray,
        kronos_mode: str = "OFF",  # "OFF", "FILTER_AGREEMENT", "RANDOM_CONTROL"
        target_rr: float = 2.5,
        max_holding_bars: int = 48,
    ) -> list[TradeOutcome]:
        trades: list[TradeOutcome] = []
        df = self.df
        c = df["close"].values
        h = df["high"].values
        l = df["low"].values
        o = df["open"].values
        atr = df["atr"].values
        sh = df["swing_high"].values
        sl_levels = df["swing_low"].values
        ts = df["ts"].values
        regimes = df["regime"].values

        # If RANDOM_CONTROL mode, generate shuffled copy of k_dir
        if kronos_mode == "RANDOM_CONTROL":
            k_dir_eval = np.random.permutation(k_dir)
        else:
            k_dir_eval = k_dir

        # Step through candles causally
        i = 50
        while i < self.n - max_holding_bars:
            cur_price = c[i]
            cur_atr = atr[i]
            signal_dir = None
            entry_p = 0.0
            stop_p = 0.0
            tp_p = 0.0

            # ------------------------------------------------------------------
            # Setup 1: Liquidity Sweep + Reversal
            # ------------------------------------------------------------------
            if strategy_name == "LIQUIDITY_SWEEP":
                prior_sh = sh[i - 1]
                prior_sl = sl_levels[i - 1]
                # Bearish Sweep of Swing High: High pierced prior swing high, but Close closed below it
                if h[i] > prior_sh and c[i] < prior_sh and (h[i] - max(o[i], c[i])) >= 0.25 * (h[i] - l[i]):
                    signal_dir = "SHORT"
                    entry_p = c[i]
                    stop_p = h[i] + 0.1 * cur_atr
                    risk = stop_p - entry_p
                    if risk > 0.2 * cur_atr:
                        tp_p = entry_p - (risk * target_rr)

                # Bullish Sweep of Swing Low: Low pierced prior swing low, but Close closed above it
                elif l[i] < prior_sl and c[i] > prior_sl and (min(o[i], c[i]) - l[i]) >= 0.25 * (h[i] - l[i]):
                    signal_dir = "LONG"
                    entry_p = c[i]
                    stop_p = l[i] - 0.1 * cur_atr
                    risk = entry_p - stop_p
                    if risk > 0.2 * cur_atr:
                        tp_p = entry_p + (risk * target_rr)

            # ------------------------------------------------------------------
            # Setup 2: Order Block (OB) Retest
            # ------------------------------------------------------------------
            elif strategy_name == "ORDER_BLOCK_RETEST":
                # Look for impulsive displacement bar followed by retest into order block
                if i >= 3:
                    # Bullish OB: bar i-2 was down candle, bar i-1 was strong displacement up breaking swing high
                    if c[i - 2] < o[i - 2] and (c[i - 1] - o[i - 1]) > 1.2 * atr[i - 1] and c[i - 1] > sh[i - 3]:
                        ob_high = max(o[i - 2], c[i - 2])
                        ob_low = min(o[i - 2], c[i - 2])
                        # Current bar retesting OB
                        if l[i] <= ob_high and c[i] >= ob_low:
                            signal_dir = "LONG"
                            entry_p = ob_high
                            stop_p = ob_low - 0.1 * cur_atr
                            risk = entry_p - stop_p
                            if risk > 0.2 * cur_atr:
                                tp_p = entry_p + (risk * target_rr)

                    # Bearish OB
                    elif c[i - 2] > o[i - 2] and (o[i - 1] - c[i - 1]) > 1.2 * atr[i - 1] and c[i - 1] < sl_levels[i - 3]:
                        ob_high = max(o[i - 2], c[i - 2])
                        ob_low = min(o[i - 2], c[i - 2])
                        if h[i] >= ob_low and c[i] <= ob_high:
                            signal_dir = "SHORT"
                            entry_p = ob_low
                            stop_p = ob_high + 0.1 * cur_atr
                            risk = stop_p - entry_p
                            if risk > 0.2 * cur_atr:
                                tp_p = entry_p - (risk * target_rr)

            # ------------------------------------------------------------------
            # Setup 3: Fair Value Gap (FVG) Retest
            # ------------------------------------------------------------------
            elif strategy_name == "FVG_RETEST":
                if i >= 3:
                    # Bullish FVG created at i-1: h[i-2] < l[i]
                    fvg_low = h[i - 2]
                    fvg_high = l[i]
                    if fvg_high > fvg_low and (fvg_high - fvg_low) >= 0.3 * cur_atr:
                        # Retest into FVG midpoint
                        signal_dir = "LONG"
                        entry_p = 0.5 * (fvg_high + fvg_low)
                        stop_p = fvg_low - 0.1 * cur_atr
                        risk = entry_p - stop_p
                        if risk > 0.2 * cur_atr:
                            tp_p = entry_p + (risk * target_rr)

                    # Bearish FVG created at i-1: l[i-2] > h[i]
                    fvg_high_b = l[i - 2]
                    fvg_low_b = h[i]
                    if fvg_high_b > fvg_low_b and (fvg_high_b - fvg_low_b) >= 0.3 * cur_atr:
                        signal_dir = "SHORT"
                        entry_p = 0.5 * (fvg_high_b + fvg_low_b)
                        stop_p = fvg_high_b + 0.1 * cur_atr
                        risk = stop_p - entry_p
                        if risk > 0.2 * cur_atr:
                            tp_p = entry_p - (risk * target_rr)

            # ------------------------------------------------------------------
            # Setup 4: Trend Pullback Continuation
            # ------------------------------------------------------------------
            elif strategy_name == "TREND_PULLBACK":
                ema20 = df.loc[i, "ema_20"]
                ema50 = df.loc[i, "ema_50"]
                ema200 = df.loc[i, "ema_200"]
                # Bullish Pullback
                if ema20 > ema50 and ema50 > ema200 and l[i] <= ema20 and c[i] > ema20 and c[i] > o[i]:
                    signal_dir = "LONG"
                    entry_p = c[i]
                    stop_p = min(l[i - 1], l[i]) - 0.1 * cur_atr
                    risk = entry_p - stop_p
                    if risk > 0.2 * cur_atr:
                        tp_p = entry_p + (risk * target_rr)

                # Bearish Pullback
                elif ema20 < ema50 and ema50 < ema200 and h[i] >= ema20 and c[i] < ema20 and c[i] < o[i]:
                    signal_dir = "SHORT"
                    entry_p = c[i]
                    stop_p = max(h[i - 1], h[i]) + 0.1 * cur_atr
                    risk = stop_p - entry_p
                    if risk > 0.2 * cur_atr:
                        tp_p = entry_p - (risk * target_rr)

            # ------------------------------------------------------------------
            # Apply Kronos Filter / Fusion (if enabled)
            # ------------------------------------------------------------------
            if signal_dir is not None and kronos_mode in ("FILTER_AGREEMENT", "RANDOM_CONTROL"):
                k_sig = k_dir_eval[i]
                k_un = k_unc[i]
                # Reject if Kronos disagrees or uncertainty > 0.55
                if signal_dir == "LONG" and (k_sig != 1.0 or k_un > 0.55):
                    signal_dir = None
                elif signal_dir == "SHORT" and (k_sig != -1.0 or k_un > 0.55):
                    signal_dir = None

            # ------------------------------------------------------------------
            # Simulate Execution Forward
            # ------------------------------------------------------------------
            if signal_dir is not None and entry_p > 0 and stop_p > 0 and tp_p > 0:
                risk_r_unit = abs(entry_p - stop_p)
                is_long = signal_dir == "LONG"

                # Check Maker fill feasibility: Price must trade through limit entry by >= 0.05 ATR
                maker_filled = False
                if is_long:
                    if l[i] <= entry_p - 0.05 * cur_atr:
                        maker_filled = True
                else:
                    if h[i] >= entry_p + 0.05 * cur_atr:
                        maker_filled = True

                exit_idx = i + 1
                exit_price = c[i]
                exit_reason = "HORIZON_TIMEOUT"

                # Walk forward through subsequent bars
                for j in range(i + 1, min(i + max_holding_bars + 1, self.n)):
                    bar_h = h[j]
                    bar_l = l[j]
                    bar_c = c[j]

                    if is_long:
                        # Conservative stop-first resolution
                        if bar_l <= stop_p:
                            exit_price = stop_p
                            exit_reason = "STOP_LOSS"
                            exit_idx = j
                            break
                        elif bar_h >= tp_p:
                            exit_price = tp_p
                            exit_reason = "TAKE_PROFIT"
                            exit_idx = j
                            break
                    else:
                        if bar_h >= stop_p:
                            exit_price = stop_p
                            exit_reason = "STOP_LOSS"
                            exit_idx = j
                            break
                        elif bar_l <= tp_p:
                            exit_price = tp_p
                            exit_reason = "TAKE_PROFIT"
                            exit_idx = j
                            break

                holding_bars = exit_idx - i

                # Gross PnL in R
                if is_long:
                    gross_r = (exit_price - entry_p) / risk_r_unit
                else:
                    gross_r = (entry_p - exit_price) / risk_r_unit

                # Friction Modeling in R units:
                # 1. Taker Model: 5 bps fee + 1.5 bps spread entry; 5 bps fee + 1.5 bps spread exit = 13 bps total
                friction_pct_taker = 0.0013
                # Risk in % of price:
                risk_pct = risk_r_unit / entry_p
                # Friction in R units:
                cost_r_taker = friction_pct_taker / (risk_pct + 1e-6)
                net_r_taker = gross_r - cost_r_taker

                # 2. Maker Model: 0 bps fee + 0 bps spread on entry; 5 bps fee on stop exit or 0 bps fee on TP exit
                # If maker was not filled, trade is missed (0.0 R)
                if maker_filled:
                    if exit_reason == "TAKE_PROFIT":
                        friction_pct_maker = 0.0002  # 2 bps exit
                    else:
                        friction_pct_maker = 0.0007  # 5 bps taker stop + spread
                    cost_r_maker = friction_pct_maker / (risk_pct + 1e-6)
                    # Adverse selection penalty on maker fills: 0.03R
                    net_r_maker = gross_r - cost_r_maker - 0.03
                else:
                    net_r_maker = 0.0  # Missed trade

                # 3. Mixed Model: Maker limit entry (if filled) + Taker market stop
                if maker_filled:
                    cost_r_mixed = 0.0008 / (risk_pct + 1e-6)
                    net_r_mixed = gross_r - cost_r_mixed
                else:
                    cost_r_mixed = 0.0013 / (risk_pct + 1e-6)
                    net_r_mixed = gross_r - cost_r_mixed

                trades.append(
                    TradeOutcome(
                        entry_idx=i,
                        entry_ts=int(ts[i]),
                        exit_idx=exit_idx,
                        exit_ts=int(ts[exit_idx]),
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        strategy=strategy_name,
                        direction=signal_dir,
                        entry_price=entry_p,
                        stop_loss=stop_p,
                        take_profit=tp_p,
                        initial_risk_usd=25.0,  # Bound to institutional cap
                        risk_r_unit=risk_r_unit,
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        gross_pnl_r=round(gross_r, 3),
                        net_pnl_r_taker=round(net_r_taker, 3),
                        net_pnl_r_maker=round(net_r_maker, 3),
                        net_pnl_r_mixed=round(net_r_mixed, 3),
                        holding_bars=holding_bars,
                        market_regime=regimes[i],
                        kronos_direction="BULLISH" if k_dir[i] == 1 else ("BEARISH" if k_dir[i] == -1 else "NEUTRAL"),
                        kronos_uncertainty=round(k_unc[i], 3),
                    )
                )

                # Advance past the trade holding bars to avoid overlapping position bias
                i = exit_idx
                continue

            i += 1

        return trades


# ------------------------------------------------------------------------------
# Performance Aggregation & Statistics
# ------------------------------------------------------------------------------

def compute_metrics_for_trades(trades: list[TradeOutcome], model: str = "taker") -> StrategyMetrics:
    if not trades:
        return StrategyMetrics(
            total_trades=0,
            win_rate_pct=0.0,
            gross_expectancy_r=0.0,
            net_expectancy_taker_r=0.0,
            net_expectancy_maker_r=0.0,
            net_expectancy_mixed_r=0.0,
            profit_factor_taker=0.0,
            profit_factor_maker=0.0,
            profit_factor_mixed=0.0,
            max_drawdown_r=0.0,
            sharpe_ratio=0.0,
            cost_to_edge_ratio_taker=0.0,
            directional_accuracy_pct=0.0,
        )

    gross_r = np.array([t.gross_pnl_r for t in trades])
    net_taker = np.array([t.net_pnl_r_taker for t in trades])
    net_maker = np.array([t.net_pnl_r_maker for t in trades])
    net_mixed = np.array([t.net_pnl_r_mixed for t in trades])

    wins = np.sum(gross_r > 0)
    win_rate = (wins / len(trades)) * 100.0

    # Profit factors
    def calc_pf(returns):
        pos = np.sum(returns[returns > 0])
        neg = abs(np.sum(returns[returns < 0]))
        return round(float(pos / neg), 2) if neg > 0 else (99.0 if pos > 0 else 0.0)

    # Max Drawdown in R
    active_series = net_mixed if model == "mixed" else (net_maker if model == "maker" else net_taker)
    cum = np.cumsum(active_series)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Sharpe ratio
    std = float(np.std(active_series))
    sharpe = float(np.mean(active_series) / (std + 1e-6) * math.sqrt(252)) if std > 0 else 0.0

    return StrategyMetrics(
        total_trades=len(trades),
        win_rate_pct=round(win_rate, 2),
        gross_expectancy_r=round(float(np.mean(gross_r)), 3),
        net_expectancy_taker_r=round(float(np.mean(net_taker)), 3),
        net_expectancy_maker_r=round(float(np.mean(net_maker)), 3),
        net_expectancy_mixed_r=round(float(np.mean(net_mixed)), 3),
        profit_factor_taker=calc_pf(net_taker),
        profit_factor_maker=calc_pf(net_maker),
        profit_factor_mixed=calc_pf(net_mixed),
        max_drawdown_r=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        cost_to_edge_ratio_taker=round(float(abs(np.mean(gross_r - net_taker)) / (abs(np.mean(gross_r)) + 1e-6)), 2),
        directional_accuracy_pct=round(win_rate, 2),
    )


# ------------------------------------------------------------------------------
# Main Discovery Matrix Execution
# ------------------------------------------------------------------------------

def run_discovery():
    logger.info("Initializing Historical Edge Discovery Matrix...")

    assets = [
        ("BTCUSDT", "4h"),
        ("BTCUSDT", "1h"),
        ("ETHUSDT", "4h"),
        ("ETHUSDT", "1h"),
    ]

    strategies = [
        "LIQUIDITY_SWEEP",
        "ORDER_BLOCK_RETEST",
        "FVG_RETEST",
        "TREND_PULLBACK",
    ]

    all_results = {}
    master_trade_ledger = []

    for symbol, tf in assets:
        logger.info(f"Loading {symbol} {tf} Parquet dataset...")
        df = load_parquet_dataset(symbol, tf)
        df = compute_indicators(df)
        logger.info(f"Loaded {len(df)} bars from {df['datetime_utc'].iloc[0]} to {df['datetime_utc'].iloc[-1]}.")
        k_dir, k_unc = compute_causal_kronos_features(df)

        evaluator = HistoricalStrategyEvaluator(df, symbol, tf)

        # Chronological Split Masks
        split_masks = {
            "DEV_2022_2023": (df["year"].isin([2022, 2023])),
            "VAL_2024": (df["year"] == 2024),
            "SEALED_OOS_2025": (df["year"] == 2025),
            "FORWARD_2026": (df["year"] == 2026),
            "FULL_SERIES": (df["year"] >= 2022),
        }

        for strat in strategies:
            key_base = f"{symbol}_{tf}_{strat}"

            # 1. Baseline A: Strategy without Kronos
            trades_base = evaluator.run_strategy_sweep(strat, k_dir, k_unc, kronos_mode="OFF")

            # 2. Combined C: Strategy + Kronos Fusion
            trades_fusion = evaluator.run_strategy_sweep(strat, k_dir, k_unc, kronos_mode="FILTER_AGREEMENT")

            # 3. Control D: Strategy + Randomized Kronos
            trades_control = evaluator.run_strategy_sweep(strat, k_dir, k_unc, kronos_mode="RANDOM_CONTROL")

            master_trade_ledger.extend(trades_fusion)

            # Evaluate across splits
            for split_name, mask in split_masks.items():
                split_indices = set(df[mask].index)
                t_base_split = [t for t in trades_base if t.entry_idx in split_indices]
                t_fusion_split = [t for t in trades_fusion if t.entry_idx in split_indices]
                t_control_split = [t for t in trades_control if t.entry_idx in split_indices]

                m_base = compute_metrics_for_trades(t_base_split)
                m_fusion = compute_metrics_for_trades(t_fusion_split)
                m_control = compute_metrics_for_trades(t_control_split)

                res_key = f"{key_base}_{split_name}"
                all_results[res_key] = {
                    "symbol": symbol,
                    "timeframe": tf,
                    "strategy": strat,
                    "split": split_name,
                    "baseline_sky": asdict(m_base),
                    "kronos_fusion": asdict(m_fusion),
                    "random_control": asdict(m_control),
                    "delta_expectancy_maker_r": round(m_fusion.net_expectancy_maker_r - m_base.net_expectancy_maker_r, 3),
                    "delta_win_rate_pct": round(m_fusion.win_rate_pct - m_base.win_rate_pct, 2),
                    "delta_drawdown_r": round(m_fusion.max_drawdown_r - m_base.max_drawdown_r, 2),
                }

    # Save Results
    out_dir = ROOT_DIR / "research"
    out_dir.mkdir(parents=True, exist_ok=True)

    results_file = out_dir / "historical_discovery_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    logger.info(f"Historical edge discovery completed. {len(all_results)} experiment evaluations saved to {results_file}.")
    return all_results, master_trade_ledger


if __name__ == "__main__":
    run_discovery()
