"""
core/research/grade_e1/hypothetical_order.py
===========================================
Grade-E1 Order State Machine & Lifecycle Manager.

Governs state transitions, post-only boundary validation, time-in-force expiration,
and data gap cancellation.
"""

from __future__ import annotations

import logging

from core.research.grade_e1.contracts import (
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e1.latency_model import AbstractLatencyModel

logger = logging.getLogger("sky.grade_e1.order_manager")


class HypotheticalOrderManager:
    """Manages active simulated orders, state transitions, and cancellation logic."""

    def __init__(self, latency_model: AbstractLatencyModel):
        self.latency_model = latency_model
        self._orders: dict[str, HypotheticalOrder] = {}
        self._active_order_ids: list[str] = []

    @property
    def orders(self) -> dict[str, HypotheticalOrder]:
        return self._orders

    @property
    def active_orders(self) -> list[HypotheticalOrder]:
        return [self._orders[oid] for oid in self._active_order_ids]

    def submit_order(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        limit_price: float,
        quantity: float,
        current_snapshot: MarketSnapshot,
        post_only: bool = True,
        time_in_force_bars: int = 4,
    ) -> HypotheticalOrder:
        """
        Creates and registers a new hypothetical limit order.
        Evaluates post-only rule against current snapshot.
        """
        half_spread = (current_snapshot.close * (current_snapshot.spread_bps / 10000.0)) / 2.0
        est_bid = current_snapshot.close - half_spread
        est_ask = current_snapshot.close + half_spread

        # Post-Only Invariant: Maker orders must not cross the book
        if post_only:
            if side == OrderSide.BUY and limit_price >= est_ask:
                order = HypotheticalOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    limit_price=limit_price,
                    quantity=quantity,
                    post_only=True,
                    status=OrderStatus.REJECTED,
                    submission_bar_idx=current_snapshot.bar_index,
                    submission_timestamp=current_snapshot.timestamp,
                    cancel_reason="POST_ONLY_RESTRICTION_CROSSED_ASK",
                )
                self._orders[order_id] = order
                return order

            if side == OrderSide.SELL and limit_price <= est_bid:
                order = HypotheticalOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    limit_price=limit_price,
                    quantity=quantity,
                    post_only=True,
                    status=OrderStatus.REJECTED,
                    submission_bar_idx=current_snapshot.bar_index,
                    submission_timestamp=current_snapshot.timestamp,
                    cancel_reason="POST_ONLY_RESTRICTION_CROSSED_BID",
                )
                self._orders[order_id] = order
                return order

        latency_ms = self.latency_model.sample_submission_latency_ms()
        ack_ts = current_snapshot.timestamp + int(latency_ms)

        order = HypotheticalOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            limit_price=limit_price,
            quantity=quantity,
            post_only=post_only,
            time_in_force_bars=time_in_force_bars,
            submission_bar_idx=current_snapshot.bar_index,
            submission_timestamp=current_snapshot.timestamp,
            ack_timestamp=ack_ts,
            status=OrderStatus.PENDING_QUEUE,
        )
        self._orders[order_id] = order
        self._active_order_ids.append(order_id)
        return order

    def on_market_bar(self, snapshot: MarketSnapshot) -> list[HypotheticalOrder]:
        """
        Processes active orders against current bar timing.
        Expires stale orders and cancels orders if crossing data gaps.
        """
        updated_active_ids: list[str] = []

        for oid in self._active_order_ids:
            order = self._orders[oid]

            # Invalidate if gap boundary
            if snapshot.is_gap_boundary:
                order.status = OrderStatus.CANCELLED_DUE_TO_DATA_GAP
                order.cancel_reason = "DATA_GAP_DETECTED"
                continue

            # Check time-in-force expiration
            elapsed_bars = snapshot.bar_index - order.submission_bar_idx
            if elapsed_bars >= order.time_in_force_bars:
                order.status = OrderStatus.EXPIRED
                order.cancel_reason = f"TIME_IN_FORCE_EXPIRED_{elapsed_bars}_BARS"
                continue

            updated_active_ids.append(oid)

        self._active_order_ids = updated_active_ids
        return self.active_orders

    def record_fill(
        self,
        order_id: str,
        fill_qty: float,
        fill_price: float,
    ) -> HypotheticalOrder:
        """Updates order execution state on fill."""
        order = self._orders[order_id]
        new_filled = order.filled_qty + fill_qty
        order.avg_fill_price = (
            (order.avg_fill_price * order.filled_qty) + (fill_price * fill_qty)
        ) / max(1e-8, new_filled)
        order.filled_qty = new_filled
        order.remaining_qty = max(0.0, order.quantity - new_filled)

        if order.remaining_qty <= 1e-8:
            order.status = OrderStatus.FILLED
            if order_id in self._active_order_ids:
                self._active_order_ids.remove(order_id)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        return order
