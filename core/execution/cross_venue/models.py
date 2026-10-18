"""
core/execution/cross_venue/models.py
====================================
Milestone 43: Advanced Execution Routing & Cross-Venue Arbitrage Data Models.
Defines immutable data structures, execution split plans, and opportunity DTOs.

Constitutional Invariant:
- real_capital_enabled: bool = False permanent across all models.
- Zero lookahead: All evaluations respect monotonic timestamp ordering.
"""

from __future__ import annotations

import enum
import time
from dataclasses import asdict, dataclass, field
from typing import Any


class VenueType(enum.StrEnum):
    """Classification of execution venues across centralized and decentralized finance."""

    CEX_SPOT = "CEX_SPOT"
    CEX_PERPETUAL = "CEX_PERPETUAL"
    DEX_CLMM = "DEX_CLMM"
    CROSS_CHAIN_SOLVER = "CROSS_CHAIN_SOLVER"


class ArbitrageType(enum.StrEnum):
    """Topology classification of cross-venue arbitrage paths."""

    SPATIAL_TWO_WAY = "SPATIAL_TWO_WAY"
    TRIANGULAR_THREE_WAY = "TRIANGULAR_THREE_WAY"
    HYBRID_CEX_DEX = "HYBRID_CEX_DEX"
    CROSS_CHAIN_INTENT = "CROSS_CHAIN_INTENT"


@dataclass(frozen=True)
class OrderBookLevel:
    """Single level in an order book depth ladder."""

    price: float
    size: float


@dataclass
class VenueDepthSnapshot:
    """Normalized order book or CLMM tick depth snapshot for a single venue."""

    venue: str
    symbol: str
    venue_type: VenueType
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    fee_bps: float
    latency_ms: float
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else float("inf")

    def mid_price(self) -> float:
        bid = self.best_bid()
        ask = self.best_ask()
        if ask < float("inf") and bid > 0.0:
            return (bid + ask) / 2.0
        return bid if bid > 0.0 else (ask if ask < float("inf") else 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "symbol": self.symbol,
            "venue_type": self.venue_type.value,
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "fee_bps": self.fee_bps,
            "latency_ms": self.latency_ms,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class ArbitrageLeg:
    """An individual execution leg within a multi-leg or spatial arbitrage path."""

    leg_id: str
    venue: str
    venue_type: VenueType
    action: str  # "BUY" or "SELL"
    symbol: str
    price: float
    size: float
    fee_bps: float
    latency_ms: float
    slippage_bps: float = 0.0

    def notional_usd(self) -> float:
        return self.price * self.size

    def fee_usd(self) -> float:
        return self.notional_usd() * (self.fee_bps / 10000.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrossVenueOpportunity:
    """A fully quantified spatial or triangular arbitrage opportunity across venues."""

    opportunity_id: str
    arb_type: ArbitrageType
    legs: list[ArbitrageLeg]
    gross_spread_bps: float
    net_spread_bps: float
    optimal_notional_usd: float
    expected_pnl_usd: float
    decay_probability: float
    leg_risk_abort_threshold_bps: float = 15.0
    is_viable: bool = True
    real_capital_enabled: bool = False
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "arb_type": self.arb_type.value,
            "legs_count": len(self.legs),
            "legs": [leg.to_dict() for leg in self.legs],
            "gross_spread_bps": self.gross_spread_bps,
            "net_spread_bps": self.net_spread_bps,
            "optimal_notional_usd": self.optimal_notional_usd,
            "expected_pnl_usd": self.expected_pnl_usd,
            "decay_probability": self.decay_probability,
            "leg_risk_abort_threshold_bps": self.leg_risk_abort_threshold_bps,
            "is_viable": self.is_viable,
            "real_capital_enabled": self.real_capital_enabled,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class RoutingSplit:
    """Portion of an order routed to a specific venue in an optimal execution plan."""

    venue: str
    venue_type: VenueType
    allocated_notional_usd: float
    allocation_pct: float
    effective_price: float
    marginal_cost_bps: float
    slippage_bps: float
    fee_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "venue_type": self.venue_type.value,
            "allocated_notional_usd": self.allocated_notional_usd,
            "allocation_pct": self.allocation_pct,
            "effective_price": self.effective_price,
            "marginal_cost_bps": self.marginal_cost_bps,
            "slippage_bps": self.slippage_bps,
            "fee_usd": self.fee_usd,
        }


@dataclass
class ExecutionPlan:
    """Synthesized multi-venue execution and order slicing plan."""

    plan_id: str
    symbol: str
    action: str  # "BUY" or "SELL"
    total_notional_usd: float
    splits: list[RoutingSplit]
    volume_weighted_price: float
    total_slippage_bps: float
    total_fee_usd: float
    latency_penalty_usd: float
    net_effective_cost_bps: float
    risk_gate_passed: bool = False
    real_capital_enabled: bool = False
    rejection_reason: str | None = None
    narrative: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "symbol": self.symbol,
            "action": self.action,
            "total_notional_usd": self.total_notional_usd,
            "splits": [s.to_dict() for s in self.splits],
            "volume_weighted_price": self.volume_weighted_price,
            "total_slippage_bps": self.total_slippage_bps,
            "total_fee_usd": self.total_fee_usd,
            "latency_penalty_usd": self.latency_penalty_usd,
            "net_effective_cost_bps": self.net_effective_cost_bps,
            "risk_gate_passed": self.risk_gate_passed,
            "real_capital_enabled": self.real_capital_enabled,
            "rejection_reason": self.rejection_reason,
            "narrative": self.narrative,
            "timestamp_ms": self.timestamp_ms,
        }
