"""
tests/governance/test_institutional_deployment.py
=================================================
Institutional Deployment & Governance Control Plane Tests.
Covers all negative, adversarial, and invariant verification requirements.
"""

from __future__ import annotations

import time

import pytest

from core.governance.institutional_deployment import (
    DeploymentGate,
    DeploymentStage,
    DirectStageMutationError,
    GateEvidence,
    GateStatus,
    InstitutionalDeploymentGovernor,
    PermanentCapitalFirewallViolation,
    PromotionRequest,
)
from core.research.grade_e3.contracts import DecoupledStrategyStatus


def create_valid_evidence(
    gate: DeploymentGate,
    strategy_id: str = "STRAT_BTC_001",
    valid_until_offset: float = 3600.0,
    revoked: bool = False,
) -> GateEvidence:
    """Helper creating valid GateEvidence with deterministic 64-char hex hash."""
    now = time.time()
    dataset_hash = "a" * 64
    return GateEvidence(
        gate_id=gate,
        status=GateStatus.PASSED,
        strategy_id=strategy_id,
        dataset_hash=dataset_hash,
        experiment_id=f"EXP_{gate.value}",
        issuer="sky.governance.audit_pipeline",
        issued_at=now - 100.0,
        valid_until=now + valid_until_offset,
        revocation_status=revoked,
    )


def test_initial_stage_is_research_only() -> None:
    governor = InstitutionalDeploymentGovernor()
    assert governor.current_stage == DeploymentStage.RESEARCH_ONLY
    assert governor.real_capital_enabled is False
    assert governor.capabilities.research is True
    assert governor.capabilities.live_order_submission is False
    assert governor.capabilities.capital_allocation is False


def test_direct_stage_assignment_is_rejected() -> None:
    governor = InstitutionalDeploymentGovernor()
    with pytest.raises(DirectStageMutationError) as exc_info:
        governor.current_stage = DeploymentStage.LIVE_AUTHORIZED
    assert "Direct mutation of current_stage" in str(exc_info.value)


def test_environment_variable_cannot_enable_capital(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REAL_CAPITAL_ENABLED", "true")
    with pytest.raises(PermanentCapitalFirewallViolation) as exc_info:
        InstitutionalDeploymentGovernor()
    assert "Permanent Capital Firewall breach detected" in str(exc_info.value)


def test_api_payload_cannot_enable_capital() -> None:
    governor = InstitutionalDeploymentGovernor()
    with pytest.raises(PermanentCapitalFirewallViolation) as exc_info:
        governor.real_capital_enabled = True
    assert "real_capital_enabled is permanently locked to False" in str(exc_info.value)


def test_gate_pass_with_missing_evidence_is_rejected() -> None:
    governor = InstitutionalDeploymentGovernor()
    req = PromotionRequest(
        target_stage=DeploymentStage.RESEARCH_VIABLE,
        strategy_id="STRAT_BTC_001",
        evidence_bundle={},  # Missing Gate 1
    )
    verdict = governor.request_promotion(req)
    assert verdict.approved is False
    assert "MISSING_EVIDENCE" in (verdict.rejection_reason or "")
    assert governor.current_stage == DeploymentStage.RESEARCH_ONLY


def test_expired_evidence_cannot_promote() -> None:
    governor = InstitutionalDeploymentGovernor()
    expired_evidence = create_valid_evidence(
        gate=DeploymentGate.GATE_1_DATA_FIDELITY,
        valid_until_offset=-100.0,  # Expired 100 seconds ago
    )
    req = PromotionRequest(
        target_stage=DeploymentStage.RESEARCH_VIABLE,
        strategy_id="STRAT_BTC_001",
        evidence_bundle={DeploymentGate.GATE_1_DATA_FIDELITY: expired_evidence},
    )
    verdict = governor.request_promotion(req)
    assert verdict.approved is False
    assert "EXPIRED" in (verdict.rejection_reason or "")
    assert governor.current_stage == DeploymentStage.RESEARCH_ONLY


def test_revoked_evidence_cannot_promote() -> None:
    governor = InstitutionalDeploymentGovernor()
    revoked_evidence = create_valid_evidence(
        gate=DeploymentGate.GATE_1_DATA_FIDELITY,
        revoked=True,
    )
    req = PromotionRequest(
        target_stage=DeploymentStage.RESEARCH_VIABLE,
        strategy_id="STRAT_BTC_001",
        evidence_bundle={DeploymentGate.GATE_1_DATA_FIDELITY: revoked_evidence},
    )
    verdict = governor.request_promotion(req)
    assert verdict.approved is False
    assert "REVOKED" in (verdict.rejection_reason or "")
    assert governor.current_stage == DeploymentStage.RESEARCH_ONLY


def test_tampered_dataset_hash_fails() -> None:
    governor = InstitutionalDeploymentGovernor()
    now = time.time()
    # Malformed dataset hash (not 64 chars)
    bad_evidence = GateEvidence(
        gate_id=DeploymentGate.GATE_1_DATA_FIDELITY,
        status=GateStatus.PASSED,
        strategy_id="STRAT_BTC_001",
        dataset_hash="short_hash_not_sha256",
        experiment_id="EXP_001",
        issuer="sky.governance",
        issued_at=now - 10,
        valid_until=now + 1000,
    )
    req = PromotionRequest(
        target_stage=DeploymentStage.RESEARCH_VIABLE,
        strategy_id="STRAT_BTC_001",
        evidence_bundle={DeploymentGate.GATE_1_DATA_FIDELITY: bad_evidence},
    )
    verdict = governor.request_promotion(req)
    assert verdict.approved is False
    assert "MALFORMED_DATASET_HASH" in (verdict.rejection_reason or "")


def test_sandbox_verified_does_not_enable_live_orders() -> None:
    governor = InstitutionalDeploymentGovernor()

    # Step 1: Promote to RESEARCH_VIABLE
    e1 = create_valid_evidence(DeploymentGate.GATE_1_DATA_FIDELITY)
    v1 = governor.request_promotion(
        PromotionRequest(
            DeploymentStage.RESEARCH_VIABLE, "S1", {DeploymentGate.GATE_1_DATA_FIDELITY: e1}
        )
    )
    assert v1.approved is True

    # Step 2: Promote to EXECUTION_MODEL_VALIDATED
    e2 = create_valid_evidence(DeploymentGate.GATE_2_EXECUTION_REALITY)
    v2 = governor.request_promotion(
        PromotionRequest(
            DeploymentStage.EXECUTION_MODEL_VALIDATED,
            "S1",
            {DeploymentGate.GATE_1_DATA_FIDELITY: e1, DeploymentGate.GATE_2_EXECUTION_REALITY: e2},
        )
    )
    assert v2.approved is True

    # Step 3: Promote to SANDBOX_ELIGIBLE
    e3 = create_valid_evidence(DeploymentGate.GATE_3_NET_EXPECTANCY)
    v3 = governor.request_promotion(
        PromotionRequest(
            DeploymentStage.SANDBOX_ELIGIBLE,
            "S1",
            {
                DeploymentGate.GATE_1_DATA_FIDELITY: e1,
                DeploymentGate.GATE_2_EXECUTION_REALITY: e2,
                DeploymentGate.GATE_3_NET_EXPECTANCY: e3,
            },
        )
    )
    assert v3.approved is True

    # Step 4: Promote to SANDBOX_VERIFIED
    e4 = create_valid_evidence(DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY)
    e5 = create_valid_evidence(DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN)
    bundle_4_5 = {
        DeploymentGate.GATE_1_DATA_FIDELITY: e1,
        DeploymentGate.GATE_2_EXECUTION_REALITY: e2,
        DeploymentGate.GATE_3_NET_EXPECTANCY: e3,
        DeploymentGate.GATE_4_ROBUSTNESS_REPRODUCIBILITY: e4,
        DeploymentGate.GATE_5_EXTENDED_SANDBOX_BURN_IN: e5,
    }
    v4 = governor.request_promotion(
        PromotionRequest(DeploymentStage.SANDBOX_VERIFIED, "S1", bundle_4_5)
    )
    assert v4.approved is True
    assert governor.current_stage == DeploymentStage.SANDBOX_VERIFIED

    # Invariant check: SANDBOX_VERIFIED != permission to submit live orders or allocate capital
    assert governor.capabilities.paper_trading is True
    assert governor.capabilities.exchange_testnet is True
    assert governor.capabilities.live_order_submission is False
    assert governor.capabilities.funded_account_connection is False
    assert governor.capabilities.capital_allocation is False


def test_human_review_does_not_authorize_automatically() -> None:
    governor = InstitutionalDeploymentGovernor()

    # Attempt to jump straight to HUMAN_LIVE_REVIEW without predecessor
    req = PromotionRequest(
        target_stage=DeploymentStage.HUMAN_LIVE_REVIEW,
        strategy_id="S1",
        evidence_bundle={},
    )
    v = governor.request_promotion(req)
    assert v.approved is False
    assert "INVALID_SEQUENCE" in (v.rejection_reason or "")


def test_emergency_downgrade_revokes_capabilities() -> None:
    governor = InstitutionalDeploymentGovernor()

    # Promote to RESEARCH_VIABLE
    e1 = create_valid_evidence(DeploymentGate.GATE_1_DATA_FIDELITY)
    v = governor.request_promotion(
        PromotionRequest(
            DeploymentStage.RESEARCH_VIABLE, "S1", {DeploymentGate.GATE_1_DATA_FIDELITY: e1}
        )
    )
    assert v.approved is True

    # Emergency downgrade
    governor.emergency_downgrade(reason="Reconciliation anomaly detected on testnet feed")
    assert governor.current_stage == DeploymentStage.RESEARCH_ONLY
    assert governor.capabilities.paper_trading is False
    assert governor.capabilities.live_order_submission is False


def test_decoupled_status_properties() -> None:
    status = DecoupledStrategyStatus(
        research_viable=True,
        execution_model_validated=False,
        tradeable=False,
        live_authorized=False,
    )
    assert status.research_viable is True
    assert status.tradeable is False
    assert status.live_authorized is False
    data = status.to_dict()
    assert data["research_viable"] is True
    assert data["tradeable"] is False
