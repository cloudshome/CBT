"""
core/research/grade_e2/toxicity_filter.py
=========================================
Grade-E2 Volume-Synchronized Probability of Toxicity (VPIN) Proxy.

Estimates directional flow toxicity from candle volume asymmetry and price displacement.
Identifies toxic regimes where passive maker limit orders are susceptible to the Winner's Curse.
"""

from __future__ import annotations

import logging
from collections import deque

import numpy as np

from core.research.grade_e1.contracts import MarketSnapshot
from core.research.grade_e2.contracts import ToxicityState

logger = logging.getLogger("sky.grade_e2.toxicity_filter")


class GradeE2ToxicityFilter:
    """Estimates rolling order flow toxicity (VPIN proxy) on causal candle feeds."""

    def __init__(self, window_bars: int = 12, toxicity_threshold: float = 0.55):
        self.window_bars = window_bars
        self.toxicity_threshold = toxicity_threshold
        self._buy_vols: deque[float] = deque(maxlen=window_bars)
        self._sell_vols: deque[float] = deque(maxlen=window_bars)
        self._total_vols: deque[float] = deque(maxlen=window_bars)

    def reset(self) -> None:
        self._buy_vols.clear()
        self._sell_vols.clear()
        self._total_vols.clear()

    def update(self, snapshot: MarketSnapshot) -> tuple[float, ToxicityState]:
        """
        Updates the causal rolling VPIN proxy with the latest bar.
        Returns: (vpin_score, toxicity_state)
        """
        bar_range = max(1e-8, snapshot.high - snapshot.low)
        delta_p = snapshot.close - snapshot.open
        displacement_ratio = np.clip(delta_p / bar_range, -1.0, 1.0)

        # Estimate buy/sell volume allocation
        buy_frac = 0.5 + (0.5 * displacement_ratio)
        sell_frac = 1.0 - buy_frac

        v_buy = snapshot.volume * buy_frac
        v_sell = snapshot.volume * sell_frac

        self._buy_vols.append(v_buy)
        self._sell_vols.append(v_sell)
        self._total_vols.append(snapshot.volume)

        if len(self._total_vols) < 3:
            return 0.30, ToxicityState.NORMAL

        sum_imbalance = sum(
            abs(b - s) for b, s in zip(self._buy_vols, self._sell_vols, strict=True)
        )
        sum_total_vol = max(1e-8, sum(self._total_vols))

        vpin = float(sum_imbalance / sum_total_vol)

        if vpin >= self.toxicity_threshold:
            state = ToxicityState.HIGH_TOXICITY
        elif vpin <= 0.25:
            state = ToxicityState.LOW
        else:
            state = ToxicityState.NORMAL

        return round(vpin, 4), state

    def is_order_safe(self, snapshot: MarketSnapshot) -> tuple[bool, float, str | None]:
        """Convenience method checking whether market conditions permit passive quoting."""
        vpin, state = self.update(snapshot)
        if state == ToxicityState.HIGH_TOXICITY:
            return False, vpin, f"HIGH_TOXICITY_FLOW (VPIN={vpin:.2f} >= {self.toxicity_threshold})"
        return True, vpin, None
