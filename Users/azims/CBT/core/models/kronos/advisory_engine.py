"""
Advisory Shadow Engine for Kronos Integration in Paper Trading.
Logs hypothetical entries and counterfactual outcomes without bypassing the deterministic risk gate.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from core.models.kronos.adapter import KronosModelAdapter, kronos_adapter
from core.models.kronos.calibration import kronos_probability_calibrator
from core.models.kronos.schemas import KronosForecast

logger = logging.getLogger("ai_quant_sentinel.kronos.advisory")


@dataclass
class KronosAdvisoryVerdict:
    symbol: str
    timeframe: str
    timestamp_ms: int
    sky_decision: str
    kronos_bias: str
    forecast_expected_return_pct: float
    calibrated_win_probability: float
    model_uncertainty: float
    advisory_recommendation: str  # "CONFIRM_TRADE", "DIVERGENCE_CAUTION", "VETO_TRADE", "NEUTRAL"
    sizing_multiplier: float  # [0.0, 1.25]
    narrative: str
    evidence_grade: str = "SIMULATED"
    is_tradeable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp_ms": self.timestamp_ms,
            "sky_decision": self.sky_decision,
            "kronos_bias": self.kronos_bias,
            "forecast_expected_return_pct": round(self.forecast_expected_return_pct, 4),
            "calibrated_win_probability": round(self.calibrated_win_probability, 3),
            "model_uncertainty": round(self.model_uncertainty, 3),
            "advisory_recommendation": self.advisory_recommendation,
            "sizing_multiplier": round(self.sizing_multiplier, 2),
            "narrative": self.narrative,
            "evidence_grade": self.evidence_grade,
            "is_tradeable": self.is_tradeable,
        }


class KronosAdvisoryEngine:
    """Evaluates Kronos forecasts as an advisory overlay on SKY setups."""

    def __init__(self, adapter: KronosModelAdapter | None = None):
        self.adapter = adapter or kronos_adapter

    def evaluate_advisory(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        sky_decision: str,
        horizon: int = 12,
    ) -> KronosAdvisoryVerdict:
        now_ts = int(time.time() * 1000)

        # 1. Run inference
        forecast: KronosForecast = self.adapter.predict(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            horizon=horizon,
            sample_count=5,
        )

        # 2. Calibrate win probability
        calibrated_p = kronos_probability_calibrator.calibrate(
            raw_consensus=forecast.directional_consensus,
            model_uncertainty=forecast.model_uncertainty,
            symbol=symbol,
            timeframe=timeframe,
        )

        # 3. Formulate advisory recommendation
        bias = forecast.directional_bias
        multiplier = 1.0

        if sky_decision == "LONG":
            if bias == "BULLISH" and forecast.model_uncertainty < 0.40:
                rec = "CONFIRM_TRADE"
                multiplier = 1.15
                narrative = f"Kronos neural paths strongly confirm LONG setup (consensus {forecast.directional_consensus * 100:.0f}%, exp ret {forecast.expected_return_pct * 100:+.2f}%)."
            elif bias == "BEARISH":
                rec = "DIVERGENCE_CAUTION"
                multiplier = 0.50
                narrative = f"DIVERGENCE: SKY suggests LONG, but Kronos neural paths project BEARISH trajectory ({forecast.expected_return_pct * 100:+.2f}%)."
            else:
                rec = "NEUTRAL"
                narrative = "Kronos is neutral; proceeding with standard SKY risk parameters."

        elif sky_decision == "SHORT":
            if bias == "BEARISH" and forecast.model_uncertainty < 0.40:
                rec = "CONFIRM_TRADE"
                multiplier = 1.15
                narrative = f"Kronos neural paths strongly confirm SHORT setup (consensus {forecast.directional_consensus * 100:.0f}%, exp ret {forecast.expected_return_pct * 100:+.2f}%)."
            elif bias == "BULLISH":
                rec = "DIVERGENCE_CAUTION"
                multiplier = 0.50
                narrative = f"DIVERGENCE: SKY suggests SHORT, but Kronos neural paths project BULLISH trajectory ({forecast.expected_return_pct * 100:+.2f}%)."
            else:
                rec = "NEUTRAL"
                narrative = "Kronos is neutral; proceeding with standard SKY risk parameters."

        else:
            rec = "NEUTRAL"
            multiplier = 0.0
            narrative = f"SKY decision is {sky_decision}; Kronos remains in advisory standby."

        return KronosAdvisoryVerdict(
            symbol=symbol,
            timeframe=timeframe,
            timestamp_ms=now_ts,
            sky_decision=sky_decision,
            kronos_bias=bias,
            forecast_expected_return_pct=forecast.expected_return_pct,
            calibrated_win_probability=calibrated_p,
            model_uncertainty=forecast.model_uncertainty,
            advisory_recommendation=rec,
            sizing_multiplier=multiplier,
            narrative=narrative,
        )


kronos_advisory_engine = KronosAdvisoryEngine()
