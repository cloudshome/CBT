"""
tests/test_hypothesis_falsifier.py
==================================
Unit tests for HypothesisFalsificationEngine:
1. Tests extraction of unverified claims from Research Wikipedia.
2. Runs empirical testing and verifies status transition to FACT or FALSIFIED.
3. Tests falsification telemetry report.
"""

from pathlib import Path

import pytest

from core.autonomous_research.hypothesis_falsifier import HypothesisFalsificationEngine
from core.knowledge_os.research_wikipedia import (
    EpistemicClaim,
    ResearchWikipediaEngine,
    WikiArticle,
)


@pytest.fixture
def temp_falsifier_env(tmp_path: Path):
    db_path = tmp_path / "test_wiki.db"
    wiki = ResearchWikipediaEngine(db_path=db_path)
    engine = HypothesisFalsificationEngine(wiki_engine=wiki)
    return engine, wiki


def test_falsification_batch_execution(temp_falsifier_env):
    falsifier, wiki = temp_falsifier_env

    # 1. Seed an unverified article & claim
    art = WikiArticle(
        article_id="art_test_falsify_01",
        title="Test Breakout Hypothesis",
        category="Quantitative Market Structure",
        source_url="https://test.arxiv.org/abs/12345",
        source_type="RESEARCH_DOCUMENT",
        provenance_id="PROV-TEST-01",
        author_or_speaker="Quant Researcher",
        executive_summary="Testing momentum persistence claim.",
        key_claims=[
            EpistemicClaim(
                claim_id="CLM-TEST-001",
                speaker_claim="BTC volatility breakout always yields 3R within 4 hours.",
                epistemic_status="[HYPOTHESIS] UNVERIFIED",
                cross_verification_evidence="",
                confidence_score=0.50,
            )
        ],
        wikilinks=[],
        tags=["test", "momentum"],
        contradictions_detected=[],
        macro_regime_implications="None",
        full_markdown_content="# Test Content",
        verification_score=60.0,
        created_at=1000000,
        updated_at=1000000,
    )
    wiki.save_article(art)

    # 2. Run falsification batch
    report = falsifier.run_falsification_batch(limit=1)
    assert report.claims_evaluated == 1
    assert len(report.results) == 1
    res = report.results[0]
    assert res.claim_id is not None
    assert res.new_status in ("EMPIRICALLY_VERIFIED_FACT", "FALSIFIED_REJECTED")

    # 3. Status check
    status = falsifier.get_status()
    assert status["status"] == "ACTIVE"
    assert status["last_batch"] is not None
