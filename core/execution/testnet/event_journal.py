"""
core/execution/testnet/event_journal.py
=======================================
Milestone 22: Append-Only Event Journal & Forensic Deduplication Shield.

Implements Section 10:
- Immutable, append-only raw event preservation with SHA-256 content hashes.
- Authoritative execution identifier preference.
- Strict conflicting duplicate defense: matching execution_id with differing
  economic parameters (price, quantity, symbol, side) preserves both events,
  halts the affected order lifecycle, records forensic evidence, and fails closed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sky.execution.testnet.journal")


class ConflictingEventAnomalyError(Exception):
    """Raised when an incoming event conflicts with a previously journaled event."""


class EventProcessingStatus(StrEnum):
    """Processing status for journaled raw events."""

    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    CONFLICT_HALTED = "CONFLICT_HALTED"


@dataclass(frozen=True)
class JournaledEvent:
    """
    Append-only forensic raw event record.
    """

    event_id: str
    venue: str
    event_type: str
    raw_payload_json: str
    reception_utc: str
    received_monotonic_ns: int
    venue_timestamp_ms: int
    source_channel: str
    flight_id: str
    parent_order_id: str
    child_slice_id: str
    intent_id: str
    processing_status: EventProcessingStatus
    content_hash_sha256: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["processing_status"] = self.processing_status.value
        return d


class AppendOnlyEventJournal:
    """
    Append-only SQLite and in-memory event journal with conflicting duplicate protection.
    """

    def __init__(self, db_conn: sqlite3.Connection | None = None) -> None:
        self._db_conn = db_conn
        self._events: list[JournaledEvent] = []
        # Key: (venue, execution_id) -> (price, quantity, symbol, side, event_id)
        self._known_executions: dict[str, tuple[Decimal, Decimal, str, str, str]] = {}
        self.total_events_received: int = 0
        self.total_duplicates_detected: int = 0
        self.total_conflicts_detected: int = 0

        if self._db_conn:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        assert self._db_conn is not None
        cursor = self._db_conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS testnet_event_journal (
                event_id TEXT PRIMARY KEY,
                venue TEXT NOT NULL,
                event_type TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                reception_utc TEXT NOT NULL,
                received_monotonic_ns INTEGER NOT NULL,
                venue_timestamp_ms INTEGER NOT NULL,
                source_channel TEXT NOT NULL,
                flight_id TEXT NOT NULL,
                parent_order_id TEXT NOT NULL,
                child_slice_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                processing_status TEXT NOT NULL,
                content_hash_sha256 TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_journal_slice
            ON testnet_event_journal(child_slice_id);
            """
        )
        self._db_conn.commit()

    def record_event(
        self,
        venue: str,
        event_type: str,
        raw_payload: dict[str, Any] | str,
        source_channel: str,
        flight_id: str = "UNKNOWN",
        parent_order_id: str = "UNKNOWN",
        child_slice_id: str = "UNKNOWN",
        intent_id: str = "UNKNOWN",
        venue_timestamp_ms: int = 0,
        execution_id: str | None = None,
        exec_price: Decimal | str | float | None = None,
        exec_quantity: Decimal | str | float | None = None,
        exec_symbol: str | None = None,
        exec_side: str | None = None,
    ) -> tuple[JournaledEvent, bool]:
        """
        Appends raw event to forensic journal.
        Returns: (event: JournaledEvent, is_new_unique_execution: bool)

        Fails closed with ConflictingEventAnomalyError if duplicate execution_id has conflicting data.
        """
        self.total_events_received += 1
        payload_str = (
            json.dumps(raw_payload, default=str, sort_keys=True)
            if isinstance(raw_payload, dict)
            else str(raw_payload)
        )
        content_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        now_mono = time.monotonic_ns()
        event_id = f"EVT_{content_hash[:16].upper()}_{now_mono % 1_000_000:06d}"

        is_new_execution = True
        status = EventProcessingStatus.RECEIVED

        # Conflicting Duplicate Execution Shield
        if execution_id:
            exec_key = f"{venue.upper()}:{execution_id}"
            price_dec = Decimal(str(exec_price)) if exec_price is not None else None
            qty_dec = Decimal(str(exec_quantity)) if exec_quantity is not None else None
            sym = exec_symbol.upper() if exec_symbol else ""
            sd = exec_side.upper() if exec_side else ""

            if exec_key in self._known_executions:
                prev_price, prev_qty, prev_sym, prev_side, prev_evt_id = self._known_executions[
                    exec_key
                ]
                # Compare economic attributes
                if (
                    (price_dec is not None and prev_price != price_dec)
                    or (qty_dec is not None and prev_qty != qty_dec)
                    or (sym and prev_sym != sym)
                    or (sd and prev_side != sd)
                ):
                    self.total_conflicts_detected += 1
                    status = EventProcessingStatus.CONFLICT_HALTED
                    conflict_event = JournaledEvent(
                        event_id=event_id,
                        venue=venue,
                        event_type=event_type,
                        raw_payload_json=payload_str,
                        reception_utc=now_utc,
                        received_monotonic_ns=now_mono,
                        venue_timestamp_ms=venue_timestamp_ms,
                        source_channel=source_channel,
                        flight_id=flight_id,
                        parent_order_id=parent_order_id,
                        child_slice_id=child_slice_id,
                        intent_id=intent_id,
                        processing_status=status,
                        content_hash_sha256=content_hash,
                    )
                    self._persist_to_storage(conflict_event)
                    logger.critical(
                        f"[EventJournal] CONFLICTING DUPLICATE on {exec_key}: "
                        f"Existing=(P={prev_price}, Q={prev_qty}, S={prev_sym}, Side={prev_side}) vs "
                        f"Incoming=(P={price_dec}, Q={qty_dec}, S={sym}, Side={sd})"
                    )
                    raise ConflictingEventAnomalyError(
                        f"Conflicting duplicate execution detected for {exec_key}. "
                        f"Halting affected lifecycle. Prior event: {prev_evt_id}"
                    )

                # Identical duplicate execution -> skip idempotently
                self.total_duplicates_detected += 1
                status = EventProcessingStatus.DUPLICATE_SKIPPED
                is_new_execution = False
            else:
                if price_dec is not None and qty_dec is not None:
                    self._known_executions[exec_key] = (price_dec, qty_dec, sym, sd, event_id)
                status = EventProcessingStatus.PROCESSED

        event = JournaledEvent(
            event_id=event_id,
            venue=venue,
            event_type=event_type,
            raw_payload_json=payload_str,
            reception_utc=now_utc,
            received_monotonic_ns=now_mono,
            venue_timestamp_ms=venue_timestamp_ms,
            source_channel=source_channel,
            flight_id=flight_id,
            parent_order_id=parent_order_id,
            child_slice_id=child_slice_id,
            intent_id=intent_id,
            processing_status=status,
            content_hash_sha256=content_hash,
        )
        self._persist_to_storage(event)
        return event, is_new_execution

    def _persist_to_storage(self, event: JournaledEvent) -> None:
        self._events.append(event)
        if self._db_conn:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT INTO testnet_event_journal (
                    event_id, venue, event_type, raw_payload_json,
                    reception_utc, received_monotonic_ns, venue_timestamp_ms,
                    source_channel, flight_id, parent_order_id,
                    child_slice_id, intent_id, processing_status,
                    content_hash_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.venue,
                    event.event_type,
                    event.raw_payload_json,
                    event.reception_utc,
                    event.received_monotonic_ns,
                    event.venue_timestamp_ms,
                    event.source_channel,
                    event.flight_id,
                    event.parent_order_id,
                    event.child_slice_id,
                    event.intent_id,
                    event.processing_status.value,
                    event.content_hash_sha256,
                ),
            )
            self._db_conn.commit()

    def get_events_for_slice(self, child_slice_id: str) -> list[JournaledEvent]:
        """Retrieves all journaled events for a specific slice."""
        return [e for e in self._events if e.child_slice_id == child_slice_id]
