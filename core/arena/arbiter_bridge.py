"""
core/arena/arbiter_bridge.py
============================
Read-Only Qualification & Risk-Information Bridge between the Darwinian Arena and Mastermind Arbiter Council.

Enforces:
- Read-only qualification reporting.
- The 1.2x winner multiplier is strictly disabled: arena outperformance does not automatically
  grant oversized authority on the master $10,000 portfolio.
- Veto Primacy: A QUARANTINED or REJECTED arena specialist is disqualified from submitting
  proposals to the master portfolio.
- Zero dilution of Master Risk Gate authority.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from core.arena.engine import DarwinianArenaEngine
from core.arena.models import SpecialistSurvivalStatus

logger = logging.getLogger("sky.arena.arbiter_bridge")


@dataclass(frozen=True)
class ArenaBridgeAssessment:
    is_eligible: bool
    status: SpecialistSurvivalStatus
    alpha_vs_benchmark_pct: float
    max_drawdown_pct: float
    rejection_reason: str | None
    weight_multiplier: float


class ArenaArbiterBridge:
    """Provides read-only survival status and qualification gating to Mastermind Arbiter Council."""

    def __init__(self, arena_engine: DarwinianArenaEngine) -> None:
        self.arena_engine = arena_engine

    def evaluate_specialist_for_mastermind(self, symbol: str) -> ArenaBridgeAssessment:
        """
        Queries the arena status for a given symbol:
        - QUARANTINED / REJECTED -> is_eligible = False, weight = 0.0, proposal rejected.
        - PROBATION -> is_eligible = True, weight = 0.5 (penalized sizing).
        - SURVIVING / PAPER_QUALIFIED -> is_eligible = True, weight = 1.0 (standard sizing).
        """
        account = self.arena_engine.get_specialist_by_symbol(symbol)
        if not account:
            # If asset is not in the arena universe, allow normal mastermind evaluation
            return ArenaBridgeAssessment(
                is_eligible=True,
                status=SpecialistSurvivalStatus.SURVIVING,
                alpha_vs_benchmark_pct=0.0,
                max_drawdown_pct=0.0,
                rejection_reason=None,
                weight_multiplier=1.0,
            )

        if account.status in (SpecialistSurvivalStatus.QUARANTINED, SpecialistSurvivalStatus.REJECTED):
            reason = (
                f"Darwinian Arena Veto: Specialist for {symbol} is {account.status.value} "
                f"(Drawdown: {account.max_drawdown_pct:.1f}%, Reason: {account.quarantine_reason or 'Risk limit breached'})."
            )
            return ArenaBridgeAssessment(
                is_eligible=False,
                status=account.status,
                alpha_vs_benchmark_pct=account.alpha_vs_benchmark_pct,
                max_drawdown_pct=account.max_drawdown_pct,
                rejection_reason=reason,
                weight_multiplier=0.0,
            )

        if account.status == SpecialistSurvivalStatus.PROBATION:
            return ArenaBridgeAssessment(
                is_eligible=True,
                status=account.status,
                alpha_vs_benchmark_pct=account.alpha_vs_benchmark_pct,
                max_drawdown_pct=account.max_drawdown_pct,
                rejection_reason=None,
                weight_multiplier=0.5,
            )

        # SURVIVING or PAPER_QUALIFIED (1.2x winner multiplier is strictly disabled per directive)
        return ArenaBridgeAssessment(
            is_eligible=True,
            status=account.status,
            alpha_vs_benchmark_pct=account.alpha_vs_benchmark_pct,
            max_drawdown_pct=account.max_drawdown_pct,
            rejection_reason=None,
            weight_multiplier=1.0,
        )
