"""
core/research/grade_e1/latency_model.py
======================================
Grade-E1 Latency Simulation Models.

Models wire transit, venue matching engine ingress, acknowledgement,
and cancellation round-trip delays.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np

from core.research.grade_e1.contracts import LatencyModelType


class AbstractLatencyModel(ABC):
    """Base interface for latency modeling."""

    @abstractmethod
    def sample_submission_latency_ms(self) -> float:
        """Returns sampled network/matching ingress delay in milliseconds."""
        pass

    @abstractmethod
    def sample_cancellation_latency_ms(self) -> float:
        """Returns sampled cancellation round-trip delay in milliseconds."""
        pass


class ZeroLatencyModel(AbstractLatencyModel):
    """L0: Optimistic instantaneous baseline (0 ms)."""

    def sample_submission_latency_ms(self) -> float:
        return 0.0

    def sample_cancellation_latency_ms(self) -> float:
        return 0.0


class FixedLatencyModel(AbstractLatencyModel):
    """L1: Central benchmark fixed delay (50 ms)."""

    def __init__(self, delay_ms: float = 50.0):
        self.delay_ms = delay_ms

    def sample_submission_latency_ms(self) -> float:
        return self.delay_ms

    def sample_cancellation_latency_ms(self) -> float:
        return self.delay_ms


class StochasticLognormalLatencyModel(AbstractLatencyModel):
    """
    L2: Realistic stochastic delay with log-normal distribution and tail spikes.
    Base median ~45ms, tail spikes up to 250ms+ simulating network jitter and exchange queueing.
    """

    def __init__(self, median_ms: float = 45.0, sigma: float = 0.35, seed: int = 42):
        self.mu = math.log(median_ms)
        self.sigma = sigma
        self.rng = np.random.default_rng(seed)

    def sample_submission_latency_ms(self) -> float:
        # 1% probability of exchange congestion tail spike
        is_spike = self.rng.random() < 0.01
        spike_multiplier = 4.0 if is_spike else 1.0
        val = float(self.rng.lognormal(self.mu, self.sigma)) * spike_multiplier
        return max(5.0, round(val, 2))

    def sample_cancellation_latency_ms(self) -> float:
        # Cancellation typically experiences similar distribution
        is_spike = self.rng.random() < 0.01
        spike_multiplier = 3.5 if is_spike else 1.0
        val = float(self.rng.lognormal(self.mu, self.sigma)) * spike_multiplier
        return max(5.0, round(val, 2))


def create_latency_model(model_type: LatencyModelType, seed: int = 42) -> AbstractLatencyModel:
    if model_type == LatencyModelType.L0_ZERO_LATENCY:
        return ZeroLatencyModel()
    elif model_type == LatencyModelType.L1_FIXED_50MS:
        return FixedLatencyModel(50.0)
    elif model_type == LatencyModelType.L2_STOCHASTIC_LOGNORMAL:
        return StochasticLognormalLatencyModel(seed=seed)
    raise ValueError(f"Unknown latency model type: {model_type}")
