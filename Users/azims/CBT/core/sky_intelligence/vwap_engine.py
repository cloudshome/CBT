"""
Phase 8: VWAP Engine.
Calculates institutional volume-weighted average price (VWAP) primitives:
- Session VWAP (calculated from UTC 00:00 or lookback session anchor)
- Rolling Standard Deviation Bands (±1.0σ, ±1.5σ, ±2.0σ)
- Anchored VWAP (AVWAP from designated structural pivot/high-volume anchor)
- Mean-Reversion probability score & deviation z-score
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional
import numpy as np

from core.sky_intelligence.types import VWAPFeature

logger = logging.getLogger("sky_intelligence.vwap_engine")


class VWAPEngine:
    """
    Quantitative Volume-Weighted Average Price (VWAP) Engine.
    """

    def __init__(self, default_lookback_bars: int = 96):
        # 96 bars on 15m timeframe = 24 hours (1 full daily session)
        self.default_lookback = default_lookback_bars

    def compute_vwap(
        self,
        candles: List[Dict[str, Any]],
        anchor_index: Optional[int] = None,
    ) -> VWAPFeature:
        """
        Computes VWAP, standard deviation bands, and mean-reversion metrics.
        """
        if not candles:
            return VWAPFeature(
                timestamp=0,
                vwap=0.0,
                upper_band_1sigma=0.0,
                lower_band_1sigma=0.0,
                upper_band_2sigma=0.0,
                lower_band_2sigma=0.0,
                std_dev=0.0,
                deviation_sigmas=0.0,
                is_above_vwap=False,
                is_extended_overbought=False,
                is_extended_oversold=False,
                is_reclaiming=False,
                mean_reversion_prob=0.0,
                anchored_vwap=None,
            )

        n = len(candles)
        start_idx = 0
        if anchor_index is not None and 0 <= anchor_index < n:
            start_idx = anchor_index
        else:
            start_idx = max(0, n - self.default_lookback)

        sub_candles = candles[start_idx:]
        if not sub_candles:
            sub_candles = candles

        cum_vol = 0.0
        cum_tp_vol = 0.0
        cum_tp_sq_vol = 0.0

        for c in sub_candles:
            h = float(c["high"])
            l = float(c["low"])
            cl = float(c["close"])
            v = max(float(c.get("volume", 1.0)), 1e-6)
            tp = (h + l + cl) / 3.0

            cum_vol += v
            cum_tp_vol += tp * v
            cum_tp_sq_vol += (tp ** 2) * v

        if cum_vol <= 0:
            vwap = float(candles[-1]["close"])
            std_dev = 0.0
        else:
            vwap = cum_tp_vol / cum_vol
            variance = max(0.0, (cum_tp_sq_vol / cum_vol) - (vwap ** 2))
            std_dev = math.sqrt(variance)

        curr_price = float(candles[-1]["close"])
        ts = int(candles[-1].get("timestamp", 0))

        # Deviation in sigmas
        safe_std = max(std_dev, 1e-4)
        deviation_sigmas = (curr_price - vwap) / safe_std

        # Sigma bands
        upper_1s = vwap + (1.0 * std_dev)
        lower_1s = vwap - (1.0 * std_dev)
        upper_2s = vwap + (2.0 * std_dev)
        lower_2s = vwap - (2.0 * std_dev)

        is_above = curr_price >= vwap
        is_overbought = deviation_sigmas >= 2.0
        is_oversold = deviation_sigmas <= -2.0

        # Check reclaim condition (previous candle was beyond ±1.5σ and current is moving inside)
        is_reclaiming = False
        if len(candles) >= 2:
            prev_close = float(candles[-2]["close"])
            prev_dev = (prev_close - vwap) / safe_std
            if prev_dev < -1.5 and curr_price > prev_close:
                is_reclaiming = True
            elif prev_dev > 1.5 and curr_price < prev_close:
                is_reclaiming = True

        # Mean reversion probability via sigmoid of absolute deviation
        abs_dev = abs(deviation_sigmas)
        # Logistic curve: around 2.0 sigma prob reaches ~70%, 3.0 sigma reaches ~85%
        mean_rev_prob = 1.0 / (1.0 + math.exp(-1.2 * (abs_dev - 1.5)))
        mean_rev_prob = max(0.05, min(0.95, mean_rev_prob))

        # Anchored VWAP (if anchor_index provided)
        anchored_val = vwap if anchor_index is not None else None

        return VWAPFeature(
            timestamp=ts,
            vwap=round(vwap, 4),
            upper_band_1sigma=round(upper_1s, 4),
            lower_band_1sigma=round(lower_1s, 4),
            upper_band_2sigma=round(upper_2s, 4),
            lower_band_2sigma=round(lower_2s, 4),
            std_dev=round(std_dev, 4),
            deviation_sigmas=round(deviation_sigmas, 2),
            is_above_vwap=is_above,
            is_extended_overbought=is_overbought,
            is_extended_oversold=is_oversold,
            is_reclaiming=is_reclaiming,
            mean_reversion_prob=round(mean_rev_prob, 3),
            anchored_vwap=round(anchored_val, 4) if anchored_val is not None else None,
        )

    def compute_anchored_vwap(
        self,
        candles: List[Dict[str, Any]],
        anchor_index: int,
    ) -> float:
        """
        Computes an anchored VWAP from a specific historical index.
        """
        if not candles or anchor_index >= len(candles):
            return 0.0

        sub = candles[max(0, anchor_index):]
        cum_vol = 0.0
        cum_tp_vol = 0.0

        for c in sub:
            h = float(c["high"])
            l = float(c["low"])
            cl = float(c["close"])
            v = max(float(c.get("volume", 1.0)), 1e-6)
            tp = (h + l + cl) / 3.0
            cum_vol += v
            cum_tp_vol += tp * v

        return round(cum_tp_vol / cum_vol, 4) if cum_vol > 0 else 0.0


# Global singleton instance
vwap_engine = VWAPEngine()
