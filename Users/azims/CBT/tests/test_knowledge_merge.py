"""
tests/test_knowledge_merge.py
=============================
Unit tests for multi-node knowledge synthesis and provenance preservation.
"""

import tempfile
from pathlib import Path

import pytest
from core.collective.adapters.research_adapter import ResearchEventAdapter
from core.collective.event_store import EventStore
from core.collective.identity import NodeIdentityManager
from core.collective.reducer import CollectiveReducer


def test_multi_node_knowledge_merge():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        id_mgr = NodeIdentityManager(base_dir=base_dir)

        # Node HOME
        id_home = id_mgr.create_identity("HOME-01")
        store_home = EventStore(base_dir=base_dir / "home")
        adapter_home = ResearchEventAdapter(identity=id_home, store=store_home)

        # Node OFFICE
        id_office = id_mgr.create_identity("OFFICE-01")
        store_office = EventStore(base_dir=base_dir / "office")
        adapter_office = ResearchEventAdapter(identity=id_office, store=store_office)

        # 1. HOME in-gests a PDF and registers source & claims
        adapter_home.emit_source_registered(
            source_id="SRC-HOME-01",
            title="Institutional Liquidity & Order Flow",
            source_uri="https://quant.org/orderflow.pdf",
            author="Dr. Quant",
        )
        adapter_home.emit_claim_created(
            claim_id="CLM-001",
            statement="CVD absorption at key levels signals reversal",
            source_id="SRC-HOME-01",
            confidence=0.82,
        )

        # 2. OFFICE conducts backtests and attaches empirical evidence
        adapter_office.emit_evidence_attached(
            evidence_id="EVD-OFFICE-01",
            claim_id="CLM-001",
            verdict="SUPPORTED",
            evidence_grade=3,  # EMPIRICAL
            sample_size=350,
            p_value=0.002,
            details={"sharpe": 1.95, "win_rate": 0.64},
        )
        adapter_office.emit_hypothesis_rejected(
            hypothesis_id="HYP-OFFICE-99",
            reason="OVERFITTING",
            autopsy_notes="Monte Carlo test showed 14% ruin probability in bear regime",
        )

        # 3. Combine events and reduce
        all_events = store_home.get_all_events() + store_office.get_all_events()
        reducer = CollectiveReducer()
        state = reducer.reduce(all_events)

        # Verify collective knowledge state
        assert len(state.knowledge.sources) == 1
        assert len(state.knowledge.claims) == 1
        assert len(state.knowledge.evidence) == 1
        assert len(state.knowledge.hypotheses) == 1

        # Check evidence was properly attached to claim
        ev = state.knowledge.evidence["EVD-OFFICE-01"]
        assert ev["claim_id"] == "CLM-001"
        assert ev["evidence_grade"] == 3
        assert ev["sample_size"] == 350

        # Check node contributions
        assert state.knowledge.contributions_by_node["HOME-01"] == 2
        assert state.knowledge.contributions_by_node["OFFICE-01"] == 2
