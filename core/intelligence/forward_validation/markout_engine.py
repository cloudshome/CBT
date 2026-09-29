"""
core/intelligence/forward_validation/markout_engine.py
======================================================
Microstructure Markout Engine for Milestone 31.

Enforces:
1. Three-Tier Markout Taxonomy:
   - Mid-Price Markout (M_mid): Measures midpoint drift.
   - Executable Markout (M_exec): Measures executable opposite-quote movement.
   - Net Markout (M_net): Subtracts fees, slippage, and modeled frictions.
2. Standard Horizons: 100ms, 1s (1000ms), 5s (5000ms), 30s (30000ms).
3. Data Quality Gate: Flags DATA_UNAVAILABLE or degraded quality if book is stale or missing.
4. Permanent Capital Firewall: Pure diagnostic engine with zero execution authority.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.orderbook_tracker import (
    FeedQualityState,
    OrderBookSnapshot,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    OrderSide,
    PaperFill,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.markout_engine")

STANDARD_HORIZONS_MS = [100, 1000, 5000, 30000]


class MarkoutObservation(BaseModel):
    """
    Immutable post-trade microstructure markout measurement.
    """

    observation_id: str = Field(..., description="Unique markout observation ID")
    fill_id: str = Field(..., description="Referenced PaperFill ID")
    admission_id: str = Field(..., description="Strategy admission ID")
    symbol: str = Field(..., description="Asset symbol")
    venue: str = Field(..., description="Exchange venue")
    side: OrderSide = Field(..., description="Trade side")
    fill_price: float = Field(..., description="Original execution price")
    fill_timestamp_utc: float = Field(..., description="Execution timestamp")
    horizon_ms: int = Field(..., description="Markout horizon in milliseconds")
    target_timestamp_utc: float = Field(..., description="fill_timestamp_utc + horizon")
    actual_observation_utc: float = Field(..., description="Timestamp of book snapshot used")
    future_mid_price: float | None = Field(default=None, description="Mid price at target horizon")
    future_executable_price: float | None = Field(
        default=None, description="Opposite quote at target horizon"
    )
    gross_mid_markout_bps: float | None = Field(
        default=None, description="Mid-price markout in basis points"
    )
    gross_exec_markout_bps: float | None = Field(
        default=None, description="Executable quote markout in basis points"
    )
    net_markout_bps: float | None = Field(
        default=None, description="Net markout after fees and slippage"
    )
    estimated_cost_bps: float = Field(
        default=0.0, description="Total costs (fee + slippage) subtracted"
    )
    data_quality: FeedQualityState = Field(default=FeedQualityState.HEALTHY)
    is_valid: bool = Field(default=True, description="True if snapshot was fresh and uncrossed")
    calculation_version: str = Field(default="v1.0-three-tier-taxonomy")
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = (
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    )
    real_capital_enabled: Literal[False] = False


class PendingFillMarkout:
    """Tracks a fill awaiting markout calculations across horizons."""

    def __init__(self, fill: PaperFill, horizons_ms: list[int] | None = None) -> None:
        self.fill = fill
        self.pending_horizons: set[int] = set(horizons_ms or STANDARD_HORIZONS_MS)
        self.completed_horizons: set[int] = set()


class MicrostructureMarkoutEngine:
    """
    Computes forward price movement conditional on paper trade executions
    across discrete microsecond and sub-minute horizons.
    """

    def __init__(
        self, horizons_ms: list[int] | None = None, max_clock_skew_ms: float = 500.0
    ) -> None:
        self.horizons_ms = sorted(horizons_ms or STANDARD_HORIZONS_MS)
        self.max_clock_skew_ms = max_clock_skew_ms
        # fill_id -> PendingFillMarkout
        self._pending_fills: dict[str, PendingFillMarkout] = {}

    def register_fill(self, fill: PaperFill) -> None:
        """Enqueues a new fill for forward markout tracking."""
        self._pending_fills[fill.fill_id] = PendingFillMarkout(fill, self.horizons_ms)
        logger.debug(
            "Registered fill %s for markouts at horizons %s", fill.fill_id, self.horizons_ms
        )

    def compute_markout(
        self,
        fill: PaperFill,
        future_book: OrderBookSnapshot,
        horizon_ms: int,
    ) -> MarkoutObservation:
        """
        Computes the three-tier markout for a single fill against a specific future order book state.
        """
        now = time.time()
        target_utc = fill.fill_timestamp_utc + (horizon_ms / 1000.0)
        obs_id = f"MOBS-{int(now)}-{uuid.uuid4().hex[:8]}"
        total_costs_bps = fill.fee_bps + fill.slippage_bps

        # 1. Quality & Skew Checks
        is_quality_ok = (future_book.quality == FeedQualityState.HEALTHY) and (
            not future_book.is_crossed
        )
        skew_ms = abs(future_book.timestamps.exchange_event_time_utc - target_utc) * 1000.0
        is_timing_ok = skew_ms <= self.max_clock_skew_ms

        if not is_quality_ok or not is_timing_ok:
            quality = future_book.quality if not is_quality_ok else FeedQualityState.STALE_FEED
            return MarkoutObservation(
                observation_id=obs_id,
                fill_id=fill.fill_id,
                admission_id=fill.admission_id,
                symbol=fill.symbol,
                venue=fill.venue,
                side=fill.side,
                fill_price=fill.fill_price,
                fill_timestamp_utc=fill.fill_timestamp_utc,
                horizon_ms=horizon_ms,
                target_timestamp_utc=target_utc,
                actual_observation_utc=future_book.timestamps.exchange_event_time_utc,
                estimated_cost_bps=total_costs_bps,
                data_quality=quality,
                is_valid=False,
            )

        mid = future_book.mid_price
        # Executable price: opposite quote for liquidating the position
        # For BUY trade: we liquidate by selling at the future best bid
        # For SELL trade: we liquidate by buying at the future best ask
        exec_price = future_book.best_bid if fill.side == OrderSide.BUY else future_book.best_ask

        if mid is None or mid <= 0 or exec_price is None or exec_price <= 0:
            return MarkoutObservation(
                observation_id=obs_id,
                fill_id=fill.fill_id,
                admission_id=fill.admission_id,
                symbol=fill.symbol,
                venue=fill.venue,
                side=fill.side,
                fill_price=fill.fill_price,
                fill_timestamp_utc=fill.fill_timestamp_utc,
                horizon_ms=horizon_ms,
                target_timestamp_utc=target_utc,
                actual_observation_utc=future_book.timestamps.exchange_event_time_utc,
                estimated_cost_bps=total_costs_bps,
                data_quality=FeedQualityState.INVALID_QUOTE,
                is_valid=False,
            )

        # 2. Compute Three-Tier Markouts in Basis Points
        if fill.side == OrderSide.BUY:
            mid_bps = ((mid - fill.benchmark_mid_price) / fill.benchmark_mid_price) * 10000.0
            exec_bps = ((exec_price - fill.fill_price) / fill.fill_price) * 10000.0
        else:
            mid_bps = ((fill.benchmark_mid_price - mid) / fill.benchmark_mid_price) * 10000.0
            exec_bps = ((fill.fill_price - exec_price) / fill.fill_price) * 10000.0

        net_bps = exec_bps - total_costs_bps

        return MarkoutObservation(
            observation_id=obs_id,
            fill_id=fill.fill_id,
            admission_id=fill.admission_id,
            symbol=fill.symbol,
            venue=fill.venue,
            side=fill.side,
            fill_price=fill.fill_price,
            fill_timestamp_utc=fill.fill_timestamp_utc,
            horizon_ms=horizon_ms,
            target_timestamp_utc=target_utc,
            actual_observation_utc=future_book.timestamps.exchange_event_time_utc,
            future_mid_price=mid,
            future_executable_price=exec_price,
            gross_mid_markout_bps=mid_bps,
            gross_exec_markout_bps=exec_bps,
            net_markout_bps=net_bps,
            estimated_cost_bps=total_costs_bps,
            data_quality=FeedQualityState.HEALTHY,
            is_valid=True,
        )

    def process_book_update(self, book: OrderBookSnapshot) -> list[MarkoutObservation]:
        """
        Scans all registered pending fills and evaluates any horizons that have matured
        under the arrival of `book`.
        """
        completed_observations: list[MarkoutObservation] = []
        book_time = book.timestamps.exchange_event_time_utc

        for fill_id, pending in list(self._pending_fills.items()):
            if pending.fill.symbol != book.symbol or pending.fill.venue != book.venue:
                continue

            for horizon_ms in list(pending.pending_horizons):
                target_utc = pending.fill.fill_timestamp_utc + (horizon_ms / 1000.0)

                # Has the book reached or passed this horizon?
                if book_time >= target_utc:
                    obs = self.compute_markout(pending.fill, book, horizon_ms)
                    completed_observations.append(obs)
                    pending.pending_horizons.remove(horizon_ms)
                    pending.completed_horizons.add(horizon_ms)

            # If all horizons evaluated, clean up pending fill
            if not pending.pending_horizons:
                del self._pending_fills[fill_id]

        return completed_observations

    def get_pending_count(self) -> int:
        """Returns the number of fills currently awaiting future horizon observations."""
        return len(self._pending_fills)
