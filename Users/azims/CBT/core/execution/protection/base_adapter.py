"""
core/execution/protection/base_adapter.py
=========================================
Abstract Base Interface for Live Exchange Protection Adapters.

Institutional Invariants:
- A position is UNPROTECTED until an exchange-native bracket is confirmed (ACKed).
- Fail-Closed: If protection placement fails or rejects, immediate panic-flatten is initiated.
- Break-Even Transition: No unprotected window allowed during stop amendment.
- All secrets stripped and sanitized in responses and error messages.
"""

from __future__ import annotations

import abc
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProtectionStatus(str, Enum):
    PENDING = "PENDING"
    PROTECTED = "PROTECTED"
    BREAKEVEN_PENDING = "BREAKEVEN_PENDING"
    BREAKEVEN_ACTIVE = "BREAKEVEN_ACTIVE"
    FILLED_TP = "FILLED_TP"
    FILLED_SL = "FILLED_SL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EMERGENCY_FLATTEN = "EMERGENCY_FLATTEN"
    FLAT_VERIFIED = "FLAT_VERIFIED"


@dataclass
class ProtectionBracket:
    bracket_id: str
    exchange: str
    environment: str
    symbol: str
    position_side: str  # "BUY" (Long) or "SELL" (Short)
    quantity: float
    entry_price: float
    take_profit_price: float
    stop_loss_price: float
    stop_loss_limit_price: float | None = None
    status: ProtectionStatus = ProtectionStatus.PENDING
    exchange_tp_order_id: str | None = None
    exchange_sl_order_id: str | None = None
    exchange_order_list_id: str | None = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in (
            ProtectionStatus.PROTECTED,
            ProtectionStatus.BREAKEVEN_PENDING,
            ProtectionStatus.BREAKEVEN_ACTIVE,
        )

    @property
    def is_closed(self) -> bool:
        return self.status in (
            ProtectionStatus.FILLED_TP,
            ProtectionStatus.FILLED_SL,
            ProtectionStatus.CANCELLED,
            ProtectionStatus.FLAT_VERIFIED,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["is_active"] = self.is_active
        d["is_closed"] = self.is_closed
        return d


@dataclass
class ProtectionResult:
    success: bool
    bracket_id: str
    status: ProtectionStatus
    exchange_order_list_id: str | None = None
    tp_order_id: str | None = None
    sl_order_id: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class BaseProtectionAdapter(abc.ABC):
    """
    Abstract interface for exchange-specific bracket and stop placement.
    """

    def __init__(self, exchange: str, environment: str):
        self.exchange = exchange.upper().strip()
        self.environment = environment.upper().strip()
        if self.environment not in ("TESTNET", "PRODUCTION"):
            raise ValueError(f"Invalid environment: '{self.environment}'. Must be TESTNET or PRODUCTION.")

    @abc.abstractmethod
    async def place_bracket(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        tp_price: float,
        sl_price: float,
        sl_limit_price: float | None = None,
        entry_price: float = 0.0,
        bracket_id: str | None = None,
    ) -> ProtectionResult:
        """
        Dispatches native exchange protection (e.g. Binance OCO or Bybit trading-stop).
        Fail-closed: Returns a ProtectionResult with success=False if not acknowledged.
        """

    @abc.abstractmethod
    async def amend_stop_loss(
        self,
        bracket: ProtectionBracket,
        new_sl_price: float,
        new_sl_limit_price: float | None = None,
    ) -> ProtectionResult:
        """
        Amends or replaces the stop loss leg (e.g. Move SL to Break-Even).
        Must guarantee ZERO unprotected window during transition.
        """

    @abc.abstractmethod
    async def cancel_protection(
        self,
        bracket: ProtectionBracket,
    ) -> bool:
        """
        Cancels working protection orders for this bracket.
        """

    @abc.abstractmethod
    async def query_protection_status(
        self,
        bracket: ProtectionBracket,
    ) -> ProtectionBracket:
        """
        Queries exchange REST endpoints to reconcile current protection fill/open state.
        """
