"""data/binance_client.py

Binance market-data client.

* OHLCV klines are fetched from the geo-friendly public market-data mirror
  (data-api.binance.vision) first, with api.binance.com as fallback.
* Futures endpoints (funding rate, open interest, long/short ratio,
  liquidations) live on fapi.binance.com, which geo-blocks some regions
  (including this sandbox). The client tries them and *degrades gracefully*:
  if unreachable, the engine simply runs without futures features and the
  output notes they were unavailable. On your machine (Dhaka, BD) they will
  normally work.

All methods are read-only public endpoints — no API keys required.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

from config import BINANCE_HOSTS, BINANCE_FUTURES_HOSTS
from data.symbols import resolve_symbol


@dataclass(frozen=True)
class PageResult:
    """One raw klines page + transport metadata (P10.2 backfill contract).

    ``data`` is the Binance-shaped frame (12 standard klines columns) or
    ``None`` when the request failed; ``headers`` carries rate-limit
    metadata (``x-mbx-remaining-weight``) when the host provided it;
    ``status`` is the HTTP status (``None`` = network error).
    """

    data: Optional[pd.DataFrame]
    headers: Optional[dict]
    status: Optional[int]

TIMEFRAME_TO_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
    "6h": 21_600_000, "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000,
}

TIMEOUT = 8
_RETRIES = 1
FUT_TIMEOUT = 5
FUT_RETRIES = 0
_CONTEXT_TTL = 60  # seconds to cache market_context


class BinanceClient:
    def __init__(self, timeout: int = TIMEOUT, retries: int = _RETRIES):
        self.timeout = timeout
        self.retries = retries
        # Thread-local sessions so parallel timeframe fetches are safe.
        self._local = threading.local()
        self._futures_ok: Optional[bool] = None  # None = not yet tested
        self._futures_checked_at: float = 0.0
        self._context_cache: dict[str, tuple[float, dict]] = {}

    @property
    def session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": "cryptobrain/1.0"})
            self._local.session = s
        return s

    def _get_with_headers(self, host: str, path: str, params: dict,
                          timeout: Optional[int] = None,
                          retries: Optional[int] = None,
                          ) -> tuple[Optional[dict], Optional[dict], Optional[int]]:
        """GET returning ``(json, headers, status)``.

        Behaviour mirrors ``_get`` exactly (same retry/backoff, same
        non-retryable statuses) but also surfaces the response headers
        (rate-limit budget) and the HTTP status so the P10.2 backfiller
        can back off on 429 and abort fast on geo-blocks.
        """
        timeout = timeout or self.timeout
        retries = self.retries if retries is None else retries
        last: tuple[Optional[dict], Optional[dict], Optional[int]] = (None, None, None)
        for attempt in range(retries + 1):
            try:
                r = self.session.get(f"{host}{path}", params=params, timeout=timeout)
                if r.status_code == 200:
                    return r.json(), r.headers, 200
                if r.status_code in (451, 403, 429):
                    # geo-block / rate-limit — the transport gives up; the
                    # caller decides whether (and how long) to back off.
                    return None, r.headers, r.status_code
                last = (None, r.headers, r.status_code)  # 4xx/5xx — retry below
            except requests.RequestException:
                last = (None, None, None)  # network error — retry below
            time.sleep(0.3 * (attempt + 1))
        return last

    def _get(self, host: str, path: str, params: dict,
             timeout: Optional[int] = None, retries: Optional[int] = None) -> Optional[dict]:
        return self._get_with_headers(host, path, params, timeout=timeout,
                                      retries=retries)[0]

    def _get_first_host_with_headers(self, hosts: list[str], path: str, params: dict,
                                     timeout: Optional[int] = None,
                                     retries: Optional[int] = None,
                                     ) -> tuple[Optional[dict], Optional[dict], Optional[int]]:
        """First host that returns data; else the last host's failure detail."""
        last = (None, None, None)
        for host in hosts:
            res = self._get_with_headers(host, path, params, timeout=timeout,
                                         retries=retries)
            last = res
            if res[0] is not None:
                return res
        return last

    def _get_first_host(self, hosts: list[str], path: str, params: dict,
                        timeout: Optional[int] = None,
                        retries: Optional[int] = None) -> Optional[dict]:
        return self._get_first_host_with_headers(hosts, path, params,
                                                 timeout=timeout, retries=retries)[0]

    # ── OHLCV ────────────────────────────────────────────────────────────
    def klines_page(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
                    limit: int = 1000, start_time: Optional[int] = None,
                    end_time: Optional[int] = None,
                    market: str = "spot") -> PageResult:
        """Fetch one raw klines page for ``market`` ∈ {'spot', 'perp'}.

        Returns a :class:`PageResult` with the full Binance-shaped 12-column
        frame (ts, open, high, low, close, volume, close_ts, quote_volume,
        trades, taker_buy_base, taker_buy_quote, ignore) plus rate-limit
        headers and the HTTP status.  ``None`` data means the page failed —
        check ``status``: 429/418 = rate-limit (retryable with backoff),
        403/451 = geo-block (not retryable), ``None`` = network error.

        This is the transport contract the P10.2 backfill (``data/backfill.py``)
        pages through: ``start_time`` = candle open, UTC epoch ms, inclusive.
        """
        spec = resolve_symbol(symbol)
        if market == "perp":
            data_symbol = spec.futures_symbol
            hosts, path = BINANCE_FUTURES_HOSTS, "/fapi/v1/klines"
        else:
            data_symbol = spec.data_symbol
            hosts, path = BINANCE_HOSTS, "/api/v3/klines"
        if not data_symbol:
            return PageResult(None, None, None)
        params = {"symbol": data_symbol, "interval": timeframe,
                  "limit": min(max(1, int(limit)), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        data, headers, status = self._get_first_host_with_headers(hosts, path, params)
        if data is None:
            return PageResult(None, headers, status)
        df = pd.DataFrame(data, columns=[
            "ts", "open", "high", "low", "close", "volume",
            "close_ts", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])
        for col in ("open", "high", "low", "close", "volume",
                    "quote_volume", "taker_buy_base", "taker_buy_quote"):
            df[col] = df[col].astype(float)
        df["ts"] = df["ts"].astype("int64")
        df.attrs["symbol"] = spec.symbol
        df.attrs["data_symbol"] = data_symbol
        df.attrs["market"] = market
        df.attrs["provider"] = spec.provider
        return PageResult(df, headers, status)

    def klines(self, symbol: str = "BTCUSDT", timeframe: str = "15m",
               limit: int = 500, start_time: Optional[int] = None,
               end_time: Optional[int] = None) -> pd.DataFrame:
        """Fetch OHLCV candles.

        ``start_time`` / ``end_time`` are optional Unix timestamps in
        milliseconds.  They let the paper-trading runner resume from its last
        inspected candle instead of repeatedly treating all historical data as
        new.  The returned frame retains the standard columns ``ts, open,
        high, low, close, volume``.
        """
        res = self.klines_page(symbol, timeframe, limit=limit,
                               start_time=start_time, end_time=end_time,
                               market="spot")
        if res.data is None:
            spec = resolve_symbol(symbol)
            raise ConnectionError(
                f"Could not fetch klines for {spec.symbol} ({spec.data_symbol}) {timeframe} — "
                f"check network or try a Binance-accessible location."
            )
        out = res.data[["ts", "open", "high", "low", "close", "volume"]].copy()
        out.attrs = dict(res.data.attrs)
        return out

    # ── Futures (optional; may geo-block) ────────────────────────────────
    def _futures_pair(self, symbol: str) -> Optional[str]:
        """Return the Binance USD-M futures pair for a user-facing symbol.

        XAUUSD/GOLD uses PAXGUSDT spot candles as a proxy and has no
        futures/funding context in this project, so futures methods return
        None immediately.
        """
        return resolve_symbol(symbol).futures_symbol

    @property
    def futures_available(self) -> bool:
        now = time.time()
        # Cache the availability probe for 60s and NEVER block more than ~5s.
        if self._futures_ok is None or now - self._futures_checked_at > 60:
            self._futures_ok = self._get_first_host(
                BINANCE_FUTURES_HOSTS, "/fapi/v1/ping", {},
                timeout=FUT_TIMEOUT, retries=FUT_RETRIES) is not None
            self._futures_checked_at = now
        return self._futures_ok

    def funding_rate(self, symbol: str = "BTCUSDT") -> Optional[dict]:
        """Current (last) funding rate for the USDT-margined future."""
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol or not self.futures_available:
            return None
        data = self._get_first_host(BINANCE_FUTURES_HOSTS, "/fapi/v1/premiumIndex",
                                    {"symbol": fut_symbol}, timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        if not data:
            return None
        return {
            "funding_rate_pct": round(float(data.get("lastFundingRate", 0)) * 100, 4),
            "mark_price": float(data.get("markPrice", 0)),
            "time": data.get("time"),
        }

    def open_interest(self, symbol: str = "BTCUSDT") -> Optional[dict]:
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol or not self.futures_available:
            return None
        data = self._get_first_host(BINANCE_FUTURES_HOSTS, "/fapi/v1/openInterest",
                                    {"symbol": fut_symbol}, timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        if not data:
            return None
        return {"open_interest": float(data.get("openInterest", 0))}

    def long_short_ratio(self, symbol: str = "BTCUSDT", period: str = "5m",
                         limit: int = 1) -> Optional[dict]:
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol or not self.futures_available:
            return None
        data = self._get_first_host(
            BINANCE_FUTURES_HOSTS, "/futures/data/globalLongShortAccountRatio",
            {"symbol": fut_symbol, "period": period, "limit": limit},
            timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        if not data:
            return None
        latest = data[-1] if isinstance(data, list) and data else data
        return {"long_short_ratio": float(latest.get("longShortRatio", 0))}

    def liquidation_stats_proxy(self, symbol: str = "BTCUSDT") -> Optional[dict]:
        """24h-stats proxy for liquidation context — **not** liquidation data.

        Honest name per the P10 roadmap: Binance's ``allForceOrders`` REST
        endpoint is unusable for history, and real forced-order data only
        comes from the ``!forceOrder@arr`` WebSocket stream (accumulates
        from the day collection starts; it cannot be backfilled). This
        method therefore returns the public 24h ticker stats as a proxy
        and must never be presented as actual liquidation data.
        """
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol or not self.futures_available:
            return None
        data = self._get_first_host(BINANCE_FUTURES_HOSTS, "/fapi/v1/ticker/24hr",
                                    {"symbol": fut_symbol}, timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        if not data:
            return None
        return {
            "24h_high": float(data.get("highPrice", 0)),
            "24h_low": float(data.get("lowPrice", 0)),
            "24h_volume_base": float(data.get("volume", 0)),
            "24h_price_change_pct": float(data.get("priceChangePercent", 0)),
        }

    # ── Derivatives history (P10.4 — persist as time series) ──────────────
    def _futures_list(self, path: str, params: dict) -> Optional[list]:
        """Fetch a futures endpoint returning a JSON list (or None)."""
        data = self._get_first_host(BINANCE_FUTURES_HOSTS, path, params,
                                    timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        return data if isinstance(data, list) else None

    def funding_rate_history(self, symbol: str = "BTCUSDT",
                             start_time: Optional[int] = None,
                             end_time: Optional[int] = None,
                             limit: int = 1000) -> Optional[pd.DataFrame]:
        """Historical funding rates (``/fapi/v1/fundingRate``), newest-last.

        Returns ``ts`` (fundingTime, UTC epoch ms), ``funding_rate`` and
        ``mark_price`` at funding time, or ``None`` when unreachable.
        """
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol:
            return None
        params = {"symbol": fut_symbol, "limit": min(max(1, int(limit)), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        data = self._futures_list("/fapi/v1/fundingRate", params)
        if data is None:
            return None
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df = df.rename(columns={"fundingTime": "ts",
                                "fundingRate": "funding_rate"})
        df["ts"] = df["ts"].astype("int64")
        df["funding_rate"] = df["funding_rate"].astype(float)
        df["mark_price"] = df["mark_price"].astype(float)
        return df[["ts", "funding_rate", "mark_price"]].sort_values("ts").reset_index(drop=True)

    def open_interest_history(self, symbol: str = "BTCUSDT", period: str = "1h",
                              start_time: Optional[int] = None,
                              end_time: Optional[int] = None,
                              limit: int = 500) -> Optional[pd.DataFrame]:
        """Historical open interest (``/futures/data/openInterestHist``).

        Returns ``ts`` (UTC epoch ms), ``open_interest`` (in base asset)
        and ``open_interest_value`` (in USDT), or ``None`` when unreachable.
        """
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol:
            return None
        params = {"symbol": fut_symbol, "period": period,
                  "limit": min(max(1, int(limit)), 500)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        data = self._futures_list("/futures/data/openInterestHist", params)
        if data is None:
            return None
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df = df.rename(columns={"timestamp": "ts",
                                "sumOpenInterest": "open_interest",
                                "sumOpenInterestValue": "open_interest_value"})
        df["ts"] = df["ts"].astype("int64")
        df["open_interest"] = df["open_interest"].astype(float)
        df["open_interest_value"] = df["open_interest_value"].astype(float)
        return df[["ts", "open_interest", "open_interest_value"]].sort_values("ts").reset_index(drop=True)

    def mark_price_klines(self, symbol: str = "BTCUSDT", timeframe: str = "1h",
                          start_time: Optional[int] = None,
                          end_time: Optional[int] = None,
                          limit: int = 1000) -> Optional[pd.DataFrame]:
        """Historical mark prices (``/fapi/v1/markPriceKlines``).

        Returns ``ts`` (candle OPEN, UTC epoch ms) and ``mark_price``
        (close of the mark-price candle), or ``None`` when unreachable.
        """
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol:
            return None
        params = {"symbol": fut_symbol, "interval": timeframe,
                  "limit": min(max(1, int(limit)), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        data = self._futures_list("/fapi/v1/markPriceKlines", params)
        if data is None:
            return None
        if not data:
            return pd.DataFrame(columns=["ts", "mark_price"])
        df = pd.DataFrame(data, columns=["ts", "open", "high", "low",
                                         "mark_price", "volume", "close_ts",
                                         "quote_volume", "trades", "taker_buy_base",
                                         "taker_buy_quote", "ignore"])
        df["ts"] = df["ts"].astype("int64")
        df["mark_price"] = df["mark_price"].astype(float)
        return df[["ts", "mark_price"]].sort_values("ts").reset_index(drop=True)

    def index_price_klines(self, symbol: str = "BTCUSDT", timeframe: str = "1h",
                           start_time: Optional[int] = None,
                           end_time: Optional[int] = None,
                           limit: int = 1000) -> Optional[pd.DataFrame]:
        """Historical index prices (``/fapi/v1/indexPriceKlines``).

        Returns ``ts`` (candle OPEN, UTC epoch ms) and ``index_price``
        (close of the index-price candle), or ``None`` when unreachable.
        """
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol:
            return None
        params = {"symbol": fut_symbol, "interval": timeframe,
                  "limit": min(max(1, int(limit)), 1000)}
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        data = self._futures_list("/fapi/v1/indexPriceKlines", params)
        if data is None:
            return None
        if not data:
            return pd.DataFrame(columns=["ts", "index_price"])
        df = pd.DataFrame(data, columns=["ts", "open", "high", "low",
                                         "index_price", "volume", "close_ts",
                                         "quote_volume", "trades", "taker_buy_base",
                                         "taker_buy_quote", "ignore"])
        df["ts"] = df["ts"].astype("int64")
        df["index_price"] = df["index_price"].astype(float)
        return df[["ts", "index_price"]].sort_values("ts").reset_index(drop=True)

    def premium_index(self, symbol: str = "BTCUSDT") -> Optional[dict]:
        """Current mark/index snapshot (``/fapi/v1/premiumIndex``)."""
        fut_symbol = self._futures_pair(symbol)
        if not fut_symbol or not self.futures_available:
            return None
        data = self._get_first_host(BINANCE_FUTURES_HOSTS, "/fapi/v1/premiumIndex",
                                    {"symbol": fut_symbol}, timeout=FUT_TIMEOUT, retries=FUT_RETRIES)
        if not data:
            return None
        mark = float(data.get("markPrice", 0))
        index = float(data.get("indexPrice", 0))
        return {
            "ts": int(data.get("time") or 0),
            "mark_price": mark,
            "index_price": index,
            "basis": round(mark - index, 6),
            "last_funding_rate": float(data.get("lastFundingRate", 0)),
            "next_funding_time": data.get("nextFundingTime"),
        }

    # ── Combined convenience ─────────────────────────────────────────────
    def market_context(self, symbol: str = "BTCUSDT") -> dict:
        """Futures/provider context, cached per symbol.

        Crypto pairs such as BTCUSDT and ETHUSDT include optional Binance
        futures fields when the network permits. XAUUSD/GOLD is routed to
        PAXGUSDT spot candles and explicitly reports that futures context is
        not available rather than looking geo-blocked.
        """
        spec = resolve_symbol(symbol)
        now = time.time()
        hit = self._context_cache.get(spec.symbol)
        if hit and now - hit[0] < _CONTEXT_TTL:
            return hit[1]

        ctx = {
            "symbol": spec.symbol,
            "data_symbol": spec.data_symbol,
            "market": spec.market,
            "provider": spec.provider,
            "futures": False,
            "note": spec.note or "futures unreachable from this network",
        }
        if spec.futures_symbol and self.futures_available:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as ex:
                fr = ex.submit(self.funding_rate, spec.symbol)
                oi = ex.submit(self.open_interest, spec.symbol)
                ls = ex.submit(self.long_short_ratio, spec.symbol)
                liq = ex.submit(self.liquidation_stats_proxy, spec.symbol)
                # .exception() instead of .result(): a failing future must never
                # re-raise and kill the whole scan.
                def _safe(fut):
                    try:
                        if fut.exception():
                            return None
                        return fut.result()
                    except Exception:
                        return None
                fr, oi, ls, liq = (_safe(f) for f in (fr, oi, ls, liq))
            ctx.update({
                "futures": True,
                "note": "futures context available",
                "futures_symbol": spec.futures_symbol,
                "funding_rate_pct": fr["funding_rate_pct"] if fr else None,
                "open_interest": oi["open_interest"] if oi else None,
                "long_short_ratio": ls["long_short_ratio"] if ls else None,
                "liq_24h_high": liq["24h_high"] if liq else None,
                "liq_24h_low": liq["24h_low"] if liq else None,
                "liq_24h_change_pct": liq["24h_price_change_pct"] if liq else None,
            })
        elif spec.futures_symbol:
            ctx["note"] = "futures unreachable from this network"
        self._context_cache[spec.symbol] = (now, ctx)
        return ctx
