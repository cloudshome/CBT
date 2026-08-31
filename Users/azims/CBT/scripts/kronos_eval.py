"""
Research Evaluation CLI for Kronos Foundation Model in SKY.
Supports single predictions, multi-sample path simulations, forecast freezing,
history queries, and 3-way ablation benchmarks (SKY Baseline vs Kronos vs Fusion).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.models.kronos import (
    KronosConfig,
    KronosModelAdapter,
    KronosModelVariant,
    kronos_adapter,
)
from core.models.kronos.persistence import (
    freeze_kronos_forecast,
    get_kronos_forecasts,
)
from core.models.kronos.ablation_benchmark import kronos_ablation_benchmark
from core.data_streamer import data_streamer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kronos_eval")


def run_prediction(args: argparse.Namespace) -> None:
    logger.info(f"Generating Kronos forecast for {args.symbol} on {args.timeframe}...")

    # Fetch canonical candles from data_streamer
    candles = data_streamer.generate_synthetic_candles(args.symbol, args.timeframe, count=args.lookback + 20)

    adapter = KronosModelAdapter(
        KronosConfig(
            model_variant=KronosModelVariant(args.model),
            sample_count=args.samples,
            default_horizon=args.horizon,
        )
    )
    adapter.load_model()

    forecast = adapter.predict(
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=candles,
        horizon=args.horizon,
        lookback=args.lookback,
        sample_count=args.samples,
        seed=args.seed,
    )

    print("\n=======================================================")
    print(f"  KRONOS PROBABILISTIC FORECAST: {forecast.symbol} ({forecast.timeframe})")
    print("=======================================================")
    print(f"Model Variant:         {forecast.model_name} ({forecast.model_version})")
    print(f"Current Price:         ${forecast.current_price:,.2f}")
    print(f"Predicted Mean Close:  ${forecast.predicted_close_mean:,.2f}")
    print(f"Expected Return:       {forecast.expected_return_pct * 100:+.2f}%")
    print(f"Median Return:         {forecast.median_return_pct * 100:+.2f}%")
    print(f"Forecast Volatility:   {forecast.forecast_volatility_pct * 100:.2f}%")
    print(f"Path Dispersion:       {forecast.path_dispersion_pct * 100:.2f}%")
    print(f"Directional Consensus: {forecast.directional_consensus * 100:.1f}%")
    print(f"Model Uncertainty:     {forecast.model_uncertainty:.2f}")
    print(f"Directional Bias:      {forecast.directional_bias}")
    print(f"Inference Latency:     {forecast.inference_latency_ms:.1f} ms")
    print(f"Status:                {forecast.status.value}")
    print("=======================================================\n")

    if args.freeze:
        fid = freeze_kronos_forecast(forecast)
        print(f"Frozen to SQLite experiment_store.db with Forecast ID: {fid}\n")


def run_history(args: argparse.Namespace) -> None:
    records = get_kronos_forecasts(symbol=args.symbol, timeframe=args.timeframe, limit=args.limit)
    print(f"\nRetrieved {len(records)} frozen Kronos forecast(s):\n")
    for r in records:
        print(
            f"[{r['forecast_id']}] {r['symbol']} ({r['timeframe']}) | "
            f"Price: ${r['current_price']:,.2f} | Exp Ret: {r['expected_return_pct'] * 100:+.2f}% | "
            f"Bias: {r['directional_bias']} | Verified: {bool(r['is_verified'])} ({r.get('realized_outcome_5m', 'PENDING')})"
        )
    print()


def run_benchmark(args: argparse.Namespace) -> None:
    logger.info(f"Running 3-way ablation benchmark on {args.symbol} ({args.timeframe}, {args.bars} bars)...")
    candles = data_streamer.generate_synthetic_candles(args.symbol, args.timeframe, count=args.bars)

    result = kronos_ablation_benchmark.run_benchmark(
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=candles,
        lookback_window=args.lookback,
        forecast_horizon=args.horizon,
    )

    print("\n=========================================================================")
    print(f"  SKY × KRONOS 3-WAY ABLATION BENCHMARK: {result.symbol} ({result.timeframe})")
    print("=========================================================================")
    print(f"Evaluation Points: {result.evaluation_bars}")
    print("-------------------------------------------------------------------------")
    print(f"{'Metric':<25} | {'Mode A (SKY)':<14} | {'Mode B (Kronos)':<15} | {'Mode C (Fusion)':<15}")
    print("-------------------------------------------------------------------------")
    print(f"{'Total Trades':<25} | {result.mode_a_sky.total_trades:<14} | {result.mode_b_kronos.total_trades:<15} | {result.mode_c_fusion.total_trades:<15}")
    print(f"{'Win Rate %':<25} | {result.mode_a_sky.win_rate_pct:<13}% | {result.mode_b_kronos.win_rate_pct:<14}% | {result.mode_c_fusion.win_rate_pct:<14}%")
    print(f"{'Profit Factor':<25} | {result.mode_a_sky.profit_factor:<14} | {result.mode_b_kronos.profit_factor:<15} | {result.mode_c_fusion.profit_factor:<15}")
    print(f"{'Expectancy (R)':<25} | {result.mode_a_sky.expectancy_r:<14} | {result.mode_b_kronos.expectancy_r:<15} | {result.mode_c_fusion.expectancy_r:<15}")
    print(f"{'Max Drawdown %':<25} | {result.mode_a_sky.max_drawdown_pct:<13}% | {result.mode_b_kronos.max_drawdown_pct:<14}% | {result.mode_c_fusion.max_drawdown_pct:<14}%")
    print(f"{'Sharpe Ratio':<25} | {result.mode_a_sky.sharpe_ratio:<14} | {result.mode_b_kronos.sharpe_ratio:<15} | {result.mode_c_fusion.sharpe_ratio:<15}")
    print(f"{'Dir. Accuracy %':<25} | {result.mode_a_sky.directional_accuracy_pct:<13}% | {result.mode_b_kronos.directional_accuracy_pct:<14}% | {result.mode_c_fusion.directional_accuracy_pct:<14}%")
    print("=========================================================================")
    print(f"DELTA EXPECTANCY (C vs A): {result.delta_expectancy_r:+.3f}R")
    print(f"DELTA WIN RATE (C vs A):   {result.delta_win_rate_pct:+.2f}%")
    print(f"DELTA PROFIT FACTOR:       {result.delta_profit_factor:+.2f}")
    print(f"DELTA MAX DRAWDOWN:        {result.delta_drawdown_pct:+.2f}%")
    print(f"OFFICIAL VERDICT:          {result.verdict}")
    print("=========================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="SKY × Kronos Research & Forecasting CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Predict subcommand
    pred_parser = subparsers.add_parser("predict", help="Execute Kronos forecast prediction")
    pred_parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair symbol")
    pred_parser.add_argument("--timeframe", "--tf", type=str, default="15m", help="Timeframe (e.g. 5m, 15m, 1h)")
    pred_parser.add_argument("--lookback", type=int, default=128, help="Number of historical lookback candles")
    pred_parser.add_argument("--horizon", type=int, default=12, help="Forecast horizon in candles")
    pred_parser.add_argument("--samples", type=int, default=5, help="Number of Monte Carlo paths")
    pred_parser.add_argument("--model", type=str, default="kronos-small", choices=["kronos-mini", "kronos-small", "kronos-base"])
    pred_parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    pred_parser.add_argument("--freeze", action="store_true", help="Persist forecast in SQLite freeze ledger")

    # History subcommand
    hist_parser = subparsers.add_parser("history", help="Query frozen forecast history")
    hist_parser.add_argument("--symbol", type=str, default=None, help="Filter by symbol")
    hist_parser.add_argument("--timeframe", "--tf", type=str, default=None, help="Filter by timeframe")
    hist_parser.add_argument("--limit", type=int, default=20, help="Max records to return")

    # Benchmark subcommand
    bench_parser = subparsers.add_parser("benchmark", help="Execute 3-way ablation benchmark")
    bench_parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading pair symbol")
    bench_parser.add_argument("--timeframe", "--tf", type=str, default="15m", help="Timeframe")
    bench_parser.add_argument("--bars", type=int, default=250, help="Total evaluation candles")
    bench_parser.add_argument("--lookback", type=int, default=64, help="Historical lookback window")
    bench_parser.add_argument("--horizon", type=int, default=12, help="Prediction horizon bars")

    args = parser.parse_args()
    if args.command == "predict":
        run_prediction(args)
    elif args.command == "history":
        run_history(args)
    elif args.command == "benchmark":
        run_benchmark(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
