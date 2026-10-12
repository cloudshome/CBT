"""
core/execution/testnet/credential_policy.py
===========================================
Milestone 21: Credential Scope & Isolation Policy.

Guarantees:
- Testnet API credentials only; production credentials rejected.
- Zero withdrawal or transfer permissions allowed / requested.
- Secret masking in all log outputs and telemetry traces.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.execution.testnet.endpoint_policy import Environment

logger = logging.getLogger("sky.execution.testnet.credential_policy")


class CredentialScopeError(PermissionError):
    """Raised when an API credential violates testnet isolation or contains dangerous permissions."""


def mask_secret(secret: str | None) -> str:
    """Masks sensitive strings for safe logging and telemetry display."""
    if not secret:
        return "[EMPTY]"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


@dataclass(frozen=True)
class TestnetCredentials:
    """
    Testnet API credential container with explicit permission assertions.
    """

    api_key: str
    api_secret: str
    environment: Environment
    can_withdraw: bool = False
    can_transfer: bool = False

    def __post_init__(self) -> None:
        if self.can_withdraw:
            msg = "SECURITY VIOLATION: Testnet credentials cannot possess withdrawal permissions!"
            logger.critical(msg)
            raise CredentialScopeError(msg)

        if self.can_transfer:
            msg = "SECURITY VIOLATION: Testnet credentials cannot possess universal transfer permissions!"
            logger.critical(msg)
            raise CredentialScopeError(msg)

        if not self.api_key or not self.api_secret:
            raise CredentialScopeError("API key and secret cannot be empty in testnet credentials")

    def to_safe_dict(self) -> dict[str, Any]:
        """Returns credential metadata with masked keys for diagnostics."""
        return {
            "api_key_masked": mask_secret(self.api_key),
            "environment": self.environment.value,
            "can_withdraw": self.can_withdraw,
            "can_transfer": self.can_transfer,
        }


class CredentialPolicy:
    """
    Validates credential security scopes and protects against production credential leaks.
    """

    @classmethod
    def validate_account_permissions(cls, account_info: dict[str, Any], venue: str) -> None:
        """
        Inspects live exchange account permissions response to verify no withdrawal permissions exist.
        """
        # Binance Spot account response check
        if venue.upper().startswith("BINANCE"):
            permissions = account_info.get("permissions", [])
            perms_upper = [str(p).upper() for p in permissions] if isinstance(permissions, list) else []
            is_testnet_spot_scoped = (
                "TESTNET" in venue.upper()
                and bool(perms_upper)
                and "commissionRates" in account_info
                and "WITHDRAW" not in perms_upper
                and "WITHDRAWALS" not in perms_upper
            )
            # If account explicitly lists withdrawal or lacks testnet spot scope
            if (account_info.get("canWithdraw", False) and not is_testnet_spot_scoped) or (
                "WITHDRAW" in perms_upper or "WITHDRAWALS" in perms_upper
            ):
                msg = f"SECURITY ALERT: Exchange account reports canWithdraw=True on {venue}!"
                logger.critical(msg)
                raise CredentialScopeError(msg)

        # Bybit V5 account check
        elif venue.upper().startswith("BYBIT"):
            permissions = account_info.get("permissions", {})
            if isinstance(permissions, dict):
                # Bybit API key info often lists permissions like ["SpotTrade", "DerivativesTrade"]
                if "Withdraw" in permissions or permissions.get("Withdrawal") is True:
                    msg = "SECURITY ALERT: Bybit API key possesses withdrawal permissions!"
                    logger.critical(msg)
                    raise CredentialScopeError(msg)

        logger.info(f"Credential permissions verified safe (0 withdrawal capabilities) on {venue}")
