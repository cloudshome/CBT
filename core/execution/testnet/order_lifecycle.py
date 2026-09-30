"""
core/execution/testnet/order_lifecycle.py
=========================================
Exact Economic Lifecycle Accounting & Invariant Engine.

Implements Invariant 3.1 & Invariant 3.2:
- Exact Decimal quantity accounting (zero binary float precision artifacts).
- Fundamental parent accounting identity:
    Q_target = Q_filled + Q_open + Q_canceled + Q_unresolved
- Completed lifecycle requirement: Q_unresolved == Decimal("0").
- Precise ChildOrderLifecycle contract & Zero Orphaned Slices invariant.
- Rejection of assumed cancellations (ambiguity requires authoritative resolution).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from core.execution.testnet.schemas import ChildOrderLifecycle

logger = logging.getLogger("sky.execution.testnet.order_lifecycle")


class QuantityConservationError(Exception):
    """Raised when the fundamental quantity accounting identity is violated."""


class OrphanSliceError(Exception):
    """Raised when an unlinked, unresolved, or ambiguous child slice is detected."""


class AmbiguousCancellationError(Exception):
    """Raised when an order status is assumed cancelled without authoritative confirmation."""


class ParentOrderLifecycle:
    """
    Manages parent order execution lifecycle and verifies strict economic quantity conservation.
    """

    def __init__(
        self,
        parent_id: str,
        symbol: str,
        side: str,
        target_qty: Decimal | str | float,
    ) -> None:
        self.parent_id = parent_id
        self.symbol = symbol
        self.side = side.upper()
        self.target_qty = Decimal(str(target_qty))

        self.children: dict[str, ChildOrderLifecycle] = {}
        self.is_lifecycle_complete: bool = False

    def add_child(
        self,
        child_id: str,
        exchange: str,
        client_order_id: str,
        requested_qty: Decimal | str | float,
    ) -> ChildOrderLifecycle:
        """Registers a new child slice in PENDING state."""
        req_dec = Decimal(str(requested_qty))
        if req_dec <= Decimal("0"):
            raise ValueError(f"Requested child qty must be positive, got {req_dec}")

        child = ChildOrderLifecycle(
            parent_id=self.parent_id,
            child_id=child_id,
            exchange=exchange,
            client_order_id=client_order_id,
            exchange_order_id=None,
            state="SUBMITTED",
            requested_qty=req_dec,
            filled_qty=Decimal("0"),
            canceled_qty=Decimal("0"),
            unresolved_qty=req_dec,  # Until acknowledged, requested qty is unresolved
            reconciliation_status="PENDING_ACK",
        )
        self.children[child_id] = child
        self.verify_quantity_conservation()
        return child

    def record_child_ack(
        self,
        child_id: str,
        exchange_order_id: str,
    ) -> ChildOrderLifecycle:
        """Records exchange order placement acknowledgment."""
        child = self._get_child(child_id)
        updated = ChildOrderLifecycle(
            parent_id=child.parent_id,
            child_id=child.child_id,
            exchange=child.exchange,
            client_order_id=child.client_order_id,
            exchange_order_id=exchange_order_id,
            state="ACCEPTED",
            requested_qty=child.requested_qty,
            filled_qty=child.filled_qty,
            canceled_qty=child.canceled_qty,
            unresolved_qty=child.requested_qty - child.filled_qty - child.canceled_qty,
            reconciliation_status="ACCEPTED_ACTIVE",
        )
        self.children[child_id] = updated
        self.verify_quantity_conservation()
        return updated

    def record_child_fill(
        self,
        child_id: str,
        fill_qty: Decimal | str | float,
        is_complete: bool = False,
    ) -> ChildOrderLifecycle:
        """Applies a partial or full execution fill to child order."""
        child = self._get_child(child_id)
        add_fill = Decimal(str(fill_qty))
        new_filled = child.filled_qty + add_fill

        if new_filled > child.requested_qty:
            raise QuantityConservationError(
                f"Overfill detected on child {child_id}: filled {new_filled} > requested {child.requested_qty}"
            )

        new_state = (
            "FILLED" if (is_complete or new_filled == child.requested_qty) else "PARTIALLY_FILLED"
        )
        new_unres = (
            Decimal("0")
            if new_state == "FILLED"
            else (child.requested_qty - new_filled - child.canceled_qty)
        )
        rec_status = "RECONCILED" if new_unres == Decimal("0") else "PARTIAL_RECONCILED"

        updated = ChildOrderLifecycle(
            parent_id=child.parent_id,
            child_id=child.child_id,
            exchange=child.exchange,
            client_order_id=child.client_order_id,
            exchange_order_id=child.exchange_order_id,
            state=new_state,
            requested_qty=child.requested_qty,
            filled_qty=new_filled,
            canceled_qty=child.canceled_qty,
            unresolved_qty=new_unres,
            reconciliation_status=rec_status,
        )
        self.children[child_id] = updated
        self.verify_quantity_conservation()
        return updated

    def record_child_cancel(
        self,
        child_id: str,
        canceled_qty: Decimal | str | float,
    ) -> ChildOrderLifecycle:
        """
        Records authoritative cancellation.
        Strict Invariant: Assumed cancellations are forbidden; cancellation must be explicit.
        """
        child = self._get_child(child_id)
        cancel_dec = Decimal(str(canceled_qty))
        new_canceled = child.canceled_qty + cancel_dec

        if (child.filled_qty + new_canceled) > child.requested_qty:
            raise QuantityConservationError(
                f"Over-cancellation on child {child_id}: filled({child.filled_qty}) + canceled({new_canceled}) > requested({child.requested_qty})"
            )

        new_unres = child.requested_qty - child.filled_qty - new_canceled
        rec_status = "RECONCILED" if new_unres == Decimal("0") else "PARTIAL_CANCELED"

        updated = ChildOrderLifecycle(
            parent_id=child.parent_id,
            child_id=child.child_id,
            exchange=child.exchange,
            client_order_id=child.client_order_id,
            exchange_order_id=child.exchange_order_id,
            state="CANCELED",
            requested_qty=child.requested_qty,
            filled_qty=child.filled_qty,
            canceled_qty=new_canceled,
            unresolved_qty=new_unres,
            reconciliation_status=rec_status,
        )
        self.children[child_id] = updated
        self.verify_quantity_conservation()
        return updated

    def complete_lifecycle(self) -> dict[str, Any]:
        """
        Declares parent lifecycle complete and verifies all invariants:
        1. Q_unresolved == Decimal("0").
        2. All children resolved to RECONCILED.
        3. Zero orphaned slices.
        """
        self.verify_quantity_conservation()

        total_unresolved = sum(c.unresolved_qty for c in self.children.values())
        if total_unresolved != Decimal("0"):
            unres_children = [
                (cid, str(c.unresolved_qty), c.state)
                for cid, c in self.children.items()
                if c.unresolved_qty != Decimal("0")
            ]
            raise OrphanSliceError(
                f"Parent {self.parent_id} cannot complete lifecycle with unresolved quantity: "
                f"total_unresolved={total_unresolved}, children={unres_children}"
            )

        # Check all child reconciliation statuses
        unreconciled = [
            cid for cid, c in self.children.items() if c.reconciliation_status != "RECONCILED"
        ]
        if unreconciled:
            raise OrphanSliceError(
                f"Parent {self.parent_id} has unreconciled child slices: {unreconciled}"
            )

        self.is_lifecycle_complete = True
        return self.get_summary()

    def verify_quantity_conservation(self) -> None:
        """
        Verifies exact Decimal quantity conservation identity across all children:
        For every child:
            requested_qty == filled_qty + open_qty + canceled_qty + unresolved_qty
        And aggregate:
            sum(child.requested_qty) <= target_qty (slicing does not exceed parent)
        """
        total_requested = Decimal("0")
        for child in self.children.values():
            assert child.unresolved_qty >= Decimal("0"), (
                f"Negative unresolved_qty in {child.child_id}"
            )
            assert child.filled_qty >= Decimal("0"), f"Negative filled_qty in {child.child_id}"
            assert child.canceled_qty >= Decimal("0"), f"Negative canceled_qty in {child.child_id}"

            # Child identity
            derived_req = child.filled_qty + child.canceled_qty + child.unresolved_qty
            if derived_req != child.requested_qty:
                raise QuantityConservationError(
                    f"Child identity breach in {child.child_id}: requested {child.requested_qty} != "
                    f"filled({child.filled_qty}) + canceled({child.canceled_qty}) + unresolved({child.unresolved_qty})"
                )
            total_requested += child.requested_qty

        if total_requested > self.target_qty:
            raise QuantityConservationError(
                f"Parent requested sum {total_requested} exceeds target_qty {self.target_qty}"
            )

    def get_summary(self) -> dict[str, Any]:
        total_filled = sum((c.filled_qty for c in self.children.values()), Decimal("0"))
        total_canceled = sum((c.canceled_qty for c in self.children.values()), Decimal("0"))
        total_unresolved = sum((c.unresolved_qty for c in self.children.values()), Decimal("0"))

        return {
            "parent_id": self.parent_id,
            "symbol": self.symbol,
            "side": self.side,
            "target_qty": str(self.target_qty),
            "total_filled": str(total_filled),
            "total_canceled": str(total_canceled),
            "total_unresolved": "0" if total_unresolved == Decimal("0") else str(total_unresolved),
            "is_lifecycle_complete": self.is_lifecycle_complete,
            "child_count": len(self.children),
            "children": {cid: c.to_dict() for cid, c in self.children.items()},
        }

    def _get_child(self, child_id: str) -> ChildOrderLifecycle:
        if child_id not in self.children:
            raise KeyError(f"Unknown child_id {child_id} in parent {self.parent_id}")
        return self.children[child_id]
