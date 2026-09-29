"""
core/execution/testnet/venue_capabilities.py
============================================
Milestone 22: Concrete Venue Capability Descriptors & Operation Guards.

Provides explicit, non-emulated venue capability contracts for Binance Spot Testnet,
Bybit V5 Testnet, and the Deterministic Mock. Unsupported operations fail explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class UnsupportedVenueOperationError(Exception):
    """Raised when an operation is attempted on a venue that does not natively support it."""


@dataclass(frozen=True)
class VenueCapabilityProfile:
    """
    Exhaustive venue capability descriptor.
    Guarantees no silent emulation of unsupported venue behaviors.
    """

    venue_id: str
    supports_private_ws: bool
    supports_order_query: bool
    supports_cancel_all: bool
    supports_client_order_id: bool
    max_client_order_id_length: int
    supports_execution_id: bool
    supports_partial_fills: bool
    supports_native_iceberg: bool
    rate_limit_requests_per_minute: int
    recovery_reserve_fraction: float = 0.20

    def assert_operation_supported(self, operation: str) -> None:
        """Fails closed if the venue does not support the requested operation."""
        op = operation.upper()
        if op == "NATIVE_ICEBERG" and not self.supports_native_iceberg:
            raise UnsupportedVenueOperationError(
                f"Venue {self.venue_id} does not support native iceberg orders. "
                "Use client-side simulated slicing dispatcher instead."
            )
        if op == "CANCEL_ALL" and not self.supports_cancel_all:
            raise UnsupportedVenueOperationError(
                f"Venue {self.venue_id} does not support batch cancel-all operations."
            )
        if op == "ORDER_QUERY" and not self.supports_order_query:
            raise UnsupportedVenueOperationError(
                f"Venue {self.venue_id} does not support single order status querying."
            )
        if op == "PRIVATE_WS" and not self.supports_private_ws:
            raise UnsupportedVenueOperationError(
                f"Venue {self.venue_id} does not support private authenticated WebSocket streams."
            )

    def validate_client_order_id_length(self, client_order_id: str) -> None:
        """Enforces venue client order ID string length limit."""
        if len(client_order_id) > self.max_client_order_id_length:
            raise ValueError(
                f"Client order ID '{client_order_id}' length {len(client_order_id)} "
                f"exceeds {self.venue_id} maximum allowed length {self.max_client_order_id_length}."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical Venue Profiles
BINANCE_SPOT_TESTNET_PROFILE = VenueCapabilityProfile(
    venue_id="BINANCE_SPOT_TESTNET",
    supports_private_ws=True,
    supports_order_query=True,
    supports_cancel_all=True,
    supports_client_order_id=True,
    max_client_order_id_length=36,
    supports_execution_id=True,
    supports_partial_fills=True,
    supports_native_iceberg=True,
    rate_limit_requests_per_minute=1200,
    recovery_reserve_fraction=0.20,
)

BYBIT_V5_TESTNET_PROFILE = VenueCapabilityProfile(
    venue_id="BYBIT_V5_TESTNET",
    supports_private_ws=True,
    supports_order_query=True,
    supports_cancel_all=True,
    supports_client_order_id=True,
    max_client_order_id_length=36,
    supports_execution_id=True,
    supports_partial_fills=True,
    supports_native_iceberg=False,  # Bybit V5 Spot does not provide native iceberg parameter
    rate_limit_requests_per_minute=600,
    recovery_reserve_fraction=0.20,
)

DETERMINISTIC_MOCK_PROFILE = VenueCapabilityProfile(
    venue_id="DETERMINISTIC_MOCK",
    supports_private_ws=True,
    supports_order_query=True,
    supports_cancel_all=True,
    supports_client_order_id=True,
    max_client_order_id_length=36,
    supports_execution_id=True,
    supports_partial_fills=True,
    supports_native_iceberg=False,
    rate_limit_requests_per_minute=10000,
    recovery_reserve_fraction=0.10,
)

_VENUE_PROFILES: dict[str, VenueCapabilityProfile] = {
    "BINANCE_SPOT_TESTNET": BINANCE_SPOT_TESTNET_PROFILE,
    "BYBIT_V5_TESTNET": BYBIT_V5_TESTNET_PROFILE,
    "DETERMINISTIC_MOCK": DETERMINISTIC_MOCK_PROFILE,
}


def get_venue_capability_profile(venue_id: str) -> VenueCapabilityProfile:
    """Retrieves capability profile for the specified venue."""
    vid = venue_id.upper()
    if vid in _VENUE_PROFILES:
        return _VENUE_PROFILES[vid]
    # Fallback to conservative defaults
    return VenueCapabilityProfile(
        venue_id=vid,
        supports_private_ws=False,
        supports_order_query=True,
        supports_cancel_all=False,
        supports_client_order_id=True,
        max_client_order_id_length=32,
        supports_execution_id=True,
        supports_partial_fills=True,
        supports_native_iceberg=False,
        rate_limit_requests_per_minute=300,
        recovery_reserve_fraction=0.25,
    )
