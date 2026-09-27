"""
core/research/grade_e1/queue_model.py
====================================
Grade-E1 Queue Priority & Penetration Models.

Under the Epistemic Taxonomy: `GRADE-E1: OHLCV_APPROXIMATION`.
Provides 3 bounded queue priority models:
- Q0: Optimistic Touch (Standard backtest baseline)
- Q1: Conservative Volume-Clock Hurdle (Queue depletion requirement)
- Q2: Empirical Penetration Depth & Volatility-Weighted Probabilistic Model
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from core.research.grade_e1.contracts import (
    HypotheticalOrder,
    MarketSnapshot,
    OrderSide,
    QueueModelType,
)


class AbstractQueueModel(ABC):
    """Abstract interface for queue priority and fill estimation."""

    @abstractmethod
    def evaluate_fill(
        self,
        order: HypotheticalOrder,
        snapshot: MarketSnapshot,
        median_volume: float,
    ) -> tuple[bool, float, float]:
        """
        Evaluates whether an active order fills on the current market snapshot.
        Returns: (is_filled, fill_qty, fill_price)
        """
        pass


class OptimisticTouchQueueModel(AbstractQueueModel):
    """
    Q0: Optimistic Touch Model.
    Order fills immediately whenever market price range touches or crosses limit price.
    Acts as an upper-bound benchmark for backtest comparison.
    """

    def evaluate_fill(
        self,
        order: HypotheticalOrder,
        snapshot: MarketSnapshot,
        median_volume: float,
    ) -> tuple[bool, float, float]:
        if order.side == OrderSide.BUY:
            if snapshot.low <= order.limit_price:
                return True, order.remaining_qty, order.limit_price
        else:
            if snapshot.high >= order.limit_price:
                return True, order.remaining_qty, order.limit_price

        return False, 0.0, 0.0


class VolumeClockQueueModel(AbstractQueueModel):
    """
    Q1: Conservative Volume-Clock Queue Model.
    Models physical queue priority where limit orders join the back of the queue.
    Requires a cumulative volume hurdle to trade through the limit price before filling.
    """

    def __init__(self, participation_factor: float = 0.20):
        self.participation_factor = participation_factor

    def evaluate_fill(
        self,
        order: HypotheticalOrder,
        snapshot: MarketSnapshot,
        median_volume: float,
    ) -> tuple[bool, float, float]:
        # Initialize queue shares ahead if not set
        if order.queue_shares_ahead <= 0.0:
            order.queue_shares_ahead = median_volume * self.participation_factor

        bar_range = max(1e-8, snapshot.high - snapshot.low)

        if order.side == OrderSide.BUY:
            if snapshot.low > order.limit_price:
                # Market never reached limit price
                return False, 0.0, 0.0

            # If market traded entirely below limit price, high liquidity consumption
            if snapshot.high <= order.limit_price:
                vol_at_or_below = snapshot.volume
            else:
                fraction_below = (order.limit_price - snapshot.low) / bar_range
                vol_at_or_below = snapshot.volume * fraction_below

            order.queue_shares_ahead -= vol_at_or_below

            if order.queue_shares_ahead <= 0.0:
                return True, order.remaining_qty, order.limit_price
            return False, 0.0, 0.0

        else:  # OrderSide.SELL
            if snapshot.high < order.limit_price:
                return False, 0.0, 0.0

            if snapshot.low >= order.limit_price:
                vol_at_or_above = snapshot.volume
            else:
                fraction_above = (snapshot.high - order.limit_price) / bar_range
                vol_at_or_above = snapshot.volume * fraction_above

            order.queue_shares_ahead -= vol_at_or_above

            if order.queue_shares_ahead <= 0.0:
                return True, order.remaining_qty, order.limit_price
            return False, 0.0, 0.0


class PenetrationDepthQueueModel(AbstractQueueModel):
    """
    Q2: Empirical Penetration Depth & Volatility Model.
    Determines fill probability based on how deeply the candle penetrated past
    the limit price, scaled by volume intensity and candle range.
    """

    def __init__(self, gamma: float = 1.5, seed: int = 42):
        self.gamma = gamma
        self.rng = np.random.default_rng(seed)

    def evaluate_fill(
        self,
        order: HypotheticalOrder,
        snapshot: MarketSnapshot,
        median_volume: float,
    ) -> tuple[bool, float, float]:
        bar_range = max(1e-8, snapshot.high - snapshot.low)

        if order.side == OrderSide.BUY:
            if snapshot.low > order.limit_price:
                return False, 0.0, 0.0

            # Deep penetration: if high <= limit_price, guaranteed fill
            if snapshot.high <= order.limit_price:
                return True, order.remaining_qty, order.limit_price

            penetration_depth = (order.limit_price - snapshot.low) / bar_range
            vol_factor = min(2.0, max(0.2, snapshot.volume / max(1e-8, median_volume)))
            fill_prob = min(1.0, max(0.0, (penetration_depth**self.gamma) * vol_factor))

            if self.rng.random() <= fill_prob:
                return True, order.remaining_qty, order.limit_price
            return False, 0.0, 0.0

        else:  # SELL
            if snapshot.high < order.limit_price:
                return False, 0.0, 0.0

            if snapshot.low >= order.limit_price:
                return True, order.remaining_qty, order.limit_price

            penetration_depth = (snapshot.high - order.limit_price) / bar_range
            vol_factor = min(2.0, max(0.2, snapshot.volume / max(1e-8, median_volume)))
            fill_prob = min(1.0, max(0.0, (penetration_depth**self.gamma) * vol_factor))

            if self.rng.random() <= fill_prob:
                return True, order.remaining_qty, order.limit_price
            return False, 0.0, 0.0


def create_queue_model(
    model_type: QueueModelType,
    participation_factor: float = 0.20,
    seed: int = 42,
) -> AbstractQueueModel:
    if model_type == QueueModelType.Q0_OPTIMISTIC_TOUCH:
        return OptimisticTouchQueueModel()
    elif model_type == QueueModelType.Q1_VOLUME_CLOCK:
        return VolumeClockQueueModel(participation_factor=participation_factor)
    elif model_type == QueueModelType.Q2_PENETRATION_DEPTH:
        return PenetrationDepthQueueModel(seed=seed)
    raise ValueError(f"Unknown queue model type: {model_type}")
