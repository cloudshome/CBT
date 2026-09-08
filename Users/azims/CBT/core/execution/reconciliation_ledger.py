"""
core/execution/reconciliation_ledger.py
=======================================
High-Frequency Sub-Millisecond Fill Reconciliation & Forensic Slippage Ledger.

GOVERNANCE CLASSIFICATION: CLASS H / CLASS G (EXECUTION BOUNDARY & RISK AUDIT)
=============================================================================
Records, reconciles, and audits every executed live/testnet trade against
pre-trade expectations. Decomposes execution quality:
  - Price slippage in basis points (bps)
  - Exchange maker/taker fees in USD
  - Monotonic transit and round-trip latencies
  - Discrepancy detection (partial fills, overfills, slippage breaches)

Persists records to SQLite WAL via db_manager with zero credential leakage.
=============================================================================
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.reconciliation_ledger")


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Reconciliation Ledger Engine
# ---------------------------------------------------------------------------


class ReconciliationLedger:
    """
    Sub-millisecond forensic reconciliation ledger for Crypto Brain Terminal.
    Persists and aggregates fill quality, fees, and latency distributions.
    """

    def __init__(self) -> None:
        self._init_db_schema()

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
                        reconciliation_status TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL,
                        reconciled_at_ms INTEGER NOT NULL
                    );
                    """
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
                conn.commit()
        except Exception as e:  # noqa: BLE001
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
            # If executed < expected, paid less -> favorable (+)
            # If executed > expected, paid more -> adverse (-)
            diff = expected_price - executed_price
        else:
            # If executed > expected, received more -> favorable (+)
            # If executed < expected, received less -> adverse (-)
            diff = executed_price - expected_price

        return (diff / expected_price) * 10000.0

    def record_fill(
        self,
        parent_order_id: str,
        client_order_id: str,
        exchange_order_id: str,
        exchange: str,
        symbol: str,
        side: str,
        requested_qty: float,
        executed_qty: float,
        expected_price: float,
        executed_price: float,
        fee_paid_usd: float = 0.0,
        fee_asset: str = "USDT",
        route_venue: str = "",
        transit_latency_ms: float = 0.0,
        exchange_ack_latency_ms: float = 0.0,
        total_roundtrip_ms: float = 0.0,
        max_allowed_slippage_bps: float = 50.0,
        created_at_ms: int | None = None,
    ) -> ExecutionReconciliationRecord:
        """
        Ingests an executed order, computes slippage, classifies reconciliation status,
        persists to SQLite, and emits audit bus alerts if anomalies are found.
        """
        now_ms = int(time.time() * 1000)
        c_ms = created_at_ms if created_at_ms is not None else now_ms
        rec_id = f"REC_{uuid.uuid4().hex[:12].upper()}"

        slippage_bps = self.calculate_slippage_bps(side, expected_price, executed_price)

        # Classify status
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
            reconciliation_status=status,
            created_at_ms=c_ms,
            reconciled_at_ms=now_ms,
        )

        self._persist_record(record)

        if status in ("SLIPPAGE_BREACH", "OVERFILL", "UNFILLED_DISCREPANCY"):
            audit_bus.emit_event(
                event_type="EXECUTION_RECONCILIATION_ANOMALY",
                symbol=symbol,
                severity="WARNING" if status == "PARTIAL_FILL" else "ERROR",
                reason=f"Execution anomaly: {status} (Slippage: {slippage_bps:.1f} bps, Exec Qty: {executed_qty}/{requested_qty})",
                details=record.to_dict(),
            )

        return record

    def _persist_record(self, r: ExecutionReconciliationRecord) -> None:
        """Saves reconciliation record to database."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO execution_reconciliation_records (
                        reconciliation_id, parent_order_id, client_order_id, exchange_order_id,
                        exchange, symbol, side, requested_qty, executed_qty,
                        expected_price, executed_price, slippage_bps, fee_paid_usd,
                        fee_asset, route_venue, transit_latency_ms, exchange_ack_latency_ms,
                        total_roundtrip_ms, reconciliation_status, created_at_ms, reconciled_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.reconciliation_id,
                        r.parent_order_id,
                        r.client_order_id,
                        r.exchange_order_id,
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
                        r.reconciliation_status,
                        r.created_at_ms,
                        r.reconciled_at_ms,
                    ),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
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

                    v = row["route_venue"]
                    venue_distribution[v] = venue_distribution.get(v, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error computing reconciliation summary: {e}")

        avg_slippage = (total_slippage / total_orders) if total_orders > 0 else 0.0
        avg_roundtrip = (total_roundtrip_ms / total_orders) if total_orders > 0 else 0.0
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
            "venue_distribution": venue_distribution,
        }


# Global authoritative instance
reconciliation_ledger = ReconciliationLedger()
