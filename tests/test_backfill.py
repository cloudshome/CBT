"""P10.2 — paginated, resumable, idempotent, rate-limit-aware REST backfill.

Covers the milestone's done-when (a re-run adds **zero** rows) plus the
2026-08-13 hardening: perp actually pages the perp endpoint, 429/network
errors back off exponentially, geo-blocks abort immediately, low weight
headers stretch the sleep, and the forming tail candle is never persisted.
All tests are fully offline and deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.backfill import (
    PAGE_LIMIT,
    BackfillError,
    FakePagedTransport,
    backfill,
    fmt_ts,
    iter_klines_pages,
    parse_ts,
)
from data.binance_client import TIMEFRAME_TO_MS
from data.store import CandleStore

EXCH, MARKET, SYMBOL, TF = "binance", "perp", "BTCUSDT", "1m"
STEP = 60_000
START = 1_750_000_000_000
TF_MS = TIMEFRAME_TO_MS[TF]
ALIGNED = (START // TF_MS) * TF_MS          # aligned 1m open time
N_CANDLES = 5000
END = ALIGNED + N_CANDLES * TF_MS            # exclusive


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


def make_transport(**kw) -> FakePagedTransport:
    kw.setdefault("start_ts", ALIGNED)
    kw.setdefault("end_ts", END)
    return FakePagedTransport(**kw)


def clock_at_end() -> int:
    """Clock exactly when the last fake candle has closed."""
    return END


def no_sleep(_secs: float) -> None:
    pass


# --------------------------------------------------------------------------- #
# Paging (main's original P10.2 contract)
# --------------------------------------------------------------------------- #

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


def test_demo_backfill_without_end_ts_terminates_at_now(store):
    """Regression: SampleClient's synthetic venue never runs out of history,
    so an unbounded backfill used to page forever. end_ts must default to
    now (also correct against the real API)."""
    from data.sample_client import SampleClient
    frozen = 1_786_000_000_000                     # fixed "now" for both runs
    client = SampleClient()
    first = backfill(store=store, symbol=SYMBOL, timeframe=TF, client=client,
                     start_ts=frozen - 120 * STEP, page_limit=1000, sleep_s=0.0,
                     clock=lambda: frozen)
    assert first.pages == 1                        # bounded by now, not infinite
    assert first.rows_added == 120
    assert first.forming_skipped == 1              # the candle at `now` is forming
    assert first.last_ts == frozen                 # last fetched OPEN
    second = backfill(store=store, symbol=SYMBOL, timeframe=TF, client=client,
                      page_limit=1000, sleep_s=0.0, clock=lambda: frozen)
    assert second.rows_added == 0                  # idempotent even in demo


def test_sleeps_between_pages_when_configured(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    src = book(15)
    backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=FakeBook(src), page_limit=5, sleep_s=0.2, resume=False, start_ts=START,
    )
    assert slept == [0.2, 0.2]  # 3 pages → 2 sleeps


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


# --------------------------------------------------------------------------- #
# Hardening: perp routing
# --------------------------------------------------------------------------- #

def test_default_fetch_routes_perp_to_perp_endpoint(store):
    transport = make_transport()
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF, client=transport,
        start_ts=ALIGNED, end_ts=ALIGNED, sleep_s=0.0,
        clock=clock_at_end,
    )
    assert result.rows_added == 1
    # every transport request must have asked for the perp market
    assert transport.calls, "transport was never called"
    assert all(c["market"] == "perp" for c in transport.calls)


def test_gold_perp_is_rejected_with_honest_message(store):
    transport = make_transport()
    with pytest.raises(BackfillError, match="no Binance perp market"):
        backfill(store=store, symbol="XAUUSD", timeframe=TF, client=transport,
                 start_ts=ALIGNED, clock=clock_at_end, sleep_s=0.0)


# --------------------------------------------------------------------------- #
# Hardening: forming-candle rule
# --------------------------------------------------------------------------- #

def test_forming_tail_candle_is_never_stored(store):
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF, client=make_transport(),
        start_ts=ALIGNED, sleep_s=0.0, clock=lambda: clock_at_end() - 1,
    )
    assert result.forming_skipped == 1
    assert result.rows_added == N_CANDLES - 1
    assert store.count(EXCH, MARKET, SYMBOL, TF) == N_CANDLES - 1


def test_forming_candle_is_picked_up_by_next_run(store):
    transport = make_transport()
    backfill(store=store, symbol=SYMBOL, timeframe=TF, client=transport,
             start_ts=ALIGNED, sleep_s=0.0, clock=lambda: clock_at_end() - 1)
    result = backfill(store=store, symbol=SYMBOL, timeframe=TF, client=transport,
                      sleep_s=0.0, clock=clock_at_end)
    assert result.forming_skipped == 0
    assert result.rows_added == 1                    # the now-closed tail
    assert store.count(EXCH, MARKET, SYMBOL, TF) == N_CANDLES


# --------------------------------------------------------------------------- #
# Hardening: rate limits / geo-blocks / caps
# --------------------------------------------------------------------------- #

def test_429_is_retried_with_backoff_and_succeeds(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        client=make_transport(faults={1: 429}),
        start_ts=ALIGNED, end_ts=ALIGNED + TF_MS, sleep_s=0.0,
        clock=clock_at_end, backoff_base=1.0,
    )
    assert result.rows_added == 2                   # end_ts is inclusive
    assert result.rate_limit_stalls == 1
    assert result.retries == 1
    assert 1.0 in slept                             # one exponential backoff


def test_429_after_retries_exhausted_raises(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    with pytest.raises(BackfillError, match="transport failed"):
        backfill(
            store=store, symbol=SYMBOL, timeframe=TF,
            client=make_transport(faults={1: 429, 2: 429, 3: 429, 4: 429}),
            start_ts=ALIGNED, sleep_s=0.0, clock=clock_at_end,
            backoff_attempts=3,
        )
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 0   # nothing written
    assert slept == [1.0, 2.0, 4.0]                     # exponential backoff


def test_network_error_is_retried(store, monkeypatch):
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: None)
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        client=make_transport(faults={1: None, 2: None}),
        start_ts=ALIGNED, end_ts=ALIGNED, sleep_s=0.0,
        clock=clock_at_end,
    )
    assert result.rows_added == 1
    assert result.retries == 2
    assert result.rate_limit_stalls == 0


def test_geo_block_aborts_immediately_without_backoff(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    with pytest.raises(BackfillError, match="geo-blocked"):
        backfill(
            store=store, symbol=SYMBOL, timeframe=TF,
            client=make_transport(faults={1: 451}),
            start_ts=ALIGNED, sleep_s=0.0, clock=clock_at_end,
        )
    assert slept == []                                # never paced/backed off
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 0


def test_low_weight_header_triggers_longer_sleep(store, monkeypatch):
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", lambda s: slept.append(s))
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        client=make_transport(weight_budget=4),       # 2/page → 2 then 0
        start_ts=ALIGNED, end_ts=ALIGNED + 1000 * TF_MS, sleep_s=0.0,
        clock=clock_at_end, weight_min=100,
        weight_sleep=5.0, low_weight_sleep=20.0,
    )
    assert result.rows_added == 1001                  # 1000 + boundary candle
    assert 5.0 in slept                               # low-but-positive budget
    assert 20.0 in slept                              # budget exhausted


def test_max_requests_cap_raises_and_run_is_resumable(store):
    transport = make_transport()
    with pytest.raises(BackfillError, match="max_requests"):
        backfill(store=store, symbol=SYMBOL, timeframe=TF, client=transport,
                 start_ts=ALIGNED, sleep_s=0.0, clock=clock_at_end,
                 max_requests=2)
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 2000   # partial, safe

    result = backfill(store=store, symbol=SYMBOL, timeframe=TF,
                      client=transport, sleep_s=0.0, clock=clock_at_end)
    assert result.resumed_from == ALIGNED + 2000 * TF_MS
    assert result.rows_added == N_CANDLES - 2000
    assert store.count(EXCH, MARKET, SYMBOL, TF) == N_CANDLES


def test_dry_run_writes_nothing(store):
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        client=make_transport(), start_ts=ALIGNED, sleep_s=0.0,
        clock=clock_at_end, dry_run=True,
    )
    assert result.rows_added == N_CANDLES            # what WOULD be added
    assert result.rows_after == 0                    # nothing written
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def test_parse_ts_forms():
    now = 1_760_000_000_000
    assert parse_ts(None, now_ms=now) is None
    assert parse_ts("1750000000000", now_ms=now) == 1_750_000_000_000
    assert parse_ts("2024-01-01", now_ms=now) == 1_704_067_200_000
    assert parse_ts("2024-01-01T12:30", now_ms=now) == 1_704_112_200_000
    assert parse_ts("90d", now_ms=now) == now - 90 * 86_400_000
    with pytest.raises(BackfillError, match="cannot parse ts"):
        parse_ts("last week", now_ms=now)


def test_fmt_ts_utc():
    assert fmt_ts(1_704_067_200_000) == "2024-01-01 00:00"
    assert fmt_ts(None) == "-"


# --------------------------------------------------------------------------- #
# Edge cases from the parallel P10.2 session (PR #13 reconciliation)
# --------------------------------------------------------------------------- #

def test_empty_first_page_terminates_cleanly(store):
    """Window starts before the venue's oldest data: the empty first page
    ends the run with zero rows instead of looping or guessing."""
    fake = FakeBook(book(0))
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=fake, page_limit=1000, sleep_s=0.0, resume=False,
        start_ts=START,
    )
    assert result.pages == 0
    assert result.rows_added == 0
    assert result.rows_after == 0
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 0


def test_start_past_end_is_a_clean_noop(store):
    """start > end must fetch one empty page and stop — no rows, no error."""
    src = book(20)
    fake = FakeBook(src)
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=fake, page_limit=10, sleep_s=0.0, resume=False,
        start_ts=START + 100 * STEP, end_ts=START,
    )
    assert result.pages == 0
    assert result.rows_added == 0
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 0


def test_mid_history_hole_stops_run_without_duplicates(store):
    """A venue outage hole (empty page mid-window) terminates the iterator:
    everything fetched before the hole is stored exactly once. Repairing
    the hole is P10.3's job (`repair_gaps`)."""
    full = book(30)
    # The venue answers exactly one full page, then the hole begins.
    holey = FakeBook(full.iloc[:10])
    result = backfill(
        store=store, symbol=SYMBOL, timeframe=TF,
        fetch=holey, page_limit=10, sleep_s=0.0, resume=False,
        start_ts=START,
    )
    assert result.rows_added == 10
    df = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(df) == 10
    assert df["ts"].is_unique
    assert int(df["ts"].max()) == int(full["ts"].iloc[9])
