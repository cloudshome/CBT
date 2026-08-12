"""data/backfill.py — P10.2: paginated, resumable REST backfill.

Reuses ``BinanceClient.klines`` / ``SampleClient.klines`` as transport and
writes through ``CandleStore.write()`` / ``normalise_klines()``. A re-run
against the same range adds **zero** unique rows (upsert PK).

``DEMO_MODE=1`` stays fully offline: the sample client is the default
transport when no ``fetch`` is injected.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, asdict
from typing import Callable, Optional

import pandas as pd

from data.binance_client import TIMEFRAME_TO_MS
from data.sample_client import maybe_client
from data.store import CandleStore, normalise_klines

PAGE_LIMIT = 1000  # Binance hard cap — never request more

FetchFn = Callable[..., pd.DataFrame]


@dataclass
class BackfillResult:
    exchange: str
    market: str
    symbol: str
    timeframe: str
    pages: int
    rows_before: int
    rows_after: int
    rows_added: int
    resumed_from: Optional[int]
    last_ts: Optional[int]
    sleeps: int
    demo: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _step_ms(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_TO_MS:
        raise ValueError(f"unknown timeframe: {timeframe}")
    return TIMEFRAME_TO_MS[timeframe]


def _default_fetch(symbol: str, timeframe: str) -> FetchFn:
    client = maybe_client()

    def fetch(start_time=None, end_time=None, limit: int = PAGE_LIMIT) -> pd.DataFrame:
        return client.klines(
            symbol, timeframe, limit=limit,
            start_time=start_time, end_time=end_time,
        )

    return fetch


def iter_klines_pages(
    fetch: FetchFn,
    *,
    start_ts: Optional[int],
    end_ts: Optional[int],
    page_limit: int = PAGE_LIMIT,
    step_ms: int = 60_000,
) -> list[pd.DataFrame]:
    """Walk ``fetch`` forward until a short page or ``end_ts``.

    Cursor advances to ``last_ts + step_ms`` so we never re-request the
    last closed candle of the previous page as the *start* of the next
    (Binance ``startTime`` is inclusive).
    """
    pages: list[pd.DataFrame] = []
    cursor = start_ts
    seen_last: Optional[int] = None
    while True:
        page = fetch(start_time=cursor, end_time=end_ts, limit=page_limit)
        if page is None or getattr(page, "empty", True):
            break
        page = page.sort_values("ts").reset_index(drop=True)
        last = int(page["ts"].iloc[-1])
        if seen_last is not None and last <= seen_last:
            break
        pages.append(page)
        seen_last = last
        if len(page) < page_limit:
            break
        if end_ts is not None and last >= end_ts:
            break
        nxt = last + step_ms
        if cursor is not None and nxt <= cursor:
            break
        cursor = nxt
    return pages


def backfill(
    *,
    store: CandleStore,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    exchange: str = "binance",
    market: str = "perp",
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    fetch: Optional[FetchFn] = None,
    page_limit: int = PAGE_LIMIT,
    sleep_s: float = 0.0,
    resume: bool = True,
) -> BackfillResult:
    """Paginated REST backfill into ``store``. Returns a row-count report.

    ``rows_added`` is ``count_after - count_before`` — a re-run of the
    same range reports **0**. Rate-limit courtesy is ``sleep_s`` between
    pages (tests set 0; live backfill should use ~0.2s).
    """
    step = _step_ms(timeframe)
    demo = os.getenv("DEMO_MODE", "0") in ("1", "true", "yes")
    fetch = fetch or _default_fetch(symbol, timeframe)

    before = store.count(exchange, market, symbol, timeframe)
    existing = store.read(exchange, market, symbol, timeframe)
    resumed_from: Optional[int] = None
    cursor = start_ts
    if resume and not existing.empty:
        resumed_from = int(existing["ts"].max()) + step
        if cursor is None or resumed_from > cursor:
            cursor = resumed_from

    pages = iter_klines_pages(
        fetch, start_ts=cursor, end_ts=end_ts,
        page_limit=page_limit, step_ms=step,
    )

    sleeps = 0
    last_ts: Optional[int] = None
    for i, page in enumerate(pages):
        frame = normalise_klines(
            page, exchange=exchange, market=market,
            symbol=symbol, timeframe=timeframe, source="rest",
        )
        store.write(frame)
        if not frame.empty:
            last_ts = int(frame["ts"].max())
        if sleep_s and i < len(pages) - 1:
            time.sleep(sleep_s)
            sleeps += 1

    after = store.count(exchange, market, symbol, timeframe)
    if last_ts is None and not existing.empty:
        last_ts = int(existing["ts"].max())
    return BackfillResult(
        exchange=exchange, market=market, symbol=symbol, timeframe=timeframe,
        pages=len(pages), rows_before=before, rows_after=after,
        rows_added=after - before, resumed_from=resumed_from,
        last_ts=last_ts, sleeps=sleeps, demo=demo,
    )
