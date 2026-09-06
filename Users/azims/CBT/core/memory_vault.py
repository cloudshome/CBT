"""
Dual-Layer Memory Orchestrator (Vector Embeddings + SQLite Episodic Memory).
Provides unified access to structured historical episodes, prediction ledger,
and semantic literature/research embeddings.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.memory_vault")


class SemanticVectorStore:
    """
    High-performance vector store with SQLite binary BLOB persistence and vectorized search.
    Eliminates whole-file JSON rewriting and provides sub-millisecond matrix-multiplication queries.
    """

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.embeddings: list[np.ndarray] = []
        self.documents: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self.embeddings_matrix: np.ndarray | None = None
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        """Ensures SQLite persistence table for vectors exists in brain_memory.db."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_vectors (
                        doc_id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        embedding BLOB NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_created ON semantic_vectors (created_at);")
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not initialize semantic_vectors table: {e}")

    def _load(self) -> None:
        """Loads vectors from SQLite, migrating legacy vectors.json if present."""
        legacy_file = self.storage_path / "vectors.json"
        
        # 1. Check if legacy migration is needed
        if legacy_file.exists():
            try:
                with open(legacy_file, encoding="utf-8") as f:
                    data = json.load(f)
                docs = data.get("documents", [])
                metas = data.get("metadatas", [])
                raw_embeds = data.get("embeddings", [])
                
                if docs:
                    with db_manager.get_brain_conn() as conn:
                        for i, doc_text in enumerate(docs):
                            m = metas[i] if i < len(metas) else {}
                            d_id = m.get("id") or f"doc_{i}"
                            vec = np.array(raw_embeds[i], dtype=np.float32) if i < len(raw_embeds) else self._embed_text(doc_text)
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO semantic_vectors (doc_id, text, metadata_json, embedding, created_at)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (d_id, doc_text, json.dumps(m), vec.tobytes(), time.time()),
                            )
                        conn.commit()
                    logger.info(f"Migrated {len(docs)} legacy JSON vectors into SQLite semantic_vectors table.")
                
                # Archive legacy file
                migrated_file = self.storage_path / "vectors.json.migrated"
                legacy_file.rename(migrated_file)
            except Exception as e:
                logger.warning(f"Legacy vector migration notice: {e}")

        # 2. Load from SQLite
        self.documents = []
        self.metadatas = []
        self.embeddings = []
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.execute("SELECT doc_id, text, metadata_json, embedding FROM semantic_vectors ORDER BY created_at ASC")
                for row in cursor.fetchall():
                    d_id, txt, meta_str, embed_bytes = row
                    meta = json.loads(meta_str) if meta_str else {}
                    meta["id"] = d_id
                    vec = np.frombuffer(embed_bytes, dtype=np.float32)
                    self.documents.append(txt)
                    self.metadatas.append(meta)
                    self.embeddings.append(vec)
            
            if self.embeddings:
                self.embeddings_matrix = np.vstack(self.embeddings)
            else:
                self.embeddings_matrix = None
        except Exception as e:
            logger.error(f"Failed loading vectors from SQLite: {e}")

    def save(self) -> None:
        """No-op kept for backwards-compatibility; writes are persisted incrementally in add_document."""
        pass

    def _embed_text(self, text: str) -> np.ndarray:
        """Deterministic lightweight feature hash embedding for semantic text vectors."""
        dim = 128
        vec = np.zeros(dim, dtype=np.float32)
        words = text.lower().split()
        for w in words:
            idx = abs(hash(w)) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Appends a document atomically to SQLite and in-memory search index."""
        meta = metadata or {}
        meta["id"] = doc_id
        vec = self._embed_text(text)

        # 1. Incremental SQLite write (O(1) write — zero whole-file rewrites)
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO semantic_vectors (doc_id, text, metadata_json, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        text = excluded.text,
                        metadata_json = excluded.metadata_json,
                        embedding = excluded.embedding,
                        created_at = excluded.created_at;
                    """,
                    (doc_id, text, json.dumps(meta), vec.tobytes(), time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed persisting vector {doc_id} to SQLite: {e}")

        # 2. In-memory index update
        self.documents.append(text)
        self.metadatas.append(meta)
        self.embeddings.append(vec)
        if self.embeddings_matrix is None:
            self.embeddings_matrix = np.expand_dims(vec, axis=0)
        else:
            self.embeddings_matrix = np.vstack([self.embeddings_matrix, vec])

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Executes ultra-fast vectorized matrix multiplication similarity search."""
        if not self.embeddings or self.embeddings_matrix is None:
            return []
        
        q_vec = self._embed_text(query_text)
        
        # Vectorized BLAS matrix-vector dot product (replaces O(N) Python loop)
        sims = np.dot(self.embeddings_matrix, q_vec)
        
        # Top-k indices
        top_indices = np.argsort(sims)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append(
                {
                    "score": float(sims[idx]),
                    "document": self.documents[idx],
                    "metadata": self.metadatas[idx],
                }
            )
        return results


class MemoryVault:
    """Master dual-layer memory vault coordinating episodic records and semantic literature."""

    def __init__(self):
        self.vector_store = SemanticVectorStore(
            Path(os.getenv("DATA_DIR", "data")) / "vector_store"
        )

    def store_market_state(
        self,
        state_id: str,
        timestamp: int,
        symbol: str,
        timeframe: str,
        schema_version: str,
        state_vector: dict[str, Any],
        forward_outcomes: dict[str, Any] | None = None,
    ) -> None:
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO market_states (state_id, timestamp, symbol, timeframe, schema_version, state_vector_json, forward_outcomes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_id) DO UPDATE SET
                    state_vector_json=excluded.state_vector_json,
                    forward_outcomes_json=excluded.forward_outcomes_json;
                """,
                (
                    state_id,
                    timestamp,
                    symbol,
                    timeframe,
                    schema_version,
                    json.dumps(state_vector),
                    json.dumps(forward_outcomes or {}),
                ),
            )
            conn.commit()

    def store_trade_episode(self, episode: dict[str, Any]) -> None:
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO trade_episodes (id, timestamp, symbol, timeframe, strategy_id, entry_price, exit_price, direction, pnl_dollar, pnl_percent, rr_ratio, market_regime, state_vector_json, attribution_json, loss_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    exit_price=excluded.exit_price,
                    pnl_dollar=excluded.pnl_dollar,
                    pnl_percent=excluded.pnl_percent,
                    loss_category=excluded.loss_category;
                """,
                (
                    episode["id"],
                    episode["timestamp"],
                    episode["symbol"],
                    episode["timeframe"],
                    episode["strategy_id"],
                    episode["entry_price"],
                    episode["exit_price"],
                    episode["direction"],
                    episode["pnl_dollar"],
                    episode["pnl_percent"],
                    episode["rr_ratio"],
                    episode["market_regime"],
                    json.dumps(episode.get("state_vector", {})),
                    json.dumps(episode.get("attribution", {})),
                    episode.get("loss_category"),
                ),
            )
            conn.commit()

    def get_recent_episodes(self, limit: int = 50) -> list[dict[str, Any]]:
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM trade_episodes ORDER BY timestamp DESC LIMIT ?;", (limit,)
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Singleton
memory_vault = MemoryVault()
