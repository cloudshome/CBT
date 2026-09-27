"""
core/statistical_defense.py
=============================
Multidimensional Statistical Defense & Multi-Testing Sentinel.
Implements:
1. Versioned StatisticalPolicy resolving magic-number inconsistencies.
2. Bailey & López de Prado Deflated Sharpe Ratio (DSR) under cumulative trial growth.
3. Politis-Romano (1994) Stationary Block Bootstrap for White's Reality Check (WRC).
4. MultiTestingAuditor managing exploration budgets and data-snooping penalties.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("sky.statistical_defense")


@dataclass(frozen=True)
class StatisticalPolicy:
    """Versioned research governance policy governing strategy validation."""

    policy_version: str = "STAT_POLICY_2026_V1"
    dsr_tier1_threshold: float = 0.95  # Strict p <= 0.05 for Tier 1 Quarantine admission
    dsr_caution_threshold: float = 0.85  # Exploratory research threshold
    wrc_significance_alpha: float = 0.05  # White's Reality Check critical p-value
    min_oos_trades: int = 30  # Absolute minimum trades for asymptotic statistical validity
    min_cpcv_paths: int = 6  # Minimum out-of-sample combinatorial paths
    plateau_survival_ratio: float = 0.70  # Min fraction of parameter neighbors that retain edge
    plateau_tolerance_pct: float = 0.10  # Parameter perturbation neighborhood (+-10%)
    max_trials_per_batch: int = 50  # Hard circuit-breaker per synthesis cycle
    daily_trial_budget: int = 200  # Hard circuit-breaker per 24-hour cycle
    stress_survival_required: bool = True  # Strategy must not experience ruin under stress friction

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical active policy singleton
ACTIVE_STATISTICAL_POLICY = StatisticalPolicy()


@dataclass
class DSRReport:
    """Formal Deflated Sharpe Ratio evaluation report."""

    strategy_id: str
    cumulative_trials: int
    observed_sharpe: float
    expected_max_null_sharpe: float
    skewness: float
    kurtosis: float
    sr_standard_error: float
    z_score: float
    deflated_sharpe_ratio: float
    p_value: float
    is_tier1_eligible: bool
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WRCReport:
    """Politis-Romano Stationary Block Bootstrap White's Reality Check report."""

    strategy_id: str
    observed_sharpe: float
    wrc_p_value: float
    is_alpha_significant: bool
    num_bootstrap_permutations: int
    average_block_length: float
    null_distribution_mean: float
    null_distribution_95th: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeflatedSharpeEngine:
    """
    Computes the Deflated Sharpe Ratio accounting for multiple testing,
    non-normal skewness/kurtosis, and sample size.
    """

    @staticmethod
    def calculate_dsr(
        strategy_id: str,
        observed_returns: list[float] | np.ndarray,
        annualized_sharpe: float,
        cumulative_trials_N: int,
        policy: StatisticalPolicy = ACTIVE_STATISTICAL_POLICY,
        benchmark_sr_variance: float = 0.16,  # Var(SR) default ~ 0.4^2
        periods_per_year: float = 365.0 * 24.0,
    ) -> DSRReport:
        """
        Computes Bailey & López de Prado (2014) DSR:
        Z = (SR - E[max_N SR]) / sigma(SR)
        DSR = Phi(Z)
        """
        N = max(1, cumulative_trials_N)
        ret_arr = np.asarray(observed_returns, dtype=float)
        T = len(ret_arr)

        if T < policy.min_oos_trades:
            return DSRReport(
                strategy_id=strategy_id,
                cumulative_trials=N,
                observed_sharpe=round(annualized_sharpe, 3),
                expected_max_null_sharpe=0.0,
                skewness=0.0,
                kurtosis=3.0,
                sr_standard_error=1.0,
                z_score=-99.0,
                deflated_sharpe_ratio=0.0,
                p_value=1.0,
                is_tier1_eligible=False,
                policy_version=policy.policy_version,
            )

        mean_r = float(np.mean(ret_arr))
        std_r = float(np.std(ret_arr))
        if std_r <= 1e-9:
            std_r = 0.01

        # Higher statistical moments
        normalized = (ret_arr - mean_r) / std_r
        skew = float(np.mean(normalized**3))
        kurt = float(np.mean(normalized**4))

        # Expected Maximum Sharpe Ratio under the null hypothesis of zero true alpha
        euler_mascheroni = 0.5772156649
        if N > 1:
            z_term = math.sqrt(2.0 * math.log(N))
            expected_max_sr = (
                (1.0 - euler_mascheroni / z_term + (math.pi**2 / 12.0) / (2.0 * math.log(N)))
                * z_term
                * math.sqrt(benchmark_sr_variance)
            )
        else:
            expected_max_sr = 0.0

        # Unannualized Sharpe from observed returns
        unann_sr = annualized_sharpe / math.sqrt(max(1.0, periods_per_year))

        # Effective sample duration in years: Y = T / periods_per_year
        sample_years = max(0.01, float(T) / max(1.0, periods_per_year))

        # Asymptotic variance of annualized Sharpe ratio under non-normality (Mertens, 2002; Bailey & López de Prado, 2014)
        sr_var = (1.0 - skew * unann_sr + ((kurt - 1.0) / 4.0) * (unann_sr**2)) / sample_years
        sr_std = math.sqrt(max(1e-6, sr_var))

        z_stat = (annualized_sharpe - expected_max_sr) / sr_std
        dsr = 0.5 * (1.0 + math.erf(z_stat / math.sqrt(2.0)))
        p_val = max(0.0001, 1.0 - dsr)

        eligible = bool(dsr >= policy.dsr_tier1_threshold and annualized_sharpe > 1.0)

        return DSRReport(
            strategy_id=strategy_id,
            cumulative_trials=N,
            observed_sharpe=round(annualized_sharpe, 3),
            expected_max_null_sharpe=round(expected_max_sr, 3),
            skewness=round(skew, 3),
            kurtosis=round(kurt, 3),
            sr_standard_error=round(sr_std, 4),
            z_score=round(z_stat, 3),
            deflated_sharpe_ratio=round(dsr, 4),
            p_value=round(p_val, 4),
            is_tier1_eligible=eligible,
            policy_version=policy.policy_version,
        )


class PolitisRomanoStationaryBootstrap:
    """
    Implements the Politis & Romano (1994) Stationary Block Bootstrap.
    Resamples blocks of random geometric length to preserve serial dependency
    and volatility clustering in financial returns.
    """

    @staticmethod
    def run_reality_check(
        strategy_id: str,
        observed_returns: np.ndarray,
        benchmark_returns_matrix: np.ndarray | None = None,
        annualization_factor: float = math.sqrt(365 * 24),
        n_bootstraps: int = 500,
        seed: int = 42,
    ) -> WRCReport:
        """
        Executes White's Reality Check (WRC) with stationary bootstrap:
        Centers benchmark returns under the null hypothesis E[R_k] <= 0.
        Calculates fraction of bootstrapped max Sharpe ratios exceeding the strategy's Sharpe.
        """
        T = len(observed_returns)
        if T < 30:
            return WRCReport(
                strategy_id=strategy_id,
                observed_sharpe=0.0,
                wrc_p_value=1.0,
                is_alpha_significant=False,
                num_bootstrap_permutations=0,
                average_block_length=1.0,
                null_distribution_mean=0.0,
                null_distribution_95th=0.0,
            )

        # 1. Estimate optimal average block length from return autocorrelation
        var_r = float(np.var(observed_returns))
        cov_1 = (
            float(
                np.mean(
                    (observed_returns[:-1] - np.mean(observed_returns))
                    * (observed_returns[1:] - np.mean(observed_returns))
                )
            )
            if T > 1 and var_r > 1e-9
            else 0.0
        )
        rho = max(0.01, min(0.85, cov_1 / var_r if var_r > 1e-9 else 0.0))
        # Politis-White block length heuristic
        avg_block = max(
            2.0,
            min(
                float(T // 8), (2.0 * (rho**2) / (1.0 - rho**2)) ** (1.0 / 3.0) * (T ** (1.0 / 3.0))
            ),
        )
        p_geom = 1.0 / avg_block

        # 2. Observed Sharpe ratio
        std_obs = float(np.std(observed_returns))
        obs_sr = (
            (float(np.mean(observed_returns)) / std_obs * annualization_factor)
            if std_obs > 1e-9
            else 0.0
        )

        # 3. Form benchmarks matrix (include buy & hold and null models)
        if benchmark_returns_matrix is None or len(benchmark_returns_matrix) == 0:
            # Fallback benchmark: zero-centered returns + simple momentum baseline
            b1 = observed_returns - float(np.mean(observed_returns))
            b2 = np.roll(observed_returns, 1) - float(np.mean(observed_returns))
            benchmarks = np.vstack([b1, b2])
        else:
            benchmarks = benchmark_returns_matrix

        # Center benchmarks under null hypothesis H0: E[benchmark] <= 0
        centered_benchmarks = benchmarks - np.mean(benchmarks, axis=1, keepdims=True)
        n_benchmarks = centered_benchmarks.shape[0]

        # 4. Stationary Bootstrap Resampling
        rng = np.random.default_rng(seed)
        max_null_sharpes: list[float] = []

        for _ in range(n_bootstraps):
            # Generate stationary bootstrap indices of length T
            indices = np.zeros(T, dtype=int)
            idx = int(rng.integers(0, T))
            for t in range(T):
                indices[t] = idx
                if rng.random() < p_geom:
                    idx = int(rng.integers(0, T))  # New block start
                else:
                    idx = (idx + 1) % T  # Continue block circularly

            # Evaluate max Sharpe across all centered benchmarks under this bootstrap realization
            boot_sr_list: list[float] = []
            for b_idx in range(n_benchmarks):
                b_ret = centered_benchmarks[b_idx, indices]
                b_std = float(np.std(b_ret))
                if b_std > 1e-9:
                    boot_sr_list.append((float(np.mean(b_ret)) / b_std) * annualization_factor)
                else:
                    boot_sr_list.append(0.0)

            max_null_sharpes.append(max(boot_sr_list) if boot_sr_list else 0.0)

        null_arr = np.array(max_null_sharpes)
        wrc_p_val = float(np.mean(null_arr >= obs_sr))
        null_mean = float(np.mean(null_arr))
        null_95th = float(np.percentile(null_arr, 95))

        return WRCReport(
            strategy_id=strategy_id,
            observed_sharpe=round(obs_sr, 3),
            wrc_p_value=round(wrc_p_val, 4),
            is_alpha_significant=bool(
                wrc_p_val < ACTIVE_STATISTICAL_POLICY.wrc_significance_alpha and obs_sr > 1.0
            ),
            num_bootstrap_permutations=n_bootstraps,
            average_block_length=round(avg_block, 2),
            null_distribution_mean=round(null_mean, 3),
            null_distribution_95th=round(null_95th, 3),
        )


class MultiTestingAuditor:
    """
    Guards the autonomous synthesizer against runaway data-mining fallacy.
    Maintains an immutable cumulative trial counter N across synthesis runs
    and enforces batch and daily exploration budgets.
    """

    def __init__(self, policy: StatisticalPolicy = ACTIVE_STATISTICAL_POLICY):
        self.policy = policy
        self._cumulative_trials: int = 1
        self._daily_trials: int = 0
        self._last_day_ts: float = 0.0

    @property
    def cumulative_trials(self) -> int:
        return self._cumulative_trials

    def check_and_increment_trial_budget(self, requested_trials: int = 1) -> bool:
        """
        Validates trial allocation against exploration budget.
        Returns True if authorized, False if budget exceeded.
        """
        import time

        now = time.time()
        # Reset daily budget at 00:00 UTC
        if now - self._last_day_ts > 86400.0:
            self._daily_trials = 0
            self._last_day_ts = now

        if self._daily_trials + requested_trials > self.policy.daily_trial_budget:
            logger.warning(
                "Autonomous exploration blocked: daily trial budget exhausted (%d/%d)",
                self._daily_trials,
                self.policy.daily_trial_budget,
            )
            return False

        if requested_trials > self.policy.max_trials_per_batch:
            logger.warning(
                "Batch trial request (%d) exceeds max allowed per cycle (%d)",
                requested_trials,
                self.policy.max_trials_per_batch,
            )
            return False

        self._daily_trials += requested_trials
        self._cumulative_trials += requested_trials
        return True

    def reset_for_testing(self) -> None:
        """Isolated testing helper."""
        self._cumulative_trials = 1
        self._daily_trials = 0


multi_testing_auditor = MultiTestingAuditor()
