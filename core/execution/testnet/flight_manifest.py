"""
core/execution/testnet/flight_manifest.py
=========================================
Milestone 22: Durable Flight Manifest & Configuration Integrity.

Implements Section 12:
- Immutable flight manifest governing testnet execution boundaries.
- Collision-resistant flight ID and SHA-256 configuration hash.
- Bounded execution parameters: approved venues, symbols, max quantity, max notional.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from core.execution.testnet.endpoint_policy import Environment
from core.execution.testnet.models import SlicingStrategy


class ManifestValidationError(Exception):
    """Raised when a flight manifest violates constitutional boundaries or bounds."""


@dataclass(frozen=True)
class FlightManifest:
    """
    Durable authorization manifest for an autonomous testnet flight rehearsal.
    """

    flight_id: str
    environment: Environment
    venue_allowlist: list[str]
    symbol_allowlist: list[str]
    max_parent_quantity: Decimal
    max_notional_usd: Decimal
    max_child_count: int
    max_concurrent_exposure_usd: Decimal
    max_duration_sec: float
    max_request_rate_per_min: int
    execution_policy: SlicingStrategy
    panic_cancel_scope: str = "FLIGHT_ONLY"
    expiration_utc: str = ""
    operator_metadata: dict[str, str] = field(default_factory=dict)
    config_hash_sha256: str = ""

    def validate_flight_bounds(
        self,
        symbol: str,
        venue: str,
        quantity: Decimal,
        notional_usd: Decimal,
        child_count: int,
    ) -> None:
        """Validates requested execution against manifest boundaries."""
        if venue.upper() not in [v.upper() for v in self.venue_allowlist]:
            raise ManifestValidationError(
                f"Venue {venue} not permitted in flight {self.flight_id}. Allowed: {self.venue_allowlist}"
            )
        if symbol.upper() not in [s.upper() for s in self.symbol_allowlist]:
            raise ManifestValidationError(
                f"Symbol {symbol} not permitted in flight {self.flight_id}. Allowed: {self.symbol_allowlist}"
            )
        if quantity > self.max_parent_quantity:
            raise ManifestValidationError(
                f"Requested quantity {quantity} exceeds manifest ceiling {self.max_parent_quantity}"
            )
        if notional_usd > self.max_notional_usd:
            raise ManifestValidationError(
                f"Requested notional ${notional_usd} exceeds manifest ceiling ${self.max_notional_usd}"
            )
        if child_count > self.max_child_count:
            raise ManifestValidationError(
                f"Requested child count {child_count} exceeds manifest ceiling {self.max_child_count}"
            )

    @classmethod
    def create_standard_rehearsal_manifest(
        cls,
        flight_id: str | None = None,
        environment: Environment = Environment.BINANCE_TESTNET,
        venue_allowlist: list[str] | None = None,
        symbol_allowlist: list[str] | None = None,
        max_parent_quantity: Decimal = Decimal("10.0"),
        max_notional_usd: Decimal = Decimal("50000.00"),
        max_child_count: int = 50,
        max_duration_sec: float = 3600.0,
        execution_policy: SlicingStrategy = SlicingStrategy.TWAP,
    ) -> FlightManifest:
        """Constructs and computes SHA-256 digest for a standard rehearsal flight manifest."""
        fid = flight_id or f"FLIGHT_{uuid.uuid4().hex[:8].upper()}"
        venues = venue_allowlist or [
            "BINANCE_SPOT_TESTNET",
            "BYBIT_V5_TESTNET",
            "DETERMINISTIC_MOCK",
        ]
        symbols = symbol_allowlist or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BTCUSDT", "ETHUSDT"]
        exp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + max_duration_sec))

        raw_dict = {
            "flight_id": fid,
            "environment": environment.value,
            "venue_allowlist": sorted(venues),
            "symbol_allowlist": sorted(symbols),
            "max_parent_quantity": str(max_parent_quantity),
            "max_notional_usd": str(max_notional_usd),
            "max_child_count": max_child_count,
            "max_duration_sec": max_duration_sec,
            "execution_policy": execution_policy.value,
            "panic_cancel_scope": "FLIGHT_ONLY",
            "expiration_utc": exp_utc,
        }
        config_hash = hashlib.sha256(
            json.dumps(raw_dict, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return cls(
            flight_id=fid,
            environment=environment,
            venue_allowlist=venues,
            symbol_allowlist=symbols,
            max_parent_quantity=max_parent_quantity,
            max_notional_usd=max_notional_usd,
            max_child_count=max_child_count,
            max_concurrent_exposure_usd=max_notional_usd,
            max_duration_sec=max_duration_sec,
            max_request_rate_per_min=600,
            execution_policy=execution_policy,
            panic_cancel_scope="FLIGHT_ONLY",
            expiration_utc=exp_utc,
            operator_metadata={"operator": "ANTIGRAVITY", "mode": "AUTONOMOUS_TESTNET_REHEARSAL"},
            config_hash_sha256=config_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["environment"] = self.environment.value
        d["max_parent_quantity"] = str(self.max_parent_quantity)
        d["max_notional_usd"] = str(self.max_notional_usd)
        d["max_concurrent_exposure_usd"] = str(self.max_concurrent_exposure_usd)
        d["execution_policy"] = self.execution_policy.value
        return d
