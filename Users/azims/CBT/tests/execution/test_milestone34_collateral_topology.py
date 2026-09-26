"""
tests/execution/test_milestone34_collateral_topology.py
========================================================
Adversarial Verification Battery for Milestone 34:
Cross-Venue Collateral Telemetry, Liquidation Distance Buffer, and Rebalancing Advisor.

Mandatory Invariants Tested:
1. Exact mathematical Liquidation Distance Buffer (LDB) calculation and risk tier transitions.
2. Flat position / zero-risk handling.
3. Asymmetric Liquidation Hazard detection across divergent synthetic legs.
4. Balanced cross-venue margin stability (no false positive hazard).
5. Optimal internal rebalancing trajectory and post-transfer margin projection.
6. Safe source capacity constraint (preventing source venue over-depletion).
7. Minimum transfer threshold enforcement.
8. Permanent constitutional capital isolation (real_capital_enabled == False).
9. Milestone 18 execution surface isolation (149/149 certified tests untouched).
"""

from __future__ import annotations

import pytest

from core.risk_engine.collateral_monitor import (
    AsymmetricHazardReport,
    CollateralHeartbeatMonitor,
    LiquidationRiskTier,
)
from core.risk_engine.rebalancing_advisor import (
    RebalancingAdvisor,
    RebalancingInstruction,
)


@pytest.fixture
def collateral_monitor() -> CollateralHeartbeatMonitor:
    return CollateralHeartbeatMonitor(
        normal_ldb_threshold_bps=1500.0,
        warning_ldb_threshold_bps=800.0,
        critical_ldb_threshold_bps=300.0,
        max_asymmetric_hazard_delta_bps=1000.0,
    )


@pytest.fixture
def rebalancing_advisor() -> RebalancingAdvisor:
    return RebalancingAdvisor(
        target_margin_utilization=0.50,
        min_transfer_amount_usd=100.0,
        flat_transfer_fee_usd=5.0,
    )


def test_01_liquidation_distance_buffer_calculation(collateral_monitor: CollateralHeartbeatMonitor):
    """Verifies exact LDB math: (|P_mark - P_liq| / P_mark) * 10,000 and risk tier transitions."""
    # Mark price = 100,000, Liq price = 90,000
    # Diff = 10,000. LDB = (10,000 / 100,000) * 10,000 = 1,000 bps (10%)
    # Tier should be ELEVATED_RISK (800 < LDB <= 1500 bps)
    tel = collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE_PERP",
        symbol="BTC-PERP",
        position_size=1.0,
        entry_price=98000.0,
        mark_price=100000.0,
        liquidation_price=90000.0,
        total_equity_usd=50000.0,
        used_margin_usd=15000.0,
        maintenance_margin_req_usd=5000.0,
    )

    assert pytest.approx(tel.liquidation_distance_bps, 1e-4) == 1000.0
    assert tel.risk_tier == LiquidationRiskTier.ELEVATED_RISK
    assert pytest.approx(tel.margin_utilization, 1e-4) == 0.30
    assert tel.available_margin_usd == 35000.0

    # Test CRITICAL_EMERGENCY tier (LDB <= 300 bps):
    # Mark = 100,000, Liq = 98,000 -> Diff = 2,000 -> LDB = 200 bps
    tel_crit = collateral_monitor.compute_collateral_telemetry(
        venue="BYBIT_PERP",
        symbol="BTC-PERP",
        position_size=1.0,
        entry_price=99000.0,
        mark_price=100000.0,
        liquidation_price=98000.0,
        total_equity_usd=10000.0,
        used_margin_usd=9000.0,
        maintenance_margin_req_usd=5000.0,
    )
    assert pytest.approx(tel_crit.liquidation_distance_bps, 1e-4) == 200.0
    assert tel_crit.risk_tier == LiquidationRiskTier.CRITICAL_EMERGENCY


def test_02_flat_position_zero_liquidation_risk(collateral_monitor: CollateralHeartbeatMonitor):
    """Verifies that flat position or zero liquidation price defaults to safe NORMAL tier."""
    tel = collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE_SPOT",
        symbol="BTC/USDT",
        position_size=0.0,  # Flat
        entry_price=0.0,
        mark_price=100000.0,
        liquidation_price=0.0,
        total_equity_usd=50000.0,
        used_margin_usd=0.0,
        maintenance_margin_req_usd=0.0,
    )
    assert tel.risk_tier == LiquidationRiskTier.NORMAL
    assert tel.liquidation_distance_bps > 50000.0


def test_03_asymmetric_hazard_detection(collateral_monitor: CollateralHeartbeatMonitor):
    """Verifies that when one leg enters critical LDB while counter-leg is safe, an asymmetric hazard is flagged."""
    # Leg 1: Binance Spot (safe: LDB = 50,000 bps, NORMAL)
    collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE_SPOT",
        symbol="BTC",
        position_size=1.0,
        entry_price=100000.0,
        mark_price=100000.0,
        liquidation_price=0.0,
        total_equity_usd=50000.0,
        used_margin_usd=0.0,
        maintenance_margin_req_usd=0.0,
    )

    # Leg 2: Hyperliquid Perp (critical: Mark = 100,000, Liq = 102,500, Short position)
    # LDB = (2500 / 100,000) * 10,000 = 250 bps <= 300 bps (CRITICAL)
    collateral_monitor.compute_collateral_telemetry(
        venue="HYPERLIQUID_L1",
        symbol="BTC",
        position_size=-1.0,
        entry_price=95000.0,
        mark_price=100000.0,
        liquidation_price=102500.0,
        total_equity_usd=10000.0,
        used_margin_usd=8500.0,
        maintenance_margin_req_usd=4000.0,
    )

    hazard = collateral_monitor.evaluate_asymmetric_hazard(
        synthetic_pair_id="SYNTH_BTC_CASH_CARRY",
        symbol="BTC",
        leg_1_venue="BINANCE_SPOT",
        leg_2_venue="HYPERLIQUID_L1",
    )

    assert hazard.hazard_detected is True
    assert hazard.leg_2_risk_tier == LiquidationRiskTier.CRITICAL_EMERGENCY
    assert "EMERGENCY_DELEVERAGE_OR_REBALANCE" in hazard.action_required
    assert hazard.real_capital_enabled is False


def test_04_balanced_position_no_hazard(collateral_monitor: CollateralHeartbeatMonitor):
    """Verifies that balanced cross-venue positions do not trigger false hazard alarms."""
    # Both venues healthy with LDB > 2,000 bps
    collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE_SPOT",
        symbol="ETH",
        position_size=10.0,
        entry_price=3000.0,
        mark_price=3100.0,
        liquidation_price=0.0,
        total_equity_usd=50000.0,
        used_margin_usd=0.0,
        maintenance_margin_req_usd=0.0,
    )
    collateral_monitor.compute_collateral_telemetry(
        venue="BYBIT_PERP",
        symbol="ETH",
        position_size=-10.0,
        entry_price=3050.0,
        mark_price=3100.0,
        liquidation_price=4000.0,  # LDB = (900/3100)*10000 = 2903 bps
        total_equity_usd=50000.0,
        used_margin_usd=10000.0,
        maintenance_margin_req_usd=3000.0,
    )

    hazard = collateral_monitor.evaluate_asymmetric_hazard(
        synthetic_pair_id="SYNTH_ETH_PAIR",
        symbol="ETH",
        leg_1_venue="BINANCE_SPOT",
        leg_2_venue="BYBIT_PERP",
    )

    assert hazard.hazard_detected is False
    assert hazard.action_required == "NONE"


def test_05_rebalancing_plan_generation(
    rebalancing_advisor: RebalancingAdvisor,
    collateral_monitor: CollateralHeartbeatMonitor,
):
    """Verifies optimal rebalancing plan calculation to restore 50% target margin utilization."""
    # Source: Binance (Equity = $50,000, Used = $10,000 -> 20% util)
    source_tel = collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=50000.0,
        used_margin_usd=10000.0,
        maintenance_margin_req_usd=5000.0,
    )

    # Destination: Hyperliquid (Equity = $10,000, Used = $8,000 -> 80% util!)
    # To reach 50% target util with $8,000 used margin:
    # Target equity = $8,000 / 0.50 = $16,000. Transfer needed = $16,000 - $10,000 = $6,000.
    dest_tel = collateral_monitor.compute_collateral_telemetry(
        venue="HYPERLIQUID",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=10000.0,
        used_margin_usd=8000.0,
        maintenance_margin_req_usd=4000.0,
    )

    hazard_report = AsymmetricHazardReport(
        synthetic_pair_id="TEST_PAIR",
        symbol="BTC",
        leg_1_venue="BINANCE",
        leg_1_ldb_bps=100000.0,
        leg_1_risk_tier=LiquidationRiskTier.NORMAL,
        leg_2_venue="HYPERLIQUID",
        leg_2_ldb_bps=200.0,
        leg_2_risk_tier=LiquidationRiskTier.CRITICAL_EMERGENCY,
        hazard_detected=True,
        asymmetry_ratio=500.0,
        action_required="REBALANCE",
    )

    plan = rebalancing_advisor.generate_rebalancing_plan(hazard_report, source_tel, dest_tel)

    assert plan is not None
    assert plan.source_venue == "BINANCE"
    assert plan.destination_venue == "HYPERLIQUID"
    assert pytest.approx(plan.recommended_transfer_usd, 1e-2) == 6000.0
    assert plan.hazard_mitigated is True
    assert plan.dest_projected_margin_utilization <= 0.55
    assert plan.real_capital_enabled is False
    assert plan.advisory_mode_only is True


def test_06_insufficient_source_capacity_prevents_rebalancing(
    rebalancing_advisor: RebalancingAdvisor,
    collateral_monitor: CollateralHeartbeatMonitor,
):
    """Verifies that if source venue is also near max margin utilization, no transfer is advised."""
    # Source is already at 50% utilization (Equity = $20,000, Used = $10,000)
    source_tel = collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=20000.0,
        used_margin_usd=10000.0,
        maintenance_margin_req_usd=5000.0,
    )
    # Dest is at 80% (Equity = $10,000, Used = $8,000)
    dest_tel = collateral_monitor.compute_collateral_telemetry(
        venue="HYPERLIQUID",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=10000.0,
        used_margin_usd=8000.0,
        maintenance_margin_req_usd=4000.0,
    )
    hazard_report = AsymmetricHazardReport(
        synthetic_pair_id="TEST_PAIR",
        symbol="BTC",
        leg_1_venue="BINANCE",
        leg_1_ldb_bps=2000.0,
        leg_1_risk_tier=LiquidationRiskTier.NORMAL,
        leg_2_venue="HYPERLIQUID",
        leg_2_ldb_bps=200.0,
        leg_2_risk_tier=LiquidationRiskTier.CRITICAL_EMERGENCY,
        hazard_detected=True,
        asymmetry_ratio=10.0,
        action_required="REBALANCE",
    )

    plan = rebalancing_advisor.generate_rebalancing_plan(hazard_report, source_tel, dest_tel)
    # Source cannot safely transfer without exceeding 50% target utilization, so plan is None
    assert plan is None


def test_07_transfer_below_minimum_threshold(
    rebalancing_advisor: RebalancingAdvisor,
    collateral_monitor: CollateralHeartbeatMonitor,
):
    """Verifies that transfers below $100 are ignored."""
    source_tel = collateral_monitor.compute_collateral_telemetry(
        venue="BINANCE",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=50000.0,
        used_margin_usd=10000.0,
        maintenance_margin_req_usd=5000.0,
    )
    # Dest needs only $50 transfer
    dest_tel = collateral_monitor.compute_collateral_telemetry(
        venue="HYPERLIQUID",
        symbol="USDT",
        position_size=0.0,
        entry_price=1.0,
        mark_price=1.0,
        liquidation_price=0.0,
        total_equity_usd=10000.0,
        used_margin_usd=5025.0,  # 50.25% util
        maintenance_margin_req_usd=2000.0,
    )
    hazard_report = AsymmetricHazardReport(
        synthetic_pair_id="TEST_PAIR",
        symbol="BTC",
        leg_1_venue="BINANCE",
        leg_1_ldb_bps=100000.0,
        leg_1_risk_tier=LiquidationRiskTier.NORMAL,
        leg_2_venue="HYPERLIQUID",
        leg_2_ldb_bps=2000.0,
        leg_2_risk_tier=LiquidationRiskTier.NORMAL,
        hazard_detected=False,
        asymmetry_ratio=1.0,
        action_required="NONE",
    )

    plan = rebalancing_advisor.generate_rebalancing_plan(hazard_report, source_tel, dest_tel)
    assert plan is None


def test_08_permanent_constitutional_capital_isolation():
    """Verifies that real_capital_enabled is permanently False in all data structures."""
    hazard = AsymmetricHazardReport(
        synthetic_pair_id="TEST",
        symbol="BTC",
        leg_1_venue="A",
        leg_1_ldb_bps=1000.0,
        leg_1_risk_tier=LiquidationRiskTier.NORMAL,
        leg_2_venue="B",
        leg_2_ldb_bps=1000.0,
        leg_2_risk_tier=LiquidationRiskTier.NORMAL,
        hazard_detected=False,
        asymmetry_ratio=1.0,
        action_required="NONE",
    )
    assert hazard.real_capital_enabled is False

    inst = RebalancingInstruction(
        plan_id="P1",
        source_venue="A",
        destination_venue="B",
        recommended_transfer_usd=500.0,
        source_equity_before_usd=1000.0,
        source_equity_after_usd=500.0,
        dest_equity_before_usd=500.0,
        dest_equity_after_usd=995.0,
        source_projected_margin_utilization=0.5,
        dest_projected_margin_utilization=0.5,
        hazard_mitigated=True,
    )
    assert inst.real_capital_enabled is False


def test_09_milestone18_execution_surface_untouched():
    """Verifies that Milestone 18 certified execution surface is untouched and active."""
    from scripts.verify_m18_certification import check_certified_surface, load_manifest
    manifest = load_manifest()
    exit_code = check_certified_surface(manifest, run_tests_if_dirty=False)
    assert exit_code == 0, "Milestone 18 certification invalidated or surface touched!"
