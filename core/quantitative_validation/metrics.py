"""
core/quantitative_validation/metrics.py
======================================
Comprehensive statistical validation metrics for institutional strategy evaluation.
Eliminates win-rate bias by focusing on:
1. Net Expectancy in R (adjusted for fees, slippage, and funding).
2. Profit Factor and Win/Loss Ratios.
3. Wilson Score confidence intervals for win rates.
4. Block-bootstrap distribution and 95% Confidence Intervals for Expectancy.
5. Effective sample size (N_eff) adjusting for auto-correlation and trade clustering.
6. Deflated Sharpe Ratio (DSR) and Ulcer Index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class TradeReturn:
    trade_id: str
    symbol: str
    gross_r: float
    fee_r: float = 0.0
    slippage_r: float = 0.0
    funding_r: float = 0.0
    opened_at_ms: int = 0
    closed_at_ms: int = 0
    regime: str = "UNKNOWN"
    strategy_id: str = "DEFAULT"

    @property
    def net_r(self) -> float:
        return self.gross_r - self.fee_r - self.slippage_r - self.funding_r

    @property
    def is_win(self) -> bool:
        return self.net_r > 0.0


def calculate_net_expectancy(trades: list[TradeReturn] | list[float]) -> float:
    """
    Computes average net realized return in R per trade.
    E_net = sum(R_net) / N
    """
    if not trades:
        return 0.0
    if isinstance(trades[0], TradeReturn):
        net_returns = [t.net_r for t in trades]  # type: ignore[union-attr]
    else:
        net_returns = [float(x) for x in trades]  # type: ignore[union-attr]
    return float(np.mean(net_returns))


def calculate_profit_factor(trades: list[TradeReturn] | list[float]) -> float:
    """
    Gross Wins / |Gross Losses|.
    If no losses, returns round(gross_profit, 2) or float('inf').
    """
    if not trades:
        return 0.0
    if isinstance(trades[0], TradeReturn):
        net_returns = [t.net_r for t in trades]  # type: ignore[union-attr]
    else:
        net_returns = [float(x) for x in trades]  # type: ignore[union-attr]

    wins = [r for r in net_returns if r > 0.0]
    losses = [abs(r) for r in net_returns if r < 0.0]

    sum_wins = sum(wins)
    sum_losses = sum(losses)

    if sum_losses > 0.0:
        return round(float(sum_wins / sum_losses), 4)
    if sum_wins > 0.0:
        return 999.0  # Infinite profit factor capped for serialization
    return 0.0


def calculate_wilson_win_rate_ci(
    wins: int, total: int, confidence: float = 0.95
) -> tuple[float, float, float]:
    """
    Computes Wilson score interval for binomial proportions.
    Returns: (point_estimate, lower_bound, upper_bound) in percentages [0.0, 100.0].
    """
    if total <= 0:
        return 0.0, 0.0, 0.0

    p = wins / total
    z = stats.norm.ppf(1.0 - (1.0 - confidence) / 2.0)
    z2 = z * z
    n = float(total)

    denominator = 1.0 + z2 / n
    centre_adjusted_probability = p + z2 / (2.0 * n)
    adjusted_std_dev = math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)

    lower = (centre_adjusted_probability - z * adjusted_std_dev) / denominator
    upper = (centre_adjusted_probability + z * adjusted_std_dev) / denominator

    lower = max(0.0, lower) * 100.0
    upper = min(1.0, upper) * 100.0
    point = p * 100.0

    return round(point, 2), round(lower, 2), round(upper, 2)


def calculate_block_bootstrap_ci(
    returns: list[float],
    n_bootstrap: int = 2000,
    confidence: float = 0.95,
    block_size: int | None = None,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Dependence-aware stationary block bootstrap to compute confidence interval
    for expected net return E[R].
    Returns: (mean_expectancy, ci_lower, ci_upper)
    """
    n = len(returns)
    if n < 5:
        mean_val = float(np.mean(returns)) if returns else 0.0
        return mean_val, mean_val, mean_val

    arr = np.array(returns, dtype=np.float64)
    if block_size is None:
        block_size = max(2, round(n ** (1.0 / 3.0)))

    rng = np.random.default_rng(seed)
    num_blocks = math.ceil(n / block_size)

    bootstrap_means = np.empty(n_bootstrap, dtype=np.float64)
    for i in range(n_bootstrap):
        # Sample starting indices with replacement
        start_indices = rng.integers(0, max(1, n - block_size + 1), size=num_blocks)
        sampled_blocks = [arr[idx : idx + block_size] for idx in start_indices]
        sample = np.concatenate(sampled_blocks)[:n]
        bootstrap_means[i] = np.mean(sample)

    alpha = 1.0 - confidence
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - alpha / 2.0) * 100.0

    ci_lower = float(np.percentile(bootstrap_means, lower_pct))
    ci_upper = float(np.percentile(bootstrap_means, upper_pct))
    mean_val = float(np.mean(arr))

    return round(mean_val, 4), round(ci_lower, 4), round(ci_upper, 4)


def calculate_effective_sample_size(returns: list[float], max_lags: int = 10) -> float:
    """
    Computes effective sample size (N_eff) adjusting for autocorrelation:
    N_eff = N / (1 + 2 * sum_{k=1}^K (1 - k/K) * rho_k)
    """
    n = len(returns)
    if n < 3:
        return float(n)

    arr = np.array(returns, dtype=np.float64)
    denom = np.var(arr)
    if denom <= 1e-12:
        return float(n)

    mean_val = np.mean(arr)
    centered = arr - mean_val

    k_max = min(max_lags, n // 3)
    if k_max < 1:
        return float(n)

    autocorr_sum = 0.0
    for k in range(1, k_max + 1):
        c_k = np.dot(centered[:-k], centered[k:]) / ((n - k) * denom)
        # Bartlett kernel weighting
        weight = 1.0 - (k / (k_max + 1.0))
        autocorr_sum += weight * c_k

    inflation_factor = 1.0 + 2.0 * autocorr_sum
    inflation_factor = max(1.0, inflation_factor)  # Cannot be less than 1.0

    n_eff = float(n / inflation_factor)
    return round(max(1.0, min(float(n), n_eff)), 2)


def calculate_deflated_sharpe_ratio(
    returns: list[float],
    estimated_trials: int = 10,
    benchmark_sharpe: float = 0.0,
) -> tuple[float, float, float]:
    """
    Computes Deflated Sharpe Ratio (DSR) using Bailey and Lopez de Prado (2014).
    Returns: (annualized_sharpe, deflated_sharpe_ratio, p_value)
    """
    n = len(returns)
    if n < 5:
        return 0.0, 0.0, 1.0

    arr = np.array(returns, dtype=np.float64)
    std_val = float(np.std(arr, ddof=1))
    if std_val <= 1e-12:
        return 0.0, 0.0, 1.0

    mean_val = float(np.mean(arr))
    sharpe = mean_val / std_val

    # Skewness and Kurtosis
    skew = float(stats.skew(arr))
    kurt = float(stats.kurtosis(arr, fisher=False))  # Pearson kurtosis (normal = 3)

    # Standard error of Sharpe ratio
    var_sharpe = (1.0 + 0.5 * (sharpe**2) - skew * sharpe + ((kurt - 3.0) / 4.0) * (sharpe**2)) / (
        n - 1
    )
    se_sharpe = math.sqrt(max(1e-9, var_sharpe))

    # Expected maximum Sharpe under null hypothesis across multiple trials
    gamma = 0.57721566490153286  # Euler-Mascheroni constant
    z_trials = (1.0 - gamma) * stats.norm.ppf(
        1.0 - 1.0 / estimated_trials
    ) + gamma * stats.norm.ppf(1.0 - 1.0 / (estimated_trials * math.e))
    exp_max_sharpe = benchmark_sharpe + math.sqrt(max(1e-9, var_sharpe)) * z_trials

    dsr_stat = (sharpe - exp_max_sharpe) / se_sharpe
    p_val = float(1.0 - stats.norm.cdf(dsr_stat))
    dsr_cdf = float(stats.norm.cdf(dsr_stat))

    return round(sharpe, 4), round(dsr_cdf, 4), round(p_val, 4)


def calculate_drawdown_series(
    returns: list[float], starting_capital: float = 10000.0
) -> dict[str, Any]:
    """
    Computes peak-to-trough drawdown series, maximum drawdown percentage,
    and maximum drawdown duration.
    """
    if not returns:
        return {
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration": 0,
            "equity_curve": [starting_capital],
            "drawdown_pct_series": [0.0],
        }

    equity = starting_capital
    peak = equity
    equity_curve = [equity]
    dd_pct_series = [0.0]

    max_dd = 0.0
    current_dd_duration = 0
    max_dd_duration = 0

    for r in returns:
        equity += r
        equity_curve.append(round(equity, 2))
        if equity >= peak:
            peak = equity
            current_dd_duration = 0
        else:
            current_dd_duration += 1
            if current_dd_duration > max_dd_duration:
                max_dd_duration = current_dd_duration

        dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
        dd_pct_series.append(round(dd, 4))
        if dd > max_dd:
            max_dd = dd

    return {
        "max_drawdown_pct": round(max_dd, 2),
        "max_drawdown_duration": max_dd_duration,
        "equity_curve": equity_curve,
        "drawdown_pct_series": dd_pct_series,
    }


def calculate_ulcer_index(drawdown_pct_series: list[float]) -> float:
    """
    Computes Ulcer Index: quadratic mean of drawdowns.
    UI = sqrt(sum(DD_i^2) / N)
    """
    if not drawdown_pct_series:
        return 0.0
    arr = np.array(drawdown_pct_series, dtype=np.float64)
    squared_sum = np.sum(arr**2)
    return round(float(math.sqrt(squared_sum / len(arr))), 4)


def calculate_full_statistical_profile(trades: list[TradeReturn]) -> dict[str, Any]:
    """
    Executes deep statistical profiling across all dimensions.
    """
    n = len(trades)
    if n == 0:
        return {
            "total_trades": 0,
            "effective_sample_size": 0.0,
            "net_expectancy_r": 0.0,
            "expectancy_95_ci": (0.0, 0.0, 0.0),
            "win_rate_pct": 0.0,
            "win_rate_wilson_ci": (0.0, 0.0, 0.0),
            "profit_factor": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "win_loss_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration": 0,
            "ulcer_index": 0.0,
            "deflated_sharpe_ratio": 0.0,
            "dsr_p_value": 1.0,
            "sharpe_ratio": 0.0,
        }

    net_returns = [t.net_r for t in trades]
    wins = [r for r in net_returns if r > 0.0]
    losses = [r for r in net_returns if r < 0.0]

    expectancy_mean, exp_lower, exp_upper = calculate_block_bootstrap_ci(net_returns)
    win_point, win_lower, win_upper = calculate_wilson_win_rate_ci(len(wins), n)
    n_eff = calculate_effective_sample_size(net_returns)
    pf = calculate_profit_factor(trades)

    dd_info = calculate_drawdown_series(net_returns, starting_capital=10000.0)
    ulcer = calculate_ulcer_index(dd_info["drawdown_pct_series"])
    sharpe, dsr, dsr_p = calculate_deflated_sharpe_ratio(net_returns)

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0
    win_loss_ratio = (
        round(avg_win / avg_loss, 4) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)
    )

    return {
        "total_trades": n,
        "effective_sample_size": n_eff,
        "net_expectancy_r": expectancy_mean,
        "expectancy_95_ci": {
            "mean": expectancy_mean,
            "ci_lower": exp_lower,
            "ci_upper": exp_upper,
        },
        "win_rate_pct": win_point,
        "win_rate_wilson_ci": {
            "point": win_point,
            "ci_lower": win_lower,
            "ci_upper": win_upper,
        },
        "profit_factor": pf,
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss, 4),
        "win_loss_ratio": win_loss_ratio,
        "max_drawdown_pct": dd_info["max_drawdown_pct"],
        "max_drawdown_duration": dd_info["max_drawdown_duration"],
        "ulcer_index": ulcer,
        "deflated_sharpe_ratio": dsr,
        "dsr_p_value": dsr_p,
        "sharpe_ratio": sharpe,
    }
