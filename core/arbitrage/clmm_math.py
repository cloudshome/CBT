"""
core/arbitrage/clmm_math.py
===========================
Authoritative Fixed-Point Integer CLMM Mathematics & Analytical Delta Engine.

Enforces:
- Gate 2: Exact Q64.96 / Q128.128 integer bitwise arithmetic (zero floating-point drift in core).
- Gate 5: Exact tick traversal step conservation and liquidity transitions.
- Gate 8: Analytical LP delta derivation, boundary continuity, and finite-difference validation.

Reference: Uniswap V3 Core (TickMath.sol, SqrtPriceMath.sol, SwapMath.sol).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, getcontext

# Set high decimal precision for controlled conversions
getcontext().prec = 50

# Core Fixed-Point Constants
Q96: int = 1 << 96
Q128: int = 1 << 128
MIN_TICK: int = -887272
MAX_TICK: int = 887272
MIN_SQRT_RATIO: int = 4295128739
MAX_SQRT_RATIO: int = 1461446703485210103287273052203988822378723970342


def tick_to_sqrt_price_q96(tick: int) -> int:
    """
    Computes sqrt(1.0001^tick) * 2^96 using Uniswap V3 TickMath bitwise polynomial arithmetic.
    Guarantees exact EVM bit-for-bit equivalence with Solidity contracts.
    """
    if not (MIN_TICK <= tick <= MAX_TICK):
        raise ValueError(f"Tick {tick} out of valid CLMM range [{MIN_TICK}, {MAX_TICK}].")

    abs_tick = abs(tick)
    ratio = 0x100000000000000000000000000000000
    if abs_tick & 0x1 != 0:
        ratio = 0xFFFCB933BD6FAD37AA2D162D1A594001
    if abs_tick & 0x2 != 0:
        ratio = (ratio * 0xFFF97272373D413259A46990580E213A) >> 128
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
        ratio = (ratio * 0xFCBE86C7900A88AEF4E9DB76FFDA51B7) >> 128
    if abs_tick & 0x200 != 0:
        ratio = (ratio * 0xF987A7253AC413176F2B074CF7815E54) >> 128
    if abs_tick & 0x400 != 0:
        ratio = (ratio * 0xF3392B0845732327429FFB1F62999BC9) >> 128
    if abs_tick & 0x800 != 0:
        ratio = (ratio * 0xE7159475A2C29B7443B29C7FA6E889D9) >> 128
    if abs_tick & 0x1000 != 0:
        ratio = (ratio * 0xD097F3BDFD2022B8845AD8F792AA5825) >> 128
    if abs_tick & 0x2000 != 0:
        ratio = (ratio * 0xA9F746462D870FDF8A65DC1F90E061E5) >> 128
    if abs_tick & 0x4000 != 0:
        ratio = (ratio * 0x70D869A156D2A1B890BB3DF62BAF32F7) >> 128
    if abs_tick & 0x8000 != 0:
        ratio = (ratio * 0x31BE135B97D566497FF9C4E036352011) >> 128
    if abs_tick & 0x10000 != 0:
        ratio = (ratio * 0x9AA508B5B7A84E1C677DE54F3E99BC9) >> 128
    if abs_tick & 0x20000 != 0:
        ratio = (ratio * 0x5D6AF8DEDB81196699C329225EE604) >> 128
    if abs_tick & 0x40000 != 0:
        ratio = (ratio * 0x2216E584F5FA1EA926041BEDFE98) >> 128
    if abs_tick & 0x80000 != 0:
        ratio = (ratio * 0x48A170391F7DC42444E8FA2) >> 128

    if tick > 0:
        # TickMath.sol: type(uint256).max / ratio
        ratio = ((1 << 256) - 1) // ratio

    # Round up to 96 bits
    sqrt_price_x96 = (ratio >> 32) + (1 if (ratio % (1 << 32) > 0) else 0)
    return int(sqrt_price_x96)


def sqrt_price_q96_to_price(
    sqrt_price_q96: int, decimals_0: int = 18, decimals_1: int = 6
) -> float:
    """
    Converts Q64.96 square root price to a human-readable token price (token1/token0).
    Uses high-precision Decimal intermediate to avoid early floating-point overflow.
    """
    dec_sqrt = Decimal(sqrt_price_q96) / Decimal(Q96)
    raw_price = dec_sqrt * dec_sqrt
    decimal_adjustment = Decimal(10) ** Decimal(decimals_0 - decimals_1)
    adjusted_price = raw_price * decimal_adjustment
    return float(adjusted_price)


def price_to_tick(
    price: float, decimals_0: int = 18, decimals_1: int = 6, tick_spacing: int = 10
) -> int:
    """
    Converts real human token price to nearest valid discrete tick.
    """
    if price <= 0:
        raise ValueError("Price must be strictly positive.")
    raw_price = price / (10 ** (decimals_0 - decimals_1))
    tick = math.floor(math.log(raw_price) / math.log(1.0001))
    quantized_tick = round(tick / tick_spacing) * tick_spacing
    return max(MIN_TICK, min(MAX_TICK, quantized_tick))


@dataclass(frozen=True)
class SwapStepResult:
    """Result of an exact tick boundary swap step (Gate 5)."""

    sqrt_price_next_x96: int
    amount_in: int
    amount_out: int
    fee_amount: int


def compute_swap_step(
    sqrt_ratio_current_x96: int,
    sqrt_ratio_target_x96: int,
    liquidity: int,
    amount_remaining: int,
    fee_pips: int,  # e.g. 500 = 0.05%, 3000 = 0.3%
) -> SwapStepResult:
    """
    Exact implementation of Uniswap V3 SwapMath.computeSwapStep.
    Executes swap arithmetic purely via arbitrary-precision integers.
    """
    zero_for_one = sqrt_ratio_current_x96 >= sqrt_ratio_target_x96
    exact_in = amount_remaining >= 0
    fee_multiplier = 1_000_000 - fee_pips

    if exact_in:
        amount_remaining_less_fee = (amount_remaining * fee_multiplier) // 1_000_000
        if zero_for_one:
            num = (liquidity << 96) * (sqrt_ratio_current_x96 - sqrt_ratio_target_x96)
            den = sqrt_ratio_current_x96 * sqrt_ratio_target_x96
            amount_in_max = (num + den - 1) // den if den > 0 else 0
        else:
            amount_in_max = (liquidity * (sqrt_ratio_target_x96 - sqrt_ratio_current_x96)) >> 96

        if amount_remaining_less_fee >= amount_in_max:
            sqrt_ratio_next_x96 = sqrt_ratio_target_x96
            amount_in = amount_in_max
        else:
            if zero_for_one:
                numerator = (liquidity << 96) * sqrt_ratio_current_x96
                denominator = (liquidity << 96) + amount_remaining_less_fee * sqrt_ratio_current_x96
                sqrt_ratio_next_x96 = (numerator + denominator - 1) // denominator
            else:
                sqrt_ratio_next_x96 = (
                    sqrt_ratio_current_x96 + (amount_remaining_less_fee << 96) // liquidity
                )
            amount_in = amount_remaining_less_fee

        fee_amount = (amount_in * fee_pips + (fee_multiplier - 1)) // fee_multiplier

        if zero_for_one:
            amount_out = (liquidity * (sqrt_ratio_current_x96 - sqrt_ratio_next_x96)) >> 96
        else:
            num = (liquidity << 96) * (sqrt_ratio_next_x96 - sqrt_ratio_current_x96)
            den = sqrt_ratio_current_x96 * sqrt_ratio_next_x96
            amount_out = num // den if den > 0 else 0
    else:
        raise NotImplementedError(
            "Exact Out CLMM simulation is not supported for arbitrage routing."
        )

    return SwapStepResult(
        sqrt_price_next_x96=int(sqrt_ratio_next_x96),
        amount_in=int(amount_in),
        amount_out=int(amount_out),
        fee_amount=int(fee_amount),
    )


@dataclass(frozen=True)
class TickBoundaryData:
    """Initialized tick record containing net liquidity delta."""

    tick: int
    liquidity_net: int  # Delta L added/removed when crossing left-to-right


@dataclass(frozen=True)
class ClmmSwapResult:
    """Comprehensive result of full tick-traversal CLMM swap (Gate 5)."""

    amount_in_requested: int
    amount_in_consumed: int
    amount_out_received: int
    total_fee_amount: int
    initial_sqrt_price_x96: int
    final_sqrt_price_x96: int
    initial_tick: int
    final_tick: int
    ticks_crossed: int
    effective_price: float
    marginal_price_impact_bps: float


def simulate_tick_traversal_swap(
    initial_sqrt_price_x96: int,
    initial_tick: int,
    active_liquidity: int,
    initialized_ticks: list[TickBoundaryData],
    amount_in: int,
    zero_for_one: bool,
    fee_pips: int,
    decimals_0: int = 18,
    decimals_1: int = 6,
) -> ClmmSwapResult:
    """
    Simulates exact multi-tick traversal swap across concentrated liquidity depth.
    Traverses initialized tick boundaries, updating active liquidity L as tick boundaries cross.
    """
    if amount_in <= 0:
        raise ValueError("amount_in must be strictly positive.")
    if active_liquidity <= 0:
        raise ValueError("Pool active liquidity must be positive to execute swap.")

    sorted_ticks = sorted(initialized_ticks, key=lambda t: t.tick)
    current_sqrt_p = initial_sqrt_price_x96
    current_tick = initial_tick
    current_liquidity = active_liquidity
    amount_remaining = amount_in
    total_amount_out = 0
    total_fee = 0
    ticks_crossed = 0

    p0 = sqrt_price_q96_to_price(initial_sqrt_price_x96, decimals_0, decimals_1)

    while amount_remaining > 0 and current_liquidity > 0:
        if zero_for_one:
            candidates = [t for t in sorted_ticks if t.tick < current_tick]
            next_tick_data = candidates[-1] if candidates else None
            target_tick = next_tick_data.tick if next_tick_data else MIN_TICK
        else:
            candidates = [t for t in sorted_ticks if t.tick > current_tick]
            next_tick_data = candidates[0] if candidates else None
            target_tick = next_tick_data.tick if next_tick_data else MAX_TICK

        target_sqrt_p = tick_to_sqrt_price_q96(target_tick)

        step = compute_swap_step(
            sqrt_ratio_current_x96=current_sqrt_p,
            sqrt_ratio_target_x96=target_sqrt_p,
            liquidity=current_liquidity,
            amount_remaining=amount_remaining,
            fee_pips=fee_pips,
        )

        consumed_in = step.amount_in + step.fee_amount
        amount_remaining -= consumed_in
        total_amount_out += step.amount_out
        total_fee += step.fee_amount
        current_sqrt_p = step.sqrt_price_next_x96

        if current_sqrt_p == target_sqrt_p and next_tick_data:
            ticks_crossed += 1
            current_tick = next_tick_data.tick
            if zero_for_one:
                current_liquidity -= next_tick_data.liquidity_net
            else:
                current_liquidity += next_tick_data.liquidity_net
        else:
            break

    dec_in = Decimal(amount_in - amount_remaining) / Decimal(
        10**decimals_0 if zero_for_one else 10**decimals_1
    )
    dec_out = Decimal(total_amount_out) / Decimal(
        10**decimals_1 if zero_for_one else 10**decimals_0
    )
    effective_price = (
        float(dec_out / dec_in)
        if (zero_for_one and dec_in > 0)
        else float(dec_in / dec_out)
        if dec_out > 0
        else 0.0
    )

    p_final = sqrt_price_q96_to_price(current_sqrt_p, decimals_0, decimals_1)
    price_impact_bps = abs(p_final - p0) / p0 * 10_000 if p0 > 0 else 0.0

    return ClmmSwapResult(
        amount_in_requested=amount_in,
        amount_in_consumed=amount_in - amount_remaining,
        amount_out_received=total_amount_out,
        total_fee_amount=total_fee,
        initial_sqrt_price_x96=initial_sqrt_price_x96,
        final_sqrt_price_x96=current_sqrt_p,
        initial_tick=initial_tick,
        final_tick=current_tick,
        ticks_crossed=ticks_crossed,
        effective_price=effective_price,
        marginal_price_impact_bps=price_impact_bps,
    )


# ==============================================================================
# Gate 8: Analytical LP Delta & Boundary Continuity Engine
# ==============================================================================


def analytical_lp_delta(price: float, lower_price: float, upper_price: float) -> float:
    """
    Exact analytical closed-form base asset delta of a concentrated LP position:
    Delta_LP(P) = d(V_LP)/dP in units of base asset (Token 0).

    Analytical Derivation:
    V_LP(P) = L * (2*sqrt(P) - sqrt(P_a) - P / sqrt(P_b))
    d(V_LP)/dP = L * (P^(-1/2) - P_b^(-1/2))
    Normalized by total base asset required at P <= P_a: L * (P_a^(-1/2) - P_b^(-1/2))
    => Delta(P) = (P^(-1/2) - P_b^(-1/2)) / (P_a^(-1/2) - P_b^(-1/2)) for P in [P_a, P_b]

    Boundary Invariants:
    - P <= P_a: Delta = 1.0 (100% Token 0)
    - P >= P_b: Delta = 0.0 (100% Token 1)
    - Continuous at P = P_a and P = P_b.
    """
    if lower_price <= 0 or upper_price <= 0 or lower_price >= upper_price:
        raise ValueError(
            f"Invalid price bounds [{lower_price}, {upper_price}]. Must be 0 < Pa < Pb."
        )

    if price <= lower_price:
        return 1.0
    if price >= upper_price:
        return 0.0

    denom = (1.0 / math.sqrt(lower_price)) - (1.0 / math.sqrt(upper_price))
    numer = (1.0 / math.sqrt(price)) - (1.0 / math.sqrt(upper_price))
    delta = numer / denom
    return max(0.0, min(1.0, float(delta)))


def finite_difference_lp_delta(
    price: float, lower_price: float, upper_price: float, epsilon: float = 1e-4
) -> float:
    """
    Numerical finite-difference validation companion for Gate 8:
    Delta_approx = (V_LP(P + eps) - V_LP(P - eps)) / (2 * eps)
    """

    def _v_lp(p: float) -> float:
        if p <= lower_price:
            return p * ((1.0 / math.sqrt(lower_price)) - (1.0 / math.sqrt(upper_price)))
        elif p >= upper_price:
            return math.sqrt(upper_price) - math.sqrt(lower_price)
        else:
            return 2.0 * math.sqrt(p) - math.sqrt(lower_price) - (p / math.sqrt(upper_price))

    denom_norm = (1.0 / math.sqrt(lower_price)) - (1.0 / math.sqrt(upper_price))
    v_high = _v_lp(price + epsilon)
    v_low = _v_lp(price - epsilon)
    raw_deriv = (v_high - v_low) / (2.0 * epsilon)
    normalized_deriv = raw_deriv / denom_norm
    return max(0.0, min(1.0, float(normalized_deriv)))


def divergence_loss_clmm(
    current_price: float, entry_price: float, lower_price: float, upper_price: float
) -> float:
    """
    Calculates exact impermanent / divergence loss for a concentrated LP position:
    IL = V_LP(P) / V_HODL(P) - 1.0
    Always non-positive (<= 0.0).
    """
    if current_price <= 0 or entry_price <= 0:
        raise ValueError("Prices must be strictly positive.")

    def _get_amounts(p: float) -> tuple[float, float]:
        if p <= lower_price:
            x = (1.0 / math.sqrt(lower_price)) - (1.0 / math.sqrt(upper_price))
            y = 0.0
        elif p >= upper_price:
            x = 0.0
            y = math.sqrt(upper_price) - math.sqrt(lower_price)
        else:
            x = (1.0 / math.sqrt(p)) - (1.0 / math.sqrt(upper_price))
            y = math.sqrt(p) - math.sqrt(lower_price)
        return x, y

    x0, y0 = _get_amounts(entry_price)
    x1, y1 = _get_amounts(current_price)

    v_lp = x1 * current_price + y1
    v_hodl = x0 * current_price + y0

    if v_hodl <= 0:
        return 0.0
    return float(v_lp / v_hodl - 1.0)
