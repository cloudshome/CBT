"""
core/collective/routes.py
=========================
FastAPI REST API router for SDCC Collective Health, Status, and Controls.
Section 56: Required API endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.collective.checkpoint import vector_checkpoint
from core.collective.conflict import conflict_manager
from core.collective.event_store import event_store
from core.collective.identity import node_identity_manager
from core.collective.node import node_registry
from core.collective.quarantine import quarantine_manager
from core.collective.reconciler import collective_reconciler
from core.collective.sync_engine import sync_engine

logger = logging.getLogger("sky.collective.api")

router = APIRouter(prefix="/api/collective", tags=["collective"])


class SyncResponse(BaseModel):
    status: str
    receipts: list[dict[str, Any]]


class RebuildResponse(BaseModel):
    status: str
    state_hash: str
    events_reduced: int
    open_positions: int
    closed_trades: int
    sources_rebuilt: int
    evidence_rebuilt: int


@router.get("/status")
def get_collective_status() -> dict[str, Any]:
    """Returns comprehensive health, node, event, and conflict statistics."""
    identity = node_identity_manager.get_or_create_identity()
    peers = node_registry.list_peers()
    total_events = event_store.get_total_count()
    highest_seq = event_store.get_highest_sequence(identity.node_id)
    conflicts = conflict_manager.list_conflicts(unresolved_only=True)
    quarantined = quarantine_manager.get_quarantine_count()
    vector_clock = vector_checkpoint.get_vector_clock()

    return {
        "node_id": identity.node_id,
        "protocol_version": identity.protocol_version,
        "schema_version": identity.schema_version,
        "status": "ONLINE",
        "total_events": total_events,
        "local_sequence": highest_seq,
        "known_peers_count": len(peers),
        "unresolved_conflicts": len(conflicts),
        "quarantined_events": quarantined,
        "vector_clock": vector_clock,
        "installation_id": identity.installation_id,
    }


@router.get("/nodes")
def get_collective_nodes() -> dict[str, Any]:
    """Returns list of all cluster nodes, last seen timestamps, and sequence progress."""
    identity = node_identity_manager.get_or_create_identity()
    peers = [p.to_dict() for p in node_registry.list_peers()]
    local_info = {
        "node_id": identity.node_id,
        "public_key_hex": identity.public_key_hex,
        "status": "ONLINE",
        "highest_known_sequence": event_store.get_highest_sequence(identity.node_id),
        "last_seen_at": "NOW",
        "is_self": True,
    }
    return {
        "local_node": local_info,
        "peer_nodes": peers,
    }


@router.get("/sync")
def get_sync_status() -> dict[str, Any]:
    """Returns sync receipts and outbox/inbox pending package counts."""
    inbox_pkgs = sync_engine.transport.list_inbox_packages()
    return {
        "pending_inbox_packages": len(inbox_pkgs),
        "inbox_peers": [peer_id for peer_id, _ in inbox_pkgs],
        "vector_clock": vector_checkpoint.get_vector_clock(),
    }


@router.post("/sync")
def trigger_sync() -> dict[str, Any]:
    """Forces an immediate synchronization cycle."""
    receipts = sync_engine.run_sync_cycle()
    return {
        "status": "SUCCESS",
        "receipts": [r.to_dict() for r in receipts],
    }


@router.get("/conflicts")
def get_conflicts(unresolved_only: bool = Query(default=False)) -> dict[str, Any]:
    """Returns recorded conflicts from disk."""
    records = conflict_manager.list_conflicts(unresolved_only=unresolved_only)
    return {
        "conflicts": [r.to_dict() for r in records],
        "count": len(records),
    }


@router.get("/events")
def get_events(
    node_id: str | None = Query(default=None),
    from_seq: int = Query(default=1),
    to_seq: int | None = Query(default=None),
    limit: int = Query(default=100),
) -> dict[str, Any]:
    """Returns events from the local event store."""
    if node_id:
        events = event_store.get_events(node_id, from_sequence=from_seq, to_sequence=to_seq)
    else:
        events = event_store.get_all_events()

    sliced = events[:limit]
    return {
        "events": [e.to_dict() for e in sliced],
        "count": len(sliced),
        "total": len(events),
    }


@router.get("/knowledge")
def get_collective_knowledge() -> dict[str, Any]:
    """Returns the current reduced collective knowledge vault and metrics."""
    state = collective_reconciler.reconcile_state()
    return {
        "state_hash": state.state_sha256,
        "sources": state.knowledge.sources,
        "claims": state.knowledge.claims,
        "evidence": state.knowledge.evidence,
        "hypotheses": state.knowledge.hypotheses,
        "contributions_by_node": state.knowledge.contributions_by_node,
    }


@router.post("/rebuild")
def trigger_rebuild() -> dict[str, Any]:
    """Triggers deterministic replay to reconstruct local SQLite projections."""
    result = collective_reconciler.rebuild_projections()
    return result


@router.post("/verify")
def trigger_verify() -> dict[str, Any]:
    """Performs integrity verification across all events and artifacts."""
    from core.collective.event_hash import verify_event_integrity

    all_events = event_store.get_all_events()
    corrupt_count = 0
    errors = []

    for ev in all_events:
        is_valid, err = verify_event_integrity(ev.to_dict())
        if not is_valid:
            corrupt_count += 1
            errors.append(f"{ev.event_id}: {err}")

    return {
        "status": "PASS" if corrupt_count == 0 else "FAIL",
        "total_events_checked": len(all_events),
        "corrupt_events_count": corrupt_count,
        "errors": errors[:10],
    }
