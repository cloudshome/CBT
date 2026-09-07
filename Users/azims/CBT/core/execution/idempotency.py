"""
core/execution/idempotency.py
=============================
Durable Idempotency & Order Reconciliation Engine for Live Execution.

Critical Invariants:
- Format: CBT_{VENUE}_{TIMESTAMP_MS}_{NONCE} (max 36 chars per Binance/Bybit API limits).
- Atomic Reservation: Duplicate submission attempts fail closed with DuplicateOrderError.
- Ambiguous State Tracking: Network timeouts or dropped packets transition order to
  AMBIGUOUS_RECONCILIATION_REQUIRED rather than triggering dangerous blind retries.
- Survives process restarts via durable SQLite WAL persistence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.auth.credential_vault import sanitize_dict, sanitize_text
from core.database import db_manager

logger = logging.getLogger("sky.live_idempotency")


class IdempotencyError(Exception):
    """Base exception for order idempotency violations."""


class DuplicateOrderError(IdempotencyError):
    """Raised when an order with the same client order ID or active submission is detected."""


class AmbiguousOrderError(IdempotencyError):
    """Raised when order submission state is ambiguous and requires status query reconciliation."""


class OrderStatus:
    RESERVED = "RESERVED"
    DISPATCHED = "DISPATCHED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    AMBIGUOUS_RECONCILIATION_REQUIRED = "AMBIGUOUS_RECONCILIATION_REQUIRED"


def generate_client_order_id(venue: str) -> str:
    """
    Generates unique client order ID strictly conforming to exchange length restrictions.
    Binance max length: 36 chars.
    Bybit max length: 36 chars.
    Format: CBT_{VENUE_3}_{TIMESTAMP_13}_{NONCE_8} -> exactly 30-32 chars.
    """
    v_short = venue.upper().replace("_", "")[:3]  # "BIN", "BYB"
    now_ms = int(time.time() * 1000)
    nonce = uuid.uuid4().hex[:8]
    cid = f"CBT_{v_short}_{now_ms}_{nonce}"
    if len(cid) > 36:
        cid = cid[:36]
    return cid


@dataclass
class IdempotencyRecord:
    client_order_id: str
    exchange: str
    environment: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    status: str
    exchange_order_id: str | None = None
    error_message: str | None = None
    created_at: int = 0
    updated_at: int = 0
    reconciled_at: int | None = None
    audit_payload_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiveOrderIdempotencyStore:
    """
    SQLite WAL-backed persistent idempotency and reconciliation ledger.
    """

    def __init__(self):
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS live_order_idempotency (
                        client_order_id TEXT PRIMARY KEY,
                        exchange TEXT NOT NULL,
                        environment TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        order_type TEXT NOT NULL,
                        quantity REAL NOT NULL,
                        price REAL,
                        status TEXT NOT NULL,
                        exchange_order_id TEXT,
                        error_message TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        reconciled_at INTEGER,
                        audit_payload_json TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_idemp_exch_id ON live_order_idempotency(exchange_order_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_idemp_status ON live_order_idempotency(status)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize live_order_idempotency table: {e}")

    def reserve_order(
        self,
        client_order_id: str,
        exchange: str,
        environment: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None,
        audit_payload: dict[str, Any] | None = None,
    ) -> IdempotencyRecord:
        """
        Atomically reserves an order record in RESERVED status before network dispatch.
        Fails if client_order_id already exists.
        """
        now_ms = int(time.time() * 1000)
        clean_audit = sanitize_dict(audit_payload or {})
        audit_json = json.dumps(clean_audit)

        record = IdempotencyRecord(
            client_order_id=client_order_id,
            exchange=exchange.upper(),
            environment=environment.upper(),
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=quantity,
            price=price,
            status=OrderStatus.RESERVED,
            created_at=now_ms,
            updated_at=now_ms,
            audit_payload_json=audit_json,
        )

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO live_order_idempotency (
                        client_order_id, exchange, environment, symbol, side, order_type,
                        quantity, price, status, created_at, updated_at, audit_payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.client_order_id,
                        record.exchange,
                        record.environment,
                        record.symbol,
                        record.side,
                        record.order_type,
                        record.quantity,
                        record.price,
                        record.status,
                        record.created_at,
                        record.updated_at,
                        record.audit_payload_json,
                    ),
                )
                conn.commit()
            return record
        except sqlite3.IntegrityError as e:
            msg = f"Duplicate Order Detected: Client order ID '{client_order_id}' has already been reserved or executed."
            logger.error(msg)
            raise DuplicateOrderError(msg) from e

    def mark_dispatched(self, client_order_id: str) -> None:
        """Transitions order status to DISPATCHED once network transmission has initiated."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                UPDATE live_order_idempotency
                SET status = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (OrderStatus.DISPATCHED, now_ms, client_order_id),
            )
            conn.commit()

    def mark_final(
        self,
        client_order_id: str,
        status: str,
        exchange_order_id: str | None = None,
        error_message: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        """Transitions order to definitive outcome (FILLED, REJECTED, CANCELLED, etc.)."""
        now_ms = int(time.time() * 1000)
        safe_response = sanitize_dict(raw_response or {})
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                UPDATE live_order_idempotency
                SET status = ?, exchange_order_id = ?, error_message = ?, updated_at = ?, audit_payload_json = ?
                WHERE client_order_id = ?
                """,
                (
                    status,
                    exchange_order_id,
                    sanitize_text(error_message or "") if error_message else None,
                    now_ms,
                    json.dumps(safe_response),
                    client_order_id,
                ),
            )
            conn.commit()

    def mark_ambiguous(self, client_order_id: str, error_reason: str) -> None:
        """
        Transitions order to AMBIGUOUS_RECONCILIATION_REQUIRED when network outcome is indeterminate
        (e.g., timeout, connection reset, HTTP 504).
        """
        now_ms = int(time.time() * 1000)
        clean_err = sanitize_text(error_reason)
        logger.warning(
            f"ORDER MARKED AMBIGUOUS: {client_order_id}. Reason: {clean_err}. Blind retry strictly prohibited."
        )
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                UPDATE live_order_idempotency
                SET status = ?, error_message = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (OrderStatus.AMBIGUOUS_RECONCILIATION_REQUIRED, clean_err, now_ms, client_order_id),
            )
            conn.commit()

    def mark_reconciled(
        self,
        client_order_id: str,
        resolved_status: str,
        exchange_order_id: str | None = None,
        notes: str = "",
    ) -> None:
        """Marks an ambiguous order as safely resolved via reconciliation query."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                UPDATE live_order_idempotency
                SET status = ?, exchange_order_id = COALESCE(?, exchange_order_id),
                    error_message = ?, reconciled_at = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (resolved_status, exchange_order_id, sanitize_text(notes), now_ms, now_ms, client_order_id),
            )
            conn.commit()

    def get_order_record(self, client_order_id: str) -> IdempotencyRecord | None:
        """Fetches stored idempotency record."""
        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM live_order_idempotency WHERE client_order_id = ?",
                (client_order_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return IdempotencyRecord(**dict(row))

    def get_ambiguous_orders(self) -> list[IdempotencyRecord]:
        """Returns all unresolved ambiguous orders requiring status reconciliation."""
        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM live_order_idempotency WHERE status = ? ORDER BY created_at DESC",
                (OrderStatus.AMBIGUOUS_RECONCILIATION_REQUIRED,),
            )
            rows = cursor.fetchall()
            return [IdempotencyRecord(**dict(r)) for r in rows]

    def get_recent_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns recent order history sanitized for UI/audit display."""
        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT client_order_id, exchange, environment, symbol, side, order_type,
                       quantity, price, status, exchange_order_id, error_message, created_at, updated_at
                FROM live_order_idempotency
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


# Global singleton instance
idempotency_store = LiveOrderIdempotencyStore()
