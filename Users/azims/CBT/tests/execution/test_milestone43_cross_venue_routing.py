"""
tests/execution/test_milestone43_cross_venue_routing.py
========================================================
Milestone 43 Adversarial Certification Suite:
Advanced Execution Routing & Cross-Venue Arbitrage Analytics.

Verifies:
1. Spatial two-way arbitrage discovery and spread calculation
2. Graph-theoretic Bellman-Ford triangular cycle extraction
3. Rejection of efficient non-arbitrage market rates
4. Single-venue L2 depth walking and slippage modeling
5. Convex multi-venue order waterfilling and price-impact minimization
6. Hybrid CEX and DEX CLMM continuous liquidity routing
7. Latency-decay probability and Hawkes adverse selection modeling
8. Constitutional 1.5% equity cap and Half-Kelly sizing
9. Leg-Risk Fail-Safe abort upon excessive single-leg slippage (>15 bps)
10. Permanent capital firewall invariant (real_capital_enabled = False)
11. Fail-closed exception containment under malformed inputs
"""

from __future__ import annotations

import pytest

from core.execution.cross_venue.cross_venue_sentinel import (
    CrossVenueSentinel,
    cross_venue_sentinel,
)
from core.execution.cross_venue.latency_penalty import latency_penalty_modeler
from core.execution.cross_venue.models import (
    ArbitrageLeg,
    ArbitrageType,
    CrossVenueOpportunity,
    OrderBookLevel,
    VenueDepthSnapshot,
    VenueType,
)
from core.execution.cross_venue.optimal_router import (
    OptimalCrossVenueRouter,
    optimal_router,
)
from core.execution.cross_venue.triangular_arb import (
    RateEdge,
    triangular_arbitrage_engine,
)


def _build_mock_snapshot(
    venue: str,
    venue_type: VenueType,
    best_bid: float,
    best_ask: float,
    fee_bps: float = 7.5,
    latency_ms: float = 25.0,
    depth_size: float = 2.0,
) -> VenueDepthSnapshot:
    """Helper creating a 3-level order book depth ladder."""
    bids = [
        OrderBookLevel(price=best_bid, size=depth_size),
        OrderBookLevel(price=best_bid * 0.9995, size=depth_size * 2),
        OrderBookLevel(price=best_bid * 0.9990, size=depth_size * 4),
    ]
    asks = [
        OrderBookLevel(price=best_ask, size=depth_size),
        OrderBookLevel(price=best_ask * 1.0005, size=depth_size * 2),
        OrderBookLevel(price=best_ask * 1.0010, size=depth_size * 4),
    ]
    return VenueDepthSnapshot(
        venue=venue,
        symbol="BTC/USDT",
        venue_type=venue_type,
        bids=bids,
        asks=asks,
        fee_bps=fee_bps,
        latency_ms=latency_ms,
    )


# ------------------------------------------------------------------------------
# Test 1: Spatial Arbitrage Detection
# ------------------------------------------------------------------------------
def test_01_spatial_arbitrage_discovery_and_spread_math():
    """Verify detection of spatial price dislocations between two venues."""
    # Buy on Binance at 88,000, Sell on Bybit at 88,300 (34.09 bps gross)
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=87980.0, best_ask=88000.0, fee_bps=5.0)
    v2 = _build_mock_snapshot("bybit", VenueType.CEX_PERPETUAL, best_bid=88300.0, best_ask=88320.0, fee_bps=5.0)

    opps = cross_venue_sentinel.detect_spatial_arbitrage(
        symbol="BTC/USDT",
        venues=[v1, v2],
        portfolio_equity_usd=100_000.0,
    )

    assert len(opps) >= 1
    best_opp = opps[0]
    assert best_opp.arb_type == ArbitrageType.SPATIAL_TWO_WAY
    assert best_opp.gross_spread_bps > 30.0
    assert best_opp.net_spread_bps > 20.0  # 34.09 - 10.0 = 24.09 bps net
    assert best_opp.optimal_notional_usd <= 1500.0  # Capped by 1.5% equity cap
    assert best_opp.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 2: Triangular Arbitrage Cycle Detection
# ------------------------------------------------------------------------------
def test_02_triangular_arbitrage_negative_cycle_detection():
    """Verify Bellman-Ford extraction of profitable triangular cycle."""
    # USDT -> BTC -> ETH -> USDT
    # 1. Buy BTC with USDT: 1 USDT = 1 / 88,000 BTC
    # 2. Buy ETH with BTC : 1 BTC = 32.5 ETH (Rate = 32.5)
    # 3. Sell ETH for USDT: 1 ETH = 2,750 USDT (Rate = 2750.0)
    # Product = (1 / 88000) * 32.5 * 2750 = 89375 / 88000 = 1.0156 (+1.56% return!)
    edges = [
        RateEdge("USDT", "BTC", "binance", VenueType.CEX_SPOT, rate=1.0 / 88000.0, fee_bps=5.0, latency_ms=15.0, depth_available=100000.0),
        RateEdge("BTC", "ETH", "binance", VenueType.CEX_SPOT, rate=32.5, fee_bps=5.0, latency_ms=15.0, depth_available=100000.0),
        RateEdge("ETH", "USDT", "bybit", VenueType.CEX_PERPETUAL, rate=2750.0, fee_bps=5.0, latency_ms=20.0, depth_available=100000.0),
    ]

    cycles = triangular_arbitrage_engine.find_arbitrage_cycles(edges, source_currency="USDT")

    assert len(cycles) >= 1
    best_cycle = cycles[0]
    assert len(best_cycle.legs) == 3
    assert best_cycle.gross_spread_bps > 100.0  # ~156 bps gross
    assert best_cycle.net_spread_bps > 90.0    # Net after 15 bps total fees
    assert best_cycle.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 3: Unprofitable Cycle Rejection
# ------------------------------------------------------------------------------
def test_03_triangular_arbitrage_unprofitable_cycle_rejection():
    """Verify efficient market cycle without arbitrage is cleanly rejected."""
    # Efficient triangular loop: Product < 1.0 after fees
    edges = [
        RateEdge("USDT", "BTC", "binance", VenueType.CEX_SPOT, rate=1.0 / 88000.0, fee_bps=10.0, latency_ms=15.0, depth_available=100000.0),
        RateEdge("BTC", "ETH", "binance", VenueType.CEX_SPOT, rate=31.8, fee_bps=10.0, latency_ms=15.0, depth_available=100000.0),
        RateEdge("ETH", "USDT", "bybit", VenueType.CEX_PERPETUAL, rate=2760.0, fee_bps=10.0, latency_ms=20.0, depth_available=100000.0),
    ]

    cycles = triangular_arbitrage_engine.find_arbitrage_cycles(edges, source_currency="USDT")
    assert len(cycles) == 0


# ------------------------------------------------------------------------------
# Test 4: Single-Venue L2 Depth Walking
# ------------------------------------------------------------------------------
def test_04_optimal_router_single_venue_capacity():
    """Verify depth-walking cost computation on single venue."""
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88100.0, fee_bps=7.5)

    m_cost, eff_price, slip = optimal_router.calculate_marginal_buy_cost(
        v1, already_allocated_usd=0.0, incremental_usd=1000.0
    )

    assert eff_price >= 88100.0
    assert slip >= 0.0
    assert m_cost > v1.fee_bps


# ------------------------------------------------------------------------------
# Test 5: Convex Multi-Venue Waterfilling
# ------------------------------------------------------------------------------
def test_05_optimal_router_convex_multi_venue_waterfilling():
    """Verify convex order splitting routes across multiple venues to minimize impact."""
    # Venue 1 has lower initial ask but smaller depth
    # Venue 2 has slightly higher ask but lower fee
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88050.0, fee_bps=10.0, depth_size=0.1)
    v2 = _build_mock_snapshot("bybit", VenueType.CEX_PERPETUAL, best_bid=88040.0, best_ask=88060.0, fee_bps=5.0, depth_size=2.0)

    plan = optimal_router.generate_execution_plan(
        symbol="BTC/USDT",
        action="BUY",
        total_notional_usd=25000.0,
        venue_snapshots=[v1, v2],
    )

    assert plan.risk_gate_passed is True
    assert len(plan.splits) >= 2
    total_allocated = sum(s.allocated_notional_usd for s in plan.splits)
    assert pytest.approx(total_allocated, rel=1e-3) == 25000.0
    assert plan.volume_weighted_price > 88050.0
    assert plan.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 6: Hybrid CEX and DEX CLMM Routing
# ------------------------------------------------------------------------------
def test_06_hybrid_cex_and_dex_clmm_routing():
    """Verify execution plan incorporates DEX CLMM continuous liquidity pools."""
    v_cex = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88080.0, fee_bps=7.5)
    v_dex = _build_mock_snapshot("uniswap_v3", VenueType.DEX_CLMM, best_bid=88010.0, best_ask=88075.0, fee_bps=5.0)

    plan = optimal_router.generate_execution_plan(
        symbol="BTC/USDT",
        action="BUY",
        total_notional_usd=15000.0,
        venue_snapshots=[v_cex, v_dex],
    )

    dex_splits = [s for s in plan.splits if s.venue_type == VenueType.DEX_CLMM]
    cex_splits = [s for s in plan.splits if s.venue_type == VenueType.CEX_SPOT]
    assert len(dex_splits) == 1
    assert len(cex_splits) == 1
    assert plan.total_slippage_bps >= 0.0


# ------------------------------------------------------------------------------
# Test 7: Latency-Decay & Adverse Selection Penalty
# ------------------------------------------------------------------------------
def test_07_latency_decay_probability_and_hurdle_rate():
    """Verify fill probability decays exponentially with latency and flow toxicity."""
    # Fast execution (20 ms)
    fast_eval = latency_penalty_modeler.evaluate_opportunity_survivability(
        total_latency_ms=20.0,
        net_spread_bps=15.0,
        notional_usd=5000.0,
        vpin=0.15,
    )
    assert fast_eval.fill_probability > 0.99
    assert fast_eval.is_favorable is True

    # Slow execution (2000 ms = 2.0s) under high toxicity
    slow_eval = latency_penalty_modeler.evaluate_opportunity_survivability(
        total_latency_ms=2000.0,
        net_spread_bps=5.0,
        notional_usd=5000.0,
        vpin=0.85,
    )
    assert slow_eval.fill_probability < fast_eval.fill_probability
    assert slow_eval.decay_probability > fast_eval.decay_probability


# ------------------------------------------------------------------------------
# Test 8: Constitutional 1.5% Equity Cap
# ------------------------------------------------------------------------------
def test_08_constitutional_1_5_percent_equity_cap():
    """Verify Sentinel clamps any excessive requested notional to 1.5% equity."""
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88050.0)
    v2 = _build_mock_snapshot("bybit", VenueType.CEX_PERPETUAL, best_bid=88040.0, best_ask=88060.0)

    # Request $20,000 on a $100,000 account (20.0% requested)
    res = cross_venue_sentinel.evaluate_and_route(
        symbol="BTC/USDT",
        total_notional_usd=20000.0,
        venue_snapshots=[v1, v2],
        portfolio_equity_usd=100000.0,
    )

    assert res.is_approved is True
    assert res.is_equity_capped is True
    assert res.allocated_notional_usd == 1500.0  # Exactly 1.5% of $100,000
    assert res.kelly_fraction == 0.015


# ------------------------------------------------------------------------------
# Test 9: Leg-Risk Fail-Safe Abort
# ------------------------------------------------------------------------------
def test_09_leg_risk_fail_safe_abort_on_excessive_slippage():
    """Verify Sentinel halts execution when an individual leg trips the slippage ceiling."""
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88050.0)
    v2 = _build_mock_snapshot("bybit", VenueType.CEX_PERPETUAL, best_bid=88040.0, best_ask=88060.0)

    # Mock an opportunity with an unhedged leg exhibiting 25.0 bps slippage (> 15.0 bps threshold)
    bad_opp = CrossVenueOpportunity(
        opportunity_id="opp_bad_slippage",
        arb_type=ArbitrageType.SPATIAL_TWO_WAY,
        legs=[
            ArbitrageLeg("l1", "binance", VenueType.CEX_SPOT, "BUY", "BTC/USDT", 88000.0, 0.1, 5.0, 10.0, slippage_bps=2.0),
            ArbitrageLeg("l2", "bybit", VenueType.CEX_PERPETUAL, "SELL", "BTC/USDT", 88200.0, 0.1, 5.0, 10.0, slippage_bps=22.5),
        ],
        gross_spread_bps=25.0,
        net_spread_bps=15.0,
        optimal_notional_usd=1000.0,
        expected_pnl_usd=1.5,
        decay_probability=0.05,
    )

    res = cross_venue_sentinel.evaluate_and_route(
        symbol="BTC/USDT",
        total_notional_usd=1000.0,
        venue_snapshots=[v1, v2],
        portfolio_equity_usd=100000.0,
        opportunity=bad_opp,
    )

    assert res.is_approved is False
    assert "Leg-Risk Fail-Safe Tripped" in str(res.rejection_reason)
    assert res.allocated_notional_usd == 0.0
    assert res.execution_plan is None


# ------------------------------------------------------------------------------
# Test 10: Permanent Capital Firewall
# ------------------------------------------------------------------------------
def test_10_permanent_capital_firewall_invariant():
    """Verify real_capital_enabled == False across all data structures and outputs."""
    v1 = _build_mock_snapshot("binance", VenueType.CEX_SPOT, best_bid=88000.0, best_ask=88050.0)
    res = cross_venue_sentinel.evaluate_and_route(
        symbol="BTC/USDT",
        total_notional_usd=500.0,
        venue_snapshots=[v1],
        portfolio_equity_usd=50000.0,
    )

    assert cross_venue_sentinel.real_capital_enabled is False
    assert res.real_capital_enabled is False
    assert res.execution_plan.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 11: Fail-Closed Sandbox Containment
# ------------------------------------------------------------------------------
def test_11_fail_closed_sandbox_containment():
    """Verify unhandled anomalies are trapped by sandbox without crashing."""
    # Pass completely empty list and corrupted snapshot
    res = cross_venue_sentinel.evaluate_and_route(
        symbol="BTC/USDT",
        total_notional_usd=-500.0,
        venue_snapshots=[],
    )

    assert res.is_approved is False
    assert res.allocated_notional_usd == 0.0
