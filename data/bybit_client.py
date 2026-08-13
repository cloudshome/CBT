"""data/bybit_client.py — P10.6: Bybit V5 klines transport behind the P10.2 contract.

The second exchange behind the same normalised schema
(``docs/DATA_INFRASTRUCTURE_ROADMAP.md`` §4/§9): one ``Candle`` record,
one meaning, regardless of venue. P10.7 also pages
``/v5/market/funding/history`` (``funding_history()``) so the
cross-exchange collector can derive a Binance-vs-Bybit funding
spread offline. This module implements the exact
transport contract the hardened P10.2 backfill pages through —
``klines_page()`` returning a :class:`~data.binance_client.PageResult`
with data, HTTP status, and headers — so ``data/backfill.py`` and the
Parquet store treat Bybit pages identically to Binance pages.

Venue specifics handled **here, at the adapter boundary**, so they never
leak into the analytics layer:

1. **V5 categories.** ``market="spot"`` → ``category=spot``;
   ``market="perp"`` → ``category=linear`` (USDT perpetuals). No Bybit
   perp for XAUUSD → honest empty ``PageResult`` (same rule as Binance).
2. **V5 intervals.** ``1m→"1"``, ``15m→"15"``, ``1h→"60"``, ``1d→"D"`` …
3. **V5 rows are newest-first.** The response ``list`` is sorted by
   descending start time; rows are reversed to ascending ``ts`` here so
   every consumer (backfill, store, analytics) sees venue-agnostic order.
4. **V5 rows are strings.** OHLCV + turnover parsed to floats here.
   Bybit klines carry no per-candle trade count; ``trades`` is left to
   the store's safe default (0).
5. **retCode → HTTP mapping.** ``retCode 0`` → 200; ``10006`` (too many
   visits) → 429 so the backfill's exponential backoff engages; any
   other non-zero retCode → 400 (generic, ends the run resumably).
   HTTP-level 403/451 (geo-blocks) pass through untouched so the
   backfill aborts immediately instead of hammering a wall.

Rate-limit pacing: Binance's ``x-mbx-remaining-weight`` header does not
exist on Bybit, so the header-aware pacer is a no-op for Bybit pages —
pacing falls back to the backfill's between-pages ``sleep_s`` (the CLI
default 0.2 s is fine for V5's 120 requests/5 s per-IP kline budget
once a backfill is underway). Fully offline in ``DEMO_MODE`` via the
existing demo fetcher — no network, ever, in tests.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

import pandas as pd
import requests

from data.binance_client import PageResult
from data.symbols import resolve_symbol

BYBIT_HOSTS = ["https://api.bybit.com", "https://api.bytick.com"]

# SKY timeframe → Bybit V5 interval code.
BYBIT_INTERVALS = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W",
}

# SKY market → Bybit V5 category.
BYBIT_CATEGORY = {"spot": "spot", "perp": "linear"}

RETCODE_RATE_LIMIT = 10006   # "too many visits" — maps to HTTP 429

TIMEOUT = 8
_RETRIES = 1


class BybitClient:
    """Read-only Bybit V5 public market-data transport (no keys, ever)."""

    def __init__(self, timeout: int = TIMEOUT, retries: int = _RETRIES):
        self.timeout = timeout
        self.retries = retries
        # Thread-local sessions so parallel timeframe fetches are safe.
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": "cryptobrain/1.0"})
            self._local.session = s
        return s

    # ── transport ────────────────────────────────────────────────────────
    def _get_host_with_headers(
        self, host: str, path: str, params: dict,
        timeout: Optional[int] = None, retries: Optional[int] = None,
    ) -> tuple[Optional[dict], Optional[dict], Optional[int]]:
        """One host: ``(json, headers, status)``, mirroring Binance's seam."""
        timeout = timeout or self.timeout
        retries = self.retries if retries is None else retries
        last: tuple[Optional[dict], Optional[dict], Optional[int]] = (
            None, None, None)
        for attempt in range(retries + 1):
            try:
                r = self.session.get(f"{host}{path}", params=params,
                                     timeout=timeout)
                if r.status_code == 200:
                    return r.json(), r.headers, 200
                if r.status_code in (451, 403, 429):
                    # geo-block / rate-limit — give up; the caller decides
                    # whether (and how long) to back off.
                    return None, r.headers, r.status_code
                last = (None, r.headers, r.status_code)   # 4xx/5xx — retry
            except requests.RequestException:
                last = (None, None, None)                 # network — retry
            time.sleep(0.3 * (attempt + 1))
        return last

    def _get_page_with_headers(
        self, hosts: list[str], path: str, params: dict,
        timeout: Optional[int] = None, retries: Optional[int] = None,
    ) -> tuple[Optional[dict], Optional[dict], Optional[int]]:
        """First host that returns data; else the last host's failure detail."""
        last: tuple[Optional[dict], Optional[dict], Optional[int]] = (
            None, None, None)
        for host in hosts:
            res = self._get_host_with_headers(host, path, params,
                                              timeout=timeout, retries=retries)
            last = res
            if res[0] is not None:
                return res
        return last

    # ── OHLCV (P10.2 transport contract) ─────────────────────────────────
    def klines_page(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
                    limit: int = 1000, start_time: Optional[int] = None,
                    end_time: Optional[int] = None,
                    market: str = "spot") -> PageResult:
        """One raw Bybit V5 klines page, normalised to the P10.2 contract.

        Returns a :class:`PageResult` whose ``data`` is a frame with
        ``ts/open/high/low/close/volume/quote_volume``, ascending by
        candle open time. ``None`` data + ``status`` carries the failure:
        429 = rate-limited (retryable), 403/451 = geo-block, ``None`` =
        network error, 400 = venue-level error (e.g. bad params or a
        non-zero retCode).
        """
        spec = resolve_symbol(symbol)
        if market == "perp":
            data_symbol = spec.futures_symbol
        elif market == "spot":
            data_symbol = spec.data_symbol
        else:
            raise ValueError(f"unknown market {market!r}: use 'spot' or 'perp'")
        if not data_symbol:
            # XAUUSD has no Bybit perp — honest empty, same rule as Binance.
            return PageResult(None, None, None)
        interval = BYBIT_INTERVALS.get(timeframe)
        if interval is None:
            raise ValueError(
                f"unsupported timeframe {timeframe!r}: Bybit supports "
                f"{sorted(BYBIT_INTERVALS)}")
        params = {
            "category": BYBIT_CATEGORY[market],
            "symbol": data_symbol,
            "interval": interval,
            "limit": min(max(1, int(limit)), 1000),
        }
        if start_time is not None:
            params["start"] = int(start_time)
        if end_time is not None:
            params["end"] = int(end_time)
        payload, headers, status = self._get_page_with_headers(
            BYBIT_HOSTS, "/v5/market/kline", params)
        if payload is None:
            return PageResult(None, headers, status)

        ret = int(payload.get("retCode", -1))
        if ret != 0:
            mapped = 429 if ret == RETCODE_RATE_LIMIT else 400
            return PageResult(None, headers, mapped)

        rows = (payload.get("result") or {}).get("list") or []
        df = pd.DataFrame(rows, columns=[
            "ts", "open", "high", "low", "close", "volume", "quote_volume"])
        if not df.empty:
            for col in ("open", "high", "low", "close", "volume",
                        "quote_volume"):
                df[col] = df[col].astype(float)
            df["ts"] = df["ts"].astype("int64")
            # V5 returns newest-first; normalise to ascending here so the
            # venue quirk never leaks past this boundary.
            df = df.sort_values("ts").reset_index(drop=True)
        df.attrs["symbol"] = spec.symbol
        df.attrs["data_symbol"] = data_symbol
        df.attrs["market"] = market
        df.attrs["provider"] = "bybit_v5"
        return PageResult(df, headers, 200)

    def klines(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
               limit: int = 500, start_time: Optional[int] = None,
               end_time: Optional[int] = None,
               market: str = "spot") -> pd.DataFrame:
        """BinanceClient-style convenience: the page's data, or raise.

        Lets BybitClient stand in anywhere a ``klines()``-shaped client is
        expected (e.g. the backfill's ``--repair`` fetch path).
        """
        page = self.klines_page(symbol, timeframe, limit=limit,
                                start_time=start_time, end_time=end_time,
                                market=market)
        if page.data is None:
            raise ConnectionError(
                f"Could not fetch Bybit klines for {symbol} {timeframe} "
                f"[{market}] — status {page.status}; check network or a "
                f"Bybit-accessible location.")
        return page.data

    # ── Funding history (P10.7 — cross-exchange funding spread) ──────────
    def funding_history(self, symbol: str = "BTCUSDT",
                        start_time: Optional[int] = None,
                        end_time: Optional[int] = None,
                        limit: int = 200) -> Optional[pd.DataFrame]:
        """Historical USDT-perp funding (``/v5/market/funding/history``).

        Returns ``ts`` (fundingRateTimestamp, UTC epoch ms) and
        ``funding_rate``, ascending. ``None`` when the transport failed;
        an empty frame when the venue has no perp (XAUUSD) or the page
        is empty. Public endpoint — no keys.
        """
        spec = resolve_symbol(symbol)
        if not spec.futures_symbol:
            return pd.DataFrame(columns=["ts", "funding_rate"])
        params = {
            "category": "linear",
            "symbol": spec.futures_symbol,
            "limit": min(max(1, int(limit)), 200),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        payload, _headers, _status = self._get_page_with_headers(
            BYBIT_HOSTS, "/v5/market/funding/history", params)
        if payload is None:
            return None
        ret = int(payload.get("retCode", -1))
        if ret != 0:
            return None
        rows = (payload.get("result") or {}).get("list") or []
        if not rows:
            return pd.DataFrame(columns=["ts", "funding_rate"])
        df = pd.DataFrame(rows)
        df = df.rename(columns={"fundingRateTimestamp": "ts",
                                "fundingRate": "funding_rate"})
        df["ts"] = df["ts"].astype("int64")
        df["funding_rate"] = df["funding_rate"].astype(float)
        return (df[["ts", "funding_rate"]]
                .sort_values("ts")
                .reset_index(drop=True))
