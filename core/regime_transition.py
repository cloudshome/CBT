"""
Regime Classification & Structural Phase Transition Detector.
Classifies macro and intraday regimes (TRENDING_BULL, TRENDING_BEAR, RANGING_CONSOLIDATION, VOLATILE_EXPANSION)
and pinpoints critical structural transitions (Squeeze Breakouts, Trend Exhaustion, Expansion).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.regime_transition")


class MarketRegime(StrEnum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING_CONSOLIDATION = "RANGING_CONSOLIDATION"
    VOLATILE_EXPANSION = "VOLATILE_EXPANSION"


class StructuralTransition(StrEnum):
    NONE = "NONE"
    RANGE_TO_EXPANSION = "RANGE -> VOLATILITY_EXPANSION -> TREND_FORMATION"
    TREND_EXHAUSTION_TO_RANGE = "TREND_EXHAUSTION -> RANGE_COMPRESSION"
    SQUEEZE_TO_BREAKOUT = "LOW_VOL_SQUEEZE -> HIGH_VOL_BREAKOUT"


@dataclass
class RegimeClassificationResult:
    current_regime: MarketRegime
    confidence: float  # [0.0, 1.0]
    active_transition: StructuralTransition
    trend_strength: float  # [-1.0, 1.0]
    volatility_state: str  # "COMPRESSED", "NORMAL", "EXPANDED", "EXTREME"
    adx_value: float
    atr_percentile: float
    bb_squeeze: bool
    summary: str


class RegimeTransitionDetector:
    """
    Classifies underlying dynamic market state distributions and detects early structural transitions.
    """

    def classify_regime(
        self,
        candles: list[dict[str, Any]],
        lookback: int = 50,
    ) -> RegimeClassificationResult:
        """
        Calculates ADX, ATR, Bollinger Band bandwidth, and EMA slopes to determine market regime.
        """
        if len(candles) < 20:
            return RegimeClassificationResult(
                current_regime=MarketRegime.RANGING_CONSOLIDATION,
                confidence=0.50,
                active_transition=StructuralTransition.NONE,
                trend_strength=0.0,
                volatility_state="NORMAL",
                adx_value=15.0,
                atr_percentile=0.50,
                bb_squeeze=False,
                summary="Insufficient data for full regime estimation; defaulting to RANGING_CONSOLIDATION.",
            )

        highs = np.array([c["high"] for c in candles[-lookback:]], dtype=np.float64)
        lows = np.array([c["low"] for c in candles[-lookback:]], dtype=np.float64)
        closes = np.array([c["close"] for c in candles[-lookback:]], dtype=np.float64)

        # 1. Trend Direction & Slope via EMAs
        ema9 = float(np.mean(closes[-9:]))
        ema21 = float(np.mean(closes[-21:])) if len(closes) >= 21 else ema9
        ema50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ema21
        trend_slope = (ema9 - ema50) / ema50 * 100.0
        norm_trend = float(np.clip(np.tanh(trend_slope * 2.0), -1.0, 1.0))

        # 2. ADX Approximation (Directional Movement)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])),
        )
        atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        p_di = (
            float(np.mean(plus_dm[-14:])) / (atr14 + 1e-5) * 100.0 if len(plus_dm) >= 14 else 20.0
        )
        m_di = (
            float(np.mean(minus_dm[-14:])) / (atr14 + 1e-5) * 100.0 if len(minus_dm) >= 14 else 20.0
        )
        dx = abs(p_di - m_di) / (p_di + m_di + 1e-5) * 100.0
        adx = float(np.clip(dx, 0.0, 100.0))

        # 3. Bollinger Band Squeeze & Volatility
        sma20 = np.mean(closes[-20:])
        std20 = np.std(closes[-20:])
        bb_width = (2.0 * std20) / (sma20 + 1e-5)
        bb_squeeze = bool(bb_width < 0.018)

        # ATR Percentile Rank
        rolling_atr = [np.mean(tr[max(0, k - 14) : k + 1]) for k in range(len(tr))]
        atr_rank = float(np.mean(np.array(rolling_atr) <= atr14))

        vol_state = (
            "EXTREME"
            if atr_rank > 0.85
            else (
                "EXPANDED" if atr_rank > 0.65 else ("COMPRESSED" if atr_rank < 0.25 else "NORMAL")
            )
        )

        # 4. Regime Determination
        if atr_rank > 0.80 and adx < 22:
            regime = MarketRegime.VOLATILE_EXPANSION
            confidence = 0.82
        elif adx >= 25.0:
            if ema9 > ema21 > ema50 or norm_trend > 0.35:
                regime = MarketRegime.TRENDING_BULL
                confidence = float(np.clip(0.60 + (adx / 200.0), 0.60, 0.95))
            elif ema9 < ema21 < ema50 or norm_trend < -0.35:
                regime = MarketRegime.TRENDING_BEAR
                confidence = float(np.clip(0.60 + (adx / 200.0), 0.60, 0.95))
            else:
                regime = MarketRegime.RANGING_CONSOLIDATION
                confidence = 0.70
        else:
            regime = MarketRegime.RANGING_CONSOLIDATION
            confidence = 0.78

        # 5. Critical Structural Transitions
        transition = StructuralTransition.NONE
        if bb_squeeze and atr_rank < 0.25 and abs(norm_trend) < 0.15:
            transition = StructuralTransition.SQUEEZE_TO_BREAKOUT
        elif (
            regime in [MarketRegime.TRENDING_BULL, MarketRegime.TRENDING_BEAR]
            and adx < 20
            and atr_rank < 0.40
        ):
            transition = StructuralTransition.TREND_EXHAUSTION_TO_RANGE
        elif (
            regime == MarketRegime.RANGING_CONSOLIDATION
            and atr_rank > 0.60
            and (norm_trend > 0.4 or norm_trend < -0.4)
        ):
            transition = StructuralTransition.RANGE_TO_EXPANSION

        summary = (
            f"Active Regime: {regime.value} (Confidence: {confidence * 100:.0f}%, ADX: {adx:.1f}). "
            f"Volatility State: {vol_state} (ATR Pct: {atr_rank * 100:.0f}%). "
            f"Transition: {transition.value}."
        )

        return RegimeClassificationResult(
            current_regime=regime,
            confidence=round(confidence, 3),
            active_transition=transition,
            trend_strength=round(norm_trend, 3),
            volatility_state=vol_state,
            adx_value=round(adx, 2),
            atr_percentile=round(atr_rank, 3),
            bb_squeeze=bb_squeeze,
            summary=summary,
        )

    def evaluate_market_state(
        self,
        symbol: str,
        prices: list[float],
        volumes: list[float] | None = None,
    ) -> dict[str, Any]:
        """Backward-compatible market state evaluation from price and volume sequences."""
        if not prices:
            return {"regime": MarketRegime.RANGING_CONSOLIDATION.value, "confidence": 0.5}
        candles = [
            {
                "open": p,
                "high": p,
                "low": p,
                "close": p,
                "volume": volumes[i] if volumes and i < len(volumes) else 1.0,
            }
            for i, p in enumerate(prices)
        ]
        res = self.classify_regime(candles)
        return {
            "regime": res.current_regime.value,
            "confidence": res.confidence,
            "active_transition": res.active_transition.value,
            "summary": res.summary,
        }


# Singleton
regime_transition_detector = RegimeTransitionDetector()
