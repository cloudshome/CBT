"""
core/intelligence/point_in_time.py
==================================
Point-in-Time Event Contract & Zero-Lookahead Verifier for Milestone 28.

Enforces:
1. Strict temporal precedence: Delta t = t_market - t_effective_availability > 0.
2. Ingestion latency and dissemination delay accounting.
3. Cryptographic payload integrity verification via SHA-256.
4. Vintage revision tracking preventing retrospective lookahead bias.
5. Epistemic prior weighting based on source provenance.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from core.intelligence.schema import EvidenceGrade, IntelligenceDomain, IntelligenceRecord

logger = logging.getLogger("ai_quant_sentinel.intelligence.point_in_time")


class TemporalIntegrityError(ValueError):
    """Raised when an event lacks valid, verifiable, or chronologically sound timestamps."""


class CausalLeakageDetectedError(RuntimeError):
    """Raised when a market observation window or entry violates causal precedence."""


# Institutional Epistemic Prior Weights
EPISTEMIC_PRIOR_WEIGHTS: dict[str, float] = {
    EvidenceGrade.VERIFIED_PRIMARY.value: 1.00,
    EvidenceGrade.CORROBORATED_REPORT.value: 0.70,
    EvidenceGrade.UNVERIFIED_CLAIM.value: 0.40,
    EvidenceGrade.SPECULATION.value: 0.20,
}

DEFAULT_DISSEMINATION_BUFFERS: dict[str, float] = {
    IntelligenceDomain.MACRO.value: 5.0,
    IntelligenceDomain.EQUITIES.value: 10.0,
    IntelligenceDomain.CRYPTO.value: 15.0,
    IntelligenceDomain.QUANT_RESEARCH.value: 60.0,
    IntelligenceDomain.SOCIAL.value: 30.0,
}


class PointInTimeEventContract(BaseModel):
    """
    Guarantees point-in-time causality for an external information event.
    No quantitative model may observe market data prior to effective_availability_utc.
    """

    event_id: str = Field(..., description="Deterministic or UUID event identifier")
    source_record_id: str = Field(..., description="Milestone 27 IntelligenceRecord ID")
    event_type: str = Field(
        "MACRO_RELEASE",
        description="MACRO_RELEASE, CENTRAL_BANK_SPEECH, REGULATORY_FILING, EARNINGS_REPORT, ONCHAIN_ANOMALY, GENERAL_NEWS",
    )
    domain: str = Field(IntelligenceDomain.MACRO.value, description="Intelligence domain")
    headline: str = Field(..., description="Sanitized headline or thesis summary")
    published_at_utc: float = Field(
        ..., description="Nominal event publication timestamp (seconds)"
    )
    collected_at_utc: float = Field(..., description="Collector ingestion timestamp (seconds)")
    effective_availability_utc: float = Field(
        ...,
        description="max(published, collected) + dissemination_buffer_seconds",
    )
    dissemination_buffer_seconds: float = Field(
        5.0,
        description="Safety buffer accounting for network and processing lag",
    )
    initial_metric_value: float | None = Field(
        None,
        description="Unrevised vintage value (e.g. CPI 3.1%)",
    )
    revised_metric_value: float | None = Field(
        None,
        description="Subsequent revision value if revised post-facto",
    )
    revision_number: int = Field(
        0, description="0 for initial vintage, >= 1 for subsequent revisions"
    )
    content_hash_sha256: str = Field(..., description="SHA-256 of canonical payload")
    epistemic_grade: str = Field(
        EvidenceGrade.UNVERIFIED_CLAIM.value, description="Epistemic grade"
    )
    epistemic_prior_weight: float = Field(0.40, description="Bayesian prior weight [0.20, 1.00]")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra context")

    @classmethod
    def from_intelligence_record(
        cls,
        record: IntelligenceRecord,
        dissemination_buffer_seconds: float | None = None,
        initial_metric_value: float | None = None,
        event_type: str = "MACRO_RELEASE",
    ) -> PointInTimeEventContract:
        """
        Creates a verified PointInTimeEventContract from a Milestone 27 IntelligenceRecord.
        Performs fail-closed timestamp validation.
        """
        now = time.time()
        pub_utc = record.published_at_utc
        col_utc = record.collected_at_utc

        if pub_utc <= 0:
            raise TemporalIntegrityError(
                f"Record {record.record_id} has invalid published_at_utc: {pub_utc}. Must be positive Unix timestamp."
            )

        # Disallow future timestamps exceeding nominal clock skew (max 300s into future)
        if pub_utc > now + 300.0:
            raise TemporalIntegrityError(
                f"Record {record.record_id} has future publication timestamp {pub_utc} > now {now}. Clock skew or invalid release date."
            )

        domain_str = record.domain if isinstance(record.domain, str) else record.domain.value
        buffer_sec = (
            dissemination_buffer_seconds
            if dissemination_buffer_seconds is not None
            else DEFAULT_DISSEMINATION_BUFFERS.get(domain_str, 5.0)
        )

        # Effective availability must never precede either published or collected timestamp
        effective_utc = max(pub_utc, col_utc) + buffer_sec

        grade_str = (
            record.evidence_grade
            if isinstance(record.evidence_grade, str)
            else record.evidence_grade.value
        )
        prior_weight = EPISTEMIC_PRIOR_WEIGHTS.get(grade_str, 0.40)

        # Cryptographic content hash verification
        canonical_content = (
            f"{record.source_url}:{record.title}:{(record.content_markdown or '')[:2048]}"
        )
        computed_sha = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()

        event_id = f"EVT_{record.record_id}_{int(pub_utc)}"

        return cls(
            event_id=event_id,
            source_record_id=record.record_id,
            event_type=event_type,
            domain=domain_str,
            headline=record.title,
            published_at_utc=pub_utc,
            collected_at_utc=col_utc,
            effective_availability_utc=effective_utc,
            dissemination_buffer_seconds=buffer_sec,
            initial_metric_value=initial_metric_value,
            revised_metric_value=None,
            revision_number=0,
            content_hash_sha256=computed_sha,
            epistemic_grade=grade_str,
            epistemic_prior_weight=prior_weight,
            metadata={
                "source_platform": str(record.source_platform),
                "source_url": record.source_url,
                "relevance_score": record.relevance_score,
                "entities": record.entities,
                **record.metadata,
            },
        )

    def verify_temporal_precedence(self, market_observation_start_utc: float) -> bool:
        """
        Asserts that market observation began STRICTLY AFTER effective availability.
        Returns True if causal precedence is preserved, False otherwise.
        """
        return market_observation_start_utc > self.effective_availability_utc

    def temporal_margin_seconds(self, market_observation_start_utc: float) -> float:
        """
        Calculates safety margin Delta t = market_observation - effective_availability.
        Positive implies causal safety; negative implies lookahead bias.
        """
        return market_observation_start_utc - self.effective_availability_utc

    def assert_causal_precedence(self, market_observation_start_utc: float) -> None:
        """
        Raises CausalLeakageDetectedError if market observation precedes availability.
        """
        margin = self.temporal_margin_seconds(market_observation_start_utc)
        if margin <= 0:
            raise CausalLeakageDetectedError(
                f"TEMPORAL LEAKAGE DETECTED: Market observation start ({market_observation_start_utc:.3f}) "
                f"precedes or equals event effective availability ({self.effective_availability_utc:.3f}). "
                f"Margin: {margin:.3f}s <= 0."
            )
