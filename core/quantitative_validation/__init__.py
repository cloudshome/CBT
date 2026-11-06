"""
core/quantitative_validation
============================
Institutional Quantitative Strategy Validation & Statistical Evidence Engine.
Implements multi-layer quantitative evidence standards, progressive lifecycle
state machines, dependence-aware bootstrapping, and 3-tier friction stress.

Permanent Governance Invariant:
    REAL_CAPITAL_ENABLED = False
"""

from __future__ import annotations

REAL_CAPITAL_ENABLED: bool = False

try:
    from .auditor import (
        QuantitativeGate5Auditor,
        generate_audit_manifest,
    )
    from .cost_stress import (
        FrictionTier,
        apply_friction_stress,
        evaluate_cost_stress_decay,
    )
    from .metrics import (
        TradeReturn,
        calculate_block_bootstrap_ci,
        calculate_deflated_sharpe_ratio,
        calculate_drawdown_series,
        calculate_effective_sample_size,
        calculate_full_statistical_profile,
        calculate_net_expectancy,
        calculate_profit_factor,
        calculate_ulcer_index,
        calculate_wilson_win_rate_ci,
    )
    from .regime_attribution import (
        MarketRegime,
        classify_market_regime,
        decompose_regime_performance,
    )
    from .state_machine import (
        Gate5EvaluationResult,
        Gate5State,
        evaluate_gate5_lifecycle,
    )
    from .trade_quality import (
        NoTradeDecision,
        TradeQualityAssessment,
        evaluate_trade_quality,
    )
except ImportError:
    # Optional quantitative dependencies in minimal runtime environments
    pass

__all__ = [
    "REAL_CAPITAL_ENABLED",
    "FrictionTier",
    "Gate5EvaluationResult",
    "Gate5State",
    "MarketRegime",
    "NoTradeDecision",
    "QuantitativeGate5Auditor",
    "TradeQualityAssessment",
    "TradeReturn",
    "apply_friction_stress",
    "calculate_block_bootstrap_ci",
    "calculate_deflated_sharpe_ratio",
    "calculate_drawdown_series",
    "calculate_effective_sample_size",
    "calculate_full_statistical_profile",
    "calculate_net_expectancy",
    "calculate_profit_factor",
    "calculate_ulcer_index",
    "calculate_wilson_win_rate_ci",
    "classify_market_regime",
    "decompose_regime_performance",
    "evaluate_cost_stress_decay",
    "evaluate_gate5_lifecycle",
    "evaluate_trade_quality",
    "generate_audit_manifest",
]
