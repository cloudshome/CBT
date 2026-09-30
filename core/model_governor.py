"""
Model Ensemble Governor & Dynamic Regime-Conditional Reliability Weights Engine.
Governs multi-model probability synthesis and enforces the core principle:
'LLM is an evidence interpreter, not the probability authority.'
Calculates model disagreement entropy and dynamically weights models based on regime fit.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.model_governor")

# Dynamic Regime-Conditional Reliability Weights Matrix
REGIME_RELIABILITY_WEIGHTS: dict[str, dict[str, float]] = {
    "TRENDING_BULL": {
        "orderflow_cvd": 0.28,
        "historical_analogue": 0.25,
        "smc_structure": 0.20,
        "scenario_engine": 0.15,
        "tri_bootstrap_paths": 0.12,
    },
    "TRENDING_BEAR": {
        "orderflow_cvd": 0.28,
        "historical_analogue": 0.25,
        "smc_structure": 0.20,
        "scenario_engine": 0.15,
        "tri_bootstrap_paths": 0.12,
    },
    "HIGH_VOLATILITY": {
        "tri_bootstrap_paths": 0.35,
        "orderflow_cvd": 0.22,
        "historical_analogue": 0.18,
        "macro_sentinel": 0.15,
        "scenario_engine": 0.10,
    },
    "RANGING_CONSOLIDATION": {
        "smc_structure": 0.30,
        "historical_analogue": 0.25,
        "scenario_engine": 0.20,
        "orderflow_cvd": 0.15,
        "tri_bootstrap_paths": 0.10,
    },
}


@dataclass
class EnsembleProbabilityForecast:
    consensus_p_win: float  # Calibrated consensus probability [0.0, 1.0]
    p_min_range: float  # Lower probability bound
    p_max_range: float  # Upper probability bound
    confidence_interval_95: tuple[float, float]
    disagreement_entropy: float  # [0.0, 1.0]
    active_regime: str
    model_contributions: dict[str, float]
    model_probabilities: dict[str, float]
    is_consensus_clear: bool  # False if disagreement_entropy > 0.40

    def to_dict(self) -> dict[str, Any]:
        return {
            "consensus_p_win": round(self.consensus_p_win, 3),
            "p_min_range": round(self.p_min_range, 3),
            "p_max_range": round(self.p_max_range, 3),
            "confidence_interval_95": (
                round(self.confidence_interval_95[0], 3),
                round(self.confidence_interval_95[1], 3),
            ),
            "disagreement_entropy": round(self.disagreement_entropy, 3),
            "active_regime": self.active_regime,
            "model_contributions": {k: round(v, 3) for k, v in self.model_contributions.items()},
            "model_probabilities": {k: round(v, 3) for k, v in self.model_probabilities.items()},
            "is_consensus_clear": self.is_consensus_clear,
        }


class ModelEnsembleGovernor:
    """
    Synthesizes multiple specialized quantitative models into an honest consensus forecast.
    """

    def synthesize_forecast(
        self,
        active_regime: str,
        analogue_p_win: float,
        scenario_p_win: float,
        bootstrap_p_win: float,
        orderflow_p_win: float,
        smc_p_win: float,
    ) -> EnsembleProbabilityForecast:
        """
        Computes regime-weighted ensemble probability and disagreement entropy.
        """
        regime_key = active_regime.upper()
        if "BULL" in regime_key:
            weights_map = REGIME_RELIABILITY_WEIGHTS["TRENDING_BULL"]
        elif "BEAR" in regime_key:
            weights_map = REGIME_RELIABILITY_WEIGHTS["TRENDING_BEAR"]
        elif "VOLATILITY" in regime_key or "EXPANSION" in regime_key:
            weights_map = REGIME_RELIABILITY_WEIGHTS["HIGH_VOLATILITY"]
        else:
            weights_map = REGIME_RELIABILITY_WEIGHTS["RANGING_CONSOLIDATION"]

        prob_map = {
            "historical_analogue": min(1.0, max(0.0, analogue_p_win)),
            "scenario_engine": min(1.0, max(0.0, scenario_p_win)),
            "tri_bootstrap_paths": min(1.0, max(0.0, bootstrap_p_win)),
            "orderflow_cvd": min(1.0, max(0.0, orderflow_p_win)),
            "smc_structure": min(1.0, max(0.0, smc_p_win)),
        }

        # Weighted Dot Product
        weighted_p = 0.0
        total_w = 0.0
        for model_name, w in weights_map.items():
            if model_name in prob_map:
                weighted_p += w * prob_map[model_name]
                total_w += w

        consensus_p = weighted_p / total_w if total_w > 0 else 0.50

        # Spread & Disagreement Entropy
        probs_array = np.array(list(prob_map.values()))
        p_min = float(np.min(probs_array))
        p_max = float(np.max(probs_array))
        variance = float(np.var(probs_array))

        # Normalized Disagreement Entropy (0 = perfect agreement, 1 = maximum divergence)
        disagreement_entropy = min(1.0, float(math.sqrt(variance) * 3.5))

        # 95% Confidence Interval based on inter-model dispersion
        margin = max(0.04, float(1.96 * math.sqrt(variance)))
        ci_low = max(0.05, consensus_p - margin)
        ci_high = min(0.95, consensus_p + margin)

        return EnsembleProbabilityForecast(
            consensus_p_win=consensus_p,
            p_min_range=p_min,
            p_max_range=p_max,
            confidence_interval_95=(ci_low, ci_high),
            disagreement_entropy=disagreement_entropy,
            active_regime=active_regime,
            model_contributions=weights_map,
            model_probabilities=prob_map,
            is_consensus_clear=disagreement_entropy < 0.40,
        )


model_ensemble_governor = ModelEnsembleGovernor()
