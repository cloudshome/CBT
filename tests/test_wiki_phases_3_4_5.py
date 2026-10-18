"""
tests/test_wiki_phases_3_4_5.py
================================
Adversarial Verification & Quality Gate Tests for Phases 3, 4, 5:
- Phase 3: Bidirectional WikiLinks, Backlinks Indexing, Contradiction Tracking & Specialized Schemas.
- Phase 4: Human-in-the-Loop Triage Inbox Desk (Staging -> Merging) & Strategy Bridge.
- Phase 5: Terminal Workstation Command Bar & Integration Stability.
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
    db_file = tmp_path / "test_wiki_345.db"
    articles_dir = tmp_path / "articles_345"
    engine = ResearchWikipediaEngine(db_path=db_file, articles_dir=articles_dir)
    return engine


def test_bidirectional_backlinks_indexing(temp_wiki_engine: ResearchWikipediaEngine):
    """
    Phase 3: When Article A links to Article B via [[Target Title|Anchor]],
    querying backlinks for Target Title must return Article A.
    """
    art_a = WikiArticle(
        article_id="art_alpha_flow_01",
        title="L2 Orderbook Skew Factor",
        category="Quantitative Market Structure",
        source_url="https://example.com/flow-factor",
        source_type="RESEARCH_PAPER",
        provenance_id="PROV-ALPHA-01",
        author_or_speaker="Quant Researcher",
        executive_summary="Microstructure order flow imbalance factor.",
        key_claims=[
            EpistemicClaim(
                claim_id="CLM-01",
                speaker_claim="OBI elasticity predicts 1-minute delta with 58% accuracy.",
                epistemic_status="FACT",
                cross_verification_evidence="L2 tick data backtest.",
                confidence_score=0.92,
            )
        ],
        wikilinks=[
            "[[Market Regime Transition|Regime Switch]]",
            "[[Execution Venue Microstructure]]",
        ],
        tags=["orderbook", "microstructure"],
        contradictions_detected=[],
        macro_regime_implications="High efficacy during volatile expansion regimes.",
        full_markdown_content="# L2 Orderbook Skew Factor\n\nSee [[Market Regime Transition|Regime Switch]].",
        verification_score=88.0,
    )
    temp_wiki_engine.save_article(art_a)

    # Query backlinks for target title "Market Regime Transition"
    backlinks = temp_wiki_engine.get_backlinks("Market Regime Transition")
    assert len(backlinks) == 1
    assert backlinks[0]["source_article_id"] == "art_alpha_flow_01"
    assert backlinks[0]["source_title"] == "L2 Orderbook Skew Factor"
    assert backlinks[0]["anchor_text"] == "Regime Switch"


def test_contradiction_automatic_recording(temp_wiki_engine: ResearchWikipediaEngine):
    """
    Phase 3: When an article contains contradictions_detected, save_article must
    automatically record them in the wiki_contradictions table with OPEN status.
    """
    art_contra = WikiArticle(
        article_id="art_macro_disagreement_01",
        title="Federal Reserve Balance Sheet Runoff Discrepancy",
        category="Monetary Policy & Debt Cycles",
        source_url="https://example.com/fed-notes",
        source_type="WEB_ARTICLE",
        provenance_id="PROV-FED-01",
        author_or_speaker="Macro Analyst",
        executive_summary="Divergence in reported Fed QT runoff pace.",
        key_claims=[
            EpistemicClaim(
                claim_id="CLM-FED-A",
                speaker_claim="Fed QT runoff pace was reduced to $25B monthly.",
                epistemic_status="FACT",
                cross_verification_evidence="FOMC statement reference.",
                confidence_score=0.90,
            ),
            EpistemicClaim(
                claim_id="CLM-FED-B",
                speaker_claim="Fed balance sheet expanded by $10B in bank term repo.",
                epistemic_status="FACT",
                cross_verification_evidence="H.4.1 release table.",
                confidence_score=0.90,
            ),
        ],
        wikilinks=[],
        tags=["fed", "qt"],
        contradictions_detected=[
            "Fed announced QT taper to $25B, but H.4.1 ledger shows total liquidity expansion via BTFP runoff offset."
        ],
        macro_regime_implications="Mixed monetary impulses.",
        full_markdown_content="# Federal Reserve Balance Sheet Runoff Discrepancy",
        verification_score=85.0,
    )
    temp_wiki_engine.save_article(art_contra)

    # Query contradictions for this article
    tracked = temp_wiki_engine.get_contradictions("art_macro_disagreement_01")
    assert len(tracked) == 1
    assert tracked[0]["article_id"] == "art_macro_disagreement_01"
    assert tracked[0]["resolution_status"] == "OPEN"
    assert "taper" in tracked[0]["contradiction_nature"]


def test_triage_inbox_merge_lifecycle(temp_wiki_engine: ResearchWikipediaEngine):
    """
    Phase 4: A candidate in wiki_triage_inbox can be approved and merged into a
    fully recorded WikiArticleDetail with version history and status 'MERGED'.
    """
    item_id = temp_wiki_engine.add_to_triage_inbox(
        candidate_title="Cross-Border Stablecoin Remittance Arbitrage",
        candidate_summary="USDT vs Local FX settlement premia in emerging markets.",
        source_url="https://example.com/arbitrage-research",
        source_domain="example.com",
        proposed_category="Crypto & Decentralized Settlement",
        extracted_claims=[
            {"claim": "Local FX trades at a persistent 2.5% premium to off-shore spot."}
        ],
    )

    # Verify staged item
    staged = temp_wiki_engine.list_triage_inbox(status="STAGING")
    assert any(x["item_id"] == item_id for x in staged)

    # Merge candidate
    merged = temp_wiki_engine.merge_triage_item(item_id)
    assert merged is not None
    assert merged["title"] == "Cross-Border Stablecoin Remittance Arbitrage"

    # Verify triage status updated to MERGED
    staged_after = temp_wiki_engine.list_triage_inbox(status="STAGING")
    assert not any(x["item_id"] == item_id for x in staged_after)

    merged_items = temp_wiki_engine.list_triage_inbox(status="MERGED")
    assert any(x["item_id"] == item_id for x in merged_items)


def test_rest_endpoints_backlinks_and_merge(
    temp_wiki_engine: ResearchWikipediaEngine, monkeypatch: pytest.MonkeyPatch
):
    """
    Phase 4 & 5: Verifies REST routing for /wiki/article/{id}/backlinks and /wiki/triage/{id}/merge.
    """
    from fastapi import FastAPI

    import core.knowledge_os.research_wikipedia as rw_mod
    from core.knowledge_os.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Mock engine
    monkeypatch.setattr(rw_mod, "research_wikipedia_engine", temp_wiki_engine)

    # 1. Add article with WikiLink
    art = WikiArticle(
        article_id="art_test_src_01",
        title="SMC Order Block Analysis",
        category="Quantitative Market Structure",
        source_url="https://example.com/smc",
        source_type="NOTE",
        provenance_id="PROV-SMC",
        author_or_speaker="Analyst",
        executive_summary="Smart money order block validation.",
        key_claims=[],
        wikilinks=["[[Fair Value Gap]]"],
        tags=["smc"],
        contradictions_detected=[],
        macro_regime_implications="",
        full_markdown_content="# SMC\n\nSee [[Fair Value Gap]].",
        verification_score=80.0,
    )
    temp_wiki_engine.save_article(art)

    # 2. Query backlinks via REST endpoint
    res = client.get("/api/knowledge/wiki/article/art_test_src_01/backlinks")
    assert res.status_code == 200
    data = res.json()
    assert "backlinks" in data

    # 3. Add triage candidate & merge via REST endpoint
    tid = temp_wiki_engine.add_to_triage_inbox(
        candidate_title="Macro Hegemonic Cycle",
        candidate_summary="Ray Dalio long-term debt cycle synthesis.",
        source_url="https://example.com/dalio-cycle",
        source_domain="example.com",
        proposed_category="Macro Geopolitics & Hegemony",
        extracted_claims=[],
    )
    merge_res = client.post(f"/api/knowledge/wiki/triage/{tid}/merge")
    assert merge_res.status_code == 200
    merge_data = merge_res.json()
    assert merge_data["status"] == "MERGED"
    assert merge_data["article"]["title"] == "Macro Hegemonic Cycle"
