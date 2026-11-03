"""
core/risk/execution_isolation.py
================================
Milestone 33.1: Permanent Execution Isolation & Multi-Layer Constitutional Airgap.

Constitutional Mandate:
REAL_CAPITAL_ENABLED is permanently False.
No environment variable, CLI flag, configuration file, database mutation,
API request, admin privilege, AI-generated instruction, or multi-signature
workflow can enable real-capital execution.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Final

logger = logging.getLogger(__name__)

# Permanent Constitutional Constant (Type-checked as Final)
REAL_CAPITAL_ENABLED: Final[bool] = False

# Forbidden venue, desk, and mode indicators
FORBIDDEN_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "LIVE",
        "REAL",
        "PRODUCTION",
        "PROD",
        "REAL_CAPITAL",
        "MAINNET",
        "BINANCE_REAL",
        "BYBIT_REAL",
        "COINBASE_REAL",
        "OKX_REAL",
        "KRAKEN_REAL",
        "LIVE_BROKER",
    }
)

FORBIDDEN_ENV_VARS: Final[frozenset[str]] = frozenset(
    {
        "REAL_CAPITAL_ENABLED",
        "ENABLE_LIVE_TRADING",
        "ALLOW_REAL_CAPITAL",
        "CBT_LIVE_EXECUTION",
        "CBT_REAL_CAPITAL",
        "SKY_LIVE_TRADING",
        "FORCE_LIVE_EXECUTION",
    }
)

ALLOWED_ENVIRONMENTS: Final[frozenset[str]] = frozenset(
    {
        "PAPER",
        "TESTNET",
        "SHADOW",
        "SIMULATION",
        "REPLAY",
        "BACKTEST",
        "RESEARCH",
        "SANDBOX",
    }
)


class ConstitutionalViolationError(PermissionError):
    """Raised when an attempt is made to bypass constitutional capital isolation."""

    pass


def assert_execution_airgap(
    exchange: str | None = None,
    desk: str | None = None,
    mode: str | None = None,
    environment: str | None = None,
) -> None:
    """
    Enforces runtime execution airgap across all venue, desk, mode, and env parameters.
    Raises ConstitutionalViolationError immediately if any parameter targets real capital.
    """
    # 1. Environment variable tamper scan
    for var in FORBIDDEN_ENV_VARS:
        val = os.environ.get(var, "").strip().lower()
        if val in ("1", "true", "yes", "on", "enable", "enabled"):
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Environment variable '{var}={val}' attempted to activate real-capital execution. "
                "REAL_CAPITAL_ENABLED is permanently False."
            )

    # 2. Exchange venue check
    if exchange:
        ex_clean = exchange.strip().upper()
        if ex_clean in FORBIDDEN_KEYWORDS:
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Exchange venue '{exchange}' targets live/real execution. "
                "REAL_CAPITAL_ENABLED is permanently False. Only paper, testnet, and simulation venues are authorized."
            )

    # 3. Desk check
    if desk:
        desk_clean = desk.strip().upper()
        if desk_clean in FORBIDDEN_KEYWORDS:
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Trading desk '{desk}' targets live/real capital. "
                "REAL_CAPITAL_ENABLED is permanently False. Only sovereign paper and shadow desks are authorized."
            )

    # 4. Mode check
    if mode:
        mode_clean = mode.strip().upper()
        if mode_clean in FORBIDDEN_KEYWORDS:
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Execution mode '{mode}' targets live broker execution. "
                "REAL_CAPITAL_ENABLED is permanently False. Live execution is permanently disabled."
            )

    # 5. Environment whitelist check
    if environment:
        env_clean = environment.strip().upper()
        if env_clean not in ALLOWED_ENVIRONMENTS:
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Environment '{environment}' is not in authorized whitelist: "
                f"{sorted(ALLOWED_ENVIRONMENTS)}. REAL_CAPITAL_ENABLED is permanently False."
            )


def validate_config_isolation(config_dict: dict[str, Any]) -> None:
    """
    Scans a configuration dictionary. Rejects any attempt to set real_capital_enabled=True.
    """
    if not isinstance(config_dict, dict):
        return

    # Check root keys
    for k, v in config_dict.items():
        k_lower = str(k).lower()
        if "real_capital" in k_lower or "live_trading" in k_lower:
            if v is True or str(v).lower() in ("true", "1", "yes"):
                raise ConstitutionalViolationError(
                    f"Constitutional Violation: Configuration key '{k}={v}' attempted to enable real capital. "
                    "REAL_CAPITAL_ENABLED is permanently False."
                )
        if isinstance(v, dict):
            validate_config_isolation(v)
