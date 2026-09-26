"""
tests/execution/test_milestone33_synthetic_basis.py
===================================================
Adversarial Verification Battery for Milestone 33:
Multi-Venue Synthetic Cross-Arbitrage, Basis Dispersion Engine, and Leg-Risk Fail-Safe.

Mandatory Invariants Tested:
1. Mathematical basis calculation, executable spreads, and annualized carry yields.
2. Cross-venue dispersion matrix across Binance, Bybit, and Hyperliquid.
3. Engle-Granger two-step cointegration and Ornstein-Uhlenbeck half-life calibration.
4. Non-cointegrated random walk rejection.
5. Basis Dislocation Shock circuit breaker (>300 bps).
6. Funding Inversion Gate (rejects toxic inverted carry).
7. Collateral Imbalance Shield (prevents asymmetric margin depletion).
8. Monotonic 1.5% equity risk cap clamping.
9. Two-Phase Commit Dual-Leg routing with reconciled basis.
10. Leg-Risk Fail-Safe: Protective unwind on partial execution failure.
11. Constitutional capital isolation (real_capital_enabled == False permanent).
12. Milestone 18 execution surface isolation (149/149 certified tests untouched).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.execution.strategy_gateway.synthetic_router import (
    DualLegState,
    LegSide,
    SyntheticLegOrder,
    SyntheticOrderRequest,
    SyntheticRouter,
    SyntheticRouterLedger,
)
from core.intelligence.synthetic_basis_engine import (
    BasisMetrics,
    BasisObservation,
    BasisRegime,
    EpistemicTag,
    SyntheticBasisEngine,
)
from core.risk_engine.basis_governor import (
    BasisRiskGovernor,
    VenueMarginSnapshot,
)


@pytest.fixture
def basis_engine() -> SyntheticBasisEngine:
    return SyntheticBasisEngine(rolling_window_size=100, min_cointegration_samples=30)


@pytest.fixture
def risk_governor() -> BasisRiskGovernor:
    return BasisRiskGovernor(
        max_dislocation_bps=300.0,
        max_margin_utilization=0.80,
        max_margin_asymmetry=0.50,
        max_single_trade_loss_pct=0.015,
        max_ou_half_life_hours=72.0,
    )


@pytest.fixture
def synthetic_router(risk_governor: BasisRiskGovernor) -> SyntheticRouter:
    ledger = SyntheticRouterLedger(":memory:")
    return SyntheticRouter(risk_governor=risk_governor, ledger=ledger)


def test_01_basis_calculation_and_annualized_carry_yield(basis_engine: SyntheticBasisEngine):
    """Verifies exact basis math, bid-ask executable spreads, and annualized carry yield."""
    # Spot: bid=100,000, ask=100,010 (mid=100,005)
    # Perp: bid=100,050, ask=100,060 (mid=100,055)
    # Funding: 0.01% per 8h (0.0001)
    obs = BasisObservation(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_bid=100000.0,
        spot_ask=100010.0,
        perp_bid=100050.0,
        perp_ask=100060.0,
        funding_rate=0.0001,
        funding_interval_hours=8.0,
        borrow_rate_annual=0.05,
    )

    metrics = basis_engine.ingest_observation(obs)

    # Spot mid = 100005.0, Perp mid = 100055.0
    # Diff = 50.0. Basis bps = (50 / 100005) * 10,000 = 4.99975 bps
    assert pytest.approx(metrics.spot_mid, 1e-4) == 100005.0
    assert pytest.approx(metrics.perp_mid, 1e-4) == 100055.0
    assert pytest.approx(metrics.raw_basis_bps, 1e-2) == 5.0
    assert metrics.regime == BasisRegime.CONTANGO

    # Executable cash carry: Sell perp at 100,050, Buy spot at 100,010. Spread = +40.0
    expected_cash_carry = ((100050.0 - 100010.0) / 100010.0) * 10000.0
    assert pytest.approx(metrics.executable_cash_carry_bps, 1e-2) == expected_cash_carry

    # Annualized funding yield: 0.0001 * 3 * 365 = 0.1095 (10.95% APR)
    assert pytest.approx(metrics.annualized_funding_yield, 1e-4) == 0.1095
    assert metrics.net_cash_carry_apr > 0.1095
    assert metrics.epistemic_tag == EpistemicTag.INFERENCE


def test_02_cross_venue_dispersion_matrix(basis_engine: SyntheticBasisEngine):
    """Verifies dispersion matrix calculation across Binance, Bybit, and Hyperliquid."""
    observations = [
        BasisObservation(
            symbol="BTC",
            spot_venue="BINANCE_SPOT",
            perp_venue="BINANCE_PERP",
            spot_bid=100000.0,
            spot_ask=100005.0,
            perp_bid=100020.0,
            perp_ask=100025.0,
        ),
        BasisObservation(
            symbol="BTC",
            spot_venue="BYBIT_SPOT",
            perp_venue="BYBIT_PERP",
            spot_bid=100001.0,
            spot_ask=100006.0,
            perp_bid=100030.0,
            perp_ask=100035.0,
        ),
        BasisObservation(
            symbol="BTC",
            spot_venue="BINANCE_SPOT",
            perp_venue="HYPERLIQUID_L1",
            spot_bid=100000.0,
            spot_ask=100005.0,
            perp_bid=100045.0,
            perp_ask=100050.0,
        ),
    ]

    matrix = basis_engine.get_cross_venue_dispersion_matrix("BTC", observations)
    assert len(matrix) == 3
    assert "BINANCE_SPOT:BINANCE_PERP" in matrix
    assert "BYBIT_SPOT:BYBIT_PERP" in matrix
    assert "BINANCE_SPOT:HYPERLIQUID_L1" in matrix

    # Hyperliquid basis should be higher than Binance basis in this scenario
    hl_basis = matrix["BINANCE_SPOT:HYPERLIQUID_L1"].raw_basis_bps
    bn_basis = matrix["BINANCE_SPOT:BINANCE_PERP"].raw_basis_bps
    assert hl_basis > bn_basis


def test_03_engle_granger_cointegration_and_ou_half_life(basis_engine: SyntheticBasisEngine):
    """Verifies Engle-Granger cointegration detection and Ornstein-Uhlenbeck half-life estimation."""
    np.random.seed(42)
    n = 150
    spot_base = 100000.0 + np.cumsum(np.random.normal(0, 50, n))
    # Stationary OU mean-reverting spread: kappa = 0.2, half-life = ln(2)/0.2 = 3.47h
    dt = 1.0
    kappa = 0.2
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = spread[i-1] + kappa * (50.0 - spread[i-1]) * dt + np.random.normal(0, 5)

    perp_series = spot_base + spread

    for i in range(n):
        obs = BasisObservation(
            symbol="BTC",
            spot_venue="BINANCE_SPOT",
            perp_venue="HYPERLIQUID_L1",
            spot_bid=float(spot_base[i] - 1.0),
            spot_ask=float(spot_base[i] + 1.0),
            perp_bid=float(perp_series[i] - 1.0),
            perp_ask=float(perp_series[i] + 1.0),
        )
        basis_engine.ingest_observation(obs)

    res = basis_engine.compute_cointegration("BTC", "BINANCE_SPOT", "HYPERLIQUID_L1", dt_hours=dt)

    assert res.is_cointegrated is True
    assert res.adf_t_stat < -2.86
    assert pytest.approx(res.hedge_ratio_beta, abs=0.05) == 1.0
    assert res.ou_half_life_hours < 10.0  # Fast mean reversion
    assert res.sample_size == n
    assert res.epistemic_tag == EpistemicTag.HYPOTHESIS


def test_04_non_cointegrated_random_walk_rejection(basis_engine: SyntheticBasisEngine):
    """Verifies that independent random walks fail cointegration and return infinite half-life."""
    np.random.seed(123)
    n = 100
    spot_series = 100000.0 + np.cumsum(np.random.normal(0, 50, n))
    perp_series = 100000.0 + np.cumsum(np.random.normal(0, 50, n))  # Independent random walk

    for i in range(n):
        obs = BasisObservation(
            symbol="ETH",
            spot_venue="BYBIT_SPOT",
            perp_venue="BYBIT_PERP",
            spot_bid=float(spot_series[i] - 1.0),
            spot_ask=float(spot_series[i] + 1.0),
            perp_bid=float(perp_series[i] - 1.0),
            perp_ask=float(perp_series[i] + 1.0),
        )
        basis_engine.ingest_observation(obs)

    res = basis_engine.compute_cointegration("ETH", "BYBIT_SPOT", "BYBIT_PERP")
    assert res.is_cointegrated is False
    assert res.adf_t_stat >= -2.86 or res.ou_half_life_hours == float("inf")


def test_05_basis_dislocation_breaker_trips(risk_governor: BasisRiskGovernor):
    """Verifies that an extreme basis dislocation (>300 bps) trips the circuit breaker."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=103500.0,
        raw_basis_bps=350.0,  # 350 bps > 300 bps threshold!
        executable_cash_carry_bps=340.0,
        executable_reverse_carry_bps=-360.0,
        annualized_funding_yield=0.10,
        net_cash_carry_apr=0.135,
        net_reverse_carry_apr=-0.185,
        rolling_mean_basis_bps=10.0,
        rolling_std_basis_bps=5.0,
        z_score=68.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=10000.0, available_margin_usd=40000.0, maintenance_margin_req_usd=5000.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=10000.0, available_margin_usd=40000.0, maintenance_margin_req_usd=5000.0)

    verdict = risk_governor.evaluate_synthetic_trade(
        strategy_id="STRAT_SYNTH_BTC",
        requested_quantity=0.5,
        spot_price=100000.0,
        stop_loss_basis_bps=50.0,
        portfolio_equity_usd=100000.0,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
    )

    assert verdict.is_approved is False
    assert verdict.approved_quantity == 0.0
    assert verdict.circuit_breaker_active is True
    assert any("BASIS_DISLOCATION_SHOCK" in r for r in verdict.rejection_reasons)


def test_06_funding_inversion_rejection(risk_governor: BasisRiskGovernor):
    """Verifies that cash-and-carry is blocked when funding is negative (inverted carry)."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=100020.0,
        raw_basis_bps=2.0,
        executable_cash_carry_bps=1.0,
        executable_reverse_carry_bps=-3.0,
        annualized_funding_yield=-0.08,  # -8% APR inverted funding!
        net_cash_carry_apr=-0.078,
        net_reverse_carry_apr=0.028,
        rolling_mean_basis_bps=2.0,
        rolling_std_basis_bps=1.0,
        z_score=0.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=10000.0, available_margin_usd=40000.0, maintenance_margin_req_usd=5000.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=10000.0, available_margin_usd=40000.0, maintenance_margin_req_usd=5000.0)

    verdict = risk_governor.evaluate_synthetic_trade(
        strategy_id="STRAT_SYNTH_BTC",
        requested_quantity=0.2,
        spot_price=100000.0,
        stop_loss_basis_bps=50.0,
        portfolio_equity_usd=100000.0,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
        trade_type="CASH_AND_CARRY",
    )

    assert verdict.is_approved is False
    assert any("FUNDING_INVERSION_ALERT" in r for r in verdict.rejection_reasons)


def test_07_collateral_imbalance_shield(risk_governor: BasisRiskGovernor):
    """Verifies that asymmetric margin utilization between venues trips the collateral shield."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=100050.0,
        raw_basis_bps=5.0,
        executable_cash_carry_bps=4.0,
        executable_reverse_carry_bps=-6.0,
        annualized_funding_yield=0.10,
        net_cash_carry_apr=0.105,
        net_reverse_carry_apr=-0.155,
        rolling_mean_basis_bps=5.0,
        rolling_std_basis_bps=1.0,
        z_score=0.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    # Spot utilization is 85% (>80% max) and asymmetry is 85% - 20% = 65% (>50% max)
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=42500.0, available_margin_usd=7500.0, maintenance_margin_req_usd=20000.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=10000.0, available_margin_usd=40000.0, maintenance_margin_req_usd=5000.0)

    verdict = risk_governor.evaluate_synthetic_trade(
        strategy_id="STRAT_SYNTH_BTC",
        requested_quantity=0.1,
        spot_price=100000.0,
        stop_loss_basis_bps=50.0,
        portfolio_equity_usd=100000.0,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
    )

    assert verdict.is_approved is False
    assert any("COLLATERAL_IMBALANCE_BREACH" in r for r in verdict.rejection_reasons)


def test_08_equity_cap_1_5_percent_monotonic_clamping(risk_governor: BasisRiskGovernor):
    """Verifies that requested trade size is clamped monotonically to respect the 1.5% equity risk limit."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=100050.0,
        raw_basis_bps=5.0,
        executable_cash_carry_bps=4.0,
        executable_reverse_carry_bps=-6.0,
        annualized_funding_yield=0.10,
        net_cash_carry_apr=0.105,
        net_reverse_carry_apr=-0.155,
        rolling_mean_basis_bps=5.0,
        rolling_std_basis_bps=1.0,
        z_score=0.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)

    # Portfolio Equity = $100,000. Max risk (1.5%) = $1,500.
    # Spot price = $100,000. SL distance = 50 bps (0.0050). Loss per BTC = $500.
    # Max risk quantity = $1,500 / $500 = 3.0 BTC.
    # If strategy requests 10.0 BTC, it must be clamped to 3.0 BTC!
    verdict = risk_governor.evaluate_synthetic_trade(
        strategy_id="STRAT_SYNTH_BTC",
        requested_quantity=10.0,
        spot_price=100000.0,
        stop_loss_basis_bps=50.0,
        portfolio_equity_usd=100000.0,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
    )

    assert verdict.is_approved is True
    assert pytest.approx(verdict.approved_quantity, 1e-4) == 3.0
    assert verdict.approved_quantity < verdict.requested_quantity
    assert any("EQUITY_RISK_CAP_CLAMPED" in r for r in verdict.rejection_reasons)


def test_09_two_phase_commit_atomic_dual_leg_fill(synthetic_router: SyntheticRouter):
    """Verifies successful two-phase atomic dual-leg routing and 4-denominator accounting."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=100050.0,
        raw_basis_bps=5.0,
        executable_cash_carry_bps=4.0,
        executable_reverse_carry_bps=-6.0,
        annualized_funding_yield=0.10,
        net_cash_carry_apr=0.105,
        net_reverse_carry_apr=-0.155,
        rolling_mean_basis_bps=5.0,
        rolling_std_basis_bps=1.0,
        z_score=0.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)

    request = SyntheticOrderRequest(
        synthetic_order_id="SYNTH_ORD_001",
        strategy_id="STRAT_SYNTH_BTC",
        symbol="BTC",
        leg_1=SyntheticLegOrder(
            leg_id="LEG_1_SPOT",
            venue="BINANCE_SPOT",
            symbol="BTC/USDT",
            side=LegSide.BUY,
            target_quantity=0.5,
            limit_price=100005.0,
        ),
        leg_2=SyntheticLegOrder(
            leg_id="LEG_2_PERP",
            venue="HYPERLIQUID_L1",
            symbol="BTC-PERP",
            side=LegSide.SELL,
            target_quantity=0.5,
            limit_price=100055.0,
        ),
        expected_basis_bps=5.0,
    )

    report = synthetic_router.route_dual_leg_order(
        request=request,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
    )

    assert report.state == DualLegState.BOTH_FILLED
    assert report.leg_1_report.status == "FILLED"
    assert report.leg_2_report.status == "FILLED"
    assert pytest.approx(report.net_captured_basis_bps, 1e-2) == 5.0
    assert report.real_capital_enabled is False
    assert report.denominators.is_conserved is True
    assert report.denominators.executed_observations == 1


def test_10_leg_risk_failsafe_protective_unwind(synthetic_router: SyntheticRouter):
    """Verifies that if Leg 1 fills and Leg 2 rejects, the router automatically unwinds Leg 1."""
    metrics = BasisMetrics(
        symbol="BTC",
        spot_venue="BINANCE_SPOT",
        perp_venue="HYPERLIQUID_L1",
        spot_mid=100000.0,
        perp_mid=100050.0,
        raw_basis_bps=5.0,
        executable_cash_carry_bps=4.0,
        executable_reverse_carry_bps=-6.0,
        annualized_funding_yield=0.10,
        net_cash_carry_apr=0.105,
        net_reverse_carry_apr=-0.155,
        rolling_mean_basis_bps=5.0,
        rolling_std_basis_bps=1.0,
        z_score=0.0,
        regime=BasisRegime.CONTANGO,
        timestamp_ns=1000,
    )
    spot_margin = VenueMarginSnapshot(venue="BINANCE_SPOT", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)
    perp_margin = VenueMarginSnapshot(venue="HYPERLIQUID_L1", total_equity_usd=50000.0, used_margin_usd=5000.0, available_margin_usd=45000.0, maintenance_margin_req_usd=2500.0)

    request = SyntheticOrderRequest(
        synthetic_order_id="SYNTH_ORD_FAILSAFE",
        strategy_id="STRAT_SYNTH_BTC",
        symbol="BTC",
        leg_1=SyntheticLegOrder(
            leg_id="LEG_1_SPOT",
            venue="BINANCE_SPOT",
            symbol="BTC/USDT",
            side=LegSide.BUY,
            target_quantity=0.5,
            limit_price=100000.0,
        ),
        leg_2=SyntheticLegOrder(
            leg_id="LEG_2_PERP",
            venue="HYPERLIQUID_L1",
            symbol="BTC-PERP",
            side=LegSide.SELL,
            target_quantity=0.5,
            limit_price=100050.0,
        ),
        expected_basis_bps=5.0,
    )

    # Mock: Leg 1 succeeds, but Leg 2 fails (e.g. rate limit, post-only reject, connection drop)
    def leg_1_mock(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
        return True, 100000.0, 5.0

    def leg_2_mock(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
        return False, 0.0, 0.0

    def unwind_mock(leg: SyntheticLegOrder) -> tuple[bool, float, float]:
        return True, 99990.0, 5.0

    report = synthetic_router.route_dual_leg_order(
        request=request,
        basis_metrics=metrics,
        spot_margin=spot_margin,
        perp_margin=perp_margin,
        leg_1_executor=leg_1_mock,
        leg_2_executor=leg_2_mock,
        unwind_executor=unwind_mock,
    )

    assert report.state == DualLegState.LEG_RISK_FAILSAFE_UNWOUND
    assert report.leg_1_report.status == "FILLED"
    assert report.leg_2_report.status == "PENDING"  # Failed to fill
    assert report.unwind_order_id == "LEG_1_SPOT_UNWIND"
    assert report.unwind_filled_qty == 0.5
    assert report.denominators.is_conserved is True


def test_11_permanent_constitutional_capital_isolation(risk_governor: BasisRiskGovernor):
    """Verifies that real_capital_enabled cannot be enabled under any circumstances."""
    with pytest.raises(ValueError, match="CONSTITUTIONAL VIOLATION"):
        SyntheticRouter(risk_governor=risk_governor, real_capital_enabled=True)


def test_12_milestone18_execution_surface_untouched():
    """Verifies that Milestone 18 certified execution surface is untouched and active."""
    from scripts.verify_m18_certification import check_certified_surface, load_manifest
    manifest = load_manifest()
    exit_code = check_certified_surface(manifest, run_tests_if_dirty=False)
    assert exit_code == 0, "Milestone 18 certification invalidated or surface touched!"

