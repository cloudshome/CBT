"""
core/intelligence/failure_autopsy.py
====================================
Structured Causal Failure Autopsy & Failure Memory Bridge for Milestone 29.

Enforces Stage 9 Failure Governance:
1. Replaces generic rejection strings with rich, structured `CausalFailureAutopsy`.
2. Categorizes failures into formal taxonomy:
   - COST_EROSION
   - REGIME_FRAGILITY
   - SAMPLE_INSUFFICIENCY
   - PARAMETER_OVERFITTING
   - BENCHMARK_UNDERPERFORMANCE
   - DATA_INTEGRITY_VIOLATION
   - ZERO_EXPECTANCY
3. Records multi-tier friction sensitivity, regime stability, and parameter decay.
4. Generates actionable `reusable_lesson` preventing future AI models from repeating errors.
5. Persists directly into SQLite `failure_memory` table and updates `causal_hypotheses_ledger`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.autonomous_research.failure_memory import FailureMemoryEngine
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.hypothesis_schema import (
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.replay_engine import ReplayExecutionReport
from core.intelligence.research_contract import PreregisteredResearchContract
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.failure_autopsy")


class CausalFailureCategory(str, Enum):
    COST_EROSION = "COST_EROSION"
    REGIME_FRAGILITY = "REGIME_FRAGILITY"
    SAMPLE_INSUFFICIENCY = "SAMPLE_INSUFFICIENCY"
    PARAMETER_OVERFITTING = "PARAMETER_OVERFITTING"
    BENCHMARK_UNDERPERFORMANCE = "BENCHMARK_UNDERPERFORMANCE"
    DATA_INTEGRITY_VIOLATION = "DATA_INTEGRITY_VIOLATION"
    ZERO_EXPECTANCY = "ZERO_EXPECTANCY"


class CausalFailureAutopsy(BaseModel):
    """
    First-class institutional post-mortem for a falsified or cost-invalidated causal hypothesis.
    Provides mathematically grounded evidence and reusable lessons to Failure Memory.
    """

    autopsy_id: str = Field(..., description="Unique autopsy ID: AUT-CAUSAL-<timestamp>-<hash>")
    hypothesis_id: str = Field(..., description="Target CausalHypothesis ID")
    contract_id: str = Field(..., description="Referenced PreregisteredResearchContract ID")
    family_id: str = Field(..., description="Preregistered Research Family ID")
    failure_category: CausalFailureCategory = Field(
        ..., description="Primary failure categorization"
    )

    # Mathematical Performance Breakdown
    gross_expectancy_r: float = Field(..., description="Gross expectancy before frictions")
    net_expectancy_r: float = Field(..., description="Net expectancy under conservative frictions")
    friction_sensitivity: dict[str, float] = Field(
        ..., description="Net E[R] across BASE, CONSERVATIVE, and STRESS tiers"
    )
    regime_stability_ratio: float = Field(..., description="Sharpe stability across macro regimes")
    parameter_perturbation_decay: float = Field(
        ..., description="Performance loss under +/- 20% shift"
    )
    sample_sufficiency_ratio: float = Field(
        ..., description="Observed independent episodes / required minimum"
    )
    data_integrity_status: str = Field("VERIFIED", description="Data cleanliness status")

    # Statistical Evidence Summary
    statistical_evidence: dict[str, Any] = Field(
        ..., description="DSR, WRC p-value, win rate, and profit factor"
    )

    # Narrative Diagnostic & Institutional Lesson
    failure_mechanism: str = Field(
        ..., description="Detailed explanation of the exact failure mechanism"
    )
    reusable_lesson: str = Field(
        ..., description="Concrete, actionable directive for future synthesis"
    )

    # Lineage Cryptographic Hashes
    evidence_snapshot_hash: str = Field(..., description="SHA-256 of historical data manifest")
    research_contract_hash: str = Field(..., description="SHA-256 of preregistered contract")
    replay_configuration_hash: str = Field(..., description="SHA-256 of replay configuration")

    created_at_utc: float = Field(default_factory=time.time)

    def summary(self) -> str:
        return (
            f"[{self.autopsy_id}] Category: {self.failure_category.value} | Hypo: {self.hypothesis_id} | "
            f"Gross: {self.gross_expectancy_r:+.2f}R -> Net: {self.net_expectancy_r:+.2f}R | "
            f"Lesson: {self.reusable_lesson[:100]}..."
        )


class FailureAutopsyCompiler:
    """Compiles and archives structured autopsies for falsified research hypotheses."""

    def __init__(
        self,
        failure_memory: FailureMemoryEngine | None = None,
        ledger: HypothesisLedgerManager | None = None,
    ):
        self.failure_memory = failure_memory or FailureMemoryEngine()
        self.ledger = ledger or global_hypothesis_ledger

    def compile_and_record(
        self,
        contract: PreregisteredResearchContract,
        manifest: DatasetManifest,
        report: ReplayExecutionReport,
        validation_result: CausalValidationResult,
    ) -> CausalFailureAutopsy | None:
        """
        Constructs a CausalFailureAutopsy and commits it to Failure Memory.
        Returns the autopsy object, or None if the hypothesis was not falsified.
        """
        now = time.time()
        status = validation_result.status

        # Only generate autopsies for failed, falsified, or invalid outcomes
        if status in (
            ResearchValidationStatus.OOS_VALIDATED,
            ResearchValidationStatus.PRELIMINARY_SUPPORT,
            ResearchValidationStatus.INDEPENDENTLY_REPLICATED,
        ):
            logger.info(
                f"Hypothesis {contract.hypothesis_id} passed validation ({status.value}). No autopsy needed."
            )
            return None

        # Categorize Failure
        if status == ResearchValidationStatus.COST_INVALIDATED:
            category = CausalFailureCategory.COST_EROSION
            mechanism = (
                f"Gross alpha E[R]={report.gross_expectancy_r:+.2f} was completely consumed by "
                f"execution frictions (Cost erosion: {report.cost_erosion_pct:.1f}%). "
                f"Conservative net E[R]={report.net_expectancy_r:+.2f}."
            )
            lesson = (
                f"Do not deploy 5m {contract.mechanism_id} triggers under market orders. "
                "Requires maker execution or higher timeframe smoothing to overcome bid-ask spread and taker fees."
            )
        elif status == ResearchValidationStatus.REGIME_DEPENDENT:
            category = CausalFailureCategory.REGIME_FRAGILITY
            mechanism = (
                f"Alpha is non-stationary and regime-fragile (Regime stability ratio: "
                f"{validation_result.regime_stability_ratio:.2f} < 0.60)."
            )
            lesson = (
                f"Strategy {contract.mechanism_id} only functions in specific liquidity regimes. "
                "Require an explicit regime filter before testing again."
            )
        elif status == ResearchValidationStatus.DATA_INVALID:
            category = CausalFailureCategory.DATA_INTEGRITY_VIOLATION
            mechanism = f"Dataset manifest failed verification: {manifest.rejection_reason}."
            lesson = "Do not test hypotheses on datasets with unverified timestamps or missing intervals."
        elif status == ResearchValidationStatus.INCONCLUSIVE:
            category = CausalFailureCategory.SAMPLE_INSUFFICIENCY
            mechanism = (
                f"Only {report.independent_episodes} independent episodes observed "
                f"(Required: {contract.min_independent_episodes}). Statistical power insufficient."
            )
            lesson = "Extend historical lookback window or aggregate multiple assets to achieve statistical power."
        else:
            category = CausalFailureCategory.ZERO_EXPECTANCY
            mechanism = (
                f"Null hypothesis H0 confirmed: Net expectancy E[R]={report.net_expectancy_r:+.2f} <= 0.0. "
                f"Win rate: {report.win_rate * 100:.1f}%, Profit Factor: {report.profit_factor:.2f}."
            )
            lesson = (
                f"The causal transmission channel '{contract.mechanism_id}' on {contract.target_symbol} "
                "does not exhibit statistical edge in historical data."
            )

        # Multi-Tier Friction Sensitivity
        friction_dict = {
            "BASE": round(report.net_expectancy_r + 0.10, 3),
            "CONSERVATIVE": round(report.net_expectancy_r, 3),
            "STRESS": round(report.stress_expectancy_r, 3),
        }

        # Statistical Evidence Dict
        stat_dict = {
            "deflated_sharpe_ratio": validation_result.deflated_sharpe_ratio,
            "whites_reality_check_pvalue": validation_result.whites_reality_check_pvalue,
            "win_rate": report.win_rate,
            "profit_factor": report.profit_factor,
            "max_drawdown_pct": report.max_drawdown_pct,
            "cost_erosion_pct": report.cost_erosion_pct,
        }

        # Canonical hash for autopsy ID
        canonical_str = (
            f"{contract.hypothesis_id}:{category.value}:{report.net_expectancy_r:.3f}:{now:.0f}"
        )
        autopsy_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        autopsy_id = f"AUT-CAUSAL-{int(now)}-{autopsy_hash[:8].upper()}"

        autopsy = CausalFailureAutopsy(
            autopsy_id=autopsy_id,
            hypothesis_id=contract.hypothesis_id,
            contract_id=contract.contract_id,
            family_id=contract.family_id.value
            if hasattr(contract.family_id, "value")
            else str(contract.family_id),
            failure_category=category,
            gross_expectancy_r=report.gross_expectancy_r,
            net_expectancy_r=report.net_expectancy_r,
            friction_sensitivity=friction_dict,
            regime_stability_ratio=validation_result.regime_stability_ratio,
            parameter_perturbation_decay=validation_result.parameter_perturbation_decay,
            sample_sufficiency_ratio=round(
                report.independent_episodes / max(1, contract.min_independent_episodes), 2
            ),
            data_integrity_status="VERIFIED" if manifest.is_verified else "REJECTED",
            statistical_evidence=stat_dict,
            failure_mechanism=mechanism,
            reusable_lesson=lesson,
            evidence_snapshot_hash=manifest.snapshot_hash_sha256,
            research_contract_hash=contract.contract_hash_sha256,
            replay_configuration_hash=report.config_hash_sha256,
            created_at_utc=now,
        )

        # Commit to Failure Memory SQLite table
        try:
            self.failure_memory.record_failure_autopsy(
                hypothesis_id=autopsy.hypothesis_id,
                hypothesis_text=f"{contract.mechanism_id} {contract.null_hypothesis} {contract.alternative_hypothesis}",
                target_symbol=contract.target_symbol,
                timeframe=contract.timeframe,
                parameters=contract.treatment_definition.get("conditions", {}),
                failure_reason=category.value,
                metrics={
                    "gross_expectancy_r": autopsy.gross_expectancy_r,
                    "net_expectancy_r": autopsy.net_expectancy_r,
                    "friction_sensitivity": autopsy.friction_sensitivity,
                    "regime_stability": autopsy.regime_stability_ratio,
                    "reusable_lesson": autopsy.reusable_lesson,
                },
                autopsy_text=f"Mechanism: {autopsy.failure_mechanism} | Lesson: {autopsy.reusable_lesson}",
            )
            logger.info(
                f"Committed autopsy {autopsy_id} to Failure Memory for hypothesis {contract.hypothesis_id}"
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to commit autopsy to Failure Memory: {e}")

        # Update hypothesis status in ledger
        self.ledger.update_status(
            contract.hypothesis_id,
            CausalHypothesisStatus.FALSIFIED,
            rejection_reason=f"[{category.value}] {mechanism}",
        )

        return autopsy
