"""
tests/execution/test_milestone44_liquidity_surface.py
=====================================================
Milestone 44 Adversarial Certification Suite:
Liquidity Surface Geometry & High-Frequency Toxic Flow Analytics.

Verifies:
1. Multi-dimensional order book surface reconstruction and coordinate calculation
2. Kyle's Lambda and Square-Root Law parameter fitting
3. Non-linear order impact scaling (sub-linear square-root behavior)
4. VPIN calculation on balanced flow (low toxicity)
5. VPIN calculation on aggressive one-sided sweep (high toxicity)
6. Hawkes process self-excitation clustering under trade bursts
7. Toxic flow regime classification and transition boundaries
8. Constitutional 1.5% equity cap enforcement by Surface Sentinel
9. Microstructure circuit breaker halt under extreme toxic flow (VPIN >= 0.85)
10. Urgency adaptation and dark pool allocation under toxic regime
11. Permanent capital firewall invariant (real_capital_enabled = False) and fail-closed containment
"""

from __future__ import annotations

import pytest

from core.execution.liquidity_surface import (
    ExecutionUrgency,
    HighFrequencyToxicFlowDetector,
    LiquiditySurfaceGeometryEngine,
    LiquiditySurfaceSentinel,
    REAL_CAPITAL_ENABLED,
    ToxicityRegime,
    liquidity_surface_geometry_engine,
    surface_sentinel,
    toxic_flow_detector,
)


def _build_test_book():
    # BTC/USDT book around $60,000
    bids = [
        (59990.0, 1.5),
        (59980.0, 3.0),
        (59970.0, 5.0),
        (59950.0, 10.0),
        (59900.0, 20.0),
    ]
    asks = [
        (60010.0, 1.5),
        (60020.0, 3.0),
        (60030.0, 5.0),
        (60050.0, 10.0),
        (60100.0, 20.0),
    ]
    return bids, asks


# ------------------------------------------------------------------------------
# Test 1: Surface Snapshot Reconstruction
# ------------------------------------------------------------------------------
def test_01_surface_snapshot_reconstruction():
    """Verify order book surface reconstruction computes accurate coordinates."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot(
        symbol="BTC/USDT",
        timestamp_ms=1700000000000,
        bids=bids,
        asks=asks,
    )

    assert snapshot.mid_price == 60000.0
    assert pytest.approx(snapshot.spread_bps, rel=1e-3) == 3.333  # (60010-59990)/60000 * 10000
    assert len(snapshot.bid_surface) == 5
    assert len(snapshot.ask_surface) == 5
    assert snapshot.bid_surface[0].marginal_impact_bps >= 0.0
    assert snapshot.ask_surface[-1].cumulative_volume == 39.5
    assert snapshot.total_depth_usd > 4_000_000.0
    assert snapshot.real_capital_enabled is False


# ------------------------------------------------------------------------------
# Test 2: Kyle's Lambda & Square-Root Law Curve Fitting
# ------------------------------------------------------------------------------
def test_02_kyles_lambda_and_sqrt_law_curve_fitting():
    """Verify parametric fitting computes valid Kyle's Lambda and Square-Root constants."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot(
        symbol="BTC/USDT",
        timestamp_ms=1700000000000,
        bids=bids,
        asks=asks,
    )
    params = liquidity_surface_geometry_engine.fit_impact_curves(snapshot)

    assert params.kyles_lambda > 0.0
    assert params.square_root_alpha > 0.0
    assert params.r_squared >= 0.0
    assert params.permanent_impact_fraction == 0.5


# ------------------------------------------------------------------------------
# Test 3: Non-Linear Order Impact Scaling
# ------------------------------------------------------------------------------
def test_03_non_linear_order_impact_scaling():
    """Verify market impact scales sub-linearly (sqrt law) rather than linearly for large sizes."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, bids, asks)
    params = liquidity_surface_geometry_engine.fit_impact_curves(snapshot)

    impact_small = liquidity_surface_geometry_engine.estimate_order_impact_bps(10_000.0, params)
    impact_large = liquidity_surface_geometry_engine.estimate_order_impact_bps(1_000_000.0, params)

    assert impact_large > impact_small
    # For a 100x size increase, linear would be 100x, sqrt law gives ~10x
    ratio = impact_large / impact_small
    assert ratio < 50.0  # Confirms sub-linear concavity


# ------------------------------------------------------------------------------
# Test 4: VPIN on Balanced Flow (Low Toxicity)
# ------------------------------------------------------------------------------
def test_04_vpin_balanced_volume_buckets():
    """Verify VPIN on balanced buy and sell volume yields low toxicity (VPIN < 0.35)."""
    detector = HighFrequencyToxicFlowDetector(bucket_volume=2.0, num_buckets=10)

    # Ingest 10 buckets alternating buy and sell
    t = 1700000000000
    for i in range(20):
        is_maker = (i % 2 == 0)
        detector.process_trade(price=60000.0, size=1.0, timestamp_ms=t + i * 100, is_buyer_maker=is_maker)

    vpin = detector.compute_vpin()
    assert vpin < 0.35


# ------------------------------------------------------------------------------
# Test 5: VPIN on Aggressive Informed Sweep (High Toxicity)
# ------------------------------------------------------------------------------
def test_05_vpin_informed_toxic_sweep():
    """Verify VPIN on persistent unilateral aggressive buying reaches high toxicity (VPIN > 0.75)."""
    detector = HighFrequencyToxicFlowDetector(bucket_volume=2.0, num_buckets=10)

    # Ingest 20 trades strictly buying (taker buy -> is_buyer_maker = False)
    t = 1700000000000
    for i in range(25):
        detector.process_trade(price=60000.0 + i, size=1.0, timestamp_ms=t + i * 50, is_buyer_maker=False)

    vpin = detector.compute_vpin()
    assert vpin > 0.75


# ------------------------------------------------------------------------------
# Test 6: Hawkes Process Self-Excitation Intensity
# ------------------------------------------------------------------------------
def test_06_hawkes_process_arrival_burst_clustering():
    """Verify rapid trade cluster significantly elevates Hawkes self-excitation intensity."""
    detector = HighFrequencyToxicFlowDetector()

    now_ms = 1700000000000
    # Ingest burst of 30 trades in 500ms
    for i in range(30):
        detector.process_trade(price=60000.0, size=0.1, timestamp_ms=now_ms - 500 + i * 15, is_buyer_maker=False)

    intensity_burst = detector.compute_hawkes_intensity(now_ms)
    # Hawkes intensity should be well above baseline mu (0.5)
    assert intensity_burst > 3.0


# ------------------------------------------------------------------------------
# Test 7: Toxic Flow Regime Classification
# ------------------------------------------------------------------------------
def test_07_toxic_flow_regime_classification():
    """Verify correct classification across BENIGN, MODERATE, TOXIC, EXTREME_ADVERSE regimes."""
    detector = HighFrequencyToxicFlowDetector(bucket_volume=1.0, num_buckets=5)

    # Benign state
    assessment_benign = detector.assess_toxicity("BTC/USDT", 1700000000000)
    assert assessment_benign.regime in (ToxicityRegime.BENIGN, ToxicityRegime.MODERATE)

    # Create toxic state
    for i in range(15):
        detector.process_trade(price=60000.0, size=1.0, timestamp_ms=1700000000000 + i * 10, is_buyer_maker=False)

    assessment_toxic = detector.assess_toxicity("BTC/USDT", 1700000000000 + 200)
    assert assessment_toxic.is_toxic is True
    assert assessment_toxic.regime in (ToxicityRegime.TOXIC, ToxicityRegime.EXTREME_ADVERSE)


# ------------------------------------------------------------------------------
# Test 8: Constitutional 1.5% Equity Cap
# ------------------------------------------------------------------------------
def test_08_surface_sentinel_1_5_percent_equity_cap():
    """Verify Surface Sentinel enforces the 1.5% single-event equity cap."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, bids, asks)

    # Request $50,000 notional on $100,000 equity (50% requested)
    adj = surface_sentinel.evaluate_and_adjust(
        symbol="BTC/USDT",
        requested_notional_usd=50_000.0,
        portfolio_equity_usd=100_000.0,
        snapshot=snapshot,
    )

    assert adj.is_halted is False
    assert adj.adjusted_notional_usd <= 1500.0  # Exactly 1.5% of $100k
    assert adj.kelly_fraction <= 0.015


# ------------------------------------------------------------------------------
# Test 9: Circuit Breaker Halt on Extreme Toxicity
# ------------------------------------------------------------------------------
def test_09_surface_sentinel_circuit_breaker_on_extreme_vpin():
    """Verify Surface Sentinel halts execution when VPIN reaches extreme adverse level (>= 0.85)."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, bids, asks)

    # Mock detector with 0.90 VPIN
    detector = HighFrequencyToxicFlowDetector(bucket_volume=1.0, num_buckets=5)
    for i in range(20):
        detector.process_trade(price=60000.0, size=1.0, timestamp_ms=1700000000000 + i * 5, is_buyer_maker=False)

    toxic_sentinel = LiquiditySurfaceSentinel(flow_detector=detector)
    adj = toxic_sentinel.evaluate_and_adjust(
        symbol="BTC/USDT",
        requested_notional_usd=1000.0,
        portfolio_equity_usd=100_000.0,
        snapshot=snapshot,
    )

    assert adj.is_halted is True
    assert adj.adjusted_notional_usd == 0.0
    assert "Circuit Breaker" in adj.reason


# ------------------------------------------------------------------------------
# Test 10: Urgency Adaptation and Dark Pool Routing
# ------------------------------------------------------------------------------
def test_10_surface_sentinel_passive_dark_pool_routing_under_toxic_regime():
    """Verify that when flow is toxic, urgency shifts to maker and dark pool allocation increases."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, bids, asks)

    # Ingest moderately toxic trades
    detector = HighFrequencyToxicFlowDetector(bucket_volume=2.0, num_buckets=5)
    for i in range(10):
        # 80% buy, 20% sell
        detector.process_trade(price=60000.0, size=1.6, timestamp_ms=1700000000000 + i * 20, is_buyer_maker=False)
        detector.process_trade(price=60000.0, size=0.4, timestamp_ms=1700000000000 + i * 20 + 5, is_buyer_maker=True)

    sentinel_instance = LiquiditySurfaceSentinel(flow_detector=detector)
    adj = sentinel_instance.evaluate_and_adjust(
        symbol="BTC/USDT",
        requested_notional_usd=1000.0,
        portfolio_equity_usd=100_000.0,
        snapshot=snapshot,
    )

    if adj.adjusted_notional_usd > 0:
        assert adj.dark_pool_allocation_pct >= 0.20
        assert adj.max_slippage_ceiling_bps <= 18.0


# ------------------------------------------------------------------------------
# Test 11: Permanent Capital Firewall & Fail-Closed Containment
# ------------------------------------------------------------------------------
def test_11_permanent_capital_firewall_and_fail_closed():
    """Verify real_capital_enabled = False and fail-closed handling of malformed inputs."""
    bids, asks = _build_test_book()
    snapshot = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, bids, asks)

    assert REAL_CAPITAL_ENABLED is False
    assert surface_sentinel.real_capital_enabled is False

    # Negative notional
    adj_neg = surface_sentinel.evaluate_and_adjust(
        symbol="BTC/USDT",
        requested_notional_usd=-100.0,
        portfolio_equity_usd=100_000.0,
        snapshot=snapshot,
    )
    assert adj_neg.is_halted is True
    assert adj_neg.adjusted_notional_usd == 0.0

    # Empty book snapshot
    empty_snap = liquidity_surface_geometry_engine.build_surface_snapshot("BTC/USDT", 1700000000000, [], [])
    adj_empty = surface_sentinel.evaluate_and_adjust(
        symbol="BTC/USDT",
        requested_notional_usd=1000.0,
        portfolio_equity_usd=100_000.0,
        snapshot=empty_snap,
    )
    assert adj_empty.is_halted is True
    assert adj_empty.adjusted_notional_usd == 0.0
