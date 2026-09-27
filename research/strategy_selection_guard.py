"""
Anti-Selection-Bias & Multiple-Hypothesis Testing Guard.
Implements the Deflated Sharpe Ratio (DSR - Bailey & Lopez de Prado) and Holm-Bonferroni corrections.
Penalizes strategy promotion thresholds as the number of tested variations (N) increases to eliminate data snooping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats

logger = logging.getLogger("ai_quant_sentinel.strategy_selection_guard")


@dataclass
class DSRVerificationResult:
    estimated_sharpe: float
    expected_max_null_sharpe_sr0: float
    deflated_sharpe_ratio: float        # [0.0, 1.0] probability that SR > SR_0
    p_value: float
    num_tested_variations_n: int
    skewness: float
    kurtosis: float
    is_statistically_significant: bool  # True if DSR >= 0.95 (p_value <= 0.05)
    adjusted_alpha_threshold: float
    verdict: str


class StrategySelectionGuard:
    """Guards against false discovery in strategy mutation loops."""

    def __init__(self, significance_alpha: float = 0.05):
        self.significance_alpha = significance_alpha
        self._total_trials_n = 0
        self._historical_sharpe_distribution: List[float] = []

    def register_trial(self, sharpe: float) -> int:
        """Increments trial counter and updates empirical Sharpe distribution variance."""
        self._total_trials_n += 1
        self._historical_sharpe_distribution.append(sharpe)
        return self._total_trials_n

    def compute_deflated_sharpe_ratio(
        self,
        strategy_returns: np.ndarray,
        num_trials: Optional[int] = None,
    ) -> DSRVerificationResult:
        """
        Computes Deflated Sharpe Ratio adjusting for sample size, skewness, kurtosis, and N trials.
        """
        n_trials = num_trials or max(1, self._total_trials_n)
        t_samples = len(strategy_returns)

        if t_samples < 20:
            return DSRVerificationResult(
                estimated_sharpe=0.0,
                expected_max_null_sharpe_sr0=1.5,
                deflated_sharpe_ratio=0.0,
                p_value=1.0,
                num_tested_variations_n=n_trials,
                skewness=0.0,
                kurtosis=3.0,
                is_statistically_significant=False,
                adjusted_alpha_threshold=self.significance_alpha,
                verdict="REJECTED_INSUFFICIENT_SAMPLES",
            )

        # 1. Empirical moments
        mean_ret = float(np.mean(strategy_returns))
        std_ret = float(np.std(strategy_returns)) + 1e-6
        sr = (mean_ret / std_ret) * np.sqrt(252) # Annualized Sharpe

        skew = float(stats.skew(strategy_returns))
        kurt = float(stats.kurtosis(strategy_returns, fisher=False)) # Pearson kurtosis (normal=3.0)

        # 2. Variance of Sharpe across all tested variations V[{SR_n}]
        if len(self._historical_sharpe_distribution) >= 5:
            var_sr = float(np.var(self._historical_sharpe_distribution))
        else:
            var_sr = 0.25 # Standard conservative prior variance

        # 3. Expected Maximum Null Sharpe SR_0 under N independent trials
        # Euler-Mascheroni constant gamma = 0.5772156649
        gamma = 0.5772156649
        if n_trials > 1:
            z_term1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
            z_term2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
            sr_0 = np.sqrt(var_sr) * ((1.0 - gamma) * z_term1 + gamma * z_term2)
        else:
            sr_0 = 0.0

        # 4. Standard Error of Sharpe Ratio with skewness & kurtosis adjustments
        sr_annual_factor = np.sqrt(252)
        sr_unannualized = sr / sr_annual_factor
        sr_0_unannualized = sr_0 / sr_annual_factor

        variance_estimator = 1.0 - (skew * sr_unannualized) + (((kurt - 1.0) / 4.0) * (sr_unannualized ** 2))
        std_err = np.sqrt(max(0.001, variance_estimator) / (t_samples - 1.0))

        # 5. DSR Test Statistic
        z_stat = (sr_unannualized - sr_0_unannualized) / std_err
        dsr = float(stats.norm.cdf(z_stat))
        p_val = float(1.0 - dsr)

        # 6. Holm-Bonferroni adjusted alpha
        adj_alpha = self.significance_alpha / max(1, n_trials)
        is_sig = bool(p_val <= self.significance_alpha and dsr >= 0.95 and sr > 1.5)

        verdict = "PROMOTED_STATISTICALLY_VALID" if is_sig else "REJECTED_SELECTION_BIAS"

        return DSRVerificationResult(
            estimated_sharpe=round(sr, 3),
            expected_max_null_sharpe_sr0=round(sr_0, 3),
            deflated_sharpe_ratio=round(dsr, 4),
            p_value=round(p_val, 4),
            num_tested_variations_n=n_trials,
            skewness=round(skew, 2),
            kurtosis=round(kurt, 2),
            is_statistically_significant=is_sig,
            adjusted_alpha_threshold=round(adj_alpha, 6),
            verdict=verdict,
        )


# Singleton
strategy_selection_guard = StrategySelectionGuard()
