"""
Phase 15: Feature Ablation Framework.
Tests incremental feature combinations against a Baseline to evaluate genuine predictive edge
(Delta Expectancy in R, Win Rate improvement, Drawdown reduction, and Statistical Significance).
"""

from __future__ import annotations

import logging

import numpy as np

from core.sky_intelligence.types import AblationResult

logger = logging.getLogger("sky_intelligence.ablation_framework")


class FeatureAblationFramework:
    """
    Quantitative Feature Ablation and Incremental Predictive Edge Validator.
    """

    def run_ablation_study(
        self,
        baseline_outcomes_r: list[float],
        feature_test_outcomes_r: dict[str, list[float]],
    ) -> list[AblationResult]:
        """
        Runs ablation comparisons between baseline and incremental feature combinations.
        """
        results: list[AblationResult] = []

        base_n = len(baseline_outcomes_r)
        if base_n == 0:
            return []

        base_arr = np.array(baseline_outcomes_r)
        base_exp = float(np.mean(base_arr))
        base_wr = float(np.mean(base_arr > 0))
        base_pf = float(np.sum(base_arr[base_arr > 0])) / abs(
            float(np.sum(base_arr[base_arr < 0])) or 0.001
        )

        # Record Baseline entry
        results.append(
            AblationResult(
                feature_combination="BASELINE",
                sample_size=base_n,
                expectancy_r=round(base_exp, 3),
                win_rate=round(base_wr, 4),
                profit_factor=round(base_pf, 2),
                delta_expectancy_vs_baseline=0.0,
                is_statistically_significant=True,
            )
        )

        for combo_name, outcomes in feature_test_outcomes_r.items():
            n = len(outcomes)
            if n == 0:
                continue

            arr = np.array(outcomes)
            exp_val = float(np.mean(arr))
            wr = float(np.mean(arr > 0))
            pf = float(np.sum(arr[arr > 0])) / abs(float(np.sum(arr[arr < 0])) or 0.001)
            delta_exp = exp_val - base_exp

            # Two-sample t-test / Welch's t-statistic for significance
            var_base = float(np.var(base_arr, ddof=1)) if base_n > 1 else 1.0
            var_feat = float(np.var(arr, ddof=1)) if n > 1 else 1.0
            se_diff = np.sqrt((var_base / max(base_n, 1)) + (var_feat / max(n, 1)))
            t_stat = delta_exp / max(se_diff, 0.0001)

            # Significant if |t| > 1.96 (p < 0.05)
            is_sig = abs(t_stat) >= 1.96 and delta_exp > 0.05

            results.append(
                AblationResult(
                    feature_combination=combo_name,
                    sample_size=n,
                    expectancy_r=round(exp_val, 3),
                    win_rate=round(wr, 4),
                    profit_factor=round(pf, 2),
                    delta_expectancy_vs_baseline=round(delta_exp, 3),
                    is_statistically_significant=is_sig,
                )
            )

        return results


# Global singleton instance
ablation_framework = FeatureAblationFramework()
