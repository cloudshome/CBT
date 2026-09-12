"""
core/collective/checkpoint.py
=============================
Vector clock checkpoint tracking imported event sequences across all collective nodes.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("sky.collective.checkpoint")


class VectorCheckpoint:
    """Tracks the highest sequence number imported from every known node."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.checkpoint_file = self.checkpoints_dir / "vector_checkpoint.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        if not self.checkpoint_file.exists():
            self._save({})

    def _load(self) -> dict[str, int]:
        try:
            with open(self.checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)
                return {k: int(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"Could not load vector checkpoint from {self.checkpoint_file}: {exc}")
            return {}

    def _save(self, data: dict[str, int]) -> None:
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def get_imported_sequence(self, node_id: str) -> int:
        """Returns the highest contiguous sequence number imported for node_id."""
        data = self._load()
        return data.get(node_id, 0)

    def update_checkpoint(self, node_id: str, sequence: int) -> None:
        """Updates checkpoint for node_id if sequence is higher."""
        data = self._load()
        current = data.get(node_id, 0)
        if sequence > current:
            data[node_id] = sequence
            self._save(data)
            logger.debug(f"Advanced checkpoint for {node_id}: {current} -> {sequence}")

    def get_vector_clock(self) -> dict[str, int]:
        """Returns the full vector clock snapshot."""
        return self._load()

    def compute_missing_range(
        self,
        peer_node_id: str,
        peer_last_sequence: int,
    ) -> tuple[int, int] | None:
        """
        Determines the exact sequence range needed from peer_node_id.
        Returns (from_seq, to_seq) or None if up to date.
        """
        last_imported = self.get_imported_sequence(peer_node_id)
        if peer_last_sequence > last_imported:
            return (last_imported + 1, peer_last_sequence)
        return None


vector_checkpoint = VectorCheckpoint()
