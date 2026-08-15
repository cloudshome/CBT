"""P10.3 — gap detection / repair / 1m→higher-TF aggregation (offline)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.gaps import (
    ROLLUP_TIMEFRAMES,
    aggregate_ohlcv,
    detect_gaps,
    repair_gaps,
    rollup,
    step_ms,
)
from data.store import CandleStore, normalise_klines

EXCH, MARKET, SYMBOL = "binance", "perp", "BTCUSDT"
START = 1_704_067_200_000  # 2024-01-01 00:00:00 UTC


def minutes(n: int, start: int = START, drop: set[int] | None = None,
            seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    keep = [i for i in range(n) if i not in (drop or set())]
    ts = np.array(keep, dtype=np.int64) * 60_000 + start
    close = 40_000.0 + rng.normal(0, 8, len(keep)).cumsum()
    return pd.DataFrame({
        "ts": ts,
        "open": np.round(close, 2),
        "high": np.round(close + 5, 2),
        "low": np.round(close - 5, 2),
        "close": np.round(close, 2),
        "volume": np.round(rng.uniform(1, 3, len(keep)), 4),
    })


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path)


def test_detect_gaps_finds_missing_opens():
    raw = minutes(20, drop={5, 6, 14})
    gaps = detect_gaps(raw, "1m")
    assert len(gaps) == 2
    assert gaps[0].missing == 2
    assert gaps[0].start_ts == START + 5 * 60_000
    assert gaps[0].end_ts == START + 6 * 60_000
    assert gaps[1].missing == 1
    assert gaps[1].start_ts == START + 14 * 60_000


def test_no_gaps_on_contiguous_series():
    assert detect_gaps(minutes(40), "1m") == []


def test_repair_fills_synthetic_holes(store):
    full = minutes(25)
    holed = minutes(25, drop={8, 9, 10})
    store.write(normalise_klines(
        holed, exchange=EXCH, market=MARKET, symbol=SYMBOL, timeframe="1m",
    ))
    assert len(detect_gaps(store.read(EXCH, MARKET, SYMBOL, "1m"), "1m")) == 1

    def fetch(start_time=None, end_time=None, limit=1000):
        df = full
        if start_time is not None:
            df = df[df["ts"] >= int(start_time)]
        if end_time is not None:
            df = df[df["ts"] <= int(end_time)]
        return df.head(int(limit))

    report = repair_gaps(store, fetch, exchange=EXCH, market=MARKET, symbol=SYMBOL)
    assert report["gaps_remaining"] == 0
    assert store.count(EXCH, MARKET, SYMBOL, "1m") == 25
    assert detect_gaps(store.read(EXCH, MARKET, SYMBOL, "1m"), "1m") == []


def test_aggregate_5m_matches_manual_ohlc():
    raw = minutes(15)  # three complete 5m buckets
    agg = aggregate_ohlcv(raw, "5m")
    assert len(agg) == 3
    first = raw.iloc[:5]
    assert float(agg.iloc[0]["open"]) == float(first.iloc[0]["open"])
    assert float(agg.iloc[0]["close"]) == float(first.iloc[-1]["close"])
    assert float(agg.iloc[0]["high"]) == float(first["high"].max())
    assert float(agg.iloc[0]["low"]) == float(first["low"].min())
    assert abs(float(agg.iloc[0]["volume"]) - float(first["volume"].sum())) < 1e-9
    assert int(agg.iloc[0]["ts"]) == START
    assert int(agg.iloc[1]["ts"]) == START + 5 * 60_000


def test_incomplete_trailing_bucket_is_dropped():
    raw = minutes(12)  # 2 full 5m + 2 leftover minutes
    agg = aggregate_ohlcv(raw, "5m")
    assert len(agg) == 2


def test_rollup_preserves_bid_ask_provenance(store):
    raw = minutes(60)
    store.write(normalise_klines(
        raw, exchange="dukascopy", market="spot", symbol="XAUUSD",
        timeframe="1m", source="dukascopy_csv", price_type="bid"))
    rollup(store, exchange="dukascopy", market="spot", symbol="XAUUSD",
           targets=("5m", "15m"))
    for tf in ("5m", "15m"):
        derived = store.read("dukascopy", "spot", "XAUUSD", tf)
        assert set(derived["source"]) == {"aggregated"}
        assert set(derived["price_type"]) == {"bid"}


def test_rollup_writes_all_higher_tfs(store):
    # 2 days of 1m = 2880 bars → complete 5m/15m/1h/4h/1d buckets
    raw = minutes(2 * 24 * 60)
    store.write(normalise_klines(
        raw, exchange=EXCH, market=MARKET, symbol=SYMBOL, timeframe="1m",
    ))
    report = rollup(store, exchange=EXCH, market=MARKET, symbol=SYMBOL)
    assert report["master_bars"] == 2880
    assert store.count(EXCH, MARKET, SYMBOL, "5m") == 2 * 24 * 12
    assert store.count(EXCH, MARKET, SYMBOL, "15m") == 2 * 24 * 4
    assert store.count(EXCH, MARKET, SYMBOL, "1h") == 2 * 24
    assert store.count(EXCH, MARKET, SYMBOL, "4h") == 2 * 6
    assert store.count(EXCH, MARKET, SYMBOL, "1d") == 2
    # source tag
    five = store.read(EXCH, MARKET, SYMBOL, "5m")
    assert set(five["source"]) == {"aggregated"}
    # 5m open of first bucket equals first 1m open
    assert float(five.iloc[0]["open"]) == float(raw.iloc[0]["open"])
    assert set(ROLLUP_TIMEFRAMES) == {"5m", "15m", "1h", "4h", "1d"}
    assert step_ms("1h") == 3_600_000
