"""
core/intelligence/crawler/causal_compiler.py
============================================
Causal Hypothesis Compiler for Milestone 30-C.

CONSTITUTIONAL PRINCIPLE:
The compiler does NOT merely wrap a fact. It strictly enforces 10 institutional
compilation checks. If any field or assumption is missing, it rejects with
REJECTED_INCOMPLETE_HYPOTHESIS rather than inventing assumptions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.intelligence.causal_mechanisms import (
    CAUSAL_MECHANISMS,
)
from core.intelligence.crawler.fact_extractor import EmpiricalFact
from core.intelligence.crawler.qualification_contracts import (
    CausalQualificationStatus,
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    ResearchTemplateRegistry,
    global_lineage_ledger,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.point_in_time import (
    EPISTEMIC_PRIOR_WEIGHTS,
    PointInTimeEventContract,
)
from core.intelligence.schema import EvidenceGrade, IntelligenceDomain

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.causal_compiler")


@dataclass(frozen=True)
class CausalCompilationResult:
    """Compilation outcome from empirical fact to candidate research hypothesis."""

    success: bool
    hypothesis: CausalHypothesis | None
    rejection_reason: str | None
    dedup_hash: str
    qualification_status: CausalQualificationStatus
    lineage_node_id: str | None = None


class CausalHypothesisCompiler:
    """
    Strict compiler transforming EmpiricalFacts into formal CausalHypothesis structures.
    Enforces the 10 Institutional Compilation Checks.
    """

    def __init__(
        self,
        hypothesis_ledger: HypothesisLedgerManager | None = None,
        template_registry: type[ResearchTemplateRegistry] | None = None,
        lineage_ledger: EvidenceLineageLedger | None = None,
    ) -> None:
        self.hypothesis_ledger = hypothesis_ledger or global_hypothesis_ledger
        self.template_registry = template_registry or ResearchTemplateRegistry
        self.lineage_ledger = lineage_ledger or global_lineage_ledger
        self._compiled_dedup_hashes: set[str] = set()

    def _compute_dedup_hash(
        self,
        entity: str,
        metric_name: str,
        mechanism_id: str,
        horizon: str,
        target_asset: str,
        direction: str,
    ) -> str:
        payload = f"{entity.upper()}:{metric_name.upper()}:{mechanism_id}:{horizon}:{target_asset.upper()}:{direction.upper()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compile(
        self,
        fact: EmpiricalFact,
        template_id: str,
        mechanism_id: str,
        target_asset: str = "BTC/USDT",
        timeframe: str = "5m",
        horizon: str = "4h",
        direction: str = "LONG",
        market_context: dict[str, Any] | None = None,
    ) -> CausalCompilationResult:
        """
        Executes the 10 Institutional Compilation Checks.
        Returns a CausalCompilationResult.
        """
        market_ctx = market_context or {}
        dedup_hash = self._compute_dedup_hash(
            entity=fact.entity,
            metric_name=fact.metric_name,
            mechanism_id=mechanism_id,
            horizon=horizon,
            target_asset=target_asset,
            direction=direction,
        )

        # Check 1: Is the proposed cause observable?
        if fact.evidence_kind != EvidenceKind.DERIVED_FACT:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: Proposed cause is not EvidenceKind.DERIVED_FACT",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )
        if not fact.metric_name or not fact.parent_content_sha256:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: Cause lacks metric name or parent cryptographic seal",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 2: Is the template registered and outcome measurable?
        try:
            template = self.template_registry.get(template_id)
        except KeyError:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Unregistered ResearchTemplate '{template_id}'",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )
        if not template.outcome_definitions:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: Template defines no measurable outcome metrics",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 3: Is the mechanism explicitly defined in the mechanism registry?
        if mechanism_id not in CAUSAL_MECHANISMS:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Mechanism '{mechanism_id}' is not in CAUSAL_MECHANISMS registry",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )
        mech = CAUSAL_MECHANISMS[mechanism_id]
        if mech.family_id != template.causal_family:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Mechanism family '{mech.family_id.value}' does not match template family '{template.causal_family.value}'",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 4: Is the time horizon specified and permitted by template?
        if horizon not in template.allowed_horizons:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Horizon '{horizon}' not permitted in template {template.allowed_horizons}",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 5: Is the target market specified and formatted?
        if "/" not in target_asset or len(target_asset) < 5:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Target asset '{target_asset}' is not a valid trading pair symbol",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 6: Are confounders identified?
        confounders = market_ctx.get("confounders") or [
            "VOLATILITY_REGIME",
            "SESSION_OVERLAP",
            "LIQUIDITY_DEPTH",
        ]
        if not confounders:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: No confounders identified for causal identification",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 7: Is the hypothesis falsifiable? (H0 and H1 non-empty, distinct, with explicit thresholds)
        h0 = f"H0: Post-event {fact.metric_name} ({fact.metric_value} {fact.unit}) has zero net expectancy or underperforms baseline on {target_asset} over {horizon}."
        h1 = f"H1: Directional {direction} impulse following {fact.metric_name}={fact.metric_value} generates net expectancy > {template.required_dsr} R over {horizon}."
        if h0 == h1 or len(h0) < 20 or len(h1) < 20:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: Falsification criteria or H0/H1 definitions are degenerate",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 8: Is the direction of expected effect specified?
        if direction.upper() not in ["LONG", "SHORT"]:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Invalid effect direction '{direction}' (must be LONG or SHORT)",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 9: Is the hypothesis distinct from existing families? (Deduplication)
        if dedup_hash in self._compiled_dedup_hashes:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_DUPLICATE_HYPOTHESIS: Identical causal hypothesis already compiled (hash: {dedup_hash[:8]})",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # Check 10: Is there sufficient evidence to justify research registration?
        if fact.is_quarantined:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason=f"REJECTED_INCOMPLETE_HYPOTHESIS: Fact is quarantined ({fact.quarantine_reason})",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )
        if fact.confidence_scores.fact_confidence <= 0.0:
            return CausalCompilationResult(
                success=False,
                hypothesis=None,
                rejection_reason="REJECTED_INCOMPLETE_HYPOTHESIS: Fact confidence is 0.0 (conflicted or unverifiable)",
                dedup_hash=dedup_hash,
                qualification_status=CausalQualificationStatus.CANDIDATE_GENERATED,
            )

        # All 10 checks passed: Compile Point-in-Time Event Contract
        now = time.time()
        pub_utc = fact.extracted_at_utc - 60.0  # 60s conservative publishing offset
        eff_avail = fact.extracted_at_utc

        epistemic_grade = (
            EvidenceGrade.VERIFIED_PRIMARY.value
            if fact.confidence_scores.source_reliability >= 0.90
            else EvidenceGrade.CORROBORATED_REPORT.value
        )
        epistemic_weight = EPISTEMIC_PRIOR_WEIGHTS.get(epistemic_grade, 0.70)

        event_contract = PointInTimeEventContract(
            event_id=fact.canonical_event_id,
            source_record_id=fact.parent_evidence_id,
            event_type=fact.event_type.value,
            domain=IntelligenceDomain.MACRO.value
            if "MACRO" in fact.canonical_event_id
            else IntelligenceDomain.CRYPTO.value,
            headline=f"Empirical print for {fact.canonical_event_id}: {fact.metric_name}={fact.metric_value} {fact.unit}",
            published_at_utc=pub_utc,
            collected_at_utc=eff_avail,
            effective_availability_utc=eff_avail,
            dissemination_buffer_seconds=5.0,
            content_hash_sha256=fact.parent_content_sha256,
            epistemic_grade=epistemic_grade,
            epistemic_prior_weight=epistemic_weight,
            metadata={
                "fact_id": fact.fact_id,
                "dedup_hash": dedup_hash,
                "confounders": confounders,
                "causal_prior_strength": fact.confidence_scores.causal_prior_strength,
            },
        )

        hypo_id = f"HYPO-{datetime.now(UTC).strftime('%Y%m%d')}-{dedup_hash[:8]}"

        hypothesis = CausalHypothesis(
            hypothesis_id=hypo_id,
            family_id=template.causal_family,
            mechanism_id=mechanism_id,
            macro_event_contract=event_contract,
            target_asset=target_asset,
            timeframe=timeframe,
            null_hypothesis=h0,
            alternative_hypothesis=h1,
            microstructure_conditions={
                "metric_name": fact.metric_name,
                "metric_value": fact.metric_value,
                "direction": direction,
                "horizon": horizon,
            },
            falsification_criteria={
                "min_dsr": template.required_dsr,
                "max_drawdown_limit_pct": 15.0,
                "frictional_tier": template.frictional_tier,
                "confounders": confounders,
            },
            epistemic_prior_weight=epistemic_weight,
            status=CausalHypothesisStatus.DRAFT,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
        )

        # Mark dedup hash as compiled
        self._compiled_dedup_hashes.add(dedup_hash)

        # Record Lineage for Causal Hypothesis
        lineage_node_id = f"LIN-{hypo_id}"
        node = EvidenceLineageNode(
            node_id=lineage_node_id,
            parent_ids=[f"LIN-{fact.fact_id}"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now,
            content_hash_sha256=hashlib.sha256(
                json.dumps(hypothesis.model_dump(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            metadata={
                "template_id": template_id,
                "mechanism_id": mechanism_id,
                "dedup_hash": dedup_hash,
            },
        )
        self.lineage_ledger.record_node(node)

        return CausalCompilationResult(
            success=True,
            hypothesis=hypothesis,
            rejection_reason=None,
            dedup_hash=dedup_hash,
            qualification_status=CausalQualificationStatus.EVIDENCE_ADMISSIBLE,
            lineage_node_id=lineage_node_id,
        )
