"""P10.1 — normalised Candle schema + Parquet store.

Milestone deliverable (docs/DATA_INFRASTRUCTURE_ROADMAP.md §9):
"round-trips 1m candles; dedup + ordering tested offline."
All tests are fully offline and deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.store import (
    CANDLE_COLUMNS,
    PRIMARY_KEY,
    CandleStore,
    coerce_candle_frame,
    empty_frame,
    normalise_klines,
)

EXCH, MARKET, SYMBOL, TF = "binance", "perp", "BTCUSDT", "1m"


def ohlcv(n: int = 50, start_ts: int = 1_750_000_000_000,
          step_ms: int = 60_000, seed: int = 11) -> pd.DataFrame:
    """Deterministic 1m OHLCV (same shape the adapters hand us)."""
    rng = np.random.default_rng(seed)
    ts = np.arange(n, dtype=np.int64) * step_ms + start_ts
    close = 60_000.0 + rng.normal(0, 50, n).cumsum()
    return pd.DataFrame({
        "ts": ts,
        "open": np.round(close, 2),
        "high": np.round(close + 30, 2),
        "low": np.round(close - 30, 2),
        "close": np.round(close, 2),
        "volume": np.round(rng.uniform(1, 10, n), 4),
    })


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path)


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

def test_empty_frame_has_canonical_columns_and_dtypes():
    df = empty_frame()
    assert list(df.columns) == CANDLE_COLUMNS
    assert df["ts"].dtype == np.int64
    assert df["closed"].dtype == np.bool_
    assert df["open"].dtype == np.float64


def test_primary_key_is_the_upsert_key():
    assert PRIMARY_KEY == ["exchange", "market", "symbol", "timeframe", "ts"]


def test_normalise_klines_attaches_context_and_closed_true():
    raw = ohlcv(5)
    df = normalise_klines(
        raw, exchange=EXCH, market=MARKET, symbol=SYMBOL,
        timeframe=TF, source="rest", ingested_at=1_760_000_000_000,
    )
    assert list(df.columns) == CANDLE_COLUMNS
    assert (df["closed"] == True).all()          # noqa: E712  persisted history is closed
    assert (df["source"] == "rest").all()
    assert (df["price_type"] == "").all()
    assert (df["ingested_at"] == 1_760_000_000_000).all()
    # prices survive the normalisation untouched
    assert df["close"].tolist() == raw["close"].round(2).tolist()


def test_normalise_klines_honours_input_closed_column(store):
    raw = ohlcv(4)
    raw["closed"] = [True, True, False, True]      # P10.2 backfill marks the tail
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    assert list(df["closed"]) == [True, True, False, True]
    store.write(df)                                # forming row never persists
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(back) == 3
    assert (back["closed"] == True).all()           # noqa: E712


def test_coerce_fills_missing_optional_fields():
    df = coerce_candle_frame([{
        "ts": 1_750_000_000_000, "open": 1.0, "high": 2.0,
        "low": 0.5, "close": 1.5, "volume": 10.0,
    }])
    assert df.loc[0, "exchange"] == ""
    assert bool(df.loc[0, "closed"]) is False
    assert float(df.loc[0, "quote_volume"]) == 0.0
    assert int(df.loc[0, "ingested_at"]) == 0


# --------------------------------------------------------------------------- #
# Round-trip / dedup / ordering
# --------------------------------------------------------------------------- #

def test_round_trips_1m_candles(store):
    raw = ohlcv(120)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    written = store.write(df)
    assert written == 120

    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(back) == 120
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 120
    # values intact
    pd.testing.assert_frame_equal(
        back[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True),
        df[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True),
    )


def test_upsert_dedup_last_write_wins(store):
    raw = ohlcv(10)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    store.write(df)

    # Rewrite with a revised close on some rows (venue backfill scenario).
    revised = df.copy()
    revised["close"] = revised["close"] + 123.0
    revised["ingested_at"] = revised["ingested_at"] + 1_000
    store.write(revised)

    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(back) == 10            # still no duplicates
    assert back["ts"].is_unique
    # the revised value wins for the rewritten rows
    assert set(back["close"].tolist()) == set(revised["close"].tolist())


def test_out_of_order_input_returns_sorted(store):
    raw = ohlcv(30)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    shuffled = df.iloc[list(range(len(df) - 1, -1, -1))]  # descending
    store.write(shuffled)
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert (back["ts"].diff().dropna() > 0).all()          # strictly ascending


def test_duplicate_ts_within_single_write_collapses(store):
    raw = ohlcv(5)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)   # repeat row 0
    store.write(dup)
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(back) == 5
    assert back["ts"].is_unique


def test_unclosed_candles_never_persist(store):
    raw = ohlcv(6)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    df.loc[df.index[-1], "closed"] = False   # forming candle
    store.write(df)
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(back) == 5                    # the forming candle is dropped
    assert (back["closed"] == True).all()    # noqa: E712


# --------------------------------------------------------------------------- #
# Partitioning / filtering
# --------------------------------------------------------------------------- #

def test_partitions_across_year_month_boundary(store):
    # 3 candles spanning the turn of the year (Dec 31 23:58 .. Jan 1 00:00)
    base = 1_704_067_199_000  # 2023-12-31 23:59:59 UTC (approx)
    raw = pd.DataFrame({
        "ts": [base - 60_000, base, base + 60_000],
        "open": [1.0, 1.0, 1.0], "high": [2.0, 2.0, 2.0],
        "low": [0.5, 0.5, 0.5], "close": [1.5, 1.5, 1.5],
        "volume": [1.0, 1.0, 1.0],
    })
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    store.write(df)
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 3
    assert len(store.series(EXCH, MARKET, SYMBOL, TF)) == 2   # two year/month parts
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert back["ts"].is_monotonic_increasing


def test_read_range_filter(store):
    raw = ohlcv(20, start_ts=1_750_000_000_000)
    df = normalise_klines(raw, exchange=EXCH, market=MARKET,
                          symbol=SYMBOL, timeframe=TF)
    store.write(df)
    lo = int(df["ts"].iloc[5])
    hi = int(df["ts"].iloc[15])
    window = store.read(EXCH, MARKET, SYMBOL, TF, start_ts=lo, end_ts=hi)
    assert len(window) == 11                     # inclusive both ends
    assert window["ts"].iloc[0] >= lo
    assert window["ts"].iloc[-1] <= hi


def test_read_missing_series_returns_empty_canonical_frame(store):
    df = store.read("bybit", MARKET, SYMBOL, TF)
    assert df.empty
    assert list(df.columns) == CANDLE_COLUMNS


def test_store_isolates_series(store):
    a = normalise_klines(ohlcv(8), exchange=EXCH, market=MARKET,
                         symbol="BTCUSDT", timeframe=TF)
    b = normalise_klines(ohlcv(8), exchange=EXCH, market=MARKET,
                         symbol="ETHUSDT", timeframe="5m")
    store.write(a)
    store.write(b)
    assert store.count(EXCH, MARKET, "BTCUSDT", TF) == 8
    assert store.count(EXCH, MARKET, "ETHUSDT", "5m") == 8
