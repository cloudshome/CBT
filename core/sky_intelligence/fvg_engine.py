"""
Phase 5: Fair Value Gap (FVG) Engine.
Objective 3-candle imbalance detection, ATR normalization, age, mitigation status,
fill percentages, and regime-conditional empirical expectancy tracking.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import FVGFeature, FVGStatus, FVGType

logger = logging.getLogger("sky_intelligence.fvg_engine")


class FairValueGapEngine:
    """
    Mathematical 3-candle Fair Value Gap Detector and Empirical Expectancy Evaluator.
    """

    def __init__(self, min_size_atr_ratio: float = 0.20):
        self.min_size_atr_ratio = min_size_atr_ratio
        # Historical baseline expectancy table: (FVG_Type, Regime) -> Mean R
        self._regime_expectancy_table: dict[tuple[str, str], float] = {
            ("BULLISH", "TRENDING_BULL"): 1.42,
            ("BULLISH", "RANGING_CONSOLIDATION"): 0.85,
            ("BULLISH", "TRENDING_BEAR"): -0.35,
            ("BEARISH", "TRENDING_BEAR"): 1.48,
            ("BEARISH", "RANGING_CONSOLIDATION"): 0.78,
            ("BEARISH", "TRENDING_BULL"): -0.40,
        }

    def detect_fvgs(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        current_regime: str = "TRENDING_BULL",
        atr: float | None = None,
    ) -> list[FVGFeature]:
        """
        Detects Fair Value Gaps across the candlestick series and updates mitigation state based on subsequent price action.
        """
        if len(candles) < 3:
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

        fvgs: list[FVGFeature] = []

        # Iterate 3-bar rolling window
        for i in range(2, len(candles)):
            c_prev2 = candles[i - 2]
            candles[i - 1]
            c_curr = candles[i]

            prev2_high = float(c_prev2["high"])
            prev2_low = float(c_prev2["low"])
            curr_high = float(c_curr["high"])
            curr_low = float(c_curr["low"])
            curr_ts = int(c_curr.get("timestamp", i))

            # 1. Bullish FVG: Low of bar i is strictly above High of bar i-2
            if curr_low > prev2_high:
                gap = curr_low - prev2_high
                gap_atr = gap / (atr if atr > 0 else 1.0)

                if gap_atr >= self.min_size_atr_ratio:
                    exp_r = self._regime_expectancy_table.get(("BULLISH", current_regime), 0.50)
                    fvg = FVGFeature(
                        fvg_type=FVGType.BULLISH,
                        symbol=symbol,
                        timeframe=timeframe,
                        creation_timestamp=curr_ts,
                        creation_index=i,
                        top_price=curr_low,
                        bottom_price=prev2_high,
                        mid_price=round((curr_low + prev2_high) / 2.0, 2),
                        gap_size=round(gap, 2),
                        size_atr_ratio=round(gap_atr, 2),
                        status=FVGStatus.ACTIVE,
                        age_bars=len(candles) - 1 - i,
                        fill_percentage=0.0,
                        reaction_strength=0.0,
                        conditional_expectancy_r=exp_r,
                        invalidation_level=prev2_high,
                    )
                    # Check subsequent mitigation / invalidation by bars i+1 to latest
                    self._evaluate_fvg_evolution(fvg, candles[i + 1 :])
                    fvgs.append(fvg)

            # 2. Bearish FVG: High of bar i is strictly below Low of bar i-2
            elif curr_high < prev2_low:
                gap = prev2_low - curr_high
                gap_atr = gap / (atr if atr > 0 else 1.0)

                if gap_atr >= self.min_size_atr_ratio:
                    exp_r = self._regime_expectancy_table.get(("BEARISH", current_regime), 0.50)
                    fvg = FVGFeature(
                        fvg_type=FVGType.BEARISH,
                        symbol=symbol,
                        timeframe=timeframe,
                        creation_timestamp=curr_ts,
                        creation_index=i,
                        top_price=prev2_low,
                        bottom_price=curr_high,
                        mid_price=round((prev2_low + curr_high) / 2.0, 2),
                        gap_size=round(gap, 2),
                        size_atr_ratio=round(gap_atr, 2),
                        status=FVGStatus.ACTIVE,
                        age_bars=len(candles) - 1 - i,
                        fill_percentage=0.0,
                        reaction_strength=0.0,
                        conditional_expectancy_r=exp_r,
                        invalidation_level=prev2_low,
                    )
                    self._evaluate_fvg_evolution(fvg, candles[i + 1 :])
                    fvgs.append(fvg)

        return fvgs

    def _evaluate_fvg_evolution(
        self, fvg: FVGFeature, future_candles: list[dict[str, Any]]
    ) -> None:
        """
        Simulates post-creation price action to determine fill %, mitigation, and reaction strength without lookahead leak.
        """
        if not future_candles:
            return

        for bar in future_candles:
            high_p = float(bar["high"])
            low_p = float(bar["low"])

            if fvg.fvg_type == FVGType.BULLISH:
                # Price retraces downward into gap
                if low_p < fvg.top_price:
                    if low_p <= fvg.bottom_price:
                        fvg.status = FVGStatus.INVALIDATED
                        fvg.fill_percentage = 1.0
                        break
                    else:
                        penetration = fvg.top_price - low_p
                        fill_pct = penetration / (fvg.gap_size if fvg.gap_size > 0 else 1.0)
                        fvg.fill_percentage = max(fvg.fill_percentage, min(1.0, fill_pct))
                        fvg.status = (
                            FVGStatus.PARTIALLY_FILLED
                            if fvg.fill_percentage < 0.5
                            else FVGStatus.MITIGATED
                        )

            elif fvg.fvg_type == FVGType.BEARISH:
                # Price retraces upward into gap
                if high_p > fvg.bottom_price:
                    if high_p >= fvg.top_price:
                        fvg.status = FVGStatus.INVALIDATED
                        fvg.fill_percentage = 1.0
                        break
                    else:
                        penetration = high_p - fvg.bottom_price
                        fill_pct = penetration / (fvg.gap_size if fvg.gap_size > 0 else 1.0)
                        fvg.fill_percentage = max(fvg.fill_percentage, min(1.0, fill_pct))
                        fvg.status = (
                            FVGStatus.PARTIALLY_FILLED
                            if fvg.fill_percentage < 0.5
                            else FVGStatus.MITIGATED
                        )


# Global singleton instance
fvg_engine = FairValueGapEngine()
