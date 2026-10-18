"""
core/execution/latency_arb/amm_pool_math.py
===========================================
Milestone 38: Analytical Automated Market Maker (AMM) Mathematics.

Implements exact pricing, liquidity curves, and price impact for:
1. Constant Product AMM (Uniswap v2: x * y = k)
2. Concentrated Liquidity AMM (Uniswap v3: tick spacing, sqrtPriceX96, L)

Mathematical Specifications:
-----------------------------
1. Constant Product:
     (x + dx * (1 - fee)) * (y - dy) = x * y = k
     dy = (y * dx * (1 - fee)) / (x + dx * (1 - fee))
     Effective Execution Price = dy / dx (or dx / dy depending on swap direction)
     Marginal Spot Price = y / x
     Price Impact = |(Effective Price - Spot Price) / Spot Price|

2. Concentrated Liquidity (Uniswap v3):
     Price = 1.0001^tick
     sqrtPrice = 1.0001^(tick / 2)
     Delta x = L * (1 / sqrt(P_lower) - 1 / sqrt(P_upper))
     Delta y = L * (sqrt(P_upper) - sqrt(P_lower))
     Within a tick / single concentrated range:
     P_new = (sqrt(P_current) + dy / L)^2  or  1 / (1 / sqrt(P_current) + dx / L)^2

3. Constitutional Capital Isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class PoolType(StrEnum):
    CONSTANT_PRODUCT_V2 = "CONSTANT_PRODUCT_V2"
    CONCENTRATED_LIQUIDITY_V3 = "CONCENTRATED_LIQUIDITY_V3"


class SwapDirection(StrEnum):
    BUY_BASE_WITH_QUOTE = "BUY_BASE_WITH_QUOTE"  # e.g., Swap USDT -> Buy ETH (In: Quote, Out: Base)
    SELL_BASE_FOR_QUOTE = "SELL_BASE_FOR_QUOTE"  # e.g., Swap ETH -> Get USDT (In: Base, Out: Quote)


@dataclass
class SwapSimulationResult:
    """Detailed analytical output of an AMM swap."""

    pool_type: PoolType
    direction: SwapDirection
    amount_in: float
    amount_out: float
    initial_spot_price: float
    final_spot_price: float
    effective_execution_price: float
    price_impact_bps: float
    fee_paid_quote: float
    fee_tier_bps: float
    real_capital_enabled: bool = False


class ConstantProductPool:
    """
    Uniswap v2 Style Constant Product AMM: x * y = k.
    Base asset: x (e.g., ETH)
    Quote asset: y (e.g., USDT)
    Spot price P = y / x
    """

    def __init__(
        self,
        reserve_base: float,
        reserve_quote: float,
        fee_bps: float = 30.0,  # 30 bps = 0.3% standard v2 fee
    ) -> None:
        if reserve_base <= 0.0 or reserve_quote <= 0.0:
            raise ValueError("Reserves must be strictly positive")
        if fee_bps < 0.0 or fee_bps > 1000.0:
            raise ValueError("fee_bps must be between 0 and 1000 bps (10%)")

        self.reserve_base = reserve_base
        self.reserve_quote = reserve_quote
        self.fee_rate = fee_bps / 10_000.0
        self.fee_bps = fee_bps
        self.real_capital_enabled: bool = False

    @property
    def spot_price(self) -> float:
        """Spot price of base asset in quote terms: P = y / x."""
        return self.reserve_quote / self.reserve_base

    def simulate_swap(
        self,
        direction: SwapDirection,
        amount_in: float,
    ) -> SwapSimulationResult:
        """
        Simulates exact output amount and price impact without state mutation.
        """
        if amount_in <= 0.0:
            raise ValueError("amount_in must be strictly positive")

        x = self.reserve_base
        y = self.reserve_quote
        initial_p = self.spot_price
        gamma_fee = 1.0 - self.fee_rate

        if direction == SwapDirection.BUY_BASE_WITH_QUOTE:
            # Trader inputs quote (dy_in), gets base (dx_out)
            # (x - dx_out) * (y + dy_in * gamma) = x * y
            dy_in = amount_in
            dx_out = (x * dy_in * gamma_fee) / (y + dy_in * gamma_fee)
            final_p = (y + dy_in) / (x - dx_out)
            effective_p = dy_in / dx_out
            fee_paid = dy_in * self.fee_rate
            impact_bps = ((effective_p - initial_p) / initial_p) * 10_000.0
            amt_out = dx_out

        elif direction == SwapDirection.SELL_BASE_FOR_QUOTE:
            # Trader inputs base (dx_in), gets quote (dy_out)
            # (x + dx_in * gamma) * (y - dy_out) = x * y
            dx_in = amount_in
            dy_out = (y * dx_in * gamma_fee) / (x + dx_in * gamma_fee)
            final_p = (y - dy_out) / (x + dx_in)
            effective_p = dy_out / dx_in
            fee_paid = dy_out * self.fee_rate
            impact_bps = ((initial_p - effective_p) / initial_p) * 10_000.0
            amt_out = dy_out

        else:
            raise ValueError(f"Unknown direction: {direction}")

        return SwapSimulationResult(
            pool_type=PoolType.CONSTANT_PRODUCT_V2,
            direction=direction,
            amount_in=amount_in,
            amount_out=amt_out,
            initial_spot_price=initial_p,
            final_spot_price=final_p,
            effective_execution_price=effective_p,
            price_impact_bps=max(0.0, impact_bps),
            fee_paid_quote=fee_paid,
            fee_tier_bps=self.fee_bps,
            real_capital_enabled=False,
        )


class ConcentratedLiquidityPool:
    """
    Uniswap v3 Style Concentrated Liquidity AMM.
    Tick mathematics: P(i) = 1.0001^i
    Liquidity L defines price elasticity inside the active range:
      dy = L * d(sqrt(P))
      dx = -L * d(1 / sqrt(P))
    """

    def __init__(
        self,
        current_tick: int,
        liquidity_L: float,
        fee_bps: float = 5.0,  # 5 bps = 0.05% standard v3 stable/major pool
        tick_lower: int | None = None,
        tick_upper: int | None = None,
    ) -> None:
        if liquidity_L <= 0.0:
            raise ValueError("liquidity_L must be strictly positive")
        if fee_bps < 0.0 or fee_bps > 1000.0:
            raise ValueError("fee_bps must be between 0 and 1000 bps")

        self.current_tick = current_tick
        self.liquidity_L = liquidity_L
        self.fee_rate = fee_bps / 10_000.0
        self.fee_bps = fee_bps
        self.tick_lower = tick_lower if tick_lower is not None else current_tick - 1000
        self.tick_upper = tick_upper if tick_upper is not None else current_tick + 1000
        self.real_capital_enabled: bool = False

    @staticmethod
    def tick_to_price(tick: int) -> float:
        """P = 1.0001^tick."""
        return 1.0001**tick

    @staticmethod
    def price_to_tick(price: float) -> int:
        """tick = round(log(price) / log(1.0001))."""
        if price <= 0.0:
            raise ValueError("Price must be strictly positive")
        return round(math.log(price) / math.log(1.0001))

    @property
    def spot_price(self) -> float:
        """Current pool spot price from current_tick."""
        return self.tick_to_price(self.current_tick)

    def simulate_swap(
        self,
        direction: SwapDirection,
        amount_in: float,
    ) -> SwapSimulationResult:
        """
        Simulates exact output within active concentrated liquidity range.
        dy = L * (sqrt(P_next) - sqrt(P_current))
        dx = L * (1 / sqrt(P_current) - 1 / sqrt(P_next))
        """
        if amount_in <= 0.0:
            raise ValueError("amount_in must be strictly positive")

        p_init = self.spot_price
        sqrt_p_init = math.sqrt(p_init)
        L = self.liquidity_L
        gamma_fee = 1.0 - self.fee_rate
        net_amount_in = amount_in * gamma_fee

        if direction == SwapDirection.BUY_BASE_WITH_QUOTE:
            # Trader inputs quote (amount_in), pushing price UP
            # sqrt_p_next = sqrt_p_init + dy / L
            sqrt_p_next = sqrt_p_init + (net_amount_in / L)
            p_final = sqrt_p_next**2
            # Base received: dx = L * (1 / sqrt_p_init - 1 / sqrt_p_next)
            amt_out = L * (1.0 / sqrt_p_init - 1.0 / sqrt_p_next)
            effective_p = amount_in / amt_out
            fee_paid = amount_in * self.fee_rate
            impact_bps = ((effective_p - p_init) / p_init) * 10_000.0

        elif direction == SwapDirection.SELL_BASE_FOR_QUOTE:
            # Trader inputs base (amount_in), pushing price DOWN
            # 1 / sqrt_p_next = 1 / sqrt_p_init + dx / L
            inv_sqrt_p_next = (1.0 / sqrt_p_init) + (net_amount_in / L)
            sqrt_p_next = 1.0 / inv_sqrt_p_next
            p_final = sqrt_p_next**2
            # Quote received: dy = L * (sqrt_p_init - sqrt_p_next)
            amt_out = L * (sqrt_p_init - sqrt_p_next)
            effective_p = amt_out / amount_in
            fee_paid = amt_out * self.fee_rate
            impact_bps = ((p_init - effective_p) / p_init) * 10_000.0

        else:
            raise ValueError(f"Unknown direction: {direction}")

        return SwapSimulationResult(
            pool_type=PoolType.CONCENTRATED_LIQUIDITY_V3,
            direction=direction,
            amount_in=amount_in,
            amount_out=amt_out,
            initial_spot_price=p_init,
            final_spot_price=p_final,
            effective_execution_price=effective_p,
            price_impact_bps=max(0.0, impact_bps),
            fee_paid_quote=fee_paid,
            fee_tier_bps=self.fee_bps,
            real_capital_enabled=False,
        )
