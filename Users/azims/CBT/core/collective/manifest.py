"""
core/collective/manifest.py
===========================
Signed event manifest generation and verification for SDCC sync packages.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.collective.checkpoint import VectorCheckpoint
from core.collective.event_hash import canonical_json_bytes, sha256_digest
from core.collective.event_store import EventStore
from core.collective.identity import NodeIdentity

MANIFEST_VERSION = 1
PROTOCOL_VERSION = 1
SCHEMA_VERSION = 1


@dataclass
class EventManifest:
    """Cryptographically signed manifest describing a node's event corpus."""

    manifest_version: int
    protocol_version: int
    schema_version: int
    node_id: str
    created_at: str
    events: dict[str, int]  # {"first_sequence": int, "last_sequence": int, "count": int}
    vector_clock: dict[str, int]
    content_sha256: str
    knowledge_head: str | None
    artifact_count: int
    signature: str = ""

    def get_signable_bytes(self) -> bytes:
        """Returns canonical JSON bytes of the manifest excluding signature."""
        data = {
            "manifest_version": self.manifest_version,
            "protocol_version": self.protocol_version,
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "created_at": self.created_at,
            "events": self.events,
            "vector_clock": self.vector_clock,
            "content_sha256": self.content_sha256,
            "knowledge_head": self.knowledge_head,
            "artifact_count": self.artifact_count,
        }
        return canonical_json_bytes(data)

    def sign(self, identity: NodeIdentity) -> None:
        """Signs the manifest using the node's Ed25519 private key."""
        signable = self.get_signable_bytes()
        self.signature = identity.sign(signable)

    def verify_signature(self, public_key_hex: str) -> bool:
        """Verifies the Ed25519 signature against the peer's public key."""
        if not self.signature:
            return False
        signable = self.get_signable_bytes()
        temp_id = NodeIdentity(
            node_id=self.node_id,
            installation_id="",
            public_key_hex=public_key_hex,
            created_at="",
        )
        return temp_id.verify(signable, self.signature, public_key_hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventManifest:
        return cls(
            manifest_version=data.get("manifest_version", MANIFEST_VERSION),
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            node_id=data["node_id"],
            created_at=data["created_at"],
            events=data["events"],
            vector_clock=data.get("vector_clock", {}),
            content_sha256=data["content_sha256"],
            knowledge_head=data.get("knowledge_head"),
            artifact_count=data.get("artifact_count", 0),
            signature=data.get("signature", ""),
        )


def build_node_manifest(
    identity: NodeIdentity,
    event_store: EventStore,
    checkpoint: VectorCheckpoint,
    from_sequence: int = 1,
    to_sequence: int | None = None,
    knowledge_head: str | None = None,
    artifact_count: int = 0,
) -> EventManifest:
    """
    Constructs and signs a canonical manifest for the node's local events.
    """
    highest_seq = event_store.get_highest_sequence(identity.node_id)
    effective_to = to_sequence or highest_seq
    effective_from = min(from_sequence, effective_to) if effective_to > 0 else 0

    events = event_store.get_events(identity.node_id, from_sequence=effective_from, to_sequence=effective_to)
    event_count = len(events)

    # Compute content SHA-256 over all event bytes
    all_event_hashes = "".join(e.integrity["event_sha256"] for e in events)
    content_sha256 = sha256_digest(all_event_hashes)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clock = checkpoint.get_vector_clock()
    clock[identity.node_id] = highest_seq

    manifest = EventManifest(
        manifest_version=MANIFEST_VERSION,
        protocol_version=PROTOCOL_VERSION,
        schema_version=SCHEMA_VERSION,
        node_id=identity.node_id,
        created_at=now_iso,
        events={
            "first_sequence": effective_from,
            "last_sequence": effective_to,
            "count": event_count,
        },
        vector_clock=clock,
        content_sha256=content_sha256,
        knowledge_head=knowledge_head,
        artifact_count=artifact_count,
    )

    manifest.sign(identity)
    return manifest
