# SKY — Project Status & Agent Handoff Document

> **Last Updated:** 2026-09-20  
> **Release Tag:** `v5.2.0-grade-e3-l2-reality-engine` (ACTIVE 🚀)  
> **Branch:** `main`  
> **Remote:** `https://github.com/cloudshome/CTB.git`  
> **Lead Agent:** Antigravity  
> **Repo local path:** `c:\Users\azims\CBT`  
> **Tests Passing:** 1,338 / 1,338 (1,191 Pytest, 147 Jest — 100% passing)  
> **Milestone 18 Status:** PRODUCTION PASS (Certified & Active — 149/149 Tests)  
> **Milestone 19 Status:** COMPLETED & VERIFIED (Cloud KMS Enclave, SOR Benchmarking & WS Reconciliation)  
> **Grade-E3 Status:** COMPLETED & CERTIFIED (High-Frequency L2 Empirical Reality Engine & Tamper-Evident Provenance — 35/35 Tests)  
> **Preflight Status:** ALL 7 QUALITY GATES PASSED (100% GREEN)

---

## ⚠️ READ FIRST — MANDATORY FOR ALL AGENTS

Before making ANY change to this repo, you MUST read `AGENTS.md` in the repo root.
It defines the 34-point project operating manual including the Golden Rule, Conflict Protocol,
the trading logic pipeline, no-lookahead-bias rule, and agent roles.

---

## Project Mission

SKY is a **professional cryptocurrency market-intelligence and trading decision-support system**.

It is NOT a trading bot. It is a statistical evidence engine. The goal is to determine whether a
trading idea has genuine statistical edge — before any live capital is committed.

Architecture priority:
```
DATA QUALITY > RISK > EXECUTION SAFETY > STATISTICAL VALIDITY > SIGNAL QUALITY > UX
```

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     SKY SYSTEM ARCHITECTURE                       │
├───────────────────────┬──────────────────────────────────────────┤
│  FRONTEND             │  BACKENDS                                 │
│  React + Vite         │                                           │
│  Port 5173 (dev)      │  Node/Express  → :3000  (market data,     │
│  Port 80 (prod nginx) │                           WS streams,     │
│                       │                           watchlist)       │
│  Vite proxy splits:   │                                           │
│  /api/sky/*  ──────── │→ Python FastAPI → :8000  (SKY intelligence│
│  /api/lab/*  ──────── │→                           pipeline,       │
│  /api/decision/* ───  │→                           backtesting,    │
│  /api/league/* ─────  │→                           risk engine,    │
│  /api/governance/* ── │→                           paper trading)  │
│  /ws/* ────────────── │→ Node/Express :3000 (WebSocket passthrough)│
└───────────────────────┴──────────────────────────────────────────┘
```

**Nginx (production)** splits the same way via `frontend/nginx.conf`.

---

## Current Branch — Recent Commits (newest first)

| Hash | Description |
|------|-------------|
| `adc1b2e` | feat(grade-e3): implement institutional deployment framework and L2 reality engine (35 passing tests) |
| `7b4835f` | fix(ci): track manifest_k9.json in git and add fallback path to fix CI test discovery |
| `15f7d47` | feat(provenance): harden StrategyRealityBridge with ProvenanceAuthority and specify Grade-E3 (9 passing tests) |
| `518326b` | feat(m19): implement KMS enclave, WS fill stream, strategy reality bridge, and JIT benchmarks (21 passing tests) |
| `b34fdd4` | feat(grade-e2): implement toxic flow defense, volatility gating and adaptive pegging (25 passing tests) |
| `9b6172a` | feat(grade-e1): implement institutional maker execution reality engine and empirical matrix (19 passing tests) |
| `d353931` | fix(audit): add REPO_ROOT to sys.path in verify_k10_m19_prerequisites |
| `bff5b16` | feat(k10-m19): implement dynamic calibration, cost policy, maker simulation, KMS zeroization, and SOR benchmarks (37 passing gates) |
| `c738d8f` | Merge pull request #49 from cloudshome/arena/01a07d0a-ctb (clear ruff debt in M17 execution/auth/vault) |
| `8ecae25` | docs(pipeline): update SKY_STATUS, roadmap, and next session plan to v3.7.0 and Milestone 18 |
| `d41fa1b` | Merge remote-tracking branch 'origin/main' into main |
| `33417b4` | fix(execution): enforce 1.5% single-trade risk ceiling and dynamic clock drift validation (29 passing tests) |
| `3d50dda` | feat(execution): implement live exchange execution router, aes-256-gcm vault, and hmac signers (26 passing tests) |
| `2b4136f` | feat(canary): implement live canary shadow burn-in orchestrator, hf telemetry pipeline, and incident escalation (17 passing tests) |
| `0084d7e` | docs(status): update SKY_STATUS to v3.5.0 with 447 passing tests and recent commit history |
| `5991e82` | feat(core): implement autonomous trader, memory cache hardening, and capacity audit report (18 passing tests) |
| `934ef80` | feat(youtube): implement YouTube Research Intelligence V5 autonomous channel & playlist explorer (15 passing tests) |
| `7629c94` | feat(telegram-v5): complete hardened mobile control plane, rbac, 2-phase execution, and emergency controls (35 passing tests) |
| `60d981e` | feat(telegram): implement automated research dispatch and two-way reverse flow for links, images, and documents (7 passing tests) |
| `f2f6a09` | feat(research): add youtube and multi-source summary synthesis and telegram summary dispatch (5 passing tests) |
| `b3ac91d` | feat(research-desk): add scanned pdf vision ocr, literature summary reading section, and half-kelly paper execution rules (32 passing tests) |
| `4bc9c29` | fix(api): fallback to recent candle close in orderbook imbalance when live depth unavailable |
| `2c983bd` | feat(evidence-integrity): seal cold-start risk authorization and purge fake strategy league track records (260 passing tests) |
| `e3a9519` | Fix dynamic live price liquidation clusters strictly relative to current price (228 passing tests) |
| `dfadbf6` | Implement P7.2 Performance Profiler, P8.1 Staging Burn-In, and P8.2 Production Overrides (227 passing tests) |
| `2e283df` | Implement P6.2 Strategy League Evaluator and P7.4 API & Environment docs (224 passing tests) |
| `6fa6bac` | Implement P6.4 Monte Carlo 10k-path stress tester and P7.3 deterministic intelligence fallback (223 passing tests) |
| `0a6eea4` | Implement P6.1 Empirical Evidence Accumulator and P7.1 Production Operations Runbook (220 passing tests) |
| `8df7839` | Implement P5.2 WebSocket lifecycle state machine and P5.3 SQLite database VACUUM maintenance (218 passing tests) |
| `86da62f` | Implement P4.4 Prometheus metrics, P4.5 CI/CD enhancement, and P5.1 Exchange circuit breakers (216 passing tests) |
| `6e51d7b` | Implement P3.3 dual-tier rate limiter, P4.1 Docker hardening, P4.2 online SQLite backups, and P4.3 Nginx OWASP headers (209 passing tests) |
| `8e905e6` | Implement P3.1 API key auth and P3.2 CORS hardening across Express, FastAPI, and frontend client (198 passing tests) |
| `c2ac396` | Fix flaky expectancy_r test assertion, bump @google/genai to 2.19.0, add P3-P8 production roadmap to TODO.md (187 passing tests) |
| `e6b396b` | Implement universal provenance engine, strategy genome compiler, gold macro layer, loss autopsy hook, and 24/7 deployment healthchecks (115 passing tests) |
| `129c337` | Complete TradingView obsidian terminal theme with granular timeframes, dynamic legend, countdown timer, magnet snap, time range bar, snapshot tool |
| `354c517` | Wire Python FastAPI to frontend; fix XAUUSDT→PAXGUSDT; fix OBI port; expand api.ts with 15 Python endpoints |
| `e9be8ef` | Implement 4 Cross-Cutting Governance Control Planes; fix 4H/1D candle multi-timeframe streams |
| `c347505` | Implement 8-Pillar Live Asset Intelligence Dossier Matrix |
| `35286f9` | Implement authentic live 24hr market ticker stream + REST fallback |
| `1554bc3` | Prioritize Core Triad (BTC, ETH, GOLD/PAXG) in Watchlist, Header, WebSocket |
| `64f775f` | Zero-Shake Realtime Architecture, long-lived chart instance, Dev Diagnostic HUD |
| `5163fc6` | 6 Hedge-Fund Brain Quant Engines (Adversarial Debate, Whale Radar, Monte Carlo 10k, etc.) |
| `21781c7` | TradingView Left Vertical Drawing Toolbar, 1000-candle deep backfill |

---

## File Map — Key Files

### Frontend (`frontend/src/`)
| File | Purpose |
|------|---------|
| `frontend/src/services/api.ts` | All HTTP calls to both backends. Node routes + 15 Python FastAPI routes. |
| `frontend/src/App.tsx` | Root. Long-lived chart instance, Zero-Shake realtime, Dev HUD. |
| `frontend/src/components/` | All UI panels (Dossier, Governance, Quant engines, etc.) |
| `frontend/vite.config.ts` | Dev proxy split: `/api/sky*`, `/api/lab*`, `/api/decision*` → :8000; `/api*`, `/ws*` → :3001 |
| `frontend/nginx.conf` | Production proxy split (same logic as vite.config.ts) |

### Node Backend (`src/`)
| File | Purpose |
|------|---------|
| `src/server.ts` | Express entry point, WS manager, all Node routes |
| `src/services/marketDataService.ts` | OHLCV data, candle streams, multi-TF fetch |
| `src/services/binanceService.ts` | Binance REST candles (XAUUSDT→PAXGUSDT mapping) |
| `src/services/bybitService.ts` | Bybit REST candles (same mapping) |
| `src/middleware/rateLimit.ts` | Rate limiting / risk gate |
| `src/routes/paper.ts` | Paper trading routes (isolated from live) |

### Python Backend (`core/` + `app.py`)
| File | Purpose |
|------|---------|
| `app.py` | FastAPI entry. Hosts all /api/sky/*, /api/lab/*, /api/decision/*, /api/league/*, /api/governance/* |
| `core/sky_intelligence/` | 12-stage SKY Market Intelligence pipeline |
| `core/expectancy_engine.py` | Empirical expectancy from historical setups |
| `core/backtest/` | Purged walk-forward backtesting engine |
| `core/market_path_simulator.py` | Monte Carlo 10k path stress test |
| `core/risk_engine/` | Risk gate — no signal bypasses this |
| `core/execution_engine/` | Paper trading execution (isolated) |
| `core/data_sources/` | Exchange adapters (ccxt-based) |
| `core/market_db.py` | SQLite/Postgres market data store |
| `core/data_integrity.py` | Data quality validator |
| `core/regime_conditional_calibrator.py` | Regime classification + expectancy calibration |
| `core/institutional_alpha.py` | Institutional alpha layer |
| `core/data_streamer.py` | Real-time L2 order book streamer |

### Config / Infra
| File | Purpose |
|------|---------|
| `prisma/schema.prisma` | Database schema |
| `docker-compose.yml` | 3-service compose: frontend, node-backend, python-backend |
| `.env.example` | Environment template (copy to `.env`, fill secrets) |
| `AGENTS.md` | **34-point operating manual — MUST READ before any change** |

---

## 17-Phase SKY Roadmap — Completion Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Market Data Infrastructure | ✅ DONE |
| 2 | Market Structure Analysis | ✅ DONE |
| 3 | Liquidity & Volatility Analytics | ✅ DONE |
| 4 | Volume & Order Flow | ✅ DONE |
| 5 | Multi-Timeframe Framework | ✅ DONE |
| 6 | Market Regime Detection | ✅ DONE |
| 7 | Trading Setup Identification | ✅ DONE (hypotheses only — not validated) |
| 8 | Backtesting Engine | ✅ DONE (purged walk-forward in `core/backtest/`) |
| 9 | Expectancy Measurement | ✅ DONE (empirical, `core/expectancy_engine.py`) |
| 10 | Out-of-Sample Validation | ✅ DONE (walk-forward) |
| 11 | Paper Trading | ✅ DONE (`core/execution_engine/`, isolated) |
| 12 | Risk Controls | ✅ DONE (`core/risk_engine/` — no bypass allowed) |
| 13 | Adversarial Debate Intelligence | ✅ DONE (council endpoint in `app.py`) |
| 14 | Quant Brain Engines (6x) | ✅ DONE (Whale Radar, Monte Carlo, Lead-Lag, etc.) |
| 15 | Governance Control Planes (4x) | ✅ DONE (circuit breakers, position limits, etc.) |
| 16 | Live Voice Interface | ✅ DONE (STT voice notes, command parser, TTS speech synthesis) |
| 17 | Telegram Bot Integration | ✅ DONE (webhook router, broadcast alerts, TP/SL telemetry alerts) |

---

## What Was Completed This Session (2026-09-07)

1. **Milestone 17 — Live Exchange Execution & Private API Credential Vault (Class H)**:
   - Built `core/auth/credential_vault.py`: AES-256-GCM AEAD encryption with PBKDF2 key derivation (600,000 rounds) and zero-leakage secret sanitizer.
   - Built `core/auth/exchange_signers.py`: Deterministic HMAC-SHA256 request signers for Binance v3 and Bybit V5 with strict millisecond timestamps and $\le 1000$ms clock drift protection.
   - Built `core/execution/kill_switch.py`: Durable fail-closed master kill switch with SQLite WAL persistence and strict boolean parsing.
   - Built `core/execution/idempotency.py`: Atomic SQLite WAL reservation ledger with ambiguous order state machine and reconciliation protection.
   - Built `core/execution/connectors/`: Abstract base and concrete Binance and Bybit live connectors with sub-millisecond latency telemetry.
   - Built `core/execution/live_router.py`: 20 pre-trade validation gates preceding network dispatch.
   - Registered 8 REST endpoints in `app.py` with reverse proxy routes in `frontend/vite.config.ts` and `frontend/nginx.conf`.
2. **Milestone 17.1 — Boss-Level Remediation & Adversarial Re-Audit (FAIL → PASS)**:
   - Remediated M17.1-FINDING-01: Clamped `core/half_kelly_sizer.py` risk ceiling from 2.5% down to constitutional 1.5% and added independent Gate 12 in `LiveExecutionRouter` enforcing $|P_{\text{entry}} - P_{\text{stop}}| \times Q \le \text{Equity} \times 0.015 (+ 10^{-6})$.
   - Remediated M17.1-FINDING-02: Implemented dynamic clock drift verification in Gate 3 & Gate 17 ($|t_{\text{local}} - t_{\text{ref}}| \le 1000\text{ms}$) with fail-closed semantics if reference is required but unavailable.
   - Remediated M17.1-FINDING-03: Formally minted and verified Git release tag `v3.7.0-live-execution-vault`.
   - Expanded adversarial test suite to 29 tests covering 11 risk cases and 7 clock drift cases with zero network calls on all rejections.
   - Full repository test pass: **493 / 493 tests passing (367 Pytest + 126 Jest — 100% Green)**.
   - Verified clean preflight scorecard: ALL 4 QUALITY GATES PASSED.
3. **Remote Main Reconciliation**:
   - Reconciled with `origin/main` via clean git merge (0 conflicts).

---

## How to Run SKY Locally

```bash
# 1. Copy env
cp .env.example .env
# Fill in: BINANCE_API_KEY, BYBIT_API_KEY, GEMINI_API_KEY, etc.

# 2. Install Node deps
npm install
cd frontend && npm install && cd ..

# 3. Install Python deps
pip install -r requirements.txt

# 4a. Dev mode (3 terminals)
npm run dev             # Node backend :3000
npm --prefix frontend run dev  # Vite :5173
.venv\Scripts\uvicorn app:app --host 0.0.0.0 --port 8000  # Python FastAPI :8000

# 4b. Production (Docker)
docker-compose up --build
```

---

## Milestone 18: Multi-Venue Smart Execution & High-Resolution Fill Reconciliation — PRODUCTION PASS ✅

Milestone 18 has been audited and remediated under the Boss-Level Adversarial Directive. It is certified **PRODUCTION PASS** via [`docs/audits/M18_BOSS_LEVEL_AUDIT.md`](file:///c:/Users/azims/CBT/docs/audits/M18_BOSS_LEVEL_AUDIT.md).

### Completed & Hardened Deliverables:
1. **Task 18.1:** Real-Time Multi-Venue Smart Order Routing (SOR) between Binance Spot and Bybit V5 with automated liquidity splits, venue constraints (min notional $5.00), and parent-level 1.5% equity risk cap enforcement.
2. **Task 18.2:** Almgren-Chriss Optimal Execution Slicer with finite parameter validation and proven quantity conservation ($\sum n_j == X$).
3. **Task 18.3:** High-Resolution Fill Reconciliation Ledger (`execution_reconciliation_records`) with monotonic nanosecond durations (`time.monotonic_ns()`), SQLite unique composite index deduplication, out-of-order partial fill replay, and overfill circuit breaker.
4. **Task 18.4:** Production Live-Order Terminal UI Controls in `frontend/src/components/RiskFirstOrderDesk.tsx` (Live toggle behind dual-confirmation modal).
5. **Task 18.5:** Dedicated 10-Category Boss-Level Adversarial Test Suite (`tests/test_milestone18_boss_adversarial.py`, 83 passing tests) and Preflight Suite passing all 4 gates (603 total tests passing).

---

## Grade-E3: High-Frequency L2 Empirical Reality Engine — COMPLETED & CERTIFIED ✅

Grade-E3 has been implemented, validated, and audited under the Master Antigravity Directive. It establishes institutional Level 2 empirical microstructure research capabilities with cryptographic tamper-evident bundles and strict capital isolation.

### Completed & Hardened Deliverables:
1. **L2 Empirical Data Reconstruction & Ingestor:** Monotonic sequence-gap detection (`pu == u_prev`), out-of-order/clock regression detection, reconnect boundary handling, and SHA-256 raw payload provenance.
2. **Reconstructed Orderbook Invariants:** Strict bid < ask validation with `raise_on_crossed` enforcement, zero-quantity level removal, micro-price calculation, and replay determinism.
3. **Queue & Latency Physics Simulation:** Q1 (Pessimistic FIFO), Q2 (Empirical Volume Proportion), and Q3 (Uncalibrated Queue/Fallback with uncertainty penalty); realistic cancellation latency racing with in-flight fills.
4. **Markout & Winner's Curse Estimators:** Multi-horizon (100ms, 1s, 5s, 30s, 5m) mid/micro/executable markouts, unconditional drift benchmarking, and Winner's Curse bias quantification ($E[\Delta M_{fill}] - E[\Delta M_{all}]$).
5. **StrategyRealityBridge & Provenance Integration:** Cryptographic evidence bundles (`bundle_btc_l2.json`, `bundle_eth_l2.json`, `bundle_sol_l2.json`) validated via `ProvenanceAuthority.verify_l2_bundle` and mounted via `GradeE3RealityAdapter`.
6. **Permanent Research-Only Firewall:** `is_tradeable(profile)` hardcoded to `False`. Pure mathematical and empirical separation guarantees Grade-E3 profiles can never authorize live capital deployment.
7. **Adversarial & Regression Test Coverage:** 35/35 passing Grade-E3 tests (`tests/research/grade_e3/`) covering data integrity, queue mechanics, markout science, bridge integration, and architectural isolation.

---

## Agent Roles

| Agent | Role | Branching Convention |
|-------|------|---------------------|
| Antigravity | Senior Architect / Lead Engineer / Technical Guardian | `feature/<short>` |
| Copilot | Interactive orchestrator | — |
| Jules | CI / bounded task worker | `jules/<short>` |
| AI Studio | Prototyping | `ai/<short>-prototype` |

---

## Notes for Next Agent

- **Never** add a second data pipeline. Extend the existing one.
- **Never** hardcode exchange symbols — use the symbol mapping layer.
- **Never** bypass `core/risk_engine/`. Risk has architecture priority.
- **Never** call a strategy "VALIDATED" without N≥100 trades per regime with out-of-sample confirmation.
- **Never** expose API keys in committed code.
- The UI follows Zero-Shake Realtime Architecture — do NOT recreate chart instances on data refresh. See `AGENTS.md` §20.
- All research features must follow the **Spec First — Evidence First — Code Second** protocol in `AGENTS.md` §35.
