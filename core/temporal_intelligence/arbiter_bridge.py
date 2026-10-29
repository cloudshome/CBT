"""
core/temporal_intelligence/arbiter_bridge.py
============================================
Read-Only Temporal Forecast Evidence Bridge to Mastermind Arbiter Council (Milestone 22).

Enforces:
- FORECAST != SIGNAL: Provides evidentiary probability context, never direct order execution.
- Read-only evidence feed to Mastermind Arbiter Council.
- Advises NO_TRADE or demotes confidence when temporal forecast uncertainty is elevated.
- Zero bypass of Master Risk Gate.
"""

from __future__ import annotations

import logging
from typing import Any

from core.temporal_intelligence.forecaster import TemporalPriceActionForecaster
from core.temporal_intelligence.models import ForecastHorizon

logger = logging.getLogger("sky.temporal.arbiter_bridge")


class TemporalArbiterBridge:
    """Provides temporal forecast probabilities and uncertainty context to Mastermind Arbiter."""

    def __init__(self, forecaster: TemporalPriceActionForecaster) -> None:
        self.forecaster = forecaster

    def get_temporal_evidence(
        self,
        symbol: str,
        candles: list[dict[str, Any]],
        horizon: ForecastHorizon = ForecastHorizon.H_15M,
    ) -> dict[str, Any]:
        """
        Computes the point-in-time forecast and formats evidentiary metrics for Arbiter deliberation.
        """
        if not candles or len(candles) < 20:
            return {
                "has_forecast": False,
                "advisory": "NO_FORECAST",
                "reason": "Insufficient candle history (< 20 bars)",
                "confidence_scale": 1.0,
            }

        fc = self.forecaster.forecast(candles, symbol=symbol, horizon=horizon)
        if not fc:
            return {
                "has_forecast": False,
                "advisory": "NO_FORECAST",
                "reason": "Feature extraction failed",
                "confidence_scale": 1.0,
            }

        # Formulate Advisory:
        # High uncertainty or high range probability -> scale down confidence
        confidence_scale = 1.0
        if fc.epistemic_uncertainty >= 0.60 or fc.prob_range >= 0.50:
            advisory = "ADVISE_NO_TRADE"
            confidence_scale = 0.70  # Discount confidence due to temporal chop
        elif fc.prob_pump >= 0.50:
            advisory = "FAVORS_LONG"
            confidence_scale = 1.10
        elif fc.prob_dump >= 0.50:
            advisory = "FAVORS_SHORT"
            confidence_scale = 1.10
        else:
            advisory = "NEUTRAL"
            confidence_scale = 1.0

        return {
            "has_forecast": True,
            "forecast_id": fc.forecast_id,
            "horizon": fc.horizon.value,
            "prob_pump": fc.prob_pump,
            "prob_dump": fc.prob_dump,
            "prob_range": fc.prob_range,
            "expected_return_pct": fc.expected_return_pct,
            "epistemic_uncertainty": fc.epistemic_uncertainty,
            "brier_skill_score": fc.brier_skill_score,
            "active_laws": fc.active_law_ids,
            "advisory": advisory,
            "confidence_scale": confidence_scale,
        }
