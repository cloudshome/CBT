"""
core/execution/cross_venue/latency_penalty.py
=============================================
Milestone 43: Latency-Decay & Adverse Selection Penalty Modeler.

Mathematical Formulation:
- In competitive high-frequency and cross-venue arbitrage, price dislocations
  exhibit an exponential half-life due to competing algorithmic solvers and taker flow:
      P_fill(Delta_t) = exp( - lambda_decay * Delta_t )
- Hazard rate lambda_decay is dynamically calibrated by flow toxicity and market volatility:
      lambda_decay = lambda_base * (1.0 + beta_vpin * VPIN + gamma_vol * Volatility)
- Expected Arbitrage Payoff considering partial execution failure:
      E[Payoff] = P_fill(Delta_t) * NetSpread - (1.0 - P_fill(Delta_t)) * AdversePenalty
- Any path with E[Payoff] <= HurdleRate is rejected prior to routing.

Constitutional Invariant:
- real_capital_enabled: bool = False.
- Causal cutoff: Uses only information available at event arrival time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class LatencyDecayAssessment:
    """Quantitative report on latency decay and fill survivability."""
    total_latency_ms: float
    hazard_rate_hz: float
    fill_probability: float
    decay_probability: float
    expected_payoff_usd: float
    adverse_selection_cost_usd: float
    is_favorable: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_latency_ms": self.total_latency_ms,
            "hazard_rate_hz": self.hazard_rate_hz,
            "fill_probability": round(self.fill_probability, 4),
            "decay_probability": round(self.decay_probability, 4),
            "expected_payoff_usd": round(self.expected_payoff_usd, 2),
            "adverse_selection_cost_usd": round(self.adverse_selection_cost_usd, 2),
            "is_favorable": self.is_favorable,
        }


class LatencyPenaltyModeler:
    """
    Evaluates adverse selection risk and probability of dislocation vanishing in flight.
    """

    def __init__(
        self,
        base_hazard_rate_hz: float = 0.005,  # 5 Hz base event rate
        vpin_sensitivity: float = 2.0,
        vol_sensitivity: float = 1.5,
    ):
        self.base_hazard_rate_hz = base_hazard_rate_hz
        self.vpin_sensitivity = vpin_sensitivity
        self.vol_sensitivity = vol_sensitivity

    def compute_hazard_rate(self, vpin: float = 0.20, realized_vol_ann: float = 0.50) -> float:
        """Calculates dynamic hazard decay parameter lambda."""
        vpin_clamped = max(0.0, min(1.0, vpin))
        vol_clamped = max(0.0, min(2.0, realized_vol_ann))
        return self.base_hazard_rate_hz * (
            1.0 + self.vpin_sensitivity * vpin_clamped + self.vol_sensitivity * vol_clamped
        )

    def evaluate_opportunity_survivability(
        self,
        total_latency_ms: float,
        net_spread_bps: float,
        notional_usd: float,
        vpin: float = 0.20,
        realized_vol_ann: float = 0.50,
        hurdle_pnl_usd: float = 1.0,
    ) -> LatencyDecayAssessment:
        """
        Computes fill probability and expected profit after latency drag.
        """
        hazard_rate = self.compute_hazard_rate(vpin, realized_vol_ann)
        # Latency in seconds
        delta_t_sec = max(0.001, total_latency_ms / 1000.0)

        # Exponential survival probability
        fill_prob = math.exp(-hazard_rate * delta_t_sec)
        decay_prob = 1.0 - fill_prob

        gross_potential_pnl = notional_usd * (net_spread_bps / 10000.0)
        # Adverse selection penalty if the dislocation moved against us
        # Conservative model: lose 0.5x the spread on failed leg unwind
        adverse_selection_cost = notional_usd * ((net_spread_bps * 0.5) / 10000.0)

        expected_payoff = (fill_prob * gross_potential_pnl) - (decay_prob * adverse_selection_cost)
        is_favorable = expected_payoff >= hurdle_pnl_usd and fill_prob >= 0.50

        return LatencyDecayAssessment(
            total_latency_ms=total_latency_ms,
            hazard_rate_hz=round(hazard_rate, 4),
            fill_probability=fill_prob,
            decay_probability=decay_prob,
            expected_payoff_usd=expected_payoff,
            adverse_selection_cost_usd=adverse_selection_cost,
            is_favorable=is_favorable,
        )


# Global singleton
latency_penalty_modeler = LatencyPenaltyModeler()
