"""
core/collective/conflict.py
===========================
Explicit conflict classification, conflict set persistence, and reconciliation for SDCC.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.collective.conflict")


class ConflictType(StrEnum):
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    EVENT_HASH_MISMATCH = "EVENT_HASH_MISMATCH"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    ENTITY_ID_COLLISION = "ENTITY_ID_COLLISION"
    KNOWLEDGE_SEMANTIC_DUPLICATE = "KNOWLEDGE_SEMANTIC_DUPLICATE"
    KNOWLEDGE_CONTRADICTION = "KNOWLEDGE_CONTRADICTION"
    EXPERIMENT_DIVERGENCE = "EXPERIMENT_DIVERGENCE"
    PAPER_TRADE_COLLISION = "PAPER_TRADE_COLLISION"
    SCHEMA_INCOMPATIBILITY = "SCHEMA_INCOMPATIBILITY"
    PROVENANCE_MISSING = "PROVENANCE_MISSING"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"


@dataclass
class ConflictRecord:
    """Immutable conflict record documenting an epistemic or execution discrepancy."""

    conflict_id: str
    conflict_type: str
    detected_at: str
    source_node: str
    target_entity_id: str | None
    details: dict[str, Any]
    resolved: bool = False
    resolved_at: str | None = None
    resolution_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConflictRecord:
        return cls(
            conflict_id=data["conflict_id"],
            conflict_type=data["conflict_type"],
            detected_at=data["detected_at"],
            source_node=data["source_node"],
            target_entity_id=data.get("target_entity_id"),
            details=data.get("details", {}),
            resolved=data.get("resolved", False),
            resolved_at=data.get("resolved_at"),
            resolution_notes=data.get("resolution_notes"),
        )


class ConflictManager:
    """Coordinates persistence, querying, and resolution of collective conflicts."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.conflicts_dir = self.base_dir / "conflicts"
        self.conflicts_dir.mkdir(parents=True, exist_ok=True)

    def record_conflict(
        self,
        conflict_type: ConflictType | str,
        source_node: str,
        details: dict[str, Any],
        target_entity_id: str | None = None,
    ) -> ConflictRecord:
        """Persists a new conflict record to data/collective/conflicts/."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conflict_id = f"CONF-{int(datetime.datetime.now().timestamp()*1000)}-{uuid.uuid4().hex[:8]}"

        rec = ConflictRecord(
            conflict_id=conflict_id,
            conflict_type=str(conflict_type),
            detected_at=now_iso,
            source_node=source_node,
            target_entity_id=target_entity_id,
            details=details,
        )

        path = self.conflicts_dir / f"{conflict_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec.to_dict(), f, indent=2)

        logger.warning(f"Recorded collective conflict [{conflict_type}] for entity {target_entity_id}: {conflict_id}")
        return rec

    def create_knowledge_contradiction_set(
        self,
        claim_a: dict[str, Any],
        claim_b: dict[str, Any],
        context: dict[str, Any],
    ) -> ConflictRecord:
        """
        Creates a specialized CONFLICT_SET preserving both contradictory empirical claims.
        Neither claim is overwritten or deleted.
        """
        details = {
            "claim_a": claim_a,
            "claim_b": claim_b,
            "datasets": context.get("datasets", []),
            "market_regimes": context.get("market_regimes", []),
            "timeframes": context.get("timeframes", []),
            "code_versions": context.get("code_versions", []),
            "methodology": context.get("methodology", "empirical_comparison"),
        }
        return self.record_conflict(
            conflict_type=ConflictType.KNOWLEDGE_CONTRADICTION,
            source_node=claim_b.get("node_id", "UNKNOWN"),
            details=details,
            target_entity_id=claim_a.get("claim_id"),
        )

    def list_conflicts(
        self,
        conflict_type: str | None = None,
        unresolved_only: bool = False,
    ) -> list[ConflictRecord]:
        """Lists recorded conflicts from disk."""
        records: list[ConflictRecord] = []
        if not self.conflicts_dir.exists():
            return []

        for p in self.conflicts_dir.glob("CONF-*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rec = ConflictRecord.from_dict(data)
                if conflict_type and rec.conflict_type != conflict_type:
                    continue
                if unresolved_only and rec.resolved:
                    continue
                records.append(rec)
            except Exception as exc:
                logger.error(f"Error reading conflict file {p}: {exc}")

        records.sort(key=lambda x: x.detected_at, reverse=True)
        return records

    def resolve_conflict(self, conflict_id: str, notes: str) -> bool:
        """Marks a conflict as resolved with notes."""
        path = self.conflicts_dir / f"{conflict_id}.json"
        if not path.exists():
            return False

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["resolved"] = True
        data["resolved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data["resolution_notes"] = notes

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Resolved conflict {conflict_id}: {notes}")
        return True


conflict_manager = ConflictManager()
