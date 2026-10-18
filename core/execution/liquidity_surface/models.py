"""
core/execution/liquidity_surface/models.py
=========================================
Data Transfer Objects and Enums for Milestone 44:
Liquidity Surface Geometry & High-Frequency Toxic Flow Analytics.

All data structures are immutable, statically typed, and strictly isolated
under simulation constraints (real_capital_enabled = False).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ToxicityRegime(enum.StrEnum):
    """Classification of order flow toxicity based on VPIN and adverse selection hazard."""

    BENIGN = "BENIGN"  # VPIN < 0.35: Retail/Noise-dominated flow
    MODERATE = "MODERATE"  # 0.35 <= VPIN < 0.65: Normal balanced market
    TOXIC = "TOXIC"  # 0.65 <= VPIN < 0.85: Informed flow burst
    EXTREME_ADVERSE = "EXTREME_ADVERSE"  # VPIN >= 0.85: Toxic inventory cascade / predatory sweep


class ExecutionUrgency(enum.StrEnum):
    """Prescribed execution urgency under dynamic surface geometry."""

    PASSIVE_POST_ONLY = "PASSIVE_POST_ONLY"  # Route exclusively as maker to capture toxic spread
    NORMAL_SCHEDULED = "NORMAL_SCHEDULED"  # Standard TWAP / VWAP execution
    AGGRESSIVE_IMMEDIATE = "AGGRESSIVE_IMMEDIATE"  # Urgent taker fill (only when flow is benign)


@dataclass(frozen=True)
class LiquiditySurfacePoint:
    """Represents a discrete coordinate on the empirical order book liquidity surface."""

    price: float
    depth_size: float
    cumulative_volume: float
    marginal_impact_bps: float
    delta_t_ms: float = 0.0


@dataclass(frozen=True)
class OrderBookSurfaceSnapshot:
    """Multi-dimensional order book surface state across depth and arrival intervals."""

    symbol: str
    timestamp_ms: int
    mid_price: float
    bid_surface: list[LiquiditySurfacePoint]
    ask_surface: list[LiquiditySurfacePoint]
    spread_bps: float
    total_depth_usd: float
    real_capital_enabled: bool = False


@dataclass(frozen=True)
class ToxicFlowAssessment:
    """High-frequency microstructure toxicity and informed trading assessment."""

    symbol: str
    timestamp_ms: int
    vpin: float
    regime: ToxicityRegime
    hawkes_intensity: float
    adverse_selection_risk: float
    is_toxic: bool
    recommended_action: str
    real_capital_enabled: bool = False


@dataclass(frozen=True)
class SurfaceCurveParams:
    """Parametric curve coefficients fitted to empirical order book depth."""

    kyles_lambda: float  # Kyle's Lambda (Price impact per unit volume)
    square_root_alpha: float  # Square-root law constant: I = alpha * sigma * sqrt(Q/V)
    permanent_impact_fraction: float  # Fraction of price displacement persisting (0.0 to 1.0)
    r_squared: float  # Goodness-of-fit metric (0.0 to 1.0)


@dataclass(frozen=True)
class ProtectiveExecutionAdjustment:
    """Risk-governed sizing and routing guidance output by Surface Sentinel."""

    symbol: str
    original_notional_usd: float
    adjusted_notional_usd: float
    urgency: ExecutionUrgency
    dark_pool_allocation_pct: float
    max_slippage_ceiling_bps: float
    kelly_fraction: float
    reason: str
    is_halted: bool = False
    real_capital_enabled: bool = False
