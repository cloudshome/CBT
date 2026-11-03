# SKY / CBT — Milestone 33.1: Guardian Supervision Audit

**Document ID:** `docs/audit/M33_1_GUARDIAN_SUPERVISION_AUDIT.md`  
**Execution Timestamp:** 2026-11-03T18:25:00Z  
**Auditor:** Independent Principal Security Architect & Distributed Systems Reliability Specialist  
**Module Audited:** `core/risk/guardian_supervisor.py` & `core/risk/portfolio_risk_guardian.py`  
**Audit Verdict:** **PRODUCTION PASS (SUPERVISED FAIL-CLOSED CONFIRMED)**

---

## 1. Executive Summary & Audit Context

Milestone 33 established an in-process monitoring daemon (`start_daemon()` / `stop_daemon()`) within `PortfolioRiskGuardian`. However, a rigorous adversarial review identified critical architectural single points of failure in passive daemon supervision:
1. **Passive Startup Blindspot:** If an application process initialized `PortfolioRiskGuardian` without invoking `start_daemon()`, the guardian operated purely passively on incoming orders without active background mark-to-market valuations.
2. **Silent Worker Termination:** If the monitoring worker thread crashed due to an unhandled OS error or fatal exception, order intake could continue if `require_active_daemon` was not strictly validated by an independent supervisory authority.
3. **Recovery State Contamination:** If a supervisory daemon auto-restarted, there was a risk of improperly resetting active circuit breaker trips (such as `HARD_FREEZE` or `QUARANTINED`).

To resolve these vulnerabilities, Milestone 33.1 engineered the **`GuardianSupervisor`** architecture ([`core/risk/guardian_supervisor.py`](file:///c:/Users/azims/CBT/core/risk/guardian_supervisor.py)), establishing an independent watchdog layer that monitors thread vitality, enforces monotonic heartbeat constraints, and guarantees fail-closed invariants.

---

## 2. Architectural Analysis of Guardian Supervision

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GUARDIAN SUPERVISOR ARCHITECTURE                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │               Independent GuardianSupervisor                 │     │
│   │   - Autonomous Supervisory Thread (0.25s poll interval)      │     │
│   │   - Monotonic Heartbeat Expiry Watchdog                      │     │
│   │   - Auto-Recovery with Max Restart Bounds (<= 3)             │     │
│   └──────────────────────────────┬───────────────────────────────┘     │
│                                  │ Supervises & Enforces               │
│                                  ▼                                     │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │            PortfolioRiskGuardian Monitoring Daemon           │     │
│   │   - Continuous Mark-to-Market Valuation Worker               │     │
│   │   - Emits Monotonic Heartbeat Every Loop Cycle               │     │
│   │   - Trips Circuit Breaker on Intraday Drawdown Breaches      │     │
│   └──────────────────────────────┬───────────────────────────────┘     │
│                                  │ Feeds Status                        │
│                                  ▼                                     │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │             Order Intake Gateway (Pre-Trade Gate)            │     │
│   │   - Asserts supervisor.is_healthy == True                    │     │
│   │   - Rejects orders if daemon stalled or supervisor halted    │     │
│   └──────────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supervision Invariants Verified

| Invariant ID | Supervisory Requirement | Failure Mode Prevented | Verification Method |
|:---:|:---|:---|:---:|
| **SUP-01** | **Startup Fail-Closed** | Uninitialized or crashed thread treated as healthy | `test_m33_1_daemon_never_started_fails_closed` |
| **SUP-02** | **Worker Death Detection** | Silent thread termination leaking order execution | `test_m33_1_supervisor_detects_dead_worker_and_trips_hard_freeze` |
| **SUP-03** | **Monotonic Stall Detection** | Process freeze or infinite loop blocking evaluation | `test_m33_1_heartbeat_stall_trips_supervisor_hard_freeze` |
| **SUP-04** | **Quarantine Inviolability** | Supervisor recovery resetting `HARD_FREEZE` | `test_m33_1_recovery_never_clears_historical_quarantine` |
| **SUP-05** | **Dead Guardian Rejection** | Inactive supervisor passing `is_healthy` check | `test_m33_1_compound_adversarial_injection_fails_closed` |

---

## 4. Key Hardening Implementations

### A. Dynamic Worker Heartbeat Scaling
To guarantee that high-speed testing and low-latency paper execution never suffer false-positive watchdog trips, `GuardianSupervisor` dynamically scales the worker loop interval relative to the configured watchdog SLA:
$$\tau_{\text{worker}} = \max\left(0.01\,\text{s}, \min\left(1.0\,\text{s}, \frac{\tau_{\text{watchdog}}}{2.5}\right)\right)$$
This ensures that the monitoring loop always executes at least $2.5\times$ faster than the watchdog expiration threshold.

### B. Two-Layer Health Barrier
`GuardianSupervisor.is_healthy` enforces a strict conjunction:
```python
@property
def is_healthy(self) -> bool:
    with self._lock:
        if not self._is_running or not self._is_healthy:
            return False
        if not self.guardian.is_daemon_alive():
            return False
        if self.guardian.is_heartbeat_stalled():
            return False
        if self.guardian.state in (CircuitBreakerState.HARD_FREEZE, CircuitBreakerState.INVESTIGATION):
            return False
        return True
```
If the guardian enters `HARD_FREEZE`, `supervisor.is_healthy` evaluates to `False`, permanently denying order intake until manual requalification.

### C. Bounded Recovery Without State Corruption
If the guardian worker thread terminates unexpectedly, the supervisor attempts restart up to `max_restarts = 3`. However:
- **State Preservation Guarantee:** If the guardian was in `HARD_FREEZE` or `QUARANTINED`, restarting the worker thread **NEVER** resets the state to `NORMAL`.
- **Exhaustion Lockout:** If `restart_count >= max_restarts`, the supervisor permanently halts automatic recovery, locking the system in `HARD_FREEZE`.

