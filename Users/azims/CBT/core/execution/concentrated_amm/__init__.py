"""
core/execution/concentrated_amm/__init__.py
==========================================
Milestone 42: Concentrated Liquidity AMM Microstructure Engine (Uniswap v3 / v4).

Architectural Declaration:
--------------------------
M42 is strictly a microstructure simulation and quantitative research engine,
NOT an AMM execution engine. It does not move capital, sign transactions,
or dispatch calldata.
Permanent Capital Firewall: real_capital_enabled = False.
"""

from core.execution.concentrated_amm.tick_math import (
    FEE_TICK_SPACING_MAP,
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
    Q96,
    Q128,
    QUALIFICATION_MAX_PRICE_IMPACT_BPS,
    REAL_CAPITAL_ENABLED,
    evaluate_price_impact_constraint,
    get_amount0_delta,
    get_amount1_delta,
    get_next_sqrt_price_from_amount0_rounding_up,
    get_next_sqrt_price_from_amount1_rounding_down,
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
    is_valid_tick_for_spacing,
    nearest_valid_tick,
    price_to_sqrt_ratio_x96,
    price_to_tick,
    sqrt_ratio_x96_to_price,
    tick_to_price,
)

__all__ = [
    "REAL_CAPITAL_ENABLED",
    "QUALIFICATION_MAX_PRICE_IMPACT_BPS",
    "MIN_TICK",
    "MAX_TICK",
    "MIN_SQRT_RATIO",
    "MAX_SQRT_RATIO",
    "Q96",
    "Q128",
    "FEE_TICK_SPACING_MAP",
    "get_sqrt_ratio_at_tick",
    "get_tick_at_sqrt_ratio",
    "is_valid_tick_for_spacing",
    "nearest_valid_tick",
    "sqrt_ratio_x96_to_price",
    "price_to_sqrt_ratio_x96",
    "tick_to_price",
    "price_to_tick",
    "get_amount0_delta",
    "get_amount1_delta",
    "get_next_sqrt_price_from_amount0_rounding_up",
    "get_next_sqrt_price_from_amount1_rounding_down",
    "evaluate_price_impact_constraint",
]
