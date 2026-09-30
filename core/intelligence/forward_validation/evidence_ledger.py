"""
core/intelligence/forward_validation/evidence_ledger.py
=======================================================
Machine-Readable Evidence Ledger & Denominator Integrity Gate for Milestone 31-R.

Enforces:
1. Denominator Integrity Gate: Every reported performance metric MUST disclose
   all 4 observation tiers:
   - raw_observations
   - eligible_observations
   - executed_simulated_observations
   - excluded_observations
   where: raw = eligible + excluded, and eligible >= executed.
2. Feed Quality & Continuity Metrics: Telemetry for drops, sequence gaps, crossed books.
3. Monotonic Clock Integrity: Verifies zero clock regressions or unhandled skew.
4. Cryptographic Hash Manifest: Chained SHA-256 seals binding data, code, manifest, and decision.
5. Permanent Capital Firewall: real_capital_enabled = False strictly verified.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.intelligence.forward_validation.forward_ledger import StrategyForwardScorecard
from core.intelligence.forward_validation.strategy_manifest import StrategyConstitutionManifest


class DenominatorIntegrityError(ValueError):
    """Raised when observation conservation or denominator integrity is violated."""


class DenominatorBreakdown(BaseModel):
    """
    Mandatory 4-Tier Denominator Disclosure Object.
    Guarantees no difficult market regimes are silently filtered out.
    """

    raw_observations: int = Field(
        ..., ge=0, description="Total market events/ticks received on active feeds"
    )
    eligible_observations: int = Field(
        ...,
        ge=0,
        description="Events meeting feed validity, uncrossed book, and non-quarantine rules",
    )
    executed_simulated_observations: int = Field(
        ..., ge=0, description="Simulated paper fills executed under APPROXIMATE_AGGREGATED_L2"
    )
    excluded_observations: int = Field(
        ...,
        ge=0,
        description="Sum of invalid feed, lookahead quarantine, crossed-book, and rate-limit drops",
    )
    exclusion_details: dict[str, int] = Field(
        default_factory=dict,
        description="Detailed breakdown of exclusions (e.g. {'invalid_feed': 10, 'crossed_book': 5, 'clock_skew': 2})",
    )

    @model_validator(mode="after")
    def validate_conservation(self) -> DenominatorBreakdown:
        """Enforces mathematical conservation: raw = eligible + excluded."""
        expected_raw = self.eligible_observations + self.excluded_observations
        if self.raw_observations != expected_raw:
            raise DenominatorIntegrityError(
                f"Denominator Conservation Violation: raw_observations ({self.raw_observations}) "
                f"!= eligible ({self.eligible_observations}) + excluded ({self.excluded_observations})"
            )
        if self.executed_simulated_observations > self.eligible_observations:
            raise DenominatorIntegrityError(
                f"Executed observations ({self.executed_simulated_observations}) "
                f"cannot exceed eligible opportunities ({self.eligible_observations})"
            )
        sum_details = sum(self.exclusion_details.values())
        if self.exclusion_details and sum_details != self.excluded_observations:
            raise DenominatorIntegrityError(
                f"Exclusion details sum ({sum_details}) != excluded_observations ({self.excluded_observations})"
            )
        return self


class FeedQualityEvidence(BaseModel):
    """
    Hardware and feed continuity telemetry across the observation window.
    """

    total_feed_events: int = Field(
        ..., ge=0, description="Total WebSocket/REST feed ticks received"
    )
    feed_continuity_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of time feed remained fully continuous (target >= 0.995)",
    )
    packet_loss_estimate: float = Field(
        default=0.0, ge=0.0, description="Estimated packet loss ratio"
    )
    reconnect_count: int = Field(
        default=0, ge=0, description="Total socket reconnect events observed"
    )
    sequence_gap_count: int = Field(default=0, ge=0, description="Detected packet sequence gaps")
    crossed_book_count: int = Field(
        default=0, ge=0, description="Crossed book anomalies (bid >= ask)"
    )
    stale_quote_count: int = Field(
        default=0, ge=0, description="Observed quotes exceeding freshness threshold"
    )
    clock_integrity_breaches: int = Field(
        default=0, ge=0, description="Non-monotonic timestamp or excessive skew breaches"
    )
    p50_latency_us: float = Field(
        default=500.0, description="Median book processing latency in microseconds"
    )
    p99_latency_us: float = Field(
        default=2500.0, description="99th percentile processing latency in microseconds"
    )

    @property
    def is_feed_qualified(self) -> bool:
        """Feed passes qualification if continuity >= 99.5% and clock breaches == 0."""
        return self.feed_continuity_rate >= 0.995 and self.clock_integrity_breaches == 0


class M31REvidenceBundle(BaseModel):
    """
    Complete, typed evidence bundle capturing every empirical dimension
    of strategy forward validation.
    """

    evidence_id: str = Field(..., description="Unique ID: EVID-M31R-<timestamp>-<hash>")
    generation_timestamp_utc: float = Field(default_factory=time.time)
    strategy_manifest: StrategyConstitutionManifest = Field(
        ..., description="Sealed Strategy Constitution"
    )
    denominators: DenominatorBreakdown = Field(..., description="4-tier denominator breakdown")
    feed_quality: FeedQualityEvidence = Field(..., description="Feed continuity telemetry")
    scorecard: StrategyForwardScorecard = Field(
        ..., description="Denominator-transparent performance scorecard"
    )
    drift_summary: dict[str, Any] = Field(
        default_factory=dict, description="Multi-dimensional drift analysis summary"
    )
    circuit_breaker_events_count: int = Field(default=0, ge=0)
    failure_memory_ids: list[str] = Field(
        default_factory=list, description="Associated FailureRecord IDs"
    )

    # Cryptographic Lineage
    research_protocol_hash: str = Field(..., description="SHA-256 of QUANT_RESEARCH_PROTOCOL.md")
    codebase_commit_hash: str = Field(..., description="Git commit hash of repository during run")
    dataset_hash: str = Field(..., description="Dataset or historical baseline hash")

    # Constitutional Invariants
    real_capital_enabled: Literal[False] = False
    simulation_only_cancel_verified: Literal[True] = True

    @model_validator(mode="after")
    def validate_bundle_invariants(self) -> M31REvidenceBundle:
        """Guarantees zero live capital bypass."""
        if self.real_capital_enabled is not False:
            raise ValueError("Constitutional violation: real_capital_enabled MUST be False.")
        if self.simulation_only_cancel_verified is not True:
            raise ValueError(
                "Constitutional violation: simulation_only_cancel_verified MUST be True."
            )
        return self

    def compute_evidence_hash(self) -> str:
        """Computes deterministic SHA-256 digest of this evidence bundle."""
        d = self.model_dump(mode="json")
        canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_json(self, indent: int = 2) -> str:
        """Exports evidence bundle to structured JSON string."""
        return json.dumps(self.model_dump(mode="json"), indent=indent, sort_keys=True)


class M31RHashManifest(BaseModel):
    """
    Cryptographic Hash Manifest verifying the tamper-evident integrity
    of all M31-R evidence artifacts.
    """

    manifest_id: str = Field(..., description="Unique manifest ID")
    timestamp_utc: float = Field(default_factory=time.time)
    strategy_manifest_hash: str = Field(..., description="SHA-256 of StrategyConstitutionManifest")
    dataset_hash: str = Field(..., description="SHA-256 of historical benchmark dataset")
    evidence_bundle_hash: str = Field(..., description="SHA-256 of M31REvidenceBundle")
    decision_hash: str = Field(..., description="SHA-256 of M31RQualificationDecision")
    codebase_git_hash: str = Field(..., description="Git HEAD commit hash")
    master_integrity_hash: str = Field(
        ..., description="Chained SHA-256 digest binding all components"
    )

    @classmethod
    def create(
        cls,
        strategy_manifest_hash: str,
        dataset_hash: str,
        evidence_bundle_hash: str,
        decision_hash: str,
        codebase_git_hash: str,
    ) -> M31RHashManifest:
        """Factory computing the master chained integrity hash."""
        now = time.time()
        chained_components = [
            strategy_manifest_hash,
            dataset_hash,
            evidence_bundle_hash,
            decision_hash,
            codebase_git_hash,
            str(now),
        ]
        master_digest = hashlib.sha256(":".join(chained_components).encode("utf-8")).hexdigest()
        manifest_id = f"MANIFEST-M31R-{int(now)}-{master_digest[:10]}"

        return cls(
            manifest_id=manifest_id,
            timestamp_utc=now,
            strategy_manifest_hash=strategy_manifest_hash,
            dataset_hash=dataset_hash,
            evidence_bundle_hash=evidence_bundle_hash,
            decision_hash=decision_hash,
            codebase_git_hash=codebase_git_hash,
            master_integrity_hash=master_digest,
        )
