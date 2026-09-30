"""
core/intelligence/crawler/conflict_ledger.py
=============================================
Conflict & Revision Ledger for Milestone 30-B.

Enforces:
1. First-class persistence of disagreements, revisions, and contradictory claims.
2. Prevention of silent overwrites of historical observations.
3. Explicit quarantine of contested data until reconciled by primary official sources.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.conflict_ledger")


class ConflictType(str, Enum):
    DATA_REVISION = "DATA_REVISION"  # Official agency revised previous print (e.g. GDP, CPI)
    CONTRADICTORY_REPORT = "CONTRADICTORY_REPORT"  # Two sources report conflicting values
    TIMING_DISCREPANCY = "TIMING_DISCREPANCY"  # Conflicting release timestamps reported
    ENTITY_AMBIGUITY = "ENTITY_AMBIGUITY"  # Unclear whether report applies to asset or issuer


class ConflictStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    OFFICIAL_PREVAILED = (
        "OFFICIAL_PREVAILED"  # Primary source (officiality=1.0) overrides secondary
    )
    CONSENSUS_RECONCILED = "CONSENSUS_RECONCILED"  # Reconciled via multi-source consensus
    QUARANTINED = "QUARANTINED"  # Flagged unusable for quantitative modeling


@dataclass(frozen=True)
class EvidenceConflict:
    conflict_id: str
    event_id: str
    conflict_type: ConflictType
    status: ConflictStatus
    source_a_id: str
    source_b_id: str
    value_a_json: str
    value_b_json: str
    timestamp_a: datetime
    timestamp_b: datetime
    detected_at: datetime
    resolution_notes: str = ""
    resolved_at: datetime | None = None
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False


class ConflictLedger:
    """SQLite WAL-backed store for multi-source evidence discrepancies."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("BRAIN_DB_PATH")
            if env_path:
                self._db_path = env_path
            else:
                db_dir = Path("data")
                db_dir.mkdir(exist_ok=True)
                self._db_path = str(db_dir / "brain_memory.db")
        else:
            self._db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_a_id TEXT NOT NULL,
                    source_b_id TEXT NOT NULL,
                    value_a_json TEXT NOT NULL,
                    value_b_json TEXT NOT NULL,
                    timestamp_a TEXT NOT NULL,
                    timestamp_b TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    resolution_notes TEXT NOT NULL,
                    resolved_at TEXT,
                    execution_authority TEXT NOT NULL,
                    real_capital_enabled INTEGER NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conf_evt ON evidence_conflicts(event_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conf_stat ON evidence_conflicts(status);"
            )
            conn.commit()

    def record_conflict(
        self,
        event_id: str,
        conflict_type: ConflictType,
        source_a_id: str,
        source_b_id: str,
        value_a: Any,
        value_b: Any,
        timestamp_a: datetime,
        timestamp_b: datetime,
        status: ConflictStatus = ConflictStatus.UNRESOLVED,
        resolution_notes: str = "",
    ) -> EvidenceConflict:
        """Records a new evidence conflict without overwriting prior data."""
        conflict_id = f"CONF_{uuid.uuid4().hex[:12].upper()}"
        now_utc = datetime.now(UTC)
        record = EvidenceConflict(
            conflict_id=conflict_id,
            event_id=event_id,
            conflict_type=conflict_type,
            status=status,
            source_a_id=source_a_id,
            source_b_id=source_b_id,
            value_a_json=json.dumps(value_a, sort_keys=True),
            value_b_json=json.dumps(value_b, sort_keys=True),
            timestamp_a=timestamp_a,
            timestamp_b=timestamp_b,
            detected_at=now_utc,
            resolution_notes=resolution_notes,
        )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO evidence_conflicts (
                    conflict_id, event_id, conflict_type, status,
                    source_a_id, source_b_id, value_a_json, value_b_json,
                    timestamp_a, timestamp_b, detected_at, resolution_notes,
                    resolved_at, execution_authority, real_capital_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.conflict_id,
                    record.event_id,
                    record.conflict_type.value,
                    record.status.value,
                    record.source_a_id,
                    record.source_b_id,
                    record.value_a_json,
                    record.value_b_json,
                    record.timestamp_a.isoformat(),
                    record.timestamp_b.isoformat(),
                    record.detected_at.isoformat(),
                    record.resolution_notes,
                    None,
                    record.execution_authority,
                    1 if record.real_capital_enabled else 0,
                ),
            )
            conn.commit()

        logger.warning(
            "Recorded %s conflict %s for event %s between %s and %s",
            conflict_type.value,
            conflict_id,
            event_id,
            source_a_id,
            source_b_id,
        )
        return record

    def resolve_conflict(
        self,
        conflict_id: str,
        status: ConflictStatus,
        resolution_notes: str,
    ) -> bool:
        """Updates the status and resolution rationale of a conflict."""
        now_utc = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE evidence_conflicts
                SET status = ?, resolution_notes = ?, resolved_at = ?
                WHERE conflict_id = ?;
                """,
                (status.value, resolution_notes, now_utc, conflict_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_conflicts_for_event(self, event_id: str) -> list[EvidenceConflict]:
        """Returns all conflicts associated with a specific canonical event."""
        clean_id = event_id.replace("'", "''")
        return self._query_conflicts(f"WHERE event_id = '{clean_id}' ORDER BY detected_at DESC")

    def list_unresolved(self) -> list[EvidenceConflict]:
        """Returns all currently unresolved conflicts."""
        return self._query_conflicts("WHERE status = 'UNRESOLVED' ORDER BY detected_at DESC")

    def list_all(self, limit: int = 100) -> list[EvidenceConflict]:
        """Returns the most recent conflicts."""
        return self._query_conflicts(f"ORDER BY detected_at DESC LIMIT {limit}")

    def _query_conflicts(self, clause: str) -> list[EvidenceConflict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT conflict_id, event_id, conflict_type, status,
                       source_a_id, source_b_id, value_a_json, value_b_json,
                       timestamp_a, timestamp_b, detected_at, resolution_notes,
                       resolved_at, execution_authority, real_capital_enabled
                FROM evidence_conflicts
                {clause};
                """
            )
            rows = cursor.fetchall()

        conflicts = []
        for r in rows:
            conflicts.append(
                EvidenceConflict(
                    conflict_id=r[0],
                    event_id=r[1],
                    conflict_type=ConflictType(r[2]),
                    status=ConflictStatus(r[3]),
                    source_a_id=r[4],
                    source_b_id=r[5],
                    value_a_json=r[6],
                    value_b_json=r[7],
                    timestamp_a=datetime.fromisoformat(r[8]),
                    timestamp_b=datetime.fromisoformat(r[9]),
                    detected_at=datetime.fromisoformat(r[10]),
                    resolution_notes=r[11],
                    resolved_at=datetime.fromisoformat(r[12]) if r[12] else None,
                    execution_authority=r[13],
                    real_capital_enabled=bool(r[14]),
                )
            )
        return conflicts
