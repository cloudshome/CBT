"""
tests/test_research_wiki_ledger.py
==================================
Adversarial Verification & Quality Gate Tests for Phase 1:
Institutional Research Wikipedia Relational Ledger, Versioning, Citations & Triage.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.knowledge_os.research_wikipedia import (
    EpistemicClaim,
    ResearchWikipediaEngine,
    WikiArticle,
)


@pytest.fixture
def temp_wiki_engine(tmp_path: Path) -> ResearchWikipediaEngine:
    db_file = tmp_path / "test_research_wiki.db"
    articles_dir = tmp_path / "articles"
    engine = ResearchWikipediaEngine(db_path=db_file, articles_dir=articles_dir)
    return engine


def test_immutable_version_incrementing(temp_wiki_engine: ResearchWikipediaEngine):
    """Invariant: Every save_article call increments the version in wiki_article_versions without mutating past history."""
    art = WikiArticle(
        article_id="art_macro_liquidity_01",
        title="US Treasury General Account Liquidity Drain",
        category="Monetary & Debt",
        source_url="https://example.com/macro-note-1",
        source_type="WEB_ARTICLE",
        provenance_id="PROV-TEST-001",
        author_or_speaker="Macro Quant Desk",
        executive_summary="TGA drain injects net reserves into the commercial banking system.",
        key_claims=[
            EpistemicClaim(
                claim_id="C-01",
                speaker_claim="TGA drain increased banking reserves by $50B in Q1.",
                epistemic_status="FACT",
                cross_verification_evidence="Empirical FRED WTREGEN series match.",
                confidence_score=0.95,
            )
        ],
        wikilinks=["[[US Treasury Liquidity]]", "[[Reverse Repo Drain]]"],
        tags=["macro", "liquidity", "tga"],
        contradictions_detected=[],
        macro_regime_implications="Expansionary reserve liquidity bias for crypto beta.",
        full_markdown_content="# US Treasury General Account Liquidity Drain\n\nSee [[US Treasury Liquidity]] and [[Reverse Repo Drain]].",
        verification_score=95.0,
    )

    # First save -> Version 1
    temp_wiki_engine.save_article(art)
    versions_v1 = temp_wiki_engine.get_article_versions("art_macro_liquidity_01")
    assert len(versions_v1) == 1
    assert versions_v1[0]["version"] == 1
    assert versions_v1[0]["article_id"] == "art_macro_liquidity_01"

    # Modify content and save again -> Version 2
    art.full_markdown_content += "\n\nAdditional paragraph updating the debt ceiling analysis."
    temp_wiki_engine.save_article(art)

    versions_v2 = temp_wiki_engine.get_article_versions("art_macro_liquidity_01")
    assert len(versions_v2) == 2
    assert versions_v2[0]["version"] == 2
    assert versions_v2[1]["version"] == 1
    assert "debt ceiling analysis" in versions_v2[0]["content_markdown"]
    assert "debt ceiling analysis" not in versions_v2[1]["content_markdown"]


def test_bidirectional_wikilinks_indexing(temp_wiki_engine: ResearchWikipediaEngine):
    """Invariant: Markdown [[Target|Anchor]] WikiLinks must be extracted and indexed into wiki_links."""
    art = WikiArticle(
        article_id="art_order_flow_01",
        title="Order Flow Imbalance and VPIN Microstructure",
        category="Market Structure",
        source_url="https://example.com/vpin-paper",
        source_type="JOURNAL_PAPER",
        provenance_id="PROV-TEST-002",
        author_or_speaker="Easley et al.",
        executive_summary="Volume-synchronized Probability of Toxicity identifies adverse selection.",
        key_claims=[],
        wikilinks=["[[Volume-Synchronized Probability of Toxicity]]", "[[Bid-Ask Spread Asymmetry|Adverse Selection]]"],
        tags=["microstructure", "vpin"],
        contradictions_detected=[],
        macro_regime_implications="Microstructure toxicity spikes precede violent liquidations.",
        full_markdown_content="""
        # VPIN Microstructure
        We apply [[Volume-Synchronized Probability of Toxicity]] to measure order toxicity.
        See also [[Bid-Ask Spread Asymmetry|Adverse Selection]] during volatile sweeps.
        """,
        verification_score=90.0,
    )

    temp_wiki_engine.save_article(art)
    links = temp_wiki_engine.get_article_links("art_order_flow_01")
    assert len(links) == 2

    slugs = {l["target_slug"] for l in links}
    assert "volume-synchronized-probability-of-toxicity" in slugs
    assert "bid-ask-spread-asymmetry" in slugs

    anchors = {l["anchor_text"] for l in links}
    assert "Volume-Synchronized Probability of Toxicity" in anchors
    assert "Adverse Selection" in anchors


def test_provenance_citations_recording(temp_wiki_engine: ResearchWikipediaEngine):
    """Invariant: Claims attached to an article must record provenance citations."""
    art = WikiArticle(
        article_id="art_fvg_01",
        title="Fair Value Gap Microstructure Mechanics",
        category="Market Structure",
        source_url="https://example.com/fvg-analysis",
        source_type="RESEARCH_NOTE",
        provenance_id="PROV-TEST-003",
        author_or_speaker="ICT Research Review",
        executive_summary="Three-candle displacement gaps represent single-sided orderbook liquidity voids.",
        key_claims=[
            EpistemicClaim(
                claim_id="C-FVG-01",
                speaker_claim="FVGs refill with 72% probability within 48 hours.",
                epistemic_status="HYPOTHESIS",
                cross_verification_evidence="Pending CPCV walk-forward backtest.",
                confidence_score=0.60,
            )
        ],
        wikilinks=[],
        tags=["fvg", "liquidity"],
        contradictions_detected=[],
        macro_regime_implications="Mean reversion expected toward unfilled imbalance.",
        full_markdown_content="# FVG Mechanics\n\nDetailed breakdown of 3-candle imbalance.",
        verification_score=60.0,
    )

    temp_wiki_engine.save_article(art)
    citations = temp_wiki_engine.get_article_citations("art_fvg_01")
    assert len(citations) == 1
    assert citations[0]["claim_id"] == "C-FVG-01"
    assert citations[0]["epistemic_level"] == "HYPOTHESIS"
    assert "72% probability" in citations[0]["exact_quote"]


def test_dialectical_contradictions_tracking(temp_wiki_engine: ResearchWikipediaEngine):
    """Invariant: Contradictory claims can be registered and retrieved across articles."""
    cid = temp_wiki_engine.record_contradiction(
        article_id="art_breakout_regime",
        claim_a_id="claim_asian_breakout_pos",
        claim_b_id="claim_asian_breakout_neg",
        contradiction_nature="EMPIRICAL_DISAGREEMENT",
        resolution_status="OPEN",
        resolution_notes="Disagreement conditioned on ATR volatility regime.",
    )
    assert cid.startswith("contra_")

    all_contra = temp_wiki_engine.get_contradictions("art_breakout_regime")
    assert len(all_contra) == 1
    assert all_contra[0]["contradiction_nature"] == "EMPIRICAL_DISAGREEMENT"
    assert all_contra[0]["resolution_status"] == "OPEN"
    assert "ATR volatility regime" in all_contra[0]["resolution_notes"]


def test_human_in_the_loop_triage_inbox(temp_wiki_engine: ResearchWikipediaEngine):
    """Invariant: Autonomous research discoveries enter STAGING and require human status transitions."""
    item_id = temp_wiki_engine.add_to_triage_inbox(
        candidate_title="Ethena USDe Delta-Neutral Basis Arbitrage",
        candidate_summary="Investigates funding rate basis compression risks on centralized perpetual futures.",
        source_url="https://example.com/ethena-basis-risk",
        source_domain="example.com",
        proposed_category="Crypto Liquidity",
        extracted_claims=[
            {"claim": "Negative funding rates drain insurance fund", "epistemic": "HYPOTHESIS"}
        ],
        source_id="src_ethena_01",
    )
    assert item_id.startswith("tri_")

    # Listed under STAGING
    staging_items = temp_wiki_engine.list_triage_inbox(status="STAGING")
    assert any(it["item_id"] == item_id for it in staging_items)

    # Approve item
    updated = temp_wiki_engine.update_triage_status(item_id, "APPROVED")
    assert updated is True

    # No longer in STAGING
    staging_after = temp_wiki_engine.list_triage_inbox(status="STAGING")
    assert not any(it["item_id"] == item_id for it in staging_after)

    # Present in APPROVED
    approved_items = temp_wiki_engine.list_triage_inbox(status="APPROVED")
    assert any(it["item_id"] == item_id for it in approved_items)


def test_fastapi_routes_integration():
    """Invariant: REST endpoints for versions, citations, links, contradictions, and triage are healthy."""
    from app import app

    client = TestClient(app)

    # 1. Triage Inbox GET
    triage_resp = client.get("/api/knowledge/wiki/triage")
    assert triage_resp.status_code == 200
    assert "items" in triage_resp.json()

    # 2. Contradictions GET
    contra_resp = client.get("/api/knowledge/wiki/contradictions")
    assert contra_resp.status_code == 200
    assert "contradictions" in contra_resp.json()

    # 3. Post a candidate to triage
    post_triage = client.post(
        "/api/knowledge/wiki/triage",
        json={
            "candidate_title": "Test REST Triage Candidate",
            "candidate_summary": "Summary of discovered research candidate.",
            "source_url": "https://example.com/candidate-test",
            "source_domain": "example.com",
            "proposed_category": "Macro Geopolitics & Hegemony",
            "extracted_claims": [{"claim": "Test claim", "epistemic": "FACT"}],
            "source_id": "src_rest_test",
        },
    )
    assert post_triage.status_code == 200
    item_id = post_triage.json()["item_id"]

    # 4. Patch triage candidate status
    patch_resp = client.patch(
        f"/api/knowledge/wiki/triage/{item_id}",
        json={"status": "APPROVED"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["new_status"] == "APPROVED"
