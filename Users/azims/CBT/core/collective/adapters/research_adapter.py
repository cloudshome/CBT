"""
core/collective/adapters/research_adapter.py
============================================
Adapts Research Lab knowledge discovery and epistemic verification into immutable SDCC events.
Enforces Section 3 & 48:
1. Source provides provenance, not ontology.
2. Neutral representation with evidence status, confidence, and empirical results.
"""

from __future__ import annotations

import logging
from typing import Any

from core.collective.event import build_canonical_event
from core.collective.event_store import EventStore, event_store
from core.collective.event_types import CollectiveEventType
from core.collective.identity import NodeIdentity, node_identity_manager

logger = logging.getLogger("sky.collective.adapter.research")


class ResearchEventAdapter:
    """Emits canonical Class A events for research, claims, hypotheses, and evidence."""

    def __init__(
        self,
        identity: NodeIdentity | None = None,
        store: EventStore | None = None,
    ):
        self.identity = identity or node_identity_manager.get_or_create_identity()
        self.store = store or event_store

    def emit_source_registered(
        self,
        source_id: str,
        title: str,
        source_uri: str,
        author: str,
        source_type: str = "RESEARCH_LAB",
        content_hash: str | None = None,
    ) -> str:
        """Emits RESEARCH_SOURCE_REGISTERED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "source_id": source_id,
            "title": title,
            "source_uri": source_uri,
            "author": author,
            "content_hash": content_hash,
        }
        prov = {
            "source_type": source_type,
            "node_id": self.identity.node_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.RESEARCH_SOURCE_REGISTERED,
            entity_type="source",
            entity_id=source_id,
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        logger.info(f"Emitted {event.event_id} for registered source {source_id} ('{title}')")
        return event.event_id

    def emit_claim_created(
        self,
        claim_id: str,
        statement: str,
        source_id: str,
        confidence: float = 0.5,
        worldview: str = "SMC_QUANTITATIVE",
    ) -> str:
        """Emits CLAIM_CREATED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "claim_id": claim_id,
            "statement": statement,
            "confidence": float(confidence),
            "worldview": worldview,
        }
        prov = {
            "source_type": "RESEARCH_LAB",
            "node_id": self.identity.node_id,
            "source_id": source_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.CLAIM_CREATED,
            entity_type="claim",
            entity_id=claim_id,
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        return event.event_id

    def emit_evidence_attached(
        self,
        evidence_id: str,
        claim_id: str,
        verdict: str,
        evidence_grade: int,  # 0=FABRICATED, 1=SIMULATED, 2=IMPUTED, 3=EMPIRICAL
        sample_size: int,
        p_value: float,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Emits EVIDENCE_ATTACHED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "evidence_id": evidence_id,
            "claim_id": claim_id,
            "verdict": verdict,
            "evidence_grade": evidence_grade,
            "sample_size": sample_size,
            "statistical_p_value": p_value,
            "details": details or {},
        }
        prov = {
            "source_type": "EVIDENCE_VAULT",
            "node_id": self.identity.node_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.EVIDENCE_ATTACHED,
            entity_type="evidence",
            entity_id=evidence_id,
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        return event.event_id

    def emit_hypothesis_rejected(
        self,
        hypothesis_id: str,
        reason: str,
        autopsy_notes: str,
    ) -> str:
        """Emits HYPOTHESIS_REJECTED event."""
        seq = self.store.sequence_manager.next_sequence(self.identity.node_id)
        payload = {
            "hypothesis_id": hypothesis_id,
            "reason": reason,
            "autopsy_notes": autopsy_notes,
        }
        prov = {
            "source_type": "RESEARCH_LAB",
            "node_id": self.identity.node_id,
        }

        event = build_canonical_event(
            node_id=self.identity.node_id,
            sequence=seq,
            event_type=CollectiveEventType.HYPOTHESIS_REJECTED,
            entity_type="hypothesis",
            entity_id=hypothesis_id,
            payload=payload,
            provenance=prov,
        )

        self.store.append_event(event)
        return event.event_id


research_adapter = ResearchEventAdapter()
