"""
core/arena/survival.py
======================
Deterministic Evidence-Based Survival & Elimination State Machine (Milestone 21).

States:
- RESEARCH: Strategy being specified/backtested, not eligible for Mastermind proposals.
- SURVIVING: Healthy risk metrics, normal paper trading.
- PROBATION: Drawdown >= 10.0%, authority discounted by 50%.
- QUARANTINED: Drawdown >= 20.0% or 5 consecutive negative EV losses, trading suspended.
- PAPER_QUALIFIED: Consistently outperforming benchmark over 10+ trades with < 5% drawdown.
- REJECTED: Terminal failure or permanent disqualification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.arena.models import ArenaSpecialistAccount, SpecialistSurvivalStatus

logger = logging.getLogger("sky.arena.survival")


@dataclass(frozen=True)
class SurvivalEvaluationResult:
    new_status: SpecialistSurvivalStatus
    status_changed: bool
    reason: str
    is_active: bool
    is_mastermind_eligible: bool
    arbiter_weight_multiplier: float


class SurvivalStateMachine:
    """Evaluates specialist metrics against hard risk limits and statistical survival gates."""

    def __init__(
        self,
        drawdown_probation_pct: float = 10.0,
        drawdown_quarantine_pct: float = 20.0,
        consecutive_losses_quarantine: int = 5,
        min_trades_for_qualification: int = 10,
        min_alpha_for_qualification_pct: float = 2.0,
    ) -> None:
        self.drawdown_probation_pct = drawdown_probation_pct
        self.drawdown_quarantine_pct = drawdown_quarantine_pct
        self.consecutive_losses_quarantine = consecutive_losses_quarantine
        self.min_trades_for_qualification = min_trades_for_qualification
        self.min_alpha_for_qualification_pct = min_alpha_for_qualification_pct

    def evaluate(self, account: ArenaSpecialistAccount) -> SurvivalEvaluationResult:
        current_status = account.status

        # 1. Terminal Rejection check: If already REJECTED, status is permanent
        if current_status == SpecialistSurvivalStatus.REJECTED:
            return SurvivalEvaluationResult(
                new_status=SpecialistSurvivalStatus.REJECTED,
                status_changed=False,
                reason=account.quarantine_reason or "Specialist permanently rejected",
                is_active=False,
                is_mastermind_eligible=False,
                arbiter_weight_multiplier=0.0,
            )

        # 2. Hard Risk Kill Switch: Drawdown >= 20% or 5 consecutive losses -> QUARANTINED
        if account.max_drawdown_pct >= self.drawdown_quarantine_pct:
            reason = f"Max drawdown ({account.max_drawdown_pct:.1f}%) breached {self.drawdown_quarantine_pct:.1f}% threshold"
            return SurvivalEvaluationResult(
                new_status=SpecialistSurvivalStatus.QUARANTINED,
                status_changed=current_status != SpecialistSurvivalStatus.QUARANTINED,
                reason=reason,
                is_active=False,
                is_mastermind_eligible=False,
                arbiter_weight_multiplier=0.0,
            )

        if account.consecutive_losses >= self.consecutive_losses_quarantine:
            reason = f"Consecutive loss streak ({account.consecutive_losses}) breached limit ({self.consecutive_losses_quarantine})"
            return SurvivalEvaluationResult(
                new_status=SpecialistSurvivalStatus.QUARANTINED,
                status_changed=current_status != SpecialistSurvivalStatus.QUARANTINED,
                reason=reason,
                is_active=False,
                is_mastermind_eligible=False,
                arbiter_weight_multiplier=0.0,
            )

        # 3. Probation Check: Drawdown >= 10% -> PROBATION
        if account.max_drawdown_pct >= self.drawdown_probation_pct:
            reason = f"Drawdown ({account.max_drawdown_pct:.1f}%) in probation band ({self.drawdown_probation_pct:.1f}% - {self.drawdown_quarantine_pct:.1f}%)"
            return SurvivalEvaluationResult(
                new_status=SpecialistSurvivalStatus.PROBATION,
                status_changed=current_status != SpecialistSurvivalStatus.PROBATION,
                reason=reason,
                is_active=True,
                is_mastermind_eligible=True,
                arbiter_weight_multiplier=0.5,
            )

        # 4. Evidence-Based Qualification Check: 10+ trades, drawdown < 5%, alpha >= 2.0%
        if (
            account.total_trades >= self.min_trades_for_qualification
            and account.max_drawdown_pct < 5.0
            and account.alpha_vs_benchmark_pct >= self.min_alpha_for_qualification_pct
        ):
            reason = (
                f"Qualified: {account.total_trades} trades, Alpha +{account.alpha_vs_benchmark_pct:.1f}%, "
                f"Drawdown {account.max_drawdown_pct:.1f}%"
            )
            return SurvivalEvaluationResult(
                new_status=SpecialistSurvivalStatus.PAPER_QUALIFIED,
                status_changed=current_status != SpecialistSurvivalStatus.PAPER_QUALIFIED,
                reason=reason,
                is_active=True,
                is_mastermind_eligible=True,
                arbiter_weight_multiplier=1.0,  # Note: 1.2x winner multiplier intentionally disabled per directive!
            )

        # 5. Nominal Surviving State
        reason = f"Surviving: DD {account.max_drawdown_pct:.1f}%, Alpha {account.alpha_vs_benchmark_pct:+.1f}%"
        return SurvivalEvaluationResult(
            new_status=SpecialistSurvivalStatus.SURVIVING,
            status_changed=current_status != SpecialistSurvivalStatus.SURVIVING,
            reason=reason,
            is_active=True,
            is_mastermind_eligible=True,
            arbiter_weight_multiplier=1.0,
        )

