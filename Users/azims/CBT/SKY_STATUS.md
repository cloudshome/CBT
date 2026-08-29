# SKY — Project Status & Agent Handoff Document

> **Last Updated:** 2026-08-29  
> **Branch:** `feature/institutional-quant-platform-and-chart-tools`  
> **Remote:** `https://github.com/cloudshome/CTB`  
> **Lead Agent:** Antigravity  
> **Repo local path:** `c:\Users\azims\CBT`

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
│  Port 5173 (dev)      │  Node/Express  → :3001  (market data,     │
│  Port 80 (prod nginx) │                           WS streams,     │
│                       │                           watchlist)       │
│  Vite proxy splits:   │                                           │
│  /api/sky/*  ──────── │→ Python FastAPI → :8000  (SKY intelligence│
│  /api/lab/*  ──────── │→                           pipeline,       │
│  /api/decision/* ───  │→                           backtesting,    │
│  /api/league/* ─────  │→                           risk engine,    │
│  /api/governance/* ── │→                           paper trading)  │
│  /ws/* ────────────── │→ Node/Express :3001 (WebSocket passthrough)│
└───────────────────────┴──────────────────────────────────────────┘
```

**Nginx (production)** splits the same way via `frontend/nginx.conf`.

---

## Current Branch — Recent Commits (newest first)

| Hash | Description |
|------|-------------|
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
| 16 | Live Voice Interface | ❌ NOT STARTED |
| 17 | Telegram Bot Integration | ❌ NOT STARTED (config stub only) |

---

## What Was Fixed This Session (2026-08-29)

1. **XAUUSDT → PAXGUSDT symbol mapping** — added in both `binanceService.ts` and `bybitService.ts` so Gold queries don't fail on exchanges that don't have spot XAUUSDT.
2. **Hardcoded OBI port** — `app.py` `/api/stream/obi` endpoint was using hardcoded port; fixed to use `data_streamer.get_order_book()` async call.
3. **Hardcoded Gemini model name** — `.env.example` updated with correct model identifier.
4. **Vite dev proxy split** — `frontend/vite.config.ts` updated to route Python-only paths to `:8000`.
5. **Nginx production proxy split** — `frontend/nginx.conf` updated to match.
6. **api.ts 15 new endpoints** — All Python FastAPI endpoints now have typed TypeScript wrappers in `frontend/src/services/api.ts`:
   - `getSKYDecision`, `getSKYStatistics`
   - `getDecisionCouncil`
   - `getOrderBookImbalance`, `getMarketDepth`
   - `getMarketRegime`
   - `getExpectancyReport`
   - `startPaperSession`, `getPaperSessionStatus`, `stopPaperSession`
   - `getSystemHealth`, `getPreflight`
   - `runBacktest`, `runWalkForward`, `runStressTest`
   - `getStrategyLeaderboard`, `getGovernanceProposals`

---

## What Remains — Prioritized TODO

### P0 — Correctness / Integrity
- [ ] Run `npm test` in `frontend/` — verify no regressions in api.ts expansion
- [ ] Run `python -m pytest` in repo root — verify `app.py` routes are healthy

### P1 — Core Trading Intelligence
- [ ] Accumulate real historical backtest data (currently engine exists but sample sizes are small — label "NOT YET VALIDATED" on all strategy stats until N≥100 trades per regime)
- [ ] Connect `core/regime_conditional_calibrator.py` output live to the frontend regime pill

### P2 — Validation / Backtesting / Risk
- [ ] Walk-forward validation runner — need a scheduled job (e.g., nightly) to keep expectancy fresh
- [ ] Out-of-sample test window freeze — ensure train/validate/test splits are locked before any strategy is reported as "VALIDATED"

### P3 — Reliability / Performance
- [ ] WebSocket auto-reconnect test under network interruption
- [ ] Memory leak audit on 24/7 Node WS streams (order book, ticker)
- [ ] Python backend health check / liveness probe in docker-compose

### P4 — UX
- [ ] Write `SKY_STATUS.md` (this file ✅) and pin to repo root
- [ ] Voice interface (Phase 16) — design spec not yet written
- [ ] Telegram bot (Phase 17) — config stub exists in `.env.example`

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
npm run dev             # Node backend :3001
cd frontend && npm run dev  # Vite :5173 (with split proxy)
python app.py           # Python FastAPI :8000

# 4b. Production (Docker)
docker-compose up --build
```

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
