"""
core/execution/market_making/market_maker_sentinel.py
=====================================================
Milestone 37: Autonomous Market Making Sentinel & Risk Gate.

Mandates:
1. Coordinates Avellaneda-Stoikov reservation pricing and Hawkes flow toxicity filter.
2. Enforces the non-negotiable constitutional 1.5% equity risk cap:
   |q| * mid_price <= account_equity * 0.015
3. Dynamic inventory shedding:
   - When long inventory approaches 1.5% cap: Suppresses BID quotes, emitting ASK quotes only.
   - When short inventory approaches 1.5% cap: Suppresses ASK quotes, emitting BID quotes only.
4. Hawkes toxicity spread defense:
   - Widens quoting half-spreads by up to 2.5x during informed trade cascades.
5. Permanent constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from core.execution.market_making.avellaneda_stoikov import (
    AvellanedaStoikovModel,
    AvellanedaStoikovQuotes,
)
from core.execution.market_making.hawkes_intensity import (
    FlowToxicityTier,
    HawkesIntensityState,
    HawkesTradeArrivalEstimator,
)

logger = logging.getLogger("ai_quant_sentinel.market_making.sentinel")


@dataclass
class MarketMakingDecision:
    """Decision output emitted by the Market Making Sentinel."""

    symbol: str
    quotes: AvellanedaStoikovQuotes
    hawkes_state: HawkesIntensityState
    allowed_sides: list[str]  # ["BUY", "SELL"], ["SELL"], ["BUY"], or []
    is_single_sided_only: bool
    inventory_notional_usd: float
    inventory_equity_pct: float
    max_equity_cap_pct: float
    is_within_risk_cap: bool
    action_narrative: str
    real_capital_enabled: bool = False
    timestamp_ns: int = 0


class ASMarketMakerSentinel:
    """
    Autonomous High-Frequency Market Making Sentinel.
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        risk_aversion_gamma: float = 0.1,
        book_liquidity_density_kappa: float = 1.5,
        holding_horizon_sec: float = 10.0,
        tick_size: float = 0.1,
        max_single_position_equity_pct: float = 0.015,  # Constitutional 1.5% cap
    ) -> None:
        self.symbol = symbol
        self.max_cap_pct = max_single_position_equity_pct

        self.pricing_model = AvellanedaStoikovModel(
            risk_aversion_gamma=risk_aversion_gamma,
            book_liquidity_density_kappa=book_liquidity_density_kappa,
            holding_horizon_sec=holding_horizon_sec,
            tick_size=tick_size,
        )
        self.hawkes_estimator = HawkesTradeArrivalEstimator()
        self.real_capital_enabled: bool = False

    def process_incoming_trade(self, timestamp_ns: int | None = None) -> HawkesIntensityState:
        """Notifies the Hawkes estimator of an observed trade on the venue order book."""
        return self.hawkes_estimator.record_trade_event(timestamp_ns=timestamp_ns)

    def evaluate_quoting_opportunity(
        self,
        account_equity_usd: float,
        mid_price: float,
        current_inventory: float,
        volatility_sigma: float,
        current_time_ns: int | None = None,
    ) -> MarketMakingDecision:
        """
        Evaluates the current order book and inventory, computing optimal bid/ask quotes
        and enforcing constitutional risk ceilings.
        """
        if account_equity_usd <= 0.0:
            raise ValueError("account_equity_usd must be > 0")

        now_ns = current_time_ns if current_time_ns is not None else time.monotonic_ns()

        # 1. Evaluate Hawkes Toxicity
        hawkes_state = self.hawkes_estimator.get_current_state(now_ns=now_ns)
        spread_mult = hawkes_state.spread_widening_multiplier

        # 2. Compute Avellaneda-Stoikov Quotes
        quotes = self.pricing_model.compute_optimal_quotes(
            symbol=self.symbol,
            mid_price=mid_price,
            current_inventory=current_inventory,
            volatility_sigma=volatility_sigma,
            spread_multiplier=spread_mult,
        )

        # 3. Inventory & Constitutional 1.5% Risk Cap Evaluation
        inventory_notional = abs(current_inventory) * mid_price
        inventory_pct = inventory_notional / account_equity_usd

        is_within_cap = inventory_pct <= self.max_cap_pct + 1e-6

        # Quoting Side Determination
        allowed_sides = ["BUY", "SELL"]
        is_single_sided = False
        action = "DUAL_SIDED_QUOTING"

        # If inventory reaches or exceeds cap, enforce defensive one-sided quoting
        if inventory_pct >= self.max_cap_pct - 1e-4:
            is_single_sided = True
            if current_inventory > 0:
                # Long inventory: Quote SELL only (shed inventory)
                allowed_sides = ["SELL"]
                action = f"DEFENSIVE_INVENTORY_SHED: Long inventory ({inventory_pct * 100:.2f}%) at 1.5% cap. Bids disabled."
            else:
                # Short inventory: Quote BUY only (cover inventory)
                allowed_sides = ["BUY"]
                action = f"DEFENSIVE_INVENTORY_COVER: Short inventory ({inventory_pct * 100:.2f}%) at 1.5% cap. Asks disabled."
        elif hawkes_state.toxicity_tier == FlowToxicityTier.CRITICAL_TOXIC_SURGE:
            action = f"TOXIC_FLOW_DEFENSE: Quoting spread widened by {spread_mult:.2f}x to protect against adverse selection."

        return MarketMakingDecision(
            symbol=self.symbol,
            quotes=quotes,
            hawkes_state=hawkes_state,
            allowed_sides=allowed_sides,
            is_single_sided_only=is_single_sided,
            inventory_notional_usd=round(inventory_notional, 2),
            inventory_equity_pct=round(inventory_pct, 4),
            max_equity_cap_pct=self.max_cap_pct,
            is_within_risk_cap=is_within_cap,
            action_narrative=action,
            real_capital_enabled=False,
            timestamp_ns=now_ns,
        )
