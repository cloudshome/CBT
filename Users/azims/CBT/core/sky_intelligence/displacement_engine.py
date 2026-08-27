"""
Phase 7: Displacement Engine.
Measures abnormal directional velocity, body/ATR ratios, range expansion, and consecutive drive.
Generates a statistically calibrated Displacement Score in [0, 100].
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from core.sky_intelligence.types import DisplacementFeature

logger = logging.getLogger("sky_intelligence.displacement_engine")


class DisplacementEngine:
    """
    Directional Momentum and Abnormal Volatility Displacement Engine.
    """

    def __init__(self, atr_period: int = 14):
        self.atr_period = atr_period

    def calculate_displacement(
        self,
        candles: List[Dict[str, Any]],
        target_index: Optional[int] = None,
        atr: Optional[float] = None,
    ) -> DisplacementFeature:
        """
        Calculates the multi-factor Displacement Score (0–100) for a given candle or the latest candle.
        """
        if not candles:
            return DisplacementFeature(
                candle_index=0,
                timestamp=0,
                direction="NEUTRAL",
                body_atr_ratio=0.0,
                range_atr_ratio=0.0,
                consecutive_directional_bars=0,
                volume_expansion_ratio=1.0,
                price_velocity=0.0,
                breakout_distance=0.0,
                close_location_in_range=0.5,
                displacement_score=0.0,
            )

        idx = len(candles) - 1 if target_index is None else max(0, min(len(candles) - 1, target_index))
        curr = candles[idx]

        if atr is None or atr <= 0:
            tr_list = [
                max(
                    candles[i]["high"] - candles[i]["low"],
                    abs(candles[i]["high"] - candles[i - 1]["close"]),
                    abs(candles[i]["low"] - candles[i - 1]["close"]),
                )
                for i in range(1, len(candles))
            ]
            atr = float(np.mean(tr_list[-self.atr_period :])) if len(tr_list) >= self.atr_period else (curr["close"] * 0.01)

        safe_atr = max(atr, 0.0001)

        open_p = float(curr["open"])
        close_p = float(curr["close"])
        high_p = float(curr["high"])
        low_p = float(curr["low"])
        vol_p = float(curr.get("volume", 1.0))
        ts = int(curr.get("timestamp", idx))

        body = abs(close_p - open_p)
        candle_range = max(high_p - low_p, 0.0001)
        direction = "BULLISH" if close_p > open_p else ("BEARISH" if close_p < open_p else "NEUTRAL")

        body_atr = body / safe_atr
        range_atr = candle_range / safe_atr

        # Close location within the full high-low range [0.0 = low extreme, 1.0 = high extreme]
        close_loc = (close_p - low_p) / candle_range

        # Volume expansion ratio vs 20-bar baseline
        lookback_vols = [float(c.get("volume", 1.0)) for c in candles[max(0, idx - 20) : idx]]
        avg_vol = float(np.mean(lookback_vols)) if lookback_vols else vol_p
        vol_expansion = vol_p / max(avg_vol, 0.0001)

        # Count consecutive directional bars up to this index
        consecutive = 1
        for k in range(idx - 1, max(-1, idx - 6), -1):
            c_k = candles[k]
            if direction == "BULLISH" and c_k["close"] > c_k["open"]:
                consecutive += 1
            elif direction == "BEARISH" and c_k["close"] < c_k["open"]:
                consecutive += 1
            else:
                break

        # Price velocity: body / 1 bar
        velocity = body / 1.0

        # Breakout distance beyond previous 5-bar high/low
        prev_5_highs = [float(c["high"]) for c in candles[max(0, idx - 5) : idx]]
        prev_5_lows = [float(c["low"]) for c in candles[max(0, idx - 5) : idx]]

        if direction == "BULLISH" and prev_5_highs:
            breakout_dist = max(0.0, close_p - max(prev_5_highs))
        elif direction == "BEARISH" and prev_5_lows:
            breakout_dist = max(0.0, min(prev_5_lows) - close_p)
        else:
            breakout_dist = 0.0

        # Statistically calibrated composite score [0, 100]:
        # 1. Body/ATR contribution (up to 40 pts for 2.0x ATR body)
        comp_body = min(40.0, (body_atr / 2.0) * 40.0)
        # 2. Range/ATR contribution (up to 25 pts for 2.5x ATR range)
        comp_range = min(25.0, (range_atr / 2.5) * 25.0)
        # 3. Volume expansion contribution (up to 20 pts for 2.0x volume)
        comp_vol = min(20.0, (vol_expansion / 2.0) * 20.0)
        # 4. Proximity to closing extreme (up to 15 pts if close near wick tip)
        extreme_proximity = close_loc if direction == "BULLISH" else (1.0 - close_loc)
        comp_extreme = extreme_proximity * 15.0

        raw_score = comp_body + comp_range + comp_vol + comp_extreme
        final_score = min(100.0, max(0.0, raw_score))

        return DisplacementFeature(
            candle_index=idx,
            timestamp=ts,
            direction=direction,
            body_atr_ratio=round(body_atr, 2),
            range_atr_ratio=round(range_atr, 2),
            consecutive_directional_bars=consecutive,
            volume_expansion_ratio=round(vol_expansion, 2),
            price_velocity=round(velocity, 2),
            breakout_distance=round(breakout_dist, 2),
            close_location_in_range=round(close_loc, 2),
            displacement_score=round(final_score, 1),
        )


# Global singleton instance
displacement_engine = DisplacementEngine()
