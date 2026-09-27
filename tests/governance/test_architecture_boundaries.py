"""
tests/governance/test_architecture_boundaries.py
================================================
Machine-Enforced Architectural Stratification & Boundary Compliance Tests.

Validates:
1. Entire codebase (514+ Python files, 4300+ internal imports) produces 0 boundary violations.
2. Layer Stratification invariant: Layer N can only import Layer <= N.
3. Authority Isolation: Simulation/Research modules have strictly zero execution authority
   and cannot import live venue connectors or live order routers.
4. Forbidden import patterns fail-closed.
5. Frozen M18 execution surface is strictly classified and protected.
"""

from pathlib import Path
import pytest

from core.governance.architecture_registry import (
    ArchitectureLayer,
    ModuleAuthority,
    LAYER_DEPENDENCY_ALLOWLIST,
    FORBIDDEN_IMPORT_PATTERNS,
    EXPLICIT_ALLOWED_EDGES,
    resolve_module_layer,
    resolve_module_authority,
    validate_import_direction,
)
from scripts.verify_architecture_boundaries import run_architecture_boundary_verification


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_entire_codebase_boundary_compliance(repo_root: Path):
    """
    Verifies that all Python modules across the repository adhere strictly to
    the 4-Registry Architecture Contract with zero AST import violations.
    """
    is_compliant, violations, scanned_files, scanned_imports = run_architecture_boundary_verification(repo_root)

    violation_report = "\n".join(
        f"  - [{v.file_path}:{v.line_number}] {v.source_module} -> {v.target_module}: {v.reason}"
        for v in violations
    )

    assert is_compliant, f"Detected {len(violations)} architectural boundary violations across {scanned_files} files:\n{violation_report}"
    assert len(violations) == 0
    assert scanned_files >= 500
    assert scanned_imports >= 4000


def test_layer_stratification_rules():
    """Verifies the directional allowlist rules for each architectural layer."""
    # Layer 0 (Risk/Constitution) cannot import Layer 2, 3, or 4
    l0_allowed = LAYER_DEPENDENCY_ALLOWLIST[ArchitectureLayer.LAYER_0_CONSTITUTION_RISK]
    assert ArchitectureLayer.LAYER_2_QUANT_SIMULATION not in l0_allowed
    assert ArchitectureLayer.LAYER_3_GATEWAY_API not in l0_allowed
    assert ArchitectureLayer.LAYER_4_PRESENTATION_UI not in l0_allowed

    # Layer 2 (Quant Simulation) cannot import Layer 3 or 4
    l2_allowed = LAYER_DEPENDENCY_ALLOWLIST[ArchitectureLayer.LAYER_2_QUANT_SIMULATION]
    assert ArchitectureLayer.LAYER_3_GATEWAY_API not in l2_allowed
    assert ArchitectureLayer.LAYER_4_PRESENTATION_UI not in l2_allowed

    # Layer 3 (Gateway API) cannot import Layer 4 (UI)
    l3_allowed = LAYER_DEPENDENCY_ALLOWLIST[ArchitectureLayer.LAYER_3_GATEWAY_API]
    assert ArchitectureLayer.LAYER_4_PRESENTATION_UI not in l3_allowed


def test_authority_isolation_resolution():
    """Verifies authority classification resolution for key modules."""
    # M18 Certified Live Router has Certified Execution Authority
    assert resolve_module_authority("core.execution.live_router") == ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY
    assert resolve_module_authority("core.execution.connectors.binance_connector") == ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY

    # Risk Engine has Governance Risk Authority
    assert resolve_module_authority("core.risk_engine") == ModuleAuthority.GOVERNANCE_RISK_AUTHORITY
    assert resolve_module_authority("core.half_kelly_sizer") == ModuleAuthority.GOVERNANCE_RISK_AUTHORITY

    # M42 Concentrated AMM & M41 Cross Chain are strictly Simulation/Research Only
    assert resolve_module_authority("core.execution.concentrated_amm") == ModuleAuthority.SIMULATION_RESEARCH_ONLY
    assert resolve_module_authority("core.execution.cross_chain") == ModuleAuthority.SIMULATION_RESEARCH_ONLY
    assert resolve_module_authority("core.research.walk_forward") == ModuleAuthority.SIMULATION_RESEARCH_ONLY


def test_forbidden_import_rejection():
    """Verifies that attempt to import live execution or gateways from simulation is blocked."""
    # Simulation attempting to import live execution router
    is_valid, reason = validate_import_direction(
        "core.execution.concentrated_amm.swap_engine",
        "core.execution.live_router",
    )
    assert not is_valid
    assert "Live Execution Router" in reason or "AUTHORITY ISOLATION" in reason

    # Simulation attempting to import live venue connectors
    is_valid, reason = validate_import_direction(
        "core.execution.cross_chain.solver",
        "core.execution.connectors.binance_connector",
    )
    assert not is_valid
    assert "Live Venue Connectors" in reason or "AUTHORITY ISOLATION" in reason

    # Risk Engine attempting to import FastAPI app
    is_valid, reason = validate_import_direction(
        "core.risk_engine",
        "app",
    )
    assert not is_valid
    assert "Application Gateway" in reason or "STRATIFICATION" in reason


def test_explicit_allowed_edges():
    """Verifies explicit authorized cross-layer edges (emergency circuit breaker & alerts)."""
    assert ("core.incident_escalation", "core.autonomous_trader") in EXPLICIT_ALLOWED_EDGES
    assert ("core.incident_escalation", "core.shadow_burn_in_orchestrator") in EXPLICIT_ALLOWED_EDGES
    assert ("core.incident_escalation", "core.autonomous_auditor") in EXPLICIT_ALLOWED_EDGES

    # Validate that these edges pass validation
    is_valid, reason = validate_import_direction("core.incident_escalation", "core.autonomous_trader")
    assert is_valid
    assert reason is None
