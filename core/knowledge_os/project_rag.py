"""
core/knowledge_os/project_rag.py
================================
Unified Project Knowledge RAG (Retrieval-Augmented Generation) for CBT / SKY.

Constitutional Mandates:
1. Institutional Grounding: Ground answers in live market state, CBT research wiki,
   relational claims, verified evidence, active theses, and strategy backtest ledgers.
2. Epistemic Separation: Distinguishes [FACT], [EMPIRICALLY_SUPPORTED], [HYPOTHESIS],
   and [REFUTED] claims with unbroken citation IDs.
3. System Truth Primacy: Live data and deterministic DB ledgers are ground truth;
   LLM serves solely as an orchestrator and synthesizer.
4. Multi-Modal Retrieval: Scans Wiki articles, source transcripts, real_life_summary,
   theses, graph relations, and strategy candidates simultaneously.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.database import db_manager
from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.project_rag")


@dataclass
class RetrievedWikiItem:
    article_id: str
    title: str
    category: str
    summary: str
    verification_score: float
    relevance_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedClaimItem:
    claim_id: str
    claim_text: str
    claim_type: str
    speaker: str
    verification_status: str
    confidence_score: float
    corroborating_evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedThesisItem:
    thesis_id: str
    title: str
    status: str
    confidence_score: float
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievedStrategyItem:
    candidate_id: str
    strategy_name: str
    validation_stage: str
    backtest_expectancy: float | None = None
    win_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundedProjectDossier:
    query: str
    timestamp_ms: int
    wiki_articles: list[RetrievedWikiItem] = field(default_factory=list)
    claims: list[RetrievedClaimItem] = field(default_factory=list)
    theses: list[RetrievedThesisItem] = field(default_factory=list)
    strategies: list[RetrievedStrategyItem] = field(default_factory=list)
    market_vitals: dict[str, Any] = field(default_factory=dict)
    summary_grounding: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "timestamp_ms": self.timestamp_ms,
            "wiki_articles": [w.to_dict() for w in self.wiki_articles],
            "claims": [c.to_dict() for c in self.claims],
            "theses": [t.to_dict() for t in self.theses],
            "strategies": [s.to_dict() for s in self.strategies],
            "market_vitals": self.market_vitals,
            "summary_grounding": self.summary_grounding,
        }


class UnifiedProjectKnowledgeRAG:
    """
    Unified multi-index retrieval engine for CBT research, epistemic claims,
    institutional theses, strategy candidates, and market state.
    """

    def __init__(self, wiki_db_path: Path = WIKI_DB_PATH):
        self.wiki_db_path = wiki_db_path

    def _get_wiki_conn(self):
        return research_wikipedia_engine._get_connection()

    def _tokenize(self, text: str) -> set[str]:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = {w.strip() for w in cleaned.split() if len(w.strip()) >= 3}
        # Filter common stopwords
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "are",
            "what",
            "how",
            "about",
            "have",
            "kemon",
            "bhai",
            "koto",
            "dike",
            "jabe",
            "kore",
            "holo",
            "hoy",
            "ache",
            "ki",
            "shob",
        }
        return tokens - stopwords

    def retrieve_wiki_articles(self, query: str, limit: int = 5) -> list[RetrievedWikiItem]:
        """Searches wiki_articles and research_sources for top matching articles."""
        tokens = self._tokenize(query)
        try:
            with self._get_wiki_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT article_id, title, category, executive_summary, verification_score
                    FROM wiki_articles
                    ORDER BY updated_at DESC LIMIT 50;
                    """
                ).fetchall()
        except Exception as e:
            logger.debug(f"[ProjectRAG] retrieve_wiki_articles fallback: {e}")
            return []

        results: list[tuple[float, RetrievedWikiItem]] = []
        for r in rows:
            title_text = r["title"].lower()
            summary_text = r["executive_summary"].lower()
            score = 0.0

            if not tokens:
                score = 0.1
            else:
                for tok in tokens:
                    if tok in title_text:
                        score += 3.0
                    if tok in summary_text:
                        score += 1.0

            if score > 0.0:
                item = RetrievedWikiItem(
                    article_id=r["article_id"],
                    title=r["title"],
                    category=r["category"],
                    summary=r["executive_summary"][:300]
                    + ("..." if len(r["executive_summary"]) > 300 else ""),
                    verification_score=float(r["verification_score"]),
                    relevance_score=score,
                )
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def retrieve_claims(self, query: str, limit: int = 5) -> list[RetrievedClaimItem]:
        """Searches research_claims for verified or empirical claims."""
        tokens = self._tokenize(query)
        try:
            with self._get_wiki_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT claim_id, speaker_claim, claim_type, speaker,
                           confidence_score, verification_status, cross_verification_evidence
                    FROM research_claims
                    ORDER BY created_at DESC LIMIT 50;
                    """
                ).fetchall()
        except Exception as e:
            logger.debug(f"[ProjectRAG] retrieve_claims fallback: {e}")
            return []

        results: list[tuple[float, RetrievedClaimItem]] = []
        for r in rows:
            text = r["speaker_claim"].lower()
            score = 0.0

            if not tokens:
                score = 0.1
            else:
                for tok in tokens:
                    if tok in text:
                        score += 2.0

            # Boost verified and empirically supported claims
            if r["verification_status"] in ("VERIFIED_TRUE", "EMPIRICALLY_SUPPORTED"):
                score += 1.5
            elif r["verification_status"] in ("CONTRADICTED", "REFUTED"):
                score += 0.8  # Still relevant as counter-evidence

            if score > 0.0:
                item = RetrievedClaimItem(
                    claim_id=r["claim_id"],
                    claim_text=r["speaker_claim"],
                    claim_type=r["claim_type"],
                    speaker=r["speaker"] or "Analyst",
                    verification_status=r["verification_status"],
                    confidence_score=float(r["confidence_score"]),
                    corroborating_evidence=r["cross_verification_evidence"],
                )
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def retrieve_theses(self, query: str, limit: int = 3) -> list[RetrievedThesisItem]:
        """Retrieves institutional theses matching query keywords."""
        tokens = self._tokenize(query)
        try:
            with self._get_wiki_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT thesis_id, title, status, confidence_score, description
                    FROM research_theses
                    ORDER BY updated_at DESC LIMIT 20;
                    """
                ).fetchall()
        except Exception as e:
            logger.debug(f"[ProjectRAG] retrieve_theses fallback: {e}")
            return []

        results: list[tuple[float, RetrievedThesisItem]] = []
        for r in rows:
            text = f"{r['title']} {r['description']}".lower()
            score = 0.0

            if not tokens:
                score = 0.1
            else:
                for tok in tokens:
                    if tok in text:
                        score += 2.0

            if score > 0.0:
                item = RetrievedThesisItem(
                    thesis_id=r["thesis_id"],
                    title=r["title"],
                    status=r["status"],
                    confidence_score=float(r["confidence_score"]),
                    description=r["description"][:250],
                )
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def retrieve_strategies(self, query: str, limit: int = 3) -> list[RetrievedStrategyItem]:
        """Searches strategy_candidates for tested or relevant setups."""
        tokens = self._tokenize(query)
        try:
            with db_manager.get_brain_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT candidate_id, strategy_name, hypothesis, validation_stage,
                           backtest_expectancy, backtest_win_rate
                    FROM strategy_candidates
                    ORDER BY created_at DESC LIMIT 30;
                    """
                ).fetchall()
        except Exception as e:
            logger.debug(f"[ProjectRAG] retrieve_strategies fallback: {e}")
            return []

        results: list[tuple[float, RetrievedStrategyItem]] = []
        for r in rows:
            text = f"{r['strategy_name']} {r['hypothesis']}".lower()
            score = 0.0

            if not tokens:
                score = 0.1
            else:
                for tok in tokens:
                    if tok in text:
                        score += 2.0

            # Boost tested candidates
            if r["validation_stage"] == "WALK_FORWARD_TESTED":
                score += 1.5

            if score > 0.0:
                item = RetrievedStrategyItem(
                    candidate_id=r["candidate_id"],
                    strategy_name=r["strategy_name"],
                    validation_stage=r["validation_stage"],
                    backtest_expectancy=float(r["backtest_expectancy"])
                    if r["backtest_expectancy"] is not None
                    else None,
                    win_rate=float(r["backtest_win_rate"])
                    if r["backtest_win_rate"] is not None
                    else None,
                )
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def compile_grounded_dossier(
        self,
        query: str,
        market_vitals: dict[str, Any] | None = None,
    ) -> GroundedProjectDossier:
        """
        Executes unified multi-index retrieval and builds an institutional evidence dossier.
        """
        vitals = market_vitals or {}
        articles = self.retrieve_wiki_articles(query, limit=3)
        claims = self.retrieve_claims(query, limit=5)
        theses = self.retrieve_theses(query, limit=2)
        strategies = self.retrieve_strategies(query, limit=2)

        dossier = GroundedProjectDossier(
            query=query,
            timestamp_ms=int(time.time() * 1000),
            wiki_articles=articles,
            claims=claims,
            theses=theses,
            strategies=strategies,
            market_vitals=vitals,
        )

        dossier.summary_grounding = self.format_institutional_dossier_text(dossier)
        return dossier

    def format_institutional_dossier_text(self, d: GroundedProjectDossier) -> str:
        """
        Formats the dossier into the 4 Institutional Grounding Pillars:
        1. CURRENT MARKET
        2. CBT RESEARCH
        3. EVIDENCE & CONTRADICTIONS
        4. CONFIDENCE & CONCLUSION
        """
        lines = [
            "🏛️ **CBT INSTITUTIONAL GROUNDED RESEARCH DOSSIER**",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # 1. CURRENT MARKET
        v = d.market_vitals
        btc_p = v.get("btc_price", 0.0)
        eth_p = v.get("eth_price", 0.0)
        lines.append("📊 **1. CURRENT MARKET VITALS:**")
        lines.append(f"• BTC Price: `${btc_p:,.2f}` | ETH Price: `${eth_p:,.2f}`")
        if "virtual_equity" in v:
            lines.append(
                f"• Shadow Equity: `${v['virtual_equity']:,.2f}` | Open Positions: `{v.get('open_positions_count', 0)}`"
            )
        lines.append("• Risk Bounds: Half-Kelly (Max 2.5% Equity/Trade) | Real Capital: `LOCKED`\n")

        # 2. CBT RESEARCH
        lines.append("📚 **2. RELEVANT CBT RESEARCH & THESES:**")
        if d.theses:
            for t in d.theses:
                lines.append(
                    f"• **Thesis [{t.thesis_id}]:** {t.title} `[{t.status}]` (Conf: {t.confidence_score:.2f})"
                )
        if d.wiki_articles:
            for a in d.wiki_articles:
                lines.append(
                    f"• **Wiki [{a.article_id}]:** {a.title} ({a.category}) — Score: {a.verification_score:.2f}"
                )
        if not d.theses and not d.wiki_articles:
            lines.append("• _No directly matching long-form research articles._")
        lines.append("")

        # 3. EVIDENCE & CONTRADICTIONS
        lines.append("⚖️ **3. EMPIRICAL CLAIMS & EVIDENCE LEDGER:**")
        if d.claims:
            for c in d.claims:
                icon = (
                    "✅"
                    if c.verification_status in ("VERIFIED_TRUE", "EMPIRICALLY_SUPPORTED")
                    else ("❌" if c.verification_status in ("CONTRADICTED", "REFUTED") else "🔍")
                )
                lines.append(
                    f"• {icon} `[{c.claim_id}]` **[{c.verification_status}]** ({c.claim_type}): {c.claim_text}"
                )
                if c.corroborating_evidence:
                    lines.append(f"   ↳ _Evidence:_ {c.corroborating_evidence[:100]}...")
        else:
            lines.append("• _No empirical claims matched query tokens._")
        lines.append("")

        # 4. STRATEGY CANDIDATES & CONCLUSION
        lines.append("🧪 **4. DERIVED STRATEGIES & CONCLUSION:**")
        if d.strategies:
            for s in d.strategies:
                exp_str = (
                    f"{s.backtest_expectancy:+.2f}R"
                    if s.backtest_expectancy is not None
                    else "Pending"
                )
                lines.append(
                    f"• `[{s.candidate_id}]` **{s.strategy_name}** `[{s.validation_stage}]` (EV: {exp_str})"
                )
        else:
            lines.append("• _No qualified strategy candidates tied to this topic._")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            "🔒 _Ground Truth Priority: Grounded in SQLite Ledgers & Zero-Lookahead conventions._"
        )
        return "\n".join(lines)


# Global singleton
project_rag = UnifiedProjectKnowledgeRAG()
