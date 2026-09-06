"""data/feature_store.py — P10.12: Feature store.

One wide table per timestamp — price + derivatives + flow + regime — so
P10.12's conditioned-expectancy questions (e.g. "how did this setup do
when price ↑, OI ↑, funding < 0, CVD > 0?") are answerable from our own
stored data, without importing Freqtrade or Backtrader.

Design rules (carried from ``docs/DATA_INFRASTRUCTURE_ROADMAP.md``):

1. **One row per (symbol, timeframe, ts)** — no duplicate timestamps.
2. **Reads from existing stored sources only** — ``CandleStore`` (price),
   ``derivatives`` series (funding/OI/basis), ``hidden_alpha`` features
   (CVD/volume delta/regime), and never from a live fetch when computing
   the feature table.
3. **Does not store a second copy of raw candles** — it joins to the
   existing ``CandleStore.read()`` output; the feature file lives under
   ``data/store/features/`` (gitignored) as a derived dataset.
4. **Offline-first / DEMO-safe** — the feature table can be rebuilt from
   stored history with zero network.

Usage (CLI / background):

    from data.feature_store import build_feature_table, feature_path
    df = build_feature_table("BTCUSDT", "15m", limit=500)

Usage (P11 paper-book / P12 validation engine):

    # The feature table feeds `run_backtest_on_store` so the grader can
    # condition on `regime`, `funding_rate_pct`, `open_interest`, `cvd_z`,
    # etc. — the conditioned-query goal of P10.12.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from data.derivatives import DerivativesSeries  # existing P10.4 module
from data.store import DEFAULT_ROOT, CandleStore

FEATURE_STORE_DIR = DEFAULT_ROOT / "features"
FEATURE_COLUMNS = [
    # primary key
    "symbol",
    "timeframe",
    "ts",
    # price (from CandleStore)
    "open",
    "high",
    "low",
    "close",
    "volume",
    # derivatives (P10.4 series)
    "funding_rate_pct",
    "open_interest",
    "long_short_ratio",
    "basis",
    "index_price",
    "mark_price",
    # flow / order-flow (engine hidden_alpha / feature snapshot)
    "cvd_z",
    "volume_delta_z",
    "volume_spike_ratio",
    "buy_volume_pct",
    "sell_volume_pct",
    "above_vwap",
    # regime / structure (engine hidden_alpha / structure)
    "regime",
    "trend_bias",
    "ema_alignment_bull",
    "event_kind",
    "premium_discount",
    "fvg_bull_count",
    "fvg_bear_count",
    # meta
    "ingested_at",
]


def feature_path(symbol: str, timeframe: str) -> Path:
    FEATURE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    # Hive-style partitioning for easy reads (same pattern as candles).
    return FEATURE_STORE_DIR / f"symbol={symbol.upper()}" / f"tf={timeframe}"


def build_feature_table(
    symbol: str,
    timeframe: str,
    exchange: str = "binance",
    market: str = "perp",
    limit: int = 500,
) -> pd.DataFrame:
    """Build the wide feature table from stored series.

    This is a **derived** dataset: it reads the existing ``CandleStore``,
    ``derivatives`` series, and engine feature functions, then writes
    one Parquet partition.  It never creates new raw data.

    The result is the input to ``run_backtest_on_store`` and to P12's
    conditioned-expectancy queries.
    """
    # 1. Price series (existing store — P10.1)
    store = CandleStore()
    price_df = store.read(exchange, market, symbol, timeframe)
    if price_df.empty:
        # Graceful empty result; caller (e.g. P11/12) handles missing store.
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    price_df = price_df.tail(limit).copy()
    price_df = price_df.sort_values("ts").reset_index(drop=True)

    # 2. Derivatives (existing series — P10.4)
    # DerivativesSeries provides funding/OI/basis as a time-aligned DataFrame.
    try:
        deriv_df = DerivativesSeries(
            symbol=exchange, market=market, symbol_name=symbol
        ).to_frame()
    except Exception:
        # If the derivatives series has no stored data yet, we fall back
        # to empty columns (the feature table degrades, never crashes).
        deriv_df = pd.DataFrame(index=price_df.index)

    # 3. Feature snapshot / hidden alpha (engine layer — P9 / existing)
    # We call ``engine.hidden_alpha`` on each price row; for speed on
    # large backtests, this can be replaced by a pre-computed feature file.
    try:
        from engine.hidden_alpha import compute_feature_snapshot

        feature_rows = []
        for _, row in price_df.iterrows():
            try:
                snap = compute_feature_snapshot(
                    row.to_dict(), symbol=symbol, timeframe=timeframe
                )
                feature_rows.append(snap)
            except Exception:
                feature_rows.append({})
        feature_df = pd.DataFrame(feature_rows, index=price_df.index)
    except Exception:
        feature_df = pd.DataFrame(index=price_df.index)

    # 4. Regime (from hidden_alpha or structure output)
    try:
        from engine.hidden_alpha import regime_for_frame

        regime_rows = []
        for _, row in price_df.iterrows():
            try:
                regime_rows.append({"regime": regime_for_frame(row.to_dict())})
            except Exception:
                regime_rows.append({"regime": ""})
        regime_df = pd.DataFrame(regime_rows, index=price_df.index)
    except Exception:
        regime_df = pd.DataFrame({"regime": ""}, index=price_df.index)

    # 5. Assemble wide table (one row per ts; no duplicate timestamps)
    # Primary key: (symbol, timeframe, ts)
    result = price_df.rename(
        columns={
            "ts": "ts",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )

    # Derivatives merge (left join on index; both sorted by ts if possible)
    # For simplicity we align by position when the series share length;
    # a full time-alignment (ts merge) is the production upgrade path.
    for col in [
        "funding_rate_pct",
        "open_interest",
        "long_short_ratio",
        "basis",
        "index_price",
        "mark_price",
    ]:
        if col in deriv_df.columns:
            result[col] = deriv_df[col].values
        else:
            result[col] = np.nan

    # Flow / hidden alpha
    for col in [
        "cvd_z",
        "volume_delta_z",
        "volume_spike_ratio",
        "buy_volume_pct",
        "sell_volume_pct",
        "above_vwap",
    ]:
        if col in feature_df.columns:
            result[col] = feature_df[col].values
        else:
            result[col] = np.nan

    # Regime
    if "regime" in regime_df.columns:
        result["regime"] = regime_df["regime"].values
    else:
        result["regime"] = ""

    # Additional structure fields
    result["trend_bias"] = feature_df.get(
        "trend_bias", pd.Series(np.nan, index=price_df.index)
    ).values
    result["ema_alignment_bull"] = feature_df.get(
        "ema_alignment_bull", pd.Series(np.nan, index=price_df.index)
    ).values
    result["event_kind"] = feature_df.get(
        "event_kind", pd.Series("", index=price_df.index)
    ).values
    result["premium_discount"] = feature_df.get(
        "premium_discount", pd.Series("", index=price_df.index)
    ).values
    result["fvg_bull_count"] = feature_df.get(
        "fvg_bull_count", pd.Series(0, index=price_df.index)
    ).values
    result["fvg_bear_count"] = feature_df.get(
        "fvg_bear_count", pd.Series(0, index=price_df.index)
    ).values

    # Meta / key fields
    result["symbol"] = symbol.upper()
    result["timeframe"] = timeframe
    result["ingested_at"] = int(time.time() * 1000)

    # Ensure only defined columns remain
    result = result[[c for c in FEATURE_COLUMNS if c in result.columns]]
    # Reindex to canonical column order (fill missing with safe defaults)
    for col in FEATURE_COLUMNS:
        if col not in result.columns:
            if col in (
                "symbol",
                "timeframe",
                "regime",
                "event_kind",
                "premium_discount",
            ):
                result[col] = ""
            elif col in ("fvg_bull_count", "fvg_bear_count", "ingested_at"):
                result[col] = 0
            elif col == "above_vwap":
                result[col] = False
            else:
                result[col] = np.nan
    result = result[FEATURE_COLUMNS]

    # Deduplicate by the natural key (symbol, timeframe, ts) — upsert-style
    result = result.drop_duplicates(subset=["symbol", "timeframe", "ts"], keep="last")
    result = result.sort_values(["symbol", "timeframe", "ts"]).reset_index(drop=True)

    return result


def save_feature_table(df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
    """Persist the feature table as a single Parquet file (derived layer)."""
    path = feature_path(symbol, timeframe)
    path.mkdir(parents=True, exist_ok=True)
    out_path = path / "part-000.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def read_feature_table(symbol: str, timeframe: str) -> pd.DataFrame:
    """Read the derived feature table (P10.12 query surface)."""
    path = feature_path(symbol, timeframe)
    parquet_path = path / "part-000.parquet"
    if not parquet_path.exists():
        return pd.DataFrame(columns=FEATURE_COLUMNS)
    df = pd.read_parquet(parquet_path)
    return df.sort_values(["symbol", "timeframe", "ts"]).reset_index(drop=True)


def feature_summary(symbol: str, timeframe: str) -> dict:
    """Quick diagnostic summary for a feature-series — feeds readiness."""
    df = read_feature_table(symbol, timeframe)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": len(df),
        "columns": list(df.columns) if not df.empty else FEATURE_COLUMNS,
        "path": feature_path(symbol, timeframe).as_posix(),
        "exists": not df.empty,
    }
