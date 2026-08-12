"""P10.2 — paginated, resumable, idempotent REST backfill (fully offline)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.backfill import PAGE_LIMIT, backfill, iter_klines_pages
from data.store import CandleStore

EXCH, MARKET, SYMBOL, TF = "binance", "perp", "BTCUSDT", "1m"
STEP = 60_000
START = 1_750_000_000_000


def book(n: int, start: int = START, step: int = STEP, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = np.arange(n, dtype=np.int64) * step + start
    close = 60_000.0 + rng.normal(0, 20, n).cumsum()
    return pd.DataFrame({
        "ts": ts,
        "open": np.round(close, 2),
        "high": np.round(close + 10, 2),
        "low": np.round(close - 10, 2),
        "close": np.round(close, 2),
        "volume": np.round(rng.uniform(1, 5, n), 4),
    })


class FakeBook:
    """In-memory venue that pages like Binance (limit cap, inclusive start)."""

    def __init__(self, frame: pd.DataFrame, calls: list | None = None):
        self.frame = frame.sort_values("ts").reset_index(drop=True)
        self.calls = calls if calls is not None else []

    def __call__(self, start_time=None, end_time=None, limit: int = 1000) -> pd.DataFrame:
        self.calls.append({"start_time": start_time, "end_time": end_time, "limit": limit})
        df = self.frame
        if start_time is not None:
            df = df[df["ts"] >= int(start_time)]
        if end_time is not None:
            df = df[df["ts"] <= int(end_time)]
        return df.head(int(limit)).reset_index(drop=True)


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path)


def test_page_limit_is_binance_cap():
    assert PAGE_LIMIT == 1000


def test_iter_pages_respects_limit_and_advances(store):
    src = book(25)
    fake = FakeBook(src)
    pages = iter_klines_pages(
        fake, start_ts=START, end_ts=None, page_limit=10, step_ms=STEP,
    )
    assert len(pages) == 3
    assert [len(p) for p in pages] == [10, 10, 5]
    # second page must start after the first page's last open
    assert int(pages[1]["ts"].iloc[0]) == int(pages[0]["ts"].iloc[-1]) + STEP


def test_backfill_writes_full_history(store):
    src = book(37)
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=FakeBook(src), page_limit=10, sleep_s=0.0, resume=False,
        start_ts=START,
    )
    assert result.pages == 4
    assert result.rows_added == 37
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 37
    back = store.read(EXCH, MARKET, SYMBOL, TF)
    assert back["ts"].tolist() == src["ts"].tolist()


def test_rerun_adds_zero_rows(store):
    src = book(20)
    fake = FakeBook(src)
    first = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=fake, page_limit=7, sleep_s=0.0, resume=False, start_ts=START,
    )
    second = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=FakeBook(src), page_limit=7, sleep_s=0.0, resume=False, start_ts=START,
    )
    assert first.rows_added == 20
    assert second.rows_added == 0
    assert second.rows_after == 20
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 20


def test_resume_skips_already_stored_prefix(store):
    src = book(30)
    backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=FakeBook(src.iloc[:12]), page_limit=20, sleep_s=0.0,
        resume=False, start_ts=START,
    )
    calls = []
    fake = FakeBook(src, calls=calls)
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=fake, page_limit=20, sleep_s=0.0, resume=True,
    )
    assert result.resumed_from == int(src["ts"].iloc[12])
    assert result.rows_added == 18
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 30
    # first fetch must start at the resume cursor, not the series origin
    assert calls[0]["start_time"] == result.resumed_from


def test_cli_backfill_demo_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main
    start = 1_780_000_000_000
    end = start + 59 * 60_000  # 60 one-minute bars
    argv = [
        "backfill", "--symbol", "BTCUSDT", "--tf", "1m",
        "--start-ts", str(start), "--end-ts", str(end),
        "--page-limit", "25", "--no-sleep", "--root", str(tmp_path),
        "--json",
    ]
    assert main(argv) == 0
    rc = main(argv)
    assert rc == 0
    store = CandleStore(root=tmp_path)
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 60


def test_sleeps_between_pages_when_configured(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    src = book(15)
    backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=FakeBook(src), page_limit=5, sleep_s=0.2, resume=False, start_ts=START,
    )
    assert slept == [0.2, 0.2]  # 3 pages → 2 sleeps
