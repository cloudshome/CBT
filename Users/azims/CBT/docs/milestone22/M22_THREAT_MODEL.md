# Milestone 22 Threat Model & Adversarial Defense Architecture

> **System:** SKY / Crypto Brain Terminal (CBT)  
> **Milestone:** 22 — Live Testnet Execution Flight Runner & Multi-Venue Order Lifecycle Engine  
> **Security Level:** Institutional Electronic Trading Safety Standard  
> **Date:** September 2026  

---

## 1. Threat Taxonomy & Mitigation Matrix

| Threat ID | Threat Vector | Attack / Failure Scenario | Defense Architecture & Machine Invariant | Fail-Closed Posture |
|:---:|:---|:---|:---|:---:|
| **THREAT-01** | **Accidental Production Capital Deployment** | Misconfigured environment variable or spoofed URL causes order to reach live Binance/Bybit production order book. | `EndpointPolicy` canonical hostname allowlist rejects all production domains (`api.binance.com`, `api.bybit.com`, etc.) pre-socket. `REAL_CAPITAL_ENABLED = False` metaclass immutable firewall. | Socket creation aborted; process raises `EndpointSecurityBreachError`. |
| **THREAT-02** | **Lost-ACK Phantom Placement** | HTTP 504 / timeout on order placement; matching engine actually placed the order. System assumes order dropped, retries, and doubles position. | `LostAckRecoveryFSM` transitions to `UNKNOWN_EXTERNAL_STATE` -> `RECOVERY_PENDING` -> `QUERYING`. Venue matching engine is queried with `client_order_id`. If found, maps `order_id` and records ACK. $0$ duplicate placements permitted. | New placements blocked until external state resolved. |
| **THREAT-03** | **Matching Engine Ingest Lag (`ORDER_NOT_FOUND != CANCELED`)** | Transport drops; immediate query to exchange returns 404 / `ORDER_NOT_FOUND` because order is queued in matching engine. Dispatcher marks order canceled and reallocates slice. 50ms later, order matches. | Absolute Rule: `ORDER_NOT_FOUND != ORDER_CANCELED`. Recovery FSM performs 3 exponential backoff queries and checks execution history before declaring `REJECTED_CONFIRMED`. Never assumes canceled without positive terminal status. | Slice quantity locked in `Q_unresolved` during query retry loop. |
| **THREAT-04** | **Overfill & Position Runaway** | Partial fills aggregate beyond target quantity due to concurrent fill reports or missed cancellations. | `ParentExecutionLedger` verifies $Q_{\text{filled}} \le Q_{\text{target}}$ on every fill event. If $Q_{\text{filled}} > Q_{\text{target}}$, immediately trips `OverfillCircuitBreakerError`, sets `is_halted = True`, and aborts all subsequent slice dispatches. | Ledger permanently halts; emergency panic cancel-all invoked. |
| **THREAT-05** | **Conflicting Duplicate Execution Reports** | Exchange replay or malicious stream sends duplicate execution report with identical `trade_id` but conflicting price or quantity. | `AppendOnlyEventJournal` and 4-tier deduplicator check economic attributes. If duplicate `execution_id` has different price/qty/symbol/side, both events are preserved in forensic storage and system raises `ConflictingEventAnomalyError`. | Lifecycle immediately halted; flight disqualified from burn-in. |
| **THREAT-06** | **Rate-Limit Starvation During Outage** | Reconnection query flurry exhausts exchange IP rate limit (1200 req/min), blocking emergency panic cancellations. | `RateLimitGovernor` enforces priority token budgeting. Dedicated 20% reserve is inaccessible to normal order placements and exclusively allocated to `EMERGENCY_CANCEL` (Priority 3). | Normal dispatches throttled; emergency cancellations guaranteed capacity. |
| **THREAT-07** | **Host Clock Drift Distorting Latency Telemetry** | Local host NTP drift or VM time jump distorts markout and latency measurements. | Real-time `ClockSkewSentinel` estimates round-trip midpoint offset $\hat{\theta} = \frac{T_0 + T_1}{2} - T_{\text{server}}$. If $|\hat{\theta}| > 1000\,\text{ms}$, trips circuit breaker. | Flight supervisor fails closed with `ClockSkewSentinelError`. |
| **THREAT-08** | **Supervisor Split-Brain / Duplicate Flight Run** | Two worker processes attempt to execute the same flight manifest concurrently, causing double-slicing. | `FlightSupervisor` requires atomic lease lock (`testnet_flight_leases`). Active lease prevents secondary supervisor from acquiring flight. | Second supervisor raises `DuplicateFlightRunError` and terminates. |

---

## 2. Quantitative Risk Primacy Guarantees

1. **Zero-Bypass Capital Gate:** No code path in Milestone 22 can route orders to live production connectors. The live connector boundary remains strictly isolated under Milestone 18 certified code.
2. **Zero Orphaned Slices:** Every child slice is durably mapped to a parent order and an immutable `placement_intent_id`.
3. **Quantity Conservation Identity:**
   $$Q_{\text{target}} = Q_{\text{filled}} + Q_{\text{open}} + Q_{\text{canceled}} + Q_{\text{unresolved}}$$
   Violating this identity by even $10^{-18}$ raises `QuantityConservationBreachError` and aborts the execution.
