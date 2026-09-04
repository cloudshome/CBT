"""
Phase 6: Candidate Order Block Engine.
Hypothesis-driven detection of Candidate Bullish and Bearish Order Blocks.
Evaluates ATR-normalized displacement, retests, mitigation, and statistical validity without dogmatic assumptions.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import CandidateOrderBlock, OrderBlockType

logger = logging.getLogger("sky_intelligence.order_block_engine")


class OrderBlockEngine:
    """
    Hypothesis-Driven Candidate Order Block Detector.
    Neutral terminology: 'CANDIDATE ORDER BLOCK'.
    """

    def __init__(self, min_displacement_atr: float = 1.2):
        self.min_displacement_atr = min_displacement_atr

    def detect_candidate_order_blocks(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        atr: float | None = None,
    ) -> list[CandidateOrderBlock]:
        """
        Scans for candidate order blocks: origin down/up candle preceding an explosive directional move.
        """
        if len(candles) < 4:
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

        candidate_obs: list[CandidateOrderBlock] = []

        # Iterate looking for origin candle at i-2 or i-3 followed by strong displacement
        for i in range(3, len(candles)):
            c_origin = candles[i - 2]
            c_disp1 = candles[i - 1]
            c_disp2 = candles[i]

            op_origin = float(c_origin["open"])
            cl_origin = float(c_origin["close"])
            hi_origin = float(c_origin["high"])
            lo_origin = float(c_origin["low"])
            vol_origin = float(c_origin.get("volume", 1.0))
            ts_origin = int(c_origin.get("timestamp", i - 2))

            # 1. Candidate Bullish OB: Origin is a down-candle (Close < Open), followed by explosive upward expansion
            if cl_origin < op_origin:
                expansion_move = float(c_disp2["high"]) - lo_origin
                disp_atr = expansion_move / (atr if atr > 0 else 1.0)

                if disp_atr >= self.min_displacement_atr:
                    # Verified strong post-origin displacement
                    vol_expansion = (
                        float(c_disp1.get("volume", 1.0)) + float(c_disp2.get("volume", 1.0))
                    ) / (2.0 * max(vol_origin, 0.01))

                    ob = CandidateOrderBlock(
                        ob_type=OrderBlockType.CANDIDATE_BULLISH_OB,
                        symbol=symbol,
                        timeframe=timeframe,
                        origin_timestamp=ts_origin,
                        origin_index=i - 2,
                        zone_high=round(hi_origin, 2),
                        zone_low=round(lo_origin, 2),
                        origin_candle={
                            "open": op_origin,
                            "high": hi_origin,
                            "low": lo_origin,
                            "close": cl_origin,
                            "volume": vol_origin,
                        },
                        post_origin_displacement_atr=round(disp_atr, 2),
                        volume_expansion_ratio=round(vol_expansion, 2),
                        distance_to_liquidity=0.0,
                        retest_count=0,
                        is_mitigated=False,
                        is_invalidated=False,
                        expectancy_score=round(min(1.5, 0.5 + (disp_atr * 0.2)), 2),
                    )
                    self._evaluate_ob_evolution(ob, candles[i + 1 :])
                    candidate_obs.append(ob)

            # 2. Candidate Bearish OB: Origin is an up-candle (Close > Open), followed by explosive downward expansion
            elif cl_origin > op_origin:
                expansion_move = hi_origin - float(c_disp2["low"])
                disp_atr = expansion_move / (atr if atr > 0 else 1.0)

                if disp_atr >= self.min_displacement_atr:
                    vol_expansion = (
                        float(c_disp1.get("volume", 1.0)) + float(c_disp2.get("volume", 1.0))
                    ) / (2.0 * max(vol_origin, 0.01))

                    ob = CandidateOrderBlock(
                        ob_type=OrderBlockType.CANDIDATE_BEARISH_OB,
                        symbol=symbol,
                        timeframe=timeframe,
                        origin_timestamp=ts_origin,
                        origin_index=i - 2,
                        zone_high=round(hi_origin, 2),
                        zone_low=round(lo_origin, 2),
                        origin_candle={
                            "open": op_origin,
                            "high": hi_origin,
                            "low": lo_origin,
                            "close": cl_origin,
                            "volume": vol_origin,
                        },
                        post_origin_displacement_atr=round(disp_atr, 2),
                        volume_expansion_ratio=round(vol_expansion, 2),
                        distance_to_liquidity=0.0,
                        retest_count=0,
                        is_mitigated=False,
                        is_invalidated=False,
                        expectancy_score=round(min(1.5, 0.5 + (disp_atr * 0.2)), 2),
                    )
                    self._evaluate_ob_evolution(ob, candles[i + 1 :])
                    candidate_obs.append(ob)

        return candidate_obs

    def _evaluate_ob_evolution(
        self, ob: CandidateOrderBlock, future_candles: list[dict[str, Any]]
    ) -> None:
        """
        Evaluates retest counts, mitigation, and invalidation of the candidate order block.
        """
        for bar in future_candles:
            high_p = float(bar["high"])
            low_p = float(bar["low"])

            if ob.ob_type == OrderBlockType.CANDIDATE_BULLISH_OB:
                # Retest: low touches inside zone [zone_low, zone_high]
                if low_p <= ob.zone_high:
                    ob.retest_count += 1
                    ob.is_mitigated = True
                    if low_p < ob.zone_low:
                        # Full invalidation below origin candle low
                        ob.is_invalidated = True
                        break

            elif ob.ob_type == OrderBlockType.CANDIDATE_BEARISH_OB:
                # Retest: high touches inside zone
                if high_p >= ob.zone_low:
                    ob.retest_count += 1
                    ob.is_mitigated = True
                    if high_p > ob.zone_high:
                        # Full invalidation above origin candle high
                        ob.is_invalidated = True
                        break


# Global singleton instance
order_block_engine = OrderBlockEngine()
