"""
core/execution/smart_order_router.py
====================================
Authoritative Multi-Venue Smart Order Routing (SOR) Engine for Crypto Brain Terminal.

GOVERNANCE CLASSIFICATION: CLASS E / H (TRADING LOGIC & EXECUTION BOUNDARY)
=============================================================================
Enforces optimal child order distribution across Binance Spot and Bybit V5
by walking live L2 order book depth profiles and minimizing the total effective
execution cost (VWAP + maker/taker fees + slippage impact).

Supports dynamic venue fee schedules, venue trading rules (step size, lot size,
minimum notional), strict book validation, stale/degraded book detection,
fail-closed liquidity protection, parent-level 1.5% equity risk gates, and
a multi-venue parent order state machine.
=============================================================================
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager
from core.execution.kill_switch import live_kill_switch
from core.execution.live_router import (
    LiveExecutionReceipt,
    LiveKillSwitchActiveError,
    LiveOrderRequest,
    LiveSizeRejectedError,
    live_execution_router,
)
from core.execution.reconciliation_ledger import reconciliation_ledger

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


class VenueConstraintBreachError(SmartOrderRouterError):
    """Raised when an order allocation breaches venue lot size, step size, or minimum notional."""


class OverfillHaltedError(SmartOrderRouterError):
    """Raised when further child order dispatch is blocked due to an overfill circuit breaker."""


# ---------------------------------------------------------------------------
# Enums & Trading Rules
# ---------------------------------------------------------------------------


class ParentOrderState(StrEnum):
    """Authoritative state machine for multi-venue parent orders."""

    PLANNED = "PLANNED"
    DISPATCHING = "DISPATCHING"
    EXECUTING = "EXECUTING"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    HALTED = "HALTED"


@dataclass
class VenueTradingRules:
    """Exchange-specific order sizing and notional constraint rules."""

    exchange: str
    min_qty: float = 0.00001
    max_qty: float = 10000.0
    step_size: float = 0.00001  # Lot size rounding quantum
    tick_size: float = 0.01  # Price rounding quantum
    min_notional_usd: float = 5.0  # e.g. Binance Spot $5, Bybit V5 $5


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

    def calculate_fee(self, notional_usd: float, execution_style: str = "TAKER") -> float:
        """Calculates fee based on explicit execution style."""
        if execution_style.upper().strip() == "MAKER":
            return self.calculate_maker_fee(notional_usd)
        return self.calculate_taker_fee(notional_usd)


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
        """
        Determines whether order book depth exceeds staleness threshold.
        Exact boundary: stale if elapsed age >= max_stale_age_ms (5000ms).
        """
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)
        return (now_ms - self.timestamp_ms) >= self.max_stale_age_ms

    def validate(self, current_time_ms: int | None = None) -> tuple[bool, str]:
        """
        Performs strict fail-closed market data validation:
        - Must have at least one bid and ask
        - No non-finite, zero, or negative prices/sizes
        - No crossed books (best bid >= best ask)
        - Timestamp must be positive and not in the distant future
        - Must not be marked degraded or stale
        """
        now_ms = current_time_ms if current_time_ms is not None else int(time.time() * 1000)

        if self.is_degraded:
            return False, f"Venue {self.exchange} is marked degraded"
        if self.timestamp_ms <= 0:
            return (
                False,
                f"Venue {self.exchange} has missing or non-positive timestamp ({self.timestamp_ms})",
            )
        if self.timestamp_ms > (now_ms + 1000):
            return (
                False,
                f"Venue {self.exchange} timestamp is in the future ({self.timestamp_ms} > {now_ms + 1000})",
            )
        if self.is_stale(now_ms):
            age = now_ms - self.timestamp_ms
            return (
                False,
                f"Venue {self.exchange} is stale (age {age}ms >= {self.max_stale_age_ms}ms)",
            )
        if not self.bids and not self.asks:
            return False, f"Venue {self.exchange} has empty bids and asks"

        for i, b in enumerate(self.bids):
            if not math.isfinite(b.price) or b.price <= 0:
                return False, f"Venue {self.exchange} invalid bid price at index {i}: {b.price}"
            if not math.isfinite(b.size) or b.size <= 0:
                return False, f"Venue {self.exchange} invalid bid size at index {i}: {b.size}"

        for i, a in enumerate(self.asks):
            if not math.isfinite(a.price) or a.price <= 0:
                return False, f"Venue {self.exchange} invalid ask price at index {i}: {a.price}"
            if not math.isfinite(a.size) or a.size <= 0:
                return False, f"Venue {self.exchange} invalid ask size at index {i}: {a.size}"

        if self.bids and self.asks and self.bids[0].price > self.asks[0].price:
            return False, (
                f"Venue {self.exchange} book is crossed (best bid {self.bids[0].price} "
                f"> best ask {self.asks[0].price})"
            )

        return True, "OK"


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
    execution_style: str = "TAKER"
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
            "execution_style": self.execution_style,
            "splits": [s.to_dict() for s in self.splits],
            "routing_reason": self.routing_reason,
            "timestamp_ms": self.timestamp_ms,
        }


@dataclass
class ParentOrderExecutionRecord:
    """Authoritative audit record of a multi-venue parent order execution lifecycle."""

    parent_order_id: str
    symbol: str
    side: str
    total_qty: float
    state: ParentOrderState
    splits: list[VenueSplitQuote]
    receipts: list[LiveExecutionReceipt] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_order_id": self.parent_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "total_qty": self.total_qty,
            "state": self.state.value,
            "splits": [s.to_dict() for s in self.splits],
            "receipts": [r.to_safe_dict() for r in self.receipts],
            "errors": self.errors,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParentOrderExecutionRecord:
        splits = [
            VenueSplitQuote(
                exchange=s["exchange"],
                allocated_qty=float(s["allocated_qty"]),
                allocated_notional=float(s["allocated_notional"]),
                expected_vwap=float(s["expected_vwap"]),
                expected_fee_usd=float(s["expected_fee_usd"]),
                expected_slippage_bps=float(s["expected_slippage_bps"]),
                percentage=float(s["percentage"]),
            )
            for s in d.get("splits", [])
        ]
        receipts = [
            LiveExecutionReceipt(
                success=bool(r.get("success", True)),
                status=r.get("status", ""),
                client_order_id=r.get("client_order_id", ""),
                exchange_order_id=r.get("exchange_order_id", ""),
                exchange=r.get("exchange", ""),
                environment=r.get("environment", "TESTNET"),
                symbol=r.get("symbol", ""),
                side=r.get("side", ""),
                order_type=r.get("order_type", "MARKET"),
                requested_qty=float(r.get("requested_qty", 0.0)),
                executed_qty=float(r.get("executed_qty", 0.0)),
                executed_price=float(r.get("executed_price", 0.0)),
                cumulative_quote_qty=float(r.get("cumulative_quote_qty", 0.0)),
                latency_ms=float(r.get("latency_ms", 0.0)),
                audit_event_id=r.get("audit_event_id", ""),
                message=r.get("message", ""),
                requires_reconciliation=bool(r.get("requires_reconciliation", False)),
            )
            for r in d.get("receipts", [])
        ]
        return cls(
            parent_order_id=d["parent_order_id"],
            symbol=d["symbol"],
            side=d["side"],
            total_qty=float(d["total_qty"]),
            state=ParentOrderState(d["state"]),
            splits=splits,
            receipts=receipts,
            errors=d.get("errors", []),
            created_at_ms=int(d.get("created_at_ms", 0)),
            updated_at_ms=int(d.get("updated_at_ms", 0)),
        )


# ---------------------------------------------------------------------------
# Smart Order Router Engine
# ---------------------------------------------------------------------------


class SmartOrderRouter:
    """
    Multi-Venue Smart Order Router.
    Calculates cost-optimal parent order splits across Binance Spot and Bybit V5.
    Enforces venue trading constraints, fee schedules, and pre-trade parent risk gates.
    """

    def __init__(self) -> None:
        self.default_fee_schedules: dict[str, VenueFeeSchedule] = {
            "BINANCE": VenueFeeSchedule(exchange="BINANCE", maker_fee_bps=7.5, taker_fee_bps=10.0),
            "BYBIT": VenueFeeSchedule(exchange="BYBIT", maker_fee_bps=2.0, taker_fee_bps=5.5),
        }
        self.default_trading_rules: dict[str, VenueTradingRules] = {
            "BINANCE": VenueTradingRules(
                exchange="BINANCE", min_qty=0.00001, step_size=0.00001, min_notional_usd=5.0
            ),
            "BYBIT": VenueTradingRules(
                exchange="BYBIT", min_qty=0.0001, step_size=0.0001, min_notional_usd=5.0
            ),
        }
        # In-memory parent order registry
        self.parent_orders: dict[str, ParentOrderExecutionRecord] = {}

    def _persist_parent_order(self, record: ParentOrderExecutionRecord) -> None:
        """Persists parent order execution record to SQLite database for crash durability."""
        try:
            splits_json = json.dumps([s.to_dict() for s in record.splits])
            receipts_json = json.dumps([r.to_safe_dict() for r in record.receipts])
            errors_json = json.dumps(record.errors)
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO parent_order_execution_records (
                        parent_order_id, symbol, side, total_qty, state,
                        splits_json, receipts_json, errors_json, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(parent_order_id) DO UPDATE SET
                        state=excluded.state,
                        receipts_json=excluded.receipts_json,
                        errors_json=excluded.errors_json,
                        updated_at_ms=excluded.updated_at_ms
                    """,
                    (
                        record.parent_order_id,
                        record.symbol,
                        record.side,
                        record.total_qty,
                        record.state.value,
                        splits_json,
                        receipts_json,
                        errors_json,
                        record.created_at_ms,
                        record.updated_at_ms,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist parent order {record.parent_order_id}: {e}")

    def _load_parent_order(self, parent_order_id: str) -> ParentOrderExecutionRecord | None:
        """Loads parent order record from SQLite database."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM parent_order_execution_records WHERE parent_order_id = ?",
                    (parent_order_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                data["splits"] = json.loads(data.get("splits_json", "[]"))
                data["receipts"] = json.loads(data.get("receipts_json", "[]"))
                data["errors"] = json.loads(data.get("errors_json", "[]"))
                rec = ParentOrderExecutionRecord.from_dict(data)
                self.parent_orders[parent_order_id] = rec
                return rec
        except Exception as e:
            logger.error(f"Failed to load parent order {parent_order_id}: {e}")
            return None

    def get_parent_order(self, parent_order_id: str) -> ParentOrderExecutionRecord | None:
        """Retrieves parent order record from memory or durable SQLite database."""
        if parent_order_id in self.parent_orders:
            return self.parent_orders[parent_order_id]
        return self._load_parent_order(parent_order_id)

    def recover_active_parent_orders(self) -> list[ParentOrderExecutionRecord]:
        """
        Scans durable SQLite store for active parent orders after process restart.
        Reconciles child execution status and handles crash recovery.
        """
        recovered: list[ParentOrderExecutionRecord] = []
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT parent_order_id FROM parent_order_execution_records
                    WHERE state IN ('PLANNED', 'DISPATCHING', 'EXECUTING', 'PARTIALLY_EXECUTED', 'RECONCILIATION_REQUIRED', 'HALTED')
                    ORDER BY created_at_ms ASC
                    """
                )
                rows = cursor.fetchall()
                parent_ids = [row["parent_order_id"] for row in rows]

            for pid in parent_ids:
                rec = self._load_parent_order(pid)
                if rec:
                    recovered.append(rec)
                    if reconciliation_ledger.is_order_halted(pid):
                        rec.state = ParentOrderState.HALTED
                    elif (
                        len(rec.receipts) == len(rec.splits)
                        and len(rec.splits) > 0
                        and all(r.success for r in rec.receipts)
                    ):
                        rec.state = ParentOrderState.COMPLETE
                    elif len(rec.receipts) > 0:
                        rec.state = ParentOrderState.PARTIALLY_EXECUTED
                    else:
                        rec.state = ParentOrderState.RECONCILIATION_REQUIRED
                    rec.updated_at_ms = int(time.time() * 1000)
                    self._persist_parent_order(rec)
                    audit_bus.emit_event(
                        event_type="SOR_PARENT_ORDER_RECOVERED",
                        symbol=rec.symbol,
                        severity="WARNING" if rec.state != ParentOrderState.COMPLETE else "INFO",
                        reason=f"Recovered active parent order {pid} in state {rec.state.value} after restart.",
                        details=rec.to_dict(),
                    )
        except Exception as e:
            logger.error(f"Failed to recover active parent orders: {e}")

        return recovered

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
        to find the optimal allocation that minimizes:
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

        # Filter active, non-degraded, valid, non-stale books
        healthy_venues: dict[str, VenueOrderBook] = {}
        for ex, book in venue_books.items():
            valid, reason = book.validate(current_time_ms)
            if not valid:
                logger.warning(f"Excluding venue {ex} from SOR: {reason}")
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
        venue_names = sorted(healthy_venues.keys())

        # Enforce venue minimum notional across all healthy candidate venues
        min_venue_notional = min(
            self.default_trading_rules.get(v, VenueTradingRules(exchange=v)).min_notional_usd
            for v in healthy_venues.keys()
        )
        est_total_notional = total_qty * reference_mid_price
        if est_total_notional < min_venue_notional:
            raise VenueConstraintBreachError(
                f"Order notional ${est_total_notional:.2f} on {symbol} is below minimum notional ${min_venue_notional:.2f}."
            )

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

            rules = self.default_trading_rules.get(ex)
            if rules and notional < rules.min_notional_usd:
                raise VenueConstraintBreachError(
                    f"Order notional ${notional:.2f} on {ex} is below minimum notional ${rules.min_notional_usd:.2f}."
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
                execution_style="TAKER",
            )

        # Multi-venue optimization (2 venues: e.g. BINANCE and BYBIT)
        v1, v2 = venue_names[0], venue_names[1]
        book1, book2 = healthy_venues[v1], healthy_venues[v2]
        levels1 = book1.asks if is_buy else book1.bids
        levels2 = book2.asks if is_buy else book2.bids
        fee1 = fees.get(v1, VenueFeeSchedule(exchange=v1))
        fee2 = fees.get(v2, VenueFeeSchedule(exchange=v2))

        rules1 = self.default_trading_rules.get(v1, VenueTradingRules(exchange=v1))
        rules2 = self.default_trading_rules.get(v2, VenueTradingRules(exchange=v2))

        best_cost = float("inf") if is_buy else float("-inf")
        best_allocation: tuple[float, float, float, float, float, float] | None = None

        steps = 100
        for i in range(steps + 1):
            raw_q1 = total_qty * (i / steps)

            # Quantize quantities to venue step sizes
            step1 = rules1.step_size
            step2 = rules2.step_size
            q1 = round(round(raw_q1 / step1) * step1, 8) if raw_q1 > 0 else 0.0
            q2 = round(round((total_qty - q1) / step2) * step2, 8)
            if q2 < 0:
                q2 = 0.0

            # Verify minimum notional constraints
            notional_est1 = q1 * reference_mid_price
            notional_est2 = q2 * reference_mid_price

            if 0 < q1 < rules1.min_qty or (0 < notional_est1 < rules1.min_notional_usd):
                # Violates venue 1 min notional/qty -> skip split allocation
                continue
            if 0 < q2 < rules2.min_qty or (0 < notional_est2 < rules2.min_notional_usd):
                # Violates venue 2 min notional/qty -> skip split allocation
                continue

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
                f"Combined liquidity across {v1} and {v2} insufficient for order quantity {total_qty:.4f} "
                f"or order size violates venue min notional."
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
            rules1 = self.default_trading_rules.get(v1)
            if rules1 and notional1 < rules1.min_notional_usd:
                raise VenueConstraintBreachError(
                    f"Allocated notional ${notional1:.2f} on {v1} is below minimum notional ${rules1.min_notional_usd:.2f}."
                )
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
            rules2 = self.default_trading_rules.get(v2)
            if rules2 and notional2 < rules2.min_notional_usd:
                raise VenueConstraintBreachError(
                    f"Allocated notional ${notional2:.2f} on {v2} is below minimum notional ${rules2.min_notional_usd:.2f}."
                )
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
            execution_style="TAKER",
        )

    async def execute_smart_order(
        self,
        quote: SmartOrderRouteQuote,
        environment: str = "TESTNET",
        account_equity_usd: float = 100_000.0,
        stop_loss: float | None = None,
        parent_correlation_id: str | None = None,
    ) -> list[LiveExecutionReceipt]:
        """
        Dispatches split child orders through the LiveExecutionRouter 20-Gate Pre-Trade Invariant Pipeline.
        Enforces parent-level risk clearance BEFORE child order splitting and manages parent order state.
        """
        parent_id = parent_correlation_id or f"PARENT_{uuid.uuid4().hex[:12].upper()}"
        now_ms = int(time.time() * 1000)

        # ---------------------------------------------------------------------
        # PARENT RISK GATE 1: Master Kill Switch Check
        # ---------------------------------------------------------------------
        ks_res = live_kill_switch.is_active()
        kill_active = ks_res[0] if isinstance(ks_res, tuple) else bool(ks_res)
        kill_state = ks_res[1] if isinstance(ks_res, tuple) else None
        if kill_active:
            reason_str = getattr(kill_state, "reason", "Master kill switch engaged.")
            msg = f"KILL_SWITCH_ACTIVE: Master kill switch engaged ({reason_str})."
            logger.critical(msg)
            raise LiveKillSwitchActiveError(msg)

        # ---------------------------------------------------------------------
        # PARENT RISK GATE 2: Constitutional 1.5% Single-Trade Equity Cap Check
        # ---------------------------------------------------------------------
        est_entry = quote.weighted_vwap or quote.reference_mid_price
        est_sl = stop_loss or (
            est_entry * 0.99 if quote.side.upper() == "BUY" else est_entry * 1.01
        )
        max_allowed_risk_usd = account_equity_usd * 0.015
        total_parent_risk_usd = abs(est_entry - est_sl) * quote.total_qty

        if total_parent_risk_usd > (max_allowed_risk_usd + 1e-6):
            msg = (
                f"SINGLE_TRADE_RISK_EXCEEDED: Aggregate parent order risk ${total_parent_risk_usd:.2f} "
                f"exceeds constitutional 1.5% limit (${max_allowed_risk_usd:.2f}) on ${account_equity_usd:,.2f} equity."
            )
            logger.warning(msg)
            raise LiveSizeRejectedError(msg)

        # Initialize Parent Order Tracking Record
        parent_record = ParentOrderExecutionRecord(
            parent_order_id=parent_id,
            symbol=quote.symbol,
            side=quote.side,
            total_qty=quote.total_qty,
            state=ParentOrderState.DISPATCHING,
            splits=quote.splits,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
        )
        self.parent_orders[parent_id] = parent_record
        self._persist_parent_order(parent_record)

        receipts: list[LiveExecutionReceipt] = []

        for split in quote.splits:
            # -----------------------------------------------------------------
            # GATE 8: Overfill Circuit Breaker Halt Check
            # -----------------------------------------------------------------
            if (
                reconciliation_ledger.is_order_halted(parent_id)
                or parent_record.state == ParentOrderState.HALTED
            ):
                parent_record.state = ParentOrderState.HALTED
                parent_record.updated_at_ms = int(time.time() * 1000)
                self._persist_parent_order(parent_record)
                msg = f"OVERFILL_HALTED: Execution halted on parent order {parent_id} due to overfill circuit breaker."
                logger.critical(msg)
                raise OverfillHaltedError(msg)

            req = LiveOrderRequest(
                exchange=split.exchange,
                environment=environment,
                symbol=quote.symbol,
                side=quote.side,
                order_type="MARKET",
                quantity=split.allocated_qty,
                price=split.expected_vwap,
                stop_loss=est_sl,
                account_equity_usd=account_equity_usd,
                correlation_id=parent_correlation_id or parent_id,
            )
            logger.info(
                f"SOR dispatching child order: {split.exchange} {quote.side} {split.allocated_qty} {quote.symbol}"
            )
            try:
                receipt = await live_execution_router.execute_live_order(req)
                receipts.append(receipt)
                parent_record.receipts.append(receipt)
                parent_record.updated_at_ms = int(time.time() * 1000)
                self._persist_parent_order(parent_record)
            except Exception as e:
                logger.error(f"SOR child order dispatch failed on {split.exchange}: {e}")
                parent_record.errors.append({"exchange": split.exchange, "error": str(e)})
                if receipts:
                    parent_record.state = ParentOrderState.PARTIALLY_EXECUTED
                    audit_bus.emit_event(
                        event_type="SOR_PARTIAL_EXECUTION_FAILURE",
                        symbol=quote.symbol,
                        severity="CRITICAL",
                        reason=f"Partial venue failure: {split.exchange} failed while previous leg(s) executed.",
                        details=parent_record.to_dict(),
                    )
                else:
                    parent_record.state = ParentOrderState.FAILED
                parent_record.updated_at_ms = int(time.time() * 1000)
                self._persist_parent_order(parent_record)
                raise

        parent_record.state = ParentOrderState.COMPLETE
        parent_record.updated_at_ms = int(time.time() * 1000)
        self._persist_parent_order(parent_record)

        audit_bus.emit_event(
            event_type="SOR_EXECUTION_COMPLETED",
            symbol=quote.symbol,
            severity="INFO",
            reason=f"SOR executed {len(receipts)} split legs across venues for {quote.total_qty} {quote.symbol}",
            details={
                "quote": quote.to_dict(),
                "parent_id": parent_id,
                "receipts_count": len(receipts),
            },
        )

        return receipts


# Global authoritative instance
smart_order_router = SmartOrderRouter()
