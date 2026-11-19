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
    constitutional real-capital lock and strict fail-closed allowlist.
    """

    ALLOWED_TESTNET_HOSTS: set[str] = {
        "testnet.binance.vision",
        "testnet.binancefuture.com",
        "api-testnet.bybit.com",
    }

    ALLOWED_NOTIFICATION_AND_LLM_HOSTS: set[str] = {
        "api.telegram.org",
        "generativelanguage.googleapis.com",
        "api.openai.com",
    }

    BINANCE_PUBLIC_SPOT_PATHS: tuple[str, ...] = (
        "/api/v3/klines",
        "/api/v3/ticker",
        "/api/v3/depth",
        "/api/v3/exchangeinfo",
        "/api/v3/time",
        "/api/v3/ping",
        "/api/v3/trades",
        "/api/v3/historicaltrades",
        "/api/v3/aggtrades",
        "/api/v3/uiklines",
    )

    BINANCE_PUBLIC_FUTURES_PATHS: tuple[str, ...] = (
        "/fapi/v1/klines",
        "/fapi/v1/fundingrate",
        "/fapi/v1/openinterest",
        "/fapi/v1/ticker",
        "/fapi/v1/depth",
        "/fapi/v1/time",
        "/fapi/v1/ping",
        "/fapi/v1/exchangeinfo",
        "/fapi/v1/premiumindex",
    )

    BYBIT_PUBLIC_MARKET_PREFIX: str = "/v5/market/"

    PROHIBITED_SUBSTRINGS: tuple[str, ...] = (
        "/account",
        "/order",
        "/sapi/",
        "/fapi/v2/account",
        "/fapi/v1/order",
        "/position",
        "/withdraw",
        "/transfer",
    )

    @classmethod
    def verify_request(cls, method: str, url: str) -> tuple[bool, str]:
        """
        Validates an outbound request method and URL against a strict fail-closed allowlist.

        Raises:
            PermissionError: When attempting to send any unapproved outbound request,
                             mutating request to production exchanges, private endpoint access,
                             or unknown hosts while REAL_CAPITAL_ENABLED is False.

        Returns:
            tuple[bool, str]: (True, reason) if permitted.
        """
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().strip()
        path = parsed.path.lower()
        norm_method = method.upper().strip()

        if not REAL_CAPITAL_ENABLED:
            if not host:
                msg = f"EGRESS_FIREWALL_BLOCKED: Missing destination host in URL '{url}'."
                logger.critical(msg)
                raise PermissionError(msg)

            # 1. Testnet endpoints (full CRUD permitted)
            if host in cls.ALLOWED_TESTNET_HOSTS:
                return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"

            # 2. Notification and LLM endpoints (GET / POST permitted)
            if host in cls.ALLOWED_NOTIFICATION_AND_LLM_HOSTS:
                if norm_method in ("GET", "POST"):
                    return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
                msg = (
                    f"EGRESS_FIREWALL_BLOCKED: Prohibited method {norm_method} to '{url}'."
                )
                logger.critical(msg)
                raise PermissionError(msg)

            # 3. Dedicated public mirror (GET only, no account/order)
            if host == "data-api.binance.vision":
                if norm_method == "GET" and not any(p in path for p in cls.PROHIBITED_SUBSTRINGS):
                    return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
                msg = (
                    f"EGRESS_FIREWALL_BLOCKED: Non-GET or sensitive access to '{url}' is prohibited."
                )
                logger.critical(msg)
                raise PermissionError(msg)

            # 4. Binance Spot Public Market Data (strictly GET on public paths)
            if host == "api.binance.com":
                if norm_method == "GET":
                    if any(p in path for p in cls.PROHIBITED_SUBSTRINGS):
                        msg = f"EGRESS_FIREWALL_BLOCKED: Private Binance endpoint '{path}' is prohibited."
                        logger.critical(msg)
                        raise PermissionError(msg)
                    if any(path.startswith(allowed) for allowed in cls.BINANCE_PUBLIC_SPOT_PATHS):
                        return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
                msg = (
                    f"EGRESS_FIREWALL_BLOCKED: Disallowed request {norm_method} '{url}' on api.binance.com."
                )
                logger.critical(msg)
                raise PermissionError(msg)

            # 5. Binance Futures Public Market Data (strictly GET on public paths)
            if host == "fapi.binance.com":
                if norm_method == "GET":
                    if any(p in path for p in cls.PROHIBITED_SUBSTRINGS):
                        msg = f"EGRESS_FIREWALL_BLOCKED: Private Binance Futures endpoint '{path}' is prohibited."
                        logger.critical(msg)
                        raise PermissionError(msg)
                    if any(path.startswith(allowed) for allowed in cls.BINANCE_PUBLIC_FUTURES_PATHS):
                        return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
                msg = (
                    f"EGRESS_FIREWALL_BLOCKED: Disallowed request {norm_method} '{url}' on fapi.binance.com."
                )
                logger.critical(msg)
                raise PermissionError(msg)

            # 6. Bybit Public Market Data (strictly GET on /v5/market/*)
            if host == "api.bybit.com":
                if (
                    norm_method == "GET"
                    and path.startswith(cls.BYBIT_PUBLIC_MARKET_PREFIX)
                    and not any(p in path for p in cls.PROHIBITED_SUBSTRINGS)
                ):
                    return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
                msg = (
                    f"EGRESS_FIREWALL_BLOCKED: Disallowed request {norm_method} '{url}' on api.bybit.com."
                )
                logger.critical(msg)
                raise PermissionError(msg)

            # 7. Fail-Closed Default: Any other host or IP address is rejected
            msg = (
                f"EGRESS_FIREWALL_BLOCKED: Outbound request to unapproved host '{host}' "
                f"('{url}') is strictly prohibited while REAL_CAPITAL_ENABLED is False."
            )
            logger.critical(msg)
            raise PermissionError(msg)

        return True, "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"
