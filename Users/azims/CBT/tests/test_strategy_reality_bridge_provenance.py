"""
tests/test_strategy_reality_bridge_provenance.py
================================================
Comprehensive verification suite for StrategyRealityBridge:
1. Cryptographic provenance verification against data/research/datasets/manifest_k9.json
2. Anti-tampering fail-closed checks (ProvenanceTamperError)
3. Anti-epistemic grade inflation checks (EpistemicInflationError)
4. Constitutional viability vs. tradeability decoupling (is_viable != is_tradeable)
5. Backward-compatible sequence unpacking (cal_pnl, drag, is_viable = result)
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from core.kronos.research.strategy_reality_bridge import (
    EMPIRICAL_DRAG_REGISTRY,
    CalibratedExecutionResult,
    EpistemicInflationError,
    MicrostructureDragProfile,
    ProvenanceAuthority,
    ProvenanceTamperError,
    ProvenanceVerificationError,
    StrategyRealityBridge,
    compute_profile_digest,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_provenance_verification_against_k9_manifest() -> None:
    """Verifies that all registry profiles match content hashes in manifest_k9.json."""
    authority = ProvenanceAuthority()
    manifest = authority._load_manifest()
    assert len(manifest) > 0, "Manifest must not be empty"

    for key, profile in EMPIRICAL_DRAG_REGISTRY.items():
        assert profile.dataset_id in manifest, f"Dataset {profile.dataset_id} missing from manifest"
        expected_hash = manifest[profile.dataset_id]["content_hash"]
        assert profile.dataset_hash == expected_hash, (
            f"Hash mismatch in {key}: {profile.dataset_hash} != {expected_hash}"
        )
        # Verification method must pass
        assert authority.verify_profile(profile) is True


def test_provenance_tamper_fails_closed() -> None:
    """Tampering with profile values without valid profile_hash must fail closed."""
    authority = ProvenanceAuthority()
    legit_profile = EMPIRICAL_DRAG_REGISTRY["BTC_15m"]

    # Tamper with maker_net_edge_bps (make it look profitable)
    tampered_data = asdict(legit_profile)
    tampered_data["maker_net_edge_bps"] = +50.0
    # Keep the old profile_hash
    tampered_profile = MicrostructureDragProfile(**tampered_data)

    with pytest.raises(ProvenanceTamperError) as exc_info:
        authority.verify_profile(tampered_profile)
    assert "Tamper detected" in str(exc_info.value)


def test_provenance_manifest_hash_mismatch_fails_closed() -> None:
    """Providing a forged dataset hash for a known dataset ID must fail closed."""
    authority = ProvenanceAuthority()
    legit_profile = EMPIRICAL_DRAG_REGISTRY["BTC_15m"]

    tampered_data = asdict(legit_profile)
    tampered_data["dataset_hash"] = "deadbeef" * 8
    # Recompute digest so tamper check passes, but manifest check fails
    tampered_data["profile_hash"] = compute_profile_digest(tampered_data)
    tampered_profile = MicrostructureDragProfile(**tampered_data)

    with pytest.raises(ProvenanceVerificationError) as exc_info:
        authority.verify_profile(tampered_profile)
    assert "Dataset hash mismatch" in str(exc_info.value)


def test_viability_does_not_imply_tradeability() -> None:
    """
    Constitutional Regression Test:
    A strategy exhibiting positive calibrated net PnL (is_viable = True) MUST NOT
    receive live execution authority (is_tradeable = False) under OHLCV approximation.
    """
    bridge = StrategyRealityBridge()

    # SOL 4h has strong empirical maker net edge (+181.84 bps)
    # Raw PnL 50 bps + 181.84 bps = 231.84 bps -> highly viable!
    result: CalibratedExecutionResult = bridge.apply_execution_reality(
        asset="SOL",
        timeframe="4h",
        raw_pnl_bps=50.0,
        is_maker=True,
    )

    # Viability is TRUE: strategy is economically viable in research
    assert result.is_viable is True
    assert result.calibrated_net_pnl_bps > 200.0

    # Tradeability is strictly FALSE: cannot execute live under OHLCV approximation!
    assert result.is_tradeable is False
    assert "DENIED_EVIDENCE_GRADE" in result.authorization_status
    assert result.epistemic_grade == "GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE"


def test_quarantine_verdict_blocks_tradeability() -> None:
    """Quarantined profiles (BTC, ETH) strictly deny live execution authority."""
    bridge = StrategyRealityBridge()

    # Even with a massive raw PnL of 500 bps on BTC 1h:
    result = bridge.apply_execution_reality(
        asset="BTC",
        timeframe="1h",
        raw_pnl_bps=500.0,
        is_maker=True,
    )
    assert result.is_viable is True
    assert result.is_tradeable is False
    assert result.research_verdict == "QUARANTINE"
    assert "DENIED_CONSTITUTIONAL_QUARANTINE" in result.authorization_status


def test_epistemic_grade_inflation_prohibited() -> None:
    """Attempting to label an OHLCV dataset as L2_TICK_VERIFIED must fail closed."""
    authority = ProvenanceAuthority()
    legit_profile = EMPIRICAL_DRAG_REGISTRY["BTC_15m"]

    inflated_data = asdict(legit_profile)
    inflated_data["epistemic_grade"] = "L2_TICK_VERIFIED"
    inflated_data["profile_hash"] = compute_profile_digest(inflated_data)
    inflated_profile = MicrostructureDragProfile(**inflated_data)

    with pytest.raises(EpistemicInflationError) as exc_info:
        authority.verify_profile(inflated_profile)
    assert "Epistemic inflation rejected" in str(exc_info.value)


def test_backward_compatible_sequence_unpacking() -> None:
    """Preserves legacy 3-tuple unpacking: cal_pnl, drag, is_viable = bridge.apply_execution_reality(...)."""
    bridge = StrategyRealityBridge()

    # Legacy syntax
    cal_pnl, drag, is_viable = bridge.apply_execution_reality(
        asset="ETH",
        timeframe="1h",
        raw_pnl_bps=50.0,
        is_maker=True,
    )
    assert isinstance(cal_pnl, float)
    assert isinstance(drag, float)
    assert isinstance(is_viable, bool)

    # Object access syntax
    res = bridge.apply_execution_reality(
        asset="ETH",
        timeframe="1h",
        raw_pnl_bps=50.0,
        is_maker=True,
    )
    assert res.calibrated_net_pnl_bps == cal_pnl
    assert res.drag_bps == drag
    assert res.is_viable == is_viable
    assert res.is_tradeable is False


def test_synthetic_fallback_profile_safety() -> None:
    """Unmapped assets generate conservative synthetic fallbacks with zero tradeability."""
    bridge = StrategyRealityBridge()

    fallback_result = bridge.apply_execution_reality(
        asset="DOGE",
        timeframe="5m",
        raw_pnl_bps=100.0,
        is_maker=True,
    )
    assert fallback_result.epistemic_grade == "SYNTHETIC_CONSERVATIVE_FALLBACK"
    assert fallback_result.research_verdict == "QUARANTINE"
    assert fallback_result.is_tradeable is False
    assert fallback_result.dataset_id == "SYNTHETIC_CONSERVATIVE_FALLBACK"


def test_verify_all_profiles_preflight() -> None:
    """Verifies that all registered profiles pass preflight provenance authority validation."""
    bridge = StrategyRealityBridge()
    validation_map = bridge.verify_all_profiles()
    assert len(validation_map) == 6
    for key, valid in validation_map.items():
        assert valid is True, f"Profile {key} failed preflight validation"
