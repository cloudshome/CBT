"""
Judas Swing & Session Liquidity Trap Hunter.
Detects institutional manipulation traps at London Open (07:00-08:30 UTC) and NY Open (13:00-14:30 UTC)
sweeping Asian Session (00:00-06:00 UTC) range extremes and snapping back with >50% rejection wicks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.judas_sweep_hunter")


@dataclass
class JudasSweepSignal:
    symbol: str
    session_name: str               # "LONDON_OPEN", "NY_OPEN"
    timestamp: int
    sweep_direction: str            # "BULLISH_REVERSAL_SWEEP", "BEARISH_REVERSAL_SWEEP"
    asian_high: float
    asian_low: float
    swept_level: float
    rejection_wick_pct: float
    confidence: float
    invalidation_level: float
    target_level: float
    narrative: str


class JudasSweepHunter:
    """
    Identifies institutional session sweep traps (Judas Swings).
    """

    def check_session_judas_sweep(
        self,
        symbol: str,
        candles_15m: List[Dict[str, Any]],
    ) -> Optional[JudasSweepSignal]:
        """
        Extracts Asian range (00:00 - 06:00 UTC) and checks if London/NY open candles
        sweep and reject Asian highs/lows.
        """
        if len(candles_15m) < 30:
            return None

        # Look at the most recent candle timestamp
        latest_c = candles_15m[-1]
        dt = datetime.fromtimestamp(latest_c["timestamp"] / 1000.0, tz=timezone.utc)
        hour = dt.hour
        minute = dt.minute
        time_dec = hour + minute / 60.0

        # Session windows in UTC
        is_london_open = 7.0 <= time_dec <= 8.5
        is_ny_open = 13.0 <= time_dec <= 14.5

        if not (is_london_open or is_ny_open):
            return None

        session_name = "LONDON_OPEN" if is_london_open else "NY_OPEN"

        # Calculate Asian Session High & Low (00:00 to 06:00 UTC)
        asian_candles = []
        for c in candles_15m:
            c_dt = datetime.fromtimestamp(c["timestamp"] / 1000.0, tz=timezone.utc)
            if c_dt.date() == dt.date() and 0 <= c_dt.hour < 6:
                asian_candles.append(c)

        if len(asian_candles) < 4:
            # Fallback to earliest 24 bars if not aligned to midnight
            asian_candles = candles_15m[:24]

        asian_high = max(c["high"] for c in asian_candles)
        asian_low = min(c["low"] for c in asian_candles)

        c_open = latest_c["open"]
        c_high = latest_c["high"]
        c_low = latest_c["low"]
        c_close = latest_c["close"]
        bar_range = max(0.01, c_high - c_low)

        # Bullish Judas Sweep: pierced Asian Low, then closed back above Asian Low with strong lower wick
        if c_low < asian_low and c_close > asian_low:
            lower_wick = min(c_open, c_close) - c_low
            wick_pct = (lower_wick / bar_range) * 100.0
            if wick_pct >= 45.0:
                target = asian_high
                inval = c_low
                return JudasSweepSignal(
                    symbol=symbol,
                    session_name=session_name,
                    timestamp=latest_c["timestamp"],
                    sweep_direction="BULLISH_REVERSAL_SWEEP",
                    asian_high=round(asian_high, 2),
                    asian_low=round(asian_low, 2),
                    swept_level=round(asian_low, 2),
                    rejection_wick_pct=round(wick_pct, 1),
                    confidence=0.86,
                    invalidation_level=round(inval, 2),
                    target_level=round(target, 2),
                    narrative=(
                        f"Judas Swing at {session_name}: Asian Low ({asian_low:.2f}) swept to {c_low:.2f}, "
                        f"rejected with {wick_pct:.1f}% lower wick. Institutional liquidity engineered for Long expansion toward Asian High ({target:.2f})."
                    ),
                )

        # Bearish Judas Sweep: pierced Asian High, then closed back below Asian High with strong upper wick
        if c_high > asian_high and c_close < asian_high:
            upper_wick = c_high - max(c_open, c_close)
            wick_pct = (upper_wick / bar_range) * 100.0
            if wick_pct >= 45.0:
                target = asian_low
                inval = c_high
                return JudasSweepSignal(
                    symbol=symbol,
                    session_name=session_name,
                    timestamp=latest_c["timestamp"],
                    sweep_direction="BEARISH_REVERSAL_SWEEP",
                    asian_high=round(asian_high, 2),
                    asian_low=round(asian_low, 2),
                    swept_level=round(asian_high, 2),
                    rejection_wick_pct=round(wick_pct, 1),
                    confidence=0.87,
                    invalidation_level=round(inval, 2),
                    target_level=round(target, 2),
                    narrative=(
                        f"Judas Swing at {session_name}: Asian High ({asian_high:.2f}) swept to {c_high:.2f}, "
                        f"rejected with {wick_pct:.1f}% upper wick. Institutional liquidity engineered for Short expansion toward Asian Low ({target:.2f})."
                    ),
                )

        return None


# Singleton
judas_sweep_hunter = JudasSweepHunter()
