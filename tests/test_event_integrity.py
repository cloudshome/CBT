"""
tests/test_event_integrity.py
=============================
Unit tests for SDCC canonical event construction, deterministic hashing, and integrity verification.
"""

from core.collective.event import EventProvenance, build_canonical_event
from core.collective.event_hash import (
    canonical_json_bytes,
    compute_payload_hash,
    verify_event_integrity,
)
from core.collective.event_types import CollectiveEventType


def test_build_canonical_event_structure():
    prov = EventProvenance(
        source_type="PAPER_ENGINE",
        node_id="HOME-01",
        strategy_id="SMC_FVG_01",
        code_version="commit_abc123",
    )
    payload = {"symbol": "BTCUSDT", "side": "BUY", "price": 60000.0, "size": 0.5}

    event = build_canonical_event(
        node_id="HOME-01",
        sequence=18421,
        event_type=CollectiveEventType.PAPER_ORDER_FILLED,
        entity_type="paper_trade",
        entity_id="PT-HOME01-20260912-00001",
        payload=payload,
        provenance=prov,
    )

    assert event.node_id == "HOME-01"
    assert event.sequence == 18421
    # Check 12-digit zero padded sequence in event_id
    assert ":000000018421:" in event.event_id
    assert event.event_id.startswith("HOME-01:")

    # Verify cryptographic integrity
    is_valid, err = verify_event_integrity(event.to_dict())
    assert is_valid is True
    assert err is None


def test_tamper_detection():
    prov = {"source_type": "RESEARCH_LAB", "node_id": "OFFICE-01"}
    payload = {"claim": "Liquidity sweep precedes reversal", "confidence": 0.85}

    event = build_canonical_event(
        node_id="OFFICE-01",
        sequence=1,
        event_type=CollectiveEventType.CLAIM_CREATED,
        entity_type="claim",
        entity_id="C-0001",
        payload=payload,
        provenance=prov,
    )

    ev_dict = event.to_dict()

    # 1. Tamper payload
    ev_dict["payload"]["confidence"] = 0.99
    is_valid, err = verify_event_integrity(ev_dict)
    assert is_valid is False
    assert "Payload hash mismatch" in err

    # 2. Reset payload and tamper envelope field
    ev_dict["payload"]["confidence"] = 0.85
    ev_dict["entity_id"] = "C-9999"
    is_valid, err = verify_event_integrity(ev_dict)
    assert is_valid is False
    assert "Event hash mismatch" in err


def test_deterministic_canonical_serialization():
    # Two dictionaries with different key insertion orders must yield identical canonical bytes
    dict_a = {"z": 10, "a": {"b": 2, "a": 1}}
    dict_b = {"a": {"a": 1, "b": 2}, "z": 10}

    assert canonical_json_bytes(dict_a) == canonical_json_bytes(dict_b)
    assert compute_payload_hash(dict_a) == compute_payload_hash(dict_b)
