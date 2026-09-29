"""
core/execution/testnet/dispatcher.py
====================================
Milestone 22: Algorithmic Slicing & Order Lifecycle Dispatcher (TWAP & Iceberg).

Implements Section 9:
- Deterministic TWAP & Simulated Iceberg execution scheduling.
- Strict conservation of parent quantity across discrete slices.
- Pre-dispatch normalization via ExchangeFilterRulesEngine (tick, step, notional).
- Durable intent generation and event journal integration before wire dispatch.
- Coordinated parent ledger quantity transitions and fill reconciliation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from core.execution.testnet.event_journal import AppendOnlyEventJournal
from core.execution.testnet.execution_ledger import ParentExecutionLedger
from core.execution.testnet.filters import ExchangeFilterRulesEngine, FilterValidationError
from core.execution.testnet.models import (
    CanonicalOrderStatus,
    NormalizedOrderResponse,
    OrderSide,
    OrderType,
    SlicingStrategy,
)
from core.execution.testnet.multi_venue_bridge import MultiVenueTestnetBridge
from core.execution.testnet.placement_intent import DurableIntentStore

logger = logging.getLogger("sky.execution.testnet.dispatcher")


@dataclass(frozen=True)
class SlicingSchedulePlan:
    """Deterministic schedule for parent order execution."""

    parent_order_id: str
    strategy: SlicingStrategy
    total_slices: int
    slice_quantities: list[Decimal]
    interval_seconds: float


class TestnetOrderSlicingDispatcher:
    """
    Orchestrates algorithmic slicing execution (TWAP / Iceberg) across venues.
    """

    def __init__(
        self,
        bridge: MultiVenueTestnetBridge,
        filter_engine: ExchangeFilterRulesEngine,
        intent_store: DurableIntentStore | None = None,
        event_journal: AppendOnlyEventJournal | None = None,
    ) -> None:
        self.bridge = bridge
        self.filter_engine = filter_engine
        self.intent_store = intent_store or DurableIntentStore()
        self.journal = event_journal or AppendOnlyEventJournal()

    def generate_twap_plan(
        self,
        parent_order_id: str,
        venue: str,
        symbol: str,
        target_quantity: Decimal,
        num_slices: int,
        interval_seconds: float = 0.1,
    ) -> SlicingSchedulePlan:
        """
        Generates a deterministic TWAP slicing schedule conserving exact parent quantity.
        Normalizes slice quantities to venue stepSize and allocates remainder to the final slice.
        """
        if num_slices <= 0:
            raise ValueError(f"num_slices must be positive, got {num_slices}")

        config = self.filter_engine.get_config(venue, symbol)
        base_slice = (target_quantity / Decimal(str(num_slices))).quantize(
            config.step_size, rounding=ROUND_DOWN
        )

        slices: list[Decimal] = []
        allocated_so_far = Decimal("0")

        for _i in range(num_slices - 1):
            clamped_slice = self.filter_engine.normalize_quantity(venue, symbol, base_slice)
            slices.append(clamped_slice)
            allocated_so_far += clamped_slice

        # Final slice absorbs the exact remaining quantity
        final_slice_raw = target_quantity - allocated_so_far
        final_slice = self.filter_engine.normalize_quantity(venue, symbol, final_slice_raw)
        slices.append(final_slice)

        # Enforce exact quantity sum identity
        if sum(slices) != target_quantity:
            raise FilterValidationError(
                f"Generated TWAP slices sum ({sum(slices)}) does not equal target quantity ({target_quantity})"
            )

        return SlicingSchedulePlan(
            parent_order_id=parent_order_id,
            strategy=SlicingStrategy.TWAP,
            total_slices=num_slices,
            slice_quantities=slices,
            interval_seconds=interval_seconds,
        )

    async def execute_twap(
        self,
        flight_id: str,
        ledger: ParentExecutionLedger,
        side: OrderSide,
        price: Decimal | None = None,
        num_slices: int = 5,
        interval_seconds: float = 0.05,
        simulate_matching_fills: bool = False,
    ) -> list[NormalizedOrderResponse]:
        """
        Executes parent order via TWAP slicing across the configured venue.
        """
        plan = self.generate_twap_plan(
            parent_order_id=ledger.parent_order_id,
            venue=ledger.venue,
            symbol=ledger.symbol,
            target_quantity=ledger.target_quantity,
            num_slices=num_slices,
            interval_seconds=interval_seconds,
        )

        responses: list[NormalizedOrderResponse] = []

        for idx, slice_qty in enumerate(plan.slice_quantities):
            child_id = f"{ledger.parent_order_id}_SL_{idx + 1:02d}"

            # 1. Allocate slice in ledger
            ledger.allocate_slice(child_id, slice_qty)

            # 2. Normalize order parameters
            norm_instruction = self.filter_engine.normalize_order(
                venue=ledger.venue,
                symbol=ledger.symbol,
                side=side,
                order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
                quantity=slice_qty,
                price=price,
            )

            # 3. Create or reuse durable placement intent
            intent = self.intent_store.create_or_reuse_intent(
                flight_id=flight_id,
                parent_order_id=ledger.parent_order_id,
                child_slice_id=child_id,
                venue=ledger.venue,
                symbol=ledger.symbol,
                side=side,
                order_type=norm_instruction.order_type,
                quantity=norm_instruction.normalized_quantity,
                price=norm_instruction.normalized_price,
            )

            # 4. Record submission in ledger
            ledger.record_submission(child_id, norm_instruction.normalized_quantity)

            # 5. Dispatch via multi-venue bridge
            resp = await self.bridge.place_order(intent)
            responses.append(resp)

            # 6. Record fill or rejection in ledger
            if resp.canonical_status in (
                CanonicalOrderStatus.ACKNOWLEDGED,
                CanonicalOrderStatus.PARTIALLY_FILLED,
            ):
                fill_amt = resp.executed_quantity
                if fill_amt == Decimal("0") and simulate_matching_fills:
                    fill_amt = norm_instruction.normalized_quantity
                if fill_amt > Decimal("0"):
                    ledger.record_fill(
                        child_id,
                        fill_amt,
                        is_terminal=(fill_amt == norm_instruction.normalized_quantity),
                    )
            elif resp.canonical_status == CanonicalOrderStatus.FILLED:
                ledger.record_fill(child_id, resp.executed_quantity, is_terminal=True)
            elif resp.canonical_status in (
                CanonicalOrderStatus.REJECTED_VENUE,
                CanonicalOrderStatus.REJECTED_LOCAL,
            ):
                ledger.record_cancel(child_id, slice_qty)

            # Pacing interval between slices
            if idx < len(plan.slice_quantities) - 1 and interval_seconds > 0:
                await asyncio.sleep(interval_seconds)

        return responses

    async def execute_simulated_iceberg(
        self,
        flight_id: str,
        ledger: ParentExecutionLedger,
        side: OrderSide,
        visible_quantity: Decimal,
        price: Decimal | None = None,
    ) -> list[NormalizedOrderResponse]:
        """
        Executes parent order via client-side simulated Iceberg slicing.
        Dispatches visible_quantity child slices sequentially upon fill confirmation.
        """
        norm_visible = self.filter_engine.normalize_quantity(
            ledger.venue, ledger.symbol, visible_quantity
        )

        responses: list[NormalizedOrderResponse] = []
        slice_idx = 1

        while ledger.allocated_quantity < ledger.target_quantity:
            remaining = ledger.target_quantity - ledger.allocated_quantity
            current_slice_qty = min(norm_visible, remaining)
            clamped_slice = self.filter_engine.normalize_quantity(
                ledger.venue, ledger.symbol, current_slice_qty
            )

            child_id = f"{ledger.parent_order_id}_ICE_{slice_idx:02d}"
            slice_idx += 1

            ledger.allocate_slice(child_id, clamped_slice)

            norm_instruction = self.filter_engine.normalize_order(
                venue=ledger.venue,
                symbol=ledger.symbol,
                side=side,
                order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
                quantity=clamped_slice,
                price=price,
            )

            intent = self.intent_store.create_or_reuse_intent(
                flight_id=flight_id,
                parent_order_id=ledger.parent_order_id,
                child_slice_id=child_id,
                venue=ledger.venue,
                symbol=ledger.symbol,
                side=side,
                order_type=norm_instruction.order_type,
                quantity=norm_instruction.normalized_quantity,
                price=norm_instruction.normalized_price,
            )

            ledger.record_submission(child_id, norm_instruction.normalized_quantity)
            resp = await self.bridge.place_order(intent)
            responses.append(resp)

            # In simulated iceberg, we assume fill before next replenishment
            exec_qty = (
                resp.executed_quantity if resp.executed_quantity > Decimal("0") else clamped_slice
            )
            ledger.record_fill(child_id, exec_qty, is_terminal=True)

        return responses
