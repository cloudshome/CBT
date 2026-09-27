"""
core/execution/strategy_gateway/strategies/__init__.py
======================================================
Strategy signal compilers and institutional adapters for Milestone 24/25.
Adapts research-grade models (Kronos Grade-E3, SMC Order Flow) into deterministic
execution proposals obeying causal firewalls and governance boundaries.
"""

from __future__ import annotations

from core.execution.strategy_gateway.strategies.kronos_adapter import (
    KronosForecastSignal,
    KronosStrategyAdapter,
)
from core.execution.strategy_gateway.strategies.smc_adapter import (
    SMCOrderFlowSignal,
    SMCStrategyAdapter,
)

__all__ = [
    "KronosForecastSignal",
    "KronosStrategyAdapter",
    "SMCOrderFlowSignal",
    "SMCStrategyAdapter",
]
