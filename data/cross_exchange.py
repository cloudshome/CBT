"""data/cross_exchange.py — P10.7: cross-exchange premium/discount + funding spread.

The roadmap is ``docs/DATA_INFRASTRUCTURE_ROADMAP.md`` (Layer 4); this is
milestone **P10.7**. It generalises the live health probe that used to live
only in ``brain/agent.py:_cross_exchange_probe()`` into:

1. **One snapshot function** — KuCoin + OKX + Bybit public prices vs a
   Binance reference. Health, preflight, and the collector all call this.
   Do not write a second probe.
2. **A stored per-timestamp series** — ``price``, ``premium_pct``,
   ``funding_rate``, ``funding_spread`` under ``data/store/cross/**``
   (same normalised row shape as P10.4, different root).
3. **Historical derivation** from the stores we already own — Binance vs
   Bybit candles (both page through the same ``Candle`` schema since
   P10.6) and Binance vs Bybit funding (P10.4 series + Bybit V5 history).

Design rules (do not bend):

1. ``ts`` is UTC epoch ms. Snapshots floor to the 15m (price) or 8h
   (funding) open so a re-run inside the same bucket upserts.
2. Premium is ``(venue / binance − 1) × 100`` (percent). Funding spread
   is ``venue − binance`` (same units as the rate).
3. Primary key ``(exchange, market, symbol, metric, ts)`` — upsert.
4. Public endpoints only. No keys, no signed requests, ever.
5. Offline-first: ``FakeVenueTransport`` is deterministic; ``DEMO_MODE=1``
   never touches the network.
6. **Store first.** Do not turn a premium or a funding spread into a
   trading rule until the data proves it.
"""
from __future__ import annotations

import os
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from data.derivatives import (
    DERIVATIVE_COLUMNS,
    DERIVATIVE_PK,
    DerivativesStore,
    coerce_derivative_frame,
    empty_frame,
)
from data.symbols import resolve_symbol

# --------------------------------------------------------------------------- #
# Metrics + store root
# --------------------------------------------------------------------------- #

PRICE = "price"
PREMIUM_PCT = "premium_pct"
FUNDING_RATE = "funding_rate"
FUNDING_SPREAD = "funding_spread"

ALL_CROSS_METRICS: tuple[str, ...] = (
    PRICE, PREMIUM_PCT, FUNDING_RATE, FUNDING_SPREAD,
)

THRESHOLD_PCT = 1.0                 # same 1% flag the health probe always used
SNAPSHOT_STEP_MS = 900_000          # 15m — the probe's candle
FUNDING_STEP_MS = 8 * 3_600_000     # BTCUSDT funding interval

DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent / "data" / "store" / "cross"
)

# Re-export so tests/CLI can pin the schema without importing derivatives.
CROSS_COLUMNS = DERIVATIVE_COLUMNS
CROSS_PK = DERIVATIVE_PK


def floor_ts(now_ms: int, step_ms: int) -> int:
    """Bucket open time (UTC epoch ms)."""
    return (int(now_ms) // int(step_ms)) * int(step_ms)


# --------------------------------------------------------------------------- #
# Venue registry — the single source of truth for the live probe
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Venue:
    """One public venue the probe knows how to read.

    Price endpoints return a newest-first candle list; ``latest_idx`` /
    ``close_idx`` pick the current close. ``envelope`` is where that list
    lives in the JSON (KuCoin/OKX: ``data``; Bybit V5: ``result.list``).
    Funding is optional — a venue without a public rate is skipped, not
    failed.
    """

    name: str
    url: str
    symbols: dict[str, str]
    latest_idx: int
    close_idx: int
    envelope: str = "data"
    funding_url: Optional[str] = None
    funding_symbols: Optional[dict[str, str]] = None
    funding_envelope: Optional[str] = None
    funding_field: Optional[str] = None


VENUES: dict[str, Venue] = {
    "kucoin": Venue(
        name="kucoin",
        url="https://api.kucoin.com/api/v1/market/candles?type=15min&symbol={sym}",
        symbols={"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT",
                 "XAUUSD": "PAXG-USDT"},
        # KuCoin: [time, open, close, high, low, volume, turnover], newest-first.
        latest_idx=0, close_idx=2, envelope="data",
        funding_url=("https://api-futures.kucoin.com/api/v1/"
                     "funding-rate/{sym}/current"),
        funding_symbols={"BTCUSDT": "XBTUSDTM", "ETHUSDT": "ETHUSDTM"},
        funding_envelope="data",
        funding_field="value",
    ),
    "okx": Venue(
        name="okx",
        url="https://www.okx.com/api/v5/market/candles?instId={sym}&bar=15m&limit=1",
        symbols={"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT",
                 "XAUUSD": "PAXG-USDT"},
        # OKX: [ts, o, h, l, c, vol, ...], newest-first.
        latest_idx=0, close_idx=4, envelope="data",
        funding_url="https://www.okx.com/api/v5/public/funding-rate?instId={sym}",
        funding_symbols={"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP"},
        funding_envelope="data",
        funding_field="fundingRate",
    ),
    "bybit": Venue(
        name="bybit",
        url=("https://api.bybit.com/v5/market/kline?category=spot"
             "&symbol={sym}&interval=15&limit=1"),
        # Bybit spot has no XAUUSD/PAXG we trust — skip gold (same rule as perp).
        symbols={"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"},
        # V5 kline: [start, open, high, low, close, volume, turnover], newest-first.
        latest_idx=0, close_idx=4, envelope="result.list",
        funding_url=("https://api.bybit.com/v5/market/tickers"
                     "?category=linear&symbol={sym}"),
        funding_symbols={"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT"},
        funding_envelope="result.list",
        funding_field="fundingRate",
    ),
}


def _pull_list(payload: dict, envelope: str) -> list:
    """Walk a dotted envelope (``data`` / ``result.list``) to a list."""
    cur: object = payload
    for part in envelope.split("."):
        if not isinstance(cur, dict):
            return []
        cur = cur.get(part)
    if cur is None:
        return []
    if isinstance(cur, list):
        return cur
    return [cur]


def _close_from_row(row, close_idx: int) -> float:
    if isinstance(row, dict):
        # ticker-shaped (Bybit lastPrice) — not used for the candle probe
        for key in ("close", "lastPrice", "last"):
            if key in row:
                return float(row[key])
        raise KeyError("no close in ticker row")
    return float(row[close_idx])


def _funding_from_row(row, field: str) -> float:
    if isinstance(row, dict):
        return float(row[field])
    raise TypeError("funding row is not an object")


# --------------------------------------------------------------------------- #
# The probe (this IS _cross_exchange_probe)
# --------------------------------------------------------------------------- #

def snapshot_prices(binance_last: dict, *,
                    get: Optional[Callable] = None,
                    timeout: int = 6,
                    venues: Optional[dict[str, Venue]] = None) -> dict:
    """Best-effort price cross-check: Binance vs KuCoin + OKX + Bybit.

    Flags deviations > 1%. Every exchange call is wrapped — an unreachable
    venue degrades to a note instead of failing the health report.

    This is the function ``brain.agent._cross_exchange_probe`` calls. The
    output shape is the contract preflight already reads::

        {ok, note, threshold_pct, exchanges: {name: {ok, symbols: {
            SYM: {price, deviation_pct, flag} | {error}
        }}}}
    """
    if get is None:
        import requests
        get = requests.get
    registry = venues if venues is not None else VENUES
    names = " + ".join(v.name.capitalize() if v.name != "okx" else "OKX"
                       for v in registry.values())
    # Keep the historical phrasing so existing docs still parse, then name
    # every venue actually compared.
    out = {
        "ok": True,
        "note": f"multi-exchange cross-check ({names} public)",
        "threshold_pct": THRESHOLD_PCT,
        "exchanges": {},
    }
    for name, cfg in registry.items():
        ex: dict = {"ok": False, "symbols": {}}
        for our, theirs in cfg.symbols.items():
            last = binance_last.get(our)
            if last is None:
                continue
            try:
                resp = get(cfg.url.format(sym=theirs), timeout=timeout)
                payload = resp.json() if hasattr(resp, "json") else resp
                candles = _pull_list(payload or {}, cfg.envelope)
                if not candles:
                    ex["symbols"][our] = {"error": "no candles in response"}
                    continue
                price = _close_from_row(candles[cfg.latest_idx], cfg.close_idx)
                last_f = float(last)
                if last_f == 0:
                    ex["symbols"][our] = {"error": "binance reference is zero"}
                    continue
                dev = round((price / last_f - 1.0) * 100.0, 3)
                ex["symbols"][our] = {
                    "price": round(price, 4),
                    "deviation_pct": dev,
                    "flag": abs(dev) > THRESHOLD_PCT,
                }
                ex["ok"] = True
            except Exception as exc:
                ex["symbols"][our] = {
                    "error": f"{type(exc).__name__}: {exc}",
                }
        if not ex["symbols"]:
            ex["note"] = "no symbols compared (no live Binance prices)"
        out["exchanges"][name] = ex
        if not ex["ok"]:
            out["ok"] = False
    return out


def snapshot_funding(binance_funding: dict, *,
                     get: Optional[Callable] = None,
                     timeout: int = 6,
                     venues: Optional[dict[str, Venue]] = None) -> dict:
    """Best-effort funding-rate cross-check vs a Binance reference.

    Separate from :func:`snapshot_prices` so a missing funding endpoint
    cannot change the price-probe contract preflight already depends on.
    """
    if get is None:
        import requests
        get = requests.get
    registry = venues if venues is not None else VENUES
    out = {"ok": True, "note": "funding cross-check (public)", "exchanges": {}}
    for name, cfg in registry.items():
        if not cfg.funding_url or not cfg.funding_symbols:
            continue
        ex: dict = {"ok": False, "symbols": {}}
        for our, theirs in cfg.funding_symbols.items():
            ref = binance_funding.get(our)
            if ref is None:
                continue
            try:
                resp = get(cfg.funding_url.format(sym=theirs), timeout=timeout)
                payload = resp.json() if hasattr(resp, "json") else resp
                rows = _pull_list(payload or {}, cfg.funding_envelope or "data")
                if not rows:
                    ex["symbols"][our] = {"error": "no funding in response"}
                    continue
                rate = _funding_from_row(rows[0], cfg.funding_field or "value")
                spread = float(rate) - float(ref)
                ex["symbols"][our] = {
                    "funding_rate": float(rate),
                    "spread": spread,
                }
                ex["ok"] = True
            except Exception as exc:
                ex["symbols"][our] = {
                    "error": f"{type(exc).__name__}: {exc}",
                }
        if ex["symbols"]:
            out["exchanges"][name] = ex
            if not ex["ok"]:
                out["ok"] = False
    if not out["exchanges"]:
        out["ok"] = False
        out["note"] = "no venues compared (no live Binance funding)"
    return out


# --------------------------------------------------------------------------- #
# Snapshot → store rows
# --------------------------------------------------------------------------- #

def snapshot_price_rows(snap: dict, *, ts: int, ingested_at: int,
                        market: str = "spot") -> pd.DataFrame:
    """Turn a :func:`snapshot_prices` result into canonical store rows."""
    rows: list[dict] = []
    for venue, ex in (snap.get("exchanges") or {}).items():
        for symbol, info in (ex.get("symbols") or {}).items():
            if "price" not in info:
                continue
            rows.append({
                "ts": ts, "exchange": venue, "market": market,
                "symbol": symbol, "metric": PRICE,
                "value": float(info["price"]), "ingested_at": ingested_at,
            })
            rows.append({
                "ts": ts, "exchange": venue, "market": market,
                "symbol": symbol, "metric": PREMIUM_PCT,
                "value": float(info["deviation_pct"]),
                "ingested_at": ingested_at,
            })
    return coerce_derivative_frame(rows) if rows else empty_frame()


def snapshot_funding_rows(snap: dict, *, ts: int, ingested_at: int,
                          market: str = "perp") -> pd.DataFrame:
    """Turn a :func:`snapshot_funding` result into canonical store rows."""
    rows: list[dict] = []
    for venue, ex in (snap.get("exchanges") or {}).items():
        for symbol, info in (ex.get("symbols") or {}).items():
            if "funding_rate" not in info:
                continue
            rows.append({
                "ts": ts, "exchange": venue, "market": market,
                "symbol": symbol, "metric": FUNDING_RATE,
                "value": float(info["funding_rate"]),
                "ingested_at": ingested_at,
            })
            rows.append({
                "ts": ts, "exchange": venue, "market": market,
                "symbol": symbol, "metric": FUNDING_SPREAD,
                "value": float(info["spread"]),
                "ingested_at": ingested_at,
            })
    return coerce_derivative_frame(rows) if rows else empty_frame()


# --------------------------------------------------------------------------- #
# Historical derivation (Binance vs Bybit from our own stores)
# --------------------------------------------------------------------------- #

def _price_col(frame: pd.DataFrame) -> str:
    for col in ("close", "value", "funding_rate", "price"):
        if col in frame.columns:
            return col
    raise ValueError("frame needs a close / value / funding_rate column")


def derive_premium(reference: pd.DataFrame, other: pd.DataFrame, *,
                   exchange: str = "bybit", market: str = "perp",
                   symbol: str = "BTCUSDT",
                   ingested_at: Optional[int] = None) -> pd.DataFrame:
    """premium_pct = (other / reference − 1) × 100 at common timestamps.

    Accepts candle frames (``close``) or canonical store frames (``value``).
    Zero / missing reference prices are dropped — a divide-by-zero must
    never become a stored premium.
    """
    if reference.empty or other.empty:
        return empty_frame()
    r = reference[["ts", _price_col(reference)]].copy()
    o = other[["ts", _price_col(other)]].copy()
    r = r.rename(columns={r.columns[1]: "ref"})
    o = o.rename(columns={o.columns[1]: "oth"})
    merged = pd.merge(r, o, on="ts", how="inner")
    merged = merged[merged["ref"].astype(float) != 0.0]
    if merged.empty:
        return empty_frame()
    ingest = ingested_at if ingested_at is not None else int(time.time() * 1000)
    return coerce_derivative_frame(pd.DataFrame({
        "ts": merged["ts"].astype("int64"),
        "exchange": exchange, "market": market, "symbol": symbol,
        "metric": PREMIUM_PCT,
        "value": (merged["oth"].astype(float) / merged["ref"].astype(float)
                  - 1.0) * 100.0,
        "ingested_at": ingest,
    }))


def derive_funding_spread(reference: pd.DataFrame, other: pd.DataFrame, *,
                          exchange: str = "bybit", market: str = "perp",
                          symbol: str = "BTCUSDT",
                          ingested_at: Optional[int] = None) -> pd.DataFrame:
    """funding_spread = other − reference at common timestamps."""
    if reference.empty or other.empty:
        return empty_frame()
    r = reference[["ts", _price_col(reference)]].copy()
    o = other[["ts", _price_col(other)]].copy()
    r = r.rename(columns={r.columns[1]: "ref"})
    o = o.rename(columns={o.columns[1]: "oth"})
    merged = pd.merge(r, o, on="ts", how="inner")
    if merged.empty:
        return empty_frame()
    ingest = ingested_at if ingested_at is not None else int(time.time() * 1000)
    return coerce_derivative_frame(pd.DataFrame({
        "ts": merged["ts"].astype("int64"),
        "exchange": exchange, "market": market, "symbol": symbol,
        "metric": FUNDING_SPREAD,
        "value": merged["oth"].astype(float) - merged["ref"].astype(float),
        "ingested_at": ingest,
    }))


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

class CrossExchangeStore(DerivativesStore):
    """Partitioned Parquet store for cross-exchange series.

    Same schema / upsert PK as :class:`DerivativesStore`, rooted at
    ``data/store/cross/**`` so Layer-2 Binance derivatives never mix
    with Layer-4 venue comparisons.
    """

    def __init__(self, root: str | Path | None = None):
        super().__init__(root=root if root is not None else DEFAULT_ROOT)

    def list_series(self) -> list[dict]:
        """Every stored ``{exchange, market, symbol, metric}``."""
        if not self.root.exists():
            return []
        found: dict[tuple[str, str, str, str], dict] = {}
        for d in sorted(self.root.glob(
                "exchange=*/market=*/symbol=*/metric=*")):
            meta: dict[str, str] = {}
            for seg in d.parts:
                key, _, value = seg.partition("=")
                if key in ("exchange", "market", "symbol", "metric"):
                    meta[key] = value
            if len(meta) == 4:
                key = (meta["exchange"], meta["market"],
                       meta["symbol"], meta["metric"])
                found[key] = meta
        return [found[k] for k in sorted(found)]


# --------------------------------------------------------------------------- #
# Offline fake transport (tests + DEMO_MODE)
# --------------------------------------------------------------------------- #

def _seed(key: str) -> int:
    return zlib.crc32(key.encode("utf-8"))


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeVenueTransport:
    """Deterministic stand-in for the public candle + funding endpoints.

    ``get(url)`` returns a Response-shaped object the probe can ``.json()``.
    ``funding_history()`` serves an 8h synthetic Bybit series so the
    collector's historical path is fully offline.
    """

    def __init__(self, *, prices: Optional[dict[str, dict[str, float]]] = None,
                 funding: Optional[dict[str, dict[str, float]]] = None,
                 start_ts: Optional[int] = None,
                 end_ts: Optional[int] = None,
                 seed: int = 7):
        # prices[venue][symbol] = last close
        self.prices = prices or {
            "kucoin": {"BTCUSDT": 60_060.0, "ETHUSDT": 3_003.0,
                       "XAUUSD": 2_301.0},
            "okx": {"BTCUSDT": 59_940.0, "ETHUSDT": 2_997.0,
                    "XAUUSD": 2_299.0},
            "bybit": {"BTCUSDT": 60_120.0, "ETHUSDT": 3_006.0},
        }
        self.funding = funding or {
            "kucoin": {"BTCUSDT": 0.00011, "ETHUSDT": 0.00009},
            "okx": {"BTCUSDT": 0.00008, "ETHUSDT": 0.00010},
            "bybit": {"BTCUSDT": 0.00013, "ETHUSDT": 0.00007},
        }
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.seed = seed
        self.requests = 0

    def _venue_from_url(self, url: str) -> str:
        lower = url.lower()
        if "kucoin" in lower:
            return "kucoin"
        if "okx" in lower:
            return "okx"
        if "bybit" in lower:
            return "bybit"
        return "unknown"

    def _symbol_from_url(self, url: str, venue: str) -> Optional[str]:
        cfg = VENUES.get(venue)
        if cfg is None:
            return None
        # Prefer the longer token so BTC-USDT-SWAP wins over BTC-USDT.
        pairs = list((cfg.funding_symbols or {}).items()) + list(cfg.symbols.items())
        pairs.sort(key=lambda kv: len(kv[1]), reverse=True)
        for our, theirs in pairs:
            if theirs in url:
                return our
        return None

    def get(self, url: str, timeout: int = 6):
        """Response-shaped payload for :func:`snapshot_prices` / funding."""
        self.requests += 1
        venue = self._venue_from_url(url)
        symbol = self._symbol_from_url(url, venue)
        cfg = VENUES.get(venue)
        is_funding = any(
            token in url for token in
            ("funding-rate", "fundingRate", "tickers", "funding")
        )
        if is_funding and cfg and cfg.funding_url and "kline" not in url:
            rate = (self.funding.get(venue) or {}).get(symbol or "", 0.0001)
            field = cfg.funding_field or "value"
            row = {field: rate}
            if cfg.funding_envelope == "result.list":
                payload = {"result": {"list": [row]}}
            else:
                # KuCoin wraps a single object; OKX wraps a list.
                payload = {"data": [row] if cfg.name == "okx" else row}
            return _FakeResponse(payload)

        price = (self.prices.get(venue) or {}).get(symbol or "", 60_000.0)
        if venue == "kucoin":
            # [time, open, close, high, low, volume, turnover]
            row = ["200", str(price), str(price), str(price), str(price),
                   "1", "1"]
            older = ["100", "1", "1", "1", "1", "1", "1"]
            return _FakeResponse({"data": [row, older]})
        if venue == "okx":
            # [ts, o, h, l, c, vol]
            row = ["200", str(price), str(price), str(price), str(price), "1"]
            older = ["100", "1", "1", "1", "1", "1"]
            return _FakeResponse({"data": [row, older]})
        if venue == "bybit":
            # [start, open, high, low, close, volume, turnover]
            row = ["200", str(price), str(price), str(price), str(price),
                   "1", "1"]
            older = ["100", "1", "1", "1", "1", "1", "1"]
            return _FakeResponse({"result": {"list": [row, older]}})
        return _FakeResponse({"data": []})

    def funding_history(self, symbol: str, start_time=None, end_time=None,
                        limit: int = 200) -> pd.DataFrame:
        """8h synthetic Bybit funding page (ascending ``ts``)."""
        self.requests += 1
        start = (int(start_time) if start_time is not None
                 else (self.start_ts if self.start_ts is not None
                       else 1_700_000_000_000))
        end = (int(end_time) if end_time is not None
               else (self.end_ts if self.end_ts is not None
                     else start + 30 * FUNDING_STEP_MS))
        step = FUNDING_STEP_MS
        first = ((start + step - 1) // step) * step
        n = max(0, (end - first) // step + (1 if first <= end else 0))
        # Exclusive-end convention when end == a grid point and we used
        # +1 above can overshoot by one; clip to the requested window.
        rng = np.random.default_rng(_seed(f"{symbol}:bybit-funding:{self.seed}"))
        ts = first + np.arange(n, dtype=np.int64) * step
        ts = ts[ts <= end]
        if start_time is not None:
            ts = ts[ts >= int(start_time)]
        base = (self.funding.get("bybit") or {}).get(symbol, 0.00013)
        rate = base + rng.normal(0, 0.00002, len(ts))
        df = pd.DataFrame({"ts": ts, "funding_rate": rate})
        return df.head(int(limit)).reset_index(drop=True)


def default_http_get():
    """DEMO_MODE → fake; else ``requests.get``."""
    if os.getenv("DEMO_MODE", "0") in ("1", "true", "yes"):
        return FakeVenueTransport().get
    import requests
    return requests.get


def default_funding_fetch():
    """DEMO_MODE → fake history; else live Bybit V5."""
    if os.getenv("DEMO_MODE", "0") in ("1", "true", "yes"):
        return FakeVenueTransport().funding_history
    from data.bybit_client import BybitClient
    return BybitClient().funding_history


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #

class CrossExchangeError(Exception):
    """A cross-exchange collect step failed honestly."""


@dataclass
class CrossRun:
    venue: str
    metric: str
    market: str
    rows_fetched: int = 0
    rows_new: int = 0
    first_ts: Optional[int] = None
    last_ts: Optional[int] = None
    source: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _span(frame: pd.DataFrame) -> tuple[Optional[int], Optional[int]]:
    if frame is None or frame.empty:
        return None, None
    return int(frame["ts"].iloc[0]), int(frame["ts"].iloc[-1])


class CrossExchangeCollector:
    """Persist probe snapshots + derive Binance-vs-Bybit historical series.

    Resumable (historical funding pages continue at the last stored ts),
    idempotent (upsert PK → a completed re-run of the same bucket / range
    adds zero rows), and fully offline under ``DEMO_MODE=1``.
    """

    def __init__(self, store: CrossExchangeStore, *,
                 candle_store=None, deriv_store=None,
                 get: Optional[Callable] = None,
                 funding_fetch: Optional[Callable] = None,
                 clock: Optional[Callable[[], int]] = None,
                 sleep_fn: Optional[Callable[[float], None]] = None,
                 sleep_s: float = 0.0):
        self.store = store
        self.candle_store = candle_store
        self.deriv_store = deriv_store
        self.get = get if get is not None else default_http_get()
        self.funding_fetch = (funding_fetch if funding_fetch is not None
                              else default_funding_fetch())
        self.clock = clock if clock is not None else (
            lambda: int(time.time() * 1000))
        self.sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
        self.sleep_s = sleep_s

    def collect(self, symbol: str, *,
                market: str = "perp",
                timeframe: str = "1m",
                since: Optional[int] = None,
                until: Optional[int] = None,
                snapshot: bool = True,
                dry_run: bool = False,
                binance_last: Optional[dict] = None,
                binance_funding: Optional[dict] = None) -> dict[str, CrossRun]:
        """Collect premium/discount + funding spread for ``symbol``.

        Steps (each independent; a missing input skips that step):

        1. Derive ``bybit.premium_pct`` from stored Binance + Bybit candles.
        2. Page Bybit funding history, then derive ``bybit.funding_spread``
           against stored Binance funding (P10.4).
        3. Persist one live/fake probe snapshot (price + funding).
        """
        spec = resolve_symbol(symbol)
        now = self.clock()
        until = int(until) if until is not None else now
        runs: dict[str, CrossRun] = {}

        if self.candle_store is not None:
            run = self._derive_premium_from_candles(
                spec.symbol, market, timeframe, since, until, dry_run, now)
            if run is not None:
                runs[f"{run.venue}.{run.market}.{run.metric}"] = run

        if spec.futures_symbol:
            fund_run, spread_run = self._collect_bybit_funding(
                spec.symbol, since, until, dry_run, now)
            if fund_run is not None:
                runs[f"{fund_run.venue}.{fund_run.market}.{fund_run.metric}"] = fund_run
            if spread_run is not None:
                runs[f"{spread_run.venue}.{spread_run.market}.{spread_run.metric}"] = spread_run

        if snapshot:
            runs.update(self._persist_snapshot(
                spec.symbol, dry_run=dry_run, now=now,
                binance_last=binance_last,
                binance_funding=binance_funding))
        return runs

    # -- historical premium -------------------------------------------------- #
    def _derive_premium_from_candles(self, symbol: str, market: str,
                                     timeframe: str, since, until,
                                     dry_run: bool, now: int) -> Optional[CrossRun]:
        ref = self.candle_store.read(
            "binance", market, symbol, timeframe,
            start_ts=since, end_ts=until)
        other = self.candle_store.read(
            "bybit", market, symbol, timeframe,
            start_ts=since, end_ts=until)
        prem = derive_premium(ref, other, exchange="bybit", market=market,
                              symbol=symbol, ingested_at=now)
        return self._commit("bybit", PREMIUM_PCT, market, prem, dry_run,
                            source="candle_store")

    # -- bybit funding history + spread -------------------------------------- #
    def _collect_bybit_funding(self, symbol: str, since, until,
                               dry_run: bool, now: int):
        existing = self.store.read("bybit", "perp", symbol, FUNDING_RATE)
        last_ts = int(existing["ts"].max()) if not existing.empty else None
        cursor = since if since is not None else (
            last_ts + FUNDING_STEP_MS if last_ts is not None else None)
        pages: list[pd.DataFrame] = []
        seen_last: Optional[int] = None
        while True:
            page = self.funding_fetch(symbol, cursor, until, 200)
            if page is None or getattr(page, "empty", True):
                break
            page = page.sort_values("ts").reset_index(drop=True)
            last = int(page["ts"].iloc[-1])
            if seen_last is not None and last <= seen_last:
                break
            pages.append(page)
            seen_last = last
            if len(page) < 200:
                break
            if until is not None and last >= until:
                break
            nxt = last + FUNDING_STEP_MS
            if cursor is not None and nxt <= cursor:
                break
            cursor = nxt
            if self.sleep_s:
                self.sleep_fn(self.sleep_s)

        if pages:
            raw = pd.concat(pages, ignore_index=True)
            raw = raw.drop_duplicates(subset=["ts"]).sort_values("ts")
            bybit_fund = coerce_derivative_frame(pd.DataFrame({
                "ts": raw["ts"].astype("int64"),
                "exchange": "bybit", "market": "perp", "symbol": symbol,
                "metric": FUNDING_RATE,
                "value": raw["funding_rate"].astype(float),
                "ingested_at": now,
            }))
        else:
            bybit_fund = empty_frame()

        fund_run = self._commit("bybit", FUNDING_RATE, "perp",
                                bybit_fund, dry_run, source="bybit_history")

        # Spread needs Binance funding from the P10.4 store.
        if self.deriv_store is None:
            return fund_run, None
        binance = self.deriv_store.read(
            "binance", "perp", symbol, "funding_rate",
            start_ts=since, end_ts=until)
        # Prefer what we just wrote (or already had) for the Bybit side.
        bybit = (bybit_fund if not bybit_fund.empty
                 else self.store.read("bybit", "perp", symbol, FUNDING_RATE,
                                      start_ts=since, end_ts=until))
        spread = derive_funding_spread(
            binance, bybit, exchange="bybit", market="perp",
            symbol=symbol, ingested_at=now)
        spread_run = self._commit("bybit", FUNDING_SPREAD, "perp",
                                  spread, dry_run, source="derived")
        return fund_run, spread_run

    # -- live / fake snapshot ------------------------------------------------ #
    def _persist_snapshot(self, symbol: str, *, dry_run: bool, now: int,
                          binance_last, binance_funding) -> dict[str, CrossRun]:
        runs: dict[str, CrossRun] = {}
        last = binance_last if binance_last is not None else (
            self._demo_binance_last(symbol))
        fund = binance_funding if binance_funding is not None else (
            self._demo_binance_funding(symbol))

        price_ts = floor_ts(now, SNAPSHOT_STEP_MS)
        snap = snapshot_prices(last, get=self.get)
        price_rows = snapshot_price_rows(snap, ts=price_ts, ingested_at=now)
        # Restrict to the requested symbol (the probe may return the watchlist).
        if not price_rows.empty:
            price_rows = price_rows[price_rows["symbol"] == symbol].reset_index(
                drop=True)
        for metric in (PRICE, PREMIUM_PCT):
            part = (price_rows[price_rows["metric"] == metric]
                    if not price_rows.empty else empty_frame())
            # one row per venue
            if part.empty:
                continue
            # commit per venue so status is readable
            for venue, chunk in part.groupby("exchange"):
                run = self._commit(str(venue), metric, "spot",
                                   coerce_derivative_frame(chunk),
                                   dry_run, source="snapshot")
                if run is not None:
                    runs[f"{run.venue}.{run.market}.{run.metric}"] = run

        fund_ts = floor_ts(now, FUNDING_STEP_MS)
        fund_snap = snapshot_funding(fund, get=self.get)
        fund_rows = snapshot_funding_rows(
            fund_snap, ts=fund_ts, ingested_at=now)
        if not fund_rows.empty:
            fund_rows = fund_rows[fund_rows["symbol"] == symbol].reset_index(
                drop=True)
        for metric in (FUNDING_RATE, FUNDING_SPREAD):
            part = (fund_rows[fund_rows["metric"] == metric]
                    if not fund_rows.empty else empty_frame())
            if part.empty:
                continue
            for venue, chunk in part.groupby("exchange"):
                key = f"{venue}.perp.{metric}"
                # Historical bybit funding_rate / funding_spread already
                # landed above; don't let the snapshot overwrite the key
                # — still persist the snapshot row (same PK bucket).
                run = self._commit(str(venue), metric, "perp",
                                   coerce_derivative_frame(chunk),
                                   dry_run, source="snapshot")
                if run is not None and key not in runs:
                    runs[key] = run
                elif run is not None and key in runs:
                    # merge counts so the snapshot upsert is visible
                    runs[key].rows_fetched += run.rows_fetched
                    runs[key].rows_new += run.rows_new
        return runs

    def _demo_binance_last(self, symbol: str) -> dict:
        try:
            from data.sample_client import SampleClient
            df = SampleClient().klines(symbol, "15m", 60)
            if df is None or df.empty:
                return {}
            return {symbol: float(df["close"].iloc[-1])}
        except Exception:
            return {symbol: 60_000.0}

    def _demo_binance_funding(self, symbol: str) -> dict:
        spec = resolve_symbol(symbol)
        if not spec.futures_symbol:
            return {}
        if self.deriv_store is not None:
            df = self.deriv_store.read(
                "binance", "perp", spec.symbol, "funding_rate")
            if not df.empty:
                return {spec.symbol: float(df["value"].iloc[-1])}
        try:
            from data.sample_client import SampleClient
            df = SampleClient().funding_rate_history(
                spec.symbol, None, None, 8)
            if df is None or df.empty:
                return {spec.symbol: 0.0001}
            return {spec.symbol: float(df["funding_rate"].iloc[-1])}
        except Exception:
            return {spec.symbol: 0.0001}

    def _commit(self, venue: str, metric: str, market: str,
                frame: pd.DataFrame, dry_run: bool,
                source: str) -> Optional[CrossRun]:
        if frame is None or frame.empty:
            return None
        first, last = _span(frame)
        before = self.store.count(venue, market, frame["symbol"].iloc[0], metric)
        if dry_run:
            existing = self.store.read(
                venue, market, frame["symbol"].iloc[0], metric)
            have = set(int(t) for t in existing["ts"]) if not existing.empty else set()
            new = len({int(t) for t in frame["ts"]} - have)
            return CrossRun(venue=venue, metric=metric, market=market,
                            rows_fetched=len(frame), rows_new=new,
                            first_ts=first, last_ts=last, source=source)
        self.store.write(frame)
        after = self.store.count(venue, market, frame["symbol"].iloc[0], metric)
        return CrossRun(venue=venue, metric=metric, market=market,
                        rows_fetched=len(frame),
                        rows_new=max(0, after - before),
                        first_ts=first, last_ts=last, source=source)
