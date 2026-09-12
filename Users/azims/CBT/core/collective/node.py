"""
core/collective/node.py
=======================
Node operational state, node registry, and health telemetry.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sky.collective.node")


class NodeOperationalState(StrEnum):
    ONLINE = "ONLINE"
    SYNCING = "SYNCING"
    OFFLINE = "OFFLINE"
    RECOVERY = "RECOVERY"
    READ_ONLY = "READ_ONLY"


@dataclass
class PeerNodeInfo:
    """Registry record for a known collective peer node."""

    node_id: str
    public_key_hex: str
    last_seen_at: str
    status: NodeOperationalState = NodeOperationalState.OFFLINE
    last_imported_sequence: int = 0
    highest_known_sequence: int = 0
    protocol_version: int = 1
    schema_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        return d


class NodeRegistry:
    """In-memory and persisted registry of known cluster nodes."""

    def __init__(self):
        self._peers: dict[str, PeerNodeInfo] = {}

    def register_or_update_peer(
        self,
        node_id: str,
        public_key_hex: str,
        highest_sequence: int = 0,
        protocol_version: int = 1,
        schema_version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> PeerNodeInfo:
        """Registers a newly discovered peer or updates known sequence numbers."""
        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        if node_id in self._peers:
            peer = self._peers[node_id]
            peer.last_seen_at = now_iso
            peer.status = NodeOperationalState.ONLINE
            peer.highest_known_sequence = max(peer.highest_known_sequence, highest_sequence)
            if metadata:
                peer.metadata.update(metadata)
        else:
            peer = PeerNodeInfo(
                node_id=node_id,
                public_key_hex=public_key_hex,
                last_seen_at=now_iso,
                status=NodeOperationalState.ONLINE,
                highest_known_sequence=highest_sequence,
                protocol_version=protocol_version,
                schema_version=schema_version,
                metadata=metadata or {},
            )
            self._peers[node_id] = peer
            logger.info(f"Registered collective peer node: {node_id}")
        return peer

    def get_peer(self, node_id: str) -> PeerNodeInfo | None:
        return self._peers.get(node_id)

    def list_peers(self) -> list[PeerNodeInfo]:
        return list(self._peers.values())

    def update_imported_sequence(self, node_id: str, sequence: int) -> None:
        if node_id in self._peers:
            self._peers[node_id].last_imported_sequence = max(
                self._peers[node_id].last_imported_sequence, sequence
            )


node_registry = NodeRegistry()
