"""
core/incident_escalation.py
===========================
Autonomous 4-Tier Incident Escalation & Emergency Protection Engine.

Implements Phase 16.3 of the SKY Quantitative Platform:
- 4-Tier Escalation Matrix: NOTICE, WARNING, CRITICAL, EMERGENCY.
- Autonomous Tier 4 Emergency Auto-Halt (local safety first, does NOT depend on Telegram).
- Idempotent Emergency Halt (single coherent halt state, zero storming).
- Signed 2-Phase HMAC-SHA256 Operator Confirmation Tokens with replay defense.
- Liquidity Evaporation Detector (baseline-referenced withdrawal ratio).
- CUSUM Expectancy Drift Sentinel integration (Z > 2.5 sigma).
- Multi-channel notification dispatch with graceful degradation.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.api_health_guard import api_health_guard
from core.audit_bus import audit_bus
from core.autonomous_auditor import autonomous_risk_auditor
from core.autonomous_trader import autonomous_trader
from core.database import db_manager
from core.shadow_burn_in_orchestrator import (
    ExecutionMode,
    OrchestratorState,
    shadow_burn_in_orchestrator,
)

logger = logging.getLogger("sky.incident_escalation")

TOKEN_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "sky_phase16_incident_hmac_secret")
DEFAULT_TOKEN_EXPIRY_SEC = 60.0


class IncidentTier:
    NOTICE = "NOTICE"  # Tier 1: Logged to audit bus only
    WARNING = "WARNING"  # Tier 2: Dispatched to Sentinel Telegram
    CRITICAL = "CRITICAL"  # Tier 3: High-priority Telegram + 2-Phase Confirmation required
    EMERGENCY = "EMERGENCY"  # Tier 4: Autonomous Auto-Halt + READ_ONLY + Telegram ADMIN page


@dataclass
class IncidentRecord:
    incident_id: str
    timestamp: int
    tier: str
    severity: str
    source_engine: str
    trigger_type: str
    trigger_value: float
    threshold_value: float
    description: str
    automated_action: str
    operator_action: str | None = None
    confirmation_required: bool = False
    confirmation_status: str = "NONE"  # "NONE", "PENDING", "CONFIRMED", "REJECTED", "EXPIRED"
    nonce: str | None = None
    token_hash: str | None = None
    issued_at: int | None = None
    expires_at: int | None = None
    resolved: bool = False
    resolved_at: int | None = None
    resolved_by: str | None = None
    execution_mode: str = ExecutionMode.SHADOW
    metadata_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IncidentEscalationEngine:
    """
    Central incident supervisor, chaos responder, and emergency circuit breaker.
    """

    def __init__(
        self,
        daily_loss_limit_pct: float = 5.0,
        cusum_drift_threshold: float = 2.5,
        min_disk_free_gb: float = 1.0,
        liquidity_withdrawal_threshold: float = 0.70,
    ):
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.cusum_drift_threshold = cusum_drift_threshold
        self.min_disk_free_gb = min_disk_free_gb
        self.liquidity_withdrawal_threshold = liquidity_withdrawal_threshold

        self._active_incidents: dict[str, IncidentRecord] = {}
        self._consumed_nonces: set[str] = set()
        self._is_emergency_halted: bool = False
        self._halt_lock = asyncio.Lock()
        self._depth_baselines: dict[str, list[float]] = {}  # rolling depth for liquidity anomaly
        self._background_tasks: set[asyncio.Task] = set()

    # -------------------------------------------------------------------------
    # 1. HMAC Token Generator & 2-Phase Confirmation Engine
    # -------------------------------------------------------------------------

    def create_confirmation_token(
        self, incident_id: str, action: str, operator_id: str = "ADMIN"
    ) -> dict[str, Any]:
        """
        Creates a single-use cryptographically signed HMAC token for 2-Phase operator confirmation.
        """
        now = time.time()
        nonce = uuid.uuid4().hex
        expires_at = now + DEFAULT_TOKEN_EXPIRY_SEC

        message = f"{incident_id}:{action}:{nonce}:{operator_id}:{int(expires_at)}"
        sig = hmac.new(
            TOKEN_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return {
            "incident_id": incident_id,
            "action": action,
            "operator_id": operator_id,
            "nonce": nonce,
            "issued_at": int(now * 1000),
            "expires_at": int(expires_at * 1000),
            "token_signature": sig,
        }

    def verify_and_consume_token(
        self,
        incident_id: str,
        action: str,
        nonce: str,
        expires_at_ms: int,
        token_signature: str,
        operator_id: str = "ADMIN",
    ) -> tuple[bool, str]:
        """
        Verifies HMAC signature, constant-time comparison, expiry, and single-use nonce.
        """
        now_ms = int(time.time() * 1000)

        # 1. Check Expiry
        if now_ms > expires_at_ms:
            return False, "TOKEN_EXPIRED"

        # 2. Check Replay Attack
        if nonce in self._consumed_nonces:
            return False, "TOKEN_ALREADY_CONSUMED_REPLAY_ATTACK"

        # 3. Verify Cryptographic HMAC Signature in Constant Time
        expires_at_sec = int(expires_at_ms / 1000)
        message = f"{incident_id}:{action}:{nonce}:{operator_id}:{expires_at_sec}"
        expected_sig = hmac.new(
            TOKEN_SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(token_signature, expected_sig):
            return False, "INVALID_HMAC_SIGNATURE"

        # Consume nonce
        self._consumed_nonces.add(nonce)
        return True, "VERIFIED_VALID"

    # -------------------------------------------------------------------------
    # 2. Multi-Tier Escalation Dispatcher
    # -------------------------------------------------------------------------

    async def raise_incident(
        self,
        tier: str,
        source_engine: str,
        trigger_type: str,
        trigger_value: float,
        threshold_value: float,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> IncidentRecord:
        """
        Main incident intake pipeline. Executes appropriate tier actions deterministically.
        """
        now_ms = int(time.time() * 1000)
        inc_id = f"INC_{tier}_{int(now_ms)}_{uuid.uuid4().hex[:6]}"
        meta_dict = metadata or {}
        meta_json = json.dumps(meta_dict)

        action_taken = "LOGGED"
        conf_required = False
        token_info = {}

        if tier == IncidentTier.NOTICE:
            action_taken = "LOGGED_TO_AUDIT_BUS"

        elif tier == IncidentTier.WARNING:
            action_taken = "TELEGRAM_SENTINEL_ALERT"
            await self._dispatch_telegram_alert(tier, description, inc_id)

        elif tier == IncidentTier.CRITICAL:
            action_taken = "2PHASE_CONFIRMATION_REQUESTED"
            conf_required = True
            token_info = self.create_confirmation_token(inc_id, "QUARANTINE_STRATEGY")
            await self._dispatch_telegram_alert(
                tier,
                f"{description}\nAction Required: 2-Phase Confirmation Token Generated",
                inc_id,
                token_info,
            )

        elif tier == IncidentTier.EMERGENCY:
            # TIER 4: LOCAL AUTONOMOUS SAFETY ACTION FIRST
            action_taken = await self.execute_emergency_auto_halt(
                reason=description, incident_id=inc_id
            )
            # Best-effort notification second
            await self._dispatch_telegram_alert(
                tier, f"🚨 EMERGENCY AUTO-HALT EXECUTED: {description}", inc_id
            )

        record = IncidentRecord(
            incident_id=inc_id,
            timestamp=now_ms,
            tier=tier,
            severity=tier,
            source_engine=source_engine,
            trigger_type=trigger_type,
            trigger_value=round(trigger_value, 4),
            threshold_value=round(threshold_value, 4),
            description=description,
            automated_action=action_taken,
            confirmation_required=conf_required,
            confirmation_status="PENDING" if conf_required else "NONE",
            nonce=token_info.get("nonce"),
            token_hash=token_info.get("token_signature"),
            issued_at=token_info.get("issued_at"),
            expires_at=token_info.get("expires_at"),
            execution_mode=shadow_burn_in_orchestrator.execution_mode,
            metadata_json=meta_json,
        )

        self._active_incidents[inc_id] = record
        self._persist_incident(record)

        audit_bus.emit_event(
            event_type=f"INCIDENT_{tier}",
            symbol="SYSTEM",
            reason=f"[{tier}] {source_engine}: {trigger_type} ({trigger_value:.2f} >= {threshold_value:.2f})",
            severity="CRITICAL"
            if tier in (IncidentTier.CRITICAL, IncidentTier.EMERGENCY)
            else "WARNING",
            details=record.to_dict(),
        )

        return record

    # -------------------------------------------------------------------------
    # 3. Tier 4 Autonomous Emergency Auto-Halt (Idempotent)
    # -------------------------------------------------------------------------

    async def execute_emergency_auto_halt(self, reason: str, incident_id: str) -> str:
        """
        Executes immediate, deterministic, idempotent system halt.
        Shuts down AutonomousTrader, sets orchestrator to HALTED -> READ_ONLY,
        and ensures NO duplicate execution storms occur.
        """
        async with self._halt_lock:
            if self._is_emergency_halted:
                logger.info(f"Emergency halt already active (Idempotent bypass for {incident_id}).")
                return "ALREADY_HALTED_IDEMPOTENT"

            self._is_emergency_halted = True
            logger.critical(
                f"Executing Tier 4 EMERGENCY AUTO-HALT: {reason} [Incident: {incident_id}]"
            )

            # 1. Stop Autonomous Trader Loop
            autonomous_trader.stop()

            # 2. Transition Burn-In Orchestrator to HALTED and then READ_ONLY
            shadow_burn_in_orchestrator.transition_to(
                OrchestratorState.HALTING, f"Emergency halt: {reason}"
            )
            shadow_burn_in_orchestrator.transition_to(
                OrchestratorState.HALTED, f"Trader stopped: {reason}"
            )
            shadow_burn_in_orchestrator.transition_to(
                OrchestratorState.READ_ONLY, "System quarantined to READ_ONLY"
            )

            # 3. Shadow Execution Isolation Guarantee
            # In SHADOW mode: close virtual positions or lock from opening new trades
            if shadow_burn_in_orchestrator.execution_mode == ExecutionMode.SHADOW:
                logger.info(
                    "Emergency Halt: SHADOW mode active. Virtual paper execution frozen. No real broker orders touched."
                )
            else:
                logger.warning("Emergency Halt: LIVE mode active. Emergency protocol dispatched.")

            return "EMERGENCY_AUTO_HALT_COMPLETE_READ_ONLY"

    def reset_emergency_halt(self, operator_note: str) -> bool:
        """Allows authorized operator recovery from emergency halt."""
        self._is_emergency_halted = False
        return shadow_burn_in_orchestrator.recover_from_halt(operator_note)

    # -------------------------------------------------------------------------
    # 4. Specific Automated Health Sentinels
    # -------------------------------------------------------------------------

    async def check_cusum_drift(self) -> IncidentRecord | None:
        """Evaluates CUSUM expectancy drift from AutonomousRiskAuditor."""
        audit_report = autonomous_risk_auditor.audit_system_health()
        z_score = audit_report.cusum_drift_score

        if z_score >= self.cusum_drift_threshold:
            return await self.raise_incident(
                tier=IncidentTier.CRITICAL,
                source_engine="CUSUM_DRIFT_AUDITOR",
                trigger_type="EXPECTANCY_COLLAPSE",
                trigger_value=z_score,
                threshold_value=self.cusum_drift_threshold,
                description=f"Expectancy drift Z-score ({z_score:.2f} sigma) breached threshold ({self.cusum_drift_threshold:.2f} sigma).",
                metadata=audit_report.to_dict(),
            )
        return None

    async def check_disk_capacity(self) -> IncidentRecord | None:
        """Evaluates host disk capacity via APIHealthGuard."""
        vitals = api_health_guard.check_disk_space(min_free_gb=self.min_disk_free_gb)
        free_gb = vitals.get("free_gb", 100.0)

        if free_gb < self.min_disk_free_gb:
            return await self.raise_incident(
                tier=IncidentTier.EMERGENCY,
                source_engine="API_HEALTH_GUARD",
                trigger_type="LOW_DISK_SPACE_CIRCUIT_BREAKER",
                trigger_value=free_gb,
                threshold_value=self.min_disk_free_gb,
                description=f"Host free disk space ({free_gb:.2f} GB) fell below emergency limit ({self.min_disk_free_gb:.2f} GB).",
                metadata=vitals,
            )
        return None

    async def evaluate_liquidity_anomaly(
        self, symbol: str, current_l2_depth: float
    ) -> IncidentRecord | None:
        """
        Evaluates liquidity evaporation relative to rolling depth baseline.
        Requires >= 10 baseline observations to prevent false alarms.
        """
        depths = self._depth_baselines.setdefault(symbol, [])
        depths.append(current_l2_depth)
        if len(depths) > 50:
            depths.pop(0)

        if len(depths) < 10:
            return None

        baseline = sum(depths[:-1]) / len(depths[:-1])
        if baseline <= 1.0:
            return None

        withdrawal_ratio = 1.0 - (current_l2_depth / baseline)
        if withdrawal_ratio >= self.liquidity_withdrawal_threshold:
            return await self.raise_incident(
                tier=IncidentTier.CRITICAL,
                source_engine="LIQUIDITY_EVAPORATION_SENTINEL",
                trigger_type="ANOMALOUS_DEPTH_WITHDRAWAL",
                trigger_value=withdrawal_ratio,
                threshold_value=self.liquidity_withdrawal_threshold,
                description=f"Sudden {withdrawal_ratio * 100.0:.1f}% liquidity withdrawal detected on {symbol} (Depth: {current_l2_depth:.2f} vs Baseline: {baseline:.2f}).",
                metadata={
                    "symbol": symbol,
                    "current_depth": current_l2_depth,
                    "baseline": baseline,
                },
            )
        return None

    # -------------------------------------------------------------------------
    # 5. Telegram Notification & Best-Effort Dispatch
    # -------------------------------------------------------------------------

    async def _dispatch_telegram_alert(
        self,
        tier: str,
        message: str,
        incident_id: str,
        token_info: dict[str, Any] | None = None,
    ) -> bool:
        """
        Best-effort asynchronous dispatch to Telegram.
        If Telegram fails or times out, safety actions remain unaffected.
        """
        try:
            from core.telegram_bot import telegram_bot

            alert_text = f"🚨 *SKY INCIDENT [{tier}]*\n\n{message}\n\n`Incident ID: {incident_id}`"
            if token_info:
                alert_text += f"\n`Nonce: {token_info.get('nonce')}`\n`Expiry: 60s`"
            # Asynchronously send without blocking
            alert_task = asyncio.create_task(telegram_bot.broadcast_trade_alert(alert_text))
            self._background_tasks.add(alert_task)
            alert_task.add_done_callback(self._background_tasks.discard)
            return True
        except Exception as ex:
            logger.debug(f"Telegram alert delivery skipped (safe degradation): {ex}")
            return False

    # -------------------------------------------------------------------------
    # 6. Persistence & Query API
    # -------------------------------------------------------------------------

    def _persist_incident(self, rec: IncidentRecord) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO incident_escalations (
                        id, incident_id, timestamp, tier, severity, source_engine,
                        trigger_type, trigger_value, threshold_value, description,
                        automated_action, operator_action, confirmation_required,
                        confirmation_status, nonce, token_hash, issued_at, expires_at,
                        resolved, execution_mode, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, CURRENT_TIMESTAMP);
                    """,
                    (
                        rec.incident_id,
                        rec.incident_id,
                        rec.timestamp,
                        rec.tier,
                        rec.severity,
                        rec.source_engine,
                        rec.trigger_type,
                        rec.trigger_value,
                        rec.threshold_value,
                        rec.description,
                        rec.automated_action,
                        rec.operator_action,
                        1 if rec.confirmation_required else 0,
                        rec.confirmation_status,
                        rec.nonce,
                        rec.token_hash,
                        rec.issued_at,
                        rec.expires_at,
                        rec.execution_mode,
                        rec.metadata_json,
                    ),
                )
                conn.commit()
        except Exception as ex:
            logger.error(f"Failed to persist incident {rec.incident_id}: {ex}")

    def resolve_incident(self, incident_id: str, operator_id: str, notes: str = "") -> bool:
        """Marks an active incident as resolved."""
        now_ms = int(time.time() * 1000)
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    UPDATE incident_escalations SET
                        resolved = 1,
                        resolved_at = ?,
                        resolved_by = ?,
                        operator_action = ?
                    WHERE incident_id = ?;
                    """,
                    (now_ms, operator_id, notes, incident_id),
                )
                conn.commit()

            if incident_id in self._active_incidents:
                rec = self._active_incidents[incident_id]
                rec.resolved = True
                rec.resolved_at = now_ms
                rec.resolved_by = operator_id
                rec.operator_action = notes

            audit_bus.emit_event(
                event_type="INCIDENT_RESOLVED",
                symbol="SYSTEM",
                reason=f"Incident {incident_id} resolved by {operator_id}: {notes}",
                severity="INFO",
                details={"incident_id": incident_id, "resolved_by": operator_id},
            )
            return True
        except Exception as ex:
            logger.error(f"Failed to resolve incident {incident_id}: {ex}")
            return False

    def get_incidents(self, limit: int = 50, unresolved_only: bool = False) -> list[dict[str, Any]]:
        with db_manager.get_trading_conn() as conn:
            query = "SELECT * FROM incident_escalations "
            if unresolved_only:
                query += "WHERE resolved = 0 "
            query += "ORDER BY timestamp DESC LIMIT ?;"
            cursor = conn.execute(query, (limit,))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Master Singleton
incident_escalation_engine = IncidentEscalationEngine()
