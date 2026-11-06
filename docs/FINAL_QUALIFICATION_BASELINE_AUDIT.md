# CBT / SKY — FINAL QUALIFICATION BASELINE AUDIT

**Protocol Authority:** `AGENTS.md` Level 0 & System Constitution Level 1  
**Audit Classification:** Class A (System Inspection & Baseline Establishment — Zero Code Modifications)  
**Date:** 2026-11-04  
**Audit Status:** `COMPLETE & EMPIRICALLY GROUNDED`  
**Git HEAD Commit:** `e1495d4` (Fast-forward synchronized with remote `origin/main`)

---

## 1. Executive Summary & Epistemic Verdict

An exhaustive, non-destructive audit of the complete SKY / Crypto Brain Terminal repository was conducted to establish the true project baseline. The assessment from the review is confirmed:

> **[FACT]** The project is **not** a collection of mock ideas; it contains over 3,600 automated tests, a cryptographically certified execution router (Milestone 18), institutional risk gates (Portfolio Risk Guardian), and rigorous empirical validation tooling.  
> **[FACT]** However, the system is **not yet ready for autonomous live capital deployment**. Many certified engineering milestones verify *component-level invariants*, not end-to-end portfolio profitability or live execution autonomy.  
> **[FACT] Feature additions are now FROZEN.** The remaining distance requires zero new indicators or AI agents; it strictly requires solving 6 concrete architectural and empirical blockers.

---

## 2. Quality Gates & Test Suite Verification Scorecard

The complete system preflight verification suite (`scripts/system_preflight.py`), TypeScript test harness, and M18 certification verifiers were executed.

| Quality Gate | Measured Status | Passing / Total | Epistemic Finding |
| :--- | :---: | :---: | :--- |
| **Database Schema Integrity** | `PASS` | 100% | SQLite ledgers (`cryptobrain.db`, `trading_logs.db`) match active models. |
| **Proxy Route Contract Parity** | `PASS` | 100% | Express gateway (`server.ts`) and FastAPI (`app.py`) API routes align. |
| **M18 Cryptographic Certification** | `PASS` | **149 / 149** (100%) | All 14 adversarial execution & SOR gates verified green. |
| **TypeScript / Jest Test Suite** | `PASS` | **151 / 151** (100%) | 23/23 test suites passing across paper, scan, and security. |
| **Frontend Production Build** | `PASS` | 100% | Vite + TypeScript builds production bundle in 16.36s. |
| **Pytest Quantitative Suite** | `FAIL` (99.86%) | **3,597 / 3,605** | **5 failures** identified and root-caused below. |

### Root Cause Analysis of the 5 Pytest Failures:
1. `tests/governance/test_architecture_boundaries.py::test_entire_codebase_boundary_compliance`:
   - *Failure:* Layer 2 (`core/worker.py`) imports Layer 3 (`core.telegram.jobs` and `core.telegram_bot`).
   - *Root Cause:* Stratification violation introduced during background worker decoupling.
2. `tests/test_milestone33_failure_injection.py::test_m33_stalled_daemon_watchdog_failure_injection`:
   - *Failure:* Stalled daemon watchdog test failed assertion.
   - *Root Cause:* Test harness race condition—the background daemon thread running at 20ms intervals refreshed the heartbeat before the assertion evaluated.
3. `tests/test_phase3_backtester_and_sizing_audit.py::test_stop_first_ambiguous_candle_rule`:
   - *Failure:* `assert -1.002 == -1.0`.
   - *Root Cause:* `EXECUTION_MODEL` default was set to `"slip"`, causing `_evaluate()` to apply slippage to `gp.rr_achieved` in place.
4. `tests/test_phase3_backtester_and_sizing_audit.py::test_long_and_short_payoff_symmetry`:
   - *Failure:* `assert 1.998 == 2.0`.
   - *Root Cause:* Same as above—slippage deduction applied during pure payoff symmetry test.
5. `tests/test_trading_concept_intelligence.py::test_fail_closed_lifecycle_promotion_gates`:
   - *Failure:* Transient registry state pollution when run after 3,000 preceding tests (passes 11/11 standalone).

---

## 3. Subsystem Breakdown: Implemented vs. Genuinely Operational

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                SKY SUBSYSTEM STATUS                               │
├──────────────────────┬────────────────────────────────┬───────────────────────────┤
│ Subsystem            │ Implemented Architecture       │ Genuinely Operational?    │
├──────────────────────┼────────────────────────────────┼───────────────────────────┤
│ Signal Engine        │ SMC, OB, FVG, Trend Pullback   │ YES (in backtest/sim)     │
│ Execution Router     │ SOR, TWAP, VWAP, Slicing       │ YES (paper/sim); NO (live)│
│ Risk Desk            │ Half-Kelly, Drawdown Ceiling   │ YES (hard rejection)      │
│ Opportunity Dispatch │ 3-Position Capacity            │ PARTIAL (No displacement) │
│ Historical Replay    │ Walk-forward single setup      │ YES (single); NO (10k PR) │
│ Live Execution Gate  │ Fail-closed, kill-switch       │ YES (Safe, strictly off)  │
│ Multi-Modal Kronos   │ Vision-language parsing        │ MOCK / HEAVY API DEPENDENT│
└──────────────────────┴────────────────────────────────┴───────────────────────────┘
```

### Detailed Audits by Subsystem:

### A. Execution & Smart Order Routing (`core/execution/`)
- **Implemented:** Full SOR with multi-venue book aggregation (Binance, Bybit), liquidity-seeking slicing, Almgren-Chriss market impact, and cryptographic fill reconciliation ledger.
- **Operational Reality:** Operates with 100% pass rate in simulated/paper trading.
- **Missing for Production:** Live network execution router is deliberately locked behind `REAL_CAPITAL_ENABLED=false` and requires live exchange credentials, reconnect watchdog, and exchange-level dead-man's switch verification.

### B. Risk Management & Capital Governance (`core/risk/`, `core/execution/capital_governor.py`)
- **Implemented:** `PortfolioRiskGuardian` enforces:
  - Base capital: $10,000 USD
  - Daily loss freeze: 1.5% ($150)
  - Max drawdown ceiling: 2.0% ($200)
  - Max single trade risk: 0.50% ($50)
  - Aggregate open risk cap: 0.75% ($75)
  - Single asset exposure cap: 1.5% ($150)
  - Max concurrent positions: 3 positions
- **Operational Reality:** The risk checks are mathematically strict, deterministic, and fail-closed.
- **Critical Unfinished Integration:** **The 4th Trade Displacement Blocker.**
  - When 3 positions are open and a 4th valid signal appears, line 775 of `core/risk/portfolio_risk_guardian.py` unconditionally throws `MAX_CONCURRENT_POSITIONS_REACHED`.
  - **There is zero replacement logic.** The system cannot currently compare the marginal utility, unrealized PnL, remaining risk, or correlation of existing positions to swap out an inferior holding for a superior setup.

### C. Historical Research & Empirical Edge Validation (`data/backtester.py`, `engine/edge_validation.py`)
- **Implemented:** 4-window walk-forward validation (Train 60%, Val 15%, OOS 15%, Recent 10%), 3-tier cost modeling (taker, maker_in_taker_out, maker), and Monte Carlo bootstrapping.
- **Operational Reality:** The recent Milestone 47.1 audit on 1,000 real market bars across `BTCUSDT`, `ETHUSDT`, `SOLUSDT` demonstrated:
  - Moving to 4h and maker limit execution reduces friction drag from ~0.46R to < 0.09R.
  - However, directional net expectancy remains negative on untouched OOS windows (`-0.853R` to `-1.019R`).
  - The Phase 4 research experiment (showing +0.710R to +0.863R on BTC/ETH 1h) represents specific filtered setups (Buy/Sell Pullback, FVG Retest) under selected regimes, not the entire baseline engine.
- **Missing for Production:** **The $10,000 Portfolio-Level Historical Replay.** Single-plan graders grade trades in isolation. They do not simulate concurrent cash flows, portfolio margin, correlation-based sizing, and simultaneous drawdowns of a $10,000 balance over time.

---

## 4. Documentation vs. Source Code Divergence

| Area | Documentation Claim | Actual Source Code Reality | Discrepancy Severity |
| :--- | :--- | :--- | :---: |
| **Position Limit** | "Intelligent multi-asset portfolio arbiter dynamically managing 3 positions." | `portfolio_risk_guardian.py:775` executes hard rejection if `open_positions >= 3`. No displacement algorithm exists. | **High** |
| **Milestone 46 / Burn-in** | "Milestone 46 Certified; Milestone 32 336-hour testnet burn-in qualified." | Component test suites pass in offline mock mode (`tests/conftest.py`). No real exchange burn-in has been run against a live exchange order book. | **High** |
| **Execution Default** | "Honest backtest default `EXECUTION_MODEL=none`." | Commit `5a9925e` changed `config.py` default to `EXECUTION_MODEL=slip`, causing 2 regression failures in raw math unit tests. | **Medium** |
| **Kronos Engine** | "Multi-modal vision and macro reasoning driving real-time risk." | Kronos defaults to `LLM_PROVIDER=off` in production configurations; falls back to static indicators. | **Medium** |

---

## 5. The 6 Critical Blockers Before Final Release

To reach a finished, production-grade, trustworthy autonomous trading system, work must be strictly focused on these 6 deliverables:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          ROADMAP TO FINAL QUALIFICATION & RELEASE                       │
├────┬─────────────────────────────────────────────────┬──────────┬───────────────────────┤
│ #  │ Deliverable                                     │ Priority │ Core Challenge        │
├────┼─────────────────────────────────────────────────┼──────────┼───────────────────────┤
│ P0 │ Architecture Cleanliness & 100% Green Gates     │ Critical │ Fix 5 test failures   │
│ P0 │ Intelligent 4th Trade Displacement Engine       │ Critical │ Multi-factor arbiter  │
│ P0 │ $10,000 Portfolio-Level Historical Replay Engine│ Critical │ Concurrent cash & DD  │
│ P1 │ BTC, ETH, and GOLD Strategy Filter Validation   │ High     │ Prove positive edge   │
│ P1 │ Multi-Venue Live Paper Burn-in (Testnet/Demo)   │ High     │ Real websocket stream │
│ P1 │ Failure Recovery & Dead-Man's Switch Audit      │ High     │ Cancel-on-disconnect  │
└────┴─────────────────────────────────────────────────┴──────────┴───────────────────────┘
```

### Detailed Deliverable Specifications:

### Deliverable 1 (P0): Architecture Cleanliness & 100% Test Gate Convergence
- **Task:** Eliminate the 5 failing tests in the Pytest suite:
  1. Fix Layer 2 $\to$ Layer 3 import in `core/worker.py` (move Telegram jobs notification dispatch to Layer 3 hook).
  2. Fix race condition in `test_m33_stalled_daemon_watchdog_failure_injection`.
  3. Ensure backtester math unit tests isolate `EXECUTION_MODEL="none"` via scoped fixture.
  4. Fix transient registry state in trading concept tests.
  5. Format 6 files flagged by `ruff format`.

### Deliverable 2 (P0): Intelligent 4th-Trade Opportunity Displacement Engine
- **Task:** Replace the hard-cap rejection in `PortfolioRiskGuardian` with an active Opportunity Displacement Arbiter.
- **Algorithm Requirements:**
  When `open_positions == 3` and a 4th proposed trade $T_{\text{new}}$ is submitted:
  1. Calculate marginal utility score $U(T) = f(\mathbb{E}[R], \text{WinRate}, \text{Confidence}, \text{RegimeFit})$.
  2. Inspect each active position $P_i$:
     - Unrealized PnL ($uPnL \ge +1.5R \implies$ runner secured, low risk to replace).
     - Remaining distance to Stop-Loss.
     - Correlation $\rho(P_i, T_{\text{new}})$ (penalize redundant directional crypto exposure).
  3. If $U(T_{\text{new}}) > \min_i U(P_i) + \delta_{\text{friction}}$ AND replacing $P_i$ does not trigger wash sale or risk breaches:
     - Generate a structured `REPLACE_POSITION` intent: atomically market-close $P_i$ at market and execute $T_{\text{new}}$.
  4. If no existing trade is inferior: reject $T_{\text{new}}$ with `OPPORTUNITY_INFERIOR_TO_ACTIVE_PORTFOLIO`.

### Deliverable 3 (P0): $10,000 Portfolio-Level Historical Replay Engine
- **Task:** Build a discrete-event, concurrent multi-asset portfolio simulator (`scripts/research/portfolio_historical_replay.py`).
- **Invariants:**
  - Initial capital: $10,000.00 cash.
  - Feeds: 1-hour and 4-hour historical OHLCV across `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, and `XAUUSD`.
  - Concurrency: Max 3 positions active at any timestamp.
  - Realistic accounting: Deduct 7 bps maker/taker round-trip fee, exit spread, and 8h funding rates.
  - Outputs: Continuous equity curve, max portfolio drawdown, Sharpe/Sortino ratio, daily margin usage, and Ulcer Index.

### Deliverable 4 (P1): BTC, ETH, and GOLD Strategy Filter Validation
- **Task:** Preregister the 4 positive-expectancy strategy families identified in Phase 4 (`Buy Pullback`, `Sell Pullback`, `FVG Retest Buy`, `FVG Retest Sell`) on 1h/4h timeframes.
- **Standard:** Must achieve $\mathbb{E}_{\text{net}} > +0.20\text{R}$ and Deflated Sharpe Ratio (DSR) $> 0.85$ over out-of-sample data under realistic costs.

### Deliverable 5 (P1): Multi-Venue Live Paper Burn-in (Testnet)
- **Task:** Run the decoupled daemon (`RUN_BACKGROUND_DAEMONS=true`) against public Binance and Bybit testnet streams continuously for 168 hours (7 days).
- **Verification:** Log every order intent, tick latency, websocket heartbeat, and risk check to SQLite without human intervention or unhandled exceptions.

### Deliverable 6 (P1): Autonomous Execution Failure Recovery Audit
- **Task:** Verify that network dropouts, exchange 502/429 errors, process SIGKILL, or database locks automatically cause the system to fail closed, cancel outstanding orders, and safely reconcile state upon reboot.

---

## 6. Conclusion & Recommendation

The baseline is established:
- **Core Architecture:** Substantially complete and well-tested.
- **Risk System:** Exceptionally conservative and fail-closed.
- **Trading Edge:** Demonstrated in filtered historical research, but unverified at the concurrent portfolio level.
- **Immediate Action:** **Commit to the Feature Freeze.** Do not add new modules. Proceed systematically through Deliverables 1 through 6.

