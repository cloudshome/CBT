"""
core/collective/quarantine.py
=============================
Quarantine management and inspection for corrupted, invalid, or mismatched SDCC material.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.collective.quarantine")


class QuarantineManager:
    """Manages files in data/collective/events/quarantined/."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.quarantine_dir = self.base_dir / "events" / "quarantined"
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def quarantine_item(
        self,
        item_id: str,
        source_node: str,
        reason: str,
        raw_content: Any,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
    ) -> Path:
        """Quarantines an invalid event or artifact and writes an incident dossier."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        safe_id = item_id.replace(":", "_").replace("/", "_")
        filename = f"quarantine_{safe_id}.json"
        target_path = self.quarantine_dir / filename

        dossier = {
            "quarantined_at": now_iso,
            "item_id": item_id,
            "source_node": source_node,
            "reason": reason,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "raw_content": raw_content,
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(dossier, f, indent=2)

        logger.warning(f"Quarantined invalid item {item_id} from {source_node}: {reason}")
        return target_path

    def list_quarantined(self) -> list[dict[str, Any]]:
        """Returns all quarantined items."""
        items = []
        if not self.quarantine_dir.exists():
            return []

        for p in self.quarantine_dir.glob("quarantine_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    items.append(json.load(f))
            except Exception as exc:
                logger.error(f"Error reading quarantine file {p}: {exc}")

        items.sort(key=lambda x: x.get("quarantined_at", ""), reverse=True)
        return items

    def get_quarantine_count(self) -> int:
        """Returns the total number of quarantined items."""
        if not self.quarantine_dir.exists():
            return 0
        return len(list(self.quarantine_dir.glob("quarantine_*.json")))


quarantine_manager = QuarantineManager()
