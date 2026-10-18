"""
core/execution/reconciliation_ledger.py
=======================================
High-Resolution Fill Reconciliation & Forensic Slippage Ledger.

GOVERNANCE CLASSIFICATION: CLASS H / CLASS G (EXECUTION BOUNDARY & RISK AUDIT)
=============================================================================
Records, reconciles, and audits every executed live/testnet trade against
pre-trade expectations. Decomposes execution quality:
  - Price slippage in basis points (bps)
  - Exchange maker/taker fees in USD
  - Monotonic nanosecond transit and round-trip latencies
  - Discrepancy detection (partial fills, overfills, slippage breaches)
  - Idempotent duplicate fill defense and out-of-order event aggregation

Persists records to SQLite WAL via db_manager with zero credential leakage.
=============================================================================
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.reconciliation_ledger")


# ---------------------------------------------------------------------------
# Monotonic Timing Helpers
# ---------------------------------------------------------------------------


def compute_monotonic_duration_ns(start_ns: int, end_ns: int) -> int:
    """
    Computes duration in nanoseconds using monotonic clock readings.
    Guarantees non-negative result even under NTP jumps or wall-clock skew.
    """
    if start_ns <= 0 or end_ns <= 0:
        return 0
    return max(0, end_ns - start_ns)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ExecutionReconciliationRecord:
    """Detailed forensic record of an executed child/parent order fill."""

    reconciliation_id: str
    parent_order_id: str
    client_order_id: str
    exchange_order_id: str
    exchange: str
    symbol: str
    side: str  # "BUY" or "SELL"
    requested_qty: float
    executed_qty: float
    expected_price: float
    executed_price: float
    slippage_bps: float
    fee_paid_usd: float
    fee_asset: str
    route_venue: str
    transit_latency_ms: float
    exchange_ack_latency_ms: float
    total_roundtrip_ms: float
    reconciliation_status: (
        str  # "MATCHED", "PARTIAL_FILL", "OVERFILL", "SLIPPAGE_BREACH", "DISCREPANCY"
    )
    created_at_ms: int
    reconciled_at_ms: int
    execution_id: str = ""
    dispatch_monotonic_ns: int = 0
    ack_monotonic_ns: int = 0
    fill_monotonic_ns: int = 0
    roundtrip_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CumulativeFillState:
    """Authoritative order lifecycle state aggregating multiple partial fills."""

    client_order_id: str
    exchange_order_id: str
    exchange: str
    requested_qty: float
    executed_qty: float = 0.0
    remaining_qty: float = 0.0
    weighted_executed_price: float = 0.0
    total_fee_usd: float = 0.0
    status: str = "NEW"  # "NEW", "PARTIAL_FILL", "COMPLETE", "OVERFILL", "CANCELLED"
    fill_count: int = 0
    parent_order_id: str = ""
    symbol: str = ""
    side: str = ""
    fills: list[dict[str, Any]] = field(default_factory=list)
    is_halted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Reconciliation Ledger Engine
# ---------------------------------------------------------------------------


class ReconciliationLedger:
    """
    High-Resolution forensic reconciliation ledger for Crypto Brain Terminal.
    Persists and aggregates fill quality, fees, and latency distributions.
    """

    def __init__(self) -> None:
        self._init_db_schema()
        # In-memory cumulative order state tracker: client_order_id -> CumulativeFillState
        self._cumulative_orders: dict[str, CumulativeFillState] = {}

    def _init_db_schema(self) -> None:
        """Initializes SQLite schema for execution reconciliation records."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_reconciliation_records (
                        reconciliation_id TEXT PRIMARY KEY,
                        parent_order_id TEXT NOT NULL,
                        client_order_id TEXT NOT NULL,
                        exchange_order_id TEXT NOT NULL,
                        execution_id TEXT NOT NULL DEFAULT '',
                        exchange TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        requested_qty REAL NOT NULL,
                        executed_qty REAL NOT NULL,
                        expected_price REAL NOT NULL,
                        executed_price REAL NOT NULL,
                        slippage_bps REAL NOT NULL,
                        fee_paid_usd REAL NOT NULL,
                        fee_asset TEXT NOT NULL,
                        route_venue TEXT NOT NULL,
                        transit_latency_ms REAL NOT NULL,
                        exchange_ack_latency_ms REAL NOT NULL,
                        total_roundtrip_ms REAL NOT NULL,
                        dispatch_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                        ack_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                        fill_monotonic_ns INTEGER NOT NULL DEFAULT 0,
                        roundtrip_ns INTEGER NOT NULL DEFAULT 0,
                        reconciliation_status TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL,
                        reconciled_at_ms INTEGER NOT NULL
                    );
                    """
                )

                # Safe column migration check
                cursor = conn.execute("PRAGMA table_info(execution_reconciliation_records);")
                existing_cols = {row[1] for row in cursor.fetchall()}
                if "execution_id" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE execution_reconciliation_records ADD COLUMN execution_id TEXT NOT NULL DEFAULT '';"
                    )
                if "dispatch_monotonic_ns" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE execution_reconciliation_records ADD COLUMN dispatch_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                    )
                if "ack_monotonic_ns" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE execution_reconciliation_records ADD COLUMN ack_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                    )
                if "fill_monotonic_ns" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE execution_reconciliation_records ADD COLUMN fill_monotonic_ns INTEGER NOT NULL DEFAULT 0;"
                    )
                if "roundtrip_ns" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE execution_reconciliation_records ADD COLUMN roundtrip_ns INTEGER NOT NULL DEFAULT 0;"
                    )

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rec_symbol ON execution_reconciliation_records(symbol);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rec_exchange ON execution_reconciliation_records(exchange);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rec_status ON execution_reconciliation_records(reconciliation_status);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rec_created ON execution_reconciliation_records(created_at_ms);"
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rec_unique_fill ON execution_reconciliation_records(exchange, exchange_order_id, execution_id);"
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize execution_reconciliation_records schema: {e}")

    @staticmethod
    def calculate_slippage_bps(side: str, expected_price: float, executed_price: float) -> float:
        """
        Computes price slippage in basis points.
        Positive bps = Favorable execution (Price Improvement)
        Negative bps = Adverse slippage (Paid more on BUY, received less on SELL)
        """
        if expected_price <= 0:
            return 0.0

        is_buy = side.upper().strip() == "BUY"
        if is_buy:
            diff = expected_price - executed_price
        else:
            diff = executed_price - expected_price

        return (diff / expected_price) * 10000.0

    def _emit_audit_safe(
        self,
        event_type: str,
        symbol: str,
        severity: str,
        reason: str,
        details: dict[str, Any],
    ) -> None:
        """Emits event to audit bus with fail-safe error boundary."""
        try:
            audit_bus.emit_event(
                event_type=event_type,
                symbol=symbol,
                severity=severity,
                reason=reason,
                details=details,
            )
        except Exception as e:
            logger.critical(
                f"Audit bus failed to emit {event_type} for {symbol}: {e}. Record persisted to WAL."
            )

    def record_fill(
        self,
        parent_order_id: str | ExecutionReconciliationRecord,
        client_order_id: str = "",
        exchange_order_id: str = "",
        exchange: str = "",
        symbol: str = "",
        side: str = "",
        requested_qty: float = 0.0,
        executed_qty: float = 0.0,
        expected_price: float = 0.0,
        executed_price: float = 0.0,
        fee_paid_usd: float = 0.0,
        fee_asset: str = "USDT",
        route_venue: str = "",
        transit_latency_ms: float = 0.0,
        exchange_ack_latency_ms: float = 0.0,
        total_roundtrip_ms: float = 0.0,
        max_allowed_slippage_bps: float = 50.0,
        created_at_ms: int | None = None,
        execution_id: str = "",
        dispatch_monotonic_ns: int = 0,
        ack_monotonic_ns: int = 0,
        fill_monotonic_ns: int = 0,
        roundtrip_ns: int = 0,
    ) -> ExecutionReconciliationRecord:
        """
        Ingests an executed order or fill, computes slippage, classifies reconciliation status,
        persists to SQLite with database-level uniqueness, and emits audit alerts if anomalies are found.
        Idempotently ignores duplicate fills. Supports receiving either parameters or an ExecutionReconciliationRecord.
        """
        if isinstance(parent_order_id, ExecutionReconciliationRecord):
            rec = parent_order_id
            return self.record_fill(
                parent_order_id=rec.parent_order_id,
                client_order_id=rec.client_order_id,
                exchange_order_id=rec.exchange_order_id,
                exchange=rec.exchange,
                symbol=rec.symbol,
                side=rec.side,
                requested_qty=rec.requested_qty,
                executed_qty=rec.executed_qty,
                expected_price=rec.expected_price,
                executed_price=rec.executed_price,
                fee_paid_usd=rec.fee_paid_usd,
                fee_asset=rec.fee_asset,
                route_venue=rec.route_venue,
                transit_latency_ms=rec.transit_latency_ms,
                exchange_ack_latency_ms=rec.exchange_ack_latency_ms,
                total_roundtrip_ms=rec.total_roundtrip_ms,
                created_at_ms=rec.created_at_ms,
                execution_id=getattr(rec, "execution_id", ""),
            )
        now_ms = int(time.time() * 1000)
        c_ms = created_at_ms if created_at_ms is not None else now_ms
        eff_exec_id = execution_id or exchange_order_id or f"EXEC_{uuid.uuid4().hex[:8].upper()}"

        # 1. Check existing record for idempotent deduplication
        existing = self.get_record_by_fill(exchange, exchange_order_id, eff_exec_id)
        if existing is not None:
            logger.info(
                f"Duplicate fill detected and idempotently ignored: {exchange} {exchange_order_id} {eff_exec_id}"
            )
            return existing

        rec_id = f"REC_{uuid.uuid4().hex[:12].upper()}"
        slippage_bps = self.calculate_slippage_bps(side, expected_price, executed_price)

        # 2. Compute nanosecond durations if provided
        calc_roundtrip_ns = roundtrip_ns
        if calc_roundtrip_ns == 0 and dispatch_monotonic_ns > 0 and fill_monotonic_ns > 0:
            calc_roundtrip_ns = compute_monotonic_duration_ns(
                dispatch_monotonic_ns, fill_monotonic_ns
            )

        # 3. Classify status
        qty_diff = abs(executed_qty - requested_qty)
        qty_tolerance = max(0.0001, requested_qty * 0.001)

        if executed_qty == 0:
            status = "UNFILLED_DISCREPANCY"
        elif qty_diff > qty_tolerance and executed_qty < requested_qty:
            status = "PARTIAL_FILL"
        elif executed_qty > (requested_qty + qty_tolerance):
            status = "OVERFILL"
        elif slippage_bps < -max_allowed_slippage_bps:
            status = "SLIPPAGE_BREACH"
        else:
            status = "MATCHED"

        record = ExecutionReconciliationRecord(
            reconciliation_id=rec_id,
            parent_order_id=parent_order_id,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            execution_id=eff_exec_id,
            exchange=exchange,
            symbol=symbol,
            side=side.upper(),
            requested_qty=requested_qty,
            executed_qty=executed_qty,
            expected_price=expected_price,
            executed_price=executed_price,
            slippage_bps=slippage_bps,
            fee_paid_usd=fee_paid_usd,
            fee_asset=fee_asset,
            route_venue=route_venue or exchange,
            transit_latency_ms=transit_latency_ms,
            exchange_ack_latency_ms=exchange_ack_latency_ms,
            total_roundtrip_ms=total_roundtrip_ms,
            dispatch_monotonic_ns=dispatch_monotonic_ns,
            ack_monotonic_ns=ack_monotonic_ns,
            fill_monotonic_ns=fill_monotonic_ns,
            roundtrip_ns=calc_roundtrip_ns,
            reconciliation_status=status,
            created_at_ms=c_ms,
            reconciled_at_ms=now_ms,
        )

        self._persist_record(record)

        if status in ("SLIPPAGE_BREACH", "OVERFILL", "UNFILLED_DISCREPANCY"):
            self._emit_audit_safe(
                event_type="EXECUTION_RECONCILIATION_ANOMALY",
                symbol=symbol,
                severity="CRITICAL" if status == "OVERFILL" else "ERROR",
                reason=f"Execution anomaly: {status} (Slippage: {slippage_bps:.1f} bps, Exec Qty: {executed_qty}/{requested_qty})",
                details=record.to_dict(),
            )

        return record

    def record_fill_event(
        self,
        parent_order_id: str,
        client_order_id: str,
        exchange_order_id: str,
        execution_id: str,
        exchange: str,
        symbol: str,
        side: str,
        requested_qty: float,
        fill_qty: float,
        fill_price: float,
        expected_price: float,
        fee_paid_usd: float = 0.0,
        fee_asset: str = "USDT",
        route_venue: str = "",
        dispatch_monotonic_ns: int = 0,
        ack_monotonic_ns: int = 0,
        fill_monotonic_ns: int = 0,
        roundtrip_ns: int = 0,
        max_allowed_slippage_bps: float = 50.0,
        created_at_ms: int | None = None,
    ) -> tuple[ExecutionReconciliationRecord, CumulativeFillState]:
        """
        Authoritative event ingestion for multi-fill order streams.
        Reconciles cumulative executed quantities, handles out-of-order fill events,
        detects cumulative overfill, and persists discrete fill records idempotently.
        """
        # Retrieve or initialize cumulative state for client_order_id
        if client_order_id not in self._cumulative_orders:
            self._cumulative_orders[client_order_id] = CumulativeFillState(
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
                exchange=exchange,
                parent_order_id=parent_order_id,
                symbol=symbol,
                side=side.upper(),
                requested_qty=requested_qty,
                executed_qty=0.0,
                remaining_qty=requested_qty,
                weighted_executed_price=0.0,
                total_fee_usd=0.0,
                status="NEW",
                fill_count=0,
                fills=[],
            )

        order_state = self._cumulative_orders[client_order_id]

        # Deduplicate fill by execution_id
        existing_fill = next(
            (f for f in order_state.fills if f.get("execution_id") == execution_id),
            None,
        )
        if existing_fill is not None:
            logger.info(
                f"Duplicate fill {execution_id} ignored in order stream for {client_order_id}"
            )
            rec = self.get_record_by_fill(exchange, exchange_order_id, execution_id)
            if rec is not None:
                return rec, order_state

        # Register fill event
        order_state.fills.append(
            {
                "execution_id": execution_id,
                "qty": fill_qty,
                "price": fill_price,
                "fee_usd": fee_paid_usd,
                "fill_monotonic_ns": fill_monotonic_ns,
            }
        )
        order_state.fill_count += 1
        order_state.total_fee_usd += fee_paid_usd

        # Re-compute cumulative metrics deterministically across all distinct fills
        tot_qty = sum(f["qty"] for f in order_state.fills)
        tot_notional = sum(f["qty"] * f["price"] for f in order_state.fills)
        vwap = (tot_notional / tot_qty) if tot_qty > 0 else fill_price

        order_state.executed_qty = tot_qty
        order_state.remaining_qty = max(0.0, requested_qty - tot_qty)
        order_state.weighted_executed_price = vwap

        # Classify order state
        qty_tolerance = max(0.0001, requested_qty * 0.001)
        if tot_qty > (requested_qty + qty_tolerance):
            order_state.status = "OVERFILL"
            order_state.is_halted = True
            self._emit_audit_safe(
                event_type="EXECUTION_OVERFILL_BREACH",
                symbol=symbol,
                severity="CRITICAL",
                reason=f"Cumulative overfill breach: {tot_qty:.4f} > requested {requested_qty:.4f}",
                details=order_state.to_dict(),
            )
        elif abs(tot_qty - requested_qty) <= qty_tolerance:
            order_state.status = "COMPLETE"
        elif tot_qty < requested_qty:
            order_state.status = "PARTIAL_FILL"

        # Record discrete fill record in database
        rec = self.record_fill(
            parent_order_id=parent_order_id,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            requested_qty=requested_qty,
            executed_qty=fill_qty,
            expected_price=expected_price,
            executed_price=fill_price,
            fee_paid_usd=fee_paid_usd,
            fee_asset=fee_asset,
            route_venue=route_venue,
            dispatch_monotonic_ns=dispatch_monotonic_ns,
            ack_monotonic_ns=ack_monotonic_ns,
            fill_monotonic_ns=fill_monotonic_ns,
            roundtrip_ns=roundtrip_ns,
            max_allowed_slippage_bps=max_allowed_slippage_bps,
            created_at_ms=created_at_ms,
            execution_id=execution_id,
        )

        return rec, order_state

    def get_order_cumulative_state(self, client_order_id: str) -> CumulativeFillState | None:
        """Returns in-memory cumulative fill state for an order if tracked."""
        return self._cumulative_orders.get(client_order_id)

    def is_order_halted(self, order_id: str) -> bool:
        """Returns whether execution is halted for an order or parent order due to overfill circuit breaker."""
        if not order_id:
            return False
        if order_id in self._cumulative_orders and self._cumulative_orders[order_id].is_halted:
            return True
        for state in self._cumulative_orders.values():
            if (
                state.parent_order_id == order_id or state.client_order_id == order_id
            ) and state.is_halted:
                return True
        return False

    def get_record_by_fill(
        self,
        exchange: str,
        exchange_order_id: str,
        execution_id: str,
    ) -> ExecutionReconciliationRecord | None:
        """Queries an existing fill record by unique key for idempotent deduplication."""
        query = """
            SELECT * FROM execution_reconciliation_records
            WHERE exchange = ? AND exchange_order_id = ? AND execution_id = ?
            LIMIT 1;
        """
        try:
            with db_manager.get_trading_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, (exchange, exchange_order_id, execution_id))
                row = cursor.fetchone()
                if row:
                    return ExecutionReconciliationRecord(**dict(row))
        except Exception as e:
            logger.error(f"Error querying fill by execution_id: {e}")
        return None

    def _persist_record(self, r: ExecutionReconciliationRecord) -> None:
        """Saves reconciliation record to SQLite database with insert-or-ignore semantics."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO execution_reconciliation_records (
                        reconciliation_id, parent_order_id, client_order_id, exchange_order_id,
                        execution_id, exchange, symbol, side, requested_qty, executed_qty,
                        expected_price, executed_price, slippage_bps, fee_paid_usd,
                        fee_asset, route_venue, transit_latency_ms, exchange_ack_latency_ms,
                        total_roundtrip_ms, dispatch_monotonic_ns, ack_monotonic_ns,
                        fill_monotonic_ns, roundtrip_ns, reconciliation_status,
                        created_at_ms, reconciled_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.reconciliation_id,
                        r.parent_order_id,
                        r.client_order_id,
                        r.exchange_order_id,
                        r.execution_id,
                        r.exchange,
                        r.symbol,
                        r.side,
                        r.requested_qty,
                        r.executed_qty,
                        r.expected_price,
                        r.executed_price,
                        r.slippage_bps,
                        r.fee_paid_usd,
                        r.fee_asset,
                        r.route_venue,
                        r.transit_latency_ms,
                        r.exchange_ack_latency_ms,
                        r.total_roundtrip_ms,
                        r.dispatch_monotonic_ns,
                        r.ack_monotonic_ns,
                        r.fill_monotonic_ns,
                        r.roundtrip_ns,
                        r.reconciliation_status,
                        r.created_at_ms,
                        r.reconciled_at_ms,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist reconciliation record {r.reconciliation_id}: {e}")

    def list_records(
        self,
        limit: int = 50,
        symbol: str | None = None,
        exchange: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Returns paginated reconciliation records with forensic filters."""
        query = "SELECT * FROM execution_reconciliation_records WHERE 1=1"
        params: list[Any] = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)
        if status:
            query += " AND reconciliation_status = ?"
            params.append(status)

        query += " ORDER BY created_at_ms DESC LIMIT ?"
        params.append(limit)

        records: list[dict[str, Any]] = []
        try:
            with db_manager.get_trading_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    records.append(dict(row))
        except Exception as e:
            logger.error(f"Error querying execution_reconciliation_records: {e}")

        return records

    def get_reconciliation_summary(
        self,
        symbol: str | None = None,
        exchange: str | None = None,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """
        Computes aggregate execution quality metrics over a time window.
        """
        cutoff_ms = int((time.time() - (window_hours * 3600)) * 1000)
        query = "SELECT * FROM execution_reconciliation_records WHERE created_at_ms >= ?"
        params: list[Any] = [cutoff_ms]

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if exchange:
            query += " AND exchange = ?"
            params.append(exchange)

        total_orders = 0
        status_counts: dict[str, int] = {}
        total_slippage = 0.0
        max_adverse_slippage_bps = 0.0
        total_fees_usd = 0.0
        total_roundtrip_ms = 0.0
        total_roundtrip_ns = 0
        venue_distribution: dict[str, int] = {}

        try:
            with db_manager.get_trading_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    total_orders += 1
                    st = row["reconciliation_status"]
                    status_counts[st] = status_counts.get(st, 0) + 1

                    slip = float(row["slippage_bps"])
                    total_slippage += slip
                    if slip < max_adverse_slippage_bps:
                        max_adverse_slippage_bps = slip

                    total_fees_usd += float(row["fee_paid_usd"])
                    total_roundtrip_ms += float(row["total_roundtrip_ms"])
                    total_roundtrip_ns += int(row["roundtrip_ns"] or 0)

                    v = row["route_venue"]
                    venue_distribution[v] = venue_distribution.get(v, 0) + 1
        except Exception as e:
            logger.error(f"Error computing reconciliation summary: {e}")

        avg_slippage = (total_slippage / total_orders) if total_orders > 0 else 0.0
        avg_roundtrip = (total_roundtrip_ms / total_orders) if total_orders > 0 else 0.0
        avg_roundtrip_ns = (total_roundtrip_ns // total_orders) if total_orders > 0 else 0
        matched_count = status_counts.get("MATCHED", 0)
        fill_rate_pct = ((matched_count) / total_orders * 100.0) if total_orders > 0 else 100.0

        return {
            "window_hours": window_hours,
            "total_reconciled_orders": total_orders,
            "fill_rate_pct": round(fill_rate_pct, 2),
            "status_breakdown": status_counts,
            "average_slippage_bps": round(avg_slippage, 2),
            "max_adverse_slippage_bps": round(max_adverse_slippage_bps, 2),
            "total_fees_usd": round(total_fees_usd, 4),
            "average_roundtrip_latency_ms": round(avg_roundtrip, 2),
            "average_roundtrip_latency_ns": avg_roundtrip_ns,
            "venue_distribution": venue_distribution,
        }


# Global authoritative instance
reconciliation_ledger = ReconciliationLedger()
