# Milestone 23 Architecture: Continuous 14-Day Live Testnet Burn-In Campaign & Real-Time Flight Cockpit

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 23  
**Classification:** Long-Running Autonomous Systems & Forensic Evidence Architecture  

---

## 1. System Topology & Subsystem Separation

Milestone 23 connects the certified order lifecycle and recovery engine of Milestone 22 to a multi-day autonomous campaign supervisor, an append-only qualification evidence ledger, and a real-time institutional desktop cockpit:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DESKTOP COCKPIT / FRONTEND                            │
│  TestnetBurnInHUD.tsx  │  Latency Distribution  │  14-Day Progress Tracker  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Sequence-Monotonic Telemetry (/api/testnet)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    CAMPAIGN TELEMETRY & CONTROL ROUTER                      │
│                  (core/execution/testnet/routes.py)                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    CAMPAIGN ORCHESTRATOR & FENCED SUPERVISOR                │
│            (core/execution/testnet/campaign_orchestrator.py)                │
│                                                                             │
│  - 16-State Campaign FSM                                                    │
│  - Monotonic Lease Fencing (SQLite WAL: data/testnet_campaign.db)           │
│  - Safe Pause / Resume Reconciler                                           │
│  - Inter-Flight Scheduling & Heartbeat Loop                                 │
└───────────────────┬───────────────────────────────────────┬─────────────────┘
                    │                                       │
┌───────────────────▼──────────────────┐ ┌──────────────────▼─────────────────┐
│     REGIME COVERAGE POLICY ENGINE    │ │    CONTINUOUS QUALIFICATION ENGINE │
│ (core/execution/testnet/regime_*.py) │ │ (core/execution/testnet/qual_*.py) │
│                                      │ │                                    │
│ - MarketRegimeObservation Provenance │ │ - 3-Stream Time Accounting         │
│ - Coverage Stress Profiles:          │ │   (H_elapsed, H_qual, H_disqual)   │
│   BURST, WIDE, BASIS, NORMAL         │ │ - 7-Tier Event Classifier          │
│ - Fallback to Safe Default           │ │ - Chained SHA-256 Evidence Ledger  │
└───────────────────┬──────────────────┘ └──────────────────┬─────────────────┘
                    │                                       │
                    ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 MILESTONE 22 TESTNET EXECUTION ENGINE                       │
│  TestnetFlightRunnerService │ MultiVenueTestnetBridge │ ParentExecutionLedger│
│  filters.py │ placement_intent.py │ event_journal.py │ recovery_fsm.py      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 EXTERNAL TESTNET EXCHANGES (MILESTONE 21)                   │
│   Binance Spot Testnet (testnet.binance.vision)                             │
│   Bybit V5 Testnet (api-testnet.bybit.com)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Monotonic Lease Fencing & Split-Brain Prevention

When operating continuously for 336 hours, machine restarts, OS sleep cycles, or garbage collection pauses can cause temporary process freezing. If a frozen process wakes up after its lease has been acquired by a replacement instance, both might attempt to place testnet orders simultaneously.

### Fencing Algorithm:
1. `testnet_campaign_leases` maintains an auto-incrementing integer `fencing_token`.
2. Upon lease acquisition or takeover, the new supervisor executes:
   $$\text{UPDATE testnet\_campaign\_leases SET fencing\_token = fencing\_token + 1, supervisor\_id = ?, expires\_at = ?}$$
3. The supervisor stores this `local_fencing_token`.
4. Prior to initiating any flight, dispatching any slice, or committing any telemetry, the supervisor queries the database within a transaction.
5. If $\text{current\_db\_token} > \text{local\_fencing\_token}$, the supervisor immediately trips `StaleLeaseFencingError`, revokes its local authority, aborts in-flight execution, and enters `CAMPAIGN_HALTED`.

---

## 3. The 3-Stream Time Partitioning Architecture

Operational time is partitioned into 1-hour discrete accounting buckets. Each bucket records:

```python
@dataclass
class QualificationIntervalRecord:
    interval_id: str             # INT_YYYYMMDD_HH00
    start_epoch: float
    end_epoch: float
    duration_sec: float
    elapsed_hours: float
    qualified_hours: float       # Counted towards 336h
    disqualified_hours: float     # Excluded from 336h
    event_counts: dict[str, int] # Count by 7-tier classification
    is_qualifying: bool
    prev_interval_hash: str      # Cryptographic hash chain
    interval_hash: str           # SHA-256(prev_hash || data)
```

### Cumulative Aggregation Identity:
At all times $t$, the engine asserts:
$$H_{\text{elapsed}} = H_{\text{qualified}} + H_{\text{disqualified}}$$
If any discrepancy exceeds $10^{-6}$ hours ($< 3.6\,\text{ms}$), the qualification engine fails closed with `AccountingConservationBreachError`.

---

## 4. Safe Pause, Resume & Crash Reconciliation

### 4.1 Pausing
1. When `pause_campaign()` is invoked, the state transitions from `CAMPAIGN_ACTIVE` or `FLIGHT_EXECUTING` to `PAUSE_REQUESTED`.
2. In `PAUSE_REQUESTED`, no new parent flights or child slices are created.
3. Open child slices in the active flight are allowed to finish, or are canceled via the bridge.
4. Once $Q_{\text{open}} == 0$ and $Q_{\text{unresolved}} == 0$, the state transitions to `PAUSED`.
5. The qualification timer pauses immediately; all elapsed time in `PAUSED` is assigned strictly to $H_{\text{disqualified}}$.

### 4.2 Resuming
1. When `resume_campaign()` is invoked, the state transitions to `RESUME_RECONCILING`.
2. The orchestrator conducts an authoritative REST audit of Binance Spot Testnet and Bybit V5 Testnet to check for unexpected open orders or orphan executions.
3. If open testnet orders exist, they are audited against the local event journal.
4. Only when the ledger verifies $Q_{\text{unresolved}} == 0$ does the state advance to `CAMPAIGN_ACTIVE`.
