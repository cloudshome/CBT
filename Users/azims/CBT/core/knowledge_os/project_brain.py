"""
core/knowledge_os/project_brain.py
==================================
SKY Project Brain & Quantitative Context Engine (PROJECT_BRAIN_POLICY).

Constitutional Safety Mandate (Articles I & II):
1. Informs, recommends, warns, suggests, explains, and identifies contradictions.
2. NEVER silently modifies:
   - Risk limits (Conservative Kelly, Max Drawdown, Exposure caps)
   - Execution logic (Smart execution gateways, SOR, routing)
   - Live trading permissions & keys
   - Capital allocation
   - Strategy activation or quarantine bypass
   - Production system parameters
3. Research Knowledge != Trading Authorization.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager
from core.knowledge_os.epistemic_system import EpistemicStatus
from core.knowledge_os.hybrid_retriever import hybrid_retriever

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.project_brain")


@dataclass
class ProjectKnowledgeContext:
    """Bounded, auditable context package tailored for SKY engineering & research tasks."""

    query: str
    concepts: list[dict[str, Any]]
    source_claims: list[dict[str, Any]]
    competing_definitions: list[dict[str, Any]]
    empirical_evidence: list[dict[str, Any]]
    autopsy_failures: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    current_sky_assumptions: list[str]
    risk_boundary_warnings: list[str]
    provenance_citations: list[dict[str, str]]
    recommendation: str
    proposed_test_plan: list[str]
    epistemic_summary: dict[str, Any]
    safety_disclaimer: str = (
        "RESEARCH KNOWLEDGE ONLY: This context is advisory and educational. "
        "It does NOT grant execution authorization or modify deterministic risk perimeters."
    )
    generated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectBrainContextEngine:
    """Master context aggregator implementing PROJECT_BRAIN_POLICY."""

    def __init__(self):
        self.retriever = hybrid_retriever

    def build_project_context(
        self,
        query: str,
        target_symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        max_context_items: int = 12,
    ) -> ProjectKnowledgeContext:
        """
        Synthesizes a bounded quantitative research context package for any
        system task or architectural decision.
        """
        # Hybrid retrieval with zero unverified promotion
        retrieved_items = self.retriever.retrieve(
            query=query,
            limit=max_context_items * 2,
            include_unverified=True,
            include_autopsies=True,
            include_contradictions=True,
        )

        concepts: list[dict[str, Any]] = []
        source_claims: list[dict[str, Any]] = []
        competing_defs: list[dict[str, Any]] = []
        empirical_evidence: list[dict[str, Any]] = []
        autopsy_failures: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        citations: list[dict[str, str]] = []

        seen_authors = set()

        for item in retrieved_items:
            d = item.to_dict()

            # Record line-item citation
            citations.append(
                {
                    "node_id": item.node_id,
                    "title": item.title,
                    "source": item.source_title or "Research Archive",
                    "author": item.author or "Unknown",
                    "citation": item.location_citation or "General",
                    "status": item.epistemic_status,
                }
            )

            if item.node_type == "CONCEPT":
                concepts.append(d)
            elif item.node_type == "CLAIM":
                source_claims.append(d)
                if item.metadata.get("evidence_type") == "DEFINITION":
                    if item.author and item.author in seen_authors:
                        competing_defs.append(d)
                    elif item.author:
                        seen_authors.add(item.author)
            elif item.node_type == "EVIDENCE":
                empirical_evidence.append(d)
            elif item.node_type == "AUTOPSY":
                autopsy_failures.append(d)
            elif item.node_type == "CONFLICT":
                contradictions.append(d)

        # Truncate to bound context budget
        concepts = concepts[:4]
        source_claims = source_claims[:6]
        competing_defs = competing_defs[:3]
        empirical_evidence = empirical_evidence[:4]
        autopsy_failures = autopsy_failures[:3]
        contradictions = contradictions[:3]

        # Standard SKY architecture assumptions & risk constraints for query context
        sky_assumptions = self._get_relevant_sky_assumptions(query)
        risk_warnings = self._get_risk_boundary_warnings(query, empirical_evidence, autopsy_failures)

        # Synthesize recommendation
        recommendation = self._synthesize_recommendation(
            query=query,
            evidence=empirical_evidence,
            autopsies=autopsy_failures,
            contradictions=contradictions,
        )

        test_plan = self._generate_test_plan(query, empirical_evidence)

        epistemic_summary = {
            "total_relevant_claims": len(source_claims),
            "empirical_proofs_found": len(empirical_evidence),
            "known_failures_autopsied": len(autopsy_failures),
            "active_contradictions": len(contradictions),
            "highest_epistemic_tier": (
                "TIER_4_EMPIRICAL_EVIDENCE"
                if empirical_evidence
                else "TIER_1_EXTRACTED_UNVERIFIED"
            ),
            "has_rejection_precedent": len(autopsy_failures) > 0,
        }

        return ProjectKnowledgeContext(
            query=query,
            concepts=concepts,
            source_claims=source_claims,
            competing_definitions=competing_defs,
            empirical_evidence=empirical_evidence,
            autopsy_failures=autopsy_failures,
            contradictions=contradictions,
            current_sky_assumptions=sky_assumptions,
            risk_boundary_warnings=risk_warnings,
            provenance_citations=citations,
            recommendation=recommendation,
            proposed_test_plan=test_plan,
            epistemic_summary=epistemic_summary,
        )

    def _get_relevant_sky_assumptions(self, query: str) -> list[str]:
        """Maps query keywords to active SKY algorithmic assumptions."""
        q_lower = query.lower()
        assumptions = [
            "Baseline execution assumes 1.5 bps taker fee and 2.0 bps median slippage under normal liquidity.",
            "Synthetic or fabricated price data is strictly quarantined from alpha validation.",
        ]
        if "volatility" in q_lower or "regime" in q_lower:
            assumptions.append("Current volatility classifier partitions into LOW_VOL, TREND_EXPANSION, and CHOP_COMPRESSION.")
        if "fvg" in q_lower or "liquidity" in q_lower or "sweep" in q_lower:
            assumptions.append("SMC structures are treated as liquidity attraction pools, NOT guaranteed turning points.")
        if "stop" in q_lower or "risk" in q_lower:
            assumptions.append("Position sizing is constrained by Half-Kelly (max 2% portfolio equity per trade).")
        return assumptions

    def _get_risk_boundary_warnings(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        autopsies: list[dict[str, Any]],
    ) -> list[str]:
        """Flags risk constraints and known failure pitfalls."""
        warnings = [
            "Constitutional Rule: New strategy logic must undergo walk-forward validation before shadow paper promotion.",
        ]
        if not evidence:
            warnings.append("WARNING: No peer-reviewed or internally verified backtest evidence exists for this concept in the Evidence Vault.")
        if autopsies:
            warnings.append(f"CAUTION: {len(autopsies)} historically failed backtests or autopsies match this setup. Inspect failure reasons to avoid repeat drawdowns.")
        return warnings

    def _synthesize_recommendation(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        autopsies: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
    ) -> str:
        """Synthesizes an empirical, honest recommendation."""
        if autopsies and not evidence:
            return (
                f"REJECT / HIGH CAUTION: Similar implementations exist in the Autopsy Vault with confirmed failures "
                f"({autopsies[0]['metadata'].get('failure_reason', 'UNSTABLE_EXPECTANCY')}). Do not implement without altering primary root mechanics."
            )
        if evidence:
            return (
                f"VALIDATED CANDIDATE: Supported by {len(evidence)} verified empirical tests in the Evidence Vault. "
                "Recommend testing parameter sensitivity under current market regimes before paper deployment."
            )
        if contradictions:
            return (
                "DISPUTED THEORY: Literature contains active contradictions regarding directional outcome or execution rules. "
                "Construct an arbitration hypothesis to empirically isolate which parameter set holds statistical edge."
            )
        return (
            "THEORETICAL EXPLORATION: Widespread in literature but empirically UNTESTED in SKY. "
            "Proceed with formal H0/H1 hypothesis generation and walk-forward backtest before any strategy implementation."
        )

    def _generate_test_plan(self, query: str, evidence: list[dict[str, Any]]) -> list[str]:
        """Generates statistical test plan."""
        return [
            "1. Extract 120-day historical real candle series across target asset (exclude synthetic data).",
            "2. Formulate H0: Setup produces zero statistical expectancy after transaction costs.",
            "3. Execute Event Study / Walk-Forward backtest with multiple-testing correction.",
            "4. Verify p-value < 0.05, Sharpe > 1.0, and maximum drawdown < 15%.",
            "5. Archive results: Promote to Evidence Vault if passed; otherwise log autopsy into Failure Memory.",
        ]


# Singleton
project_brain = ProjectBrainContextEngine()
