"""
tests/test_slo_monitoring.py
============================
Automated Institutional Verification Suite for SLO Monitoring Engine.
Verifies:
1. Exact quantile calculation across empirical distributions
2. Operational SLO target evaluation (NOMINAL, WARNING, BREACH)
3. 4-Dimension telemetry snapshot generation
4. Thread-safe concurrent recording under burst pressure
5. Prometheus metric serialization
"""

from __future__ import annotations

import concurrent.futures

from core.metrics import generate_prometheus_metrics
from core.slo_monitor import (
    RollingPercentileTracker,
    SLOMonitor,
    SLOStatus,
    slo_monitor,
)


class TestRollingPercentileTracker:
    """Verifies empirical quantile accuracy and bounded memory safety."""

    def test_empty_tracker_returns_zeroes_safely(self):
        tracker = RollingPercentileTracker(max_samples=100)
        pct = tracker.compute_percentiles()
        assert pct.sample_count == 0
        assert pct.p50 == 0.0
        assert pct.p95 == 0.0
        assert pct.max == 0.0

    def test_exact_quantile_accuracy_on_known_distribution(self):
        tracker = RollingPercentileTracker(max_samples=1000)
        # Feed 100 evenly spaced measurements from 1.0 to 100.0 ms
        for i in range(1, 101):
            tracker.record(float(i))

        pct = tracker.compute_percentiles()
        assert pct.sample_count == 100
        assert pct.min == 1.0
        assert pct.max == 100.0
        assert 49.0 <= pct.p50 <= 51.0
        assert 89.0 <= pct.p90 <= 91.0
        assert 94.0 <= pct.p95 <= 96.0
        assert 98.0 <= pct.p99 <= 100.0
        assert abs(pct.mean - 50.5) < 0.1

    def test_negative_and_nan_values_ignored_defensively(self):
        tracker = RollingPercentileTracker(max_samples=50)
        tracker.record(-10.0)
        tracker.record(float("nan"))
        tracker.record(float("inf"))
        pct = tracker.compute_percentiles()
        assert pct.sample_count == 0

    def test_rolling_window_eviction(self):
        tracker = RollingPercentileTracker(max_samples=10)
        for i in range(20):
            tracker.record(float(i))
        pct = tracker.compute_percentiles()
        assert pct.sample_count == 10
        # Earliest 0..9 should be evicted; min should be 10.0
        assert pct.min == 10.0
        assert pct.max == 19.0


class TestSLOMonitorComplianceAndReporting:
    """Verifies operational compliance evaluation and multi-dimensional reporting."""

    def test_nominal_compliance_when_within_targets(self):
        monitor = SLOMonitor(max_window_samples=100)
        # Record nominal measurements well below 50ms target
        for _ in range(10):
            monitor.record_latency("order_routing", "sor_decision_ms", 12.5)

        compliance = monitor.evaluate_compliance()
        sor_comp = next((c for c in compliance if "sor_decision_ms" in c.metric_name), None)
        assert sor_comp is not None
        assert sor_comp.status == SLOStatus.NOMINAL

    def test_warning_compliance_in_warning_band(self):
        monitor = SLOMonitor(max_window_samples=100)
        # Target p95 is 50.0ms; warning factor is 0.80 (40.0ms)
        # Record 45.0ms (between 40 and 50)
        for _ in range(10):
            monitor.record_latency("order_routing", "sor_decision_ms", 45.0)

        compliance = monitor.evaluate_compliance()
        sor_comp = next((c for c in compliance if "sor_decision_ms" in c.metric_name), None)
        assert sor_comp is not None
        assert sor_comp.status == SLOStatus.WARNING
        assert "warning zone" in sor_comp.message

    def test_breach_compliance_when_exceeding_target(self):
        monitor = SLOMonitor(max_window_samples=100)
        # Target p95 is 50.0ms
        for _ in range(10):
            monitor.record_latency("order_routing", "sor_decision_ms", 75.0)

        compliance = monitor.evaluate_compliance()
        sor_comp = next((c for c in compliance if "sor_decision_ms" in c.metric_name), None)
        assert sor_comp is not None
        assert sor_comp.status == SLOStatus.BREACH
        assert "target" in sor_comp.message

    def test_snapshot_structure_and_error_rate(self):
        monitor = SLOMonitor(max_window_samples=100)
        monitor.record_latency("market_data", "clock_drift_ms", 15.0)
        monitor.increment_counter("api_requests_total", 100)
        monitor.increment_counter("api_errors_total", 2)

        snap = monitor.get_snapshot()
        assert "dimensions" in snap
        assert "market_data" in snap["dimensions"]
        assert snap["api_error_rate_pct"] == 2.0


class TestPrometheusIntegrationAndConcurrency:
    """Verifies standard Prometheus export and thread safety under burst."""

    def test_prometheus_metrics_export(self):
        slo_monitor.record_latency("order_routing", "preflight_ms", 4.2)
        lines = slo_monitor.generate_prometheus_lines()
        text = "\n".join(lines)
        assert "sky_slo_order_routing_preflight_ms" in text
        assert 'quantile="0.95"' in text

        # Also test global metrics integration
        full_prom = generate_prometheus_metrics()
        assert "sky_slo_order_routing_preflight_ms" in full_prom
        assert "sky_uptime_seconds" in full_prom

    def test_concurrent_recording_thread_safety(self):
        monitor = SLOMonitor(max_window_samples=2000)

        def worker(val: float):
            for _ in range(100):
                monitor.record_latency("order_routing", "risk_check_ms", val)
                monitor.increment_counter("api_requests_total", 1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, float(i)) for i in range(8)]
            concurrent.futures.wait(futures)

        pct = monitor.get_percentiles("order_routing", "risk_check_ms")
        assert pct.sample_count == 800
        snap = monitor.get_snapshot()
        assert snap["counters"]["api_requests_total"] == 800
