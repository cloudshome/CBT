"""
Phase 4: Volume Engine.
Computes Relative Volume (rVol), Volume Moving Averages, Expansion/Contraction,
Delta, Cumulative Volume Delta (CVD), and records explicit Exchange Source Attribution.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import VolumeFeature

logger = logging.getLogger("sky_intelligence.volume_engine")


class VolumeEngine:
    """
    Algorithmic Volume Engine with explicit source tagging and CVD integration.
    """

    def __init__(self, ma_period: int = 20, default_exchange: str = "binance_futures"):
        self.ma_period = ma_period
        self.default_exchange = default_exchange

    def analyze_volume(
        self,
        candles: list[dict[str, Any]],
        exchange_source: str | None = None,
    ) -> VolumeFeature:
        """
        Calculates volume features from a candlestick series.
        """
        source = exchange_source or self.default_exchange
        if not candles:
            return VolumeFeature(
                timestamp=0,
                volume=0.0,
                relative_volume=1.0,
                volume_ma=1.0,
                is_expanding=False,
                is_contracting=False,
                buy_volume=0.0,
                sell_volume=0.0,
                delta=0.0,
                cumulative_volume_delta=0.0,
                source_exchange=source,
            )

        vols = [float(c.get("volume", 0.0)) for c in candles]
        curr_vol = vols[-1] if vols else 0.0

        # Moving Average of volume
        window = vols[-self.ma_period :] if len(vols) >= self.ma_period else vols
        vol_ma = float(np.mean(window)) if window else 1.0
        safe_ma = max(vol_ma, 0.0001)

        r_vol = curr_vol / safe_ma

        # Expansion/Contraction
        is_expanding = r_vol >= 1.5
        is_contracting = r_vol <= 0.65

        # Estimate Buy vs Sell Volume & Delta from candle wick/body geometry if orderbook delta not present
        cvd = 0.0
        curr_delta = 0.0
        curr_buy = 0.0
        curr_sell = 0.0

        for c in candles:
            v = float(c.get("volume", 0.0))
            float(c.get("open", 0.0))
            cl = float(c.get("close", 0.0))
            hi = float(c.get("high", 0.0))
            lo = float(c.get("low", 0.0))
            rng = max(hi - lo, 0.0001)

            # Check if direct taker delta is attached in candle metadata
            if "buy_volume" in c and "sell_volume" in c:
                b_v = float(c["buy_volume"])
                s_v = float(c["sell_volume"])
                d = b_v - s_v
            else:
                # Approximate delta via fractional close position inside the candle range
                frac = (cl - lo) / rng
                b_v = v * frac
                s_v = v * (1.0 - frac)
                d = b_v - s_v

            cvd += d
            curr_buy = b_v
            curr_sell = s_v
            curr_delta = d

        last_ts = int(candles[-1].get("timestamp", 0))

        return VolumeFeature(
            timestamp=last_ts,
            volume=round(curr_vol, 2),
            relative_volume=round(r_vol, 2),
            volume_ma=round(vol_ma, 2),
            is_expanding=is_expanding,
            is_contracting=is_contracting,
            buy_volume=round(curr_buy, 2),
            sell_volume=round(curr_sell, 2),
            delta=round(curr_delta, 2),
            cumulative_volume_delta=round(cvd, 2),
            source_exchange=source,
        )


# Global singleton instance
volume_engine = VolumeEngine()
