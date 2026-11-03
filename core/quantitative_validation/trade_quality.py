"""
core/quantitative_validation/trade_quality.py
============================================
Trade Quality Intelligence & Explicit NO_TRADE Decision Architecture.
Evaluates candidate trade opportunities against multi-dimensional criteria:
1. Multi-timeframe trend alignment.
2. Structural liquidity sweeps & order flow confirmation.
3. Volume expansion / displacement.
4. Entry location relative to invalidation (asymmetric R:R).
5. Market regime compatibility (avoids chop and uncalibrated volatility).
6. Net cost-adjusted R:R >= 2.0.

Rewards and formalizes the NO_TRADE decision as first-class capital preservation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NoTradeDecision:
    decision_id: str
    symbol: str
    timeframe: str
    timestamp_ms: int
    regime: str
    rejection_reasons: list[str]
    capital_preserved_usd: float
    epistemic_status: str = "VALIDATED_ABSTENTION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp_ms": self.timestamp_ms,
            "regime": self.regime,
            "rejection_reasons": self.rejection_reasons,
            "capital_preserved_usd": round(self.capital_preserved_usd, 2),
            "epistemic_status": self.epistemic_status,
        }


@dataclass(frozen=True)
class TradeQualityAssessment:
    candidate_id: str
    symbol: str
    timeframe: str
    decision: str  # "ACCEPT_SHADOW" or "NO_TRADE"
    quality_score: float  # 0.0 - 100.0
    trend_alignment: str
    liquidity_evidence: str
    volume_confirmation: str
    cost_adjusted_rr: float
    regime: str
    historical_statistical_support: bool
    explanation: str
    no_trade_decision: NoTradeDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "decision": self.decision,
            "quality_score": round(self.quality_score, 1),
            "trend_alignment": self.trend_alignment,
            "liquidity_evidence": self.liquidity_evidence,
            "volume_confirmation": self.volume_confirmation,
            "cost_adjusted_rr": round(self.cost_adjusted_rr, 2),
            "regime": self.regime,
            "historical_statistical_support": self.historical_statistical_support,
            "explanation": self.explanation,
            "no_trade": self.no_trade_decision.to_dict() if self.no_trade_decision else None,
        }


def evaluate_trade_quality(
    symbol: str,
    timeframe: str,
    raw_rr: float,
    regime: str,
    trend_aligned: bool,
    sweep_confirmed: bool,
    volume_expansion: bool,
    fvg_or_ob_overlap: bool,
    roundtrip_friction_bps: float = 23.0,  # 15 bps slippage + 8 bps fees
    notional_position_usd: float = 2000.0,
) -> TradeQualityAssessment:
    """
    Evaluates candidate trade quality and determines whether to ACCEPT for shadow
    evaluation or emit a structured NO_TRADE capital preservation decision.
    """
    rejection_reasons: list[str] = []
    score = 0.0

    # 1. Structure & Geometry (30 pts)
    if sweep_confirmed:
        score += 15.0
    else:
        rejection_reasons.append("Missing liquidity sweep / reclaim confirmation.")

    if fvg_or_ob_overlap:
        score += 15.0
    else:
        rejection_reasons.append("Entry not anchored in unmitigated FVG or Order Block.")

    # 2. Trend & MTF Context (25 pts)
    if trend_aligned:
        score += 25.0
        trend_status = "STRONG"
    else:
        trend_status = "COUNTER_TREND"
        rejection_reasons.append("Counter-trend direction without HTF exhaustion.")

    # 3. Order Flow & Volume (20 pts)
    if volume_expansion:
        score += 20.0
        vol_status = "EXPANDING"
    else:
        score += 5.0
        vol_status = "LOW_OR_CONTRACTING"
        rejection_reasons.append("Insufficient volume expansion (rVol < 1.35x).")

    # 4. Regime Compatibility (15 pts)
    if regime == "RANGING_CHOP":
        rejection_reasons.append("Market regime is RANGING_CHOP (cash preservation active).")
    elif regime == "VOLATILITY_SHOCK":
        rejection_reasons.append("Market regime is VOLATILITY_SHOCK (uncalibrated variance).")
    else:
        score += 15.0

    # 5. Friction-adjusted Risk/Reward (10 pts)
    # Deduct roundtrip friction from gross R:R
    friction_pct = roundtrip_friction_bps / 10000.0
    cost_adjusted_rr = max(0.0, raw_rr - (friction_pct * 10.0))

    if cost_adjusted_rr >= 2.0:
        score += 10.0
    else:
        rejection_reasons.append(
            f"Cost-adjusted R:R ({cost_adjusted_rr:.2f}) falls below institutional hurdle (2.00)."
        )

    # Acceptance Decision
    # Threshold: Score >= 75.0, cost-adjusted R:R >= 2.0, no fatal regime blocks
    if (
        score >= 75.0
        and cost_adjusted_rr >= 2.0
        and regime not in ("RANGING_CHOP", "VOLATILITY_SHOCK")
    ):
        decision = "ACCEPT_SHADOW"
        explanation = f"Qualified trade setup accepted for shadow evaluation (Quality Score: {score:.1f}/100)."
        no_trade = None
    else:
        decision = "NO_TRADE"
        explanation = f"Setup rejected to preserve capital: {'; '.join(rejection_reasons)}"
        no_trade = NoTradeDecision(
            decision_id=f"NOTRADE_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            timeframe=timeframe,
            timestamp_ms=int(time.time() * 1000),
            regime=regime,
            rejection_reasons=rejection_reasons,
            capital_preserved_usd=notional_position_usd * 0.005,  # 0.5% risk capacity preserved
        )

    return TradeQualityAssessment(
        candidate_id=f"CAND_{uuid.uuid4().hex[:8]}",
        symbol=symbol,
        timeframe=timeframe,
        decision=decision,
        quality_score=score,
        trend_alignment=trend_status,
        liquidity_evidence="CONFIRMED" if sweep_confirmed else "UNCONFIRMED",
        volume_confirmation=vol_status,
        cost_adjusted_rr=cost_adjusted_rr,
        regime=regime,
        historical_statistical_support=score >= 70.0,
        explanation=explanation,
        no_trade_decision=no_trade,
    )
