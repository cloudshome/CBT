# Milestone 22 Architecture Specification: Live Testnet Execution Flight Runner & Multi-Venue Lifecycle Engine

> **System:** SKY / Crypto Brain Terminal (CBT)  
> **Milestone:** 22 — Live Testnet Execution Flight Runner & Multi-Venue Order Lifecycle Engine  
> **Classification:** Class D (Major Architecture) / Class H (Live / Paper Boundary Governance)  
> **Status:** IMPLEMENTED & VERIFIED  

---

## 1. Architectural Overview & Single-Responsibility Topology

Milestone 22 implements the bridge between algorithmic execution (TWAP and Simulated Iceberg slicing) and real external exchange testnets (Binance Spot Testnet and Bybit V5 Unified Testnet) with formal lost-ACK recovery, exact Decimal accounting, nanosecond latency decomposition, and 10-point burn-in qualification gating.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLIGHT REHEARSAL SUPERVISOR                        │
│                         (flight_runner.py / supervisor.py)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ • Bound to immutable FlightManifest with SHA-256 config digest              │
│ • Atomic supervisor lease lock preventing duplicate concurrent executions   │
│ • Real-time Clock Skew Sentinel: fails closed if |theta_hat| > 1000ms       │
│ • Emergency Panic Cancel-All Trigger (strictly flight-scoped)               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Parent Execution Intent
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ALGORITHMIC SLICING DISPATCHER                        │
│                                (dispatcher.py)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ • TWAP: Deterministic schedule generation with final-slice remainder absorp.│
│ • Simulated Iceberg: Sequential visible_qty replenishment upon fill confirm │
│ • Slices bound to durable PlacementIntent before wire dispatch              │
└──────────────────┬───────────────────────────────────────┬──────────────────┘
                   │ Child Slice Intent                    │ Fills & Receipts
                   ▼                                       ▲
┌──────────────────────────────────────┐ ┌────────────────────────────────────┐
│      EXCHANGE FILTER RULES ENGINE    │ │    PARENT / CHILD EXECUTION LEDGER │
│              (filters.py)            │ │        (execution_ledger.py)       │
├──────────────────────────────────────┤ ├────────────────────────────────────┤
│ • Exact Decimal quantize (no float)  │ │ • Tracks 8 distinct quantities     │
│ • Price: tickSize quantization       │ │ • Q_target = Q_filled + Q_open +   │
│   BUY: ROUND_FLOOR, SELL: ROUND_CEIL │ │             Q_canceled + Q_unres   │
│ • Qty: stepSize quantization         │ │ • Q_submitted <= Q_target          │
│   Strictly ROUND_DOWN                │ │ • Overfill Circuit Breaker trips   │
│ • Notional: price * qty >= minNotional│ │   fail-closed halt on Q_f > Q_t    │
└──────────────────┬───────────────────┘ └─────────────────┬──────────────────┘
                   │ Normalized Slice                      │ Clean Fills
                   ▼                                       │
┌───────────────────────────────────────────────────────┐  │
│              MULTI-VENUE TESTNET BRIDGE               │  │
│               (multi_venue_bridge.py)                 │  │
├───────────────────────────────────────────────────────┤  │
│ • Unified execution interface across Binance & Bybit  │  │
│ • Strict venue capability enforcement (no emulation)  │  │
│ • 10-State Formal Lost-ACK Recovery FSM:              │  │
│   ORDER_NOT_FOUND != ORDER_CANCELED                   │  │
│   Ambiguity triggers query loop with backoff          │  │
└──────────────────┬────────────────────────────────────┘  │
                   │ REST / Private WS                     ▼
                   ▼                     ┌────────────────────────────────────┐
    ┌──────────────────────────────┐     │     QUALIFICATION EVIDENCE GATE    │
    │   EXTERNAL EXCHANGE TESTNETS │────▶│       (qualification_gate.py)      │
    │  (Binance Spot & Bybit V5)   │     │ • 10-point strict audit scorecard  │
    └──────────────────────────────┘     │ • Feeds 14-day burn-in ledger      │
                                         │ • Classification:                  │
                                         │   LIFECYCLE_VALIDITY_EVIDENCE      │
                                         └────────────────────────────────────┘
```

---

## 2. Immutable Identity Hierarchy

Milestone 22 enforces a strict, collision-resistant identity chain:

$$\text{flight\_id} \longrightarrow \text{parent\_order\_id} \longrightarrow \text{child\_slice\_id} \longrightarrow \text{placement\_intent\_id} \longrightarrow \text{venue\_order\_id} \longrightarrow \text{execution\_id}$$

### Rules:
1. **`placement_intent_id` Reuse:** A retry of the same logical slice (e.g. after a query attempt or transport reconnect) reuses the exact same `placement_intent_id`. It is never regenerated.
2. **Client Order ID Normalization:** Normalized format `M22_<intent_hash>_<slice_id[-6:]>` capped at 36 characters to satisfy both Binance (`newClientOrderId` max 36 chars) and Bybit (`orderLinkId` max 36 chars).
3. **No Synthetic Identifiers:** Exchange execution reports retain native `trade_id` / `execId` for authoritative deduplication.

---

## 3. Rate-Limit Governance & Priority Reserves

To prevent recovery storms and WebSocket reconnection floods from starving critical operations:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       VENUE RATE LIMIT GOVERNOR                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. EMERGENCY_CANCEL (Priority 3): Dedicated 20% Reserve                     │
│    • Reserved for panic cancel-all and kill switch activations              │
│    • Never throttled until bucket reaches 0 tokens                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. RECOVERY_QUERY (Priority 2): High Priority                               │
│    • Authoritative order status queries during Lost-ACK recovery            │
│    • Allowed to consume into upper 50% of the emergency reserve             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. NORMAL_PLACEMENT (Priority 1): Standard Budget                           │
│    • New parent slice dispatches                                            │
│    • Strictly blocked when available tokens <= 20% emergency reserve floor  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 7-Stage Monotonic Latency Telemetry ($T_0 \to T_7$)

Milestone 22 decomposes the order lifecycle into 7 precise intervals in monotonic nanoseconds:

| Interval | Stage Description | Measurement Points | Institutional Target |
|:---:|:---|:---:|:---:|
| $\Delta T_1$ | Intent Persistence | $T_1 - T_0$ | $< 500\,\mu\text{s}$ |
| $\Delta T_2$ | Wire Dispatch Preparation | $T_2 - T_1$ | $< 250\,\mu\text{s}$ |
| $\Delta T_3$ | Network Transport RTT | $T_3 - T_2$ | Venue RTT ($< 150\,\text{ms}$) |
| $\Delta T_4$ | Order ACK Normalization | $T_4 - T_3$ | $< 100\,\mu\text{s}$ |
| $\Delta T_5$ | WebSocket Fill Latency | $T_5 - T_4$ | Exchange matching time |
| $\Delta T_6$ | Reconciliation Ledger Commit | $T_6 - T_5$ | $< 500\,\mu\text{s}$ |
| $\Delta T_7$ | Qualification Ledger Ingestion | $T_7 - T_6$ | $< 250\,\mu\text{s}$ |

### Monotonicity Invariant:
For every execution slice:
$$T_0 \le T_1 \le T_2 \le T_3 \le T_4 \le T_5 \le T_6 \le T_7$$
Any clock regression or negative duration triggers immediate telemetry quarantine.
