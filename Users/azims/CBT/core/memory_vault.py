"""
Dual-Layer Memory Orchestrator (Vector Embeddings + SQLite Episodic Memory).
Provides unified access to structured historical episodes, prediction ledger,
and semantic literature/research embeddings.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.memory_vault")


class SemanticVectorStore:
    """
    Lightweight, high-performance in-memory vector store with disk persistence.
    Provides fast cosine similarity retrieval without heavy external dependencies.
    """

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.embeddings: list[np.ndarray] = []
        self.documents: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        file_path = self.storage_path / "vectors.json"
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.documents = data.get("documents", [])
                    self.metadatas = data.get("metadatas", [])
                    raw_embeds = data.get("embeddings", [])
                    self.embeddings = [np.array(e, dtype=np.float32) for e in raw_embeds]
            except Exception as e:  # noqa: BLE001 — defensive fallback
                logger.error(f"Failed loading vector store: {e}")

    def save(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_path / "vectors.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "documents": self.documents,
                    "metadatas": self.metadatas,
                    "embeddings": [e.tolist() for e in self.embeddings],
                },
                f,
                indent=2,
            )

    def _embed_text(self, text: str) -> np.ndarray:
        """
        Deterministic lightweight feature hash embedding for semantic text vectors.
        In production, can be upgraded to sentence-transformers or Gemini embeddings.
        """
        dim = 128
        vec = np.zeros(dim, dtype=np.float32)
        words = text.lower().split()
        for w in words:
            idx = abs(hash(w)) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        meta = metadata or {}
        meta["id"] = doc_id
        vec = self._embed_text(text)
        self.documents.append(text)
        self.metadatas.append(meta)
        self.embeddings.append(vec)
        self.save()

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.embeddings:
            return []
        q_vec = self._embed_text(query_text)
        scores = []
        for i, doc_vec in enumerate(self.embeddings):
            sim = float(np.dot(q_vec, doc_vec))
            scores.append((sim, i))
        scores.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, idx in scores[:top_k]:
            results.append(
                {
                    "score": sim,
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
