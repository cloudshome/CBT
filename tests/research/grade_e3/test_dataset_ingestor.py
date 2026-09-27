"""
tests/research/grade_e3/test_dataset_ingestor.py
================================================
Unit tests for Grade-E3 Dataset Ingestor and Sequence Validator.
"""

from __future__ import annotations

import pytest

from core.research.grade_e3.contracts import EvidenceStatus
from core.research.grade_e3.dataset_ingestor import (
    ClockRegressionError,
    L2DatasetIngestor,
    SequenceIntegrityError,
)


def test_raw_payload_ingestion_and_hashing() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    sample_bytes = b'{"e":"depthUpdate","E":1700000000000,"s":"BTCUSDT"}'
    status = ingestor.ingest_raw_payload(sample_bytes)
    assert status == EvidenceStatus.RAW_CAPTURED
    assert len(ingestor.raw_data_hash) == 64


def test_parsing_valid_diffs_and_trades() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    diff_dicts = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000000,
            "bids": [["60000.0", "1.5"]],
            "asks": [["60001.0", "2.0"]],
        },
        {
            "U": 106,
            "u": 110,
            "pu": 105,
            "E": 1700000000100,
            "bids": [["60000.5", "1.0"]],
            "asks": [["60001.0", "2.5"]],
        },
    ]
    trade_dicts = [
        {"t": 1001, "T": 1700000000050, "p": "60001.0", "q": "0.5", "m": False},
        {"t": 1002, "T": 1700000000080, "p": "60000.0", "q": "0.2", "m": True},
    ]

    status = ingestor.parse_records(diff_dicts, trade_dicts)
    assert status == EvidenceStatus.PARSED
    assert len(ingestor.get_diffs()) == 2
    assert len(ingestor.get_trades()) == 2

    # Validate sequences
    report = ingestor.validate_sequences(fail_on_gap=True)
    assert report.evidence_status == EvidenceStatus.SEQUENCE_VALIDATED
    assert report.is_fidelity_certified is True
    assert report.sequence_gaps == 0


def test_sequence_gap_detection() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    gap_diff_dicts = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000000,
            "bids": [["60000.0", "1.5"]],
            "asks": [["60001.0", "2.0"]],
        },
        {
            "U": 120,  # Gap: expected pu=105, but got pu=119
            "u": 125,
            "pu": 119,
            "E": 1700000000100,
            "bids": [["60000.5", "1.0"]],
            "asks": [["60001.0", "2.5"]],
        },
    ]
    ingestor.parse_records(gap_diff_dicts, [])

    # fail_on_gap=True must raise SequenceIntegrityError
    with pytest.raises(SequenceIntegrityError) as exc_info:
        ingestor.validate_sequences(fail_on_gap=True)
    assert "Sequence gap at packet 1" in str(exc_info.value)

    # fail_on_gap=False must record the gap and fail certification
    report = ingestor.validate_sequences(fail_on_gap=False)
    assert report.sequence_gaps == 1
    assert report.is_fidelity_certified is False
    assert report.evidence_status == EvidenceStatus.PARSED


def test_clock_regression_detection() -> None:
    ingestor = L2DatasetIngestor(venue="BINANCE_SPOT", symbol="BTCUSDT")
    clock_diff_dicts = [
        {
            "U": 100,
            "u": 105,
            "pu": 99,
            "E": 1700000000500,  # Later timestamp
            "bids": [["60000.0", "1.5"]],
            "asks": [["60001.0", "2.0"]],
        },
        {
            "U": 106,
            "u": 110,
            "pu": 105,
            "E": 1700000000100,  # Backward jump by 400ms!
            "bids": [["60000.5", "1.0"]],
            "asks": [["60001.0", "2.5"]],
        },
    ]
    ingestor.parse_records(clock_diff_dicts, [])

    with pytest.raises(ClockRegressionError) as exc_info:
        ingestor.validate_sequences(fail_on_gap=True, clock_drift_tolerance_ms=50.0)
    assert "Clock regression" in str(exc_info.value)
