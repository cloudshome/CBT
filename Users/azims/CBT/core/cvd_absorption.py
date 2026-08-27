"""
Orderflow Cumulative Volume Delta (CVD) & Hidden Institutional Absorption Engine.
Computes tick-by-tick / candle-by-candle CVD: CVD_t = CVD_{t-1} + (V_buy - V_sell).
Detects Bullish & Bearish Hidden Absorption where aggressive market orders are absorbed by institutional limit books.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.cvd_absorption")


@dataclass
class CVDAnalysisResult:
    symbol: str
    timestamp: int
    current_cvd: float
    cvd_delta: float                    # [-1.0, 1.0] normalized velocity
    absorption_detected: bool
    absorption_type: str                # "BULLISH_ABSORPTION", "BEARISH_ABSORPTION", "NONE"
    absorption_score: float             # [0.0, 1.0] intensity
    volume_ratio: float                 # current vol / 20-period mean
    divergence_score: float             # [-1.0, 1.0]
    narrative: str


class CVDAbsorptionEngine:
    """
    Analyzes orderflow delta and identifies passive institutional absorption.
    """

    def analyze_orderflow(
        self,
        candles: List[Dict[str, Any]],
        symbol: str = "BTC/USDT",
    ) -> CVDAnalysisResult:
        """
        Computes CVD series and checks for price vs. CVD divergence with elevated volume.
        """
        if len(candles) < 10:
            return CVDAnalysisResult(
                symbol=symbol,
                timestamp=candles[-1]["timestamp"] if candles else 0,
                current_cvd=0.0,
                cvd_delta=0.0,
                absorption_detected=False,
                absorption_type="NONE",
                absorption_score=0.0,
                volume_ratio=1.0,
                divergence_score=0.0,
                narrative="Insufficient orderflow history.",
            )

        n = len(candles)
        closes = np.array([c["close"] for c in candles], dtype=np.float64)
        volumes = np.array([c.get("volume", 100.0) for c in candles], dtype=np.float64)
        opens = np.array([c["open"] for c in candles], dtype=np.float64)
        highs = np.array([c["high"] for c in candles], dtype=np.float64)
        lows = np.array([c["low"] for c in candles], dtype=np.float64)

        # Estimate buy/sell volume split via candle intra-bar footprint model
        # Buy Vol = Vol * (Close - Low) / (High - Low + eps)
        # Sell Vol = Vol * (High - Close) / (High - Low + eps)
        span = np.maximum(0.0001, highs - lows)
        buy_ratios = (closes - lows) / span
        buy_vols = volumes * buy_ratios
        sell_vols = volumes * (1.0 - buy_ratios)
        deltas = buy_vols - sell_vols

        cvd_series = np.cumsum(deltas)
        current_cvd = float(cvd_series[-1])

        # CVD Delta velocity over last 5 bars normalized [-1.0, 1.0]
        recent_delta = float(np.sum(deltas[-5:]))
        recent_vol = float(np.sum(volumes[-5:])) + 1e-5
        cvd_delta_norm = float(np.clip(recent_delta / recent_vol, -1.0, 1.0))

        # Rolling 20-period volume average
        mean_vol = float(np.mean(volumes[-20:])) if n >= 20 else float(np.mean(volumes))
        vol_ratio = float(volumes[-1] / (mean_vol + 1e-5))

        # Check Absorption:
        # Bullish: Price Lower Lows (last 5 vs prior 5) but CVD Higher Lows + Vol >= 1.8x
        price_p5_low = np.min(lows[-10:-5]) if n >= 10 else lows[0]
        price_curr_low = np.min(lows[-5:])
        cvd_p5_low = np.min(cvd_series[-10:-5]) if n >= 10 else cvd_series[0]
        cvd_curr_low = np.min(cvd_series[-5:])

        price_p5_high = np.max(highs[-10:-5]) if n >= 10 else highs[0]
        price_curr_high = np.max(highs[-5:])
        cvd_p5_high = np.max(cvd_series[-10:-5]) if n >= 10 else cvd_series[0]
        cvd_curr_high = np.max(cvd_series[-5:])

        is_bull_absorp = (price_curr_low < price_p5_low) and (cvd_curr_low >= cvd_p5_low) and (vol_ratio >= 1.5)
        is_bear_absorp = (price_curr_high > price_p5_high) and (cvd_curr_high <= cvd_p5_high) and (vol_ratio >= 1.5)

        absorption_type = "NONE"
        absorption_score = 0.0
        divergence_score = 0.0

        if is_bull_absorp:
            absorption_type = "BULLISH_ABSORPTION"
            absorption_score = float(np.clip(0.60 + (vol_ratio - 1.5) * 0.2, 0.60, 0.95))
            divergence_score = 0.85
            narrative = (
                f"Bullish Hidden Absorption detected on {symbol}: Price made lower low ({price_curr_low:.2f} < {price_p5_low:.2f}) "
                f"while CVD held higher low ({cvd_curr_low:.0f} >= {cvd_p5_low:.0f}) with {vol_ratio:.1f}x volume. "
                "Aggressive market sellers being absorbed by institutional limit bids."
            )
        elif is_bear_absorp:
            absorption_type = "BEARISH_ABSORPTION"
            absorption_score = float(np.clip(0.60 + (vol_ratio - 1.5) * 0.2, 0.60, 0.95))
            divergence_score = -0.85
            narrative = (
                f"Bearish Hidden Absorption detected on {symbol}: Price pushed higher high ({price_curr_high:.2f} > {price_p5_high:.2f}) "
                f"while CVD failed to make higher high with {vol_ratio:.1f}x volume. "
                "Aggressive retail market buys being filled into passive institutional supply."
            )
        else:
            narrative = f"CVD neutral. Current Delta: {recent_delta:+.1f} ({cvd_delta_norm:+.2f} norm), Volume Ratio: {vol_ratio:.2f}x."

        return CVDAnalysisResult(
            symbol=symbol,
            timestamp=candles[-1]["timestamp"],
            current_cvd=round(current_cvd, 2),
            cvd_delta=round(cvd_delta_norm, 3),
            absorption_detected=is_bull_absorp or is_bear_absorp,
            absorption_type=absorption_type,
            absorption_score=round(absorption_score, 3),
            volume_ratio=round(vol_ratio, 2),
            divergence_score=round(divergence_score, 2),
            narrative=narrative,
        )


# Singleton
cvd_absorption_engine = CVDAbsorptionEngine()
