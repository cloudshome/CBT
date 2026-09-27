"""
tests/research/grade_e1/test_statistical_defense.py
===================================================
Tests for Grade-E1 Statistical Defense and Hypothesis Testing.
"""

from __future__ import annotations

import numpy as np

from core.research.grade_e1.contracts import (
    CalibratedCostBreakdown,
    FillEvent,
    OrderSide,
)
from core.research.grade_e1.statistical_tests import GradeE1StatisticalDefense


def test_block_bootstrap_reproducibility_and_bounds() -> None:
    defense = GradeE1StatisticalDefense(n_bootstrap=500, block_size=5, seed=123)
    data = np.array([1.0, 2.0, 1.5, 3.0, 2.5, 1.0, 2.0, 1.8, 2.2, 2.7] * 5)

    boot_means = defense.block_bootstrap_mean(data)
    assert len(boot_means) == 500
    assert 1.0 < np.mean(boot_means) < 3.0


def test_hypothesis_h0_a_net_maker_edge_rejection() -> None:
    defense = GradeE1StatisticalDefense(n_bootstrap=200, block_size=5, seed=42)

    cost_breakdown = CalibratedCostBreakdown(
        fee_tier_name="TEST",
        maker_fee_bps=5.0,
        taker_fee_bps=10.0,
        gross_spread_earned_bps=1.0,
        adverse_selection_loss_bps=10.0,
        opportunity_cost_bps=2.0,
        net_maker_edge_bps=-16.0,
        taker_benchmark_cost_bps=12.0,
        maker_advantage_bps=-4.0,
        is_maker_superior=False,
    )

    # Heavily negative markouts
    fills = [
        FillEvent(
            fill_id=f"F{i}",
            order_id=f"O{i}",
            bar_index=i,
            timestamp=1000 + i * 1000,
            side=OrderSide.BUY,
            fill_price=100.0,
            fill_qty=1.0,
            fee_bps=5.0,
            markout_5_bar_bps=-12.0,
        )
        for i in range(30)
    ]

    summary = defense.test_h0_a_net_maker_edge(cost_breakdown, fills)
    assert summary.hypothesis_id == "H0-A"
    assert summary.null_rejected is True
    assert summary.verdict_impact == "FAILS_ECONOMIC_VIABILITY"
