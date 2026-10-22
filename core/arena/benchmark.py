"""
core/arena/benchmark.py
=======================
Asset-specific Buy-and-Hold benchmark tracking for the Darwinian Arena (Milestone 21).

Mathematical Definition:
    Benchmark Return (%) = ((Current Price - Initial Price) / Initial Price) * 100
    Specialist Return (%) = ((Current Equity - Initial Equity) / Initial Equity) * 100
    Alpha vs Benchmark (%) = Specialist Return (%) - Benchmark Return (%)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("sky.arena.benchmark")


@dataclass(frozen=True)
class BenchmarkMetrics:
    initial_price: float
    current_price: float
    benchmark_return_pct: float
    specialist_return_pct: float
    alpha_pct: float
    is_outperforming: bool


class AssetBenchmarkEngine:
    """Calculates asset-specific relative alpha against a Buy-and-Hold benchmark."""

    @staticmethod
    def calculate(
        initial_price: float | None,
        current_price: float,
        initial_equity: float,
        current_equity: float,
    ) -> BenchmarkMetrics:
        """
        Computes benchmark and specialist performance.
        If initial_price is missing or zero, initial_price defaults to current_price (0% return).
        """
        p0 = initial_price if (initial_price is not None and initial_price > 0) else current_price
        p1 = current_price

        bench_ret = ((p1 - p0) / p0) * 100.0 if p0 > 0 else 0.0
        spec_ret = ((current_equity - initial_equity) / initial_equity) * 100.0 if initial_equity > 0 else 0.0
        alpha = spec_ret - bench_ret

        return BenchmarkMetrics(
            initial_price=round(p0, 4),
            current_price=round(p1, 4),
            benchmark_return_pct=round(bench_ret, 2),
            specialist_return_pct=round(spec_ret, 2),
            alpha_pct=round(alpha, 2),
            is_outperforming=alpha > 0.0,
        )

