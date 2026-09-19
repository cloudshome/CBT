"""
core/research/grade_e1/fill_engine.py
====================================
Grade-E1 Fill Determination Engine.

Combines queue models, latency models, and order lifecycle management to
generate deterministic, calibrated simulated fill events.
"""

from __future__ import annotations

import logging

from core.research.grade_e1.contracts import (
    FillEngineType,
    FillEvent,
    LatencyModelType,
    LiquidityRole,
    MarketSnapshot,
    QueueModelType,
)
from core.research.grade_e1.hypothetical_order import HypotheticalOrderManager
from core.research.grade_e1.latency_model import create_latency_model
from core.research.grade_e1.queue_model import create_queue_model

logger = logging.getLogger("sky.grade_e1.fill_engine")


class GradeE1FillEngine:
    """Evaluates and executes hypothetical fills across causal market snapshots."""

    def __init__(
        self,
        engine_type: FillEngineType = FillEngineType.F1_CONSERVATIVE,
        maker_fee_bps: float = 2.0,
        queue_participation_factor: float = 0.20,
        seed: int = 42,
    ):
        self.engine_type = engine_type
        self.maker_fee_bps = maker_fee_bps

        # Configure queue and latency models according to engine tier
        if engine_type == FillEngineType.F1_CONSERVATIVE:
            self.queue_model = create_queue_model(
                QueueModelType.Q1_VOLUME_CLOCK,
                participation_factor=max(0.20, queue_participation_factor),
                seed=seed,
            )
            self.latency_model = create_latency_model(
                LatencyModelType.L2_STOCHASTIC_LOGNORMAL, seed=seed
            )
        elif engine_type == FillEngineType.F2_CENTRAL:
            self.queue_model = create_queue_model(QueueModelType.Q2_PENETRATION_DEPTH, seed=seed)
            self.latency_model = create_latency_model(LatencyModelType.L1_FIXED_50MS, seed=seed)
        elif engine_type == FillEngineType.F3_OPTIMISTIC:
            self.queue_model = create_queue_model(QueueModelType.Q0_OPTIMISTIC_TOUCH, seed=seed)
            self.latency_model = create_latency_model(LatencyModelType.L0_ZERO_LATENCY, seed=seed)
        else:
            raise ValueError(f"Unknown fill engine type: {engine_type}")

        self.order_manager = HypotheticalOrderManager(self.latency_model)
        self.fill_history: list[FillEvent] = []
        self._fill_counter: int = 0

    def process_bar(
        self,
        snapshot: MarketSnapshot,
        median_volume: float,
    ) -> list[FillEvent]:
        """
        Advances the simulation by one market bar:
        1. Checks order expiration and data gap conditions.
        2. Evaluates queue priority and fill conditions for all active orders.
        3. Generates immutable FillEvent instances on execution.
        """
        new_fills: list[FillEvent] = []

        # Update active order statuses for this bar
        active_orders = self.order_manager.on_market_bar(snapshot)

        for order in active_orders:
            # Don't evaluate fills on the exact bar of submission if latency delays placement
            if (
                order.submission_bar_idx == snapshot.bar_index
                and self.engine_type != FillEngineType.F3_OPTIMISTIC
            ):
                # Still within submission ingress bar
                continue

            is_filled, fill_qty, fill_price = self.queue_model.evaluate_fill(
                order=order,
                snapshot=snapshot,
                median_volume=median_volume,
            )

            if is_filled and fill_qty > 0:
                self._fill_counter += 1
                fill_id = f"FILL_{self._fill_counter:06d}_{order.order_id}"
                queue_time = float(snapshot.bar_index - order.submission_bar_idx)

                self.order_manager.record_fill(
                    order_id=order.order_id,
                    fill_qty=fill_qty,
                    fill_price=fill_price,
                )

                fill_event = FillEvent(
                    fill_id=fill_id,
                    order_id=order.order_id,
                    bar_index=snapshot.bar_index,
                    timestamp=snapshot.timestamp,
                    side=order.side,
                    fill_price=fill_price,
                    fill_qty=fill_qty,
                    fee_bps=self.maker_fee_bps,
                    role=LiquidityRole.MAKER,
                    queue_time_bars=queue_time,
                )
                self.fill_history.append(fill_event)
                new_fills.append(fill_event)

        return new_fills
