"""
core/intelligence/crawler/firewall_adapter.py
============================================
Firewall Adapter for Milestone 30-C.

CONSTITUTIONAL SEPARATION:
The 9-Gate Causal Firewall is a qualification and admissibility filter, NOT a proof engine.
Passing the firewall establishes only that a hypothesis is QUALIFIED_FOR_RESEARCH.
It DOES NOT establish that the causal relationship is true (causal_validity_established=False).
Out-of-sample empirical replay is strictly required before any scientific claim.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.intelligence.causal_firewall import CausalFirewallDecision, CausalFirewallValidator
from core.intelligence.crawler.qualification_contracts import (
    CausalQualificationStatus,
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    global_lineage_ledger,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.firewall_adapter")


@dataclass(frozen=True)
class FirewallQualificationResult:
    """Explicit result of firewall admissibility screening."""

    admissible: bool
    qualification_status: CausalQualificationStatus
    causal_validity_established: bool  # Permanently False at this stage
    replay_required: bool
    hypothesis_id: str
    violations: list[str]
    gate_results: dict[str, bool]
    lineage_node_id: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["qualification_status"] = self.qualification_status.value
        return d


class ResearchFirewallAdapter:
    """
    Connects compiled hypotheses to the institutional 9-Gate Causal Firewall
    without weakening constitutional invariants or overstating causal validity.
    """

    def __init__(
        self,
        validator: CausalFirewallValidator | None = None,
        ledger: HypothesisLedgerManager | None = None,
        lineage_ledger: EvidenceLineageLedger | None = None,
    ) -> None:
        self.validator = validator or CausalFirewallValidator()
        self.ledger = ledger or global_hypothesis_ledger
        self.lineage_ledger = lineage_ledger or global_lineage_ledger

    def evaluate_hypothesis(
        self,
        hypothesis: CausalHypothesis,
    ) -> FirewallQualificationResult:
        """
        Evaluates the candidate hypothesis through the 9-Gate Firewall.
        Updates hypothesis status and persists decision into ledger and lineage graph.
        """
        decision: CausalFirewallDecision = self.validator.validate(hypothesis)
        now = time.time()

        if decision.passed:
            admissible = True
            qual_status = CausalQualificationStatus.QUALIFIED_FOR_RESEARCH
            causal_validity_established = False  # NEVER True prior to out-of-sample replay
            replay_required = True
            hypothesis.status = CausalHypothesisStatus.FIREWALL_VALIDATED
            hypothesis.rejection_reason = None
        else:
            admissible = False
            qual_status = CausalQualificationStatus.FIREWALL_EVALUATED
            causal_validity_established = False
            replay_required = False
            hypothesis.status = CausalHypothesisStatus.REJECTED
            hypothesis.rejection_reason = f"FIREWALL_REJECTION: {'; '.join(decision.violations)}"

        # Save to SQLite ledger
        self.ledger.save_hypothesis(hypothesis)

        # Record Lineage Node for Firewall Evaluation
        lineage_node_id = f"LIN-FW-{hypothesis.hypothesis_id}"
        node = EvidenceLineageNode(
            node_id=lineage_node_id,
            parent_ids=[f"LIN-{hypothesis.hypothesis_id}"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now,
            content_hash_sha256=hashlib.sha256(
                json.dumps(decision.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            metadata={
                "admissible": admissible,
                "qualification_status": qual_status.value,
                "causal_validity_established": causal_validity_established,
                "replay_required": replay_required,
                "violations": decision.violations,
            },
        )
        self.lineage_ledger.record_node(node)

        return FirewallQualificationResult(
            admissible=admissible,
            qualification_status=qual_status,
            causal_validity_established=causal_validity_established,
            replay_required=replay_required,
            hypothesis_id=hypothesis.hypothesis_id,
            violations=decision.violations,
            gate_results=decision.gate_results,
            lineage_node_id=lineage_node_id,
        )
