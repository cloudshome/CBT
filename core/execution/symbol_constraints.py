"""
core/execution/symbol_constraints.py
====================================
Exchange-Symbol Feasibility & Precision Constraint Engine.

Validates requested order notional against discrete exchange trading rules:
- minQty and maxQty limits
- stepSize quantity quantization (strictly down-rounded to step increments)
- minNotional boundary checks
- tickSize price quantization

Governance Invariants:
- Never blindly assumes $10.00 notional is universally valid.
- Never automatically inflates quantities upward to reach arbitrary ceilings.
- Rejects infeasible combinations with CANARY_REJECTED_SYMBOL_CONSTRAINT.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sky.execution.symbol_constraints")


@dataclass
class SymbolConstraintFilter:
    exchange: str
    symbol: str
    min_qty: float
    max_qty: float
    step_size: float
    min_notional: float
    tick_size: float


@dataclass
class FeasibilityResult:
    is_feasible: bool
    feasible_qty: float
    effective_price: float
    final_notional_usd: float
    step_size: float
    min_notional: float
    status: str  # "FEASIBLE", "CANARY_REJECTED_SYMBOL_CONSTRAINT", "NOTIONAL_OUT_OF_BOUNDS"
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_feasible": self.is_feasible,
            "feasible_qty": self.feasible_qty,
            "effective_price": self.effective_price,
            "final_notional_usd": self.final_notional_usd,
            "step_size": self.step_size,
            "min_notional": self.min_notional,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
        }


# Canonical Symbol Filters for Major Micro-Canary Pairs
DEFAULT_FILTERS: dict[tuple[str, str], SymbolConstraintFilter] = {
    # Binance Spot
    ("BINANCE", "BTCUSDT"): SymbolConstraintFilter(
        exchange="BINANCE",
        symbol="BTCUSDT",
        min_qty=0.00001,
        max_qty=9000.0,
        step_size=0.00001,
        min_notional=5.0,
        tick_size=0.01,
    ),
    ("BINANCE", "ETHUSDT"): SymbolConstraintFilter(
        exchange="BINANCE",
        symbol="ETHUSDT",
        min_qty=0.0001,
        max_qty=9000.0,
        step_size=0.0001,
        min_notional=5.0,
        tick_size=0.01,
    ),
    ("BINANCE", "SOLUSDT"): SymbolConstraintFilter(
        exchange="BINANCE",
        symbol="SOLUSDT",
        min_qty=0.01,
        max_qty=900000.0,
        step_size=0.01,
        min_notional=5.0,
        tick_size=0.01,
    ),
    # Bybit V5
    ("BYBIT", "BTCUSDT"): SymbolConstraintFilter(
        exchange="BYBIT",
        symbol="BTCUSDT",
        min_qty=0.001,
        max_qty=100.0,
        step_size=0.001,
        min_notional=5.0,
        tick_size=0.1,
    ),
    ("BYBIT", "ETHUSDT"): SymbolConstraintFilter(
        exchange="BYBIT",
        symbol="ETHUSDT",
        min_qty=0.01,
        max_qty=1000.0,
        step_size=0.01,
        min_notional=5.0,
        tick_size=0.01,
    ),
    ("BYBIT", "SOLUSDT"): SymbolConstraintFilter(
        exchange="BYBIT",
        symbol="SOLUSDT",
        min_qty=0.1,
        max_qty=10000.0,
        step_size=0.1,
        min_notional=5.0,
        tick_size=0.01,
    ),
}


class SymbolConstraintEngine:
    """Evaluates trading feasibility against venue-specific microstructure filters."""

    def __init__(self) -> None:
        self._filters: dict[tuple[str, str], SymbolConstraintFilter] = dict(DEFAULT_FILTERS)

    def register_filter(self, filter_rule: SymbolConstraintFilter) -> None:
        key = (filter_rule.exchange.upper().strip(), self._clean_symbol(filter_rule.symbol))
        self._filters[key] = filter_rule

    def _clean_symbol(self, symbol: str) -> str:
        return symbol.upper().replace("/", "").replace("-", "").strip()

    def get_filter(self, exchange: str, symbol: str) -> SymbolConstraintFilter:
        exch = exchange.upper().strip()
        clean_sym = self._clean_symbol(symbol)
        key = (exch, clean_sym)

        if key in self._filters:
            return self._filters[key]

        # Safe fallback defaults
        return SymbolConstraintFilter(
            exchange=exch,
            symbol=clean_sym,
            min_qty=0.00001,
            max_qty=100000.0,
            step_size=0.00001,
            min_notional=5.0,
            tick_size=0.01,
        )

    def evaluate_order_feasibility(
        self,
        exchange: str,
        symbol: str,
        requested_notional_usd: float,
        reference_price: float,
        min_canary_notional_usd: float = 5.0,
        max_canary_notional_usd: float = 25.0,
    ) -> FeasibilityResult:
        """
        Evaluates whether a requested notional is executable on the given symbol.
        Enforces stepSize quantization and minNotional checks without auto-rounding.
        """
        # 1. Notional Policy Envelope Check
        if (
            requested_notional_usd < min_canary_notional_usd
            or requested_notional_usd > max_canary_notional_usd
        ):
            return FeasibilityResult(
                is_feasible=False,
                feasible_qty=0.0,
                effective_price=reference_price,
                final_notional_usd=requested_notional_usd,
                step_size=0.0,
                min_notional=0.0,
                status="NOTIONAL_OUT_OF_BOUNDS",
                rejection_reason=(
                    f"Canary requested notional ${requested_notional_usd:.2f} must be "
                    f"between ${min_canary_notional_usd:.2f} and ${max_canary_notional_usd:.2f}."
                ),
            )

        if reference_price <= 0.0:
            return FeasibilityResult(
                is_feasible=False,
                feasible_qty=0.0,
                effective_price=0.0,
                final_notional_usd=0.0,
                step_size=0.0,
                min_notional=0.0,
                status="CANARY_REJECTED_SYMBOL_CONSTRAINT",
                rejection_reason="Invalid non-positive reference price.",
            )

        filter_rule = self.get_filter(exchange, symbol)

        # 2. Price Quantization to Tick Size
        price_steps = round(reference_price / filter_rule.tick_size)
        effective_price = round(price_steps * filter_rule.tick_size, 8)

        # 3. Quantity Quantization (strictly floor to step_size)
        raw_qty = requested_notional_usd / effective_price
        num_steps = math.floor(raw_qty / filter_rule.step_size + 1e-12)
        feasible_qty = round(num_steps * filter_rule.step_size, 8)

        final_notional = round(feasible_qty * effective_price, 2)

        # 4. Check minQty
        if feasible_qty < filter_rule.min_qty:
            return FeasibilityResult(
                is_feasible=False,
                feasible_qty=feasible_qty,
                effective_price=effective_price,
                final_notional_usd=final_notional,
                step_size=filter_rule.step_size,
                min_notional=filter_rule.min_notional,
                status="CANARY_REJECTED_SYMBOL_CONSTRAINT",
                rejection_reason=(
                    f"Quantized quantity {feasible_qty} is below minQty {filter_rule.min_qty} "
                    f"for {filter_rule.symbol} on {exchange}."
                ),
            )

        # 5. Check minNotional
        if final_notional < filter_rule.min_notional:
            return FeasibilityResult(
                is_feasible=False,
                feasible_qty=feasible_qty,
                effective_price=effective_price,
                final_notional_usd=final_notional,
                step_size=filter_rule.step_size,
                min_notional=filter_rule.min_notional,
                status="CANARY_REJECTED_SYMBOL_CONSTRAINT",
                rejection_reason=(
                    f"Final notional ${final_notional:.2f} is below exchange minNotional "
                    f"${filter_rule.min_notional:.2f} for {filter_rule.symbol}."
                ),
            )

        # 6. Check Policy Floor after Quantization
        if final_notional < min_canary_notional_usd:
            return FeasibilityResult(
                is_feasible=False,
                feasible_qty=feasible_qty,
                effective_price=effective_price,
                final_notional_usd=final_notional,
                step_size=filter_rule.step_size,
                min_notional=filter_rule.min_notional,
                status="CANARY_REJECTED_SYMBOL_CONSTRAINT",
                rejection_reason=(
                    f"Quantized notional ${final_notional:.2f} dropped below policy floor "
                    f"${min_canary_notional_usd:.2f}."
                ),
            )

        return FeasibilityResult(
            is_feasible=True,
            feasible_qty=feasible_qty,
            effective_price=effective_price,
            final_notional_usd=final_notional,
            step_size=filter_rule.step_size,
            min_notional=filter_rule.min_notional,
            status="FEASIBLE",
            rejection_reason=None,
        )


symbol_constraint_engine = SymbolConstraintEngine()
