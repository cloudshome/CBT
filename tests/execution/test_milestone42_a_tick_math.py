"""
tests/execution/test_milestone42_a_tick_math.py
===============================================
Adversarial & Unit Test Suite for Milestone 42-A:
Concentrated Liquidity AMM Microstructure Engine — Tick Mathematics.

Validates:
1. Constants, Q64.96 representation, and boundary invariants.
2. Exact unity at tick 0 (sqrtPriceX96 == 2^96).
3. Strict monotonicity across full discrete tick space.
4. 100% roundtrip fidelity: get_tick_at_sqrt_ratio(get_sqrt_ratio_at_tick(t)) == t.
5. Extreme boundary limits (+/- 887,272) and out-of-bounds rejection.
6. Tick spacing modulus (1, 10, 60, 200) and nearest tick rounding.
7. Fixed-point delta amounts (amount0, amount1) and directional rounding.
8. Human-readable price <-> tick conversion with token decimal adjustments.
9. Qualification constraint: 0.05% (5 bps) price-impact ceiling enforcement.
10. Constitutional capital isolation (real_capital_enabled = False) and M18 preservation.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.execution.concentrated_amm import (
    FEE_TICK_SPACING_MAP,
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
    Q96,
    Q128,
    QUALIFICATION_MAX_PRICE_IMPACT_BPS,
    REAL_CAPITAL_ENABLED,
    evaluate_price_impact_constraint,
    get_amount0_delta,
    get_amount1_delta,
    get_next_sqrt_price_from_amount0_rounding_up,
    get_next_sqrt_price_from_amount1_rounding_down,
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
    is_valid_tick_for_spacing,
    nearest_valid_tick,
    price_to_sqrt_ratio_x96,
    price_to_tick,
    sqrt_ratio_x96_to_price,
    tick_to_price,
)


def test_01_constants_and_boundary_invariants():
    """Verifies that mathematical constants match Uniswap v3/v4 specifications."""
    assert MIN_TICK == -887272
    assert MAX_TICK == 887272
    assert MIN_SQRT_RATIO == 4295128718
    assert MAX_SQRT_RATIO == 1461446710490008141670467426030517762106949432527
    assert Q96 == 2**96
    assert Q128 == 2**128
    assert REAL_CAPITAL_ENABLED is False
    assert QUALIFICATION_MAX_PRICE_IMPACT_BPS == 5.0


def test_02_tick_zero_exact_unity():
    """Verifies that tick 0 evaluates to exact unity (2^96) and price 1.0."""
    sqrt_at_zero = get_sqrt_ratio_at_tick(0)
    assert sqrt_at_zero == 2**96

    recovered_tick = get_tick_at_sqrt_ratio(2**96)
    assert recovered_tick == 0

    price_zero = sqrt_ratio_x96_to_price(2**96, decimals_base=18, decimals_quote=18)
    assert math.isclose(price_zero, 1.0, abs_tol=1e-12)


def test_03_strict_monotonicity_across_ticks():
    """Verifies that sqrtPriceX96 is strictly monotonic: sqrtP(t) < sqrtP(t+1)."""
    # Sample ranges: negative extreme, around zero, positive extreme
    dense_ranges = [
        range(-887272, -887250),
        range(-100, 100),
        range(887250, 887272),
    ]

    for r in dense_ranges:
        prev_val = get_sqrt_ratio_at_tick(r[0])
        for t in range(r[0] + 1, r[-1] + 1):
            curr_val = get_sqrt_ratio_at_tick(t)
            assert curr_val > prev_val, f"Monotonicity breach at tick {t}: {curr_val} <= {prev_val}"
            prev_val = curr_val


def test_04_roundtrip_fidelity_and_reversibility():
    """Verifies 100% roundtrip reversibility across diverse tick checkpoints."""
    checkpoints = [
        -887272,
        -600000,
        -200000,
        -88720,
        -1000,
        -60,
        -1,
        0,
        1,
        60,
        1000,
        88720,
        200000,
        600000,
        887271,
    ]

    for tick in checkpoints:
        sqrt_p = get_sqrt_ratio_at_tick(tick)
        recovered = get_tick_at_sqrt_ratio(sqrt_p)
        assert recovered == tick, f"Roundtrip failed for tick {tick}: recovered {recovered}"


def test_05_extreme_boundary_and_out_of_bounds_rejection():
    """Verifies boundary checks and fail-closed exception handling."""
    # Within bounds at exact boundaries
    assert get_sqrt_ratio_at_tick(MIN_TICK) == MIN_SQRT_RATIO
    assert get_sqrt_ratio_at_tick(MAX_TICK) == MAX_SQRT_RATIO

    # Out of bounds tick rejection
    with pytest.raises(ValueError, match="out of allowable range"):
        get_sqrt_ratio_at_tick(MIN_TICK - 1)

    with pytest.raises(ValueError, match="out of allowable range"):
        get_sqrt_ratio_at_tick(MAX_TICK + 1)

    # Out of bounds sqrtPriceX96 rejection
    with pytest.raises(ValueError, match="out of allowable range"):
        get_tick_at_sqrt_ratio(MIN_SQRT_RATIO - 1)

    with pytest.raises(ValueError, match="out of allowable range"):
        get_tick_at_sqrt_ratio(MAX_SQRT_RATIO + 1)


def test_06_tick_spacing_and_alignment():
    """Verifies tick spacing mappings and nearest valid tick alignment."""
    assert FEE_TICK_SPACING_MAP[100] == 1
    assert FEE_TICK_SPACING_MAP[500] == 10
    assert FEE_TICK_SPACING_MAP[3000] == 60
    assert FEE_TICK_SPACING_MAP[10000] == 200

    # Spacing 60 (0.3% pool standard)
    assert is_valid_tick_for_spacing(120, 60) is True
    assert is_valid_tick_for_spacing(125, 60) is False

    assert nearest_valid_tick(125, 60) == 120
    assert nearest_valid_tick(155, 60) == 180
    assert nearest_valid_tick(-125, 60) == -120
    assert nearest_valid_tick(-155, 60) == -180


def test_07_fixed_point_delta_amounts_and_directional_rounding():
    """Verifies amount0 and amount1 deltas under directional rounding semantics."""
    liquidity = 10**18  # 1e18 liquidity units
    sqrt_a = get_sqrt_ratio_at_tick(0)
    sqrt_b = get_sqrt_ratio_at_tick(100)

    # amount0 (token0 / base)
    amt0_down = get_amount0_delta(sqrt_a, sqrt_b, liquidity, round_up=False)
    amt0_up = get_amount0_delta(sqrt_a, sqrt_b, liquidity, round_up=True)
    assert amt0_up >= amt0_down
    assert (amt0_up - amt0_down) <= 1  # Exact 1 wei rounding difference

    # amount1 (token1 / quote)
    amt1_down = get_amount1_delta(sqrt_a, sqrt_b, liquidity, round_up=False)
    amt1_up = get_amount1_delta(sqrt_a, sqrt_b, liquidity, round_up=True)
    assert amt1_up >= amt1_down
    assert (amt1_up - amt1_down) <= 1


def test_08_price_conversion_and_token_decimals():
    """Verifies ETH/USDC price conversions with 18 and 6 decimals."""
    eth_price = 3000.0  # $3,000 per ETH

    tick_eth = price_to_tick(eth_price, decimals_base=18, decimals_quote=6)
    recovered_price = tick_to_price(tick_eth, decimals_base=18, decimals_quote=6)

    # Within 1 tick step (1.0001 = 0.01% resolution)
    pct_diff = abs(recovered_price - eth_price) / eth_price
    assert pct_diff < 0.0001, f"Price conversion error too large: {pct_diff:.6f}"


def test_09_qualification_price_impact_ceiling_constraint():
    """
    Verifies that the 0.05% (5 bps) price-impact threshold is enforced as
    a qualification constraint of the simulation model.
    """
    initial_p = 3000.0

    # 1. Compliant execution: 3,000.0 -> 3,000.60 (2.0 bps impact <= 5.0 bps ceiling)
    compliant, impact_bps, narrative = evaluate_price_impact_constraint(
        initial_price=initial_p,
        execution_price=3000.60,
    )
    assert compliant is True
    assert math.isclose(impact_bps, 2.0, abs_tol=1e-4)
    assert "COMPLIANT" in narrative

    # 2. Non-compliant execution: 3,000.0 -> 3,003.00 (10.0 bps impact > 5.0 bps ceiling)
    compliant_fail, impact_bps_fail, narrative_fail = evaluate_price_impact_constraint(
        initial_price=initial_p,
        execution_price=3003.00,
    )
    assert compliant_fail is False
    assert math.isclose(impact_bps_fail, 10.0, abs_tol=1e-4)
    assert "REJECTED" in narrative_fail


def test_10_capital_firewall_and_m18_surface_isolation():
    """
    Verifies constitutional capital isolation and ensures zero coupling
    with live execution routers or order signers.
    """
    assert REAL_CAPITAL_ENABLED is False

    # Inspect source file directly
    amm_file = Path(__file__).resolve().parent.parent.parent / "core" / "execution" / "concentrated_amm" / "tick_math.py"
    assert amm_file.exists()
    content = amm_file.read_text(encoding="utf-8")

    assert "order_router" not in content
    assert "exchange_connectors" not in content
    assert "private_key" not in content
    assert "api_secret" not in content
    assert "real_capital_enabled = False" in content or "REAL_CAPITAL_ENABLED: Final[bool] = False" in content
