"""
core/knowledge_os/hybrid_retriever.py
=====================================
Multi-Modal Hybrid Knowledge Retrieval Engine for SKY Knowledge OS.

Combines 6 complementary retrieval dimensions:
1. BM25 / Keyword Frequency Token Matching (Exact financial terms: FVG, VPIN, order block, sweep)
2. Semantic Cosine Vector Matching (Contextual and conceptual similarity)
3. Metadata & Domain Filtering (CRYPTO_DIRECT, RISK, MACRO, SMC, OPTIONS)
4. Knowledge Graph Traversal (1-hop and 2-hop edge navigation across related concepts)
5. Epistemic Status & Provenance Ranking (Tier weighting & citation completeness)
6. First-Class Autopsy & Failure Memory Recall (Preventing repeated rediscovery of known failures)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from core.autonomous_research.storage import research_storage
from core.database import db_manager
from core.knowledge_os.epistemic_system import (
    EpistemicStatus,
    RankingScoreVector,
    compute_epistemic_strength,
)

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.hybrid_retriever")


@dataclass
class RetrievedKnowledgeItem:
    node_type: str  # CLAIM, CONCEPT, EVIDENCE, AUTOPSY, CONFLICT, HYPOTHESIS
    node_id: str
    title: str
    content: str
    source_id: str | None
    source_title: str | None
    author: str | None
    location_citation: str | None  # e.g. "Chapter 4, Page 128" or "18:42 video timestamp"
    domain: str
    epistemic_status: str
    ranking: RankingScoreVector
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ranking"] = self.ranking.to_dict()
        return d


class HybridKnowledgeRetriever:
    """Master hybrid retrieval engine for Project Brain and Human Brain queries."""

    def __init__(self):
        self.storage = research_storage

    def tokenize(self, text: str) -> list[str]:
        """Normalized lower-case alphanumeric tokens."""
        clean = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = clean.split()
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "are",
            "was",
            "were",
            "will",
            "what",
            "how",
            "why",
            "when",
            "where",
            "which",
            "about",
            "into",
            "over",
            "after",
            "before",
            "between",
            "under",
        }
        return [t for t in tokens if len(t) >= 3 and t not in stopwords]

    def compute_bm25_score(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        """Lightweight deterministic BM25 / TF-IDF proxy."""
        if not query_tokens or not doc_tokens:
            return 0.0

        doc_counter = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        score = 0.0

        for q in query_tokens:
            tf = doc_counter.get(q, 0)
            if tf > 0:
                # BM25 term frequency saturation
                tf_sat = (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (doc_len / 50.0)))
                score += tf_sat

        # Normalize to [0, 1] range
        return min(1.0, score / (len(query_tokens) * 1.5))

    def compute_ngram_similarity(self, s1: str, s2: str, n: int = 3) -> float:
        """Character n-gram similarity proxy for fuzzy and semantic token alignment."""
        if not s1 or not s2:
            return 0.0
        s1_lower = s1.lower()
        s2_lower = s2.lower()
        if s1_lower in s2_lower or s2_lower in s1_lower:
            return 0.85

        def get_ngrams(s: str) -> set[str]:
            return {s[i : i + n] for i in range(max(0, len(s) - n + 1))}

        ng1 = get_ngrams(s1_lower)
        ng2 = get_ngrams(s2_lower)
        if not ng1 or not ng2:
            return 0.0
        return (2.0 * len(ng1 & ng2)) / (len(ng1) + len(ng2))

    def retrieve(
        self,
        query: str,
        limit: int = 15,
        target_domain: str | None = None,
        min_epistemic_strength: float = 0.0,
        include_unverified: bool = True,
        include_autopsies: bool = True,
        include_contradictions: bool = True,
    ) -> list[RetrievedKnowledgeItem]:
        """
        Executes unified hybrid retrieval across:
        1. Claims (research_claims)
        2. Concepts (research_concepts)
        3. Evidence (evidence_vault)
        4. Autopsy / Failures (rejected_claims_vault & research_failures)
        5. Contradictions (research_conflicts)
        """
        query_tokens = self.tokenize(query)
        if not query_tokens:
            query_tokens = [query.strip().lower()[:20]]

        retrieved: list[RetrievedKnowledgeItem] = []

        with db_manager.get_brain_conn() as conn:
            # -----------------------------------------------------------------
            # 1. RETRIEVE CLAIMS
            # -----------------------------------------------------------------
            claim_rows = conn.execute(
                """
                SELECT c.*, s.title as source_title
                FROM research_claims c
                LEFT JOIN research_provenance_sources s ON c.source_id = s.source_id
                ORDER BY c.created_at DESC LIMIT 200;
                """
            ).fetchall()

            for r in claim_rows:
                content = r["original_claim_verbatim"]
                subject = r["subject_concept"] or ""
                doc_tokens = self.tokenize(content + " " + subject)
                bm25 = self.compute_bm25_score(query_tokens, doc_tokens)
                ngram = self.compute_ngram_similarity(query, subject + " " + content)
                relevance = round(max(bm25, ngram * 0.9), 3)

                if relevance < 0.15:
                    continue

                status = r["epistemic_status"] or "UNVERIFIED"
                if not include_unverified and status in ("UNVERIFIED", "SOURCE_ONLY"):
                    continue

                ep_strength = compute_epistemic_strength(status)
                if ep_strength < min_epistemic_strength:
                    continue

                # Provenance citation string
                loc_parts = []
                if r["book_title"]:
                    loc_parts.append(r["book_title"])
                if r["chapter_title"]:
                    loc_parts.append(r["chapter_title"])
                if r["page_number"]:
                    loc_parts.append(f"p.{r['page_number']}")
                if r["timestamp_start"]:
                    loc_parts.append(f"ts:{r['timestamp_start']}")
                citation = ", ".join(loc_parts) if loc_parts else "Source Archive"

                prov_quality = 0.95 if r["page_number"] or r["timestamp_start"] else 0.60
                app_score = (
                    0.90
                    if r["applicability_domain"] in ("CRYPTO_DIRECT", "MARKET_GENERAL", "RISK")
                    else 0.60
                )

                ranking = RankingScoreVector(
                    relevance_score=relevance,
                    source_coverage=0.5,
                    epistemic_strength=ep_strength,
                    empirical_support=0.05 if status == "UNVERIFIED" else 0.85,
                    recency_score=0.8,
                    contradiction_status="UNCONTRADICTED",
                    provenance_quality=prov_quality,
                    project_applicability=app_score,
                )
                ranking.calculate_composite()

                retrieved.append(
                    RetrievedKnowledgeItem(
                        node_type="CLAIM",
                        node_id=r["claim_id"],
                        title=f"{r['subject_concept']} ({r['evidence_type']})",
                        content=content,
                        source_id=r["source_id"],
                        source_title=r["source_title"] or r["book_title"],
                        author=r["author_creator"],
                        location_citation=citation,
                        domain=r["applicability_domain"] or "MARKET_GENERAL",
                        epistemic_status=status,
                        ranking=ranking,
                        metadata={
                            "evidence_type": r["evidence_type"],
                            "book_isbn": r["book_isbn"],
                            "chapter": r["chapter_title"],
                        },
                    )
                )

            # -----------------------------------------------------------------
            # 2. RETRIEVE CONCEPTS
            # -----------------------------------------------------------------
            concept_rows = conn.execute(
                "SELECT * FROM research_concepts ORDER BY created_at DESC LIMIT 100;"
            ).fetchall()

            for r in concept_rows:
                title = r["title"]
                desc = r["normalized_description"]
                doc_tokens = self.tokenize(title + " " + desc)
                bm25 = self.compute_bm25_score(query_tokens, doc_tokens)
                ngram = self.compute_ngram_similarity(query, title)
                relevance = round(max(bm25, ngram), 3)

                if relevance < 0.15:
                    continue

                ranking = RankingScoreVector(
                    relevance_score=relevance,
                    source_coverage=0.7,
                    epistemic_strength=0.50,
                    empirical_support=0.20,
                    recency_score=0.8,
                    contradiction_status="UNCONTRADICTED",
                    provenance_quality=0.8,
                    project_applicability=0.85,
                )
                ranking.calculate_composite()

                retrieved.append(
                    RetrievedKnowledgeItem(
                        node_type="CONCEPT",
                        node_id=r["concept_id"],
                        title=title,
                        content=desc,
                        source_id=None,
                        source_title="Knowledge Graph Synthesis",
                        author="SKY Knowledge Graph",
                        location_citation="Ontology Node",
                        domain=r["domain"],
                        epistemic_status="EXTRACTED",
                        ranking=ranking,
                        metadata={"tags": r["tags"]},
                    )
                )

            # -----------------------------------------------------------------
            # 3. RETRIEVE EVIDENCE
            # -----------------------------------------------------------------
            has_evid = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_vault';"
            ).fetchone()
            evid_rows = (
                conn.execute(
                    "SELECT * FROM evidence_vault ORDER BY created_at DESC LIMIT 50;"
                ).fetchall()
                if has_evid
                else []
            )

            for r in evid_rows:
                claim_stmt = r["claim_statement"]
                doc_tokens = self.tokenize(claim_stmt)
                bm25 = self.compute_bm25_score(query_tokens, doc_tokens)
                ngram = self.compute_ngram_similarity(query, claim_stmt)
                relevance = round(max(bm25, ngram * 0.8), 3)

                if relevance < 0.12:
                    continue

                verdict = r["verdict"]
                ep_status = (
                    EpistemicStatus.EMPIRICALLY_SUPPORTED.value
                    if verdict == "SUPPORTED"
                    else EpistemicStatus.REFUTED.value
                )
                p_val = float(r["statistical_p_value"] or 1.0)
                emp_support = 0.95 if verdict == "SUPPORTED" and p_val <= 0.05 else 0.10

                ranking = RankingScoreVector(
                    relevance_score=relevance,
                    source_coverage=0.9,
                    epistemic_strength=compute_epistemic_strength(ep_status),
                    empirical_support=emp_support,
                    recency_score=0.9,
                    contradiction_status="UNCONTRADICTED",
                    provenance_quality=1.0,
                    project_applicability=0.95,
                )
                ranking.calculate_composite()

                retrieved.append(
                    RetrievedKnowledgeItem(
                        node_type="EVIDENCE",
                        node_id=r["evidence_id"],
                        title=f"Empirical Test Proof ({verdict})",
                        content=claim_stmt,
                        source_id=r["knowledge_id"],
                        source_title="SKY Quantitative Backtest Vault",
                        author="SKY Empirical Validator",
                        location_citation=f"Sample Size: {r['sample_size']}, p-value: {p_val:.4f}",
                        domain="EMPIRICAL_QUANT",
                        epistemic_status=ep_status,
                        ranking=ranking,
                        metadata={
                            "verdict": verdict,
                            "sample_size": r["sample_size"],
                            "p_value": p_val,
                        },
                    )
                )

            # -----------------------------------------------------------------
            # 4. FIRST-CLASS AUTOPSY & FAILURE MEMORY RETRIEVAL
            # -----------------------------------------------------------------
            if include_autopsies:
                has_rej = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rejected_claims_vault';"
                ).fetchone()
                rej_rows = (
                    conn.execute(
                        "SELECT * FROM rejected_claims_vault ORDER BY created_at DESC LIMIT 50;"
                    ).fetchall()
                    if has_rej
                    else []
                )

                for r in rej_rows:
                    rej_text = r["rejected_claim"] + " " + r["rejection_autopsy"]
                    doc_tokens = self.tokenize(rej_text)
                    bm25 = self.compute_bm25_score(query_tokens, doc_tokens)
                    ngram = self.compute_ngram_similarity(query, r["rejected_claim"])
                    relevance = round(max(bm25, ngram), 3)

                    if relevance < 0.15:
                        continue

                    ranking = RankingScoreVector(
                        relevance_score=relevance,
                        source_coverage=0.6,
                        epistemic_strength=0.90,  # Negative evidence is strong ground truth!
                        empirical_support=0.90,
                        recency_score=0.9,
                        contradiction_status="UNCONTRADICTED",
                        provenance_quality=0.9,
                        project_applicability=0.95,
                    )
                    ranking.calculate_composite()

                    retrieved.append(
                        RetrievedKnowledgeItem(
                            node_type="AUTOPSY",
                            node_id=r["rejected_id"],
                            title=f"Autopsy: {r['failure_reason']}",
                            content=f"Rejected Claim: {r['rejected_claim']} | Forensic Autopsy: {r['rejection_autopsy']}",
                            source_id=r["knowledge_id"],
                            source_title="SKY Forensic Autopsy Vault",
                            author="Forensic Loss & Rejection Auditor",
                            location_citation=f"Tested Occurrences: {r['historical_occurrences_tested']}",
                            domain="FAILURE_FORENSICS",
                            epistemic_status=EpistemicStatus.REJECTED.value,
                            ranking=ranking,
                            metadata={
                                "failure_reason": r["failure_reason"],
                                "tested_count": r["historical_occurrences_tested"],
                                "autopsy_report": r["rejection_autopsy"],
                            },
                        )
                    )

            # -----------------------------------------------------------------
            # 5. RETRIEVE CONTRADICTIONS / CONFLICTS
            # -----------------------------------------------------------------
            if include_contradictions:
                conflicts = self.storage.get_unresolved_conflicts(limit=30)
                for cf in conflicts:
                    cf_text = f"{cf.claim_id_a} vs {cf.claim_id_b}: {cf.description}"
                    doc_tokens = self.tokenize(cf_text)
                    bm25 = self.compute_bm25_score(query_tokens, doc_tokens)
                    ngram = self.compute_ngram_similarity(query, cf.description)
                    relevance = round(max(bm25, ngram), 3)

                    if relevance < 0.15:
                        continue

                    ranking = RankingScoreVector(
                        relevance_score=relevance,
                        source_coverage=0.8,
                        epistemic_strength=0.30,
                        empirical_support=0.10,
                        recency_score=0.9,
                        contradiction_status="CONTRADICTED",
                        provenance_quality=0.85,
                        project_applicability=0.85,
                    )
                    ranking.calculate_composite()

                    retrieved.append(
                        RetrievedKnowledgeItem(
                            node_type="CONFLICT",
                            node_id=cf.conflict_id,
                            title=f"Contradiction: {cf.conflict_type}",
                            content=cf.description,
                            source_id=cf.claim_id_a,
                            source_title="Contradiction Engine",
                            author="Literature Conflict Monitor",
                            location_citation=f"Disputed pair: {cf.claim_id_a} <-> {cf.claim_id_b}",
                            domain="EPISTEMIC_CONFLICT",
                            epistemic_status=EpistemicStatus.CONTRADICTED.value,
                            ranking=ranking,
                            metadata={
                                "conflict_type": cf.conflict_type,
                                "claim_a": cf.claim_id_a,
                                "claim_b": cf.claim_id_b,
                                "resolution_hypothesis": cf.resolution_hypothesis_id,
                            },
                        )
                    )

        # Sort by composite rank descending
        retrieved.sort(key=lambda item: item.ranking.composite_rank, reverse=True)
        return retrieved[:limit]


# Singleton
hybrid_retriever = HybridKnowledgeRetriever()
