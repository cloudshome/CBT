"""
Audit Bus & Immutable Incident Event Stream.
Captures every critical system decision, signal rejection, risk gate enforcement,
trade closure, and post-mortem autopsy with structured JSON audit records.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.correlation_context import get_correlation_id
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.audit_bus")


@dataclass
class AuditEvent:
    event_id: str
    timestamp: float
    event_type: str  # "SIGNAL_GENERATED", "SIGNAL_REJECTED", "RISK_ENFORCED", "TRADE_CLOSED", "LOSS_AUTOPSY", "KILL_SWITCH"
    symbol: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    software_version: str = "2.0.0"
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditBus:
    """Central event ledger recording immutable system decisions."""

    def __init__(self, memory_buffer_size: int = 200):
        self._memory_buffer_size = memory_buffer_size
        self._memory_ring: list[AuditEvent] = []
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_audit_events (
                        event_id TEXT PRIMARY KEY,
                        timestamp REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        details_json TEXT,
                        software_version TEXT NOT NULL,
                        correlation_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_type ON system_audit_events(event_type)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_sym ON system_audit_events(symbol)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_cid ON system_audit_events(correlation_id)"
                )

                # Ensure backwards-compatible schema migration for existing tables
                cursor = conn.execute("PRAGMA table_info(system_audit_events);")
                cols = [r[1] for r in cursor.fetchall()]
                if "correlation_id" not in cols:
                    conn.execute("ALTER TABLE system_audit_events ADD COLUMN correlation_id TEXT;")
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_audit_cid ON system_audit_events(correlation_id)"
                    )
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not initialize system_audit_events table: {e}")

    def emit_event(
        self,
        event_type: str,
        symbol: str,
        reason: str,
        severity: str = "INFO",
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditEvent:
        """Emits and records an immutable audit event."""
        now = time.time()
        # Millisecond timestamp alone collides when two events of the same type
        # are recorded within 1 ms → UNIQUE violation and a silently DROPPED
        # audit record. UUID suffix keeps the audit ledger lossless.
        event_id = f"AUD-{int(now * 1000)}-{event_type[:4]}-{uuid.uuid4().hex[:8]}"
        cid = correlation_id or get_correlation_id()
        ev = AuditEvent(
            event_id=event_id,
            timestamp=now,
            event_type=event_type,
            symbol=symbol,
            severity=severity.upper(),
            reason=reason,
            details=details or {},
            correlation_id=cid,
        )

        # In-memory buffer
        self._memory_ring.append(ev)
        if len(self._memory_ring) > self._memory_buffer_size:
            self._memory_ring.pop(0)

        # Persist to SQLite
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO system_audit_events (
                        event_id, timestamp, event_type, symbol, severity, reason, details_json, software_version, correlation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.event_id,
                        ev.timestamp,
                        ev.event_type,
                        ev.symbol,
                        ev.severity,
                        ev.reason,
                        json.dumps(ev.details),
                        ev.software_version,
                        ev.correlation_id,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record audit event {event_id}: {e}")

        logger.info(f"Audit [{ev.severity}] {ev.event_type} on {ev.symbol}: {ev.reason}")
        return ev

    def record_event(
        self,
        event_type: str | AuditEvent,
        symbol: str = "SYSTEM",
        reason: str = "",
        severity: str = "INFO",
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AuditEvent:
        """Compatibility wrapper for callers using record_event."""
        if isinstance(event_type, AuditEvent):
            ev = event_type
            self._memory_ring.append(ev)
            if len(self._memory_ring) > self._memory_buffer_size:
                self._memory_ring.pop(0)
            try:
                with db_manager.get_trading_conn() as conn:
                    conn.execute(
                        """
                        INSERT INTO system_audit_events (
                            event_id, timestamp, event_type, symbol, severity, reason, details_json, software_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ev.event_id,
                            ev.timestamp,
                            ev.event_type,
                            ev.symbol,
                            ev.severity,
                            ev.reason,
                            json.dumps(ev.details),
                            ev.software_version,
                        ),
                    )
                    conn.commit()
            except Exception as e:
                logger.error(f"Failed to record audit event {ev.event_id}: {e}")
            logger.info(f"Audit [{ev.severity}] {ev.event_type} on {ev.symbol}: {ev.reason}")
            return ev

        sym = (
            symbol
            if symbol != "SYSTEM"
            else kwargs.get("module", kwargs.get("strategy_id", "SYSTEM"))
        )
        r = reason or kwargs.get("reason", f"{event_type} recorded")
        d = dict(details) if details else {}
        for k, v in kwargs.items():
            if k not in ("module", "strategy_id", "reason"):
                d[k] = v
        return self.emit_event(
            event_type=event_type,
            symbol=str(sym),
            reason=str(r),
            severity=severity,
            details=d,
        )

    def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        symbol: str = "SYSTEM",
        severity: str = "INFO",
        reason: str = "",
    ) -> str:
        """Publishes an event from a payload dictionary and returns the event_id."""
        p = payload or {}
        sym = symbol if symbol != "SYSTEM" else p.get("symbol", "SYSTEM")
        r = reason or p.get("reason", p.get("message", event_type))
        ev = self.emit_event(
            event_type=event_type,
            symbol=sym,
            reason=r,
            severity=severity,
            details=p,
        )
        return ev.event_id

    def get_recent_events(self, limit: int = 50, event_type: str | None = None) -> list[AuditEvent]:
        """Retrieves recent audit events."""
        events = []
        try:
            with db_manager.get_trading_conn() as conn:
                if event_type:
                    cursor = conn.execute(
                        "SELECT * FROM system_audit_events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                        (event_type, limit),
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM system_audit_events ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    )
                rows = cursor.fetchall()
                for r in rows:
                    keys = r.keys()
                    cid = r["correlation_id"] if "correlation_id" in keys else None
                    events.append(
                        AuditEvent(
                            event_id=r["event_id"],
                            timestamp=float(r["timestamp"]),
                            event_type=r["event_type"],
                            symbol=r["symbol"],
                            severity=r["severity"],
                            reason=r["reason"],
                            details=json.loads(r["details_json"] or "{}"),
                            software_version=r["software_version"],
                            correlation_id=cid,
                        )
                    )
        except Exception as e:
            logger.error(f"Error fetching audit events: {e}")
            # Fallback to memory ring
            if event_type:
                return [e for e in reversed(self._memory_ring) if e.event_type == event_type][
                    :limit
                ]
            return list(reversed(self._memory_ring))[:limit]

        return events

    def get_events_by_correlation_id(self, correlation_id: str) -> list[AuditEvent]:
        """Retrieves all audit events tagged with a specific correlation ID."""
        events: list[AuditEvent] = []
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM system_audit_events WHERE correlation_id = ? ORDER BY timestamp ASC",
                    (correlation_id,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    keys = r.keys()
                    cid = r["correlation_id"] if "correlation_id" in keys else None
                    events.append(
                        AuditEvent(
                            event_id=r["event_id"],
                            timestamp=float(r["timestamp"]),
                            event_type=r["event_type"],
                            symbol=r["symbol"],
                            severity=r["severity"],
                            reason=r["reason"],
                            details=json.loads(r["details_json"] or "{}"),
                            software_version=r["software_version"],
                            correlation_id=cid,
                        )
                    )
        except Exception as e:
            logger.error(f"Error fetching audit events by correlation_id {correlation_id}: {e}")

        # Also search memory buffer in case DB was mocked or bypassed
        seen_ids = {e.event_id for e in events}
        for mem_ev in self._memory_ring:
            if mem_ev.correlation_id == correlation_id and mem_ev.event_id not in seen_ids:
                events.append(mem_ev)

        return events


# Singleton
audit_bus = AuditBus()
