"""
core/execution/market_making/avellaneda_stoikov.py
==================================================
Milestone 37: Avellaneda-Stoikov (2008) High-Frequency Market Making Engine.

Mathematical Specifications:
-----------------------------
1. Reservation Price (Indifference Price) r(s, q, t):
     r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
   - When q > 0 (long inventory): r < s (lowers reservation price to attract buyers on ask)
   - When q < 0 (short inventory): r > s (raises reservation price to attract sellers on bid)
   - When q = 0 (flat): r = s

2. Optimal Bid and Ask Half-Spreads (delta^a, delta^b):
     spread* = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / kappa)
     delta^a = (r - s) / 2 + (1 / gamma) * ln(1 + gamma / kappa) + (1 / 2) * gamma * sigma^2 * (T - t)
     delta^b = (s - r) / 2 + (1 / gamma) * ln(1 + gamma / kappa) + (1 / 2) * gamma * sigma^2 * (T - t)
     raw_ask = s + delta^a
     raw_bid = s - delta^b

3. Microstructure Discretization & Spread Floor:
     discrete_ask = ceil(raw_ask / tick_size) * tick_size
     discrete_bid = floor(raw_bid / tick_size) * tick_size
     Guarantees discrete_ask - discrete_bid >= 2 * tick_size (non-crossed, positive spread).

4. Non-negotiable constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_quant_sentinel.market_making.avellaneda_stoikov")


@dataclass
class AvellanedaStoikovQuotes:
    """Optimal reservation price, half-spreads, and discrete limit quotes."""
    symbol: str
    mid_price: float
    reservation_price: float
    inventory_q: float
    optimal_spread: float
    optimal_half_spread_ask: float
    optimal_half_spread_bid: float
    raw_ask_price: float
    raw_bid_price: float
    discrete_ask_price: float
    discrete_bid_price: float
    tick_size: float
    skew_bps: float
    is_inventory_long: bool
    is_inventory_short: bool
    is_inventory_flat: bool
    risk_aversion_gamma: float
    volatility_sigma: float
    liquidity_kappa: float
    real_capital_enabled: bool = False
    timestamp_ns: int = 0


class AvellanedaStoikovModel:
    """
    Sub-millisecond analytical Avellaneda-Stoikov (2008) Market Making Engine.
    """

    def __init__(
        self,
        risk_aversion_gamma: float = 0.1,         # gamma: Risk aversion coefficient
        book_liquidity_density_kappa: float = 1.5, # kappa: Order flow arrival density decay
        holding_horizon_sec: float = 10.0,         # T - t: Terminal inventory target horizon
        tick_size: float = 0.1,                    # Exchange tick size (e.g. 0.1 for BTC/USDT)
    ) -> None:
        if risk_aversion_gamma <= 0:
            raise ValueError("risk_aversion_gamma must be > 0")
        if book_liquidity_density_kappa <= 0:
            raise ValueError("book_liquidity_density_kappa must be > 0")
        if tick_size <= 0:
            raise ValueError("tick_size must be > 0")

        self.gamma = risk_aversion_gamma
        self.kappa = book_liquidity_density_kappa
        self.T_minus_t = max(0.1, holding_horizon_sec)
        self.tick_size = tick_size
        self.real_capital_enabled: bool = False

    def compute_reservation_price(
        self,
        mid_price: float,
        inventory_q: float | None = None,
        volatility_sigma: float = 0.001,
        current_inventory: float | None = None,
    ) -> float:
        """
        Calculates the indifference reservation price:
        r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
        """
        q = inventory_q if inventory_q is not None else (current_inventory if current_inventory is not None else 0.0)
        var = volatility_sigma ** 2
        skew = q * self.gamma * var * self.T_minus_t
        return mid_price - skew

    def compute_optimal_quotes(
        self,
        symbol: str,
        mid_price: float,
        current_inventory: float,
        volatility_sigma: float,
        spread_multiplier: float = 1.0,
    ) -> AvellanedaStoikovQuotes:
        """
        Calculates exact Avellaneda-Stoikov reservation price, half-spreads,
        and tick-discretized bid/ask quotes with Hawkes toxicity scaling.
        """
        if mid_price <= 0.0:
            raise ValueError("mid_price must be > 0")
        if volatility_sigma <= 0.0:
            volatility_sigma = 0.001  # Safe floor for zero vol

        # 1. Reservation Price
        r = self.compute_reservation_price(
            mid_price=mid_price,
            inventory_q=current_inventory,
            volatility_sigma=volatility_sigma,
        )

        # 2. Optimal Spread Components
        var = volatility_sigma ** 2
        horizon_var_term = self.gamma * var * self.T_minus_t
        liquidity_term = (2.0 / self.gamma) * math.log(1.0 + (self.gamma / self.kappa))

        base_spread = (horizon_var_term + liquidity_term) * max(1.0, spread_multiplier)

        # Asymmetric Half-Spreads around mid-price
        delta_ask = ((r - mid_price) / 2.0) + (base_spread / 2.0)
        delta_bid = ((mid_price - r) / 2.0) + (base_spread / 2.0)

        # Ensure half-spreads are at least 1 tick
        delta_ask = max(self.tick_size, delta_ask)
        delta_bid = max(self.tick_size, delta_bid)

        raw_ask = mid_price + delta_ask
        raw_bid = mid_price - delta_bid

        # 3. Discretization to Tick Grid
        discrete_ask = math.ceil(raw_ask / self.tick_size) * self.tick_size
        discrete_bid = math.floor(raw_bid / self.tick_size) * self.tick_size

        # Enforce minimum spread constraint
        if discrete_ask - discrete_bid < (2.0 * self.tick_size):
            discrete_ask = discrete_bid + (2.0 * self.tick_size)

        skew_bps = ((r - mid_price) / mid_price) * 10000.0

        is_long = current_inventory > 1e-6
        is_short = current_inventory < -1e-6
        is_flat = not (is_long or is_short)

        return AvellanedaStoikovQuotes(
            symbol=symbol,
            mid_price=round(mid_price, 4),
            reservation_price=round(r, 4),
            inventory_q=round(current_inventory, 6),
            optimal_spread=round(delta_ask + delta_bid, 4),
            optimal_half_spread_ask=round(delta_ask, 4),
            optimal_half_spread_bid=round(delta_bid, 4),
            raw_ask_price=round(raw_ask, 4),
            raw_bid_price=round(raw_bid, 4),
            discrete_ask_price=round(discrete_ask, 4),
            discrete_bid_price=round(discrete_bid, 4),
            tick_size=self.tick_size,
            skew_bps=round(skew_bps, 2),
            is_inventory_long=is_long,
            is_inventory_short=is_short,
            is_inventory_flat=is_flat,
            risk_aversion_gamma=self.gamma,
            volatility_sigma=volatility_sigma,
            liquidity_kappa=self.kappa,
            real_capital_enabled=False,
            timestamp_ns=time.monotonic_ns(),
        )
