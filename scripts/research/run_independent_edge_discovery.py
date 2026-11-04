"""
Independent Trading Edge Discovery Engine (M36)
==============================================
Systematically evaluates 3 distinct, falsifiable research families across
4.8 years of continuous 1H and 4H Binance Perpetual Parquet datasets:
- Family 1: Trend Continuation & Dynamic Value Pullback
- Family 2: Volatility Compression & Breakout Expansion (Squeeze Breakout)
- Family 3: Liquidity Sweep & Failed Breakout Reversal (Turtle Soup Reclaim)

Applies:
- Causal, zero-lookahead feature engineering
- 4-way chronological split (Dev 2022-2023, Val 2024, OOS 2025, Replay 2026)
- 3-tier execution models (Taker, Maker, Strict Mixed without fallback)
- Cross-strategy correlation analysis against frozen M35 Order Block benchmark
- Emits trade-level ledger and machine-readable manifests
"""

import json
import logging
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

ROOT_DIR = Path("C:/Users/azims/CBT")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.research.run_historical_edge_discovery import load_parquet_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("edge_discovery")


@dataclass
class FamilyTrade:
    trade_id: str
    family_id: str
    family_name: str
    symbol: str
    timeframe: str
    entry_idx: int
    entry_ts: int
    entry_datetime_utc: str
    exit_idx: int
    exit_ts: int
    exit_datetime_utc: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_reason: str  # "TAKE_PROFIT", "STOP_LOSS", "TIMEOUT"
    risk_r_unit: float
    gross_pnl_r: float
    net_pnl_r_taker: float
    net_pnl_r_strict_mixed: float
    maker_penetrated: bool
    holding_bars: int
    market_regime: str
    setup_features: dict[str, Any]


def compute_family_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical indicators required across all 3 families."""
    df = df.copy()
    c = df["close"].values
    h = df["high"].values
    l = df["low"].values
    o = df["open"].values
    v = df["volume"].values
    n = len(df)

    # 1. ATR (14)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().values
    df["atr"] = atr

    # 2. EMAs (20, 50, 200)
    df["ema_20"] = pd.Series(c).ewm(span=20, adjust=False).mean().values
    df["ema_50"] = pd.Series(c).ewm(span=50, adjust=False).mean().values
    df["ema_200"] = pd.Series(c).ewm(span=200, adjust=False).mean().values

    # 3. Bollinger Bands (20, 2.0)
    bb_mid = pd.Series(c).rolling(20, min_periods=1).mean().values
    bb_std = pd.Series(c).rolling(20, min_periods=1).std(ddof=0).fillna(0).values
    df["bb_upper"] = bb_mid + 2.0 * bb_std
    df["bb_lower"] = bb_mid - 2.0 * bb_std
    df["bb_mid"] = bb_mid

    # 4. Keltner Channels (20, 1.5 ATR)
    df["kc_upper"] = df["ema_20"].values + 1.5 * atr
    df["kc_lower"] = df["ema_20"].values - 1.5 * atr

    # Squeeze Indicator: BB inside KC
    df["in_squeeze"] = (df["bb_upper"] < df["kc_upper"]) & (df["bb_lower"] > df["kc_lower"])

    # 5. Volume SMA (20)
    df["vol_sma_20"] = pd.Series(v).rolling(20, min_periods=1).mean().values

    # 6. Swing Highs & Lows (10 bars left, 10 bars right causal)
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

    # 7. ADX (14) for trend strength
    up_move = h[1:] - h[:-1]
    down_move = l[:-1] - l[1:]
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        if up_move[i - 1] > down_move[i - 1] and up_move[i - 1] > 0:
            plus_dm[i] = up_move[i - 1]
        if down_move[i - 1] > up_move[i - 1] and down_move[i - 1] > 0:
            minus_dm[i] = down_move[i - 1]
    plus_di = 100 * pd.Series(plus_dm).rolling(14, min_periods=1).mean() / (pd.Series(atr) + 1e-6)
    minus_di = 100 * pd.Series(minus_dm).rolling(14, min_periods=1).mean() / (pd.Series(atr) + 1e-6)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-6)
    df["adx"] = dx.rolling(14, min_periods=1).mean().values

    # 8. Date & Year splits
    dt = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["datetime_utc"] = dt
    df["year"] = dt.dt.year

    return df


class ResearchTrackEvaluator:
    """Evaluates the three research tracks causally across historical series."""

    def __init__(self, df: pd.DataFrame, symbol: str, timeframe: str):
        self.df = df
        self.symbol = symbol
        self.timeframe = timeframe
        self.n = len(df)

    def evaluate_family_1_trend_pullback(self) -> list[FamilyTrade]:
        """
        Family 1: Trend Continuation & Dynamic Value Pullback.
        Hypothesis: In confirmed trends (EMA20 > EMA50 > EMA200 and ADX > 25), pullbacks
        into the EMA20-50 zone that reject (pinbar/engulfing) offer high-expectancy continuation.
        """
        trades: list[FamilyTrade] = []
        df = self.df
        c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
        atr = df["atr"].values
        ema20 = df["ema_20"].values
        ema50 = df["ema_50"].values
        ema200 = df["ema_200"].values
        adx = df["adx"].values
        ts = df["ts"].values

        i = 50
        while i < self.n - 48:
            signal_dir = None
            entry_p = 0.0
            stop_p = 0.0
            tp_p = 0.0

            # Bullish Trend Pullback:
            # 1. Trend alignment: EMA20 > EMA50 > EMA200
            # 2. Strong trend: ADX > 25
            # 3. Pullback into value zone: Low pierces EMA20, but stays above EMA50
            # 4. Rejection close: Close > EMA20 and Close > Open (bullish candle)
            if (ema20[i] > ema50[i] > ema200[i]) and adx[i] > 25.0:
                if l[i] <= ema20[i] and min(l[i - 1], l[i]) >= ema50[i] * 0.998 and c[i] > ema20[i] and c[i] > o[i]:
                    signal_dir = "LONG"
                    entry_p = c[i]
                    stop_p = min(l[i - 1], l[i]) - 0.15 * atr[i]
                    risk = entry_p - stop_p
                    if risk > 0.25 * atr[i]:
                        tp_p = entry_p + 2.5 * risk

            # Bearish Trend Pullback:
            elif (ema20[i] < ema50[i] < ema200[i]) and adx[i] > 25.0:
                if h[i] >= ema20[i] and max(h[i - 1], h[i]) <= ema50[i] * 1.002 and c[i] < ema20[i] and c[i] < o[i]:
                    signal_dir = "SHORT"
                    entry_p = c[i]
                    stop_p = max(h[i - 1], h[i]) + 0.15 * atr[i]
                    risk = stop_p - entry_p
                    if risk > 0.25 * atr[i]:
                        tp_p = entry_p - 2.5 * risk

            if signal_dir and entry_p > 0 and stop_p > 0 and tp_p > 0:
                trade = self._simulate_trade(
                    i=i,
                    family_id="FAMILY_1",
                    family_name="TREND_PULLBACK_CONTINUATION",
                    signal_dir=signal_dir,
                    entry_p=entry_p,
                    stop_p=stop_p,
                    tp_p=tp_p,
                    setup_features={"adx": float(adx[i]), "trend_type": "EMA_ALIGNED"}
                )
                trades.append(trade)
                i = trade.exit_idx
                continue
            i += 1

        return trades

    def evaluate_family_2_volatility_squeeze(self) -> list[FamilyTrade]:
        """
        Family 2: Volatility Compression & Breakout Expansion (Squeeze Breakout).
        Hypothesis: Extended consolidation (BB inside KC for >= 5 bars) releases directional
        energy when price breaks out of the band accompanied by above-average volume.
        """
        trades: list[FamilyTrade] = []
        df = self.df
        c, h, l, o, v = df["close"].values, df["high"].values, df["low"].values, df["open"].values, df["volume"].values
        atr = df["atr"].values
        bb_upper = df["bb_upper"].values
        bb_lower = df["bb_lower"].values
        bb_mid = df["bb_mid"].values
        in_squeeze = df["in_squeeze"].values
        vol_sma = df["vol_sma_20"].values

        i = 50
        while i < self.n - 48:
            signal_dir = None
            entry_p = 0.0
            stop_p = 0.0
            tp_p = 0.0

            # Require squeeze active for at least 5 of the prior 8 bars
            prior_squeeze_count = sum(in_squeeze[max(0, i - 8) : i])
            if prior_squeeze_count >= 5:
                # Bullish Breakout: Close breaks above BB upper with expanding volume
                if c[i] > bb_upper[i] and c[i] > o[i] and v[i] > 1.2 * vol_sma[i]:
                    signal_dir = "LONG"
                    entry_p = c[i]
                    stop_p = bb_mid[i] - 0.1 * atr[i]
                    risk = entry_p - stop_p
                    if risk > 0.3 * atr[i]:
                        tp_p = entry_p + 2.5 * risk

                # Bearish Breakout: Close breaks below BB lower with expanding volume
                elif c[i] < bb_lower[i] and c[i] < o[i] and v[i] > 1.2 * vol_sma[i]:
                    signal_dir = "SHORT"
                    entry_p = c[i]
                    stop_p = bb_mid[i] + 0.1 * atr[i]
                    risk = stop_p - entry_p
                    if risk > 0.3 * atr[i]:
                        tp_p = entry_p - 2.5 * risk

            if signal_dir and entry_p > 0 and stop_p > 0 and tp_p > 0:
                trade = self._simulate_trade(
                    i=i,
                    family_id="FAMILY_2",
                    family_name="VOLATILITY_SQUEEZE_EXPANSION",
                    signal_dir=signal_dir,
                    entry_p=entry_p,
                    stop_p=stop_p,
                    tp_p=tp_p,
                    setup_features={"prior_squeeze_bars": int(prior_squeeze_count), "vol_ratio": float(v[i] / (vol_sma[i] + 1e-6))}
                )
                trades.append(trade)
                i = trade.exit_idx
                continue
            i += 1

        return trades

    def evaluate_family_3_liquidity_sweep(self) -> list[FamilyTrade]:
        """
        Family 3: Liquidity Sweep & Failed Breakout Reversal (Turtle Soup Reclaim).
        Hypothesis: When price pierces a confirmed swing high/low by > 0.1 ATR but aggressively
        fails and closes back inside the range with a rejection wick >= 35% of total bar range,
        trapped breakout traders trigger a mean-reverting reversal toward range equilibrium.
        """
        trades: list[FamilyTrade] = []
        df = self.df
        c, h, l, o = df["close"].values, df["high"].values, df["low"].values, df["open"].values
        atr = df["atr"].values
        sh = df["swing_high"].values
        sl = df["swing_low"].values

        i = 50
        while i < self.n - 48:
            signal_dir = None
            entry_p = 0.0
            stop_p = 0.0
            tp_p = 0.0

            prior_sh = sh[i - 1]
            prior_sl = sl[i - 1]
            bar_range = h[i] - l[i]

            if bar_range > 0.3 * atr[i]:
                # Bearish Sweep of Swing High:
                # 1. High pierced prior swing high by >= 0.1 ATR
                # 2. Close ended back BELOW prior swing high
                # 3. Upper wick >= 35% of bar range
                upper_wick = h[i] - max(o[i], c[i])
                if h[i] >= prior_sh + 0.1 * atr[i] and c[i] < prior_sh and upper_wick >= 0.35 * bar_range:
                    signal_dir = "SHORT"
                    entry_p = c[i]
                    stop_p = h[i] + 0.1 * atr[i]
                    risk = stop_p - entry_p
                    if risk > 0.25 * atr[i]:
                        tp_p = entry_p - 2.5 * risk

                # Bullish Sweep of Swing Low:
                # 1. Low pierced prior swing low by >= 0.1 ATR
                # 2. Close ended back ABOVE prior swing low
                # 3. Lower wick >= 35% of bar range
                lower_wick = min(o[i], c[i]) - l[i]
                if l[i] <= prior_sl - 0.1 * atr[i] and c[i] > prior_sl and lower_wick >= 0.35 * bar_range:
                    signal_dir = "LONG"
                    entry_p = c[i]
                    stop_p = l[i] - 0.1 * atr[i]
                    risk = entry_p - stop_p
                    if risk > 0.25 * atr[i]:
                        tp_p = entry_p + 2.5 * risk

            if signal_dir and entry_p > 0 and stop_p > 0 and tp_p > 0:
                trade = self._simulate_trade(
                    i=i,
                    family_id="FAMILY_3",
                    family_name="LIQUIDITY_SWEEP_RECLAIM",
                    signal_dir=signal_dir,
                    entry_p=entry_p,
                    stop_p=stop_p,
                    tp_p=tp_p,
                    setup_features={"sweep_depth_atr": float((h[i] - prior_sh) / atr[i] if signal_dir == "SHORT" else (prior_sl - l[i]) / atr[i])}
                )
                trades.append(trade)
                i = trade.exit_idx
                continue
            i += 1

        return trades

    def _simulate_trade(
        self,
        i: int,
        family_id: str,
        family_name: str,
        signal_dir: str,
        entry_p: float,
        stop_p: float,
        tp_p: float,
        setup_features: dict[str, Any],
        max_holding_bars: int = 48,
    ) -> FamilyTrade:
        df = self.df
        c, h, l = df["close"].values, df["high"].values, df["low"].values
        ts = df["ts"].values
        atr = df["atr"].values
        risk_r_unit = abs(entry_p - stop_p)
        is_long = (signal_dir == "LONG")

        # Maker penetration condition: Low <= entry - 0.05 ATR for long
        maker_filled = False
        if is_long:
            if l[i] <= entry_p - 0.05 * atr[i]:
                maker_filled = True
        else:
            if h[i] >= entry_p + 0.05 * atr[i]:
                maker_filled = True

        exit_idx = i + 1
        exit_price = c[i]
        exit_reason = "TIMEOUT"

        for j in range(i + 1, min(i + max_holding_bars + 1, self.n)):
            bar_h = h[j]
            bar_l = l[j]

            if is_long:
                # Conservative stop-first
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
        gross_r = (exit_price - entry_p) / risk_r_unit if is_long else (entry_p - exit_price) / risk_r_unit

        # Friction Accounting:
        # Taker: 13 bps total
        risk_pct = risk_r_unit / entry_p
        cost_r_taker = 0.0013 / (risk_pct + 1e-6)
        net_r_taker = gross_r - cost_r_taker

        # Strict Mixed: Maker limit entry (if filled) + Taker stop. If NOT filled -> 0.0R!
        if maker_filled:
            cost_r_mixed = 0.0008 / (risk_pct + 1e-6)
            net_r_mixed = gross_r - cost_r_mixed
        else:
            net_r_mixed = 0.0

        trade_id = f"{family_id}_{self.symbol}_{self.timeframe}_{ts[i]}_{signal_dir}"
        regime = "TREND_BULL" if c[i] > df.loc[i, "ema_50"] else "TREND_BEAR"

        return FamilyTrade(
            trade_id=trade_id,
            family_id=family_id,
            family_name=family_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            entry_idx=i,
            entry_ts=int(ts[i]),
            entry_datetime_utc=datetime.fromtimestamp(ts[i] / 1000, tz=timezone.utc).isoformat(),
            exit_idx=exit_idx,
            exit_ts=int(ts[exit_idx]),
            exit_datetime_utc=datetime.fromtimestamp(ts[exit_idx] / 1000, tz=timezone.utc).isoformat(),
            direction=signal_dir,
            entry_price=round(entry_p, 2),
            stop_loss=round(stop_p, 2),
            take_profit=round(tp_p, 2),
            exit_price=round(exit_price, 2),
            exit_reason=exit_reason,
            risk_r_unit=round(risk_r_unit, 2),
            gross_pnl_r=round(gross_r, 3),
            net_pnl_r_taker=round(net_r_taker, 3),
            net_pnl_r_strict_mixed=round(net_r_mixed, 3),
            maker_penetrated=maker_filled,
            holding_bars=holding_bars,
            market_regime=regime,
            setup_features=setup_features,
        )


def compute_metrics(trades: list[FamilyTrade], model: str = "strict_mixed") -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "mean_net_r": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
            "sharpe_per_trade": 0.0,
        }
    returns = np.array([t.net_pnl_r_strict_mixed if model == "strict_mixed" else t.net_pnl_r_taker for t in trades])
    pos = np.sum(returns[returns > 0])
    neg = abs(np.sum(returns[returns < 0]))
    pf = round(float(pos / neg), 2) if neg > 0 else 99.0

    cum = np.cumsum(returns)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = round(float(np.max(dd)), 2) if len(dd) > 0 else 0.0

    std = float(np.std(returns))
    sharpe = round(float(np.mean(returns) / (std + 1e-6)), 3)

    return {
        "total_trades": len(trades),
        "win_rate_pct": round(float(np.mean(returns > 0) * 100), 1),
        "mean_net_r": round(float(np.mean(returns)), 3),
        "profit_factor": pf,
        "max_drawdown_r": max_dd,
        "sharpe_per_trade": sharpe,
    }


def main():
    logger.info("Initializing Independent Edge Discovery Engine (M36)...")
    assets = [
        ("BTCUSDT", "1h"),
        ("BTCUSDT", "4h"),
        ("ETHUSDT", "1h"),
        ("ETHUSDT", "4h"),
    ]

    all_family_trades: list[FamilyTrade] = []
    results_by_family_asset = {}

    for symbol, tf in assets:
        logger.info(f"Loading {symbol} {tf} dataset...")
        df = load_parquet_dataset(symbol, tf)
        df = compute_family_indicators(df)
        evaluator = ResearchTrackEvaluator(df, symbol, tf)

        # 1. Family 1: Trend Pullback
        t_f1 = evaluator.evaluate_family_1_trend_pullback()
        all_family_trades.extend(t_f1)

        # 2. Family 2: Volatility Squeeze
        t_f2 = evaluator.evaluate_family_2_volatility_squeeze()
        all_family_trades.extend(t_f2)

        # 3. Family 3: Liquidity Sweep
        t_f3 = evaluator.evaluate_family_3_liquidity_sweep()
        all_family_trades.extend(t_f3)

        # Compute per split metrics for each family
        split_masks = {
            "DEV_2022_2023": (df["year"].isin([2022, 2023])),
            "VAL_2024": (df["year"] == 2024),
            "SEALED_OOS_2025": (df["year"] == 2025),
            "FORWARD_2026": (df["year"] == 2026),
            "FULL_SERIES": (df["year"] >= 2022),
        }

        for fam_id, f_trades in [("FAMILY_1", t_f1), ("FAMILY_2", t_f2), ("FAMILY_3", t_f3)]:
            for split_name, mask in split_masks.items():
                split_indices = set(df[mask].index)
                t_split = [t for t in f_trades if t.entry_idx in split_indices]
                res_key = f"{fam_id}_{symbol}_{tf}_{split_name}"
                results_by_family_asset[res_key] = {
                    "family_id": fam_id,
                    "symbol": symbol,
                    "timeframe": tf,
                    "split": split_name,
                    "strict_mixed_metrics": compute_metrics(t_split, model="strict_mixed"),
                    "taker_metrics": compute_metrics(t_split, model="taker"),
                }

    # Save all trades to ledger
    research_dir = ROOT_DIR / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = research_dir / "independent_edges_trade_ledger.jsonl"
    with open(ledger_path, "w", encoding="utf-8") as f:
        for t in all_family_trades:
            f.write(json.dumps(asdict(t)) + "\n")
    logger.info(f"Saved {len(all_family_trades)} independent family trades to {ledger_path}.")

    # Load frozen benchmark trades from M35 ledger to compute return correlations
    benchmark_file = research_dir / "m34_trade_level_ledger.jsonl"
    bm_trades = []
    if benchmark_file.exists():
        with open(benchmark_file, "r", encoding="utf-8") as f:
            bm_trades = [json.loads(line) for line in f if "ORDER_BLOCK_RETEST" in line and "BTCUSDT" in line and "1h" in line]

    logger.info(f"Loaded {len(bm_trades)} frozen benchmark trades for correlation comparison.")

    # Calculate correlation between Family returns and Benchmark
    # We aggregate returns into monthly buckets to measure temporal co-movement
    monthly_returns = {"BENCHMARK_OB": {}}
    for t in bm_trades:
        dt = datetime.fromtimestamp(t["entry_ts"] / 1000, tz=timezone.utc)
        m_key = f"{dt.year}-{dt.month:02d}"
        monthly_returns["BENCHMARK_OB"][m_key] = monthly_returns["BENCHMARK_OB"].get(m_key, 0.0) + t["net_pnl_r_strict_mixed"] if "net_pnl_r_strict_mixed" in t else t.get("net_pnl_r_mixed", 0.0)

    for fam_id in ["FAMILY_1", "FAMILY_2", "FAMILY_3"]:
        monthly_returns[fam_id] = {}
        fam_trades = [t for t in all_family_trades if t.family_id == fam_id and t.symbol == "BTCUSDT" and t.timeframe == "1h"]
        for t in fam_trades:
            dt = datetime.fromtimestamp(t.entry_ts / 1000, tz=timezone.utc)
            m_key = f"{dt.year}-{dt.month:02d}"
            monthly_returns[fam_id][m_key] = monthly_returns[fam_id].get(m_key, 0.0) + t.net_pnl_r_strict_mixed

    # Build monthly dataframe
    all_months = sorted(list(set().union(*[d.keys() for d in monthly_returns.values()])))
    corr_data = []
    for m in all_months:
        row = {"month": m}
        for k in monthly_returns:
            row[k] = monthly_returns[k].get(m, 0.0)
        corr_data.append(row)
    df_corr = pd.DataFrame(corr_data).set_index("month")
    corr_matrix = df_corr.corr().to_dict()

    manifest_output = {
        "manifest_version": "M36.1-INDEPENDENT-EDGE-DISCOVERY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_trades_logged": len(all_family_trades),
        "families_evaluated": [
            {"family_id": "FAMILY_1", "name": "Trend Continuation & Dynamic Value Pullback"},
            {"family_id": "FAMILY_2", "name": "Volatility Compression & Breakout Expansion"},
            {"family_id": "FAMILY_3", "name": "Liquidity Sweep & Failed Breakout Reversal"},
        ],
        "correlation_with_frozen_benchmark": corr_matrix,
        "results": results_by_family_asset,
    }

    manifest_file = research_dir / "m36_independent_edges_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_output, f, indent=2)

    results_file = research_dir / "m36_independent_edges_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results_by_family_asset, f, indent=2)

    logger.info(f"Saved M36 results to {results_file} and manifest to {manifest_file}.")
    print("M36 INDEPENDENT EDGE DISCOVERY COMPLETED.")


if __name__ == "__main__":
    main()
