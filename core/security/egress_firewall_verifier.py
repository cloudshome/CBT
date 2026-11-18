"""
core/security/egress_firewall_verifier.py
=========================================
Surgical Outbound Egress Firewall & Endpoint Policy for SKY / CBT.

Constitutional Invariant:
- When REAL_CAPITAL_ENABLED is False, any outbound order placement or mutating request
  (POST/PUT/DELETE) targeting live production exchange order endpoints is hard-blocked
  at Layer 7 before socket creation or HTTP transmission.
- Public read-only market data (GET klines, tickers, orderbook depth), testnet endpoints,
  and essential platform notifications (Telegram) remain fully operational.
"""

from __future__ import annotations

import logging
import urllib.parse

from core.risk.execution_isolation import REAL_CAPITAL_ENABLED

logger = logging.getLogger("sky.security.egress_firewall")


class OutboundEgressPolicy:
    """
    Evaluates outbound HTTP and WebSocket connection targets against the
    constitutional real-capital lock and surgical endpoint egress rules.
    """

    PRODUCTION_ORDER_HOSTS: set[str] = {
        "fapi.binance.com",
        "dapi.binance.com",
        "api1.binance.com",
        "api2.binance.com",
        "api3.binance.com",
        "api.bybit.com",
        "api.hyperliquid.xyz",
    }

    PRODUCTION_ORDER_PATH_PATTERNS: list[str] = [
        "/api/v3/order",
        "/sapi/v1/margin/order",
        "/sapi/v1/capital/withdraw",
    ]

    ALLOWED_TESTNET_AND_PUBLIC_HOSTS: set[str] = {
        "testnet.binance.vision",
        "testnet.binancefuture.com",
        "api-testnet.bybit.com",
        "data-api.binance.vision",
        "api.telegram.org",
    }

    @classmethod
    def verify_request(cls, method: str, url: str) -> tuple[bool, str]:
        """
        Validates an outbound request method and URL.

        Raises:
            PermissionError: When attempting to send mutating requests to production
                             order endpoints while REAL_CAPITAL_ENABLED is False.

        Returns:
            tuple[bool, str]: (True, reason) if permitted.
        """
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path
        norm_method = method.upper().strip()

        if not REAL_CAPITAL_ENABLED:
            # 1. Dedicated production order hosts (Binance Futures/Derivatives, Bybit, Hyperliquid)
            if host in cls.PRODUCTION_ORDER_HOSTS:
                if norm_method in ("POST", "PUT", "DELETE") or "/order" in path.lower():
                    msg = (
                        f"EGRESS_FIREWALL_BLOCKED: Outbound {norm_method} to production exchange "
                        f"endpoint '{url}' is prohibited while REAL_CAPITAL_ENABLED is False."
                    )
                    logger.critical(msg)
                    raise PermissionError(msg)

            # 2. Dual-use production hosts (api.binance.com): allow GET klines, block order mutations
            if host == "api.binance.com":
                if norm_method in ("POST", "PUT", "DELETE") or any(
                    p in path.lower() for p in cls.PRODUCTION_ORDER_PATH_PATTERNS
                ):
                    msg = (
                        f"EGRESS_FIREWALL_BLOCKED: Outbound order/mutation request to '{url}' "
                        f"is prohibited while REAL_CAPITAL_ENABLED is False."
                    )
                    logger.critical(msg)
                    raise PermissionError(msg)

        return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
