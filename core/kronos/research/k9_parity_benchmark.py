"""
core/kronos/research/k9_parity_benchmark.py
===========================================
Milestone 42: K9 Historical Backtest Parity Benchmark Campaign.

Benchmarks the M41 Prediction Ladder Parity Engine (evaluate_ladder_tick)
against Legacy Naive Fill Mode across all 9 local K9 historical datasets:
  - BTCUSDT: 15m, 1h, 4h
  - ETHUSDT: 15m, 1h, 4h
  - SOLUSDT: 15m, 1h, 4h

Quantifies:
1. Knife-catch losses avoided (where Naive suffered -1.0R loss, but Parity remained NOT_TRIGGERED).
2. Net Expectancy delta (ΔR = Parity Expectancy - Naive Expectancy).
3. Profit Factor improvement and Max Drawdown reduction.
4. Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) under multiple testing.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.research.concept_evaluation import compute_deflated_sharpe
from data.backtester import GradedPlan, run_backtest

logger = logging.getLogger("sky.k9_parity_benchmark")


@dataclass
class ModeMetrics:
    mode: str
    plans_total: int
    trades_executed: int
    wins: int
    losses: int
    not_triggered: int
    win_rate_pct: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_r: float
    dsr: float
    dsr_p_value: float


@dataclass
class DatasetBenchmarkResult:
    dataset_id: str
    symbol: str
    timeframe: str
    bars_count: int
    knife_catches_avoided: int
    expectancy_delta_r: float
    profit_factor_delta: float
    drawdown_reduction_r: float
    naive: ModeMetrics
    parity: ModeMetrics


class K9ParityBenchmarkRunner:
    """Deterministic comparative benchmark runner for K9 datasets."""

    def __init__(self, dataset_dir: str = "data/research/datasets") -> None:
        self.dataset_dir = dataset_dir

    def discover_datasets(self) -> list[dict[str, str]]:
        """Finds and categorizes all 9 K9 JSON datasets."""
        pattern = os.path.join(self.dataset_dir, "K9_*.json")
        files = glob.glob(pattern)
        discovered = []
        for f in files:
            fname = os.path.basename(f)
            parts = fname.replace(".json", "").split("_")
            if len(parts) >= 3:
                discovered.append({
                    "symbol": parts[1],
                    "timeframe": parts[2],
                    "dataset_id": fname.replace(".json", ""),
                    "path": f,
                })
        # Sort predictably by symbol and timeframe
        tf_order = {"15m": 1, "1h": 2, "4h": 3}
        discovered.sort(key=lambda x: (x["symbol"], tf_order.get(x["timeframe"], 99)))
        return discovered

    def _compute_metrics(self, mode_name: str, plans: list[GradedPlan]) -> ModeMetrics:
        """Calculates institutional performance metrics from a list of GradedPlans."""
        total = len(plans)
        not_triggered = sum(1 for p in plans if p.outcome == "NOT_TRIGGERED")
        executed = [p for p in plans if p.outcome in ("WIN", "FULL_WIN", "PARTIAL_WIN", "LOSS")]
        wins = sum(1 for p in executed if p.outcome in ("WIN", "FULL_WIN", "PARTIAL_WIN"))
        losses = sum(1 for p in executed if p.outcome == "LOSS")

        win_rate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0

        returns = [
            float(p.rr_net if p.rr_net is not None else (p.rr_achieved if p.rr_achieved is not None else 0.0))
            for p in executed
        ]
        expectancy = float(np.mean(returns)) if returns else 0.0

        pos_r = sum(r for r in returns if r > 0)
        neg_r = abs(sum(r for r in returns if r < 0))
        pf = (pos_r / neg_r) if neg_r > 0 else (99.0 if pos_r > 0 else 0.0)

        # Max drawdown in R
        max_dd = 0.0
        if returns:
            cum = np.cumsum(returns)
            peak = np.maximum.accumulate(cum)
            dd = peak - cum
            max_dd = float(np.max(dd))

        # Deflated Sharpe Ratio
        dsr, p_val = compute_deflated_sharpe(np.array(returns) if len(returns) >= 10 else np.array([]), num_trials=6)

        return ModeMetrics(
            mode=mode_name,
            plans_total=total,
            trades_executed=len(executed),
            wins=wins,
            losses=losses,
            not_triggered=not_triggered,
            win_rate_pct=round(win_rate, 2),
            expectancy_r=round(expectancy, 3),
            profit_factor=round(pf, 3),
            max_drawdown_r=round(max_dd, 3),
            dsr=dsr,
            dsr_p_value=p_val,
        )

    def run_dataset_benchmark(
        self,
        dataset_info: dict[str, str],
        step_override: int | None = None,
        strict_a_plus_only: bool = False,
    ) -> DatasetBenchmarkResult:
        """Executes comparative benchmark on a single K9 dataset."""
        path = dataset_info["path"]
        sym = dataset_info["symbol"]
        tf = dataset_info["timeframe"]
        dataset_id = dataset_info["dataset_id"]

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        raw_candles = data.get("candles", [])
        df = pd.DataFrame(raw_candles).rename(columns={"timestamp": "ts"})

        # Timeframe horizons and adaptive sampling step
        if tf == "4h":
            horizons = [12.0]
            step = step_override or 2
        elif tf == "1h":
            horizons = [6.0]
            step = step_override or 4
        else:
            horizons = [3.0]
            step = step_override or 16

        # Run 1: Legacy Naive Fill Mode
        naive_out = run_backtest(
            df,
            symbol=sym,
            timeframe=tf,
            horizons=horizons,
            min_bars=30,
            step=step,
            ladder_parity=False,
        )
        naive_graded = naive_out["graded"]

        # Run 2: M41 Ladder Parity Mode (with optional Strict A+ filter)
        parity_out = run_backtest(
            df,
            symbol=sym,
            timeframe=tf,
            horizons=horizons,
            min_bars=30,
            step=step,
            ladder_parity=True,
            strict_a_plus_only=strict_a_plus_only,
        )
        parity_graded = parity_out["graded"]

        # Calculate knife-catch avoidance
        knife_catches_avoided = 0
        min_len = min(len(naive_graded), len(parity_graded))
        for k in range(min_len):
            g_naive = naive_graded[k]
            g_parity = parity_graded[k]
            if g_naive.outcome == "LOSS" and g_parity.outcome == "NOT_TRIGGERED":
                knife_catches_avoided += 1

        mode_lbl = "A_PLUS_LADDER" if strict_a_plus_only else "LADDER_PARITY"
        naive_m = self._compute_metrics("NAIVE", naive_graded)
        parity_m = self._compute_metrics(mode_lbl, parity_graded)

        exp_delta = round(parity_m.expectancy_r - naive_m.expectancy_r, 3)
        pf_delta = round(parity_m.profit_factor - naive_m.profit_factor, 3)
        dd_red = round(naive_m.max_drawdown_r - parity_m.max_drawdown_r, 3)

        return DatasetBenchmarkResult(
            dataset_id=dataset_id,
            symbol=sym,
            timeframe=tf,
            bars_count=len(df),
            knife_catches_avoided=knife_catches_avoided,
            expectancy_delta_r=exp_delta,
            profit_factor_delta=pf_delta,
            drawdown_reduction_r=dd_red,
            naive=naive_m,
            parity=parity_m,
        )

    def run_a_plus_scorecard(self, step_override: int | None = None) -> dict[str, Any]:
        """
        Executes strict Grade A+ Net-of-Cost Benchmark across all 9 K9 datasets.
        Deducts round-trip maker/taker fees and slippage on every trade.
        Verifies positive net expectancy (E[R] > 0.25R) and profit factor >= 1.45.
        """
        datasets = self.discover_datasets()
        results: list[dict[str, Any]] = []

        logger.info(f"Running A+ Net-of-Cost Benchmark across {len(datasets)} K9 datasets...")
        t0 = time.time()

        for d in datasets:
            bench = self.run_dataset_benchmark(d, step_override=step_override, strict_a_plus_only=True)
            res = bench.parity
            results.append({
                "dataset_id": bench.dataset_id,
                "symbol": bench.symbol,
                "timeframe": bench.timeframe,
                "bars_count": bench.bars_count,
                "trades_executed": res.trades_executed,
                "wins": res.wins,
                "losses": res.losses,
                "win_rate_pct": res.win_rate_pct,
                "net_expectancy_r": res.expectancy_r,
                "profit_factor": res.profit_factor,
                "max_drawdown_r": res.max_drawdown_r,
                "knife_catches_avoided": bench.knife_catches_avoided,
                "hurdle_positive_ev": bool(res.expectancy_r >= 0.25 and res.profit_factor >= 1.45),
            })

        elapsed = round(time.time() - t0, 2)
        total_trades = sum(r["trades_executed"] for r in results)
        total_wins = sum(r["wins"] for r in results)
        total_losses = sum(r["losses"] for r in results)
        total_avoided = sum(r["knife_catches_avoided"] for r in results)
        overall_win_rate = (total_wins / max(1, total_wins + total_losses)) * 100.0

        active_res = [r for r in results if r["trades_executed"] > 0]
        avg_exp = float(np.mean([r["net_expectancy_r"] for r in active_res])) if active_res else 0.0
        avg_pf = float(np.mean([r["profit_factor"] for r in active_res])) if active_res else 0.0

        all_hurdles_met = bool(avg_exp >= 0.25 and avg_pf >= 1.45)

        return {
            "timestamp": time.time(),
            "elapsed_seconds": elapsed,
            "datasets_evaluated": len(results),
            "aggregate_scorecard": {
                "total_trades_executed": total_trades,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "overall_win_rate_pct": round(overall_win_rate, 2),
                "avg_net_expectancy_r": round(avg_exp, 3),
                "avg_profit_factor": round(avg_pf, 3),
                "total_knife_catches_avoided": total_avoided,
                "hurdle_target_met": all_hurdles_met,
            },
            "per_dataset": results,
        }

    def run_all(self, step_override: int | None = None) -> dict[str, Any]:
        """Runs the benchmark across all discovered K9 datasets."""
        datasets = self.discover_datasets()
        results: list[DatasetBenchmarkResult] = []

        logger.info(f"Starting K9 Parity Benchmark Campaign across {len(datasets)} datasets...")
        t0 = time.time()

        for d in datasets:
            res = self.run_dataset_benchmark(d, step_override=step_override)
            results.append(res)
            logger.info(
                f"[{res.symbol} {res.timeframe}] Avoided {res.knife_catches_avoided} knife catches | "
                f"Exp Δ: {res.expectancy_delta_r:+.3f}R | PF Δ: {res.profit_factor_delta:+.2f}"
            )

        elapsed = round(time.time() - t0, 2)

        # Aggregate metrics
        total_knife_catches = sum(r.knife_catches_avoided for r in results)
        total_naive_losses = sum(r.naive.losses for r in results)
        total_parity_losses = sum(r.parity.losses for r in results)
        avg_exp_delta = float(np.mean([r.expectancy_delta_r for r in results])) if results else 0.0
        avg_pf_delta = float(np.mean([r.profit_factor_delta for r in results])) if results else 0.0
        avg_dd_red = float(np.mean([r.drawdown_reduction_r for r in results])) if results else 0.0

        return {
            "timestamp": time.time(),
            "elapsed_seconds": elapsed,
            "datasets_evaluated": len(results),
            "aggregate_summary": {
                "total_knife_catches_avoided": total_knife_catches,
                "naive_total_losses": total_naive_losses,
                "parity_total_losses": total_parity_losses,
                "loss_reduction_pct": round(
                    ((total_naive_losses - total_parity_losses) / max(1, total_naive_losses)) * 100.0, 1
                ),
                "avg_expectancy_delta_r": round(avg_exp_delta, 3),
                "avg_profit_factor_delta": round(avg_pf_delta, 3),
                "avg_drawdown_reduction_r": round(avg_dd_red, 3),
            },
            "per_dataset": [asdict(r) for r in results],
        }

    def format_ascii_table(self, report: dict[str, Any]) -> str:
        """Formats an institutional terminal scorecard table from the benchmark report."""
        lines = [
            "==================================================================================================",
            "                   K9 HISTORICAL BACKTEST PARITY BENCHMARK SCORECARD                              ",
            "                  (Legacy Naive Fill vs. M41 Ladder Parity Parity Engine)                         ",
            "==================================================================================================",
            f"{'Dataset / Pair':<18} | {'TF':<4} | {'Bars':<5} | {'Knife Avoided':<14} | {'Exp Δ (R)':<10} | {'PF Δ':<8} | {'DD Red (R)':<10} | {'DSR':<6}",
            "-------------------+------+-------+----------------+------------+----------+------------+-------",
        ]

        for item in report.get("per_dataset", []):
            sym = item["symbol"]
            tf = item["timeframe"]
            bars = item["bars_count"]
            avoided = item["knife_catches_avoided"]
            exp_d = f"{item['expectancy_delta_r']:+.3f}R"
            pf_d = f"{item['profit_factor_delta']:+.2f}"
            dd_r = f"{item['drawdown_reduction_r']:+.2f}R"
            dsr = f"{item['parity']['dsr']:.2f}"
            lines.append(
                f"{sym:<18} | {tf:<4} | {bars:<5} | {avoided:<14} | {exp_d:<10} | {pf_d:<8} | {dd_r:<10} | {dsr:<6}"
            )

        agg = report.get("aggregate_summary", {})
        lines.extend([
            "==================================================================================================",
            f"TOTAL KNIFE-CATCHES AVOIDED : {agg.get('total_knife_catches_avoided', 0)} setups",
            f"OVERALL LOSS REDUCTION      : {agg.get('loss_reduction_pct', 0.0)}% (Naive: {agg.get('naive_total_losses', 0)} losses -> Parity: {agg.get('parity_total_losses', 0)} losses)",
            f"AVERAGE EXPECTANCY DELTA    : {agg.get('avg_expectancy_delta_r', 0.0):+.3f}R per trade",
            f"AVERAGE PROFIT FACTOR DELTA : {agg.get('avg_profit_factor_delta', 0.0):+.2f}",
            f"AVERAGE MAX DRAWDOWN SAVED  : {agg.get('avg_drawdown_reduction_r', 0.0):+.2f}R",
            "==================================================================================================",
        ])
        return "\n".join(lines)


def run_k9_parity_benchmark(
    dataset_dir: str = "data/research/datasets",
    step_override: int | None = None,
) -> dict[str, Any]:
    """Helper entry point for external runners and test suites."""
    runner = K9ParityBenchmarkRunner(dataset_dir=dataset_dir)
    return runner.run_all(step_override=step_override)


def run_k9_a_plus_scorecard(
    dataset_dir: str = "data/research/datasets",
    step_override: int | None = None,
) -> dict[str, Any]:
    """Helper entry point for Grade A+ Net-of-Cost Benchmark across K9 datasets."""
    runner = K9ParityBenchmarkRunner(dataset_dir=dataset_dir)
    return runner.run_a_plus_scorecard(step_override=step_override)


if __name__ == "__main__":
    root_path = str(Path(__file__).resolve().parents[3])
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    runner = K9ParityBenchmarkRunner()
    report = runner.run_all()
    print("\n" + runner.format_ascii_table(report))
    out_path = os.path.join("data", "research", "k9_parity_benchmark_report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {out_path}")
