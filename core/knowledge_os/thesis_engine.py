"""
core/knowledge_os/thesis_engine.py
==================================
Institutional Quantitative Thesis & Macro Hypothesis Layer.

Constitutional Mandates:
1. Higher-Order Synthesis: Aggregates atomic claims into evolving, falsifiable macro theses.
2. Epistemic Lifecycle Governance:
   NEW -> EMERGING -> SUPPORTED -> CONTESTED -> WEAKENING -> REJECTED -> ARCHIVED.
3. Bidirectional Evidence Verification: A thesis's confidence is dynamically derived from
   supporting and contradicting claim statuses.
4. Auto-Clustering: Dispatches incoming research claims to relevant active theses.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.thesis_engine")


@dataclass
class ResearchThesis:
    thesis_id: str
    title: str
    description: str
    asset_class: str  # CRYPTO, MACRO_RATES, COMMODITIES, EQUITIES, CROSS_ASSET
    status: str  # NEW, EMERGING, SUPPORTED, CONTESTED, WEAKENING, REJECTED, ARCHIVED
    supporting_claims_count: int = 0
    contradicting_claims_count: int = 0
    confidence_score: float = 0.50
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ThesisEngine:
    """
    Manages institutional research hypotheses and dynamic evidence attribution.
    """

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path
        self._ensure_tables()
        self._seed_canonical_theses()

    def _get_connection(self) -> sqlite3.Connection:
        return research_wikipedia_engine._get_connection()

    def _ensure_tables(self) -> None:
        """Initializes tables for theses and claim-thesis links."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_theses (
                    thesis_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    supporting_claims_count INTEGER DEFAULT 0,
                    contradicting_claims_count INTEGER DEFAULT 0,
                    confidence_score REAL NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_theses_status ON research_theses(status);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_theses_asset ON research_theses(asset_class);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_thesis_claims (
                    thesis_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,  -- SUPPORTS, CONTRADICTS
                    weight REAL DEFAULT 1.0,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (thesis_id, claim_id),
                    FOREIGN KEY (thesis_id) REFERENCES research_theses(thesis_id),
                    FOREIGN KEY (claim_id) REFERENCES research_claims(claim_id)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tc_thesis ON research_thesis_claims(thesis_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tc_claim ON research_thesis_claims(claim_id);"
            )
            conn.commit()

    def _seed_canonical_theses(self) -> None:
        """Pre-seeds CBT's foundational institutional macro & microstructure hypotheses."""
        canonical = [
            ResearchThesis(
                thesis_id="thesis_liquidity_m2",
                title="Global M2 Expansion & Bitcoin Liquidity Beta",
                description="Central bank balance sheet expansion and global M2 growth structurally lead Bitcoin returns with high positive liquidity beta.",
                asset_class="CRYPTO",
                status="SUPPORTED",
                supporting_claims_count=4,
                contradicting_claims_count=0,
                confidence_score=0.88,
            ),
            ResearchThesis(
                thesis_id="thesis_dxy_yield_pressure",
                title="US Real Rates and DXY Pressure on Digital Assets",
                description="Sustained dollar strength and elevated 10Y real treasury yields contract crypto market multiples and drain high-beta liquidity.",
                asset_class="CROSS_ASSET",
                status="SUPPORTED",
                supporting_claims_count=3,
                contradicting_claims_count=0,
                confidence_score=0.82,
            ),
            ResearchThesis(
                thesis_id="thesis_institutional_smc",
                title="Institutional Liquidity Sweep & Fair Value Rebalancing",
                description="Algorithmic market makers engineer liquidity sweeps beyond retail swing highs/lows before fulfilling Fair Value Gaps (FVG).",
                asset_class="CRYPTO",
                status="EMERGING",
                supporting_claims_count=2,
                contradicting_claims_count=0,
                confidence_score=0.76,
            ),
        ]

        with self._get_connection() as conn:
            for t in canonical:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO research_theses (
                        thesis_id, title, description, asset_class, status,
                        supporting_claims_count, contradicting_claims_count,
                        confidence_score, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        t.thesis_id,
                        t.title,
                        t.description,
                        t.asset_class,
                        t.status,
                        t.supporting_claims_count,
                        t.contradicting_claims_count,
                        t.confidence_score,
                        t.created_at,
                        t.updated_at,
                    ),
                )
            conn.commit()

    def create_thesis(
        self,
        thesis_id: str,
        title: str,
        description: str,
        asset_class: str = "CRYPTO",
    ) -> ResearchThesis:
        """Creates a new research hypothesis."""
        now = int(time.time() * 1000)
        t = ResearchThesis(
            thesis_id=thesis_id,
            title=title,
            description=description,
            asset_class=asset_class,
            status="NEW",
            confidence_score=0.50,
            created_at=now,
            updated_at=now,
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_theses (
                    thesis_id, title, description, asset_class, status,
                    supporting_claims_count, contradicting_claims_count,
                    confidence_score, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thesis_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    asset_class = excluded.asset_class,
                    updated_at = excluded.updated_at;
                """,
                (
                    t.thesis_id,
                    t.title,
                    t.description,
                    t.asset_class,
                    t.status,
                    t.supporting_claims_count,
                    t.contradicting_claims_count,
                    t.confidence_score,
                    t.created_at,
                    t.updated_at,
                ),
            )
            conn.commit()
        return t

    def link_claim(
        self,
        thesis_id: str,
        claim_id: str,
        relationship: str = "SUPPORTS",
        weight: float = 1.0,
    ) -> None:
        """Links an epistemic claim to a thesis as either SUPPORTS or CONTRADICTS."""
        rel_clean = "CONTRADICTS" if "CONTRADICT" in relationship.upper() else "SUPPORTS"
        now = int(time.time() * 1000)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_thesis_claims (
                    thesis_id, claim_id, relationship, weight, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thesis_id, claim_id) DO UPDATE SET
                    relationship = excluded.relationship,
                    weight = excluded.weight;
                """,
                (thesis_id, claim_id, rel_clean, weight, now),
            )
            conn.commit()

        # Recalculate thesis metrics
        self.evaluate_thesis(thesis_id)

    def evaluate_thesis(self, thesis_id: str) -> ResearchThesis | None:
        """
        Dynamically calculates confidence score, supporting/contradicting claim counts,
        and transitions epistemic lifecycle status.
        """
        with self._get_connection() as conn:
            t_row = conn.execute(
                "SELECT * FROM research_theses WHERE thesis_id = ?;", (thesis_id,)
            ).fetchone()
            if not t_row:
                return None

            # Get linked claims
            links = conn.execute(
                """
                SELECT tc.relationship, tc.weight, c.verification_status, c.confidence_score
                FROM research_thesis_claims tc
                JOIN research_claims c ON tc.claim_id = c.claim_id
                WHERE tc.thesis_id = ?;
                """,
                (thesis_id,),
            ).fetchall()

            supporting = [lnk for lnk in links if lnk["relationship"] == "SUPPORTS"]
            contradicting = [lnk for lnk in links if lnk["relationship"] == "CONTRADICTS"]

            sup_count = len(supporting)
            con_count = len(contradicting)

            # Score computation
            base_score = 0.50
            if sup_count + con_count > 0:
                sup_weight = sum(
                    float(lnk["confidence_score"]) * float(lnk["weight"]) for lnk in supporting
                )
                con_weight = sum(
                    float(lnk["confidence_score"]) * float(lnk["weight"]) for lnk in contradicting
                )
                net = sup_weight - con_weight
                base_score = max(0.10, min(0.95, 0.50 + (net * 0.12)))

            # Status transition logic
            if con_count > sup_count and con_count >= 2:
                status = "CONTESTED" if base_score > 0.35 else "WEAKENING"
            elif sup_count >= 3 and con_count == 0 and base_score >= 0.75:
                status = "SUPPORTED"
            elif sup_count >= 1 or con_count >= 1:
                status = "EMERGING"
            else:
                status = "NEW"

            now = int(time.time() * 1000)
            conn.execute(
                """
                UPDATE research_theses
                SET supporting_claims_count = ?,
                    contradicting_claims_count = ?,
                    confidence_score = ?,
                    status = ?,
                    updated_at = ?
                WHERE thesis_id = ?;
                """,
                (sup_count, con_count, round(base_score, 2), status, now, thesis_id),
            )
            conn.commit()

            return ResearchThesis(
                thesis_id=thesis_id,
                title=t_row["title"],
                description=t_row["description"],
                asset_class=t_row["asset_class"],
                status=status,
                supporting_claims_count=sup_count,
                contradicting_claims_count=con_count,
                confidence_score=round(base_score, 2),
                created_at=int(t_row["created_at"]),
                updated_at=now,
            )

    def auto_cluster_claim_to_theses(self, claim_id: str, claim_text: str) -> list[str]:
        """Automatically checks if an incoming claim aligns with existing theses."""
        text_lower = claim_text.lower()
        linked_theses: list[str] = []

        # Check M2 / Liquidity thesis
        if any(
            w in text_lower for w in ("liquidity", "m2", "money supply", "balance sheet", "inflow")
        ):
            rel = (
                "SUPPORTS"
                if any(w in text_lower for w in ("expand", "grow", "boost", "support", "bull"))
                else "CONTRADICTS"
            )
            self.link_claim("thesis_liquidity_m2", claim_id, relationship=rel)
            linked_theses.append("thesis_liquidity_m2")

        # Check DXY / Rates thesis
        if any(
            w in text_lower
            for w in ("dxy", "dollar", "treasury yield", "us10y", "interest rate", "fed hike")
        ):
            rel = (
                "SUPPORTS"
                if any(
                    w in text_lower
                    for w in ("pressure", "suppress", "drain", "fall", "dump", "bear")
                )
                else "CONTRADICTS"
            )
            self.link_claim("thesis_dxy_yield_pressure", claim_id, relationship=rel)
            linked_theses.append("thesis_dxy_yield_pressure")

        # Check SMC / Liquidity sweep thesis
        if any(
            w in text_lower
            for w in ("fvg", "order block", "fair value gap", "liquidity sweep", "orderflow", "smc")
        ):
            self.link_claim("thesis_institutional_smc", claim_id, relationship="SUPPORTS")
            linked_theses.append("thesis_institutional_smc")

        return linked_theses

    def list_theses(
        self,
        asset_class: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Lists active theses with optional filtering."""
        with self._get_connection() as conn:
            query = "SELECT * FROM research_theses"
            conditions = []
            params: list[Any] = []

            if asset_class:
                conditions.append("asset_class = ?")
                params.append(asset_class.upper())
            if status:
                conditions.append("status = ?")
                params.append(status.upper())

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY confidence_score DESC, updated_at DESC LIMIT ?;"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_thesis_dossier(self, thesis_id: str) -> dict[str, Any] | None:
        """Returns complete thesis details with all linked supporting and contradicting claims."""
        with self._get_connection() as conn:
            t_row = conn.execute(
                "SELECT * FROM research_theses WHERE thesis_id = ?;", (thesis_id,)
            ).fetchone()
            if not t_row:
                return None

            claim_rows = conn.execute(
                """
                SELECT tc.relationship, tc.weight, tc.created_at as linked_at,
                       c.claim_id, c.speaker_claim, c.claim_type, c.confidence_score,
                       c.verification_status, c.source_id
                FROM research_thesis_claims tc
                JOIN research_claims c ON tc.claim_id = c.claim_id
                WHERE tc.thesis_id = ?
                ORDER BY tc.created_at DESC;
                """,
                (thesis_id,),
            ).fetchall()

        supporting = [dict(r) for r in claim_rows if r["relationship"] == "SUPPORTS"]
        contradicting = [dict(r) for r in claim_rows if r["relationship"] == "CONTRADICTS"]

        return {
            "thesis": dict(t_row),
            "supporting_claims": supporting,
            "contradicting_claims": contradicting,
            "total_linked_claims": len(claim_rows),
        }


# Global singleton instance
thesis_engine = ThesisEngine()
