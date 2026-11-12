"""
tests/test_checkpoint3_forward_qualification.py
================================================
Milestone 39 WP-4.2 Verification Suite:
- Checkpoint 2: Certified Statistical Edge (CPCV + DSR > 0.95 across 100+ OOS trades with positive net expectancy)
- Checkpoint 3: Decided Forward Paper / Testnet Trades (>= 20 decided trades with positive net expectancy and zero drift)
- Dual-Prerequisite Gatekeeper Enforcement in CapitalGovernor
- Verification that CapitalGovernor remains at TIER_0_PAPER unless both checkpoints pass
"""

from __future__ import annotations

import time

import pytest

from core.execution.capital_governor import CapitalGovernor, CapitalTier


@pytest.fixture
def gov():
    strat_id = f"STRAT_QUAL_TEST_{int(time.time() * 1000)}"
    return CapitalGovernor(default_strategy_id=strat_id)


def test_rejection_when_no_checkpoints_provided(gov):
    """When evaluating escalation without Checkpoints 2 and 3, promotion is rejected."""
    # Live database currently has only 4 decided qualification trades (< 20)
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 30,
            "max_drawdown": 0.02,
        }
    )
    assert res["action"] == "REJECTED_PREREQUISITES_NOT_MET"
    assert res["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert any("REJECTED_CHECKPOINT_2" in r for r in res["reasons"])
    assert any("REJECTED_CHECKPOINT_3" in r for r in res["reasons"])


def test_rejection_when_checkpoint_2_edge_missing(gov):
    """Promotion is rejected if Checkpoint 2 edge verification has not passed, even if forward trades = 25."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 30,
            "max_drawdown": 0.02,
            "checkpoint_2_certified": False,
            "cpcv_dsr": 0.82,  # < 0.95
            "oos_trade_count": 90,  # < 100
            "checkpoint_3_certified": True,
        }
    )
    assert res["action"] == "REJECTED_PREREQUISITES_NOT_MET"
    assert res["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert any("REJECTED_CHECKPOINT_2" in r for r in res["reasons"])


def test_rejection_when_checkpoint_3_forward_trades_below_20(gov):
    """Promotion is rejected if forward decided trade count is less than 20."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 30,
            "max_drawdown": 0.02,
            "checkpoint_2_certified": True,
            "forward_decided_trades": 19,  # Deficit of 1 trade
            "forward_net_expectancy": 0.35,
            "reconciliation_drift": 0.0,
        }
    )
    assert res["action"] == "REJECTED_PREREQUISITES_NOT_MET"
    assert res["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert any("insufficient forward trades (19/20 required)" in r for r in res["reasons"])


def test_rejection_when_forward_expectancy_negative(gov):
    """Promotion is rejected if forward paper net expectancy is negative or non-positive."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 30,
            "max_drawdown": 0.02,
            "checkpoint_2_certified": True,
            "forward_decided_trades": 25,
            "forward_net_expectancy": -0.05,  # Negative expectancy
            "reconciliation_drift": 0.0,
        }
    )
    assert res["action"] == "REJECTED_PREREQUISITES_NOT_MET"
    assert res["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert any("non-positive forward expectancy" in r for r in res["reasons"])


def test_rejection_when_reconciliation_drift_detected(gov):
    """Promotion is rejected if shadow ledger accounting drift exceeds $0.001."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 30,
            "max_drawdown": 0.02,
            "checkpoint_2_certified": True,
            "forward_decided_trades": 25,
            "forward_net_expectancy": 0.25,
            "reconciliation_drift": 0.05,  # $0.05 drift > $0.001
        }
    )
    assert res["action"] == "REJECTED_PREREQUISITES_NOT_MET"
    assert res["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert any("accounting drift" in r for r in res["reasons"])


def test_promotion_when_both_checkpoints_certified(gov):
    """Promotion to TIER_1_CANARY_ELIGIBLE succeeds when both Checkpoints 2 and 3 are certified."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 25,
            "trials_count": 5,
            "max_drawdown": 0.02,
            "slippage_bps": 5.0,
            "cpcv_dsr": 0.965,
            "oos_trade_count": 120,
            "net_expectancy_r": 0.42,
            "forward_decided_trades": 22,
            "forward_net_expectancy": 0.28,
            "reconciliation_drift": 0.0001,
        }
    )
    assert res["action"] == "PROMOTED_TO_ELIGIBLE"
    assert res["current_tier"] == CapitalTier.TIER_1_CANARY_ELIGIBLE.value
    assert any("Passed Tier 1 Canary Eligibility" in r for r in res["reasons"])


def test_real_money_order_still_prohibited_in_canary_eligible(gov):
    """Even after promotion to TIER_1_CANARY_ELIGIBLE, live capital orders remain blocked until operator activation."""
    res = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.5,
            "trade_count": 25,
            "trials_count": 5,
            "max_drawdown": 0.02,
            "checkpoint_2_certified": True,
            "checkpoint_3_certified": True,
        }
    )
    assert res["current_tier"] == CapitalTier.TIER_1_CANARY_ELIGIBLE.value

    clearance = gov.evaluate_order_risk(
        requested_notional_usd=25.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        current_equity=1000.0,
    )
    assert clearance.passed is False
    assert any(
        "real-money live execution is prohibited" in r.lower() for r in clearance.rejection_reasons
    )
