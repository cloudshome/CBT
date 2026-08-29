"""
SKY Market Intelligence Engine — Strongly Typed Data Contracts & Schemas.
Implements immutable, timestamped, verifiable data structures for SMC, Market Structure,
Liquidity, Volume, Volatility, Derivatives, Regimes, Setups, and Empirical Expectancy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class StructureEventType(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH_BULLISH = "CHOCH_BULLISH"
    CHOCH_BEARISH = "CHOCH_BEARISH"
    MSS_BULLISH = "MSS_BULLISH"
    MSS_BEARISH = "MSS_BEARISH"
    FAILED_BREAKOUT_BULLISH = "FAILED_BREAKOUT_BULLISH"
    FAILED_BREAKOUT_BEARISH = "FAILED_BREAKOUT_BEARISH"
    STRUCTURE_RECLAIM = "STRUCTURE_RECLAIM"
    STRUCTURE_FAILURE = "STRUCTURE_FAILURE"


class LiquidityPoolType(str, Enum):
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    PREVIOUS_DAY_HIGH = "PREVIOUS_DAY_HIGH"
    PREVIOUS_DAY_LOW = "PREVIOUS_DAY_LOW"
    PREVIOUS_WEEK_HIGH = "PREVIOUS_WEEK_HIGH"
    PREVIOUS_WEEK_LOW = "PREVIOUS_WEEK_LOW"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    RANGE_HIGH = "RANGE_HIGH"
    RANGE_LOW = "RANGE_LOW"


class FVGType(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class FVGStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


class OrderBlockType(str, Enum):
    CANDIDATE_BULLISH_OB = "CANDIDATE_BULLISH_OB"
    CANDIDATE_BEARISH_OB = "CANDIDATE_BEARISH_OB"


class VolatilityRegime(str, Enum):
    LOW_VOLATILITY = "LOW_VOLATILITY"
    NORMAL_VOLATILITY = "NORMAL_VOLATILITY"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"


class MarketRegimeType(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING_CONSOLIDATION = "RANGING_CONSOLIDATION"
    VOLATILE_EXPANSION = "VOLATILE_EXPANSION"
    COMPRESSION_SQUEEZE = "COMPRESSION_SQUEEZE"
    MEAN_REVERTING = "MEAN_REVERTING"
    UNSTABLE = "UNSTABLE"


class SetupType(str, Enum):
    SETUP_A_SWEEP_MSS = "SETUP_A_SWEEP_MSS"
    SETUP_B_PULLBACK_FVG = "SETUP_B_PULLBACK_FVG"
    SETUP_C_BREAKOUT_EXPANSION = "SETUP_C_BREAKOUT_EXPANSION"
    SETUP_D_RANGE_SWEEP_RECLAIM = "SETUP_D_RANGE_SWEEP_RECLAIM"
    SETUP_E_VWAP_RECLAIM = "SETUP_E_VWAP_RECLAIM"


class DecisionAction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class SwingPoint:
    index: int
    timestamp: int
    swing_type: SwingType
    price: float
    timeframe: str
    is_confirmed: bool = True
    confirmation_index: Optional[int] = None
    confirmation_timestamp: Optional[int] = None


@dataclass(frozen=True)
class StructureEvent:
    event_type: StructureEventType
    timeframe: str
    event_timestamp: int
    confirmation_timestamp: int
    price: float
    broken_level: float
    displacement_atr: float
    strength_score: float                # [0.0, 1.0]
    confirmation_status: str             # "CONFIRMED", "PENDING", "FAILED"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiquidityPool:
    pool_type: LiquidityPoolType
    symbol: str
    timeframe: str
    price_level: float
    top_boundary: float
    bottom_boundary: float
    creation_timestamp: int
    retest_count: int
    volume_depth: float
    is_active: bool = True


@dataclass(frozen=True)
class LiquiditySweep:
    pool_type: LiquidityPoolType
    symbol: str
    timeframe: str
    sweep_timestamp: int
    swept_level: float
    extreme_price: float
    penetration_distance: float
    penetration_atr_ratio: float
    rejection_distance: float
    wick_to_body_ratio: float
    volume_delta: float
    subsequent_displacement_score: float
    is_valid_reclaim: bool
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FVGFeature:
    fvg_type: FVGType
    symbol: str
    timeframe: str
    creation_timestamp: int
    creation_index: int
    top_price: float
    bottom_price: float
    mid_price: float
    gap_size: float
    size_atr_ratio: float
    status: FVGStatus = FVGStatus.ACTIVE
    age_bars: int = 0
    fill_percentage: float = 0.0
    reaction_strength: float = 0.0
    conditional_expectancy_r: float = 0.50
    invalidation_level: float = 0.0


@dataclass
class CandidateOrderBlock:
    ob_type: OrderBlockType
    symbol: str
    timeframe: str
    origin_timestamp: int
    origin_index: int
    zone_high: float
    zone_low: float
    origin_candle: Dict[str, float]
    post_origin_displacement_atr: float
    volume_expansion_ratio: float
    distance_to_liquidity: float
    retest_count: int = 0
    is_mitigated: bool = False
    is_invalidated: bool = False
    expectancy_score: float = 0.50


@dataclass(frozen=True)
class DisplacementFeature:
    candle_index: int
    timestamp: int
    direction: str                       # "BULLISH", "BEARISH", "NEUTRAL"
    body_atr_ratio: float
    range_atr_ratio: float
    consecutive_directional_bars: int
    volume_expansion_ratio: float
    price_velocity: float
    breakout_distance: float
    close_location_in_range: float       # [0.0, 1.0]
    displacement_score: float            # [0.0, 100.0]


@dataclass(frozen=True)
class VolumeFeature:
    timestamp: int
    volume: float
    relative_volume: float               # rVol = V / SMA(V, 20)
    volume_ma: float
    is_expanding: bool
    is_contracting: bool
    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_volume_delta: float
    source_exchange: str = "binance_futures"


@dataclass(frozen=True)
class VolatilityState:
    timestamp: int
    atr: float
    atr_percentile: float                # [0.0, 1.0] (rolling 100-bar)
    realized_volatility: float
    regime: VolatilityRegime
    is_expanding: bool
    is_contracting: bool


@dataclass(frozen=True)
class VWAPFeature:
    timestamp: int
    vwap: float
    upper_band_1sigma: float
    lower_band_1sigma: float
    upper_band_2sigma: float
    lower_band_2sigma: float
    std_dev: float
    deviation_sigmas: float              # (price - vwap) / std_dev
    is_above_vwap: bool
    is_extended_overbought: bool         # deviation > +2.0 sigma
    is_extended_oversold: bool           # deviation < -2.0 sigma
    is_reclaiming: bool
    mean_reversion_prob: float           # [0.0, 1.0]
    anchored_vwap: Optional[float] = None



@dataclass(frozen=True)
class DerivativesState:
    timestamp: int
    open_interest: float
    oi_change_pct: float
    oi_velocity: float
    price_vs_oi_state: str               # "LONG_EXPANSION", "SHORT_SQUEEZE", "SHORT_EXPANSION", "LONG_LIQUIDATION"
    funding_rate: float
    funding_percentile: float
    funding_zscore: float
    is_funding_extreme: bool
    long_liquidations_usd: float
    short_liquidations_usd: float
    liquidation_spike_detected: bool
    basis_premium_annualized_pct: float


@dataclass(frozen=True)
class MultiTimeframeContext:
    timestamp: int
    htf_1d_trend: str
    htf_4h_trend: str
    mtf_1h_state: str
    mtf_15m_state: str
    ltf_5m_trigger: str
    ltf_1m_trigger: str
    confluence_score: float              # [0.0, 100.0]
    stack_alignment: str                 # "BULLISH_CONFLUENT", "BEARISH_CONFLUENT", "MIXED_CONFLICT"


@dataclass(frozen=True)
class MarketRegimeState:
    timestamp: int
    regime_type: MarketRegimeType
    confidence: float                    # [0.0, 1.0]
    trend_strength_adx: float
    volatility_state: VolatilityRegime
    is_mean_reverting: bool
    key_characteristics: List[str] = field(default_factory=list)


@dataclass
class SKYSetup:
    setup_type: SetupType
    direction: DecisionAction
    symbol: str
    trigger_timeframe: str
    timestamp: int
    entry_price: float
    invalidation_sl: float
    target_tp: float
    risk_reward_ratio: float
    displacement_score: float
    regime: MarketRegimeType
    historical_expectancy_r: float
    historical_win_rate: float
    historical_sample_size: int
    confluence_score: float
    is_qualified: bool
    rejection_reasons: List[str] = field(default_factory=list)
    feature_snapshot: Dict[str, Any] = field(default_factory=dict)
    explanation_text: str = ""


@dataclass(frozen=True)
class ExpectancyRecord:
    concept_name: str
    regime: str
    timeframe: str
    sample_size: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    median_r: float
    profit_factor: float
    max_drawdown_r: float
    sharpe_ratio: float
    sortino_ratio: float
    max_adverse_excursion_mean_r: float
    max_favorable_excursion_mean_r: float


@dataclass(frozen=True)
class AblationResult:
    feature_combination: str
    sample_size: int
    expectancy_r: float
    win_rate: float
    profit_factor: float
    delta_expectancy_vs_baseline: float
    is_statistically_significant: bool


@dataclass(frozen=True)
class DecisionOutput:
    decision: DecisionAction
    symbol: str
    timestamp: int
    setup_qualified: Optional[SKYSetup]
    net_ev_r: float
    kelly_fraction: float
    suggested_position_size_usd: float
    risk_gate_passed: bool
    explanation_dossier: Dict[str, Any]
    no_trade_reason: Optional[str] = None
