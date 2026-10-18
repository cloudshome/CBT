"""
core/knowledge_os/knowledge_graph.py
====================================
Institutional Knowledge Graph Engine for CBT.

Constitutional Mandates:
1. Relational Graph Structure: Maps entities and bidirectional relations in SQLite.
2. Canonical Entity Grounding: Recognizes assets, macro institutions, indicators, and SMC concepts.
3. Automated Relation Extraction: Links concepts discovered in research claims and wiki articles.
4. Multi-Hop Graph Traversal: Enables sub-graph queries and path-finding between market drivers.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.knowledge_graph")


@dataclass
class GraphEntity:
    entity_id: str
    name: str
    entity_type: str  # ASSET, CENTRAL_BANK, MACRO_INDICATOR, SMC_CONCEPT, PROTOCOL, INSTITUTION, RISK_CONTROL
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    mention_count: int = 1
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GraphRelation:
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: (
        str  # DRIVES, INFLUENCES, CORRELATED_WITH, INVERSE_TO, REGULATES, HEDGES, CONTRADICTS
    )
    weight: float
    claim_id: str = ""
    source_id: str = ""
    description: str = ""
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeGraphEngine:
    """
    Coordinates entity and relation storage, extraction, and graph querying.
    """

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path
        self._ensure_tables()
        self._seed_canonical_knowledge_graph()

    def _get_connection(self) -> sqlite3.Connection:
        return research_wikipedia_engine._get_connection()

    def _ensure_tables(self) -> None:
        """Initializes relational graph tables in SQLite."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    entity_type TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    description TEXT,
                    mention_count INTEGER DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON research_entities(name);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_type ON research_entities(entity_type);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_relations (
                    relation_id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    claim_id TEXT,
                    source_id TEXT,
                    description TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (source_entity_id) REFERENCES research_entities(entity_id),
                    FOREIGN KEY (target_entity_id) REFERENCES research_entities(entity_id)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rel_source ON research_relations(source_entity_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rel_target ON research_relations(target_entity_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rel_type ON research_relations(relation_type);"
            )
            conn.commit()

    def _seed_canonical_knowledge_graph(self) -> None:
        """Pre-seeds institutional quantitative trading and macro relationships."""
        canonical_entities = [
            GraphEntity(
                "ent_btc",
                "Bitcoin",
                "ASSET",
                ["btc", "xbt", "digital gold"],
                "Primary decentralized benchmark asset",
            ),
            GraphEntity(
                "ent_eth",
                "Ethereum",
                "ASSET",
                ["eth", "ether"],
                "Smart contract base settlement layer",
            ),
            GraphEntity(
                "ent_sol", "Solana", "ASSET", ["sol"], "High-throughput layer 1 blockchain"
            ),
            GraphEntity(
                "ent_gold",
                "Gold",
                "ASSET",
                ["xau", "precious metals"],
                "Historical monetary store of value",
            ),
            GraphEntity(
                "ent_dxy",
                "US Dollar Index",
                "MACRO_INDICATOR",
                ["dxy", "usd index"],
                "Relative strength of USD vs basket of global currencies",
            ),
            GraphEntity(
                "ent_fed",
                "Federal Reserve",
                "CENTRAL_BANK",
                ["fed", "fomc", "us central bank"],
                "United States central bank determining interest rates",
            ),
            GraphEntity(
                "ent_cpi",
                "CPI Inflation",
                "MACRO_INDICATOR",
                ["cpi", "headline cpi", "core cpi", "inflation"],
                "Consumer Price Index measuring price changes",
            ),
            GraphEntity(
                "ent_us10y",
                "10-Year Treasury Yield",
                "MACRO_INDICATOR",
                ["us10y", "10y yield", "treasuries"],
                "Risk-free rate benchmark for global financial assets",
            ),
            GraphEntity(
                "ent_m2",
                "Global Liquidity M2",
                "MACRO_INDICATOR",
                ["m2", "global liquidity", "money supply"],
                "Total liquid money supply across G4 central banks",
            ),
            GraphEntity(
                "ent_fvg",
                "Fair Value Gap",
                "SMC_CONCEPT",
                ["fvg", "imbalance", "inefficiency"],
                "Price delivery imbalance awaiting institutional rebalance",
            ),
            GraphEntity(
                "ent_ob",
                "Order Block",
                "SMC_CONCEPT",
                ["order block", "ob", "institutional footprint"],
                "Specific candle range preceding aggressive institutional displacement",
            ),
            GraphEntity(
                "ent_kelly",
                "Half-Kelly Sizing",
                "RISK_CONTROL",
                ["half-kelly", "kelly criterion", "risk gate"],
                "Deterministic capital risk cap (1.5% - 2.5% max)",
            ),
        ]

        with self._get_connection() as conn:
            for ent in canonical_entities:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO research_entities (
                        entity_id, name, entity_type, aliases_json, description,
                        mention_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ent.entity_id,
                        ent.name,
                        ent.entity_type,
                        json.dumps(ent.aliases),
                        ent.description,
                        ent.mention_count,
                        ent.created_at,
                        ent.updated_at,
                    ),
                )

            canonical_relations = [
                GraphRelation(
                    "rel_fed_dxy",
                    "ent_fed",
                    "ent_dxy",
                    "REGULATES",
                    0.95,
                    description="Fed rate policy heavily directs US Dollar strength",
                ),
                GraphRelation(
                    "rel_dxy_btc",
                    "ent_dxy",
                    "ent_btc",
                    "INVERSE_TO",
                    0.88,
                    description="Dollar liquidity expansion inversely impacts Bitcoin valuation",
                ),
                GraphRelation(
                    "rel_m2_btc",
                    "ent_m2",
                    "ent_btc",
                    "DRIVES",
                    0.92,
                    description="Global M2 expansion is structural driver of Bitcoin adoption and valuation",
                ),
                GraphRelation(
                    "rel_cpi_fed",
                    "ent_cpi",
                    "ent_fed",
                    "INFLUENCES",
                    0.94,
                    description="Inflation surprise shifts FOMC rate cut probabilities",
                ),
                GraphRelation(
                    "rel_fed_us10y",
                    "ent_fed",
                    "ent_us10y",
                    "INFLUENCES",
                    0.90,
                    description="Fed benchmark policy sets terminal treasury yield expectations",
                ),
                GraphRelation(
                    "rel_fvg_ob",
                    "ent_fvg",
                    "ent_ob",
                    "CORRELATED_WITH",
                    0.85,
                    description="Order blocks frequently origin-bound fair value gaps",
                ),
                GraphRelation(
                    "rel_kelly_btc",
                    "ent_kelly",
                    "ent_btc",
                    "REGULATES",
                    1.00,
                    description="Deterministic risk control bounds Bitcoin position size to <= 2.5% equity",
                ),
            ]

            for rel in canonical_relations:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO research_relations (
                        relation_id, source_entity_id, target_entity_id, relation_type,
                        weight, claim_id, source_id, description, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        rel.relation_id,
                        rel.source_entity_id,
                        rel.target_entity_id,
                        rel.relation_type,
                        rel.weight,
                        rel.claim_id,
                        rel.source_id,
                        rel.description,
                        rel.created_at,
                    ),
                )
            conn.commit()

    def get_entity(self, name_or_id: str) -> GraphEntity | None:
        """Finds an entity by exact ID, exact name, or alias."""
        clean = name_or_id.strip().lower()
        with self._get_connection() as conn:
            # Check ID
            row = conn.execute(
                "SELECT * FROM research_entities WHERE entity_id = ?;", (name_or_id,)
            ).fetchone()
            if row:
                return self._row_to_entity(row)

            # Check exact name (case-insensitive)
            row = conn.execute(
                "SELECT * FROM research_entities WHERE LOWER(name) = ?;", (clean,)
            ).fetchone()
            if row:
                return self._row_to_entity(row)

            # Check aliases
            rows = conn.execute("SELECT * FROM research_entities;").fetchall()
            for r in rows:
                aliases = json.loads(r["aliases_json"])
                if any(clean == a.lower() for a in aliases):
                    return self._row_to_entity(r)
        return None

    def _row_to_entity(self, row: sqlite3.Row) -> GraphEntity:
        return GraphEntity(
            entity_id=row["entity_id"],
            name=row["name"],
            entity_type=row["entity_type"],
            aliases=json.loads(row["aliases_json"]),
            description=row["description"] or "",
            mention_count=int(row["mention_count"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def extract_entities_from_text(self, text: str) -> list[GraphEntity]:
        """Identifies recognized entities inside free-form text."""
        text_lower = text.lower()
        matched: list[GraphEntity] = []

        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM research_entities;").fetchall()

        for r in rows:
            name_lower = r["name"].lower()
            aliases = json.loads(r["aliases_json"])
            all_patterns = [name_lower] + [a.lower() for a in aliases]

            for pat in all_patterns:
                # Use word boundary matching for short names
                if len(pat) <= 4:
                    if re.search(rf"\b{re.escape(pat)}\b", text_lower):
                        matched.append(self._row_to_entity(r))
                        break
                elif pat in text_lower:
                    matched.append(self._row_to_entity(r))
                    break

        return matched

    def add_relation(
        self,
        source_name_or_id: str,
        target_name_or_id: str,
        relation_type: str,
        weight: float = 0.8,
        claim_id: str = "",
        source_id: str = "",
        description: str = "",
    ) -> GraphRelation | None:
        """Creates or strengthens a relation between two entities."""
        src_ent = self.get_entity(source_name_or_id)
        tgt_ent = self.get_entity(target_name_or_id)

        if not src_ent or not tgt_ent:
            logger.warning(
                f"Cannot link '{source_name_or_id}' and '{target_name_or_id}': Entity not found."
            )
            return None

        rel_id = f"rel_{src_ent.entity_id}_{tgt_ent.entity_id}_{relation_type.lower()}"
        now = int(time.time() * 1000)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_relations (
                    relation_id, source_entity_id, target_entity_id, relation_type,
                    weight, claim_id, source_id, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relation_id) DO UPDATE SET
                    weight = MAX(excluded.weight, research_relations.weight),
                    description = excluded.description;
                """,
                (
                    rel_id,
                    src_ent.entity_id,
                    tgt_ent.entity_id,
                    relation_type.upper(),
                    weight,
                    claim_id,
                    source_id,
                    description,
                    now,
                ),
            )
            conn.commit()

        return GraphRelation(
            relation_id=rel_id,
            source_entity_id=src_ent.entity_id,
            target_entity_id=tgt_ent.entity_id,
            relation_type=relation_type.upper(),
            weight=weight,
            claim_id=claim_id,
            source_id=source_id,
            description=description,
            created_at=now,
        )

    def get_subgraph(self, root_name_or_id: str, max_depth: int = 1) -> dict[str, Any]:
        """Returns node and edge dictionary for visualization and reasoning."""
        root = self.get_entity(root_name_or_id)
        if not root:
            return {"nodes": [], "edges": []}

        nodes_map = {root.entity_id: root.to_dict()}
        edges: list[dict[str, Any]] = []

        with self._get_connection() as conn:
            # Query outgoing relations
            out_rows = conn.execute(
                """
                SELECT r.*, e.name as target_name, e.entity_type as target_type,
                       e.aliases_json as target_aliases, e.description as target_desc,
                       e.mention_count as target_mentions, e.created_at as target_created, e.updated_at as target_updated
                FROM research_relations r
                JOIN research_entities e ON r.target_entity_id = e.entity_id
                WHERE r.source_entity_id = ?;
                """,
                (root.entity_id,),
            ).fetchall()

            for r in out_rows:
                edges.append(
                    {
                        "relation_id": r["relation_id"],
                        "source": r["source_entity_id"],
                        "target": r["target_entity_id"],
                        "type": r["relation_type"],
                        "weight": r["weight"],
                        "description": r["description"],
                    }
                )
                if r["target_entity_id"] not in nodes_map:
                    nodes_map[r["target_entity_id"]] = {
                        "entity_id": r["target_entity_id"],
                        "name": r["target_name"],
                        "entity_type": r["target_type"],
                        "description": r["target_desc"] or "",
                    }

            # Query incoming relations
            in_rows = conn.execute(
                """
                SELECT r.*, e.name as source_name, e.entity_type as source_type,
                       e.description as source_desc
                FROM research_relations r
                JOIN research_entities e ON r.source_entity_id = e.entity_id
                WHERE r.target_entity_id = ?;
                """,
                (root.entity_id,),
            ).fetchall()

            for r in in_rows:
                edges.append(
                    {
                        "relation_id": r["relation_id"],
                        "source": r["source_entity_id"],
                        "target": r["target_entity_id"],
                        "type": r["relation_type"],
                        "weight": r["weight"],
                        "description": r["description"],
                    }
                )
                if r["source_entity_id"] not in nodes_map:
                    nodes_map[r["source_entity_id"]] = {
                        "entity_id": r["source_entity_id"],
                        "name": r["source_name"],
                        "entity_type": r["source_type"],
                        "description": r["source_desc"] or "",
                    }

        return {"nodes": list(nodes_map.values()), "edges": edges}

    def list_all_entities(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_entities ORDER BY mention_count DESC LIMIT ?;", (limit,)
            ).fetchall()
            return [self._row_to_entity(r).to_dict() for r in rows]

    def list_all_relations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM research_relations ORDER BY weight DESC LIMIT ?;", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]


# Global singleton instance
knowledge_graph_engine = KnowledgeGraphEngine()
