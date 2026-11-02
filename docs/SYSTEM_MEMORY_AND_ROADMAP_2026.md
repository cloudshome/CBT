# SKY / CRYPTO BRAIN TERMINAL (CBT)
## System Memory, Operational Baseline & Alpha Roadmap (2026)

> **Document Identity:** `SKY-MEM-2026-V1`  
> **Status:** ACTIVE & AUTHORITATIVE  
> **Anchored Commit:** `b889dce` (`main`, synchronized with `origin/main`)  
> **Certified Invariants:** Milestone 18 Execution Surface (14/14 gates, 149/149 tests green) | Milestone 35-R Independent Audit (15/15 obligations green) | Frontend Jest (148/148 green)  
> **Operational Stance:** Risk Primacy, Zero-Bypass Half-Kelly, Triple Confluence Gating, Absolute Test Isolation  

---

## 1. Executive Summary & Current Operational Truth

As of November 2026, the Crypto Brain Terminal (CBT / SKY) has reached an institutional level of engineering discipline and structural reliability:

1. **Test Isolation & Sandbox Hardening:**
   - All 3,500+ tests run strictly inside ephemeral SQLite sandboxes (`tests/conftest.py`), with complete schema auto-initialization across all subsystems (`causal_hypotheses_ledger`, `hypothesis_queue`, `research_variables`, `personal_learning_graph`, `evidence_vault`, `credential_vault`).
   - Inter-suite environment leakage (e.g. `MAX_AGGREGATE_RISK_PCT`) is deterministically purged between test runs.
   - Leftover paper positions in `shadow_positions` are automatically reset before and after each test function.

2. **Milestone 18 Certified Execution Surface Area:**
   - 14 certified files (`app.py`, `core/database.py`, `core/execution/...`) verified against cryptographic test identity SHA-256 (`2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b`).
   - 149/149 adversarial gates passed (Smart Order Routing, TWAP/VWAP slicing, Almgren-Chriss market impact, idempotency locks, and fill reconciliation).

3. **Milestone 35-R Independent Release Audit:**
   - 15/15 audit obligations verified green in `tests/execution/test_milestone35_r_independent_audit.py`.
   - Dual-profile Authenticode code signing with Digicert RFC-3161 HTTPS timestamps recorded in `release/CODE_SIGNING_REPORT.json`.
   - Release state machine locked to `RELEASE_CANDIDATE` awaiting physical Gate G-21 operator signature before any live trading promotion.

---

## 2. Service Authority Matrix & Backend Convergence (Priority 1)

To eliminate architectural seams and state divergence identified in `docs/PROJECT_INSPECTION_REPORT_AI.md`:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BROWSER & DESKTOP TERMINAL UI                         │
│                    (React 18 + TypeScript + Vite + Tailwind)                │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │ /api/*                      │ WebSocket
                        ▼                             ▼
┌───────────────────────────────────────────┐  ┌──────────────────────────────┐
│       FASTAPI BACKEND (PORT 8000)         │  │   CENTRAL INTELLIGENCE BUS   │
│          AUTHORITATIVE ROOT               │  │  (Order Book, Ticks, SMC)     │
│  - Quantitative Intelligence Engine       │  └──────────────┬───────────────┘
│  - SMC & Confluence Setup Engine          │                 │
│  - Portfolio Shadow & Risk Gatekeeper     │                 │
│  - Smart Order Router & Connectors        │                 │
└───────────────────────▲───────────────────┘                 │
                        │ Direct proxy for                     │
                        │ legacy clients                       │
┌───────────────────────┴───────────────────┐                 │
│       NODE / EXPRESS (PORT 3000)          │                 │
│         BOUNDED COMPATIBILITY LAYER       │                 │
│  - Forwards all trading & intelligence    │                 │
│    routes to FastAPI (127.0.0.1:8000)     │                 │
│  - Zero independent risk/trading state    │                 │
└───────────────────────────────────────────┘                 │
                                                              ▼
                                               ┌──────────────────────────────┐
                                               │   PERSISTENT SQLITE LEDGERS  │
                                               │  (trading_logs.db, brain.db) │
                                               └──────────────────────────────┘
```

* **Authoritative Trading & Risk Source:** Python FastAPI (`app.py`). All order validation, position management, margin calculation, and Half-Kelly sizing are executed exclusively in Python.
* **Node/Express Role:** Strictly bounded compatibility proxy. It must never independently mutate trading records or maintain divergent risk state.

---

## 3. The 80% Win-Rate Quantitative Engine Formulation

In institutional crypto quantitative trading, achieving an ~80% win-rate is mathematically impossible with a naive "always-in-the-market" strategy. It is achieved **only through hyper-selective filtering**—ruthlessly refusing 90% of mediocre setups and executing only when three independent dimensions converge:

### 3.1 The Triple Confluence Convergence Model

A trade is only authorized by the **Sovereign Master Agent** and **CentralTradingMind** when all three layers agree:

$$\text{Confluence Score} = B_1 (\text{Structure}) + B_2 (\text{Order Flow}) + B_3 (\text{Regime \& MTF}) + B_4 (\text{Derivatives}) \ge 85.0 / 100$$

1. **Layer 1: Structural Market Architecture (SMC & Geometry - 30 Pts)**
   - **Liquidity Sweep & Reclaim:** Price sweeps key swing high/low liquidity and aggressively reclaims the level within 1-3 bars.
   - **Order Block & FVG Mitigation:** Entry occurs within an unmitigated Fair Value Gap overlapping an institutional Order Block.
   - **Asymmetric Risk Hurdle:** Strict minimum $R:R \ge 2.0$, with Stop-Loss anchored strictly outside structural invalidation (max 2.5% distance).

2. **Layer 2: Microstructure & Order Flow (30 Pts)**
   - **Closed Candle Confirmation:** Wicks indicating absorption; no blind limit fills in front of high-velocity momentum.
   - **Displacement Score $\ge 70$:** Clear institutional expansion bar with expanding volume ($rVol \ge 1.35x$).
   - **Cumulative Volume Delta (CVD) Alignment:** Aggressive market buy/sell volume matches proposed trade direction.

3. **Layer 3: MTF & Regime Alignment (25 Pts)**
   - **Higher Timeframe Confluence:** 4-Hour and 1-Hour trend stacks must either agree or confirm counter-trend exhaustion.
   - **Chop / Low-Energy Prohibition:** If $ADX < 20$ or $rVol < 0.85$, the system triggers **100% CASH PRESERVATION**. Zero trades are permitted during choppy consolidation.

4. **Layer 4: Derivatives & Sentiment Crowding (15 Pts)**
   - **Crowding Filter:** Rejects LONG if perpetual funding rate $> +0.03\%$ (crowded longs paying high premium); rejects SHORT if funding rate $< -0.03\%$.
   - **Open Interest Squeeze Dynamics:** Requires Open Interest expansion on breakouts or aggressive liquidation cascades on sweeps.

---

## 4. Immediate Tactical Action Items

| Priority | Action Item | Target Modules | Status |
|:---:|:---|:---|:---:|
| **P-1** | **Confluence Hurdle Hardening** | `core/sky_intelligence/setup_engine.py`<br>`core/mastermind/sovereign_master_agent.py` | Ready to Implement |
| **P-2** | **Backend Proxy Convergence** | `src/routes/paper.ts`<br>`src/routes/scan.ts` | Ready to Audit & Bridge |
| **P-3** | **Live Telemetry & WebSocket Heartbeat** | `core/terminal_routes.py`<br>`frontend/src/providers/DataProvider.tsx` | Ready to Inspect |
| **P-4** | **Testnet Paper Forward Validation** | `core/execution/paper_routes.py`<br>`data/trading_logs.db` | Active |

---

## 5. Architectural Invariants (Non-Negotiable)

1. **Risk Primacy:** No trade can bypass the 1.5% equity risk cap or the 2.0% cumulative portfolio ceiling.
2. **Directional Anti-Cannibalization:** The system can never open conflicting LONG and SHORT positions on the same underlying asset simultaneously.
3. **Causal Firewalls:** Past performance claims require out-of-sample backtests with $N \ge 30$, $p \le 0.05$, and Deflated Sharpe Ratio (DSR) $\ge 0.80$.
4. **Zero-Lookahead Invariant:** Candle $t$ indicators close before bar $t+1$ execution.
5. **Production SQLite Isolation:** All tests must run against ephemeral in-memory or temp SQLite sandboxes.
