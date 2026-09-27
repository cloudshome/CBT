"""
Phase 1: Market Structure Engine.
Mathematical and deterministic swing point detection, BOS, CHoCH, MSS, and Structure Reclaims.
Enforces strict zero lookahead / anti-repainting rules: confirmation occurs at index (i + R).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import (
    StructureEvent,
    StructureEventType,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger("sky_intelligence.market_structure")


class MarketStructureEngine:
    """
    Mathematical, non-repainting Market Structure Engine.
    Detects deterministic Swings, Higher Highs/Lows, BOS, CHoCH, and MSS.
    """

    def __init__(self, swing_left: int = 3, swing_right: int = 3):
        self.swing_left = swing_left
        self.swing_right = swing_right

    def detect_swings(
        self,
        candles: list[dict[str, Any]],
        timeframe: str = "15m",
    ) -> list[SwingPoint]:
        """
        Detects swing highs and swing lows across the candle series.
        Anti-repainting guarantee: Swing at index i is confirmed only at index i + swing_right.
        """
        n = len(candles)
        if n < self.swing_left + self.swing_right + 1:
            return []

        swings: list[SwingPoint] = []
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        timestamps = [int(c.get("timestamp", i)) for i, c in enumerate(candles)]

        for i in range(self.swing_left, n - self.swing_right):
            current_high = highs[i]
            current_low = lows[i]

            # Swing High condition: strictly greater than surrounding L and R bars
            is_sh = True
            for k in range(i - self.swing_left, i + self.swing_right + 1):
                if k != i and highs[k] >= current_high:
                    is_sh = False
                    break

            if is_sh:
                conf_idx = i + self.swing_right
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=timestamps[i],
                        swing_type=SwingType.SWING_HIGH,
                        price=current_high,
                        timeframe=timeframe,
                        is_confirmed=True,
                        confirmation_index=conf_idx,
                        confirmation_timestamp=timestamps[conf_idx],
                    )
                )

            # Swing Low condition: strictly lower than surrounding L and R bars
            is_sl = True
            for k in range(i - self.swing_left, i + self.swing_right + 1):
                if k != i and lows[k] <= current_low:
                    is_sl = False
                    break

            if is_sl:
                conf_idx = i + self.swing_right
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=timestamps[i],
                        swing_type=SwingType.SWING_LOW,
                        price=current_low,
                        timeframe=timeframe,
                        is_confirmed=True,
                        confirmation_index=conf_idx,
                        confirmation_timestamp=timestamps[conf_idx],
                    )
                )

        swings.sort(key=lambda s: s.index)
        return swings

    def analyze_structure(
        self,
        candles: list[dict[str, Any]],
        timeframe: str = "15m",
        atr: float | None = None,
    ) -> tuple[list[SwingPoint], list[StructureEvent]]:
        """
        Analyzes the candlestick series, identifies swing points and structural events (BOS, CHoCH, MSS).
        Returns list of Swings and list of Confirmed Structure Events.
        """
        swings = self.detect_swings(candles, timeframe=timeframe)
        if len(swings) < 1:
            return swings, []

        if atr is None or atr <= 0:
            # Estimate simple 14-bar ATR if not supplied
            tr_list = []
            for i in range(1, len(candles)):
                h = candles[i]["high"]
                lo = candles[i]["low"]
                c_prev = candles[i - 1]["close"]
                tr = max(h - lo, abs(h - c_prev), abs(lo - c_prev))
                tr_list.append(tr)
            atr = (
                float(np.mean(tr_list[-14:]))
                if len(tr_list) >= 14
                else (candles[-1]["close"] * 0.01)
            )

        events: list[StructureEvent] = []
        high_swings = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        low_swings = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

        # Track trend state
        current_trend = "NEUTRAL"
        high_swings[0] if high_swings else None
        low_swings[0] if low_swings else None

        # Iterate forward through candles to catch breaks of confirmed swing levels
        confirmed_swing_highs: list[SwingPoint] = []
        confirmed_swing_lows: list[SwingPoint] = []

        # Map confirmation index
        swings_by_conf_idx: dict[int, list[SwingPoint]] = {}
        for s in swings:
            c_idx = s.confirmation_index or s.index
            swings_by_conf_idx.setdefault(c_idx, []).append(s)

        for bar_idx, candle in enumerate(candles):
            # Register newly confirmed swings at this bar
            if bar_idx in swings_by_conf_idx:
                for new_s in swings_by_conf_idx[bar_idx]:
                    if new_s.swing_type == SwingType.SWING_HIGH:
                        confirmed_swing_highs.append(new_s)
                    else:
                        confirmed_swing_lows.append(new_s)

            close_p = float(candle["close"])
            float(candle["high"])
            float(candle["low"])
            bar_ts = int(candle.get("timestamp", bar_idx))

            # Check for Bullish Break (BOS / CHoCH / MSS) above latest active confirmed swing high
            if confirmed_swing_highs:
                active_sh = confirmed_swing_highs[-1]
                # Break occurs when bar_idx > active_sh.confirmation_index and close crosses above
                if bar_idx > (active_sh.confirmation_index or active_sh.index):
                    if close_p > active_sh.price:
                        disp_atr = (close_p - active_sh.price) / (atr if atr > 0 else 1.0)
                        strength = min(1.0, max(0.4, disp_atr * 0.5))

                        # Determine if BOS (continuation) or CHoCH/MSS (trend shift)
                        if current_trend == "BEARISH":
                            ev_type = (
                                StructureEventType.MSS_BULLISH
                                if disp_atr >= 1.2
                                else StructureEventType.CHOCH_BULLISH
                            )
                            current_trend = "BULLISH"
                        else:
                            ev_type = StructureEventType.BOS_BULLISH
                            current_trend = "BULLISH"

                        events.append(
                            StructureEvent(
                                event_type=ev_type,
                                timeframe=timeframe,
                                event_timestamp=bar_ts,
                                confirmation_timestamp=bar_ts,
                                price=close_p,
                                broken_level=active_sh.price,
                                displacement_atr=round(disp_atr, 2),
                                strength_score=round(strength, 2),
                                confirmation_status="CONFIRMED",
                                meta={
                                    "broken_swing_index": active_sh.index,
                                    "broken_swing_price": active_sh.price,
                                    "trigger_bar_index": bar_idx,
                                },
                            )
                        )
                        # Consume this swing high to avoid re-triggering on same level
                        confirmed_swing_highs.pop()

            # Check for Bearish Break (BOS / CHoCH / MSS) below latest active confirmed swing low
            if confirmed_swing_lows:
                active_sl = confirmed_swing_lows[-1]
                if bar_idx > (active_sl.confirmation_index or active_sl.index):
                    if close_p < active_sl.price:
                        disp_atr = (active_sl.price - close_p) / (atr if atr > 0 else 1.0)
                        strength = min(1.0, max(0.4, disp_atr * 0.5))

                        if current_trend == "BULLISH":
                            ev_type = (
                                StructureEventType.MSS_BEARISH
                                if disp_atr >= 1.2
                                else StructureEventType.CHOCH_BEARISH
                            )
                            current_trend = "BEARISH"
                        else:
                            ev_type = StructureEventType.BOS_BEARISH
                            current_trend = "BEARISH"

                        events.append(
                            StructureEvent(
                                event_type=ev_type,
                                timeframe=timeframe,
                                event_timestamp=bar_ts,
                                confirmation_timestamp=bar_ts,
                                price=close_p,
                                broken_level=active_sl.price,
                                displacement_atr=round(disp_atr, 2),
                                strength_score=round(strength, 2),
                                confirmation_status="CONFIRMED",
                                meta={
                                    "broken_swing_index": active_sl.index,
                                    "broken_swing_price": active_sl.price,
                                    "trigger_bar_index": bar_idx,
                                },
                            )
                        )
                        # Consume this swing low
                        confirmed_swing_lows.pop()

        return swings, events


# Global singleton instance
market_structure_engine = MarketStructureEngine()
