"""
core/arbitrage/models.py
========================
Institutional data models, enums, and schemas for Task 20.1:
Cross-Exchange Arbitrage & Funding Dislocation Sentinel.

Structural Safety Invariant:
- Operates under ArbitrageExecutionPermission.RESEARCH_ONLY.
- No live execution methods or parameters exist in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ArbitrageExecutionPermission(StrEnum):
    """Structural research-only guard. Live execution is impossible through this system."""

    RESEARCH_ONLY = "RESEARCH_ONLY"


class Venue(StrEnum):
    BINANCE_SPOT = "BINANCE_SPOT"
    BINANCE_PERP = "BINANCE_PERP"
    BYBIT_LINEAR = "BYBIT_LINEAR"
    OKX_PERP = "OKX_PERP"
    OKX_SPOT = "OKX_SPOT"


class MarketType(StrEnum):
    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"


class ContractType(StrEnum):
    SPOT = "SPOT"
    LINEAR = "LINEAR"
    INVERSE = "INVERSE"


class SourceHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DEAD = "DEAD"


class OpportunityType(StrEnum):
    SPOT_PERP_BASIS = "SPOT_PERP_BASIS"
    CROSS_VENUE_PERP = "CROSS_VENUE_PERP"
    FUNDING_RATE_DIVERGENCE = "FUNDING_RATE_DIVERGENCE"
    TRIANGULAR_DISLOCATION = "TRIANGULAR_DISLOCATION"


class OpportunityClassification(StrEnum):
    OBSERVE = "OBSERVE"
    CANDIDATE = "CANDIDATE"
    VALIDATING = "VALIDATING"
    ECONOMICALLY_VIABLE = "ECONOMICALLY_VIABLE"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RejectionCode(StrEnum):
    NONE = "NONE"
    ERR_STALE_DATA = "ERR_STALE_DATA"
    ERR_CLOCK_DRIFT = "ERR_CLOCK_DRIFT"
    ERR_INVALID_TIMESTAMPS = "ERR_INVALID_TIMESTAMPS"
    ERR_INVALID_ORDERBOOK = "ERR_INVALID_ORDERBOOK"
    ERR_CROSSED_BOOK = "ERR_CROSSED_BOOK"
    ERR_MISSING_FUNDING_TIMESTAMP = "ERR_MISSING_FUNDING_TIMESTAMP"
    ERR_UNCERTAIN_SYMBOL_MAPPING = "ERR_UNCERTAIN_SYMBOL_MAPPING"
    ERR_INSUFFICIENT_LIQUIDITY = "ERR_INSUFFICIENT_LIQUIDITY"
    ERR_SOURCE_HEALTH_DEGRADED = "ERR_SOURCE_HEALTH_DEGRADED"
    ERR_SEQUENCE_INCONSISTENCY = "ERR_SEQUENCE_INCONSISTENCY"
    ERR_SEQUENCE_GAP = "ERR_SEQUENCE_GAP"
    ERR_DUPLICATE_MESSAGE = "ERR_DUPLICATE_MESSAGE"
    ERR_NEGATIVE_NET_EV = "ERR_NEGATIVE_NET_EV"
    ERR_ECONOMIC_HURDLE_UNMET = "ERR_ECONOMIC_HURDLE_UNMET"
    ERR_INSUFFICIENT_PERSISTENCE = "ERR_INSUFFICIENT_PERSISTENCE"
    ERR_RISK_PERIMETER_BLOCKED = "ERR_RISK_PERIMETER_BLOCKED"


class BasisRegime(StrEnum):
    CONTANGO_EXTREME = "CONTANGO_EXTREME"  # Z >= 2.5
    NORMAL_CONTANGO = "NORMAL_CONTANGO"  # 0.5 <= Z < 2.5
    NEUTRAL_BASIS = "NEUTRAL_BASIS"  # -0.5 <= Z < 0.5
    NORMAL_BACKWARDATION = "NORMAL_BACKWARDATION"  # -2.5 < Z <= -0.5
    BACKWARDATION_EXTREME = "BACKWARDATION_EXTREME"  # Z <= -2.5


@dataclass(frozen=True)
class InstrumentIdentity:
    """Verified canonical instrument mapping across venues."""

    canonical_symbol: str  # e.g., "BTCUSDT"
    venue_symbol: str  # e.g., "BTC-USDT-SWAP", "BTCUSDT"
    venue: Venue
    canonical_asset: str  # e.g., "BTC"
    quote_asset: str  # e.g., "USDT"
    instrument_family: str  # e.g., "BTC_USDT"
    market_type: MarketType
    contract_type: ContractType
    contract_multiplier: float  # e.g., 1.0 or 0.01 for OKX
    contract_size: float  # e.g., 1.0 or 100
    settlement_asset: str  # e.g., "USDT"
    tick_size: float  # e.g., 0.10
    lot_size: float  # e.g., 0.001
    min_notional: float  # e.g., 5.0 USD
    mapping_confidence: float = 1.0


@dataclass
class OrderBookLevel:
    price: float
    size: float


@dataclass
class OrderBookSnapshot:
    venue: Venue
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp_ms: int
    sequence_id: int
    checksum: str = ""


@dataclass
class NormalizedMarketQuote:
    venue: Venue
    symbol: str
    canonical_symbol: str
    market_type: MarketType
    bid: float
    ask: float
    last: float
    mark_price: float
    index_price: float
    volume_24h: float
    timestamp_ms: int
    exchange_timestamp_ms: int
    received_timestamp_ms: int
    data_age_ms: float
    sequence_id: int
    source_health: SourceHealth
    is_synthetic: bool = False


@dataclass
class FundingRateRecord:
    venue: Venue
    symbol: str
    canonical_symbol: str
    funding_rate: float
    next_funding_time_ms: int
    interval_hours: int
    exchange_timestamp_ms: int
    local_receipt_ms: int


@dataclass
class FundingEstimate:
    venue: Venue
    symbol: str
    current_rate: float
    predicted_rate: float
    confidence: float
    time_to_payment_sec: float
    expected_cashflow_bps: float
    worst_case_cashflow_bps: float
    source_timestamp_ms: int


@dataclass
class FundingMatrixEntry:
    pair_id: str  # e.g. "BINANCE_PERP::BYBIT_LINEAR::BTCUSDT"
    canonical_symbol: str
    venue_a: Venue
    venue_b: Venue
    rate_a: float
    rate_b: float
    raw_divergence: float  # rate_a - rate_b
    raw_divergence_bps: float
    annualized_divergence_pct: float
    time_to_funding_sec: float
    estimated_capture_bps: float
    confidence: float
    data_freshness_ms: float
    proposed_long_leg: Venue
    proposed_short_leg: Venue


@dataclass
class BasisMetrics:
    canonical_symbol: str
    spot_venue: Venue
    perp_venue: Venue
    spot_price: float
    perp_price: float
    raw_basis_bps: float  # (perp - spot) / spot * 10000
    rolling_mean_bps: float
    rolling_std_bps: float
    zscore: float
    regime: BasisRegime
    duration_outside_threshold_ms: float
    candidate_trigger: bool  # True if |Z| >= 3.0


@dataclass
class ExecutableSpread:
    canonical_symbol: str
    notional_usd: float
    quantity: float
    long_venue: Venue
    short_venue: Venue
    vwap_long_ask: float
    vwap_short_bid: float
    mid_price_reference: float
    theoretical_spread_bps: float  # Mid-to-mid
    executable_spread_bps: float  # Crossing the book: (bid_short - ask_long) / mid * 10000
    gross_spread_usd: float


@dataclass
class EVCostBreakdown:
    gross_edge_usd: float
    entry_fee_long_usd: float
    entry_fee_short_usd: float
    expected_exit_fee_long_usd: float
    expected_exit_fee_short_usd: float
    orderbook_slippage_long_usd: float
    orderbook_slippage_short_usd: float
    hedge_cost_usd: float
    latency_cost_usd: float
    funding_cashflow_usd: float  # Positive if net received, negative if paid
    borrow_cost_usd: float
    safety_buffer_usd: float
    net_ev_usd: float
    net_ev_bps: float
    model_version: str = "EVM_v20.1_PROD"


@dataclass
class MultiScenarioEV:
    base_net_ev_usd: float
    base_net_ev_bps: float
    conservative_net_ev_usd: float
    conservative_net_ev_bps: float
    stress_net_ev_usd: float
    stress_net_ev_bps: float
    cost_breakdown: EVCostBreakdown


@dataclass
class CapacityTier:
    notional_usd: float
    executable_qty: float
    vwap_long: float
    vwap_short: float
    slippage_bps: float
    gross_edge_usd: float
    net_ev_usd: float
    net_ev_bps: float
    viable: bool


@dataclass
class FillSimulation:
    leg: str  # "LEG_A" or "LEG_B"
    venue: Venue
    side: str  # "BUY" or "SELL"
    requested_qty: float
    filled_qty: float
    fill_ratio: float
    residual_qty: float
    vwap_fill_price: float
    execution_lag_ms: float
    adverse_move_bps: float


@dataclass
class ShadowOpportunity:
    opportunity_id: str
    detected_at: float
    qualified_at: float
    expired_at: float | None
    canonical_symbol: str
    opportunity_type: OpportunityType
    long_venue: Venue
    short_venue: Venue
    target_notional_usd: float
    predicted_net_ev_usd: float
    realized_reference_ev_usd: float | None
    opportunity_duration_ms: float
    leg_a_sim: FillSimulation | None = None
    leg_b_sim: FillSimulation | None = None
    unhedged_residual_qty: float = 0.0
    funding_realized_usd: float = 0.0
    model_attribution_error_usd: float = 0.0
    status: str = "OPEN"  # "OPEN", "RESOLVED", "EXPIRED"


@dataclass
class ArbitrageOpportunity:
    opportunity_id: str
    detected_at_ms: int
    canonical_symbol: str
    opportunity_type: OpportunityType
    long_venue: Venue
    short_venue: Venue
    classification: OpportunityClassification
    rejection_code: RejectionCode
    rejection_reason: str
    basis_metrics: BasisMetrics | None
    executable_spread: ExecutableSpread | None
    multi_scenario_ev: MultiScenarioEV | None
    capacity_tiers: list[CapacityTier] = field(default_factory=list)
    max_viable_notional_usd: float = 0.0
    persistence_observations: int = 1
    persistence_duration_ms: float = 0.0
    data_freshness_ms: float = 0.0
    confidence_score: float = 0.0
    provenance_hash: str = ""
    permission: ArbitrageExecutionPermission = ArbitrageExecutionPermission.RESEARCH_ONLY


@dataclass
class ArbitrageProvenanceEnvelope:
    opportunity_id: str
    observation_timestamp_ms: int
    source_timestamps: dict[str, int]
    exchange_sequence_ids: dict[str, int]
    normalized_quotes: list[dict[str, Any]]
    orderbook_snapshot_hash: str
    funding_records: list[dict[str, Any]]
    instrument_mapping_version: str
    fee_model_version: str
    ev_model_version: str
    capacity_model_version: str
    classifier_version: str
    configuration_hash: str
    decision: OpportunityClassification
    rejection_code: RejectionCode
    software_build_sha: str
    canonical_envelope_hash: str = ""
