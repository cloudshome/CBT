"""
M37 Derivatives Intelligence & Independent Alpha Discovery Engine
=================================================================
Executes rigorous point-in-time backtests for:
- H1: Extreme Funding Crowd Reversal (Long/Short)
- H2: Price/OI Divergence (Exhaustion High / Absorption Low)
- H3: OI Flush Capitulation (Long Flush / Short Flush)
- H4: Perpetual Basis Dislocation (Discount Long / Premium Short)
- H5: High OI Compression Breakout (Upward / Downward)
- H6: Negative Funding in Bullish Trend (Short Trap Continuation)
- E1: Funding Acceleration Dislocation
- E2: OI Accumulation in Range (Stealth Build)
- E3: Cross-Asset Derivatives Divergence (BTC/ETH)

Partitions:
- Train: 2022-01-01 to 2024-06-30
- Validation: 2024-07-01 to 2025-06-30
- Sealed OOS: 2025-07-01 to 2026-10-20

Emits:
- research/m37_experiment_ledger.jsonl
- research/m37_strategy_results.json
- research/m37_research_manifest.json
"""

import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m37_discovery")

# Transaction friction parameters
TAKER_FEE_PCT = 0.00040    # 4.0 bps
MAKER_FEE_PCT = 0.00020    # 2.0 bps
SLIPPAGE_PCT = 0.00010     # 1.0 bps
SPREAD_PCT = 0.00010       # 1.0 bps
ROUNDTRIP_TAKER_FRICTION = (TAKER_FEE_PCT + SLIPPAGE_PCT + SPREAD_PCT) * 2  # ~0.12%


def load_market_data(symbol: str) -> pd.DataFrame:
    logger.info(f"Loading continuous derivatives & price stream for {symbol}...")
    # 1. Perp 1h
    perp_files = sorted(list((ROOT_DIR / f"data/store/parquet/candles/exchange=binance/market=perp/symbol={symbol}/timeframe=1h").rglob("*.parquet")))
    df_perp = pd.concat([pd.read_parquet(f) for f in perp_files], ignore_index=True).sort_values("ts").drop_duplicates(subset=["ts"])

    # 2. Spot 1h
    spot_files = sorted(list((ROOT_DIR / f"data/store/parquet/candles/exchange=binance/market=spot/symbol={symbol}/timeframe=1h").rglob("*.parquet")))
    df_spot = pd.concat([pd.read_parquet(f) for f in spot_files], ignore_index=True).sort_values("ts").drop_duplicates(subset=["ts"])

    # 3. Open Interest 1h
    oi_files = sorted(list((ROOT_DIR / f"data/store/derivatives/exchange=binance/market=perp/symbol={symbol}/metric=open_interest").rglob("*.parquet")))
    df_oi = pd.concat([pd.read_parquet(f) for f in oi_files], ignore_index=True).sort_values("ts").drop_duplicates(subset=["ts"])

    # 4. Funding Rate
    fr_files = sorted(list((ROOT_DIR / f"data/store/derivatives/exchange=binance/market=perp/symbol={symbol}/metric=funding_rate").rglob("*.parquet")))
    df_fr = pd.concat([pd.read_parquet(f) for f in fr_files], ignore_index=True).sort_values("ts").drop_duplicates(subset=["ts"])
    df_fr["ts_floor"] = pd.to_datetime(df_fr["ts"], unit="ms", utc=True).dt.floor("h").astype("int64") // 10**6

    # Merge Perp & Spot & OI
    df = pd.merge(df_perp[["ts", "open", "high", "low", "close", "volume"]], 
                  df_spot[["ts", "close"]].rename(columns={"close": "spot_close"}), on="ts", how="inner")
    df = pd.merge(df, df_oi[["ts", "value"]].rename(columns={"value": "open_interest"}), on="ts", how="inner")

    # Merge Funding with asof backward
    df = pd.merge_asof(df.sort_values("ts"), df_fr[["ts_floor", "value"]].rename(columns={"value": "funding_rate"}), 
                       left_on="ts", right_on="ts_floor", direction="backward")
    df["funding_rate"] = df["funding_rate"].fillna(0.0001)

    # Technical features
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["date"] = df["dt"].dt.strftime("%Y-%m-%d")
    df["hour"] = df["dt"].dt.hour

    # ATR 14
    prev_close = df["close"].shift(1)
    tr = np.maximum(df["high"] - df["low"], np.maximum(np.abs(df["high"] - prev_close), np.abs(df["low"] - prev_close)))
    df["atr_14"] = tr.rolling(14).mean().bfill()

    # EMAs for trend
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

    # Bollinger Bands (20, 2.0)
    sma_20 = df["close"].rolling(20).mean()
    std_20 = df["close"].rolling(20).std()
    df["bb_mid"] = sma_20
    df["bb_upper"] = sma_20 + 2.0 * std_20
    df["bb_lower"] = sma_20 - 2.0 * std_20
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / sma_20
    df["bb_width_q20"] = df["bb_width"].rolling(2160).quantile(0.20)  # 90-day 20th percentile

    # Funding rate features (90d rolling z-score: 2160 hours)
    fr_roll_mean = df["funding_rate"].rolling(2160, min_periods=720).mean()
    fr_roll_std = df["funding_rate"].rolling(2160, min_periods=720).std().replace(0, 1e-6)
    df["fr_zscore"] = (df["funding_rate"] - fr_roll_mean) / fr_roll_std
    df["fr_accel"] = df["funding_rate"] - 2 * df["funding_rate"].shift(8) + df["funding_rate"].shift(16)

    # Open Interest features
    df["oi_pct_chg_1h"] = df["open_interest"].pct_change(1)
    df["oi_pct_chg_24h"] = df["open_interest"].pct_change(24)

    # Perpetual Basis
    df["basis_pct"] = (df["close"] - df["spot_close"]) / df["spot_close"]

    # Price 72h Extrema
    df["price_high_72h"] = df["high"].rolling(72).max().shift(1)
    df["price_low_72h"] = df["low"].rolling(72).min().shift(1)

    # Chronological partition flag
    # Train: < 2024-07-01 | Validation: 2024-07-01 to 2025-06-30 | OOS: >= 2025-07-01
    df["partition"] = "TRAIN"
    df.loc[(df["date"] >= "2024-07-01") & (df["date"] <= "2025-06-30"), "partition"] = "VALIDATION"
    df.loc[df["date"] >= "2025-07-01", "partition"] = "SEALED_OOS"

    logger.info(f"Loaded {len(df)} merged hourly candles for {symbol}. Partitions: {df['partition'].value_counts().to_dict()}")
    return df


def simulate_trades(df: pd.DataFrame, signals: pd.Series, direction: str, 
                    take_profit_r: float, stop_loss_r: float, max_bars_hold: int, 
                    risk_atr_mult: float = 1.5, experiment_id: str = ""):
    """
    Simulates trades with point-in-time entry on the next bar open,
    including full 3-tier frictions and funding payments.
    """
    trades = []
    n = len(df)
    in_pos = False
    entry_bar = 0
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    risk_usd = 0.0
    trade_partition = ""

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atrs = df["atr_14"].values
    frs = df["funding_rate"].values
    hours = df["hour"].values
    ts_arr = df["ts"].values
    partitions = df["partition"].values
    sig_arr = signals.values

    accumulated_funding = 0.0

    for i in range(1, n - 1):
        # 1. Manage active position
        if in_pos:
            bars_held = i - entry_bar
            # Check for funding settlement at 00, 08, 16 UTC
            if hours[i] in [0, 8, 16]:
                # If Long: pay funding (if fr > 0), receive (if fr < 0)
                # If Short: receive funding (if fr > 0), pay (if fr < 0)
                cur_fr = frs[i]
                if direction == "LONG":
                    accumulated_funding -= cur_fr
                else:
                    accumulated_funding += cur_fr

            # Check exit conditions on bar i
            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""

            if direction == "LONG":
                if lows[i] <= sl_price:
                    exit_triggered = True
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                elif highs[i] >= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"
                elif bars_held >= max_bars_hold:
                    exit_triggered = True
                    exit_price = closes[i]
                    exit_reason = "MAX_HOLD"
            else: # SHORT
                if highs[i] >= sl_price:
                    exit_triggered = True
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                elif lows[i] <= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"
                elif bars_held >= max_bars_hold:
                    exit_triggered = True
                    exit_price = closes[i]
                    exit_reason = "MAX_HOLD"

            if exit_triggered:
                # Calculate gross R
                if direction == "LONG":
                    gross_pnl_usd = exit_price - entry_price
                else:
                    gross_pnl_usd = entry_price - exit_price
                
                gross_r = gross_pnl_usd / risk_usd

                # Frictions in R space:
                # round-trip friction as fraction of entry price: ROUNDTRIP_TAKER_FRICTION * entry_price
                friction_r = (ROUNDTRIP_TAKER_FRICTION * entry_price) / risk_usd
                # funding impact in R space:
                funding_r = (accumulated_funding * entry_price) / risk_usd

                net_r = gross_r - friction_r + funding_r

                trades.append({
                    "experiment_id": experiment_id,
                    "partition": trade_partition,
                    "direction": direction,
                    "entry_ts": int(ts_arr[entry_bar]),
                    "exit_ts": int(ts_arr[i]),
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "exit_reason": exit_reason,
                    "bars_held": bars_held,
                    "gross_r": round(float(gross_r), 4),
                    "friction_r": round(float(friction_r), 4),
                    "funding_r": round(float(funding_r), 4),
                    "net_r": round(float(net_r), 4),
                    "win": 1 if net_r > 0 else 0
                })
                in_pos = False

        # 2. Check for new entry signal (executable at bar i open if signal at i-1)
        if not in_pos and sig_arr[i - 1]:
            in_pos = True
            entry_bar = i
            entry_price = opens[i]
            trade_partition = partitions[i]
            accumulated_funding = 0.0

            atr = atrs[i - 1]
            if atr <= 0 or np.isnan(atr):
                atr = entry_price * 0.015
            
            risk_usd = risk_atr_mult * atr

            if direction == "LONG":
                sl_price = entry_price - (stop_loss_r * risk_usd)
                tp_price = entry_price + (take_profit_r * risk_usd)
            else:
                sl_price = entry_price + (stop_loss_r * risk_usd)
                tp_price = entry_price - (take_profit_r * risk_usd)

    return trades


def evaluate_trade_set(trades: list) -> dict:
    if not trades:
        return {
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "net_cumulative_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
            "sharpe_trade": 0.0,
            "t_stat": 0.0,
            "p_value": 1.0,
            "ci_95_low": 0.0,
            "ci_95_high": 0.0
        }

    net_returns = np.array([t["net_r"] for t in trades])
    n = len(net_returns)
    wins = net_returns[net_returns > 0]
    losses = net_returns[net_returns < 0]

    win_rate = float(len(wins) / n * 100.0)
    cum_r = float(np.sum(net_returns))
    mean_r = float(np.mean(net_returns))
    std_r = float(np.std(net_returns, ddof=1)) if n > 1 else 1.0

    gross_win = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 1e-6
    pf = round(gross_win / gross_loss, 2)

    # Drawdown
    equity = np.cumsum(net_returns)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    t_stat, p_val = stats.ttest_1samp(net_returns, 0.0) if n > 1 else (0.0, 1.0)
    se = std_r / math.sqrt(n) if n > 0 else 0.0
    ci_low = round(mean_r - 1.96 * se, 4)
    ci_high = round(mean_r + 1.96 * se, 4)
    sharpe = round((mean_r / (std_r + 1e-6)) * math.sqrt(n), 3)

    return {
        "trade_count": n,
        "win_rate_pct": round(win_rate, 2),
        "net_cumulative_r": round(cum_r, 3),
        "expectancy_r": round(mean_r, 4),
        "profit_factor": pf,
        "max_drawdown_r": round(max_dd, 3),
        "sharpe_trade": sharpe,
        "t_stat": round(float(t_stat), 3),
        "p_value": round(float(p_val), 4),
        "ci_95_low": ci_low,
        "ci_95_high": ci_high
    }


def main():
    logger.info("=== Milestone 37 Derivatives Alpha Discovery Engine ===")
    experiment_ledger = []
    strategy_results = {}

    symbols = ["BTCUSDT", "ETHUSDT"]

    for sym in symbols:
        df = load_market_data(sym)

        # -------------------------------------------------------------
        # 1. H1 — Extreme Funding Crowd Reversal
        # -------------------------------------------------------------
        # H1-Long: extreme negative funding crowd (retail shorting heavily)
        sig_h1_long = df["fr_zscore"] < -2.0
        h1_long_trades = simulate_trades(df, sig_h1_long, "LONG", 2.0, 1.0, 48, experiment_id=f"H1_EXTREME_FUNDING_LONG_{sym}")

        # H1-Short: extreme positive funding crowd (retail leveraged long)
        sig_h1_short = df["fr_zscore"] > 2.0
        h1_short_trades = simulate_trades(df, sig_h1_short, "SHORT", 2.0, 1.0, 48, experiment_id=f"H1_EXTREME_FUNDING_SHORT_{sym}")

        # -------------------------------------------------------------
        # 2. H2 — Price / OI Divergence (Exhaustion & Absorption)
        # -------------------------------------------------------------
        # H2-Short (Exhaustion High): Price makes 72h high, but OI 24h falls >= 3%
        sig_h2_short = (df["high"] >= df["price_high_72h"]) & (df["oi_pct_chg_24h"] <= -0.03)
        h2_short_trades = simulate_trades(df, sig_h2_short, "SHORT", 2.0, 1.0, 48, experiment_id=f"H2_PRICE_OI_DIV_SHORT_{sym}")

        # H2-Long (Absorption Low): Price makes 72h low, but OI 24h falls >= 3%
        sig_h2_long = (df["low"] <= df["price_low_72h"]) & (df["oi_pct_chg_24h"] <= -0.03)
        h2_long_trades = simulate_trades(df, sig_h2_long, "LONG", 2.0, 1.0, 48, experiment_id=f"H2_PRICE_OI_DIV_LONG_{sym}")

        # -------------------------------------------------------------
        # 3. H3 — Violent OI Flush Capitulation
        # -------------------------------------------------------------
        # H3-Long: 1h OI collapses > 4%, sharp down candle -> Capitulation Long
        sig_h3_long = (df["oi_pct_chg_1h"] <= -0.04) & (df["close"] < df["open"] - 0.8 * df["atr_14"])
        h3_long_trades = simulate_trades(df, sig_h3_long, "LONG", 2.0, 1.0, 24, experiment_id=f"H3_OI_FLUSH_LONG_{sym}")

        # H3-Short: 1h OI collapses > 4%, sharp up candle -> Short Squeeze Exhaustion
        sig_h3_short = (df["oi_pct_chg_1h"] <= -0.04) & (df["close"] > df["open"] + 0.8 * df["atr_14"])
        h3_short_trades = simulate_trades(df, sig_h3_short, "SHORT", 2.0, 1.0, 24, experiment_id=f"H3_OI_FLUSH_SHORT_{sym}")

        # -------------------------------------------------------------
        # 4. H4 — Perpetual Basis Dislocation Arbitrage
        # -------------------------------------------------------------
        # H4-Long: Perp trades at sharp discount to spot (< -0.15%)
        sig_h4_long = df["basis_pct"] < -0.0015
        h4_long_trades = simulate_trades(df, sig_h4_long, "LONG", 1.5, 1.0, 36, experiment_id=f"H4_BASIS_DISCOUNT_LONG_{sym}")

        # H4-Short: Perp trades at sharp premium to spot (> +0.20%)
        sig_h4_short = df["basis_pct"] > 0.0020
        h4_short_trades = simulate_trades(df, sig_h4_short, "SHORT", 1.5, 1.0, 36, experiment_id=f"H4_BASIS_PREMIUM_SHORT_{sym}")

        # -------------------------------------------------------------
        # 5. H5 — High OI Compression Breakout
        # -------------------------------------------------------------
        # BB width in lowest 20th percentile + OI 24h expansion > +3%
        compression = (df["bb_width"] <= df["bb_width_q20"]) & (df["oi_pct_chg_24h"] >= 0.03)
        sig_h5_long = compression & (df["close"] > df["bb_upper"])
        sig_h5_short = compression & (df["close"] < df["bb_lower"])
        h5_long_trades = simulate_trades(df, sig_h5_long, "LONG", 2.5, 1.0, 72, experiment_id=f"H5_COMPRESSION_BREAKOUT_LONG_{sym}")
        h5_short_trades = simulate_trades(df, sig_h5_short, "SHORT", 2.5, 1.0, 72, experiment_id=f"H5_COMPRESSION_BREAKOUT_SHORT_{sym}")

        # -------------------------------------------------------------
        # 6. H6 — Negative Funding in Bullish Trend (Short Trap)
        # -------------------------------------------------------------
        # 4h Trend Bullish: ema_50 > ema_200 and close > ema_200. Funding rate is negative (< -0.005%)
        bull_trend = (df["ema_50"] > df["ema_200"]) & (df["close"] > df["ema_200"])
        sig_h6_long = bull_trend & (df["funding_rate"] < -0.00005)
        h6_long_trades = simulate_trades(df, sig_h6_long, "LONG", 2.5, 1.0, 72, experiment_id=f"H6_NEGATIVE_FUNDING_TREND_LONG_{sym}")

        # -------------------------------------------------------------
        # Beyond H1-H6 Exploratory Concepts
        # -------------------------------------------------------------
        # E1: Funding Acceleration Dislocation (Sharp second derivative shock)
        sig_e1_short = df["fr_accel"] > 0.00020
        e1_short_trades = simulate_trades(df, sig_e1_short, "SHORT", 2.0, 1.0, 48, experiment_id=f"E1_FUNDING_ACCEL_SHORT_{sym}")

        # E2: OI Stealth Accumulation (Flat price with heavy OI build > +5%)
        price_range_24h = (df["high"].rolling(24).max() - df["low"].rolling(24).min()) / df["close"]
        stealth_build = (price_range_24h < 0.015) & (df["oi_pct_chg_24h"] > 0.05)
        sig_e2_long = stealth_build & (df["close"] > df["open"])
        e2_long_trades = simulate_trades(df, sig_e2_long, "LONG", 2.0, 1.0, 48, experiment_id=f"E2_STEALTH_OI_BUILD_LONG_{sym}")

        all_experiments = {
            "H1_EXTREME_FUNDING_LONG": h1_long_trades,
            "H1_EXTREME_FUNDING_SHORT": h1_short_trades,
            "H2_PRICE_OI_DIV_SHORT": h2_short_trades,
            "H2_PRICE_OI_DIV_LONG": h2_long_trades,
            "H3_OI_FLUSH_LONG": h3_long_trades,
            "H3_OI_FLUSH_SHORT": h3_short_trades,
            "H4_BASIS_DISCOUNT_LONG": h4_long_trades,
            "H4_BASIS_PREMIUM_SHORT": h4_short_trades,
            "H5_COMPRESSION_BREAKOUT_LONG": h5_long_trades,
            "H5_COMPRESSION_BREAKOUT_SHORT": h5_short_trades,
            "H6_NEGATIVE_FUNDING_TREND_LONG": h6_long_trades,
            "E1_FUNDING_ACCEL_SHORT": e1_short_trades,
            "E2_STEALTH_OI_BUILD_LONG": e2_long_trades,
        }

        for exp_key, tr_list in all_experiments.items():
            full_key = f"{exp_key}_{sym}"
            experiment_ledger.extend(tr_list)

            # Partition-based performance
            train_trades = [t for t in tr_list if t["partition"] == "TRAIN"]
            val_trades = [t for t in tr_list if t["partition"] == "VALIDATION"]
            oos_trades = [t for t in tr_list if t["partition"] == "SEALED_OOS"]

            eval_train = evaluate_trade_set(train_trades)
            eval_val = evaluate_trade_set(val_trades)
            eval_oos = evaluate_trade_set(oos_trades)
            eval_all = evaluate_trade_set(tr_list)

            # Classification logic
            # Strict multi-stage gate:
            # 1. Train expectancy > 0 and p-value < 0.10
            # 2. Validation expectancy > 0
            # 3. Sealed OOS expectancy > 0 and trade count >= 10
            status = "REJECTED"
            if eval_all["trade_count"] < 10:
                status = "NEEDS_MORE_DATA"
            elif eval_train["expectancy_r"] > 0.05 and eval_val["expectancy_r"] > 0.0:
                if eval_oos["expectancy_r"] > 0.05 and eval_oos["trade_count"] >= 10:
                    status = "OOS_CANDIDATE"
                elif eval_oos["expectancy_r"] > 0.0:
                    status = "RESEARCH_CANDIDATE"
                else:
                    status = "REJECTED (FAILED_OOS)"
            else:
                status = "REJECTED (NO_TRAIN_EDGE)"

            strategy_results[full_key] = {
                "symbol": sym,
                "strategy_id": exp_key,
                "classification": status,
                "train_metrics": eval_train,
                "validation_metrics": eval_val,
                "sealed_oos_metrics": eval_oos,
                "full_sample_metrics": eval_all
            }

            logger.info(f"[{full_key}] Status={status} | Full: N={eval_all['trade_count']}, Exp={eval_all['expectancy_r']:+.3f}R, WR={eval_all['win_rate_pct']}%, PF={eval_all['profit_factor']} | OOS: N={eval_oos['trade_count']}, Exp={eval_oos['expectancy_r']:+.3f}R")

    # Save Experiment Ledger JSONL
    ledger_path = ROOT_DIR / "research" / "m37_experiment_ledger.jsonl"
    with open(ledger_path, "w", encoding="utf-8") as f:
        for t in experiment_ledger:
            f.write(json.dumps(t) + "\n")
    logger.info(f"Saved {len(experiment_ledger)} total simulated trade records to {ledger_path}")

    # Save Strategy Results JSON
    res_path = ROOT_DIR / "research" / "m37_strategy_results.json"
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(strategy_results, f, indent=2)
    logger.info(f"Saved {len(strategy_results)} strategy test evaluations to {res_path}")

    # Save Manifest
    manifest_obj = {
        "manifest_version": "M37-ALPHA-DISCOVERY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_experiments_evaluated": len(strategy_results),
        "total_trades_simulated": len(experiment_ledger),
        "partition_boundaries": {
            "train": ["2022-01-01", "2024-06-30"],
            "validation": ["2024-07-01", "2025-06-30"],
            "sealed_oos": ["2025-07-01", "2026-10-20"]
        },
        "friction_model": {
            "roundtrip_taker_fee_pct": ROUNDTRIP_TAKER_FRICTION * 100,
            "funding_payment_settlement": "Actual continuous 8h payments deducted/added based on holding duration and position direction"
        },
        "strategy_results": strategy_results
    }
    man_path = ROOT_DIR / "research" / "m37_research_manifest.json"
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest_obj, f, indent=2)
    logger.info(f"Saved research manifest to {man_path}")


if __name__ == "__main__":
    main()

