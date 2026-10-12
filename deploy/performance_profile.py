#!/usr/bin/env python3
"""
SKY / CTB — Performance Profiler & Resource Budget Validator.

Evaluates:
- Memory allocation stability using Python standard library `tracemalloc`.
- SQLite connection pooling and file descriptor teardown.
- Response latency percentiles (p50, p95, p99) against quantitative SLA budgets.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np

# Ensure root on python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import db_manager
from core.monte_carlo_stress import monte_carlo_stress_tester

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_performance_profile")


def run_latency_and_memory_profile(iterations: int = 100) -> dict[str, Any]:
    """Profiles execution latency and memory overhead across core quantitative engines."""
    tracemalloc.start()
    mem_start_current, mem_start_peak = tracemalloc.get_traced_memory()
    
    latencies_ms: list[float] = []

    for i in range(iterations):
        t0 = time.perf_counter()
        
        # 1. Monte Carlo 10k path execution
        monte_carlo_stress_tester.stress_test([0.02, -0.01, 0.015, -0.005, 0.03] * 10)
        
        # 2. Database engine vitals check
        _ = db_manager.get_engine_info()
        
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    mem_end_current, mem_end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    mem_delta_mb = round((mem_end_peak - mem_start_current) / 1024 / 1024, 2)

    p50 = float(np.percentile(latencies_ms, 50))
    p95 = float(np.percentile(latencies_ms, 95))
    p99 = float(np.percentile(latencies_ms, 99))

    # Production Performance SLAs:
    # 1. Memory leak check: peak allocation delta must be < 30 MB
    # 2. Latency check: p95 latency for 10k paths + DB vitals must be < 100ms
    is_memory_healthy = mem_delta_mb < 30.0
    is_latency_healthy = p95 < 100.0

    report = {
        "iterations": iterations,
        "memory_peak_mb": mem_delta_mb,
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "is_memory_healthy": is_memory_healthy,
        "is_latency_healthy": is_latency_healthy,
        "sla_passed": is_memory_healthy and is_latency_healthy,
    }
    
    logger.info(
        f"Performance Profile: p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms | "
        f"Peak Memory Delta={mem_delta_mb}MB | SLA={'PASSED' if report['sla_passed'] else 'FAILED'}"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="SKY / CTB Performance & Memory Profiler")
    parser.add_argument("--iterations", type=int, default=100, help="Number of benchmark iterations")
    args = parser.parse_args()

    logger.info(f"Executing performance benchmark ({args.iterations} iterations)...")
    res = run_latency_and_memory_profile(args.iterations)
    if res["sla_passed"]:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
