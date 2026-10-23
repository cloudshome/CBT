"""
core/mastermind/specialist_base.py
==================================
Base Specialist Agent Contract for the SKY Mastermind Swarm.
Each specialist operates on specific asset archetypes (BTC macro, ETH DeFi, SOL velocity,
Meme momentum spike, Low-cap orderbook breakout).
Specialists produce normalized CandidateProposal contracts. They have ZERO direct execution authority.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger(__name__)


class SpecialistArchetype(StrEnum):
    BTC_MACRO_MICROSTRUCTURE = "BTC_MACRO_MICROSTRUCTURE"
    ETH_DEFI_STRUCTURAL = "ETH_DEFI_STRUCTURAL"
    GOLD_MACRO_RESERVE = "GOLD_MACRO_RESERVE"
    SOVEREIGN_MASTER_AGENT = "SOVEREIGN_MASTER_AGENT"
    SOL_HIGH_VELOCITY = "SOL_HIGH_VELOCITY"
    MEME_MOMENTUM_SPIKE = "MEME_MOMENTUM_SPIKE"
    LOW_CAP_BREAKOUT = "LOW_CAP_BREAKOUT"
    DYNAMIC_OPPORTUNITY_HUNTER = "DYNAMIC_OPPORTUNITY_HUNTER"


class EpistemicGrade(StrEnum):
    """
    Epistemic taxonomy grade classifying the certainty of claims in CandidateProposals.
    Strictly separates verifiable facts from mathematical inferences, hypotheses, and forecasts.
    """
    FACT = "FACT"                  # Direct, observable market data (e.g. current bid/ask, exact volume, candle close)
    INFERENCE = "INFERENCE"        # Derived indicator calculation (e.g. RSI, ATR ratio, CVD divergence)
    HYPOTHESIS = "HYPOTHESIS"      # Testable structural setup (e.g. order block retest, FVG retest, sweep continuation)
    FORECAST = "FORECAST"          # Forward probabilistic projection (e.g. target price, net expected value)
    UNVERIFIED = "UNVERIFIED"      # Missing timestamps or uncorroborated telemetry


@dataclass
class CandidateProposal:
    """
    Normalized proposal produced by an asset specialist.
    Must be reviewed and sized by the Mastermind Arbiter Council and Authoritative Risk Manager.
    """

    proposal_id: str
    specialist_id: str
    archetype: SpecialistArchetype
    symbol: str
    direction: DecisionAction  # LONG, SHORT, NO_TRADE, WATCH
    thesis: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    expected_value_r: float
    confidence_score: float  # [0.0, 1.0]
    invalidation_condition: str
    suggested_notional_usd: float
    telemetry: dict[str, Any] = field(default_factory=dict)
    disconfirming_evidence: list[str] = field(default_factory=list)
    epistemic_grade: EpistemicGrade = EpistemicGrade.HYPOTHESIS
    alternative_explanation: str = ""
    falsification_conditions: list[str] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["direction"] = (
            self.direction.value if isinstance(self.direction, DecisionAction) else self.direction
        )
        d["archetype"] = (
            self.archetype.value
            if isinstance(self.archetype, SpecialistArchetype)
            else self.archetype
        )
        d["epistemic_grade"] = (
            self.epistemic_grade.value
            if isinstance(self.epistemic_grade, EpistemicGrade)
            else self.epistemic_grade
        )
        return d


class BaseSpecialistAgent(ABC):
    """
    Abstract Base Class for Mastermind Specialists.
    Enforces Phase 1 Adversarial Self-Review and Epistemic Integrity.
    """

    def __init__(
        self, specialist_id: str, archetype: SpecialistArchetype, target_symbol: str
    ) -> None:
        self.specialist_id = specialist_id
        self.archetype = archetype
        self.target_symbol = target_symbol
        self.last_proposal: CandidateProposal | None = None

    def find_falsifying_evidence(
        self,
        candidate_direction: DecisionAction,
        candles_15m: list[dict[str, Any]],
        order_book: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        Adversarial self-review searching for disconfirming market evidence.
        Actively checks for exhaustion wicks, order book resistance walls, and volume divergence.
        """
        disconfirming: list[str] = []
        if not candles_15m or len(candles_15m) < 5:
            return disconfirming

        latest = candles_15m[-1]
        c = float(latest.get("close", 0.0))
        h = float(latest.get("high", 0.0))
        l = float(latest.get("low", 0.0))
        vol = float(latest.get("volume", 0.0))

        # 1. Price Wick Rejection Check (using 1e-12 epsilon to support low-cap/sub-cent tokens)
        bar_range = h - l
        if bar_range > 1e-12:
            close_position = (c - l) / bar_range
            if candidate_direction == DecisionAction.LONG:
                # Trapped buyers: close in bottom 35% of bar range
                if close_position < 0.35:
                    disconfirming.append(
                        f"Upper rejection wick detected (close at {close_position:.1%} of bar range); indicates heavy overhead supply / trapped longs."
                    )
            elif candidate_direction == DecisionAction.SHORT:
                # Absorption: close in top 35% of bar range
                if close_position > 0.65:
                    disconfirming.append(
                        f"Lower absorption wick detected (close at {close_position:.1%} of bar range); indicates aggressive demand / trapped shorts."
                    )

        # 2. Volume Divergence Check
        recent_vols = [float(b.get("volume", 0.0)) for b in candles_15m[-10:-1]]
        avg_vol = sum(recent_vols) / max(1, len(recent_vols))
        if avg_vol > 0 and (vol / avg_vol) < 0.50 and candidate_direction in (DecisionAction.LONG, DecisionAction.SHORT):
            disconfirming.append(
                f"Severe volume dry-up ({vol/avg_vol:.2f}x avg); move lacks institutional expansion volume."
            )

        # 3. Order Book Depth Wall Check (if L2 available)
        if order_book and isinstance(order_book, dict):
            bids = order_book.get("bids", [])
            asks = order_book.get("asks", [])
            if bids and asks:
                bid_vol = sum(float(s) for _, s in bids[:5])
                ask_vol = sum(float(s) for _, s in asks[:5])
                if candidate_direction == DecisionAction.LONG and ask_vol > 2.5 * max(1e-6, bid_vol):
                    disconfirming.append(
                        f"Severe ask-side liquidity wall detected ({ask_vol/max(1e-6, bid_vol):.1f}x bid depth); strong overhead resistance."
                    )
                elif candidate_direction == DecisionAction.SHORT and bid_vol > 2.5 * max(1e-6, ask_vol):
                    disconfirming.append(
                        f"Severe bid-side liquidity cushion detected ({bid_vol/max(1e-6, ask_vol):.1f}x ask depth); strong underlying support."
                    )

        return disconfirming

    def apply_adversarial_review(
        self,
        proposal: CandidateProposal,
        candles_15m: list[dict[str, Any]],
        order_book: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        """
        Subjects CandidateProposal to adversarial self-review.
        If disconfirming evidence is detected, demotes confidence or pivots to NO_TRADE/WATCH.
        """
        if proposal.direction not in (DecisionAction.LONG, DecisionAction.SHORT):
            return proposal

        disconfirming = self.find_falsifying_evidence(
            candidate_direction=proposal.direction,
            candles_15m=candles_15m,
            order_book=order_book,
        )

        if not disconfirming:
            proposal.falsification_conditions = [
                f"Close beyond invalidation level {proposal.stop_loss:.4f}",
                "Opposing high-volume order flow displacement",
            ]
            return proposal

        proposal.disconfirming_evidence.extend(disconfirming)

        # If 2 or more disconfirming signals (or severe rejection wick), force NO_TRADE
        if len(disconfirming) >= 2 or any("rejection wick" in e or "absorption wick" in e for e in disconfirming):
            logger.warning(
                "Specialist %s [%s] adversarial review triggered veto on %s: %s",
                self.specialist_id,
                self.target_symbol,
                proposal.direction.value,
                "; ".join(disconfirming),
            )
            proposal.direction = DecisionAction.NO_TRADE
            proposal.confidence_score = min(proposal.confidence_score, 0.25)
            proposal.expected_value_r = 0.0
            proposal.alternative_explanation = (
                f"Setup negated by adversarial evidence: {'; '.join(disconfirming)}"
            )
            proposal.thesis = f"[VETOED BY ADVERSARIAL REVIEW] {proposal.thesis}"
        else:
            # Single moderate contradiction: discount confidence score by 35%
            proposal.confidence_score = round(proposal.confidence_score * 0.65, 3)
            proposal.alternative_explanation = (
                f"Elevated risk due to partial contradiction: {'; '.join(disconfirming)}"
            )

        return proposal

    @abstractmethod
    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        """
        Evaluates market data and produces a structured CandidateProposal.
        """
        pass
