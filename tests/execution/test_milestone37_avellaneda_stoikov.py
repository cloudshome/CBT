"""
tests/execution/test_milestone37_avellaneda_stoikov.py
=====================================================
Adversarial & Unit Test Suite for Milestone 37:
Avellaneda-Stoikov (2008) Market Making & Hawkes Flow Toxicity Engine.

Validates:
1. Reservation price indifference dynamics under inventory skew.
2. Asymmetric bid/ask half-spread calculation and tick-size discretization.
3. Hawkes point process recursive arrival intensity and half-life decay.
4. Trade cascade clustering detection and spread widening defense.
5. Constitutional 1.5% equity cap enforcement (defensive single-sided quoting).
6. Permanent constitutional capital isolation (real_capital_enabled = False).
7. Milestone 18 execution surface preservation (149/149 tests green).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.execution.market_making.avellaneda_stoikov import (
    AvellanedaStoikovModel,
)
from core.execution.market_making.hawkes_intensity import (
    FlowToxicityTier,
    HawkesTradeArrivalEstimator,
)
from core.execution.market_making.market_maker_sentinel import (
    ASMarketMakerSentinel,
)


@pytest.fixture
def as_model() -> AvellanedaStoikovModel:
    return AvellanedaStoikovModel(
        risk_aversion_gamma=0.1,
        book_liquidity_density_kappa=1.5,
        holding_horizon_sec=10.0,
        tick_size=0.10,
    )


@pytest.fixture
def hawkes_estimator() -> HawkesTradeArrivalEstimator:
    return HawkesTradeArrivalEstimator(
        baseline_rate_mu=2.0,
        excitation_alpha=1.2,
        decay_beta=2.0,
    )


@pytest.fixture
def mm_sentinel() -> ASMarketMakerSentinel:
    return ASMarketMakerSentinel(
        symbol="BTC/USDT",
        risk_aversion_gamma=0.1,
        book_liquidity_density_kappa=1.5,
        holding_horizon_sec=10.0,
        tick_size=0.10,
        max_single_position_equity_pct=0.015,
    )


def test_01_reservation_price_inventory_symmetry(as_model: AvellanedaStoikovModel):
    """
    Verifies that reservation price is symmetric around mid:
    - Flat (q=0): r == s
    - Long (q>0): r < s (lowers price to unload)
    - Short (q<0): r > s (raises price to cover)
    """
    mid = 50_000.0
    vol = 0.02

    r_flat = as_model.compute_reservation_price(mid, current_inventory=0.0, volatility_sigma=vol)
    r_long = as_model.compute_reservation_price(mid, current_inventory=1.5, volatility_sigma=vol)
    r_short = as_model.compute_reservation_price(mid, current_inventory=-1.5, volatility_sigma=vol)

    assert r_flat == mid
    assert r_long < mid
    assert r_short > mid

    # Symmetry: (s - r_long) == (r_short - s)
    assert math.isclose(mid - r_long, r_short - mid, rel_tol=1e-6)


def test_02_optimal_spreads_and_quote_asymmetry(as_model: AvellanedaStoikovModel):
    """
    Verifies that inventory skew tightens the unloading side and widens the accumulating side:
    - Long (q>0): delta_ask < delta_bid (Ask tightens, Bid retreats)
    - Short (q<0): delta_bid < delta_ask (Bid tightens, Ask retreats)
    """
    mid = 60_000.0
    vol = 0.02

    quotes_long = as_model.compute_optimal_quotes(
        "BTC/USDT", mid, current_inventory=2.0, volatility_sigma=vol
    )
    quotes_short = as_model.compute_optimal_quotes(
        "BTC/USDT", mid, current_inventory=-2.0, volatility_sigma=vol
    )

    # Long inventory: Ask half-spread is tighter to mid than bid
    assert quotes_long.optimal_half_spread_ask < quotes_long.optimal_half_spread_bid
    # Short inventory: Bid half-spread is tighter to mid than ask
    assert quotes_short.optimal_half_spread_bid < quotes_short.optimal_half_spread_ask


def test_03_discrete_quotes_tick_grid_and_non_crossing(as_model: AvellanedaStoikovModel):
    """
    Verifies that discrete limit quotes are valid tick multiples and non-crossed.
    """
    mid = 65_432.17
    vol = 0.015

    quotes = as_model.compute_optimal_quotes(
        "BTC/USDT", mid, current_inventory=0.5, volatility_sigma=vol
    )

    # Must be integer multiple of tick_size (0.10)
    assert math.isclose(quotes.discrete_ask_price % 0.10, 0.0, abs_tol=1e-5) or math.isclose(
        quotes.discrete_ask_price % 0.10, 0.10, abs_tol=1e-5
    )
    assert math.isclose(quotes.discrete_bid_price % 0.10, 0.0, abs_tol=1e-5) or math.isclose(
        quotes.discrete_bid_price % 0.10, 0.10, abs_tol=1e-5
    )

    # Must have positive spread >= 2 ticks
    spread = quotes.discrete_ask_price - quotes.discrete_bid_price
    assert spread >= (2.0 * as_model.tick_size)
    assert quotes.discrete_ask_price > quotes.mid_price
    assert quotes.discrete_bid_price < quotes.mid_price


def test_04_hawkes_exponential_decay_and_half_life(hawkes_estimator: HawkesTradeArrivalEstimator):
    """
    Verifies that Hawkes arrival intensity jumps on event and decays exponentially
    with calibrated half-life tau_half = ln(2) / beta.
    """
    t0_ns = 1_000_000_000_000  # Arbitrary start
    s0 = hawkes_estimator.record_trade_event(timestamp_ns=t0_ns)

    # After first event, intensity = mu + alpha
    expected_initial = hawkes_estimator.mu + hawkes_estimator.alpha
    assert math.isclose(s0.current_intensity, expected_initial, rel_tol=1e-4)

    # Advance by exact half-life: dt = ln(2) / beta = ln(2) / 2.0 ~ 0.34657 sec
    half_life_ns = int((math.log(2.0) / hawkes_estimator.beta) * 1e9)
    decayed_intensity = hawkes_estimator.get_current_intensity(now_ns=t0_ns + half_life_ns)

    # Excess intensity over baseline should halve: alpha * 0.5
    excess_initial = hawkes_estimator.alpha
    excess_decayed = decayed_intensity - hawkes_estimator.mu
    assert math.isclose(excess_decayed, excess_initial * 0.5, rel_tol=1e-3)


def test_05_hawkes_clustering_triggers_spread_widening(
    hawkes_estimator: HawkesTradeArrivalEstimator,
):
    """
    Verifies that rapid trade cascades cause Hawkes intensity to surge into
    ELEVATED_TOXICITY or CRITICAL_TOXIC_SURGE, triggering spread widening.
    """
    t_ns = 1_000_000_000_000

    # 10 trades in 100ms (10ms apart)
    for _ in range(10):
        t_ns += 10_000_000  # 10ms
        state = hawkes_estimator.record_trade_event(timestamp_ns=t_ns)

    assert state.current_intensity > (hawkes_estimator.mu * hawkes_estimator.moderate_ratio)
    assert state.toxicity_tier in (
        FlowToxicityTier.ELEVATED_TOXICITY,
        FlowToxicityTier.CRITICAL_TOXIC_SURGE,
    )
    assert state.spread_widening_multiplier > 1.0


def test_06_inventory_at_1_5_percent_cap_disables_accumulating_side(
    mm_sentinel: ASMarketMakerSentinel,
):
    """
    Verifies that when inventory reaches the 1.5% equity cap,
    the sentinel suppresses quotes on the accumulating side.
    """
    equity = 100_000.0  # $100k equity -> $1,500 max inventory cap
    mid = 50_000.0
    vol = 0.02

    # Case 1: Safe inventory ($500 notional = 0.5% equity) -> Dual-sided
    q_safe = 500.0 / mid
    d_safe = mm_sentinel.evaluate_quoting_opportunity(equity, mid, q_safe, vol)
    assert d_safe.allowed_sides == ["BUY", "SELL"]
    assert d_safe.is_single_sided_only is False

    # Case 2: Max Long inventory ($1,500 notional = 1.5% equity) -> SELL only
    q_max_long = 1500.0 / mid
    d_long = mm_sentinel.evaluate_quoting_opportunity(equity, mid, q_max_long, vol)
    assert d_long.allowed_sides == ["SELL"]
    assert d_long.is_single_sided_only is True
    assert "Long inventory" in d_long.action_narrative

    # Case 3: Max Short inventory (-$1,500 notional = 1.5% equity) -> BUY only
    q_max_short = -1500.0 / mid
    d_short = mm_sentinel.evaluate_quoting_opportunity(equity, mid, q_max_short, vol)
    assert d_short.allowed_sides == ["BUY"]
    assert d_short.is_single_sided_only is True
    assert "Short inventory" in d_short.action_narrative


def test_07_permanent_capital_isolation_firewall(mm_sentinel: ASMarketMakerSentinel):
    """Verifies that real_capital_enabled = False is enforced across all market making modules."""
    assert mm_sentinel.real_capital_enabled is False
    assert mm_sentinel.pricing_model.real_capital_enabled is False
    assert mm_sentinel.hawkes_estimator.real_capital_enabled is False

    decision = mm_sentinel.evaluate_quoting_opportunity(10_000.0, 50_000.0, 0.0, 0.02)
    assert decision.real_capital_enabled is False
    assert decision.quotes.real_capital_enabled is False


def test_08_milestone18_execution_surface_untouched():
    """Guarantees that Milestone 18 certified execution surface is NOT modified."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    py_exe = str(repo_root / ".venv" / "Scripts" / "python.exe")
    if not Path(py_exe).exists():
        py_exe = sys.executable

    res = subprocess.run(
        [py_exe, "scripts/verify_m18_certification.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Milestone 18 certification invalid:\n{res.stdout}\n{res.stderr}"
    assert "M18 Production Pass remains ACTIVE" in res.stdout
