"""
core/arbitrage/basis_engine.py
==============================
Spot/Perpetual Basis Dislocation & Z-Score Anomaly Engine.

Core Principles:
- Computes basis = (F - S) / S in basis points.
- Tracks historical rolling mean, standard deviation, and Z-score.
- 3-sigma (|Z| >= 3.0) is strictly a CANDIDATE trigger, never an unhedged trading signal.
- Classifies market structure into Contango and Backwardation regimes.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Dict, List, Tuple

import numpy as np

from core.arbitrage.models import BasisMetrics, BasisRegime, Venue

logger = logging.getLogger("ai_quant_sentinel.arbitrage.basis_engine")


class BasisEngine:
    """Evaluates spot-perpetual price basis dispersion and statistical Z-score dislocations."""

    def __init__(
        self,
        window_size: int = 120,
        zscore_candidate_threshold: float = 3.0,
    ) -> None:
        self.window_size = window_size
        self.zscore_candidate_threshold = zscore_candidate_threshold
        # Key: (canonical_symbol, spot_venue, perp_venue) -> deque of basis_bps
        self._history: Dict[Tuple[str, Venue, Venue], deque[float]] = {}
        self._breach_start_time: Dict[Tuple[str, Venue, Venue], float] = {}

    def compute_basis(
        self,
        canonical_symbol: str,
        spot_venue: Venue,
        perp_venue: Venue,
        spot_price: float,
        perp_price: float,
    ) -> BasisMetrics:
        """Computes basis, rolling statistics, regime, and candidate trigger status."""
        now_ms = time.time() * 1000.0
        key = (canonical_symbol, spot_venue, perp_venue)

        if spot_price <= 0:
            raw_basis_bps = 0.0
        else:
            raw_basis_bps = ((perp_price - spot_price) / spot_price) * 10000.0

        # Append to rolling history
        if key not in self._history:
            self._history[key] = deque(maxlen=self.window_size)
        history = self._history[key]
        history.append(raw_basis_bps)

        # Rolling statistics
        arr = np.array(history, dtype=float)
        mean_bps = float(np.mean(arr))
        std_bps = float(np.std(arr)) if len(arr) >= 5 else 1.0

        if std_bps < 0.05:
            std_bps = 0.05  # Prevent division by zero on tightly clustered synthetic quotes

        zscore = (raw_basis_bps - mean_bps) / std_bps

        # Structural regime classification
        if zscore >= 2.5:
            regime = BasisRegime.CONTANGO_EXTREME
        elif zscore >= 0.5:
            regime = BasisRegime.NORMAL_CONTANGO
        elif zscore <= -2.5:
            regime = BasisRegime.BACKWARDATION_EXTREME
        elif zscore <= -0.5:
            regime = BasisRegime.NORMAL_BACKWARDATION
        else:
            regime = BasisRegime.NEUTRAL_BASIS

        candidate_trigger = abs(zscore) >= self.zscore_candidate_threshold

        # Duration outside threshold tracking
        if candidate_trigger:
            if key not in self._breach_start_time:
                self._breach_start_time[key] = now_ms
            duration_outside_ms = now_ms - self._breach_start_time[key]
        else:
            self._breach_start_time.pop(key, None)
            duration_outside_ms = 0.0

        return BasisMetrics(
            canonical_symbol=canonical_symbol,
            spot_venue=spot_venue,
            perp_venue=perp_venue,
            spot_price=spot_price,
            perp_price=perp_price,
            raw_basis_bps=raw_basis_bps,
            rolling_mean_bps=mean_bps,
            rolling_std_bps=std_bps,
            zscore=zscore,
            regime=regime,
            duration_outside_threshold_ms=duration_outside_ms,
            candidate_trigger=candidate_trigger,
        )

    def reset_history(self) -> None:
        """Clears rolling history for testing and state resets."""
        self._history.clear()
        self._breach_start_time.clear()


# Global singleton
basis_engine = BasisEngine()
