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


def test_closed_loop_depth_friction_calibration():
    """
    Phase 4 Closed-Loop Feedback Test:
    When realized paper slippage exceeds expected baseline (ratio > 1.2x),
    the simulator dynamically scales up adverse_selection_factor and latency.
    """
    from core.intelligence.forward_validation.paper_fill_simulator import (
        RealisticPaperFillSimulator,
    )

    sim = RealisticPaperFillSimulator(
        adverse_selection_factor=0.5,
        market_order_latency_ms=50.0,
    )

    # Simulate elevated slippage: 1.5 bps realized vs 0.5 bps expected (3.0x ratio)
    res = sim.calibrate_depth_friction(realized_slippage_bps=1.5, expected_slippage_bps=0.5)

    assert res["slippage_ratio"] == 3.0
    assert sim.adverse_selection_factor > 0.5
    assert sim.market_order_latency_ms > 50.0
    assert res["adverse_selection_factor"] == sim.adverse_selection_factor

    # Simulate benign market: 0.2 bps realized vs 0.5 bps expected (0.4x ratio)
    old_factor = sim.adverse_selection_factor
    res_benign = sim.calibrate_depth_friction(realized_slippage_bps=0.2, expected_slippage_bps=0.5)
    assert sim.adverse_selection_factor < old_factor


def test_drift_detector_dispatches_telegram_alert_on_severe_drift():
    """
    Phase 4 Drift-to-Telegram Dispatch Test:
    When the multi-dimensional drift detector flags SEVERE structural divergence
    (e.g. KS return test p < 0.001 or toxic markout slope), it dispatches an urgent alert.
    """
    from unittest.mock import MagicMock, patch
    from core.intelligence.forward_validation.drift_detector import (
        AxisDriftResult,
        DriftStatus,
        MultiDimensionalDriftDetector,
        MultiDimensionalDriftReport,
    )

    detector = MultiDimensionalDriftDetector(min_sample_size=30, auto_dispatch_telegram=True)

    report = MultiDimensionalDriftReport(
        admission_id="strat_trend_alpha_01",
        sample_size_n=45,
        overall_status=DriftStatus.SEVERE,
        axes={
            "return_distribution": AxisDriftResult(
                axis_name="return_distribution",
                status=DriftStatus.SEVERE,
                statistic=0.45,
                p_value=0.0001,
                warning_message="Severe return distribution drift: KS statistic=0.450, p=1.00e-04",
            ),
            "markout_decay": AxisDriftResult(
                axis_name="markout_decay",
                status=DriftStatus.DEGRADED,
                statistic=-0.22,
                warning_message="Degraded markout decay: slope=-0.220 bps/s",
            ),
        },
        drift_summary="CRITICAL: 1 axis/axes showing severe structural drift or adverse selection.",
    )

    with patch("core.telegram_bot.telegram_bot.send_message") as mock_send:
        sent = detector.dispatch_drift_alert(report)
        assert sent is True
        assert mock_send.called
        # Check alert content
        call_args = mock_send.call_args[0][0]
        assert "strat_trend_alpha_01" in call_args
        assert "CRITICAL" in call_args
        assert "Return Distribution" in call_args


def test_drift_detector_triggers_closed_loop_calibration():
    """
    Phase 4 Closed-Loop Sentinel Test:
    When evaluate_drift detects severe slippage drift, it automatically calls
    calibrate_depth_friction on the attached RealisticPaperFillSimulator.
    """
    from core.intelligence.forward_validation.drift_detector import (
        BacktestBaselineExpectations,
        DriftStatus,
        MultiDimensionalDriftDetector,
    )
    from core.intelligence.forward_validation.forward_ledger import (
        StrategyForwardScorecard,
    )
    from core.intelligence.forward_validation.paper_fill_simulator import (
        RealisticPaperFillSimulator,
    )

    sim = RealisticPaperFillSimulator(
        adverse_selection_factor=0.5,
        market_order_latency_ms=50.0,
    )
    detector = MultiDimensionalDriftDetector(
        min_sample_size=30, fill_simulator=sim, auto_dispatch_telegram=False
    )

    scorecard = StrategyForwardScorecard(
        admission_id="strat_slip_test",
        total_trades=35,
        winning_trades=20,
        losing_trades=15,
        win_rate=0.57,
        gross_pnl_bps=200.0,
        net_pnl_bps=175.0,
        mean_trade_net_bps=5.0,
        std_dev_bps=20.0,
        standard_error_bps=3.38,
        ci_95_lower_bps=-1.6,
        ci_95_upper_bps=11.6,
        max_drawdown_bps=50.0,
        high_water_mark_bps=180.0,
        avg_slippage_bps=2.5,  # 5.0x higher than 0.5 bps baseline!
        avg_fee_bps=2.0,
        markout_curve_bps={100: 1.0, 5000: 2.0, 30000: 3.0},
    )
    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=5.0,
        expected_std_dev_bps=20.0,
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=3.0,
    )

    report = detector.evaluate_drift(scorecard=scorecard, baseline=baseline)

    # Slippage drift is SEVERE (5.0x baseline > 3.0x threshold)
    assert report.axes["slippage_drift"].status == DriftStatus.SEVERE
    # Simulator parameters must have been scaled up automatically!
    assert sim.adverse_selection_factor > 0.5
    assert sim.market_order_latency_ms > 50.0


def test_suspension_controller_dispatches_telegram_on_circuit_breaker():
    """
    Phase 4 Circuit Breaker Alert Test:
    When SuspensionController executes a drawdown circuit breaker suspension,
    an urgent notification is dispatched to Telegram.
    """
    from unittest.mock import MagicMock, patch
    from core.intelligence.forward_validation.models import AdmissionStatus
    from core.intelligence.forward_validation.suspension_controller import (
        SuspensionController,
        SuspensionPolicy,
    )

    mock_registry = MagicMock()
    policy = SuspensionPolicy(max_drawdown_bps=200.0)
    controller = SuspensionController(registry=mock_registry, policy=policy)

    with patch("core.telegram_bot.telegram_bot.send_message") as mock_send:
        tripped = controller.check_drawdown("strat_drawdown_test", current_drawdown_bps=250.0)
        assert tripped is True
        assert mock_registry.transition_status.called
        assert mock_send.called
        msg = mock_send.call_args[0][0]
        assert "CIRCUIT BREAKER TRIGGERED" in msg
        assert "strat_drawdown_test" in msg
        assert "250.00" in msg
