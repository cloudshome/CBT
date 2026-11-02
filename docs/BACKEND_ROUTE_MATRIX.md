# SKY / CRYPTO BRAIN TERMINAL (CBT)
## Authoritative Backend Route & Service Ownership Matrix

> **Document Identity:** `SKY-ROUTE-MATRIX-2026`  
> **Status:** AUTHORITATIVE & CONTRACT-VERIFIED  
> **Governing Gate:** `tests/test_proxy_route_contract.py`  
> **Architecture Principle:** Python FastAPI (`http://127.0.0.1:8000`) is the sole authoritative owner of market intelligence, quant models, risk decisioning, and execution ledgers. Node/Express (`http://127.0.0.1:3000`) acts strictly as a bounded legacy fallback and readiness service.

---

## 1. Architectural Routing Topology

```
                      ┌──────────────────────────────────────────┐
                      │    Terminal Web UI / Electron Client     │
                      └────────────────────┬─────────────────────┘
                                           │
                    HTTP /api/*            │ WebSocket /ws/*
                         ▼                 ▼
          ┌────────────────────────────────────────────────────────┐
          │ Reverse Proxy Gateway (Nginx :80 / Caddy / Vite :5173) │
          └───────────┬────────────────────────────────┬───────────┘
                      │                                │
                      │ /api/readiness                 │ All Intelligence, Risk,
                      │ /api/metrics/* (Node)          │ Scanning, Paper, Trade,
                      │                                │ and WebSocket Routes
                      ▼                                ▼
       ┌─────────────────────────────┐  ┌─────────────────────────────┐
       │     NODE / EXPRESS :3000    │  │    PYTHON FASTAPI :8000     │
       │    Bounded Fallback Layer   │  │     Authoritative Core      │
       │  - Readiness health check   │  │  - 12-Stage SMC & Quants    │
       │  - Node process metrics     │  │  - Half-Kelly Risk Gates    │
       │  - Legacy proxy headers     │  │  - Smart Order Routing (SOR)│
       │  - No persistent state      │  │  - SQLite Trading & Brain DB│
       └─────────────────────────────┘  └─────────────────────────────┘
```

---

## 2. Global Route Ownership Matrix

| Route Prefix | Authoritative Service | Auth Type | Primary Side Effect / Persistence | Primary Test Suites |
|---|:---:|:---:|---|---|
| `/api/candles` | Python FastAPI | Public / API Key | In-memory cache, provider failover | `test_market_data.py`, `candles.test.ts` |
| `/api/tickers` | Python FastAPI | Public | Cache refresh, L1 feed ticker stream | `test_market_data.py`, `tickers.test.ts` |
| `/api/mtf` | Python FastAPI | Public | Multi-timeframe trend compilation | `test_sky_intelligence.py`, `desk.test.ts` |
| `/api/scan` | Python FastAPI | Public | Real-time SMC setup candidate scanning | `test_sky_intelligence.py`, `scan.test.ts` |
| `/api/desk` | Python FastAPI | API Key | Institutional desk analytics synthesis | `test_institutional_math_and_learning.py` |
| `/api/paper` | Python FastAPI | API Key | `shadow_positions` in `trading_logs.db` | `test_e2e_critical_path.py`, `paper.test.ts` |
| `/api/institutional` | Python FastAPI | API Key | Risk limits, institutional factor exposures | `test_phase5_strategy_codification.py` |
| `/api/terminal` | Python FastAPI | API Key | Terminal state, auto-pilot configuration | `test_sovereign_master_agent.py` |
| `/api/sky` | Python FastAPI | Public | 12-stage sequential engine evaluation | `test_sky_intelligence.py`, `sky.test.ts` |
| `/api/decision` | Python FastAPI | Public / API Key | Confluence scoring, trade dispatch | `test_sovereign_master_agent.py` |
| `/api/prediction` | Python FastAPI | API Key | `prediction_ledger` in `trading_logs.db` | `test_evidence_grade_research_and_agent.py` |
| `/api/scenarios` | Python FastAPI | API Key | Monte Carlo simulation scenarios | `test_institutional_math_and_learning.py` |
| `/api/path-simulation` | Python FastAPI | API Key | Geometric Brownian Motion path projections | `test_institutional_math_and_learning.py` |
| `/api/shadow` | Python FastAPI | API Key | Shadow paper positions ledger | `test_conditional_allocator.py` |
| `/api/lab` | Python FastAPI | API Key | Sandbox portfolio backtesting | `test_phase5_strategy_codification.py` |
| `/api/governance` | Python FastAPI | API Key | System constitution invariant checks | `test_constitution_compliance.py` |
| `/api/league` | Python FastAPI | Public | Agent performance leaderboard | `test_sovereign_master_agent.py` |
| `/api/command` | Python FastAPI | API Key | Terminal command execution router | `test_terminal_commands.py` |
| `/api/market` | Python FastAPI | Public | Market structure state compilation | `test_market_state.py` |
| `/api/dossier` | Python FastAPI | Public / API Key | 8-Pillar quantitative dossier | `test_sky_intelligence.py`, `dossier.test.ts` |
| `/api/smc` | Python FastAPI | Public | Sweeps, FVGs, Order Blocks, MSS | `test_sky_intelligence.py` |
| `/api/voice` | Python FastAPI | API Key | Natural language voice synthesis | `test_voice_interface.py` |
| `/api/telegram` | Python FastAPI | API Key | Encrypted operational notifications | `test_telegram_bot.py` |
| `/api/ingest` | Python FastAPI | API Key | Historical market tick data ingestion | `test_provenance.py` |
| `/api/strategy` | Python FastAPI | API Key | Strategy registry and parameter updates | `test_phase5_strategy_codification.py` |
| `/api/macro` | Python FastAPI | Public | Gold macro network and yield curves | `test_macro_network.py` |
| `/api/audit` | Python FastAPI | API Key | Execution audit trails, immutable hashes | `test_milestone35_r_independent_audit.py` |
| `/api/microstructure` | Python FastAPI | Public | L2 Order Book Imbalance, OBI, VPIN | `test_microstructure.py` |
| `/api/execution` | Python FastAPI | Certified Gate | Smart Order Routing, TWAP, reconciliation | `scripts/verify_m18_certification.py` |
| `/api/auditor` | Python FastAPI | API Key | Milestone 18/35-R compliance auditor | `test_milestone35_r_independent_audit.py` |
| `/api/burn-in` | Python FastAPI | API Key | Burn-in stress test telemetry | `test_burn_in.py` |
| `/api/telemetry` | Python FastAPI | Public | High-frequency execution telemetry | `test_telemetry.py` |
| `/api/incident` | Python FastAPI | API Key | Incident escalation and dead-man switches | `test_incident_escalation.py` |
| `/api/vault` | Python FastAPI | Hardware Key | Encrypted credential vault (`data/vault.db`)| `test_credential_vault.py` |
| `/api/chart` | Python FastAPI | Public | Lightweight chart candle series feeds | `test_market_data.py` |
| `/api/memory` | Python FastAPI | API Key | `personal_learning_graph` in `brain.db` | `test_knowledge_graph.py` |
| `/api/ai` | Python FastAPI | API Key | Adversarial debate committee, LLM bridge | `test_debate_committee.py` |
| `/api/kronos` | Python FastAPI | API Key | Kronos probabilistic forecast ledger | `test_kronos_engine.py` |
| `/api/collective` | Python FastAPI | API Key | Multi-agent consensus mechanism | `test_collective_intelligence.py` |
| `/api/volatility` | Python FastAPI | Public | Realized vol, Yang-Zhang, Parkinson | `test_volatility_engine.py` |
| `/api/arbitrage` | Python FastAPI | API Key | Triangular & Cross-Exchange arbitrage | `test_arbitrage_engine.py` |
| `/api/mbo` | Python FastAPI | API Key | Market-by-Order L3 depth telemetry | `test_mbo_engine.py` |
| `/api/system` | Python FastAPI | API Key | Hardware metrics, thread pool utilization | `test_system_health.py` |
| `/api/auth` | Python FastAPI | API Key / FIDO2 | FIDO2 WebAuthn & hardware key validation | `test_hardware_key_auth.py` |
| `/api/cexdex` | Python FastAPI | API Key | CEX/DEX arbitrage matrix | `test_cexdex_routes.py` |
| `/api/heatmap` | Python FastAPI | Public | Liquidation heatmap & depth clusters | `test_heatmap_engine.py` |
| `/api/portfolio` | Python FastAPI | API Key | Aggregate risk & dynamic capital allocation| `test_conditional_allocator.py` |
| `/api/strategist` | Python FastAPI | API Key | Autonomous strategy generation | `test_strategist_agent.py` |
| `/api/mastermind` | Python FastAPI | API Key | Mastermind arbiter & trade execution | `test_sovereign_master_agent.py` |
| `/api/screener` | Python FastAPI | Public | Asset universe filtering & sorting | `test_screener.py` |
| `/api/arena` | Python FastAPI | API Key | Live strategy tournament arena | `test_strategy_arena.py` |
| `/api/temporal` | Python FastAPI | API Key | Temporal intelligence & session regimes | `test_temporal_intelligence.py` |
| `/api/central-mind` | Python FastAPI | API Key | Sovereign central trading mind | `test_phase5_strategy_codification.py` |
| `/api/hermes` | Python FastAPI | API Key | Cognitive LLM reasoning bridge | `test_hermes_agent_bridge.py` |
| `/api/risk` | Python FastAPI | Certified Gate | Deterministic Half-Kelly and equity caps | `test_risk_engine.py` |
| `/api/trader` | Python FastAPI | API Key | Manual trade injection & emergency exit | `test_trader_portal.py` |
| `/api/testnet` | Python FastAPI | API Key | Binance/Bybit testnet execution mirror | `test_testnet_gateway.py` |
| `/api/v1` | Python FastAPI | Public / API Key | Versioned public API surface | `test_v1_endpoints.py` |
| `/api/web3` | Python FastAPI | Hardware Key | On-chain EVM wallet & DEX interaction | `test_web3_routes.py` |
| `/api/health` | Python FastAPI | Public | Central engine health & subsystem readiness | `test_system_health.py` |
| `/api/readiness` | Node / Express | Public | Node event-loop readiness check | `tests/readiness.test.ts` |
| `/api/metrics` | Python FastAPI | Prometheus | Authoritative Prometheus metric export | `test_metrics.py` |
| `/ws/*` | Python FastAPI | WebSocket | Sub-second order book, ticks, SMC events | `test_ws_streaming.py` |

---

## 3. Proxy Routing Synchronization Contract

To ensure that development (`vite.config.ts`) and production (`nginx.conf` and `deploy/Caddyfile`) route identical requests to identical backends without configuration drift:

1. **Continuous Automated Verification:**  
   `pytest tests/test_proxy_route_contract.py` executes on every preflight check and CI build.
2. **Fail-Closed Contract:**  
   Any route prefix registered on `app.py` that is missing from `frontend/vite.config.ts` or `frontend/nginx.conf` immediately fails the test gate with an actionable error.
3. **No Hidden Seams:**  
   Node Express only receives `/api/readiness`, `/api/metrics/*` (Node-specific metrics), and strictly labeled legacy fallback traffic with `X-Backend-Service: CTB-Express-Legacy` and `X-Authoritative-Backend: Python-FastAPI` response headers.

