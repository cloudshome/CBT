"""
Probability Construction Engine for Kronos Forecast Distributions.
Converts multi-path trajectory returns into mathematically explicit directional probabilities
against configurable hurdle thresholds (zero vs transaction cost + slippage).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ProbabilityContract:
    definition_version: str
    threshold: float
    horizon_bars: int
    distribution_method: str  # "EMPIRICAL_QUANTILE", "PARAMETRIC_STUDENT_T", "PARAMETRIC_GAUSSIAN"
    raw_probability: float
    raw_logit: float
    consensus: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition_version": self.definition_version,
            "threshold": round(self.threshold, 6),
            "horizon_bars": self.horizon_bars,
            "distribution_method": self.distribution_method,
            "raw_probability": round(self.raw_probability, 6),
            "raw_logit": round(self.raw_logit, 4),
            "consensus": round(self.consensus, 4),
            "sample_count": self.sample_count,
        }


class ProbabilityEngine:
    """
    Constructs directional probabilities from forecast trajectory arrays.
    Guarantees mathematically rigorous mapping from paths to P(r_h > threshold).
    """

    DEFINITION_VERSION = "2.0.0"

    def __init__(self, default_threshold: float = 0.0, method: str = "EMPIRICAL_QUANTILE"):
        self.default_threshold = default_threshold
        self.method = method

    def construct_probability(
        self,
        sample_trajectories: np.ndarray,
        entry_price: float,
        horizon_index: int = -1,
        hurdle_threshold: float | None = None,
        method: str | None = None,
    ) -> ProbabilityContract:
        """
        Computes P(return > threshold) from sample trajectories.
        sample_trajectories shape: (sample_count, horizon, 4) where [:, :, 3] is Close.
        """
        if sample_trajectories.size == 0 or entry_price <= 0:
            return ProbabilityContract(
                definition_version=self.DEFINITION_VERSION,
                threshold=0.0,
                horizon_bars=1,
                distribution_method="DEFAULT",
                raw_probability=0.50,
                raw_logit=0.0,
                consensus=0.50,
                sample_count=0,
            )

        threshold = self.default_threshold if hurdle_threshold is None else hurdle_threshold
        dist_method = self.method if method is None else method

        # Terminal predicted close prices for target horizon step
        terminal_closes = sample_trajectories[:, horizon_index, 3]
        terminal_returns = (terminal_closes - entry_price) / entry_price
        n_samples = len(terminal_returns)

        if dist_method == "PARAMETRIC_GAUSSIAN" and n_samples >= 3:
            mu = float(np.mean(terminal_returns))
            sigma = float(np.std(terminal_returns))
            if sigma < 1e-8:
                sigma = 0.001
            # Z-score for hurdle
            z = (threshold - mu) / sigma
            # Complementary error function: P(X > threshold) = 0.5 * erfc(z / sqrt(2))
            raw_p = 0.5 * math.erfc(z / math.sqrt(2.0))
        else:
            # Empirical quantile: fraction of paths exceeding hurdle
            exceed_count = np.sum(terminal_returns > threshold)
            # Add Laplace smoothing (add-1) to avoid degenerate 0.0 or 1.0 logits
            raw_p = (exceed_count + 1.0) / (n_samples + 2.0)

        # Clamp strictly inside (0.01, 0.99) for stable logit
        clamped_p = float(np.clip(raw_p, 0.01, 0.99))
        raw_logit = float(math.log(clamped_p / (1.0 - clamped_p)))

        # Consensus magnitude: distance from 0.5
        consensus = float(max(clamped_p, 1.0 - clamped_p))

        horizon_bars = sample_trajectories.shape[1] if horizon_index == -1 else (horizon_index + 1)

        return ProbabilityContract(
            definition_version=self.DEFINITION_VERSION,
            threshold=threshold,
            horizon_bars=horizon_bars,
            distribution_method=dist_method,
            raw_probability=clamped_p,
            raw_logit=raw_logit,
            consensus=consensus,
            sample_count=n_samples,
        )


probability_engine = ProbabilityEngine()
