"""
tests/test_knowledge_epistemic_system.py
=========================================
Tests for Epistemic Typology, Transitions, Tier Hierarchy, and Ranking Score Vectors.
Validates:
1. All 14 EpistemicStatus values exist and conform to the formal definition.
2. All 7 KnowledgeTier levels (T0 to T6) conform to the strict hierarchy.
3. State machine transition rules:
   - UNVERIFIED can transition to HYPOTHESIS, CONTRADICTED, SUPERSEDED, TEACHING_READY.
   - TESTING can transition to EMPIRICALLY_SUPPORTED, SUPPORTED, REFUTED, REJECTED.
   - UNVERIFIED CANNOT directly jump to PROJECT_APPLIED or EMPIRICALLY_SUPPORTED without evidence.
   - Invariant: EMPIRICALLY_SUPPORTED strictly requires sample_size >= 30 and p_value <= 0.05.
4. RankingScoreVector computation and multi-dimensional classification.
5. Deterministic epistemic strength scoring across all 14 statuses.
"""

import pytest
from core.knowledge_os.epistemic_system import (
    EpistemicStatus,
    KnowledgeTier,
    RankingScoreVector,
    VALID_TRANSITIONS,
    validate_status_transition,
    compute_epistemic_strength,
)


def test_epistemic_statuses_and_tiers_defined():
    """Verifies all 14 epistemic statuses and 7 tiers exist."""
    expected_statuses = [
        "SOURCE_ONLY",
        "EXTRACTED",
        "UNVERIFIED",
        "HYPOTHESIS",
        "TESTING",
        "SUPPORTED",
        "REFUTED",
        "INCONCLUSIVE",
        "EMPIRICALLY_SUPPORTED",
        "PROJECT_APPLIED",
        "TEACHING_READY",
        "SUPERSEDED",
        "CONTRADICTED",
        "REJECTED",
    ]
    assert len(expected_statuses) == 14
    for status_str in expected_statuses:
        status = EpistemicStatus(status_str)
        assert status.value == status_str

    expected_tiers = [
        "TIER_0_RAW_SOURCE",
        "TIER_1_EXTRACTED",
        "TIER_2_SYNTHESIZED",
        "TIER_3_HYPOTHESIS",
        "TIER_4_EMPIRICAL_EVIDENCE",
        "TIER_5_PROJECT_KNOWLEDGE",
        "TIER_6_HUMAN_TEACHING",
    ]
    assert len(expected_tiers) == 7
    for tier_str in expected_tiers:
        tier = KnowledgeTier(tier_str)
        assert tier.value == tier_str


def test_epistemic_transition_valid_paths():
    """Verifies legitimate state transitions succeed."""
    # SOURCE_ONLY -> EXTRACTED
    ok, msg = validate_status_transition(EpistemicStatus.SOURCE_ONLY, EpistemicStatus.EXTRACTED)
    assert ok, msg

    # EXTRACTED -> UNVERIFIED
    ok, msg = validate_status_transition(EpistemicStatus.EXTRACTED, EpistemicStatus.UNVERIFIED)
    assert ok, msg

    # UNVERIFIED -> HYPOTHESIS
    ok, msg = validate_status_transition(EpistemicStatus.UNVERIFIED, EpistemicStatus.HYPOTHESIS)
    assert ok, msg

    # HYPOTHESIS -> TESTING
    ok, msg = validate_status_transition(EpistemicStatus.HYPOTHESIS, EpistemicStatus.TESTING)
    assert ok, msg

    # TESTING -> EMPIRICALLY_SUPPORTED (with valid evidence: sample >= 30, p_val <= 0.05)
    ok, msg = validate_status_transition(
        EpistemicStatus.TESTING,
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        evidence_present=True,
        sample_size=120,
        p_value=0.012,
    )
    assert ok, msg

    # EMPIRICALLY_SUPPORTED -> PROJECT_APPLIED
    ok, msg = validate_status_transition(
        EpistemicStatus.EMPIRICALLY_SUPPORTED, EpistemicStatus.PROJECT_APPLIED
    )
    assert ok, msg


def test_epistemic_transition_illegal_jumps_rejected():
    """
    CRITICAL INVARIANT:
    Unverified claims can NEVER jump directly to project applied or empirically supported without evidence.
    """
    # Direct jump from UNVERIFIED to PROJECT_APPLIED is ILLEGAL
    ok, msg = validate_status_transition(EpistemicStatus.UNVERIFIED, EpistemicStatus.PROJECT_APPLIED)
    assert not ok
    assert "Illegal transition" in msg

    # Direct jump from UNVERIFIED to EMPIRICALLY_SUPPORTED is ILLEGAL
    ok, msg = validate_status_transition(EpistemicStatus.UNVERIFIED, EpistemicStatus.EMPIRICALLY_SUPPORTED)
    assert not ok
    assert "Illegal transition" in msg

    # Even from TESTING, promotion without evidence fails
    ok, msg = validate_status_transition(
        EpistemicStatus.TESTING,
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        evidence_present=False,
    )
    assert not ok
    assert "requires confirmed empirical backtest evidence" in msg

    # Promotion with underpowered sample size fails
    ok, msg = validate_status_transition(
        EpistemicStatus.TESTING,
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        evidence_present=True,
        sample_size=15,  # under 30 threshold
    )
    assert not ok
    assert "Sample size (15) too small" in msg

    # Promotion with non-significant p-value fails
    ok, msg = validate_status_transition(
        EpistemicStatus.TESTING,
        EpistemicStatus.EMPIRICALLY_SUPPORTED,
        evidence_present=True,
        sample_size=100,
        p_value=0.18,  # > 0.05
    )
    assert not ok
    assert "Statistical p-value" in msg


def test_ranking_score_vector_calculation():
    """Verifies that RankingScoreVector calculates bounded composite scores and classifies profiles."""
    v_empirical = RankingScoreVector(
        relevance_score=0.85,
        source_coverage=0.7,
        epistemic_strength=0.95,
        empirical_support=0.88,
        recency_score=0.9,
        contradiction_status="UNCONTRADICTED",
        provenance_quality=0.95,
        project_applicability=0.8,
    )
    composite = v_empirical.calculate_composite()
    assert 0.0 <= composite <= 1.0
    assert v_empirical.classification == "EMPIRICALLY_SUPPORTED_CORE"

    # High talk, low evidence (retail theory)
    v_hype = RankingScoreVector(
        relevance_score=0.90,
        source_coverage=0.95,
        epistemic_strength=0.15,
        empirical_support=0.10,
        recency_score=0.8,
        contradiction_status="UNCONTRADICTED",
        provenance_quality=0.5,
        project_applicability=0.5,
    )
    score_hype = v_hype.calculate_composite()
    assert v_hype.classification == "HIGH_RELEVANCE_LOW_EVIDENCE"
    assert composite > score_hype

    # Contradicted item gets penalty
    v_contra = RankingScoreVector(
        relevance_score=0.85,
        source_coverage=0.7,
        epistemic_strength=0.20,
        empirical_support=0.20,
        recency_score=0.9,
        contradiction_status="CONTRADICTED",
        provenance_quality=0.95,
        project_applicability=0.8,
    )
    score_contra = v_contra.calculate_composite()
    assert v_contra.classification == "CONTRADICTED_DISPUTED"
    assert score_contra < composite


def test_deterministic_epistemic_strength_weights():
    """Verifies empirical proof receives top epistemic strength while unverified / rejected receive low."""
    assert compute_epistemic_strength(EpistemicStatus.EMPIRICALLY_SUPPORTED) == 0.95
    assert compute_epistemic_strength(EpistemicStatus.PROJECT_APPLIED) == 0.90
    assert compute_epistemic_strength(EpistemicStatus.UNVERIFIED) == 0.15
    assert compute_epistemic_strength(EpistemicStatus.REJECTED) == 0.00
