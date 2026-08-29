"""
Phase 3: Volatility Engine.
Calculates Average True Range (ATR), rolling historical ATR percentiles, realized volatility,
and classifies volatility into dynamic non-arbitrary regimes (LOW, NORMAL, HIGH, EXTREME).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from core.sky_intelligence.types import VolatilityRegime, VolatilityState

logger = logging.getLogger("sky_intelligence.volatility_engine")


class VolatilityEngine:
    """
    Empirical Volatility Engine with rolling quantile normalization.
    """

    def __init__(self, atr_period: int = 14, rolling_history: int = 100):
        self.atr_period = atr_period
        self.rolling_history = rolling_history

    def compute_volatility(
        self,
        candles: List[Dict[str, Any]],
    ) -> VolatilityState:
        """
        Computes ATR, rolling percentiles, realized volatility, and assigns VolatilityRegime.
        """
        n = len(candles)
        if n < 2:
            return VolatilityState(
                timestamp=0,
                atr=1.0,
                atr_percentile=0.5,
                realized_volatility=0.01,
                regime=VolatilityRegime.NORMAL_VOLATILITY,
                is_expanding=False,
                is_contracting=False,
            )

        # Compute True Range series
        tr_series: List[float] = []
        close_prices: List[float] = [float(c["close"]) for c in candles]
        for i in range(1, n):
            h = float(candles[i]["high"])
            l = float(candles[i]["low"])
            c_prev = close_prices[i - 1]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_series.append(tr)

        # 14-period Wilder / Simple ATR
        atr_window = tr_series[-self.atr_period:] if len(tr_series) >= self.atr_period else tr_series
        current_atr = float(np.mean(atr_window)) if atr_window else 1.0

        # Rolling ATR distribution for percentile computation
        atr_history: List[float] = []
        if len(tr_series) >= self.atr_period:
            for k in range(self.atr_period, len(tr_series) + 1):
                sub_tr = tr_series[k - self.atr_period : k]
                atr_history.append(float(np.mean(sub_tr)))
        else:
            atr_history = [current_atr]

        # Use recent rolling_history for empirical CDF
        recent_dist = atr_history[-self.rolling_history :]
        if len(recent_dist) > 1:
            atr_percentile = float(np.mean(np.array(recent_dist) <= current_atr))
        else:
            atr_percentile = 0.50

        # Realized Volatility: standard deviation of log returns annualized
        log_returns = []
        for i in range(1, len(close_prices)):
            if close_prices[i - 1] > 0:
                ret = np.log(close_prices[i] / close_prices[i - 1])
                log_returns.append(ret)

        realized_vol = float(np.std(log_returns[-self.atr_period :])) if len(log_returns) >= self.atr_period else 0.01

        # Classify regime based on rolling percentile
        if atr_percentile >= 0.85:
            regime = VolatilityRegime.EXTREME_VOLATILITY
        elif atr_percentile >= 0.65:
            regime = VolatilityRegime.HIGH_VOLATILITY
        elif atr_percentile <= 0.20:
            regime = VolatilityRegime.LOW_VOLATILITY
        else:
            regime = VolatilityRegime.NORMAL_VOLATILITY

        # Expansion / Contraction flags
        is_expanding = (
            len(atr_history) >= 3 and atr_history[-1] > atr_history[-2] > atr_history[-3]
        )
        is_contracting = (
            len(atr_history) >= 3 and atr_history[-1] < atr_history[-2] < atr_history[-3]
        )

        last_ts = int(candles[-1].get("timestamp", 0))

        return VolatilityState(
            timestamp=last_ts,
            atr=round(current_atr, 4),
            atr_percentile=round(atr_percentile, 4),
            realized_volatility=round(realized_vol, 6),
            regime=regime,
            is_expanding=is_expanding,
            is_contracting=is_contracting,
        )


# Global singleton instance
volatility_engine = VolatilityEngine()
