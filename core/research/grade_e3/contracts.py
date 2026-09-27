"""
core/research/grade_e3/contracts.py
===================================
Canonical Type Contracts, Enums, and Dataclasses for Grade-E3 High-Frequency L2 Engine.

Key Architectural Guarantees:
1. Evidence Status is EARNED through progressive validation stages, never hardcoded.
2. Queue Models expose explicit uncertainty intervals and confidence metrics.
3. Cancellation Latency is fully configurable and supports parametric/empirical distributions.
4. Tamper-Evident Evidence Bundles bind raw hashes, normalized hashes, and code commits.
5. Decoupled Strategy Status enforces separation between viability, validation, tradeability, and authorization.
6. Permanent Capital Firewall (Amendment A): Zero imports or calls to live order routing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Progressive Evidence Status & Epistemic Classification
# ─────────────────────────────────────────────────────────────────────────────


class EvidenceStatus(StrEnum):
    """
    Earned evidence status progression for Grade-E3 research datasets.
    Cannot be skipped or assigned at raw ingestion time.
    """

    RAW_CAPTURED = "RAW_CAPTURED"
    PARSED = "PARSED"
    SEQUENCE_VALIDATED = "SEQUENCE_VALIDATED"
    REPLAYABLE = "REPLAYABLE"
    RESEARCH_GRADE_E3 = "RESEARCH_GRADE_E3"
    L2_TICK_VERIFIED = "L2_TICK_VERIFIED"


class VenueFeasibilityStatus(StrEnum):
    """Feasibility outcome for candidate venue market data evaluation."""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    NOT_FEASIBLE = "NOT_FEASIBLE"


class L2OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class L2OrderStatus(StrEnum):
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# ─────────────────────────────────────────────────────────────────────────────
# Queue Modeling & Uncertainty
# ─────────────────────────────────────────────────────────────────────────────


class QueueModelType(StrEnum):
    """Supported queue estimation models reflecting public data uncertainty."""

    Q0_NAIVE_DISPLAYED = "Q0_NAIVE_DISPLAYED"
    Q1_VOLUME_CANCELLATIONS = "Q1_VOLUME_CANCELLATIONS"
    Q2_PROBABILISTIC_QUEUE = "Q2_PROBABILISTIC_QUEUE"
    Q3_VENUE_CALIBRATED = "Q3_VENUE_CALIBRATED"


@dataclass(frozen=True)
class QueuePositionEstimate:
    """
    Exposes empirical queue position uncertainty intervals.
    Public L2 data cannot observe exact position; uncertainty is non-negotiable.
    """

    queue_ahead_estimate: float
    queue_ahead_lower_bound: float
    queue_ahead_upper_bound: float
    queue_model_confidence: float
    queue_position_assumption: str
    simulated_fill_probability: float
    fill_assumption_class: str
    queue_uncertainty_interval: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueueModelMetadata:
    """
    Explicit model governance metadata identifying calibration status and uncertainty bounds.
    Prohibits claiming venue calibration without verifiable empirical calibration.
    """

    model_id: str
    model_type: QueueModelType
    parameter_hash: str
    calibration_dataset: str
    calibration_status: (
        str  # e.g. "UNCALIBRATED_SCENARIO", "SYNTHETIC_BENCHMARK", "EMPIRICALLY_CALIBRATED"
    )
    random_seed: int
    fill_uncertainty_bps: float
    wait_uncertainty_ms: float
    sensitivity_scenario: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "parameter_hash": self.parameter_hash,
            "calibration_dataset": self.calibration_dataset,
            "calibration_status": self.calibration_status,
            "random_seed": self.random_seed,
            "fill_uncertainty_bps": self.fill_uncertainty_bps,
            "wait_uncertainty_ms": self.wait_uncertainty_ms,
            "sensitivity_scenario": self.sensitivity_scenario,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cancellation Latency Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CancelLatencyConfig:
    """
    Configurable, empirical or scenario-based cancellation latency distribution.
    Rejects rigid constant assumptions.
    """

    source: str = "CONFIGURED_SCENARIO"
    distribution: str = "parametric_lognormal"
    p50_ms: float = 25.0
    p90_ms: float = 45.0
    p99_ms: float = 80.0
    venue: str = "BINANCE_SPOT"
    connection_type: str = "COLOCATED_OR_CLOUD"
    measured: bool = False
    epistemic_status: str = "ASSUMED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Core L2 Order Book & Trade Records
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class L2DiffUpdate:
    """Canonical Level 2 order book difference packet."""

    exchange: str
    symbol: str
    first_update_id: int  # U
    last_update_id: int  # u
    prev_last_update_id: int | None  # pu (for Binance sequence continuity)
    timestamp_ns: int
    bids: list[tuple[float, float]]  # (price, quantity)
    asks: list[tuple[float, float]]  # (price, quantity)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeTick:
    """Individual executed market trade print."""

    trade_id: int | str
    timestamp_ns: int
    price: float
    size: float
    is_buyer_maker: bool  # True: maker was buyer (aggressor was seller); False: maker was seller
    symbol: str = "BTCUSDT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderBookTop:
    """Top of book snapshot with microstructural metrics."""

    best_bid: float
    best_ask: float
    bid_qty: float
    ask_qty: float
    mid_price: float
    micro_price: float
    spread_bps: float
    is_inverted: bool
    is_stale: bool
    timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class L2FillEvent:
    """Record of a simulated fill with ex-post post-fill markouts."""

    fill_id: str
    order_id: str
    timestamp_ns: int
    side: L2OrderSide
    fill_price: float
    fill_qty: float
    fee_bps: float
    queue_wait_ms: float
    markouts_bps: dict[str, float]  # "100ms", "1s", "5s", "30s", "5m"
    winner_curse_bias_bps: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarkoutHorizonResult:
    """Rigorous scientific markout metrics for an individual horizon."""

    horizon: str
    horizon_ms: int
    mid_price_markout_bps: float
    micro_price_markout_bps: float
    executable_price_markout_bps: float
    fee_adjusted_markout_bps: float
    conditional_fill_markout_bps: float
    reference_population_drift_bps: float
    winners_curse_bias_bps: float
    standard_error_bps: float
    confidence_interval_95: tuple[float, float]
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiHorizonMarkoutReport:
    """Comprehensive ex-post markout & adverse selection report across all 5 standard horizons."""

    asset: str
    venue: str
    sample_size_fills: int
    reference_population_size: int
    horizons: dict[str, MarkoutHorizonResult]
    mean_adverse_selection_5s_bps: float
    mean_winners_curse_bias_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "venue": self.venue,
            "sample_size_fills": self.sample_size_fills,
            "reference_population_size": self.reference_population_size,
            "horizons": {k: v.to_dict() for k, v in self.horizons.items()},
            "mean_adverse_selection_5s_bps": self.mean_adverse_selection_5s_bps,
            "mean_winners_curse_bias_bps": self.mean_winners_curse_bias_bps,
        }


@dataclass(frozen=True)
class FidelityAuditReport:
    """Summary of data integrity and sequence audit for an ingested dataset."""

    venue: str
    symbol: str
    total_diffs: int
    total_ticks: int
    sequence_gaps: int
    clock_drift_p99_ms: float
    spread_inversions: int
    raw_data_sha256: str
    evidence_status: EvidenceStatus
    is_fidelity_certified: bool
    duplicates_detected: int = 0
    out_of_order_detected: int = 0
    malformed_packets: int = 0
    reconnect_boundaries: int = 0
    exclusions_count: int = 0
    audit_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "symbol": self.symbol,
            "total_diffs": self.total_diffs,
            "total_ticks": self.total_ticks,
            "sequence_gaps": self.sequence_gaps,
            "clock_drift_p99_ms": round(self.clock_drift_p99_ms, 2),
            "spread_inversions": self.spread_inversions,
            "raw_data_sha256": self.raw_data_sha256,
            "evidence_status": self.evidence_status.value,
            "is_fidelity_certified": self.is_fidelity_certified,
            "duplicates_detected": self.duplicates_detected,
            "out_of_order_detected": self.out_of_order_detected,
            "malformed_packets": self.malformed_packets,
            "reconnect_boundaries": self.reconnect_boundaries,
            "exclusions_count": self.exclusions_count,
            "audit_summary": self.audit_summary,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Decoupled Strategy Status (Amendment D)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DecoupledStrategyStatus:
    """
    Decoupled four-tier strategy status ensuring properties are never inferred.
    Viability != Validation != Tradeability != Authorization.
    """

    research_viable: bool = False
    execution_model_validated: bool = False
    tradeable: bool = False
    live_authorized: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Tamper-Evident Evidence Bundle (Amendment B)
# ─────────────────────────────────────────────────────────────────────────────


def compute_bundle_digest(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical evidence bundle."""
    canonical = {
        "raw_data_hash": data.get("raw_data_hash"),
        "normalized_data_hash": data.get("normalized_data_hash"),
        "reconstructed_book_hash": data.get("reconstructed_book_hash"),
        "parser_version": data.get("parser_version"),
        "book_builder_version": data.get("book_builder_version"),
        "queue_model_version": data.get("queue_model_version"),
        "configuration_hash": data.get("configuration_hash"),
        "code_commit": data.get("code_commit"),
        "venue": data.get("venue"),
        "symbol": data.get("symbol"),
        "time_range": list(data.get("time_range", [0, 0])),
        "experiment_id": data.get("experiment_id"),
        "result_artifact_hash": data.get("result_artifact_hash"),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TamperEvidentEvidenceBundle:
    """
    Immutable, cryptographic audit bundle produced for every Grade-E3 experiment.
    Enables zero-trust independent reproduction of all metrics and conclusions.
    """

    raw_data_hash: str
    normalized_data_hash: str
    reconstructed_book_hash: str
    parser_version: str
    book_builder_version: str
    queue_model_version: str
    configuration_hash: str
    code_commit: str
    venue: str
    symbol: str
    time_range: tuple[int, int]
    sequence_audit: dict[str, Any]
    clock_audit: dict[str, Any]
    missing_data_report: dict[str, Any]
    experiment_id: str
    result_artifact_hash: str
    bundle_hash: str = ""

    def __post_init__(self) -> None:
        if not self.bundle_hash:
            calculated = compute_bundle_digest(asdict(self))
            object.__setattr__(self, "bundle_hash", calculated)

    def verify_integrity(self) -> bool:
        expected = compute_bundle_digest(asdict(self))
        return self.bundle_hash == expected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
