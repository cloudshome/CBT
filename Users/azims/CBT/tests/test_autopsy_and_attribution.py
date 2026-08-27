"""
Tests for Layer 10: 11-Category Loss Autopsies, Counterfactuals & Shapley Alpha Attribution.
"""

import pytest
from core.loss_autopsy import loss_autopsy_engine, LossCategory
from core.counterfactual_engine import counterfactual_engine
from core.alpha_attribution import alpha_attribution_engine


def test_loss_autopsy_classification():
    """Verify 11-category root cause classification on compromised data feed."""
    report = loss_autopsy_engine.conduct_autopsy(
        trade_id="TR_1001",
        symbol="BTC/USDT",
        entry_price=88500.0,
        exit_price=87200.0,
        direction="LONG",
        pnl_usd=-1300.0,
        data_quality_score=0.88, # Compromised
    )
    assert report.loss_category == LossCategory.DATA_FAILURE
    assert report.confidence > 0.85
    assert len(report.forensic_evidence) >= 1


def test_counterfactual_what_if_simulator():
    """Verify counterfactual parameter perturbation simulation."""
    rep = counterfactual_engine.run_counterfactual_simulations(
        trade_id="TR_1002",
        symbol="BTC/USDT",
        entry_price=88500.0,
        actual_exit_price=87200.0,
        stop_loss=87300.0,
        take_profit=90500.0,
        direction="LONG",
        actual_pnl_usd=-1200.0,
        trade_candles=[],
    )
    assert len(rep.counterfactual_scenarios) == 4
    assert rep.optimal_scenario is not None
    assert rep.optimal_scenario.is_better_than_actual


def test_shapley_alpha_attribution():
    """Verify Shapley value component decomposition."""
    attr = alpha_attribution_engine.attribute_trade_return(
        trade_id="TR_1003",
        symbol="BTC/USDT",
        pnl_usd=2500.0,
    )
    assert len(attr.attributions) >= 6
    total_dollar = sum(a.dollar_impact for a in attr.attributions)
    assert total_dollar > 2000.0
    assert attr.top_alpha_driver in ["HTF_Trend", "Liquidity_Sweep", "CVD_Absorption"]
