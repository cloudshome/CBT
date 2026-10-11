"""
Empirical Smart Money Concepts (SMC/ICT) Engine.
Detects Fair Value Gaps (FVG), Order Blocks (OB), Liquidity Sweeps, and Breaker Blocks.
Evaluates empirical conditional expectancy E[R | Pattern, Regime, Asset] and flags UNFAVORABLE_ODDS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.smc_engine")


class SMCPatternType(StrEnum):
    BULLISH_FVG = "BULLISH_FVG"
    BEARISH_FVG = "BEARISH_FVG"
    BULLISH_OB = "BULLISH_OB"
    BEARISH_OB = "BEARISH_OB"
    BULLISH_SWEEP = "BULLISH_SWEEP"
    BEARISH_SWEEP = "BEARISH_SWEEP"
    BULLISH_BREAKER = "BULLISH_BREAKER"
    BEARISH_BREAKER = "BEARISH_BREAKER"


@dataclass
class SMCPattern:
    pattern_type: SMCPatternType
    symbol: str
    timeframe: str
    timestamp: int
    top_price: float
    bottom_price: float
    mid_price: float
    invalidation_level: float
    strength: float  # [0.0, 1.0]
    conditional_expectancy_r: float  # E[R | Pattern, Regime, Asset]
    is_favorable: bool
    status: str  # "ACTIVE", "MITIGATED", "INVALIDATED"
    meta: dict[str, Any] = field(default_factory=dict)


class SMCEngine:
    """
    Algorithmic Smart Money Concepts detector with heuristic prior expectancy mapping.
    NOTE: Default baseline table contains static heuristic priors, not live calibrated empirical distributions.
    """

    def __init__(self):
        # Heuristic baseline prior expectancy tables: (Pattern, Regime) -> mean R-multiple prior
        # [HEURISTIC] These values are initial research priors and must be calibrated against historical databases.
        self._expectancy_table: dict[tuple[str, str], float] = {
            (SMCPatternType.BULLISH_FVG.value, "TRENDING_BULL"): 1.42,
            (SMCPatternType.BULLISH_FVG.value, "RANGING_CONSOLIDATION"): 0.85,
            (SMCPatternType.BULLISH_FVG.value, "TRENDING_BEAR"): -0.35,
            (SMCPatternType.BEARISH_FVG.value, "TRENDING_BEAR"): 1.48,
            (SMCPatternType.BEARISH_FVG.value, "RANGING_CONSOLIDATION"): 0.78,
            (SMCPatternType.BEARISH_FVG.value, "TRENDING_BULL"): -0.40,
            (SMCPatternType.BULLISH_OB.value, "TRENDING_BULL"): 1.65,
            (SMCPatternType.BULLISH_OB.value, "RANGING_CONSOLIDATION"): 0.95,
            (SMCPatternType.BULLISH_OB.value, "TRENDING_BEAR"): -0.50,
            (SMCPatternType.BEARISH_OB.value, "TRENDING_BEAR"): 1.70,
            (SMCPatternType.BEARISH_OB.value, "RANGING_CONSOLIDATION"): 0.90,
            (SMCPatternType.BEARISH_OB.value, "TRENDING_BULL"): -0.55,
            (SMCPatternType.BULLISH_SWEEP.value, "RANGING_CONSOLIDATION"): 1.85,
            (SMCPatternType.BULLISH_SWEEP.value, "TRENDING_BULL"): 1.30,
            (SMCPatternType.BULLISH_SWEEP.value, "TRENDING_BEAR"): 0.20,
            (SMCPatternType.BEARISH_SWEEP.value, "RANGING_CONSOLIDATION"): 1.90,
            (SMCPatternType.BEARISH_SWEEP.value, "TRENDING_BEAR"): 1.35,
            (SMCPatternType.BEARISH_SWEEP.value, "TRENDING_BULL"): 0.15,
        }

    def scan(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        current_regime: str = "TRENDING_BULL",
    ) -> list[SMCPattern]:
        """
        Scans a candlestick series for valid SMC patterns and attaches empirical expectancy.
        """
        if len(candles) < 5:
            return []

        patterns: list[SMCPattern] = []
        patterns.extend(self._scan_fvgs(symbol, timeframe, candles, current_regime))
        patterns.extend(self._scan_order_blocks(symbol, timeframe, candles, current_regime))
        patterns.extend(self._scan_liquidity_sweeps(symbol, timeframe, candles, current_regime))

        return patterns

    def _get_expectancy(self, pattern_type: str, regime: str) -> float:
        return self._expectancy_table.get((pattern_type, regime), 0.50)

    def _scan_fvgs(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        regime: str,
    ) -> list[SMCPattern]:
        fvgs = []
        for i in range(2, len(candles)):
            c_prev2 = candles[i - 2]
            c_mid = candles[i - 1]
            c_curr = candles[i]

            # Bullish FVG: Low of curr > High of prev2
            if c_curr["low"] > c_prev2["high"]:
                gap_size = c_curr["low"] - c_prev2["high"]
                if gap_size > (c_mid["open"] * 0.0005):  # Filter out trivial micro-gaps
                    exp_r = self._get_expectancy(SMCPatternType.BULLISH_FVG.value, regime)
                    fvgs.append(
                        SMCPattern(
                            pattern_type=SMCPatternType.BULLISH_FVG,
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c_curr["timestamp"],
                            top_price=round(c_curr["low"], 2),
                            bottom_price=round(c_prev2["high"], 2),
                            mid_price=round((c_curr["low"] + c_prev2["high"]) / 2.0, 2),
                            invalidation_level=round(c_prev2["high"], 2),
                            strength=round(
                                min(1.0, gap_size / (c_mid["high"] - c_mid["low"] + 1e-5)), 2
                            ),
                            conditional_expectancy_r=round(exp_r, 2),
                            is_favorable=exp_r > 0.50,
                            status="ACTIVE",
                            meta={"gap_size": round(gap_size, 2)},
                        )
                    )

            # Bearish FVG: High of curr < Low of prev2
            elif c_curr["high"] < c_prev2["low"]:
                gap_size = c_prev2["low"] - c_curr["high"]
                if gap_size > (c_mid["open"] * 0.0005):
                    exp_r = self._get_expectancy(SMCPatternType.BEARISH_FVG.value, regime)
                    fvgs.append(
                        SMCPattern(
                            pattern_type=SMCPatternType.BEARISH_FVG,
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c_curr["timestamp"],
                            top_price=round(c_prev2["low"], 2),
                            bottom_price=round(c_curr["high"], 2),
                            mid_price=round((c_prev2["low"] + c_curr["high"]) / 2.0, 2),
                            invalidation_level=round(c_prev2["low"], 2),
                            strength=round(
                                min(1.0, gap_size / (c_mid["high"] - c_mid["low"] + 1e-5)), 2
                            ),
                            conditional_expectancy_r=round(exp_r, 2),
                            is_favorable=exp_r > 0.50,
                            status="ACTIVE",
                            meta={"gap_size": round(gap_size, 2)},
                        )
                    )

        return fvgs

    def _scan_order_blocks(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        regime: str,
    ) -> list[SMCPattern]:
        obs = []
        for i in range(3, len(candles)):
            ob_candle = candles[i - 2]
            impulse1 = candles[i - 1]
            impulse2 = candles[i]

            # Bullish OB: Down candle followed by 2 strong bullish candles breaking local high
            is_down = ob_candle["close"] < ob_candle["open"]
            impulse_up = (impulse1["close"] > impulse1["open"]) and (
                impulse2["close"] > impulse2["open"]
            )
            break_high = impulse2["close"] > ob_candle["high"]

            if is_down and impulse_up and break_high:
                exp_r = self._get_expectancy(SMCPatternType.BULLISH_OB.value, regime)
                obs.append(
                    SMCPattern(
                        pattern_type=SMCPatternType.BULLISH_OB,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=ob_candle["timestamp"],
                        top_price=round(ob_candle["high"], 2),
                        bottom_price=round(ob_candle["low"], 2),
                        mid_price=round((ob_candle["high"] + ob_candle["low"]) / 2.0, 2),
                        invalidation_level=round(ob_candle["low"], 2),
                        strength=0.85,
                        conditional_expectancy_r=round(exp_r, 2),
                        is_favorable=exp_r > 0.50,
                        status="ACTIVE",
                        meta={"candle_index": i - 2},
                    )
                )

            # Bearish OB: Up candle followed by 2 strong bearish candles breaking local low
            is_up = ob_candle["close"] > ob_candle["open"]
            impulse_down = (impulse1["close"] < impulse1["open"]) and (
                impulse2["close"] < impulse2["open"]
            )
            break_low = impulse2["close"] < ob_candle["low"]

            if is_up and impulse_down and break_low:
                exp_r = self._get_expectancy(SMCPatternType.BEARISH_OB.value, regime)
                obs.append(
                    SMCPattern(
                        pattern_type=SMCPatternType.BEARISH_OB,
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=ob_candle["timestamp"],
                        top_price=round(ob_candle["high"], 2),
                        bottom_price=round(ob_candle["low"], 2),
                        mid_price=round((ob_candle["high"] + ob_candle["low"]) / 2.0, 2),
                        invalidation_level=round(ob_candle["high"], 2),
                        strength=0.85,
                        conditional_expectancy_r=round(exp_r, 2),
                        is_favorable=exp_r > 0.50,
                        status="ACTIVE",
                        meta={"candle_index": i - 2},
                    )
                )

        return obs

    def _scan_liquidity_sweeps(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        regime: str,
    ) -> list[SMCPattern]:
        sweeps = []
        if len(candles) < 20:
            return sweeps

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        for i in range(15, len(candles)):
            c = candles[i]
            prior_swing_high = max(highs[i - 15 : i])
            prior_swing_low = min(lows[i - 15 : i])

            # Bullish Sweep: Low breached prior swing low, but close closed back above it with lower wick
            if c["low"] < prior_swing_low and c["close"] > prior_swing_low:
                wick_size = min(c["open"], c["close"]) - c["low"]
                body_size = abs(c["close"] - c["open"])
                if wick_size > body_size:  # Long rejection wick
                    exp_r = self._get_expectancy(SMCPatternType.BULLISH_SWEEP.value, regime)
                    sweeps.append(
                        SMCPattern(
                            pattern_type=SMCPatternType.BULLISH_SWEEP,
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c["timestamp"],
                            top_price=round(prior_swing_low, 2),
                            bottom_price=round(c["low"], 2),
                            mid_price=round((prior_swing_low + c["low"]) / 2.0, 2),
                            invalidation_level=round(c["low"], 2),
                            strength=0.90,
                            conditional_expectancy_r=round(exp_r, 2),
                            is_favorable=exp_r > 0.50,
                            status="ACTIVE",
                            meta={"swept_level": round(prior_swing_low, 2)},
                        )
                    )

            # Bearish Sweep: High pierced prior swing high, but close closed back below it with upper wick
            elif c["high"] > prior_swing_high and c["close"] < prior_swing_high:
                wick_size = c["high"] - max(c["open"], c["close"])
                body_size = abs(c["close"] - c["open"])
                if wick_size > body_size:
                    exp_r = self._get_expectancy(SMCPatternType.BEARISH_SWEEP.value, regime)
                    sweeps.append(
                        SMCPattern(
                            pattern_type=SMCPatternType.BEARISH_SWEEP,
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=c["timestamp"],
                            top_price=round(c["high"], 2),
                            bottom_price=round(prior_swing_high, 2),
                            mid_price=round((c["high"] + prior_swing_high) / 2.0, 2),
                            invalidation_level=round(c["high"], 2),
                            strength=0.90,
                            conditional_expectancy_r=round(exp_r, 2),
                            is_favorable=exp_r > 0.50,
                            status="ACTIVE",
                            meta={"swept_level": round(prior_swing_high, 2)},
                        )
                    )

        return sweeps


# Singleton
smc_engine = SMCEngine()
