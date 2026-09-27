"""
core/research/grade_e2/adaptive_fill_engine.py
=============================================
Grade-E2 Protected Maker Execution Engine.

Combines VPIN toxicity filtering, Parkinson volatility gating, and adaptive depth
pegging with the Grade-E1 queue priority fill determination engine.
"""

from __future__ import annotations

import logging

from core.research.grade_e1.contracts import (
    FillEngineType,
    FillEvent,
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e1.fill_engine import GradeE1FillEngine
from core.research.grade_e2.contracts import (
    DefenseEvaluation,
    PeggingMode,
)
from core.research.grade_e2.pegging_engine import GradeE2PeggingEngine
from core.research.grade_e2.toxicity_filter import GradeE2ToxicityFilter
from core.research.grade_e2.volatility_gate import GradeE2VolatilityGate

logger = logging.getLogger("sky.grade_e2.adaptive_fill_engine")


class GradeE2AdaptiveFillEngine:
    """Protected maker execution engine equipped with toxic flow defense and adaptive pegging."""

    def __init__(
        self,
        fill_engine_type: FillEngineType = FillEngineType.F1_CONSERVATIVE,
        maker_fee_bps: float = 2.0,
        pegging_mode: PeggingMode = PeggingMode.VOLATILITY_SCALED,
        toxicity_threshold: float = 0.55,
        queue_participation_factor: float = 0.20,
        seed: int = 42,
    ):
        self.base_engine = GradeE1FillEngine(
            engine_type=fill_engine_type,
            maker_fee_bps=maker_fee_bps,
            queue_participation_factor=queue_participation_factor,
            seed=seed,
        )
        self.toxicity_filter = GradeE2ToxicityFilter(toxicity_threshold=toxicity_threshold)
        self.volatility_gate = GradeE2VolatilityGate()
        self.pegging_engine = GradeE2PeggingEngine(mode=pegging_mode)

        self.rejected_order_count: int = 0
        self.rejection_reasons: dict[str, int] = {}
        self._order_counter: int = 0

    @property
    def order_manager(self):
        return self.base_engine.order_manager

    @property
    def fill_history(self) -> list[FillEvent]:
        return self.base_engine.fill_history

    def evaluate_pre_trade_defenses(self, snapshot: MarketSnapshot) -> DefenseEvaluation:
        """Evaluates causal toxicity and volatility gating prior to order dispatch."""
        safe_tox, vpin, tox_reason = self.toxicity_filter.is_order_safe(snapshot)
        safe_vol, vol, regime, vol_reason = self.volatility_gate.is_order_safe(snapshot)

        offset_bps = self.pegging_engine.compute_adaptive_offset_bps(snapshot, regime)

        if not safe_tox:
            return DefenseEvaluation(
                is_order_permitted=False,
                toxicity_score=vpin,
                volatility_bps=vol,
                volatility_regime=regime,
                recommended_offset_bps=offset_bps,
                rejection_reason=tox_reason,
            )

        if not safe_vol:
            return DefenseEvaluation(
                is_order_permitted=False,
                toxicity_score=vpin,
                volatility_bps=vol,
                volatility_regime=regime,
                recommended_offset_bps=offset_bps,
                rejection_reason=vol_reason,
            )

        return DefenseEvaluation(
            is_order_permitted=True,
            toxicity_score=vpin,
            volatility_bps=vol,
            volatility_regime=regime,
            recommended_offset_bps=offset_bps,
            rejection_reason=None,
        )

    def submit_defensive_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        snapshot: MarketSnapshot,
        time_in_force_bars: int = 4,
    ) -> HypotheticalOrder | None:
        """
        Attempts to submit a defended passive limit order.
        If market toxicity or volatility fails safety gates, order is suppressed.
        """
        defense = self.evaluate_pre_trade_defenses(snapshot)
        if not defense.is_order_permitted:
            self.rejected_order_count += 1
            reason = defense.rejection_reason or "DEFENSE_SUPPRESSION"
            self.rejection_reasons[reason] = self.rejection_reasons.get(reason, 0) + 1
            return None

        # Only 1 pending order at a time per symbol
        if len(self.order_manager.active_orders) > 0:
            return None

        self._order_counter += 1
        limit_p = self.pegging_engine.calculate_limit_price(
            side=side,
            snapshot=snapshot,
            regime=defense.volatility_regime,
        )
        order_id = f"DEF_ORD_{self._order_counter:06d}_{side.value}"

        order = self.order_manager.submit_order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            limit_price=limit_p,
            quantity=quantity,
            current_snapshot=snapshot,
            post_only=True,
            time_in_force_bars=time_in_force_bars,
        )
        return order

    def process_bar(self, snapshot: MarketSnapshot, median_volume: float) -> list[FillEvent]:
        """
        Processes dynamic repegging checks, order aging, and queue fill evaluations.
        """
        # Check active orders for drift and repeg
        for order in list(self.order_manager.active_orders):
            if self.pegging_engine.should_repeg_order(order, snapshot):
                order.status = OrderStatus.CANCELLED
                order.cancel_reason = "REPEGGED_DUE_TO_PRICE_DRIFT"

        # Delegate queue processing to base engine
        return self.base_engine.process_bar(snapshot, median_volume=median_volume)
