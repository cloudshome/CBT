"""
core/execution/testnet/models.py
================================
Milestone 22: Live Testnet Execution Flight Runner & Multi-Venue Domain Models.

Establishes:
1. Immutable Domain Identity Hierarchy:
   flight_id -> parent_order_id -> child_slice_id -> placement_intent_id -> venue_order_id -> execution_id
2. Canonical Order & Lifecycle State Enums.
3. Normalized Execution & Order Response Models with full raw provenance.
4. 7-Stage Latency Interval Taxonomy (T0 -> T7).
5. Epistemic Classification Enums (LIFECYCLE_VALIDITY_EVIDENCE).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class CanonicalOrderStatus(StrEnum):
    """
    Canonical, venue-agnostic lifecycle states for order tracking.
    """

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    ACK_PENDING = "ACK_PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED_LOCAL = "REJECTED_LOCAL"
    REJECTED_VENUE = "REJECTED_VENUE"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    ANOMALY_HALTED = "ANOMALY_HALTED"


class OrderSide(StrEnum):
    """Order side enumeration."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Supported order type enumeration."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class SlicingStrategy(StrEnum):
    """Supported algorithmic execution slicing strategies."""

    TWAP = "TWAP"
    ICEBERG = "ICEBERG"


class VenueType(StrEnum):
    """Approved venue types under strict endpoint isolation."""

    BINANCE_SPOT_TESTNET = "BINANCE_SPOT_TESTNET"
    BYBIT_V5_TESTNET = "BYBIT_V5_TESTNET"
    DETERMINISTIC_MOCK = "DETERMINISTIC_MOCK"


class EpistemicClassification(StrEnum):
    """
    Epistemic boundaries for testnet execution claims.
    Enforces that testnet performance is never conflated with live alpha.
    """

    LIFECYCLE_VALIDITY_EVIDENCE = "LIFECYCLE_VALIDITY_EVIDENCE"
    NON_CAPITAL_QUALIFICATION = "NON_CAPITAL_QUALIFICATION"
    ALPHA_UNPROVEN = "ALPHA_UNPROVEN"


@dataclass(frozen=True)
class NormalizedOrderResponse:
    """
    Normalized response across venues retaining venue-native attributes and raw provenance.
    """

    venue: str
    native_order_id: str | None
    client_order_id: str
    native_status: str
    canonical_status: CanonicalOrderStatus
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_quantity: Decimal
    executed_quantity: Decimal
    remaining_quantity: Decimal
    price: Decimal | None
    fees: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    exchange_timestamp_ms: int = 0
    received_monotonic_ns: int = 0
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["requested_quantity"] = str(self.requested_quantity)
        d["executed_quantity"] = str(self.executed_quantity)
        d["remaining_quantity"] = str(self.remaining_quantity)
        if self.price is not None:
            d["price"] = str(self.price)
        d["fees"] = str(self.fees)
        d["canonical_status"] = self.canonical_status.value
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        return d


@dataclass(frozen=True)
class M22LatencyDecomposition:
    """
    7-interval decomposed latency telemetry (T0 -> T7) in monotonic nanoseconds.

    Timestamps:
    - T0: Slicing intent generated
    - T1: Intent durably persisted
    - T2: Wire dispatch initiated
    - T3: HTTP / transport ACK received
    - T4: Order acknowledgment normalized
    - T5: WebSocket execution report received
    - T6: Reconciliation ledger committed
    - T7: Qualification ledger accepted
    """

    slice_id: str
    placement_intent_id: str
    t0_intent_created_ns: int
    t1_intent_persisted_ns: int
    t2_wire_dispatch_ns: int
    t3_transport_ack_ns: int
    t4_ack_normalized_ns: int
    t5_ws_execution_ns: int
    t6_reconcile_committed_ns: int
    t7_qualification_accepted_ns: int
    clock_offset_ms: float = 0.0
    clock_uncertainty_ms: float = 0.0

    @property
    def intent_persistence_duration_ns(self) -> int:
        return max(0, self.t1_intent_persisted_ns - self.t0_intent_created_ns)

    @property
    def wire_dispatch_duration_ns(self) -> int:
        return max(0, self.t2_wire_dispatch_ns - self.t1_intent_persisted_ns)

    @property
    def transport_rtt_duration_ns(self) -> int:
        return max(0, self.t3_transport_ack_ns - self.t2_wire_dispatch_ns)

    @property
    def ack_normalization_duration_ns(self) -> int:
        return max(0, self.t4_ack_normalized_ns - self.t3_transport_ack_ns)

    @property
    def ws_fill_latency_duration_ns(self) -> int:
        return max(0, self.t5_ws_execution_ns - self.t4_ack_normalized_ns)

    @property
    def reconciliation_duration_ns(self) -> int:
        return max(0, self.t6_reconcile_committed_ns - self.t5_ws_execution_ns)

    @property
    def qualification_duration_ns(self) -> int:
        return max(0, self.t7_qualification_accepted_ns - self.t6_reconcile_committed_ns)

    @property
    def total_end_to_end_duration_ns(self) -> int:
        return max(0, self.t7_qualification_accepted_ns - self.t0_intent_created_ns)

    def is_strictly_monotonic(self) -> bool:
        """Verifies that all recorded timestamps satisfy T_i <= T_{i+1} without clock regression."""
        ts = [
            self.t0_intent_created_ns,
            self.t1_intent_persisted_ns,
            self.t2_wire_dispatch_ns,
            self.t3_transport_ack_ns,
            self.t4_ack_normalized_ns,
            self.t5_ws_execution_ns,
            self.t6_reconcile_committed_ns,
            self.t7_qualification_accepted_ns,
        ]
        return all(ts[i] <= ts[i + 1] for i in range(len(ts) - 1))

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "placement_intent_id": self.placement_intent_id,
            "t0_intent_created_ns": self.t0_intent_created_ns,
            "t1_intent_persisted_ns": self.t1_intent_persisted_ns,
            "t2_wire_dispatch_ns": self.t2_wire_dispatch_ns,
            "t3_transport_ack_ns": self.t3_transport_ack_ns,
            "t4_ack_normalized_ns": self.t4_ack_normalized_ns,
            "t5_ws_execution_ns": self.t5_ws_execution_ns,
            "t6_reconcile_committed_ns": self.t6_reconcile_committed_ns,
            "t7_qualification_accepted_ns": self.t7_qualification_accepted_ns,
            "intent_persistence_ms": round(self.intent_persistence_duration_ns / 1_000_000, 3),
            "wire_dispatch_ms": round(self.wire_dispatch_duration_ns / 1_000_000, 3),
            "transport_rtt_ms": round(self.transport_rtt_duration_ns / 1_000_000, 3),
            "ack_normalization_ms": round(self.ack_normalization_duration_ns / 1_000_000, 3),
            "ws_fill_latency_ms": round(self.ws_fill_latency_duration_ns / 1_000_000, 3),
            "reconciliation_ms": round(self.reconciliation_duration_ns / 1_000_000, 3),
            "qualification_ms": round(self.qualification_duration_ns / 1_000_000, 3),
            "total_end_to_end_ms": round(self.total_end_to_end_duration_ns / 1_000_000, 3),
            "clock_offset_ms": self.clock_offset_ms,
            "clock_uncertainty_ms": self.clock_uncertainty_ms,
            "is_strictly_monotonic": self.is_strictly_monotonic(),
        }
