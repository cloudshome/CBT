"""
Unit tests for core/smart_execution.py.
Verifies TWAP, VWAP, Almgren-Chriss trajectories, Smart Order Routing (SOR),
and square-root market impact modeling.
"""

from core.smart_execution import (
    AlmgrenChrissTrajectory,
    MarketImpactSimulation,
    SmartExecutionEngine,
)


def test_smart_execution_twap_schedule():
    engine = SmartExecutionEngine()
    slices = engine.generate_twap_schedule(
        qty=10.0, duration_sec=300, num_slices=5, mid_price=60000.0
    )

    assert len(slices) == 5
    total_scheduled = sum(s.slice_qty for s in slices)
    assert abs(total_scheduled - 10.0) < 1e-3
    assert slices[0].order_type == "TWAP_CHILD"


def test_smart_execution_vwap_schedule():
    engine = SmartExecutionEngine()
    slices = engine.generate_vwap_schedule(
        qty=20.0, duration_sec=600, num_slices=4, mid_price=50000.0
    )

    assert len(slices) == 4
    total_scheduled = sum(s.slice_qty for s in slices)
    assert abs(total_scheduled - 20.0) < 1e-3
    assert slices[0].order_type == "VWAP_CHILD"


def test_smart_execution_almgren_chriss_trajectory():
    engine = SmartExecutionEngine()
    traj = engine.solve_almgren_chriss(
        total_qty=50.0,
        duration_sec=900,
        num_intervals=6,
        mid_price=65000.0,
        volatility_annual=0.60,
    )

    assert isinstance(traj, AlmgrenChrissTrajectory)
    assert len(traj.schedule) == 6
    total_scheduled = sum(s.slice_qty for s in traj.schedule)
    assert abs(total_scheduled - 50.0) < 1e-2
    assert traj.expected_total_impact_cost_usd > 0
    assert traj.variance_risk_usd > 0


def test_smart_execution_market_impact_simulation():
    engine = SmartExecutionEngine()
    impact_small = engine.simulate_market_impact(order_size=0.1, mid_price=60000.0)
    impact_large = engine.simulate_market_impact(order_size=100.0, mid_price=60000.0)

    assert isinstance(impact_small, MarketImpactSimulation)
    assert impact_large.total_expected_slippage_usd > impact_small.total_expected_slippage_usd
    assert impact_large.temporary_impact_bps > impact_small.temporary_impact_bps
    assert impact_large.adverse_selection_risk in ["MODERATE", "SEVERE"]


def test_smart_execution_smart_order_router():
    engine = SmartExecutionEngine()

    # Small urgent order -> IOC sweep
    decision_ioc = engine.route_order(order_size=0.05, mid_price=60000.0, urgency="HIGH")
    assert decision_ioc.recommended_route == "AGGRESSIVE_IOC_SWEEP"

    # Huge order -> Almgren-Chriss
    decision_ac = engine.route_order(order_size=10.0, mid_price=60000.0, urgency="MEDIUM")  # $600k
    assert decision_ac.recommended_route == "ALMGREN_CHRISS_OPTIMAL"
    assert len(decision_ac.execution_slices) > 1

    # Low urgency wide spread -> Passive limit queue
    decision_passive = engine.route_order(
        order_size=1.0, mid_price=60000.0, urgency="LOW", spread_bps=3.0
    )
    assert decision_passive.recommended_route == "PASSIVE_LIMIT_QUEUE"
