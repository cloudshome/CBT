"""
scripts/benchmarks/benchmark_order_router.py
============================================
Milestone 19: High-Resolution JIT Hotpath Micro-Benchmarking Suite.

Measures Smart Order Router (SOR) depth walking and Almgren-Chriss optimal
trajectory schedule generation over 5,000 iterations.
Verifies sub-millisecond decision latency (< 250 microseconds target).
"""

from __future__ import annotations

from pathlib import Path
import sys
import time

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np  # noqa: E402

from core.execution.almgren_chriss import AlmgrenChrissSlicer  # noqa: E402
from core.execution.smart_order_router import (  # noqa: E402
    L2DepthLevel,
    SmartOrderRouter,
    VenueOrderBook,
)


def generate_synthetic_book(exchange: str, base_price: float) -> VenueOrderBook:
    """Generates a realistic 10-level order book for benchmarking."""
    now_ms = int(time.time() * 1000)
    bids = [
        L2DepthLevel(price=round(base_price - (i * 0.5), 2), size=1.0 + (i * 0.5))
        for i in range(10)
    ]
    asks = [
        L2DepthLevel(price=round(base_price + (i * 0.5) + 0.5, 2), size=1.0 + (i * 0.5))
        for i in range(10)
    ]
    return VenueOrderBook(
        exchange=exchange,
        symbol="BTC/USDT",
        bids=bids,
        asks=asks,
        timestamp_ms=now_ms,
    )


def benchmark_sor(iterations: int = 5000) -> dict[str, float]:
    """Micro-benchmarks SmartOrderRouter optimal multi-venue quote splitting."""
    sor = SmartOrderRouter()
    binance_book = generate_synthetic_book("BINANCE", 60000.0)
    bybit_book = generate_synthetic_book("BYBIT", 60000.2)

    durations_ns: list[int] = []

    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        _ = sor.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=5.0,
            venue_books={"BINANCE": binance_book, "BYBIT": bybit_book},
        )
        t1 = time.perf_counter_ns()
        durations_ns.append(t1 - t0)

    arr_us = np.array(durations_ns) / 1000.0  # Convert to microseconds
    return {
        "p50_us": float(np.percentile(arr_us, 50)),
        "p90_us": float(np.percentile(arr_us, 90)),
        "p99_us": float(np.percentile(arr_us, 99)),
        "p999_us": float(np.percentile(arr_us, 99.9)),
        "mean_us": float(np.mean(arr_us)),
        "max_us": float(np.max(arr_us)),
    }


def benchmark_slicer(iterations: int = 5000) -> dict[str, float]:
    """Micro-benchmarks Almgren-Chriss discrete trajectory optimization."""
    slicer = AlmgrenChrissSlicer()

    durations_ns: list[int] = []

    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        _ = slicer.generate_execution_schedule(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=10.0,
            current_price=60000.0,
            time_horizon_sec=600.0,
            num_intervals=10,
            annualized_volatility=0.65,
            risk_aversion_lambda=1e-5,
        )
        t1 = time.perf_counter_ns()
        durations_ns.append(t1 - t0)

    arr_us = np.array(durations_ns) / 1000.0  # Convert to microseconds
    return {
        "p50_us": float(np.percentile(arr_us, 50)),
        "p90_us": float(np.percentile(arr_us, 90)),
        "p99_us": float(np.percentile(arr_us, 99)),
        "p999_us": float(np.percentile(arr_us, 99.9)),
        "mean_us": float(np.mean(arr_us)),
        "max_us": float(np.max(arr_us)),
    }


def main() -> None:
    print("[INFO] Starting Milestone 19 JIT Hotpath Microbenchmarking...")
    sor_metrics = benchmark_sor(5000)
    print(
        f"  [SOR] p50: {sor_metrics['p50_us']:.1f}us | p90: {sor_metrics['p90_us']:.1f}us | "
        f"p99: {sor_metrics['p99_us']:.1f}us | Mean: {sor_metrics['mean_us']:.1f}us"
    )

    slicer_metrics = benchmark_slicer(5000)
    print(
        f"  [SLICER] p50: {slicer_metrics['p50_us']:.1f}us | p90: {slicer_metrics['p90_us']:.1f}us | "
        f"p99: {slicer_metrics['p99_us']:.1f}us | Mean: {slicer_metrics['mean_us']:.1f}us"
    )

    # Output benchmark report
    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "M19_JIT_HOTPATH_BENCHMARK.md"

    # Use plain text "us" instead of LaTeX to avoid f-string escape issues
    md = f"""# Milestone 19: JIT Execution Hotpath Latency Benchmark

**Target Metric:** Sub-millisecond routing cycle (< 250 us)  
**Iterations:** 5,000 per engine  
**Timing Precision:** Nanoseconds (`time.perf_counter_ns()`)  

## 1. Smart Order Router (SOR) Depth Walking Latency

| Metric | Latency (us) | Latency (ms) | Target Status |
|---|---|---|---|
| **Median (p50)** | {sor_metrics['p50_us']:.2f} us | {sor_metrics['p50_us']/1000.0:.4f} ms | {"PASS" if sor_metrics['p50_us'] < 250 else "FAIL"} (< 250 us) |
| **90th Percentile (p90)** | {sor_metrics['p90_us']:.2f} us | {sor_metrics['p90_us']/1000.0:.4f} ms | {"PASS" if sor_metrics['p90_us'] < 500 else "FAIL"} |
| **99th Percentile (p99)** | {sor_metrics['p99_us']:.2f} us | {sor_metrics['p99_us']/1000.0:.4f} ms | {"PASS" if sor_metrics['p99_us'] < 1000 else "FAIL"} (< 1 ms) |
| **99.9th Percentile (p999)** | {sor_metrics['p999_us']:.2f} us | {sor_metrics['p999_us']/1000.0:.4f} ms | - |
| **Mean** | {sor_metrics['mean_us']:.2f} us | {sor_metrics['mean_us']/1000.0:.4f} ms | {"PASS" if sor_metrics['mean_us'] < 250 else "FAIL"} |
| **Max** | {sor_metrics['max_us']:.2f} us | {sor_metrics['max_us']/1000.0:.4f} ms | - |

## 2. Almgren-Chriss Slicer Optimization Latency

| Metric | Latency (us) | Latency (ms) | Target Status |
|---|---|---|---|
| **Median (p50)** | {slicer_metrics['p50_us']:.2f} us | {slicer_metrics['p50_us']/1000.0:.4f} ms | {"PASS" if slicer_metrics['p50_us'] < 250 else "FAIL"} (< 250 us) |
| **90th Percentile (p90)** | {slicer_metrics['p90_us']:.2f} us | {slicer_metrics['p90_us']/1000.0:.4f} ms | {"PASS" if slicer_metrics['p90_us'] < 500 else "FAIL"} |
| **99th Percentile (p99)** | {slicer_metrics['p99_us']:.2f} us | {slicer_metrics['p99_us']/1000.0:.4f} ms | {"PASS" if slicer_metrics['p99_us'] < 1000 else "FAIL"} (< 1 ms) |
| **99.9th Percentile (p999)** | {slicer_metrics['p999_us']:.2f} us | {slicer_metrics['p999_us']/1000.0:.4f} ms | - |
| **Mean** | {slicer_metrics['mean_us']:.2f} us | {slicer_metrics['mean_us']/1000.0:.4f} ms | {"PASS" if slicer_metrics['mean_us'] < 250 else "FAIL"} |
| **Max** | {slicer_metrics['max_us']:.2f} us | {slicer_metrics['max_us']/1000.0:.4f} ms | - |
"""
    report_file.write_text(md, encoding="utf-8")
    print(f"[SAVED] {report_file}")


if __name__ == "__main__":
    main()
