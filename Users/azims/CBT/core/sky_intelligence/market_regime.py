"""
Phase 12: Market Regime Engine.
Classifies market environment into mathematically measurable regimes:
TRENDING_BULL, TRENDING_BEAR, RANGING_CONSOLIDATION, VOLATILE_EXPANSION, COMPRESSION_SQUEEZE, MEAN_REVERTING, UNSTABLE.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from core.sky_intelligence.types import (
    MarketRegimeState,
    MarketRegimeType,
    VolatilityRegime,
    VolatilityState,
)

logger = logging.getLogger("sky_intelligence.market_regime")


class MarketRegimeEngine:
    """
    Measurable Multi-Factor Market Regime Classifier.
    """

    def classify_regime(
        self,
        candles: List[Dict[str, Any]],
        volatility_state: VolatilityState,
    ) -> MarketRegimeState:
        """
        Classifies regime using ADX, EMA momentum alignment, ATR percentile, and Bollinger bandwidth.
        """
        n = len(candles)
        if n < 30:
            return MarketRegimeState(
                timestamp=0,
                regime_type=MarketRegimeType.RANGING_CONSOLIDATION,
                confidence=0.50,
                trend_strength_adx=15.0,
                volatility_state=volatility_state.regime,
                is_mean_reverting=True,
                key_characteristics=["Insufficient historical bars for full regime determination"],
            )

        closes = np.array([float(c["close"]) for c in candles], dtype=np.float64)
        highs = np.array([float(c["high"]) for c in candles], dtype=np.float64)
        lows = np.array([float(c["low"]) for c in candles], dtype=np.float64)

        # 1. Simple Directional Movement / ADX approximation (14-period)
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr_arr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])),
        )
        safe_tr = np.maximum(tr_arr[-14:], 0.0001)

        plus_di = 100.0 * (np.sum(plus_dm[-14:]) / np.sum(safe_tr))
        minus_di = 100.0 * (np.sum(minus_dm[-14:]) / np.sum(safe_tr))
        di_sum = max(plus_di + minus_di, 0.0001)
        dx = 100.0 * (abs(plus_di - minus_di) / di_sum)
        adx = float(dx)

        # 2. Moving Average Slopes (20 vs 50)
        sma20 = float(np.mean(closes[-20:]))
        sma50 = float(np.mean(closes[-50:])) if n >= 50 else sma20
        curr_price = float(closes[-1])

        # 3. Bollinger Bandwidth for Squeeze detection
        bb_std = float(np.std(closes[-20:]))
        bb_width_pct = (2.0 * bb_std) / max(sma20, 1.0)

        chars: List[str] = []

        # Decision Tree logic grounded in quantifiable metrics
        if volatility_state.regime == VolatilityRegime.EXTREME_VOLATILITY:
            regime = MarketRegimeType.VOLATILE_EXPANSION
            confidence = 0.85
            chars.append(f"Extreme Volatility (ATR Percentile {volatility_state.atr_percentile * 100:.1f}%)")
            is_mean_rev = False

        elif bb_width_pct <= 0.008 and volatility_state.regime == VolatilityRegime.LOW_VOLATILITY:
            regime = MarketRegimeType.COMPRESSION_SQUEEZE
            confidence = 0.80
            chars.append("Volatility Squeeze (BB width compressed, Low ATR)")
            is_mean_rev = True

        elif adx >= 25.0 and curr_price > sma20 >= sma50 and plus_di > minus_di:
            regime = MarketRegimeType.TRENDING_BULL
            confidence = min(0.95, 0.60 + (adx / 100.0))
            chars.append(f"Bullish Trend (ADX={adx:.1f}, Price > SMA20 > SMA50)")
            is_mean_rev = False

        elif adx >= 25.0 and curr_price < sma20 <= sma50 and minus_di > plus_di:
            regime = MarketRegimeType.TRENDING_BEAR
            confidence = min(0.95, 0.60 + (adx / 100.0))
            chars.append(f"Bearish Trend (ADX={adx:.1f}, Price < SMA20 < SMA50)")
            is_mean_rev = False

        elif abs(curr_price - sma20) / sma20 > 0.025:
            regime = MarketRegimeType.MEAN_REVERTING
            confidence = 0.72
            chars.append(f"Extended Deviation from Mean ({((curr_price - sma20)/sma20)*100:+.2f}%)")
            is_mean_rev = True

        else:
            regime = MarketRegimeType.RANGING_CONSOLIDATION
            confidence = 0.75
            chars.append(f"Range Consolidation (ADX={adx:.1f} < 25, Oscillating around mean)")
            is_mean_rev = True

        last_ts = int(candles[-1].get("timestamp", 0))

        return MarketRegimeState(
            timestamp=last_ts,
            regime_type=regime,
            confidence=round(confidence, 2),
            trend_strength_adx=round(adx, 1),
            volatility_state=volatility_state.regime,
            is_mean_reverting=is_mean_rev,
            key_characteristics=chars,
        )


# Global singleton instance
market_regime_engine = MarketRegimeEngine()
