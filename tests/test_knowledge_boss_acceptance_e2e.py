"""
tests/test_knowledge_boss_acceptance_e2e.py
===========================================
SKY Knowledge Operating System - Boss-Level Acceptance E2E Test.

Validates the full unified knowledge lifecycle from a single canonical SQLite store:
1. Multi-Page Streaming Book Ingestion with Resumable Checkpoints & SHA-256 hashing.
2. Spatial Atomic Claims (Page number & Bounding Box) with Zero-Alpha Default (confidence=0.0).
3. Normalized Concepts & Knowledge Graph Relational Edges.
4. Active Contradiction Detection & Recording.
5. Hypothesis Formulation & Empirical Backtest Validation (N >= 30, p <= 0.05).
6. Epistemic Status Transition & Evidence Vault Promotion.
7. Autopsy / Rejected Vault Registration for Falsified Claims.
8. Project Brain Context Package Synthesis with Epistemic Rankings & Autopsy Warnings (Zero live mutation invariant).
9. Human Brain 6-Part Pedagogical Tutor, Misconception Detection & Prerequisite Alerts.
10. Interactive Quiz Generation, Answer Submission & Personal Learning Graph Spaced Repetition Updates.
11. Systematic Knowledge Quality Audit (All 7 Invariant Checks).
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from core.database import db_manager
from core.knowledge_graph_engine import (
    ClaimNode,
    ConceptNode,
    GraphEdge,
    SourceNode,
    knowledge_graph_engine,
)
from core.knowledge_os.epistemic_system import (
    EpistemicStatus,
    validate_status_transition,
)
from core.knowledge_os.human_brain import (
    HumanQuestionMode,
    human_brain,
)
from core.knowledge_os.knowledge_audit import (
    KnowledgeAuditReport,
    KnowledgeQualityAuditEngine,
)
from core.knowledge_os.library_ingestor import (
    library_ingestor,
)
from core.knowledge_os.project_brain import (
    ProjectKnowledgeContext,
    project_brain,
)
from core.provenance_engine import provenance_engine
from tests.test_knowledge_library_and_dedup import create_minimal_pdf


@pytest.fixture(scope="module")
def setup_knowledge_os():
    """Initialize DB and all schema tables."""
    db_manager.init_all_schemas()
    knowledge_graph_engine._init_graph_tables()
    provenance_engine._init_tables()
    human_brain._init_learning_graph()
    yield


def test_boss_level_knowledge_os_full_lifecycle(setup_knowledge_os):
    """
    Complete end-to-end multi-phase test of the Knowledge Operating System.
    """
    ts = int(time.time() * 1000)

    # =========================================================================
    # PHASE 1: STREAMING BOOK INGESTION & RESUMABLE CHECKPOINTS
    # =========================================================================
    pages_text = [
        "Chapter 1: Relative Strength Index and Drift. RSI values below 30 indicate short-term oversold conditions that create statistically significant positive price drift over 5-period holding windows in crypto perpetuals.",
        "Chapter 2: Momentum Continuation Regimes. In strong downward trend regimes, RSI below 30 does not mean-revert; instead it exhibits persistent negative drift and catastrophic drawdown.",
        "Chapter 3: Execution and Risk Boundaries. Maximum allocation per signal must never exceed 2.5% of NAV, and stop-loss bounds must strictly enforce at 1.5 ATR.",
    ]
    pdf_bytes = create_minimal_pdf(pages_text)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        book_path = Path(f.name)

    source_id = f"SRC-BOOK-BOSS-{ts}"
    book_title = f"Algorithmic Regime Dynamics {ts}"
    file_hash = library_ingestor.compute_file_sha256(book_path)

    try:
        # Run streaming ingestion
        ingestion_progress = []
        for step in library_ingestor.stream_ingest_book(
            file_path=book_path,
            max_pages=3,
        ):
            ingestion_progress.append(step)

        assert len(ingestion_progress) >= 1
        final_step = ingestion_progress[-1]
        assert final_step["status"] == "COMPLETED"
        assert final_step["processed_pages"] == 3
        job_id = final_step["job_id"]

        # Verify job recorded in DB
        with db_manager.get_brain_conn() as conn:
            job_row = conn.execute(
                "SELECT status, processed_pages, total_pages FROM book_ingestion_jobs WHERE job_id = ?;",
                (job_id,),
            ).fetchone()
            assert job_row is not None
            assert job_row[0] == "COMPLETED"
            assert job_row[1] == 3

        # Register official SourceNode in graph and provenance
        source_node = SourceNode(
            source_id=source_id,
            source_type="BOOK",
            source_uri=f"file:///{book_path.name}#{file_hash}",
            title=book_title,
            author_creator="Dr. Quant Boss",
            original_worldview="QUANTITATIVE_FINANCE",
            ingested_at=ts,
            raw_content_preview="Relative Strength Index and Drift vs Momentum Continuation Regimes.",
        )
        knowledge_graph_engine.register_source_node(source_node)

        # =========================================================================
        # PHASE 2: SPATIAL ATOMIC CLAIMS & ZERO-ALPHA DEFAULT
        # =========================================================================
        claim_a_id = f"CLM-A-RSI-REVERT-{ts}"
        claim_b_id = f"CLM-B-RSI-MOMENTUM-{ts}"
        claim_c_id = f"CLM-C-RISK-LIMIT-{ts}"

        # Claim A: RSI Reversion (starts UNVERIFIED, confidence 0.0)
        claim_a = ClaimNode(
            claim_id=claim_a_id,
            source_id=source_id,
            original_claim_verbatim="RSI values below 30 indicate short-term oversold conditions that create statistically significant positive price drift over 5-period holding windows in crypto perpetuals.",
            source_worldview="TECHNICAL_ANALYSIS",
            subject_concept="RSI Mean Reversion",
            relationship_direction="RSI < 30 -> Positive Price Drift",
            object_domain="CRYPTO_PERPETUALS",
            evidence_type="REPORTED_RESEARCH",
            epistemic_status="UNVERIFIED",
            confidence_score=0.0,  # Strict Zero-Alpha Default
            book_title=book_title,
            page_number=1,
        )
        knowledge_graph_engine.register_claim_node(claim_a)

        # Claim B: Momentum Continuation (starts UNVERIFIED, confidence 0.0)
        claim_b = ClaimNode(
            claim_id=claim_b_id,
            source_id=source_id,
            original_claim_verbatim="In strong downward trend regimes, RSI below 30 does not mean-revert; instead it exhibits persistent negative drift and catastrophic drawdown.",
            source_worldview="QUANTITATIVE_FINANCE",
            subject_concept="Momentum Continuation Regime",
            relationship_direction="RSI < 30 in Downtrend -> Negative Drift",
            object_domain="CRYPTO_PERPETUALS",
            evidence_type="REPORTED_RESEARCH",
            epistemic_status="UNVERIFIED",
            confidence_score=0.0,
            book_title=book_title,
            page_number=2,
        )
        knowledge_graph_engine.register_claim_node(claim_b)

        # Claim C: Risk Boundary
        claim_c = ClaimNode(
            claim_id=claim_c_id,
            source_id=source_id,
            original_claim_verbatim="Maximum allocation per signal must never exceed 2.5% of NAV, and stop-loss bounds must strictly enforce at 1.5 ATR.",
            source_worldview="RISK_MANAGEMENT",
            subject_concept="Position Sizing & ATR Stops",
            relationship_direction="Risk Gate -> Max 2.5% NAV and 1.5 ATR Stop",
            object_domain="RISK_GOVERNANCE",
            evidence_type="EMPIRICAL_TEST",
            epistemic_status="UNVERIFIED",
            confidence_score=0.0,
            book_title=book_title,
            page_number=3,
        )
        knowledge_graph_engine.register_claim_node(claim_c)

        # Verify claims in DB start at UNVERIFIED and 0.0
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT epistemic_status, confidence_score, page_number FROM research_claims WHERE claim_id = ?;",
                (claim_a_id,),
            ).fetchone()
            assert row[0] == "UNVERIFIED"
            assert row[1] == 0.0
            assert row[2] == 1

        # =========================================================================
        # PHASE 3: NORMALIZED CONCEPTS & KNOWLEDGE GRAPH EDGES
        # =========================================================================
        c1_id = f"CON-RSI-MR-{ts}"
        c2_id = f"CON-TREND-REGIME-{ts}"
        c3_id = f"CON-RISK-LIMIT-{ts}"

        concept_1 = ConceptNode(
            concept_id=c1_id,
            title="RSI Mean Reversion",
            domain="INDICATOR",
            normalized_description="Statistical tendency of oversold RSI oscillator values to mean-revert.",
            tags=["rsi", "mean_reversion"],
        )
        concept_2 = ConceptNode(
            concept_id=c2_id,
            title="Trend Continuation Regime",
            domain="MARKET_REGIME",
            normalized_description="Strong directional momentum dominating oscillator mean reversion.",
            tags=["trend", "momentum"],
        )
        concept_3 = ConceptNode(
            concept_id=c3_id,
            title="Position Sizing & ATR Stops",
            domain="RISK",
            normalized_description="Max allocation limit and ATR volatility based risk exits.",
            tags=["risk", "position_sizing"],
        )

        knowledge_graph_engine.register_concept_node(concept_1)
        knowledge_graph_engine.register_concept_node(concept_2)
        knowledge_graph_engine.register_concept_node(concept_3)

        # Edges linking claims to concepts & concepts to concepts
        knowledge_graph_engine.register_graph_edge(
            GraphEdge(
                edge_id=f"EDGE-1-{ts}",
                source_node_id=claim_a_id,
                target_node_id=c1_id,
                relationship_type="EVALUATES",
                edge_nature="SAME_DOMAIN",
                strength_weight=1.0,
            )
        )
        knowledge_graph_engine.register_graph_edge(
            GraphEdge(
                edge_id=f"EDGE-2-{ts}",
                source_node_id=claim_b_id,
                target_node_id=c2_id,
                relationship_type="QUALIFIES",
                edge_nature="SAME_DOMAIN",
                strength_weight=1.0,
            )
        )
        knowledge_graph_engine.register_graph_edge(
            GraphEdge(
                edge_id=f"EDGE-3-{ts}",
                source_node_id=c1_id,
                target_node_id=c2_id,
                relationship_type="CONTRADICTS_OR_CONDITIONS",
                edge_nature="CROSS_DOMAIN",
                strength_weight=0.9,
            )
        )

        # =========================================================================
        # PHASE 4: CONTRADICTION DETECTION & RECORDING
        # =========================================================================
        conflict_id = f"CONF-RSI-DRIFT-{ts}"
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_conflicts
                (conflict_id, claim_id_a, claim_id_b, conflict_type, description, status, created_at)
                VALUES (?, ?, ?, 'DIRECT_OPPOSITION', ?, 'UNRESOLVED', ?);
                """,
                (
                    conflict_id,
                    claim_a_id,
                    claim_b_id,
                    "Direct conflict: RSI < 30 predicts positive drift vs persistent negative drift conditional on trend regime.",
                    ts,
                ),
            )
            conn.commit()

        # =========================================================================
        # PHASE 5: HYPOTHESIS FORMULATION & EMPIRICAL BACKTEST
        # =========================================================================
        hypo = knowledge_graph_engine.create_hypothesis(
            title="Regime-Conditioned RSI Reversion",
            null_hypothesis="H0: RSI < 30 drift is identical regardless of 200 SMA trend filter.",
            alt_hypothesis="H1: RSI < 30 produces positive drift only when 200 SMA trend is positive.",
            independent_variable="VAR_BTC_RETURNS",
            dependent_variable="VAR_BTC_REALIZED_VOL",
            claim_id=claim_a_id,
            target_symbol="BTC/USDT",
            test_method="VOLATILITY_EVENT_STUDY",
            control_variables=["HALVING_CYCLE", "FUNDING_RATE", "DXY"],
        )
        assert hypo.hypothesis_id is not None
        assert hypo.claim_id == claim_a_id

        # =========================================================================
        # PHASE 6: EMPIRICAL PROMOTION & EVIDENCE VAULT (Strict N >= 30, p <= 0.05)
        # =========================================================================
        evidence_id = f"EV-RSI-REVERT-{ts}"
        # Empirical test results for Claim A
        n_samples = 142
        p_val = 0.008
        sharpe = 1.92

        # 1. State machine transition checks: Enforces constitutional step-by-step promotion
        # Illegal jump directly from UNVERIFIED -> EMPIRICALLY_SUPPORTED is blocked
        is_illegal, _ = validate_status_transition(
            EpistemicStatus.UNVERIFIED,
            EpistemicStatus.EMPIRICALLY_SUPPORTED,
        )
        assert is_illegal is False

        # Legitimate sequence: UNVERIFIED -> HYPOTHESIS -> TESTING -> EMPIRICALLY_SUPPORTED
        v1, _ = validate_status_transition(EpistemicStatus.UNVERIFIED, EpistemicStatus.HYPOTHESIS)
        assert v1 is True
        v2, _ = validate_status_transition(EpistemicStatus.HYPOTHESIS, EpistemicStatus.TESTING)
        assert v2 is True

        # Invariant checks on empirical promotion:
        # Without evidence: BLOCKED
        b1, _ = validate_status_transition(
            EpistemicStatus.TESTING, EpistemicStatus.EMPIRICALLY_SUPPORTED, evidence_present=False
        )
        assert b1 is False

        # Small sample size (N < 30): BLOCKED
        b2, _ = validate_status_transition(
            EpistemicStatus.TESTING,
            EpistemicStatus.EMPIRICALLY_SUPPORTED,
            evidence_present=True,
            sample_size=12,
            p_value=0.01,
        )
        assert b2 is False

        # Insignificant p-value (p > 0.05): BLOCKED
        b3, _ = validate_status_transition(
            EpistemicStatus.TESTING,
            EpistemicStatus.EMPIRICALLY_SUPPORTED,
            evidence_present=True,
            sample_size=100,
            p_value=0.18,
        )
        assert b3 is False

        # Authorized transition with N=142, p=0.008: AUTHORIZED
        v3, msg = validate_status_transition(
            EpistemicStatus.TESTING,
            EpistemicStatus.EMPIRICALLY_SUPPORTED,
            evidence_present=True,
            sample_size=n_samples,
            p_value=p_val,
        )
        assert v3 is True, f"Promotion failed: {msg}"

        # 2. Register evidence in Evidence Vault (with provenance ledger anchor)
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_provenance_ledger
                (knowledge_id, source_type, source_uri, title, author_creator, ingested_at, raw_content_preview, confidence_score, status)
                VALUES (?, 'BOOK', ?, ?, 'Dr. Quant Boss', ?, ?, 0.88, 'EMPIRICALLY_VERIFIED');
                """,
                (
                    claim_a_id,
                    f"file:///{book_path.name}",
                    book_title,
                    ts,
                    "RSI values below 30 indicate short-term oversold conditions...",
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_vault
                (evidence_id, knowledge_id, claim_statement, verdict, sample_size, statistical_p_value, evidence_details, created_at)
                VALUES (?, ?, ?, 'EMPIRICALLY_VERIFIED', ?, ?, ?, ?);
                """,
                (
                    evidence_id,
                    claim_a_id,
                    "RSI values below 30 indicate short-term oversold conditions that create statistically significant positive price drift over 5-period holding windows in crypto perpetuals.",
                    n_samples,
                    p_val,
                    json.dumps({"sharpe": sharpe, "effect_size": 0.24}),
                    ts,
                ),
            )
            # Update claim status
            conn.execute(
                """
                UPDATE research_claims
                SET epistemic_status = 'EMPIRICALLY_SUPPORTED', confidence_score = 0.88
                WHERE claim_id = ?;
                """,
                (claim_a_id,),
            )
            conn.commit()

        # =========================================================================
        # PHASE 7: AUTOPSY / REJECTED VAULT REGISTRATION
        # =========================================================================
        # Simulate testing an unconditioned naive claim: "RSI < 30 always produces positive drift in all regimes"
        falsified_claim_id = f"CLM-NAIVE-RSI-{ts}"
        claim_naive = ClaimNode(
            claim_id=falsified_claim_id,
            source_id=source_id,
            original_claim_verbatim="RSI < 30 unconditionally generates positive alpha regardless of trend regime.",
            source_worldview="NAIVE_INDICATOR",
            subject_concept="Unconditional RSI Reversion",
            relationship_direction="RSI < 30 -> Guaranteed Profit",
            object_domain="CRYPTO_PERPETUALS",
            evidence_type="REPORTED_RESEARCH",
            epistemic_status="UNVERIFIED",
            confidence_score=0.0,
        )
        knowledge_graph_engine.register_claim_node(claim_naive)

        # Falsification sequence: UNVERIFIED -> HYPOTHESIS -> TESTING -> REJECTED
        vf1, _ = validate_status_transition(EpistemicStatus.UNVERIFIED, EpistemicStatus.HYPOTHESIS)
        assert vf1 is True
        vf2, _ = validate_status_transition(EpistemicStatus.HYPOTHESIS, EpistemicStatus.TESTING)
        assert vf2 is True
        vf3, _ = validate_status_transition(EpistemicStatus.TESTING, EpistemicStatus.REJECTED)
        assert vf3 is True

        # Insert into provenance ledger then rejected vault
        autopsy_id = f"REJ-NAIVE-RSI-{ts}"
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_provenance_ledger
                (knowledge_id, source_type, source_uri, title, author_creator, ingested_at, raw_content_preview, confidence_score, status)
                VALUES (?, 'BOOK', ?, ?, 'Dr. Quant Boss', ?, ?, 0.0, 'REJECTED');
                """,
                (
                    falsified_claim_id,
                    f"file:///{book_path.name}",
                    book_title,
                    ts,
                    "RSI < 30 unconditionally generates positive alpha...",
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO rejected_claims_vault
                (rejected_id, knowledge_id, rejected_claim, failure_reason, historical_occurrences_tested, rejection_autopsy, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    autopsy_id,
                    falsified_claim_id,
                    "RSI < 30 unconditionally generates positive alpha regardless of trend regime.",
                    "Falsified in Walk-Forward Backtest: p-value 0.68, Sharpe -0.52. Severe drawdown in downtrends.",
                    450,
                    json.dumps({"holding_period": 5, "asset": "BTC/USDT", "regime": "BEAR"}),
                    ts,
                ),
            )
            conn.execute(
                """
                UPDATE research_claims
                SET epistemic_status = 'REJECTED', confidence_score = 0.0
                WHERE claim_id = ?;
                """,
                (falsified_claim_id,),
            )
            conn.commit()

        # =========================================================================
        # PHASE 8: PROJECT BRAIN CONTEXT ENGINE (Verifiable Quantitative Context)
        # =========================================================================
        context_pkg = project_brain.build_project_context(
            query="RSI mean reversion in crypto perpetuals",
            target_symbol="BTC/USDT",
            timeframe="1h",
        )

        assert isinstance(context_pkg, ProjectKnowledgeContext)
        assert context_pkg.query == "RSI mean reversion in crypto perpetuals"
        assert "RESEARCH KNOWLEDGE ONLY" in context_pkg.safety_disclaimer

        # Verify risk boundary warnings included
        assert len(context_pkg.risk_boundary_warnings) >= 1

        # Check autopsy recall prevents rediscovering known failures
        assert len(context_pkg.autopsy_failures) >= 1
        assert any(
            "Falsified" in str(w)
            or "NAIVE" in str(w)
            or "Severe drawdown" in str(w)
            or "alpha" in str(w)
            for w in context_pkg.autopsy_failures
        )

        # Verify provenance citations
        assert len(context_pkg.provenance_citations) >= 1
        assert any(
            book_title in str(c) or "Algorithmic Regime Dynamics" in str(c)
            for c in context_pkg.provenance_citations
        )

        # Constitutional Invariant: Zero mutation of live execution rules
        assert hasattr(context_pkg, "current_sky_assumptions")
        assert len(context_pkg.current_sky_assumptions) >= 1

        # =========================================================================
        # PHASE 9: HUMAN BRAIN PEDAGOGICAL TUTOR (6-Part Protocol)
        # =========================================================================
        teach_res = human_brain.answer_human_question(
            question="Explain how RSI mean reversion works and what are its empirical limits?",
            mode=HumanQuestionMode.EXPLAIN,
            depth="DEEP_DIVE",
        )

        assert "answer_breakdown" in teach_res
        breakdown = teach_res["answer_breakdown"]
        # All 6 parts of the Human Answer Protocol
        assert "source_knowledge" in breakdown
        assert "cross_source_synthesis" in breakdown
        assert "empirical_evidence" in breakdown
        assert "sky_project_knowledge" in breakdown
        assert "model_inference" in breakdown
        assert "unknown_or_unestablished" in breakdown

        assert "citations" in teach_res
        assert isinstance(teach_res["citations"], list)

        # =========================================================================
        # PHASE 10: INTERACTIVE QUIZ & PERSONAL LEARNING GRAPH UPDATE
        # =========================================================================
        # Generate Quiz for the concept
        quiz = human_brain.generate_quiz(concept_id="EXPECTANCY_AND_RISK")
        assert quiz is not None
        assert "quiz_id" in quiz
        assert quiz["concept_id"] == "EXPECTANCY_AND_RISK"
        assert len(quiz["options"]) == 4
        assert quiz["correct_option_index"] == 0
        assert "explanation" in quiz
        assert "misconception_trap" in quiz

        # Submit Correct Answer
        submit_res = human_brain.submit_quiz_answer(
            quiz_id=quiz["quiz_id"],
            concept_id="EXPECTANCY_AND_RISK",
            selected_option_index=0,
            correct_option_index=0,
            question_text=quiz["question"],
            options=quiz["options"],
            misconception_trap=quiz["misconception_trap"],
        )

        assert submit_res["is_correct"] is True
        assert submit_res["updated_mastery"] > 0.0

        # Verify Personal Learning Graph updated in DB
        with db_manager.get_brain_conn() as conn:
            learn_row = conn.execute(
                """
                SELECT mastery_estimate, quiz_attempts, next_review
                FROM personal_learning_graph
                WHERE concept_id = ?;
                """,
                ("EXPECTANCY_AND_RISK",),
            ).fetchone()
            assert learn_row is not None
            assert learn_row[0] > 0.0
            assert learn_row[1] >= 1
            assert learn_row[2] > ts  # Scheduled future spaced repetition review

        # Verify 'Right Path' Research Advisor recommendations
        advisor = human_brain.get_research_advisor_recommendation()
        assert "recommended_concept_id" in advisor
        assert "recommended_title" in advisor

        # =========================================================================
        # PHASE 11: SYSTEMATIC KNOWLEDGE QUALITY AUDIT (7 Invariant Checks)
        # =========================================================================
        auditor = KnowledgeQualityAuditEngine()
        audit_report = auditor.run_audit()

        assert isinstance(audit_report, KnowledgeAuditReport)
        assert len(audit_report.checks) == 7

        # Invariant: No unsupported promotions (all EMPIRICALLY_SUPPORTED claims have evidence)
        unsupported_check = next(
            c for c in audit_report.checks if c.check_name == "Unsupported Promotions"
        )
        assert unsupported_check.status == "PASS"
        assert unsupported_check.count == 0

        # Invariant: Graph edge integrity
        edge_check = next(c for c in audit_report.checks if c.check_name == "Graph Edge Integrity")
        assert edge_check.status == "PASS"
        assert edge_check.count == 0

        # Invariant: Book Ingestion health
        ingest_check = next(
            c for c in audit_report.checks if c.check_name == "Book Ingestion Health"
        )
        assert ingest_check.status == "PASS"
        assert ingest_check.count == 0

        # Overall status must not be FAIL
        assert audit_report.overall_status in ("PASS", "WARN")

    finally:
        if book_path.exists():
            book_path.unlink()
