"""
core/intelligence/validation_result.py
======================================
10-Tier Institutional Research Result Taxonomy for Milestone 29.

Enforces Stage 8 Result Taxonomy:
1. Replaces naive binary VALIDATED/FALSIFIED with a rigorous 10-tier epistemic taxonomy:
   - INCONCLUSIVE: Sample size or statistical power insufficient to reject H0.
   - PRELIMINARY_SUPPORT: Net positive expectancy, but replication or regime check pending.
   - FALSIFIED: Empirical net expectancy E[R] <= 0 or formal stop criteria triggered.
   - COST_INVALIDATED: Positive gross edge, but eliminated by realistic 3-tier frictions.
   - REGIME_DEPENDENT: Edge present in one macro regime (e.g. easing) but negative in another.
   - DATA_INVALID: Gaps, timestamp leakage, or unverified vintages detected in manifest.
   - REPLICATION_PENDING: Passed single-window replay; multi-fold walk-forward queued.
   - OOS_VALIDATED: Passed Purged K-Fold CPCV with stability ratio >= 0.65 and DSR > 0.95.
   - INDEPENDENTLY_REPLICATED: Confirmed on separate, non-overlapping asset or timeframe.
   - HUMAN_REVIEW_REQUIRED: Statistical anomaly or boundary condition requiring quant operator review.
2. Invariant: Positive research results NEVER grant execution authority.
3. Invariant: real_capital_enabled is permanently False.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_quant_sentinel.intelligence.validation_result")


class ResearchValidationStatus(StrEnum):
    INCONCLUSIVE = "INCONCLUSIVE"
    PRELIMINARY_SUPPORT = "PRELIMINARY_SUPPORT"
    FALSIFIED = "FALSIFIED"
    COST_INVALIDATED = "COST_INVALIDATED"
    REGIME_DEPENDENT = "REGIME_DEPENDENT"
    DATA_INVALID = "DATA_INVALID"
    REPLICATION_PENDING = "REPLICATION_PENDING"
    OOS_VALIDATED = "OOS_VALIDATED"
    INDEPENDENTLY_REPLICATED = "INDEPENDENTLY_REPLICATED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class CausalValidationResult(BaseModel):
    """
    Formal, immutable statistical validation result evaluating a CausalHypothesis
    against preregistered contract criteria and 8-attribute scorecard.
    """

    result_id: str = Field(..., description="Unique result ID: RES-<timestamp>-<hash>")
    contract_id: str = Field(..., description="Referenced PreregisteredResearchContract ID")
    hypothesis_id: str = Field(..., description="Referenced CausalHypothesis ID")
    status: ResearchValidationStatus = Field(..., description="10-Tier Epistemic Research Status")

    # 8-Attribute Empirical Scorecard Metrics
    primary_endpoint_value: float = Field(
        ..., description="Observed primary endpoint (e.g. Net E[R])"
    )
    benchmark_relative_alpha: float = Field(..., description="Excess return over passive benchmark")
    effective_sample_size: float = Field(
        ..., description="Sample size adjusted for autocorrelation and clustering"
    )
    deflated_sharpe_ratio: float = Field(
        ..., description="DSR accounting for multiple testing trials"
    )
    whites_reality_check_pvalue: float = Field(..., description="WRC bootstrap p-value")
    regime_stability_ratio: float = Field(
        ..., description="OOS Sharpe / IS Sharpe across macro regimes"
    )
    parameter_perturbation_decay: float = Field(
        ..., description="Max performance decay under +/- 20% perturbation"
    )
    cost_erosion_pct: float = Field(
        ..., description="Percentage of gross edge consumed by frictions"
    )

    # Verdict Details
    verdict_rationale: str = Field(
        ..., description="Detailed institutional explanation of evaluation"
    )
    scorecard_passes: dict[str, bool] = Field(
        default_factory=dict, description="Per-attribute scorecard pass/fail"
    )

    # Constitutional Invariants
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Never grants order routing authority",
    )
    real_capital_enabled: Literal[False] = Field(
        False,
        description="CONSTITUTIONAL INVARIANT: Real capital routing permanently disabled",
    )
    evaluated_at_utc: float = Field(default_factory=time.time)

    def summary(self) -> str:
        return (
            f"[{self.result_id}] Status: {self.status.value} | Hypo: {self.hypothesis_id} | "
            f"Net E[R]: {self.primary_endpoint_value:+.2f} | DSR: {self.deflated_sharpe_ratio:.2f} | "
            f"Alpha: {self.benchmark_relative_alpha:+.2f}% | Erosion: {self.cost_erosion_pct:.1f}%"
        )
