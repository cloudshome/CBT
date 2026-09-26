"""
core/execution/concentrated_amm/swap_math.py
===========================================
Milestone 42-B3 & M42-B5: Single Swap-Step Accounting & Directional Symmetry.

Architectural Declarations:
---------------------------
1. Microstructure simulation only (NOT an execution engine).
2. Permanent capital firewall: real_capital_enabled = False.
3. Exact sub-wei integer conservation without floating-point drift.

Mathematical Specifications:
-----------------------------
Uniswap v3 / v4 SwapMath.sol:
- Given current sqrtPriceX96, target sqrtPriceX96, active liquidity, amountRemaining, and feePips:
- ExactIn:
    amountRemainingLessFee = (amountRemaining * (1e6 - feePips)) // 1e6
    Compute amountIn to reach target.
    If amountRemainingLessFee >= amountIn:
        sqrtPriceNext = sqrtPriceTarget
    Else:
        sqrtPriceNext = getNextSqrtPriceFromInput(...)
    Compute actual amountIn, amountOut, and feeAmount.
    Conservation Invariant:
        amountIn + feeAmount <= amountRemaining (exactIn)
"""

from __future__ import annotations

from typing import Final, Tuple

from core.execution.concentrated_amm.tick_math import (
    Q96,
    REAL_CAPITAL_ENABLED,
    get_amount0_delta,
    get_amount1_delta,
    get_next_sqrt_price_from_amount0_rounding_up,
    get_next_sqrt_price_from_amount1_rounding_down,
)

FEE_DENOMINATOR: Final[int] = 1_000_000


def mul_div(a: int, b: int, denominator: int) -> int:
    """Exact full-precision 512-bit integer multiplication and division: (a * b) // denominator."""
    if denominator <= 0:
        raise ZeroDivisionError("denominator must be strictly positive")
    return (a * b) // denominator


def mul_div_rounding_up(a: int, b: int, denominator: int) -> int:
    """Exact full-precision integer multiplication and division with ceiling rounding."""
    if denominator <= 0:
        raise ZeroDivisionError("denominator must be strictly positive")
    product = a * b
    return (product + denominator - 1) // denominator


def get_next_sqrt_price_from_input(
    sqrt_price_current_x96: int,
    liquidity: int,
    amount_in: int,
    zero_for_one: bool,
) -> int:
    """
    Computes next sqrtPriceX96 given an input token delta.
    - zero_for_one (token0 in, price down): rounds up
    - one_for_zero (token1 in, price up): rounds down
    """
    if sqrt_price_current_x96 <= 0:
        raise ValueError("sqrt_price_current_x96 must be strictly positive")
    if liquidity <= 0:
        raise ValueError("liquidity must be strictly positive")

    if zero_for_one:
        return get_next_sqrt_price_from_amount0_rounding_up(
            sqrt_price_current_x96, liquidity, amount_in, add=True
        )
    else:
        return get_next_sqrt_price_from_amount1_rounding_down(
            sqrt_price_current_x96, liquidity, amount_in, add=True
        )


def get_next_sqrt_price_from_output(
    sqrt_price_current_x96: int,
    liquidity: int,
    amount_out: int,
    zero_for_one: bool,
) -> int:
    """
    Computes next sqrtPriceX96 given an output token delta.
    - zero_for_one (token1 out, price down): rounds down
    - one_for_zero (token0 out, price up): rounds up
    """
    if sqrt_price_current_x96 <= 0:
        raise ValueError("sqrt_price_current_x96 must be strictly positive")
    if liquidity <= 0:
        raise ValueError("liquidity must be strictly positive")

    if zero_for_one:
        return get_next_sqrt_price_from_amount1_rounding_down(
            sqrt_price_current_x96, liquidity, amount_out, add=False
        )
    else:
        return get_next_sqrt_price_from_amount0_rounding_up(
            sqrt_price_current_x96, liquidity, amount_out, add=False
        )


def compute_swap_step(
    sqrt_ratio_current_x96: int,
    sqrt_ratio_target_x96: int,
    liquidity: int,
    amount_remaining: int,
    fee_pips: int,
) -> Tuple[int, int, int, int]:
    """
    Computes exact state transitions and quantities for a single swap step.
    
    Args:
        sqrt_ratio_current_x96: Active pool sqrtPriceX96.
        sqrt_ratio_target_x96: Target sqrtPriceX96 (e.g. next initialized tick or limit price).
        liquidity: Active in-range virtual liquidity.
        amount_remaining: Remaining swap amount (positive for exact-in, negative for exact-out).
        fee_pips: Pool fee in hundredths of a pip (e.g. 500 = 5 bps = 0.05%, 3000 = 30 bps = 0.3%).
        
    Returns:
        (sqrt_ratio_next_x96, amount_in, amount_out, fee_amount)
    """
    zero_for_one = sqrt_ratio_current_x96 >= sqrt_ratio_target_x96
    exact_in = amount_remaining >= 0

    if liquidity == 0:
        # Zero liquidity: cannot swap, advance price directly to target without output
        return sqrt_ratio_target_x96, 0, 0, 0

    if exact_in:
        amount_remaining_less_fee = mul_div(
            amount_remaining, FEE_DENOMINATOR - fee_pips, FEE_DENOMINATOR
        )
        amount_in = (
            get_amount0_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, round_up=True)
            if zero_for_one
            else get_amount1_delta(sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, round_up=True)
        )

        if amount_remaining_less_fee >= amount_in:
            sqrt_ratio_next_x96 = sqrt_ratio_target_x96
        else:
            sqrt_ratio_next_x96 = get_next_sqrt_price_from_input(
                sqrt_ratio_current_x96,
                liquidity,
                amount_remaining_less_fee,
                zero_for_one,
            )
    else:
        abs_remaining = abs(amount_remaining)
        amount_out = (
            get_amount1_delta(sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, round_up=False)
            if zero_for_one
            else get_amount0_delta(sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, round_up=False)
        )

        if abs_remaining >= amount_out:
            sqrt_ratio_next_x96 = sqrt_ratio_target_x96
        else:
            sqrt_ratio_next_x96 = get_next_sqrt_price_from_output(
                sqrt_ratio_current_x96,
                liquidity,
                abs_remaining,
                zero_for_one,
            )

    reached_target = sqrt_ratio_next_x96 == sqrt_ratio_target_x96

    if zero_for_one:
        amount_in = (
            amount_in
            if (reached_target and exact_in)
            else get_amount0_delta(sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, round_up=True)
        )
        amount_out = (
            amount_out
            if (reached_target and not exact_in)
            else get_amount1_delta(sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, round_up=False)
        )
    else:
        amount_in = (
            amount_in
            if (reached_target and exact_in)
            else get_amount1_delta(sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, round_up=True)
        )
        amount_out = (
            amount_out
            if (reached_target and not exact_in)
            else get_amount0_delta(sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, round_up=False)
        )

    # Cap amountOut if exact-out
    if not exact_in and amount_out > abs(amount_remaining):
        amount_out = abs(amount_remaining)

    # Compute fee amount
    if exact_in and sqrt_ratio_next_x96 != sqrt_ratio_target_x96:
        # Did not reach target: fee is exact remainder of available input
        fee_amount = amount_remaining - amount_in
    else:
        fee_amount = mul_div_rounding_up(
            amount_in, fee_pips, FEE_DENOMINATOR - fee_pips
        )

    return sqrt_ratio_next_x96, amount_in, amount_out, fee_amount
