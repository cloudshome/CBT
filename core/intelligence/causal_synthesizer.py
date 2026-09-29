"""
core/intelligence/causal_synthesizer.py
=======================================
Cross-Domain Macro-Micro Causal Synthesizer for Milestone 28.

Institutional Causal Research Compiler:
1. Translates qualitative IntelligenceRecords and NarrativeClusters into testable CausalHypotheses.
2. Bridges macro shocks to existing microstructure receptors (CVD absorption, L2 OBI, SMC/ICT).
3. Formulates Popperian null (H0) and alternative (H1) hypotheses with falsification rules.
4. Executes the 9-Gate CausalFirewallValidator before persisting to the research ledger.
5. Produces SynthesizedExperimentPlans ready for Autonomous Research Lab dispatch.
"""

from __future__ import annotations

import logging
import time
import uuid

from core.intelligence.causal_firewall import CausalFirewallValidator, global_causal_firewall
from core.intelligence.causal_mechanisms import (
    CAUSAL_MECHANISMS,
    RESEARCH_FAMILIES,
    CausalMechanism,
    lookup_family,
    match_candidate_mechanisms,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    SynthesizedExperimentPlan,
    global_hypothesis_ledger,
)
from core.intelligence.narrative_radar import NarrativeCluster
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    global_plan_ledger,
)
from core.intelligence.point_in_time import PointInTimeEventContract
from core.intelligence.schema import IntelligenceRecord

logger = logging.getLogger("ai_quant_sentinel.intelligence.causal_synthesizer")


class CausalHypothesisSynthesizer:
    """
    Cross-domain causal synthesizer compiling unstructured intelligence
    into rigorous, point-in-time quantitative research hypotheses.
    """

    def __init__(
        self,
        firewall: CausalFirewallValidator | None = None,
        ledger: HypothesisLedgerManager | None = None,
        plan_ledger: ExperimentPlanLedger | None = None,
    ):
        self.firewall = firewall or global_causal_firewall
        self.ledger = ledger or global_hypothesis_ledger
        self.plan_ledger = plan_ledger or global_plan_ledger

    def synthesize_from_record(
        self,
        record: IntelligenceRecord,
        target_asset: str = "BTC/USDT",
        timeframe: str = "5m",
        auto_validate: bool = True,
    ) -> list[CausalHypothesis]:
        """
        Compiles an IntelligenceRecord into candidate CausalHypotheses based on
        preregistered causal transmission mechanisms.
        """
        candidate_mechanisms = match_candidate_mechanisms(
            domain=record.domain if isinstance(record.domain, str) else record.domain.value,
            headline=record.title,
            entities=record.entities,
        )

        if not candidate_mechanisms:
            # Fallback to the primary mechanism of the family matching the domain
            domain_str = record.domain if isinstance(record.domain, str) else record.domain.value
            for mech in CAUSAL_MECHANISMS.values():
                family = RESEARCH_FAMILIES[mech.family_id]
                if domain_str in family.applicable_domains:
                    candidate_mechanisms.append(mech)
                    break

        if not candidate_mechanisms:
            logger.info(f"No viable causal mechanisms matched for record {record.record_id}")
            return []

        # Construct PointInTimeEventContract with deterministic timestamp precedence
        contract = PointInTimeEventContract.from_intelligence_record(record)

        hypotheses: list[CausalHypothesis] = []
        for mech in candidate_mechanisms:
            hypo = self._build_hypothesis(
                contract=contract,
                mechanism=mech,
                target_asset=target_asset,
                timeframe=timeframe,
            )

            # Persist draft to ledger
            self.ledger.save_hypothesis(hypo)

            if auto_validate:
                decision = self.firewall.validate(hypo)
                hypo.status = (
                    CausalHypothesisStatus.FIREWALL_VALIDATED
                    if decision.passed
                    else CausalHypothesisStatus.REJECTED
                )
                hypo.rejection_reason = (
                    "; ".join(decision.violations) if not decision.passed else None
                )

            hypotheses.append(hypo)

        return hypotheses

    def synthesize_from_narrative(
        self,
        cluster: NarrativeCluster,
        target_asset: str = "BTC/USDT",
        timeframe: str = "15m",
        auto_validate: bool = True,
    ) -> list[CausalHypothesis]:
        """
        Compiles a high-level NarrativeCluster into cross-asset contagion or liquidity hypotheses.
        """
        grade_map = {
            "INSTITUTIONAL_BACKED": "CORROBORATED_REPORT",
            "CORROBORATED": "CORROBORATED_REPORT",
            "HYPE_DRIVEN": "SPECULATION",
        }
        grade = grade_map.get(cluster.credibility_tag, "UNVERIFIED_CLAIM")

        fake_rec = IntelligenceRecord.create(
            source_platform="WEB",
            source_url=f"urn:narrative:{abs(hash(cluster.theme))}",
            title=f"Narrative Cluster: {cluster.theme}",
            content_markdown=(
                f"Narrative: {cluster.theme}. Records: {cluster.total_records}. "
                f"Velocity: {cluster.velocity_score:.2f}/hr."
            ),
            summary=cluster.theme,
            domain="MACRO",
            entities=cluster.entities,
            evidence_grade=grade,
            relevance_score=0.85,
            published_at_utc=cluster.latest_timestamp_utc,
        )

        return self.synthesize_from_record(
            record=fake_rec,
            target_asset=target_asset,
            timeframe=timeframe,
            auto_validate=auto_validate,
        )

    def batch_synthesize(
        self,
        records: list[IntelligenceRecord],
        target_asset: str = "BTC/USDT",
        timeframe: str = "5m",
    ) -> list[CausalHypothesis]:
        """Runs causal compilation across a batch of intelligence records."""
        results: list[CausalHypothesis] = []
        for rec in records:
            hypos = self.synthesize_from_record(
                record=rec,
                target_asset=target_asset,
                timeframe=timeframe,
                auto_validate=True,
            )
            results.extend(hypos)
        return results

    def dispatch_to_research_lab(
        self,
        hypothesis_id: str,
        frictional_tier: str = "CONSERVATIVE",
    ) -> SynthesizedExperimentPlan:
        """
        Packages a firewall-validated hypothesis into an experiment plan ready for backtesting.
        Persists a DurableExperimentPlan in SQLite and updates hypothesis status to QUEUED_FOR_LAB.
        Raises ValueError if hypothesis is not found or not firewall-validated.
        """
        hypo = self.ledger.get_hypothesis(hypothesis_id)
        if not hypo:
            raise ValueError(f"Hypothesis {hypothesis_id} not found in ledger.")

        existing_plan = self.plan_ledger.get_plan_by_hypothesis(hypothesis_id)
        if hypo.status == CausalHypothesisStatus.QUEUED_FOR_LAB and existing_plan:
            logger.info(
                f"Hypothesis {hypothesis_id} already dispatched as plan {existing_plan.plan_id}. Returning existing plan."
            )
            return SynthesizedExperimentPlan(
                plan_id=existing_plan.plan_id,
                hypothesis_id=existing_plan.hypothesis_id,
                family_id=existing_plan.family_id,
                target_symbol=existing_plan.target_symbol,
                timeframe=existing_plan.timeframe,
                backtest_range_start_utc=existing_plan.backtest_range_start_utc,
                backtest_range_end_utc=existing_plan.backtest_range_end_utc,
                frictional_tier=existing_plan.frictional_tier,
                min_oos_trades=existing_plan.min_oos_trades,
                required_dsr=existing_plan.required_dsr,
                execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
                real_capital_enabled=False,
                created_at_utc=existing_plan.created_at_utc,
            )

        if hypo.status != CausalHypothesisStatus.FIREWALL_VALIDATED:
            raise ValueError(
                f"Cannot dispatch hypothesis {hypothesis_id} with status '{hypo.status.value}'. "
                "Must be FIREWALL_VALIDATED."
            )

        now = time.time()
        # Look up research family for dynamic lookback requirement
        family = lookup_family(hypo.family_id)
        lookback_days = getattr(family, "min_lookback_days", 90) if family else 90

        event_avail = hypo.macro_event_contract.effective_availability_utc
        range_start = max(0.0, event_avail - (lookback_days * 86400))
        range_end = event_avail

        # Persist DurableExperimentPlan into SQLite
        durable_plan = DurableExperimentPlan.create(
            hypothesis_id=hypo.hypothesis_id,
            family_id=hypo.family_id.value,
            target_symbol=hypo.target_asset,
            timeframe=hypo.timeframe,
            backtest_range_start_utc=range_start,
            backtest_range_end_utc=range_end,
            lookback_days=lookback_days,
            frictional_tier=frictional_tier,
            min_oos_trades=30,
            required_dsr=0.95,
        )
        self.plan_ledger.save_plan(durable_plan)

        # Build SynthesizedExperimentPlan for backwards-compatible response
        plan = SynthesizedExperimentPlan(
            plan_id=durable_plan.plan_id,
            hypothesis_id=hypo.hypothesis_id,
            family_id=hypo.family_id.value,
            target_symbol=hypo.target_asset,
            timeframe=hypo.timeframe,
            backtest_range_start_utc=range_start,
            backtest_range_end_utc=range_end,
            frictional_tier=frictional_tier,
            min_oos_trades=30,
            required_dsr=0.95,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            created_at_utc=now,
        )

        # Update ledger status to QUEUED_FOR_LAB
        self.ledger.update_status(hypo.hypothesis_id, CausalHypothesisStatus.QUEUED_FOR_LAB)

        logger.info(
            f"Dispatched hypothesis {hypo.hypothesis_id} to Research Lab as durable plan {durable_plan.plan_id}"
        )
        return plan

    # ========================================================================
    # Private Helpers
    # ========================================================================

    def _build_hypothesis(
        self,
        contract: PointInTimeEventContract,
        mechanism: CausalMechanism,
        target_asset: str,
        timeframe: str,
    ) -> CausalHypothesis:
        """Formulates Popperian H0 vs H1 hypotheses and binds microstructure gates."""
        now = time.time()
        # Guarantee strict chronological precedence: created_at >= effective_availability + 1.0s
        created_at = max(now, contract.effective_availability_utc + 1.0)

        hypo_id = f"HYPO-{int(created_at)}-{uuid.uuid4().hex[:8].upper()}"

        # Formal Null Hypothesis (H0)
        h0 = (
            f"Mean net expected value per risk unit E[R] <= 0.0 under conservative frictions "
            f"following {mechanism.name} on {target_asset} ({timeframe})."
        )

        # Formal Alternative Hypothesis (H1)
        direction_phrase = "long" if mechanism.direction == "BULLISH" else "short"
        h1 = (
            f"Entering {direction_phrase} on {target_asset} ({timeframe}) upon confirmation of "
            f"{mechanism.primary_receptor.value} following {contract.headline[:60]} yields net positive "
            f"expectancy E[R] >= 0.18 with Sharpe >= 1.50 and max drawdown <= 8.5% under conservative frictions."
        )

        return CausalHypothesis(
            hypothesis_id=hypo_id,
            family_id=mechanism.family_id,
            mechanism_id=mechanism.mechanism_id,
            macro_event_contract=contract,
            target_asset=target_asset,
            timeframe=timeframe,
            null_hypothesis=h0,
            alternative_hypothesis=h1,
            microstructure_conditions=mechanism.default_micro_conditions,
            falsification_criteria=mechanism.default_falsification_criteria,
            epistemic_prior_weight=contract.epistemic_prior_weight,
            status=CausalHypothesisStatus.DRAFT,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            created_at_utc=created_at,
            updated_at_utc=created_at,
        )


# Global singleton synthesizer
global_causal_synthesizer = CausalHypothesisSynthesizer()
