# Milestone 23 State Machines: Campaign FSM & Qualification FSM

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 23  
**Classification:** Formal Transition Specifications  

---

## 1. Formal 16-State Campaign FSM (`CampaignState`)

| State | Allowed Transitions | Invariants Maintained |
|---|---|---|
| **`IDLE`** | `STARTING` | No active flights; timer stopped. |
| **`STARTING`** | `PREFLIGHT_VALIDATION` | SQLite connection initialized; WAL mode enabled. |
| **`PREFLIGHT_VALIDATION`** | `CAMPAIGN_ACTIVE`, `STARTUP_BLOCKED` | Checks clock offset, exchange connectivity, and acquires fenced lease. |
| **`STARTUP_BLOCKED`** | `[*]`, `IDLE` | Terminal failure or requires manual parameter reset. |
| **`CAMPAIGN_ACTIVE`** | `FLIGHT_EXECUTING`, `PAUSE_REQUESTED`, `EVIDENCE_CONVERGING` | Lease heartbeat refreshed every $10\text{s}$. Time counts towards $H_{\text{qualified}}$. |
| **`FLIGHT_EXECUTING`** | `INTER_FLIGHT_REST`, `FLIGHT_RECOVERY_PENDING`, `PAUSE_REQUESTED`, `PANIC_CANCELING` | Child slices dispatched; rate limiter governed; latency recorded. |
| **`FLIGHT_RECOVERY_PENDING`** | `FLIGHT_EXECUTING`, `CAMPAIGN_HALTED` | Lost-ACK recovery loop active; queries REST order status. |
| **`INTER_FLIGHT_REST`** | `CAMPAIGN_ACTIVE`, `PAUSE_REQUESTED` | Inter-flight rest period; heartbeat active; $Q_{\text{unresolved}} == 0$. |
| **`PAUSE_REQUESTED`** | `PAUSED` | Prevents new flight starts; drains or cancels active child slices. |
| **`PAUSED`** | `RESUME_RECONCILING` | Zero active slices; elapsed time assigned to $H_{\text{disqualified}}$. |
| **`RESUME_RECONCILING`** | `CAMPAIGN_ACTIVE`, `CAMPAIGN_HALTED` | Audits venue open orders; asserts $Q_{\text{unresolved}} == 0$. |
| **`PANIC_CANCELING`** | `CAMPAIGN_HALTED` | Dispatches cancellations under `RequestPriority.EMERGENCY_CANCEL`. |
| **`CAMPAIGN_HALTED`** | `[*]` | Safety halt due to overfill, accounting breach, or fencing violation. |
| **`EVIDENCE_CONVERGING`** | `QUALIFIED_PENDING_REVIEW`, `FAILED` | Recomputes cryptographic hash chain over all 336 hourly intervals. |
| **`QUALIFIED_PENDING_REVIEW`**| `CERTIFIED`, `FAILED` | All 8 gates evaluated; awaiting operator governance sign-off. |
| **`FAILED`** | `[*]` | Disqualified campaign. |

---

## 2. Campaign Qualification State Machine (`CampaignQualificationState`)

```
NOT_STARTED
    │
    ▼
QUALIFYING ◄────────────────────────────────────────┐
    │                                               │
    ├─────────────► TEMPORARILY_DISQUALIFIED ───────┤ (Transient issue resolved)
    │                       │                       │
    │                       ▼                       │
    ├─────────────► RECOVERY_PENDING ───────────────┘
    │                       │
    │                       ▼ (Disqualification window > 5%)
    ├─────────────► QUALIFICATION_RESET_REQUIRED
    │                       │
    ▼ (H_qual >= 336.0h)    ▼
QUALIFIED_PENDING_REVIEW   FAILED
    │
    ▼ (Sign-off)
CERTIFIED
```

### Transition Guard Rules:
1. `QUALIFYING` $\to$ `TEMPORARILY_DISQUALIFIED`: Triggered by `EXTERNAL_VENUE_FAULT`, `OPERATOR_CONTROL`, or `RECOVERABLE_DEGRADATION`.
2. `TEMPORARILY_DISQUALIFIED` $\to$ `QUALIFYING`: Returned when healthy telemetry resumes and discrepancy is zero.
3. `QUALIFYING` $\to$ `QUALIFICATION_RESET_REQUIRED`: Triggered if $H_{\text{disqualified}} / H_{\text{elapsed}} > 0.05$ or on any `ACCOUNTING_FAILURE`.
4. `QUALIFYING` $\to$ `QUALIFIED_PENDING_REVIEW`: Triggered only when $H_{\text{qualified}} \ge 336.0$ and all 8 gates pass.
