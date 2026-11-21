"""tests/test_m74_active_surface_and_alignment.py — Milestone 74 Active Surface & Architecture Alignment Tests.

Verifies:
1. active_surface_manifest.json schema and disk existence of all ACTIVE_PRODUCTION and RESEARCH_LAB files.
2. scripts/audit_active_surface.py passes cleanly with exit code 0.
3. Governance invariants (REAL_CAPITAL_ENABLED=False & CAPITAL_MODE="TIER_0_PAPER") across operational modules.
4. STATIC_FALSIFIED_RECORDS contains FALSIFIED_M63, FALSIFIED_M67, and FALSIFIED_M72.
5. docs/architecture/ACTIVE_PRODUCTION_ARCHITECTURE.md exists and contains canonical architectural terms.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "core" / "governance" / "active_surface_manifest.json"
ARCH_DOC_PATH = ROOT / "docs" / "architecture" / "ACTIVE_PRODUCTION_ARCHITECTURE.md"


def test_manifest_schema_and_files_exist():
    """Assert active_surface_manifest.json is valid and every registered file exists."""
    assert MANIFEST_PATH.exists(), f"Missing manifest: {MANIFEST_PATH}"
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest.get("schema_version") == "1.0.0" or manifest.get("MANIFEST_VERSION") == "1.0.0"
    assert manifest.get("milestone") == "M74" or manifest.get("MILESTONE") == "M74"
    assert "TIERS" in manifest

    tiers = manifest["TIERS"]
    assert "ACTIVE_PRODUCTION" in tiers
    assert "RESEARCH_LAB" in tiers
    assert "CERTIFIED_PROTECTED" in tiers
    assert "LEGACY_QUARANTINED" in tiers

    # Check ACTIVE_PRODUCTION files
    active_files = tiers["ACTIVE_PRODUCTION"].get("files", [])
    assert len(active_files) >= 15, f"Expected at least 15 active production files, found {len(active_files)}"
    for item in active_files:
        rel_path = item.get("path") if isinstance(item, dict) else item
        full_path = ROOT / rel_path
        assert full_path.exists(), f"ACTIVE_PRODUCTION file missing on disk: {rel_path}"

    # Check RESEARCH_LAB files
    lab_files = tiers["RESEARCH_LAB"].get("files", [])
    assert len(lab_files) >= 5, f"Expected at least 5 research lab files, found {len(lab_files)}"
    for item in lab_files:
        rel_path = item.get("path") if isinstance(item, dict) else item
        full_path = ROOT / rel_path
        assert full_path.exists(), f"RESEARCH_LAB file missing on disk: {rel_path}"


def test_audit_script_passes():
    """Assert scripts/audit_active_surface.py executes and exits with code 0."""
    audit_script = ROOT / "scripts" / "audit_active_surface.py"
    assert audit_script.exists()

    result = subprocess.run(
        [sys.executable, str(audit_script)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"audit_active_surface.py failed with returncode {result.returncode}.\n"
        f"Stdout: {result.stdout}\n"
        f"Stderr: {result.stderr}"
    )
    assert "[SUCCESS] ACTIVE SURFACE AUDIT PASSED" in result.stdout


def test_governance_invariants_across_operational_modules():
    """Assert REAL_CAPITAL_ENABLED is False and CAPITAL_MODE is 'TIER_0_PAPER' across all 4 operational modules."""
    import core.ops.market_radar as radar
    import core.ops.p2_shadow_watchdog as watchdog
    import core.strategies.p2_risk_parity as p2_rp
    import core.strategies.p2_shadow_runner as runner

    modules = [p2_rp, runner, watchdog, radar]
    for mod in modules:
        mod_name = mod.__name__
        assert hasattr(mod, "REAL_CAPITAL_ENABLED"), f"{mod_name} missing REAL_CAPITAL_ENABLED"
        assert mod.REAL_CAPITAL_ENABLED is False, f"{mod_name}.REAL_CAPITAL_ENABLED must be False"

        assert hasattr(mod, "CAPITAL_MODE"), f"{mod_name} missing CAPITAL_MODE"
        assert mod.CAPITAL_MODE == "TIER_0_PAPER", f"{mod_name}.CAPITAL_MODE must be 'TIER_0_PAPER'"


def test_failure_memory_contains_canonical_records():
    """Assert failure memory contains all three canonical falsification records (M63, M67, M72)."""
    from core.autonomous_research.failure_memory import STATIC_FALSIFIED_RECORDS

    record_ids = {r.failure_id for r in STATIC_FALSIFIED_RECORDS}
    expected_ids = {"FALSIFIED_M63", "FALSIFIED_M67", "FALSIFIED_M72"}

    for eid in expected_ids:
        assert eid in record_ids, f"Expected {eid} in STATIC_FALSIFIED_RECORDS, found {record_ids}"


def test_active_production_architecture_documentation():
    """Assert docs/architecture/ACTIVE_PRODUCTION_ARCHITECTURE.md exists and contains required canonical terms."""
    assert ARCH_DOC_PATH.exists(), f"Architecture doc missing: {ARCH_DOC_PATH}"
    content = ARCH_DOC_PATH.read_text(encoding="utf-8")

    assert "TIER_0_PAPER" in content
    assert "FALSIFIED_M72" in content
    assert "market_radar.py" in content
    assert "p2_shadow_runner.py" in content
    assert "p2_shadow_watchdog.py" in content
    assert "active_surface_manifest.json" in content
