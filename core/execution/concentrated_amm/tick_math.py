"""
core/execution/concentrated_amm/tick_math.py
============================================
Milestone 42-A: Concentrated Liquidity AMM Microstructure Engine — Tick Mathematics.

Architectural Distinctions & Constraints:
-----------------------------------------
1. MICROSTRUCTURE SIMULATION ONLY:
   M42 is strictly a microstructure simulation and quantitative research engine,
   NOT an AMM execution engine. It does not move capital, sign transactions,
   or dispatch calldata.
2. PERMANENT CAPITAL ISOLATION:
   real_capital_enabled = False is permanently hardcoded across all structures.
3. QUALIFICATION CONSTRAINT:
   QUALIFICATION_MAX_PRICE_IMPACT_BPS = 5.0 (0.05% maximum price impact ceiling).
   This is a qualification constraint of the simulation model; scenarios where
   modeled impact exceeds this ceiling are rejected/flagged.

Mathematical Specifications:
-----------------------------
Uniswap v3 / v4 Q64.96 Fixed-Point Tick Mathematics:
- Base: 1.0001
- P(i) = 1.0001^i
- sqrtP(i) = 1.0001^(i / 2)
- Q96 = 2^96 = 79228162514264337593543950336
- sqrtPriceX96 = sqrtP(i) * 2^96
- MIN_TICK = -887272
- MAX_TICK = 887272
- MIN_SQRT_RATIO = 4295128718
- MAX_SQRT_RATIO = 1461446710490008141670467426030517762106949432527
"""

from __future__ import annotations

import math
from typing import Final, Tuple

# Permanent capital firewall
REAL_CAPITAL_ENABLED: Final[bool] = False

# Maximum price impact qualification ceiling (0.05% = 5 bps)
QUALIFICATION_MAX_PRICE_IMPACT_BPS: Final[float] = 5.0

# Uniswap v3/v4 boundary constants
MIN_TICK: Final[int] = -887272
MAX_TICK: Final[int] = 887272

Q32: Final[int] = 1 << 32
Q96: Final[int] = 1 << 96
Q128: Final[int] = 1 << 128
MAX_UINT256: Final[int] = (1 << 256) - 1

MIN_SQRT_RATIO: Final[int] = 4295128718
MAX_SQRT_RATIO: Final[int] = 1461446710490008141670467426030517762106949432527

# Fee Tier to Tick Spacing Mapping
FEE_TICK_SPACING_MAP: Final[dict[int, int]] = {
    100: 1,     # 1 bps (0.01%) -> spacing 1
    500: 10,    # 5 bps (0.05%) -> spacing 10
    3000: 60,   # 30 bps (0.30%) -> spacing 60
    10000: 200, # 100 bps (1.00%) -> spacing 200
}


def get_sqrt_ratio_at_tick(tick: int) -> int:
    """
    Computes exact Q64.96 sqrt(price) for a given discrete tick index.
    Implements the bitwise expansion polynomial from Uniswap v3/v4 TickMath.sol.
    
    Returns:
        sqrtPriceX96 as uint160 integer (represented as Python int).
    Raises:
        ValueError if tick is outside [MIN_TICK, MAX_TICK].
    """
    if not (MIN_TICK <= tick <= MAX_TICK):
        raise ValueError(f"Tick {tick} is out of allowable range [{MIN_TICK}, {MAX_TICK}]")

    abs_tick = abs(tick)
    ratio = (
        0xFFFCB933BD6FAD37AA2D162D1A594001
        if (abs_tick & 0x1 != 0)
        else 0x100000000000000000000000000000000
    )

    if abs_tick & 0x2 != 0:
        ratio = (ratio * 0xFFF97272373D413259A46990570E21B7) >> 128
    if abs_tick & 0x4 != 0:
        ratio = (ratio * 0xFFF2E50F5F656932EF12357CF3C7FDCC) >> 128
    if abs_tick & 0x8 != 0:
        ratio = (ratio * 0xFFE5CACA7E10E4E61C3624EAA0941CD0) >> 128
    if abs_tick & 0x10 != 0:
        ratio = (ratio * 0xFFCB9843D60F6159C9DB58835C926644) >> 128
    if abs_tick & 0x20 != 0:
        ratio = (ratio * 0xFF973B41FA98C081472E6896DFB254C0) >> 128
    if abs_tick & 0x40 != 0:
        ratio = (ratio * 0xFF2EA16466C96A3843EC78B326B52861) >> 128
    if abs_tick & 0x80 != 0:
        ratio = (ratio * 0xFE5DEE046A99A2A811C461F1969C3053) >> 128
    if abs_tick & 0x100 != 0:
        ratio = (ratio * 0xFCBE86C7900A88AEDCFFC83B479AA3A4) >> 128
    if abs_tick & 0x200 != 0:
        ratio = (ratio * 0xF987A7253AC413176F2B074CF7815E54) >> 128
    if abs_tick & 0x400 != 0:
        ratio = (ratio * 0xF3392B0822B70005940C7A398E4B70F3) >> 128
    if abs_tick & 0x800 != 0:
        ratio = (ratio * 0xE7159475A2C29B7443B29C7FA6E889D9) >> 128
    if abs_tick & 0x1000 != 0:
        ratio = (ratio * 0xD097F3BDFD2022B8845AD8F792AA5825) >> 128
    if abs_tick & 0x2000 != 0:
        ratio = (ratio * 0xA9F746462D870FDF8A65DC1F90E061E5) >> 128
    if abs_tick & 0x4000 != 0:
        ratio = (ratio * 0x70D869A156D2A1B890BB3DF62BAF32F7) >> 128
    if abs_tick & 0x8000 != 0:
        ratio = (ratio * 0x31BE135B97D08FD981231505542FCFA6) >> 128
    if abs_tick & 0x10000 != 0:
        ratio = (ratio * 0x9AA508B5B7A84E1C677DE54F0099BC8) >> 128
    if abs_tick & 0x20000 != 0:
        ratio = (ratio * 0x5D6AF8DEDB81196699C329225EE604) >> 128
    if abs_tick & 0x40000 != 0:
        ratio = (ratio * 0x2216E584F5FA1EA926041BEDFE98) >> 128
    if abs_tick & 0x80000 != 0:
        ratio = (ratio * 0x48A170391F7DC42444E8FA2) >> 128

    if tick > 0:
        ratio = MAX_UINT256 // ratio

    # Divide by 2^32 rounding up to go from Q128.128 to Q128.96
    sqrt_price_x96 = (ratio >> 32) + (1 if (ratio % Q32 != 0) else 0)
    return sqrt_price_x96


def get_tick_at_sqrt_ratio(sqrt_ratio_x96: int) -> int:
    """
    Computes exact discrete tick index for a given Q64.96 sqrt(price).
    Guarantees that get_sqrt_ratio_at_tick(tick) <= sqrt_ratio_x96 < get_sqrt_ratio_at_tick(tick + 1).
    
    Returns:
        tick as int in range [MIN_TICK, MAX_TICK].
    Raises:
        ValueError if sqrt_ratio_x96 is outside [MIN_SQRT_RATIO, MAX_SQRT_RATIO].
    """
    if not (MIN_SQRT_RATIO <= sqrt_ratio_x96 <= MAX_SQRT_RATIO):
        raise ValueError(
            f"sqrtPriceX96 {sqrt_ratio_x96} is out of allowable range [{MIN_SQRT_RATIO}, {MAX_SQRT_RATIO}]"
        )

    # Initial approximation via double-precision float logarithm
    ratio_f = sqrt_ratio_x96 / Q96
    approx_tick = int(math.floor(2.0 * math.log(ratio_f) / math.log(1.0001)))
    approx_tick = max(MIN_TICK, min(MAX_TICK - 1, approx_tick))

    # Constant-time local search refinement
    while approx_tick < MAX_TICK and get_sqrt_ratio_at_tick(approx_tick + 1) <= sqrt_ratio_x96:
        approx_tick += 1
    while approx_tick > MIN_TICK and get_sqrt_ratio_at_tick(approx_tick) > sqrt_ratio_x96:
        approx_tick -= 1

    return approx_tick


def is_valid_tick_for_spacing(tick: int, tick_spacing: int) -> bool:
    """Checks whether a tick satisfies the spacing modulus."""
    if tick_spacing <= 0:
        raise ValueError("tick_spacing must be strictly positive")
    return (tick % tick_spacing) == 0


def nearest_valid_tick(tick: int, tick_spacing: int) -> int:
    """Rounds a tick to the nearest valid tick satisfying tick_spacing."""
    if tick_spacing <= 0:
        raise ValueError("tick_spacing must be strictly positive")
    remainder = tick % tick_spacing
    if remainder == 0:
        return tick
    rounded = round(tick / tick_spacing) * tick_spacing
    return max(MIN_TICK, min(MAX_TICK, rounded))


def sqrt_ratio_x96_to_price(
    sqrt_ratio_x96: int,
    decimals_base: int = 18,
    decimals_quote: int = 6,
) -> float:
    """
    Converts Q64.96 sqrt(price) to human-readable price adjusted for token decimals.
    Price = (sqrtPriceX96 / 2^96)^2 * 10^(decimals_base - decimals_quote)
    """
    ratio = sqrt_ratio_x96 / Q96
    raw_price = ratio * ratio
    decimal_adjustment = 10 ** (decimals_base - decimals_quote)
    return raw_price * decimal_adjustment


def price_to_sqrt_ratio_x96(
    price: float,
    decimals_base: int = 18,
    decimals_quote: int = 6,
) -> int:
    """
    Converts human-readable price to Q64.96 sqrt(price).
    """
    if price <= 0.0:
        raise ValueError("Price must be strictly positive")
    decimal_adjustment = 10 ** (decimals_base - decimals_quote)
    raw_price = price / decimal_adjustment
    ratio = math.sqrt(raw_price)
    return int(ratio * Q96)


def tick_to_price(
    tick: int,
    decimals_base: int = 18,
    decimals_quote: int = 6,
) -> float:
    """Converts a tick index directly to human-readable price."""
    sqrt_ratio = get_sqrt_ratio_at_tick(tick)
    return sqrt_ratio_x96_to_price(sqrt_ratio, decimals_base, decimals_quote)


def price_to_tick(
    price: float,
    decimals_base: int = 18,
    decimals_quote: int = 6,
) -> int:
    """Converts a human-readable price directly to discrete tick index."""
    sqrt_ratio = price_to_sqrt_ratio_x96(price, decimals_base, decimals_quote)
    return get_tick_at_sqrt_ratio(sqrt_ratio)


def get_amount0_delta(
    sqrt_ratio_a_x96: int,
    sqrt_ratio_b_x96: int,
    liquidity: int,
    round_up: bool = False,
) -> int:
    """
    Computes token0 amount delta for a price change between sqrtRatioA and sqrtRatioB:
    Delta x = L * (sqrt(P_b) - sqrt(P_a)) / (sqrt(P_b) * sqrt(P_a))
    """
    if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
        sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96

    if sqrt_ratio_a_x96 <= 0:
        raise ValueError("sqrt_ratio_a_x96 must be strictly positive")

    numerator1 = liquidity << 96
    numerator2 = sqrt_ratio_b_x96 - sqrt_ratio_a_x96

    if round_up:
        # div_round_up(numerator1 * numerator2 / sqrt_ratio_b_x96, sqrt_ratio_a_x96)
        num = (numerator1 * numerator2)
        den = (sqrt_ratio_b_x96 * sqrt_ratio_a_x96)
        return (num + den - 1) // den
    else:
        return (numerator1 * numerator2) // (sqrt_ratio_b_x96 * sqrt_ratio_a_x96)


def get_amount1_delta(
    sqrt_ratio_a_x96: int,
    sqrt_ratio_b_x96: int,
    liquidity: int,
    round_up: bool = False,
) -> int:
    """
    Computes token1 amount delta for a price change between sqrtRatioA and sqrtRatioB:
    Delta y = L * (sqrt(P_b) - sqrt(P_a)) / 2^96
    """
    if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
        sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96

    diff = sqrt_ratio_b_x96 - sqrt_ratio_a_x96
    prod = liquidity * diff

    if round_up:
        return (prod + Q96 - 1) >> 96
    else:
        return prod >> 96


def get_next_sqrt_price_from_amount0_rounding_up(
    sqrt_p_x96: int,
    liquidity: int,
    amount: int,
    add: bool,
) -> int:
    """
    Computes next sqrtPriceX96 given token0 input or output delta, rounding up.
    """
    if amount == 0:
        return sqrt_p_x96

    numerator1 = liquidity << 96
    if add:
        product = amount * sqrt_p_x96
        if product // amount == sqrt_p_x96:
            denominator = numerator1 + product
            if denominator >= numerator1:
                return (numerator1 * sqrt_p_x96 + denominator - 1) // denominator
        return (numerator1 + (numerator1 // sqrt_p_x96) + amount - 1) // ((numerator1 // sqrt_p_x96) + amount)
    else:
        product = amount * sqrt_p_x96
        denominator = numerator1 - product
        return (numerator1 * sqrt_p_x96 + denominator - 1) // denominator


def get_next_sqrt_price_from_amount1_rounding_down(
    sqrt_p_x96: int,
    liquidity: int,
    amount: int,
    add: bool,
) -> int:
    """
    Computes next sqrtPriceX96 given token1 input or output delta, rounding down.
    """
    if add:
        quotient = (amount << 96) // liquidity
        return sqrt_p_x96 + quotient
    else:
        quotient = (amount << 96 + liquidity - 1) // liquidity
        return sqrt_p_x96 - quotient


def evaluate_price_impact_constraint(
    initial_price: float,
    execution_price: float,
    max_allowed_impact_bps: float = QUALIFICATION_MAX_PRICE_IMPACT_BPS,
) -> Tuple[bool, float, str]:
    """
    Evaluates whether simulated trade satisfies the qualification price-impact constraint.
    Returns: (is_compliant, impact_bps, rejection_narrative)
    """
    if initial_price <= 0.0 or execution_price <= 0.0:
        return False, 0.0, "Invalid non-positive price in impact evaluation"

    impact_bps = abs(execution_price - initial_price) / initial_price * 10_000.0
    is_compliant = impact_bps <= max_allowed_impact_bps
    if is_compliant:
        narrative = f"Price impact {impact_bps:.2f} bps <= {max_allowed_impact_bps:.2f} bps ceiling (COMPLIANT)"
    else:
        narrative = f"REJECTED: Price impact {impact_bps:.2f} bps exceeds qualification constraint ({max_allowed_impact_bps:.2f} bps ceiling)"

    return is_compliant, impact_bps, narrative
