"""
Historical Gap Recovery & Boot-Time Backfiller.
Detects missing candle segments in SQLite market store upon startup
and automatically backfills the missing sequences.
"""

from __future__ import annotations

import logging

from core.data_streamer import TIMEFRAME_TO_MS, data_streamer
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.gap_recovery")


class GapRecoveryManager:
    """Detects and repairs historical discontinuities in candlestick series."""

    def __init__(self):
        self.streamer = data_streamer

    def scan_and_repair_all(self, symbols: list[str], timeframes: list[str]) -> dict[str, int]:
        """
        Scans all tracked symbol/timeframe combinations and repairs detected gaps.
        Returns a dictionary of total repaired bars per symbol.
        """
        results: dict[str, int] = {}
        for sym in symbols:
            total_repaired = 0
            for tf in timeframes:
                repaired = self.scan_and_repair(sym, tf)
                total_repaired += repaired
            results[sym] = total_repaired
        return results

    def scan_and_repair(self, symbol: str, timeframe: str) -> int:
        """
        Scans a single symbol and timeframe for missing bars and repairs them.
        """
        tf_ms = TIMEFRAME_TO_MS.get(timeframe, 60000)
        with db_manager.get_market_conn() as conn:
            cursor = conn.execute(
                """
                SELECT timestamp, close FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp ASC;
                """,
                (symbol, timeframe),
            )
            rows = cursor.fetchall()

        if len(rows) < 2:
            return 0

        repaired_count = 0
        candles_to_insert = []

        for i in range(1, len(rows)):
            t_prev = rows[i - 1]["timestamp"]
            t_curr = rows[i]["timestamp"]
            p_prev = rows[i - 1]["close"]
            p_curr = rows[i]["close"]

            gap = t_curr - t_prev
            if gap > (1.5 * tf_ms):
                missing_bars = int(gap // tf_ms) - 1
                logger.info(
                    f"Detected {missing_bars} missing bars in {symbol} {timeframe} between {t_prev} and {t_curr}"
                )

                # Linear price interpolation for gap filling with small noise
                for j in range(1, missing_bars + 1):
                    t_fill = t_prev + (j * tf_ms)
                    fraction = j / (missing_bars + 1)
                    p_fill = p_prev + (p_curr - p_prev) * fraction
                    candles_to_insert.append(
                        {
                            "timestamp": t_fill,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "open": round(p_fill, 2),
                            "high": round(p_fill * 1.0005, 2),
                            "low": round(p_fill * 0.9995, 2),
                            "close": round(p_fill, 2),
                            "volume": 10.0,
                            "is_synthetic": 1,
                        }
                    )
                    repaired_count += 1

        if candles_to_insert:
            self.streamer.save_candles(symbol, timeframe, candles_to_insert)
            logger.info(
                f"Successfully repaired {repaired_count} gap candles for {symbol} {timeframe}."
            )

        return repaired_count


# Singleton
gap_recovery_manager = GapRecoveryManager()
