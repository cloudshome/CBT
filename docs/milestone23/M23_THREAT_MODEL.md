# Milestone 23 Threat Model & Adversarial Failure Matrix

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 23  
**Classification:** Long-Running Autonomous Systems Threat Assessment  

---

## 1. Adversarial Failure Vectors & Structural Mitigations

| Threat ID | Threat Description | Attack Vector / Trigger | Structural Mitigation | Fail-Closed Behavior |
|:---:|:---|:---|:---|:---|
| **THREAT-01** | **Split-Brain Dual Execution** | Process A freezes during GC pause; Process B acquires lease; Process A unfreezes and executes concurrently. | Monotonic fencing token (`fencing_token`). Token validated before every slice dispatch. | Process A detects stale token; raises `StaleLeaseFencingError` and halts. |
| **THREAT-02** | **Phantom Time Accumulation** | Campaign paused or exchange down, but qualification timer keeps ticking towards 336 hours. | 3-stream time partitioning ($H_{\text{elapsed}} = H_{\text{qualified}} + H_{\text{disqualified}}$). Only active, healthy intervals qualify. | Downtime assigned to $H_{\text{disqualified}}$. Timer resets if threshold breached. |
| **THREAT-03** | **Orphan Slice on Pause** | Operator triggers pause while child slice is in flight; parent order left half-executed. | `PAUSE_REQUESTED` state waits for active flight to reach clean terminal state before transitioning to `PAUSED`. | Aborts new slices; actively cancels open slices. |
| **THREAT-04** | **Regime Signal Hallucination** | Volatility classifier emits directional bias or triggers unvalidated trading logic. | Causal firewall: `MarketRegimeObservation` strictly selects test coverage stress profiles (burst/wide/basis). | Rejects any order parameter attempting directional positioning. |
| **THREAT-05** | **Emergency Cancel Starvation** | Trading loop exhausts rate limit tokens; panic cancel request blocked by HTTP 429. | RateLimitGovernor enforces 20% token reserve dedicated strictly to `RequestPriority.EMERGENCY_CANCEL`. | Cancel requests bypass normal tier; dispatch immediately. |
| **THREAT-06** | **Telemetry Sequence Corruption** | WebSocket drops packet; frontend displays optimistic or stale fills. | Strict sequence numbering (`telemetry_seq`). Heartbeat watchdog triggers `DEGRADED / STALE` watermark if $>3\text{s}$. | UI displays warning badge and blocks optimistic rendering. |
| **THREAT-07** | **Evidence Log Tampering** | Operator or corrupted disk alters past interval qualification metrics. | Chained cryptographic hashing: $H_i = \text{SHA256}(H_{i-1} \parallel \text{IntervalData}_i)$. | Any mismatch breaks hash chain; fails audit verification. |
| **THREAT-08** | **Production Capital Leakage** | Code change attempts to dispatch real capital during testnet campaign. | Permanent metaclass firewall: `REAL_CAPITAL_ENABLED = False`. Endpoint policy blocks production URLs pre-socket. | Throws `FatalConstitutionalViolationError` and crashes instantly. |

---

## 2. Invariant Falsification Guarantees

Under no circumstances may any of the following occur:
1. $H_{\text{qualified}}$ increments while the campaign is in `PAUSED`, `CAMPAIGN_HALTED`, or `STARTUP_BLOCKED`.
2. A slice is dispatched with an expired lease or stale fencing token.
3. An unresolved quantity ($Q_{\text{unresolved}} > 0$) is ignored or zeroed out without exchange proof.
4. An emergency panic cancel fails due to lack of rate limit capacity.
