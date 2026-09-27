"""
core/execution/connectors/base.py
=================================
Abstract Base Interface for Live Exchange Connectors.

Safety Invariants:
- Strict Environment Separation: TESTNET vs PRODUCTION.
- Strongly-typed inputs and outputs; raw arbitrary requests are rejected.
- Sanitized exceptions and responses: API keys, secrets, and signatures are stripped.
- Explicit status modeling (FILLED, PARTIALLY_FILLED, REJECTED, CANCELLED, AMBIGUOUS).
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any

from core.auth.credential_vault import sanitize_text

logger = logging.getLogger("sky.exchange_connectors")


class ExchangeError(Exception):
    """Base exception for exchange communication errors."""


class ExchangeAuthenticationError(ExchangeError):
    """Raised when exchange rejects API key, secret, or signature."""


class ExchangeRateLimitError(ExchangeError):
    """Raised when exchange returns HTTP 429 rate limit."""

    def __init__(self, message: str, retry_after_sec: float = 10.0):
        super().__init__(sanitize_text(message))
        self.retry_after_sec = retry_after_sec


class ExchangeTimeoutError(ExchangeError):
    """Raised when exchange request times out (results in AMBIGUOUS state)."""


class ExchangeNetworkError(ExchangeError):
    """Raised when DNS/TLS/Connection reset occurs."""


class ExchangeRejectedError(ExchangeError):
    """Raised when exchange explicitly rejects order (insufficient funds, bad price, etc.)."""


@dataclass
class NormalizedBalance:
    asset: str
    free: float
    locked: float
    total: float


@dataclass
class NormalizedOrderResult:
    client_order_id: str
    exchange_order_id: str
    symbol: str
    status: str  # "FILLED", "PARTIALLY_FILLED", "NEW", "REJECTED", "CANCELLED"
    executed_qty: float
    executed_price: float
    cumulative_quote_qty: float
    raw_status: str
    exchange: str
    environment: str
    latency_ms: float
    message: str = ""


class BaseExchangeConnector(abc.ABC):
    """
    Abstract connector interface for live spot exchange order execution.
    """

    def __init__(
        self,
        exchange: str,
        environment: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        timeout_sec: float = 5.0,
    ):
        self.exchange = exchange.upper().strip()
        self.environment = environment.upper().strip()
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.timeout_sec = timeout_sec

        if self.environment not in ("TESTNET", "PRODUCTION"):
            raise ValueError(
                f"Invalid environment: '{self.environment}'. Must be 'TESTNET' or 'PRODUCTION'."
            )

    @abc.abstractmethod
    async def get_balances(self) -> list[NormalizedBalance]:
        """Fetches account asset balances."""

    @abc.abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """Places a live order on the exchange."""

    @abc.abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancels an active order."""

    @abc.abstractmethod
    async def get_order_status(
        self,
        symbol: str,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> NormalizedOrderResult:
        """Queries order status for reconciliation."""

    @abc.abstractmethod
    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Queries all currently active open orders."""

    @abc.abstractmethod
    async def cancel_all_orders(
        self,
        symbol: str,
    ) -> list[dict[str, Any]]:
        """Cancels all active open orders for a given symbol."""
