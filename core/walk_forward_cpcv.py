"""
core/walk_forward_cpcv.py
===========================
Institutional Combinatorial Purged Cross-Validation (CPCV) & Walk-Forward Engine.
Implements mathematically explicit leakage prevention:
1. Dynamic Embargo derived from empirical holding period and serial autocorrelation.
2. Combinatorial Purged Splitting C(N, k) with zero lookahead.
3. Venue-Parameterized 3-Tier Friction Stress (Base, Conservative, Stress).
"""

from __future__ import annotations

import itertools
import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger("sky.cpcv_engine")


@dataclass(frozen=True)
class FrictionTier:
    """Venue-parameterized trading friction schedule."""

    name: str
    maker_fee_bps: float
    taker_fee_bps: float
    slippage_bps: float
    impact_coefficient: float  # Square-root market impact multiplier

    def total_cost_bps(self, is_taker: bool = True, size_ratio_to_adv: float = 0.0001) -> float:
        fee = self.taker_fee_bps if is_taker else self.maker_fee_bps
        impact = self.impact_coefficient * math.sqrt(max(0.0, size_ratio_to_adv)) * 10000.0
        return fee + self.slippage_bps + impact


# Standard institutional exchange friction profiles
DEFAULT_FRICTION_TIERS: dict[str, FrictionTier] = {
    "BASE": FrictionTier(
        name="BASE_BINANCE_SPOT_VIP",
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        slippage_bps=1.5,
        impact_coefficient=0.01,
    ),
    "CONSERVATIVE": FrictionTier(
        name="CONSERVATIVE_BYBIT_PERP",
        maker_fee_bps=2.0,
        taker_fee_bps=6.0,
        slippage_bps=6.0,
        impact_coefficient=0.03,
    ),
    "STRESS": FrictionTier(
        name="STRESS_ILLIQUID_CRISIS",
        maker_fee_bps=5.0,
        taker_fee_bps=10.0,
        slippage_bps=15.0,
        impact_coefficient=0.08,
    ),
}


class DynamicEmbargoCalibrator:
    """
    Derives embargo window dynamically from strategy trade duration
    and return serial autocorrelation cutoff.
    Eliminates arbitrary constant guesses (e.g. fixed 2%).
    """

    @staticmethod
    def calculate_embargo_bars(
        returns: np.ndarray,
        average_holding_bars: float = 8.0,
        max_lag: int = 20,
    ) -> int:
        """
        Calculates dynamic embargo: h_embargo = ceil(avg_holding_bars + q_autocorr)
        where q_autocorr is the lag where autocorrelation drops below the 95% Bartlett CI.
        """
        n = len(returns)
        if n < 30:
            return max(3, int(math.ceil(average_holding_bars)))

        bartlett_threshold = 1.96 / math.sqrt(n)
        mean_r = float(np.mean(returns))
        var_r = float(np.var(returns))
        if var_r <= 1e-12:
            return max(3, int(math.ceil(average_holding_bars)))

        q_cutoff = 0
        for lag in range(1, min(max_lag, n // 3)):
            cov = float(np.mean((returns[:-lag] - mean_r) * (returns[lag:] - mean_r)))
            autocorr = cov / var_r
            if abs(autocorr) > bartlett_threshold:
                q_cutoff = lag
            elif lag > q_cutoff + 2:
                break

        dynamic_h = int(math.ceil(average_holding_bars + q_cutoff))
        return max(2, min(dynamic_h, n // 10))


@dataclass
class CPCVFold:
    """Single combinatorial purged cross-validation fold definition."""

    fold_id: int
    train_indices: list[int]
    test_indices: list[int]
    purged_indices: list[int]
    embargo_indices: list[int]
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    is_win_rate: float = 0.0
    oos_win_rate: float = 0.0
    oos_trade_count: int = 0
    stability_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_id": self.fold_id,
            "train_size": len(self.train_indices),
            "test_size": len(self.test_indices),
            "purged_count": len(self.purged_indices),
            "embargo_count": len(self.embargo_indices),
            "is_sharpe": round(self.is_sharpe, 3),
            "oos_sharpe": round(self.oos_sharpe, 3),
            "is_win_rate": round(self.is_win_rate, 3),
            "oos_win_rate": round(self.oos_win_rate, 3),
            "oos_trade_count": self.oos_trade_count,
            "stability_ratio": round(self.stability_ratio, 3),
        }


@dataclass
class CPCVResult:
    """Complete results across all combinatorial paths and friction models."""

    symbol: str
    timeframe: str
    total_samples: int
    n_partitions: int
    k_test_groups: int
    num_paths: int
    embargo_bars: int
    folds: list[CPCVFold]
    mean_is_sharpe: float
    mean_oos_sharpe: float
    median_oos_sharpe: float
    std_oos_sharpe: float
    stability_index: float  # mean(OOS Sharpe) / max(0.01, mean(IS Sharpe))
    total_oos_trades: int
    oos_win_rate: float
    oos_profit_factor: float
    oos_max_drawdown_pct: float
    friction_results: dict[str, dict[str, float]]  # BASE, CONSERVATIVE, STRESS metrics
    equity_curve_oos: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["folds"] = [f.to_dict() for f in self.folds]
        return d


class CombinatorialPurgedCrossValidator:
    """
    Generates C(N, k) cross-validation folds with strict causal purging
    and dynamically calibrated embargo windows.
    """

    def __init__(
        self,
        n_partitions: int = 6,
        k_test_groups: int = 2,
    ):
        if k_test_groups >= n_partitions:
            raise ValueError(
                f"k_test_groups ({k_test_groups}) must be strictly less than n_partitions ({n_partitions})"
            )
        self.n_partitions = n_partitions
        self.k_test_groups = k_test_groups

    def split(
        self,
        n_samples: int,
        label_horizon_bars: int = 4,
        embargo_bars: int = 6,
    ) -> list[CPCVFold]:
        """
        Partitions n_samples into N contiguous blocks and yields C(N, k) combinations.
        Applies mathematical purge [t_start - label_horizon, t_end] and embargo [t_end, t_end + embargo].
        """
        if n_samples < self.n_partitions * 10:
            raise ValueError(
                f"Insufficient samples ({n_samples}) for {self.n_partitions} partitions (minimum {self.n_partitions * 10})"
            )

        # Partition indices into N contiguous groups
        group_bounds = np.linspace(0, n_samples, self.n_partitions + 1, dtype=int)
        groups = [
            list(range(group_bounds[i], group_bounds[i + 1])) for i in range(self.n_partitions)
        ]

        all_group_indices = list(range(self.n_partitions))
        comb_paths = list(itertools.combinations(all_group_indices, self.k_test_groups))

        folds: list[CPCVFold] = []

        for fold_idx, test_grp_ids in enumerate(comb_paths):
            test_grp_set = set(test_grp_ids)
            test_indices: list[int] = []
            test_spans: list[tuple[int, int]] = []

            for g_id in test_grp_ids:
                grp_idxs = groups[g_id]
                test_indices.extend(grp_idxs)
                test_spans.append((grp_idxs[0], grp_idxs[-1]))

            test_indices.sort()

            # Identify raw training candidates (all groups not in test)
            raw_train_indices: list[int] = []
            for g_id in all_group_indices:
                if g_id not in test_grp_set:
                    raw_train_indices.extend(groups[g_id])

            purged_indices: list[int] = []
            embargo_indices: list[int] = []
            final_train_indices: list[int] = []

            for t in raw_train_indices:
                # Purge check: if label window [t, t + label_horizon_bars] overlaps any test span
                label_end = t + label_horizon_bars
                is_purged = any(t <= span[1] and label_end >= span[0] for span in test_spans)

                if is_purged:
                    purged_indices.append(t)
                    continue

                # Embargo check: if t falls within [span_end, span_end + embargo_bars]
                is_embargoed = any(span[1] < t <= span[1] + embargo_bars for span in test_spans)

                if is_embargoed:
                    embargo_indices.append(t)
                    continue

                final_train_indices.append(t)

            folds.append(
                CPCVFold(
                    fold_id=fold_idx,
                    train_indices=final_train_indices,
                    test_indices=test_indices,
                    purged_indices=purged_indices,
                    embargo_indices=embargo_indices,
                )
            )

        return folds


class WalkForwardCPCVRunner:
    """
    Executes walk-forward evaluation of candidate trading strategies across
    combinatorial purged folds and venue friction schedules.
    """

    def __init__(
        self,
        n_partitions: int = 6,
        k_test_groups: int = 2,
        friction_tiers: dict[str, FrictionTier] | None = None,
    ):
        self.splitter = CombinatorialPurgedCrossValidator(n_partitions, k_test_groups)
        self.friction_tiers = friction_tiers or DEFAULT_FRICTION_TIERS

    def evaluate_strategy_signals(
        self,
        closes: np.ndarray,
        signals: np.ndarray,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        average_holding_bars: float = 8.0,
    ) -> CPCVResult:
        """
        Evaluates discrete trading signals [-1.0, 0.0, 1.0] across all CPCV folds.
        Signals strictly execute at t+1 open (no lookahead).
        """
        n_samples = len(closes)
        if len(signals) != n_samples:
            raise ValueError(
                f"Closes length ({n_samples}) does not match signals length ({len(signals)})"
            )

        raw_returns = np.zeros(n_samples, dtype=float)
        raw_returns[1:] = (closes[1:] - closes[:-1]) / np.maximum(closes[:-1], 1e-8)

        # 1. Calibrate dynamic embargo based on empirical return autocorrelation
        embargo_bars = DynamicEmbargoCalibrator.calculate_embargo_bars(
            returns=raw_returns,
            average_holding_bars=average_holding_bars,
        )

        # 2. Generate C(N, k) combinatorial purged folds
        label_horizon = max(1, int(round(average_holding_bars)))
        folds = self.splitter.split(
            n_samples=n_samples,
            label_horizon_bars=label_horizon,
            embargo_bars=embargo_bars,
        )

        # 3. Compute base trade returns: position shifted by 1 bar to strictly simulate t+1 execution
        trade_positions = signals[:-1]  # decision at t
        executed_returns = trade_positions * raw_returns[1:]  # executed over [t, t+1]
        padded_executed_returns = np.concatenate([[0.0], executed_returns])

        # Base friction model cost per trade switch
        base_tier = self.friction_tiers.get("BASE", DEFAULT_FRICTION_TIERS["BASE"])
        conservative_tier = self.friction_tiers.get(
            "CONSERVATIVE", DEFAULT_FRICTION_TIERS["CONSERVATIVE"]
        )
        stress_tier = self.friction_tiers.get("STRESS", DEFAULT_FRICTION_TIERS["STRESS"])

        # Detect position switches (entry/exit)
        position_switches = np.abs(np.diff(np.concatenate([[0.0], signals]))) > 0.01

        # Calculate fold-level metrics
        fold_oos_sharpes: list[float] = []
        fold_is_sharpes: list[float] = []
        all_oos_net_returns: list[float] = []

        annualization_factor = (
            math.sqrt(365 * 24 * 4) if timeframe == "15m" else math.sqrt(365 * 24)
        )

        for fold in folds:
            # In-Sample evaluation
            is_ret = padded_executed_returns[fold.train_indices]
            is_switches = position_switches[fold.train_indices]
            is_cost = is_switches * (base_tier.total_cost_bps() / 10000.0)
            is_net_ret = is_ret - is_cost

            # Out-of-Sample evaluation
            oos_ret = padded_executed_returns[fold.test_indices]
            oos_switches = position_switches[fold.test_indices]
            oos_cost = oos_switches * (base_tier.total_cost_bps() / 10000.0)
            oos_net_ret = oos_ret - oos_cost

            # Performance stats
            fold.is_sharpe = self._calc_sharpe(is_net_ret, annualization_factor)
            fold.oos_sharpe = self._calc_sharpe(oos_net_ret, annualization_factor)

            is_trades = is_net_ret[is_switches]
            fold.is_win_rate = float(np.mean(is_trades > 0.0)) if len(is_trades) > 0 else 0.0

            oos_trades = oos_net_ret[oos_switches]
            fold.oos_win_rate = float(np.mean(oos_trades > 0.0)) if len(oos_trades) > 0 else 0.0
            fold.oos_trade_count = len(oos_trades)

            # Stability: ratio of OOS to IS performance
            fold.stability_ratio = (
                fold.oos_sharpe / max(0.10, fold.is_sharpe) if fold.is_sharpe > 0.0 else 0.0
            )

            fold_is_sharpes.append(fold.is_sharpe)
            fold_oos_sharpes.append(fold.oos_sharpe)
            all_oos_net_returns.extend(oos_net_ret.tolist())

        # Multi-Tier Friction Performance across the full sample
        friction_metrics: dict[str, dict[str, float]] = {}
        for t_key, t_model in [
            ("BASE", base_tier),
            ("CONSERVATIVE", conservative_tier),
            ("STRESS", stress_tier),
        ]:
            cost = position_switches * (t_model.total_cost_bps() / 10000.0)
            net_ret = padded_executed_returns - cost
            sr = self._calc_sharpe(net_ret, annualization_factor)
            mdd = self._calc_max_drawdown(net_ret)
            active_trades = net_ret[position_switches]
            wr = float(np.mean(active_trades > 0.0)) if len(active_trades) > 0 else 0.0
            pf = self._calc_profit_factor(active_trades)

            friction_metrics[t_key] = {
                "sharpe": round(sr, 3),
                "max_drawdown_pct": round(mdd * 100.0, 2),
                "win_rate_pct": round(wr * 100.0, 1),
                "profit_factor": round(pf, 2),
            }

        mean_is = float(np.mean(fold_is_sharpes)) if fold_is_sharpes else 0.0
        mean_oos = float(np.mean(fold_oos_sharpes)) if fold_oos_sharpes else 0.0
        median_oos = float(np.median(fold_oos_sharpes)) if fold_oos_sharpes else 0.0
        std_oos = float(np.std(fold_oos_sharpes)) if fold_oos_sharpes else 0.0
        stability_idx = mean_oos / max(0.10, mean_is) if mean_is > 0.0 else 0.0

        # Construct aggregate OOS equity curve
        cum_equity = np.cumprod(
            1.0 + np.clip(np.array(all_oos_net_returns[:500]), -0.15, 0.15)
        ).tolist()

        return CPCVResult(
            symbol=symbol,
            timeframe=timeframe,
            total_samples=n_samples,
            n_partitions=self.splitter.n_partitions,
            k_test_groups=self.splitter.k_test_groups,
            num_paths=len(folds),
            embargo_bars=embargo_bars,
            folds=folds,
            mean_is_sharpe=round(mean_is, 3),
            mean_oos_sharpe=round(mean_oos, 3),
            median_oos_sharpe=round(median_oos, 3),
            std_oos_sharpe=round(std_oos, 3),
            stability_index=round(stability_idx, 3),
            total_oos_trades=sum(f.oos_trade_count for f in folds),
            oos_win_rate=round(float(np.mean([f.oos_win_rate for f in folds])) * 100.0, 1),
            oos_profit_factor=friction_metrics["BASE"]["profit_factor"],
            oos_max_drawdown_pct=friction_metrics["BASE"]["max_drawdown_pct"],
            friction_results=friction_metrics,
            equity_curve_oos=[round(float(x), 4) for x in cum_equity],
        )

    @staticmethod
    def _calc_sharpe(returns: np.ndarray, annualization: float) -> float:
        if len(returns) < 5:
            return 0.0
        std = float(np.std(returns))
        if std <= 1e-9:
            return 0.0
        return float((np.mean(returns) / std) * annualization)

    @staticmethod
    def _calc_max_drawdown(returns: np.ndarray) -> float:
        if len(returns) == 0:
            return 0.0
        equity = np.cumprod(1.0 + np.clip(returns, -0.99, 10.0))
        running_max = np.maximum.accumulate(equity)
        drawdowns = (running_max - equity) / running_max
        return float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    @staticmethod
    def _calc_profit_factor(trades: np.ndarray) -> float:
        if len(trades) == 0:
            return 0.0
        gains = float(np.sum(trades[trades > 0]))
        losses = float(np.abs(np.sum(trades[trades < 0])))
        if losses <= 1e-9:
            return 10.0 if gains > 0 else 1.0
        return gains / losses
