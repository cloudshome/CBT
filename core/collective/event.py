"""
core/collective/event.py
========================
Canonical Event Envelope and Factory for SDCC.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any

from core.collective.event_hash import compute_event_hash, compute_payload_hash
from core.collective.event_types import CollectiveEventType

CURRENT_EVENT_SCHEMA_VERSION = 1
CURRENT_PROTOCOL_VERSION = 1


@dataclass
class EventProvenance:
    """Provenance context declaring origin, execution environment, and dataset."""

    source_type: str  # "PAPER_ENGINE", "RESEARCH_LAB", "STRATEGY_LEAGUE", "AUTONOMOUS_TRADER"
    node_id: str
    source_id: str | None = None
    code_version: str | None = None
    dataset_id: str | None = None
    strategy_id: str | None = None
    config_hash: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class EventIntegrity:
    """Cryptographic integrity hashes for payload and envelope."""

    payload_sha256: str
    event_sha256: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class CanonicalEvent:
    """Class A Immutable Event Record."""

    event_id: str
    event_type: str
    schema_version: int
    protocol_version: int
    node_id: str
    sequence: int
    created_at: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    provenance: dict[str, Any]
    integrity: dict[str, str]
    causation_id: str | None = None
    correlation_id: str | None = None
    node_epoch: int = 1
    vector_clock: dict[str, int] = field(default_factory=dict)
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "node_id": self.node_id,
            "node_epoch": self.node_epoch,
            "sequence": self.sequence,
            "created_at": self.created_at,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "vector_clock": self.vector_clock,
            "payload": self.payload,
            "provenance": self.provenance,
            "integrity": self.integrity,
        }
        if self.signature:
            d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalEvent:
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            schema_version=data.get("schema_version", CURRENT_EVENT_SCHEMA_VERSION),
            protocol_version=data.get("protocol_version", CURRENT_PROTOCOL_VERSION),
            node_id=data["node_id"],
            sequence=data["sequence"],
            created_at=data["created_at"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            causation_id=data.get("causation_id"),
            correlation_id=data.get("correlation_id"),
            payload=data["payload"],
            provenance=data["provenance"],
            integrity=data["integrity"],
            node_epoch=data.get("node_epoch", 1),
            vector_clock=data.get("vector_clock", {}),
            signature=data.get("signature"),
        )


def build_canonical_event(
    node_id: str,
    sequence: int,
    event_type: CollectiveEventType | str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    provenance: EventProvenance | dict[str, Any],
    causation_id: str | None = None,
    correlation_id: str | None = None,
    created_at: str | None = None,
    node_epoch: int = 1,
    vector_clock: dict[str, int] | None = None,
    signature: str | None = None,
) -> CanonicalEvent:
    """
    Constructs an immutable CanonicalEvent with computed SHA-256 hashes and formatted event_id.
    """
    now_iso = created_at or datetime.datetime.now(datetime.UTC).isoformat()
    prov_dict = provenance.to_dict() if isinstance(provenance, EventProvenance) else provenance

    # Ensure node_id in provenance
    if "node_id" not in prov_dict:
        prov_dict["node_id"] = node_id

    # 1. Compute payload hash
    payload_hash = compute_payload_hash(payload)

    # 2. Build preliminary envelope for event hash calculation
    # Format event_id with 12-digit zero-padded sequence and 8-char hash prefix
    hash_prefix = payload_hash[:8]
    event_id = f"{node_id}:{sequence:012d}:{hash_prefix}"

    preliminary_dict = {
        "event_id": event_id,
        "event_type": str(event_type),
        "schema_version": CURRENT_EVENT_SCHEMA_VERSION,
        "protocol_version": CURRENT_PROTOCOL_VERSION,
        "node_id": node_id,
        "node_epoch": node_epoch,
        "sequence": sequence,
        "created_at": now_iso,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "vector_clock": vector_clock or {node_id: sequence},
        "payload": payload,
        "provenance": prov_dict,
    }

    # 3. Compute event hash
    event_hash = compute_event_hash(preliminary_dict)

    integrity_dict = {
        "payload_sha256": payload_hash,
        "event_sha256": event_hash,
    }

    return CanonicalEvent(
        event_id=event_id,
        event_type=str(event_type),
        schema_version=CURRENT_EVENT_SCHEMA_VERSION,
        protocol_version=CURRENT_PROTOCOL_VERSION,
        node_id=node_id,
        sequence=sequence,
        created_at=now_iso,
        entity_type=entity_type,
        entity_id=entity_id,
        causation_id=causation_id,
        correlation_id=correlation_id,
        payload=payload,
        provenance=prov_dict,
        integrity=integrity_dict,
        node_epoch=node_epoch,
        vector_clock=vector_clock or {node_id: sequence},
        signature=signature,
    )
