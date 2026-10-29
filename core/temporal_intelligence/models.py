"""
core/temporal_intelligence/models.py
====================================
Data contracts and schemas for the Temporal Price-Action Intelligence & Mathematical Law Discovery Engine (Milestone 22).

Enforces:
- Point-in-time feature representation with zero lookahead.
- Explicit forecast horizons matched to dataset resolution (15m, 30m, 1h, 2h).
- Discrete ternary probability distribution: P(Pump) + P(Dump) + P(Range) = 1.0.
- Out-of-sample Brier Skill Score (BSS) relative to unconditioned base rate.
- 3-tier friction modeling (Base: 14 bps, Conservative: 24 bps, Stress: 40 bps).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ForecastHorizon(StrEnum):
    H_15M = "15m"  # 1 bar
    H_30M = "30m"  # 2 bars
    H_1H = "1h"    # 4 bars
    H_2H = "2h"    # 8 bars


class PriceActionLawStatus(StrEnum):
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FrictionScenario(StrEnum):
    BASE = "BASE"                  # 5 bps fee + 2 bps slippage per side = 14 bps round-trip
    CONSERVATIVE = "CONSERVATIVE"  # 7 bps fee + 5 bps slippage per side = 24 bps round-trip
    STRESS = "STRESS"              # 10 bps fee + 10 bps slippage per side = 40 bps round-trip


class TemporalFeatureVector(BaseModel):
    """Point-in-time observable features at candle close timestamp t."""

    timestamp_ms: int
    symbol: str
    reference_price: float
    return_1bar_pct: float          # 15m return
    return_2bar_pct: float          # 30m return
    return_4bar_pct: float          # 1h return
    relative_volume: float          # Volume_t / SMA(Volume, 20)
    volatility_ratio: float         # Bar Range / ATR(14)
    body_to_range_ratio: float      # abs(Close - Open) / (High - Low)
    upper_wick_ratio: float         # (High - max(Open, Close)) / (High - Low)
    lower_wick_ratio: float         # (min(Open, Close) - Low) / (High - Low)
    distance_to_swing_high_pct: float  # (High_20 - Close) / Close * 100
    distance_to_swing_low_pct: float   # (Close - Low_20) / Close * 100
    is_out_of_distribution: bool = False


class PriceActionLaw(BaseModel):
    """Discovered conditional mathematical relationship with out-of-sample evidence."""

    law_id: str
    name: str
    description: str
    condition_expr: str
    target_horizon: ForecastHorizon
    movement_threshold_pct: float
    # In-sample discovery statistics
    sample_size_train: int
    effective_sample_size_train: float
    base_rate_pump_pct: float
    conditional_pump_pct_train: float
    lift_train: float
    p_value: float
    adjusted_p_value_fdr: float
    # Sealed out-of-sample validation statistics
    sample_size_test: int
    conditional_pump_pct_test: float
    lift_test: float
    brier_score_test: float
    brier_skill_score_test: float  # 1 - (BS_model / BS_baseline)
    # Economic viability under 3-tier friction
    net_expectancy_r_base: float
    net_expectancy_r_conservative: float
    net_expectancy_r_stress: float
    status: PriceActionLawStatus
    rejection_reason: str | None = None


class TemporalForecastPayload(BaseModel):
    """Ternary probabilistic forecast and barrier-crossing path model."""

    forecast_id: str
    timestamp_ms: int
    symbol: str
    reference_price: float
    horizon: ForecastHorizon
    movement_threshold_pct: float
    # Directional probabilities (sum to 1.0)
    prob_pump: float
    prob_dump: float
    prob_range: float
    # First-barrier crossing probabilities (sum to 1.0)
    prob_hit_upper_barrier_first: float
    prob_hit_lower_barrier_first: float
    prob_neither_barrier_hit: float
    # Performance & calibration metrics
    expected_return_pct: float
    brier_skill_score: float
    epistemic_uncertainty: float
    active_law_ids: list[str]
    model_version: str = "temporal_v1.0.0"
    resolution_status: str = "PENDING"


class TraderQueryEvaluation(BaseModel):
    """Interactive response to a trader's conditional price action scenario query."""

    query_summary: str
    symbol: str
    historical_matches_count: int
    effective_sample_size: float
    prob_continuation_pump: float
    prob_reversal_dump: float
    prob_range_chop: float
    mean_realized_return_pct: float
    median_realized_return_pct: float
    net_profit_after_base_friction_pct: float
    evidence_status: PriceActionLawStatus
    verdict: str
