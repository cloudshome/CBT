"""
core/research/grade_e2/volatility_gate.py
========================================
Grade-E2 Volatility Regime Gate.

Monitors rolling Parkinson volatility to detect volatility expansion regimes.
Suppresses passive limit order placement during explosive breakout regimes
where limit orders act as free options to aggressive market participants.
"""

from __future__ import annotations

import logging
from collections import deque

import numpy as np

from core.research.grade_e1.contracts import MarketSnapshot
from core.research.grade_e2.contracts import VolatilityRegime

logger = logging.getLogger("sky.grade_e2.volatility_gate")


class GradeE2VolatilityGate:
    """Detects microstructure volatility regimes using causal historical baselines."""

    def __init__(self, window_bars: int = 30, percentile_cutoff: float = 85.0):
        self.window_bars = window_bars
        self.percentile_cutoff = percentile_cutoff
        self._vol_history: deque[float] = deque(maxlen=window_bars)

    def reset(self) -> None:
        self._vol_history.clear()

    def update(self, snapshot: MarketSnapshot) -> tuple[float, VolatilityRegime]:
        """
        Ingests current snapshot volatility, updates historical distribution,
        and classifies current volatility regime.
        """
        vol = snapshot.volatility_bps
        self._vol_history.append(vol)

        if len(self._vol_history) < 10:
            return vol, VolatilityRegime.NORMAL

        arr = np.array(self._vol_history)
        p85 = float(np.percentile(arr, self.percentile_cutoff))
        median_vol = float(np.median(arr))

        if vol >= 2.2 * median_vol:
            regime = VolatilityRegime.EXPLOSIVE
        elif vol >= p85:
            regime = VolatilityRegime.HIGH_VOLATILITY
        elif vol <= 0.6 * median_vol:
            regime = VolatilityRegime.CALM
        else:
            regime = VolatilityRegime.NORMAL

        return round(vol, 2), regime

    def is_order_safe(
        self, snapshot: MarketSnapshot
    ) -> tuple[bool, float, VolatilityRegime, str | None]:
        """Convenience method checking whether volatility permits passive quoting."""
        vol, regime = self.update(snapshot)
        if regime in (VolatilityRegime.HIGH_VOLATILITY, VolatilityRegime.EXPLOSIVE):
            return (
                False,
                vol,
                regime,
                f"VOLATILITY_EXPANSION_REGIME ({regime.value}, vol={vol:.1f} bps)",
            )
        return True, vol, regime, None
