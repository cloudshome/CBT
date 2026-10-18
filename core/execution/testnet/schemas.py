"""
core/execution/testnet/schemas.py
=================================
Milestone 20: Gate 5 Extended Testnet Reliability Qualification & Execution Lifecycle Rehearsal.

Contracts, data classes, and enums for durable FSM states, session epochs,
clock policies, venue capabilities, and 7-stage decomposed latency telemetry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any


class BurnInState(StrEnum):
    """
    Durable FSM states for Milestone 20 testnet burn-in rehearsal.
    Includes explicit RECOVERY_RECONCILIATION and INVALIDATED states.
    """

    IDLE = "IDLE"
    WARMING_UP = "WARMING_UP"
    ACTIVE_REHEARSAL = "ACTIVE_REHEARSAL"
    DEGRADED = "DEGRADED"
    RECOVERY_RECONCILIATION = "RECOVERY_RECONCILIATION"
    ANOMALY_HALTED = "ANOMALY_HALTED"
    COMPLETED_14_DAYS = "COMPLETED_14_DAYS"
    INVALIDATED = "INVALIDATED"


class FaultSeverity(StrEnum):
    """Severity classification for injected faults and operational anomalies."""

    INFORMATIONAL = "INFORMATIONAL"
    DEGRADED = "DEGRADED"
    HALT_REQUIRED = "HALT_REQUIRED"
    SESSION_INVALIDATING = "SESSION_INVALIDATING"


class FaultType(StrEnum):
    """Controlled 13-point testnet fault matrix scenarios."""

    REQUEST_DELAY = "REQUEST_DELAY"
    ACK_DROP = "ACK_DROP"
    DUPLICATE_ACK = "DUPLICATE_ACK"
    DUPLICATE_FILL = "DUPLICATE_FILL"
    FILL_BEFORE_ACK = "FILL_BEFORE_ACK"
    OUT_OF_ORDER_REPORTS = "OUT_OF_ORDER_REPORTS"
    WS_DISCONNECT = "WS_DISCONNECT"
    REST_TIMEOUT = "REST_TIMEOUT"
    CANCEL_TIMEOUT = "CANCEL_TIMEOUT"
    EXCHANGE_REJECT = "EXCHANGE_REJECT"
    SQLITE_CRASH = "SQLITE_CRASH"
    PROCESS_KILL = "PROCESS_KILL"
    EXCHANGE_RESET = "EXCHANGE_RESET"


@dataclass(frozen=True)
class VenueCapabilities:
    """Venue capabilities and operational constraints specification."""

    venue_id: str
    supports_private_ws: bool
    supports_order_query: bool
    supports_cancel_all: bool
    supports_client_order_id: bool
    supports_execution_id: bool
    supports_partial_fills: bool
    market_data_characteristics: str
    reset_behavior: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClockPolicy:
    """
    Clock synchronization and offset-estimation policy.
    Decouples clock offset from network RTT and event processing delays.
    """

    max_estimated_offset_ms: float = 50.0
    max_offset_uncertainty_ms: float = 25.0
    max_measurement_age_ms: float = 5000.0
    stale_offset_action: str = "DEGRADED"
    offset_uncertainty_required: bool = True
    monotonic_clock_for_durations: bool = True
    wall_clock_for_audit_timestamps: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionEpoch:
    """Session epoch for tracking continuity across restarts and interruptions."""

    session_id: str
    epoch_id: str
    epoch_index: int
    started_at_utc: str
    ended_at_utc: str | None = None
    status: str = "ACTIVE"
    continuity_break_reason: str | None = None
    healthy_duration_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionDurations:
    """3-tier duration accounting distinguishing wall-clock from qualifying health."""

    wall_clock_elapsed_sec: float
    healthy_duration_sec: float
    invalidated_duration_sec: float
    target_duration_sec: float = 14.0 * 24.0 * 3600.0  # 14 days in seconds
    is_continuous_14_days: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChildOrderLifecycle:
    """
    Child execution instruction lifecycle contract.
    Guarantees exact Decimal quantity accounting and zero orphaned slices.
    """

    parent_id: str
    child_id: str
    exchange: str
    client_order_id: str
    exchange_order_id: str | None
    state: str
    requested_qty: Decimal
    filled_qty: Decimal
    canceled_qty: Decimal
    unresolved_qty: Decimal
    reconciliation_status: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["requested_qty"] = str(self.requested_qty)
        d["filled_qty"] = str(self.filled_qty)
        d["canceled_qty"] = str(self.canceled_qty)
        d["unresolved_qty"] = str(self.unresolved_qty)
        return d


@dataclass(frozen=True)
class EconomicFillRecord:
    """
    Authoritative economic fill record.
    Deduplicated strictly by (venue, account_scope, execution_id).
    """

    venue: str
    account_scope: str
    execution_id: str
    order_id: str
    trade_id: str
    client_order_id: str
    symbol: str
    side: str
    fill_price: Decimal
    fill_qty: Decimal
    fee: Decimal
    fee_asset: str
    is_maker: bool
    exchange_timestamp_ms: int
    received_monotonic_ns: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fill_price"] = str(self.fill_price)
        d["fill_qty"] = str(self.fill_qty)
        d["fee"] = str(self.fee)
        return d


@dataclass
class DecomposedLatencyRecord:
    """
    7-Stage decomposed hotpath latency record.
    All stage durations are measured via monotonic nanoseconds.
    """

    slice_id: str
    decision_to_dispatch_ns: int
    dispatch_to_send_ns: int
    send_to_ack_ns: int
    ack_to_fill_ns: int
    fill_to_receive_ns: int
    receive_to_reconcile_ns: int
    total_end_to_end_ns: int
    clock_offset_estimate_ms: float
    is_fault_injected: bool = False
    fault_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LatencyQuantileSummary:
    """Statistical summary of decomposed latency across percentiles."""

    stage_name: str
    sample_count: int
    p50_us: float
    p90_us: float
    p95_us: float
    p99_us: float
    max_us: float
    is_fault_injected_sample: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
