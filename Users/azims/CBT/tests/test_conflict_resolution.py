"""
tests/test_conflict_resolution.py
=================================
Unit tests for SDCC conflict management, contradiction sets, and provenance validation.
"""

import tempfile
from pathlib import Path

import pytest
from core.collective.conflict import ConflictManager, ConflictType
from core.collective.event import build_canonical_event
from core.collective.event_types import CollectiveEventType
from core.collective.provenance import validate_event_provenance
from core.collective.quarantine import QuarantineManager


def test_knowledge_contradiction_preservation():
    """
    Validates Section 22: Contradictory claims create a CONFLICT_SET preserving both.
    Neither claim is overwritten or deleted.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ConflictManager(base_dir=Path(tmpdir))

        claim_a = {
            "claim_id": "CLM-001",
            "statement": "Strategy SMC increases expectancy by +0.41R",
            "node_id": "HOME-01",
            "dataset": "BTC_2025_Q1",
        }
        claim_b = {
            "claim_id": "CLM-002",
            "statement": "Strategy SMC decreases expectancy by -0.15R",
            "node_id": "OFFICE-01",
            "dataset": "BTC_2026_Q2",
        }
        context = {
            "datasets": ["BTC_2025_Q1", "BTC_2026_Q2"],
            "market_regimes": ["BULL_TREND", "CHOPPY_RANGE"],
            "code_versions": ["commit_111", "commit_222"],
        }

        rec = mgr.create_knowledge_contradiction_set(claim_a, claim_b, context)
        assert rec.conflict_type == ConflictType.KNOWLEDGE_CONTRADICTION
        assert rec.target_entity_id == "CLM-001"
        assert rec.details["claim_a"]["statement"] == claim_a["statement"]
        assert rec.details["claim_b"]["statement"] == claim_b["statement"]

        # Confirm listing from disk
        conflicts = mgr.list_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].conflict_id == rec.conflict_id


def test_quarantine_corrupted_item():
    with tempfile.TemporaryDirectory() as tmpdir:
        qm = QuarantineManager(base_dir=Path(tmpdir))

        path = qm.quarantine_item(
            item_id="EVENT-BAD-01",
            source_node="NODE-ROGUE",
            reason="EVENT_HASH_MISMATCH",
            raw_content={"corrupt": "data"},
            expected_hash="hash_a",
            actual_hash="hash_b",
        )

        assert path.exists()
        assert qm.get_quarantine_count() == 1
        quarantined = qm.list_quarantined()
        assert len(quarantined) == 1
        assert quarantined[0]["reason"] == "EVENT_HASH_MISMATCH"


def test_provenance_validation():
    # Valid paper trade event
    valid_ev = build_canonical_event(
        node_id="HOME-01",
        sequence=1,
        event_type=CollectiveEventType.PAPER_POSITION_OPENED,
        entity_type="paper_trade",
        entity_id="PT-001",
        payload={"symbol": "BTCUSDT", "size": 1.0},
        provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01", "strategy_id": "SMC"},
    )
    is_valid, err = validate_event_provenance(valid_ev)
    assert is_valid is True
    assert err is None

    # Invalid paper trade: missing symbol
    invalid_ev = build_canonical_event(
        node_id="HOME-01",
        sequence=2,
        event_type=CollectiveEventType.PAPER_POSITION_OPENED,
        entity_type="paper_trade",
        entity_id="PT-002",
        payload={"size": 1.0},  # Missing symbol
        provenance={"source_type": "PAPER_ENGINE", "node_id": "HOME-01"},
    )
    is_valid, err = validate_event_provenance(invalid_ev)
    assert is_valid is False
    assert "missing required 'symbol'" in err
