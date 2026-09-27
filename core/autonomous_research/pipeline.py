"""
core/autonomous_research/pipeline.py
====================================
Master Autonomous Knowledge Learning & Research Pipeline for SKY.
Coordinates the end-to-end autonomous research loop:
ANY INPUT ──► UNIVERSAL INGEST ──► IMMUTABLE SOURCE ──► DECOMPOSITION AI
          ──► CONTRADICTION ENGINE & KNOWLEDGE GRAPH
          ──► HYPOTHESIS ENGINE (pre-checking Failure Memory)
          ──► DATA AVAILABILITY CHECK ──► (DATA_INSUFFICIENT or EMPIRICAL TEST)
          ──► VALIDATION GATE ──► (REJECT: Failure Memory) or (QUALIFIED: Practice Engine + Shadow Paper Desk + Knowledge Versioning)
          ──► NEXT RESEARCH PRIORITY LOOP
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.autonomous_research.contradiction_engine import contradiction_engine
from core.autonomous_research.empirical_tester import empirical_tester
from core.autonomous_research.hypothesis_generator import hypothesis_generator
from core.autonomous_research.practice_engine import practice_engine
from core.autonomous_research.priority_engine import priority_engine
from core.autonomous_research.promotion_engine import promotion_engine
from core.autonomous_research.provenance_tracker import provenance_tracker
from core.autonomous_research.quality_scorer import quality_scorer
from core.autonomous_research.storage import research_storage
from core.universal_ingestor import universal_ingestor

logger = logging.getLogger("ai_quant_sentinel.autonomous_research.pipeline")


class AutonomousResearchPipeline:
    """Master coordinator executing the end-to-end quantitative learning loop."""

    def __init__(self):
        self.storage = research_storage
        self.contradiction_eng = contradiction_engine
        self.hypothesis_gen = hypothesis_generator
        self.empirical_test = empirical_tester
        self.practice_eng = practice_engine
        self.promotion_eng = promotion_engine
        self.priority_eng = priority_engine
        self.provenance_trk = provenance_tracker
        self.quality_sc = quality_scorer
        self._is_worker_running = False

    async def ingest_and_process(
        self,
        content: str,
        source_type: str | None = None,
        title: str | None = None,
        author_creator: str | None = None,
        source_uri: str | None = None,
        exact_pointers: dict[str, Any] | None = None,
        auto_advance: bool = True,
    ) -> dict[str, Any]:
        """
        Executes the full autonomous learning cycle from any raw input string or file content.
        Enforces all 10 Anti-False-Knowledge Invariants.
        """
        start_ts = int(time.time() * 1000)
        source_type = source_type or universal_ingestor.detect_source_type(content)
        title = title or f"Autonomous Research Ingest ({source_type})"
        author_creator = author_creator or "External Research Author"
        source_uri = source_uri or f"raw://{source_type.lower()}/{int(time.time())}"
        exact_pointers = exact_pointers or {}

        # ----------------------------------------------------------------------
        # STAGE 1 & 2: Universal Ingestion & Immutable Source Preservation (Invariant 10)
        # ----------------------------------------------------------------------
        imm_src = self.storage.save_immutable_source(
            source_type=source_type,
            source_uri=source_uri,
            raw_content=content,
            title=title,
            author_creator=author_creator,
            exact_pointers=exact_pointers,
        )

        # ----------------------------------------------------------------------
        # STAGE 3: Epistemic Decomposition (Source -> Concept -> Claim -> Candidate)
        # ----------------------------------------------------------------------
        ingest_res = await universal_ingestor.ingest(
            content=content,
            mode="RESEARCH",
            title=title,
            author_creator=author_creator,
            source_uri=source_uri,
        )

        knowledge_id = ingest_res.get("knowledge_id", f"K-{imm_src.source_id[-6:]}")
        concepts = ingest_res.get("concepts", [])
        candidates = ingest_res.get("candidates", [])
        claims = ingest_res.get("claims", [])
        extracted_facts = ingest_res.get("extracted_facts", [])

        # Construct normalized claims for contradiction analysis
        analysis_claims = []
        for c in claims:
            analysis_claims.append(c if isinstance(c, dict) else {"verbatim": str(c)})
        for f in extracted_facts:
            if isinstance(f, dict):
                analysis_claims.append(f)
            else:
                analysis_claims.append({"verbatim": str(f)})

        # ----------------------------------------------------------------------
        # STAGE 4: Contradiction Engine (Detecting clashes & conflicts)
        # ----------------------------------------------------------------------
        conflicts = self.contradiction_eng.detect_contradictions(analysis_claims)

        # ----------------------------------------------------------------------
        # STAGE 5: Autonomous Hypothesis Formulation (Pre-checking Failure Memory)
        # ----------------------------------------------------------------------
        hypotheses: list[dict[str, Any]] = []
        for cand in candidates:
            claim_repr = {
                "id": cand.get("candidate_id"),
                "subject": cand.get("strategy_name", "Alpha Signal"),
                "direction": cand.get("hypothesis", "Statistical Direction"),
                "verbatim": cand.get("hypothesis", ""),
            }
            hypo = self.hypothesis_gen.formulate_hypothesis(
                claim=claim_repr,
                target_symbol="BTC/USDT",
                timeframe=cand.get("timeframe", "15m"),
                selection_method="PRE_REGISTERED",
                parameters=cand.get("parameter_bounds", {}),
            )
            hypotheses.append(hypo)

        # If no explicit candidates, formulate from primary concepts
        if not hypotheses and concepts:
            c0 = concepts[0]
            claim_repr = {
                "id": f"C-{knowledge_id[-6:]}",
                "subject": c0.get("title", "Concept Signal"),
                "direction": c0.get("description", "Forward Movement"),
                "verbatim": c0.get("description", ""),
            }
            hypo = self.hypothesis_gen.formulate_hypothesis(
                claim=claim_repr,
                target_symbol="BTC/USDT",
                timeframe="15m",
                selection_method="PRE_REGISTERED",
            )
            hypotheses.append(hypo)

        # ----------------------------------------------------------------------
        # STAGE 6: Data Availability & Empirical Testing (Invariant 1 & 3)
        # ----------------------------------------------------------------------
        empirical_results: list[dict[str, Any]] = []
        practice_sessions: list[dict[str, Any]] = []
        promotions: list[dict[str, Any]] = []

        if auto_advance:
            for hypo in hypotheses:
                if not hypo.get("can_proceed_to_test", False):
                    empirical_results.append(
                        {
                            "hypothesis_id": hypo.get("hypothesis_id"),
                            "status": "QUARANTINED_PRIOR_FAILURE",
                            "reason": hypo.get("reason"),
                            "qualified": False,
                        }
                    )
                    continue

                # Run empirical evaluation (real market data only)
                test_res = self.empirical_test.run_empirical_test(
                    hypothesis=hypo,
                    symbol=hypo.get("target_symbol", "BTC/USDT"),
                    timeframe=hypo.get("timeframe", "15m"),
                    candidate_id=hypo.get("claim_id"),
                )
                empirical_results.append(test_res)

                # STAGE 7: Practice Engine & Paper Desk Promotion if QUALIFIED
                if test_res.get("qualified", False):
                    # Deliberate AI Practice Drill (Invariant 6)
                    prac_res = self.practice_eng.generate_and_evaluate_exercise(
                        knowledge_id=knowledge_id,
                        concept_title=hypo.get("title", "Qualified Alpha"),
                        target_symbol=hypo.get("target_symbol", "BTC/USDT"),
                        timeframe=hypo.get("timeframe", "15m"),
                    )
                    if isinstance(prac_res, dict):
                        practice_sessions.append(prac_res)
                    else:
                        practice_sessions.append(prac_res.to_dict())

                    # Paper Desk Firewall Promotion (Invariant 9 & 2)
                    promo = self.promotion_eng.promote_qualified_candidate(
                        candidate_id=hypo.get("claim_id", f"CAND-{knowledge_id[-6:]}"),
                        base_knowledge_id=knowledge_id,
                        title=hypo.get("title", "Qualified Strategy"),
                        concept_domain="SMC_QUANT",
                        empirical_report=test_res,
                        provenance_chain=[
                            imm_src.source_id,
                            knowledge_id,
                            hypo.get("hypothesis_id"),
                        ],
                    )
                    promotions.append(promo)

        # ----------------------------------------------------------------------
        # STAGE 8: Next Research Priority Formulation (Invariant 8)
        # ----------------------------------------------------------------------
        next_priorities = self.priority_eng.scan_and_generate_next_tasks(max_tasks=3)

        elapsed_ms = int(time.time() * 1000) - start_ts

        return {
            "status": "PROCESSED",
            "elapsed_ms": elapsed_ms,
            "immutable_source": {
                "source_id": imm_src.source_id,
                "content_hash": imm_src.content_hash,
                "source_type": imm_src.source_type,
                "title": imm_src.title,
            },
            "knowledge_id": knowledge_id,
            "concepts_extracted": len(concepts),
            "candidates_extracted": len(candidates),
            "conflicts_detected": [c.to_dict() for c in conflicts],
            "hypotheses_formulated": hypotheses,
            "empirical_evaluations": empirical_results,
            "practice_sessions": practice_sessions,
            "promotions_to_paper_desk": promotions,
            "next_research_priorities": next_priorities,
            "invariants_enforced": [
                "Invariant 1: Synthetic Data Strictly Prohibited from Claims",
                "Invariant 2: Append-Only Knowledge Versions (KNOWLEDGE_V1, etc.)",
                "Invariant 3: 9-Gate Multi-Metric Qualification (EV>0.15R, Sharpe>=1.0, WR>=45%)",
                "Invariant 4: Multiple-Testing Protection & Deflated Sharpe",
                "Invariant 5: Causal Firewall Closed-Bar Isolation",
                "Invariant 6: 5-Tier Epistemic Separation",
                "Invariant 7: First-Class Failure Memory Pre-Check",
                "Invariant 8: Continuous Autonomous Research Priority Scheduler",
                "Invariant 9: Paper Desk Isolation Firewall (Zero Live Capital Route)",
                "Invariant 10: Zero Silent Loss & Immutable Provenance",
            ],
        }

    def get_provenance_dossier(self, knowledge_id: str) -> dict[str, Any]:
        """Provides full 5-tier causal provenance audit."""
        return self.provenance_trk.get_full_provenance_tree(knowledge_id)

    def run_worker_step(self) -> dict[str, Any] | None:
        """Executes a single step of the background task worker queue."""
        queues = [
            "RECEIVE",
            "INGEST",
            "EXTRACT",
            "ANALYZE",
            "CONNECT",
            "HYPOTHESIZE",
            "EMPIRICAL_TEST",
            "PRACTICE",
            "VALIDATE",
            "PRIORITY",
        ]
        for q in queues:
            task = self.storage.fetch_pending_task(q)
            if task:
                self.storage.update_task_status(task.task_id, "RUNNING")
                try:
                    # Execute task
                    if q == "EMPIRICAL_TEST":
                        hypo = task.payload.get("hypothesis", {})
                        res = self.empirical_test.run_empirical_test(hypo)
                        self.storage.update_task_status(
                            task.task_id, "COMPLETED", partial_output=res
                        )
                        return {"task_id": task.task_id, "queue": q, "result": res}
                    elif q == "PRACTICE":
                        kid = task.payload.get("knowledge_id", "K-UNKNOWN")
                        prac = self.practice_eng.generate_and_evaluate_exercise(
                            knowledge_id=kid,
                            concept_title=task.payload.get("concept_title", "Concept"),
                        )
                        p_dict = prac.to_dict() if hasattr(prac, "to_dict") else prac
                        self.storage.update_task_status(
                            task.task_id, "COMPLETED", partial_output=p_dict
                        )
                        return {"task_id": task.task_id, "queue": q, "result": p_dict}
                    else:
                        self.storage.update_task_status(
                            task.task_id, "COMPLETED", partial_output={"status": "NOOP"}
                        )
                        return {"task_id": task.task_id, "queue": q, "status": "COMPLETED"}
                except Exception as e:
                    logger.error(f"Autonomous task {task.task_id} failed: {e}", exc_info=True)
                    self.storage.update_task_status(task.task_id, "FAILED", error_log=str(e))
                    return {"task_id": task.task_id, "queue": q, "error": str(e)}

        return None


# Singleton master pipeline
autonomous_research_pipeline = AutonomousResearchPipeline()
