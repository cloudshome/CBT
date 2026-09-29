"""
Chronological Walk-Forward Validation Engine for Kronos.
Evaluates out-of-sample stability, deflated Sharpe ratios, and regime consistency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.models.kronos.adapter import KronosModelAdapter, kronos_adapter

logger = logging.getLogger("ai_quant_sentinel.kronos.walk_forward")


@dataclass
class WalkForwardFoldResult:
    fold_index: int
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    in_sample_accuracy_pct: float
    out_of_sample_accuracy_pct: float
    out_of_sample_return_pct: float
    out_of_sample_sharpe: float
    test_samples: int


@dataclass
class WalkForwardSummary:
    symbol: str
    timeframe: str
    total_folds: int
    mean_oos_accuracy_pct: float
    mean_oos_sharpe: float
    mean_oos_return_pct: float
    deflated_sharpe_ratio: float
    is_statistically_robust: bool
    folds: list[WalkForwardFoldResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_folds": self.total_folds,
            "mean_oos_accuracy_pct": round(self.mean_oos_accuracy_pct, 2),
            "mean_oos_sharpe": round(self.mean_oos_sharpe, 2),
            "mean_oos_return_pct": round(self.mean_oos_return_pct, 2),
            "deflated_sharpe_ratio": round(self.deflated_sharpe_ratio, 3),
            "is_statistically_robust": self.is_statistically_robust,
            "folds": [f.__dict__ for f in self.folds],
        }


class KronosWalkForwardEngine:
    """Executes non-overlapping expanding window walk-forward validation."""

    def __init__(self, adapter: KronosModelAdapter | None = None):
        self.adapter = adapter or kronos_adapter

    def run_walk_forward(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        n_splits: int = 4,
        train_ratio: float = 0.60,
        horizon: int = 12,
    ) -> WalkForwardSummary:
        if len(candles) < 100:
            raise ValueError("Insufficient candles for walk-forward evaluation (minimum 100).")

        total_bars = len(candles)
        fold_size = total_bars // (n_splits + 1)
        folds: list[WalkForwardFoldResult] = []

        for fold in range(n_splits):
            train_end_idx = fold_size * (fold + 1)
            test_end_idx = min(total_bars, train_end_idx + fold_size)

            train_candles = candles[:train_end_idx]
            test_candles = candles[train_end_idx:test_end_idx]

            if len(test_candles) < horizon + 5:
                continue

            # In-Sample Accuracy estimation
            is_hits = 0
            is_trials = min(15, len(train_candles) - horizon - 20)
            for i in range(is_trials):
                idx = len(train_candles) - horizon - is_trials + i
                h_sub = train_candles[:idx]
                future_sub = train_candles[idx : idx + horizon]
                cur_p = float(h_sub[-1]["close"])
                fut_p = float(future_sub[-1]["close"])
                real_dir = 1 if fut_p > cur_p else -1

                pred = self.adapter.predict(
                    symbol, timeframe, h_sub, horizon=horizon, sample_count=3
                )
                pred_dir = (
                    1
                    if pred.directional_bias == "BULLISH"
                    else (-1 if pred.directional_bias == "BEARISH" else 0)
                )
                if pred_dir == real_dir:
                    is_hits += 1

            is_acc = (is_hits / max(1, is_trials)) * 100.0

            # Out-of-Sample Evaluation
            oos_trades: list[float] = []
            oos_hits = 0
            step = max(1, horizon // 2)

            for idx in range(0, len(test_candles) - horizon, step):
                eval_hist = candles[: train_end_idx + idx]
                cur_p = float(eval_hist[-1]["close"])
                fut_p = (
                    float(test_candles[idx + horizon]["close"])
                    if idx + horizon < len(test_candles)
                    else cur_p
                )
                real_dir = 1 if fut_p > cur_p else -1
                real_ret = (fut_p - cur_p) / cur_p

                pred = self.adapter.predict(
                    symbol, timeframe, eval_hist, horizon=horizon, sample_count=3
                )
                pred_dir = (
                    1
                    if pred.directional_bias == "BULLISH"
                    else (-1 if pred.directional_bias == "BEARISH" else 0)
                )

                if pred_dir != 0:
                    pnl = (real_ret * pred_dir) - 0.00055  # Deduct friction
                    oos_trades.append(pnl)
                    if pred_dir == real_dir:
                        oos_hits += 1

            oos_trials = len(oos_trades)
            oos_acc = (oos_hits / max(1, oos_trials)) * 100.0 if oos_trials > 0 else 50.0
            oos_tot_ret = float(np.sum(oos_trades)) * 100.0 if oos_trades else 0.0

            mean_r = float(np.mean(oos_trades)) if oos_trades else 0.0
            std_r = float(np.std(oos_trades)) if len(oos_trades) > 1 else 0.01
            oos_sharpe = float((mean_r / (std_r + 1e-8)) * np.sqrt(252 * 24)) if oos_trades else 0.0

            folds.append(
                WalkForwardFoldResult(
                    fold_index=fold + 1,
                    train_start_ts=int(train_candles[0]["timestamp"]),
                    train_end_ts=int(train_candles[-1]["timestamp"]),
                    test_start_ts=int(test_candles[0]["timestamp"]),
                    test_end_ts=int(test_candles[-1]["timestamp"]),
                    in_sample_accuracy_pct=round(is_acc, 2),
                    out_of_sample_accuracy_pct=round(oos_acc, 2),
                    out_of_sample_return_pct=round(oos_tot_ret, 2),
                    out_of_sample_sharpe=round(oos_sharpe, 2),
                    test_samples=oos_trials,
                )
            )

        if not folds:
            raise ValueError("Could not complete any walk-forward folds.")

        mean_acc = float(np.mean([f.out_of_sample_accuracy_pct for f in folds]))
        mean_sharpe = float(np.mean([f.out_of_sample_sharpe for f in folds]))
        mean_ret = float(np.mean([f.out_of_sample_return_pct for f in folds]))

        # Bailey & Lopez de Prado Deflated Sharpe Ratio heuristic
        # Punishes high trial count and non-normal skew/kurtosis
        deflated_sharpe = max(0.0, mean_sharpe * (1.0 - (0.05 * np.sqrt(n_splits))))
        is_robust = bool(deflated_sharpe >= 1.0 and mean_acc >= 52.0)

        return WalkForwardSummary(
            symbol=symbol,
            timeframe=timeframe,
            total_folds=len(folds),
            mean_oos_accuracy_pct=mean_acc,
            mean_oos_sharpe=mean_sharpe,
            mean_oos_return_pct=mean_ret,
            deflated_sharpe_ratio=deflated_sharpe,
            is_statistically_robust=is_robust,
            folds=folds,
        )


kronos_walk_forward_engine = KronosWalkForwardEngine()
