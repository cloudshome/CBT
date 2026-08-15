"""data/store.py — P10.1: normalised ``Candle`` schema + Parquet store.

SKY's own market-history layer. The roadmap is ``docs/DATA_INFRASTRUCTURE_ROADMAP.md``;
this is milestone **P10.1 (Schema + store)**: a normalised ``Candle`` record, a
``data/store/`` Parquet store, an upsert primary key, and offline, deterministic
round-trip / dedup / ordering behaviour.

Design rules carried from the roadmap (do not bend these):

1. ``ts`` is always the candle **OPEN** time, **UTC**, **epoch ms**, inclusive.
2. An **unclosed** candle (``closed=False``) is **never** persisted into
   immutable history. ``closed=False`` belongs in the hot cache only.
3. ``ingested_at`` is separate from ``ts`` so a venue backfilling or revising
   data after the fact is detectable.
4. Primary key ``(exchange, market, symbol, timeframe, ts)`` — upsert on
   conflict kills the duplicate-row class of bug by construction.
5. This layer is **read-only by design**: it stores public market data only.
   It cannot authenticate and cannot trade.

Storage layout (gitignored)::

    data/store/parquet/candles/
        exchange=binance/market=perp/symbol=BTCUSDT/timeframe=1m/
            year=2024/month=01/part-000.parquet

Hive-style partitioning means a query for one month reads one file, and the
whole series stays small enough to keep in ``data/store/`` on disk (never in
Git).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Canonical schema
# --------------------------------------------------------------------------- #

CANDLE_COLUMNS: list[str] = [
    "ts", "exchange", "market", "symbol", "timeframe",
    "open", "high", "low", "close", "volume", "quote_volume", "trades",
    "closed", "source", "price_type", "ingested_at",
]

PRIMARY_KEY: list[str] = ["exchange", "market", "symbol", "timeframe", "ts"]

_STR_COLS = {"exchange", "market", "symbol", "timeframe", "source", "price_type"}
_INT_COLS = {"ts", "trades", "ingested_at"}
_FLOAT_COLS = {"open", "high", "low", "close", "volume", "quote_volume"}
_BOOL_COLS = {"closed"}


def empty_frame() -> pd.DataFrame:
    """Return an empty canonical candle frame (right columns, right dtypes)."""
    data: dict[str, object] = {}
    for col in CANDLE_COLUMNS:
        if col in _STR_COLS:
            data[col] = pd.Series(dtype=str)
        elif col in _BOOL_COLS:
            data[col] = pd.Series(dtype=bool)
        elif col in _INT_COLS:
            data[col] = pd.Series(dtype=np.int64)
        else:
            data[col] = pd.Series(dtype=np.float64)
    return pd.DataFrame(data)


def coerce_candle_frame(frame: pd.DataFrame | Iterable[dict]) -> pd.DataFrame:
    """Coerce arbitrary candle-shaped input into the canonical schema.

    - fills missing optional fields with safe defaults
    - enforces the canonical column set, dtype per column
    - drops any unknown columns

    Callers should normalise ``ts`` to UTC epoch-ms **before** this (see
    ``normalise_klines``). This function is deliberately strict and cheap.
    """
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(list(frame))
    if frame.empty:
        return empty_frame()

    out = pd.DataFrame(index=frame.index)
    for col in CANDLE_COLUMNS:
        if col in frame.columns:
            out[col] = frame[col]
        else:
            if col in _STR_COLS:
                out[col] = ""
            elif col in _BOOL_COLS:
                out[col] = False
            elif col in _INT_COLS:
                out[col] = 0
            else:
                out[col] = 0.0

    for col in _STR_COLS:
        out[col] = out[col].fillna("").astype(str)
    for col in _BOOL_COLS:
        out[col] = out[col].fillna(False).astype(bool)
    for col in _INT_COLS:
        out[col] = out[col].fillna(0).astype(np.int64)
    for col in _FLOAT_COLS:
        out[col] = out[col].fillna(0.0).astype(np.float64)

    return out[CANDLE_COLUMNS]


def normalise_klines(
    ohlcv: pd.DataFrame,
    *,
    exchange: str,
    market: str,
    symbol: str,
    timeframe: str,
    source: str = "rest",
    price_type: str = "",
    ingested_at: int | None = None,
) -> pd.DataFrame:
    """Normalise a raw OHLCV frame (the adapter boundary).

    ``ohlcv`` needs at least ``ts / open / high / low / close``; ``volume``,
    ``quote_volume`` and ``trades`` are carried over when present. This is the
    single normalisation point P10.2's backfill (and any future adapter) feeds,
    so exchange-specific quirks never leak past this function.

    A ``closed`` column in the input is honoured — a forming candle
    (``closed=False``) is marked so the store can drop it before it ever
    reaches immutable history. When absent, candles are treated as closed.

    ``ts`` is expected to already be UTC epoch-ms candle OPEN time. If the
    venue reports the candle close time or seconds, normalise it *here* by
    passing ``ts`` already converted.
    """
    ingest = ingested_at if ingested_at is not None else int(time.time() * 1000)
    keep = ["ts", "open", "high", "low", "close"]
    for extra in ("volume", "quote_volume", "trades"):
        if extra in ohlcv.columns:
            keep.append(extra)

    frame = ohlcv[keep].copy()
    frame["exchange"] = exchange
    frame["market"] = market
    frame["symbol"] = symbol
    frame["timeframe"] = timeframe
    if "closed" in ohlcv.columns:
        frame["closed"] = ohlcv["closed"]   # coerce_candle_frame cleans it
    else:
        frame["closed"] = True              # history is closed unless told otherwise
    frame["source"] = source
    # Exchange candles are usually last-trade prices; Dukascopy OHLC is
    # explicitly bid or ask. Keep that distinction in the canonical row so a
    # later backtest cannot silently mix unlike price series.
    frame["price_type"] = price_type
    frame["ingested_at"] = ingest
    return coerce_candle_frame(frame)


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "store"


class CandleStore:
    """Partitioned Parquet candle store with an upsert primary key.

    ``write`` upserts on ``PRIMARY_KEY`` (last write wins) and never persists
    unclosed candles. ``read`` returns deduplicated rows ordered by ``ts``
    ascending. Both are deterministic and fully offline.
    """

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else DEFAULT_ROOT
        self.parquet_dir = self.root / "parquet" / "candles"

    # -- paths -------------------------------------------------------------- #
    def _series_dir(self, exchange: str, market: str,
                    symbol: str, timeframe: str) -> Path:
        return (
            self.parquet_dir
            / f"exchange={exchange}"
            / f"market={market}"
            / f"symbol={symbol}"
            / f"timeframe={timeframe}"
        )

    def _partition_paths(self, frame: pd.DataFrame):
        """Yield (year, month, partition_dir, subframe) for an incoming frame."""
        dt = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        years = dt.dt.year.to_numpy()
        months = dt.dt.month.to_numpy()
        groups: dict[tuple[int, int], list[int]] = {}
        for i, (y, m) in enumerate(zip(years, months)):
            groups.setdefault((int(y), int(m)), []).append(i)

        # One partition_dir per series (from first row; all rows share series).
        exchange = frame["exchange"].iloc[0]
        market = frame["market"].iloc[0]
        symbol = frame["symbol"].iloc[0]
        timeframe = frame["timeframe"].iloc[0]
        base = self._series_dir(exchange, market, symbol, timeframe)

        for (year, month), idxs in sorted(groups.items()):
            part_dir = base / f"year={year:04d}" / f"month={month:02d}"
            yield year, month, part_dir, frame.iloc[idxs]

    # -- write -------------------------------------------------------------- #
    def write(self, frame: pd.DataFrame | Iterable[dict]) -> int:
        """Upsert candles into the store. Returns rows persisted (added/changed).

        Unclosed candles (``closed == False``) are dropped: a forming candle
        changes, a stored one must not.
        """
        df = coerce_candle_frame(frame)
        df = df[df["closed"]].copy()
        if df.empty:
            return 0

        total = 0
        for _year, _month, part_dir, sub in self._partition_paths(df):
            part_dir.mkdir(parents=True, exist_ok=True)
            path = part_dir / "part-000.parquet"
            sub = sub.reset_index(drop=True)
            if path.exists():
                # Additive schema migration: old partitions predate fields
                # such as ``price_type``. Coerce before concatenation so a
                # rewrite upgrades them without NaN/object drift.
                old = coerce_candle_frame(pd.read_parquet(path))
                merged = pd.concat([old, sub], ignore_index=True)
            else:
                merged = sub
            merged = merged.drop_duplicates(subset=PRIMARY_KEY, keep="last")
            merged = merged.sort_values("ts").reset_index(drop=True)
            merged.to_parquet(path, index=False)
            total += len(sub)
        return total

    # -- read --------------------------------------------------------------- #
    def read(
        self,
        exchange: str,
        market: str,
        symbol: str,
        timeframe: str,
        *,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> pd.DataFrame:
        """Return candles for a series, deduplicated and sorted by ``ts``.

        Optional ``start_ts`` / ``end_ts`` filter the result by candle OPEN
        time (inclusive, UTC epoch ms).
        """
        series_dir = self._series_dir(exchange, market, symbol, timeframe)
        if not series_dir.exists():
            return empty_frame()

        parts = sorted(series_dir.rglob("part-*.parquet"))
        frames = [pd.read_parquet(p) for p in parts]
        if not frames:
            return empty_frame()
        df = pd.concat(frames, ignore_index=True)
        df = df.drop_duplicates(subset=PRIMARY_KEY, keep="last")
        df = df.sort_values("ts").reset_index(drop=True)

        if start_ts is not None:
            df = df[df["ts"] >= start_ts].reset_index(drop=True)
        if end_ts is not None:
            df = df[df["ts"] <= end_ts].reset_index(drop=True)
        # Readers see the current canonical schema even when a partition was
        # written by an older release. The next write upgrades it on disk.
        return coerce_candle_frame(df)

    # -- introspection ------------------------------------------------------ #
    def count(self, exchange: str, market: str,
              symbol: str, timeframe: str) -> int:
        return len(self.read(exchange, market, symbol, timeframe))

    def series(self, exchange: str, market: str,
               symbol: str, timeframe: str) -> list[str]:
        """List stored partition keys (year/month) for a series."""
        series_dir = self._series_dir(exchange, market, symbol, timeframe)
        if not series_dir.exists():
            return []
        return sorted(
            f"{p.parent.name}/{p.name}"
            for p in series_dir.glob("year=*/month=*")
        )

    def list_series(self) -> list[dict]:
        """List every stored candle series as {exchange, market, symbol, timeframe}.

        P10.5: lets the data-quality pillar inspect each stored series
        without knowing the keys up front. Empty store → ``[]``.
        """
        if not self.parquet_dir.exists():
            return []
        found: dict[tuple[str, str, str, str], dict] = {}
        for tdir in sorted(self.parquet_dir.glob(
                "exchange=*/market=*/symbol=*/timeframe=*")):
            meta: dict[str, str] = {}
            for seg in tdir.parts:
                key, _, value = seg.partition("=")
                if key in ("exchange", "market", "symbol", "timeframe"):
                    meta[key] = value
            if len(meta) == 4:
                key = (meta["exchange"], meta["market"],
                       meta["symbol"], meta["timeframe"])
                found[key] = meta
        return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------- #
# klines-style read client (P12.3.2 — real market data)
# --------------------------------------------------------------------------- #

class StoreClient:
    """Drop-in ``klines()`` reader over the Parquet store.

    P12.3.2 gives the desk its first real market history. The offline
    walkers (``backtest``, ``simulator``) take a client with
    ``klines(symbol, timeframe, limit, start_time, end_time)``; this one
    serves **stored** candles — immutable, deduplicated, ordered — with
    the same ``ts/open/high/low/close/volume`` shape and the same
    ``attrs["symbol"]`` / ``attrs["timeframe"]`` contract, so no walker
    knows whether the series came from a live socket or the store.

    It never fetches anything: a missing series returns an empty frame,
    exactly like the demo client outside its synthetic range.
    """

    def __init__(self, store: CandleStore | None = None, *,
                 exchange: str = "binance", market: str = "spot"):
        self.store = store or CandleStore()
        self.exchange = exchange
        self.market = market

    def klines(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
               limit: int = 500, start_time=None, end_time=None):
        """OHLCV tail from the store, honouring cursors like the REST client."""
        df = self.store.read(self.exchange, self.market, symbol, timeframe)
        if not df.empty:
            if start_time is not None:
                df = df[df["ts"] >= int(start_time)]
            if end_time is not None:
                df = df[df["ts"] <= int(end_time)]
            df = df.tail(int(limit)).reset_index(drop=True)
        df.attrs["symbol"] = symbol
        df.attrs["timeframe"] = timeframe
        # P12.11 — stamp provenance so every downstream grader/writer knows
        # which price series it is reading without being told separately.
        df.attrs["exchange"] = self.exchange
        df.attrs["market"] = self.market
        return df
