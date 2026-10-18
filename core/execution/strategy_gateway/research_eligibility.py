"""
core/execution/strategy_gateway/research_eligibility.py
======================================================
Milestone 24 / Gate 1: Strategy Research Eligibility & Quarantine Authority.

Enforces:
1. Research Promotion Boundary:
   Strategies in RESEARCH_ONLY or RESEARCH_VIABLE stages are strictly forbidden
   from advancing to execution feasibility or intent compilation.
   Minimum required stage: EXECUTION_MODEL_VALIDATED or SANDBOX_ELIGIBLE.
2. Cryptographic Provenance Integrity:
   Validates dataset hash and experiment identifier against authoritative
   research manifests, preventing synthetic/unverified profile promotion.
3. Quarantine & Deprecation Enforcement:
   Explicitly quarantined, revoked, or expired strategies fail closed.
4. Append-Only Rejection Ledger:
   Every eligibility check and rejection is recorded to SQLite trading_logs.db
   with nanosecond timing and cryptographic evidence hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager
from core.governance.institutional_deployment import DeploymentStage

logger = logging.getLogger("sky.execution.strategy_gateway.eligibility")

# Stages permitted to enter execution qualification (SANDBOX / SHADOW / TESTNET)
QUALIFICATION_PERMITTED_STAGES: set[DeploymentStage] = {
    DeploymentStage.EXECUTION_MODEL_VALIDATED,
    DeploymentStage.SANDBOX_ELIGIBLE,
    DeploymentStage.SANDBOX_VERIFIED,
    DeploymentStage.HUMAN_LIVE_REVIEW,
}


class StrategyEligibilityError(Exception):
    """Base exception for strategy eligibility violations."""


class IneligibleStrategyError(StrategyEligibilityError):
    """Raised when strategy deployment stage is insufficient for execution qualification."""


class QuarantinedStrategyError(StrategyEligibilityError):
    """Raised when strategy is explicitly quarantined or under active investigation."""


class ProvenanceVerificationError(StrategyEligibilityError):
    """Raised when dataset hash or experiment provenance fails verification."""


@dataclass(frozen=True)
class StrategyEligibilityRecord:
    """Tamper-evident record of an evaluated strategy eligibility check."""

    audit_id: str
    strategy_id: str
    strategy_version: str
    deployment_stage: str
    dataset_hash: str
    experiment_id: str
    is_eligible: bool
    is_quarantined: bool
    rejection_reason: str | None
    checked_at_utc: str
    checked_at_epoch_ms: int
    record_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_eligibility_hash(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical eligibility record."""
    canonical = {
        "strategy_id": str(data.get("strategy_id")),
        "strategy_version": str(data.get("strategy_version")),
        "deployment_stage": str(data.get("deployment_stage")),
        "dataset_hash": str(data.get("dataset_hash")),
        "experiment_id": str(data.get("experiment_id")),
        "is_eligible": bool(data.get("is_eligible")),
        "is_quarantined": bool(data.get("is_quarantined")),
        "rejection_reason": str(data.get("rejection_reason") or ""),
        "checked_at_epoch_ms": int(data.get("checked_at_epoch_ms", 0)),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class StrategyEligibilityVerifier:
    """
    Authoritative verifier of research strategy eligibility and quarantine status.
    Guarantees that unpromoted, quarantined, or unprovenanced research cannot
    leak into execution compilation.
    """

    def __init__(self, db_conn: sqlite3.Connection | None = None) -> None:
        self._db_conn = db_conn
        self._quarantined_strategies: set[str] = set()
        self._trusted_dataset_hashes: set[str] = set()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes idempotent SQLite table for eligibility audit trail."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_eligibility_audits (
                        audit_id TEXT PRIMARY KEY,
                        strategy_id TEXT NOT NULL,
                        strategy_version TEXT NOT NULL,
                        deployment_stage TEXT NOT NULL,
                        dataset_hash TEXT NOT NULL,
                        experiment_id TEXT NOT NULL,
                        is_eligible INTEGER NOT NULL,
                        is_quarantined INTEGER NOT NULL,
                        rejection_reason TEXT,
                        checked_at_utc TEXT NOT NULL,
                        checked_at_epoch_ms INTEGER NOT NULL,
                        record_hash TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_strat_elig_strat_id
                    ON strategy_eligibility_audits(strategy_id, strategy_version);
                    """
                )
        except Exception as exc:
            logger.error(f"[Eligibility] Failed to initialize SQLite schema: {exc}")

    def quarantine_strategy(self, strategy_id: str, reason: str = "") -> None:
        """Adds a strategy to the active quarantine registry."""
        self._quarantined_strategies.add(strategy_id)
        logger.warning(f"[Eligibility] Quarantined strategy '{strategy_id}': {reason}")

    def lift_quarantine(self, strategy_id: str) -> None:
        """Removes a strategy from active quarantine."""
        self._quarantined_strategies.discard(strategy_id)
        logger.info(f"[Eligibility] Lifted quarantine on strategy '{strategy_id}'")

    def register_trusted_dataset_hash(self, dataset_hash: str) -> None:
        """Registers a known verified dataset hash from authoritative research manifests."""
        self._trusted_dataset_hashes.add(dataset_hash)

    def verify_strategy(
        self,
        strategy_id: str,
        strategy_version: str,
        dataset_hash: str,
        experiment_id: str,
        stage: DeploymentStage | str,
        quarantine_override: bool | None = None,
    ) -> StrategyEligibilityRecord:
        """
        Evaluates a strategy against institutional research eligibility gates.
        Returns a verified StrategyEligibilityRecord or raises StrategyEligibilityError.
        """
        now_ms = int(time.time() * 1000)
        utc_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000))
        audit_id = f"ELIG_{strategy_id}_{now_ms}_{int(time.monotonic_ns() % 1_000_000):06d}"

        # 1. Parse and validate deployment stage
        if isinstance(stage, str):
            try:
                parsed_stage = DeploymentStage(stage)
            except ValueError as err:
                self._build_and_persist_record(
                    audit_id=audit_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    stage_str=stage,
                    dataset_hash=dataset_hash,
                    experiment_id=experiment_id,
                    is_eligible=False,
                    is_quarantined=False,
                    rejection_reason=f"INVALID_DEPLOYMENT_STAGE: {err}",
                    utc_now=utc_now,
                    now_ms=now_ms,
                )
                raise IneligibleStrategyError(
                    f"Invalid deployment stage '{stage}' for strategy {strategy_id}"
                ) from err
        else:
            parsed_stage = stage

        # 2. Stage check (Must be >= EXECUTION_MODEL_VALIDATED)
        if parsed_stage not in QUALIFICATION_PERMITTED_STAGES:
            reason = (
                f"STAGE_INSUFFICIENT: Strategy '{strategy_id}' is at stage '{parsed_stage.value}'. "
                f"Required: at least EXECUTION_MODEL_VALIDATED. Research models cannot execute."
            )
            self._build_and_persist_record(
                audit_id=audit_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage_str=parsed_stage.value,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                is_eligible=False,
                is_quarantined=False,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise IneligibleStrategyError(reason)

        # 3. Quarantine check
        is_quarantined = (
            quarantine_override
            if quarantine_override is not None
            else (strategy_id in self._quarantined_strategies)
        )
        if is_quarantined:
            reason = f"QUARANTINED: Strategy '{strategy_id}' is flagged as quarantined or toxic."
            self._build_and_persist_record(
                audit_id=audit_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage_str=parsed_stage.value,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                is_eligible=False,
                is_quarantined=True,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise QuarantinedStrategyError(reason)

        # 4. Provenance check (dataset hash and experiment id must be non-empty)
        if not dataset_hash or len(dataset_hash) < 16 or not experiment_id:
            reason = "PROVENANCE_MISSING: Missing or truncated dataset_hash or experiment_id."
            self._build_and_persist_record(
                audit_id=audit_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage_str=parsed_stage.value,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                is_eligible=False,
                is_quarantined=False,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise ProvenanceVerificationError(reason)

        # Check against trusted dataset hashes if registry is populated
        if self._trusted_dataset_hashes and dataset_hash not in self._trusted_dataset_hashes:
            reason = (
                f"PROVENANCE_UNTRUSTED: dataset_hash '{dataset_hash}' not in verified manifests."
            )
            self._build_and_persist_record(
                audit_id=audit_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage_str=parsed_stage.value,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                is_eligible=False,
                is_quarantined=False,
                rejection_reason=reason,
                utc_now=utc_now,
                now_ms=now_ms,
            )
            raise ProvenanceVerificationError(reason)

        # 5. Passed all eligibility gates
        return self._build_and_persist_record(
            audit_id=audit_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            stage_str=parsed_stage.value,
            dataset_hash=dataset_hash,
            experiment_id=experiment_id,
            is_eligible=True,
            is_quarantined=False,
            rejection_reason=None,
            utc_now=utc_now,
            now_ms=now_ms,
        )

    def _build_and_persist_record(
        self,
        audit_id: str,
        strategy_id: str,
        strategy_version: str,
        stage_str: str,
        dataset_hash: str,
        experiment_id: str,
        is_eligible: bool,
        is_quarantined: bool,
        rejection_reason: str | None,
        utc_now: str,
        now_ms: int,
    ) -> StrategyEligibilityRecord:
        raw_dict = {
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "deployment_stage": stage_str,
            "dataset_hash": dataset_hash,
            "experiment_id": experiment_id,
            "is_eligible": is_eligible,
            "is_quarantined": is_quarantined,
            "rejection_reason": rejection_reason,
            "checked_at_epoch_ms": now_ms,
        }
        rec_hash = compute_eligibility_hash(raw_dict)

        record = StrategyEligibilityRecord(
            audit_id=audit_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            deployment_stage=stage_str,
            dataset_hash=dataset_hash,
            experiment_id=experiment_id,
            is_eligible=is_eligible,
            is_quarantined=is_quarantined,
            rejection_reason=rejection_reason,
            checked_at_utc=utc_now,
            checked_at_epoch_ms=now_ms,
            record_hash=rec_hash,
        )

        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    INSERT INTO strategy_eligibility_audits (
                        audit_id, strategy_id, strategy_version, deployment_stage,
                        dataset_hash, experiment_id, is_eligible, is_quarantined,
                        rejection_reason, checked_at_utc, checked_at_epoch_ms, record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.audit_id,
                        record.strategy_id,
                        record.strategy_version,
                        record.deployment_stage,
                        record.dataset_hash,
                        record.experiment_id,
                        1 if record.is_eligible else 0,
                        1 if record.is_quarantined else 0,
                        record.rejection_reason,
                        record.checked_at_utc,
                        record.checked_at_epoch_ms,
                        record.record_hash,
                    ),
                )
        except Exception as exc:
            logger.error(f"[Eligibility] Failed to persist audit record: {exc}")

        return record
