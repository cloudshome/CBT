"""
Institutional Market Data Provider Abstraction Layer.
Decouples exchange-specific API logic from charting and intelligence engines.
Supports Binance REST, Bybit V5 Linear, Persistent SQLite Cache, and Synthetic Fallback.
"""

from __future__ import annotations

import abc
import logging
import time
from typing import Any

import aiohttp

from core.causal_firewall import causal_firewall
from core.database import db_manager
from core.evidence_integrity import EvidenceGrade, stamp_records

logger = logging.getLogger("ai_quant_sentinel.market_providers")

# Standardized Timeframe Definitions (Milliseconds)
TIMEFRAME_TO_MS: dict[str, int] = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "10m": 10 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "45m": 45 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "3h": 3 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
    "1M": 30 * 24 * 60 * 60 * 1000,
}

BINANCE_INTERVAL_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M",
}

BYBIT_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}


class BaseMarketDataProvider(abc.ABC):
    """
    Abstract interface for market data providers.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        pass

    @abc.abstractmethod
    async def fetch_historical_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        """Fetches normalized historical OHLCV bars."""
        pass

    @abc.abstractmethod
    async def fetch_live_ticker(self, symbol: str) -> dict[str, Any] | None:
        """Fetches current live price and 24h metrics."""
        pass

    @abc.abstractmethod
    async def fetch_order_book_depth(self, symbol: str, limit: int = 10) -> dict[str, Any] | None:
        """Fetches level 2 order book snapshot."""
        pass


class HttpSessionManager:
    """Manages persistent pooled aiohttp ClientSession with TCP keep-alive."""

    _session: aiohttp.ClientSession | None = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=30.0)
            cls._session = aiohttp.ClientSession(connector=connector)
        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        if cls._session is not None and not cls._session.closed:
            await cls._session.close()
            cls._session = None


class BinanceMarketDataProvider(BaseMarketDataProvider):
    """
    Binance Spot & USD-M Futures Public REST Client.
    """

    @property
    def provider_name(self) -> str:
        return "BINANCE_REST"

    def _normalize_symbol(self, symbol: str) -> str:
        clean = symbol.replace("/", "").upper()
        if "XAU" in clean:
            return "PAXGUSDT"
        return clean

    async def fetch_historical_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        binance_interval = BINANCE_INTERVAL_MAP.get(timeframe)
        if not binance_interval:
            return None

        sym = self._normalize_symbol(symbol)
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={binance_interval}&limit={limit}"
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    return [
                        {
                            "timestamp": int(k[0]),
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        }
                        for k in raw
                    ]
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Binance OHLCV failed for {symbol} ({timeframe}): {e}")
        return None

    async def fetch_live_ticker(self, symbol: str) -> dict[str, Any] | None:
        sym = self._normalize_symbol(symbol)
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}"
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    return {
                        "symbol": symbol,
                        "price": float(d["lastPrice"]),
                        "change_24h_pct": float(d["priceChangePercent"]),
                        "high_24h": float(d["highPrice"]),
                        "low_24h": float(d["lowPrice"]),
                        "volume_24h": float(d["volume"]),
                        "timestamp": int(d["closeTime"]),
                        "source": self.provider_name,
                        "evidence_grade": EvidenceGrade.EMPIRICAL.label,
                        "is_synthetic": 0,
                        "data_unavailable": False,
                    }
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Binance Ticker failed for {symbol}: {e}")
        return None

    async def fetch_order_book_depth(self, symbol: str, limit: int = 10) -> dict[str, Any] | None:
        sym = self._normalize_symbol(symbol)
        url = f"https://api.binance.com/api/v3/depth?symbol={sym}&limit={limit}"
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    asks = [{"price": float(a[0]), "size": float(a[1])} for a in d.get("asks", [])]
                    bids = [{"price": float(b[0]), "size": float(b[1])} for b in d.get("bids", [])]
                    return {
                        "symbol": symbol,
                        "asks": asks,
                        "bids": bids,
                        "timestamp": int(time.time() * 1000),
                    }
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Binance Depth failed for {symbol}: {e}")
        return None


class BybitMarketDataProvider(BaseMarketDataProvider):
    """
    Bybit V5 Linear Public REST Client.
    """

    @property
    def provider_name(self) -> str:
        return "BYBIT_V5"

    def _normalize_symbol(self, symbol: str) -> str:
        clean = symbol.replace("/", "").upper()
        if "XAU" in clean:
            return "XAUUSDT"
        return clean

    async def fetch_historical_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        bybit_interval = BYBIT_INTERVAL_MAP.get(timeframe, "15")
        sym = self._normalize_symbol(symbol)
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval={bybit_interval}&limit={limit}"
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    raw_list = raw.get("result", {}).get("list", [])
                    candles = [
                        {
                            "timestamp": int(k[0]),
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        }
                        for k in reversed(raw_list)
                    ]
                    return candles if candles else None
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Bybit OHLCV failed for {symbol} ({timeframe}): {e}")
        return None

    async def fetch_live_ticker(self, symbol: str) -> dict[str, Any] | None:
        sym = self._normalize_symbol(symbol)
        url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={sym}"
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    item = raw.get("result", {}).get("list", [{}])[0]
                    if item:
                        return {
                            "symbol": symbol,
                            "price": float(item["lastPrice"]),
                            "change_24h_pct": float(item.get("price24hPcnt", "0")) * 100,
                            "high_24h": float(item.get("highPrice24h", "0")),
                            "low_24h": float(item.get("lowPrice24h", "0")),
                            "volume_24h": float(item.get("volume24h", "0")),
                            "timestamp": int(time.time() * 1000),
                            "source": self.provider_name,
                            "evidence_grade": EvidenceGrade.EMPIRICAL.label,
                            "is_synthetic": 0,
                            "data_unavailable": False,
                        }
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Bybit Ticker failed for {symbol}: {e}")
        return None

    async def fetch_order_book_depth(self, symbol: str, limit: int = 10) -> dict[str, Any] | None:
        sym = self._normalize_symbol(symbol)
        url = (
            f"https://api.bybit.com/v5/market/orderbook?category=linear&symbol={sym}&limit={limit}"
        )
        try:
            session = await HttpSessionManager.get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                if resp.status == 200:
                    d = await resp.json()
                    res = d.get("result", {})
                    asks = [{"price": float(a[0]), "size": float(a[1])} for a in res.get("a", [])]
                    bids = [{"price": float(b[0]), "size": float(b[1])} for b in res.get("b", [])]
                    return {
                        "symbol": symbol,
                        "asks": asks,
                        "bids": bids,
                        "timestamp": int(time.time() * 1000),
                    }
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.debug(f"Bybit Depth failed for {symbol}: {e}")
        return None


class SQLiteCacheProvider(BaseMarketDataProvider):
    """
    Local SQLite Cache Provider for offline resilience and point-in-time isolation.
    """

    @property
    def provider_name(self) -> str:
        return "SQLITE_LOCAL_CACHE"

    async def fetch_historical_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        max_time = causal_firewall.get_current_time_ms()
        with db_manager.get_market_conn() as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, symbol, timeframe, open, high, low, close, volume,
                       is_synthetic
                FROM candles
                WHERE symbol = ? AND timeframe = ? AND timestamp <= ?
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (symbol, timeframe, max_time, limit),
            )
            rows = cursor.fetchall()
            if len(rows) >= min(20, limit):
                # Replay the provenance that was stored with each row. Dropping
                # ``is_synthetic`` here would silently launder cached synthetic
                # bars back into the pipeline as untagged (and therefore
                # promotable) records.
                return [
                    {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "is_synthetic": int(row["is_synthetic"] or 0),
                    }
                    for row in reversed(rows)
                ]
        return None

    async def fetch_live_ticker(self, symbol: str) -> dict[str, Any] | None:
        max_staleness_ms = 15 * 60 * 1000  # 15-minute staleness guard
        now_ms = causal_firewall.get_current_time_ms()
        with db_manager.get_market_conn() as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, close FROM candles
                WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1;
                """,
                (symbol,),
            )
            row = cursor.fetchone()
            if row:
                candle_time = int(row["timestamp"])
                if (now_ms - candle_time) <= max_staleness_ms:
                    return {
                        "symbol": symbol,
                        "price": float(row["close"]),
                        "change_24h_pct": 1.25,
                        "high_24h": float(row["close"]) * 1.015,
                        "low_24h": float(row["close"]) * 0.985,
                        "volume_24h": 10000.0,
                        "timestamp": candle_time,
                        "source": self.provider_name,
                        "evidence_grade": EvidenceGrade.EMPIRICAL.label,
                        "is_synthetic": 0,
                        "data_unavailable": False,
                    }
                logger.warning(
                    "SQLiteCacheProvider rejecting stale candle for %s (age=%.1f min > 15m).",
                    symbol,
                    (now_ms - candle_time) / 60000.0,
                )
        return None

    async def fetch_order_book_depth(self, symbol: str, limit: int = 10) -> dict[str, Any] | None:
        return None


class SyntheticMarketProvider(BaseMarketDataProvider):
    """
    Unavailability sentinel for the market-data chain.

    This provider used to fabricate a stochastic OHLCV series when every real
    venue failed, and it emitted those candles *untagged*. Downstream,
    ``data_streamer.fetch_external_ohlcv()`` stamped ``is_synthetic = 0`` over
    whatever the gateway returned and persisted it — so a transient outage
    permanently wrote random walks into ``market_data.db`` labelled as observed
    market data, which then fed ``market_states`` and the analogue engine.

    It no longer invents price history. When the real providers are exhausted
    the honest answer is "no data", and the evidence layer must be able to say
    so. Everything this class still returns is explicitly stamped
    ``EvidenceGrade.FABRICATED`` so it can never satisfy a live-decision gate.
    """

    @property
    def provider_name(self) -> str:
        return "UNAVAILABLE_SENTINEL"

    def __init__(self):
        self.base_prices: dict[str, float] = {
            "BTC/USDT": 79000.0,
            "ETH/USDT": 2500.0,
            "SOL/USDT": 188.5,
            "BNB/USDT": 625.0,
            "XRP/USDT": 0.62,
            "DOGE/USDT": 0.145,
            "XAU/USD": 2685.0,
        }

    async def fetch_historical_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        """
        Return no candles. Ever.

        Fabricating OHLCV here is what allowed random data to be persisted as
        empirical evidence. An empty series is the truthful representation of
        "all real providers are unavailable", and it propagates as
        ``EvidenceGrade.FABRICATED`` (see ``weakest_grade`` on empty input).
        """
        logger.warning(
            "Market data unavailable for %s %s — all real providers exhausted. "
            "Returning no candles; fabrication is disabled by policy.",
            symbol,
            timeframe,
        )
        return []

    async def fetch_live_ticker(self, symbol: str) -> dict[str, Any] | None:
        """
        Last-resort reference price so the terminal can still render a number
        during an outage. Explicitly graded FABRICATED and jitter-free — a
        random walk would imply live movement that is not happening.
        """
        price = self.base_prices.get(symbol, 79000.0)
        return {
            "symbol": symbol,
            "price": price,
            "evidence_grade": EvidenceGrade.FABRICATED.label,
            "is_synthetic": 1,
            "data_unavailable": True,
            "change_24h_pct": 2.15,
            "high_24h": round(price * 1.018, 2),
            "low_24h": round(price * 0.982, 2),
            "volume_24h": 45000.0,
            "timestamp": int(time.time() * 1000),
            "source": self.provider_name,
        }

    async def fetch_order_book_depth(self, symbol: str, limit: int = 10) -> dict[str, Any] | None:
        """
        Return empty depth. Fabricated liquidity drove order-book imbalance and
        VPIN toxicity signals, which fed directional scoring.
        """
        return {
            "symbol": symbol,
            "asks": [],
            "bids": [],
            "timestamp": int(time.time() * 1000),
            "evidence_grade": EvidenceGrade.FABRICATED.label,
            "data_unavailable": True,
        }


class CompositeMarketDataGateway:
    """
    Tiered Market Data Provider Gateway with automatic failover, health tracking, and local caching.
    """

    def __init__(self):
        self.providers: list[BaseMarketDataProvider] = [
            BinanceMarketDataProvider(),
            BybitMarketDataProvider(),
            SQLiteCacheProvider(),
            SyntheticMarketProvider(),
        ]
        self.active_provider_name: str = "BINANCE_REST"
        self._provider_health: dict[str, dict[str, Any]] = {
            p.provider_name: {"status": "HEALTHY", "latency_ms": 15.0, "errors": 0}
            for p in self.providers
        }

    async def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Fetch OHLCV from the first healthy real venue.

        Provenance is stamped *here*, at the single chokepoint every consumer
        goes through, rather than in each provider — a provider that forgets to
        stamp cannot then leak untagged data into the pipeline.

        Returns an empty list when no real venue can serve the request. Callers
        must treat empty as "no evidence", never as "no signal".
        """
        for p in self.providers:
            t0 = time.time()
            try:
                data = await p.fetch_historical_ohlcv(symbol, timeframe, limit=limit)
                if data and len(data) > 0:
                    rtt = (time.time() - t0) * 1000
                    self._provider_health[p.provider_name]["latency_ms"] = round(rtt, 1)
                    self._provider_health[p.provider_name]["status"] = "HEALTHY"
                    self.active_provider_name = p.provider_name
                    # EMPIRICAL is a *ceiling*, not an assignment: stamping is
                    # downgrade-only, so cached rows that were stored as
                    # synthetic keep their FABRICATED grade.
                    return stamp_records(data, EvidenceGrade.EMPIRICAL)
            except Exception as e:  # noqa: BLE001 — defensive fallback
                self._provider_health[p.provider_name]["errors"] += 1
                self._provider_health[p.provider_name]["status"] = "DEGRADED"
                logger.debug(f"Provider {p.provider_name} failed for {symbol}: {e}")

        # All real venues exhausted. Do not fabricate — say so.
        self.active_provider_name = "UNAVAILABLE"
        logger.warning(
            "No real market data available for %s %s; returning empty series.",
            symbol,
            timeframe,
        )
        return []

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        for p in self.providers:
            try:
                data = await p.fetch_live_ticker(symbol)
                if data and data.get("price"):
                    return data
            except Exception:  # noqa: BLE001, S110 — best-effort fallback, never raise
                pass
        fallback = await SyntheticMarketProvider().fetch_live_ticker(symbol)
        if fallback:
            return fallback
        return {
            "symbol": symbol,
            "price": 79000.0 if "BTC" in symbol else 2500.0,
            "evidence_grade": EvidenceGrade.FABRICATED.label,
            "is_synthetic": 1,
            "data_unavailable": True,
            "source": "UNAVAILABLE_SENTINEL",
        }

    async def get_order_book(self, symbol: str, limit: int = 10) -> dict[str, Any]:
        for p in self.providers:
            try:
                data = await p.fetch_order_book_depth(symbol, limit=limit)
                if data and data.get("asks") and data.get("bids"):
                    return data
            except Exception:  # noqa: BLE001, S110 — best-effort fallback, never raise
                pass
        return await SyntheticMarketProvider().fetch_order_book_depth(symbol, limit) or {
            "symbol": symbol,
            "asks": [],
            "bids": [],
        }

    def get_provider_health(self) -> dict[str, Any]:
        return {
            "active_provider": self.active_provider_name,
            "providers": self._provider_health,
        }


market_gateway = CompositeMarketDataGateway()
