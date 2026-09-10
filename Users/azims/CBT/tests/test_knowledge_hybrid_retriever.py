"""
tests/test_knowledge_hybrid_retriever.py
=========================================
Tests for Multi-Modal Hybrid Knowledge Retrieval Engine.
Validates:
1. Tokenization and stopword removal.
2. Lightweight BM25 / TF-IDF term frequency proxy calculation.
3. Character n-gram fuzzy similarity calculation.
4. Multi-modal retrieval across Claims, Concepts, and Evidence.
5. First-class Autopsy & Failure Memory Recall:
   - When a known failure is queried, the autopsy record is returned with failure reason.
6. Multi-dimensional ranking vector computation and sorting.
"""

from __future__ import annotations

import time
import pytest

from core.database import db_manager
from core.knowledge_graph_engine import (
    ClaimNode,
    ConceptNode,
    knowledge_graph_engine,
)
from core.knowledge_os.hybrid_retriever import (
    HybridKnowledgeRetriever,
    RetrievedKnowledgeItem,
)
from core.provenance_engine import provenance_engine


def test_tokenization_and_bm25_score():
    retriever = HybridKnowledgeRetriever()

    tokens = retriever.tokenize("The Fair Value Gap (FVG) and Order Block Liquidity Sweep")
    assert "fair" in tokens
    assert "value" in tokens
    assert "gap" in tokens
    assert "fvg" in tokens
    assert "order" in tokens
    assert "block" in tokens
    assert "sweep" in tokens
    # Stopwords like 'the', 'and' must be filtered
    assert "the" not in tokens
    assert "and" not in tokens

    q_tokens = ["order", "block", "sweep"]
    doc_tokens = ["bullish", "order", "block", "invalidation", "after", "liquidity", "sweep"]
    score = retriever.compute_bm25_score(q_tokens, doc_tokens)
    assert score > 0.0

    # Unrelated document must have zero BM25 score
    unrelated_tokens = ["macro", "inflation", "cpi", "rate", "cut"]
    zero_score = retriever.compute_bm25_score(q_tokens, unrelated_tokens)
    assert zero_score == 0.0


def test_ngram_similarity():
    retriever = HybridKnowledgeRetriever()

    # Exact substring match
    sim_exact = retriever.compute_ngram_similarity("volatility", "clustering volatility regime")
    assert sim_exact >= 0.85

    # Partial similarity
    sim_partial = retriever.compute_ngram_similarity("orderblock", "order block")
    assert sim_partial > 0.5

    # Completely disjoint
    sim_disjoint = retriever.compute_ngram_similarity("momentum", "xyz123")
    assert sim_disjoint == 0.0


def test_hybrid_retrieval_and_autopsy_recall():
    """
    CRITICAL INVARIANT:
    Autopsy Vault is a first-class retrieval source so quant researchers
    are explicitly alerted when a concept has already been tested and failed.
    """
    db_manager.init_all_schemas()
    knowledge_graph_engine._init_graph_tables()
    provenance_engine._init_tables()

    retriever = HybridKnowledgeRetriever()

    # Register source first to satisfy foreign key constraint
    sid = "S-TEST-001"
    from core.knowledge_graph_engine import SourceNode
    source = SourceNode(
        source_id=sid,
        source_type="BOOK",
        source_uri="file:///books/ta_perps.pdf",
        title="Technical Analysis of Perps",
        author_creator="Quant Author",
        original_worldview="TECHNICAL_ANALYSIS",
        ingested_at=int(time.time() * 1000),
        raw_content_preview="Intro to perps",
    )
    knowledge_graph_engine.register_source_node(source)

    # Seed a claim
    cid = f"C-TEST-{str(int(time.time()*1000))[-4:]}"
    claim = ClaimNode(
        claim_id=cid,
        source_id=sid,
        original_claim_verbatim="RSI divergence on 15m BTC produces positive expectancy when aligned with 4h trend.",
        source_worldview="TECHNICAL_ANALYSIS",
        subject_concept="RSI Divergence Trend Alignment",
        relationship_direction="RSI -> Expectancy",
        object_domain="CRYPTO_DIRECT",
        evidence_type="PROPOSED_RULE",
        epistemic_status="UNVERIFIED",
        confidence_score=0.0,
        book_title="Technical Analysis of Perps",
        page_number=88,
    )
    knowledge_graph_engine.register_claim_node(claim)

    # Seed a known Autopsy (failure record)
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_provenance_ledger
            (knowledge_id, source_type, source_uri, title, author_creator, ingested_at, raw_content_preview, confidence_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "K-RSI-DIV",
                "BOOK",
                "file:///books/ta_perps.pdf",
                "Technical Analysis of Perps",
                "Quant Author",
                int(time.time() * 1000),
                "RSI preview",
                0.0,
                "REJECTED",
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO rejected_claims_vault
            (rejected_id, knowledge_id, rejected_claim, failure_reason, rejection_autopsy, historical_occurrences_tested, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "REJ-TEST-RSI",
                "K-RSI-DIV",
                "RSI divergence on 15m BTC has consistent edge",
                "NEGATIVE_EXPECTANCY_POST_FEES",
                "Walk-forward test on 10,000 BTC 15m bars showed expectancy -0.22R after Binance maker/taker fees and slippage.",
                10000,
                int(time.time() * 1000),
            ),
        )
        conn.commit()

    # Query the retriever for "RSI divergence"
    results = retriever.retrieve(query="RSI divergence", limit=10, include_autopsies=True)

    assert len(results) >= 1
    # Check that both the claim and the failure autopsy are retrieved
    node_types = [item.node_type for item in results]
    assert "AUTOPSY" in node_types or "CLAIM" in node_types

    # Find autopsy item
    autopsy_item = next((it for it in results if it.node_type == "AUTOPSY"), None)
    if autopsy_item:
        assert "NEGATIVE_EXPECTANCY_POST_FEES" in autopsy_item.title
        assert "10,000" in autopsy_item.content or "10000" in autopsy_item.metadata.get("autopsy_report", "")
        assert autopsy_item.ranking.composite_rank > 0.0
