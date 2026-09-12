"""
core/knowledge_os/epistemic_system.py
======================================
SKY Epistemic Status Engine, Knowledge Tier Hierarchy & Multi-Dimensional Ranking.

Constitutional Mandates:
1. Frequency != Truth: A concept appearing in 100 books is NOT automatically empirically valid.
2. Authority != Evidence: Famous traders or video creators saying something does not make it true.
3. Popularity != Edge: Retail TA popularity often correlates with liquidity extraction, not alpha.
4. Zero-Alpha Default: All extracted claims start as UNVERIFIED with 0.0 assumed alpha.
5. Controlled Promotion: Only empirical testing with out-of-sample data can elevate to EMPIRICALLY_SUPPORTED.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.epistemic_system")


class EpistemicStatus(StrEnum):
    """Formal 14-state epistemic lifecycle for all durable knowledge objects."""

    SOURCE_ONLY = "SOURCE_ONLY"
    EXTRACTED = "EXTRACTED"
    UNVERIFIED = "UNVERIFIED"
    HYPOTHESIS = "HYPOTHESIS"
    TESTING = "TESTING"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    EMPIRICALLY_SUPPORTED = "EMPIRICALLY_SUPPORTED"
    PROJECT_APPLIED = "PROJECT_APPLIED"
    TEACHING_READY = "TEACHING_READY"
    SUPERSEDED = "SUPERSEDED"
    CONTRADICTED = "CONTRADICTED"
    REJECTED = "REJECTED"


class KnowledgeTier(StrEnum):
    """7-tier hierarchy separating raw data from verified empirical and applied knowledge."""

    TIER_0_RAW_SOURCE = "TIER_0_RAW_SOURCE"
    TIER_1_EXTRACTED = "TIER_1_EXTRACTED"
    TIER_2_SYNTHESIZED = "TIER_2_SYNTHESIZED"
    TIER_3_HYPOTHESIS = "TIER_3_HYPOTHESIS"
    TIER_4_EMPIRICAL_EVIDENCE = "TIER_4_EMPIRICAL_EVIDENCE"
    TIER_5_PROJECT_KNOWLEDGE = "TIER_5_PROJECT_KNOWLEDGE"
    TIER_6_HUMAN_TEACHING = "TIER_6_HUMAN_TEACHING"


# Strict allowable transitions
VALID_TRANSITIONS: dict[EpistemicStatus, set[EpistemicStatus]] = {
    EpistemicStatus.SOURCE_ONLY: {
        EpistemicStatus.EXTRACTED,
        EpistemicStatus.UNVERIFIED,
        EpistemicStatus.REJECTED,
    },
    EpistemicStatus.EXTRACTED: {
        EpistemicStatus.UNVERIFIED,
        EpistemicStatus.HYPOTHESIS,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.SUPERSEDED,
    },
    EpistemicStatus.UNVERIFIED: {
        EpistemicStatus.HYPOTHESIS,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.SUPERSEDED,
        EpistemicStatus.TEACHING_READY,  # Can be taught as source material, with caveats
    },
    EpistemicStatus.HYPOTHESIS: {
        EpistemicStatus.TESTING,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.REJECTED,
    },
    EpistemicStatus.TESTING: {
        EpistemicStatus.SUPPORTED,
        EpistemicStatus.REFUTED,
        EpistemicStatus.INCONCLUSIVE,
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        EpistemicStatus.REJECTED,
    },
    EpistemicStatus.SUPPORTED: {
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.SUPERSEDED,
        EpistemicStatus.PROJECT_APPLIED,
        EpistemicStatus.TEACHING_READY,
    },
    EpistemicStatus.EMPIRICALLY_SUPPORTED: {
        EpistemicStatus.PROJECT_APPLIED,
        EpistemicStatus.TEACHING_READY,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.SUPERSEDED,
    },
    EpistemicStatus.PROJECT_APPLIED: {
        EpistemicStatus.SUPERSEDED,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.TEACHING_READY,
    },
    EpistemicStatus.TEACHING_READY: {
        EpistemicStatus.SUPERSEDED,
        EpistemicStatus.CONTRADICTED,
    },
    EpistemicStatus.REFUTED: {
        EpistemicStatus.REJECTED,
        EpistemicStatus.SUPERSEDED,
    },
    EpistemicStatus.INCONCLUSIVE: {
        EpistemicStatus.TESTING,
        EpistemicStatus.REJECTED,
    },
    EpistemicStatus.CONTRADICTED: {
        EpistemicStatus.HYPOTHESIS,
        EpistemicStatus.TESTING,
        EpistemicStatus.SUPERSEDED,
        EpistemicStatus.REJECTED,
    },
    EpistemicStatus.SUPERSEDED: set(),  # Terminal historical state
    EpistemicStatus.REJECTED: {
        EpistemicStatus.SUPERSEDED,
    },
}


def validate_status_transition(
    current_status: EpistemicStatus | str,
    target_status: EpistemicStatus | str,
    evidence_present: bool = False,
    sample_size: int = 0,
    p_value: float | None = None,
) -> tuple[bool, str]:
    """
    Validates whether a status transition complies with constitutional rules.
    Prevents unverified claims from jumping directly to EMPIRICALLY_SUPPORTED without evidence.
    """
    try:
        curr = EpistemicStatus(current_status)
        target = EpistemicStatus(target_status)
    except ValueError as e:
        return False, f"Invalid EpistemicStatus: {e}"

    if curr == target:
        return True, "Identity transition permitted"

    allowed_targets = VALID_TRANSITIONS.get(curr, set())
    if target not in allowed_targets:
        return False, (
            f"Illegal transition: Cannot move from {curr.value} to {target.value}. "
            f"Allowed next states: {[s.value for s in allowed_targets]}"
        )

    # Invariant: EMPIRICALLY_SUPPORTED strictly requires verified evidence
    if target == EpistemicStatus.EMPIRICALLY_SUPPORTED:
        if not evidence_present:
            return False, "EMPIRICALLY_SUPPORTED requires confirmed empirical backtest evidence."
        if sample_size < 30:
            return (
                False,
                f"Sample size ({sample_size}) too small for empirical support (minimum 30).",
            )
        if p_value is not None and p_value > 0.05:
            return (
                False,
                f"Statistical p-value ({p_value:.4f}) exceeds significance threshold 0.05.",
            )

    return True, "Transition authorized"


@dataclass
class RankingScoreVector:
    """
    Multi-dimensional knowledge ranking vector.
    Separates relevance from evidence strength:
    - High Relevance / Low Evidence: Heavily relevant to user prompt, but largely unproven retail theory.
    - High Evidence / Low Relevance: Proven statistical phenomenon, but tangentially related.
    """

    relevance_score: float  # [0, 1] Match to user query / domain context
    source_coverage: float  # [0, 1] Cross-source frequency / author consensus
    epistemic_strength: float  # [0, 1] 0.1 for unverified, 0.95 for empirical proof
    empirical_support: float  # [0, 1] Backtest sample size, Sharpe, p-value strength
    recency_score: float  # [0, 1] Freshness vs historical decay
    contradiction_status: str  # UNCONTRADICTED, CONTRADICTED, RESOLVED
    provenance_quality: float  # [0, 1] Page number, chapter, author, SHA-256 completeness
    project_applicability: float  # [0, 1] Degree of applicability to SKY crypto/perps
    classification: str = "UNCLASSIFIED"
    composite_rank: float = 0.0

    def calculate_composite(self) -> float:
        """
        Computes bounded composite rank without collapsing distinctions.
        Applies penalty for active contradictions.
        """
        contradiction_mult = 0.6 if self.contradiction_status == "CONTRADICTED" else 1.0
        weighted_score = (
            self.relevance_score * 0.30
            + self.epistemic_strength * 0.30
            + self.empirical_support * 0.20
            + self.provenance_quality * 0.10
            + self.project_applicability * 0.10
        ) * contradiction_mult

        self.composite_rank = round(min(1.0, max(0.0, weighted_score)), 4)

        # Classify multi-dimensional profile
        if self.contradiction_status == "CONTRADICTED":
            self.classification = "CONTRADICTED_DISPUTED"
        elif self.empirical_support >= 0.70 and self.relevance_score >= 0.60:
            self.classification = "EMPIRICALLY_SUPPORTED_CORE"
        elif self.relevance_score >= 0.65 and self.empirical_support < 0.30:
            self.classification = "HIGH_RELEVANCE_LOW_EVIDENCE"
        elif self.empirical_support >= 0.70 and self.relevance_score < 0.40:
            self.classification = "HIGH_EVIDENCE_LOW_DIRECT_RELEVANCE"
        elif self.epistemic_strength <= 0.25:
            self.classification = "THEORETICAL_UNVERIFIED"
        else:
            self.classification = "PLAUSIBLE_CANDIDATE"

        return self.composite_rank

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_epistemic_strength(status: EpistemicStatus | str) -> float:
    """Deterministic epistemic weight per status."""
    st = EpistemicStatus(status) if isinstance(status, str) else status
    weights = {
        EpistemicStatus.SOURCE_ONLY: 0.05,
        EpistemicStatus.EXTRACTED: 0.10,
        EpistemicStatus.UNVERIFIED: 0.15,
        EpistemicStatus.HYPOTHESIS: 0.25,
        EpistemicStatus.TESTING: 0.35,
        EpistemicStatus.INCONCLUSIVE: 0.30,
        EpistemicStatus.SUPPORTED: 0.65,
        EpistemicStatus.REFUTED: 0.05,
        EpistemicStatus.EMPIRICALLY_SUPPORTED: 0.95,
        EpistemicStatus.PROJECT_APPLIED: 0.90,
        EpistemicStatus.TEACHING_READY: 0.70,
        EpistemicStatus.CONTRADICTED: 0.20,
        EpistemicStatus.SUPERSEDED: 0.10,
        EpistemicStatus.REJECTED: 0.00,
    }
    return weights.get(st, 0.10)
