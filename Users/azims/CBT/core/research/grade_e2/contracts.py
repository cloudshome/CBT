"""
core/research/grade_e2/contracts.py
===================================
Grade-E2 Type Contracts, Enums, and Dataclasses.

Epistemic Guardrail:
Certified strictly as `GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE`.
Zero live order placement, zero capital allocation, zero M18 certified surface modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

E2_EVIDENCE_GRADE: Literal["GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE"] = (
    "GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE"
)


class ToxicityState(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH_TOXICITY = "HIGH_TOXICITY"


class VolatilityRegime(StrEnum):
    CALM = "CALM"
    NORMAL = "NORMAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EXPLOSIVE = "EXPLOSIVE"


class PeggingMode(StrEnum):
    STATIC_HALF_SPREAD = "STATIC_HALF_SPREAD"
    VOLATILITY_SCALED = "VOLATILITY_SCALED"
    DYNAMIC_PEGGED = "DYNAMIC_PEGGED"


@dataclass(frozen=True)
class DefenseEvaluation:
    """Outcome of pre-trade microstructure filter evaluation."""

    is_order_permitted: bool
    toxicity_score: float
    volatility_bps: float
    volatility_regime: VolatilityRegime
    recommended_offset_bps: float
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_order_permitted": self.is_order_permitted,
            "toxicity_score": round(self.toxicity_score, 4),
            "volatility_bps": round(self.volatility_bps, 2),
            "volatility_regime": self.volatility_regime.value,
            "recommended_offset_bps": round(self.recommended_offset_bps, 2),
            "rejection_reason": self.rejection_reason,
        }
