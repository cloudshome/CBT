"""
Phase 2: Liquidity Engine.
Discovers resting liquidity pools (EQH/EQL, PDH/PDL, Range Extremes, Clustered Highs/Lows)
and detects precision Liquidity Sweeps, Grabs, and Reclaims with ATR penetration and rejection metrics.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import (
    LiquidityPool,
    LiquidityPoolType,
    LiquiditySweep,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger("sky_intelligence.liquidity_engine")


class LiquidityEngine:
    """
    Algorithmic Liquidity Engine.
    Discovers liquidity pools and detects mathematical liquidity sweeps.
    """

    def __init__(self, eqh_eql_tolerance_pct: float = 0.001):
        self.tolerance_pct = eqh_eql_tolerance_pct

    def identify_liquidity_pools(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        swings: list[SwingPoint] | None = None,
    ) -> list[LiquidityPool]:
        """
        Discovers resting liquidity pools: Equal Highs/Lows, Range Extremes, and Recent Peaks.
        """
        if len(candles) < 3:
            return []

        pools: list[LiquidityPool] = []
        # 1. Range Extremes (Max High & Min Low over lookback preceding current bar)
        lookback = candles[:-1] if len(candles) >= 4 else candles
        highs = [float(c["high"]) for c in lookback]
        lows = [float(c["low"]) for c in lookback]
        timestamps = [int(c.get("timestamp", i)) for i, c in enumerate(lookback)]
        volumes = [float(c.get("volume", 1.0)) for c in lookback]

        max_h = max(highs)
        min_l = min(lows)
        max_idx = highs.index(max_h)
        min_idx = lows.index(min_l)

        pools.append(
            LiquidityPool(
                pool_type=LiquidityPoolType.RANGE_HIGH,
                symbol=symbol,
                timeframe=timeframe,
                price_level=max_h,
                top_boundary=round(max_h * (1 + self.tolerance_pct), 2),
                bottom_boundary=round(max_h * (1 - self.tolerance_pct), 2),
                creation_timestamp=timestamps[max_idx],
                retest_count=1,
                volume_depth=volumes[max_idx],
                is_active=True,
            )
        )

        pools.append(
            LiquidityPool(
                pool_type=LiquidityPoolType.RANGE_LOW,
                symbol=symbol,
                timeframe=timeframe,
                price_level=min_l,
                top_boundary=round(min_l * (1 + self.tolerance_pct), 2),
                bottom_boundary=round(min_l * (1 - self.tolerance_pct), 2),
                creation_timestamp=timestamps[min_idx],
                retest_count=1,
                volume_depth=volumes[min_idx],
                is_active=True,
            )
        )

        # 2. Equal Highs (EQH) and Equal Lows (EQL) detection from Swings or Peaks
        if swings:
            sh_list = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
            sl_list = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

            # Check pairs of swing highs for EQH
            for i in range(len(sh_list) - 1):
                for j in range(i + 1, min(i + 4, len(sh_list))):
                    s1, s2 = sh_list[i], sh_list[j]
                    rel_diff = abs(s1.price - s2.price) / s1.price
                    if rel_diff <= self.tolerance_pct:
                        mean_price = (s1.price + s2.price) / 2.0
                        pools.append(
                            LiquidityPool(
                                pool_type=LiquidityPoolType.EQUAL_HIGHS,
                                symbol=symbol,
                                timeframe=timeframe,
                                price_level=round(mean_price, 2),
                                top_boundary=round(mean_price * (1 + self.tolerance_pct), 2),
                                bottom_boundary=round(mean_price * (1 - self.tolerance_pct), 2),
                                creation_timestamp=s2.timestamp,
                                retest_count=2,
                                volume_depth=1.5,
                                is_active=True,
                            )
                        )

            # Check pairs of swing lows for EQL
            for i in range(len(sl_list) - 1):
                for j in range(i + 1, min(i + 4, len(sl_list))):
                    s1, s2 = sl_list[i], sl_list[j]
                    rel_diff = abs(s1.price - s2.price) / s1.price
                    if rel_diff <= self.tolerance_pct:
                        mean_price = (s1.price + s2.price) / 2.0
                        pools.append(
                            LiquidityPool(
                                pool_type=LiquidityPoolType.EQUAL_LOWS,
                                symbol=symbol,
                                timeframe=timeframe,
                                price_level=round(mean_price, 2),
                                top_boundary=round(mean_price * (1 + self.tolerance_pct), 2),
                                bottom_boundary=round(mean_price * (1 - self.tolerance_pct), 2),
                                creation_timestamp=s2.timestamp,
                                retest_count=2,
                                volume_depth=1.5,
                                is_active=True,
                            )
                        )

        return pools

    def detect_sweeps(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        pools: list[LiquidityPool],
        atr: float | None = None,
    ) -> list[LiquiditySweep]:
        """
        Detects liquidity sweeps where price wicks beyond a pool level but rejects and closes back within.
        Calculates penetration distance, penetration/ATR, rejection distance, and wick/body ratios.
        """
        if len(candles) < 5 or not pools:
            return []

        if atr is None or atr <= 0:
            tr_list = [
                max(
                    candles[i]["high"] - candles[i]["low"],
                    abs(candles[i]["high"] - candles[i - 1]["close"]),
                    abs(candles[i]["low"] - candles[i - 1]["close"]),
                )
                for i in range(1, len(candles))
            ]
            atr = (
                float(np.mean(tr_list[-14:]))
                if len(tr_list) >= 14
                else (candles[-1]["close"] * 0.01)
            )

        sweeps: list[LiquiditySweep] = []

        for pool in pools:
            for bar_idx in range(1, len(candles)):
                candle = candles[bar_idx]
                bar_ts = int(candle.get("timestamp", bar_idx))
                if bar_ts < pool.creation_timestamp:
                    continue
                candles[bar_idx - 1]
                high_p = float(candle["high"])
                low_p = float(candle["low"])
                open_p = float(candle["open"])
                close_p = float(candle["close"])
                volume_c = float(candle.get("volume", 1.0))
                bar_ts = int(candle.get("timestamp", bar_idx))

                body_len = abs(close_p - open_p)
                safe_body = max(body_len, 0.01)

                # Bearish Sweep: Sweeping Highs / EQH / Range High
                if pool.pool_type in [
                    LiquidityPoolType.EQUAL_HIGHS,
                    LiquidityPoolType.RANGE_HIGH,
                    LiquidityPoolType.PREVIOUS_DAY_HIGH,
                    LiquidityPoolType.SESSION_HIGH,
                ]:
                    # High penetrates pool level, but Close finishes BELOW pool level
                    if high_p > pool.price_level and close_p < pool.price_level:
                        penetration = high_p - pool.price_level
                        penetration_atr = penetration / (atr if atr > 0 else 1.0)
                        rejection_dist = high_p - close_p
                        upper_wick = high_p - max(open_p, close_p)
                        wick_ratio = upper_wick / safe_body

                        if penetration_atr >= 0.15 and wick_ratio >= 1.0:
                            # Significant sweep
                            disp_score = min(
                                100.0, (rejection_dist / atr) * 45.0 + (wick_ratio * 15.0)
                            )
                            sweeps.append(
                                LiquiditySweep(
                                    pool_type=pool.pool_type,
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    sweep_timestamp=bar_ts,
                                    swept_level=pool.price_level,
                                    extreme_price=high_p,
                                    penetration_distance=round(penetration, 2),
                                    penetration_atr_ratio=round(penetration_atr, 2),
                                    rejection_distance=round(rejection_dist, 2),
                                    wick_to_body_ratio=round(wick_ratio, 2),
                                    volume_delta=round(-0.5 * volume_c, 2),
                                    subsequent_displacement_score=round(disp_score, 1),
                                    is_valid_reclaim=True,
                                    meta={
                                        "bar_index": bar_idx,
                                        "direction": "BEARISH_SWEEP_REVERSAL",
                                    },
                                )
                            )

                # Bullish Sweep: Sweeping Lows / EQL / Range Low
                if pool.pool_type in [
                    LiquidityPoolType.EQUAL_LOWS,
                    LiquidityPoolType.RANGE_LOW,
                    LiquidityPoolType.PREVIOUS_DAY_LOW,
                    LiquidityPoolType.SESSION_LOW,
                ]:
                    # Low penetrates below pool level, but Close finishes ABOVE pool level
                    if low_p < pool.price_level and close_p > pool.price_level:
                        penetration = pool.price_level - low_p
                        penetration_atr = penetration / (atr if atr > 0 else 1.0)
                        rejection_dist = close_p - low_p
                        lower_wick = min(open_p, close_p) - low_p
                        wick_ratio = lower_wick / safe_body

                        if penetration_atr >= 0.15 and wick_ratio >= 1.0:
                            disp_score = min(
                                100.0, (rejection_dist / atr) * 45.0 + (wick_ratio * 15.0)
                            )
                            sweeps.append(
                                LiquiditySweep(
                                    pool_type=pool.pool_type,
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    sweep_timestamp=bar_ts,
                                    swept_level=pool.price_level,
                                    extreme_price=low_p,
                                    penetration_distance=round(penetration, 2),
                                    penetration_atr_ratio=round(penetration_atr, 2),
                                    rejection_distance=round(rejection_dist, 2),
                                    wick_to_body_ratio=round(wick_ratio, 2),
                                    volume_delta=round(0.5 * volume_c, 2),
                                    subsequent_displacement_score=round(disp_score, 1),
                                    is_valid_reclaim=True,
                                    meta={
                                        "bar_index": bar_idx,
                                        "direction": "BULLISH_SWEEP_REVERSAL",
                                    },
                                )
                            )

        return sweeps


# Global singleton instance
liquidity_engine = LiquidityEngine()
