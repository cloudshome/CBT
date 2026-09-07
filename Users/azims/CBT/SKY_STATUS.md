# SKY — Project Status & Agent Handoff Document

> **Last Updated:** 2026-09-07  
> **Release Tag:** `v3.6.0-canary-burn-in-telemetry` (ACTIVE 🚀)  
> **Branch:** `main`  
> **Remote:** `https://github.com/cloudshome/CTB`  
> **Lead Agent:** Antigravity  
> **Repo local path:** `c:\Users\azims\CBT`  
> **Tests Passing:** 464 / 464 (338 Pytest, 126 Jest — 100% passing)  
> **Preflight Status:** ALL QUALITY GATES PASSED (100% GREEN)

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
| *(staged)* | feat(canary): implement live canary shadow burn-in orchestrator, hf telemetry pipeline, and incident escalation (17 passing tests) |
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

## What Was Completed This Session (2026-08-29)

1. **Phase 16 — Live Voice Interface (STT & TTS)**:
   - Upgraded `core/voice_interface.py` with Gemini Multimodal audio transcription and audio MP3 synthesis.
   - Added `POST /api/voice/transcribe` and `POST /api/voice/synthesize` endpoints in `app.py`.
   - Added live microphone recording (STT) and "Read Brief" (TTS) audio synthesis in `frontend/src/components/GeminiDeskCopilot.tsx`.
   - Routed `/api/voice` in `vite.config.ts` and `nginx.conf`.
2. **Phase 17 — Telegram Bot Integration**:
   - Upgraded `core/telegram_bot.py` with interactive command routing (`/status`, `/risk`, `/brief`, `/decision`, `/approve`).
   - Added `POST /api/telegram/webhook`, `POST /api/telegram/broadcast`, and `GET /api/telegram/status` endpoints in `app.py`.
   - Wired live telemetry broadcaster loop to dispatch instant Telegram position alerts on TP/SL hits and circuit breaker triggers.
   - Added quick Telegram broadcast trigger in `frontend/src/components/Header.tsx`.
3. **Continuous Empirical Accumulator & Walk-Forward Validator**:
   - Created `core/empirical_accumulator.py` to continuously replay historical setups across market regimes into SQLite `experiments.db`.
   - Started background accumulator loop in `app.py` startup event.
   - Added `GET /api/lab/empirical-status` endpoint for real-time statistical sample tracking ($N \ge 100$).
4. **Phase 18 — Universal Provenance Engine & Immutable Research Store**:
   - Implemented `core/provenance_engine.py` with SHA-256 cryptographic content hashing and duplicate detection.
   - Added `POST /api/ingest/source`, `GET /api/ingest/provenance`, and `GET /api/ingest/provenance/{source_id}` in `app.py`.
5. **Phase 19 — Formal Strategy Compiler & Genome Validator**:
   - Implemented `core/strategy_compiler.py` with fail-closed validation (`STATUS = NOT_BACKTESTABLE` for underspecified rules).
   - Added `POST /api/strategy/compile` and `GET /api/strategy/genomes` in `app.py`.
   - Wired newly compiled valid strategies into Tier 1 of `core/strategy_league.py`.
6. **Task Board & Test Suite**:
   - Created `TODO.md` as the master single source of truth for ongoing and upcoming prioritized tasks.
   - Added `tests/test_provenance_and_compiler.py` (107 passing tests in pytest).


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

## Next Session Plan & Objectives

Detailed step-by-step tasks and acceptance criteria are documented in [`docs/NEXT_SESSION_PLAN.md`](file:///c:/Users/azims/CBT/docs/NEXT_SESSION_PLAN.md).

### Sprint K-UI Immediate Objectives:
1. **Task K-UI.1:** Add `KRONOS` forecast trajectory path & probability cone overlay to `frontend/src/components/TradingViewChart.tsx`.
2. **Task K-UI.2:** Add live advisory shadow confirmation/divergence pill to `frontend/src/components/RiskFirstOrderDesk.tsx`.
3. **Task K-UI.3:** Setup Vitest + `@testing-library/react` and write frontend component tests in `frontend/src/components/__tests__/`.
4. **Task K-UI.4:** Implement Playwright E2E critical path tests (place trade $\to$ reconcile $\to$ verify risk).
5. **Task K-UI.5:** Compile release scorecard and submit PR to `main`.

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
