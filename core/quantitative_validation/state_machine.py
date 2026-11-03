"""
core/quantitative_validation/state_machine.py
============================================
Progressive Strategy Qualification State Machine for Gate 5.
Replaces binary pass/fail with an evidence-driven qualification ladder:

1. NOT_READY: Insufficient observations (N < 30) or unhandled exceptions.
2. INITIAL_SHADOW: N >= 30, Net Expectancy E[R] > 0, Max DD <= 2.0%.
3. EXTENDED_SHADOW: N >= 100, Profit Factor >= 1.30, Conservative Friction > 0.
4. QUANTITATIVE_VALIDATION: N >= 200, Bootstrap 95% CI lower bound > 0,
   DSR >= 0.80, Stress Friction > 0, N_eff >= 50.
5. QUALIFIED_FOR_SHADOW_CONTINUATION: All quantitative, operational, and regime
   attribution gates verified green.
6. QUARANTINED: Max Drawdown breach (>2.0%), consecutive loss limit, or data integrity defect.
7. REJECTED: Falsified statistical edge, non-recoverable negative expectancy.

Permanent Constitutional Governance Invariant:
    REAL_CAPITAL_ENABLED = False
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .cost_stress import evaluate_cost_stress_decay
from .metrics import (
    TradeReturn,
    calculate_full_statistical_profile,
)
from .regime_attribution import decompose_regime_performance


class Gate5State(StrEnum):
    NOT_READY = "NOT_READY"
    INITIAL_SHADOW = "INITIAL_SHADOW"
    EXTENDED_SHADOW = "EXTENDED_SHADOW"
    QUANTITATIVE_VALIDATION = "QUANTITATIVE_VALIDATION"
    QUALIFIED_FOR_SHADOW_CONTINUATION = "QUALIFIED_FOR_SHADOW_CONTINUATION"
    QUARANTINED = "QUARANTINED"
    INVESTIGATION = "INVESTIGATION"
    PAPER_RECOVERY = "PAPER_RECOVERY"
    REQUALIFICATION = "REQUALIFICATION"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Gate5EvaluationResult:
    state: Gate5State
    real_capital_enabled: bool = False
    days_observed: float = 0.0
    total_trades: int = 0
    effective_sample_size: float = 0.0
    net_expectancy_r: float = 0.0
    expectancy_ci_lower: float = 0.0
    expectancy_ci_upper: float = 0.0
    win_rate_pct: float = 0.0
    win_rate_ci_lower: float = 0.0
    win_rate_ci_upper: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    ulcer_index: float = 0.0
    deflated_sharpe_ratio: float = 0.0
    sharpe_ratio: float = 0.0
    cost_stress: dict[str, Any] = field(default_factory=dict)
    regime_attribution: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "real_capital_enabled": self.real_capital_enabled,
            "days_observed": self.days_observed,
            "total_trades": self.total_trades,
            "effective_sample_size": self.effective_sample_size,
            "net_expectancy_r": self.net_expectancy_r,
            "expectancy_95_ci": [self.expectancy_ci_lower, self.expectancy_ci_upper],
            "win_rate_pct": self.win_rate_pct,
            "win_rate_wilson_ci": [self.win_rate_ci_lower, self.win_rate_ci_upper],
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "ulcer_index": self.ulcer_index,
            "deflated_sharpe_ratio": self.deflated_sharpe_ratio,
            "sharpe_ratio": self.sharpe_ratio,
            "cost_stress": self.cost_stress,
            "regime_attribution": self.regime_attribution,
            "failures": self.failures,
            "recommendations": self.recommendations,
        }


def count_max_consecutive_losses(trades: list[TradeReturn]) -> int:
    """Returns the maximum run of consecutive losing trades."""
    max_streak = 0
    current_streak = 0
    for t in trades:
        if not t.is_win:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0
    return max_streak


def evaluate_gate5_lifecycle(
    trades: list[TradeReturn],
    days_observed: float = 0.0,
    reconciliation_discrepancies: int = 0,
    max_allowed_drawdown: float = 2.0,
) -> Gate5EvaluationResult:
    """
    Evaluates strategy performance across the progressive Gate 5 state machine.
    Enforces risk primacy, confidence intervals, cost stress, and regime attribution.
    """
    # Strict fail-closed governance invariant
    real_capital_enabled = False

    failures: list[str] = []
    recommendations: list[str] = []

    profile = calculate_full_statistical_profile(trades)
    cost_stress = evaluate_cost_stress_decay(trades)
    regime_attr = decompose_regime_performance(trades)

    n = profile["total_trades"]
    max_dd = profile["max_drawdown_pct"]
    net_exp = profile["net_expectancy_r"]
    exp_ci_lower = profile["expectancy_95_ci"]["ci_lower"]
    exp_ci_upper = profile["expectancy_95_ci"]["ci_upper"]
    win_rate = profile["win_rate_pct"]
    win_ci_lower = profile["win_rate_wilson_ci"]["ci_lower"]
    win_ci_upper = profile["win_rate_wilson_ci"]["ci_upper"]
    pf = profile["profit_factor"]
    n_eff = profile["effective_sample_size"]
    dsr = profile["deflated_sharpe_ratio"]
    ulcer = profile["ulcer_index"]
    sharpe = profile["sharpe_ratio"]

    consecutive_losses = count_max_consecutive_losses(trades)

    # 1. Immediate Circuit Breaker / Quarantine Checks
    if reconciliation_discrepancies > 0:
        failures.append(
            f"Reconciliation integrity breach: {reconciliation_discrepancies} phantom/mismatch fill incident(s)."
        )
        return Gate5EvaluationResult(
            state=Gate5State.QUARANTINED,
            real_capital_enabled=real_capital_enabled,
            days_observed=days_observed,
            total_trades=n,
            effective_sample_size=n_eff,
            net_expectancy_r=net_exp,
            expectancy_ci_lower=exp_ci_lower,
            expectancy_ci_upper=exp_ci_upper,
            win_rate_pct=win_rate,
            win_rate_ci_lower=win_ci_lower,
            win_rate_ci_upper=win_ci_upper,
            profit_factor=pf,
            max_drawdown_pct=max_dd,
            ulcer_index=ulcer,
            deflated_sharpe_ratio=dsr,
            sharpe_ratio=sharpe,
            cost_stress=cost_stress,
            regime_attribution=regime_attr,
            failures=failures,
            recommendations=["Halt execution: investigate reconciliation discrepancies."],
        )

    if max_dd > max_allowed_drawdown:
        failures.append(
            f"Risk ceiling breach: Max peak-to-trough drawdown ({max_dd:.2f}%) exceeds {max_allowed_drawdown:.2f}% ceiling."
        )
        return Gate5EvaluationResult(
            state=Gate5State.QUARANTINED,
            real_capital_enabled=real_capital_enabled,
            days_observed=days_observed,
            total_trades=n,
            effective_sample_size=n_eff,
            net_expectancy_r=net_exp,
            expectancy_ci_lower=exp_ci_lower,
            expectancy_ci_upper=exp_ci_upper,
            win_rate_pct=win_rate,
            win_rate_ci_lower=win_ci_lower,
            win_rate_ci_upper=win_ci_upper,
            profit_factor=pf,
            max_drawdown_pct=max_dd,
            ulcer_index=ulcer,
            deflated_sharpe_ratio=dsr,
            sharpe_ratio=sharpe,
            cost_stress=cost_stress,
            regime_attribution=regime_attr,
            failures=failures,
            recommendations=[
                "Quarantine strategy: reduce exposure or recalibrate stop-loss geometry."
            ],
        )

    if consecutive_losses >= 8:
        failures.append(
            f"Adverse streak breach: {consecutive_losses} consecutive losses detected (limit: 7)."
        )
        return Gate5EvaluationResult(
            state=Gate5State.QUARANTINED,
            real_capital_enabled=real_capital_enabled,
            days_observed=days_observed,
            total_trades=n,
            effective_sample_size=n_eff,
            net_expectancy_r=net_exp,
            expectancy_ci_lower=exp_ci_lower,
            expectancy_ci_upper=exp_ci_upper,
            win_rate_pct=win_rate,
            win_rate_ci_lower=win_ci_lower,
            win_rate_ci_upper=win_ci_upper,
            profit_factor=pf,
            max_drawdown_pct=max_dd,
            ulcer_index=ulcer,
            deflated_sharpe_ratio=dsr,
            sharpe_ratio=sharpe,
            cost_stress=cost_stress,
            regime_attribution=regime_attr,
            failures=failures,
            recommendations=["Quarantine strategy: triggered consecutive-loss circuit breaker."],
        )

    # 2. Rejection Evaluation
    if n >= 30 and net_exp <= 0.0:
        failures.append(
            f"Negative net expectancy: E[R] = {net_exp:+.4f}R across {n} trades (win rate: {win_rate:.1f}%)."
        )
        return Gate5EvaluationResult(
            state=Gate5State.REJECTED,
            real_capital_enabled=real_capital_enabled,
            days_observed=days_observed,
            total_trades=n,
            effective_sample_size=n_eff,
            net_expectancy_r=net_exp,
            expectancy_ci_lower=exp_ci_lower,
            expectancy_ci_upper=exp_ci_upper,
            win_rate_pct=win_rate,
            win_rate_ci_lower=win_ci_lower,
            win_rate_ci_upper=win_ci_upper,
            profit_factor=pf,
            max_drawdown_pct=max_dd,
            ulcer_index=ulcer,
            deflated_sharpe_ratio=dsr,
            sharpe_ratio=sharpe,
            cost_stress=cost_stress,
            regime_attribution=regime_attr,
            failures=failures,
            recommendations=["Retire or redesign strategy: empirical edge falsified."],
        )

    # 3. Progressive Lifecycle Transitions
    if n < 30:
        failures.append(
            f"Insufficient sample: {n} trades observed (minimum initial threshold: 30)."
        )
        recommendations.append(
            "Continue headless paper burn-in to collect initial 30 observations."
        )
        current_state = Gate5State.NOT_READY

    elif n < 100:
        current_state = Gate5State.INITIAL_SHADOW
        recommendations.append(
            "Initial shadow milestone reached. Continue collecting data toward extended validation (100+ trades)."
        )

    elif n < 200:
        # Check Extended Shadow requirements
        if pf < 1.30:
            failures.append(f"Profit factor {pf:.2f} is below extended benchmark threshold (1.30).")
        if cost_stress["conservative_expectancy_r"] <= 0.0:
            failures.append("Edge destroyed under 1.5x conservative friction stress.")

        if not failures:
            current_state = Gate5State.EXTENDED_SHADOW
            recommendations.append(
                "Extended shadow milestone passed. Progressing toward formal quantitative validation (200+ trades)."
            )
        else:
            current_state = Gate5State.INITIAL_SHADOW

    else:  # n >= 200
        # Check Quantitative Validation requirements
        if exp_ci_lower <= 0.0:
            failures.append(
                f"Statistical uncertainty: 95% bootstrap CI lower bound ({exp_ci_lower:+.4f}R) is non-positive."
            )
        if dsr < 0.80:
            failures.append(
                f"Deflated Sharpe Ratio ({dsr:.2f}) is below statistical confidence threshold (0.80)."
            )
        if n_eff < 50.0:
            failures.append(
                f"Effective sample size ({n_eff:.1f}) is insufficient due to excessive trade auto-correlation."
            )
        if cost_stress["stress_expectancy_r"] <= 0.0:
            failures.append("Edge fails 2.5x severe friction stress testing.")

        if not failures:
            # Check Full Shadow Continuation
            if days_observed < 14.0:
                failures.append(
                    f"Observation window duration ({days_observed:.1f} days) is less than 14.0 days."
                )
            if regime_attr["subsidization_risk"]:
                failures.append(regime_attr["subsidization_reason"])
            if ulcer > 5.0:
                failures.append(
                    f"Ulcer Index ({ulcer:.2f}) indicates excessive drawdown severity (ceiling: 5.0)."
                )

            if not failures:
                current_state = Gate5State.QUALIFIED_FOR_SHADOW_CONTINUATION
                recommendations.append(
                    "All quantitative validation criteria satisfied! Qualified for sustained shadow execution."
                )
            else:
                current_state = Gate5State.QUANTITATIVE_VALIDATION
        else:
            current_state = Gate5State.EXTENDED_SHADOW

    return Gate5EvaluationResult(
        state=current_state,
        real_capital_enabled=real_capital_enabled,
        days_observed=days_observed,
        total_trades=n,
        effective_sample_size=n_eff,
        net_expectancy_r=net_exp,
        expectancy_ci_lower=exp_ci_lower,
        expectancy_ci_upper=exp_ci_upper,
        win_rate_pct=win_rate,
        win_rate_ci_lower=win_ci_lower,
        win_rate_ci_upper=win_ci_upper,
        profit_factor=pf,
        max_drawdown_pct=max_dd,
        ulcer_index=ulcer,
        deflated_sharpe_ratio=dsr,
        sharpe_ratio=sharpe,
        cost_stress=cost_stress,
        regime_attribution=regime_attr,
        failures=failures,
        recommendations=recommendations,
    )


def transition_to_investigation(
    current_result: Gate5EvaluationResult,
    investigation_rationale: str,
) -> Gate5EvaluationResult:
    """
    Transitions a strategy from QUARANTINED to INVESTIGATION.
    Does NOT reset or erase historical trades or failures.
    """
    if current_result.state != Gate5State.QUARANTINED:
        raise ValueError(
            f"Cannot transition to INVESTIGATION from state '{current_result.state}'. "
            f"Only QUARANTINED strategies can enter INVESTIGATION."
        )

    recommendations = list(current_result.recommendations)
    recommendations.append(f"Investigation commenced: {investigation_rationale}")

    return Gate5EvaluationResult(
        state=Gate5State.INVESTIGATION,
        real_capital_enabled=False,
        days_observed=current_result.days_observed,
        total_trades=current_result.total_trades,
        effective_sample_size=current_result.effective_sample_size,
        net_expectancy_r=current_result.net_expectancy_r,
        expectancy_ci_lower=current_result.expectancy_ci_lower,
        expectancy_ci_upper=current_result.expectancy_ci_upper,
        win_rate_pct=current_result.win_rate_pct,
        win_rate_ci_lower=current_result.win_rate_ci_lower,
        win_rate_ci_upper=current_result.win_rate_ci_upper,
        profit_factor=current_result.profit_factor,
        max_drawdown_pct=current_result.max_drawdown_pct,
        ulcer_index=current_result.ulcer_index,
        deflated_sharpe_ratio=current_result.deflated_sharpe_ratio,
        sharpe_ratio=current_result.sharpe_ratio,
        cost_stress=current_result.cost_stress,
        regime_attribution=current_result.regime_attribution,
        failures=list(current_result.failures),
        recommendations=recommendations,
    )


def transition_to_paper_recovery(
    current_result: Gate5EvaluationResult,
    recovery_plan: str,
) -> Gate5EvaluationResult:
    """
    Transitions a strategy from INVESTIGATION to PAPER_RECOVERY.
    Strategy is permitted to execute in isolated forward paper burn-in.
    """
    if current_result.state != Gate5State.INVESTIGATION:
        raise ValueError(
            f"Cannot transition to PAPER_RECOVERY from state '{current_result.state}'. "
            f"Strategy must be in INVESTIGATION state."
        )

    recommendations = list(current_result.recommendations)
    recommendations.append(f"Paper recovery burn-in initialized: {recovery_plan}")

    return Gate5EvaluationResult(
        state=Gate5State.PAPER_RECOVERY,
        real_capital_enabled=False,
        days_observed=current_result.days_observed,
        total_trades=current_result.total_trades,
        effective_sample_size=current_result.effective_sample_size,
        net_expectancy_r=current_result.net_expectancy_r,
        expectancy_ci_lower=current_result.expectancy_ci_lower,
        expectancy_ci_upper=current_result.expectancy_ci_upper,
        win_rate_pct=current_result.win_rate_pct,
        win_rate_ci_lower=current_result.win_rate_ci_lower,
        win_rate_ci_upper=current_result.win_rate_ci_upper,
        profit_factor=current_result.profit_factor,
        max_drawdown_pct=current_result.max_drawdown_pct,
        ulcer_index=current_result.ulcer_index,
        deflated_sharpe_ratio=current_result.deflated_sharpe_ratio,
        sharpe_ratio=current_result.sharpe_ratio,
        cost_stress=current_result.cost_stress,
        regime_attribution=current_result.regime_attribution,
        failures=list(current_result.failures),
        recommendations=recommendations,
    )


def evaluate_paper_recovery(
    prior_historical_trades: list[TradeReturn],
    recovery_trades: list[TradeReturn],
    min_recovery_trades: int = 30,
    max_recovery_drawdown: float = 2.0,
) -> Gate5EvaluationResult:
    """
    Evaluates out-of-sample forward performance during PAPER_RECOVERY.
    Constitutional rule: Past failures are preserved in the total audit trail,
    while recovery is judged strictly on the newly observed post-incident trades.
    """
    if len(recovery_trades) < min_recovery_trades:
        rec_profile = calculate_full_statistical_profile(recovery_trades) if recovery_trades else {}
        return Gate5EvaluationResult(
            state=Gate5State.PAPER_RECOVERY,
            real_capital_enabled=False,
            total_trades=len(prior_historical_trades) + len(recovery_trades),
            net_expectancy_r=rec_profile.get("net_expectancy_r", 0.0),
            max_drawdown_pct=rec_profile.get("max_drawdown_pct", 0.0),
            failures=[
                f"Insufficient paper recovery sample: {len(recovery_trades)} / {min_recovery_trades} required."
            ],
            recommendations=["Continue paper recovery forward testing."],
        )

    rec_profile = calculate_full_statistical_profile(recovery_trades)
    cost_stress = evaluate_cost_stress_decay(recovery_trades)
    regime_attr = decompose_regime_performance(recovery_trades)
    rec_losses = count_max_consecutive_losses(recovery_trades)

    failures: list[str] = []
    recommendations: list[str] = []

    if rec_losses >= 8:
        failures.append(f"Adverse streak during recovery: {rec_losses} consecutive losses.")
        return Gate5EvaluationResult(
            state=Gate5State.QUARANTINED,
            real_capital_enabled=False,
            total_trades=len(prior_historical_trades) + len(recovery_trades),
            net_expectancy_r=rec_profile["net_expectancy_r"],
            max_drawdown_pct=rec_profile["max_drawdown_pct"],
            failures=failures,
            recommendations=["Re-quarantine: strategy failed paper recovery."],
        )

    if rec_profile["max_drawdown_pct"] > max_recovery_drawdown:
        failures.append(
            f"Recovery drawdown breach: {rec_profile['max_drawdown_pct']:.2f}% exceeds {max_recovery_drawdown:.2f}% ceiling."
        )
        return Gate5EvaluationResult(
            state=Gate5State.QUARANTINED,
            real_capital_enabled=False,
            total_trades=len(prior_historical_trades) + len(recovery_trades),
            net_expectancy_r=rec_profile["net_expectancy_r"],
            max_drawdown_pct=rec_profile["max_drawdown_pct"],
            failures=failures,
            recommendations=["Re-quarantine: recovery drawdown ceiling breached."],
        )

    if rec_profile["net_expectancy_r"] <= 0.0:
        failures.append(
            f"Negative recovery expectancy: E[R] = {rec_profile['net_expectancy_r']:+.4f}R."
        )
        return Gate5EvaluationResult(
            state=Gate5State.REJECTED,
            real_capital_enabled=False,
            total_trades=len(prior_historical_trades) + len(recovery_trades),
            net_expectancy_r=rec_profile["net_expectancy_r"],
            max_drawdown_pct=rec_profile["max_drawdown_pct"],
            failures=failures,
            recommendations=["Reject strategy: recovery evidence confirmed lack of edge."],
        )

    # Recovery successfully completed!
    recommendations.append(
        "Paper recovery criteria satisfied. Transitioning to REQUALIFICATION state for sustained shadow monitoring."
    )
    combined_total = len(prior_historical_trades) + len(recovery_trades)

    return Gate5EvaluationResult(
        state=Gate5State.REQUALIFICATION,
        real_capital_enabled=False,
        total_trades=combined_total,
        effective_sample_size=rec_profile["effective_sample_size"],
        net_expectancy_r=rec_profile["net_expectancy_r"],
        expectancy_ci_lower=rec_profile["expectancy_95_ci"]["ci_lower"],
        expectancy_ci_upper=rec_profile["expectancy_95_ci"]["ci_upper"],
        win_rate_pct=rec_profile["win_rate_pct"],
        win_rate_ci_lower=rec_profile["win_rate_wilson_ci"]["ci_lower"],
        win_rate_ci_upper=rec_profile["win_rate_wilson_ci"]["ci_upper"],
        profit_factor=rec_profile["profit_factor"],
        max_drawdown_pct=rec_profile["max_drawdown_pct"],
        ulcer_index=rec_profile["ulcer_index"],
        deflated_sharpe_ratio=rec_profile["deflated_sharpe_ratio"],
        sharpe_ratio=rec_profile["sharpe_ratio"],
        cost_stress=cost_stress,
        regime_attribution=regime_attr,
        failures=[],
        recommendations=recommendations,
    )
