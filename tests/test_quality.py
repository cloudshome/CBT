"""P10.5 — data-quality pillar: corrupt or stale stored history quarantines.

Milestone deliverable (docs/DATA_INFRASTRUCTURE_ROADMAP.md §9):
"per-source checks wired into readiness_strip() — corrupt fixture ⇒
quarantine ⇒ no signal, proven by test."

All tests are fully offline and deterministic: fixed timestamps, no
network, tmp_path stores.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.quality import (FRESH_MULT, GAP_DOWN, LAG_MULT, MAX_SERIES,
                          checks_on_frame, series_health, series_item,
                          verdict_for)
from data.store import CandleStore, normalise_klines

STEP = 60_000
TF = "1m"
NOW = 1_780_000_000_000
EXCH, MARKET, SYMBOL = "binance", "perp", "BTCUSDT"


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path)


def frame(n: int = 300, *, last_ts: int = NOW - 10 * STEP,
          seed: int = 7) -> pd.DataFrame:
    """Deterministic healthy 1m OHLCV ending at ``last_ts``."""
    rng = np.random.default_rng(seed)
    ts = np.arange(n, dtype=np.int64) * STEP + (last_ts - (n - 1) * STEP)
    close = 60_000.0 + rng.normal(0, 20, n).cumsum()
    return pd.DataFrame({
        "ts": ts,
        "open": np.round(close, 2),
        "high": np.round(close + 15, 2),
        "low": np.round(close - 15, 2),
        "close": np.round(close, 2),
        "volume": np.round(rng.uniform(1, 50, n), 4),
    })


def write_series(store, df, **kwargs):
    """Persist a closed-candle series through the real store boundary."""
    norm = normalise_klines(df, exchange=EXCH, market=MARKET,
                            symbol=SYMBOL, timeframe=TF, source="rest",
                            ingested_at=NOW)
    store.write(norm)


# --------------------------------------------------------------------------- #
# Staleness ladder (timeframe-scaled)
# --------------------------------------------------------------------------- #

def test_fresh_frame_is_ok():
    h = checks_on_frame(frame(last_ts=NOW - 2 * STEP), TF, now_ms=NOW)
    v = verdict_for(h)
    assert v["level"] == "ok"
    assert v["quarantined"] is False
    assert h["violations"] == []
    assert h["gap_fraction"] == 0.0


def test_lagging_frame_is_degraded():
    age = (FRESH_MULT + 5) * STEP
    h = checks_on_frame(frame(last_ts=NOW - age), TF, now_ms=NOW)
    assert h["age_mult"] > FRESH_MULT
    assert h["age_mult"] <= LAG_MULT
    v = verdict_for(h)
    assert v["level"] == "degraded"
    assert v["quarantined"] is False


def test_stale_frame_is_quarantined():
    age = (LAG_MULT + 40) * STEP
    h = checks_on_frame(frame(last_ts=NOW - age), TF, now_ms=NOW)
    assert h["age_mult"] > LAG_MULT
    v = verdict_for(h)
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "stale" in v["headline"]


# --------------------------------------------------------------------------- #
# Gaps (reuses P10.3 detect_gaps)
# --------------------------------------------------------------------------- #

def test_large_gap_in_recent_window_quarantines():
    df = frame(600, last_ts=NOW - 2 * STEP)
    drop = df[(df["ts"] > NOW - 300 * STEP) & (df["ts"] < NOW - 150 * STEP)]
    holey = df.drop(drop.index).reset_index(drop=True)
    h = checks_on_frame(holey, TF, now_ms=NOW)
    assert h["missing"] > 0
    assert h["gap_fraction"] > GAP_DOWN
    v = verdict_for(h)
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "gaps" in v["headline"]


def test_small_gap_degrades_but_does_not_quarantine():
    df = frame(600, last_ts=NOW - 2 * STEP)
    drop_idx = [300, 301, 302, 303, 304]                     # 5 candles gone
    holey = df.drop(df.index[drop_idx]).reset_index(drop=True)
    h = checks_on_frame(holey, TF, now_ms=NOW)
    assert 0 < h["gap_fraction"] <= GAP_DOWN
    assert h["gap_fraction"] > 0.005
    v = verdict_for(h)
    assert v["level"] == "degraded"
    assert v["quarantined"] is False


# --------------------------------------------------------------------------- #
# Price / volume / ordering sanity
# --------------------------------------------------------------------------- #

def test_negative_close_quarantines():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "close"] = -1.0
    v = verdict_for(checks_on_frame(df, TF, now_ms=NOW))
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "non-positive OHLC" in v["detail"]


def test_inverted_high_quarantines():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "high"] = df["close"].min() - 5.0   # high below body
    v = verdict_for(checks_on_frame(df, TF, now_ms=NOW))
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "high below" in v["detail"]


def test_inverted_low_quarantines():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "low"] = df["close"].max() + 5.0    # low above body
    v = verdict_for(checks_on_frame(df, TF, now_ms=NOW))
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "low above" in v["detail"]


def test_negative_volume_quarantines():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "volume"] = -3.0
    v = verdict_for(checks_on_frame(df, TF, now_ms=NOW))
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "negative volume" in v["detail"]


def test_zero_volume_with_range_is_suspicious_not_corrupt():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "volume"] = 0.0
    h = checks_on_frame(df, TF, now_ms=NOW)
    assert h["violations"] == []
    assert h["suspicious"]
    v = verdict_for(h)
    assert v["level"] == "degraded"
    assert v["quarantined"] is False


def test_non_monotonic_ts_quarantines():
    df = frame(last_ts=NOW - STEP)
    df.loc[df.index[-1], "ts"] = df["ts"].iloc[0]            # duplicate ts
    v = verdict_for(checks_on_frame(df, TF, now_ms=NOW))
    assert v["level"] == "down"
    assert v["quarantined"] is True
    assert "monotonic" in v["detail"]


# --------------------------------------------------------------------------- #
# Store path: corrupt fixture ⇒ quarantine through the real boundary
# --------------------------------------------------------------------------- #

def test_corrupt_fixture_written_through_store_is_quarantined(store):
    """The milestone's done-when: a corrupt fixture, persisted exactly the
    way the backfill persists data, is detected and quarantined."""
    df = frame(200, last_ts=NOW - 2 * STEP)
    df.loc[df.index[100], "close"] = 0.0        # corruption
    write_series(store, df)
    item = series_item(store, {"exchange": EXCH, "market": MARKET,
                               "symbol": SYMBOL, "timeframe": TF},
                       now_ms=NOW)
    assert item["candles"] == 200
    assert item["level"] == "down"
    assert item["quarantined"] is True
    assert "non-positive OHLC" in item["detail"]


def test_healthy_series_through_store_is_fresh(store):
    write_series(store, frame(300, last_ts=NOW - 2 * STEP))
    item = series_item(store, {"exchange": EXCH, "market": MARKET,
                               "symbol": SYMBOL, "timeframe": TF},
                       now_ms=NOW)
    assert item["level"] == "ok"
    assert item["quarantined"] is False
    assert item["candles"] == 300


def test_list_series_and_empty_store(store):
    assert store.list_series() == []
    write_series(store, frame(10, last_ts=NOW - STEP))
    assert store.list_series() == [{"exchange": EXCH, "market": MARKET,
                                    "symbol": SYMBOL, "timeframe": TF}]
    # a second series sorts and both appear
    from data.store import normalise_klines as nk
    store.write(nk(frame(5, last_ts=NOW - STEP), exchange="binance",
                   market="spot", symbol="ETHUSDT", timeframe="1m",
                   source="rest", ingested_at=NOW))
    listed = store.list_series()
    assert len(listed) == 2
    assert listed[0]["symbol"] == "BTCUSDT"
    assert listed[1]["symbol"] == "ETHUSDT"


def test_empty_series_verdict_is_degraded_not_down():
    v = verdict_for(checks_on_frame(pd.DataFrame(), TF, now_ms=NOW))
    assert v["level"] == "degraded"
    assert v["quarantined"] is False


# --------------------------------------------------------------------------- #
# Readiness integration: quarantine ⇒ no signal (ready False)
# --------------------------------------------------------------------------- #

def test_quarantined_data_rolls_desk_to_not_ready(store, monkeypatch):
    """Corrupt fixture → data pillar down → readiness_strip not ready."""
    import brain.agent as agent
    from brain.agent import _data_pillar

    df = frame(100, last_ts=NOW - STEP)
    df.loc[df.index[50], "volume"] = -1.0
    write_series(store, df)

    monkeypatch.setattr(agent, "_channels_pillar", lambda: {
        "name": "channels", "level": "ok", "headline": "4/4 live", "detail": ""})
    monkeypatch.setattr(agent, "_immune_pillar", lambda: {
        "name": "immune", "level": "ok", "headline": "ok", "detail": ""})
    monkeypatch.setattr(agent, "_gate_pillar", lambda status: {
        "name": "risk_gate", "level": "ok", "headline": "gate OPEN",
        "detail": "no blocks"})
    monkeypatch.setattr(agent, "_data_pillar",
                        lambda: _data_pillar(store=store, now_ms=NOW))

    strip = agent.readiness_strip(status={"time": NOW, "version": "x",
                                          "advice": {}})
    assert strip["level"] == "down"
    assert strip["ready"] is False
    data = next(p for p in strip["pillars"] if p["name"] == "data")
    assert data["level"] == "down"
    assert data["quarantined"] == ["binance/perp/BTCUSDT/1m"]
    assert "quarantined" in data["headline"]


def test_data_pillar_is_exception_isolated(store, monkeypatch):
    """A crashing probe degrades the data pillar, never the whole strip."""
    import brain.agent as agent
    import data.quality as quality

    def boom(*a, **k):
        raise RuntimeError("store exploded")

    monkeypatch.setattr(quality, "series_item", boom)
    write_series(store, frame(10, last_ts=NOW - STEP))   # so the pillar has work to do

    pillar = agent._data_pillar(store=store, now_ms=NOW)
    assert pillar["name"] == "data"
    assert pillar["level"] == "down"
    assert pillar["headline"] == "data-quality check failed"
    assert "RuntimeError" in pillar["detail"]

    # and the strip still renders with every other pillar intact
    real_pillar = agent._data_pillar
    monkeypatch.setattr(agent, "_channels_pillar", lambda: {
        "name": "channels", "level": "ok", "headline": "4/4 live", "detail": ""})
    monkeypatch.setattr(agent, "_immune_pillar", lambda: {
        "name": "immune", "level": "ok", "headline": "ok", "detail": ""})
    monkeypatch.setattr(agent, "_gate_pillar", lambda status: {
        "name": "risk_gate", "level": "ok", "headline": "gate OPEN",
        "detail": "no blocks"})
    monkeypatch.setattr(agent, "_data_pillar",
                        lambda: real_pillar(store=store, now_ms=NOW))
    strip = agent.readiness_strip(status={"time": NOW, "version": "x",
                                          "advice": {}})
    assert strip["level"] == "down"
    assert {p["name"] for p in strip["pillars"]} == {
        "channels", "immune", "risk_gate", "data"}


def test_max_series_cap_is_positive():
    assert MAX_SERIES >= 1
