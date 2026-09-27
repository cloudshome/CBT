"""
tests/research/grade_e3/test_contracts.py
=========================================
Unit tests for Grade-E3 Contracts, Enums, and Dataclasses.
"""

from __future__ import annotations

from core.research.grade_e3.contracts import (
    CancelLatencyConfig,
    EvidenceStatus,
    QueuePositionEstimate,
    TamperEvidentEvidenceBundle,
)


def test_evidence_status_progression_order() -> None:
    statuses = [s.value for s in EvidenceStatus]
    assert statuses == [
        "RAW_CAPTURED",
        "PARSED",
        "SEQUENCE_VALIDATED",
        "REPLAYABLE",
        "RESEARCH_GRADE_E3",
        "L2_TICK_VERIFIED",
    ]


def test_queue_position_uncertainty_contract() -> None:
    est = QueuePositionEstimate(
        queue_ahead_estimate=12.5,
        queue_ahead_lower_bound=5.0,
        queue_ahead_upper_bound=15.0,
        queue_model_confidence=0.70,
        queue_position_assumption="Q1_EMPIRICAL_CANCELLATION_DISCOUNT",
        simulated_fill_probability=0.65,
        fill_assumption_class="Q1_VOLUME_CANCELLATIONS",
        queue_uncertainty_interval=(5.0, 15.0),
    )
    assert est.queue_ahead_estimate == 12.5
    assert est.queue_uncertainty_interval == (5.0, 15.0)
    data = est.to_dict()
    assert data["queue_model_confidence"] == 0.70


def test_cancel_latency_config_contract() -> None:
    cfg = CancelLatencyConfig(
        source="CONFIGURED_SCENARIO",
        p50_ms=25.0,
        p90_ms=45.0,
        p99_ms=80.0,
        venue="BINANCE_SPOT",
        measured=False,
        epistemic_status="ASSUMED",
    )
    assert cfg.p50_ms == 25.0
    assert cfg.epistemic_status == "ASSUMED"
    assert cfg.measured is False


def test_tamper_evident_bundle_integrity() -> None:
    bundle = TamperEvidentEvidenceBundle(
        raw_data_hash="a" * 64,
        normalized_data_hash="b" * 64,
        reconstructed_book_hash="c" * 64,
        parser_version="1.0.0",
        book_builder_version="1.0.0",
        queue_model_version="Q1_VOLUME_CANCELLATIONS",
        configuration_hash="d" * 64,
        code_commit="7b4835f",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        time_range=(1700000000, 1700086400),
        sequence_audit={"gaps": 0},
        clock_audit={"drift_ms": 0.0},
        missing_data_report={"intervals": 0},
        experiment_id="EXP_E3_PILOT",
        result_artifact_hash="e" * 64,
    )
    assert len(bundle.bundle_hash) == 64
    assert bundle.verify_integrity() is True


def test_tampered_bundle_hash_fails_integrity() -> None:
    bundle = TamperEvidentEvidenceBundle(
        raw_data_hash="a" * 64,
        normalized_data_hash="b" * 64,
        reconstructed_book_hash="c" * 64,
        parser_version="1.0.0",
        book_builder_version="1.0.0",
        queue_model_version="Q1_VOLUME_CANCELLATIONS",
        configuration_hash="d" * 64,
        code_commit="7b4835f",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        time_range=(1700000000, 1700086400),
        sequence_audit={"gaps": 0},
        clock_audit={"drift_ms": 0.0},
        missing_data_report={"intervals": 0},
        experiment_id="EXP_E3_PILOT",
        result_artifact_hash="e" * 64,
        bundle_hash="tampered_hash_value" + "0" * 45,
    )
    assert bundle.verify_integrity() is False
