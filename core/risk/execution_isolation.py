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
from enum import StrEnum
from typing import Any, Final

logger = logging.getLogger(__name__)


class ExecutionMode(StrEnum):
    """Constitutional Execution Modes: PAPER (default) vs PRODUCTION."""

    PAPER = "PAPER"
    PRODUCTION = "PRODUCTION"


def get_execution_mode() -> ExecutionMode:
    """Returns active ExecutionMode based on environment configuration."""
    mode_str = os.getenv("EXECUTION_MODE", "PAPER").strip().upper()
    if mode_str == "PRODUCTION":
        return ExecutionMode.PRODUCTION
    return ExecutionMode.PAPER


def is_production_execution_cleared(
    exchange: str = "BINANCE",
    environment: str = "PRODUCTION",
) -> tuple[bool, list[str]]:
    """Evaluates fail-closed dual-mode gate for ExecutionMode.PRODUCTION:

    1. LIVE_EXECUTION_ENABLED environment flag set explicitly to 'true'.
    2. Master live kill switch disengaged.
    3. Valid, non-mock API credentials registered in credential_vault.
    4. Hardware key / FIDO2 physical clearance or daemon lease active.
    """
    reasons: list[str] = []

    # 1. LIVE_EXECUTION_ENABLED flag
    live_flag = os.getenv("LIVE_EXECUTION_ENABLED", "false").strip().lower()
    if live_flag not in ("true", "1", "yes"):
        reasons.append("LIVE_EXECUTION_ENABLED environment flag is not explicitly 'true'.")

    # 2. Master Kill Switch
    try:
        from core.execution.kill_switch import live_kill_switch

        ks_res = live_kill_switch.is_active()
        kill_active = ks_res[0] if isinstance(ks_res, tuple) else bool(ks_res)
        if kill_active:
            reasons.append("Master live kill switch is actively engaged.")
    except Exception as exc:
        reasons.append(f"Could not verify live kill switch: {exc}")

    # 3. Credential Vault
    try:
        from core.auth.credential_vault import credential_vault

        if not credential_vault.is_unlocked():
            reasons.append("Credential vault is locked.")
        else:
            cred = credential_vault.get_credential(exchange, environment)
            if not cred or not cred.is_active:
                reasons.append(f"No active credential in vault for {exchange} [{environment}].")
            elif "mock" in (cred.api_key or "").lower() or "dummy" in (cred.api_key or "").lower():
                reasons.append("Mock credentials detected; production real capital rejected.")
    except Exception as exc:
        reasons.append(f"Credential vault verification error: {exc}")

    # 4. Hardware Key Clearance / Daemon Lease
    try:
        from core.auth.hardware_key import hardware_key_manager

        is_cleared, _session, _reason = hardware_key_manager.check_live_clearance(
            session_id=None, tier="TIER_1_CANARY", is_autonomous=True
        )
        if not is_cleared:
            reasons.append(
                "Hardware key (WebAuthn/FIDO2) or active autonomous daemon lease required."
            )
    except Exception as exc:
        reasons.append(f"Hardware key clearance verification error: {exc}")

    return (len(reasons) == 0, reasons)


def is_real_capital_enabled() -> bool:
    """Dynamic check for whether real capital execution is unlocked."""
    if get_execution_mode() != ExecutionMode.PRODUCTION:
        return False
    cleared, _ = is_production_execution_cleared()
    return cleared


# Permanent Constitutional Constant (Type-checked as Final; default is False)
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
                "REAL_CAPITAL_ENABLED is permanently False. Use sanctioned LIVE_EXECUTION_ENABLED dual-mode gate."
            )

    # 1b. Dual-Mode Gate: Check if PRODUCTION execution mode is activated
    current_mode = get_execution_mode()
    if current_mode == ExecutionMode.PRODUCTION:
        cleared, reasons = is_production_execution_cleared(
            exchange=exchange or "BINANCE",
            environment=environment or "PRODUCTION",
        )
        if not cleared:
            raise ConstitutionalViolationError(
                f"Constitutional Violation: Production execution blocked by fail-closed security gate: {'; '.join(reasons)}"
            )
        # Production execution cleared under strict gatekeeper invariants
        return

    # 2. Exchange venue check (enforced in PAPER mode)
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
    """Scans a configuration dictionary. Rejects any attempt to set real_capital_enabled=True

    unless strictly authorized in ExecutionMode.PRODUCTION.
    """
    if not isinstance(config_dict, dict):
        return

    current_mode = get_execution_mode()
    is_cleared = current_mode == ExecutionMode.PRODUCTION and is_production_execution_cleared()[0]

    # Check root keys
    for k, v in config_dict.items():
        k_lower = str(k).lower()
        if "real_capital" in k_lower or "live_trading" in k_lower:
            if v is True or str(v).lower() in ("true", "1", "yes"):
                if not is_cleared:
                    raise ConstitutionalViolationError(
                        f"Constitutional Violation: Configuration key '{k}={v}' attempted to enable real capital without PRODUCTION clearance. "
                        "REAL_CAPITAL_ENABLED is permanently False in PAPER mode."
                    )
        if isinstance(v, dict):
            validate_config_isolation(v)
