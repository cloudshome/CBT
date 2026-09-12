"""
core/collective/event_store.py
==============================
Append-only local event storage and SQLite indexing for SDCC.

Architecture:
- Segmented append-only JSONL files under data/collective/events/local/ (or received/).
- SQLite index in data/collective/collective.db for range queries, fast vector checkpoints,
  and deduplication.
- Immutability: No UPDATE or DELETE on canonical event logs.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from core.collective.event import CanonicalEvent
from core.collective.event_hash import canonical_json_str, verify_event_integrity
from core.collective.sequence import SequenceManager

logger = logging.getLogger("sky.collective.event_store")

SEGMENT_MAX_EVENTS = 10000


class EventStore:
    """Coordinates segmented append-only JSONL files and indexed SQLite lookup."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.events_dir = self.base_dir / "events"
        self.local_events_dir = self.events_dir / "local"
        self.received_events_dir = self.events_dir / "received"
        self.quarantine_dir = self.events_dir / "quarantined"
        self.db_path = self.base_dir / "collective.db"

        self._ensure_directories()
        self.sequence_manager = SequenceManager(self.db_path)
        self._init_index_db()

    def _ensure_directories(self) -> None:
        self.local_events_dir.mkdir(parents=True, exist_ok=True)
        self.received_events_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_index_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collective_event_index (
                    event_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    causation_id TEXT,
                    correlation_id TEXT,
                    created_at TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    is_local INTEGER NOT NULL DEFAULT 1,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_node_seq ON collective_event_index(node_id, sequence);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_type ON collective_event_index(event_type);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity ON collective_event_index(entity_type, entity_id);"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_segment_file(self, node_id: str, sequence: int, is_local: bool) -> Path:
        """Determines the target segment file path based on sequence number."""
        segment_index = sequence // SEGMENT_MAX_EVENTS
        segment_name = f"events-{segment_index:06d}.jsonl"
        target_dir = self.local_events_dir if is_local else (self.received_events_dir / node_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / segment_name

    def append_event(self, event: CanonicalEvent, is_local: bool = True) -> tuple[bool, str]:
        """
        Appends an event to the append-only log and index.
        Returns:
            (True, "IMPORTED") if newly imported.
            (True, "DUPLICATE") if already present with identical hash (idempotent).
            (False, "HASH_MISMATCH") if ID exists with differing hash.
            (False, "CORRUPT") if event fails integrity validation.
        """
        # 1. Verify integrity before writing
        ev_dict = event.to_dict()
        is_valid, err = verify_event_integrity(ev_dict)
        if not is_valid:
            logger.warning(f"Rejecting corrupt event {event.event_id}: {err}")
            self.quarantine_event(ev_dict, reason=f"INTEGRITY_FAILED: {err}")
            return False, "CORRUPT"

        # 2. Check index for existing event_id
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT event_sha256 FROM collective_event_index WHERE event_id = ?",
                (event.event_id,),
            )
            row = cur.fetchone()
            if row:
                existing_hash = row["event_sha256"]
                if existing_hash == event.integrity["event_sha256"]:
                    return True, "DUPLICATE"
                else:
                    logger.error(
                        f"Event ID collision with hash mismatch for {event.event_id}! "
                        f"Existing: {existing_hash}, New: {event.integrity['event_sha256']}"
                    )
                    self.quarantine_event(
                        ev_dict,
                        reason=f"EVENT_HASH_MISMATCH: Existing {existing_hash} != {event.integrity['event_sha256']}",
                    )
                    return False, "HASH_MISMATCH"

            # 3. Append to segment file
            segment_path = self._get_segment_file(event.node_id, event.sequence, is_local)
            line = canonical_json_str(ev_dict) + "\n"
            with open(segment_path, "a", encoding="utf-8") as f:
                f.write(line)

            # 4. Insert into index
            conn.execute(
                """
                INSERT INTO collective_event_index (
                    event_id, node_id, sequence, event_type, entity_type, entity_id,
                    causation_id, correlation_id, created_at, event_sha256, payload_sha256,
                    raw_json, is_local
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event.event_id,
                    event.node_id,
                    event.sequence,
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                    event.causation_id,
                    event.correlation_id,
                    event.created_at,
                    event.integrity["event_sha256"],
                    event.integrity["payload_sha256"],
                    canonical_json_str(ev_dict),
                    1 if is_local else 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # Update sequence tracker
        self.sequence_manager.set_sequence(event.node_id, event.sequence)
        return True, "IMPORTED"

    def quarantine_event(self, raw_event: dict[str, Any], reason: str) -> None:
        """Stores quarantined event with incident reason."""
        event_id = raw_event.get("event_id", "UNKNOWN_EVENT_ID")
        quarantine_file = self.quarantine_dir / f"quarantine_{event_id.replace(':', '_')}.json"
        payload = {
            "reason": reason,
            "event": raw_event,
        }
        with open(quarantine_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def get_event(self, event_id: str) -> CanonicalEvent | None:
        """Fetches a single event by event_id."""
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT raw_json FROM collective_event_index WHERE event_id = ?",
                (event_id,),
            )
            row = cur.fetchone()
            if row:
                return CanonicalEvent.from_dict(json.loads(row["raw_json"]))
            return None
        finally:
            conn.close()

    def get_events(
        self,
        node_id: str,
        from_sequence: int = 1,
        to_sequence: int | None = None,
    ) -> list[CanonicalEvent]:
        """Fetches sequence range of events for a specific node."""
        query = "SELECT raw_json FROM collective_event_index WHERE node_id = ? AND sequence >= ?"
        params: list[Any] = [node_id, from_sequence]
        if to_sequence is not None:
            query += " AND sequence <= ?"
            params.append(to_sequence)
        query += " ORDER BY sequence ASC"

        conn = self._get_connection()
        try:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [CanonicalEvent.from_dict(json.loads(r["raw_json"])) for r in rows]
        finally:
            conn.close()

    def get_all_events(self) -> list[CanonicalEvent]:
        """Fetches all events ordered by causal / chronological sequence."""
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT raw_json FROM collective_event_index ORDER BY created_at ASC, sequence ASC"
            )
            rows = cur.fetchall()
            return [CanonicalEvent.from_dict(json.loads(r["raw_json"])) for r in rows]
        finally:
            conn.close()

    def get_highest_sequence(self, node_id: str) -> int:
        """Returns the highest sequence stored for a given node."""
        return self.sequence_manager.get_current_sequence(node_id)

    def get_total_count(self) -> int:
        """Returns the total number of events in the index."""
        conn = self._get_connection()
        try:
            cur = conn.execute("SELECT COUNT(*) as total FROM collective_event_index")
            return int(cur.fetchone()["total"])
        finally:
            conn.close()

    def close(self) -> None:
        """Explicit hook for test cleanup if needed."""
        pass


event_store = EventStore()
