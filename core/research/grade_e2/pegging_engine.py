"""
core/research/grade_e2/pegging_engine.py
=======================================
Grade-E2 Adaptive Depth Offset & Pegging Engine.

Dynamically scales passive order placement depth relative to market volatility and spread,
mitigating the adverse selection penalty while maintaining viable fill rates.
"""

from __future__ import annotations

import logging

from core.research.grade_e1.contracts import (
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
)
from core.research.grade_e2.contracts import PeggingMode, VolatilityRegime

logger = logging.getLogger("sky.grade_e2.pegging_engine")


class GradeE2PeggingEngine:
    """Calculates volatility-adaptive limit prices and handles dynamic pegging logic."""

    def __init__(
        self,
        mode: PeggingMode = PeggingMode.VOLATILITY_SCALED,
        vol_multiplier: float = 0.08,
        min_offset_bps: float = 1.0,
    ):
        self.mode = mode
        self.vol_multiplier = vol_multiplier
        self.min_offset_bps = min_offset_bps

    def compute_adaptive_offset_bps(
        self,
        snapshot: MarketSnapshot,
        regime: VolatilityRegime,
    ) -> float:
        """
        Computes the target distance (in basis points) from current mid-price
        at which to quote passive limit orders.
        """
        half_spread = snapshot.spread_bps / 2.0

        if self.mode == PeggingMode.STATIC_HALF_SPREAD:
            return max(self.min_offset_bps, half_spread)

        # Volatility-scaled offset
        vol_offset = snapshot.volatility_bps * self.vol_multiplier

        if regime == VolatilityRegime.CALM:
            # Tighter offset in calm markets to maximize fill rates
            offset = max(self.min_offset_bps, min(half_spread, vol_offset))
        else:
            # Widen offset in normal/elevated volatility to buffer against adverse selection
            offset = max(self.min_offset_bps, half_spread + vol_offset)

        return round(offset, 2)

    def calculate_limit_price(
        self,
        side: OrderSide,
        snapshot: MarketSnapshot,
        regime: VolatilityRegime,
    ) -> float:
        """Calculates exact limit price incorporating adaptive depth offset."""
        offset_bps = self.compute_adaptive_offset_bps(snapshot, regime)
        price_offset = snapshot.close * (offset_bps / 10000.0)

        if side == OrderSide.BUY:
            limit_p = snapshot.close - price_offset
        else:
            limit_p = snapshot.close + price_offset

        return round(limit_p, 2)

    def should_repeg_order(
        self,
        order: HypotheticalOrder,
        snapshot: MarketSnapshot,
        drift_tolerance_bps: float = 10.0,
    ) -> bool:
        """
        Determines whether the market price has drifted too far from the order's limit price,
        requiring a cancel-and-replace action.
        """
        if order.status.value not in ("PENDING_QUEUE", "PARTIALLY_FILLED"):
            return False

        drift_bps = abs((snapshot.close - order.limit_price) / order.limit_price) * 10000.0
        return drift_bps > drift_tolerance_bps
