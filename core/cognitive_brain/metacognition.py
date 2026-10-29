"""
core/cognitive_brain/metacognition.py
====================================
Metacognitive Self-Monitoring & Uncertainty Governance Engine.

Monitors:
1. Data completeness, feed freshness, and out-of-distribution indicators.
2. Specialist consensus vs disagreement dispersion.
3. Historical calibration status from the prediction ledger.
4. Epistemic uncertainty limits triggering explicit ABSTAIN recommendations.

Constitutional Governance Invariant:
Metacognition can only RECOMMEND ABSTENTION or DOWN-GRADE confidence.
It can NEVER authorize trades, weaken deterministic risk limits, or override Guard 1.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from core.cognitive_brain.prediction_ledger import CognitivePredictionLedger
from core.cognitive_brain.world_model import MarketRegimeType, WorldModelState
from core.mastermind.specialist_base import CandidateProposal
from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger("ai_quant_sentinel.cognitive_brain.metacognition")


class MetacognitiveAdvice(StrEnum):
    """Metacognitive recommendation for the Mastermind Arbiter."""

    PROCEED = "PROCEED"
    CAUTION = "CAUTION"
    ABSTAIN = "ABSTAIN"
    QUARANTINE = "QUARANTINE"


class MetacognitiveAssessment(BaseModel):
    """Structured metacognitive audit report evaluated before trade sizing."""

    advice: MetacognitiveAdvice
    confidence_scale_factor: float = Field(ge=0.0, le=1.0)
    data_quality_acceptable: bool = True
    calibration_status: str = "UNVERIFIED"
    disagreement_dispersion: float = 0.0  # [0.0, 1.0] (0 = unanimous, 1 = maximum conflict)
    uncertainty_level: float = 0.0
    rationale: list[str] = Field(default_factory=list)
    can_execute: bool = True


class MetacognitiveMonitor:
    """
    Evaluates system uncertainty, data integrity, and specialist disagreement.
    Produces binding recommendations to enforce disciplined non-action when appropriate.
    """

    def __init__(self, ledger: CognitivePredictionLedger | None = None) -> None:
        self.ledger = ledger

    def evaluate_decision_context(
        self,
        world_state: WorldModelState,
        proposals: list[CandidateProposal],
        target_asset: str | None = None,
    ) -> MetacognitiveAssessment:
        """
        Synthesizes a structured metacognitive assessment.
        """
        rationale: list[str] = []
        scale_factor = 1.0
        can_execute = True

        # 1. Out of Distribution / Stale Data Check
        if world_state.is_out_of_distribution or world_state.primary_regime == MarketRegimeType.OUT_OF_DISTRIBUTION:
            rationale.append("Market is OUT_OF_DISTRIBUTION or data feed is stale; mandatory ABSTENTION enforced.")
            return MetacognitiveAssessment(
                advice=MetacognitiveAdvice.ABSTAIN,
                confidence_scale_factor=0.0,
                data_quality_acceptable=False,
                uncertainty_level=world_state.epistemic_uncertainty,
                rationale=rationale,
                can_execute=False,
            )

        if world_state.primary_regime == MarketRegimeType.UNKNOWN:
            rationale.append("Market regime UNKNOWN due to missing features; recommend ABSTAIN.")
            return MetacognitiveAssessment(
                advice=MetacognitiveAdvice.ABSTAIN,
                confidence_scale_factor=0.0,
                data_quality_acceptable=False,
                uncertainty_level=1.0,
                rationale=rationale,
                can_execute=False,
            )

        # 2. Elevated Epistemic Uncertainty Check
        if world_state.epistemic_uncertainty > 0.70:
            scale_factor *= 0.60
            rationale.append(f"Elevated regime uncertainty ({world_state.epistemic_uncertainty:.2f} > 0.70); scaled down confidence by 40%.")

        # 3. Specialist Disagreement Dispersion
        active_directions = [p.direction for p in proposals if p.direction in (DecisionAction.LONG, DecisionAction.SHORT)]
        has_long = DecisionAction.LONG in active_directions
        has_short = DecisionAction.SHORT in active_directions

        dispersion = 0.0
        if has_long and has_short:
            dispersion = 1.0
            scale_factor *= 0.50
            rationale.append("Severe specialist conflict: opposing LONG and SHORT proposals exist concurrently; 50% sizing discount applied.")

        # 4. Calibration Track Record (if ledger available)
        calibration_status = "UNVERIFIED"
        if self.ledger:
            try:
                with self.ledger._get_connection() as conn:
                    row = conn.execute(
                        "SELECT COUNT(*), AVG(brier_score) FROM cognitive_experience_ledger WHERE resolution_status != 'PENDING' AND brier_score IS NOT NULL"
                    ).fetchone()
                    n = row[0] if row else 0
                    avg_brier = row[1] if row and row[1] is not None else None

                    if n < 10:
                        calibration_status = "INSUFFICIENT_SAMPLES"
                        rationale.append(f"Track record sample size N={n} < 10; calibration unverified.")
                    elif avg_brier is not None:
                        if avg_brier > 0.25:
                            calibration_status = "DEGRADED"
                            scale_factor *= 0.75
                            rationale.append(f"Historical Brier score degraded ({avg_brier:.3f} > 0.25); applied 25% caution haircut.")
                        else:
                            calibration_status = "WELL_CALIBRATED"
            except Exception as e:
                logger.warning("Error checking calibration in metacognition: %s", e)

        # 5. Determine Overall Advice
        if scale_factor <= 0.25:
            advice = MetacognitiveAdvice.ABSTAIN
            can_execute = False
        elif scale_factor < 0.70 or dispersion > 0.5:
            advice = MetacognitiveAdvice.CAUTION
        else:
            advice = MetacognitiveAdvice.PROCEED

        return MetacognitiveAssessment(
            advice=advice,
            confidence_scale_factor=round(scale_factor, 3),
            data_quality_acceptable=True,
            calibration_status=calibration_status,
            disagreement_dispersion=dispersion,
            uncertainty_level=world_state.epistemic_uncertainty,
            rationale=rationale,
            can_execute=can_execute,
        )

