"""
core/mbo/queue_priority_engine.py
=================================
Queue Priority & Passive Limit Order Fill Probability Engine.
Solves FIFO waiting time distributions, queue depletion rates,
and adverse selection (toxic flow) risk.
"""

from __future__ import annotations

import logging
import math

from core.mbo.models import MBOSide, QueuePositionEstimate
from core.mbo.order_book_l3 import L3OrderBook

logger = logging.getLogger("sky.mbo.queue_priority_engine")


class QueuePriorityEngine:
    """Calculates order queue position and theoretical fill probabilities."""

    def __init__(
        self,
        default_depletion_velocity_btc_per_sec: float = 0.15,
        default_cancel_rate_ratio: float = 0.25,
    ) -> None:
        self.default_depletion_velocity = default_depletion_velocity_btc_per_sec
        self.default_cancel_rate_ratio = default_cancel_rate_ratio

    def estimate_queue_position(
        self,
        book: L3OrderBook,
        side: MBOSide,
        price: float,
        order_qty: float,
        target_order_id: str | None = None,
        observed_depletion_rate: float | None = None,
        imbalance_score: float = 0.0,
    ) -> QueuePositionEstimate:
        """
        Estimates the exact queue position and fill probability for a passive order.
        If target_order_id is None, models placing a brand new limit order at the tail of the level.
        """
        qty_ahead, orders_ahead, total_qty = book.get_queue_ahead(
            side=side, price=price, target_order_id=target_order_id
        )

        total_with_order = total_qty + (order_qty if target_order_id is None else 0.0)
        qty_behind = max(0.0, total_with_order - qty_ahead - order_qty)

        # Relative queue position (0.0 = front of queue, 1.0 = tail)
        relative_pos = qty_ahead / max(0.0001, total_with_order) if total_with_order > 0 else 0.0

        # Effective clearance rate (market order trades + cancel velocity)
        depletion_rate = (
            observed_depletion_rate
            if observed_depletion_rate and observed_depletion_rate > 0
            else self.default_depletion_velocity
        )
        total_clearance_rate = depletion_rate * (1.0 + self.default_cancel_rate_ratio)

        # Directional arrival adjustment:
        # If buying and imbalance > 0 (bid pressure), fewer sells hit bids -> slower fill
        # If selling and imbalance < 0 (ask pressure), fewer buys hit asks -> slower fill
        if side == MBOSide.BID:
            flow_multiplier = max(0.3, min(2.0, 1.0 - (imbalance_score * 0.5)))
        else:
            flow_multiplier = max(0.3, min(2.0, 1.0 + (imbalance_score * 0.5)))

        adjusted_clearance = max(0.001, total_clearance_rate * flow_multiplier)

        # Expected wait time to reach execution
        expected_wait_sec = (qty_ahead + (0.5 * order_qty)) / adjusted_clearance

        # Fill probability over discrete horizons: P(Fill in t) = 1 - exp(- adjusted_clearance * t / (qty_ahead + order_qty))
        def calc_prob(horizon_sec: float) -> float:
            target_depth = max(0.001, qty_ahead + order_qty)
            exponent = -(adjusted_clearance * horizon_sec) / target_depth
            prob = 1.0 - math.exp(max(-10.0, exponent))
            return round(min(0.999, max(0.001, prob)), 4)

        prob_30s = calc_prob(30.0)
        prob_60s = calc_prob(60.0)
        prob_300s = calc_prob(300.0)

        # Adverse selection risk:
        # High when market order depletion velocity is surging or when fill happens instantly in directional trend
        adverse_risk = min(
            0.95,
            0.20
            + (0.35 * (1.0 - relative_pos))  # Near the front receives trades first
            + (0.30 * abs(imbalance_score))  # Strong directional imbalance
            + (0.15 * min(1.0, depletion_rate / 0.5)),
        )

        return QueuePositionEstimate(
            symbol=book.symbol,
            venue=book.venue,
            side=side,
            price=price,
            simulated_order_qty=order_qty,
            queue_ahead_qty=round(qty_ahead, 4),
            queue_ahead_orders=orders_ahead,
            queue_behind_qty=round(qty_behind, 4),
            total_level_qty=round(total_with_order, 4),
            relative_queue_position_pct=round(relative_pos * 100.0, 2),
            expected_wait_seconds=round(expected_wait_sec, 2),
            fill_probability_30s=prob_30s,
            fill_probability_60s=prob_60s,
            fill_probability_300s=prob_300s,
            adverse_selection_risk_score=round(adverse_risk, 3),
            estimated_depletion_rate_qty_per_sec=round(adjusted_clearance, 4),
        )


# Global singleton
queue_priority_engine = QueuePriorityEngine()
