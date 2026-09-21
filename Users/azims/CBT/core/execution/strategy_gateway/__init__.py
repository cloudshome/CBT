"""
core/execution/strategy_gateway/__init__.py
===========================================
Milestone 24: Institutional Execution-Readiness Qualification Gateway.

Provides the 4-stage governance pipeline separating probabilistic research
forecasting from tradable, risk-governed execution intents:
Stage 1: Research Eligibility & Provenance Authority (research_eligibility.py)
Stage 2: Deterministic Strategy Compiler (strategy_compiler.py)
Stage 3: Execution Feasibility & Friction Modeling (execution_feasibility.py)
Stage 4: Multi-Ceiling Position Sizing & Intent Construction (intent_builder.py)
Supported by:
- Telemetry: Real-Time TCA Bridge & Non-Adaptive Markout Engine (tca_bridge.py)
- Dispatch: Guarded Strategy-to-Flight Execution Router (gateway_router.py)
"""

from __future__ import annotations

# Permanent capital firewall assertion
REAL_CAPITAL_ENABLED: bool = False
