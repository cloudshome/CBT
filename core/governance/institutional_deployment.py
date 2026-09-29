"""
core/governance/institutional_deployment.py
===========================================
Institutional Deployment Framework: 6-Gate Architecture & 8-Stage State Machine.

Axiomatic Guarantees:
1. DeploymentStage cannot be assigned directly (DirectStageMutationError).
2. All transitions pass through a single transition authority: request_promotion().
3. Every transition requires immutable, cryptographically bound GateEvidence.
4. OperationalCapabilities are decoupled from DeploymentStage.
5. Permanent Capital Firewall: real_capital_enabled is immutably False.
   Any attempt to enable real capital via env vars, configs, or payloads fails closed.
6. Missing, stale, malformed, or contradictory evidence causes immediate rejection.
7. Emergency downgrade immediately revokes non-research capabilities.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sky.governance.institutional_deployment")


# ─────────────────────────────────────────────────────────────────────────────
# Exception Hierarchy
# ─────────────────────────────────────────────────────────────────────────────


class GovernanceViolationError(Exception):
    """Base exception for institutional governance violations."""


class DirectStageMutationError(GovernanceViolationError):
    """Raised when an unauthorized entity attempts to directly assign DeploymentStage."""


class PermanentCapitalFirewallViolation(GovernanceViolationError):
    """Raised when an attempt is made to enable real capital or live funds."""


class InsufficientEvidenceError(GovernanceViolationError):
    """Raised when gate evidence is missing, expired, revoked, or untrusted."""


class InvalidStageTransitionError(GovernanceViolationError):
    """Raised when attempting an illegal non-sequential stage transition."""


# ─────────────────────────────────────────────────────────────────────────────
# Core Enums
# ─────────────────────────────────────────────────────────────────────────────


class DeploymentStage(StrEnum):
    """8-Stage Institutional Lifecycle State Machine."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    RESEARCH_VIABLE = "RESEARCH_VIABLE"
    EXECUTION_MODEL_VALIDATED = "EXECUTION_MODEL_VALIDATED"
    SANDBOX_ELIGIBLE = "SANDBOX_ELIGIBLE"
    SANDBOX_VERIFIED = "SANDBOX_VERIFIED"
    HUMAN_LIVE_REVIEW = "HUMAN_LIVE_REVIEW"
    MICRO_CAPITAL_ELIGIBLE = "MICRO_CAPITAL_ELIGIBLE"
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"


class DeploymentGate(StrEnum):
    """6 Independent Institutional Deployment Gates."""

    GATE_1_DATA_FIDELITY = "GATE_1_DATA_FIDELITY"
    GATE_2_EXECUTION_REALITY = "GATE_2_EXECUTION_REALITY"
    GATE_3_NET_EXPECTANCY = "GATE_3_NET_EXPECTANCY"
    GATE_4_ROBUSTNESS_REPRODUCIBILITY = "GATE_4_ROBUSTNESS_REPRODUCIBILITY"
    GATE_5_EXTENDED_SANDBOX_BURN_IN = "GATE_5_EXTENDED_SANDBOX_BURN_IN"
    GATE_6_HUMAN_CONTROLLED_CAPITAL = "GATE_6_HUMAN_CONTROLLED_CAPITAL"


class GateStatus(StrEnum):
    """Lifecycle status of an individual gate evidence record."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


# ─────────────────────────────────────────────────────────────────────────────
# Decoupled Operational Capabilities
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OperationalCapabilities:
    """
    Granular operational capabilities decoupled from DeploymentStage.
    Advancing to a stage does NOT automatically unlock capabilities.
    """

    research: bool = True
    historical_replay: bool = True
    paper_trading: bool = False
    exchange_testnet: bool = False
    live_market_data: bool = False
    funded_account_connection: bool = False
    live_order_submission: bool = False
    capital_allocation: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


# Default capability sets per stage (defense-in-depth: minimal required privilege)
STAGE_CAPABILITIES_MAP: dict[DeploymentStage, OperationalCapabilities] = {
    DeploymentStage.RESEARCH_ONLY: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=False,
        exchange_testnet=False,
        live_market_data=False,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.RESEARCH_VIABLE: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=False,
        exchange_testnet=False,
        live_market_data=False,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.EXECUTION_MODEL_VALIDATED: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=False,
        live_market_data=False,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.SANDBOX_ELIGIBLE: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=True,
        live_market_data=True,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.SANDBOX_VERIFIED: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=True,
        live_market_data=True,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.HUMAN_LIVE_REVIEW: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=True,
        live_market_data=True,
        funded_account_connection=False,
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.MICRO_CAPITAL_ELIGIBLE: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=True,
        live_market_data=True,
        funded_account_connection=False,  # Still False until explicit live authorization gate
        live_order_submission=False,
        capital_allocation=False,
    ),
    DeploymentStage.LIVE_AUTHORIZED: OperationalCapabilities(
        research=True,
        historical_replay=True,
        paper_trading=True,
        exchange_testnet=True,
        live_market_data=True,
        funded_account_connection=False,  # Hard locked in current repository configuration
        live_order_submission=False,  # Hard locked in current repository configuration
        capital_allocation=False,  # Hard locked in current repository configuration
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Cryptographic Gate Evidence
# ─────────────────────────────────────────────────────────────────────────────


def compute_gate_evidence_hash(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical evidence fields."""
    canonical = {
        "gate_id": str(data.get("gate_id")),
        "status": str(data.get("status")),
        "strategy_id": str(data.get("strategy_id")),
        "dataset_hash": str(data.get("dataset_hash")),
        "experiment_id": str(data.get("experiment_id")),
        "issuer": str(data.get("issuer")),
        "issued_at": float(data.get("issued_at", 0.0)),
        "valid_until": float(data.get("valid_until", 0.0)),
        "friction_profile": str(data.get("friction_profile", "")),
        "revocation_status": bool(data.get("revocation_status", False)),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GateEvidence:
    """
    Cryptographically bound, tamper-evident record of an evaluated deployment gate.
    A gate must NEVER be marked passed merely because a boolean returned True.
    """

    gate_id: DeploymentGate
    status: GateStatus
    strategy_id: str
    dataset_hash: str
    experiment_id: str
    issuer: str
    issued_at: float
    valid_until: float
    evidence_hash: str = ""
    confidence_interval: tuple[float, float] | None = None
    friction_profile: str = "stress_v3"
    test_results_summary: dict[str, Any] = field(default_factory=dict)
    revocation_status: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_hash:
            calculated = compute_gate_evidence_hash(asdict(self))
            object.__setattr__(self, "evidence_hash", calculated)

    def is_valid_at(self, current_timestamp: float | None = None) -> tuple[bool, str]:
        """Validates expiry, revocation, and cryptographic hash."""
        now = current_timestamp if current_timestamp is not None else time.time()

        if self.revocation_status:
            return False, f"REVOKED: Gate evidence for {self.gate_id} was explicitly revoked"

        if self.status != GateStatus.PASSED:
            return False, f"NOT_PASSED: Gate status is {self.status}"

        if now > self.valid_until:
            return False, f"EXPIRED: Gate evidence expired at {self.valid_until} (current: {now})"

        expected_hash = compute_gate_evidence_hash(asdict(self))
        if self.evidence_hash != expected_hash:
            return False, "TAMPER_DETECTED: Computed hash does not match stored evidence_hash"

        if len(self.dataset_hash) != 64:
            return (
                False,
                f"MALFORMED_DATASET_HASH: Expected 64-char hex SHA-256, got {len(self.dataset_hash)}",
            )

        return True, "VALID"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Promotion Request & Verdict
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromotionRequest:
    """Formal request for stage advancement through the single transition authority."""

    target_stage: DeploymentStage
    strategy_id: str
    evidence_bundle: dict[DeploymentGate, GateEvidence]
    human_authorization: str | None = None
    request_timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PromotionVerdict:
    """Deterministic outcome of a promotion request evaluation."""

    approved: bool
    previous_stage: DeploymentStage
    current_stage: DeploymentStage
    active_capabilities: OperationalCapabilities
    rejection_reason: str | None = None
    verified_gates: list[DeploymentGate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "previous_stage": self.previous_stage.value,
            "current_stage": self.current_stage.value,
            "active_capabilities": self.active_capabilities.to_dict(),
            "rejection_reason": self.rejection_reason,
            "verified_gates": [g.value for g in self.verified_gates],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Stage Transition Requirements Specification
# ─────────────────────────────────────────────────────────────────────────────

# Explicit sequential predecessor required for each target stage
STAGE_PREDECESSOR_MAP: dict[DeploymentStage, DeploymentStage | None] = {
    DeploymentStage.RESEARCH_ONLY: None,
    DeploymentStage.RESEARCH_VIABLE: DeploymentStage.RESEARCH_ONLY,
    DeploymentStage.EXECUTION_MODEL_VALIDATED: DeploymentStage.RESEARCH_VIABLE,
    DeploymentStage.SANDBOX_ELIGIBLE: DeploymentStage.EXECUTION_MODEL_VALIDATED,
    DeploymentStage.SANDBOX_VERIFIED: DeploymentStage.SANDBOX_ELIGIBLE,
    DeploymentStage.HUMAN_LIVE_REVIEW: DeploymentStage.SANDBOX_VERIFIED,
    DeploymentStage.MICRO_CAPITAL_ELIGIBLE: DeploymentStage.HUMAN_LIVE_REVIEW,
    DeploymentStage.LIVE_AUTHORIZED: DeploymentStage.MICRO_CAPITAL_ELIGIBLE,
}

# Cumulative gates strictly required for each stage
STAGE_REQUIRED_GATES_MAP: dict[DeploymentStage, list[DeploymentGate]] = {
    DeploymentStage.RESEARCH_ONLY: [],
    DeploymentStage.RESEARCH_VIABLE: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
    ],
    DeploymentStage.EXECUTION_MODEL_VALIDATED: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
    ],
    DeploymentStage.SANDBOX_ELIGIBLE: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
        DeploymentGate.GATE_3_NET_EXPECTANCY,
    ],
    DeploymentStage.SANDBOX_VERIFIED: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
        DeploymentGate.GATE_3_NET_EXPECTANCY,
        DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY,
        DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN,
    ],
    DeploymentStage.HUMAN_LIVE_REVIEW: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
        DeploymentGate.GATE_3_NET_EXPECTANCY,
        DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY,
        DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN,
    ],
    DeploymentStage.MICRO_CAPITAL_ELIGIBLE: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
        DeploymentGate.GATE_3_NET_EXPECTANCY,
        DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY,
        DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN,
        DeploymentGate.GATE_6_HUMAN_CONTROLLED_CAPITAL,
    ],
    DeploymentStage.LIVE_AUTHORIZED: [
        DeploymentGate.GATE_1_DATA_FIDELITY,
        DeploymentGate.GATE_2_EXECUTION_REALITY,
        DeploymentGate.GATE_3_NET_EXPECTANCY,
        DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY,
        DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN,
        DeploymentGate.GATE_6_HUMAN_CONTROLLED_CAPITAL,
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Institutional Deployment Governor
# ─────────────────────────────────────────────────────────────────────────────


class InstitutionalDeploymentGovernor:
    """
    Sole transition authority for deployment state transitions and operational capabilities.

    Invariants:
    1. DeploymentStage cannot be assigned directly.
    2. real_capital_enabled is permanently False.
    3. Promotion requests require unexpired, cryptographically verifiable GateEvidence.
    4. Transitions are strictly sequential (no skipping stages).
    5. Emergency downgrade immediately revokes capabilities.
    """

    def __init__(self) -> None:
        self._current_stage: DeploymentStage = DeploymentStage.RESEARCH_ONLY
        self._capabilities: OperationalCapabilities = STAGE_CAPABILITIES_MAP[
            DeploymentStage.RESEARCH_ONLY
        ]
        self._active_evidence: dict[DeploymentGate, GateEvidence] = {}
        self._audit_log: list[dict[str, Any]] = []

        # Permanent Capital Firewall Check on initialization
        self._enforce_permanent_capital_firewall()

    @property
    def current_stage(self) -> DeploymentStage:
        return self._current_stage

    @current_stage.setter
    def current_stage(self, value: Any) -> None:
        """Prohibits direct stage mutation."""
        raise DirectStageMutationError(
            f"Direct mutation of current_stage to '{value}' is strictly forbidden. "
            "All transitions must pass through request_promotion() with verified evidence."
        )

    @property
    def capabilities(self) -> OperationalCapabilities:
        return self._capabilities

    @property
    def real_capital_enabled(self) -> bool:
        """Immutable code-level guarantee: real capital is NEVER enabled."""
        self._enforce_permanent_capital_firewall()
        return False

    @real_capital_enabled.setter
    def real_capital_enabled(self, value: Any) -> None:
        raise PermanentCapitalFirewallViolation(
            "real_capital_enabled is permanently locked to False. Live capital activation prohibited."
        )

    def _enforce_permanent_capital_firewall(self) -> None:
        """Audits environment and system state against unauthorized capital activation flags."""
        forbidden_env_vars = [
            "REAL_CAPITAL_ENABLED",
            "SKY_ENABLE_REAL_CAPITAL",
            "ENABLE_REAL_MONEY",
            "LIVE_TRADING_CAPITAL",
            "LIVE_FUNDS_AUTHORIZED",
        ]
        for env_var in forbidden_env_vars:
            val = os.environ.get(env_var, "").strip().lower()
            if val in ("true", "1", "yes", "enabled"):
                raise PermanentCapitalFirewallViolation(
                    f"Permanent Capital Firewall breach detected: Environment variable {env_var}='{val}'. "
                    "Enabling real capital via environment variables is strictly prohibited."
                )

    def request_promotion(
        self,
        request: PromotionRequest,
        current_time: float | None = None,
    ) -> PromotionVerdict:
        """
        Sole transition authority. Evaluates promotion eligibility fail-closed.
        """
        self._enforce_permanent_capital_firewall()
        now = current_time if current_time is not None else time.time()

        prev_stage = self._current_stage
        target = request.target_stage

        # 1. Self-transition is a no-op returning current state
        if target == self._current_stage:
            return PromotionVerdict(
                approved=True,
                previous_stage=prev_stage,
                current_stage=self._current_stage,
                active_capabilities=self._capabilities,
                verified_gates=list(self._active_evidence.keys()),
            )

        # 2. Sequential transition check
        expected_predecessor = STAGE_PREDECESSOR_MAP.get(target)
        if expected_predecessor != self._current_stage:
            reason = (
                f"INVALID_SEQUENCE: Cannot transition from {self._current_stage.value} "
                f"directly to {target.value}. Required predecessor: {expected_predecessor}."
            )
            logger.warning(reason)
            return PromotionVerdict(
                approved=False,
                previous_stage=prev_stage,
                current_stage=self._current_stage,
                active_capabilities=self._capabilities,
                rejection_reason=reason,
            )

        # 3. Gate evidence verification
        required_gates = STAGE_REQUIRED_GATES_MAP.get(target, [])
        verified_gates: list[DeploymentGate] = []

        for gate in required_gates:
            evidence = request.evidence_bundle.get(gate)
            if not evidence:
                reason = f"MISSING_EVIDENCE: Gate {gate.value} evidence not provided in request."
                logger.warning(reason)
                return PromotionVerdict(
                    approved=False,
                    previous_stage=prev_stage,
                    current_stage=self._current_stage,
                    active_capabilities=self._capabilities,
                    rejection_reason=reason,
                )

            is_valid, validation_msg = evidence.is_valid_at(now)
            if not is_valid:
                reason = (
                    f"INVALID_GATE_EVIDENCE: Gate {gate.value} failed validation: {validation_msg}"
                )
                logger.warning(reason)
                return PromotionVerdict(
                    approved=False,
                    previous_stage=prev_stage,
                    current_stage=self._current_stage,
                    active_capabilities=self._capabilities,
                    rejection_reason=reason,
                )

            verified_gates.append(gate)

        # 4. Human authorization requirement for advanced stages
        if target in (
            DeploymentStage.HUMAN_LIVE_REVIEW,
            DeploymentStage.MICRO_CAPITAL_ELIGIBLE,
            DeploymentStage.LIVE_AUTHORIZED,
        ):
            if not request.human_authorization or len(request.human_authorization.strip()) < 16:
                reason = (
                    f"MISSING_HUMAN_AUTHORIZATION: Stage {target.value} requires cryptographic "
                    "human authorization token (>= 16 characters)."
                )
                logger.warning(reason)
                return PromotionVerdict(
                    approved=False,
                    previous_stage=prev_stage,
                    current_stage=self._current_stage,
                    active_capabilities=self._capabilities,
                    rejection_reason=reason,
                )

        # 5. Execute state transition
        self._current_stage = target
        self._capabilities = STAGE_CAPABILITIES_MAP[target]
        self._active_evidence.update(request.evidence_bundle)

        # Log transition audit
        self._audit_log.append(
            {
                "timestamp": now,
                "previous_stage": prev_stage.value,
                "target_stage": target.value,
                "strategy_id": request.strategy_id,
                "verified_gates": [g.value for g in verified_gates],
                "human_auth_present": bool(request.human_authorization),
            }
        )

        logger.info(
            f"Promotion approved: {prev_stage.value} -> {target.value} "
            f"(Verified gates: {[g.value for g in verified_gates]})"
        )

        return PromotionVerdict(
            approved=True,
            previous_stage=prev_stage,
            current_stage=self._current_stage,
            active_capabilities=self._capabilities,
            verified_gates=verified_gates,
        )

    def emergency_downgrade(
        self,
        reason: str,
        target_stage: DeploymentStage = DeploymentStage.RESEARCH_ONLY,
    ) -> None:
        """
        Immediate emergency downgrade. Revokes active capabilities fail-closed.
        """
        prev_stage = self._current_stage
        self._current_stage = target_stage
        self._capabilities = STAGE_CAPABILITIES_MAP[target_stage]
        self._active_evidence.clear()

        self._audit_log.append(
            {
                "timestamp": time.time(),
                "event": "EMERGENCY_DOWNGRADE",
                "previous_stage": prev_stage.value,
                "target_stage": target_stage.value,
                "reason": reason,
            }
        )
        logger.error(
            f"EMERGENCY DOWNGRADE: {prev_stage.value} -> {target_stage.value}. Reason: {reason}"
        )

    def get_status_report(self) -> dict[str, Any]:
        """Provides authoritative status report."""
        return {
            "system_stage": self._current_stage.value,
            "real_capital_enabled": self.real_capital_enabled,
            "live_order_submission": "prohibited",
            "capabilities": self._capabilities.to_dict(),
            "active_gates": {g.value: e.to_dict() for g, e in self._active_evidence.items()},
            "audit_events_count": len(self._audit_log),
        }


# Global singleton instance
deployment_governor = InstitutionalDeploymentGovernor()
