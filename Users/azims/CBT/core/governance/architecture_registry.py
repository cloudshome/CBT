"""
core/governance/architecture_registry.py
========================================
Machine-Enforced Architecture Contract & Authority Registry.

Defines the authoritative 4-Registry specification:
1. Layer Registry: Explicit stratification of all codebase modules (Layer 0 to 4).
2. Authority Registry: Execution Authority vs Simulation / Research vs Read-Only.
3. Dependency Allowlist: Mechanically verified import directionality rules.
4. Frozen Surface Registry: Milestone 18 cryptographic freeze boundary.

Core Guarantee:
---------------
A mechanically enforced zero-blast-radius architecture where physical file location,
dependency direction, execution authority, and certification status cannot silently diverge.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Final, List, Optional, Set, Tuple


class ArchitectureLayer(enum.IntEnum):
    """
    5-Tier Architecture Hierarchy.
    Strict Rule: Layer N may only import Layer <= N.
    Lower layers NEVER import higher layers.
    """
    LAYER_0_CONSTITUTION_RISK = 0  # Constitution, Risk desk, M18 certified execution freeze
    LAYER_1_MARKET_TELEMETRY = 1   # Order book feeds, bitwise tick math, VPIN, funding telemetry
    LAYER_2_QUANT_SIMULATION = 2   # Research, AMM simulation, cross-chain solvers, MM, RL, HRP
    LAYER_3_GATEWAY_API = 3        # FastAPI (app.py), Express server (src/), middleware, auth
    LAYER_4_PRESENTATION_UI = 4    # React Vite frontend, Electron desktop shell


class ModuleAuthority(enum.Enum):
    """
    Authoritative classification of what capability a module possesses.
    Guarantees research/simulation modules cannot gain execution authority.
    """
    CERTIFIED_EXECUTION_AUTHORITY = "CERTIFIED_EXECUTION_AUTHORITY"  # May dispatch orders via live connectors (M18 only)
    GOVERNANCE_RISK_AUTHORITY = "GOVERNANCE_RISK_AUTHORITY"          # Holds unbypassable risk sizing / kill-switch authority
    SIMULATION_RESEARCH_ONLY = "SIMULATION_RESEARCH_ONLY"            # Strictly zero capital authority (real_capital_enabled = False)
    READ_ONLY_TELEMETRY = "READ_ONLY_TELEMETRY"                      # Ingests market state, computes analytics, zero side-effects
    GATEWAY_ADAPTER = "GATEWAY_ADAPTER"                              # Optional network adapter / serialization bridge
    PRESENTATION_CLIENT = "PRESENTATION_CLIENT"                      # UI widgets, chart canvas, Electron shell


# ------------------------------------------------------------------------------
# 1. LAYER REGISTRY: Authoritative Mapping of Modules to Architecture Layers
# ------------------------------------------------------------------------------
MODULE_LAYER_RULES: Final[List[Tuple[str, ArchitectureLayer]]] = [
    # Layer 0: Constitution & Risk Primacy & M18 Certified Freeze & Core Invariants
    ("core.risk_engine", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.database", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.audit_bus", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.risk_manager", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.half_kelly_sizer", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.incident_escalation", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.api_health_guard", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.governance", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.auth", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.live_router", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.smart_order_router", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.reconciliation_ledger", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.almgren_chriss", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.idempotency", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.kill_switch", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.connectors", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.order_reconciliation", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.panic_close", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.protection_state_machine", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.protection", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.live_canary_runner", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution.account_probe", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.execution", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.portfolio_risk_matrix", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.causal_firewall", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.evidence_integrity", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.research_firewall", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.data_quality_gate", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),
    ("core.provenance_engine", ArchitectureLayer.LAYER_0_CONSTITUTION_RISK),

    # Layer 1: Market Telemetry & Microstructure Feeds
    ("core.market_providers", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.mbo", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.volatility", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.intelligence.synthetic_basis_engine", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.execution.concentrated_amm.tick_math", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.execution.concentrated_amm.swap_math", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),
    ("core.execution.concentrated_amm.tick_bitmap", ArchitectureLayer.LAYER_1_MARKET_TELEMETRY),

    # Layer 2: Quantitative Intelligence & Research Simulation (Zero Execution Authority)
    ("core.autonomous_auditor", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.autonomous_trader", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.shadow_burn_in_orchestrator", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.knowledge_os", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.youtube", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.youtube_extractor", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.concentrated_amm", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.cross_chain", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.market_making", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.latency_arb", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.rl_execution", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.cross_venue", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.liquidity_surface", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.mev_mitigation", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.testnet", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.execution.strategy_gateway", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.research", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.collective", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.sky_intelligence", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.kronos", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),
    ("core.arbitrage", ArchitectureLayer.LAYER_2_QUANT_SIMULATION),

    # Layer 3: Application APIs & Gateways & Alert Bots
    ("app", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("cbt_backend", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("src", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.terminal_routes", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.strategist_routes", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.heatmap_routes", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.knowledge_os.routes", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.telegram", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.telegram_bot", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.telegram_live_desk", ArchitectureLayer.LAYER_3_GATEWAY_API),
    ("core.whatsapp_bot", ArchitectureLayer.LAYER_3_GATEWAY_API),




    # Layer 4: Presentation & UI
    ("frontend", ArchitectureLayer.LAYER_4_PRESENTATION_UI),
    ("electron", ArchitectureLayer.LAYER_4_PRESENTATION_UI),
]


# ------------------------------------------------------------------------------
# 2. AUTHORITY REGISTRY: Modules Authorized to Influence Live Execution
# ------------------------------------------------------------------------------
MODULE_AUTHORITY_RULES: Final[List[Tuple[str, ModuleAuthority]]] = [
    # M18 Certified Live Execution Path & Live Connectors
    ("core.execution.live_router", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.smart_order_router", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.reconciliation_ledger", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.connectors", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.kill_switch", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.idempotency", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.order_reconciliation", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.panic_close", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.protection_state_machine", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.protection", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.live_canary_runner", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.account_probe", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution.almgren_chriss", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),
    ("core.execution", ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY),

    # Risk Primacy & Governance
    ("core.risk_engine", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),
    ("core.risk_manager", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),
    ("core.half_kelly_sizer", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),
    ("core.audit_bus", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),
    ("core.governance", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),
    ("core.auth", ModuleAuthority.GOVERNANCE_RISK_AUTHORITY),

    # Simulation & Research (Strictly ZERO live capital authority)
    ("core.execution.concentrated_amm", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.cross_chain", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.market_making", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.latency_arb", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.rl_execution", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.cross_venue", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.liquidity_surface", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.mev_mitigation", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.testnet", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.execution.strategy_gateway", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.research", ModuleAuthority.SIMULATION_RESEARCH_ONLY),
    ("core.collective", ModuleAuthority.SIMULATION_RESEARCH_ONLY),

    # Read-Only Telemetry
    ("core.mbo", ModuleAuthority.READ_ONLY_TELEMETRY),
    ("core.volatility", ModuleAuthority.READ_ONLY_TELEMETRY),
    ("core.kronos", ModuleAuthority.READ_ONLY_TELEMETRY),
    ("core.sky_intelligence", ModuleAuthority.READ_ONLY_TELEMETRY),
]


# ------------------------------------------------------------------------------
# 3. DEPENDENCY ALLOWLIST: Strict Layer Import Directionality
# ------------------------------------------------------------------------------
# Layer N may only import layers listed in its allowlist.
LAYER_DEPENDENCY_ALLOWLIST: Final[Dict[ArchitectureLayer, Set[ArchitectureLayer]]] = {
    ArchitectureLayer.LAYER_0_CONSTITUTION_RISK: {
        ArchitectureLayer.LAYER_0_CONSTITUTION_RISK,
        ArchitectureLayer.LAYER_1_MARKET_TELEMETRY,
    },
    ArchitectureLayer.LAYER_1_MARKET_TELEMETRY: {
        ArchitectureLayer.LAYER_0_CONSTITUTION_RISK,
        ArchitectureLayer.LAYER_1_MARKET_TELEMETRY,
    },
    ArchitectureLayer.LAYER_2_QUANT_SIMULATION: {
        ArchitectureLayer.LAYER_0_CONSTITUTION_RISK,
        ArchitectureLayer.LAYER_1_MARKET_TELEMETRY,
        ArchitectureLayer.LAYER_2_QUANT_SIMULATION,
    },
    ArchitectureLayer.LAYER_3_GATEWAY_API: {
        ArchitectureLayer.LAYER_0_CONSTITUTION_RISK,
        ArchitectureLayer.LAYER_1_MARKET_TELEMETRY,
        ArchitectureLayer.LAYER_2_QUANT_SIMULATION,
        ArchitectureLayer.LAYER_3_GATEWAY_API,
    },
    ArchitectureLayer.LAYER_4_PRESENTATION_UI: {
        ArchitectureLayer.LAYER_3_GATEWAY_API,
        ArchitectureLayer.LAYER_4_PRESENTATION_UI,
    },
}



# ------------------------------------------------------------------------------
# 4. EXPLICIT FORBIDDEN IMPORT COMBINATIONS (Architectural Firewall)
# ------------------------------------------------------------------------------
FORBIDDEN_IMPORT_PATTERNS: Final[List[Tuple[str, str, str]]] = [
    # (Source Module Pattern, Forbidden Target Pattern, Reason)
    ("core.risk_engine", "app", "Layer 0 Risk Desk cannot import Layer 3 Application Gateway"),
    ("core.risk_engine", "src", "Layer 0 Risk Desk cannot import Layer 3 Node Server"),
    ("core.risk_engine", "frontend", "Layer 0 Risk Desk cannot import Layer 4 Frontend"),
    ("core.research", "app", "Layer 2 Research cannot import Layer 3 Application Gateway"),
    ("core.research", "src", "Layer 2 Research cannot import Layer 3 Node Server"),
    ("core.execution.concentrated_amm", "app", "M42 Simulation cannot import Layer 3 Application Gateway"),
    ("core.execution.concentrated_amm", "core.execution.live_router", "M42 Simulation cannot import Live Execution Router"),
    ("core.execution.concentrated_amm", "core.execution.connectors", "M42 Simulation cannot import Live Venue Connectors"),
    ("core.execution.cross_chain", "core.execution.connectors", "M41 Intent Solvers cannot import Live Venue Connectors"),
    ("core.execution.cross_venue", "core.execution.live_router", "M43 Cross-Venue Routing cannot import Live Execution Router"),
    ("core.execution.cross_venue", "core.execution.connectors", "M43 Cross-Venue Routing cannot import Live Venue Connectors"),
    ("core", "frontend", "Backend Core modules cannot import Frontend UI components"),
]


# ------------------------------------------------------------------------------
# 5. EXPLICIT AUTHORIZED CROSS-LAYER EDGES
# ------------------------------------------------------------------------------
# Strictly documented cross-layer edges permitted for emergency circuit-breaking
# or asynchronous operational alerting without breaking architectural guarantees.
EXPLICIT_ALLOWED_EDGES: Final[Set[Tuple[str, str]]] = {
    # Layer 0 Emergency Auto-Halt: Incident escalation engine coordinates fail-closed halts
    # across live & paper trading loops upon critical risk breach
    ("core.incident_escalation", "core.autonomous_auditor"),
    ("core.incident_escalation", "core.autonomous_trader"),
    ("core.incident_escalation", "core.shadow_burn_in_orchestrator"),
    ("core.incident_escalation", "core.telegram_bot"),
    # Layer 2 Async Progress Alerting: Research automation & YouTube extraction send progress updates & track async jobs
    ("core.knowledge_os.research_automation_orchestrator", "core.telegram_bot"),
    ("core.youtube.agent", "core.telegram.jobs"),
    ("core.youtube.agent", "core.telegram_bot"),
}


def resolve_module_layer(module_name: str) -> ArchitectureLayer:
    """Resolves which architecture layer a module path belongs to."""
    # Match longest prefix first
    matched_layer = ArchitectureLayer.LAYER_2_QUANT_SIMULATION  # default fallback for core
    longest_prefix_len = 0

    for prefix, layer in MODULE_LAYER_RULES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            if len(prefix) > longest_prefix_len:
                longest_prefix_len = len(prefix)
                matched_layer = layer

    return matched_layer


def resolve_module_authority(module_name: str) -> ModuleAuthority:
    """Resolves execution authority classification for a module."""
    matched_auth = ModuleAuthority.SIMULATION_RESEARCH_ONLY
    longest_prefix_len = 0

    for prefix, auth in MODULE_AUTHORITY_RULES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            if len(prefix) > longest_prefix_len:
                longest_prefix_len = len(prefix)
                matched_auth = auth

    return matched_auth


def validate_import_direction(source_module: str, target_module: str) -> Tuple[bool, Optional[str]]:
    """
    Mechanically validates whether source_module is permitted to import target_module.
    Returns (is_valid, violation_reason).
    """
    # 1. Check explicit forbidden patterns
    for src_pat, tgt_pat, reason in FORBIDDEN_IMPORT_PATTERNS:
        if (source_module == src_pat or source_module.startswith(src_pat + ".")) and (
            target_module == tgt_pat or target_module.startswith(tgt_pat + ".")
        ):
            return False, f"ARCHITECTURAL FIREWALL VIOLATION: {reason} ({source_module} -> {target_module})"

    # 2. Check explicit authorized cross-layer edges (emergency circuit-breakers / alerting)
    if (source_module, target_module) in EXPLICIT_ALLOWED_EDGES:
        return True, None

    # 3. Check Layer allowlist
    source_layer = resolve_module_layer(source_module)
    target_layer = resolve_module_layer(target_module)


    allowed_target_layers = LAYER_DEPENDENCY_ALLOWLIST.get(source_layer, set())
    if target_layer not in allowed_target_layers:
        return (
            False,
            f"STRATIFICATION VIOLATION: Layer {source_layer.value} ({source_layer.name}) "
            f"is forbidden from importing Layer {target_layer.value} ({target_layer.name}). "
            f"Culprit: {source_module} -> {target_module}",
        )

    # 3. Check Authority isolation: Simulation modules cannot import execution authority internals
    source_auth = resolve_module_authority(source_module)
    target_auth = resolve_module_authority(target_module)

    if source_auth == ModuleAuthority.SIMULATION_RESEARCH_ONLY and target_auth == ModuleAuthority.CERTIFIED_EXECUTION_AUTHORITY:
        # Simulation modules may only access read-only constants or DTOs, never live connector execution
        if "connectors" in target_module or "live_router" in target_module:
            return (
                False,
                f"AUTHORITY ISOLATION VIOLATION: Simulation module '{source_module}' "
                f"attempted to import live execution authority '{target_module}'.",
            )

    return True, None
