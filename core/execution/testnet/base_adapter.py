"""
core/execution/testnet/base_adapter.py
======================================
Abstract Base Connector & Venue Capabilities Specification.

Implements Section 8:
- Explicit separation of transport and venue semantics.
- Declares exact venue capabilities and operational constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from core.execution.testnet.schemas import VenueCapabilities


class BaseTestnetAdapter(ABC):
    """
    Abstract contract for exchange testnet and simulation connectors.
    """

    def __init__(self, capabilities: VenueCapabilities) -> None:
        self.capabilities = capabilities

    @property
    def venue_id(self) -> str:
        return self.capabilities.venue_id

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Submits an order instruction to the venue or simulator."""

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Requests order cancellation from the venue or simulator."""

    @abstractmethod
    async def query_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Queries authoritative status of an order."""

    @abstractmethod
    async def get_server_time_ms(self) -> int:
        """Retrieves exchange server time in milliseconds for clock offset estimation."""

    @abstractmethod
    async def get_account_balances(self) -> dict[str, Decimal]:
        """Retrieves asset balances to verify non-negative collateral invariants."""
