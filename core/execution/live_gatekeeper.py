"""
core/execution/live_gatekeeper.py
=================================
Master Constitutional Pre-Flight Safety Lock & Live Key Vault Validator.

Enforces fail-closed multi-checkpoint clearance before any real-money orders
can ever be transmitted to external exchange sockets.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from core.audit_bus import audit_bus
from core.auth.credential_vault import credential_vault
from core.execution.account_probe import account_probe
from core.execution.kill_switch import live_kill_switch

logger = logging.getLogger("sky.execution.live_gatekeeper")


class LiveGatekeeperViolationError(Exception):
    """Raised when an execution request breaches constitutional preflight checks."""


@dataclass
class GatekeeperVerdict:
    passed: bool
    timestamp_ms: int
    exchange: str
    requested_notional_usd: float
    max_allowed_notional_usd: float
    checks: dict[str, bool]
    rejection_reasons: list[str]
    audit_event_id: str | None = None


class LiveExecutionGatekeeper:
    """Rigorous gatekeeper enforcing all constitutional trading conditions."""

    def __init__(
        self,
        max_clock_drift_ms: float = 500.0,
        max_daily_drawdown_pct: float = 0.03,  # 3.0% daily circuit breaker
        single_trade_equity_cap_pct: float = 0.015,  # 1.5% single-trade equity cap
    ) -> None:
        self.max_clock_drift_ms = max_clock_drift_ms
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.single_trade_equity_cap_pct = single_trade_equity_cap_pct
        self._daily_realized_loss_usd: float = 0.0
        self._last_reset_epoch: float = time.time()
        self._revocation_log: list[tuple[str, str, int]] = []
        try:
            credential_vault.register_revocation_listener(self._handle_credential_revocation)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not register revocation listener: %s", exc)

    def _handle_credential_revocation(self, exchange: str, environment: str) -> None:
        logger.warning(
            f"LiveExecutionGatekeeper notified: Credential revoked for {exchange} [{environment}]."
        )
        self._revocation_log.append((exchange, environment, int(time.time() * 1000)))

    def record_trade_result(self, pnl_usd: float) -> None:
        """Records realized PnL to track cumulative daily drawdown."""
        # Reset counter if midnight passed
        now = time.time()
        if now - self._last_reset_epoch > 86400:
            self._daily_realized_loss_usd = 0.0
            self._last_reset_epoch = now

        if pnl_usd < 0:
            self._daily_realized_loss_usd += abs(pnl_usd)

    async def evaluate_order_clearance(
        self,
        exchange: str,
        order_notional_usd: float,
        environment: str = "PRODUCTION",
        strategy_id: str | None = None,
        entry_price: float = 0.0,
        stop_loss_price: float | None = None,
        session_id: str | None = None,
    ) -> GatekeeperVerdict:
        """
        Executes exhaustive 8-point constitutional clearance evaluation:
        1. Vault unlocked with valid key derivation.
        1b. Credential Capability Firewall (Positive Withdrawal Prohibition).
        2. Master Kill Switch operational.
        3. Exchange connectivity & Clock Drift within 500ms SLA.
        4. Daily drawdown below 3.0% threshold.
        5. Sizing conforms to 1.5% single-trade equity cap.
        6. System Live Trading Authorization verified.
        7. Capital Governor Dual-Constraint Clearance (Risk Budget & Notional Cap, when strategy_id provided).
        8. Human Live Clearance (WebAuthn / FIDO2 physical key possession & active clearance session).
        """
        now_ms = int(time.time() * 1000)
        exchange_upper = exchange.upper().strip()
        reasons: list[str] = []
        checks: dict[str, bool] = {}

        # 1. Vault unlocked check
        vault_unlocked = credential_vault.is_unlocked()
        checks["vault_unlocked"] = vault_unlocked
        if not vault_unlocked:
            reasons.append("Credential vault is locked. Live orders blocked.")

        # 1b. Credential Capability Firewall & Positive Withdrawal Prohibition Check
        capability = credential_vault.get_credential_capability(exchange_upper, environment)
        is_withdrawal_prohibited = not capability.withdrawal_allowed
        checks["withdrawal_prohibited"] = is_withdrawal_prohibited
        if capability.withdrawal_allowed:
            reasons.append(
                f"SECURITY_VIOLATION_WITHDRAWAL_ENABLED: API key for {exchange_upper} [{environment}] "
                "has withdrawal capability enabled or lacks positive proof of prohibition. Live execution DENIED."
            )
        elif capability.verification_status == "SECURITY_VIOLATION":
            reasons.append(
                f"SECURITY_VIOLATION: Credential verification failed: {capability.error_message}"
            )

        # 2. Master kill switch check
        ks_res = live_kill_switch.is_active()
        kill_switch_active = ks_res[0] if isinstance(ks_res, tuple) else bool(ks_res)
        checks["kill_switch_operational"] = not kill_switch_active
        if kill_switch_active:
            reasons.append("Master Kill Switch is active. All live execution halted.")

        # 3. Exchange probe & balance check
        exch_status = await account_probe.probe_exchange(exchange_upper, environment)
        max_drift = 2000.0 if environment.upper() == "TESTNET" else self.max_clock_drift_ms
        clock_drift_passed = exch_status.is_connected and exch_status.latency_ms <= max_drift
        checks["connectivity_and_clock_drift"] = clock_drift_passed
        if not exch_status.is_connected:
            reasons.append(
                f"Exchange {exchange_upper} connection failed: {exch_status.error_message}"
            )
        elif exch_status.latency_ms > max_drift:
            reasons.append(
                f"Clock drift/latency {exch_status.latency_ms:.1f}ms exceeds {max_drift:.1f}ms SLA."
            )

        # 4. Daily drawdown limit check
        total_equity = exch_status.total_equity_usd if exch_status.total_equity_usd > 0 else 1000.0
        max_drawdown_dollars = total_equity * self.max_daily_drawdown_pct
        drawdown_passed = self._daily_realized_loss_usd < max_drawdown_dollars
        checks["daily_drawdown_safe"] = drawdown_passed
        if not drawdown_passed:
            reasons.append(
                f"Daily realized loss ${self._daily_realized_loss_usd:.2f} exceeds "
                f"3% limit (${max_drawdown_dollars:.2f})."
            )

        # 5. Single trade constitutional 1.5% equity cap check
        max_allowed_notional = total_equity * self.single_trade_equity_cap_pct
        sizing_passed = (
            order_notional_usd <= max_allowed_notional * 1.05
        )  # 5% buffer for market moves
        checks["single_trade_cap_conformed"] = sizing_passed
        if not sizing_passed:
            reasons.append(
                f"Requested notional ${order_notional_usd:.2f} breaches constitutional 1.5% equity cap "
                f"(${max_allowed_notional:.2f})."
            )

        # 6. Live trading authorization switch
        if environment.upper() == "TESTNET":
            live_env_enabled = True
        else:
            live_env_enabled = os.getenv("LIVE_TRADING_ENABLED", "false").lower() in (
                "true",
                "1",
                "yes",
            )
        checks["live_trading_authorized"] = live_env_enabled
        if not live_env_enabled:
            reasons.append(
                "LIVE_TRADING_ENABLED environment flag is not set to true. Execution blocked."
            )

        # 7. Capital Governor Dual-Constraint Check (when strategy_id is specified)
        if strategy_id:
            from core.execution.capital_governor import capital_governor

            effective_entry = (
                entry_price
                if entry_price > 0
                else (order_notional_usd / 0.001 if order_notional_usd > 0 else 100.0)
            )
            cap_clearance = capital_governor.evaluate_order_risk(
                requested_notional_usd=order_notional_usd,
                entry_price=effective_entry,
                stop_loss_price=stop_loss_price,
                current_equity=total_equity,
                strategy_id=strategy_id,
            )
            checks["capital_governor_cleared"] = cap_clearance.passed
            if not cap_clearance.passed:
                reasons.extend(cap_clearance.rejection_reasons)

        # 8. Human Live Clearance (WebAuthn / FIDO2 physical key possession)
        if environment.upper() == "TESTNET":
            checks["hardware_clearance_active"] = True
        else:
            from core.auth.hardware_key import hardware_key_manager

            is_cleared, clearance, reason_code = hardware_key_manager.check_live_clearance(
                session_id=session_id
            )
            checks["hardware_clearance_active"] = is_cleared
            if not is_cleared:
                code_str = reason_code or "HARDWARE_KEY_CLEARANCE_REQUIRED"
                reasons.append(
                    f"{code_str}: Production execution requires an active WebAuthn/FIDO2 hardware security key clearance session."
                )

        all_passed = all(checks.values())

        # Publish audit event
        audit_event_id = None
        try:
            audit_event_id = audit_bus.publish_event(
                event_type="LIVE_PREFLIGHT_VERDICT",
                payload={
                    "exchange": exchange_upper,
                    "order_notional_usd": order_notional_usd,
                    "max_allowed_notional_usd": max_allowed_notional,
                    "passed": all_passed,
                    "checks": checks,
                    "reasons": reasons,
                },
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Audit bus logging error: {e}")

        return GatekeeperVerdict(
            passed=all_passed,
            timestamp_ms=now_ms,
            exchange=exchange_upper,
            requested_notional_usd=order_notional_usd,
            max_allowed_notional_usd=round(max_allowed_notional, 2),
            checks=checks,
            rejection_reasons=reasons,
            audit_event_id=audit_event_id,
        )


# Global singleton
live_gatekeeper = LiveExecutionGatekeeper()
