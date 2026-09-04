"""
Vectorized Candlestick Pattern Engine.
Identifies 12 classic & institutional price action formations with
structured narrative absorption explanations and precise structural invalidation levels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.pattern_engine")


@dataclass
class CandlestickPatternResult:
    pattern_name: str
    bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    timestamp: int
    reliability: float  # [0.0, 1.0]
    invalidation_price: float
    target_price: float
    narrative_explanation: str
    candle_index: int


class PatternEngine:
    """Vectorized detector for 12 candlestick formations."""

    def scan_patterns(
        self,
        candles: list[dict[str, Any]],
        symbol: str = "BTC/USDT",
    ) -> list[CandlestickPatternResult]:
        """
        Scans candlestick array and returns detected formations with narrative explanations.
        """
        if len(candles) < 3:
            return []

        results: list[CandlestickPatternResult] = []

        opens = np.array([c["open"] for c in candles], dtype=np.float64)
        highs = np.array([c["high"] for c in candles], dtype=np.float64)
        lows = np.array([c["low"] for c in candles], dtype=np.float64)
        closes = np.array([c["close"] for c in candles], dtype=np.float64)
        timestamps = [c["timestamp"] for c in candles]

        n = len(candles)
        bodies = np.abs(closes - opens)
        ranges = np.maximum(0.0001, highs - lows)
        upper_wicks = highs - np.maximum(opens, closes)
        lower_wicks = np.minimum(opens, closes) - lows

        for i in range(2, n):
            c_open, c_high, c_low, c_close = opens[i], highs[i], lows[i], closes[i]
            body = bodies[i]
            rng = ranges[i]
            u_wick = upper_wicks[i]
            l_wick = lower_wicks[i]
            ts = timestamps[i]

            prev_open, prev_close = opens[i - 1], closes[i - 1]
            prev_body = bodies[i - 1]

            # 1. Hammer (Bullish)
            if (l_wick >= 2.0 * body) and (u_wick <= 0.2 * body) and (body > 0.1 * rng):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Hammer",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.74,
                        invalidation_price=round(c_low, 2),
                        target_price=round(c_close + (c_close - c_low) * 2.0, 2),
                        narrative_explanation=f"Sellers attempted sharp downward push to {c_low:.2f}, but aggressive buyer absorption created lower rejection wick ({l_wick:.2f}pts).",
                        candle_index=i,
                    )
                )

            # 2. Inverted Hammer (Bullish Reversal)
            elif (
                (u_wick >= 2.0 * body) and (l_wick <= 0.2 * body) and (closes[i - 1] < opens[i - 1])
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Inverted Hammer",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.68,
                        invalidation_price=round(c_low, 2),
                        target_price=round(c_high + (c_high - c_low), 2),
                        narrative_explanation="Buyer probe above downtrend structure testing overhead liquidity before sellers consolidated.",
                        candle_index=i,
                    )
                )

            # 3. Bullish Engulfing
            elif (
                (prev_close < prev_open)
                and (c_close > c_open)
                and (c_open <= prev_close)
                and (c_close >= prev_open)
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bullish Engulfing",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.79,
                        invalidation_price=round(min(c_low, lows[i - 1]), 2),
                        target_price=round(c_close + body * 1.8, 2),
                        narrative_explanation=f"Bullish expansion ({body:.2f}pts) fully engulfs prior bear candle body ({prev_body:.2f}pts), proving aggressive net institutional buy pressure.",
                        candle_index=i,
                    )
                )

            # 4. Bearish Engulfing
            elif (
                (prev_close > prev_open)
                and (c_close < c_open)
                and (c_open >= prev_close)
                and (c_close <= prev_open)
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bearish Engulfing",
                        bias="BEARISH",
                        timestamp=ts,
                        reliability=0.81,
                        invalidation_price=round(max(c_high, highs[i - 1]), 2),
                        target_price=round(c_close - body * 1.8, 2),
                        narrative_explanation=f"Sellers seized complete liquidity dominance, completely engulfing prior bull bar from open {c_open:.2f} down to {c_close:.2f}.",
                        candle_index=i,
                    )
                )

            # 5. Morning Star (3-Bar Bullish Reversal)
            elif (
                (opens[i - 2] > closes[i - 2])
                and (bodies[i - 1] < 0.3 * bodies[i - 2])
                and (c_close > c_open)
                and (c_close > (opens[i - 2] + closes[i - 2]) / 2.0)
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Morning Star",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.83,
                        invalidation_price=round(min(lows[i - 2 : i + 1]), 2),
                        target_price=round(c_close + (c_close - lows[i - 1]) * 1.5, 2),
                        narrative_explanation="Classic 3-candle institutional exhaustion sequence: sell displacement -> micro-indecision star -> strong reversal close.",
                        candle_index=i,
                    )
                )

            # 6. Evening Star (3-Bar Bearish Reversal)
            elif (
                (closes[i - 2] > opens[i - 2])
                and (bodies[i - 1] < 0.3 * bodies[i - 2])
                and (c_close < c_open)
                and (c_close < (opens[i - 2] + closes[i - 2]) / 2.0)
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Evening Star",
                        bias="BEARISH",
                        timestamp=ts,
                        reliability=0.84,
                        invalidation_price=round(max(highs[i - 2 : i + 1]), 2),
                        target_price=round(c_close - (highs[i - 1] - c_close) * 1.5, 2),
                        narrative_explanation="Institutional topping sequence: buy impulse -> liquidity distribution star -> aggressive bearish thrust.",
                        candle_index=i,
                    )
                )

            # 7. Pinbar (Bullish Pinbar)
            elif (l_wick >= 0.65 * rng) and (body <= 0.25 * rng):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bullish Pinbar",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.76,
                        invalidation_price=round(c_low, 2),
                        target_price=round(c_close + l_wick, 2),
                        narrative_explanation=f"Extreme lower wick rejection ({l_wick:.2f}pts, {l_wick / rng * 100:.0f}% of range) reveals hidden institutional limit bid absorption.",
                        candle_index=i,
                    )
                )

            # 8. Pinbar (Bearish Pinbar)
            elif (u_wick >= 0.65 * rng) and (body <= 0.25 * rng):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bearish Pinbar",
                        bias="BEARISH",
                        timestamp=ts,
                        reliability=0.77,
                        invalidation_price=round(c_high, 2),
                        target_price=round(c_close - u_wick, 2),
                        narrative_explanation=f"Extreme upper wick rejection ({u_wick:.2f}pts, {u_wick / rng * 100:.0f}% of range) reveals aggressive institutional sell limit wall.",
                        candle_index=i,
                    )
                )

            # 9. Bullish Marubozu (Clean Impulse)
            elif (
                (c_close > c_open)
                and (body >= 0.90 * rng)
                and (rng > 1.5 * np.mean(ranges[max(0, i - 10) : i]))
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bullish Marubozu",
                        bias="BULLISH",
                        timestamp=ts,
                        reliability=0.75,
                        invalidation_price=round(c_open, 2),
                        target_price=round(c_close + body, 2),
                        narrative_explanation=f"One-way buying displacement without upper/lower wick concessions ({body:.2f}pts). Strong momentum expansion.",
                        candle_index=i,
                    )
                )

            # 10. Bearish Marubozu
            elif (
                (c_close < c_open)
                and (body >= 0.90 * rng)
                and (rng > 1.5 * np.mean(ranges[max(0, i - 10) : i]))
            ):
                results.append(
                    CandlestickPatternResult(
                        pattern_name="Bearish Marubozu",
                        bias="BEARISH",
                        timestamp=ts,
                        reliability=0.76,
                        invalidation_price=round(c_open, 2),
                        target_price=round(c_close - body, 2),
                        narrative_explanation=f"One-way selling cascade without relief wicks ({body:.2f}pts). Heavy aggressive market selling.",
                        candle_index=i,
                    )
                )

            # 11. Doji (Indecision / Compression)
            elif body <= (0.05 * rng):
                doji_type = (
                    "Dragonfly Doji"
                    if l_wick > (0.6 * rng)
                    else ("Gravestone Doji" if u_wick > (0.6 * rng) else "Standard Doji")
                )
                results.append(
                    CandlestickPatternResult(
                        pattern_name=doji_type,
                        bias="NEUTRAL",
                        timestamp=ts,
                        reliability=0.60,
                        invalidation_price=round(
                            c_low if doji_type == "Dragonfly Doji" else c_high, 2
                        ),
                        target_price=round(c_close, 2),
                        narrative_explanation=f"{doji_type} detected: complete equilibrium between buyers and sellers with micro-body ({body:.2f}pts). Volatility compression.",
                        candle_index=i,
                    )
                )

            # 12. Three White Soldiers / Three Black Crows
            elif i >= 3:
                # 3 White Soldiers
                c1, c2, c3 = (
                    opens[i - 2] < closes[i - 2],
                    opens[i - 1] < closes[i - 1],
                    c_open < c_close,
                )
                if c1 and c2 and c3 and (closes[i] > closes[i - 1] > closes[i - 2]):
                    results.append(
                        CandlestickPatternResult(
                            pattern_name="Three White Soldiers",
                            bias="BULLISH",
                            timestamp=ts,
                            reliability=0.82,
                            invalidation_price=round(lows[i - 2], 2),
                            target_price=round(c_close + bodies[i] * 2.0, 2),
                            narrative_explanation="Three consecutive strong bullish candles establishing clear sustained directional expansion.",
                            candle_index=i,
                        )
                    )
                # 3 Black Crows
                b1, b2, b3 = (
                    opens[i - 2] > closes[i - 2],
                    opens[i - 1] > closes[i - 1],
                    c_open > c_close,
                )
                if b1 and b2 and b3 and (closes[i] < closes[i - 1] < closes[i - 2]):
                    results.append(
                        CandlestickPatternResult(
                            pattern_name="Three Black Crows",
                            bias="BEARISH",
                            timestamp=ts,
                            reliability=0.83,
                            invalidation_price=round(highs[i - 2], 2),
                            target_price=round(c_close - bodies[i] * 2.0, 2),
                            narrative_explanation="Three consecutive aggressive bearish candles confirming structural breakdown.",
                            candle_index=i,
                        )
                    )

        return results


# Singleton
pattern_engine = PatternEngine()
