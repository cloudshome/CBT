"""
core/execution/testnet/fault_injection.py
=========================================
Controlled 13-Point Fault Matrix & Operational Severity Engine.

Implements Section 9:
- Explicit fault severity levels: INFORMATIONAL, DEGRADED, HALT_REQUIRED, SESSION_INVALIDATING.
- 13 distinct injection points covering transport, ordering, cancellation, streams, persistence, and external reset.
- Verifies that every injected fault produces its declared expected behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.execution.testnet.schemas import FaultSeverity, FaultType

logger = logging.getLogger("sky.execution.testnet.fault_injection")


@dataclass
class FaultDefinition:
    """Declared specification for an injected fault."""

    fault_type: FaultType
    severity: FaultSeverity
    injection_point: str
    expected_behavior: str
    executed_count: int = 0
    passed_verification_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault_type": self.fault_type.value,
            "severity": self.severity.value,
            "injection_point": self.injection_point,
            "expected_behavior": self.expected_behavior,
            "executed_count": self.executed_count,
            "passed_verification_count": self.passed_verification_count,
        }


class FaultInjectionController:
    """
    Coordinates synthetic fault injection across the 13-point testnet matrix.
    Tracks executions and validates expected responses.
    """

    def __init__(self) -> None:
        self.matrix: dict[FaultType, FaultDefinition] = {
            FaultType.REQUEST_DELAY: FaultDefinition(
                fault_type=FaultType.REQUEST_DELAY,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Transport",
                expected_behavior="SLA telemetry records delay without failing order",
            ),
            FaultType.ACK_DROP: FaultDefinition(
                fault_type=FaultType.ACK_DROP,
                severity=FaultSeverity.DEGRADED,
                injection_point="Response transport",
                expected_behavior="Recovery status query initiated; zero blind retry",
            ),
            FaultType.DUPLICATE_ACK: FaultDefinition(
                fault_type=FaultType.DUPLICATE_ACK,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Response transport",
                expected_behavior="Handled idempotently with zero state corruption",
            ),
            FaultType.DUPLICATE_FILL: FaultDefinition(
                fault_type=FaultType.DUPLICATE_FILL,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Event stream",
                expected_behavior="Transport duplicate recorded; zero duplicate economic fill",
            ),
            FaultType.FILL_BEFORE_ACK: FaultDefinition(
                fault_type=FaultType.FILL_BEFORE_ACK,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Event ordering",
                expected_behavior="Out-of-order buffer reorders; parent lifecycle completes cleanly",
            ),
            FaultType.OUT_OF_ORDER_REPORTS: FaultDefinition(
                fault_type=FaultType.OUT_OF_ORDER_REPORTS,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Event stream",
                expected_behavior="Sequence-aware buffering preserves monotonic state transitions",
            ),
            FaultType.WS_DISCONNECT: FaultDefinition(
                fault_type=FaultType.WS_DISCONNECT,
                severity=FaultSeverity.DEGRADED,
                injection_point="Stream transport",
                expected_behavior="Auto-reconnect with exponential backoff and gap recovery query",
            ),
            FaultType.REST_TIMEOUT: FaultDefinition(
                fault_type=FaultType.REST_TIMEOUT,
                severity=FaultSeverity.DEGRADED,
                injection_point="Request transport",
                expected_behavior="Order query before resubmission avoids duplicate orders",
            ),
            FaultType.CANCEL_TIMEOUT: FaultDefinition(
                fault_type=FaultType.CANCEL_TIMEOUT,
                severity=FaultSeverity.DEGRADED,
                injection_point="Cancellation path",
                expected_behavior="Unknown state marked pending; never assumed canceled",
            ),
            FaultType.EXCHANGE_REJECT: FaultDefinition(
                fault_type=FaultType.EXCHANGE_REJECT,
                severity=FaultSeverity.INFORMATIONAL,
                injection_point="Venue adapter",
                expected_behavior="Terminal rejection logged; parent rebalances remaining quantity",
            ),
            FaultType.SQLITE_CRASH: FaultDefinition(
                fault_type=FaultType.SQLITE_CRASH,
                severity=FaultSeverity.HALT_REQUIRED,
                injection_point="Persistence",
                expected_behavior="WAL journal recovery verification; fail closed on corruption",
            ),
            FaultType.PROCESS_KILL: FaultDefinition(
                fault_type=FaultType.PROCESS_KILL,
                severity=FaultSeverity.HALT_REQUIRED,
                injection_point="Orchestrator process",
                expected_behavior="Crash recovery rehydrates state via RECOVERY_RECONCILIATION",
            ),
            FaultType.EXCHANGE_RESET: FaultDefinition(
                fault_type=FaultType.EXCHANGE_RESET,
                severity=FaultSeverity.SESSION_INVALIDATING,
                injection_point="External environment",
                expected_behavior="Detects sequence reset; trips INVALIDATED state; logs audit break",
            ),
        }

    def record_injection(self, fault_type: FaultType) -> FaultDefinition:
        """Records occurrence of a fault injection."""
        defn = self.matrix[fault_type]
        defn.executed_count += 1
        logger.info(
            f"[FaultInjection] Injected {fault_type.value} ({defn.severity.value}) at {defn.injection_point}"
        )
        return defn

    def record_verification_success(self, fault_type: FaultType) -> None:
        """Records verified correct handling of an injected fault."""
        self.matrix[fault_type].passed_verification_count += 1

    def get_matrix_scorecard(self) -> dict[str, Any]:
        """Returns full audit report on fault injection coverage and success rates."""
        all_passed = True
        total_injected = 0
        total_verified = 0

        details = {}
        for ftype, defn in self.matrix.items():
            total_injected += defn.executed_count
            total_verified += defn.passed_verification_count
            if defn.executed_count > defn.passed_verification_count:
                all_passed = False
            details[ftype.value] = defn.to_dict()

        return {
            "all_faults_handled_correctly": all_passed,
            "total_faults_injected": total_injected,
            "total_faults_verified": total_verified,
            "fault_scenarios": details,
        }
