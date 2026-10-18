"""
core/mbo/models.py
==================
Data models, enums, and schemas for Task 20.2:
L3 Market By Order (MBO) Liquidity Depth Reconstruction & Queue Priority Simulator.

Maintains individual simulated order identities, FIFO queue priority,
iceberg detection, and toxic order flow analytics.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MBOSide(StrEnum):
    BID = "BID"
    ASK = "ASK"


class MBOAction(StrEnum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    EXECUTE = "EXECUTE"
    TRADE = "TRADE"


class ToxicityRegime(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    ELEVATED = "ELEVATED"
    TOXIC = "TOXIC"


@dataclass
class MBOOrder:
    """Represents an individual discrete order in the L3 order book queue."""

    order_id: str
    venue: str
    symbol: str
    side: MBOSide
    price: float
    size: float
    initial_size: float
    timestamp_ns: int
    priority_index: int
    is_iceberg_child: bool = False
    parent_iceberg_id: str | None = None


@dataclass
class MBOPriceLevel:
    """A discrete price level containing an ordered FIFO queue of individual orders."""

    price: float
    side: MBOSide
    total_size: float = 0.0
    order_count: int = 0
    orders: list[MBOOrder] = field(default_factory=list)
    cumulative_executed_qty: float = 0.0
    cumulative_canceled_qty: float = 0.0
    last_update_ns: int = field(default_factory=lambda: int(time.time() * 1e9))

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "side": self.side.value,
            "total_size": round(self.total_size, 4),
            "order_count": self.order_count,
            "cumulative_executed_qty": round(self.cumulative_executed_qty, 4),
            "cumulative_canceled_qty": round(self.cumulative_canceled_qty, 4),
            "median_order_size": round(self.total_size / max(1, self.order_count), 4),
        }


@dataclass
class QueuePositionEstimate:
    """Estimated position and fill dynamics of a passive limit order in the queue."""

    symbol: str
    venue: str
    side: MBOSide
    price: float
    simulated_order_qty: float
    queue_ahead_qty: float
    queue_ahead_orders: int
    queue_behind_qty: float
    total_level_qty: float
    relative_queue_position_pct: float  # 0.0% = Top of Book front, 100% = tail
    expected_wait_seconds: float
    fill_probability_30s: float
    fill_probability_60s: float
    fill_probability_300s: float
    adverse_selection_risk_score: float  # 0.0 to 1.0 (toxic fill probability)
    estimated_depletion_rate_qty_per_sec: float


@dataclass
class IcebergDetection:
    """Identified hidden reload / algorithmic iceberg order at a price level."""

    iceberg_id: str
    symbol: str
    venue: str
    side: MBOSide
    price: float
    initial_displayed_size: float
    cumulative_executed_size: float
    estimated_reload_size: float
    estimated_total_hidden_qty: float
    total_estimated_size: float
    confidence_score: float  # 0.0 to 1.0
    reload_count: int
    first_detected_ns: int
    last_reload_ns: int
    is_active: bool = True


@dataclass
class ToxicFlowMetric:
    """Microstructure order flow toxicity and depletion velocity metrics."""

    symbol: str
    venue: str
    timestamp_ms: int
    vpin_mbo: float  # Volume-synchronized probability of toxicity
    cancel_to_trade_ratio: float  # High ratio indicates algorithmic spoofing/flicker
    depletion_velocity_usd_per_sec: float  # Speed at which liquidity is swept
    order_arrival_intensity: float  # Orders per second
    mean_order_lifetime_ms: float
    toxicity_regime: ToxicityRegime
    adverse_selection_bias_bps: float  # Expected slippage if filled passively


@dataclass
class MBODepthSnapshot:
    """High-level snapshot of reconstructed L3 depth, icebergs, and toxicity."""

    symbol: str
    venue: str
    timestamp_ms: int
    bid_levels: list[MBOPriceLevel]
    ask_levels: list[MBOPriceLevel]
    detected_icebergs: list[IcebergDetection]
    toxic_flow: ToxicFlowMetric
    total_bid_depth_usd: float
    total_ask_depth_usd: float
    microstructure_imbalance: float  # -1.0 (pure ask pressure) to +1.0 (pure bid pressure)
