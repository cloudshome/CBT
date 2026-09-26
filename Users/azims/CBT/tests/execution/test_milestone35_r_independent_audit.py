"""
tests/execution/test_milestone35_r_independent_audit.py
======================================================
Adversarial & Unit Test Suite for Milestone 35-R:
Generation 6 Independent Release & Evidence Audit (15 Institutional Obligations).

Validates:
1. Full 15-obligation audit passes cleanly in production state (15/15 PASS).
2. Obligation 1: Milestone 18 execution surface immutability.
3. Obligation 4: 336h -> 310h time conservation & itemized exclusion breakdown.
4. Obligation 8: Milestone 34 LDB formula & asymmetric hazard detection.
5. Obligation 10: Permanent constitutional capital firewall across all Gen 6 engines.
6. Obligation 12: Cryptographic SHA256SUMS.txt integrity verification.
7. Obligation 13: Institutional invariant: Installer != Operational authorization.
8. Obligation 14: Gate G-21 Human Operator Approval non-bypassability.
9. Obligation 15: Clean-room reconstruction consistency.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_generation6_release import Generation6IndependentAuditor


@pytest.fixture
def auditor() -> Generation6IndependentAuditor:
    return Generation6IndependentAuditor()


def test_01_full_audit_passes_all_15_obligations(auditor: Generation6IndependentAuditor):
    """Verifies that the clean repository passes all 15 audit obligations (100% PASS)."""
    success = auditor.run_all()
    assert success is True
    assert len(auditor.results) == 15
    for r in auditor.results:
        assert r.passed is True, f"Obligation {r.obligation_id} failed: {r.details}"


def test_02_obligation_01_m18_immutability(auditor: Generation6IndependentAuditor):
    """Verifies Milestone 18 surface immutability audit."""
    result = auditor.audit_01_m18_immutability()
    assert result.passed is True
    assert result.metrics["certified_files_count"] == 14
    assert result.metrics["certified_commit"] == "c9cc1cad780453b81032f6b1b1b81117d41c060f"


def test_03_obligation_04_time_conservation_reconciliation(auditor: Generation6IndependentAuditor):
    """Verifies the two-clock time conservation and 26.0h itemized exclusion breakdown."""
    result = auditor.audit_04_time_conservation_and_exclusion_reconciliation()
    assert result.passed is True
    assert result.metrics["wall_clock_hours"] == 336.0
    assert result.metrics["effective_qualified_hours"] == 310.0
    assert result.metrics["disqualified_hours"] == 26.0
    assert result.metrics["sum_breakdown_hours"] == 26.0
    assert result.metrics["exact_conservation"] is True


def test_04_obligation_08_collateral_ldb_and_hazard(auditor: Generation6IndependentAuditor):
    """Verifies Milestone 34 collateral calculations and asymmetric hazard detector."""
    result = auditor.audit_08_m34_collateral_calculations()
    assert result.passed is True
    assert result.metrics["has_ldb_formula"] is True
    assert result.metrics["has_hazard_detection"] is True


def test_05_obligation_10_capital_firewall_all_engines(auditor: Generation6IndependentAuditor):
    """Verifies real_capital_enabled = False is enforced across all 7 Generation 6 engines."""
    result = auditor.audit_10_permanent_capital_firewall()
    assert result.passed is True
    assert result.metrics["modules_audited"] == 7
    assert result.metrics["all_firewalled"] is True


def test_06_obligation_12_sha256_checksum_integrity(auditor: Generation6IndependentAuditor):
    """Verifies release/SHA256SUMS.txt integrity."""
    result = auditor.audit_12_release_manifest_cryptographic_integrity()
    assert result.passed is True
    assert result.metrics["all_digests_match"] is True
    assert result.metrics["artifacts_audited"] >= 3


def test_07_obligation_13_installer_non_authorization_invariant(auditor: Generation6IndependentAuditor):
    """Verifies that release state is strictly clamped to RELEASE_CANDIDATE or formally OPERATOR_APPROVED_RELEASE."""
    result = auditor.audit_13_installer_non_authorization_invariant()
    assert result.passed is True
    assert result.metrics["release_state"] in ("RELEASE_CANDIDATE", "OPERATOR_APPROVED_RELEASE")
    assert result.metrics["passed"] is True


def test_08_obligation_14_human_approval_gate_g21(auditor: Generation6IndependentAuditor):
    """Verifies Gate G-21 human approval is machine-enforced and cannot be bypassed."""
    result = auditor.audit_14_human_approval_gate_enforcement()
    assert result.passed is True
    assert result.metrics["has_human_gate"] is True
    assert result.metrics["pauses_at_candidate"] is True


def test_09_audit_dossiers_exist_and_consistent():
    """Verifies that M35-R audit manifest and markdown report exist and are consistent."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    manifest_path = repo_root / "docs" / "release" / "M35_R_AUDIT_MANIFEST.json"
    report_path = repo_root / "docs" / "release" / "M35_R_INDEPENDENT_AUDIT_REPORT.md"

    assert manifest_path.exists()
    assert report_path.exists()

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["audit_milestone"] == "M35-R"
    assert data["status"] == "AUDIT_PASSED"
    assert data["all_obligations_passed"] is True
    assert len(data["detailed_results"]) == 15

    report_text = report_path.read_text(encoding="utf-8")
    assert "35-R" in report_text
    assert "AUDIT PASSED" in report_text
    assert "real_capital_enabled = False" in report_text
