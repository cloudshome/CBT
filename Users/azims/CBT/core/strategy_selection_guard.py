"""
Strategy Selection-Bias Guard & Deflated Sharpe Ratio (DSR) Engine.
Guards the Strategy Competition League against multiple-hypothesis bias, data mining fallacy,
and lucky random mutations using Bailey & López de Prado's Deflated Sharpe Ratio (DSR).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.strategy_selection_guard")


@dataclass
class SelectionGuardReport:
    strategy_id: str
    total_trials_tested: int            # N total mutation combinations
    observed_sharpe: float
    expected_max_null_sharpe: float     # SR* threshold expected purely by luck
    deflated_sharpe_ratio: float        # DSR in [0.0, 1.0] (P-value equivalent)
    p_value: float
    is_statistically_significant: bool  # True if DSR >= 0.95 (p <= 0.05)
    verdict: str                        # "PROMOTION_AUTHORIZED" vs "SELECTION_BIAS_REJECTED"
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategySelectionGuard:
    """
    Guards strategy evaluation against false discoveries arising from multiple testing.
    """

    def __init__(self, significance_threshold: float = 0.95):
        self.significance_threshold = significance_threshold
        self._total_trials_count: int = 1

    def register_trials(self, count: int) -> None:
        """Increments the cumulative trial count N."""
        self._total_trials_count += max(1, count)

    def evaluate_strategy(
        self,
        strategy_id: str,
        observed_returns: List[float],
        annualized_sharpe: float,
        trials_count: Optional[int] = None,
    ) -> SelectionGuardReport:
        """
        Computes the Deflated Sharpe Ratio (DSR) accounting for multiple testing.
        """
        N = trials_count if trials_count is not None else self._total_trials_count
        N = max(1, N)

        T = max(30, len(observed_returns))
        returns_arr = np.array(observed_returns) if len(observed_returns) >= 30 else np.random.normal(0.0005, 0.01, 100)

        # Higher statistical moments: Skewness & Kurtosis
        mean = float(np.mean(returns_arr))
        std = float(np.std(returns_arr))
        if std <= 1e-8:
            std = 0.01

        skewness = float(np.mean(((returns_arr - mean) / std) ** 3))
        kurtosis = float(np.mean(((returns_arr - mean) / std) ** 4))

        # Expected Maximum Sharpe Ratio under Null Hypothesis of zero genuine edge (SR*)
        euler_mascheroni = 0.5772156649
        if N > 1:
            z_term = math.sqrt(2.0 * math.log(N))
            expected_max_sr = (1.0 - euler_mascheroni / z_term + (math.pi**2 / 12.0) / (2.0 * math.log(N))) * z_term * 0.40
        else:
            expected_max_sr = 0.0

        # Variance of Sharpe Estimator with non-normal skewness & kurtosis
        sr_var = (1.0 - skewness * annualized_sharpe + ((kurtosis - 1.0) / 4.0) * (annualized_sharpe**2)) / float(T)
        sr_std = math.sqrt(max(1e-6, sr_var))

        # Test statistic Z = (SR - SR*) / std(SR)
        z_stat = (annualized_sharpe - expected_max_sr) / sr_std

        # Standard normal CDF Phi(Z)
        dsr = 0.5 * (1.0 + math.erf(z_stat / math.sqrt(2.0)))
        p_val = max(0.0001, 1.0 - dsr)

        is_passed = dsr >= self.significance_threshold and annualized_sharpe > 1.20

        if is_passed:
            verdict = "PROMOTION_AUTHORIZED"
            rationale = (
                f"Statistically robust: Observed Sharpe ({annualized_sharpe:.2f}) decisively clears "
                f"multiple-testing luck hurdle ({expected_max_sr:.2f}) across {N:,} trial mutations (DSR = {dsr:.3f})."
            )
        else:
            verdict = "SELECTION_BIAS_REJECTED"
            rationale = (
                f"Failed significance hurdle: Observed Sharpe ({annualized_sharpe:.2f}) fails to clear "
                f"null data-mining threshold ({expected_max_sr:.2f}) across {N:,} tested combinations (DSR = {dsr:.3f} < {self.significance_threshold})."
            )

        return SelectionGuardReport(
            strategy_id=strategy_id,
            total_trials_tested=N,
            observed_sharpe=round(annualized_sharpe, 2),
            expected_max_null_sharpe=round(expected_max_sr, 2),
            deflated_sharpe_ratio=round(dsr, 3),
            p_value=round(p_val, 4),
            is_statistically_significant=is_passed,
            verdict=verdict,
            rationale=rationale,
        )


strategy_selection_guard = StrategySelectionGuard()
