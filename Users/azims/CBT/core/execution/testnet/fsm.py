"""
core/execution/testnet/fsm.py
=============================
Durable 8-State Rehearsal FSM & Crash Recovery Supervisor.

Implements Finding A & Finding B:
- Explicit RECOVERY_RECONCILIATION state.
- Authoritative state validation on crash restart.
- Never resumes active order dispatch directly from a potentially stale local snapshot.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import ClassVar

from core.execution.testnet.schemas import BurnInState

logger = logging.getLogger("sky.execution.testnet.fsm")


class StateTransitionError(Exception):
    """Raised when an invalid FSM state transition is attempted."""


class JournalIntegrityError(Exception):
    """Raised when the persistent SQLite journal exhibits corruption or unhandled gap."""


class RehearsalFSM:
    """
    Durable state machine managing testnet rehearsal lifecycle with crash recovery reconciliation.
    """

    ALLOWED_TRANSITIONS: ClassVar[dict[BurnInState, list[BurnInState]]] = {
        BurnInState.IDLE: [
            BurnInState.WARMING_UP,
            BurnInState.RECOVERY_RECONCILIATION,
            BurnInState.INVALIDATED,
        ],
        BurnInState.RECOVERY_RECONCILIATION: [
            BurnInState.WARMING_UP,
            BurnInState.ANOMALY_HALTED,
            BurnInState.INVALIDATED,
        ],
        BurnInState.WARMING_UP: [
            BurnInState.ACTIVE_REHEARSAL,
            BurnInState.DEGRADED,
            BurnInState.ANOMALY_HALTED,
            BurnInState.IDLE,
            BurnInState.INVALIDATED,
        ],
        BurnInState.ACTIVE_REHEARSAL: [
            BurnInState.DEGRADED,
            BurnInState.ANOMALY_HALTED,
            BurnInState.COMPLETED_14_DAYS,
            BurnInState.RECOVERY_RECONCILIATION,
            BurnInState.INVALIDATED,
        ],
        BurnInState.DEGRADED: [
            BurnInState.ACTIVE_REHEARSAL,
            BurnInState.ANOMALY_HALTED,
            BurnInState.RECOVERY_RECONCILIATION,
            BurnInState.INVALIDATED,
        ],
        BurnInState.ANOMALY_HALTED: [
            BurnInState.IDLE,  # Requires explicit operator reset
            BurnInState.RECOVERY_RECONCILIATION,
            BurnInState.INVALIDATED,
        ],
        BurnInState.COMPLETED_14_DAYS: [
            BurnInState.IDLE,  # Completed sessions can be archived
        ],
        BurnInState.INVALIDATED: [
            BurnInState.IDLE,  # Invalidated sessions require new session initialization
        ],
    }

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        session_id: str = "DEFAULT_BURNIN",
    ) -> None:
        self.session_id = session_id
        self._db_conn = db_conn
        self._state = BurnInState.IDLE
        self._state_entered_time_ns = time.monotonic_ns()
        self._state_entered_utc = datetime.now(UTC).isoformat()
        self._on_transition_hooks: list[Callable[[BurnInState, BurnInState, str], None]] = []

        if self._db_conn:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensures isolated SQLite table for FSM transition journal."""
        assert self._db_conn is not None
        cursor = self._db_conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS testnet_fsm_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                transition_monotonic_ns INTEGER NOT NULL,
                transition_utc TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fsm_session_id
            ON testnet_fsm_journal(session_id, id);
            """
        )
        self._db_conn.commit()

    @property
    def current_state(self) -> BurnInState:
        return self._state

    @property
    def state_duration_sec(self) -> float:
        return (time.monotonic_ns() - self._state_entered_time_ns) / 1_000_000_000.0

    def can_transition_to(self, target: BurnInState) -> bool:
        """Checks whether transitioning from current_state to target is permitted."""
        return target in self.ALLOWED_TRANSITIONS.get(self._state, [])

    def transition_to(self, target: BurnInState, reason: str) -> None:
        """
        Executes a deterministic state transition, logging to SQLite journal and executing hooks.
        """
        if not self.can_transition_to(target):
            raise StateTransitionError(
                f"Illegal transition: {self._state.value} -> {target.value}. Reason: {reason}"
            )

        from_state = self._state
        self._state = target
        self._state_entered_time_ns = time.monotonic_ns()
        self._state_entered_utc = datetime.now(UTC).isoformat()

        logger.info(
            f"[FSM:{self.session_id}] State changed: {from_state.value} -> {target.value} | Reason: {reason}"
        )

        if self._db_conn:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT INTO testnet_fsm_journal
                (session_id, from_state, to_state, reason, transition_monotonic_ns, transition_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.session_id,
                    from_state.value,
                    target.value,
                    reason,
                    self._state_entered_time_ns,
                    self._state_entered_utc,
                ),
            )
            self._db_conn.commit()

        for hook in self._on_transition_hooks:
            try:
                hook(from_state, target, reason)
            except Exception as e:  # noqa: BLE001
                logger.error(f"FSM transition hook error: {e}")

    def register_transition_hook(
        self, hook: Callable[[BurnInState, BurnInState, str], None]
    ) -> None:
        self._on_transition_hooks.append(hook)

    # -------------------------------------------------------------------------
    # Crash Recovery & State Rehydration Logic (Finding A)
    # -------------------------------------------------------------------------

    def recover_from_journal(
        self,
        authoritative_state_checker: Callable[[], tuple[bool, str]] | None = None,
    ) -> BurnInState:
        """
        Performs authoritative crash recovery:
        1. Reads last known state from SQLite journal.
        2. Transitions directly to RECOVERY_RECONCILIATION.
        3. Queries authoritative state checker (exchange or simulator ledger).
        4. If matched -> Transitions to WARMING_UP.
        5. If mismatched -> Transitions to ANOMALY_HALTED (fail closed).
        """
        if not self._db_conn:
            logger.warning("No database connection; cannot recover journal.")
            return self._state

        cursor = self._db_conn.cursor()
        cursor.execute(
            """
            SELECT to_state FROM testnet_fsm_journal
            WHERE session_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (self.session_id,),
        )
        row = cursor.fetchone()

        if not row:
            logger.info("No prior journal entries found; remaining in IDLE.")
            return self._state

        last_state = BurnInState(row[0])
        logger.info(f"[CrashRecovery] Discovered prior state in journal: {last_state.value}")

        # If previous state was already terminal, restore it directly
        if last_state in (
            BurnInState.ANOMALY_HALTED,
            BurnInState.COMPLETED_14_DAYS,
            BurnInState.INVALIDATED,
        ):
            self._state = last_state
            return self._state

        # Otherwise, force transition to RECOVERY_RECONCILIATION
        self._state = BurnInState.RECOVERY_RECONCILIATION
        self._record_journal_event(
            last_state,
            BurnInState.RECOVERY_RECONCILIATION,
            "Process restart: entering recovery reconciliation",
        )

        # Authoritative reconciliation
        if authoritative_state_checker is not None:
            is_valid, diag_message = authoritative_state_checker()
            if is_valid:
                self.transition_to(
                    BurnInState.WARMING_UP,
                    f"Authoritative reconciliation verified cleanly: {diag_message}",
                )
            else:
                self.transition_to(
                    BurnInState.ANOMALY_HALTED,
                    f"Authoritative reconciliation MISMATCH detected: {diag_message}",
                )
        else:
            # Without an authoritative validator, fail closed into ANOMALY_HALTED
            self.transition_to(
                BurnInState.ANOMALY_HALTED,
                "No authoritative state checker provided during crash recovery",
            )

        return self._state

    def _record_journal_event(
        self, from_state: BurnInState, to_state: BurnInState, reason: str
    ) -> None:
        if self._db_conn:
            cursor = self._db_conn.cursor()
            cursor.execute(
                """
                INSERT INTO testnet_fsm_journal
                (session_id, from_state, to_state, reason, transition_monotonic_ns, transition_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.session_id,
                    from_state.value,
                    to_state.value,
                    reason,
                    time.monotonic_ns(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._db_conn.commit()
