"""
core/collective/sequence.py
===========================
Monotonic sequence manager for local node events.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("sky.collective.sequence")


class SequenceManager:
    """Manages monotonically increasing local event sequence numbers."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collective_sequences (
                    node_id TEXT PRIMARY KEY,
                    current_sequence INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_current_sequence(self, node_id: str) -> int:
        """Returns the current highest sequence for a node (default 0)."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.execute(
                "SELECT current_sequence FROM collective_sequences WHERE node_id = ?",
                (node_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def next_sequence(self, node_id: str) -> int:
        """Atomically increments and returns the next sequence number."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.execute(
                """
                INSERT INTO collective_sequences (node_id, current_sequence)
                VALUES (?, 1)
                ON CONFLICT(node_id) DO UPDATE SET
                    current_sequence = current_sequence + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING current_sequence;
                """,
                (node_id,),
            )
            val = cur.fetchone()[0]
            conn.commit()
            return int(val)
        finally:
            conn.close()

    def set_sequence(self, node_id: str, sequence: int) -> None:
        """Sets the sequence if greater than current."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            conn.execute(
                """
                INSERT INTO collective_sequences (node_id, current_sequence)
                VALUES (?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    current_sequence = MAX(current_sequence, excluded.current_sequence),
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (node_id, sequence),
            )
            conn.commit()
        finally:
            conn.close()
