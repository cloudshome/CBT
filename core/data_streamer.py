"""
Multi-Source Live Data Streamer & Candle Ingestion Engine.
Ingests real-time and historical OHLCV market feeds for BTC/USDT, ETH/USDT, and Gold (XAU/USD).
Multi-exchange fallback chain: Binance REST -> Bybit V5 Linear -> SQLite Persistent Cache -> Dynamic Generator.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from core.causal_firewall import causal_firewall
from core.database import db_manager
from core.evidence_integrity import EVIDENCE_KEY, EvidenceGrade, grade_of, stamp_records
from core.market_providers import market_gateway

logger = logging.getLogger("ai_quant_sentinel.data_streamer")

TIMEFRAME_TO_MS = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

TIMEFRAME_TO_BYBIT = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}


class DataStreamer:
    """
    Manages multi-exchange connections, historical backfills,
    and real-time candlestick streams into the persistent market store.
    """

    def __init__(self):
        self.active_symbols = ["BTC/USDT", "ETH/USDT", "XAU/USD"]
        self.active_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        self._last_known_prices: dict[str, float] = {
            "BTC/USDT": 79850.0,
            "ETH/USDT": 2680.0,
            "SOL/USDT": 180.0,
            "BNB/USDT": 600.0,
            "XRP/USDT": 1.50,
            "LINK/USDT": 15.0,
            "DOGE/USDT": 0.15,
            "AVAX/USDT": 25.0,
            "SUI/USDT": 2.0,
            "ZEC/USDT": 30.0,
            "XAU/USD": 2678.5,
        }

    def save_candles(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> int:
        """
        Persists a list of candles to data/market_data.db with ON CONFLICT DO UPDATE.
        Each candle: {timestamp, open, high, low, close, volume}
        """
        if not candles:
            return 0

        inserted = 0
        with db_manager.get_market_conn() as conn:
            for c in candles:
                conn.execute(
                    """
                    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume, is_synthetic)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        volume=excluded.volume,
                        is_synthetic=excluded.is_synthetic;
                    """,
                    (
                        int(c["timestamp"]),
                        symbol,
                        timeframe,
                        float(c["open"]),
                        float(c["high"]),
                        float(c["low"]),
                        float(c["close"]),
                        float(c.get("volume", 0.0)),
                        int(c.get("is_synthetic", 0)),
                    ),
                )
                inserted += 1
            conn.commit()
        return inserted

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        end_time: int | None = None,
        exclude_synthetic: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Retrieves point-in-time historical candles from data/market_data.db.
        Strictly enforces causal firewall point-in-time isolation.
        """
        max_time = end_time if end_time is not None else causal_firewall.get_current_time_ms()
        synthetic_clause = (
            "AND (is_synthetic = 0 OR is_synthetic IS NULL)" if exclude_synthetic else ""
        )

        with db_manager.get_market_conn() as conn:
            cursor = conn.execute(
                f"""
                SELECT timestamp, symbol, timeframe, open, high, low, close, volume, is_synthetic
                FROM candles
                WHERE symbol = ? AND timeframe = ? AND timestamp <= ? {synthetic_clause}
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (symbol, timeframe, max_time, limit),
            )
            rows = cursor.fetchall()

        results = [
            {
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "is_synthetic": int(row["is_synthetic"])
                if "is_synthetic" in row.keys() and row["is_synthetic"] is not None
                else 0,
            }
            for row in reversed(rows)
        ]
        # Translate the stored legacy flag into an explicit evidence grade so
        # consumers never have to interpret a bare boolean.
        for rec in results:
            rec[EVIDENCE_KEY] = grade_of(rec).label

        # If database is empty or sparse, bootstrap realistic live series with synthetic marker
        if len(results) < min(30, limit) and not exclude_synthetic:
            synthetic = self.generate_synthetic_candles(
                symbol, timeframe, count=limit, end_time=max_time
            )
            stamp_records(synthetic, EvidenceGrade.FABRICATED)
            # Still persisted (tagged) so the chart has a continuous series on a
            # cold start, but the FABRICATED grade travels with every bar and
            # ``exclude_synthetic=True`` filters them from any empirical query.
            self.save_candles(symbol, timeframe, synthetic)
            results = synthetic

        return results

    async def get_live_ticker_payload(self, symbol: str) -> dict[str, Any]:
        """
        Fetches sub-second live price tick with full provenance, evidence grade, and synthetic markers.
        """
        data = await market_gateway.get_ticker(symbol)
        price = float(data.get("price", self._last_known_prices.get(symbol, 0.0)))
        if (
            data.get("evidence_grade") == EvidenceGrade.EMPIRICAL.label
            and not data.get("is_synthetic")
            and not data.get("data_unavailable")
        ):
            self._last_known_prices[symbol] = price
        return data

    async def get_live_ticker(self, symbol: str) -> float:
        """
        Fetches sub-second live price tick from Composite Market Gateway (Binance -> Bybit -> SQLite -> Synthetic).
        """
        data = await self.get_live_ticker_payload(symbol)
        # If synthetic fallback, prefer returning the last known empirical price if available
        if (
            data.get("is_synthetic")
            or data.get("data_unavailable")
            or data.get("evidence_grade") == EvidenceGrade.FABRICATED.label
        ):
            if symbol in self._last_known_prices:
                return self._last_known_prices[symbol]
        return float(data.get("price", self._last_known_prices.get(symbol, 0.0)))

    async def fetch_external_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Fetches live OHLCV candles from Composite Market Gateway with automatic failover and persistence.
        """
        candles = await market_gateway.get_ohlcv(symbol, timeframe, limit=limit)
        if candles:
            # NEVER blanket-stamp provenance here. This line used to read
            # ``c["is_synthetic"] = 0`` unconditionally, which relabelled
            # fabricated candles as real and persisted them — the single worst
            # defect in the data path. The gateway is now the authority on
            # provenance and ``stamp_records`` is downgrade-only, so the worst
            # this can do is preserve what the gateway already determined.
            grade = min((grade_of(c) for c in candles), default=EvidenceGrade.FABRICATED)
            stamp_records(candles, grade)

            if grade is EvidenceGrade.EMPIRICAL:
                self._last_known_prices[symbol] = candles[-1]["close"]
                self.save_candles(symbol, timeframe, candles)
            else:
                # Non-empirical bars are never written to the market database;
                # persisting them would contaminate the empirical corpus that
                # the analogue engine treats as ground truth.
                logger.warning(
                    "Refusing to persist %s candles for %s %s (grade=%s).",
                    len(candles),
                    symbol,
                    timeframe,
                    grade.label,
                )
            return candles

        # Local Persistent / Dynamic Fallback
        return self.get_candles(symbol, timeframe, limit=limit)

    async def get_order_book(self, symbol: str, limit: int = 10) -> dict[str, Any]:
        """
        Fetches L2 order book depth with composite failover across tier-1 venues.
        """
        return await market_gateway.get_order_book(symbol, limit=limit)

    def generate_synthetic_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generates realistic time-continuous candles with dynamic price drift and explicit is_synthetic=1 tag.
        """
        tf_ms = TIMEFRAME_TO_MS.get(timeframe, 60000)
        t_now = end_time if end_time is not None else int(time.time() * 1000)
        t_start = t_now - (count * tf_ms)

        base_price = self._last_known_prices.get(
            symbol, 79850.0 if "BTC" in symbol else (2680.0 if "ETH" in symbol else 2678.5)
        )
        vol = (
            0.0015
            if timeframe in ["1m", "5m"]
            else (0.004 if timeframe in ["15m", "1h"] else 0.012)
        )

        candles = []
        current_price = base_price

        for i in range(count):
            c_time = t_start + (i * tf_ms)
            ret = float(np.random.normal(0.0, vol))
            open_p = current_price
            close_p = open_p * (1.0 + ret)
            high_p = max(open_p, close_p) * (1.0 + abs(float(np.random.normal(0, vol * 0.7))))
            low_p = min(open_p, close_p) * (1.0 - abs(float(np.random.normal(0, vol * 0.7))))
            vol_p = float(np.random.uniform(50.0, 500.0) * (1.0 + abs(ret) * 10.0))

            candles.append(
                {
                    "timestamp": c_time,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": round(vol_p, 2),
                    "is_synthetic": 1,
                    EVIDENCE_KEY: EvidenceGrade.FABRICATED.label,
                }
            )
            current_price = close_p

        self._last_known_prices[symbol] = current_price
        return candles

    def get_data_freshness_report(self, symbols: list[str] | None = None) -> dict[str, Any]:
        """
        Inspectable data quality, freshness, and provenance audit for market data feeds.
        Addresses Priority 2 of Project Inspection Report.
        """
        target_symbols = symbols or self.active_symbols
        now_ms = causal_firewall.get_current_time_ms()
        report: dict[str, Any] = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000.0)),
            "current_time_ms": now_ms,
            "monitored_assets": len(target_symbols),
            "assets": {},
        }

        with db_manager.get_market_conn() as conn:
            for sym in target_symbols:
                cursor = conn.execute(
                    """
                    SELECT timestamp, timeframe, open, high, low, close, volume, is_synthetic
                    FROM candles
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT 100;
                    """,
                    (sym,),
                )
                rows = cursor.fetchall()
                if rows:
                    latest_row = rows[0]
                    latest_ts = int(latest_row["timestamp"])
                    age_ms = max(0, now_ms - latest_ts)
                    age_min = round(age_ms / 60000.0, 2)
                    synthetic_count = sum(1 for r in rows if int(r["is_synthetic"] or 0) == 1)
                    empirical_count = len(rows) - synthetic_count
                    quality_pct = round((empirical_count / len(rows)) * 100.0, 1) if rows else 0.0

                    # Freshness: fresh if age <= 30 minutes for crypto feeds
                    is_fresh = age_ms <= (30 * 60 * 1000)
                    evidence_grade = (
                        EvidenceGrade.EMPIRICAL.label
                        if quality_pct >= 80.0
                        else EvidenceGrade.FABRICATED.label
                    )

                    report["assets"][sym] = {
                        "symbol": sym,
                        "market_type": "PERPETUAL_FUTURES" if "USDT" in sym else "SPOT_COMMODITY",
                        "latest_candle_time_ms": latest_ts,
                        "latest_candle_time_utc": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(latest_ts / 1000.0)
                        ),
                        "age_ms": age_ms,
                        "age_minutes": age_min,
                        "freshness_status": "FRESH"
                        if is_fresh
                        else ("STALE" if age_ms <= (120 * 60 * 1000) else "DISCONNECTED"),
                        "evidence_grade": evidence_grade,
                        "sample_window_bars": len(rows),
                        "empirical_bars": empirical_count,
                        "synthetic_bars": synthetic_count,
                        "quality_score_pct": quality_pct,
                        "latest_close": float(latest_row["close"]),
                    }
                else:
                    report["assets"][sym] = {
                        "symbol": sym,
                        "market_type": "PERPETUAL_FUTURES" if "USDT" in sym else "SPOT_COMMODITY",
                        "latest_candle_time_ms": None,
                        "latest_candle_time_utc": None,
                        "age_ms": None,
                        "age_minutes": None,
                        "freshness_status": "NO_DATA",
                        "evidence_grade": EvidenceGrade.FABRICATED.label,
                        "sample_window_bars": 0,
                        "empirical_bars": 0,
                        "synthetic_bars": 0,
                        "quality_score_pct": 0.0,
                        "latest_close": self._last_known_prices.get(sym, 0.0),
                    }
        return report


# Singleton
data_streamer = DataStreamer()
