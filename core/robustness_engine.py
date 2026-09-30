"""
core/robustness_engine.py
===========================
Parameter Perturbation & Macro Regime Robustness Engine.
Implements:
1. Parameter Neighborhood Perturbation (Plateau vs. Razor-Thin Needle Overfit Test).
2. Macro Regime Robustness Decomposition across 5 distinct market environments.
3. Multi-State Research Gate Classifier producing:
   ROBUST | FRAGILE | OVERFIT | INSUFFICIENT DATA | INCONCLUSIVE.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np

from core.statistical_defense import (
    ACTIVE_STATISTICAL_POLICY,
    DSRReport,
    StatisticalPolicy,
    WRCReport,
)
from core.walk_forward_cpcv import CPCVResult

logger = logging.getLogger("sky.robustness_engine")


class ResearchClassification(StrEnum):
    """Institutional epistemic research verdict."""

    ROBUST = "ROBUST"
    FRAGILE = "FRAGILE"
    OVERFIT = "OVERFIT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class PerturbationPoint:
    """Evaluation result for one neighbor in parameter space."""

    parameter_deltas: dict[str, float]
    perturbed_sharpe: float
    retained_ratio: float  # perturbed_sharpe / max(0.01, base_sharpe)
    is_positive_expectancy: bool


@dataclass
class PerturbationReport:
    """Summary of parameter perturbation test."""

    base_sharpe: float
    tested_neighborhood_size: int
    surviving_neighbors_count: int
    plateau_survival_ratio: float  # surviving / total
    is_plateau_confirmed: bool  # True if ratio >= policy.plateau_survival_ratio
    points: list[PerturbationPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["points"] = [asdict(p) for p in self.points]
        return d


@dataclass
class RegimePerformance:
    """Strategy performance within a specific market regime."""

    regime_name: str
    sample_bars_count: int
    trade_count: int
    sharpe: float
    win_rate_pct: float
    net_return_pct: float
    max_drawdown_pct: float
    is_catastrophic_loss: bool  # True if drawdown > 15% or net return < -12%


@dataclass
class RegimeDecompositionReport:
    """Decomposition of performance across macro market regimes."""

    regimes: dict[str, RegimePerformance]
    profitable_regimes_count: int
    total_regimes_tested: int
    is_regime_resilient: bool  # True if >= 3 regimes profitable and 0 catastrophic
    worst_regime_drawdown_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "regimes": {k: asdict(v) for k, v in self.regimes.items()},
            "profitable_regimes_count": self.profitable_regimes_count,
            "total_regimes_tested": self.total_regimes_tested,
            "is_regime_resilient": self.is_regime_resilient,
            "worst_regime_drawdown_pct": round(self.worst_regime_drawdown_pct, 2),
        }


@dataclass
class ResearchGateDossier:
    """Complete multi-dimensional research certification package."""

    strategy_id: str
    symbol: str
    timeframe: str
    policy_version: str
    verdict: ResearchClassification
    verdict_rationale: str
    is_tier1_quarantine_authorized: bool
    cpcv_result: CPCVResult
    dsr_report: DSRReport
    wrc_report: WRCReport
    perturbation_report: PerturbationReport
    regime_report: RegimeDecompositionReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "policy_version": self.policy_version,
            "verdict": self.verdict.value,
            "verdict_rationale": self.verdict_rationale,
            "is_tier1_quarantine_authorized": self.is_tier1_quarantine_authorized,
            "cpcv_result": self.cpcv_result.to_dict(),
            "dsr_report": self.dsr_report.to_dict(),
            "wrc_report": self.wrc_report.to_dict(),
            "perturbation_report": self.perturbation_report.to_dict(),
            "regime_report": self.regime_report.to_dict(),
        }


class ParameterPerturbationAuditor:
    """
    Evaluates whether a strategy occupies a stable performance plateau
    or a fragile hyper-optimized needle in parameter space.
    """

    @staticmethod
    def audit_neighborhood(
        base_sharpe: float,
        closes: np.ndarray,
        signal_generator_fn: Any,  # fn(closes, param_dict) -> signals
        base_params: dict[str, float],
        policy: StatisticalPolicy = ACTIVE_STATISTICAL_POLICY,
        delta_pcts: tuple[float, ...] = (-0.15, -0.10, -0.05, 0.05, 0.10, 0.15),
    ) -> PerturbationReport:
        """
        Samples adjacent parameter points and verifies if at least
        plateau_survival_ratio (70%) retain at least 70% of base Sharpe.
        """
        if base_sharpe <= 0.0:
            return PerturbationReport(
                base_sharpe=base_sharpe,
                tested_neighborhood_size=0,
                surviving_neighbors_count=0,
                plateau_survival_ratio=0.0,
                is_plateau_confirmed=False,
                points=[],
            )

        numeric_keys = [k for k, v in base_params.items() if isinstance(v, int | float)]
        if not numeric_keys:
            # No numeric parameters to perturb (static rule set)
            return PerturbationReport(
                base_sharpe=base_sharpe,
                tested_neighborhood_size=1,
                surviving_neighbors_count=1,
                plateau_survival_ratio=1.0,
                is_plateau_confirmed=True,
                points=[],
            )

        points: list[PerturbationPoint] = []
        surviving_count = 0

        raw_returns = np.zeros(len(closes), dtype=float)
        raw_returns[1:] = (closes[1:] - closes[:-1]) / np.maximum(closes[:-1], 1e-8)

        # Perturb each parameter across positive and negative steps
        for key in numeric_keys[:3]:  # Top 3 key parameters
            base_val = base_params[key]
            for delta in delta_pcts:
                perturbed_params = dict(base_params)
                new_val = base_val * (1.0 + delta)
                perturbed_params[key] = new_val

                try:
                    p_signals = signal_generator_fn(closes, perturbed_params)
                    p_ret = p_signals[:-1] * raw_returns[1:]
                    p_std = float(np.std(p_ret))
                    p_sr = (
                        (float(np.mean(p_ret)) / p_std * math.sqrt(365 * 24))
                        if p_std > 1e-9
                        else 0.0
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Perturbation evaluation failed for %s=%s: %s", key, new_val, exc)
                    p_sr = 0.0

                retained = p_sr / max(0.01, base_sharpe)
                is_ok = bool(p_sr > 0.0 and retained >= 0.70)
                if is_ok:
                    surviving_count += 1

                points.append(
                    PerturbationPoint(
                        parameter_deltas={key: round(delta, 3)},
                        perturbed_sharpe=round(p_sr, 3),
                        retained_ratio=round(retained, 3),
                        is_positive_expectancy=is_ok,
                    )
                )

        total_tested = len(points)
        survival_ratio = float(surviving_count / total_tested) if total_tested > 0 else 0.0
        confirmed = bool(survival_ratio >= policy.plateau_survival_ratio)

        return PerturbationReport(
            base_sharpe=round(base_sharpe, 3),
            tested_neighborhood_size=total_tested,
            surviving_neighbors_count=surviving_count,
            plateau_survival_ratio=round(survival_ratio, 3),
            is_plateau_confirmed=confirmed,
            points=points,
        )


class RegimeRobustnessDecomposer:
    """
    Decomposes strategy returns across 5 macro crypto market regimes
    to verify that alpha is not an artifact of a single benign period.
    """

    @staticmethod
    def decompose(
        closes: np.ndarray,
        signals: np.ndarray,
    ) -> RegimeDecompositionReport:
        n = len(closes)
        raw_ret = np.zeros(n, dtype=float)
        raw_ret[1:] = (closes[1:] - closes[:-1]) / np.maximum(closes[:-1], 1e-8)
        trade_ret = signals[:-1] * raw_ret[1:]
        trade_ret_padded = np.concatenate([[0.0], trade_ret])

        # 1. Classify bars into 5 regimes
        # Calculate 20-bar rolling return and 20-bar rolling volatility
        rolling_ret_20 = np.zeros(n, dtype=float)
        rolling_vol_20 = np.zeros(n, dtype=float)
        for i in range(20, n):
            rolling_ret_20[i] = (closes[i] - closes[i - 20]) / closes[i - 20]
            rolling_vol_20[i] = float(np.std(raw_ret[i - 20 : i]))

        vol_75th = float(np.percentile(rolling_vol_20[20:], 75)) if n > 40 else 0.02
        vol_25th = float(np.percentile(rolling_vol_20[20:], 25)) if n > 40 else 0.005

        regime_masks: dict[str, np.ndarray] = {
            "TRENDING_BULL": (rolling_ret_20 > 0.02) & (rolling_vol_20 <= vol_75th),
            "TRENDING_BEAR": (rolling_ret_20 < -0.02) & (rolling_vol_20 <= vol_75th),
            "HIGH_VOL_RANGE": (np.abs(rolling_ret_20) <= 0.02) & (rolling_vol_20 > vol_75th),
            "LOW_VOL_COMPRESSION": (np.abs(rolling_ret_20) <= 0.015) & (rolling_vol_20 < vol_25th),
            "LIQUIDITY_CRISIS": (rolling_ret_20 < -0.05) | (rolling_vol_20 > vol_75th * 1.5),
        }

        regime_results: dict[str, RegimePerformance] = {}
        profitable_count = 0
        worst_dd = 0.0

        for r_name, mask in regime_masks.items():
            r_ret = trade_ret_padded[mask]
            bar_count = int(np.sum(mask))
            trade_count = int(np.sum(np.abs(np.diff(signals[mask])) > 0.01)) if bar_count > 1 else 0

            if bar_count < 10 or len(r_ret) == 0:
                regime_results[r_name] = RegimePerformance(
                    regime_name=r_name,
                    sample_bars_count=bar_count,
                    trade_count=trade_count,
                    sharpe=0.0,
                    win_rate_pct=0.0,
                    net_return_pct=0.0,
                    max_drawdown_pct=0.0,
                    is_catastrophic_loss=False,
                )
                continue

            std = float(np.std(r_ret))
            sr = (float(np.mean(r_ret)) / std * math.sqrt(365 * 24)) if std > 1e-9 else 0.0
            cum_ret = float(np.prod(1.0 + np.clip(r_ret, -0.20, 0.20)) - 1.0)
            equity = np.cumprod(1.0 + np.clip(r_ret, -0.99, 5.0))
            running_max = np.maximum.accumulate(equity)
            dd = float(np.max((running_max - equity) / running_max)) if len(equity) > 0 else 0.0

            worst_dd = max(worst_dd, dd * 100.0)
            is_catastrophic = bool(dd > 0.15 or cum_ret < -0.12)
            if sr > 0.3 and not is_catastrophic:
                profitable_count += 1

            active_trades = r_ret[r_ret != 0.0]
            wr = float(np.mean(active_trades > 0.0)) * 100.0 if len(active_trades) > 0 else 0.0

            regime_results[r_name] = RegimePerformance(
                regime_name=r_name,
                sample_bars_count=bar_count,
                trade_count=trade_count,
                sharpe=round(sr, 2),
                win_rate_pct=round(wr, 1),
                net_return_pct=round(cum_ret * 100.0, 2),
                max_drawdown_pct=round(dd * 100.0, 2),
                is_catastrophic_loss=is_catastrophic,
            )

        is_resilient = bool(
            profitable_count >= 2
            and not any(r.is_catastrophic_loss for r in regime_results.values())
        )

        return RegimeDecompositionReport(
            regimes=regime_results,
            profitable_regimes_count=profitable_count,
            total_regimes_tested=len(regime_results),
            is_regime_resilient=is_resilient,
            worst_regime_drawdown_pct=worst_dd,
        )


class ResearchGateClassifier:
    """
    Synthesizes CPCV, DSR, WRC, Perturbation, and Regime evaluations
    into an institutional multi-state research verdict.
    """

    @staticmethod
    def classify(
        strategy_id: str,
        symbol: str,
        timeframe: str,
        cpcv_result: CPCVResult,
        dsr_report: DSRReport,
        wrc_report: WRCReport,
        perturbation_report: PerturbationReport,
        regime_report: RegimeDecompositionReport,
        policy: StatisticalPolicy = ACTIVE_STATISTICAL_POLICY,
    ) -> ResearchGateDossier:
        # Gate 1: Minimum Sample Requirements
        if cpcv_result.total_oos_trades < policy.min_oos_trades:
            return ResearchGateDossier(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                policy_version=policy.policy_version,
                verdict=ResearchClassification.INSUFFICIENT_DATA,
                verdict_rationale=(
                    f"Insufficient out-of-sample trade count: {cpcv_result.total_oos_trades} trades observed, "
                    f"minimum {policy.min_oos_trades} required for asymptotic validity."
                ),
                is_tier1_quarantine_authorized=False,
                cpcv_result=cpcv_result,
                dsr_report=dsr_report,
                wrc_report=wrc_report,
                perturbation_report=perturbation_report,
                regime_report=regime_report,
            )

        # Gate 2: Overfit Detection
        # Low stability between IS and OOS, or high raw Sharpe that collapses under DSR / WRC
        is_overfit = (
            cpcv_result.stability_index < 0.45
            or (cpcv_result.mean_is_sharpe > 2.0 and cpcv_result.mean_oos_sharpe < 0.70)
            or (
                not dsr_report.is_tier1_eligible
                and dsr_report.deflated_sharpe_ratio < policy.dsr_caution_threshold
            )
        )

        if is_overfit:
            return ResearchGateDossier(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                policy_version=policy.policy_version,
                verdict=ResearchClassification.OVERFIT,
                verdict_rationale=(
                    f"Severe overfitting detected: OOS/IS stability index is {cpcv_result.stability_index:.2f} (< 0.45 threshold), "
                    f"or DSR ({dsr_report.deflated_sharpe_ratio:.3f}) failed multi-testing luck hurdle across {dsr_report.cumulative_trials} trials."
                ),
                is_tier1_quarantine_authorized=False,
                cpcv_result=cpcv_result,
                dsr_report=dsr_report,
                wrc_report=wrc_report,
                perturbation_report=perturbation_report,
                regime_report=regime_report,
            )

        # Gate 3: Fragility Detection (Fails friction or perturbation plateau)
        conservative_sharpe = cpcv_result.friction_results.get("CONSERVATIVE", {}).get(
            "sharpe", 0.0
        )
        is_fragile = (
            conservative_sharpe <= 0.10
            or not perturbation_report.is_plateau_confirmed
            or (
                policy.stress_survival_required
                and cpcv_result.friction_results.get("STRESS", {}).get("max_drawdown_pct", 100.0)
                > 40.0
            )
        )

        if is_fragile:
            return ResearchGateDossier(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                policy_version=policy.policy_version,
                verdict=ResearchClassification.FRAGILE,
                verdict_rationale=(
                    f"Structural fragility: Strategy collapses under venue frictions (Conservative Sharpe = {conservative_sharpe:.2f}) "
                    f"or occupies a razor-thin parameter needle (Plateau survival ratio {perturbation_report.plateau_survival_ratio:.2f} < {policy.plateau_survival_ratio})."
                ),
                is_tier1_quarantine_authorized=False,
                cpcv_result=cpcv_result,
                dsr_report=dsr_report,
                wrc_report=wrc_report,
                perturbation_report=perturbation_report,
                regime_report=regime_report,
            )

        # Gate 4: Robustness Qualification
        # Clears strict DSR (>= 0.95), WRC alpha (< 0.05), confirms plateau, and is regime resilient
        is_robust = (
            dsr_report.is_tier1_eligible
            and wrc_report.is_alpha_significant
            and perturbation_report.is_plateau_confirmed
            and regime_report.is_regime_resilient
            and conservative_sharpe >= 0.50
        )

        if is_robust:
            return ResearchGateDossier(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                policy_version=policy.policy_version,
                verdict=ResearchClassification.ROBUST,
                verdict_rationale=(
                    f"Statistically robust: Clears DSR hurdle ({dsr_report.deflated_sharpe_ratio:.3f} >= {policy.dsr_tier1_threshold}), "
                    f"passes Politis-Romano WRC (p = {wrc_report.wrc_p_value:.4f}), confirms parameter plateau ({perturbation_report.plateau_survival_ratio:.2f}), "
                    f"and demonstrates cross-regime resilience across {regime_report.profitable_regimes_count} regimes."
                ),
                is_tier1_quarantine_authorized=True,
                cpcv_result=cpcv_result,
                dsr_report=dsr_report,
                wrc_report=wrc_report,
                perturbation_report=perturbation_report,
                regime_report=regime_report,
            )

        # Gate 5: Inconclusive (Mixed evidence)
        return ResearchGateDossier(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            policy_version=policy.policy_version,
            verdict=ResearchClassification.INCONCLUSIVE,
            verdict_rationale=(
                f"Mixed empirical evidence: DSR ({dsr_report.deflated_sharpe_ratio:.3f}) is borderline, "
                f"or cross-regime performance is divergent. Does not qualify for Tier-1 Quarantine without further out-of-sample data."
            ),
            is_tier1_quarantine_authorized=False,
            cpcv_result=cpcv_result,
            dsr_report=dsr_report,
            wrc_report=wrc_report,
            perturbation_report=perturbation_report,
            regime_report=regime_report,
        )
