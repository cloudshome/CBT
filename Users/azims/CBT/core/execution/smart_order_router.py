"""
core/execution/smart_order_router.py
====================================
Authoritative Multi-Venue Smart Order Routing (SOR) Engine for Crypto Brain Terminal.

GOVERNANCE CLASSIFICATION: CLASS E / H (TRADING LOGIC & EXECUTION BOUNDARY)
=============================================================================
Enforces optimal child order distribution across Binance Spot and Bybit V5
by walking live L2 order book depth profiles and minimizing the total effective
execution cost (VWAP + maker/taker fees + slippage impact).

Supports dynamic venue fee schedules, stale/degraded book detection, circuit
breaker isolation, and fail-closed liquidity protection.
=============================================================================
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from core.audit_bus import audit_bus
from core.execution.live_router import (
    LiveExecutionReceipt,
    LiveOrderRequest,
    live_execution_router,
)

logger = logging.getLogger("sky.smart_order_router")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SmartOrderRouterError(Exception):
    """Base exception for Smart Order Router errors."""


class InsufficientLiquidityError(SmartOrderRouterError):
    """Raised when available liquidity across venues cannot fill parent order within slippage tolerance."""


class VenueDegradedError(SmartOrderRouterError):
    """Raised when a venue is offline, stale, or marked degraded."""


class InvalidOrderParametersError(SmartOrderRouterError):
    """Raised when order parameters are non-finite, non-positive, or missing."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class VenueFeeSchedule:
    """Venue maker and taker fee schedules expressed in basis points (bps)."""

    exchange: str
    maker_fee_bps: float = 7.5  # 0.075% standard VIP0 with BNB / Bybit VIP
    taker_fee_bps: float = 10.0  # 0.100% standard retail taker
    fee_asset: str = "USDT"

    def calculate_taker_fee(self, notional_usd: float) -> float:
        """Calculates taker fee in USD given traded notional."""
        return notional_usd * (self.taker_fee_bps / 10000.0)

    def calculate_maker_fee(self, notional_usd: float) -> float:
        """Calculates maker fee in USD given traded notional."""
        return notional_usd * (self.maker_fee_bps / 10000.0)


@dataclass
class L2DepthLevel:
    """Individual price level in an L2 order book."""

    price: float
    size: float


@dataclass
class VenueOrderBook:
    """Normalized L2 snapshot for a specific exchange venue."""

    exchange: str  # "BINANCE" or "BYBIT"
    symbol: str  # e.g. "BTC/USDT"
    bids: list[L2DepthLevel] = field(default_factory=list)  # Sorted descending by price
    asks: list[L2DepthLevel] = field(default_factory=list)  # Sorted ascending by price
    timestamp_ms: int = 0
    is_degraded: bool = False
    max_stale_age_ms: int = 5000

    def is_stale(self, current_time_ms: int | None = None) -> bool:
        """Determines whether order book depth exceeds staleness threshold."""
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)
        return (now_ms - self.timestamp_ms) > self.max_stale_age_ms


@dataclass
class VenueSplitQuote:
    """Execution quote allocation for an individual venue leg."""

    exchange: str
    allocated_qty: float
    allocated_notional: float
    expected_vwap: float
    expected_fee_usd: float
    expected_slippage_bps: float
    percentage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "allocated_qty": round(self.allocated_qty, 8),
            "allocated_notional": round(self.allocated_notional, 2),
            "expected_vwap": round(self.expected_vwap, 4),
            "expected_fee_usd": round(self.expected_fee_usd, 4),
            "expected_slippage_bps": round(self.expected_slippage_bps, 2),
            "percentage": round(self.percentage, 2),
        }


@dataclass
class SmartOrderRouteQuote:
    """Comprehensive multi-venue execution quote and routing plan."""

    symbol: str
    side: str  # "BUY" or "SELL"
    total_qty: float
    reference_mid_price: float
    weighted_vwap: float
    total_fee_usd: float
    total_effective_cost_usd: float
    total_slippage_bps: float
    splits: list[VenueSplitQuote]
    routing_reason: str
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "total_qty": round(self.total_qty, 8),
            "reference_mid_price": round(self.reference_mid_price, 4),
            "weighted_vwap": round(self.weighted_vwap, 4),
            "total_fee_usd": round(self.total_fee_usd, 4),
            "total_effective_cost_usd": round(self.total_effective_cost_usd, 4),
            "total_slippage_bps": round(self.total_slippage_bps, 2),
            "splits": [s.to_dict() for s in self.splits],
            "routing_reason": self.routing_reason,
            "timestamp_ms": self.timestamp_ms,
        }


# ---------------------------------------------------------------------------
# Smart Order Router Engine
# ---------------------------------------------------------------------------


class SmartOrderRouter:
    """
    Multi-Venue Smart Order Router.
    Calculates cost-optimal parent order splits across Binance Spot and Bybit V5.
    """

    def __init__(self) -> None:
        self.default_fee_schedules: dict[str, VenueFeeSchedule] = {
            "BINANCE": VenueFeeSchedule(exchange="BINANCE", maker_fee_bps=7.5, taker_fee_bps=10.0),
            "BYBIT": VenueFeeSchedule(exchange="BYBIT", maker_fee_bps=2.0, taker_fee_bps=5.5),
        }

    def _walk_single_book(
        self,
        levels: list[L2DepthLevel],
        target_qty: float,
        fee_schedule: VenueFeeSchedule,
        is_buy: bool,
    ) -> tuple[float, float, float]:
        """
        Simulates sweeping an order book ladder up to target_qty.
        Returns: (filled_qty, executed_notional, fee_usd).
        """
        remaining = target_qty
        executed_notional = 0.0
        filled_qty = 0.0

        for lvl in levels:
            if remaining <= 0:
                break
            fill = min(remaining, lvl.size)
            executed_notional += fill * lvl.price
            filled_qty += fill
            remaining -= fill

        fee_usd = fee_schedule.calculate_taker_fee(executed_notional)
        return filled_qty, executed_notional, fee_usd

    def calculate_optimal_split(
        self,
        symbol: str,
        side: str,
        total_qty: float,
        venue_books: dict[str, VenueOrderBook],
        venue_fees: dict[str, VenueFeeSchedule] | None = None,
        max_slippage_bps: float = 200.0,
        current_time_ms: int | None = None,
    ) -> SmartOrderRouteQuote:
        """
        Solves the cost-minimization problem across available venues.

        Evaluates marginal price impact across venues in discrete steps
        to find the optimal allocation (q1, q2) that minimizes:
            Cost(BUY) = Sum(Notional_v + Fee_v)
            Proceeds(SELL) = Sum(Notional_v - Fee_v)
        """
        side_upper = side.upper().strip()
        if side_upper not in ("BUY", "SELL"):
            raise InvalidOrderParametersError(
                f"Invalid order side: {side}. Must be 'BUY' or 'SELL'."
            )

        if not math.isfinite(total_qty) or total_qty <= 0:
            raise InvalidOrderParametersError(
                f"Invalid total_qty: {total_qty}. Must be finite and positive."
            )

        fees = venue_fees or self.default_fee_schedules

        # Filter active, non-degraded, non-stale books
        healthy_venues: dict[str, VenueOrderBook] = {}
        for ex, book in venue_books.items():
            if book.is_degraded:
                logger.warning(f"Excluding venue {ex} from SOR: marked degraded.")
                continue
            if book.is_stale(current_time_ms):
                logger.warning(f"Excluding venue {ex} from SOR: order book is stale.")
                continue
            healthy_venues[ex] = book

        if not healthy_venues:
            raise VenueDegradedError("All venues are degraded, stale, or unavailable for routing.")

        is_buy = side_upper == "BUY"

        # Determine reference mid price across available venues
        mids: list[float] = []
        for book in healthy_venues.values():
            if book.bids and book.asks:
                mids.append((book.bids[0].price + book.asks[0].price) / 2.0)
            elif book.bids:
                mids.append(book.bids[0].price)
            elif book.asks:
                mids.append(book.asks[0].price)

        if not mids:
            raise InsufficientLiquidityError(f"No price levels available for symbol {symbol}.")

        reference_mid_price = sum(mids) / len(mids)

        # Optimization: Discretize total_qty into 100 allocation steps across venues
        venue_names = sorted(healthy_venues.keys())

        # Single venue edge case
        if len(venue_names) == 1:
            ex = venue_names[0]
            book = healthy_venues[ex]
            levels = book.asks if is_buy else book.bids
            fee_sched = fees.get(ex, VenueFeeSchedule(exchange=ex))
            filled, notional, fee_usd = self._walk_single_book(levels, total_qty, fee_sched, is_buy)

            if filled < total_qty * 0.9999:
                raise InsufficientLiquidityError(
                    f"Venue {ex} liquidity ({filled:.4f}) insufficient for requested size {total_qty:.4f}."
                )

            vwap = notional / filled if filled > 0 else reference_mid_price
            slippage_bps = (
                ((vwap - reference_mid_price) / reference_mid_price) * 10000.0
                if is_buy
                else ((reference_mid_price - vwap) / reference_mid_price) * 10000.0
            )

            if slippage_bps > max_slippage_bps:
                raise InsufficientLiquidityError(
                    f"Execution slippage {slippage_bps:.1f} bps exceeds tolerance {max_slippage_bps:.1f} bps on {ex}."
                )

            split = VenueSplitQuote(
                exchange=ex,
                allocated_qty=filled,
                allocated_notional=notional,
                expected_vwap=vwap,
                expected_fee_usd=fee_usd,
                expected_slippage_bps=slippage_bps,
                percentage=100.0,
            )

            total_effective_cost = notional + fee_usd if is_buy else notional - fee_usd

            return SmartOrderRouteQuote(
                symbol=symbol,
                side=side_upper,
                total_qty=total_qty,
                reference_mid_price=reference_mid_price,
                weighted_vwap=vwap,
                total_fee_usd=fee_usd,
                total_effective_cost_usd=total_effective_cost,
                total_slippage_bps=slippage_bps,
                splits=[split],
                routing_reason=f"Sole operational venue: {ex}",
            )

        # Multi-venue optimization (2 venues: e.g. BINANCE and BYBIT)
        v1, v2 = venue_names[0], venue_names[1]
        book1, book2 = healthy_venues[v1], healthy_venues[v2]
        levels1 = book1.asks if is_buy else book1.bids
        levels2 = book2.asks if is_buy else book2.bids
        fee1 = fees.get(v1, VenueFeeSchedule(exchange=v1))
        fee2 = fees.get(v2, VenueFeeSchedule(exchange=v2))

        best_cost = float("inf") if is_buy else float("-inf")
        best_allocation: tuple[float, float, float, float, float, float] | None = None

        steps = 100
        for i in range(steps + 1):
            q1 = total_qty * (i / steps)
            q2 = total_qty - q1

            f1, notional1, fee_usd1 = self._walk_single_book(levels1, q1, fee1, is_buy)
            f2, notional2, fee_usd2 = self._walk_single_book(levels2, q2, fee2, is_buy)

            if (f1 + f2) < total_qty * 0.9999:
                continue

            tot_notional = notional1 + notional2
            tot_fee = fee_usd1 + fee_usd2
            net_cost = (tot_notional + tot_fee) if is_buy else (tot_notional - tot_fee)

            if is_buy:
                if net_cost < best_cost:
                    best_cost = net_cost
                    best_allocation = (q1, q2, notional1, notional2, fee_usd1, fee_usd2)
            else:
                if net_cost > best_cost:
                    best_cost = net_cost
                    best_allocation = (q1, q2, notional1, notional2, fee_usd1, fee_usd2)

        if best_allocation is None:
            raise InsufficientLiquidityError(
                f"Combined liquidity across {v1} and {v2} insufficient for order quantity {total_qty:.4f}."
            )

        q1, q2, notional1, notional2, fee_usd1, fee_usd2 = best_allocation
        total_notional = notional1 + notional2
        total_fee = fee_usd1 + fee_usd2
        weighted_vwap = total_notional / total_qty

        total_slippage_bps = (
            ((weighted_vwap - reference_mid_price) / reference_mid_price) * 10000.0
            if is_buy
            else ((reference_mid_price - weighted_vwap) / reference_mid_price) * 10000.0
        )

        if total_slippage_bps > max_slippage_bps:
            raise InsufficientLiquidityError(
                f"Optimal execution slippage {total_slippage_bps:.1f} bps exceeds tolerance {max_slippage_bps:.1f} bps."
            )

        splits: list[VenueSplitQuote] = []
        if q1 > 0:
            vwap1 = notional1 / q1
            slip1 = (
                ((vwap1 - reference_mid_price) / reference_mid_price) * 10000.0
                if is_buy
                else ((reference_mid_price - vwap1) / reference_mid_price) * 10000.0
            )
            splits.append(
                VenueSplitQuote(
                    exchange=v1,
                    allocated_qty=q1,
                    allocated_notional=notional1,
                    expected_vwap=vwap1,
                    expected_fee_usd=fee_usd1,
                    expected_slippage_bps=slip1,
                    percentage=(q1 / total_qty) * 100.0,
                )
            )

        if q2 > 0:
            vwap2 = notional2 / q2
            slip2 = (
                ((vwap2 - reference_mid_price) / reference_mid_price) * 10000.0
                if is_buy
                else ((reference_mid_price - vwap2) / reference_mid_price) * 10000.0
            )
            splits.append(
                VenueSplitQuote(
                    exchange=v2,
                    allocated_qty=q2,
                    allocated_notional=notional2,
                    expected_vwap=vwap2,
                    expected_fee_usd=fee_usd2,
                    expected_slippage_bps=slip2,
                    percentage=(q2 / total_qty) * 100.0,
                )
            )

        reason = (
            f"Optimal split: {v1} {splits[0].percentage:.1f}% / {v2} {splits[1].percentage:.1f}%"
            if len(splits) == 2
            else f"100% routed to {splits[0].exchange}"
        )

        return SmartOrderRouteQuote(
            symbol=symbol,
            side=side_upper,
            total_qty=total_qty,
            reference_mid_price=reference_mid_price,
            weighted_vwap=weighted_vwap,
            total_fee_usd=total_fee,
            total_effective_cost_usd=best_cost,
            total_slippage_bps=total_slippage_bps,
            splits=splits,
            routing_reason=reason,
        )

    async def execute_smart_order(
        self,
        quote: SmartOrderRouteQuote,
        environment: str = "TESTNET",
        account_equity_usd: float = 100_000.0,
        parent_correlation_id: str | None = None,
    ) -> list[LiveExecutionReceipt]:
        """
        Dispatches split child orders through the LiveExecutionRouter 20-Gate Pre-Trade Invariant Pipeline.
        """
        receipts: list[LiveExecutionReceipt] = []

        for split in quote.splits:
            req = LiveOrderRequest(
                exchange=split.exchange,
                environment=environment,
                symbol=quote.symbol,
                side=quote.side,
                order_type="MARKET",
                quantity=split.allocated_qty,
                price=split.expected_vwap,
                account_equity_usd=account_equity_usd,
                correlation_id=parent_correlation_id,
            )
            logger.info(
                f"SOR dispatching child order: {split.exchange} {quote.side} {split.allocated_qty} {quote.symbol}"
            )
            receipt = await live_execution_router.execute_live_order(req)
            receipts.append(receipt)

        audit_bus.emit_event(
            event_type="SOR_EXECUTION_COMPLETED",
            symbol=quote.symbol,
            severity="INFO",
            reason=f"SOR executed {len(receipts)} split legs across venues for {quote.total_qty} {quote.symbol}",
            details={"quote": quote.to_dict(), "receipts_count": len(receipts)},
        )

        return receipts


# Global authoritative instance
smart_order_router = SmartOrderRouter()
