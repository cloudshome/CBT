"""
core/research/grade_e1/contracts.py
===================================
Grade-E1: Canonical Type Contracts, Enums, and Dataclasses.

Epistemic Guardrail:
All execution evidence in this engine is certified strictly as:
`GRADE-E1: OHLCV_APPROXIMATION`.
Zero live trading dispatch, zero capital allocation, zero M18 certified surface modification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Literal

EVIDENCE_GRADE: Literal["GRADE-E1: OHLCV_APPROXIMATION"] = "GRADE-E1: OHLCV_APPROXIMATION"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    PENDING_QUEUE = "PENDING_QUEUE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED_DUE_TO_DATA_GAP = "CANCELLED_DUE_TO_DATA_GAP"


class LiquidityRole(StrEnum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class QueueModelType(StrEnum):
    Q0_OPTIMISTIC_TOUCH = "Q0_OPTIMISTIC_TOUCH"
    Q1_VOLUME_CLOCK = "Q1_VOLUME_CLOCK"
    Q2_PENETRATION_DEPTH = "Q2_PENETRATION_DEPTH"


class LatencyModelType(StrEnum):
    L0_ZERO_LATENCY = "L0_ZERO_LATENCY"
    L1_FIXED_50MS = "L1_FIXED_50MS"
    L2_STOCHASTIC_LOGNORMAL = "L2_STOCHASTIC_LOGNORMAL"


class FillEngineType(StrEnum):
    F1_CONSERVATIVE = "F1_CONSERVATIVE"
    F2_CENTRAL = "F2_CENTRAL"
    F3_OPTIMISTIC = "F3_OPTIMISTIC"


class ResearchVerdictType(StrEnum):
    PROMOTE_FOR_FURTHER_RESEARCH = "PROMOTE_FOR_FURTHER_RESEARCH"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable causal snapshot of a market interval."""

    timestamp: int
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread_bps: float = 2.0
    volatility_bps: float = 10.0
    is_gap_boundary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HypotheticalOrder:
    """Stateful simulated order representation for maker execution research."""

    order_id: str
    symbol: str
    side: OrderSide
    limit_price: float
    quantity: float
    post_only: bool = True
    time_in_force_bars: int = 4
    submission_bar_idx: int = 0
    submission_timestamp: int = 0
    ack_timestamp: int = 0
    status: OrderStatus = OrderStatus.SUBMITTED
    filled_qty: float = 0.0
    remaining_qty: float = 0.0
    avg_fill_price: float = 0.0
    cancel_reason: str | None = None
    queue_shares_ahead: float = 0.0

    def __post_init__(self) -> None:
        if self.remaining_qty == 0.0:
            self.remaining_qty = self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "limit_price": self.limit_price,
            "quantity": self.quantity,
            "post_only": self.post_only,
            "time_in_force_bars": self.time_in_force_bars,
            "submission_bar_idx": self.submission_bar_idx,
            "submission_timestamp": self.submission_timestamp,
            "ack_timestamp": self.ack_timestamp,
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "remaining_qty": self.remaining_qty,
            "avg_fill_price": self.avg_fill_price,
            "cancel_reason": self.cancel_reason,
            "queue_shares_ahead": self.queue_shares_ahead,
        }


@dataclass(frozen=True)
class FillEvent:
    """Immutable record of an executed hypothetical fill."""

    fill_id: str
    order_id: str
    bar_index: int
    timestamp: int
    side: OrderSide
    fill_price: float
    fill_qty: float
    fee_bps: float
    role: LiquidityRole = LiquidityRole.MAKER
    queue_time_bars: float = 0.0
    markout_1_bar_bps: float | None = None
    markout_5_bar_bps: float | None = None
    markout_12_bar_bps: float | None = None
    markout_24_bar_bps: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "bar_index": self.bar_index,
            "timestamp": self.timestamp,
            "side": self.side.value,
            "fill_price": self.fill_price,
            "fill_qty": self.fill_qty,
            "fee_bps": self.fee_bps,
            "role": self.role.value,
            "queue_time_bars": self.queue_time_bars,
            "markout_1_bar_bps": self.markout_1_bar_bps,
            "markout_5_bar_bps": self.markout_5_bar_bps,
            "markout_12_bar_bps": self.markout_12_bar_bps,
            "markout_24_bar_bps": self.markout_24_bar_bps,
        }


@dataclass(frozen=True)
class AdverseSelectionMetrics:
    """Summary metrics of post-fill markout and adverse selection."""

    total_fills: int
    mean_markout_1_bar_bps: float
    mean_markout_5_bar_bps: float
    mean_markout_12_bar_bps: float
    mean_markout_24_bar_bps: float
    toxic_fill_ratio_5_bar: float
    gross_spread_captured_bps: float
    realized_spread_5_bar_bps: float
    adverse_selection_half_life_bars: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibratedCostBreakdown:
    """Decomposition of gross spread, fees, adverse selection, and opportunity cost."""

    fee_tier_name: str
    maker_fee_bps: float
    taker_fee_bps: float
    gross_spread_earned_bps: float
    adverse_selection_loss_bps: float
    opportunity_cost_bps: float
    net_maker_edge_bps: float
    taker_benchmark_cost_bps: float
    maker_advantage_bps: float
    is_maker_superior: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentConfig:
    """Deterministic configuration of a Grade-E1 empirical experiment."""

    experiment_id: str
    dataset_id: str
    queue_model: QueueModelType = QueueModelType.Q1_VOLUME_CLOCK
    latency_model: LatencyModelType = LatencyModelType.L1_FIXED_50MS
    fill_engine: FillEngineType = FillEngineType.F1_CONSERVATIVE
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 6.0
    default_spread_bps: float = 2.5
    queue_participation_factor: float = 0.20
    random_seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "dataset_id": self.dataset_id,
            "queue_model": self.queue_model.value,
            "latency_model": self.latency_model.value,
            "fill_engine": self.fill_engine.value,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "default_spread_bps": self.default_spread_bps,
            "queue_participation_factor": self.queue_participation_factor,
            "random_seed": self.random_seed,
        }


@dataclass(frozen=True)
class ExperimentResult:
    """Full empirical outcome of a single Grade-E1 experiment run."""

    config: ExperimentConfig
    evidence_grade: str = EVIDENCE_GRADE
    total_orders: int = 0
    filled_orders: int = 0
    unfilled_orders: int = 0
    fill_rate_pct: float = 0.0
    adverse_selection: AdverseSelectionMetrics | None = None
    cost_breakdown: CalibratedCostBreakdown | None = None
    hypothesis_results: dict[str, bool] = field(default_factory=dict)
    statistical_details: dict[str, Any] = field(default_factory=dict)
    evidence_hash: str = ""

    def compute_hash(self) -> str:
        data_str = json.dumps(
            {
                "config": self.config.to_dict(),
                "total_orders": self.total_orders,
                "filled_orders": self.filled_orders,
                "fill_rate_pct": self.fill_rate_pct,
                "cost_breakdown": self.cost_breakdown.to_dict() if self.cost_breakdown else None,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "evidence_grade": self.evidence_grade,
            "total_orders": self.total_orders,
            "filled_orders": self.filled_orders,
            "unfilled_orders": self.unfilled_orders,
            "fill_rate_pct": round(self.fill_rate_pct, 4),
            "adverse_selection": self.adverse_selection.to_dict()
            if self.adverse_selection
            else None,
            "cost_breakdown": self.cost_breakdown.to_dict() if self.cost_breakdown else None,
            "hypothesis_results": self.hypothesis_results,
            "statistical_details": self.statistical_details,
            "evidence_hash": self.evidence_hash or self.compute_hash(),
        }
