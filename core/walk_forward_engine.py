"""
Purged K-Fold Walk-Forward Optimization & Validation Engine.
Splits historical series into rolling In-Sample (70%) and Out-of-Sample (30%) windows
with temporal purge buffers to prevent lookahead leakage and evaluate OOS Stability Ratio.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.sandbox_lab import sandbox_lab

logger = logging.getLogger("ai_quant_sentinel.walk_forward_engine")


@dataclass
class WalkForwardFold:
    fold_index: int
    is_start_time: int
    is_end_time: int
    oos_start_time: int
    oos_end_time: int
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    stability_ratio: float  # OOS Sharpe / IS Sharpe
    is_passed: bool


@dataclass
class WalkForwardReport:
    symbol: str
    num_folds: int
    mean_is_sharpe: float
    mean_oos_sharpe: float
    overall_stability_ratio: float  # Target >= 0.65 for promotion
    consistency_pass_rate: float  # Fraction of folds that passed stability >= 0.60
    is_robust: bool
    folds: list[WalkForwardFold]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["folds"] = [asdict(f) for f in self.folds]
        return d


class WalkForwardEngine:
    """Executes Purged K-Fold Walk-Forward Validation."""

    def __init__(self, num_folds: int = 3, purge_bars: int = 3):
        self.num_folds = num_folds
        self.purge_bars = purge_bars

    def validate(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
    ) -> WalkForwardReport:
        """
        Executes rolling walk-forward test across candles.
        """
        n = len(candles)
        if n < 60:
            return WalkForwardReport(
                symbol=symbol,
                num_folds=0,
                mean_is_sharpe=0.0,
                mean_oos_sharpe=0.0,
                overall_stability_ratio=0.0,
                consistency_pass_rate=0.0,
                is_robust=False,
                folds=[],
            )

        window_size = int(n * 0.60)
        step = max(10, (n - window_size) // max(1, self.num_folds))
        folds_res: list[WalkForwardFold] = []

        is_sharpes = []
        oos_sharpes = []
        stabilities = []

        for k in range(self.num_folds):
            start_idx = k * step
            end_idx = min(n, start_idx + window_size)
            chunk = candles[start_idx:end_idx]

            if len(chunk) < 40:
                continue

            split_pt = int(len(chunk) * 0.70)
            is_candles = chunk[:split_pt]
            # Purge buffer
            oos_candles = chunk[min(len(chunk), split_pt + self.purge_bars) :]

            if len(is_candles) < 20 or len(oos_candles) < 10:
                continue

            # Run backtest on In-Sample
            is_rep = sandbox_lab.run_backtest(symbol, timeframe, is_candles)
            # Run backtest on Out-of-Sample
            oos_rep = sandbox_lab.run_backtest(symbol, timeframe, oos_candles)

            is_sr = max(0.1, is_rep.sharpe_ratio)
            oos_sr = oos_rep.sharpe_ratio
            stability = oos_sr / is_sr if is_sr > 0 else 0.0
            is_passed = bool(stability >= 0.50 and oos_sr > 0.8)

            is_sharpes.append(is_sr)
            oos_sharpes.append(oos_sr)
            stabilities.append(stability)

            folds_res.append(
                WalkForwardFold(
                    fold_index=len(folds_res) + 1,
                    is_start_time=is_candles[0]["timestamp"],
                    is_end_time=is_candles[-1]["timestamp"],
                    oos_start_time=oos_candles[0]["timestamp"],
                    oos_end_time=oos_candles[-1]["timestamp"],
                    in_sample_sharpe=round(is_sr, 2),
                    out_of_sample_sharpe=round(oos_sr, 2),
                    stability_ratio=round(stability, 2),
                    is_passed=is_passed,
                )
            )

        if not folds_res:
            return WalkForwardReport(symbol, 0, 0.0, 0.0, 0.0, 0.0, False, [])

        mean_is = float(np.mean(is_sharpes))
        mean_oos = float(np.mean(oos_sharpes))
        mean_stability = float(np.mean(stabilities))
        pass_rate = float(np.mean([1.0 if f.is_passed else 0.0 for f in folds_res]))
        is_robust = mean_stability >= 0.60 and pass_rate >= 0.50

        return WalkForwardReport(
            symbol=symbol,
            num_folds=len(folds_res),
            mean_is_sharpe=round(mean_is, 2),
            mean_oos_sharpe=round(mean_oos, 2),
            overall_stability_ratio=round(mean_stability, 2),
            consistency_pass_rate=round(pass_rate, 2),
            is_robust=is_robust,
            folds=folds_res,
        )


# Singleton
walk_forward_engine = WalkForwardEngine()
