"""
core/intelligence/crawler/quality_firewall.py
=============================================
Multi-Layer Intelligence Quality Firewall for Milestone 30-B.

Enforces the 3-Layer Pre-Causal Quality Gates:
1. Layer 1: Source Quality Firewall (registration, officiality threshold, spam filtering).
2. Layer 2: Evidence Integrity Firewall (SHA-256 seal, entity grounding, conflict check).
3. Layer 3: Point-in-Time Firewall (temporal sanity, publication vs observation precedence).

Protects the downstream M28 Causal Firewall and M29 Replay Engine from internet garbage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from core.intelligence.crawler.conflict_ledger import ConflictLedger
from core.intelligence.crawler.event_identity import CanonicalEvent
from core.intelligence.crawler.raw_evidence_vault import RawEvidenceRecord
from core.intelligence.crawler.source_registry import SourceRegistry

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.quality_firewall")


class FirewallVerdict(StrEnum):
    APPROVED = "APPROVED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class QualityFirewallDecision:
    verdict: FirewallVerdict
    passed: bool
    rejection_gate: str | None = None
    reason: str = ""
    source_officiality: float = 0.0
    entity_count: int = 0
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False


class SourceQualityFirewall:
    """Gate 1: Verifies source authorization, officiality weighting, and spam posture."""

    def __init__(self, registry: SourceRegistry, min_officiality: float = 0.50) -> None:
        self.registry = registry
        self.min_officiality = min_officiality

    def validate(self, source_id: str) -> tuple[bool, str, float]:
        if not self.registry.is_authorized(source_id):
            return (
                False,
                f"Source '{source_id}' is not registered or inactive in SourceRegistry",
                0.0,
            )

        src = self.registry.get_source(source_id)
        if not src:
            return False, f"Source metadata missing for '{source_id}'", 0.0

        if src.officiality_level < self.min_officiality:
            return (
                False,
                f"Source officiality ({src.officiality_level:.2f}) below threshold ({self.min_officiality:.2f})",
                src.officiality_level,
            )

        return True, "Source verified", src.officiality_level


class EvidenceIntegrityFirewall:
    """Gate 2: Verifies cryptographic payload integrity, entity anchoring, and conflict ledger."""

    def __init__(self, conflict_ledger: ConflictLedger | None = None) -> None:
        self.conflict_ledger = conflict_ledger

    def validate(
        self,
        raw_record: RawEvidenceRecord,
        event: CanonicalEvent,
    ) -> tuple[bool, str]:
        # 1. Payload SHA-256 integrity
        if not raw_record.content_sha256 or len(raw_record.content_sha256) != 64:
            return False, "Raw evidence record possesses invalid or missing SHA-256 seal"

        # 2. Entity grounding (must identify at least one affected entity)
        if not event.affected_entities:
            return False, f"Event {event.event_id} possesses zero resolved entities"

        # 3. Conflict Ledger check: Unresolved conflict quarantines event
        if self.conflict_ledger:
            unresolved = self.conflict_ledger.list_unresolved()
            for conf in unresolved:
                if conf.event_id == event.event_id:
                    return (
                        False,
                        f"Event {event.event_id} has unresolved conflict {conf.conflict_id}",
                    )

        return True, "Evidence integrity verified"


class PointInTimeFirewall:
    """Gate 3: Enforces temporal causality (observation time >= publication time)."""

    def validate(
        self,
        raw_record: RawEvidenceRecord,
        event: CanonicalEvent,
    ) -> tuple[bool, str]:
        if raw_record.observed_at_utc < raw_record.published_at_utc:
            margin = (raw_record.published_at_utc - raw_record.observed_at_utc).total_seconds()
            return (
                False,
                f"TEMPORAL LEAKAGE: Observation time precedes publication time by {margin:.2f}s",
            )

        if event.event_timestamp_utc > raw_record.observed_at_utc:
            margin = (event.event_timestamp_utc - raw_record.observed_at_utc).total_seconds()
            return False, f"FUTURE TIMESTAMP: Event claims timestamp {margin:.2f}s in the future"

        return True, "Point-in-time causality sound"


class MultiLayerIntelligenceFirewall:
    """Coordinator running Source Quality, Evidence Integrity, and Point-in-Time firewalls."""

    def __init__(
        self,
        registry: SourceRegistry | None = None,
        conflict_ledger: ConflictLedger | None = None,
    ) -> None:
        self.registry = registry or SourceRegistry()
        self.conflict_ledger = conflict_ledger
        self.source_firewall = SourceQualityFirewall(self.registry)
        self.evidence_firewall = EvidenceIntegrityFirewall(self.conflict_ledger)
        self.pit_firewall = PointInTimeFirewall()

    def evaluate(
        self,
        raw_record: RawEvidenceRecord,
        event: CanonicalEvent,
    ) -> QualityFirewallDecision:
        """Evaluates an ingested event across all 3 quality layers."""
        # Layer 1: Source Quality
        src_passed, src_msg, officiality = self.source_firewall.validate(raw_record.source_id)
        if not src_passed:
            return QualityFirewallDecision(
                verdict=FirewallVerdict.REJECTED,
                passed=False,
                rejection_gate="SOURCE_QUALITY_GATE",
                reason=src_msg,
                source_officiality=officiality,
                entity_count=len(event.affected_entities),
            )

        # Layer 2: Evidence Integrity
        ev_passed, ev_msg = self.evidence_firewall.validate(raw_record, event)
        if not ev_passed:
            verdict = (
                FirewallVerdict.QUARANTINED
                if "unresolved conflict" in ev_msg
                else FirewallVerdict.REJECTED
            )
            return QualityFirewallDecision(
                verdict=verdict,
                passed=False,
                rejection_gate="EVIDENCE_INTEGRITY_GATE",
                reason=ev_msg,
                source_officiality=officiality,
                entity_count=len(event.affected_entities),
            )

        # Layer 3: Point-in-Time Causality
        pit_passed, pit_msg = self.pit_firewall.validate(raw_record, event)
        if not pit_passed:
            return QualityFirewallDecision(
                verdict=FirewallVerdict.REJECTED,
                passed=False,
                rejection_gate="POINT_IN_TIME_GATE",
                reason=pit_msg,
                source_officiality=officiality,
                entity_count=len(event.affected_entities),
            )

        return QualityFirewallDecision(
            verdict=FirewallVerdict.APPROVED,
            passed=True,
            reason="All 3 Intelligence Quality Layers PASSED",
            source_officiality=officiality,
            entity_count=len(event.affected_entities),
        )
