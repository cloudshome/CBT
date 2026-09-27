"""
core/execution/market_making/hawkes_intensity.py
================================================
Milestone 37: Self-Exciting Hawkes Point Process for High-Frequency Order Flow.

Mathematical Formulation:
-------------------------
Trade arrival intensity lambda(t):
    lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))

Parameters:
- mu: Baseline exogenous trade arrival rate (trades/sec).
- alpha: Self-excitation multiplier (magnitude of intensity jump per event).
- beta: Exponential decay rate of clustering memory (sec^-1).
- Branching ratio eta = alpha / beta. (Stationarity condition: eta < 1.0).
- Excitation half-life tau_half = ln(2) / beta.

Recursive O(1) state formulation:
    R(t_k) = exp(-beta * (t_k - t_{k-1})) * (1 + R(t_{k-1}))
    lambda(t_k) = mu + alpha * R(t_k)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai_quant_sentinel.market_making.hawkes")


class FlowToxicityTier(str, Enum):
    """Categorical classification of incoming order flow toxicity."""

    BENIGN = "BENIGN"
    MODERATE_CLUSTERING = "MODERATE_CLUSTERING"
    ELEVATED_TOXICITY = "ELEVATED_TOXICITY"
    CRITICAL_TOXIC_SURGE = "CRITICAL_TOXIC_SURGE"


@dataclass
class HawkesIntensityState:
    """Real-time diagnostic state of the Hawkes point process."""

    current_intensity: float
    baseline_rate_mu: float
    excitation_alpha: float
    decay_beta: float
    branching_ratio_eta: float
    is_stationary: bool
    excitation_half_life_sec: float
    toxicity_tier: FlowToxicityTier
    spread_widening_multiplier: float
    last_event_timestamp_ns: int
    events_count: int


class HawkesTradeArrivalEstimator:
    """
    Sub-second recursive Hawkes point process for detecting order arrival
    clustering, informed cascades, and adverse selection spikes.
    """

    def __init__(
        self,
        baseline_rate_mu: float = 2.0,  # 2 trades/sec baseline
        excitation_alpha: float = 1.2,  # Jump intensity per fill
        decay_beta: float = 2.0,  # Decay rate (half-life ~ 0.35s)
        moderate_intensity_ratio: float = 2.5,
        elevated_intensity_ratio: float = 5.0,
        critical_intensity_ratio: float = 10.0,
    ) -> None:
        if decay_beta <= 0:
            raise ValueError("decay_beta must be > 0")
        if excitation_alpha < 0:
            raise ValueError("excitation_alpha must be >= 0")

        self.mu = baseline_rate_mu
        self.alpha = excitation_alpha
        self.beta = decay_beta
        self.eta = excitation_alpha / decay_beta
        self.is_stationary = self.eta < 1.0

        self.moderate_ratio = moderate_intensity_ratio
        self.elevated_ratio = elevated_intensity_ratio
        self.critical_ratio = critical_intensity_ratio

        # State variables
        self._r_k: float = 0.0
        self._last_event_t_ns: int | None = None
        self._events_count: int = 0
        self.real_capital_enabled: bool = False

    @property
    def excitation_half_life_sec(self) -> float:
        """Returns the half-life of excitation in seconds."""
        return math.log(2.0) / self.beta

    def record_trade_event(self, timestamp_ns: int | None = None) -> HawkesIntensityState:
        """
        Updates the Hawkes intensity upon arrival of a trade event using O(1) recursion.
        """
        now_ns = timestamp_ns if timestamp_ns is not None else time.monotonic_ns()

        if self._last_event_t_ns is None:
            self._r_k = 1.0
        else:
            dt_sec = max(0.0, (now_ns - self._last_event_t_ns) / 1e9)
            decay = math.exp(-self.beta * dt_sec)
            self._r_k = 1.0 + decay * self._r_k

        self._last_event_t_ns = now_ns
        self._events_count += 1

        return self.get_current_state(now_ns=now_ns)

    def get_current_intensity(self, now_ns: int | None = None) -> float:
        """Computes current decayed intensity at timestamp now_ns without registering an event."""
        if self._last_event_t_ns is None:
            return self.mu

        current_ns = now_ns if now_ns is not None else time.monotonic_ns()
        dt_sec = max(0.0, (current_ns - self._last_event_t_ns) / 1e9)
        decayed_r = self._r_k * math.exp(-self.beta * dt_sec)
        intensity = self.mu + self.alpha * decayed_r
        return intensity

    def get_current_state(self, now_ns: int | None = None) -> HawkesIntensityState:
        """Evaluates toxicity tier and spread multiplier at current point in time."""
        current_intensity = self.get_current_intensity(now_ns)
        intensity_ratio = current_intensity / max(1e-6, self.mu)

        if intensity_ratio >= self.critical_ratio:
            tier = FlowToxicityTier.CRITICAL_TOXIC_SURGE
            widening = 2.50
        elif intensity_ratio >= self.elevated_ratio:
            tier = FlowToxicityTier.ELEVATED_TOXICITY
            widening = 1.75
        elif intensity_ratio >= self.moderate_ratio:
            tier = FlowToxicityTier.MODERATE_CLUSTERING
            widening = 1.25
        else:
            tier = FlowToxicityTier.BENIGN
            widening = 1.00

        return HawkesIntensityState(
            current_intensity=round(current_intensity, 4),
            baseline_rate_mu=self.mu,
            excitation_alpha=self.alpha,
            decay_beta=self.beta,
            branching_ratio_eta=round(self.eta, 4),
            is_stationary=self.is_stationary,
            excitation_half_life_sec=round(self.excitation_half_life_sec, 4),
            toxicity_tier=tier,
            spread_widening_multiplier=widening,
            last_event_timestamp_ns=self._last_event_t_ns or 0,
            events_count=self._events_count,
        )

    def reset(self) -> None:
        """Resets the Hawkes intensity state."""
        self._r_k = 0.0
        self._last_event_t_ns = None
        self._events_count = 0
