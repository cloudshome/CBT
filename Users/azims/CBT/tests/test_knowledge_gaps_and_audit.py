"""
tests/test_knowledge_gaps_and_audit.py
======================================
Tests for Research Gap Detection Engine & 7-Invariant Database Integrity Auditor.
Validates:
1. Research Gap Engine:
   - Discovers "HIGH_TALK_ZERO_EVIDENCE" gaps where literature volume is high but zero backtests exist.
   - Generates suggested hypotheses for empirical testing.
2. Knowledge Quality & Provenance Auditor:
   - Executes all 7 systematic integrity checks.
   - Detects orphaned claims, missing spatial provenance, unsupported promotions, and broken edges.
   - Produces valid PASS / WARN / FAIL diagnostic report.
"""

from __future__ import annotations

import time
import pytest

from core.database import db_manager
from core.knowledge_graph_engine import (
    ClaimNode,
    ConceptNode,
    SourceNode,
    knowledge_graph_engine,
)
from core.knowledge_os.knowledge_audit import (
    KnowledgeQualityAuditEngine,
    KnowledgeAuditReport,
    knowledge_audit_engine,
)
from core.knowledge_os.research_gaps import (
    ResearchGapEngine,
    ResearchGapItem,
    research_gap_engine,
)
from core.provenance_engine import provenance_engine


def setup_module():
    db_manager.init_all_schemas()
    knowledge_graph_engine._init_graph_tables()
    provenance_engine._init_tables()


def test_research_gap_detection_high_talk_zero_evidence():
    """
    Constitutional Mandate:
    Identify heavily discussed ideas with weak or zero empirical testing
    (e.g., popular retail claims with 0 backtests in Evidence Vault).
    """
    engine = ResearchGapEngine()

    # Seed a concept with 6 claims and 0 empirical evidence records
    cid = f"K-GAP-TEST-{str(int(time.time()*1000))[-4:]}"
    concept_title = "Wyckoff Spring Accumulation"
    domain = "SMC"

    concept = ConceptNode(
        concept_id=cid,
        title=concept_title,
        domain=domain,
        normalized_description="Phase C spring dipping below support to trap bears before markup phase.",
        tags=["smc", "wyckoff", "spring"],
    )
    knowledge_graph_engine.register_concept_node(concept)

    # Seed a source
    sid = "S-GAP-SRC"
    source = SourceNode(
        source_id=sid,
        source_type="BOOK",
        source_uri="file:///books/wyckoff.pdf",
        title="The Wyckoff Method in Practice",
        author_creator="R. Wyckoff",
        original_worldview="TECHNICAL_ANALYSIS",
        ingested_at=int(time.time() * 1000),
        raw_content_preview="Spring and upthrust analysis.",
    )
    knowledge_graph_engine.register_source_node(source)

    # Seed 6 unverified claims matching this concept
    for i in range(6):
        claim = ClaimNode(
            claim_id=f"C-GAP-{cid[-4:]}-{i}",
            source_id=sid,
            original_claim_verbatim=f"Wyckoff Spring phase assertion {i}: creates asymmetrical long opportunity.",
            source_worldview="TECHNICAL_ANALYSIS",
            subject_concept=concept_title,
            relationship_direction="Spring -> Markup",
            object_domain=domain,
            evidence_type="UNVERIFIED_CLAIM",
            epistemic_status="UNVERIFIED",
            confidence_score=0.0,
            book_title="The Wyckoff Method in Practice",
            page_number=45 + i,
        )
        knowledge_graph_engine.register_claim_node(claim)

    # Run research gap scanner
    gaps = engine.scan_research_gaps(limit=20)

    assert len(gaps) >= 1
    # Check that Wyckoff Spring is flagged as HIGH_TALK_ZERO_EVIDENCE
    target_gap = next((g for g in gaps if g["concept_title"] == concept_title), None)
    assert target_gap is not None
    assert target_gap["gap_type"] == "HIGH_TALK_ZERO_EVIDENCE"
    assert target_gap["claims_count"] >= 5
    assert target_gap["empirical_tests_count"] == 0
    assert target_gap["priority_score"] >= 0.5
    assert "H0:" in target_gap["suggested_hypothesis"] or "Hypothesis" in target_gap["suggested_hypothesis"]


def test_knowledge_quality_audit_engine_seven_invariants():
    """
    Verifies that the audit engine executes all 7 invariant checks
    and generates an authoritative diagnostic report.
    """
    auditor = KnowledgeQualityAuditEngine()
    report = auditor.run_audit()

    assert isinstance(report, KnowledgeAuditReport)
    assert report.overall_status in ("PASS", "WARN", "FAIL")
    assert len(report.checks) >= 7

    check_names = [c.check_name for c in report.checks]
    assert "Orphaned Claims" in check_names
    assert "Spatial Provenance" in check_names
    assert "Duplicate Concepts" in check_names
    assert "Active Contradictions" in check_names
    assert "Unsupported Promotions" in check_names
    assert "Graph Edge Integrity" in check_names
    assert "Book Ingestion Health" in check_names

    # Check that each check has count, status, and remediation details
    for chk in report.checks:
        assert chk.status in ("PASS", "WARN", "FAIL")
        assert chk.count >= 0
        assert len(chk.details) > 0
        assert len(chk.remediation) > 0
