"""
core/intelligence/crawler/fact_extractor.py
===========================================
Empirical Fact Extraction Engine for Milestone 30-C.

CONSTITUTIONAL SEPARATION:
Fact extraction produces strictly `EvidenceKind.DERIVED_FACT`.
It establishes WHAT occurred and quantitative deltas (e.g. CPI surprise = +0.2pp).
It DOES NOT establish causality, directionality, or trading edge.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from core.intelligence.crawler.conflict_ledger import ConflictLedger, ConflictStatus
from core.intelligence.crawler.event_identity import CanonicalEvent, EventType
from core.intelligence.crawler.qualification_contracts import (
    ConfidenceScores,
    EvidenceKind,
    EvidenceLineageLedger,
    EvidenceLineageNode,
    global_lineage_ledger,
)
from core.intelligence.crawler.raw_evidence_vault import (
    EvidenceTamperingError,
    RawEvidenceRecord,
    RawEvidenceVault,
)
from core.intelligence.crawler.source_registry import SourceRegistry

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.fact_extractor")


class FactExtractionError(ValueError):
    """Raised when an empirical fact cannot be deterministically extracted."""


@dataclass(frozen=True)
class EmpiricalFact:
    """
    Structured, reproducible numeric or categorical observation derived from raw evidence.
    Permanently stamped as EvidenceKind.DERIVED_FACT.
    """

    fact_id: str
    evidence_kind: Literal[EvidenceKind.DERIVED_FACT]
    canonical_event_id: str
    parent_evidence_id: str
    parent_content_sha256: str
    event_type: EventType
    entity: str
    metric_name: str
    metric_value: float
    unit: str
    confidence_scores: ConfidenceScores
    is_quarantined: bool
    quarantine_reason: str | None
    extracted_at_utc: float
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence_kind"] = self.evidence_kind.value
        d["event_type"] = self.event_type.value
        d["confidence_scores"] = self.confidence_scores.to_dict()
        return d


class FactExtractor:
    """
    Deterministic fact extraction pipeline verifying raw vault provenance,
    enforcing contradiction checks against ConflictLedger, and separating confidence dimensions.
    """

    def __init__(
        self,
        vault: RawEvidenceVault | None = None,
        conflict_ledger: ConflictLedger | None = None,
        source_registry: SourceRegistry | None = None,
        lineage_ledger: EvidenceLineageLedger | None = None,
    ) -> None:
        self.vault = vault or RawEvidenceVault()
        self.conflict_ledger = conflict_ledger or ConflictLedger()
        self.source_registry = source_registry or SourceRegistry()
        self.lineage_ledger = lineage_ledger or global_lineage_ledger

    def _verify_vault_integrity(self, record: RawEvidenceRecord) -> None:
        """Verifies the raw evidence payload against its cryptographic SHA-256 seal."""
        expected_hash = hashlib.sha256(record.raw_payload.encode("utf-8")).hexdigest()
        if expected_hash != record.content_sha256:
            raise EvidenceTamperingError(
                f"Raw evidence {record.evidence_id} fails cryptographic seal: "
                f"expected {expected_hash}, stored {record.content_sha256}"
            )

    def _determine_confidence_scores(
        self,
        source_id: str,
        event_id: str,
        metric_name: str,
        has_conflict: bool,
    ) -> ConfidenceScores:
        """
        Computes 3 strictly orthogonal confidence metrics.
        Never collapses them into a single score.
        """
        source_meta = self.source_registry.get_source(source_id)
        sid_upper = source_id.upper()
        if source_meta:
            source_reliability = float(source_meta.officiality_level)
        elif any(
            k in sid_upper for k in ["BLS", "FEDERAL_RESERVE", "FED", "SEC", "ECB", "TREASURY"]
        ):
            source_reliability = 1.0
        elif any(k in sid_upper for k in ["BLOOMBERG", "REUTERS"]):
            source_reliability = 0.85
        else:
            source_reliability = 0.50

        # 2. Fact Confidence (Extraction Accuracy & Conflict Status)
        if has_conflict:
            fact_confidence = 0.0
        elif source_reliability >= 0.90:
            fact_confidence = 0.95
        else:
            fact_confidence = 0.70

        # 3. Causal Prior Strength (Theoretical Plausibility prior to empirical testing)
        if "INFLATION" in event_id or "RATE" in event_id:
            causal_prior_strength = 0.80
        elif "STABLECOIN" in event_id or "MINT" in event_id:
            causal_prior_strength = 0.75
        elif "ETF" in event_id or "FLOW" in event_id:
            causal_prior_strength = 0.70
        else:
            causal_prior_strength = 0.50

        return ConfidenceScores(
            source_reliability=round(source_reliability, 3),
            fact_confidence=round(fact_confidence, 3),
            causal_prior_strength=round(causal_prior_strength, 3),
        )

    def _check_conflicts(self, event_id: str) -> tuple[bool, str | None]:
        """Queries ConflictLedger for unresolved contradictions on this event."""
        conflicts = self.conflict_ledger.get_conflicts_for_event(event_id)
        for c in conflicts:
            if c.status in [ConflictStatus.UNRESOLVED, ConflictStatus.QUARANTINED]:
                return (
                    True,
                    f"Unresolved conflict detected (ID: {c.conflict_id}, Type: {c.conflict_type.value})",
                )
        return False, None

    def extract_macro_surprise(
        self,
        event: CanonicalEvent,
        record: RawEvidenceRecord,
        actual_key: str = "actual",
        consensus_key: str = "consensus",
        metric_name: str = "MACRO_SURPRISE_DELTA",
        unit: str = "PERCENTAGE_POINTS",
    ) -> EmpiricalFact:
        """
        Extracts macroeconomic surprise: Delta = Actual - Consensus.
        """
        self._verify_vault_integrity(record)

        try:
            payload = json.loads(record.raw_payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

        actual_val = payload.get(actual_key)
        consensus_val = payload.get(consensus_key)

        if actual_val is None or consensus_val is None:
            raise FactExtractionError(
                f"Missing numeric fields '{actual_key}' or '{consensus_key}' in payload for {event.event_id}"
            )

        try:
            actual_num = float(actual_val)
            consensus_num = float(consensus_val)
        except (ValueError, TypeError) as e:
            raise FactExtractionError(f"Cannot cast macro values to float: {e}") from e

        delta = round(actual_num - consensus_num, 4)

        has_conflict, conflict_reason = self._check_conflicts(event.event_id)
        scores = self._determine_confidence_scores(
            source_id=record.source_id,
            event_id=event.event_id,
            metric_name=metric_name,
            has_conflict=has_conflict,
        )

        now = time.time()
        fact_hash = hashlib.sha256(
            f"{event.event_id}:{metric_name}:{delta}:{record.content_sha256}".encode()
        ).hexdigest()[:12]
        fact_id = f"FACT-{event.event_id}-{fact_hash}"

        fact = EmpiricalFact(
            fact_id=fact_id,
            evidence_kind=EvidenceKind.DERIVED_FACT,
            canonical_event_id=event.event_id,
            parent_evidence_id=record.evidence_id,
            parent_content_sha256=record.content_sha256,
            event_type=event.event_type,
            entity=event.affected_entities[0] if event.affected_entities else "GLOBAL",
            metric_name=metric_name,
            metric_value=delta,
            unit=unit,
            confidence_scores=scores,
            is_quarantined=has_conflict,
            quarantine_reason=conflict_reason,
            extracted_at_utc=now,
            metadata={
                "actual": actual_num,
                "consensus": consensus_num,
                "raw_keys": [actual_key, consensus_key],
            },
        )

        # Record Lineage
        node = EvidenceLineageNode(
            node_id=f"LIN-{fact_id}",
            parent_ids=[record.evidence_id],
            evidence_kind=EvidenceKind.DERIVED_FACT,
            timestamp_utc=now,
            content_hash_sha256=hashlib.sha256(
                json.dumps(fact.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            metadata={"canonical_event_id": event.event_id, "metric_name": metric_name},
        )
        self.lineage_ledger.record_node(node)

        return fact

    def extract_corporate_accumulation(
        self,
        event: CanonicalEvent,
        record: RawEvidenceRecord,
        amount_btc_key: str = "btc_purchased",
        cost_usd_key: str = "cost_usd",
    ) -> EmpiricalFact:
        """
        Extracts corporate balance sheet bitcoin purchase fact.
        """
        self._verify_vault_integrity(record)

        try:
            payload = json.loads(record.raw_payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

        btc_amount = payload.get(amount_btc_key)
        if btc_amount is None:
            raise FactExtractionError(
                f"Missing '{amount_btc_key}' in corporate payload for {event.event_id}"
            )

        try:
            btc_num = float(btc_amount)
        except (ValueError, TypeError) as e:
            raise FactExtractionError(f"Invalid BTC amount format: {e}") from e

        has_conflict, conflict_reason = self._check_conflicts(event.event_id)
        scores = self._determine_confidence_scores(
            source_id=record.source_id,
            event_id=event.event_id,
            metric_name="CORPORATE_BTC_ACCUMULATION",
            has_conflict=has_conflict,
        )

        now = time.time()
        fact_hash = hashlib.sha256(
            f"{event.event_id}:CORPORATE_BTC_ACCUMULATION:{btc_num}:{record.content_sha256}".encode()
        ).hexdigest()[:12]
        fact_id = f"FACT-{event.event_id}-{fact_hash}"

        fact = EmpiricalFact(
            fact_id=fact_id,
            evidence_kind=EvidenceKind.DERIVED_FACT,
            canonical_event_id=event.event_id,
            parent_evidence_id=record.evidence_id,
            parent_content_sha256=record.content_sha256,
            event_type=event.event_type,
            entity=event.affected_entities[0] if event.affected_entities else "MSTR",
            metric_name="CORPORATE_BTC_ACCUMULATION",
            metric_value=btc_num,
            unit="BTC",
            confidence_scores=scores,
            is_quarantined=has_conflict,
            quarantine_reason=conflict_reason,
            extracted_at_utc=now,
            metadata={"cost_usd": payload.get(cost_usd_key)},
        )

        node = EvidenceLineageNode(
            node_id=f"LIN-{fact_id}",
            parent_ids=[record.evidence_id],
            evidence_kind=EvidenceKind.DERIVED_FACT,
            timestamp_utc=now,
            content_hash_sha256=hashlib.sha256(
                json.dumps(fact.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            metadata={
                "canonical_event_id": event.event_id,
                "metric_name": "CORPORATE_BTC_ACCUMULATION",
            },
        )
        self.lineage_ledger.record_node(node)
        return fact

    def extract_stablecoin_flow(
        self,
        event: CanonicalEvent,
        record: RawEvidenceRecord,
        notional_usd_key: str = "net_mint_usd",
    ) -> EmpiricalFact:
        """
        Extracts stablecoin net mint/burn notional flow fact.
        """
        self._verify_vault_integrity(record)

        try:
            payload = json.loads(record.raw_payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}

        notional_val = payload.get(notional_usd_key)
        if notional_val is None:
            raise FactExtractionError(
                f"Missing '{notional_usd_key}' in stablecoin payload for {event.event_id}"
            )

        try:
            notional_num = float(notional_val)
        except (ValueError, TypeError) as e:
            raise FactExtractionError(f"Invalid notional USD format: {e}") from e

        has_conflict, conflict_reason = self._check_conflicts(event.event_id)
        scores = self._determine_confidence_scores(
            source_id=record.source_id,
            event_id=event.event_id,
            metric_name="STABLECOIN_NET_MINT_USD",
            has_conflict=has_conflict,
        )

        now = time.time()
        fact_hash = hashlib.sha256(
            f"{event.event_id}:STABLECOIN_NET_MINT_USD:{notional_num}:{record.content_sha256}".encode()
        ).hexdigest()[:12]
        fact_id = f"FACT-{event.event_id}-{fact_hash}"

        fact = EmpiricalFact(
            fact_id=fact_id,
            evidence_kind=EvidenceKind.DERIVED_FACT,
            canonical_event_id=event.event_id,
            parent_evidence_id=record.evidence_id,
            parent_content_sha256=record.content_sha256,
            event_type=event.event_type,
            entity=event.affected_entities[0] if event.affected_entities else "USDT",
            metric_name="STABLECOIN_NET_MINT_USD",
            metric_value=notional_num,
            unit="USD",
            confidence_scores=scores,
            is_quarantined=has_conflict,
            quarantine_reason=conflict_reason,
            extracted_at_utc=now,
            metadata={"raw_payload": payload},
        )

        node = EvidenceLineageNode(
            node_id=f"LIN-{fact_id}",
            parent_ids=[record.evidence_id],
            evidence_kind=EvidenceKind.DERIVED_FACT,
            timestamp_utc=now,
            content_hash_sha256=hashlib.sha256(
                json.dumps(fact.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            metadata={
                "canonical_event_id": event.event_id,
                "metric_name": "STABLECOIN_NET_MINT_USD",
            },
        )
        self.lineage_ledger.record_node(node)
        return fact
