"""
core/temporal_intelligence/features.py
======================================
Zero-Lookahead Point-in-Time Feature Extractor for Temporal Price-Action Intelligence (Milestone 22).

Enforces:
- Strict temporal causality: Feature vector at index i accesses candles strictly <= i.
- No forward-looking data leakage or future-candle dependency.
- Robust division-by-zero protection on compressed candles.
"""

from __future__ import annotations

import logging
from typing import Any

from core.temporal_intelligence.models import TemporalFeatureVector

logger = logging.getLogger("sky.temporal.features")


class ZeroLookaheadFeatureExtractor:
    """Extracts point-in-time technical and price-action features with guaranteed causality."""

    @staticmethod
    def extract_features(
        candles: list[dict[str, Any]],
        index: int,
        symbol: str = "BTC/USDT",
    ) -> TemporalFeatureVector | None:
        """
        Extracts feature vector at index i using strictly candles[0 : i+1].
        Requires at least 20 historical candles for rolling metrics (SMA, ATR, Swings).
        """
        if index < 20 or index >= len(candles):
            return None

        cur = candles[index]
        cur_open = float(cur["open"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        cur_close = float(cur["close"])
        cur_vol = float(cur.get("volume", 0.0))
        cur_ts = int(cur["timestamp"])

        if cur_close <= 0:
            return None

        # 1. Multi-Window Past Returns
        c_prev1 = float(candles[index - 1]["close"])
        c_prev2 = float(candles[index - 2]["close"])
        c_prev4 = float(candles[index - 4]["close"])

        ret_1bar = ((cur_close - c_prev1) / c_prev1) * 100.0 if c_prev1 > 0 else 0.0
        ret_2bar = ((cur_close - c_prev2) / c_prev2) * 100.0 if c_prev2 > 0 else 0.0
        ret_4bar = ((cur_close - c_prev4) / c_prev4) * 100.0 if c_prev4 > 0 else 0.0

        # 2. Relative Volume (RVOL over 20 bars strictly <= index)
        vol_window = [float(candles[j].get("volume", 0.0)) for j in range(index - 19, index + 1)]
        mean_vol = sum(vol_window) / len(vol_window) if vol_window else 1.0
        rvol = round(cur_vol / mean_vol, 3) if mean_vol > 0 else 1.0

        # 3. ATR(14) Volatility Normalization
        tr_list = []
        for j in range(index - 13, index + 1):
            h = float(candles[j]["high"])
            l = float(candles[j]["low"])
            prev_c = float(candles[j - 1]["close"])
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            tr_list.append(tr)
        atr_14 = sum(tr_list) / len(tr_list) if tr_list else 1.0

        candle_range = max(cur_high - cur_low, 1e-6)
        vol_ratio = round(candle_range / atr_14, 3) if atr_14 > 0 else 1.0

        # 4. Intrabar Wick & Body Geometry
        body = abs(cur_close - cur_open)
        upper_wick = cur_high - max(cur_open, cur_close)
        lower_wick = min(cur_open, cur_close) - cur_low

        body_ratio = round(min(1.0, max(0.0, body / candle_range)), 3)
        upper_wick_ratio = round(min(1.0, max(0.0, upper_wick / candle_range)), 3)
        lower_wick_ratio = round(min(1.0, max(0.0, lower_wick / candle_range)), 3)

        # 5. Distance to 20-Bar Swing High and Swing Low
        high_20 = max(float(candles[j]["high"]) for j in range(index - 19, index + 1))
        low_20 = min(float(candles[j]["low"]) for j in range(index - 19, index + 1))

        dist_high = round(((high_20 - cur_close) / cur_close) * 100.0, 3)
        dist_low = round(((cur_close - low_20) / cur_close) * 100.0, 3)

        return TemporalFeatureVector(
            timestamp_ms=cur_ts,
            symbol=symbol,
            reference_price=round(cur_close, 4),
            return_1bar_pct=round(ret_1bar, 3),
            return_2bar_pct=round(ret_2bar, 3),
            return_4bar_pct=round(ret_4bar, 3),
            relative_volume=rvol,
            volatility_ratio=vol_ratio,
            body_to_range_ratio=body_ratio,
            upper_wick_ratio=upper_wick_ratio,
            lower_wick_ratio=lower_wick_ratio,
            distance_to_swing_high_pct=dist_high,
            distance_to_swing_low_pct=dist_low,
            is_out_of_distribution=False,
        )
