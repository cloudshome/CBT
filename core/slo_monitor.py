"""
core/slo_monitor.py
===================
Institutional SLO (Service Level Objective) & Tail Latency Monitoring Engine.
Computes real-time rolling percentiles (p50, p90, p95, p99, max) across:
1. Order Routing Latency Pipeline
2. Market Data Ingestion & Clock Drift
3. Fill Reconciliation Delays & Mismatches
4. API Infrastructure Request Throughput & Error Budgets
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sky.slo_monitor")


class SLOStatus(StrEnum):
    """Operational status of a service level objective."""

    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    BREACH = "BREACH"


@dataclass(frozen=True)
class LatencyPercentiles:
    """Statistical percentile summary of latency observations."""

    p50: float
    p90: float
    p95: float
    p99: float
    min: float
    max: float
    mean: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SLOTarget:
    """Defined performance boundary for an SLO vector."""

    metric_name: str
    target_p95_ms: float | None = None
    target_p99_ms: float | None = None
    target_max_ms: float | None = None
    warning_factor: float = 0.80  # 80% of target trips WARNING


@dataclass(frozen=True)
class MetricCompliance:
    """Evaluation result for an individual metric against its target."""

    metric_name: str
    status: SLOStatus
    observed_p95_ms: float
    observed_p99_ms: float
    observed_max_ms: float
    target_p95_ms: float | None
    target_p99_ms: float | None
    message: str


class RollingPercentileTracker:
    """
    Thread-safe circular buffer computing rolling quantiles without data truncation.
    """

    def __init__(self, max_samples: int = 1000):
        self._max_samples = max_samples
        self._buffer: deque[float] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def record(self, value: float) -> None:
        """Records a single duration measurement in milliseconds."""
        if not math.isfinite(value) or value < 0.0:
            return
        with self._lock:
            self._buffer.append(float(value))

    def compute_percentiles(self) -> LatencyPercentiles:
        """Computes exact empirical quantiles from the active sample window."""
        with self._lock:
            if not self._buffer:
                return LatencyPercentiles(
                    p50=0.0, p90=0.0, p95=0.0, p99=0.0, min=0.0, max=0.0, mean=0.0, sample_count=0
                )
            sorted_data = sorted(self._buffer)

        n = len(sorted_data)

        def _quantile(q: float) -> float:
            idx = int(q * (n - 1))
            return round(sorted_data[idx], 3)

        return LatencyPercentiles(
            p50=_quantile(0.50),
            p90=_quantile(0.90),
            p95=_quantile(0.95),
            p99=_quantile(0.99),
            min=round(sorted_data[0], 3),
            max=round(sorted_data[-1], 3),
            mean=round(sum(sorted_data) / n, 3),
            sample_count=n,
        )

    def clear(self) -> None:
        """Clears the sample window."""
        with self._lock:
            self._buffer.clear()


class SLOMonitor:
    """
    Central monitor coordinating operational SLO accounting across all CBT subsystems.
    """

    def __init__(self, max_window_samples: int = 1000):
        self.max_window_samples = max_window_samples
        self._lock = threading.Lock()

        # Trackers partitioned by dimension and metric name
        self._trackers: dict[str, dict[str, RollingPercentileTracker]] = {
            "order_routing": {
                "preflight_ms": RollingPercentileTracker(max_window_samples),
                "risk_check_ms": RollingPercentileTracker(max_window_samples),
                "sor_decision_ms": RollingPercentileTracker(max_window_samples),
                "reconciliation_ms": RollingPercentileTracker(max_window_samples),
            },
            "market_data": {
                "tick_processing_ms": RollingPercentileTracker(max_window_samples),
                "clock_drift_ms": RollingPercentileTracker(max_window_samples),
            },
            "reconciliation": {
                "reconciliation_delay_ms": RollingPercentileTracker(max_window_samples),
            },
            "api_infrastructure": {
                "request_duration_ms": RollingPercentileTracker(max_window_samples),
            },
        }

        # Counters for rate/anomaly tracking
        self._counters: dict[str, int] = {
            "stale_ticks_total": 0,
            "unmatched_executions_total": 0,
            "duplicate_executions_total": 0,
            "api_requests_total": 0,
            "api_errors_total": 0,
            "api_timeouts_total": 0,
        }

        # Institutional SLO Targets
        self._targets: dict[str, SLOTarget] = {
            "order_routing:sor_decision_ms": SLOTarget(
                "sor_decision_ms", target_p95_ms=50.0, target_p99_ms=100.0, target_max_ms=250.0
            ),
            "order_routing:risk_check_ms": SLOTarget(
                "risk_check_ms", target_p95_ms=15.0, target_p99_ms=30.0, target_max_ms=75.0
            ),
            "market_data:clock_drift_ms": SLOTarget(
                "clock_drift_ms", target_p95_ms=200.0, target_p99_ms=500.0, target_max_ms=1000.0
            ),
            "reconciliation:reconciliation_delay_ms": SLOTarget(
                "reconciliation_delay_ms",
                target_p95_ms=250.0,
                target_p99_ms=500.0,
                target_max_ms=1500.0,
            ),
            "api_infrastructure:request_duration_ms": SLOTarget(
                "request_duration_ms",
                target_p95_ms=100.0,
                target_p99_ms=250.0,
                target_max_ms=1000.0,
            ),
        }

    def record_latency(self, dimension: str, metric_name: str, duration_ms: float) -> None:
        """Records a latency observation in the specified dimension."""
        with self._lock:
            if dimension not in self._trackers:
                self._trackers[dimension] = {}
            if metric_name not in self._trackers[dimension]:
                self._trackers[dimension][metric_name] = RollingPercentileTracker(
                    self.max_window_samples
                )
            tracker = self._trackers[dimension][metric_name]

        tracker.record(duration_ms)

    def increment_counter(self, counter_name: str, inc: int = 1) -> None:
        """Atomically increments an operational error or event counter."""
        with self._lock:
            if counter_name not in self._counters:
                self._counters[counter_name] = 0
            self._counters[counter_name] += inc

    def get_percentiles(self, dimension: str, metric_name: str) -> LatencyPercentiles:
        """Retrieves current percentiles for a specific metric."""
        with self._lock:
            tracker = self._trackers.get(dimension, {}).get(metric_name)
        if not tracker:
            return LatencyPercentiles(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
        return tracker.compute_percentiles()

    def get_snapshot(self) -> dict[str, Any]:
        """Returns a complete operational telemetry snapshot."""
        snapshot: dict[str, Any] = {
            "timestamp": int(time.time() * 1000),
            "dimensions": {},
            "counters": dict(self._counters),
        }

        with self._lock:
            dimensions = list(self._trackers.keys())

        for dim in dimensions:
            snapshot["dimensions"][dim] = {}
            with self._lock:
                metrics = list(self._trackers[dim].keys())
            for m in metrics:
                pct = self.get_percentiles(dim, m)
                snapshot["dimensions"][dim][m] = pct.to_dict()

        # Compute rolling API error rate
        total_reqs = self._counters.get("api_requests_total", 0)
        total_errs = self._counters.get("api_errors_total", 0)
        err_rate = round((total_errs / total_reqs * 100.0), 2) if total_reqs > 0 else 0.0
        snapshot["api_error_rate_pct"] = err_rate

        return snapshot

    def evaluate_compliance(self) -> list[MetricCompliance]:
        """Evaluates all registered targets against observed percentiles."""
        results: list[MetricCompliance] = []

        for key, target in self._targets.items():
            dim, metric_name = key.split(":")
            pct = self.get_percentiles(dim, metric_name)

            # Insufficient samples -> NOMINAL
            if pct.sample_count < 5:
                results.append(
                    MetricCompliance(
                        metric_name=key,
                        status=SLOStatus.NOMINAL,
                        observed_p95_ms=pct.p95,
                        observed_p99_ms=pct.p99,
                        observed_max_ms=pct.max,
                        target_p95_ms=target.target_p95_ms,
                        target_p99_ms=target.target_p99_ms,
                        message=f"Insufficient samples ({pct.sample_count}/5)",
                    )
                )
                continue

            status = SLOStatus.NOMINAL
            reasons = []

            if target.target_p95_ms is not None:
                if pct.p95 > target.target_p95_ms:
                    status = SLOStatus.BREACH
                    reasons.append(f"p95={pct.p95}ms > target {target.target_p95_ms}ms")
                elif pct.p95 > (target.target_p95_ms * target.warning_factor):
                    if status != SLOStatus.BREACH:
                        status = SLOStatus.WARNING
                    reasons.append(
                        f"p95={pct.p95}ms in warning zone (> {target.target_p95_ms * target.warning_factor:.1f}ms)"
                    )

            if target.target_p99_ms is not None:
                if pct.p99 > target.target_p99_ms:
                    status = SLOStatus.BREACH
                    reasons.append(f"p99={pct.p99}ms > target {target.target_p99_ms}ms")

            msg = "; ".join(reasons) if reasons else "Within operational SLO target"
            results.append(
                MetricCompliance(
                    metric_name=key,
                    status=status,
                    observed_p95_ms=pct.p95,
                    observed_p99_ms=pct.p99,
                    observed_max_ms=pct.max,
                    target_p95_ms=target.target_p95_ms,
                    target_p99_ms=target.target_p99_ms,
                    message=msg,
                )
            )

        return results

    def generate_prometheus_lines(self) -> list[str]:
        """Renders rolling percentiles in standard Prometheus metric format."""
        lines = []
        snapshot = self.get_snapshot()

        for dim, metrics in snapshot["dimensions"].items():
            for m_name, stats in metrics.items():
                base_name = f"sky_slo_{dim}_{m_name}"
                lines.append(f"# HELP {base_name} Rolling latency percentiles for {dim}:{m_name}")
                lines.append(f"# TYPE {base_name} summary")
                lines.append(f'{base_name}{{quantile="0.50"}} {stats["p50"]}')
                lines.append(f'{base_name}{{quantile="0.90"}} {stats["p90"]}')
                lines.append(f'{base_name}{{quantile="0.95"}} {stats["p95"]}')
                lines.append(f'{base_name}{{quantile="0.99"}} {stats["p99"]}')
                lines.append(f"{base_name}_count {stats['sample_count']}")

        for c_name, count in snapshot["counters"].items():
            lines.append(f"# TYPE sky_counter_{c_name} counter")
            lines.append(f"sky_counter_{c_name} {count}")

        return lines


# Global singleton instance
slo_monitor = SLOMonitor()
