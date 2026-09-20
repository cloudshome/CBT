"""
tests/research/grade_e3/test_bridge_integration.py
==================================================
Integration and governance verification suite for Grade-E3 Reality Adapter,
Provenance Authority L2 bundle validation, and Phase 9 Research-Only Firewall.
"""

from __future__ import annotations

import pytest

from core.kronos.research.strategy_reality_bridge import (
    GradeE3RealityAdapter,
    MicrostructureDragProfile,
    ProvenanceAuthority,
    ProvenanceTamperError,
)
from core.research.grade_e3.contracts import (
    TamperEvidentEvidenceBundle,
)


def _make_dummy_bundle(experiment_id: str = "TEST_EXP_001") -> TamperEvidentEvidenceBundle:
    return TamperEvidentEvidenceBundle(
        raw_data_hash="a" * 64,
        normalized_data_hash="a" * 64,
        reconstructed_book_hash="b" * 64,
        parser_version="1.0.0",
        book_builder_version="1.0.0",
        queue_model_version="Q1_VOLUME_CANCELLATIONS",
        configuration_hash="c" * 64,
        code_commit="HEAD",
        venue="BINANCE_SPOT",
        symbol="BTCUSDT",
        time_range=(1000, 2000),
        sequence_audit={"status": "PASS"},
        clock_audit={"status": "PASS"},
        missing_data_report={"status": "PASS"},
        experiment_id=experiment_id,
        result_artifact_hash="d" * 64,
    )


def test_grade_e3_adapter_is_tradeable_invariant() -> None:
    """
    Phase 9 Permanent Research Invariant:
    GradeE3RealityAdapter.is_tradeable(profile) must strictly return False for any profile.
    """
    profile = MicrostructureDragProfile(
        asset="BTC",
        timeframe="L2",
        dataset_id="GRADE_E3_BTC_L2",
        dataset_hash="e" * 64,
        experiment_id="EXP_BTC_L2",
        sample_size_orders=1000,
        sample_size_fills=800,
        epistemic_grade="L2_TICK_VERIFIED",
        research_verdict="CONDITIONALLY_PERMITTED",
        maker_fill_rate_pct=80.0,
        maker_adverse_selection_bps=-0.5,
        maker_net_edge_bps=0.48,
        taker_roundtrip_cost_bps=5.0,
        toxic_fill_ratio=0.30,
        recommended_execution_role="INSTITUTIONAL_MAKER_ONLY",
    )
    # Must strictly be False
    assert GradeE3RealityAdapter.is_tradeable(profile) is False


def test_provenance_authority_verifies_l2_bundle() -> None:
    authority = ProvenanceAuthority()
    bundle = _make_dummy_bundle()

    # Valid bundle passes
    assert authority.verify_l2_bundle(bundle) is True

    # Tampered bundle fails closed with ProvenanceTamperError
    tampered_bundle = TamperEvidentEvidenceBundle(
        raw_data_hash="f" * 64,  # Changed field
        normalized_data_hash=bundle.normalized_data_hash,
        reconstructed_book_hash=bundle.reconstructed_book_hash,
        parser_version=bundle.parser_version,
        book_builder_version=bundle.book_builder_version,
        queue_model_version=bundle.queue_model_version,
        configuration_hash=bundle.configuration_hash,
        code_commit=bundle.code_commit,
        venue=bundle.venue,
        symbol=bundle.symbol,
        time_range=bundle.time_range,
        sequence_audit=bundle.sequence_audit,
        clock_audit=bundle.clock_audit,
        missing_data_report=bundle.missing_data_report,
        experiment_id=bundle.experiment_id,
        result_artifact_hash=bundle.result_artifact_hash,
        bundle_hash=bundle.bundle_hash,  # Reusing old hash -> mismatch!
    )
    with pytest.raises(ProvenanceTamperError) as exc:
        authority.verify_l2_bundle(tampered_bundle)
    assert "verification failed" in str(exc.value)


def test_create_bridge_with_l2_profiles() -> None:
    bundle = _make_dummy_bundle("EXP_BTC_L2")
    profile = MicrostructureDragProfile(
        asset="BTC",
        timeframe="L2",
        dataset_id="SYNTHETIC_GRADE_E3_BTC_L2",
        dataset_hash="a" * 64,
        experiment_id="EXP_BTC_L2",
        sample_size_orders=1000,
        sample_size_fills=800,
        epistemic_grade="L2_TICK_VERIFIED",
        research_verdict="CONDITIONALLY_PERMITTED",
        maker_fill_rate_pct=80.0,
        maker_adverse_selection_bps=-0.5,
        maker_net_edge_bps=0.48,
        taker_roundtrip_cost_bps=5.0,
        toxic_fill_ratio=0.30,
        recommended_execution_role="INSTITUTIONAL_MAKER_ONLY",
    )

    bridge = GradeE3RealityAdapter.create_bridge_with_l2_profiles(
        l2_profiles={"BTC_L2": profile},
        bundles={"BTC_L2": bundle},
    )
    assert "BTC_L2" in bridge.registry

    # Querying profile
    retrieved = bridge.get_profile("BTC", "L2")
    assert retrieved.epistemic_grade == "L2_TICK_VERIFIED"
    assert retrieved.maker_net_edge_bps == 0.48


def test_research_to_execution_isolation() -> None:
    """
    Phase 9 Structural Isolation Test:
    Ensures Grade-E3 modules have zero imports or links to live exchange execution,
    order placement, or KMS credential release.
    """
    import inspect

    import core.research.grade_e3.dataset_ingestor as di
    import core.research.grade_e3.l2_book_builder as bb
    import core.research.grade_e3.l2_queue_engine as qe

    for mod in (di, bb, qe):
        source = inspect.getsource(mod)
        assert "core.execution.live_router" not in source
        assert "core.execution.connectors" not in source
        assert "core.auth.kms_enclave" not in source
        assert "place_order" not in source
        assert "submit_live" not in source
