"""
core/execution/concentrated_amm/lp_analytics.py
==============================================
Milestone 42-C: LP / Concentrated-Liquidity Analytics & Impermanent Loss Hedging.

Architectural Declarations:
---------------------------
1. Microstructure simulation and quantitative research only (NOT an execution engine).
2. Permanent capital firewall: real_capital_enabled = False.
3. Analytical closed-form solutions for position valuation, Greeks (Delta, Gamma),
   impermanent loss profile, and delta-neutral perp hedging requirements.

Mathematical Specifications:
-----------------------------
1. Capital Efficiency Multiplier:
     M = 1 / (1 - (P_a / P_b)^0.25)
2. Closed-Form Valuation V(P):
     - P <= P_a: V(P) = L * P * (1/sqrt(P_a) - 1/sqrt(P_b))
     - P_a < P < P_b: V(P) = L * (2*sqrt(P) - P/sqrt(P_b) - sqrt(P_a))
     - P >= P_b: V(P) = L * (sqrt(P_b) - sqrt(P_a))
3. Greeks:
     - Delta = dV/dP:
         P <= P_a: L * (1/sqrt(P_a) - 1/sqrt(P_b))
         P_a < P < P_b: L * (1/sqrt(P) - 1/sqrt(P_b)) = x(P)
         P >= P_b: 0
     - Gamma = d(Delta)/dP:
         P_a < P < P_b: -L / (2 * P^1.5) < 0 (Short Straddle Gamma)
         Outside range: 0
4. Impermanent Loss IL(P):
     V_hold(P) = x_0 * P + y_0
     IL(P) = (V_lp(P) - V_hold(P)) / V_hold(P)  (<= 0 always)
5. Delta-Neutral Perp Hedge:
     Target Short Perpetual Sizing = -Delta(P) = -x(P)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.execution.concentrated_amm.tick_math import (
    tick_to_price,
)


@dataclass
class HedgeRecommendation:
    """Quantitative recommendation for delta-neutral perpetual futures hedging."""

    current_price: float
    current_position_delta: float
    current_position_gamma: float
    target_hedge_base: float
    current_hedge_base: float
    rebalance_delta_base: float
    needs_rebalance: bool
    rebalance_threshold_pct: float
    real_capital_enabled: bool = False


@dataclass
class LPPositionMetrics:
    """Analytical snapshot of a concentrated liquidity position."""

    lower_price: float
    upper_price: float
    current_price: float
    in_range: bool
    capital_efficiency_multiplier: float
    token0_amount: float
    token1_amount: float
    position_value_usd: float
    hold_value_usd: float
    impermanent_loss_pct: float
    impermanent_loss_bps: float
    position_delta: float
    position_gamma: float
    estimated_fee_apy_pct: float
    real_capital_enabled: bool = False


class ConcentratedLPAnalytics:
    """
    Quantitative analytics and risk management engine for concentrated LP positions.
    """

    def __init__(
        self,
        lower_tick: int,
        upper_tick: int,
        liquidity: int,
        entry_price: float,
        decimals_base: int = 18,
        decimals_quote: int = 6,
    ) -> None:
        if lower_tick >= upper_tick:
            raise ValueError(f"lower_tick ({lower_tick}) must be < upper_tick ({upper_tick})")
        if liquidity <= 0:
            raise ValueError("liquidity must be strictly positive")
        if entry_price <= 0.0:
            raise ValueError("entry_price must be strictly positive")

        self.lower_tick = lower_tick
        self.upper_tick = upper_tick
        self.liquidity = liquidity
        self.entry_price = entry_price
        self.decimals_base = decimals_base
        self.decimals_quote = decimals_quote
        self.real_capital_enabled: bool = False

        self.lower_price = tick_to_price(lower_tick, decimals_base, decimals_quote)
        self.upper_price = tick_to_price(upper_tick, decimals_base, decimals_quote)

        # Baseline entry holdings for hold comparison
        self.x0, self.y0 = self.get_token_amounts(self.entry_price)
        self.v_hold_entry = self.x0 * self.entry_price + self.y0

    @property
    def capital_efficiency_multiplier(self) -> float:
        """
        Analytical capital efficiency multiplier relative to full-range V2:
        M = 1 / (1 - (P_a / P_b)^0.25)
        """
        ratio = self.lower_price / self.upper_price
        return 1.0 / (1.0 - (ratio**0.25))

    def get_token_amounts(self, price: float) -> tuple[float, float]:
        """
        Computes base (token0) and quote (token1) amounts at a given spot price.
        """
        if price <= 0.0:
            raise ValueError("price must be strictly positive")

        p_a = self.lower_price
        p_b = self.upper_price
        sqrt_p = math.sqrt(price)
        sqrt_pa = math.sqrt(p_a)
        sqrt_pb = math.sqrt(p_b)

        # Normalized liquidity scale adjusted for decimals
        # L in token0/token1 units
        l_float = self.liquidity / (10 ** ((self.decimals_base + self.decimals_quote) / 2.0))

        if price <= p_a:
            # 100% token0
            x = l_float * ((1.0 / sqrt_pa) - (1.0 / sqrt_pb))
            y = 0.0
        elif price >= p_b:
            # 100% token1
            x = 0.0
            y = l_float * (sqrt_pb - sqrt_pa)
        else:
            # Mixed in-range
            x = l_float * ((1.0 / sqrt_p) - (1.0 / sqrt_pb))
            y = l_float * (sqrt_p - sqrt_pa)

        return x, y

    def position_value(self, price: float) -> float:
        """Computes total USD value of position at given spot price."""
        x, y = self.get_token_amounts(price)
        return x * price + y

    def delta(self, price: float) -> float:
        """
        Computes position Delta (dV/dP) in base asset units:
        - P <= P_a: x(P_a)
        - P_a < P < P_b: x(P)
        - P >= P_b: 0
        """
        x, _ = self.get_token_amounts(price)
        return x

    def gamma(self, price: float) -> float:
        """
        Computes position Gamma (dDelta/dP = d^2V/dP^2):
        - In-range: -L / (2 * P^1.5) < 0
        - Out-of-range: 0
        """
        if self.lower_price < price < self.upper_price:
            l_float = self.liquidity / (10 ** ((self.decimals_base + self.decimals_quote) / 2.0))
            return -l_float / (2.0 * (price**1.5))
        return 0.0

    def impermanent_loss(self, price: float) -> tuple[float, float]:
        """
        Computes impermanent loss relative to HODL:
        Returns: (il_pct, il_bps) where il_pct <= 0
        """
        v_lp = self.position_value(price)
        v_hold = self.x0 * price + self.y0
        if v_hold <= 0.0:
            return 0.0, 0.0

        il_fraction = (v_lp - v_hold) / v_hold
        il_pct = il_fraction * 100.0
        il_bps = il_fraction * 10_000.0
        return il_pct, il_bps

    def generate_hedge_recommendation(
        self,
        current_price: float,
        current_hedge_base: float,
        rebalance_threshold_pct: float = 0.05,  # 5% delta drift trigger
    ) -> HedgeRecommendation:
        """
        Computes delta-neutral perpetual futures hedge sizing and rebalance trigger.
        Target Hedge Sizing = -Delta(P)
        """
        pos_delta = self.delta(current_price)
        pos_gamma = self.gamma(current_price)
        target_hedge = -pos_delta  # Short perpetual

        rebalance_delta = target_hedge - current_hedge_base
        threshold_abs = max(1e-4, abs(target_hedge) * rebalance_threshold_pct)
        needs_rebal = abs(rebalance_delta) >= threshold_abs

        return HedgeRecommendation(
            current_price=current_price,
            current_position_delta=pos_delta,
            current_position_gamma=pos_gamma,
            target_hedge_base=target_hedge,
            current_hedge_base=current_hedge_base,
            rebalance_delta_base=rebalance_delta,
            needs_rebalance=needs_rebal,
            rebalance_threshold_pct=rebalance_threshold_pct,
            real_capital_enabled=False,
        )

    def estimate_fee_apy(
        self,
        volume_24h_usd: float,
        fee_pips: int,
        total_pool_liquidity: int,
        current_price: float,
    ) -> float:
        """
        Estimates localized 24h fee APY given modeled volume and active liquidity share.
        """
        if total_pool_liquidity <= 0 or self.liquidity <= 0:
            return 0.0

        # Check if in-range
        if not (self.lower_price <= current_price <= self.upper_price):
            return 0.0  # Zero fee accrual when out-of-range

        pos_val = max(1.0, self.position_value(current_price))
        fee_rate = fee_pips / 1_000_000.0
        liquidity_share = min(1.0, self.liquidity / total_pool_liquidity)

        fee_yield_24h = volume_24h_usd * fee_rate * liquidity_share
        annualized_fee = fee_yield_24h * 365.0
        return (annualized_fee / pos_val) * 100.0

    def compute_metrics_snapshot(
        self,
        current_price: float,
        volume_24h_usd: float = 0.0,
        fee_pips: int = 500,
        total_pool_liquidity: int = 0,
    ) -> LPPositionMetrics:
        """Compiles a complete analytical snapshot of the LP position."""
        in_range = self.lower_price <= current_price <= self.upper_price
        x, y = self.get_token_amounts(current_price)
        v_lp = x * current_price + y
        v_hold = self.x0 * current_price + self.y0
        il_pct, il_bps = self.impermanent_loss(current_price)
        pos_delta = self.delta(current_price)
        pos_gamma = self.gamma(current_price)
        fee_apy = self.estimate_fee_apy(
            volume_24h_usd, fee_pips, total_pool_liquidity, current_price
        )

        return LPPositionMetrics(
            lower_price=self.lower_price,
            upper_price=self.upper_price,
            current_price=current_price,
            in_range=in_range,
            capital_efficiency_multiplier=self.capital_efficiency_multiplier,
            token0_amount=x,
            token1_amount=y,
            position_value_usd=v_lp,
            hold_value_usd=v_hold,
            impermanent_loss_pct=il_pct,
            impermanent_loss_bps=il_bps,
            position_delta=pos_delta,
            position_gamma=pos_gamma,
            estimated_fee_apy_pct=fee_apy,
            real_capital_enabled=False,
        )
