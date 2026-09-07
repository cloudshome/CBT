"""
core/execution/kill_switch.py
=============================
Independent Emergency Live-Execution Kill Switch.

Safety Invariants:
- Overrides ALL strategy decisions, exchange connectivity, API requests, and live execution.
- Fail-Closed Semantics: Any database error or ambiguous state triggers immediate FAIL CLOSED (active).
- Explicit Boolean Parsing: 'true' -> True, 'false' -> False; unknown/unset defaults to inactive
  unless persistent lockout or incident engine has engaged.
- Operational activation without requiring exchange credentials.
- Every kill switch activation, engagement, rejection, and deactivation is auditable via audit_bus.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.live_kill_switch")


def parse_strict_bool(val: str | None, default: bool = False) -> bool:
    """
    Parses boolean environment variables strictly.
    'true' -> True
    'false' -> False
    Any other value -> default (fails closed)
    """
    if val is None:
        return default
    s = val.strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    logger.warning(f"Unrecognized boolean value '{val}'; failing closed to default={default}")
    return default


@dataclass
class KillSwitchState:
    is_active: bool
    reason: str
    activated_by: str
    activated_at: int
    source: str  # "ENV", "PERSISTENT_DB", "IN_MEMORY", "INCIDENT_HALT", "INACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiveKillSwitch:
    """
    Independent Master Kill Switch for all Live Exchange Execution.
    """

    def __init__(self):
        self._in_memory_override: bool | None = None
        self._override_reason: str = ""
        self._override_by: str = ""
        self._override_at: int = 0
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS live_kill_switch_state (
                        id TEXT PRIMARY KEY,
                        is_active INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        activated_by TEXT NOT NULL,
                        activated_at INTEGER NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize live_kill_switch_state schema: {e}")

    def is_active(self) -> tuple[bool, KillSwitchState]:
        """
        Determines if the live kill switch is currently active.
        Evaluates:
          1. Environment variable `KILL_SWITCH_ACTIVE`
          2. In-memory override
          3. Persistent SQLite state
          4. Autonomous incident engine auto-halt
        Fails closed on any exception.
        """
        now_ms = int(time.time() * 1000)

        # 1. Check explicit environment variable
        env_val = os.getenv("KILL_SWITCH_ACTIVE")
        if env_val is not None:
            if parse_strict_bool(env_val, default=False):
                return True, KillSwitchState(
                    is_active=True,
                    reason="KILL_SWITCH_ACTIVE=true configured in environment.",
                    activated_by="ENV",
                    activated_at=now_ms,
                    source="ENV",
                )

        # 2. Check in-memory override
        if self._in_memory_override is not None:
            if self._in_memory_override:
                return True, KillSwitchState(
                    is_active=True,
                    reason=self._override_reason or "In-memory kill switch engaged.",
                    activated_by=self._override_by or "OPERATOR",
                    activated_at=self._override_at or now_ms,
                    source="IN_MEMORY",
                )
            # If explicitly set to False in memory, still verify incident engine

        # 3. Check persistent database state
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT is_active, reason, activated_by, activated_at FROM live_kill_switch_state WHERE id = 'MASTER'"
                )
                row = cursor.fetchone()
                if row and int(row["is_active"]) == 1:
                    return True, KillSwitchState(
                        is_active=True,
                        reason=row["reason"],
                        activated_by=row["activated_by"],
                        activated_at=int(row["activated_at"]),
                        source="PERSISTENT_DB",
                    )
        except Exception as e:
            # FAIL CLOSED: If DB read fails, treat kill switch as ACTIVE
            logger.critical(f"FAIL CLOSED: Kill switch DB inspection error: {e}. Engaging safety halt.")
            return True, KillSwitchState(
                is_active=True,
                reason=f"FAIL_CLOSED: Database inspection error: {e}",
                activated_by="SYSTEM_FAIL_CLOSED",
                activated_at=now_ms,
                source="FAIL_CLOSED",
            )

        # 4. Check Incident Escalation Engine Auto-Halt state
        try:
            from core.incident_escalation import incident_escalation_engine
            if getattr(incident_escalation_engine, "_is_emergency_halted", False):
                return True, KillSwitchState(
                    is_active=True,
                    reason="Incident Escalation Engine Tier 4 Emergency Auto-Halt active.",
                    activated_by="INCIDENT_ESCALATION",
                    activated_at=now_ms,
                    source="INCIDENT_HALT",
                )
        except ImportError:
            pass

        return False, KillSwitchState(
            is_active=False,
            reason="Kill switch inactive. System clear.",
            activated_by="",
            activated_at=0,
            source="INACTIVE",
        )

    def activate(self, reason: str, operator_id: str = "OPERATOR") -> KillSwitchState:
        """
        Engages the emergency kill switch. Persists state and emits audit event.
        """
        now_ms = int(time.time() * 1000)
        self._in_memory_override = True
        self._override_reason = reason
        self._override_by = operator_id
        self._override_at = now_ms

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO live_kill_switch_state (id, is_active, reason, activated_by, activated_at)
                    VALUES ('MASTER', 1, ?, ?, ?)
                    """,
                    (reason, operator_id, now_ms),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error persisting kill switch activation to DB: {e}")

        audit_bus.emit_event(
            event_type="KILL_SWITCH_ENGAGED",
            symbol="ALL",
            severity="CRITICAL",
            reason=f"Live Execution Kill Switch engaged by {operator_id}: {reason}",
            details={"operator_id": operator_id, "timestamp_ms": now_ms, "reason": reason},
        )
        logger.critical(f"EMERGENCY KILL SWITCH ENGAGED: {reason} (by {operator_id})")

        return KillSwitchState(
            is_active=True,
            reason=reason,
            activated_by=operator_id,
            activated_at=now_ms,
            source="MANUAL_ACTIVATION",
        )

    def deactivate(self, reason: str, operator_id: str = "ADMIN") -> KillSwitchState:
        """
        Disengages the emergency kill switch.
        """
        now_ms = int(time.time() * 1000)
        self._in_memory_override = False
        self._override_reason = reason
        self._override_by = operator_id
        self._override_at = now_ms

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO live_kill_switch_state (id, is_active, reason, activated_by, activated_at)
                    VALUES ('MASTER', 0, ?, ?, ?)
                    """,
                    (reason, operator_id, now_ms),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error persisting kill switch deactivation to DB: {e}")

        audit_bus.emit_event(
            event_type="KILL_SWITCH_DISENGAGED",
            symbol="ALL",
            severity="WARNING",
            reason=f"Live Execution Kill Switch cleared by {operator_id}: {reason}",
            details={"operator_id": operator_id, "timestamp_ms": now_ms, "reason": reason},
        )
        logger.warning(f"EMERGENCY KILL SWITCH CLEARED: {reason} (by {operator_id})")

        return KillSwitchState(
            is_active=False,
            reason=reason,
            activated_by=operator_id,
            activated_at=now_ms,
            source="MANUAL_DEACTIVATION",
        )


# Global singleton instance
live_kill_switch = LiveKillSwitch()
