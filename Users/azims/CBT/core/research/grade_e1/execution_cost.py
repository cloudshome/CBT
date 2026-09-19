"""
core/research/grade_e1/execution_cost.py
========================================
Grade-E1 Execution Cost Decomposition & Exchange Fee Profile Engine.

Decomposes execution economics into gross spread capture, fees, adverse selection drag,
and unfilled order opportunity costs across multi-tier exchange schedules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.research.grade_e1.contracts import (
    AdverseSelectionMetrics,
    CalibratedCostBreakdown,
    HypotheticalOrder,
    OrderStatus,
)

logger = logging.getLogger("sky.grade_e1.execution_cost")


@dataclass(frozen=True)
class FeeTierProfile:
    tier_name: str
    venue: str
    maker_fee_bps: float
    taker_fee_bps: float
    slippage_bps: float = 1.0


CANONICAL_FEE_TIERS: dict[str, FeeTierProfile] = {
    "BINANCE_VIP0": FeeTierProfile(
        "BINANCE_VIP0", "BINANCE", maker_fee_bps=7.5, taker_fee_bps=10.0, slippage_bps=1.5
    ),
    "BINANCE_VIP2": FeeTierProfile(
        "BINANCE_VIP2", "BINANCE", maker_fee_bps=4.0, taker_fee_bps=5.0, slippage_bps=1.0
    ),
    "BINANCE_VIP4": FeeTierProfile(
        "BINANCE_VIP4", "BINANCE", maker_fee_bps=2.0, taker_fee_bps=3.0, slippage_bps=0.8
    ),
    "BYBIT_VIP0": FeeTierProfile(
        "BYBIT_VIP0", "BYBIT", maker_fee_bps=2.0, taker_fee_bps=5.5, slippage_bps=1.5
    ),
    "BYBIT_VIP2": FeeTierProfile(
        "BYBIT_VIP2", "BYBIT", maker_fee_bps=1.0, taker_fee_bps=3.5, slippage_bps=1.0
    ),
}


class GradeE1ExecutionCostEngine:
    """Calculates comprehensive cost breakdowns and maker vs. taker comparative advantage."""

    def compute_breakdown(
        self,
        orders: list[HypotheticalOrder],
        adverse_selection: AdverseSelectionMetrics,
        fee_tier: FeeTierProfile,
        unfilled_opportunity_cost_bps: float = 3.0,
    ) -> CalibratedCostBreakdown:
        total_orders = len(orders)
        if total_orders == 0:
            return CalibratedCostBreakdown(
                fee_tier_name=fee_tier.tier_name,
                maker_fee_bps=fee_tier.maker_fee_bps,
                taker_fee_bps=fee_tier.taker_fee_bps,
                gross_spread_earned_bps=0.0,
                adverse_selection_loss_bps=0.0,
                opportunity_cost_bps=0.0,
                net_maker_edge_bps=0.0,
                taker_benchmark_cost_bps=0.0,
                maker_advantage_bps=0.0,
                is_maker_superior=False,
            )

        filled_orders = sum(1 for o in orders if o.status == OrderStatus.FILLED)
        unfilled_orders = total_orders - filled_orders
        unfilled_ratio = unfilled_orders / total_orders

        # Maker Economics
        gross_spread = adverse_selection.gross_spread_captured_bps
        # Markout 5 bars: if negative, it is an adverse selection loss
        markout_5 = adverse_selection.mean_markout_5_bar_bps
        adverse_selection_loss = abs(min(0.0, markout_5))

        # Expected opportunity cost scaled by unfilled fraction
        effective_opp_cost = unfilled_ratio * unfilled_opportunity_cost_bps

        # Net Maker Edge in bps per trade:
        # + earned half spread
        # - maker fee
        # + markout (which could be positive or negative)
        # - unfilled opportunity cost
        net_maker_edge = gross_spread - fee_tier.maker_fee_bps + markout_5 - effective_opp_cost

        # Taker Benchmark Cost (all entries pay taker fee + half spread + slippage)
        # Taker cost is a negative drag on PnL
        taker_cost = fee_tier.taker_fee_bps + gross_spread + fee_tier.slippage_bps
        taker_benchmark_edge = -taker_cost

        # Maker advantage: How much better (or worse) is maker execution vs taker execution
        maker_advantage = net_maker_edge - taker_benchmark_edge
        is_superior = maker_advantage > 0.0

        return CalibratedCostBreakdown(
            fee_tier_name=fee_tier.tier_name,
            maker_fee_bps=fee_tier.maker_fee_bps,
            taker_fee_bps=fee_tier.taker_fee_bps,
            gross_spread_earned_bps=round(gross_spread, 2),
            adverse_selection_loss_bps=round(adverse_selection_loss, 2),
            opportunity_cost_bps=round(effective_opp_cost, 2),
            net_maker_edge_bps=round(net_maker_edge, 2),
            taker_benchmark_cost_bps=round(taker_cost, 2),
            maker_advantage_bps=round(maker_advantage, 2),
            is_maker_superior=is_superior,
        )
