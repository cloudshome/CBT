"""
Tests for Layer 10 & 11: 4-Type Continuous Drift Monitor, Smart Order Router & Hot-Reload.
"""

from core.drift_monitor import drift_monitor
from core.execution_gateway import execution_gateway
from core.patch_governor import patch_governor
from core.system_evolver import system_evolver


def test_4_type_drift_detection():
    """Verify drift monitor detects concept and performance decay."""
    # Test nominal state
    nominal_rep = drift_monitor.evaluate_system_drift(
        current_atr_percentile=0.55,
        recent_brier_score=0.165,
        historical_sharpe=2.1,
        rolling_sharpe_30d=2.0,
    )
    assert not nominal_rep.is_system_drift_critical
    assert nominal_rep.recommended_capital_throttle_pct == 0.0

    # Test concept drift spike (Brier > 0.22)
    drifted_rep = drift_monitor.evaluate_system_drift(
        current_atr_percentile=0.55,
        recent_brier_score=0.265,  # Critical
        historical_sharpe=2.1,
        rolling_sharpe_30d=1.2,  # 40% decay
    )
    assert drifted_rep.is_system_drift_critical
    assert drifted_rep.recommended_capital_throttle_pct > 0.0


def test_smart_order_router_execution():
    """Verify Smart Order Router routes order across venues and audits execution."""
    res = execution_gateway.execute_order(
        symbol="BTC/USDT",
        direction="LONG",
        units=0.5,
        target_price=88450.0,
    )
    assert res.status == "FILLED"
    assert len(res.routes) == 3
    assert res.latency_ms < 1500.0


def test_governed_hot_reload_workflow():
    """Verify parameter proposal stages through validation before hot-reload."""
    proposals = system_evolver.get_pending_proposals()
    assert len(proposals) >= 1

    prop_id = proposals[0]["proposal_id"]
    success = patch_governor.execute_hot_reload(prop_id, operator_name="TEST_OPERATOR")
    assert success
