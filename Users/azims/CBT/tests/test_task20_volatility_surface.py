"""
Integration and quantitative test suite for Task 20.3:
Automated Volatility Surface & Skew Term Structure Model.

Validates:
1. Black-76 pricer, put-call parity, closed-form Greeks (Delta, Gamma, Vega),
   and Newton-Raphson IV inversion solver.
2. Deribit public options feed parser and calibrated baseline chain generator.
3. 25-Delta Skew engine, smile interpolation, and structural regime classification.
4. Constant-maturity ATM IV term structure engine and contango/backwardation metrics.
5. 2D Volatility Surface matrix grid bounds and moneyness resolution.
6. Net Dealer Gamma Exposure (GEX) profile and Max Pain strike solver.
7. Dynamic tail-risk multiplier integration for Half-Kelly position sizing.
8. REST API endpoints (/api/volatility/*) via FastAPI TestClient.
"""

from __future__ import annotations

import math
import time
import pytest
from fastapi.testclient import TestClient

from app import app
from core.volatility.black_scholes import (
    black76_price,
    black76_greeks,
    implied_volatility,
    compute_d1_d2,
    norm_cdf,
    norm_pdf,
)
from core.volatility.models import (
    OptionContract,
    OptionType,
    SkewRegime,
    TermStructureRegime,
    SkewSnapshot,
    TermStructureCurve,
    GEXSnapshot,
)
from core.volatility.options_feed import (
    OptionsDataFeed,
    options_feed,
    parse_deribit_instrument,
    parse_deribit_expiry,
)
from core.volatility.skew_engine import SkewEngine, skew_engine
from core.volatility.term_structure import TermStructureEngine, term_structure_engine
from core.volatility.surface_engine import VolatilitySurfaceEngine, surface_engine
from core.volatility.gex_engine import GEXEngine, gex_engine
from core.volatility.risk_integrator import VolatilityRiskIntegrator, volatility_risk_integrator


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# 1. Black-76 Pricer & Greeks Test Suite
# ============================================================================

class TestBlack76Analytics:
    """Rigorous analytical tests for Black-76 pricer, Greeks, and IV solver."""

    def test_put_call_parity(self):
        """Verify Black-76 satisfies Put-Call Parity: C - P = exp(-r*T) * (F - K)."""
        F = 100000.0
        K = 95000.0
        T = 0.25  # ~3 months
        r = 0.04
        sigma = 0.55

        call_px = black76_price(F, K, T, r, sigma, OptionType.CALL)
        put_px = black76_price(F, K, T, r, sigma, OptionType.PUT)

        expected_diff = math.exp(-r * T) * (F - K)
        actual_diff = call_px - put_px
        assert abs(actual_diff - expected_diff) < 1e-4

    def test_atm_option_pricing(self):
        """Verify ATM option pricing behavior for Call and Put."""
        F = 60000.0
        K = 60000.0
        T = 0.1
        r = 0.0
        sigma = 0.60

        call_px = black76_price(F, K, T, r, sigma, OptionType.CALL)
        put_px = black76_price(F, K, T, r, sigma, OptionType.PUT)

        assert call_px > 0
        assert put_px > 0
        # With r=0 and F=K, call and put prices must be strictly identical
        assert abs(call_px - put_px) < 1e-6

    def test_expired_option_boundary(self):
        """Verify boundary condition when T <= 0 returns intrinsic value."""
        F = 100000.0
        K = 90000.0
        r = 0.05
        sigma = 0.50

        # ITM Call
        call_itm = black76_price(F, K, 0.0, r, sigma, OptionType.CALL)
        assert abs(call_itm - 10000.0) < 1e-6

        # OTM Put
        put_otm = black76_price(F, K, 0.0, r, sigma, OptionType.PUT)
        assert abs(put_otm - 0.0) < 1e-6

    def test_greeks_delta_bounds(self):
        """Verify delta bounds: Call delta in (0, 1), Put delta in (-1, 0)."""
        F = 100000.0
        r = 0.03
        sigma = 0.50
        T = 0.2

        # ATM
        greeks_atm_c = black76_greeks(F, 100000.0, T, r, sigma, OptionType.CALL)
        greeks_atm_p = black76_greeks(F, 100000.0, T, r, sigma, OptionType.PUT)

        assert 0.40 < greeks_atm_c.delta < 0.65
        assert -0.60 < greeks_atm_p.delta < -0.35
        # Call delta - Put delta should equal discount factor exp(-rT)
        assert abs((greeks_atm_c.delta - greeks_atm_p.delta) - math.exp(-r * T)) < 1e-4

        # OTM Call
        greeks_otm_c = black76_greeks(F, 150000.0, T, r, sigma, OptionType.CALL)
        assert 0.0 < greeks_otm_c.delta < 0.25

        # OTM Put
        greeks_otm_p = black76_greeks(F, 70000.0, T, r, sigma, OptionType.PUT)
        assert -0.25 < greeks_otm_p.delta < 0.0

    def test_greeks_gamma_and_vega(self):
        """Verify Gamma and Vega are positive and identical for Call and Put."""
        F = 85000.0
        K = 85000.0
        T = 0.15
        r = 0.02
        sigma = 0.65

        gc = black76_greeks(F, K, T, r, sigma, OptionType.CALL)
        gp = black76_greeks(F, K, T, r, sigma, OptionType.PUT)

        assert gc.gamma > 0
        assert gp.gamma > 0
        assert abs(gc.gamma - gp.gamma) < 1e-8

        assert gc.vega > 0
        assert gp.vega > 0
        assert abs(gc.vega - gp.vega) < 1e-8

    def test_implied_volatility_solver(self):
        """Verify Newton-Raphson recovers known input volatility within tolerance."""
        F = 95000.0
        K = 92000.0
        T = 0.3
        r = 0.04
        true_sigma = 0.5825

        # 1. Test Call inversion
        market_call_px = black76_price(F, K, T, r, true_sigma, OptionType.CALL)
        solved_iv_call = implied_volatility(market_call_px, F, K, T, r, OptionType.CALL)
        assert abs(solved_iv_call - true_sigma) < 1e-4

        # 2. Test Put inversion
        market_put_px = black76_price(F, K, T, r, true_sigma, OptionType.PUT)
        solved_iv_put = implied_volatility(market_put_px, F, K, T, r, OptionType.PUT)
        assert abs(solved_iv_put - true_sigma) < 1e-4


# ============================================================================
# 2. Options Feed & Deribit Instrument Parser
# ============================================================================

class TestOptionsFeed:
    """Verify Deribit contract parsing and fallback options generation."""

    def test_instrument_string_parser(self):
        # BTC-25DEC26-104000-C
        base, exp_ts, strike, opt_type = parse_deribit_instrument("BTC-25DEC26-104000-C")
        assert base == "BTC"
        assert strike == 104000.0
        assert opt_type == OptionType.CALL
        assert exp_ts > 0

        # ETH-28MAR25-3600-P
        base2, exp_ts2, strike2, opt_type2 = parse_deribit_instrument("ETH-28MAR25-3600-P")
        assert base2 == "ETH"
        assert strike2 == 3600.0
        assert opt_type2 == OptionType.PUT

    def test_expiry_parser(self):
        ts = parse_deribit_expiry("25DEC26")
        assert ts > 0

    def test_baseline_calibrated_chain_generation(self):
        feed = OptionsDataFeed()
        now_ms = int(time.time() * 1000)
        chain = feed._generate_calibrated_baseline_chain("BTC", now_ms)
        assert len(chain) > 30

        # Verify all contracts have valid fields
        for c in chain:
            assert c.base_currency == "BTC"
            assert c.strike > 0
            assert c.mark_iv > 0
            assert c.time_to_expiry_years > 0
            assert c.option_type in {OptionType.CALL, OptionType.PUT}

    @pytest.mark.asyncio
    async def test_fetch_options_chain_btc(self):
        chain = await options_feed.fetch_options_chain(symbol="BTC")
        assert len(chain) >= 20
        # Verify both calls and puts are present
        calls = [c for c in chain if c.option_type == OptionType.CALL]
        puts = [c for c in chain if c.option_type == OptionType.PUT]
        assert len(calls) > 0
        assert len(puts) > 0


# ============================================================================
# 3. 25-Delta Skew Engine Test Suite
# ============================================================================

class TestSkewEngine:
    """Verify 25-Delta Skew calculation and structural regime classification."""

    def test_skew_calculation_with_synthetic_chain(self):
        feed = OptionsDataFeed()
        now_ms = int(time.time() * 1000)
        chain = feed._generate_calibrated_baseline_chain("BTC", now_ms)

        engine = SkewEngine()
        snapshot = engine.compute_skew_snapshot(chain, symbol="BTC")

        assert snapshot.symbol == "BTC"
        assert snapshot.underlying_price > 0
        assert isinstance(snapshot.dominant_regime, SkewRegime)
        assert len(snapshot.tenor_points) > 0
        assert 0.40 <= snapshot.tail_risk_multiplier <= 1.05

        # Check tenor skew point attributes
        p = snapshot.tenor_points[0]
        assert p.tenor_days > 0
        assert p.atm_iv > 0
        assert p.put_25d_iv > 0
        assert p.call_25d_iv > 0
        assert isinstance(p.twenty_five_delta_skew, float)

    def test_regime_classification_rules(self):
        """Verify regime classification criteria: DEEP_PUT_SKEW, MODERATE_PUT_SKEW, NEUTRAL_SKEW, CALL_SKEW_PREMIUM."""
        engine = SkewEngine()

        # DEEP_PUT_SKEW: skew >= 0.05
        assert engine._classify_regime(0.06) == SkewRegime.DEEP_PUT_SKEW
        # MODERATE_PUT_SKEW: 0.015 <= skew < 0.05
        assert engine._classify_regime(0.03) == SkewRegime.MODERATE_PUT_SKEW
        # NEUTRAL_SKEW: -0.015 < skew < 0.015
        assert engine._classify_regime(0.005) == SkewRegime.NEUTRAL_SKEW
        # CALL_SKEW_PREMIUM: skew <= -0.015
        assert engine._classify_regime(-0.025) == SkewRegime.CALL_SKEW_PREMIUM


# ============================================================================
# 4. Constant-Maturity Term Structure Engine Test Suite
# ============================================================================

class TestTermStructureEngine:
    """Verify constant-maturity ATM term structure interpolation and slope."""

    def test_term_structure_curve(self):
        feed = OptionsDataFeed()
        now_ms = int(time.time() * 1000)
        chain = feed._generate_calibrated_baseline_chain("BTC", now_ms)

        engine = TermStructureEngine()
        curve = engine.compute_term_structure(chain, symbol="BTC")

        assert len(curve.curve) >= 4
        assert curve.regime in {
            TermStructureRegime.CONTANGO,
            TermStructureRegime.BACKWARDATION,
            TermStructureRegime.FLAT,
        }
        assert isinstance(curve.slope_90d_minus_7d, float)

        # Check standard tenors exist
        tenors = [p.tenor_days for p in curve.curve]
        for standard_tenor in [7, 30, 60, 90]:
            assert standard_tenor in tenors


# ============================================================================
# 5. 2D Volatility Surface Engine Test Suite
# ============================================================================

class TestVolatilitySurfaceEngine:
    """Verify 2D volatility matrix interpolation across moneyness and tenors."""

    def test_surface_grid_dimensions_and_values(self):
        feed = OptionsDataFeed()
        now_ms = int(time.time() * 1000)
        chain = feed._generate_calibrated_baseline_chain("BTC", now_ms)

        engine = VolatilitySurfaceEngine()
        grid = engine.build_surface_grid(chain, symbol="BTC")

        assert len(grid.moneyness_levels) >= 5
        assert len(grid.tenors_days) >= 5
        assert len(grid.surface_matrix) == len(grid.tenors_days)
        assert len(grid.surface_matrix[0]) == len(grid.moneyness_levels)

        # Verify all values in matrix are positive implied vols
        for row in grid.surface_matrix:
            for iv in row:
                assert iv > 10.0  # Matrix stores IV in % (e.g. 52.0%)


# ============================================================================
# 6. Net Dealer GEX & Max Pain Engine Test Suite
# ============================================================================

class TestGEXEngine:
    """Verify Net Dealer Gamma Exposure profile and Max Pain strike solver."""

    def test_gex_and_max_pain(self):
        feed = OptionsDataFeed()
        now_ms = int(time.time() * 1000)
        chain = feed._generate_calibrated_baseline_chain("BTC", now_ms)

        engine = GEXEngine()
        gex_snapshot = engine.compute_gex_snapshot(chain, symbol="BTC")

        assert gex_snapshot.underlying_price > 0
        assert len(gex_snapshot.strikes) > 0
        assert gex_snapshot.max_pain_strike > 0

        # Verify max pain is reasonably close to spot (within 35%)
        spot = gex_snapshot.underlying_price
        assert 0.65 * spot <= gex_snapshot.max_pain_strike <= 1.35 * spot

        # Verify dealer net gamma is numeric
        assert isinstance(gex_snapshot.net_gamma_usd_per_1pct, float)
        assert gex_snapshot.regime in {"POSITIVE_PINNING", "NEGATIVE_EXPLOSIVE"}


# ============================================================================
# 7. Volatility Risk Integrator & Half-Kelly Scaling Test Suite
# ============================================================================

class TestVolatilityRiskIntegrator:
    """Verify dynamic tail-risk multiplier computation for Half-Kelly sizing."""

    def test_tail_risk_multiplier_bounds(self):
        now_ms = int(time.time() * 1000)
        integrator = VolatilityRiskIntegrator()

        # 1. Baseline Calm: Contango + Moderate Skew + Positive GEX
        calm_skew = SkewSnapshot(
            symbol="BTC",
            underlying_price=100000.0,
            timestamp_ms=now_ms,
            dominant_regime=SkewRegime.MODERATE_PUT_SKEW,
            average_skew_25d=0.03,
            tail_risk_multiplier=1.0,
        )
        calm_term = TermStructureCurve(
            symbol="BTC",
            timestamp_ms=now_ms,
            underlying_price=100000.0,
            regime=TermStructureRegime.CONTANGO,
            slope_90d_minus_7d=0.05,
        )
        calm_gex = GEXSnapshot(
            symbol="BTC",
            timestamp_ms=now_ms,
            underlying_price=100000.0,
            net_gamma_usd_per_1pct=50000000.0,
            regime="POSITIVE_PINNING",
            max_pain_strike=98000.0,
            zero_gamma_strike=95000.0,
        )

        res_calm = integrator.evaluate_tail_risk(calm_skew, calm_term, calm_gex)
        assert 0.85 <= res_calm["tail_risk_multiplier"] <= 1.05

        # 2. Extreme Downside Fear: Deep Put Skew + Inverted Backwardation + Negative GEX
        panic_skew = SkewSnapshot(
            symbol="BTC",
            underlying_price=80000.0,
            timestamp_ms=now_ms,
            dominant_regime=SkewRegime.DEEP_PUT_SKEW,
            average_skew_25d=0.09,
            tail_risk_multiplier=0.6,
        )
        panic_term = TermStructureCurve(
            symbol="BTC",
            timestamp_ms=now_ms,
            underlying_price=80000.0,
            regime=TermStructureRegime.BACKWARDATION,
            slope_90d_minus_7d=-0.08,
        )
        panic_gex = GEXSnapshot(
            symbol="BTC",
            timestamp_ms=now_ms,
            underlying_price=80000.0,
            net_gamma_usd_per_1pct=-30000000.0,
            regime="NEGATIVE_EXPLOSIVE",
            max_pain_strike=75000.0,
            zero_gamma_strike=82000.0,
        )

        res_panic = integrator.evaluate_tail_risk(panic_skew, panic_term, panic_gex)
        # Sizing must be attenuated significantly
        assert res_panic["tail_risk_multiplier"] <= 0.60
        assert res_panic["tail_risk_multiplier"] >= 0.40  # Respects safety floor
        assert len(res_panic["risk_flags"]) >= 3


# ============================================================================
# 8. FastAPI Endpoints Integration Test Suite
# ============================================================================

class TestFastAPIVolatilityRoutes:
    """Verify HTTP contracts for all /api/volatility/* endpoints."""

    def test_get_volatility_summary(self, client):
        res = client.get("/api/volatility/summary?symbol=BTC")
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "BTC"
        assert data["underlying_price"] > 0
        assert "skew" in data
        assert "term_structure" in data
        assert "gex" in data
        assert "tail_risk" in data
        assert 0.40 <= data["tail_risk"]["tail_risk_multiplier"] <= 1.05

    def test_get_volatility_surface(self, client):
        res = client.get("/api/volatility/surface?symbol=BTC")
        assert res.status_code == 200
        data = res.json()
        assert "moneyness_levels" in data
        assert "tenors_days" in data
        assert "surface_matrix" in data
        assert len(data["surface_matrix"]) == len(data["tenors_days"])

    def test_get_volatility_skew(self, client):
        res = client.get("/api/volatility/skew?symbol=BTC")
        assert res.status_code == 200
        data = res.json()
        assert "dominant_regime" in data
        assert "tenor_points" in data
        assert "average_skew_25d" in data

    def test_get_volatility_term_structure(self, client):
        res = client.get("/api/volatility/term-structure?symbol=BTC")
        assert res.status_code == 200
        data = res.json()
        assert "curve" in data
        assert "regime" in data
        assert "slope_90d_minus_7d" in data

    def test_get_volatility_gex(self, client):
        res = client.get("/api/volatility/gex?symbol=BTC")
        assert res.status_code == 200
        data = res.json()
        assert "strikes" in data
        assert "max_pain_strike" in data
        assert "net_gamma_usd_per_1pct" in data

    def test_symbol_variations(self, client):
        """Verify endpoints accept pairs like 'BTC/USDT' and 'ETH'."""
        res = client.get("/api/volatility/summary?symbol=BTC/USDT")
        assert res.status_code == 200
        data = res.json()
        assert "BTC" in data["symbol"]

        res_eth = client.get("/api/volatility/summary?symbol=ETH")
        assert res_eth.status_code == 200
        data_eth = res_eth.json()
        assert "ETH" in data_eth["symbol"]
