# IMPLEMENTATION PLAN — R4: SLO & Latency Monitoring
**Change Class:** Class C  

---

## 1. ARCHITECTURAL APPROACH

1. **`core/slo_monitor.py`:**
   - Define data models: `LatencyPercentiles`, `SLOMetricTarget`, `SLOComplianceStatus`, `SLOReport`
   - Implement `RollingPercentileTracker`:
     - Bounded ring buffer with thread safety
     - Compute `p50`, `p90`, `p95`, `p99`, `min`, `max`, `mean`, `sample_count`
   - Implement `SLOMonitor`:
     - Track observations across the 4 core dimensions
     - Provide `record_latency(dimension, metric_name, duration_ms)`
     - Provide `record_counter(dimension, counter_name, increment)`
     - Provide `get_snapshot()`
     - Provide `evaluate_compliance() -> SLOReport`
     - Provide `export_prometheus_metrics() -> str`
2. **`core/metrics.py` Integration:**
   - Append SLO percentiles into `generate_prometheus_metrics()` output.
3. **`tests/test_slo_monitoring.py`:**
   - Test rolling percentile accuracy (p50/p90/p95/p99) against synthetic distributions.
   - Test compliance evaluation (detect nominal state, warning, breach).
   - Test thread safety and non-blocking operation under high observation rates (10,000 samples).
   - Test Prometheus metric formatting.
