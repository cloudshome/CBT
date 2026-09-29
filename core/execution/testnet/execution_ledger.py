"""
core/execution/testnet/execution_ledger.py
=========================================
Milestone 22: Parent/Child Execution Ledger & 8-Quantity Conservation Invariant Engine.

Implements Section 8:
- Durable, Decimal-safe accounting tracking 8 distinct quantities:
  1. parent_target
  2. allocated_quantity
  3. submitted_quantity
  4. executed_quantity (filled)
  5. open_quantity
  6. canceled_quantity (unfilled remainder)
  7. unresolved_quantity
  8. overfill_quantity
- Immutable conservation identities:
  Q_target = Q_filled + Q_open + Q_canceled + Q_unresolved
  Q_submitted = Q_filled + Q_open + Q_canceled + Q_unresolved (for submitted slices)
  Q_submitted <= Q_target
- Overfill circuit breaker: trips OverfillCircuitBreakerError and protective halt if Q_filled > Q_target.
- Completed lifecycle invariant: Q_unresolved == Decimal("0").
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.execution.testnet.models import CanonicalOrderStatus

logger = logging.getLogger("sky.execution.testnet.ledger")


class OverfillCircuitBreakerError(Exception):
    """Raised when cumulative fills exceed target quantity. Fails closed immediately."""


class QuantityConservationBreachError(Exception):
    """Raised when the fundamental quantity accounting identity is violated."""


class UnresolvedQuantityLifecycleError(Exception):
    """Raised when a parent lifecycle attempts completion while Q_unresolved > 0."""


@dataclass
class ChildSliceLedgerEntry:
    """Individual child slice accounting ledger entry."""

    child_slice_id: str
    parent_order_id: str
    allocated_quantity: Decimal
    submitted_quantity: Decimal
    executed_quantity: Decimal
    open_quantity: Decimal
    canceled_quantity: Decimal
    unresolved_quantity: Decimal
    status: CanonicalOrderStatus
    last_updated_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_slice_id": self.child_slice_id,
            "parent_order_id": self.parent_order_id,
            "allocated_quantity": str(self.allocated_quantity),
            "submitted_quantity": str(self.submitted_quantity),
            "executed_quantity": str(self.executed_quantity),
            "open_quantity": str(self.open_quantity),
            "canceled_quantity": str(self.canceled_quantity),
            "unresolved_quantity": str(self.unresolved_quantity),
            "status": self.status.value,
            "last_updated_utc": self.last_updated_utc,
        }


class ParentExecutionLedger:
    """
    Authoritative parent execution ledger managing multi-slice quantities and invariants.
    """

    def __init__(
        self,
        parent_order_id: str,
        target_quantity: Decimal | str | float,
        symbol: str,
        venue: str,
    ) -> None:
        self.parent_order_id = parent_order_id
        self.target_quantity = Decimal(str(target_quantity))
        self.symbol = symbol.upper()
        self.venue = venue.upper()

        if self.target_quantity <= Decimal("0"):
            raise ValueError(f"Parent target quantity must be positive, got {self.target_quantity}")

        # 8 Distinct Quantities
        self.allocated_quantity: Decimal = Decimal("0")
        self.submitted_quantity: Decimal = Decimal("0")
        self.executed_quantity: Decimal = Decimal("0")
        self.open_quantity: Decimal = Decimal("0")
        self.canceled_quantity: Decimal = Decimal("0")
        self.unresolved_quantity: Decimal = (
            self.target_quantity
        )  # Initially entire target is unallocated/unresolved
        self.overfill_quantity: Decimal = Decimal("0")

        self.children: dict[str, ChildSliceLedgerEntry] = {}
        self.is_halted: bool = False
        self.halt_reason: str | None = None
        self.is_completed: bool = False

    def allocate_slice(
        self, child_slice_id: str, requested_qty: Decimal | str | float
    ) -> ChildSliceLedgerEntry:
        """Allocates slice quantity from the unallocated parent target."""
        self._check_halted()
        req_dec = Decimal(str(requested_qty))
        if req_dec <= Decimal("0"):
            raise ValueError(f"Requested slice quantity must be positive, got {req_dec}")

        remaining_allocatable = self.target_quantity - self.allocated_quantity
        if req_dec > remaining_allocatable:
            raise ValueError(
                f"Cannot allocate slice {req_dec}: exceeds remaining allocatable target {remaining_allocatable} "
                f"(Target={self.target_quantity}, AlreadyAllocated={self.allocated_quantity})"
            )

        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entry = ChildSliceLedgerEntry(
            child_slice_id=child_slice_id,
            parent_order_id=self.parent_order_id,
            allocated_quantity=req_dec,
            submitted_quantity=Decimal("0"),
            executed_quantity=Decimal("0"),
            open_quantity=Decimal("0"),
            canceled_quantity=Decimal("0"),
            unresolved_quantity=req_dec,
            status=CanonicalOrderStatus.CREATED,
            last_updated_utc=now_utc,
        )
        self.children[child_slice_id] = entry
        self.allocated_quantity += req_dec
        self._recompute_and_verify_invariants()
        return entry

    def record_submission(self, child_slice_id: str, submitted_qty: Decimal | str | float) -> None:
        """Records wire dispatch submission of a child slice."""
        self._check_halted()
        entry = self._get_child(child_slice_id)
        sub_dec = Decimal(str(submitted_qty))

        entry.submitted_quantity = sub_dec
        entry.open_quantity = sub_dec
        entry.unresolved_quantity = Decimal("0")  # Acknowledged/open, no longer unresolved
        entry.status = CanonicalOrderStatus.DISPATCHED
        entry.last_updated_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self._recompute_and_verify_invariants()

    def record_fill(
        self,
        child_slice_id: str,
        fill_qty: Decimal | str | float,
        is_terminal: bool = False,
    ) -> None:
        """Records an authoritative fill event on a child slice."""
        self._check_halted()
        entry = self._get_child(child_slice_id)
        f_dec = Decimal(str(fill_qty))

        entry.executed_quantity += f_dec
        entry.open_quantity = max(Decimal("0"), entry.open_quantity - f_dec)
        if is_terminal or entry.open_quantity == Decimal("0"):
            entry.status = CanonicalOrderStatus.FILLED
        else:
            entry.status = CanonicalOrderStatus.PARTIALLY_FILLED

        entry.last_updated_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._recompute_and_verify_invariants()

    def record_cancel(
        self, child_slice_id: str, canceled_unfilled_qty: Decimal | str | float
    ) -> None:
        """Records confirmed cancellation of unfilled slice quantity."""
        self._check_halted()
        entry = self._get_child(child_slice_id)
        c_dec = Decimal(str(canceled_unfilled_qty))

        entry.canceled_quantity += c_dec
        entry.open_quantity = max(Decimal("0"), entry.open_quantity - c_dec)
        entry.unresolved_quantity = Decimal("0")
        entry.status = CanonicalOrderStatus.CANCELED
        entry.last_updated_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self._recompute_and_verify_invariants()

    def record_unresolved_status(
        self, child_slice_id: str, unresolved_qty: Decimal | str | float
    ) -> None:
        """Marks slice quantity as ambiguous/unresolved during network recovery."""
        entry = self._get_child(child_slice_id)
        u_dec = Decimal(str(unresolved_qty))
        entry.unresolved_quantity = u_dec
        entry.open_quantity = max(Decimal("0"), entry.open_quantity - u_dec)
        entry.status = CanonicalOrderStatus.UNKNOWN_EXTERNAL_STATE
        entry.last_updated_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._recompute_and_verify_invariants()

    def mark_complete(self) -> None:
        """
        Marks parent order execution complete.
        Strict requirement: Q_unresolved == Decimal("0").
        """
        self._check_halted()
        self._recompute_and_verify_invariants()

        if self.unresolved_quantity > Decimal("0"):
            raise UnresolvedQuantityLifecycleError(
                f"Cannot complete parent order {self.parent_order_id}: "
                f"unresolved quantity {self.unresolved_quantity} > 0. Must resolve all external states."
            )

        self.is_completed = True
        logger.info(
            f"[Ledger] Parent {self.parent_order_id} marked COMPLETE. "
            f"(Filled={self.executed_quantity}, Canceled={self.canceled_quantity}, Target={self.target_quantity})"
        )

    def _get_child(self, child_slice_id: str) -> ChildSliceLedgerEntry:
        if child_slice_id not in self.children:
            raise KeyError(
                f"Child slice {child_slice_id} not found in parent ledger {self.parent_order_id}"
            )
        return self.children[child_slice_id]

    def _check_halted(self) -> None:
        if self.is_halted:
            raise OverfillCircuitBreakerError(
                f"Parent ledger {self.parent_order_id} is HALTED: {self.halt_reason}"
            )

    def _recompute_and_verify_invariants(self) -> None:
        """
        Recomputes aggregate ledger quantities from children and enforces conservation identities.
        """
        agg_submitted = Decimal("0")
        agg_executed = Decimal("0")
        agg_open = Decimal("0")
        agg_canceled = Decimal("0")
        agg_unresolved = (
            self.target_quantity - self.allocated_quantity
        )  # Unallocated remainder is unresolved

        for child in self.children.values():
            agg_submitted += child.submitted_quantity
            agg_executed += child.executed_quantity
            agg_open += child.open_quantity
            agg_canceled += child.canceled_quantity
            agg_unresolved += child.unresolved_quantity

        self.submitted_quantity = agg_submitted
        self.executed_quantity = agg_executed
        self.open_quantity = agg_open
        self.canceled_quantity = agg_canceled
        self.unresolved_quantity = agg_unresolved

        # 1. Overfill Check: Q_filled <= Q_target
        if self.executed_quantity > self.target_quantity:
            self.overfill_quantity = self.executed_quantity - self.target_quantity
            self.is_halted = True
            self.halt_reason = (
                f"OVERFILL DETECTED: Executed={self.executed_quantity} exceeds Target={self.target_quantity} "
                f"by {self.overfill_quantity}"
            )
            logger.critical(f"[Ledger] {self.halt_reason}")
            raise OverfillCircuitBreakerError(self.halt_reason)

        # 2. Submitted Quantity Boundary: Q_submitted <= Q_target
        if self.submitted_quantity > self.target_quantity:
            raise QuantityConservationBreachError(
                f"Submitted quantity {self.submitted_quantity} exceeds parent target {self.target_quantity}"
            )

        # 3. Fundamental Parent Accounting Identity:
        # Q_target = Q_filled + Q_open + Q_canceled + Q_unresolved
        accounted_total = (
            self.executed_quantity
            + self.open_quantity
            + self.canceled_quantity
            + self.unresolved_quantity
        )
        if accounted_total != self.target_quantity:
            raise QuantityConservationBreachError(
                f"Quantity conservation violated for parent {self.parent_order_id}: "
                f"Target={self.target_quantity} != (Filled={self.executed_quantity} + Open={self.open_quantity} + "
                f"Canceled={self.canceled_quantity} + Unresolved={self.unresolved_quantity} = {accounted_total})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_order_id": self.parent_order_id,
            "target_quantity": str(self.target_quantity),
            "allocated_quantity": str(self.allocated_quantity),
            "submitted_quantity": str(self.submitted_quantity),
            "executed_quantity": str(self.executed_quantity),
            "open_quantity": str(self.open_quantity),
            "canceled_quantity": str(self.canceled_quantity),
            "unresolved_quantity": str(self.unresolved_quantity),
            "overfill_quantity": str(self.overfill_quantity),
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
            "is_completed": self.is_completed,
            "children_count": len(self.children),
        }
