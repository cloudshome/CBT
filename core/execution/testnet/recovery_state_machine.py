"""
core/execution/testnet/recovery_state_machine.py
================================================
Milestone 22: Formal Lost-ACK Recovery Finite State Machine.

Implements Section 7:
- Formal 10-State Machine:
  PLACEMENT_INTENT_DURABLE
  SUBMISSION_ATTEMPTED
  ACKNOWLEDGED
  UNKNOWN_EXTERNAL_STATE
  RECOVERY_PENDING
  QUERYING
  CANCEL_REQUESTED
  CANCEL_CONFIRMED
  REJECTED_CONFIRMED
  RECONCILED_TERMINAL
- Non-negotiable safety rules:
  * ORDER_NOT_FOUND != ORDER_CANCELED (ambiguity requires positive authoritative resolution).
  * Never transition to CANCEL_CONFIRMED without positive exchange confirmation.
  * Never mark parent complete while any child has unresolved external state.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, ClassVar

logger = logging.getLogger("sky.execution.testnet.lost_ack_fsm")


class IllegalRecoveryTransitionError(Exception):
    """Raised when an illegal recovery state transition is attempted."""


class AmbiguousCancellationForbiddenError(Exception):
    """Raised when cancellation is assumed without authoritative venue confirmation."""


class RecoveryState(StrEnum):
    """
    Formal 10-state recovery lifecycle for handling placement ambiguity.
    """

    PLACEMENT_INTENT_DURABLE = "PLACEMENT_INTENT_DURABLE"
    SUBMISSION_ATTEMPTED = "SUBMISSION_ATTEMPTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    QUERYING = "QUERYING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    REJECTED_CONFIRMED = "REJECTED_CONFIRMED"
    RECONCILED_TERMINAL = "RECONCILED_TERMINAL"


@dataclass(frozen=True)
class RecoveryTransitionRecord:
    """Audit record for recovery state transitions."""

    slice_id: str
    intent_id: str
    from_state: RecoveryState
    to_state: RecoveryState
    reason: str
    timestamp_monotonic_ns: int
    timestamp_utc: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["from_state"] = self.from_state.value
        d["to_state"] = self.to_state.value
        return d


class LostAckRecoveryFSM:
    """
    Supervises the recovery lifecycle of a placement intent under ambiguity.
    Enforces deterministic transitions and prevents phantom cancels.
    """

    ALLOWED_TRANSITIONS: ClassVar[dict[RecoveryState, list[RecoveryState]]] = {
        RecoveryState.PLACEMENT_INTENT_DURABLE: [
            RecoveryState.SUBMISSION_ATTEMPTED,
        ],
        RecoveryState.SUBMISSION_ATTEMPTED: [
            RecoveryState.ACKNOWLEDGED,
            RecoveryState.UNKNOWN_EXTERNAL_STATE,
            RecoveryState.REJECTED_CONFIRMED,
        ],
        RecoveryState.UNKNOWN_EXTERNAL_STATE: [
            RecoveryState.RECOVERY_PENDING,
        ],
        RecoveryState.RECOVERY_PENDING: [
            RecoveryState.QUERYING,
        ],
        RecoveryState.QUERYING: [
            RecoveryState.ACKNOWLEDGED,
            RecoveryState.RECONCILED_TERMINAL,
            RecoveryState.REJECTED_CONFIRMED,
            RecoveryState.UNKNOWN_EXTERNAL_STATE,  # Query timed out, loop back
        ],
        RecoveryState.ACKNOWLEDGED: [
            RecoveryState.CANCEL_REQUESTED,
            RecoveryState.RECONCILED_TERMINAL,
            RecoveryState.UNKNOWN_EXTERNAL_STATE,
        ],
        RecoveryState.CANCEL_REQUESTED: [
            RecoveryState.CANCEL_CONFIRMED,
            RecoveryState.RECONCILED_TERMINAL,  # Fill occurred while cancel was in flight
            RecoveryState.UNKNOWN_EXTERNAL_STATE,
        ],
        RecoveryState.CANCEL_CONFIRMED: [
            RecoveryState.RECONCILED_TERMINAL,
        ],
        RecoveryState.REJECTED_CONFIRMED: [
            RecoveryState.RECONCILED_TERMINAL,
        ],
        RecoveryState.RECONCILED_TERMINAL: [],  # Terminal state
    }

    def __init__(self, slice_id: str, intent_id: str) -> None:
        self.slice_id = slice_id
        self.intent_id = intent_id
        self._current_state = RecoveryState.PLACEMENT_INTENT_DURABLE
        self.history: list[RecoveryTransitionRecord] = []

    @property
    def current_state(self) -> RecoveryState:
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        return self._current_state == RecoveryState.RECONCILED_TERMINAL

    @property
    def is_ambiguous(self) -> bool:
        return self._current_state in (
            RecoveryState.UNKNOWN_EXTERNAL_STATE,
            RecoveryState.RECOVERY_PENDING,
            RecoveryState.QUERYING,
        )

    def transition_to(
        self,
        target_state: RecoveryState,
        reason: str,
        evidence: dict[str, Any] | None = None,
    ) -> RecoveryTransitionRecord:
        """
        Executes a formal state transition. Fails closed on disallowed paths.
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self._current_state, [])
        if target_state not in allowed:
            err_msg = (
                f"[LostAckFSM] Illegal transition for slice {self.slice_id}: "
                f"{self._current_state.value} -> {target_state.value}. Allowed: {[s.value for s in allowed]}"
            )
            logger.error(err_msg)
            raise IllegalRecoveryTransitionError(err_msg)

        # Invariant: ORDER_NOT_FOUND != ORDER_CANCELED
        if target_state == RecoveryState.CANCEL_CONFIRMED:
            # Must verify that evidence contains positive cancellation confirmation
            ev = evidence or {}
            status = str(ev.get("status") or ev.get("orderStatus") or "").upper()
            if status not in ("CANCELED", "CANCELLED", "EXPIRED"):
                raise AmbiguousCancellationForbiddenError(
                    f"Cannot transition to CANCEL_CONFIRMED without positive exchange cancellation evidence. "
                    f"Got status '{status}' for slice {self.slice_id}"
                )

        now_mono = time.monotonic_ns()
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        rec = RecoveryTransitionRecord(
            slice_id=self.slice_id,
            intent_id=self.intent_id,
            from_state=self._current_state,
            to_state=target_state,
            reason=reason,
            timestamp_monotonic_ns=now_mono,
            timestamp_utc=now_utc,
            evidence=evidence or {},
        )
        self.history.append(rec)
        prior = self._current_state
        self._current_state = target_state
        logger.info(
            f"[LostAckFSM] {self.slice_id}: {prior.value} -> {target_state.value} ({reason})"
        )
        return rec
