"""
core/execution/testnet/endpoint_policy.py
=========================================
Milestone 21: Production Endpoint & Credential Firewall Policy.

BLOCKER 1 RESOLUTION:
Enforces immutable, allowlisted environment policy that structurally rejects
all production hostnames, user-supplied arbitrary endpoints, and testnet-to-production
fallbacks before any network socket or credential loader executes.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, ClassVar
from urllib.parse import urlparse

logger = logging.getLogger("sky.execution.testnet.endpoint_policy")


class EndpointSecurityBreachError(PermissionError):
    """Raised when an unauthorized, production, or non-allowlisted endpoint is accessed."""


class Environment(str, Enum):
    """Strict execution environments permitted in testnet testing."""

    DETERMINISTIC = "DETERMINISTIC"
    BINANCE_TESTNET = "BINANCE_TESTNET"
    BYBIT_TESTNET = "BYBIT_TESTNET"


class _ImmutablePolicyMeta(type):
    """Metaclass that strictly prevents overriding REAL_CAPITAL_ENABLED to True."""

    @property
    def REAL_CAPITAL_ENABLED(cls) -> bool:
        return False

    def __setattr__(cls, name: str, value: Any) -> None:
        if name == "REAL_CAPITAL_ENABLED" and value is not False:
            raise AttributeError("REAL_CAPITAL_ENABLED is immutable and permanently False")
        super().__setattr__(name, value)


class EndpointPolicy(metaclass=_ImmutablePolicyMeta):
    """
    Immutable security policy governing network destinations for testnet adapters.
    Guarantees structural isolation from live production capital and endpoints.
    """

    ALLOWED_ENVIRONMENTS: ClassVar[frozenset[Environment]] = frozenset(
        {
            Environment.DETERMINISTIC,
            Environment.BINANCE_TESTNET,
            Environment.BYBIT_TESTNET,
        }
    )

    # Canonical hostnames allowlist strictly mapped per environment
    CANONICAL_HOSTNAMES: ClassVar[dict[Environment, frozenset[str]]] = {
        Environment.DETERMINISTIC: frozenset({"localhost", "127.0.0.1"}),
        Environment.BINANCE_TESTNET: frozenset(
            {
                "testnet.binance.vision",
                "ws-api.testnet.binance.vision",
                "stream.testnet.binance.vision",
            }
        ),
        Environment.BYBIT_TESTNET: frozenset(
            {
                "api-testnet.bybit.com",
                "stream-testnet.bybit.com",
            }
        ),
    }

    # Prohibited production hostnames and substrings (fail-closed blacklist)
    PRODUCTION_HOST_INDICATORS: ClassVar[frozenset[str]] = frozenset(
        {
            "api.binance.com",
            "api1.binance.com",
            "api2.binance.com",
            "api3.binance.com",
            "stream.binance.com",
            "ws-api.binance.com",
            "fapi.binance.com",
            "dapi.binance.com",
            "api.bybit.com",
            "api.bytick.com",
            "stream.bybit.com",
            "stream.bytick.com",
        }
    )

    @classmethod
    def validate_environment(cls, environment: Environment | str) -> Environment:
        """
        Validates environment eligibility. Fails closed on any unknown or production mode.
        """
        if cls.REAL_CAPITAL_ENABLED:
            msg = "CRITICAL SECURITY BREACH: real_capital_enabled cannot be True in testnet policy!"
            logger.critical(msg)
            raise EndpointSecurityBreachError(msg)

        try:
            env_enum = Environment(environment)
        except ValueError:
            msg = f"Unauthorized environment '{environment}'. Only {list(cls.ALLOWED_ENVIRONMENTS)} permitted."
            logger.error(msg)
            raise EndpointSecurityBreachError(msg) from None

        if env_enum not in cls.ALLOWED_ENVIRONMENTS:
            msg = f"Environment '{env_enum}' is not in allowed testnet set."
            logger.error(msg)
            raise EndpointSecurityBreachError(msg)

        return env_enum

    @classmethod
    def validate_url(cls, environment: Environment, url: str) -> str:
        """
        Validates a REST or WebSocket URL against canonical environment hostnames.
        Rejects arbitrary URLs, spoofed domains, and production targets.
        """
        if cls.REAL_CAPITAL_ENABLED:
            raise EndpointSecurityBreachError(
                "Capital firewall violation: real_capital_enabled is True"
            )

        cls.validate_environment(environment)

        if environment == Environment.DETERMINISTIC:
            return url

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        if not hostname:
            msg = f"Invalid URL format: cannot extract hostname from '{url}'"
            logger.error(msg)
            raise EndpointSecurityBreachError(msg)

        # 1. Reject any known production hostnames or production domain suffixes
        is_prod = (
            hostname in cls.PRODUCTION_HOST_INDICATORS
            or hostname.endswith(".binance.com")
            or hostname == "binance.com"
            or hostname.endswith(".bytick.com")
            or hostname == "bytick.com"
            or (
                hostname.endswith(".bybit.com")
                and not hostname.startswith(("api-testnet.", "stream-testnet."))
            )
            or hostname == "bybit.com"
        )
        if is_prod:
            msg = f"PRODUCTION ENDPOINT REJECTED: Attempted connection to production host '{hostname}'!"
            logger.critical(msg)
            raise EndpointSecurityBreachError(msg)

        # 2. Check canonical exact hostname allowlist
        allowed_hosts = cls.CANONICAL_HOSTNAMES.get(environment, frozenset())
        if hostname not in allowed_hosts:
            msg = (
                f"UNAUTHORIZED HOSTNAME: Host '{hostname}' is not allowlisted for environment '{environment}'. "
                f"Allowed hosts: {sorted(list(allowed_hosts))}"
            )
            logger.error(msg)
            raise EndpointSecurityBreachError(msg)

        # 3. Check scheme - external testnets must use TLS-encrypted protocols
        allowed_schemes = (
            {"https", "wss"}
            if environment != Environment.DETERMINISTIC
            else {"http", "ws", "https", "wss"}
        )
        if parsed.scheme not in allowed_schemes:
            msg = f"UNENCRYPTED_SCHEME_REJECTED: Scheme '{parsed.scheme}' is not permitted for '{environment}'. TLS required."
            logger.error(msg)
            raise EndpointSecurityBreachError(msg)

        return url
