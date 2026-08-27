"""
Meta-Uncertainty Budget & Systemic Entropy Calculator.
Aggregates multi-source uncertainty dimensions:
- Data Quality Uncertainty (feed score & tick latency)
- Analogue Sample Uncertainty (penalizes K < 30)
- Bootstrap Model Disagreement Entropy
- Regime Transition Ambiguity
- Macro Event Shock Uncertainty
Computes composite systemic uncertainty U in [0.0, 1.0] used to discount Net EV and Kelly sizing.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from core.data_quality_gate import QualityCheckResult
from core.analogue_engine import AnalogueDistribution
from core.path_simulator import SimulationCone
from core.event_shock_engine import EventRiskState
from core.regime_transition import RegimeClassificationResult

logger = logging.getLogger("ai_quant_sentinel.uncertainty_engine")


@dataclass
class UncertaintyBudget:
    composite_uncertainty_u: float      # [0.0, 1.0] (0.0 = Absolute Confidence, 1.0 = Total Entropy)
    data_quality_uncertainty: float     # [0.0, 1.0]
    analogue_sample_uncertainty: float  # [0.0, 1.0]
    model_disagreement_entropy: float   # [0.0, 1.0]
    regime_transition_uncertainty: float# [0.0, 1.0]
    event_shock_uncertainty: float      # [0.0, 1.0]
    penalty_factor: float               # Multiplier applied to Net EV
    uncertainty_level: str              # "LOW", "MODERATE", "ELEVATED", "PROHIBITIVE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UncertaintyEngine:
    """Calculates multi-factor systemic uncertainty budget."""

    def compute_budget(
        self,
        data_quality: QualityCheckResult,
        analogue_dist: AnalogueDistribution,
        sim_cone: SimulationCone,
        regime_res: RegimeClassificationResult,
        event_state: EventRiskState,
    ) -> UncertaintyBudget:
        """
        Synthesizes all uncertainty vectors into a unified uncertainty score U.
        """
        # 1. Data Quality Uncertainty
        u_data = 1.0 - data_quality.quality_score

        # 2. Analogue Sample Uncertainty
        u_analogue = analogue_dist.uncertainty_penalty

        # 3. Model Disagreement Entropy
        # Spread between Model A, B, C win rates
        u_models = float(np.clip(sim_cone.tp_sl_uncertainty_spread * 2.5, 0.0, 1.0))

        # 4. Regime Transition Uncertainty
        u_regime = 1.0 - regime_res.confidence
        if regime_res.active_transition.value != "NONE":
            u_regime = min(1.0, u_regime + 0.15)

        # 5. Event Shock Uncertainty
        u_event = 0.50 if event_state.is_event_risk_active else 0.0
        if event_state.trading_lockout:
            u_event = 1.0

        # Weighted Composite Score U in [0.0, 1.0]
        # Weights: Data (0.25), Analogue (0.20), Models (0.25), Regime (0.15), Event (0.15)
        u_composite = (
            0.25 * u_data
            + 0.20 * u_analogue
            + 0.25 * u_models
            + 0.15 * u_regime
            + 0.15 * u_event
        )
        u_composite = float(np.clip(u_composite, 0.0, 1.0))

        penalty_factor = 1.0 + (u_composite * 1.5)  # Penalizes required hurdle

        if u_composite <= 0.25:
            level = "LOW"
        elif u_composite <= 0.50:
            level = "MODERATE"
        elif u_composite <= 0.75:
            level = "ELEVATED"
        else:
            level = "PROHIBITIVE"

        return UncertaintyBudget(
            composite_uncertainty_u=round(u_composite, 3),
            data_quality_uncertainty=round(u_data, 3),
            analogue_sample_uncertainty=round(u_analogue, 3),
            model_disagreement_entropy=round(u_models, 3),
            regime_transition_uncertainty=round(u_regime, 3),
            event_shock_uncertainty=round(u_event, 3),
            penalty_factor=round(penalty_factor, 3),
            uncertainty_level=level,
        )


# Singleton
uncertainty_engine = UncertaintyEngine()
