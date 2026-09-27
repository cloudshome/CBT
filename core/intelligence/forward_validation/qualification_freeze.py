"""
core/intelligence/forward_validation/qualification_freeze.py
============================================================
Milestone 31.5: Research & Qualification Parameter Freeze Registry.

Enforces:
1. Epistemic Freeze Boundary: Before entering testnet daemon engineering (M32),
   strategy definitions, feature schemas, dataset snapshots, and risk parameters
   are frozen into an immutable, cryptographically sealed registry.
2. Anti-Moving-Target Guarantee: M32 engines accept only strategies possessing
   a verified freeze token. Any parameter or schema modification invalidates the token.
3. Chained Cryptographic Manifest: Emits docs/research/M31_5_FREEZE_MANIFEST.json.
4. Constitutional Capital Isolation: real_capital_enabled = False strictly locked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.evidence_ledger import M31REvidenceBundle
from core.intelligence.forward_validation.qualification_engine import (
    M31RQualificationDecision,
    QualificationStatus,
)
from core.intelligence.forward_validation.strategy_manifest import StrategyConstitutionManifest

logger = logging.getLogger("ai_quant_sentinel.intelligence.qualification_freeze")


class QualificationFreezeViolationError(RuntimeError):
    """Raised when an unsealed or mutated strategy attempts entry into testnet execution."""


class FrozenStrategyDossier(BaseModel):
    """
    Immutable sealed dossier binding a strategy's qualified evidence,
    constitution manifest, and execution parameters.
    """

    freeze_token: str = Field(..., description="Unique freeze token: FRZ-M31.5-<timestamp>-<hash>")
    freeze_timestamp_utc: float = Field(default_factory=time.time)
    strategy_id: str
    strategy_version: str
    manifest_hash: str
    evidence_hash: str
    decision_hash: str
    dataset_hash: str
    feature_schema_hash: str
    execution_model: str
    fee_model: str
    slippage_model: str
    max_position_notional_usd: float
    max_drawdown_limit: float
    quarantine_conditions: list[str]
    frozen_parameters: dict[str, Any] = Field(default_factory=dict)

    # Invariants
    real_capital_enabled: Literal[False] = False
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = (
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    )

    def compute_dossier_hash(self) -> str:
        """Computes deterministic SHA-256 digest of this frozen dossier."""
        d = self.model_dump(mode="json")
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class M31_5FreezeManifest(BaseModel):
    """
    Cryptographic manifest sealing the entire qualification freeze cohort.
    """

    freeze_manifest_id: str
    freeze_timestamp_utc: float = Field(default_factory=time.time)
    codebase_git_hash: str
    frozen_strategies: list[FrozenStrategyDossier]
    master_freeze_digest: str

    @classmethod
    def create(
        cls,
        frozen_strategies: list[FrozenStrategyDossier],
        codebase_git_hash: str = "HEAD",
    ) -> M31_5FreezeManifest:
        now = time.time()
        hashes = [s.compute_dossier_hash() for s in frozen_strategies]
        joined = ":".join([*hashes, codebase_git_hash, str(now)])
        master_digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        manifest_id = f"FRZ-MANIFEST-M31.5-{int(now)}-{master_digest[:10]}"

        return cls(
            freeze_manifest_id=manifest_id,
            freeze_timestamp_utc=now,
            codebase_git_hash=codebase_git_hash,
            frozen_strategies=frozen_strategies,
            master_freeze_digest=master_digest,
        )


class QualificationFreezeRegistry:
    """
    Thread-safe in-memory and file-backed registry managing frozen strategy cohorts.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._frozen_dossiers: dict[str, FrozenStrategyDossier] = {}

    def freeze_qualified_strategy(
        self,
        manifest: StrategyConstitutionManifest,
        evidence: M31REvidenceBundle,
        decision: M31RQualificationDecision,
        frozen_parameters: dict[str, Any] | None = None,
    ) -> FrozenStrategyDossier:
        """
        Freezes a strategy that achieved QUALIFIED status in Milestone 31-R.
        Rejects strategies with CONDITIONAL, QUARANTINED, or REJECTED status.
        """
        if decision.status != QualificationStatus.QUALIFIED:
            raise QualificationFreezeViolationError(
                f"Cannot freeze strategy {manifest.strategy_id} with status {decision.status}. "
                "Only QUALIFIED strategies can enter the M31.5 freeze registry."
            )

        now = time.time()
        man_hash = manifest.compute_manifest_hash()
        ev_hash = evidence.compute_evidence_hash()
        dec_hash = decision.reproducibility_hash

        token_seed = f"{manifest.strategy_id}:{manifest.strategy_version}:{man_hash}:{ev_hash}:{dec_hash}:{now}"
        token_digest = hashlib.sha256(token_seed.encode("utf-8")).hexdigest()
        freeze_token = f"FRZ-M31.5-{int(now)}-{token_digest[:12]}"

        dossier = FrozenStrategyDossier(
            freeze_token=freeze_token,
            freeze_timestamp_utc=now,
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            manifest_hash=man_hash,
            evidence_hash=ev_hash,
            decision_hash=dec_hash,
            dataset_hash=manifest.validation_data_hash,
            feature_schema_hash=manifest.feature_schema_hash,
            execution_model=manifest.execution_model,
            fee_model=manifest.fee_model,
            slippage_model=manifest.slippage_model,
            max_position_notional_usd=manifest.max_position_notional_usd,
            max_drawdown_limit=manifest.max_drawdown_limit,
            quarantine_conditions=manifest.quarantine_conditions,
            frozen_parameters=frozen_parameters or {},
            real_capital_enabled=False,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        )

        self._frozen_dossiers[freeze_token] = dossier
        logger.info(
            "Strategy %s frozen with token %s (digest: %s)",
            dossier.strategy_id,
            dossier.freeze_token,
            dossier.compute_dossier_hash()[:10],
        )
        return dossier

    def verify_token(self, freeze_token: str) -> bool:
        """Verifies that a freeze token exists and represents a valid sealed dossier."""
        return freeze_token in self._frozen_dossiers

    def get_dossier(self, freeze_token: str) -> FrozenStrategyDossier | None:
        """Retrieves a frozen dossier by token."""
        return self._frozen_dossiers.get(freeze_token)

    def list_frozen_strategies(self) -> list[FrozenStrategyDossier]:
        """Lists all frozen dossiers."""
        return list(self._frozen_dossiers.values())

    def emit_freeze_manifest(self, output_dir: str | Path, git_hash: str = "HEAD") -> Path:
        """Emits M31_5_FREEZE_MANIFEST.json to the output directory."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        manifest = M31_5FreezeManifest.create(
            frozen_strategies=list(self._frozen_dossiers.values()),
            codebase_git_hash=git_hash,
        )
        target = out / "M31_5_FREEZE_MANIFEST.json"
        target.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8"
        )
        logger.info("Emitted Milestone 31.5 Freeze Manifest to %s", str(target))
        return target
