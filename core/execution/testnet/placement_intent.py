"""
core/execution/testnet/placement_intent.py
==========================================
Milestone 22: Durable Placement Intent & Identity Reuse Contract.

Implements Section 4 & Section 7:
- Immutable Domain Identity:
  flight_id -> parent_order_id -> child_slice_id -> placement_intent_id -> venue_order_id -> execution_id
- A retry of the same logical slice MUST reuse the same placement_intent_id.
- Durable persistence of intent before wire dispatch (T0 -> T1).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from core.execution.testnet.models import CanonicalOrderStatus, OrderSide, OrderType


@dataclass(frozen=True)
class PlacementIntent:
    """
    Durable placement intent contract.
    Persisted before wire transmission; reused across retries of the same slice.
    """

    flight_id: str
    parent_order_id: str
    child_slice_id: str
    intent_id: str
    venue: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None
    created_at_utc: str
    created_monotonic_ns: int
    retry_count: int = 0
    canonical_status: CanonicalOrderStatus = CanonicalOrderStatus.CREATED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quantity"] = str(self.quantity)
        if self.price is not None:
            d["price"] = str(self.price)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        d["canonical_status"] = self.canonical_status.value
        return d


class DurableIntentStore:
    """
    SQLite-backed durable intent store ensuring replay-safe placement recovery.
    """

    def __init__(self, db_conn: sqlite3.Connection | None = None) -> None:
        self._db_conn = db_conn
        self._memory_store: dict[str, PlacementIntent] = {}
        if self._db_conn:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        assert self._db_conn is not None
        cursor = self._db_conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS testnet_placement_intents (
                intent_id TEXT PRIMARY KEY,
                flight_id TEXT NOT NULL,
                parent_order_id TEXT NOT NULL,
                child_slice_id TEXT NOT NULL,
                venue TEXT NOT NULL,
                client_order_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT,
                created_at_utc TEXT NOT NULL,
                created_monotonic_ns INTEGER NOT NULL,
                retry_count INTEGER NOT NULL,
                canonical_status TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_intent_parent
            ON testnet_placement_intents(parent_order_id);
            """
        )
        self._db_conn.commit()

    def persist_intent(self, intent: PlacementIntent) -> None:
        """Persists placement intent before wire dispatch."""
        self._memory_store[intent.intent_id] = intent
        if self._db_conn:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO testnet_placement_intents (
                    intent_id, flight_id, parent_order_id, child_slice_id,
                    venue, client_order_id, symbol, side, order_type,
                    quantity, price, created_at_utc, created_monotonic_ns,
                    retry_count, canonical_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.intent_id,
                    intent.flight_id,
                    intent.parent_order_id,
                    intent.child_slice_id,
                    intent.venue,
                    intent.client_order_id,
                    intent.symbol,
                    intent.side.value,
                    intent.order_type.value,
                    str(intent.quantity),
                    str(intent.price) if intent.price is not None else None,
                    intent.created_at_utc,
                    intent.created_monotonic_ns,
                    intent.retry_count,
                    intent.canonical_status.value,
                ),
            )
            self._db_conn.commit()

    def get_intent(self, intent_id: str) -> PlacementIntent | None:
        """Retrieves intent by intent_id."""
        if intent_id in self._memory_store:
            return self._memory_store[intent_id]
        if self._db_conn:
            cursor = self._db_conn.cursor()
            cursor.execute(
                "SELECT * FROM testnet_placement_intents WHERE intent_id = ?", (intent_id,)
            )
            row = cursor.fetchone()
            if row:
                intent = PlacementIntent(
                    intent_id=row[0],
                    flight_id=row[1],
                    parent_order_id=row[2],
                    child_slice_id=row[3],
                    venue=row[4],
                    client_order_id=row[5],
                    symbol=row[6],
                    side=OrderSide(row[7]),
                    order_type=OrderType(row[8]),
                    quantity=Decimal(row[9]),
                    price=Decimal(row[10]) if row[10] is not None else None,
                    created_at_utc=row[11],
                    created_monotonic_ns=row[12],
                    retry_count=row[13],
                    canonical_status=CanonicalOrderStatus(row[14]),
                )
                self._memory_store[intent_id] = intent
                return intent
        return None

    def create_or_reuse_intent(
        self,
        flight_id: str,
        parent_order_id: str,
        child_slice_id: str,
        venue: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Decimal | None,
        is_retry: bool = False,
    ) -> PlacementIntent:
        """
        Creates a new placement intent or reuses existing intent identity for retries.
        """
        # Intent ID derived deterministically from child slice ID to ensure collision resistance
        raw_seed = f"{flight_id}:{parent_order_id}:{child_slice_id}"
        intent_hash = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:12].upper()
        intent_id = f"INT_{intent_hash}"

        existing = self.get_intent(intent_id)
        if existing and is_retry:
            updated = PlacementIntent(
                flight_id=existing.flight_id,
                parent_order_id=existing.parent_order_id,
                child_slice_id=existing.child_slice_id,
                intent_id=existing.intent_id,
                venue=existing.venue,
                client_order_id=existing.client_order_id,
                symbol=existing.symbol,
                side=existing.side,
                order_type=existing.order_type,
                quantity=existing.quantity,
                price=existing.price,
                created_at_utc=existing.created_at_utc,
                created_monotonic_ns=existing.created_monotonic_ns,
                retry_count=existing.retry_count + 1,
                canonical_status=existing.canonical_status,
            )
            self.persist_intent(updated)
            return updated

        # Format client order ID (max 36 chars across Binance and Bybit)
        client_order_id = f"M22_{intent_hash}_{child_slice_id[-6:]}"[:36]
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        now_mono = time.monotonic_ns()

        intent = PlacementIntent(
            flight_id=flight_id,
            parent_order_id=parent_order_id,
            child_slice_id=child_slice_id,
            intent_id=intent_id,
            venue=venue,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            created_at_utc=now_utc,
            created_monotonic_ns=now_mono,
            retry_count=0,
            canonical_status=CanonicalOrderStatus.READY,
        )
        self.persist_intent(intent)
        return intent
