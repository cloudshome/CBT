"""
core/intelligence/forward_validation/paper_fill_simulator.py
============================================================
Realistic Microstructure Paper Fill Simulator for Milestone 31.

Enforces:
1. Depth-Bounded Market Orders: Walks discrete order book levels to compute
   volume-weighted average fill price (VWAP) + adverse selection slippage.
2. Queue-Priority Limit Orders: Tracks queue position behind resting liquidity,
   requiring cumulative trade-through volume before fill execution.
3. Partial Fill Realism: Unfilled size cancelled if depth exceeds slippage tolerance.
4. Permanent Capital Firewall: simulation_only = True, real_capital_enabled = False,
   zero execution imports or live order dispatch.
5. Feed Integrity Gate: Rejects fill simulation if order book is stale, crossed, or gapped.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.orderbook_tracker import (
    FeedQualityState,
    OrderBookSnapshot,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.paper_fill")

# Microstructure model classification
QUEUE_MODEL: Final[str] = "APPROXIMATE_AGGREGATED_L2"
CANCELLATION_SCOPE: Final[str] = "SIMULATION_ONLY_CANCEL"

QUEUE_MODEL_ASSUMPTIONS: Final[tuple[str, ...]] = (
    "Queue position initialization is proportional to visible aggregate depth",
    "Hidden liquidity and icebergs are unobserved in aggregated L2",
    "Order cancellations ahead of simulated order in queue are unobserved",
    "Same-price order arrivals are assigned priority after current queue",
    "Trade attribution ambiguity exists across multi-trade fills",
    "Event batching on exchange WebSocket can delay fill notifications",
    "Feed network latency can cause price slippage between decision and fill",
    "Partial execution uncertainty is handled via depth walking up to slippage limit",
)


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class FeedIntegrityError(ValueError):
    """Raised when an order fill is requested on a corrupted or stale market data feed."""


class InsufficientLiquidityError(ValueError):
    """Raised when book has zero liquidity on the requested side."""


class PaperFill(BaseModel):
    """
    Immutable audit record of a simulated paper execution.
    Contains complete execution quality attribution (VWAP, slippage, fees, queue delay).
    """

    fill_id: str = Field(..., description="Unique fill ID: PFILL-<timestamp>-<uuid8>")
    admission_id: str = Field(..., description="Target StrategyAdmission ID")
    symbol: str = Field(..., description="Trading pair (e.g. BTCUSDT)")
    venue: str = Field(..., description="Execution venue (e.g. BINANCE / HYPERLIQUID)")
    side: OrderSide = Field(..., description="Order side (BUY / SELL)")
    order_type: OrderType = Field(..., description="Order type (MARKET / LIMIT)")
    requested_quantity: float = Field(..., description="Original order quantity")
    filled_quantity: float = Field(..., description="Actual filled quantity")
    fill_price: float = Field(..., description="Effective execution price (VWAP + slippage)")
    benchmark_mid_price: float = Field(..., description="Mid-price at decision time")
    fee_bps: float = Field(..., description="Exchange fee in basis points")
    fee_usd: float = Field(..., description="Exchange fee in USD notional")
    slippage_bps: float = Field(..., description="Execution slippage against top of book in bps")
    decision_timestamp_utc: float = Field(..., description="Timestamp strategy generated the order")
    fill_timestamp_utc: float = Field(..., description="Simulated execution completion timestamp")
    queue_delay_ms: float = Field(default=0.0, description="Modeled queue / network latency in ms")
    is_partial: bool = Field(
        default=False, description="True if filled_quantity < requested_quantity"
    )
    fill_model_version: str = Field(default="v1.0-realistic-microstructure")
    simulation_only: Literal[True] = True
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = (
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    )
    real_capital_enabled: Literal[False] = False


class RestingLimitOrder:
    """
    Tracks an active resting limit order in the simulated order book queue.
    """

    def __init__(
        self,
        order_id: str,
        admission_id: str,
        symbol: str,
        venue: str,
        side: OrderSide,
        price: float,
        quantity: float,
        queue_ahead_size: float,
        placement_utc: float,
        fee_bps: float = 2.0,
    ) -> None:
        self.order_id = order_id
        self.admission_id = admission_id
        self.symbol = symbol
        self.venue = venue
        self.side = side
        self.price = price
        self.quantity = quantity
        self.queue_ahead_size = queue_ahead_size
        self.remaining_quantity = quantity
        self.placement_utc = placement_utc
        self.fee_bps = fee_bps
        self.cumulative_volume_traded_at_level: float = 0.0

    @property
    def is_filled(self) -> bool:
        return self.remaining_quantity <= 1e-8


class RealisticPaperFillSimulator:
    """
    Simulates realistic market order executions and limit order queue dynamics
    against live or replayed OrderBookSnapshot states.
    """

    def __init__(
        self,
        taker_fee_bps: float = 5.0,
        maker_fee_bps: float = 2.0,
        market_order_latency_ms: float = 50.0,
        cancel_latency_ms: float = 50.0,
        adverse_selection_factor: float = 0.5,
    ) -> None:
        self.taker_fee_bps = taker_fee_bps
        self.maker_fee_bps = maker_fee_bps
        self.market_order_latency_ms = market_order_latency_ms
        self.cancel_latency_ms = cancel_latency_ms
        self.adverse_selection_factor = adverse_selection_factor

        # order_id -> RestingLimitOrder
        self._resting_limit_orders: dict[str, RestingLimitOrder] = {}

    def simulate_market_order(
        self,
        admission_id: str,
        book: OrderBookSnapshot,
        side: OrderSide,
        quantity: float,
        decision_timestamp_utc: float | None = None,
        max_slippage_bps: float = 100.0,
    ) -> PaperFill:
        """
        Executes a realistic market order by walking book levels to compute VWAP,
        evaluating adverse selection slippage, and applying taker fees.
        """
        now = time.time()
        decision_utc = decision_timestamp_utc or now

        # 1. Feed Integrity Check
        if book.quality != FeedQualityState.HEALTHY or book.is_crossed:
            raise FeedIntegrityError(
                f"Cannot execute paper order on {book.venue}:{book.symbol}. Feed status: {book.quality.value}, crossed={book.is_crossed}"
            )

        mid_price = book.mid_price
        if mid_price is None or mid_price <= 0:
            raise InsufficientLiquidityError(
                f"Zero mid-price or missing book quotes for {book.symbol}"
            )

        levels = book.asks if side == OrderSide.BUY else book.bids
        if not levels:
            raise InsufficientLiquidityError(
                f"Zero liquidity on {side.value} side for {book.symbol}"
            )

        top_px = levels[0].price
        max_allowed_px = (
            top_px * (1.0 + max_slippage_bps / 10000.0)
            if side == OrderSide.BUY
            else top_px * (1.0 - max_slippage_bps / 10000.0)
        )

        # 2. Walk Book Depth
        remaining_qty = quantity
        total_notional = 0.0
        filled_qty = 0.0

        for lvl in levels:
            # Check slippage limit
            if (side == OrderSide.BUY and lvl.price > max_allowed_px) or (
                side == OrderSide.SELL and lvl.price < max_allowed_px
            ):
                break

            take_qty = min(remaining_qty, lvl.size)
            total_notional += take_qty * lvl.price
            filled_qty += take_qty
            remaining_qty -= take_qty

            if remaining_qty <= 1e-8:
                break

        if filled_qty <= 0:
            raise InsufficientLiquidityError(
                f"Insufficient liquidity within {max_slippage_bps} bps slippage for {quantity} {book.symbol}"
            )

        raw_vwap = total_notional / filled_qty

        # 3. Adverse Selection & Latency Slippage Penalty
        # Larger orders relative to top-level depth suffer additional impact
        top_level_size = levels[0].size
        size_ratio = min(5.0, filled_qty / max(0.01, top_level_size))
        adverse_bps = self.adverse_selection_factor * math.sqrt(size_ratio) * 1.5

        if side == OrderSide.BUY:
            effective_fill_price = raw_vwap * (1.0 + adverse_bps / 10000.0)
            slippage_bps = ((effective_fill_price - top_px) / top_px) * 10000.0
        else:
            effective_fill_price = raw_vwap * (1.0 - adverse_bps / 10000.0)
            slippage_bps = ((top_px - effective_fill_price) / top_px) * 10000.0

        fill_notional = filled_qty * effective_fill_price
        fee_usd = fill_notional * (self.taker_fee_bps / 10000.0)

        fill_time = decision_utc + (self.market_order_latency_ms / 1000.0)
        fill_id = f"PFILL-{int(fill_time)}-{uuid.uuid4().hex[:8]}"

        return PaperFill(
            fill_id=fill_id,
            admission_id=admission_id,
            symbol=book.symbol,
            venue=book.venue,
            side=side,
            order_type=OrderType.MARKET,
            requested_quantity=quantity,
            filled_quantity=filled_qty,
            fill_price=effective_fill_price,
            benchmark_mid_price=mid_price,
            fee_bps=self.taker_fee_bps,
            fee_usd=fee_usd,
            slippage_bps=max(0.0, slippage_bps),
            decision_timestamp_utc=decision_utc,
            fill_timestamp_utc=fill_time,
            queue_delay_ms=self.market_order_latency_ms,
            is_partial=(filled_qty < quantity),
            fill_model_version="v1.0-realistic-depth-vwap",
            simulation_only=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
        )

    def place_limit_order(
        self,
        admission_id: str,
        book: OrderBookSnapshot,
        side: OrderSide,
        price: float,
        quantity: float,
        placement_utc: float | None = None,
    ) -> str:
        """
        Places a resting limit order and records its position behind existing queue depth.
        Returns unique order_id.
        """
        if book.quality != FeedQualityState.HEALTHY or book.is_crossed:
            raise FeedIntegrityError(
                f"Cannot place limit order on corrupted feed {book.venue}:{book.symbol}"
            )

        now = placement_utc or time.time()
        order_id = f"LMT-{int(now)}-{uuid.uuid4().hex[:8]}"

        # Estimate queue ahead of order at that price level
        levels = book.bids if side == OrderSide.BUY else book.asks
        queue_ahead = 0.0
        for lvl in levels:
            if (side == OrderSide.BUY and lvl.price >= price) or (
                side == OrderSide.SELL and lvl.price <= price
            ):
                queue_ahead += lvl.size

        self._resting_limit_orders[order_id] = RestingLimitOrder(
            order_id=order_id,
            admission_id=admission_id,
            symbol=book.symbol,
            venue=book.venue,
            side=side,
            price=price,
            quantity=quantity,
            queue_ahead_size=queue_ahead,
            placement_utc=now,
            fee_bps=self.maker_fee_bps,
        )
        logger.debug(
            "Placed limit order %s (%s %.4f @ %.2f, queue ahead: %.2f)",
            order_id,
            side.value,
            quantity,
            price,
            queue_ahead,
        )
        return order_id

    def process_trade_tick(
        self,
        symbol: str,
        venue: str,
        trade_price: float,
        trade_size: float,
        tick_time_utc: float,
    ) -> list[PaperFill]:
        """
        Processes an aggressive trade print against resting limit orders.
        Fills orders only when volume traded through their level exceeds queue ahead.
        """
        completed_fills: list[PaperFill] = []

        for order_id, order in list(self._resting_limit_orders.items()):
            if order.symbol != symbol or order.venue != venue:
                continue

            # Trade-through logic:
            # Buy limit order fills if trades occur at <= limit price
            # Sell limit order fills if trades occur at >= limit price
            eligible = (order.side == OrderSide.BUY and trade_price <= order.price) or (
                order.side == OrderSide.SELL and trade_price >= order.price
            )
            if not eligible:
                continue

            order.cumulative_volume_traded_at_level += trade_size

            # Check if cumulative volume exceeded queue ahead
            if order.cumulative_volume_traded_at_level > order.queue_ahead_size:
                excess_volume = order.cumulative_volume_traded_at_level - order.queue_ahead_size
                fill_qty = min(order.remaining_quantity, excess_volume)

                order.remaining_quantity -= fill_qty
                fill_notional = fill_qty * order.price
                fee_usd = fill_notional * (order.fee_bps / 10000.0)

                fill_id = f"PFILL-{int(tick_time_utc)}-{uuid.uuid4().hex[:8]}"
                paper_fill = PaperFill(
                    fill_id=fill_id,
                    admission_id=order.admission_id,
                    symbol=order.symbol,
                    venue=order.venue,
                    side=order.side,
                    order_type=OrderType.LIMIT,
                    requested_quantity=order.quantity,
                    filled_quantity=fill_qty,
                    fill_price=order.price,
                    benchmark_mid_price=order.price,
                    fee_bps=order.fee_bps,
                    fee_usd=fee_usd,
                    slippage_bps=0.0,  # Resting limit orders experience zero execution slippage
                    decision_timestamp_utc=order.placement_utc,
                    fill_timestamp_utc=tick_time_utc,
                    queue_delay_ms=max(0.0, (tick_time_utc - order.placement_utc) * 1000.0),
                    is_partial=not order.is_filled,
                    fill_model_version="v1.0-queue-priority-trade-through",
                    simulation_only=True,
                    execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
                    real_capital_enabled=False,
                )
                completed_fills.append(paper_fill)

                if order.is_filled:
                    del self._resting_limit_orders[order_id]

        return completed_fills

    def cancel_limit_order(self, order_id: str) -> bool:
        """Cancels a resting limit order. Returns True if successfully cancelled."""
        if order_id in self._resting_limit_orders:
            del self._resting_limit_orders[order_id]
            return True
        return False

    def cancel_all_orders_for_admission(self, admission_id: str) -> list[str]:
        """
        Cancels all resting simulated limit orders for an admission ID.
        Scope: SIMULATION_ONLY_CANCEL. Zero live exchange or execution router interaction.
        Returns list of cancelled simulated order IDs.
        """
        cancelled_ids: list[str] = []
        for oid, order in list(self._resting_limit_orders.items()):
            if order.admission_id == admission_id:
                del self._resting_limit_orders[oid]
                cancelled_ids.append(oid)
        if cancelled_ids:
            logger.info(
                "[%s] Cancelled %d simulated resting orders for %s",
                CANCELLATION_SCOPE,
                len(cancelled_ids),
                admission_id,
            )
        return cancelled_ids
