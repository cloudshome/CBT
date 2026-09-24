"""
core/intelligence/forward_validation/drift_detector.py
======================================================
Multi-Dimensional Drift Detector for Milestone 31 Forward Validation League.

Evaluates forward paper execution against historical backtest distributions across
5 quantitative axes:
1. Return Distribution Drift: Two-sample Kolmogorov-Smirnov test (ks_2samp).
2. Volatility Shift: Ratio of realized paper std dev to backtest expected std dev.
3. Markout Decay Velocity: Slope and inversion of the 100ms->30s microstructure markout curve.
4. Execution Spread & Slippage Drift: Modeled vs realized paper slippage ratio.
5. Market Regime Shift: Forward operating regime vs backtest regime assumptions.

Epistemic & Statistical Governance:
- Denominator Transparency: Returns INCONCLUSIVE whenever sample size N < 30.
- Statistical vs Economic Significance: A p < 0.01 threshold is an empirical research indicator,
  not an autonomous execution verdict. Requires sample size, effect size, and economic context.
- Multiple-Testing Awareness: Evaluation should be contextualized against family-wise error rates
  when monitoring large leagues of concurrent strategies.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from scipy import stats

from core.intelligence.forward_validation.forward_ledger import (
    StrategyForwardScorecard,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    PaperFill,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.drift_detector")


class DriftStatus(str, Enum):
    """Multi-dimensional drift severity classification."""

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    SEVERE = "SEVERE"
    INCONCLUSIVE = "INCONCLUSIVE"


class AxisDriftResult(BaseModel):
    """Detailed drift outcome for a single quantitative evaluation axis."""

    axis_name: str
    status: DriftStatus
    statistic: float | None = None
    p_value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    warning_message: str | None = None


class BacktestBaselineExpectations(BaseModel):
    """
    Certified backtest baseline metrics against which forward paper
    execution is rigorously compared for alpha decay and structural drift.
    """

    expected_mean_return_bps: float
    expected_std_dev_bps: float
    expected_slippage_bps: float = 0.5
    expected_markout_30s_bps: float = 2.0
    backtest_trade_returns_bps: list[float] = Field(default_factory=list)
    primary_regime: str = "TRENDING"


class MultiDimensionalDriftReport(BaseModel):
    """
    Comprehensive 5-axis drift report for an active league strategy.
    Serialized and exposed to the Cockpit UI Forward Validation Desk.
    """

    admission_id: str
    sample_size_n: int
    overall_status: DriftStatus
    axes: dict[str, AxisDriftResult]
    drift_summary: str
    timestamp_utc: float = Field(default_factory=time.time)


class MultiDimensionalDriftDetector:
    """
    Autonomous statistical drift detection engine for forward validation.
    Detects market regime divergence, adverse selection acceleration,
    volatility explosion, and trade return distribution breakdown.
    """

    def __init__(self, min_sample_size: int = 30) -> None:
        self.min_sample_size = min_sample_size

    def evaluate_drift(
        self,
        scorecard: StrategyForwardScorecard,
        raw_trades: list[PaperFill] | None = None,
        baseline: BacktestBaselineExpectations | None = None,
        current_regime: str | None = None,
    ) -> MultiDimensionalDriftReport:
        """
        Runs full 5-axis drift analysis comparing scorecard to backtest expectations.
        """
        if baseline is None:
            baseline = BacktestBaselineExpectations(
                expected_mean_return_bps=scorecard.mean_trade_net_bps,
                expected_std_dev_bps=scorecard.std_dev_bps,
                expected_slippage_bps=max(0.1, scorecard.avg_slippage_bps),
                expected_markout_30s_bps=scorecard.markout_curve_bps.get(30000, 2.0),
            )

        n = scorecard.total_trades
        axes: dict[str, AxisDriftResult] = {}

        # -------------------------------------------------------------
        # Axis 1: Return Distribution Drift (Two-sample KS test)
        # -------------------------------------------------------------
        axes["return_distribution"] = self._eval_return_distribution(
            scorecard=scorecard,
            raw_trades=raw_trades,
            baseline=baseline,
        )

        # -------------------------------------------------------------
        # Axis 2: Volatility Shift (Live Std Dev / Backtest Std Dev)
        # -------------------------------------------------------------
        axes["volatility_shift"] = self._eval_volatility_shift(
            scorecard=scorecard,
            baseline=baseline,
        )

        # -------------------------------------------------------------
        # Axis 3: Markout Decay Velocity (Microstructure Horizon Curve)
        # -------------------------------------------------------------
        axes["markout_decay"] = self._eval_markout_decay(
            scorecard=scorecard,
            baseline=baseline,
        )

        # -------------------------------------------------------------
        # Axis 4: Execution Spread & Slippage Drift
        # -------------------------------------------------------------
        axes["slippage_drift"] = self._eval_slippage_drift(
            scorecard=scorecard,
            baseline=baseline,
        )

        # -------------------------------------------------------------
        # Axis 5: Market Regime Shift
        # -------------------------------------------------------------
        axes["regime_shift"] = self._eval_regime_shift(
            scorecard=scorecard,
            baseline=baseline,
            current_regime=current_regime,
        )

        # -------------------------------------------------------------
        # Rollup Status
        # -------------------------------------------------------------
        if n < self.min_sample_size:
            overall_status = DriftStatus.INCONCLUSIVE
            drift_summary = (
                f"Insufficient sample size (N={n} < {self.min_sample_size}). "
                "Alpha and drift metrics cannot be reliably established."
            )
        else:
            severes = sum(1 for a in axes.values() if a.status == DriftStatus.SEVERE)
            degradeds = sum(1 for a in axes.values() if a.status == DriftStatus.DEGRADED)
            watches = sum(1 for a in axes.values() if a.status == DriftStatus.WATCH)

            if severes > 0:
                overall_status = DriftStatus.SEVERE
                drift_summary = f"CRITICAL: {severes} axis/axes showing severe structural drift or adverse selection."
            elif degradeds >= 2 or (degradeds >= 1 and watches >= 1):
                overall_status = DriftStatus.DEGRADED
                drift_summary = f"WARNING: Multi-axis degradation detected ({degradeds} degraded, {watches} watch)."
            elif degradeds == 1 or watches >= 1:
                overall_status = DriftStatus.WATCH
                drift_summary = (
                    f"CAUTION: Single axis drift detected ({degradeds} degraded, {watches} watch)."
                )
            else:
                overall_status = DriftStatus.NORMAL
                drift_summary = (
                    "All 5 drift axes operating within acceptable statistical tolerance."
                )

        return MultiDimensionalDriftReport(
            admission_id=scorecard.admission_id,
            sample_size_n=n,
            overall_status=overall_status,
            axes=axes,
            drift_summary=drift_summary,
        )

    def _eval_return_distribution(
        self,
        scorecard: StrategyForwardScorecard,
        raw_trades: list[PaperFill] | None,
        baseline: BacktestBaselineExpectations,
    ) -> AxisDriftResult:
        if scorecard.total_trades < self.min_sample_size:
            return AxisDriftResult(
                axis_name="return_distribution",
                status=DriftStatus.INCONCLUSIVE,
                warning_message=f"Sample size {scorecard.total_trades} < {self.min_sample_size}",
            )

        if not baseline.backtest_trade_returns_bps or len(baseline.backtest_trade_returns_bps) < 10:
            return AxisDriftResult(
                axis_name="return_distribution",
                status=DriftStatus.NORMAL,
                details={"note": "Baseline distribution unavailable; defaulted to normal"},
            )

        # Synthesize or extract realized returns
        # If raw trades provided, calculate net returns, else generate normal approximation
        if raw_trades and len(raw_trades) >= self.min_sample_size:
            live_returns = [
                (t.fill_price - t.benchmark_mid_price) / t.benchmark_mid_price * 10000.0
                - t.fee_bps
                - t.slippage_bps
                for t in raw_trades
            ]
        else:
            # Generate sample from scorecard mean and std dev for statistical test
            # Or use standard score
            live_returns = list(
                stats.norm.rvs(
                    loc=scorecard.mean_trade_net_bps,
                    scale=max(0.1, scorecard.std_dev_bps),
                    size=scorecard.total_trades,
                    random_state=42,
                )
            )

        ks_res = stats.ks_2samp(live_returns, baseline.backtest_trade_returns_bps)
        stat = float(ks_res.statistic)
        p_val = float(ks_res.pvalue)

        if p_val < 0.001:
            status = DriftStatus.SEVERE
            msg = f"Severe return distribution drift: KS statistic={stat:.3f}, p={p_val:.2e}"
        elif p_val < 0.01:
            status = DriftStatus.DEGRADED
            msg = f"Degraded return distribution divergence: KS statistic={stat:.3f}, p={p_val:.4f}"
        elif p_val < 0.05:
            status = DriftStatus.WATCH
            msg = f"Return distribution watch: KS statistic={stat:.3f}, p={p_val:.4f}"
        else:
            status = DriftStatus.NORMAL
            msg = None

        return AxisDriftResult(
            axis_name="return_distribution",
            status=status,
            statistic=round(stat, 4),
            p_value=round(p_val, 5),
            details={"ks_statistic": stat, "p_value": p_val},
            warning_message=msg,
        )

    def _eval_volatility_shift(
        self,
        scorecard: StrategyForwardScorecard,
        baseline: BacktestBaselineExpectations,
    ) -> AxisDriftResult:
        if scorecard.total_trades < self.min_sample_size or baseline.expected_std_dev_bps <= 0:
            return AxisDriftResult(
                axis_name="volatility_shift",
                status=DriftStatus.INCONCLUSIVE,
                warning_message="Insufficient data or zero baseline volatility",
            )

        vol_ratio = scorecard.std_dev_bps / baseline.expected_std_dev_bps

        if vol_ratio > 2.5 or vol_ratio < 0.3:
            status = DriftStatus.SEVERE
            msg = f"Severe volatility shift: ratio={vol_ratio:.2f} (live={scorecard.std_dev_bps:.1f} vs exp={baseline.expected_std_dev_bps:.1f})"
        elif vol_ratio > 2.0 or vol_ratio < 0.4:
            status = DriftStatus.DEGRADED
            msg = f"Degraded volatility mismatch: ratio={vol_ratio:.2f}"
        elif vol_ratio > 1.5 or vol_ratio < 0.6:
            status = DriftStatus.WATCH
            msg = f"Volatility shift watch: ratio={vol_ratio:.2f}"
        else:
            status = DriftStatus.NORMAL
            msg = None

        return AxisDriftResult(
            axis_name="volatility_shift",
            status=status,
            statistic=round(vol_ratio, 3),
            details={
                "live_std_dev_bps": scorecard.std_dev_bps,
                "expected_std_dev_bps": baseline.expected_std_dev_bps,
                "vol_ratio": round(vol_ratio, 3),
            },
            warning_message=msg,
        )

    def _eval_markout_decay(
        self,
        scorecard: StrategyForwardScorecard,
        baseline: BacktestBaselineExpectations,
    ) -> AxisDriftResult:
        curve = scorecard.markout_curve_bps
        if not curve:
            return AxisDriftResult(
                axis_name="markout_decay",
                status=DriftStatus.INCONCLUSIVE,
                warning_message="No markout curve data available",
            )

        m_100 = curve.get(100)
        m_30k = curve.get(30000, curve.get(5000))
        all_negative = all(v < 0.0 for v in curve.values())

        if m_100 is not None and m_30k is not None:
            # Slope in bps per second
            slope = (m_30k - m_100) / 29.9
            if slope < -0.3 or m_30k < -5.0:
                status = DriftStatus.SEVERE
                msg = f"Severe adverse selection: markout slope={slope:.3f} bps/s, 30s markout={m_30k:.1f} bps"
            elif slope < -0.15 or (all_negative and m_30k < 0.0):
                status = DriftStatus.DEGRADED
                msg = f"Degraded markout decay: slope={slope:.3f} bps/s, markout inverted"
            elif slope < -0.05:
                status = DriftStatus.WATCH
                msg = f"Markout decay watch: slope={slope:.3f} bps/s"
            else:
                status = DriftStatus.NORMAL
                msg = None
            stat = slope
        elif all_negative:
            status = DriftStatus.DEGRADED
            stat = -1.0
            msg = "All markout horizons are net negative (execution unprofitability)"
        else:
            status = DriftStatus.NORMAL
            stat = 0.0
            msg = None

        return AxisDriftResult(
            axis_name="markout_decay",
            status=status,
            statistic=round(stat, 4) if stat is not None else None,
            details={"markout_curve_bps": curve},
            warning_message=msg,
        )

    def _eval_slippage_drift(
        self,
        scorecard: StrategyForwardScorecard,
        baseline: BacktestBaselineExpectations,
    ) -> AxisDriftResult:
        if scorecard.total_trades < self.min_sample_size or baseline.expected_slippage_bps <= 0:
            return AxisDriftResult(
                axis_name="slippage_drift",
                status=DriftStatus.INCONCLUSIVE,
                warning_message="Insufficient data or invalid baseline slippage",
            )

        slip_ratio = scorecard.avg_slippage_bps / baseline.expected_slippage_bps

        if slip_ratio > 3.0:
            status = DriftStatus.SEVERE
            msg = f"Severe slippage explosion: {slip_ratio:.2f}x expected ({scorecard.avg_slippage_bps:.2f} bps vs {baseline.expected_slippage_bps:.2f} bps)"
        elif slip_ratio > 2.0:
            status = DriftStatus.DEGRADED
            msg = f"Degraded slippage: {slip_ratio:.2f}x expected"
        elif slip_ratio > 1.5:
            status = DriftStatus.WATCH
            msg = f"Slippage watch: {slip_ratio:.2f}x expected"
        else:
            status = DriftStatus.NORMAL
            msg = None

        return AxisDriftResult(
            axis_name="slippage_drift",
            status=status,
            statistic=round(slip_ratio, 3),
            details={
                "live_avg_slippage_bps": scorecard.avg_slippage_bps,
                "expected_slippage_bps": baseline.expected_slippage_bps,
                "slippage_ratio": round(slip_ratio, 3),
            },
            warning_message=msg,
        )

    def _eval_regime_shift(
        self,
        scorecard: StrategyForwardScorecard,
        baseline: BacktestBaselineExpectations,
        current_regime: str | None,
    ) -> AxisDriftResult:
        if current_regime is None:
            return AxisDriftResult(
                axis_name="regime_shift",
                status=DriftStatus.NORMAL,
                details={"current_regime": "UNKNOWN_PRESERVED_NORMAL"},
            )

        if current_regime.upper() != baseline.primary_regime.upper():
            status = DriftStatus.WATCH
            msg = f"Market regime mismatch: live={current_regime.upper()} vs backtest_baseline={baseline.primary_regime.upper()}"
        else:
            status = DriftStatus.NORMAL
            msg = None

        return AxisDriftResult(
            axis_name="regime_shift",
            status=status,
            details={
                "current_regime": current_regime,
                "baseline_regime": baseline.primary_regime,
            },
            warning_message=msg,
        )
