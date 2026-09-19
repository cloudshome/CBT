"""
tests/research/grade_e1/test_calibrated_costs.py
================================================
Tests for Grade-E1 Execution Cost Breakdown and Out-of-Sample Calibration.
"""

from __future__ import annotations

from core.research.grade_e1.calibration import GradeE1CostCalibrator
from core.research.grade_e1.contracts import (
    AdverseSelectionMetrics,
    FillEvent,
    HypotheticalOrder,
    OrderSide,
    OrderStatus,
)
from core.research.grade_e1.execution_cost import (
    CANONICAL_FEE_TIERS,
    GradeE1ExecutionCostEngine,
)


def test_cost_breakdown_mechanics() -> None:
    cost_engine = GradeE1ExecutionCostEngine()

    orders = [
        HypotheticalOrder("O1", "TEST", OrderSide.BUY, 100.0, 1.0, status=OrderStatus.FILLED),
        HypotheticalOrder("O2", "TEST", OrderSide.BUY, 100.0, 1.0, status=OrderStatus.EXPIRED),
    ]

    # Half spread = 2.0 bps, Mean markout 5 = -1.0 bps (adverse selection)
    adverse = AdverseSelectionMetrics(
        total_fills=1,
        mean_markout_1_bar_bps=-0.5,
        mean_markout_5_bar_bps=-1.0,
        mean_markout_12_bar_bps=-1.5,
        mean_markout_24_bar_bps=-2.0,
        toxic_fill_ratio_5_bar=1.0,
        gross_spread_captured_bps=2.0,
        realized_spread_5_bar_bps=1.0,
        adverse_selection_half_life_bars=5.0,
    )

    tier = CANONICAL_FEE_TIERS["BINANCE_VIP2"]  # Maker 4.0 bps, Taker 5.0 bps
    breakdown = cost_engine.compute_breakdown(
        orders=orders,
        adverse_selection=adverse,
        fee_tier=tier,
        unfilled_opportunity_cost_bps=3.0,
    )

    # 1 filled, 1 unfilled => unfilled ratio = 0.50 => opportunity cost = 0.5 * 3.0 = 1.5 bps
    assert breakdown.opportunity_cost_bps == 1.5
    assert breakdown.maker_fee_bps == 4.0

    # Net maker edge = gross_spread(2.0) - maker_fee(4.0) + markout(-1.0) - opp_cost(1.5) = -4.5 bps
    assert breakdown.net_maker_edge_bps == -4.5

    # Taker benchmark cost = taker_fee(5.0) + gross_spread(2.0) + slippage(1.0) = 8.0 bps => edge = -8.0 bps
    assert breakdown.taker_benchmark_cost_bps == 8.0

    # Maker advantage = -4.5 - (-8.0) = +3.5 bps
    assert breakdown.maker_advantage_bps == 3.5
    assert breakdown.is_maker_superior is True


def test_out_of_sample_calibration_stability() -> None:
    calibrator = GradeE1CostCalibrator(train_ratio=0.50)

    # 20 fills with stable markout
    fills = [
        FillEvent(
            fill_id=f"F{i}",
            order_id=f"O{i}",
            bar_index=i,
            timestamp=1000 + i * 1000,
            side=OrderSide.BUY,
            fill_price=100.0,
            fill_qty=1.0,
            fee_bps=2.0,
            markout_5_bar_bps=-2.0,
        )
        for i in range(20)
    ]

    report = calibrator.calibrate(fills)
    assert report.is_cost_stable_out_of_sample is True
    assert report.in_sample_mean_markout_bps == -2.0
    assert report.out_of_sample_mean_markout_bps == -2.0
