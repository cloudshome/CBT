"""
core/intelligence/forward_validation/failure_memory.py
======================================================
Structured Failure Memory Store for Milestone 31-R.

Enforces:
1. Permanent Failure Memory: Strategies do not merely accumulate positive evidence;
   they accumulate known failure boundaries.
2. Structured Failure Taxonomy: Categorizes root cause, trigger, regime, and adverse markout.
3. Containment Guarantee: All containment actions strictly enforce SIMULATION_ONLY_CANCEL.
4. Persistent SQLite WAL Storage: Thread-safe persistence across crash/restart cycles.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_quant_sentinel.intelligence.failure_memory")


class FailureComponent(StrEnum):
    """Subsystem where the failure or anomaly originated."""

    GATEWAY = "GATEWAY"
    ORDERBOOK_TRACKER = "ORDERBOOK_TRACKER"
    PAPER_SIMULATOR = "PAPER_SIMULATOR"
    MARKOUT_ENGINE = "MARKOUT_ENGINE"
    FORWARD_LEDGER = "FORWARD_LEDGER"
    DRIFT_DETECTOR = "DRIFT_DETECTOR"
    SUSPENSION_CONTROLLER = "SUSPENSION_CONTROLLER"
    STRATEGY_GENOME = "STRATEGY_GENOME"


class FailureTriggerType(StrEnum):
    """Formal trigger taxonomy for strategy anomalies and suspensions."""

    MAX_DRAWDOWN_BREACH = "MAX_DRAWDOWN_BREACH"
    CONSECUTIVE_NEGATIVE_MARKOUTS = "CONSECUTIVE_NEGATIVE_MARKOUTS"
    PERSISTENT_FEED_DEGRADATION = "PERSISTENT_FEED_DEGRADATION"
    SEVERE_STATISTICAL_DRIFT = "SEVERE_STATISTICAL_DRIFT"
    SPREAD_EXPLOSION = "SPREAD_EXPLOSION"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    CROSSED_BOOK = "CROSSED_BOOK"
    CLOCK_SKEW_BREACH = "CLOCK_SKEW_BREACH"
    LIQUIDITY_VACUUM = "LIQUIDITY_VACUUM"
    UNEXPECTED_EXCEPTION = "UNEXPECTED_EXCEPTION"


class FailureRecord(BaseModel):
    """
    Immutable, typed record detailing an observed failure boundary or anomaly.
    """

    failure_id: str = Field(..., description="Unique ID: FAIL-<timestamp>-<hash>")
    timestamp_ns: int = Field(..., description="Monotonic nanosecond timestamp")
    timestamp_utc: float = Field(..., description="UTC epoch timestamp")
    component: FailureComponent = Field(..., description="Failing component")
    strategy_id: str = Field(..., description="Target strategy ID")
    strategy_version: str = Field(default="1.0.0", description="Target strategy version")
    venue: str = Field(default="BINANCE_SPOT", description="Observed venue")
    symbol: str = Field(default="BTCUSDT", description="Observed market symbol")
    market_regime: str = Field(
        default="UNKNOWN", description="Active market regime at failure time"
    )
    trigger_type: FailureTriggerType = Field(..., description="Specific trigger category")
    preconditions: dict[str, Any] = Field(
        default_factory=dict, description="State prior to anomaly"
    )
    observed_behavior: str = Field(..., description="Empirical manifestation of failure")
    expected_behavior: str = Field(..., description="Theoretical specification expectation")
    adverse_markout_bps: float = Field(
        default=0.0, description="Measured adverse selection or loss in bps"
    )
    root_cause_classification: str = Field(..., description="Forensic root-cause classification")
    containment_action: str = Field(
        default="SIMULATION_ONLY_CANCEL",
        description="Immediate containment action taken (strictly simulation)",
    )
    recovery_action: str = Field(..., description="Required procedure to resolve anomaly")
    regression_test_id: str | None = Field(
        default=None, description="Automated regression test verifying boundary"
    )
    status: str = Field(
        default="ACTIVE_QUARANTINE", description="ACTIVE_QUARANTINE | CONTAINED | RESOLVED"
    )


class FailureMemoryStore:
    """
    Persistent SQLite WAL store capturing failure boundaries and anomalies.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = "data/forward_failure_memory.db"
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None
        elif str(db_path) == ":memory:":
            self._db_path = ":memory:"
            self._is_memory = True
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._is_memory:
            return self._mem_conn  # type: ignore
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_memory_records (
                    failure_id TEXT PRIMARY KEY,
                    timestamp_ns INTEGER NOT NULL,
                    timestamp_utc REAL NOT NULL,
                    component TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    preconditions TEXT NOT NULL,
                    observed_behavior TEXT NOT NULL,
                    expected_behavior TEXT NOT NULL,
                    adverse_markout_bps REAL NOT NULL,
                    root_cause_classification TEXT NOT NULL,
                    containment_action TEXT NOT NULL,
                    recovery_action TEXT NOT NULL,
                    regression_test_id TEXT,
                    status TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_strat ON failure_memory_records (strategy_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_trigger ON failure_memory_records (trigger_type);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_status ON failure_memory_records (status);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fail_ts ON failure_memory_records (timestamp_utc);"
            )
            conn.commit()
        finally:
            if not self._is_memory:
                conn.close()

    def record_failure(self, record: FailureRecord) -> str:
        """Persists a new failure record into SQLite memory."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO failure_memory_records (
                    failure_id, timestamp_ns, timestamp_utc, component,
                    strategy_id, strategy_version, venue, symbol, market_regime,
                    trigger_type, preconditions, observed_behavior, expected_behavior,
                    adverse_markout_bps, root_cause_classification, containment_action,
                    recovery_action, regression_test_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.failure_id,
                    record.timestamp_ns,
                    record.timestamp_utc,
                    record.component.value
                    if isinstance(record.component, FailureComponent)
                    else str(record.component),
                    record.strategy_id,
                    record.strategy_version,
                    record.venue,
                    record.symbol,
                    record.market_regime,
                    record.trigger_type.value
                    if isinstance(record.trigger_type, FailureTriggerType)
                    else str(record.trigger_type),
                    json.dumps(record.preconditions),
                    record.observed_behavior,
                    record.expected_behavior,
                    record.adverse_markout_bps,
                    record.root_cause_classification,
                    record.containment_action,
                    record.recovery_action,
                    record.regression_test_id,
                    record.status,
                ),
            )
            conn.commit()
            logger.info(
                "Recorded failure boundary %s for strategy %s",
                record.failure_id,
                record.strategy_id,
            )
            return record.failure_id
        finally:
            if not self._is_memory:
                conn.close()

    def get_failure(self, failure_id: str) -> FailureRecord | None:
        """Retrieves a single failure record by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM failure_memory_records WHERE failure_id = ?",
                (failure_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)
        finally:
            if not self._is_memory:
                conn.close()

    def list_failures_for_strategy(self, strategy_id: str) -> list[FailureRecord]:
        """Lists all failures associated with a specific strategy."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM failure_memory_records WHERE strategy_id = ? ORDER BY timestamp_utc ASC",
                (strategy_id,),
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]
        finally:
            if not self._is_memory:
                conn.close()

    def get_active_quarantines(self) -> list[FailureRecord]:
        """Lists all failures that currently hold an ACTIVE_QUARANTINE status."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM failure_memory_records WHERE status = 'ACTIVE_QUARANTINE' ORDER BY timestamp_utc DESC"
            )
            return [self._row_to_record(r) for r in cursor.fetchall()]
        finally:
            if not self._is_memory:
                conn.close()

    def resolve_failure(self, failure_id: str, resolution_notes: str) -> bool:
        """Marks a failure as RESOLVED with audit notes."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE failure_memory_records
                SET status = 'RESOLVED', recovery_action = recovery_action || ' [RESOLVED: ' || ? || ']'
                WHERE failure_id = ?
                """,
                (resolution_notes, failure_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if not self._is_memory:
                conn.close()

    def export_all(self) -> list[dict[str, Any]]:
        """Exports all failure records as dicts."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM failure_memory_records ORDER BY timestamp_utc ASC")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            if not self._is_memory:
                conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> FailureRecord:
        d = dict(row)
        d["preconditions"] = json.loads(d["preconditions"])
        return FailureRecord(**d)
