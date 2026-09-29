"""
core/kronos/research/promotion_gate.py
======================================
Milestone K9.11: Research Governance State Machine & Promotion Gate.
Evaluates multi-attribute evidence scorecards and assigns research governance states:
PROMOTE, QUARANTINE, REJECT, or INCONCLUSIVE.
Constitutional Invariant: NEVER converts research promotion into live trading authorization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.kronos.research.ablation_matrix import VariantEvaluationResult
from core.kronos.research.forecast_validity import ForecastValidityReport
from core.kronos.research.friction_evaluator import EconomicUtilityReport
from core.kronos.research.orthogonality_tester import IncrementalInformationReport
from core.kronos.research.regime_analyzer import RegimeSliceReport


@dataclass
class PromotionGateReport:
    governance_state: str  # "PROMOTE", "QUARANTINE", "REJECT", "INCONCLUSIVE"
    is_tradeable: bool  # Constitutional invariant: ALWAYS False
    sample_size: int
    criteria_checklist: dict[str, bool]
    scorecard: dict[str, Any]
    summary_verdict: str
    downstream_destination: str
    governance_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromotionGate:
    """
    Evaluates empirical research criteria against pre-registered thresholds.
    """

    # Pre-registered institutional thresholds
    MIN_SAMPLE_SIZE = 100
    MIN_BSS_STANDALONE = 0.01
    MIN_BETA_T_STAT = 2.0
    MIN_DSR_THRESHOLD = 0.95

    def evaluate_promotion(
        self,
        validity: ForecastValidityReport,
        incremental: IncrementalInformationReport,
        friction: EconomicUtilityReport,
        regimes: list[RegimeSliceReport] | None = None,
        ablations: list[VariantEvaluationResult] | None = None,
    ) -> PromotionGateReport:
        """
        Synthesizes complete evidence stack into deterministic governance state.
        """
        checklist: dict[str, bool] = {}
        notes: list[str] = []

        n = validity.sample_size
        checklist["sufficient_sample"] = n >= self.MIN_SAMPLE_SIZE
        checklist["positive_standalone_bss"] = validity.brier_skill_score >= self.MIN_BSS_STANDALONE
        checklist["incremental_error_reduction"] = incremental.delta_brier > 0.0
        checklist["mincer_zarnowitz_significance"] = (
            incremental.beta_kronos_t_stat >= self.MIN_BETA_T_STAT
        )

        # Friction check
        cons_result = friction.tier_results.get("CONSERVATIVE")
        checklist["conservative_friction_survival"] = bool(
            cons_result and cons_result.is_net_positive
        )

        # DSR check
        cons_dsr = cons_result.deflated_sharpe_ratio if cons_result else 0.0
        checklist["dsr_hurdle_passed"] = cons_dsr >= self.MIN_DSR_THRESHOLD

        # Regime stability check: at least 2 valid regimes with BSS > 0
        regime_pass = False
        if regimes:
            pos_regimes = [
                r
                for r in regimes
                if r.status == "VALID"
                and r.brier_skill_score is not None
                and r.brier_skill_score > 0.0
            ]
            regime_pass = len(pos_regimes) >= 2
        else:
            regime_pass = True  # If regimes omitted, neutral
        checklist["multi_regime_resilience"] = regime_pass

        # State assignment
        if not checklist["sufficient_sample"]:
            state = "INCONCLUSIVE"
            summary = f"Sample size {n} < {self.MIN_SAMPLE_SIZE}. Retained pending broader dataset collection."
            dest = "SANDBOX_INCONCLUSIVE"
        elif (
            not checklist["positive_standalone_bss"]
            or not checklist["incremental_error_reduction"]
            or incremental.beta_kronos <= 0.0
        ):
            state = "REJECT"
            summary = "Failed fundamental predictive criteria: zero standalone skill or negative incremental information."
            dest = "DECOMMISSIONED"
        elif all(checklist.values()):
            state = "PROMOTE"
            summary = "All confirmatory research criteria passed: positive incremental skill, friction survival, and DSR."
            dest = "STRATEGY_GENOME_RESEARCH_LOOP"
        else:
            # Has positive skill but fails friction or regime robustness
            state = "QUARANTINE"
            summary = "Localized predictive skill verified (BSS > 0), but failed friction hurdle or regime stability."
            dest = "RESEARCH_SANDBOX_QUARANTINE"

        scorecard = {
            "sample_size": n,
            "brier_skill_score": validity.brier_skill_score,
            "delta_brier": incremental.delta_brier,
            "beta_kronos": incremental.beta_kronos,
            "beta_kronos_t_stat": incremental.beta_kronos_t_stat,
            "conservative_net_ev_bps": cons_result.net_ev_bps if cons_result else None,
            "conservative_dsr": cons_dsr,
            "cumulative_trials": friction.cumulative_trials,
        }

        notes.append(f"Governance State: {state}")
        notes.append(f"Destination: {dest}")
        notes.append(
            "CONSTITUTIONAL INVARIANT: Promotion authorizes StrategyGenome algorithmic research ONLY. Live execution remains completely disabled."
        )

        return PromotionGateReport(
            governance_state=state,
            is_tradeable=False,  # ALWAYS False
            sample_size=n,
            criteria_checklist=checklist,
            scorecard=scorecard,
            summary_verdict=summary,
            downstream_destination=dest,
            governance_notes=notes,
        )


promotion_gate = PromotionGate()
