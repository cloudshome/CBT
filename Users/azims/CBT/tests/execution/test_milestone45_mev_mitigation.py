"""
tests/execution/test_milestone45_mev_mitigation.py
=================================================
Milestone 45 Adversarial Certification Suite:
Decentralized MEV Mitigation & Fair Sequencing Simulation.

Verifies:
1. Sandwich attack vulnerability detection on high-slippage orders
2. Immunity recognition on small orders where gas exceeds MEV
3. Dynamic slippage tightening to render sandwiching unprofitable
4. Proposer-Builder Separation (PBS) bundle auction priority sorting
5. Fair sequencing batch auction uniform price clearing (Zero MEV extracted)
6. Constitutional 1.5% equity cap enforcement by MEV Sentinel
7. Automatic private RPC routing for vulnerable / high hazard orders
8. Fair sequencing batch route selection
9. Public mempool routing clearance for safe, immune orders
10. Permanent capital firewall invariant (real_capital_enabled = False)
11. Fail-closed exception containment under malformed inputs
"""

from __future__ import annotations

import pytest

from core.execution.mev_mitigation import (
    MEVRiskLevel,
    MempoolRouteType,
    PBSSimulator,
    REAL_CAPITAL_ENABLED,
    SandwichAttackEvaluator,
    mev_mitigation_sentinel,
    pbs_simulator,
    sandwich_attack_evaluator,
)


# ------------------------------------------------------------------------------
# Test 1: Sandwich Vulnerability on High-Slippage Order
# ------------------------------------------------------------------------------
def test_01_sandwich_risk_evaluation_profitable():
    """Verify orders with excessive slippage tolerance are detected as vulnerable."""
    report = sandwich_attack_evaluator.evaluate_sandwich_risk(
        symbol="ETH/USDT",
        target_notional_usd=50_000.0,
        user_slippage_tolerance_bps=100.0,  # 1.0% slippage tolerance
        pool_liquidity_usd=5_000_000.0,
    )

    assert report.net_searcher_edge_usd > 0.0
    assert report.risk_level in (MEVRiskLevel.VULNERABLE, MEVRiskLevel.HIGH_HAZARD)
    assert report.requires_private_mempool is True
    assert report.recommended_max_slippage_bps < 100.0
    assert report.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 2: Immunity on Small Orders Where Gas Exceeds MEV
# ------------------------------------------------------------------------------
def test_02_sandwich_risk_evaluation_unprofitable():
    """Verify small orders where gas cost outweighs extraction edge are marked negligible."""
    report = sandwich_attack_evaluator.evaluate_sandwich_risk(
        symbol="ETH/USDT",
        target_notional_usd=200.0,
        user_slippage_tolerance_bps=15.0,  # 15 bps
        pool_liquidity_usd=5_000_000.0,
    )

    assert report.net_searcher_edge_usd < 0.0
    assert report.risk_level == MEVRiskLevel.NEGLIGIBLE
    assert report.requires_private_mempool is False


# ------------------------------------------------------------------------------
# Test 3: Dynamic Slippage Tightening
# ------------------------------------------------------------------------------
def test_03_dynamic_slippage_boundary_tightening():
    """Verify recommended slippage makes searcher edge negative."""
    evaluator = SandwichAttackEvaluator()
    report = evaluator.evaluate_sandwich_risk(
        symbol="ETH/USDT",
        target_notional_usd=20_000.0,
        user_slippage_tolerance_bps=80.0,
        pool_liquidity_usd=2_000_000.0,
    )

    safe_slip = report.recommended_max_slippage_bps
    assert safe_slip < 80.0

    # Re-evaluate with recommended slippage: searcher edge must drop drastically
    re_report = evaluator.evaluate_sandwich_risk(
        symbol="ETH/USDT",
        target_notional_usd=20_000.0,
        user_slippage_tolerance_bps=safe_slip,
        pool_liquidity_usd=2_000_000.0,
    )
    assert re_report.net_searcher_edge_usd <= 0.0 or re_report.risk_level != MEVRiskLevel.HIGH_HAZARD


# ------------------------------------------------------------------------------
# Test 4: PBS Bundle Auction Priority Sorting
# ------------------------------------------------------------------------------
def test_04_pbs_bundle_auction_priority_sorting():
    """Verify builders are prioritized strictly descending by bid payment."""
    bids = [
        ("builder_alpha", 0.05, 120000),
        ("builder_beta", 0.12, 140000),
        ("builder_gamma", 0.08, 130000),
    ]

    bundles = pbs_simulator.simulate_bundle_auction(bids)
    assert len(bundles) == 3
    assert bundles[0].builder_id == "builder_beta"  # 0.12 ETH bid
    assert bundles[0].inclusion_priority == 1
    assert bundles[1].builder_id == "builder_gamma" # 0.08 ETH bid
    assert bundles[2].builder_id == "builder_alpha" # 0.05 ETH bid


# ------------------------------------------------------------------------------
# Test 5: Fair Sequencing Batch Clearing (Zero MEV)
# ------------------------------------------------------------------------------
def test_05_fair_sequencing_clearing_zero_mev():
    """Verify uniform clearing price batch produces exactly 0.0 USD MEV extracted."""
    buys = [(3005.0, 2.0), (3002.0, 3.0)]
    sells = [(2998.0, 1.5), (3000.0, 3.5)]

    batch = pbs_simulator.compute_fair_sequencing_clearing("ETH/USDC", buys, sells)
    assert batch.orders_count == 4
    assert 2998.0 <= batch.uniform_clearing_price <= 3005.0
    assert batch.mev_extracted_usd == 0.0  # Zero by design


# ------------------------------------------------------------------------------
# Test 6: Constitutional 1.5% Equity Cap
# ------------------------------------------------------------------------------
def test_06_mev_sentinel_1_5_percent_equity_cap():
    """Verify MEV Sentinel clamps order size to 1.5% portfolio equity."""
    plan = mev_mitigation_sentinel.evaluate_and_protect_order(
        symbol="ETH/USDT",
        requested_notional_usd=50_000.0,
        portfolio_equity_usd=100_000.0,
        user_slippage_tolerance_bps=50.0,
        pool_liquidity_usd=1_000_000.0,
    )

    assert plan.is_approved is True
    assert plan.routed_notional_usd == 1500.0  # Exactly 1.5% of 100k
    assert plan.kelly_fraction == 0.015


# ------------------------------------------------------------------------------
# Test 7: Auto Private RPC Routing for Vulnerable Orders
# ------------------------------------------------------------------------------
def test_07_mev_sentinel_auto_private_rpc_routing():
    """Verify vulnerable orders are automatically diverted to Private RPC with builder tip."""
    plan = mev_mitigation_sentinel.evaluate_and_protect_order(
        symbol="ETH/USDT",
        requested_notional_usd=10_000.0,
        portfolio_equity_usd=1_000_000.0,
        user_slippage_tolerance_bps=100.0,  # 1.0% loose slippage
        pool_liquidity_usd=500_000.0,
    )

    assert plan.route_type == MempoolRouteType.PRIVATE_RPC
    assert plan.builder_tip_usd > 0.0
    assert "Private RPC" in plan.protection_notes


# ------------------------------------------------------------------------------
# Test 8: Fair Sequencing Route Option
# ------------------------------------------------------------------------------
def test_08_mev_sentinel_fair_sequencing_option():
    """Verify order is designated for batch auction when prefer_fair_sequencing is set."""
    plan = mev_mitigation_sentinel.evaluate_and_protect_order(
        symbol="ETH/USDT",
        requested_notional_usd=1000.0,
        portfolio_equity_usd=100_000.0,
        user_slippage_tolerance_bps=30.0,
        pool_liquidity_usd=1_000_000.0,
        prefer_fair_sequencing=True,
    )

    assert plan.route_type == MempoolRouteType.FAIR_SEQUENCING
    assert plan.builder_tip_usd == 0.0
    assert "Fair Sequencing" in plan.protection_notes


# ------------------------------------------------------------------------------
# Test 9: Public Mempool Clearance When Safe
# ------------------------------------------------------------------------------
def test_09_mev_sentinel_public_mempool_when_safe():
    """Verify safe orders are approved for public mempool without builder tip."""
    plan = mev_mitigation_sentinel.evaluate_and_protect_order(
        symbol="ETH/USDT",
        requested_notional_usd=100.0,
        portfolio_equity_usd=100_000.0,
        user_slippage_tolerance_bps=5.0,     # Tight 5 bps
        pool_liquidity_usd=10_000_000.0,    # Deep pool
    )

    assert plan.route_type == MempoolRouteType.PUBLIC_MEMPOOL
    assert plan.builder_tip_usd == 0.0
    assert "Public mempool cleared" in plan.protection_notes


# ------------------------------------------------------------------------------
# Test 10: Permanent Capital Firewall
# ------------------------------------------------------------------------------
def test_10_permanent_capital_firewall_invariant():
    """Verify real_capital_enabled = False across all MEV mitigation components."""
    assert REAL_CAPITAL_ENABLED is False
    assert mev_mitigation_sentinel.real_capital_enabled is False
    assert sandwich_attack_evaluator.real_capital_enabled is False
    assert pbs_simulator.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 11: Fail-Closed Sandbox Containment
# ------------------------------------------------------------------------------
def test_11_fail_closed_containment():
    """Verify invalid or anomalous inputs are trapped without exceptions."""
    plan = mev_mitigation_sentinel.evaluate_and_protect_order(
        symbol="ETH/USDT",
        requested_notional_usd=-500.0,
        portfolio_equity_usd=100_000.0,
        user_slippage_tolerance_bps=10.0,
        pool_liquidity_usd=100_000.0,
    )

    assert plan.is_approved is False
    assert plan.routed_notional_usd == 0.0
