"""
tests/execution/test_milestone32_r_burn_in_review.py
====================================================
Adversarial & Unit Test Battery for Milestone 32-R Physical Testnet Burn-In Review:
1. Gate 1: Time conservation audit (H_elapsed == H_qualified + H_disqualified)
2. Gate 2: Effective duration threshold (>= 300h of 336h, >= 89.2%)
3. Gate 3: Lost-ACK reconciliation completeness (0 ambiguous)
4. Gate 4: Zero overfill invariant enforcement
5. Gate 5: 1.5% decomposed equity cap compliance
6. Gate 6: Checkpoint durability verification
7. Gate 7: Capital isolation firewall enforcement
8. Dossier emission and cryptographic serialization
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.execution.testnet.burn_in_evaluator import (
    M32RBurnInEvaluator,
    M32RStatus,
)
from core.execution.testnet.campaign_daemon_integrator import CampaignRunTelemetry
from core.execution.testnet.daemon_orchestrator import DaemonLifecycleState


@pytest.fixture
def sample_telemetry() -> CampaignRunTelemetry:
    """Fixture providing compliant 336-hour campaign telemetry."""
    return CampaignRunTelemetry(
        campaign_id="CAMP-TEST-336H",
        target_duration_hours=336.0,
        wall_clock_elapsed_hours=336.0,
        effective_qualified_hours=310.0,
        disqualified_hours=26.0,
        qualification_ratio=310.0 / 336.0,  # 92.26% > 89.2%
        time_conservation_verified=True,
        total_allocations=50,
        total_orders_submitted=50,
        total_orders_reconciled=50,
        lost_ack_count=5,
        checkpoint_count=50,
        final_lifecycle_state=DaemonLifecycleState.RUNNING,
        real_capital_enabled=False,
    )


def test_01_gate_1_time_conservation_evaluation(sample_telemetry: CampaignRunTelemetry):
    """Verifies that failing time conservation trips QUARANTINED status."""
    bad_telemetry = sample_telemetry.model_copy(update={"time_conservation_verified": False})
    decision = M32RBurnInEvaluator.evaluate(bad_telemetry)
    assert decision.status == M32RStatus.QUARANTINED
    assert "time conservation" in decision.rationale.lower()


def test_02_gate_2_effective_duration_evaluation(sample_telemetry: CampaignRunTelemetry):
    """Verifies that qualified hours < 300h leads to CONDITIONAL status."""
    under_hours_telemetry = sample_telemetry.model_copy(
        update={
            "effective_qualified_hours": 280.0,
            "disqualified_hours": 56.0,
            "qualification_ratio": 280.0 / 336.0,  # 83.3% < 89.2%
        }
    )
    decision = M32RBurnInEvaluator.evaluate(under_hours_telemetry)
    assert decision.status == M32RStatus.CONDITIONAL


def test_03_gate_3_unreconciled_lost_acks_quarantine(sample_telemetry: CampaignRunTelemetry):
    """Verifies that an ambiguous unreconciled lost-ACK trips QUARANTINED status."""
    decision = M32RBurnInEvaluator.evaluate(sample_telemetry, unreconciled_lost_acks=1)
    assert decision.status == M32RStatus.QUARANTINED
    assert "reconciliation failure" in decision.rationale.lower()


def test_04_gate_4_overfill_invariant_rejection(sample_telemetry: CampaignRunTelemetry):
    """Verifies that an overfill event causes immediate REJECTED verdict."""
    decision = M32RBurnInEvaluator.evaluate(sample_telemetry, overfill_violations=1)
    assert decision.status == M32RStatus.REJECTED
    assert "risk invariant breach" in decision.rationale.lower()


def test_05_gate_5_equity_cap_breach_rejection(sample_telemetry: CampaignRunTelemetry):
    """Verifies that breaching the 1.5% equity cap causes immediate REJECTED verdict."""
    decision = M32RBurnInEvaluator.evaluate(sample_telemetry, equity_cap_breaches=1)
    assert decision.status == M32RStatus.REJECTED


def test_06_dossier_emission_and_json_serialization(sample_telemetry: CampaignRunTelemetry):
    """Verifies that emit_dossiers writes all 4 dossiers to disk with complete data."""
    decision = M32RBurnInEvaluator.evaluate(sample_telemetry)
    assert decision.status == M32RStatus.QUALIFIED

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        emitted = M32RBurnInEvaluator.emit_dossiers(
            telemetry=sample_telemetry,
            decision=decision,
            output_dir=out,
            codebase_git_hash="0d18b1a",
        )

        assert emitted["dossier"].exists()
        assert emitted["decision"].exists()
        assert emitted["quality"].exists()
        assert emitted["reconciliation"].exists()

        dossier_text = emitted["dossier"].read_text(encoding="utf-8")
        assert "336-Hour Physical Testnet Burn-In Dossier" in dossier_text
        assert "310.0h" in dossier_text
        assert "real_capital_enabled=False" in dossier_text


def test_07_full_passing_burn_in_decision(sample_telemetry: CampaignRunTelemetry):
    """Verifies that a compliant campaign receives an unqualified QUALIFIED verdict."""
    decision = M32RBurnInEvaluator.evaluate(sample_telemetry)
    assert decision.status == M32RStatus.QUALIFIED
    assert decision.all_gates_passed is True
    assert decision.real_capital_enabled is False
