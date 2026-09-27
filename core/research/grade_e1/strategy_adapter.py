"""
core/research/grade_e1/strategy_adapter.py
=========================================
Grade-E1 Strategy Signal Adapter.

Converts quantitative strategy signals (Kronos forecasts, SMC market structure,
or momentum/mean-reversion triggers) into passive limit order placement requests.
"""

from __future__ import annotations

import logging

from core.research.grade_e1.contracts import (
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
)
from core.research.grade_e1.hypothetical_order import HypotheticalOrderManager

logger = logging.getLogger("sky.grade_e1.strategy_adapter")


class GradeE1StrategyAdapter:
    """Bridges trading signals into passive limit orders without mutating strategy logic."""

    def __init__(
        self,
        symbol: str,
        half_spread_fraction: float = 0.5,
        default_order_size: float = 1.0,
        time_in_force_bars: int = 4,
    ):
        self.symbol = symbol
        self.half_spread_fraction = half_spread_fraction
        self.default_order_size = default_order_size
        self.time_in_force_bars = time_in_force_bars
        self._order_counter: int = 0

    def generate_order_from_signal(
        self,
        signal: float,  # Range [-1.0, 1.0]; positive = Long/Buy, negative = Short/Sell
        snapshot: MarketSnapshot,
        order_manager: HypotheticalOrderManager,
        threshold: float = 0.20,
    ) -> HypotheticalOrder | None:
        """
        Generates a passive limit order if directional signal exceeds threshold.
        Limit price is placed passively at the inside spread.
        """
        if abs(signal) < threshold:
            return None

        # Only place new order if no active orders are currently pending
        if len(order_manager.active_orders) > 0:
            return None

        self._order_counter += 1
        half_spread_amt = (
            snapshot.close * (snapshot.spread_bps / 10000.0)
        ) * self.half_spread_fraction

        if signal > 0:
            side = OrderSide.BUY
            # Passive buy placed at or slightly below mid
            limit_price = round(snapshot.close - half_spread_amt, 2)
        else:
            side = OrderSide.SELL
            # Passive sell placed at or slightly above mid
            limit_price = round(snapshot.close + half_spread_amt, 2)

        order_id = f"ORD_{self._order_counter:06d}_{side.value}"

        order = order_manager.submit_order(
            order_id=order_id,
            symbol=self.symbol,
            side=side,
            limit_price=limit_price,
            quantity=self.default_order_size,
            current_snapshot=snapshot,
            post_only=True,
            time_in_force_bars=self.time_in_force_bars,
        )
        return order
