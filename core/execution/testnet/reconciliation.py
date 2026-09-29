"""
core/execution/testnet/reconciliation.py
========================================
4-Tier Fill Identity & Conflicting Duplicate Shield.

Implements Section 4:
- Separation of Transport Event ID, Economic Execution ID, Order Lifecycle Event, and Reconciliation Observation.
- Strict Idempotency: 1,000 identical execution reports -> exactly 1 economic fill, 999 transport duplicates.
- Conflicting Duplicate Defense: Matching execution_id with differing price, quantity, or symbol raises
  ConflictingFillAnomalyError, fails closed, and prevents silent data corruption.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from core.execution.testnet.schemas import EconomicFillRecord

logger = logging.getLogger("sky.execution.testnet.reconciliation")


class ConflictingFillAnomalyError(Exception):
    """Raised when an incoming fill matches an existing execution_id but has conflicting economic attributes."""


class TestnetFillReconciliationEngine:
    """
    Manages 4-tier fill deduplication, transport vs economic identity tracking,
    and conflicting duplicate protection.
    """

    def __init__(self, account_scope: str = "TESTNET_SANDBOX") -> None:
        self.account_scope = account_scope

        # Tier 1: Transport message IDs seen
        self._seen_transport_event_ids: set[str] = set()
        self.total_transport_messages: int = 0
        self.total_transport_duplicates: int = 0

        # Tier 2: Authoritative economic fills mapped by (venue, account_scope, execution_id)
        self._economic_fills: dict[str, EconomicFillRecord] = {}

        # Tier 3: Order lifecycle transition logs
        self._order_lifecycle_events: list[dict[str, Any]] = []

        # Tier 4: Reconciliation observations (snapshot observations)
        self._observations_count: int = 0

    def process_execution_report(
        self,
        transport_event_id: str,
        venue: str,
        execution_id: str,
        order_id: str,
        trade_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        price: Decimal | str | float,
        quantity: Decimal | str | float,
        fee: Decimal | str | float = Decimal("0"),
        fee_asset: str = "USDT",
        is_maker: bool = False,
        exchange_timestamp_ms: int = 0,
        received_monotonic_ns: int = 0,
    ) -> tuple[bool, EconomicFillRecord]:
        """
        Processes an incoming execution report.
        Returns: (is_new_economic_fill: bool, record: EconomicFillRecord)
        """
        self.total_transport_messages += 1

        # 1. Tier 1: Transport message deduplication
        if transport_event_id in self._seen_transport_event_ids:
            self.total_transport_duplicates += 1
            is_transport_dup = True
        else:
            self._seen_transport_event_ids.add(transport_event_id)
            is_transport_dup = False

        economic_key = f"{venue}:{self.account_scope}:{execution_id}"
        price_dec = Decimal(str(price))
        qty_dec = Decimal(str(quantity))
        fee_dec = Decimal(str(fee))

        # 2. Tier 2: Economic execution deduplication & conflict defense
        if economic_key in self._economic_fills:
            existing = self._economic_fills[economic_key]

            # Check for conflicting duplicates
            if (
                existing.fill_price != price_dec
                or existing.fill_qty != qty_dec
                or existing.symbol != symbol
                or existing.side != side.upper()
            ):
                conflict_msg = (
                    f"Conflicting duplicate report for {economic_key}: "
                    f"existing=(price={existing.fill_price}, qty={existing.fill_qty}, sym={existing.symbol}, side={existing.side}) vs "
                    f"incoming=(price={price_dec}, qty={qty_dec}, sym={symbol}, side={side.upper()})"
                )
                logger.error(conflict_msg)
                raise ConflictingFillAnomalyError(conflict_msg)

            # Valid identical duplicate -> discard from economic ledger
            if not is_transport_dup:
                self.total_transport_duplicates += 1

            return False, existing

        # New economic fill
        record = EconomicFillRecord(
            venue=venue,
            account_scope=self.account_scope,
            execution_id=execution_id,
            order_id=order_id,
            trade_id=trade_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side.upper(),
            fill_price=price_dec,
            fill_qty=qty_dec,
            fee=fee_dec,
            fee_asset=fee_asset,
            is_maker=is_maker,
            exchange_timestamp_ms=exchange_timestamp_ms,
            received_monotonic_ns=received_monotonic_ns,
        )
        self._economic_fills[economic_key] = record

        # Tier 3: Record lifecycle event
        self._order_lifecycle_events.append(
            {
                "event_type": "ECONOMIC_FILL",
                "economic_key": economic_key,
                "client_order_id": client_order_id,
                "qty": str(qty_dec),
                "price": str(price_dec),
                "received_monotonic_ns": received_monotonic_ns,
            }
        )

        return True, record

    def record_reconciliation_observation(self, observation_metadata: dict[str, Any]) -> None:
        """Records a safe reconciliation snapshot observation without mutating fills."""
        self._observations_count += 1
        logger.debug(
            f"Recorded snapshot observation #{self._observations_count}: {observation_metadata}"
        )

    def get_summary(self) -> dict[str, Any]:
        """Returns comprehensive deduplication and reconciliation telemetry."""
        total_economic_qty = sum(
            (rec.fill_qty for rec in self._economic_fills.values()), Decimal("0")
        )
        return {
            "account_scope": self.account_scope,
            "total_transport_messages": self.total_transport_messages,
            "total_transport_duplicates": self.total_transport_duplicates,
            "total_economic_fills": len(self._economic_fills),
            "total_economic_qty": str(total_economic_qty),
            "total_lifecycle_events": len(self._order_lifecycle_events),
            "total_observations_count": self._observations_count,
        }
