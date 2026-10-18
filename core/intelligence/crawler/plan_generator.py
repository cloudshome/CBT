"""
core/intelligence/crawler/plan_generator.py
===========================================
Preregistered Research Plan Generator for Milestone 30-C.

CONSTITUTIONAL PRINCIPLE:
The plan generator must NOT arbitrarily invent research parameters (horizons,
win rates, friction models, or regimes). It strictly binds validated hypotheses
to versioned ResearchTemplates and preregisters immutable plans in the ExperimentPlanLedger.
All plans remain permanently research-only with real capital disabled.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from core.intelligence.crawler.qualification_contracts import (
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    MultipleTestingLedger,
    ResearchTemplate,
    ResearchTemplateRegistry,
    global_lineage_ledger,
    global_multiple_testing_ledger,
    global_research_template_registry,
)
from core.intelligence.hypothesis_schema import CausalHypothesis, CausalHypothesisStatus
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    global_plan_ledger,
)
from core.intelligence.research_contract import (
    PreregisteredResearchContract,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.plan_generator")


class PlanGenerationError(ValueError):
    """Raised when an experiment plan cannot be safely generated."""


@dataclass(frozen=True)
class PlanGenerationResult:
    """Result of generating an immutable preregistered research plan."""

    success: bool
    plan: DurableExperimentPlan | None
    contract: PreregisteredResearchContract | None
    rejection_reason: str | None
    lineage_node_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "plan_id": self.plan.plan_id if self.plan else None,
            "contract_id": self.contract.contract_id if self.contract else None,
            "rejection_reason": self.rejection_reason,
            "lineage_node_id": self.lineage_node_id,
        }


class PreregisteredPlanGenerator:
    """
    Constructs immutable PreregisteredResearchContract and DurableExperimentPlan
    specifications from firewall-qualified CausalHypotheses.
    """

    def __init__(
        self,
        plan_ledger: ExperimentPlanLedger | None = None,
        template_registry: type[ResearchTemplateRegistry] | None = None,
        lineage_ledger: EvidenceLineageLedger | None = None,
        multiple_testing_ledger: MultipleTestingLedger | None = None,
    ) -> None:
        self.plan_ledger = plan_ledger or global_plan_ledger
        self.template_registry = template_registry or global_research_template_registry
        self.lineage_ledger = lineage_ledger or global_lineage_ledger
        self.mt_ledger = multiple_testing_ledger or global_multiple_testing_ledger

    def generate_plan(
        self,
        hypothesis: CausalHypothesis,
        template_id: str,
        batch_id: str = "BATCH_SCOUT_DEFAULT",
    ) -> PlanGenerationResult:
        """
        Binds hypothesis to template methodology and generates immutable replay plan.
        """
        # Invariant 1: Must be validated by Causal Firewall
        if hypothesis.status != CausalHypothesisStatus.FIREWALL_VALIDATED:
            return PlanGenerationResult(
                success=False,
                plan=None,
                contract=None,
                rejection_reason=f"Hypothesis {hypothesis.hypothesis_id} is not FIREWALL_VALIDATED (current: {hypothesis.status.value})",
                lineage_node_id=None,
            )

        # Invariant 2: Look up versioned research template (no arbitrary parameter invention)
        try:
            template: ResearchTemplate = self.template_registry.get(template_id)
        except KeyError:
            return PlanGenerationResult(
                success=False,
                plan=None,
                contract=None,
                rejection_reason=f"ResearchTemplate '{template_id}' is not registered in registry",
                lineage_node_id=None,
            )

        if template.causal_family != hypothesis.family_id:
            return PlanGenerationResult(
                success=False,
                plan=None,
                contract=None,
                rejection_reason=f"Template family '{template.causal_family.value}' does not match hypothesis family '{hypothesis.family_id.value}'",
                lineage_node_id=None,
            )

        # Compute point-in-time backtest chronological window
        end_utc = hypothesis.macro_event_contract.published_at_utc
        start_utc = end_utc - (template.default_lookback_days * 86400.0)

        # Build PreregisteredResearchContract
        try:
            contract = PreregisteredResearchContract.from_hypothesis(
                hypothesis=hypothesis,
                holding_period_bars=12,
                trial_budget=1,
            )
        except Exception as e:
            return PlanGenerationResult(
                success=False,
                plan=None,
                contract=None,
                rejection_reason=f"Failed to compile research contract: {e}",
                lineage_node_id=None,
            )

        # Build DurableExperimentPlan
        durable_plan = DurableExperimentPlan.create(
            hypothesis_id=hypothesis.hypothesis_id,
            family_id=hypothesis.family_id.value,
            target_symbol=hypothesis.target_asset,
            timeframe=hypothesis.timeframe,
            backtest_range_start_utc=start_utc,
            backtest_range_end_utc=end_utc,
            lookback_days=template.default_lookback_days,
            frictional_tier=template.frictional_tier,
            min_oos_trades=template.min_oos_trades,
            required_dsr=template.required_dsr,
            metadata={
                "template_id": template.template_id,
                "template_version": template.template_version,
                "contract_id": contract.contract_id,
                "contract_hash": contract.contract_hash_sha256,
                "multiple_testing_policy": template.multiple_testing_policy,
                "batch_id": batch_id,
            },
        )

        # Save to SQLite plan ledger
        self.plan_ledger.save_plan(durable_plan)

        # Update Multiple-Testing Ledger
        self.mt_ledger.record_batch(
            batch_id=batch_id,
            family_id=hypothesis.family_id.value,
            hypotheses_generated=1,
            hypotheses_tested=0,
            multiple_testing_policy=template.multiple_testing_policy,
            classification="EXPLORATORY",
        )

        # Record Lineage Node
        now = time.time()
        lineage_node_id = f"LIN-{durable_plan.plan_id}"
        node = EvidenceLineageNode(
            node_id=lineage_node_id,
            parent_ids=[f"LIN-FW-{hypothesis.hypothesis_id}"],
            evidence_kind=EvidenceKind.CAUSAL_HYPOTHESIS,
            timestamp_utc=now,
            content_hash_sha256=durable_plan.plan_hash_sha256,
            metadata={
                "plan_id": durable_plan.plan_id,
                "contract_id": contract.contract_id,
                "template_id": template.template_id,
                "batch_id": batch_id,
            },
        )
        self.lineage_ledger.record_node(node)

        return PlanGenerationResult(
            success=True,
            plan=durable_plan,
            contract=contract,
            rejection_reason=None,
            lineage_node_id=lineage_node_id,
        )
