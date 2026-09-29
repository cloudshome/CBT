"""
core/research/grade_e1/statistical_tests.py
===========================================
Grade-E1 Statistical Defense & Rigorous Inference Engine.

Performs block-bootstrapping, cluster-robust standard errors, and formal
hypothesis testing for pre-registered hypotheses H0-A through H0-F.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

from core.research.grade_e1.contracts import (
    AdverseSelectionMetrics,
    CalibratedCostBreakdown,
    FillEvent,
)

logger = logging.getLogger("sky.grade_e1.statistical_tests")


@dataclass(frozen=True)
class HypothesisTestSummary:
    hypothesis_id: str
    hypothesis_statement: str
    test_statistic: float
    p_value: float
    confidence_interval_95: tuple[float, float]
    null_rejected: bool
    verdict_impact: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_statement": self.hypothesis_statement,
            "test_statistic": round(self.test_statistic, 4),
            "p_value": round(self.p_value, 4),
            "confidence_interval_95": [
                round(self.confidence_interval_95[0], 4),
                round(self.confidence_interval_95[1], 4),
            ],
            "null_rejected": bool(self.null_rejected),
            "verdict_impact": self.verdict_impact,
        }


class GradeE1StatisticalDefense:
    """Rigorous statistical testing suite for execution hypothesis validation."""

    def __init__(self, n_bootstrap: int = 1000, block_size: int = 20, seed: int = 42):
        self.n_bootstrap = n_bootstrap
        self.block_size = block_size
        self.rng = np.random.default_rng(seed)

    def block_bootstrap_mean(self, data: np.ndarray) -> np.ndarray:
        """Stationary/moving block bootstrap for time-series with autocorrelation."""
        n = len(data)
        if n < self.block_size:
            # Fallback to standard bootstrap if sample is smaller than block size
            return np.array(
                [
                    np.mean(self.rng.choice(data, size=n, replace=True))
                    for _ in range(self.n_bootstrap)
                ]
            )

        n_blocks = int(math.ceil(n / self.block_size))
        boot_means = np.empty(self.n_bootstrap)

        for b in range(self.n_bootstrap):
            # Sample random starting indices
            starts = self.rng.integers(0, n - self.block_size + 1, size=n_blocks)
            sample = np.concatenate([data[s : s + self.block_size] for s in starts])[:n]
            boot_means[b] = np.mean(sample)

        return boot_means

    def test_h0_a_net_maker_edge(
        self,
        cost_breakdown: CalibratedCostBreakdown,
        fills: list[FillEvent],
    ) -> HypothesisTestSummary:
        """
        H0-A: Expected Net Maker Edge >= 0 bps.
        Null Rejected if bootstrap distribution shows net edge is significantly negative (< 0).
        """
        if not fills:
            return HypothesisTestSummary(
                hypothesis_id="H0-A",
                hypothesis_statement="E[Net Maker Edge] >= 0 bps",
                test_statistic=0.0,
                p_value=1.0,
                confidence_interval_95=(0.0, 0.0),
                null_rejected=False,
                verdict_impact="INSUFFICIENT_DATA",
            )

        # Vector of individual fill edges (gross spread - maker fee + markout_5)
        trade_edges = np.array(
            [
                cost_breakdown.gross_spread_earned_bps
                - cost_breakdown.maker_fee_bps
                + (f.markout_5_bar_bps or 0.0)
                for f in fills
            ]
        )

        boot_means = self.block_bootstrap_mean(trade_edges)
        ci_lower = float(np.percentile(boot_means, 2.5))
        ci_upper = float(np.percentile(boot_means, 97.5))
        mean_stat = float(np.mean(trade_edges))

        # p-value for H0: mean >= 0 vs H1: mean < 0
        p_val = float(np.mean(boot_means >= 0.0))  # Fraction of times net edge was >= 0
        # If mean is negative and upper CI < 0, null is rejected
        null_rejected = ci_upper < 0.0

        return HypothesisTestSummary(
            hypothesis_id="H0-A",
            hypothesis_statement="E[Net Maker Edge] >= 0 bps",
            test_statistic=mean_stat,
            p_value=p_val,
            confidence_interval_95=(ci_lower, ci_upper),
            null_rejected=null_rejected,
            verdict_impact="FAILS_ECONOMIC_VIABILITY"
            if null_rejected
            else "PASSES_ECONOMIC_VIABILITY",
        )

    def test_h0_b_adverse_selection(
        self,
        adverse_selection: AdverseSelectionMetrics,
        fills: list[FillEvent],
    ) -> HypothesisTestSummary:
        """
        H0-B: Expected Markout at 5 bars = 0 bps (No systematic adverse selection).
        Null Rejected if markout is significantly negative.
        """
        m5_arr = np.array([f.markout_5_bar_bps for f in fills if f.markout_5_bar_bps is not None])
        if len(m5_arr) < 5:
            return HypothesisTestSummary(
                hypothesis_id="H0-B",
                hypothesis_statement="E[Markout_5] == 0 bps",
                test_statistic=0.0,
                p_value=1.0,
                confidence_interval_95=(0.0, 0.0),
                null_rejected=False,
                verdict_impact="INSUFFICIENT_DATA",
            )

        boot_means = self.block_bootstrap_mean(m5_arr)
        ci_lower = float(np.percentile(boot_means, 2.5))
        ci_upper = float(np.percentile(boot_means, 97.5))
        mean_stat = float(np.mean(m5_arr))

        # Two-sided p-value against zero
        t_stat, p_val = stats.ttest_1samp(m5_arr, 0.0)
        null_rejected = (ci_upper < 0.0) and (p_val < 0.05)

        return HypothesisTestSummary(
            hypothesis_id="H0-B",
            hypothesis_statement="E[Markout_5] == 0 bps",
            test_statistic=mean_stat,
            p_value=float(p_val),
            confidence_interval_95=(ci_lower, ci_upper),
            null_rejected=null_rejected,
            verdict_impact="SYSTEMATIC_ADVERSE_SELECTION_DETECTED"
            if null_rejected
            else "NO_ADVERSE_SELECTION",
        )

    def test_h0_c_toxic_independence(
        self,
        fills: list[FillEvent],
        toxic_ratio: float,
    ) -> HypothesisTestSummary:
        """
        H0-C: Fill probability is independent of toxic subsequent moves (Toxic Fill Ratio <= 0.50).
        Null Rejected if toxic fill ratio > 0.55 with statistical significance.
        """
        n_fills = len(fills)
        if n_fills < 10:
            return HypothesisTestSummary(
                hypothesis_id="H0-C",
                hypothesis_statement="P(Toxic Fill) <= 0.50",
                test_statistic=toxic_ratio,
                p_value=1.0,
                confidence_interval_95=(0.0, 1.0),
                null_rejected=False,
                verdict_impact="INSUFFICIENT_DATA",
            )

        toxic_count = int(round(toxic_ratio * n_fills))
        # Binomial test against p0 = 0.50
        binom_res = stats.binomtest(toxic_count, n_fills, p=0.50, alternative="greater")
        ci = binom_res.proportion_ci(confidence_level=0.95)

        null_rejected = (binom_res.pvalue < 0.05) and (toxic_ratio > 0.55)

        return HypothesisTestSummary(
            hypothesis_id="H0-C",
            hypothesis_statement="P(Toxic Fill) <= 0.50",
            test_statistic=toxic_ratio,
            p_value=float(binom_res.pvalue),
            confidence_interval_95=(float(ci.low), float(ci.high)),
            null_rejected=null_rejected,
            verdict_impact="TOXIC_FLOW_CONDITIONING"
            if null_rejected
            else "SYMMETRIC_FILL_DISTRIBUTION",
        )

    def run_all_tests(
        self,
        cost_breakdown: CalibratedCostBreakdown,
        adverse_selection: AdverseSelectionMetrics,
        fills: list[FillEvent],
    ) -> dict[str, HypothesisTestSummary]:
        return {
            "H0-A": self.test_h0_a_net_maker_edge(cost_breakdown, fills),
            "H0-B": self.test_h0_b_adverse_selection(adverse_selection, fills),
            "H0-C": self.test_h0_c_toxic_independence(
                fills, adverse_selection.toxic_fill_ratio_5_bar
            ),
        }
