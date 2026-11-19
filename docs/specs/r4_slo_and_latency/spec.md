# SPECIFICATION — R4: SLO & Operational Latency Monitoring
**Change Class:** Class C (Small Engineering Feature / Observability & Telemetry)  
**Governance Authority:** Level 0 (`AGENTS.md`) & Level 1 (`constitution.md`)  
**Target Subsystems:** `core/slo_monitor.py`, `core/metrics.py`, `tests/test_slo_monitoring.py`  

---

## 1. OBJECTIVE & STATISTICAL RIGOR

Establish institutional Service Level Objectives (SLOs) and operational latency measurements without relying on misleading arithmetic averages that conceal tail latency.
Every latency vector must track rolling percentiles:
$$\text{Percentiles: } p_{50}, \quad p_{90}, \quad p_{95}, \quad p_{99}, \quad \max$$
along with exact sample counts and rolling error rates.

---

## 2. FUNCTIONAL SCOPE

### 2.1 Monitored Dimensions
1. **Order Routing Latency:**
   - Preflight duration (`preflight_ms`)
   - Risk gate validation duration (`risk_check_ms`)
   - Smart Order Router decision duration (`sor_decision_ms`)
   - Reconciliation latency (`reconciliation_ms`)
2. **Market Data Latency:**
   - Tick ingestion and feature extraction latency (`tick_processing_ms`)
   - Observation clock drift (`clock_drift_ms`)
   - Stale tick detection counter (`stale_ticks_count`)
3. **Reconciliation Latency & Integrity:**
   - Fill reconciliation delay (`reconciliation_delay_ms`)
   - Unmatched execution counter (`unmatched_executions_count`)
   - Duplicate execution detection counter (`duplicate_executions_count`)
4. **API Infrastructure:**
   - HTTP request duration (`request_latency_ms`)
   - Error count and rate (`error_rate_pct`)
   - Service availability estimate (`availability_pct`)

### 2.2 Statistical Percentile Engine (`RollingPercentileTracker`)
- Thread-safe, bounded rolling window (default: 1,000 samples).
- Exact quantile computation via nearest-rank / linear interpolation algorithms (`numpy.percentile` or native sorted arrays).
- Non-blocking: record operations complete in $< 10\,\mu\text{s}$.

### 2.3 Proposed Institutional SLO Thresholds
Targets are evaluated continuously to detect operational degradation:
- **Order Routing Pipeline:** $p_{95} \le 50.0\,\text{ms}$, $\max \le 250.0\,\text{ms}$
- **Market Data Drift:** $p_{95} \le 200.0\,\text{ms}$
- **Reconciliation Processing:** $p_{99} \le 500.0\,\text{ms}$
- **API Request Latency:** $p_{95} \le 100.0\,\text{ms}$
- **API Error Budget:** Error Rate $\le 1.0\%$

---

## 3. INVARIANTS & SAFETY CONSTRAINTS
1. **Zero M18 Invalidation:** All monitoring logic is implemented in `core/slo_monitor.py` without touching the 14 M18 certified files.
2. **Execution Decoupling:** SLO evaluation is strictly passive and diagnostic; monitoring failures must never abort, stall, or alter active risk calculations.
3. **Test Isolation:** Sandboxed unit and stress tests execute in temporary memory via `tests/conftest.py`.
