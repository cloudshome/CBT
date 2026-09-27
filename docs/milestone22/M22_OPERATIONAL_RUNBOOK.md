# Milestone 22 Operational Runbook

**System:** SKY / Crypto Brain Terminal (CBT)  
**Component:** Testnet Execution Flight Runner & Multi-Venue Order Lifecycle Engine  
**Classification:** Standard Operating Procedures (SOP) & Incident Response Manual  
**Safety Protocol:** Fail-Closed / Metaclass Firewall Active (`REAL_CAPITAL_ENABLED = False`)  

---

## 1. Component Overview & Architecture

The Milestone 22 execution runtime operates autonomously in a supervised environment to execute pre-scheduled testnet flights across Binance Spot Testnet and Bybit V5 Testnet.

Key operational sub-systems:
- **`FlightSupervisor`**: Coordinates distributed atomic leases, prevents duplicate flight execution, and provides crash recovery.
- **`TestnetFlightRunnerService`**: Oversees the parent flight lifecycle, executes TWAP/Iceberg slicing schedules, monitors clock skew, and logs 7-stage latency telemetry.
- **`MultiVenueTestnetBridge`**: Dual-venue dispatch layer managing REST transport, exchange filter adherence, and Lost-ACK recovery FSM transitions.
- **`ParentExecutionLedger`**: Strict decimal accounting ledger tracking open, filled, canceled, and unresolved slices.
- **`RateLimitGovernor`**: Token bucket rate limiter with a reserved 20% capacity slice for `EMERGENCY_CANCEL`.

---

## 2. Pre-Flight Checklist

Before launching an execution flight, operators or autonomous orchestrators must verify:

1. **Environment & Hostname Check:**
   - Verify that endpoints resolve strictly to `testnet.binance.vision` and `api-testnet.bybit.com`.
   - Ensure production endpoints (`*.binance.com`, `*.bybit.com`) are structurally absent.
2. **Clock Synchronization:**
   - Execute an NTP synchronization verification.
   - The engine's internal `ClockSkewSentinel` will fail closed if local offset $|\hat{\theta}| > 1000\text{ ms}$.
3. **Lease Database Availability:**
   - Confirm write permissions on the SQLite database designated for leases and event journals (e.g. `data/testnet_flights.db` or configured URI).
4. **Symbol & Venue Allowlist:**
   - Confirm that the `FlightManifest` lists only authorized pairs (e.g., `BTCUSDT`, `ETHUSDT`) and venues (`BINANCE_SPOT_TESTNET`, `BYBIT_V5_TESTNET`).
5. **Notional and Quantity Limits:**
   - Verify `max_flight_notional` and `max_flight_quantity` are configured within safe testnet limits.

---

## 3. Flight Execution Workflow

### 3.1 Initializing and Starting a Flight

```python
import asyncio
from decimal import Decimal
from core.execution.testnet.flight_manifest import FlightManifest
from core.execution.testnet.supervisor import FlightSupervisor
from core.execution.testnet.flight_runner import TestnetFlightRunnerService

async def run_flight():
    manifest = FlightManifest(
        flight_id="FLIGHT_20260921_001",
        name="Scheduled TWAP Rehearsal",
        venues=["BINANCE_SPOT_TESTNET", "BYBIT_V5_TESTNET"],
        allowed_symbols=["BTCUSDT", "ETHUSDT"],
        max_flight_notional=Decimal("10000.00"),
        max_flight_quantity=Decimal("1.00"),
        max_order_slices=10,
    )

    supervisor = FlightSupervisor(db_path="data/testnet_flights.db")
    runner = TestnetFlightRunnerService(manifest=manifest, supervisor=supervisor)
    
    # Initialize components, filter metadata, and acquire lease
    await runner.initialize()
    
    # Run planned execution schedule
    await runner.run_flight()
```

---

## 4. Emergency Procedures & Panic Cancellation

### 4.1 Triggering Panic Cancellation

In the event of market anomaly, excessive slippage, external feed degradation, or manual operator override, panic cancel must be triggered immediately.

```python
# Programmatic panic cancel
await runner.trigger_panic_cancel()
```

### 4.2 Behavior of Panic Cancellation
1. The engine marks `is_panic_canceled = True`.
2. All open child slices across all active parent ledgers are identified.
3. Cancellation requests are dispatched via `MultiVenueTestnetBridge` using the highest priority:
   $$\text{RequestPriority.EMERGENCY\_CANCEL}$$
4. The rate limiter serves emergency cancellations from the reserved 20% token bucket, guaranteeing wire dispatch even if regular request tiers are exhausted.
5. **Strict Flight Scoping:** Only child orders tagged with the current `flight_id` are canceled. Foreign orders and concurrent tasks remain unaffected.

---

## 5. Failure Modes & Incident Resolution

| Incident / Symptom | Root Cause | Operator Action |
|---|---|---|
| `ClockSkewSentinelError` | Local system clock drifted $> 1000\text{ ms}$ from exchange time. | Re-sync local clock via `w32tm /resync` or chrony. Do not lower threshold. |
| `DuplicateFlightExecutionError` | A previous runner instance is holding the lease or an overlapping process started. | Check active processes; if previous run died, wait for lease expiry ($60\text{s}$) or invoke `supervisor.acquire_lease(..., force=True)`. |
| `OverfillCircuitBreakerError` | Fills received exceed parent target quantity ($Q_{\text{filled}} > Q_{\text{target}}$). | Immediate halt. Inspect exchange execution list and event journal for mismatched client order IDs or duplicate external fills. |
| `UnsupportedVenueOperationError` | An execution strategy attempted an unsupported order type (e.g. native iceberg on Bybit). | Check venue capability profile. Configure client-side simulated iceberg slicing instead. |
| `ConflictingEventAnomalyError` | Received two execution events with same `execution_id` but conflicting quantities/prices. | Engine halts fail-closed. Retain SQLite database for forensic inspection. |
| `UnresolvedQuantityLifecycleError` | Network timeout during slice placement left order status indeterminate after all retries. | Check exchange REST order query. Resolve order state manually in the FSM before completing parent order. |

---

## 6. Post-Flight Reconciliation & Qualification

Upon flight termination, the `QualificationGateEngine` evaluates the flight:
- Verification of exact quantity conservation identity:
  $$Q_{\text{target}} = Q_{\text{filled}} + Q_{\text{open}} + Q_{\text{canceled}} + Q_{\text{unresolved}}$$
- Rejection of any flight with non-zero $Q_{\text{unresolved}}$.
- Latency monotonicity inspection across all 7 stages.
- Output evidence bundle serialized to append-only JSON logs.
