"""
core/mastermind/specialist_base.py
==================================
Base Specialist Agent Contract for the SKY Mastermind Swarm.
Each specialist operates on specific asset archetypes (BTC macro, ETH DeFi, SOL velocity,
Meme momentum spike, Low-cap orderbook breakout).
Specialists produce normalized CandidateProposal contracts. They have ZERO direct execution authority.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from core.sky_intelligence.types import DecisionAction


class SpecialistArchetype(StrEnum):
    BTC_MACRO_MICROSTRUCTURE = "BTC_MACRO_MICROSTRUCTURE"
    ETH_DEFI_STRUCTURAL = "ETH_DEFI_STRUCTURAL"
    SOL_HIGH_VELOCITY = "SOL_HIGH_VELOCITY"
    MEME_MOMENTUM_SPIKE = "MEME_MOMENTUM_SPIKE"
    LOW_CAP_BREAKOUT = "LOW_CAP_BREAKOUT"


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
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.direction.value if isinstance(self.direction, DecisionAction) else self.direction
        d["archetype"] = self.archetype.value if isinstance(self.archetype, SpecialistArchetype) else self.archetype
        return d


class BaseSpecialistAgent(ABC):
    """
    Abstract Base Class for Mastermind Specialists.
    """

    def __init__(self, specialist_id: str, archetype: SpecialistArchetype, target_symbol: str) -> None:
        self.specialist_id = specialist_id
        self.archetype = archetype
        self.target_symbol = target_symbol
        self.last_proposal: CandidateProposal | None = None

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
