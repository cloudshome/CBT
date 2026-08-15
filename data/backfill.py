"""data/backfill.py — P10.2: paginated, resumable, rate-limit-aware market-data backfill.

The roadmap is ``docs/DATA_INFRASTRUCTURE_ROADMAP.md``; this is milestone
**P10.2 (market-data backfill)**: page through exchange OHLCV history and
upsert into the P10.1 Parquet store through ``CandleStore.write()`` /
``normalise_klines()``.

History: P10.2 first shipped on 2026-08-12 (PR #11) reusing
``BinanceClient.klines`` as the transport. The 2026-08-13 hardening session
(PR #12) fixed two real defects in that first cut and is why this module
looks the way it does:

1. **Perp is actually perp.** The first cut labelled *spot* candles
   (``/api/v3/klines``) as ``market=perp`` — a silent mislabelling of the
   roadmap's primary series. The default transport now pages the perp
   endpoint (``/fapi/v1/klines``) when ``market="perp"``.
2. **Rate-limit aware means headers + backoff, not just a nap.** The first
   cut only slept ``sleep_s`` between pages. This version also honours
   Binance's ``x-mbx-remaining-weight`` header (extra sleep when the budget
   runs low), backs off exponentially on 429/network errors, aborts
   immediately on geo-blocks (403/451) instead of hammering a wall, and
   caps pages per run (``max_requests``) — an interrupted run resumes.
3. **Forming candles never enter history.** A candle is closed only when
   ``ts + timeframe <= now``; the still-forming tail is skipped and picked
   up by the next run once closed (incremental top-up).
4. **P10.6: the transport is an interface, not a class.** Any client with
   a ``klines_page()`` returning ``PageResult(data, headers, status)``
   pages through the same machinery — ``BybitClient`` (V5) ships behind
   the identical contract; its pages simply carry no Binance weight
   header, so header pacing no-ops and ``sleep_s`` pacing applies.

Properties that are guaranteed by tests (all offline):

- **Resumable** — a re-run starts at the last stored candle + one timeframe.
- **Idempotent** — the store's upsert PK means a completed re-run adds
  **zero** rows; ``start_ts`` re-fetches (repair) are equally safe.
- **Offline-first** — ``DEMO_MODE=1`` uses ``SampleClient``; tests use
  ``FakePagedTransport`` (deterministic, fault/weight injection).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
import re
import time
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from data.binance_client import TIMEFRAME_TO_MS, BinanceClient, PageResult
from data.sample_client import maybe_client
from data.store import CandleStore, normalise_klines
from data.symbols import resolve_symbol

PAGE_LIMIT = 1000  # Binance hard cap — never request more

FetchFn = Callable[..., pd.DataFrame]

DEMO_STORE_ROOT = Path(__file__).resolve().parent.parent / "data" / "store_demo"


class BackfillError(Exception):
    """A backfill aborted (transport failure, geo-block, cap, bad input)."""


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #

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
    # hardening-session fields (2026-08-13)
    rate_limit_stalls: int = 0      # 429/418 responses absorbed by backoff
    retries: int = 0                # requests retried after a failure
    geo_blocked: bool = False       # 403/451 seen (aborted before retrying)
    forming_skipped: int = 0        # still-forming tail candles not persisted
    requests: int = 0               # total transport requests this run

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #

def _step_ms(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_TO_MS:
        raise ValueError(f"unknown timeframe: {timeframe}")
    return TIMEFRAME_TO_MS[timeframe]


def parse_ts(value: Optional[str], *, now_ms: Optional[int] = None) -> Optional[int]:
    """Parse a CLI timestamp into UTC epoch ms.

    Accepts ``None``/empty (→ None), raw epoch ms, an ISO date or datetime
    (``2024-01-01``, ``2024-01-01T12:30``, ``Z`` suffix ok), or a relative
    window like ``90d`` (days back from now).
    """
    if value is None:
        return None
    v = str(value).strip()
    if not v or v == "0":
        return None
    if v.isdigit():
        return int(v)
    m = re.fullmatch(r"(\d+)d", v)
    if m:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return now - int(m.group(1)) * 86_400_000
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        raise BackfillError(
            f"cannot parse ts '{value}' — use epoch ms, YYYY-MM-DD, or Nd (e.g. 90d)"
        )


def fmt_ts(ts: Optional[int]) -> str:
    """UTC 'YYYY-MM-DD HH:MM' for a human summary line."""
    if ts is None:
        return "-"
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# Rate-limit-aware transport (the hardening)
# --------------------------------------------------------------------------- #

@dataclass
class _RateLimitState:
    """Mutable counters shared between the fetch wrapper and ``backfill``."""

    rate_limit_stalls: int = 0
    retries: int = 0
    geo_blocked: bool = False
    requests: int = 0
    weight_sleeps: int = 0


def _rate_limited_fetch(client: BinanceClient, symbol: str, timeframe: str,
                        market: str, *, page_limit: int = PAGE_LIMIT,
                        max_requests: int = 0, backoff_attempts: int = 3,
                        backoff_base: float = 1.0, weight_min: int = 100,
                        weight_sleep: float = 5.0, low_weight_sleep: float = 20.0,
                        ) -> tuple[FetchFn, _RateLimitState]:
    """Wrap ``client.klines_page`` with retry/backoff/weight pacing.

    The returned fetch never returns ``None`` for a transient failure — it
    retries with exponential backoff and either returns a page or raises
    :class:`BackfillError` (geo-blocks abort immediately; exhausted retries
    and the ``max_requests`` cap abort with a resumable message).
    """
    state = _RateLimitState()
    spec = resolve_symbol(symbol)
    if market == "perp" and not spec.futures_symbol:
        raise BackfillError(
            f"{spec.symbol} has no Binance perp market — use --market spot "
            f"({spec.symbol} is analysed with spot candles)"
        )

    def fetch(start_time=None, end_time=None, limit: int = page_limit) -> pd.DataFrame:
        attempts = 0
        while True:
            state.requests += 1
            # The cap bounds *pages* (first attempt of each page), not the
            # retries of a page already in flight — so a failing network
            # reports the transport failure honestly, and an interrupted
            # backfill still resumes from the last stored candle.
            if attempts == 0 and max_requests and state.requests > max_requests:
                raise BackfillError(
                    f"max_requests reached ({max_requests}) — nothing lost, "
                    f"re-run resumes where it stopped"
                )
            result: PageResult = client.klines_page(
                symbol, timeframe, limit=limit,
                start_time=start_time, end_time=end_time, market=market)
            if result.data is not None:
                _pace_for_weight(result.headers, state, weight_min=weight_min,
                                 weight_sleep=weight_sleep,
                                 low_weight_sleep=low_weight_sleep)
                return result.data
            status = result.status
            if status in (403, 451):
                state.geo_blocked = True
                raise BackfillError(
                    f"the venue blocked this request (HTTP {status}) for "
                    f"{symbol} {market} — geo-blocked network; nothing was written."
                )
            if status in (429, 418):
                state.rate_limit_stalls += 1
            attempts += 1
            if attempts > backoff_attempts:
                raise BackfillError(
                    f"transport failed after {attempts} attempts "
                    f"(last status {status}) at {fmt_ts(start_time)} — "
                    f"re-run resumes where it stopped."
                )
            state.retries += 1
            time.sleep(backoff_base * (2 ** (attempts - 1)))

    return fetch, state


def _pace_for_weight(headers: Optional[dict], state: _RateLimitState, *,
                     weight_min: int, weight_sleep: float,
                     low_weight_sleep: float) -> None:
    """Sleep longer when Binance's remaining-weight budget runs low."""
    if not headers:
        return
    try:
        remaining = int(headers.get("x-mbx-remaining-weight", ""))
    except (TypeError, ValueError):
        return
    if remaining <= weight_min:
        state.weight_sleeps += 1
        time.sleep(low_weight_sleep if remaining <= 0 else weight_sleep)


def _fetch_for_client(client, symbol: str, timeframe: str, market: str, *,
                      page_limit: int, max_requests: int, backoff_attempts: int,
                      backoff_base: float, weight_min: int, weight_sleep: float,
                      low_weight_sleep: float) -> tuple[FetchFn, _RateLimitState]:
    """Build the fetch for a transport: any ``klines_page`` client
    (BinanceClient, BybitClient, FakePagedTransport) or a demo transport."""
    if hasattr(client, "klines_page"):          # BinanceClient / FakePagedTransport
        return _rate_limited_fetch(
            client, symbol, timeframe, market, page_limit=page_limit,
            max_requests=max_requests, backoff_attempts=backoff_attempts,
            backoff_base=backoff_base, weight_min=weight_min,
            weight_sleep=weight_sleep, low_weight_sleep=low_weight_sleep)

    # SampleClient-style demo transport (klines-only; no rate limits offline)
    state = _RateLimitState()

    def fetch(start_time=None, end_time=None, limit: int = page_limit) -> pd.DataFrame:
        state.requests += 1
        return client.klines(symbol, timeframe, limit=limit,
                             start_time=start_time, end_time=end_time)

    return fetch, state


# --------------------------------------------------------------------------- #
# Paging
# --------------------------------------------------------------------------- #

def _iter_klines_pages(
    fetch: FetchFn,
    *,
    start_ts: Optional[int],
    end_ts: Optional[int],
    page_limit: int = PAGE_LIMIT,
    step_ms: int = 60_000,
):
    """Walk ``fetch`` forward until a short page or ``end_ts`` (generator).

    Cursor advances to ``last_ts + step_ms`` so we never re-request the
    last closed candle of the previous page as the *start* of the next
    (Binance ``startTime`` is inclusive).

    ``backfill`` consumes this generator so every page is persisted the
    moment it arrives — an interrupted run (cap, network drop, Ctrl+C)
    keeps everything fetched so far, and the next run resumes from the
    last stored candle instead of starting over.
    """
    cursor = start_ts
    seen_last: Optional[int] = None
    while True:
        page = fetch(start_time=cursor, end_time=end_ts, limit=page_limit)
        if page is None or getattr(page, "empty", True):
            return
        page = page.sort_values("ts").reset_index(drop=True)
        last = int(page["ts"].iloc[-1])
        if seen_last is not None and last <= seen_last:
            return
        yield page
        seen_last = last
        if len(page) < page_limit:
            return
        if end_ts is not None and last >= end_ts:
            return
        nxt = last + step_ms
        if cursor is not None and nxt <= cursor:
            return
        cursor = nxt


def iter_klines_pages(
    fetch: FetchFn,
    *,
    start_ts: Optional[int],
    end_ts: Optional[int],
    page_limit: int = PAGE_LIMIT,
    step_ms: int = 60_000,
) -> list[pd.DataFrame]:
    """List form of :func:`_iter_klines_pages` (backwards-compatible)."""
    return list(_iter_klines_pages(
        fetch, start_ts=start_ts, end_ts=end_ts,
        page_limit=page_limit, step_ms=step_ms))


# --------------------------------------------------------------------------- #
# Backfill
# --------------------------------------------------------------------------- #

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
    client=None,
    page_limit: int = PAGE_LIMIT,
    sleep_s: float = 0.0,
    resume: bool = True,
    max_requests: int = 0,
    backoff_attempts: int = 3,
    backoff_base: float = 1.0,
    weight_min: int = 100,
    weight_sleep: float = 5.0,
    low_weight_sleep: float = 20.0,
    clock: Optional[Callable[[], int]] = None,
    dry_run: bool = False,
) -> BackfillResult:
    """Paginated REST backfill into ``store``. Returns a row-count report.

    ``rows_added`` is ``count_after - count_before`` — a re-run of the
    same range reports **0**. ``sleep_s`` is the rate-limit courtesy sleep
    between pages; the default transport (Binance) additionally retries
    with exponential backoff, paces on the weight header, and aborts fast
    on geo-blocks. ``max_requests`` caps pages per run (0 = unlimited);
    an interrupted run resumes via ``resume=True``. ``dry_run`` fetches
    and counts without writing.
    """
    step = _step_ms(timeframe)
    demo = os.getenv("DEMO_MODE", "0") in ("1", "true", "yes")
    now = clock() if clock is not None else int(time.time() * 1000)
    # Unbounded end_ts pages forever against the offline SampleClient (its
    # synthetic venue never runs out of history) and is meaningless against
    # the real API (no future candles). Bound it at now.
    end_ts = end_ts if end_ts is not None else now

    if fetch is None:
        fetch, rl = _fetch_for_client(
            client if client is not None else maybe_client(),
            symbol, timeframe, market, page_limit=page_limit,
            max_requests=max_requests, backoff_attempts=backoff_attempts,
            backoff_base=backoff_base, weight_min=weight_min,
            weight_sleep=weight_sleep, low_weight_sleep=low_weight_sleep)
    else:
        rl = _RateLimitState()

    before = store.count(exchange, market, symbol, timeframe)
    existing = store.read(exchange, market, symbol, timeframe)
    resumed_from: Optional[int] = None
    cursor = start_ts
    if resume and not existing.empty:
        resumed_from = int(existing["ts"].max()) + step
        if cursor is None or resumed_from > cursor:
            cursor = resumed_from

    pages = _iter_klines_pages(
        fetch, start_ts=cursor, end_ts=end_ts,
        page_limit=page_limit, step_ms=step,
    )

    sleeps = 0
    last_ts: Optional[int] = None
    existing_ts = {int(t) for t in existing["ts"]} if dry_run else None
    forming_skipped = 0
    dry_new = 0
    pages_seen = 0
    for i, page in enumerate(pages):
        pages_seen += 1
        page = page.copy()
        closed = (page["ts"] + step) <= now           # forming tail → not closed
        page["closed"] = closed
        forming_skipped += int((~closed).sum())
        if dry_run:
            dry_new += len({int(t) for t in page["ts"][closed]} - existing_ts)
        else:
            frame = normalise_klines(
                page[closed], exchange=exchange, market=market,
                symbol=symbol, timeframe=timeframe, source="rest",
            )
            store.write(frame)
        if not page.empty:
            last_ts = int(page["ts"].max())
        if i > 0 and sleep_s:                    # between pages, not after the last
            time.sleep(sleep_s)
            sleeps += 1

    after = store.count(exchange, market, symbol, timeframe)
    if last_ts is None and not existing.empty:
        last_ts = int(existing["ts"].max())
    return BackfillResult(
        exchange=exchange, market=market, symbol=symbol, timeframe=timeframe,
        pages=pages_seen, rows_before=before, rows_after=after,
        rows_added=dry_new if dry_run else after - before,
        resumed_from=resumed_from, last_ts=last_ts, sleeps=sleeps, demo=demo,
        rate_limit_stalls=rl.rate_limit_stalls, retries=rl.retries,
        geo_blocked=rl.geo_blocked, forming_skipped=forming_skipped,
        requests=rl.requests,
    )


# --------------------------------------------------------------------------- #
# Offline fake transport (tests + explicit demo sandbox)
# --------------------------------------------------------------------------- #

def _seed(key: str) -> int:
    """Deterministic seed (crc32 — plain hash() is salted per process)."""
    return zlib.crc32(key.encode("utf-8"))


class FakePagedTransport:
    """Deterministic offline stand-in for ``BinanceClient.klines_page``.

    Generates Binance-shaped 12-column OHLCV pages on demand (same shape as
    the real API), honouring ``start_time`` / ``end_time`` / ``limit``.
    ``faults`` injects transient HTTP errors keyed by request number
    (1-based; consumed on first hit so a retry succeeds) and
    ``weight_budget`` simulates Binance's ``x-mbx-remaining-weight`` header
    so rate-limit pacing is testable without a network.
    """

    def __init__(self, start_ts: Optional[int] = None,
                 end_ts: Optional[int] = None, *,
                 seed: int = 7,
                 faults: Optional[dict[int, Optional[int]]] = None,
                 weight_budget: Optional[int] = None,
                 base_prices: Optional[dict[str, float]] = None):
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.seed = seed
        self.faults = dict(faults or {})
        self.weight_budget = weight_budget
        self.base_prices = dict(base_prices or {
            "BTCUSDT": 60_000.0, "ETHUSDT": 3_000.0, "XAUUSD": 2_300.0})
        self.requests = 0
        self.calls: list[dict] = []           # (symbol, market, start_time, limit)
        self._frames: dict[tuple[str, str], pd.DataFrame] = {}

    # -- generation --------------------------------------------------------- #
    def _frame(self, symbol: str, timeframe: str) -> pd.DataFrame:
        key = (symbol, timeframe)
        if key in self._frames:
            return self._frames[key]
        tf = TIMEFRAME_TO_MS[timeframe]
        start = self.start_ts if self.start_ts is not None else 1_700_000_000_000
        end = self.end_ts if self.end_ts is not None else start + 100_000 * tf
        first_open = ((start + tf - 1) // tf) * tf        # align up to a candle boundary
        n = max(0, (end - first_open) // tf)
        rng = np.random.default_rng(_seed(f"{symbol}:{timeframe}:{self.seed}"))
        base = self.base_prices.get(symbol, 100.0)
        ts = first_open + np.arange(n, dtype=np.int64) * tf
        close = base + np.cumsum(rng.normal(0.005 * base / 100, base * 0.004, n))
        close = np.maximum(base * 0.1, close)
        high = close * (1 + np.abs(rng.normal(0, 0.0015, n)))
        low = close * (1 - np.abs(rng.normal(0, 0.0015, n)))
        high = np.maximum(high, np.maximum(close, low) * 1.001)
        low = np.minimum(low, np.minimum(close, high) * 0.999)
        volume = rng.uniform(50, 400, n)
        frame = pd.DataFrame({
            "ts": ts,
            "open": np.round(close, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(volume, 4),
            "close_ts": ts + tf - 1,
            "quote_volume": np.round(volume * close, 2),
            "trades": rng.integers(50, 2000, n),
            "taker_buy_base": np.round(volume * 0.5, 4),
            "taker_buy_quote": np.round(volume * 0.5 * close, 2),
            "ignore": np.zeros(n, dtype=np.int64),
        })
        self._frames[key] = frame
        return frame

    # -- transport contract -------------------------------------------------- #
    def klines_page(self, symbol: str, timeframe: str, limit: int = 1000,
                    start_time: Optional[int] = None,
                    end_time: Optional[int] = None,
                    market: str = "spot") -> PageResult:
        self.requests += 1
        self.calls.append({"symbol": symbol, "market": market,
                           "start_time": start_time, "end_time": end_time,
                           "limit": limit})
        if self.faults and self.requests in self.faults:
            status = self.faults.pop(self.requests)
            return PageResult(None, self._headers(), status)
        frame = self._frame(symbol, timeframe)
        page = frame[frame["ts"] >= (start_time if start_time is not None else 0)]
        if end_time is not None:
            page = page[page["ts"] <= end_time]
        page = page.head(int(limit)).reset_index(drop=True)
        # Like the real API, the remaining-weight header reflects the budget
        # AFTER this request was served.
        if self.weight_budget is not None:
            self.weight_budget = max(0, self.weight_budget - 2)
        return PageResult(page, self._headers(), 200)

    def _headers(self) -> dict:
        if self.weight_budget is None:
            return {}
        return {"x-mbx-remaining-weight": str(self.weight_budget)}


# --------------------------------------------------------------------------- #
# P12.3.2 — offline CSV import (real market data without a live socket)
# --------------------------------------------------------------------------- #

_KLINES_12_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume",
    "ignore",
]

_VISION_6_COLS = ["open_time_ms", "open", "high", "low", "close", "volume"]


def _read_ohlcv_csv(csv_path: str | Path) -> tuple[pd.DataFrame, bytes, str]:
    """Read a Binance-style OHLCV CSV (optionally gzipped) into a raw frame.

    Accepted layouts (Binance public-archive exports and raw klines rows):

    - header ``open_time_ms,open,high,low,close,volume`` (Vision 6-col)
    - header ``open_time,open,high,low,close,volume,...`` (12-col klines)
    - header ``timestamp,open,high,low,close,volume`` (dukascopy-node)
    - headerless 12-col klines rows
    - headerless 6-col rows

    Returns ``(frame with ts/open/high/low/close/volume, raw_bytes, sha256)``
    where the digest is of the **decompressed** bytes, so a published pin
    of the uncompressed file can be verified regardless of transport.
    """
    path = Path(csv_path)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    digest = hashlib.sha256(raw).hexdigest()
    buf = io.BytesIO(raw)
    first = raw.split(b"\n", 1)[0]
    headerless = not any(ch.isalpha() for ch in first.decode("utf-8", "ignore"))
    if headerless:
        df = pd.read_csv(buf, header=None)
        if df.shape[1] >= 12:
            df.columns = _KLINES_12_COLS[: df.shape[1]]
        elif df.shape[1] == 6:
            df.columns = _VISION_6_COLS
        else:
            raise BackfillError(
                f"headerless CSV has {df.shape[1]} columns; expected 6 or 12")
    else:
        df = pd.read_csv(buf)
    if "ts" not in df.columns:
        # Binance archives use open_time[_ms]; dukascopy-node's canonical CSV
        # output uses timestamp (UTC epoch ms).
        for cand in ("open_time", "open_time_ms", "timestamp"):
            if cand in df.columns:
                df = df.rename(columns={cand: "ts"})
                break
    missing = {"ts", "open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise BackfillError(
            f"CSV is missing required columns: {sorted(missing)}")
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    if df["ts"].isna().any():
        raise BackfillError("CSV contains non-numeric timestamps")
    df["ts"] = df["ts"].astype(np.int64)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df, raw, digest


def backfill_from_csv(
    *,
    store: CandleStore,
    csv_path: str | Path,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
    exchange: str = "binance",
    market: str = "spot",
    expected_sha256: Optional[str] = None,
    source: str = "csv",
    price_type: str = "",
) -> dict:
    """P12.3.2 — import a local Binance-style OHLCV CSV into the store.

    Same adapter boundary as the REST backfill: rows are validated,
    sorted, normalised through ``normalise_klines()`` and upserted by
    ``CandleStore.write()``, so a re-run of the same file adds zero rows
    (idempotent by the primary key). Nothing is fetched from a network:
    this is the offline transport for real market data.

    ``expected_sha256`` is the provenance pin: the digest of the
    **decompressed** file must match it or the import refuses to write
    anything. Rows that fail sanity (non-positive prices, inverted
    high/low) are dropped and counted, never fixed silently. Duplicate
    timestamps and step misalignment are counted and reported; gaps are
    measured with the same detector the P10.3 repair path uses.

    Returns a report dict (``ok`` is False only for hard parse failures,
    which are raised as ``BackfillError`` instead).
    """
    from data.gaps import detect_gaps, step_ms

    if price_type not in ("", "bid", "ask"):
        raise BackfillError("price_type must be empty, 'bid', or 'ask'")
    frame, _raw, digest = _read_ohlcv_csv(csv_path)
    if expected_sha256 and digest.lower() != expected_sha256.strip().lower():
        raise BackfillError(
            f"sha256 mismatch: file {digest} != pin {expected_sha256.strip()} "
            f"(nothing was written)")
    step = step_ms(timeframe)
    frame = frame.sort_values("ts").reset_index(drop=True)
    n_read = len(frame)
    duplicates = int(frame["ts"].duplicated().sum())
    frame = frame.drop_duplicates(subset=["ts"], keep="last").reset_index(drop=True)

    pos = (frame["open"] > 0) & (frame["high"] > 0) & (frame["low"] > 0) \
        & (frame["close"] > 0) & (frame["volume"] >= 0)
    sane = pos & (frame["high"] >= frame[["open", "close"]].max(axis=1)) \
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
    sanity_dropped = int((~sane).sum())
    frame = frame[sane].reset_index(drop=True)

    misaligned = int((frame["ts"] % step != 0).sum())

    existing = store.read(exchange, market, symbol, timeframe)
    existing_price_types = ({str(v) for v in existing.get("price_type", [])
                             if str(v)} if not existing.empty else set())
    if price_type and existing_price_types and existing_price_types != {price_type}:
        raise BackfillError(
            f"price_type mismatch: existing series is "
            f"{sorted(existing_price_types)}, import is {price_type}; "
            f"bid/ask candles must not share one store series")

    before = len(existing)
    if not frame.empty:
        canon = normalise_klines(
            frame, exchange=exchange, market=market, symbol=symbol,
            timeframe=timeframe, source=source, price_type=price_type,
        )
        store.write(canon)
    after = store.count(exchange, market, symbol, timeframe)

    # P12.9: judge gaps against the venue's calendar. Crypto stays 24/7;
    # a Dukascopy XAU import no longer reports the gold weekend as missing data.
    from data.calendar import calendar_for
    cal = calendar_for(exchange, market, symbol)
    gaps = detect_gaps(store.read(exchange, market, symbol, timeframe),
                       timeframe, cal) if after else []
    closed_bars = 0
    if not frame.empty and not getattr(cal, "always_open", True):
        from data.calendar import closed_bar_count
        closed_bars = closed_bar_count(
            int(frame["ts"].iloc[0]), int(frame["ts"].iloc[-1]), step, cal)
    first_ts = int(frame["ts"].iloc[0]) if not frame.empty else None
    last_ts = int(frame["ts"].iloc[-1]) if not frame.empty else None
    return {
        "ok": True,
        "exchange": exchange, "market": market, "symbol": symbol,
        "timeframe": timeframe, "source": source,
        "price_type": price_type,
        "csv_path": str(csv_path),
        "sha256": digest,
        "sha256_verified": bool(expected_sha256),
        "rows_read": n_read,
        "rows_added": after - before,
        "rows_after": after,
        "duplicates_dropped": duplicates,
        "sanity_dropped": sanity_dropped,
        "misaligned_ts": misaligned,
        "calendar": getattr(cal, "name", "crypto-24x7"),
        "closed_session_bars": closed_bars,
        "gaps_found": len(gaps),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "span_days": round((last_ts - first_ts) / 86_400_000, 2)
        if first_ts is not None else 0.0,
    }
