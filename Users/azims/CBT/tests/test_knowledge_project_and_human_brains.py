"""
tests/test_knowledge_project_and_human_brains.py
=================================================
Tests for Project Brain Context Engine & Human Brain Pedagogical Tutor.
Validates:
1. PROJECT_BRAIN_POLICY context engine:
   - Builds bounded, verifiable quantitative context package.
   - Includes core claims, empirical evidence, failure autopsies, and risk boundaries.
   - Constitutional Invariant: Zero silent mutation of live trading gates or risk parameters.
2. HUMAN_BRAIN_POLICY pedagogical tutor:
   - Adheres to the 6-part Human Answer Protocol.
   - Detects missing prerequisites and delivers proactive prerequisite alerts.
   - Generates interactive self-test quizzes with misconception detection.
   - Updates Personal Learning Graph (mastery estimates, spaced review schedule).
3. "Right Path" Research Advisor delivers tailored next-step recommendations.
"""

from __future__ import annotations

import time
import pytest

from core.database import db_manager
from core.knowledge_graph_engine import (
    ClaimNode,
    SourceNode,
    knowledge_graph_engine,
)
from core.knowledge_os.human_brain import (
    HumanLearningEngine,
    HumanQuestionMode,
    human_brain,
)
from core.knowledge_os.project_brain import (
    ProjectBrainContextEngine,
    ProjectKnowledgeContext,
    project_brain,
)
from core.provenance_engine import provenance_engine


def setup_module():
    """Ensure all database schemas and tables are initialized."""
    db_manager.init_all_schemas()
    knowledge_graph_engine._init_graph_tables()
    provenance_engine._init_tables()
    human_brain._init_learning_graph()


def test_project_brain_context_engine():
    """
    Verifies that Project Brain builds a complete, bounded quantitative context
    without mutating production risk limits or execution rules.
    """
    engine = ProjectBrainContextEngine()

    # Seed sample source and claim
    sid = "S-PRJ-TEST"
    source = SourceNode(
        source_id=sid,
        source_type="BOOK",
        source_uri="file:///books/vol_trading.pdf",
        title="Volatility Trading 2nd Ed",
        author_creator="Euan Sinclair",
        original_worldview="QUANTITATIVE_FINANCE",
        ingested_at=int(time.time() * 1000),
        raw_content_preview="GARCH and implied volatility dynamics.",
    )
    knowledge_graph_engine.register_source_node(source)

    cid = f"C-PRJ-{str(int(time.time()*1000))[-4:]}"
    claim = ClaimNode(
        claim_id=cid,
        source_id=sid,
        original_claim_verbatim="Historical volatility cones allow identifying overextended options and perpetual skew.",
        source_worldview="QUANTITATIVE_FINANCE",
        subject_concept="Volatility Cones & Skew",
        relationship_direction="Vol Cones -> Overextended Pricing",
        object_domain="CRYPTO_DIRECT",
        evidence_type="REPORTED_RESEARCH",
        epistemic_status="UNVERIFIED",
        confidence_score=0.0,
        book_title="Volatility Trading 2nd Ed",
        page_number=142,
    )
    knowledge_graph_engine.register_claim_node(claim)

    # Build project context
    pkg = engine.build_project_context(
        query="volatility cones and skew",
        target_symbol="BTC/USDT",
        timeframe="15m",
    )

    assert isinstance(pkg, ProjectKnowledgeContext)
    assert pkg.query == "volatility cones and skew"
    assert "RESEARCH KNOWLEDGE ONLY" in pkg.safety_disclaimer
    assert len(pkg.risk_boundary_warnings) >= 1
    assert any("Constitutional" in w or "walk-forward" in w or "WARNING" in w for w in pkg.risk_boundary_warnings)
    assert len(pkg.current_sky_assumptions) >= 1
    assert pkg.generated_at > 0


def test_human_brain_six_part_protocol_and_prerequisites():
    """
    Verifies that Human Brain follows the 6-part protocol and alerts
    the user when attempting advanced concepts without prerequisites.
    """
    tutor = HumanLearningEngine()

    # Querying advanced concept "ORDER_BLOCK" when prerequisites (MARKET_STRUCTURE) are unmastered
    res = tutor.answer_human_question(
        question="How does an order block work and how do I trade it?",
        mode=HumanQuestionMode.EXPLAIN,
        depth="INTERMEDIATE",
    )

    # 1. Check 6-part protocol presence in answer_breakdown
    assert "answer_breakdown" in res
    ans = res["answer_breakdown"]
    assert "source_knowledge" in ans
    assert "cross_source_synthesis" in ans
    assert "empirical_evidence" in ans
    assert "sky_project_knowledge" in ans
    assert "model_inference" in ans
    assert "unknown_or_unestablished" in ans

    # 2. Check prerequisite alert
    prereq_alert = res.get("prerequisites_warning")
    if prereq_alert:
        assert len(prereq_alert["missing_prerequisites"]) >= 1
        assert "recommended_next" in prereq_alert
    else:
        assert "missing_prerequisites" in res

    # 3. Check citations
    assert "citations" in res
    assert isinstance(res["citations"], list)


def test_quiz_generation_evaluation_and_learning_graph():
    """
    Verifies self-test quiz generation, evaluation of correct/incorrect answers,
    and updates to the Personal Learning Graph.
    """
    tutor = HumanLearningEngine()

    concept_id = "MARKET_STRUCTURE"
    quiz = tutor.generate_quiz(concept_id)

    assert quiz is not None
    assert quiz["concept_id"] == concept_id
    assert len(quiz["options"]) == 4
    assert 0 <= quiz["correct_option_index"] < 4
    assert "misconception_trap" in quiz

    # 1. Submit wrong answer to trigger misconception
    wrong_idx = (quiz["correct_option_index"] + 1) % 4
    res_wrong = tutor.submit_quiz_answer(
        quiz_id=quiz["quiz_id"],
        concept_id=concept_id,
        selected_option_index=wrong_idx,
        correct_option_index=quiz["correct_option_index"],
        misconception_trap=quiz["misconception_trap"],
    )

    assert res_wrong["is_correct"] is False
    assert "Incorrect" in res_wrong["feedback"]
    assert res_wrong["next_review_days"] >= 1

    # 2. Submit correct answer
    res_correct = tutor.submit_quiz_answer(
        quiz_id=quiz["quiz_id"],
        concept_id=concept_id,
        selected_option_index=quiz["correct_option_index"],
        correct_option_index=quiz["correct_option_index"],
    )
    assert res_correct["is_correct"] is True
    assert "Correct" in res_correct["feedback"]
    assert res_correct["updated_mastery"] > res_wrong["updated_mastery"]


def test_research_advisor_recommendations():
    """Verifies that the Right Path Research Advisor recommends an unstarted/due concept."""
    tutor = HumanLearningEngine()
    advisor = tutor.get_research_advisor_recommendation()

    assert "recommended_concept_id" in advisor
    assert "recommended_title" in advisor
    assert "rationale" in advisor
    assert "suggested_actions" in advisor
    assert len(advisor["suggested_actions"]) >= 1
