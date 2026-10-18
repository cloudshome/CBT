"""data/derivatives.py — P10.4: derivatives as time series.

The roadmap is ``docs/DATA_INFRASTRUCTURE_ROADMAP.md`` (Layer 2); this is
milestone **P10.4**: persist funding / OI / mark / index / basis over time
so the engine can reason over *stored* derivatives state instead of one
live snapshot, and rename the ``liquidations()`` 24h-stats proxy honestly
(done in ``data/binance_client.py`` — ``liquidation_stats_proxy``).

Design rules (same spine as the candle store — do not bend):

1. ``ts`` is always UTC epoch ms, the **open**/timestamp of the record.
2. One normalised row shape for every metric: ``(ts, exchange, market,
   symbol, metric, value, ingested_at)`` — analytics never sees a
   venue-specific shape.
3. Primary key ``(exchange, market, symbol, metric, ts)`` — upsert on
   conflict kills the duplicate-row bug class.
4. Read-only by design: public endpoints only, no credentials, ever.
5. Offline-first: ``FakeDerivativesTransport`` is deterministic, and
   ``DEMO_MODE=1`` (``SampleClient``) serves the same methods so the
   collector runs with zero network.
6. **Store first. Do not turn these into trading rules until the data
   proves them** (the roadmap's discipline for Layer 2).
"""

from __future__ import annotations

import os
import time
import zlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.binance_client import TIMEFRAME_TO_MS, BinanceClient

# --------------------------------------------------------------------------- #
# Canonical schema
# --------------------------------------------------------------------------- #

DERIVATIVE_COLUMNS: list[str] = [
    "ts",
    "exchange",
    "market",
    "symbol",
    "metric",
    "value",
    "ingested_at",
]
DERIVATIVE_PK: list[str] = ["exchange", "market", "symbol", "metric", "ts"]

# Metric names the collector understands (also the store's partition level).
FUNDING_RATE = "funding_rate"
OPEN_INTEREST = "open_interest"
OPEN_INTEREST_VALUE = "open_interest_value"
MARK_PRICE = "mark_price"
INDEX_PRICE = "index_price"
BASIS = "basis"

ALL_METRICS: tuple[str, ...] = (
    FUNDING_RATE,
    OPEN_INTEREST,
    OPEN_INTEREST_VALUE,
    MARK_PRICE,
    INDEX_PRICE,
    BASIS,
)

DEFAULT_OA_PERIOD = "1h"  # open-interest history bucket
DEFAULT_OA_TIMEFRAME = "1h"  # mark/index kline timeframe
FUNDING_STEP_MS = 8 * 3_600_000  # Binance funding interval (BTCUSDT) —
# not a kline interval, so it lives outside TIMEFRAME_TO_MS

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "store" / "derivatives"

_STR_COLS = {"exchange", "market", "symbol", "metric"}
_INT_COLS = {"ts", "ingested_at"}
_FLOAT_COLS = {"value"}


def empty_frame() -> pd.DataFrame:
    """Empty canonical derivatives frame (right columns, right dtypes)."""
    data: dict[str, object] = {}
    for col in DERIVATIVE_COLUMNS:
        if col in _STR_COLS:
            data[col] = pd.Series(dtype="string")
        elif col in _INT_COLS:
            data[col] = pd.Series(dtype=np.int64)
        else:
            data[col] = pd.Series(dtype=np.float64)
    return pd.DataFrame(data)


def coerce_derivative_frame(frame: pd.DataFrame | list[dict]) -> pd.DataFrame:
    """Coerce arbitrary derivative-shaped input into the canonical schema."""
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(list(frame))
    if frame.empty:
        return empty_frame()
    out = pd.DataFrame(index=frame.index)
    for col in DERIVATIVE_COLUMNS:
        if col in frame.columns:
            out[col] = frame[col]
        else:
            out[col] = "" if col in _STR_COLS else (0 if col in _INT_COLS else 0.0)
    for col in _STR_COLS:
        out[col] = out[col].fillna("").astype("string")
    for col in _INT_COLS:
        out[col] = out[col].fillna(0).astype(np.int64)
    out["value"] = out["value"].fillna(0.0).astype(np.float64)
    return out[DERIVATIVE_COLUMNS]


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


class DerivativesStore:
    """Partitioned Parquet derivatives store with an upsert primary key.

    Layout (gitignored under ``data/store/``)::

        data/store/derivatives/
            exchange=binance/market=perp/symbol=BTCUSDT/metric=funding_rate/
                year=2024/month=01/part-000.parquet
    """

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else DEFAULT_ROOT

    def _series_dir(self, exchange: str, market: str, symbol: str, metric: str) -> Path:
        return (
            self.root
            / f"exchange={exchange}"
            / f"market={market}"
            / f"symbol={symbol}"
            / f"metric={metric}"
        )

    def _partition_paths(self, frame: pd.DataFrame):
        dt = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        years = dt.dt.year.to_numpy()
        months = dt.dt.month.to_numpy()
        groups: dict[tuple[int, int], list[int]] = {}
        for i, (y, m) in enumerate(zip(years, months)):
            groups.setdefault((int(y), int(m)), []).append(i)
        exchange = frame["exchange"].iloc[0]
        market = frame["market"].iloc[0]
        symbol = frame["symbol"].iloc[0]
        metric = frame["metric"].iloc[0]
        base = self._series_dir(exchange, market, symbol, metric)
        for (year, month), idxs in sorted(groups.items()):
            yield (
                year,
                month,
                base / f"year={year:04d}" / f"month={month:02d}",
                frame.iloc[idxs],
            )

    def write(self, frame: pd.DataFrame | list[dict]) -> int:
        """Upsert derivative rows (last write wins on the PK)."""
        df = coerce_derivative_frame(frame)
        if df.empty:
            return 0
        total = 0
        for _y, _m, part_dir, sub in self._partition_paths(df):
            part_dir.mkdir(parents=True, exist_ok=True)
            path = part_dir / "part-000.parquet"
            sub = sub.reset_index(drop=True)
            if path.exists():
                merged = pd.concat([pd.read_parquet(path), sub], ignore_index=True)
            else:
                merged = sub
            merged = merged.drop_duplicates(subset=DERIVATIVE_PK, keep="last")
            merged = merged.sort_values("ts").reset_index(drop=True)
            merged.to_parquet(path, index=False)
            total += len(sub)
        return total

    def read(
        self,
        exchange: str,
        market: str,
        symbol: str,
        metric: str,
        *,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> pd.DataFrame:
        """Return rows for a metric series, deduplicated, sorted by ``ts``."""
        series_dir = self._series_dir(exchange, market, symbol, metric)
        if not series_dir.exists():
            return empty_frame()
        parts = sorted(series_dir.rglob("part-*.parquet"))
        if not parts:
            return empty_frame()
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        df = df.drop_duplicates(subset=DERIVATIVE_PK, keep="last")
        df = df.sort_values("ts").reset_index(drop=True)
        if start_ts is not None:
            df = df[df["ts"] >= start_ts].reset_index(drop=True)
        if end_ts is not None:
            df = df[df["ts"] <= end_ts].reset_index(drop=True)
        return df

    def count(self, exchange: str, market: str, symbol: str, metric: str) -> int:
        return len(self.read(exchange, market, symbol, metric))

    def metrics(self, exchange: str, market: str, symbol: str) -> list[str]:
        """List metrics stored for a series."""
        base = (
            self.root / f"exchange={exchange}" / f"market={market}" / f"symbol={symbol}"
        )
        if not base.exists():
            return []
        return sorted(
            p.name.replace("metric=", "") for p in base.glob("metric=*") if p.is_dir()
        )


# --------------------------------------------------------------------------- #
# Basis derivation
# --------------------------------------------------------------------------- #


def _price_col(frame: pd.DataFrame, raw: str) -> str:
    """Raw fetch frames use ``mark_price``/``index_price``; canonical store
    frames use ``value``. Accept both."""
    return raw if raw in frame.columns else "value"


def derive_basis(
    mark: pd.DataFrame,
    index: pd.DataFrame,
    *,
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    ingested_at: int | None = None,
) -> pd.DataFrame:
    """basis = mark − index at each timestamp where both are known.

    ``mark`` / ``index`` need ``ts`` and a price column (``mark_price`` /
    ``index_price`` for raw fetch frames, ``value`` for canonical store
    frames). Returns a canonical frame of ``basis`` rows.
    """
    if mark.empty or index.empty:
        return empty_frame()
    m = mark[["ts", _price_col(mark, "mark_price")]].copy()
    i = index[["ts", _price_col(index, "index_price")]].copy()
    m = m.rename(columns={m.columns[1]: "mark_price"})
    i = i.rename(columns={i.columns[1]: "index_price"})
    merged = pd.merge(m, i, on="ts", how="inner")
    if merged.empty:
        return empty_frame()
    ingest = ingested_at if ingested_at is not None else int(time.time() * 1000)
    return coerce_derivative_frame(
        pd.DataFrame(
            {
                "ts": merged["ts"].astype("int64"),
                "exchange": exchange,
                "market": market,
                "symbol": symbol,
                "metric": BASIS,
                "value": (merged["mark_price"] - merged["index_price"]).astype(float),
                "ingested_at": ingest,
            }
        )
    )


# --------------------------------------------------------------------------- #
# Transport contract
# --------------------------------------------------------------------------- #


class DerivativesTransportError(Exception):
    """A derivatives fetch failed (network, geo-block, exhausted retries)."""


class _TransientFetchError(Exception):
    """Injected one-off fault (offline fake transport) — retryable."""


def _futures_pair(symbol: str) -> str | None:
    from data.symbols import resolve_symbol

    return resolve_symbol(symbol).futures_symbol


class BinanceDerivativesTransport:
    """Adapter over :class:`BinanceClient`'s new history endpoints.

    Retries transient failures with exponential backoff, aborts immediately
    on geo-blocks (403/451), and converts ``None`` (unreachable) into a
    clear :class:`DerivativesTransportError`.
    """

    def __init__(
        self,
        client: BinanceClient | None = None,
        *,
        backoff_attempts: int = 3,
        backoff_base: float = 1.0,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.client = client if client is not None else BinanceClient()
        self.backoff_attempts = backoff_attempts
        self.backoff_base = backoff_base
        self.sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
        self.requests = 0
        self.retries = 0
        self.rate_limit_stalls = 0
        self.geo_blocked = False

    # -- generic fetch with retry/geo-block handling ----------------------- #
    def _fetch(self, method: str, *args, what: str):
        attempts = 0
        while True:
            self.requests += 1
            fn = getattr(self.client, method)
            try:
                result = fn(*args)
            except Exception as exc:  # transport error
                attempts += 1
                if attempts > self.backoff_attempts:
                    raise DerivativesTransportError(
                        f"{what}: transport failed after {attempts} attempts "
                        f"({exc!r}) — re-run resumes where it stopped"
                    ) from exc
                self.retries += 1
                self.sleep_fn(self.backoff_base * (2 ** (attempts - 1)))
                continue
            if result is not None:
                return result
            attempts += 1
            if attempts > self.backoff_attempts:
                raise DerivativesTransportError(
                    f"{what}: futures endpoints unreachable after {attempts} "
                    f"attempts — geo-blocked network or futures down; "
                    f"nothing was written."
                )
            # None = futures unreachable (geo-block) — do not hammer.
            self.geo_blocked = True
            self.sleep_fn(self.backoff_base * (2 ** (attempts - 1)))
        raise AssertionError("unreachable")

    def funding_rate_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        return self._fetch(
            "funding_rate_history",
            symbol,
            start_time,
            end_time,
            limit,
            what="funding history",
        )

    def open_interest_page(
        self, symbol: str, start_time, end_time, limit: int = 500
    ) -> pd.DataFrame:
        return self._fetch(
            "open_interest_history",
            symbol,
            DEFAULT_OA_PERIOD,
            start_time,
            end_time,
            limit,
            what="OI history",
        )

    def mark_price_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        return self._fetch(
            "mark_price_klines",
            symbol,
            DEFAULT_OA_TIMEFRAME,
            start_time,
            end_time,
            limit,
            what="mark prices",
        )

    def index_price_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        return self._fetch(
            "index_price_klines",
            symbol,
            DEFAULT_OA_TIMEFRAME,
            start_time,
            end_time,
            limit,
            what="index prices",
        )


# --------------------------------------------------------------------------- #
# Offline fake transport (tests + DEMO_MODE)
# --------------------------------------------------------------------------- #


def _seed(key: str) -> int:
    """Deterministic seed (crc32 — plain hash() is salted per process)."""
    return zlib.crc32(key.encode("utf-8"))


class FakeDerivativesTransport:
    """Deterministic offline stand-in for the derivatives history endpoints.

    Serves the same four methods as :class:`BinanceDerivativesTransport`
    from seeded synthetic series. ``faults`` injects transient
    ``DerivativesTransportError``-style failures keyed by request number
    (1-based, consumed on first hit so a retry succeeds).
    """

    def __init__(
        self,
        *,
        seed: int = 7,
        start_ts: int | None = None,
        end_ts: int | None = None,
        faults: dict[int, Exception] | None = None,
        base_prices: dict[str, float] | None = None,
    ):
        self.seed = seed
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.faults = dict(faults or {})
        self.base_prices = dict(base_prices or {"BTCUSDT": 60_000.0})
        self.requests = 0
        self._frames: dict[tuple[str, str], pd.DataFrame] = {}

    def _raise_fault(self):
        self.requests += 1
        if self.faults and self.requests in self.faults:
            exc = self.faults.pop(self.requests)
            raise _TransientFetchError(str(exc))

    def _funding(self, symbol: str) -> pd.DataFrame:
        key = ("funding", symbol)
        if key in self._frames:
            return self._frames[key]
        start = self.start_ts if self.start_ts is not None else 1_700_000_000_000
        end = self.end_ts if self.end_ts is not None else start + 366 * 8 * 3_600_000
        step = 8 * 3_600_000
        first = ((start + step - 1) // step) * step
        n = max(0, (end - first) // step)
        rng = np.random.default_rng(_seed(f"{symbol}:funding:{self.seed}"))
        ts = first + np.arange(n, dtype=np.int64) * step
        base = self.base_prices.get(symbol, 60_000.0)
        rate = rng.normal(0.0001, 0.0002, n)  # ~0.01%/8h mean
        mark = base + np.cumsum(rng.normal(0, base * 0.002, n))
        df = pd.DataFrame(
            {"ts": ts, "funding_rate": rate, "mark_price": np.round(mark, 2)}
        )
        self._frames[key] = df
        return df

    def _oi(self, symbol: str) -> pd.DataFrame:
        key = ("oi", symbol)
        if key in self._frames:
            return self._frames[key]
        start = self.start_ts if self.start_ts is not None else 1_700_000_000_000
        end = self.end_ts if self.end_ts is not None else start + 366 * 24 * 3_600_000
        step = 3_600_000
        first = ((start + step - 1) // step) * step
        n = max(0, (end - first) // step)
        rng = np.random.default_rng(_seed(f"{symbol}:oi:{self.seed}"))
        ts = first + np.arange(n, dtype=np.int64) * step
        base = self.base_prices.get(symbol, 60_000.0)
        oi = base * 100_000 + np.cumsum(rng.normal(0, base * 50, n))  # notional-ish
        oi = np.maximum(base * 10_000, oi)
        df = pd.DataFrame(
            {
                "ts": ts,
                "open_interest": np.round(oi, 2),
                "open_interest_value": np.round(oi * base, 2),
            }
        )
        self._frames[key] = df
        return df

    def _price_klines(self, symbol: str, col: str) -> pd.DataFrame:
        key = (col, symbol)
        if key in self._frames:
            return self._frames[key]
        start = self.start_ts if self.start_ts is not None else 1_700_000_000_000
        end = self.end_ts if self.end_ts is not None else start + 366 * 24 * 3_600_000
        step = 3_600_000
        first = ((start + step - 1) // step) * step
        n = max(0, (end - first) // step)
        rng = np.random.default_rng(_seed(f"{symbol}:{col}:{self.seed}"))
        ts = first + np.arange(n, dtype=np.int64) * step
        base = self.base_prices.get(symbol, 60_000.0)
        prices = base + np.cumsum(rng.normal(0, base * 0.001, n))
        df = pd.DataFrame({"ts": ts, col: np.round(prices, 2)})
        self._frames[key] = df
        return df

    # -- transport contract -------------------------------------------------- #
    def funding_rate_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        self._raise_fault()
        df = self._funding(symbol)
        df = df[df["ts"] >= (start_time if start_time is not None else 0)]
        if end_time is not None:
            df = df[df["ts"] <= end_time]
        return df.head(int(limit)).reset_index(drop=True)

    def open_interest_page(
        self, symbol: str, start_time, end_time, limit: int = 500
    ) -> pd.DataFrame:
        self._raise_fault()
        df = self._oi(symbol)
        df = df[df["ts"] >= (start_time if start_time is not None else 0)]
        if end_time is not None:
            df = df[df["ts"] <= end_time]
        return df.head(int(limit)).reset_index(drop=True)

    def mark_price_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        self._raise_fault()
        df = self._price_klines(symbol, "mark_price")
        df = df[df["ts"] >= (start_time if start_time is not None else 0)]
        if end_time is not None:
            df = df[df["ts"] <= end_time]
        return df.head(int(limit)).reset_index(drop=True)

    def index_price_page(
        self, symbol: str, start_time, end_time, limit: int = 1000
    ) -> pd.DataFrame:
        self._raise_fault()
        df = self._price_klines(symbol, "index_price")
        df = df[df["ts"] >= (start_time if start_time is not None else 0)]
        if end_time is not None:
            df = df[df["ts"] <= end_time]
        return df.head(int(limit)).reset_index(drop=True)


def default_derivatives_transport():
    """DEMO_MODE → SampleClient-backed transport; else Binance."""
    if os.getenv("DEMO_MODE", "0") in ("1", "true", "yes"):
        from data.sample_client import SampleClient

        return BinanceDerivativesTransport(SampleClient())
    return BinanceDerivativesTransport()


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #


@dataclass
class MetricRun:
    metric: str
    pages: int = 0
    rows_fetched: int = 0
    rows_new: int = 0
    first_ts: int | None = None
    last_ts: int | None = None
    skipped_forming: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _page_all(
    fetch,
    *,
    symbol: str,
    start_ts: int | None,
    end_ts: int | None,
    page_limit: int,
    step_ms: int,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    sleep_fn: Callable[[float], None] = time.sleep,
):
    """Page ``fetch(symbol, start_time, end_time, limit)`` forward.

    Generator yielding frames; cursor advances ``last_ts + step_ms`` so the
    last row of a page is never re-requested as the first of the next.
    Transient faults (offline fake injection) are retried with exponential
    backoff; terminal :class:`DerivativesTransportError` propagates.
    """
    cursor = start_ts
    seen_last: int | None = None
    while True:
        attempts = 0
        while True:
            try:
                page = fetch(symbol, cursor, end_ts, page_limit)
                break
            except _TransientFetchError:
                attempts += 1
                if attempts > max_retries:
                    raise DerivativesTransportError(
                        f"{symbol}: fetch failed after {attempts} attempts"
                    )
                sleep_fn(backoff_base * (2 ** (attempts - 1)))
        if page is None or page.empty:
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


class DerivativesCollector:
    """Collect derivatives history into a :class:`DerivativesStore`.

    Resumable per metric (re-runs continue at the last stored timestamp),
    idempotent (upsert PK → a completed re-run adds zero rows), and
    rate-limit/geo-block aware via the transport.
    """

    def __init__(
        self,
        store: DerivativesStore,
        transport=None,
        *,
        sleep_s: float = 0.2,
        page_limit: int = 1000,
        oa_page_limit: int = 500,
        clock: Callable[[], int] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.store = store
        self.transport = (
            transport if transport is not None else default_derivatives_transport()
        )
        self.sleep_s = sleep_s
        self.page_limit = page_limit
        self.oa_page_limit = oa_page_limit
        self.clock = clock if clock is not None else (lambda: int(time.time() * 1000))
        self.sleep_fn = sleep_fn if sleep_fn is not None else time.sleep

    # -- public -------------------------------------------------------------- #
    def collect(
        self,
        symbol: str,
        market: str = "perp",
        *,
        since: int | None = None,
        until: int | None = None,
        metrics: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, MetricRun]:
        """Collect the requested metrics (default: all six)."""
        from data.symbols import resolve_symbol

        spec = resolve_symbol(symbol)
        if market != "perp":
            raise DerivativesTransportError(
                f"derivatives only exist for perp markets — got '{market}' "
                f"(spot has no funding/OI/mark series)"
            )
        if not spec.futures_symbol:
            raise DerivativesTransportError(
                f"{spec.symbol} has no Binance perp market — derivatives "
                f"cannot be collected"
            )
        now = self.clock()
        until = int(until) if until is not None else now
        want = list(metrics) if metrics else list(ALL_METRICS)
        unknown = [m for m in want if m not in ALL_METRICS]
        if unknown:
            raise DerivativesTransportError(
                f"unknown metrics {unknown} — use one of {', '.join(ALL_METRICS)}"
            )

        runs: dict[str, MetricRun] = {}
        # mark + index must both be fetched before basis can be derived
        collect_mark = MARK_PRICE in want or BASIS in want
        collect_index = INDEX_PRICE in want or BASIS in want

        if FUNDING_RATE in want:
            runs[FUNDING_RATE] = self._run(
                FUNDING_RATE,
                self.transport.funding_rate_page,
                spec.symbol,
                market,
                since,
                until,
                self.page_limit,
                step_ms=FUNDING_STEP_MS,
                dry_run=dry_run,
            )
        if OPEN_INTEREST in want:
            runs[OPEN_INTEREST] = self._run(
                OPEN_INTEREST,
                self.transport.open_interest_page,
                spec.symbol,
                market,
                since,
                until,
                self.oa_page_limit,
                step_ms=TIMEFRAME_TO_MS[DEFAULT_OA_PERIOD],
                dry_run=dry_run,
            )
        if OPEN_INTEREST_VALUE in want:
            runs[OPEN_INTEREST_VALUE] = self._run_value_of(
                OPEN_INTEREST,
                spec.symbol,
                market,
                since,
                until,
                dry_run=dry_run,
            )
        if collect_mark:
            runs[MARK_PRICE] = self._run(
                MARK_PRICE,
                self.transport.mark_price_page,
                spec.symbol,
                market,
                since,
                until,
                self.page_limit,
                step_ms=TIMEFRAME_TO_MS[DEFAULT_OA_TIMEFRAME],
                dry_run=dry_run,
            )
        if collect_index:
            runs[INDEX_PRICE] = self._run(
                INDEX_PRICE,
                self.transport.index_price_page,
                spec.symbol,
                market,
                since,
                until,
                self.page_limit,
                step_ms=TIMEFRAME_TO_MS[DEFAULT_OA_TIMEFRAME],
                dry_run=dry_run,
            )
        if BASIS in want and not dry_run:
            mark = self.store.read("binance", market, spec.symbol, MARK_PRICE)
            index = self.store.read("binance", market, spec.symbol, INDEX_PRICE)
            before = self.store.count("binance", market, spec.symbol, BASIS)
            basis = derive_basis(
                mark,
                index,
                exchange="binance",
                market=market,
                symbol=spec.symbol,
                ingested_at=now,
            )
            if not basis.empty:
                self.store.write(basis)
            runs[BASIS] = MetricRun(
                metric=BASIS,
                rows_fetched=len(basis),
                rows_new=max(
                    0, self.store.count("binance", market, spec.symbol, BASIS) - before
                ),
                first_ts=int(basis["ts"].iloc[0]) if not basis.empty else None,
                last_ts=int(basis["ts"].iloc[-1]) if not basis.empty else None,
            )
        return runs

    # -- internals ------------------------------------------------------------ #
    def _run(
        self,
        metric: str,
        fetch,
        symbol: str,
        market: str,
        since: int | None,
        until: int,
        page_limit: int,
        *,
        step_ms: int,
        dry_run: bool,
    ) -> MetricRun:
        existing = self.store.read("binance", market, symbol, metric)
        last_ts = int(existing["ts"].max()) if not existing.empty else None
        cursor = (
            since
            if since is not None
            else (last_ts + step_ms if last_ts is not None else None)
        )
        run = MetricRun(metric=metric)
        before = self.store.count("binance", market, symbol, metric)
        existing_ts = {int(t) for t in existing["ts"]} if dry_run else None
        for page in _page_all(
            fetch,
            symbol=symbol,
            start_ts=cursor,
            end_ts=until,
            page_limit=page_limit,
            step_ms=step_ms,
            sleep_fn=self.sleep_fn,
        ):
            run.pages += 1
            run.rows_fetched += len(page)
            if run.first_ts is None and not page.empty:
                run.first_ts = int(page["ts"].iloc[0])
            if not page.empty:
                run.last_ts = int(page["ts"].iloc[-1])
            if not dry_run:
                canonical = self._to_canonical(page, metric, market, symbol)
                self.store.write(canonical)
            else:
                run.rows_new += len({int(t) for t in page["ts"]} - existing_ts)
            if self.sleep_s:
                self.sleep_fn(self.sleep_s)
        if not dry_run:
            run.rows_new = max(
                0, self.store.count("binance", market, symbol, metric) - before
            )
        return run

    def _run_value_of(
        self,
        oi_metric: str,
        symbol: str,
        market: str,
        since: int | None,
        until: int,
        *,
        dry_run: bool,
    ) -> MetricRun:
        """open_interest_value rides along with the OI pages (same rows)."""
        existing = self.store.read("binance", market, symbol, OPEN_INTEREST_VALUE)
        last_ts = int(existing["ts"].max()) if not existing.empty else None
        cursor = (
            since
            if since is not None
            else (last_ts + 3_600_000 if last_ts is not None else None)
        )
        run = MetricRun(metric=OPEN_INTEREST_VALUE)
        before = self.store.count("binance", market, symbol, OPEN_INTEREST_VALUE)
        for page in _page_all(
            self.transport.open_interest_page,
            symbol=symbol,
            start_ts=cursor,
            end_ts=until,
            page_limit=self.oa_page_limit,
            step_ms=3_600_000,
            sleep_fn=self.sleep_fn,
        ):
            run.pages += 1
            value = page[["ts", "open_interest_value"]].copy()
            run.rows_fetched += len(value)
            if run.first_ts is None and not value.empty:
                run.first_ts = int(value["ts"].iloc[0])
            if not value.empty:
                run.last_ts = int(value["ts"].iloc[-1])
            if not dry_run:
                canonical = self._to_canonical(
                    value.rename(columns={"open_interest_value": "value"}),
                    OPEN_INTEREST_VALUE,
                    market,
                    symbol,
                )
                self.store.write(canonical)
            if self.sleep_s:
                self.sleep_fn(self.sleep_s)
        if not dry_run:
            run.rows_new = max(
                0,
                self.store.count("binance", market, symbol, OPEN_INTEREST_VALUE)
                - before,
            )
        return run

    @staticmethod
    def _to_canonical(
        page: pd.DataFrame, metric: str, market: str, symbol: str
    ) -> pd.DataFrame:
        value_col = {
            "funding_rate": "funding_rate",
            "open_interest": "open_interest",
            "open_interest_value": "value",
            "mark_price": "mark_price",
            "index_price": "index_price",
        }.get(metric, "value")
        return coerce_derivative_frame(
            pd.DataFrame(
                {
                    "ts": page["ts"].astype("int64"),
                    "exchange": "binance",
                    "market": market,
                    "symbol": symbol,
                    "metric": metric,
                    "value": page[value_col].astype(float),
                    "ingested_at": int(time.time() * 1000),
                }
            )
        )
