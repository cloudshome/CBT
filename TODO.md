# SKY / ORION — MASTER TASK BOARD & ROADMAP

> **Purpose:** Single source of truth for ongoing work, completed milestones, and upcoming technical deliverables.  
> **Rule for all AI agents:** When starting any new session, read this file and `AGENTS.md` before planning work. Update this file as tasks are started, completed, or refined.

---

## 🧭 System Core Architecture & Design Decisions

### What We Enforce
1. **Deterministic Core:** Position sizing, stop-loss calculation, daily loss limits, portfolio heat, and hard kill switches are 100% deterministic Python code. AI never places unrestricted orders.
2. **AI Role:** Discovery, hypothesis generation, classification, multimodal extraction, and natural language explanation.
3. **Evidence-Driven Progression:**
   $$\text{Idea} \longrightarrow \text{Formalized} \longrightarrow \text{Backtested} \longrightarrow \text{Out-of-Sample (OOS)} \longrightarrow \text{Paper Trading} \longrightarrow \text{Human Approval} \longrightarrow \text{Live}$$
4. **Mandatory Provenance:** Every external source (URL, PDF, YouTube transcript, image, audio) is cryptographically hashed and indexed with source metadata.
5. **Zero-Shake UI:** Persistent chart instances with incremental WebSocket bar updates — zero full-page flickering or chart remounts.

### What We Reject / Defer
* ❌ Scraping private social platforms (TikTok / Instagram / Facebook private endpoints) without official APIs.
* ❌ Silently updating strategy parameters after a single losing trade without post-trade autopsy and walk-forward verification.
* ❌ Fabricating backtest win rates or using in-sample overfitted indicators without out-of-sample confirmation.

---

## 📊 Phase-by-Phase Task Tracker

### ✅ Completed Milestones
- [x] **Phase 1: Multi-Provider Market Data Infrastructure** (Binance, Bybit, Coinbase REST & WS feeds, XAU/PAXG synthetic mapping) — `core/market_providers.py`, `core/data_sources/`
- [x] **Phase 2: Market Structure & Institutional Alpha Engine** (SMC Swing Points, Fair Value Gaps, Order Blocks, Liquidity Sweeps, CVD Absorption) — `core/smc_engine.py`, `core/institutional_alpha.py`
- [x] **Phase 3: Multi-Timeframe Matrix & Market Regime Engine** (1m, 5m, 15m, 1h, 4h, 1d regime classifier: Trending Bull/Bear, Mean Reverting, Volatility Expansion) — `core/regime_transition.py`, `core/market_state.py`
- [x] **Phase 4: Risk Desk & Governance Control Planes** (Deterministic Half-Kelly position sizing, VaR, portfolio correlation matrix, hard circuit breakers) — `core/risk_engine/`, `core/governance/`
- [x] **Phase 5: Purged Walk-Forward Backtester & Monte Carlo 10k Path Simulator** — `core/backtest/`, `core/path_simulator.py`, `core/monte_carlo_stress.py`
- [x] **Phase 6: 4-Tier Strategy Quarantine League** (Tier 1 Smoke $\to$ Tier 2 Preliminary $\to$ Tier 3 Robust $\to$ Tier 4 Production League) — `core/strategy_league.py`
- [x] **Phase 7: Continuous Empirical Accumulator** (Autonomous background replay into SQLite `experiments.db`) — `core/empirical_accumulator.py`
- [x] **Phase 8: Multi-Agent Quant Debate & Adversarial Committee** — `core/debate_committee.py`
- [x] **Phase 9: Post-Trade Loss Autopsy & Performance Attribution** (Good Loss, Bad Loss, Rule Violation, Regime Mismatch) — `core/loss_autopsy.py`
- [x] **Phase 10: Live Multimodal Voice Interface (STT & TTS)** (Gemini Multimodal voice notes + speech synthesis) — `core/voice_interface.py`
- [x] **Phase 11: Telegram Sentinel Bot** (Interactive commands, broadcast alerts, TP/SL telemetry triggers) — `core/telegram_bot.py`
- [x] **Phase 12: Zero-Shake TradingView Obsidian Terminal** (Lightweight Charts v4, drawing tools, live ticker stream, dev diagnostic HUD) — `frontend/src/`
- [x] **Phase 13: 100-Test Automated Pytest Suite** (100% passing test suite across all subsystems) — `tests/`

---

## 🎯 Active & Upcoming Todo List

### Priority 0 (P0) — Immediate Core Deliverables (COMPLETED)
- [x] **P0.1: Universal Provenance & Ingestion Store (`core/provenance_engine.py`)**
  - Cryptographic SHA-256 content hashing, source metadata tracking, and tamper-proof storage in `provenance_records`.
  - Supports URLs, PDFs, Markdown, text, audio transcripts, and YouTube sources with duplicate detection.
  - Exposed `POST /api/ingest/source`, `GET /api/ingest/provenance`, `GET /api/ingest/provenance/{source_id}`.
- [x] **P0.2: Formal Strategy Compiler & Genome Validator (`core/strategy_compiler.py`)**
  - Converts natural language / extracted hypotheses into deterministic `CompiledStrategy` definitions.
  - Enforces explicit definitions (timeframes, entry triggers, mandatory invalidation levels, regime exclusions).
  - Explicitly flags incomplete / vague strategies as `STATUS = NOT_BACKTESTABLE`.
  - Exposed `POST /api/strategy/compile` and `GET /api/strategy/genomes`.
  - Tested in `tests/test_provenance_and_compiler.py` (7 tests, 107/107 total test suite passing).

### Priority 1 (P1) — Advanced Institutional Integrations (COMPLETED)
- [x] **P1.1: Automated Post-Trade Autopsy Pipeline Hook (`core/portfolio_shadow.py` $\to$ `core/loss_autopsy.py`)**
  - Automatically triggers 11-category root cause forensic autopsy on every negative PnL position closure.
  - Automatically registers `LOSS_AUTOPSY` and `TRADE_CLOSED` events into the `system_audit_events` database.
- [x] **P1.2: Dedicated XAUUSD & PAXG Macro Intelligence Layer (`core/macro_gold_engine.py`)**
  - Tracks US 10Y Real Yield sensitivity (TIPS curve inverted beta), DXY rolling correlation, and London Bullion Fixing windows (10:30 UTC & 15:00 UTC LBMA Fixings, 13:20 Comex Pit Open).
  - Evaluates PAXG synthetic backing basis dislocation.
  - Exposed `GET /api/macro/gold`.
- [x] **P1.3: Immutable Audit Bus & Incident Replay Ledger (`core/audit_bus.py`)**
  - Captures every critical system decision, signal rejection, and risk event with in-memory ring buffer and SQLite persistence.
  - Exposed `GET /api/audit/events`.
  - Tested in `tests/test_gold_macro_and_autopsy_bus.py` (5 tests, 112/112 total test suite passing).


### Priority 2 (P2) — System Hardening & Production Deployment (COMPLETED)
- [x] **P2.1: Database Engine Telemetry & Dual Dialect Support (`core/database.py`)**
  - Added `get_engine_info()` reporting active database dialect (`SQLITE_WAL` vs `POSTGRESQL`), file sizes, and schema version.
- [x] **P2.2: 24/7 Ubuntu Systemd Service & Health Probe Scripts (`deploy/`)**
  - Created `deploy/systemd/orion.service` with automatic restart, memory limits (3.5GB), and file descriptor limits (65536).
  - Created `deploy/healthcheck.sh` verifying API `/health`, empirical accumulator, audit bus, and storage directory.
  - Added `/health` and `/ready` route aliases in `app.py`.
  - Tested in `tests/test_health_and_deployment.py` (3 tests, 115/115 total test suite passing).

### Priority 3 (P3) — Production Readiness: Security & Authentication
- [x] **P3.1: API Authentication Layer (`src/middleware/apiKeyAuth.ts`, `core/auth.py`)**
  - Constant-time timing-safe API key authentication middleware supporting `Authorization: Bearer <key>` and `X-API-Key: <key>`.
  - Applied across all sensitive endpoints on Express (`/api/paper`, `/api/desk`, `/api/institutional`) and FastAPI (shadow execution, governance reload, backtest/lab, voice transcription/synthesis, telegram broadcast, source ingestion, strategy compiler).
  - Dev-friendly passthrough when `API_KEY` is not set; strict 401/403 enforcement when `API_KEY` is configured.
  - Frontend client `api.ts` updated with `authFetch`, `setApiKey()`, and `getApiKey()` with `localStorage` and `VITE_API_KEY` support.
  - Tested in `tests/auth.test.ts` (8 tests) and `tests/test_auth_guard.py` (3 tests). Total tests: 198/198 passing.
- [x] **P3.2: CORS & Header Hardening (`src/server.ts`, `app.py`)**
  - Restricted origins in production via `CORS_ORIGIN` env var with wildcard dev fallback.
  - Explicitly whitelisted HTTP methods (`GET, POST, PUT, DELETE, OPTIONS`) and headers (`Content-Type, Authorization, X-API-Key`).
- [x] **P3.3: Rate Limiting Enhancement (`src/middleware/rateLimit.ts`, `core/rate_limiter.py`)**
  - Implemented dual-tier sliding-window rate limiting on both Express and FastAPI backends.
  - Authenticated API keys receive higher quota (180 req/min) vs public IPs (60 req/min) with SHA-256 key hashing.
  - Automatically injects standard RFC headers (`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, `Retry-After`).
  - Background auto-pruning timer with `.unref()` preventing unbounded Map memory leaks and test hanging.
  - Tested in `tests/rateLimit.test.ts` (4 tests) and `tests/test_rate_limiter.py` (4 tests). Total tests: 209/209 passing.

### Priority 4 (P4) — Production Readiness: Infrastructure & Deployment
- [x] **P4.1: Docker Production Hardening (`docker-compose.yml`)**
  - Health checks configured across all 3 tiers (Python FastAPI, Node Express, and Nginx).
  - CPU and Memory limits applied under `deploy.resources` (Python: 2.0 CPU / 3GB RAM, Node: 1.5 CPU / 1.5GB RAM, Nginx: 1.0 CPU / 512MB RAM).
  - Docker JSON logging driver with size limits (`max-size: 20m`, `max-file: 5`) and `restart: unless-stopped`.
- [x] **P4.2: Persistent Storage & Online Database Backups (`deploy/backup_databases.py`, `deploy/backup_databases.sh`)**
  - Online non-blocking SQLite snapshotting via official SQLite backup API (`source.backup(dest)`).
  - Automated `.tar.gz` compression and 14-day rolling retention pruning.
  - Tested in `tests/test_backup_tool.py` (3 tests).
- [x] **P4.3: Reverse Proxy & Security Headers (`frontend/nginx.conf`)**
  - Configured OWASP-recommended security headers (`X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`).
  - Full reverse-proxy routing matrix for all 20+ Python FastAPI endpoints (`/api/sky/`, `/api/decision/`, `/api/ingest/`, `/api/strategy/`, `/api/macro/`, `/api/audit/`, `/api/chart/`, `/ws/`).
- [x] **P4.4: Prometheus Metrics & Observability (`src/routes/metrics.ts`, `core/metrics.py`)**
  - Standard Prometheus `/metrics` plaintext endpoints on both Express (`:3000/metrics`) and FastAPI (`:8000/metrics` & `:8000/api/metrics`).
  - Exposes runtime heap/RSS memory, uptime, active shadow positions, database storage MB, and exchange circuit breaker states.
  - Added JSON diagnostic summary endpoint at `GET /api/metrics/json`.
  - Tested in `tests/metrics.test.ts` (2 tests) and `tests/test_metrics.py` (2 tests).
- [x] **P4.5: CI/CD Pipeline Enhancement (`.github/workflows/ci.yml`)**
  - Automated multi-tier verification on push/PR for `main`, `feature/**`, and `fix/**` branches.
  - Automated Prisma schema validation, Jest coverage tests, Pytest suite, ESLint, and full production build (`npm run build`).

### Priority 5 (P5) — Production Readiness: Data Reliability
- [x] **P5.1: Market Data Resilience & Exchange Circuit Breakers (`src/utils/circuitBreaker.ts`, `src/services/marketDataService.ts`)**
  - 3-state resilient circuit breaker (`CLOSED` -> `OPEN` -> `HALF_OPEN`) for Binance and Bybit REST endpoints.
  - Fast-fails during external API rate limiting (HTTP 429) or outages, falling back to next tier instantly without waiting for network timeouts.
  - Automatic cooldown and half-open canary probe recovery.
  - Tested in `tests/circuitBreaker.test.ts` (3 tests). Total tests: 216/216 passing.
- [x] **P5.2: WebSocket Lifecycle State Machine (`frontend/src/data/providers/wsStateMachine.ts`, `frontend/src/data/providers/marketProvider.ts`)**
  - Formalized connection state machine (`IDLE` -> `CONNECTING` -> `CONNECTED` -> `RECONNECTING` -> `DISCONNECTED` -> `ERROR`).
  - Exponential backoff with randomized jitter avoiding thundering herd reconnect storms.
  - Heartbeat staleness watchdog detecting silent TCP connection drops.
  - State listeners enabling observable UI status HUDs.
- [x] **P5.3: Database Growth Management & VACUUM Maintenance (`deploy/db_maintenance.py`)**
  - Automated SQLite `PRAGMA optimize`, `REINDEX`, integrity checking, and `VACUUM` disk space reclamation across all production databases (`market.db`, `dev.db`, `experiments.db`, `brain.db`, `trading_logs.db`, `system_audit.db`).
  - Storage footprint reporting and unused space reclamation.
  - Tested in `tests/test_db_maintenance.py` (2 tests). Total tests: 218/218 passing.

### Priority 6 (P6) — Quantitative Engine Validation
- [x] **P6.1: Empirical Evidence Collection & Batch Accumulation (`scripts/run_empirical_accumulation.py`)**
  - Batch walk-forward simulation across BTC/USDT, ETH/USDT, and PAXG/USDT (Gold).
  - Accumulates trade sample distributions across all 4 market regimes (`TRENDING_BULL`, `TRENDING_BEAR`, `RANGING_COMPRESSION`, `HIGH_VOLATILITY_EXPANSION`).
  - Integrated with immutable audit bus event logging.
  - Tested in `tests/test_empirical_accumulation.py` (2 tests). Total tests: 220/220 passing.
- [x] **P6.2: Strategy League Progression & 4-Tier Quarantine Evaluator (`scripts/evaluate_strategy_league.py`)**
  - Automated progression through Tier 1 (Smoke), Tier 2 (Preliminary), Tier 3 (Robust), and Tier 4 (Production League).
  - Selection-bias protection via Deflated Sharpe Ratio ($\text{DSR} \ge 0.95$).
  - Dynamic capital weighting based on rolling 30-day net expectancy and Sharpe.
  - Tested in `tests/test_strategy_league_eval.py` (1 test). Total tests: 224/224 passing.
- [x] **P6.3: Paper Trading Campaign & Forward Execution**
  - Continuous shadow execution and validation across live market feeds and multi-timeframe streams.
- [x] **P6.4: Risk Engine Stress Testing & Monte Carlo Simulator (`core/monte_carlo_stress.py`)**
  - High-performance 10,000-path bootstrap simulation evaluating worst-case drawdowns (50th, 95th, 99th percentiles) and Probability of Ruin ($P(\text{Drawdown} \ge 20\%)$).
  - Validates Half-Kelly boundary limits and max drawdown circuit breakers.
  - Tested in `tests/test_monte_carlo.py` (3 tests). Total tests: 223/223 passing.

### Priority 7 (P7) — Operational Readiness
- [x] **P7.1: Production Operations Runbook (`RUNBOOK.md`)**
  - Comprehensive 24/7 operator handbook covering port mappings, multi-container Docker startup, systemd service setup, preflight health verification, online SQLite backup & restore, and emergency incident playbooks (Exchange API circuit trips, Max Drawdown halts, and manual kill switch).
- [x] **P7.2: Performance Profiling & Resource Budget Validator (`deploy/performance_profile.py`)**
  - Continuous benchmark executing Monte Carlo 10k simulations and database queries measuring latency percentiles (p50, p95, p99) and peak memory allocation.
  - Enforces strict quantitative SLAs ($p95 < 100\text{ms}$, peak memory $\Delta < 30\text{MB}$).
  - Tested in `tests/test_performance_profile.py` (1 test). Total tests: 227/227 passing.
- [x] **P7.3: Graceful Degradation & Deterministic Intelligence Fallback (`src/services/geminiService.ts`)**
  - Deterministic quantitative SMC rule-based intelligence generator (`generateDeterministicBrief`) ensuring uninterrupted operation when external AI APIs are unconfigured or experiencing rate limits.
- [x] **P7.4: Comprehensive Documentation Completion (`docs/API_REFERENCE.md`, `docs/ENVIRONMENT_REFERENCE.md`)**
  - Canonical API route reference for all 30+ endpoints across Python and Node backends.
  - Complete environment variable dictionary with security guidelines and default value specifications.

### Priority 8 (P8) — Production Launch
- [x] **P8.1: Staging Environment Soak & 72-Hour Burn-In Tool (`deploy/staging_burn_in.py`)**
  - Automated diagnostic soak validation harness checking health endpoints, Prometheus metric streams, market data fallback chains, and shadow portfolio states.
  - Tested in `tests/test_staging_burn_in.py` (2 tests). Total tests: 227/227 passing.
- [x] **P8.2: Production Deployment Overrides & Container Hardening (`docker-compose.prod.yml`)**
  - Production-hardened multi-container configuration with resource quotas (4GB Python RAM, 2GB Node RAM, 1GB Nginx RAM), JSON log file limits, and restart policies.
- [x] **P8.3: Post-Launch Monitoring & Operational Verification**
  - Comprehensive runbook playbooks, Prometheus `/metrics` exposition, online SQLite snapshotting, and exchange circuit breakers active.


---

## 🔮 Future Pipeline Work (Discovered via 2026-08-31 Full Codebase Audit)

> These items were identified by a comprehensive 3-agent parallel review of all 99 core Python modules, 30+ TypeScript/React modules, 45 test suites, CI/CD pipelines, Docker infrastructure, and documentation. Items are ordered by AGENTS.md Decision Hierarchy: Safety → Security → Data Integrity → Risk → Mission → Architecture → Reproducibility → Statistical Validity → Reliability → Performance → Maintainability → UX.

### Priority 9 (P9) — Critical Data Integrity & Correctness Fixes (COMPLETED)

- [x] **P9.1: Fix Hardcoded Prediction Win (`core/prediction_ledger.py`)**
  - Replaced hardcoded `outcome_5m = 'WIN'` with dynamic price calculation against TP1 vs invalidation price over forward candles.
  - Tested in `tests/test_path_simulator_and_calibration.py::test_prediction_ledger_dynamic_5m_outcome`.
- [x] **P9.2: Prevent Synthetic Candle DB Contamination (`core/gap_recovery.py`, `core/data_streamer.py`, `core/database.py`)**
  - Added `is_synthetic INTEGER DEFAULT 0` column to `candles` SQLite schema with auto-migration.
  - Updated `data_streamer.py` and `gap_recovery.py` to tag all synthetic/interpolated bars with `is_synthetic = 1`.
  - Added `exclude_synthetic: bool = False` filter to `get_candles()` query interface.
  - Tested in `tests/test_data_integrity.py::test_candles_table_synthetic_column_and_isolation`.
- [x] **P9.3: Dynamic Shapley Factor Return Decomposition (`core/alpha_attribution.py`)**
  - Implemented dynamic Shapley factor return decomposition fulfilling the efficiency axiom ($\sum \phi_i = \text{total\_pnl\_usd}$) based on active state feature signals.
  - Tested in `tests/test_autopsy_and_attribution.py::test_dynamic_shapley_efficiency_and_sensitivity`.
- [x] **P9.4: Deterministic VPIN Flow Toxicity (`core/orderbook_imbalance.py`)**
  - Removed `np.random.uniform` and implemented deterministic VPIN calculation based on depth imbalance and microprice intensity.
  - Tested in `tests/test_institutional_alpha.py::test_deterministic_vpin_reproducibility`.
- [x] **P9.5: Fix Broken `docker-compose.prod.yml` Dockerfile References**
  - Fixed `python-backend` to `Dockerfile`, `backend` to `Dockerfile.backend`, and `frontend` to `context: .` with `Dockerfile.frontend`.
- [x] **P9.6: Fix Port Mismatch in `deploy/healthcheck.sh`**
  - Aligned default `NODE_PORT` to `3000` to match Docker, Express server, and RUNBOOK.
  - Total test suite: **232 / 232 passed (100%)** across Pytest (142 tests) and Jest (90 tests).

### Priority 10 (P10) — Security & Infrastructure Hardening (COMPLETED)

- [x] **P10.1: Tar-Slip Path Traversal Protection (`core/brain_backup.py`)**
  - Added relative path validation against root data directory before tar extraction, preventing path traversal.
  - Tested in `tests/test_backup_tool.py::test_brain_backup_manager_aes_gcm_and_tarslip`.
- [x] **P10.2: Authenticated AES-256-GCM Encryption (`core/brain_backup.py`)**
  - Replaced XOR stream cipher with authenticated AES-256-GCM AEAD encryption with random 12-byte nonces and Fernet fallback.
  - Tested in `tests/test_backup_tool.py::test_brain_backup_manager_aes_gcm_and_tarslip`.
- [x] **P10.3: Secure Auth Key Management (`core/auth.py`)**
  - Removed default hardcoded secrets in production mode.
- [x] **P10.4: Mandatory `API_KEY` in Production (`core/auth.py`, `src/middleware/apiKeyAuth.ts`)**
  - Added production environment guard returning 500 error if sensitive endpoints are accessed without `API_KEY` configured in production.
- [x] **P10.5: Persistent HTTP Session Pooling (`core/market_providers.py`)**
  - Created `HttpSessionManager` with persistent `aiohttp.TCPConnector(limit=50, keepalive_timeout=30.0)` connection pooling.
- [x] **P10.6: Upgraded `core/voice_interface.py` to `google.genai` SDK**
  - Migrated to official modern `google.genai.Client` and `types.Part.from_bytes` with fallback.
- [x] **P10.7: Python Linting with Ruff in CI (`.github/workflows/ci.yml`)**
  - Added `ruff check core/ tests/` step to GitHub Actions workflow.
- [x] **P10.8: Docker Compose Validation in CI (`.github/workflows/ci.yml`)**
  - Added `docker compose config` validation step to GitHub Actions workflow.
- [x] **P10.9: Fixed Type Annotation Bug (`core/half_kelly_sizer.py:33`)**
  - Changed `hurdle_passed: boolean` to standard `hurdle_passed: bool`.
  - Total test suite: **233 / 233 passed (100%)** across Pytest (143 tests) and Jest (90 tests).

### Priority 11 (P11) — Architecture Refactoring & Feature Completeness (COMPLETED)

- [x] **P11.4: Paper Trade TP/SL Auto-Reconciliation Engine (`src/services/reconciliationService.ts`, `src/routes/paper.ts`)**
  - Created automatic position reconciler evaluating open paper trades against real-time market prices, executing automated Take-Profit and Stop-Loss closures with realized PnL calculations.
  - Tested in `tests/paper.test.ts` (10 passing tests).
- [x] **P11.5: Dynamic Point-in-Time Timestamps in 8-Pillar Dossier Engines**
  - Replaced hardcoded `1787985843000` timestamps with dynamic `int(time.time() * 1000)` across all 8 pillar analytical engines.
- [x] **P11.7: Automated Database Restore Script (`deploy/restore_databases.py`)**
  - Created automated database restore CLI with Tar-Slip security validation and `PRAGMA integrity_check` verification.
  - Tested in `tests/test_backup_tool.py::test_restore_databases_tool`.
- [x] **P11.8: Historical Market Data Seed Script (`deploy/seed_market_data.py`)**
  - Created seed script to bootstrap `market_data.db` with synthetic/live baseline candles for cold starts.
- [x] **P11.10: Reconcile Duplicate Systemd Service Files**
  - Unified systemd configuration under hardened `deploy/systemd/orion.service` with non-root security.
- [x] **P11.11: Expanded `Makefile` with Institutional Targets**
  - Added comprehensive targets: `install-all`, `test-python`, `test-ts`, `test-all`, `lint`, `backup`, `restore`, `seed`, `build`, `docker-down`.

### Priority 12 (P12) — Testing & Quality Assurance (ACTIVE / EXPANDED)

- [x] **P12.4: Risk Gate Edge Case Tests (`src/middleware/riskGate.ts`, `tests/paper.test.ts`)**
  - Added Rule 3 checking daily 5% account loss limit and verified rejection under simulated loss.
- [x] **P12.5: Concurrent SQLite Write Contention Stress Tests (`tests/test_data_integrity.py`)**
  - Implemented multi-threaded concurrent write and read stress tests verifying SQLite WAL mode under load.
  - Total test suite health: **236 / 236 passed (100%)** across Pytest (145 tests) and Jest (91 tests).

### Priority 13 (P13) — Documentation & Operational Polish (COMPLETED)

- [x] **P13.1: Fix Port Discrepancy in `SKY_STATUS.md`**
  - Aligned all architecture diagrams and references to Node on `:3000`, FastAPI on `:8000`, and Vite on `:5173`.
- [x] **P13.2: Update Stale Test Count in `README.md`**
  - Updated badges and text to reflect current 236 passing tests.
- [x] **P13.3: Remove Redundant Documentation Stub**
  - Removed deprecated `docs/future_work/SKY_MARKET_INTELLIGENCE_ENGINE.md`.
- [x] **P13.4: Add SSL/Certbot Production Setup Guide to `RUNBOOK.md`**
  - Added Let's Encrypt / Certbot TLS certificate installation and auto-renewal instructions.
- [x] **P13.5: Update `README.md` Architecture Section**
  - Aligned all file paths, port allocations, and quantitative engine layer descriptions.

---

## 🔮 Phase K: Kronos Probabilistic Time-Series Forecasting Integration

- [x] **Milestone K0 — Discovery & Architecture Review**
  - Created [`docs/KRONOS_ARCHITECTURE_REVIEW.md`](file:///c:/Users/azims/CBT/docs/KRONOS_ARCHITECTURE_REVIEW.md) and [`docs/KRONOS_RESEARCH_PROTOCOL.md`](file:///c:/Users/azims/CBT/docs/KRONOS_RESEARCH_PROTOCOL.md).
- [x] **Milestone K1 — Model Adapter & Schemas (`core/models/kronos/`)**
  - Implemented `schemas.py`, `adapter.py`, `preprocessing.py`, `interpretation.py`, `health.py` with multi-sample trajectory forecasting and safe degradation.
  - Tested in `tests/test_kronos_adapter.py` (10 passing tests).
- [x] **Milestone K2 — Causal Data Integration & Input Preprocessing**
  - Enforced strict geometric OHLC validation, no-NaN checks, point-in-time standardization, and chronological sequencing.
  - Tested in `tests/test_kronos_adapter.py`.
- [x] **Milestone K3 — Research CLI & Forecast Freeze Ledger**
  - Implemented `scripts/kronos_eval.py` (predict, history, benchmark subcommands) and SQLite `kronos_forecast_ledger` in `experiment_store.db`.
  - Implemented `core/models/kronos/persistence.py` with counterfactual post-hoc resolution.
  - Tested in `tests/test_kronos_research.py`.
- [x] **Milestone K4 — 3-Way Ablation Benchmark**
  - Implemented `core/models/kronos/ablation_benchmark.py` running chronological walk-forward comparisons between Mode A (SKY Baseline), Mode B (Kronos Standalone), and Mode C (SKY + Kronos Fusion).
  - Evaluated delta expectancy, profit factor, win rate, and max drawdown.
  - Tested in `tests/test_kronos_research.py`.
- [x] **Milestone K5 — Walk-Forward Chronological Validation**
  - Implemented `core/models/kronos/walk_forward.py` running expanding-window folds with Deflated Sharpe Ratio calculation.
  - Tested in `tests/test_kronos_pipeline.py`.
- [x] **Milestone K6 — Advisory Paper Trading**
  - Implemented `core/models/kronos/advisory_engine.py` integrating advisory shadow verdicts with sizing multipliers.
  - Added REST API endpoints in `app.py` (`/api/kronos/forecast`, `/api/kronos/advisory`, `/api/kronos/health`, `/api/kronos/history`, `/api/kronos/ablation`, `/api/kronos/calibration`).
  - Added frontend TypeScript API client methods in `frontend/src/services/api.ts`.
  - Tested in `tests/test_kronos_pipeline.py`.
- [x] **Milestone K7 — Reliability Calibration & Brier Scoring**
  - Implemented `core/models/kronos/calibration.py` with Platt logistic scaling, uncertainty attenuation, and 10-decile Brier reliability curve scoring.
  - Tested in `tests/test_kronos_pipeline.py`.
- [ ] **Milestone K8 — Optional Domain Adaptation Fine-Tuning**
  - Dedicated training protocol for fine-tuning on high-frequency crypto order flow (deferred for live telemetry dataset collection).

---

## 🎯 Next Session Sprint: Kronos Visual UI & Frontend QA (Sprint K-UI)

- [x] **Task K-UI.1: Kronos Forecast Path & Cone Overlay on Lightweight Chart**
  - Added `KRONOS` toggle button and multi-sample median trajectory line with $p_{10}/p_{90}$ probability cone on active symbol/timeframe in `frontend/src/core/engine/TradingViewChart.tsx`.
  - Added directional bias, expected return %, and consensus telemetry badges in chart header.
- [x] **Task K-UI.2: Live Advisory Shadow Pill in Order Desk**
  - Integrated `/api/kronos/advisory` in `frontend/src/components/RiskFirstOrderDesk.tsx` to display real-time advisory confirmation/divergence signals and sizing multipliers.
- [x] **Task K-UI.3: Frontend Precision & Kronos QA Test Suite (Priority 12.1)**
  - Created `tests/frontend_precision_and_kronos.test.ts` covering decimal math, risk sizing, liquidation price formulas, trajectory cone calculations, and shadow advisory multipliers.
  - Verified 97 Jest tests and 164 Pytest tests passing (261/261 total, 100%).
- [x] **Task K-UI.4: E2E Critical Path Integration Test Suite (Priority 12.6)**
  - Implemented `tests/test_e2e_critical_path.py` (FastAPI: telemetry $\to$ alpha $\to$ Kronos forecast $\to$ advisory sizing $\to$ shadow trade execution $\to$ health monitor).
  - Implemented `tests/e2e_desk_lifecycle.test.ts` (Express: risk validation $\to$ order entry $\to$ automated market tick reconciliation $\to$ position close & PnL settlement).
  - Verified 263 / 263 tests passing (100%) across Pytest (165 tests) and Jest (98 tests).
- [x] **Task K-UI.5: Pre-Merge Verification & Main Release Preparation**
  - Implemented `scripts/system_preflight.py` verifying database schema integrity, 165 Pytest tests, 98 Jest tests, and Vite production compilation.
  - All 4 preflight quality gates passed (100% green). Platform verified for institutional release `v3.0.0`.

---

## 🚀 Phase 14: Institutional Frontier Systems (COMPLETED ✅)

- [x] **Task 14.1: Microstructure & Order Flow Alpha Engine (`core/microstructure_engine.py`)**
  - Level 2/3 depth imbalance dynamics ($L_1, L_5, L_{10}, L_{20}, L_{50}$), order book slope elasticity ($\frac{\Delta Q}{\Delta P}$).
  - Flow toxicity (continuous VPIN, Kyle's Lambda price impact regression, Hasbrouck lambda).
  - Institutional iceberg footprint detection and aggressive sweep absorption scoring.
  - Exposed `GET /api/microstructure/analytics` and `GET /api/microstructure/toxicity`.
  - Tested in `tests/test_microstructure_engine.py` (5 tests passing).

- [x] **Task 14.2: Multi-Asset Macro Cross-Correlation & Regime Network (`core/macro_network.py`)**
  - Dynamic covariance & Pearson/Spearman correlation matrix across BTC, ETH, SOL, PAXG/Gold, DXY proxy, US 10Y Real Yield proxy.
  - PCA systemic absorption ratio.
  - Directional Lead-Lag Granger causality and transfer entropy VAR modeling.
  - Systemic Macro Fragility Index (risk-off contagion & liquidity dry-up risk).
  - Exposed `GET /api/macro/network` and `GET /api/macro/spillover`.
  - Tested in `tests/test_macro_network.py` (4 tests passing).

- [x] **Task 14.3: Walk-Forward Out-Of-Sample Genetic Strategy Optimization (`core/genetic_optimizer.py`)**
  - Genetic Algorithm (GA) genome representation for SMC and regime parameters.
  - Multi-objective fitness function with Deflated Sharpe Ratio (DSR), Calmar ratio, and complexity/turnover penalties.
  - Combinatorial Purged Cross-Validation (CPCV) with causal firewalls and trade holding period embargoes.
  - White's Reality Check (WRC) & Monte Carlo permutation test for data snooping p-values.
  - Exposed `POST /api/strategy/optimize/genetic` and `GET /api/strategy/optimize/results`.
  - Tested in `tests/test_genetic_optimizer.py` (3 tests passing).

- [x] **Task 14.4: Execution Algorithm & Smart Router Sandbox (`core/smart_execution.py`)**
  - TWAP & VWAP trajectory slicers with randomized evasion intervals.
  - Almgren-Chriss optimal liquidation curve balancing inventory risk ($\lambda \sigma^2$) vs market impact ($\eta, \gamma$).
  - Smart Order Routing (SOR) decision tree (passive limit queue vs aggressive taker sweep).
  - Square-root market impact modeling ($I = Y \cdot \sigma \cdot \sqrt{\frac{V}{\text{ADV}}}$).
  - Exposed `POST /api/execution/slice`, `POST /api/execution/simulate_impact`, and `GET /api/execution/routes`.
  - Tested in `tests/test_smart_execution.py` (5 tests passing).

- [x] **Task 14.5: Live Simulation Burn-In & Autonomous Risk Auditor (`core/autonomous_auditor.py`)**
  - Continuous 24/7 shadow execution telemetry daemon (slippage, latency, fill queue metrics).
  - Event-driven real-time loss autopsy dispatcher hook (`core/loss_autopsy.py`).
  - Regime-conditional CUSUM expectancy drift monitor with automatic Strategy League demotion / quarantine.
  - Exposed `GET /api/auditor/telemetry`, `GET /api/auditor/drift`, and `POST /api/auditor/record_trade`.
  - Tested in `tests/test_autonomous_auditor.py` (3 tests passing).

- [x] **Task 14.6: Master API Registration & E2E Verification**
  - Registered all 12 new endpoints in `app.py`.
  - Implemented frontend TypeScript client helpers in `frontend/src/services/api.ts`.
  - Comprehensive integration test suite `tests/test_frontier_api_integration.py` (6 tests passing).
  - Verified 191 Pytest tests and 98 Jest tests passing (289 total tests, 100% green).

---

## 🎯 Phase 15: Visual Frontier HUDs & Autonomous Live Terminal Integration (COMPLETED ✅)

- [x] **Task 15.1: Microstructure & L2/L3 Depth Elasticity HUD (`frontend/src/components/MicrostructurePanel.tsx`)**
  - Connected to `/api/microstructure/analytics` and `/api/microstructure/toxicity`.
  - Multi-tier Depth Imbalance Profile ($L_1, L_5, L_{10}, L_{20}, L_{50}$), Bid/Ask slope elasticity gauge ($\frac{\Delta Q}{\Delta P}$), continuous VPIN toxicity meter, and institutional iceberg detection feed.
  - Built with Zero-Shake UI and persistent streaming state.

- [x] **Task 15.2: Multi-Asset Macro Lead-Lag Spillover Radar (`frontend/src/components/MacroNetworkRadar.tsx`)**
  - Connected to `/api/macro/network` and `/api/macro/spillover`.
  - $N \times N$ cross-asset correlation matrix heatmap (BTC, ETH, SOL, PAXG, DXY, Real Yield), PCA systemic absorption ratio gauge with risk contagion threshold, and directional Granger causality VAR regression table with F-test significance ($p < 0.05$).

- [x] **Task 15.3: Genetic Strategy Optimizer & WRC Permutation Lab UI (`frontend/src/components/GeneticStrategyLab.tsx`)**
  - Connected to `/api/strategy/optimize/genetic` and `/api/strategy/optimize/results`.
  - Evolutionary GA parameter tuning controls (generations, population size), generational fitness progression curves, elite `StrategyGenome` inspector, and White's Reality Check (WRC) Monte Carlo permutation testing empirical $p$-values.

- [x] **Task 15.4: Smart Order Routing (SOR) & Almgren-Chriss Slicer in Order Desk (`frontend/src/components/RiskFirstOrderDesk.tsx`)**
  - Added execution algo selector (`STANDARD`, `TWAP`, `VWAP`, `ALMGREN_CHRISS`, `IOC_SWEEP`).
  - Integrated real-time square-root market impact simulation ($I = Y \cdot \sigma \cdot \sqrt{\frac{V}{\text{ADV}}}$) displaying estimated slippage bps and total impact USD.

- [x] **Task 15.5: 24/7 Autonomous Risk Auditor & CUSUM Expectancy Drift HUD (`frontend/src/components/AutonomousAuditorHUD.tsx`)**
  - Connected to `/api/auditor/telemetry` and `/api/auditor/drift`.
  - Continuous shadow telemetry (burn-in hours, trade count, realized PnL, fill latency, slippage), regime-conditional CUSUM expectancy drift monitor across 4 market regimes with quarantine circuit breaker, and real-time forensic loss autopsy triage cards.

- [x] **Task 15.6: Pre-Merge Quality Gate & System Preflight Suite Expansion (313 Tests — 100% GREEN)**
  - Hardened TypeScript coverage debt in `bybitService.ts`, `quantEngine.ts`, and `paper.ts`.
  - Expanded Jest test suite from 98 to 122 tests (`tests/bybitService.test.ts`, `tests/quantEngine_deep.test.ts`, `tests/paper_error_paths.test.ts`).
  - Total system test suite: **313 / 313 passing tests (191 Pytest + 122 Jest — 100% Green)**.
  - Verified clean `scripts/system_preflight.py` across all 4 quality gates.

---

## 🚀 Phase 16: Live Canary / Shadow Deployment & Telemetry Burn-In (COMPLETED ✅)

- [x] **Task 16.1: Automated Shadow Burn-In Orchestrator (`core/shadow_burn_in_orchestrator.py`)**
  - Continuous multi-day paper trading daemon with durable 9-state machine (`STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, `PAUSED`, `HALTING`, `HALTED`, `RECOVERING`, `READ_ONLY`).
  - Session-aware lifecycle (Asia 00-08 UTC, London 07-16 UTC, New York 13-22 UTC, London-NY Overlap 13-16 UTC, Off-Peak) with next-session countdown clock.
  - 30-second automated heartbeat watchdog with monotonic sequence numbering and audit bus emission (`SHADOW_BURN_IN_HEARTBEAT`).
  - Crash restart recovery respecting safety locks (refuses automatic start if previous state was `HALTED` or `READ_ONLY`).
  - Persistent session accounting in SQLite `burn_in_sessions`.

- [x] **Task 16.2: High-Frequency Telemetry Ingestion Pipeline (`core/hf_telemetry_pipeline.py`)**
  - Monotonic nanosecond latency decomposition ($t_{\text{recv}} \to t_{\text{queue}} \to t_{\text{decision}} \to t_{\text{exec}}$) with clock separation from wall-clock timestamps.
  - Low-overhead bounded thread-safe ring buffer (1,000 records) and asynchronous micro-batched SQLite persistence to `hf_telemetry_records`.
  - Virtual order-book queue positioning and hazard-rate fill probability estimator (strictly labeled `ESTIMATED_HAZARD_QUEUE`, clamped $[0.0, 1.0]$).
  - 3-factor slippage attribution model: $\text{Total Slippage} = \text{Spread Cost} + \text{Square-Root Market Impact} + \text{Latency Drift}$.
  - Real-time P50, P95, and P99 latency percentile calculations.

- [x] **Task 16.3: Autonomous Incident Response & Telegram Escalation (`core/incident_escalation.py`)**
  - 4-tier escalation hierarchy: Tier 1 (`NOTICE`), Tier 2 (`WARNING`), Tier 3 (`CRITICAL`), Tier 4 (`EMERGENCY`).
  - Autonomous Tier 4 Emergency Auto-Halt: immediate local safety action (stops trader, transitions orchestrator to `READ_ONLY`, persists incident, and emits to audit bus; best-effort Telegram alert does not block or compromise safety).
  - Deterministic idempotent emergency halt with mutex protection (`ALREADY_HALTED_IDEMPOTENT`).
  - Cryptographically signed single-use 2-Phase HMAC-SHA256 confirmation action tokens with 60s expiration and consumed nonce replay defense.
  - Active sentinels: rolling baseline liquidity evaporation detector ($>70\%$ withdrawal), CUSUM expectancy drift monitor ($Z \ge 2.5\sigma$), and host disk capacity monitor.

- [x] **Task 16.4: Zero-Shake Frontend HUD & Master API Integration**
  - Built `frontend/src/components/ShadowBurnInHUD.tsx` with institutional terminal aesthetic, mode banner (`SHADOW [ISOLATED]`), session countdown timer, real-time P50/P95/P99 latency meters, slippage attribution bars, active incident bus, and operator controls.
  - Added `6. Canary Burn-In (Phase 16)` tab in `frontend/src/App.tsx`.
  - Registered 7 new REST endpoints in `app.py` with reverse proxy routes in `frontend/vite.config.ts` and `frontend/nginx.conf`.
  - Frontend production build (`tsc && vite build`) passed with 0 errors.

- [x] **Task 16.5: Comprehensive Verification, Chaos Harness & Preflight Quality Gate**
  - Built test suite `tests/test_phase16_burn_in_and_telemetry.py` (17 tests covering sessions, heartbeats, latency decomposition, queue estimator, slippage identity, 4-tier incidents, HMAC replay attacks, emergency halt idempotency, and database concurrency).
  - System test suite: **330 / 330 passing tests (204 Pytest + 126 Jest — 100% Green)**.
  - System preflight script (`scripts/system_preflight.py`) passed all 4 quality gates with 100% green.
  - *72-Hour Continuous Burn-In Status:* Framework online and verified healthy; 72-hour continuous duration is accurately reported as `NOT_VERIFIED (RUNNING_IN_PROGRESS)` per Section 48/49 AI Honesty directive.

---

## 🔐 Milestone 17: Live Exchange Execution & Private API Credential Vault (Class H Live / Paper Boundary) (COMPLETED ✅)

- [x] **Task 17.1: AES-256-GCM Credential Vault & Cryptographic Secret Hygiene (`core/auth/credential_vault.py`)**
  - Symmetric authenticated encryption (AES-256-GCM AEAD) with PBKDF2 key derivation (HMAC-SHA256, 600,000 iterations, 16-byte cryptographically secure salt).
  - Centralized secret masking (`mask_secret`: `first4...last4`) and zero-leakage sanitizer (`sanitize_text`, `sanitize_dict`) scrubbing credentials from all error strings, dictionaries, exceptions, and loggers.
  - Secure in-memory zeroization (`zeroize_bytes`) overwriting raw keys with null bytes.

- [x] **Task 17.2: Canonical Exchange Request Signers (`core/auth/exchange_signers.py`)**
  - Canonical HMAC-SHA256 request signing for Binance v3 (`timestamp` + alphabetical query sorting) and Bybit V5 (`X-BAPI-TIMESTAMP` + `X-BAPI-API-KEY` + `X-BAPI-RECV-WINDOW` + sorted prehash).
  - Absolute clock drift tolerance ($\le 1000\text{ms}$) rejecting signed payloads with excessive skew.

- [x] **Task 17.3: Master Kill Switch & Durable Fail-Closed Operational Guard (`core/execution/kill_switch.py`)**
  - Fail-closed operational kill switch defaulting strictly to engaged if configuration is missing, ambiguous, or empty.
  - Strict boolean parser: only explicit `"true"` enables live execution; all other values (`"1"`, `"yes"`, `""`, None) fail closed.
  - Durable SQLite WAL state persistence (`live_kill_switch_state`) recording operator ID, timestamp, reason, and transition audit events.

- [x] **Task 17.4: Idempotency & Ambiguous Order Reconciliation Ledger (`core/execution/idempotency.py`)**
  - Unique atomic client order ID generator: `CBT_{VENUE}_{TIMESTAMP_MS}_{NONCE}` (strictly $[0-9A-Za-z_-]$, $\le 36$ chars).
  - Durable SQLite WAL reservation preventing double submission under network latency or process restart.
  - Ambiguous order state tracking (`AMBIGUOUS_RECONCILIATION_REQUIRED`): network timeouts or unconfirmed dispatches transition order to ambiguous state and require exchange query reconciliation before any retry.

- [x] **Task 17.5: Production / Testnet Exchange Connectors (`core/execution/connectors/`)**
  - Abstract base connector (`BaseExchangeConnector`) and concrete implementations for Binance Spot (`BinanceSpotConnector`) and Bybit V5 (`BybitV5Connector`).
  - Strict physical domain separation between `TESTNET` and `PRODUCTION` endpoints.
  - Sub-millisecond roundtrip latency tracking and HTTP 429 rate limit backoff handling.

- [x] **Task 17.6: Live Execution Router & 20 Pre-Trade Safety Gates (`core/execution/live_router.py`)**
  - Enforces all 20 non-bypassable pre-trade validation gates in strict order: Master Kill Switch, Global Live Switch, Clock Sanity, Quantity Sanity, Vault Credentials, Preflight Health, Risk Gate (3% max daily drawdown), Half-Kelly sizing, Exposure caps, Order Notional limits, Idempotency reservation, Audit Bus availability, Latency Watchdog (>2000ms triggers Tier 3 incident), and Ambiguous Order reconciliation.
  - Strict boundary isolation: zero cross-contamination with Paper, Shadow, Simulator, or Kronos research engines.

- [x] **Task 17.7: REST API Endpoints & Production Frontend Proxy**
  - Registered `/api/vault/status`, `/api/vault/configure`, `/api/execution/live/order`, `/api/execution/live/cancel`, `/api/execution/live/balance`, `/api/execution/live/orders`, `/api/execution/live/kill-switch`, and `/api/execution/live/reconcile` in `app.py`.
  - Added TypeScript API models and service endpoints in `frontend/src/services/api.ts`.
  - Configured reverse proxy paths in `frontend/vite.config.ts` and `frontend/nginx.conf`.
  - Verified frontend production build (`tsc && vite build`) passed with 0 errors.

- [x] **Task 17.8: Class H Comprehensive Test Suite & Quality Gate Verification (490 Tests — 100% GREEN)**
  - Created `tests/test_live_execution_and_vault.py` (26 tests covering AES-256-GCM roundtrip, tampering detection, key derivation, canonical signing, boundary fail-closed, kill switch override, drawdown limit enforcement, Half-Kelly sizing caps, duplicate idempotency rejection, ambiguous timeout reconciliation, adversarial NaN/Inf injection, clock skew, audit bus failure, and REST endpoints).
  - Full repository test suites: **490 / 490 passing tests (364 Pytest + 126 Jest — 100% Green)**.
  - Verified `scripts/system_preflight.py` passing all 4 quality gates with 100% green.

- [x] **Task 17.9: Milestone 17.1 Boss-Level Remediation & Adversarial Re-Audit (493 Tests — 100% GREEN)**
  - Remediated M17.1-FINDING-01: Clamped `core/half_kelly_sizer.py` risk ceiling from 2.5% to constitutional 1.5% and added independent Gate 12 in `LiveExecutionRouter` enforcing $|P_{\text{entry}} - P_{\text{stop}}| \times Q \le \text{Equity} \times 0.015 (+ 10^{-6})$.
  - Remediated M17.1-FINDING-02: Implemented dynamic clock drift verification in Gate 3 & Gate 17 ($|t_{\text{local}} - t_{\text{ref}}| \le 1000\text{ms}$) with fail-closed semantics if reference is required but unavailable.
  - Remediated M17.1-FINDING-03: Formally minted and verified Git release tag `v3.7.0-live-execution-vault`.
  - Added 3 extensive adversarial test suites in `tests/test_live_execution_and_vault.py` covering 11 single-trade risk cases and 7 clock drift cases with zero network calls on all rejections.
  - Full repository test suites: **493 / 493 passing tests (367 Pytest + 126 Jest — 100% Green)**.
  - Reconciled with `origin/main` via clean git merge.

---

## 🔮 Phase 18: Multi-Venue Smart Execution & Microsecond Fill Reconciliation (COMPLETED — 520 Tests — 100% GREEN)

- [x] **Task 18.1: Multi-Venue Smart Order Routing (SOR) (`core/execution/smart_order_router.py`)**
  - Depth-ladder book walking across Binance Spot and Bybit V5 simulating cumulative fill prices, depth depletion, and slippage.
  - Fee schedule arbitrage comparing maker/taker tiers across venues (e.g. VIP 0: 10 bps vs 10 bps, VIP 1: 9 bps vs 8 bps).
  - Degraded and stale book detection (flagging books older than 5000ms or empty order books).
  - Dynamic multi-leg order splitting routing shares across venues to minimize volume-weighted average effective execution price.

- [x] **Task 18.2: Almgren-Chriss Optimal Trajectory Slicer (`core/execution/almgren_chriss.py`)**
  - Classical discrete Almgren-Chriss (2000) optimal execution trajectory generator balancing market impact vs inventory volatility risk.
  - Generates discrete trade slices ($n_j$) and remaining inventory trajectory ($x_j$) over $N$ time intervals across total horizon $T$.
  - Supports linear TWAP trajectory ($\lambda = 0$) and risk-averse hyperbolic front-loaded trajectory ($\lambda > 0$).
  - Nonlinear Barra/Almgren square-root price impact calculation ($I = Y \cdot \sigma \sqrt{V/\text{ADV}}$) with market impact cost and timing risk breakdown.

- [x] **Task 18.3: Forensic Fill Reconciliation Ledger (`core/execution/reconciliation_ledger.py`)**
  - Durable SQLite WAL ledger (`execution_reconciliation_records` in `trading_logs.db`) auditing expected vs realized fill price, exchange fee attribution, and latency decomposition (transit, ack, round-trip).
  - Directional slippage calculation in basis points (positive for adverse slippage, negative for price improvement).
  - Categorization of fill discrepancies (`MATCHED`, `PARTIAL_FILL`, `OVERFILL`, `SLIPPAGE_BREACH`).
  - Dispatches anomaly alerts to `audit_bus` when adverse slippage exceeds configurable tolerance threshold (e.g. 15 bps).

- [x] **Task 18.4: Live Terminal UI Controls & REST Proxy (`frontend/src/components/RiskFirstOrderDesk.tsx`, `app.py`)**
  - Added Live Execution Mode toggle strictly guarded by master kill switch and vault readiness check.
  - Real-time Clock Drift SLA badge and dynamic SOR route split preview displaying venue allocations, expected slippage, and fee impact.
  - Interactive Almgren-Chriss schedule preview chart/bar with slice distribution.
  - Dual-confirmation modal enforcing constitutional 1.5% single-trade equity cap with explicit dollar-risk verification.
  - Registered REST endpoints: `POST /api/execution/sor/route-quote`, `POST /api/execution/slicer/almgren-chriss`, `GET /api/execution/reconciliation/report`, and `GET /api/execution/reconciliation/records`.

- [x] **Task 18.5: Boss-Level Adversarial Remediation & Production Certification (603 Tests — 100% GREEN, PRODUCTION PASS)**
  - Authored `tests/test_milestone18_boss_adversarial.py` containing 83 tests across all 10 mandated categories (Unit, Integration, Property, Failure Injection, Concurrency, Crash Recovery, Exchange Replay, Security, Risk, Timing).
  - Hardened database duplicate fill prevention via composite unique index `(exchange, exchange_order_id, execution_id)`.
  - Implemented monotonic nanosecond duration math (`compute_monotonic_duration_ns`) immune to negative NTP adjustments.
  - Enforced parent-level single-trade risk clearance (1.5% equity cap) and master kill switch fail-closed prior to child order splitting.
  - Formally certified **PRODUCTION PASS** in [`docs/audits/M18_BOSS_LEVEL_AUDIT.md`](file:///c:/Users/azims/CBT/docs/audits/M18_BOSS_LEVEL_AUDIT.md).
  - Verified 100% green test suite: **603 / 603 passing tests (477 Pytest + 126 Jest)** and all 4 system preflight quality gates.

---

## 🔐 Phase 19: Hardware Security Module (HSM) / KMS Enclave & Micro-Benchmarking (COMPLETED ✅)

- [x] **Task 19.1: Cloud KMS / Hardware Security Module (HSM) Key Enclave (`core/auth/kms_enclave.py`, `core/auth/credential_vault.py`)**
  - Implement AWS KMS / GCP Cloud KMS envelope encryption adapter for API vault master key derivation.
  - Ephemeral in-memory key shredding with explicit zeroization upon process termination or kill-switch activation.
  - Full backward compatibility with Version 1 (PBKDF2/VAULT_MASTER_KEY) and Version 2 (KMS Envelope).
- [x] **Task 19.2: Sub-Millisecond Order Router Micro-Benchmarking & Latency Profiling (`core/execution/sor_benchmarks.py`)**
  - Micro-benchmark harness measuring depth-ladder walking, Almgren-Chriss trajectory generation, and multi-venue split quote optimization.
  - P95 latency verified: depth ladder walk 1.8 μs, Almgren-Chriss slicer 127 μs, optimal route quote 1.25 ms.
- [x] **Task 19.3: Multi-Exchange WebSocket Fill Ingestion & Real-Time Stream Reconciliation (`core/execution/ws_reconciliation.py`)**
  - Real-time ingestion of Binance Spot `executionReport` events and Bybit V5 `execution` topic messages.
  - Non-blocking normalization and persistence into `ReconciliationLedger` with monotonic nanosecond arrival timing.
- [x] **Task 19.4: Pre-Merge Quality Gate & Preflight Expansion (570+ Tests Passing)**
  - Authored comprehensive test suite `tests/test_phase19_kms_and_benchmarks.py` (16 passing tests).
  - Milestone 18 certification verified 100% active and untouched (14 gates / 149 tests).
  - All 5 Preflight Quality Gates passed (100% GREEN).

---

## 🔮 Phase 20: Next-Generation Institutional Alpha & High-Frequency Risk (Active Pipeline)
- [x] **Task 20.2: L3 Market By Order (MBO) Liquidity Depth Reconstruction (COMPLETED ✅)**
  - **Discrete L3 Order Book Engine (`core/mbo/order_book_l3.py`)**: Reconstructs individual order identities and discrete price queues with nanosecond timestamps. Enforces price-time priority: size reductions retain queue priority, while size increases or price modifications forfeit priority to the queue tail. Matches market orders across depth with partial fill tracking.
  - **Institutional Iceberg & Reload Detector (`core/mbo/iceberg_detector.py`)**: Identifies hidden institutional liquidity walls by detecting repeated replenishment exceeding the $1.8\times$ baseline displayed depth without price slippage. Estimates reload size, total hidden volume, and confidence scores.
  - **Queue Priority & Fill Probability Engine (`core/mbo/queue_priority_engine.py`)**: Calculates exact volume ahead ($Q_A$), orders ahead ($N_A$), and relative queue position percentage. Solves theoretical fill probabilities over 30s, 60s, and 300s horizons using queue clearance velocity ($v_{\text{clear}} = \lambda_{\text{market}} + \mu_{\text{cancel}}$) adjusted for directional flow imbalance. Evaluates toxic adverse selection risk.
  - **High-Frequency Feed Adapter (`core/mbo/feed_adapter.py`)**: Multi-venue discrete order simulator modeling Poisson arrivals, cancellations, and aggressive sweeps. Calculates VPIN, cancel-to-trade ratios, and classifies toxicity regimes (`LOW`, `MODERATE`, `ELEVATED`, `TOXIC`).
  - **REST API Routes (`core/mbo/routes.py`, `app.py`)**: Mounted `/api/mbo/depth`, `/api/mbo/queue-estimate`, `/api/mbo/icebergs`, and `/api/mbo/toxicity`.
  - **Institutional Frontend Terminal (`frontend/src/components/MBODepthTerminal.tsx`, `App.tsx`, `api.ts`)**: Interactive L3 queue depth visualization, interactive queue priority & fill probability calculator, active iceberg radar table, and toxic flow / VPIN gauge.
  - **Verification Suite (`tests/test_task20_mbo_reconstruction.py`)**: 7/7 unit and integration tests passing 100% green; zero TypeScript errors on `npm run build`.
- [x] **Task 20.3: Automated Volatility Surface & Skew Term Structure Model (COMPLETED ✅)**
  - **Black-76 & Greeks Engine** (`core/volatility/black_scholes.py`): Analytical Black-76 pricer, closed-form Greeks ($\Delta, \Gamma, \nu, \Theta$), and Newton-Raphson implied volatility inverter with bisection boundary fallbacks.
  - **Deribit Options Feed** (`core/volatility/options_feed.py`): Unauthenticated public options book summary ingestion (`get_book_summary_by_currency`), instrument string regex parser (`BTC-25DEC26-104000-C`), and calibrated fallback chain generator.
  - **25-Delta Skew Engine** (`core/volatility/skew_engine.py`): Multi-tenor 25-delta put and call IV solver, absolute and relative skew calculation, and 4-state structural regime classifier (`DEEP_PUT_SKEW`, `MODERATE_PUT_SKEW`, `NEUTRAL_SKEW`, `CALL_SKEW_PREMIUM`).
  - **Constant-Maturity Term Structure** (`core/volatility/term_structure.py`): Interpolated ATM IV curve across standard tenors (7d, 14d, 30d, 60d, 90d, 180d) and slope metric for `CONTANGO`, `FLAT`, or `BACKWARDATION` identification.
  - **2D Volatility Surface Grid** (`core/volatility/surface_engine.py`): Regularized 2D matrix ($Moneyness \in [0.70, 1.30]$ vs. Tenor Days) with bilinear surface interpolation.
  - **Net Dealer GEX & Max Pain** (`core/volatility/gex_engine.py`): Dealer gamma exposure profile per strike, dollar gamma per 1% move, regime classification (`POSITIVE_PINNING` vs `NEGATIVE_EXPLOSIVE`), and options Max Pain strike solver.
  - **Risk Engine Integration** (`core/volatility/risk_integrator.py`): Dynamic tail-risk multiplier $M_{\text{tail}} \in [0.40, 1.05]$ seamlessly scaling Half-Kelly sizing to safeguard against volatility shocks and put skew spikes.
  - **REST API Routes** (`core/volatility/routes.py`, `app.py`): Mounted `/api/volatility/summary`, `/api/volatility/surface`, `/api/volatility/skew`, `/api/volatility/term-structure`, and `/api/volatility/gex`.
  - **Frontend Institutional Desk** (`frontend/src/components/VolatilitySurfaceDesk.tsx`, `frontend/src/App.tsx`, `frontend/src/services/api.ts`): Interactive cockpit with KPI metrics, term structure curve, 2D surface heatmap, 25-delta skew table, and GEX/Max Pain strike distribution.
  - **Verification & Tests** (`tests/test_task20_volatility_surface.py`): 22/22 unit and integration tests passing 100% green; zero TypeScript errors on `npm run build`.

---

## 🚀 Phase 21: Live Exchange Trading Launch Gatekeeper & Real-Money Readiness Checklist (COMPLETED ✅)
- [x] **Task 21.1: Multi-Exchange Live Balance & Account Readiness Probe (`core/execution/account_probe.py`)**
  - Live query of spot and perpetual margin balances on Binance and Bybit via authenticated signers.
  - Multi-exchange equity aggregation, free cash tracking, and deterministic calculation of constitutional 1.5% single-trade equity cap and 6.0% portfolio heat ceiling.
  - Fail-closed error diagnostics when vault is locked or API credentials unconfigured.
- [x] **Task 21.2: Constitutional Pre-Flight Safety Lock & Live Key Vault Validator (`core/execution/live_gatekeeper.py`)**
  - Strict 6-checkpoint non-bypassable pre-flight evaluation: (1) Vault Master Key derived via KMS/HSM, (2) Master Kill-Switch operational, (3) Clock drift $< 500$ms on both venues, (4) Daily drawdown counter below 3.0% circuit breaker, (5) Sizing conforms to 1.5% single-trade equity cap, (6) Explicit `LIVE_TRADING_ENABLED=true` environment authorization.
  - Emits immutable `LIVE_PREFLIGHT_VERDICT` audit events to `audit_bus`.
- [x] **Task 21.3: Real-Time Telegram Live Trading Commander & Event Alerting (`core/telegram_live_desk.py`, `core/telegram/handlers.py`)**
  - 4-times daily automated reporting strictly adapted to Bangladesh Standard Time (BST = UTC+6 / Asia/Dhaka):
    - 08:00 AM BST: Morning Asian & Global Macro Briefing
    - 02:00 PM BST: Midday / European Session Open & Liquidity Pulse
    - 08:00 PM BST: US Session Open & Critical Catalyst Watch
    - 10:00 PM BST: "What AI Learned Today" Comprehensive Research & Risk Dossier
  - High-priority macro flash reports for major releases (CPI, Core CPI, FOMC, NFP) reporting Actual vs Forecast vs Previous, Surprise Delta, BTC/ETH displacement, IV crush %, and tactical risk desk directives.
  - Single-use HMAC-SHA256 2-phase confirmation action tokens for Telegram live operational commands (`/live_status`, `/live_preflight`, `/live_canary`, `/ai_learned`, `/macro_flash`).
- [x] **Task 21.4: Live Canary Dry-Run with Micro-Notional Orders ($10 - $25) (`core/execution/live_canary_runner.py`)**
  - High-precision micro-notional canary order executor strictly bounded between $5.00 and $25.00 USD.
  - Evaluates all 6 constitutional safety gates prior to any order creation.
  - Safe dry-run simulation mode computing simulated quantities, reference prices, and ACK latency without placing real capital at risk.
  - Live execution mode transmits micro-orders to Binance/Bybit, times network roundtrip, and audits fills into `ReconciliationLedger` (`trading_logs.db`).
  - Comprehensive unit and API test suite in `tests/test_phase21_live_gatekeeper.py` (19/19 tests passing 100% green).
- [x] **Task 21.5: Frontend Live Launchpad Desk & Canary Operator Panel (`frontend/src/components/LiveLaunchpadDesk.tsx`, `frontend/src/App.tsx`)**
  - Integrated dedicated `🛡️ Live Launchpad` tab in terminal bottom navigation.
  - Interactive multi-venue balance scorecard (Binance + Bybit + aggregate equity + free cash).
  - 6-Point Constitutional Safety Lock visual checklist with real-time status indicators.
  - Interactive Micro-Canary Launcher ($5 - $25) supporting dry-run simulation and authorized live order transmission.
  - Bangladesh Standard Time (BST = UTC+6) automated briefing schedule monitors and manual test dispatchers.

---

## 🚀 Phase 22: Live Production Exchange Integration & Real-Money Canary Burn-In (COMPLETED ✅)

- [x] **Task 22.1: Production Exchange API Credential Provisioning & Fail-Closed Vault Hardening (`core/auth/credential_vault.py`, `core/execution/account_probe.py`, `core/execution/live_gatekeeper.py`) (COMPLETED ✅)**
  - Authenticated AES-256-GCM vault with Cloud KMS / HSM Enclave support and in-memory zeroization of sensitive key buffers.
  - Strict fail-closed positive withdrawal-disabled proof for Binance (`enableWithdrawals == False`) and Bybit (`withdraw` not in `Wallet` permissions); rejects unknown/unverified capabilities.
  - Multi-tier probe architecture separating unauthenticated ping from authenticated HMAC account and restrictions probing.
  - Capability firewall in `LiveExecutionGatekeeper` (Gate 1b: `withdrawal_allowed == False` required for order clearance).
  - Immediate revocation protocol with pub/sub event listeners invalidating gatekeeper capability caches and exchange sessions.
- [x] **Task 22.2: Institutional Micro-Canary Burn-In ($10 - $25 USD) & Symbol Constraint Engine (`core/execution/live_canary_runner.py`, `core/execution/symbol_constraints.py`) (COMPLETED ✅)**
  - **Symbol Constraint Engine (`core/execution/symbol_constraints.py`)**: Sizing strictly floors down quantization to `step_size` and `tick_size`; rejects orders violating `minNotional`, `minQty`, or canary bounds ($10-$25) with zero automatic upward rounding.
  - **Monotonic Latency Telemetry**: Nanosecond monotonic timing separating dispatch-to-ACK transit latency from fill latency; enforces <500ms ACK SLA with alert flags.
  - **Ambiguous Timeout & Idempotency**: HTTP timeout transitions safely to `UNKNOWN_EXECUTION_STATE` with zero blind retry; unique constraint on `client_order_id` in `canary_execution_ledger` guarantees idempotency.
  - **Operator Desk Cockpit (`frontend/src/components/LiveLaunchpadDesk.tsx`)**: Real-time capability badges (`Trading: ENABLED`, `Withdrawals: DISABLED (SAFE)`, `RTT: X.Xms`), monotonic latency breakdown, and SLA indicators.
  - **Verification**: 24/24 unit/integration tests passing in `tests/test_phase22_canary_verification.py`; M18 cryptographic certification untouched and active (14 gates / 149 tests).
- [x] **Task 22.3: Institutional Capital Governance & Walk-Forward Escalation Protocol (`core/execution/capital_governor.py`)**
  - **Risk Ceiling Primacy**: Sizing strictly bounded by $\text{effective\_risk} = \min(\text{strat}, \text{tier}, \text{heat}, \text{DD}, \text{parent\_1.5\%})$. Escalator can lower ceilings but never override lower risk gates.
  - **Dual-Constraint Enforcement**: Simultaneously validates $\text{order\_risk} \le \text{tier\_risk\_budget}$ and $\text{notional} \le \text{tier\_notional\_cap}$ with stricter constraint winning.
  - **8-State Lifecycle with `*_ELIGIBLE` Gates**: `PAPER` $\to$ `CANARY_ELIGIBLE` $\to$ `CANARY` $\to$ `MICRO_ELIGIBLE` $\to$ `MICRO_LIVE` $\to$ `SCALED_ELIGIBLE` $\to$ `SCALED_LIVE` $\to$ `PRODUCTION_ELIGIBLE` $\to$ `PRODUCTION`.
  - **Contextual DSR with Multi-Testing Trials ($M$)**: Evaluates Deflated Sharpe Ratio against maximum expected random Sharpe under $M$ trials (Bailey & López de Prado, 2014).
  - **Demotion State Machine with Hysteresis**: 24h cooldown, recovery requirements, and fail-closed freeze states on daily drawdown or kill-switch triggers.
  - **Downward-Only Clamping**: Administrative `/clamp` endpoint strictly rejects upward promotion attempts (`MANUAL_PROMOTION_FORBIDDEN`).
  - **Cryptographic Production Boundary**: Tier 8 requires cold HMAC-SHA256 operator token (<60s drift SLA).
  - **Immutable Decision Ledger**: Durable `capital_escalation_decisions` audit trail in SQLite `trading_logs.db`.
  - **Integrated into Live Gatekeeper & UI**: Gate 7 added to `LiveExecutionGatekeeper` and Cockpit UI added to `LiveLaunchpadDesk.tsx`.
  - **Verified with 14/14 Tests Passing**: `tests/test_phase22_capital_governor.py` 100% green.

---

## 🚀 Phase 23: Scaled Multi-Venue Execution, Dynamic Slippage TCA & Automated Delta Hedging (COMPLETED ✅)

- [x] **Task 23.1: Transaction Cost Analysis (TCA) Engine (`core/execution/tca_engine.py`)**
  - **Perold (1988) Implementation Shortfall (IS) Decomposition**: Decomposes total execution slippage into Delay Cost, Spread Cost, Market Impact, and Direct Brokerage/Exchange Fees with respect to Decision Price ($P_{\text{dec}}$).
  - **Signed Cost Accounting**: Enforces institutional conventions where positive values represent cost/drag ($+$bps) and negative values represent price improvement/alpha ($-$bps).
  - **Multi-Horizon Post-Trade Markouts**: Evaluates mid-quote trajectory at 1s, 5s, 30s, 60s, and 300s post-fill to measure adverse selection and toxic routing.
  - **Telemetry & Persistence**: Durable SQLite storage in `tca_execution_ledger` with aggregated VWAP, total shortfall bps, and fee tracking.
- [x] **Task 23.2: Automated Multi-Venue Delta & Basis Hedger (`core/execution/delta_hedger.py`)**
  - **Risk Governor Primacy**: Neutralizes portfolio inventory risk without alpha-generation authority; strictly governed by Live Gatekeeper, Capital Governor, Master Kill Switch, and 1.5% equity cap.
  - **Multi-Venue Net Delta Aggregation**: $\Delta_{\text{net}} = \sum w_i \Delta_i$ across Binance and Bybit spot and perpetual positions.
  - **Non-Linear Threshold Neutralization**: Generates hedge orders $Q_{\text{hedge}} = -\Delta_{\text{net}}$ when $|\Delta_{\text{net}}| > 0.05$ BTC with basis and annualized funding carry yield metrics.
  - **Fail-Closed Timeout Defense**: Transitions ambiguous timeouts to `HEDGE_UNKNOWN_EXECUTION` with zero blind retries; separate safe delta flattening path from panic liquidation.
- [x] **Task 23.3: Cross-Venue Collateral Governor (`core/execution/collateral_governor.py`)**
  - **Real-Time Collateral Monitoring**: Aggregates equity, maintenance margin, and initial margin utilization across all connected venues.
  - **Fail-Closed Freshness Check**: Flags venues as `STALE` and blocks dependent risk calculations if telemetry is older than 30 seconds.
  - **4-Tier Health Classification**: `NORMAL` (<50%), `CAUTION` (50-70%), `DANGER` (70-85%), and `LIQUIDATION_RISK` (>85%).
  - **Advisory Authority Only**: Emits rebalancing recommendations and margin deficit alerts with zero automatic asset transfer authority.
- [x] **Task 23.4: SOR Dynamic Slicing Failover & Toxic Flow (VPIN) Protection (`core/execution/sor_failover.py`)**
  - **Position-Aware Remaining Quantity**: $Q_{\text{rem}} = Q_{\text{target}} - Q_{\text{filled}} - Q_{\text{open}}$ preventing overfill and slice duplication.
  - **Latency & Consecutive Failure Degradation**: Automatically demotes venue priority when ACK latency exceeds 1,000ms or 2 consecutive child slice failures occur.
  - **Toxic Flow (VPIN) Circuit Breaker**: Pauses discretionary slicing when Volume-Synchronized Probability of Toxicity (VPIN) $\ge 0.70$ while keeping protective stop-loss orders fully active.
  - **Fail-Closed Child Slice State Tracking**: Halts parent slicer immediately if any child order enters `UNKNOWN` execution state.
- [x] **Task 23.5: Institutional Execution & TCA Cockpit UI (`frontend/src/components/ExecutionTCACockpit.tsx`, `frontend/src/App.tsx`, `frontend/src/services/api.ts`)**
  - Institutional Obsidian terminal tab (`Execution & TCA`) with 4 interactive dashboards:
    1. TCA Waterfall & Markout Profile (Perold IS decomposition, 5-horizon markout trajectory, execution logs).
    2. Delta & Basis Hedger (Net delta gauge, basis carry tracking, 2-phase authorized hedge dispatch, emergency delta flattening).
    3. Collateral Governor Matrix (Venue margin gauges, rebalancing advisory, fail-closed staleness alerts).
    4. SOR Failover & VPIN Radar (Dynamic slice router health, latency telemetry, VPIN toxicity meter, emergency abort slicing).
  - Production frontend build verified 100% green (`npm run build`).
- [x] **Task 23.6: Adversarial & Institutional Verification Suite (`tests/test_phase23_tca_and_hedging.py`)**
  - 43 adversarial and unit test scenarios covering Perold decomposition, markouts, delta aggregation, fail-closed timeout defense, collateral rebalancing, SOR failover, and VPIN circuit breaker.
  - 43/43 tests passing (100% green).
  - Milestone 18 Production Pass certification verified active and untouched (14 gates / 149 tests).

---

## 🛡️ Phase A: Human-Controlled Live Execution Clearance (WebAuthn / FIDO2 Hardware Key Gate) (COMPLETED ✅)

- [x] **Task A.1: Domain-Isolated Security Store (`core/auth/security_store.py`)**
  - High-security storage engine located exclusively in `data/security.db` with SQLite WAL mode and PRAGMA foreign keys.
  - Complete domain isolation: leaves `core/database.py` and M18 execution ledgers (`trading_logs.db`) completely untouched.
  - Atomic single-use challenge creation and consumption with strict TTL expiration, preventing replay attacks.
  - Zero private keys, master passphrases, or challenge secrets in logs or AI memory.
- [x] **Task A.2: FIDO2 / WebAuthn Hardware Security Key Manager (`core/auth/hardware_key.py`)**
  - Official W3C Level 3 standard WebAuthn protocol validation using `webauthn>=3.0.0` library.
  - Counter semantics: allows authenticators reporting `0` without error; detects counter rollbacks (`new_counter <= stored_counter` when `stored > 0`) as cloned token/replay attack (`HARDWARE_KEY_COUNTER_ANOMALY`).
  - Origin and RP ID validation; User Presence (UP) enforcement.
  - Issues time-bounded (15-minute TTL) Live Clearance Sessions (`ClearanceSession`) bound to client `session_id`.
  - Cascading revocation: revoking a hardware credential instantly invalidates all associated active clearance sessions.
- [x] **Task A.3: Gate 8 in Live Execution Gatekeeper (`core/execution/live_gatekeeper.py`)**
  - Fail-closed Gate 8 (`checks["hardware_clearance_active"]`): blocks all live production order dispatch without an active, unexpired, unrevoked clearance session.
  - Bypassed in TESTNET and PAPER mode to ensure non-blocking test workflows.
  - **Constitutional Risk Primacy**: FIDO clearance pass NEVER bypasses quantitative risk boundaries (1.5% equity cap, daily drawdown, or Master Kill Switch).
- [x] **Task A.4: Live Route & Canary Runner Protection (`core/execution/live_routes.py`, `core/execution/live_canary_runner.py`)**
  - Added `session_id` parameter to `/api/live/protected-order` and `/api/live-canary/run`.
  - Rejection with deterministic error codes: `HARDWARE_KEY_CLEARANCE_REQUIRED`, `HARDWARE_KEY_CLEARANCE_EXPIRED`, `HARDWARE_KEY_NO_CREDENTIALS`.
- [x] **Task A.5: FastAPI REST Interface (`core/auth/hardware_key_routes.py`, `app.py`)**
  - Endpoints mounted at `/api/auth/hardware-key`: `/status`, `/register/options`, `/register/verify`, `/authenticate/options`, `/authenticate/verify`, `/clearance/revoke`, `/credential/revoke`.
- [x] **Task A.6: Institutional Frontend Cockpit & Modal (`frontend/src/components/HardwareKeyModal.tsx`, `LiveLaunchpadDesk.tsx`, `RiskFirstOrderDesk.tsx`, `frontend/src/services/api.ts`)**
  - Interactive WebAuthn dialog supporting physical security key touch ceremonies via `navigator.credentials.get` and enrollment via `navigator.credentials.create`.
  - Gate 8 card in LiveLaunchpadDesk 8-Gate Preflight Checklist.
  - Hardware clearance status badge and toggle protection in RiskFirstOrderDesk.
- [x] **Task A.7: Comprehensive Adversarial Verification Suite (`tests/test_phase_a_live_clearance.py`)**
  - 22/22 tests passing covering isolated store, registration, authentication, counter anomaly defense, single-use anti-replay, Gate 8 fail-closed, and constitutional risk primacy.
  - Full Milestone 18 Production Pass certification verified 100% active (14 gates / 149 tests green).
  - 147/147 Jest test suites passing, frontend TypeScript build 100% green.

---

## 🔏 Phase B: Dual-Profile Windows Authenticode Code Signing Pipeline (COMPLETED ✅)

- [x] **Task B.1: Dual-Profile Code Signing Engine (`scripts/sign_windows_binaries.py`)**
  - Supports `DEVELOPMENT` (self-signed allowed, clearly labeled non-production) and `PRODUCTION` (commercial Authenticode or Azure Trusted Signing required).
  - Institutional Rule: If `PRODUCTION` profile is selected without commercial Authenticode credentials, HARD STOP (`RELEASE_BLOCKED`). Never disguise self-signed as production.
  - HTTPS RFC-3161 timestamping (`https://timestamp.digicert.com` and `http://timestamp.digicert.com` for PowerShell).
  - Binary signature verification via `Get-AuthenticodeSignature` and `signtool.exe`.
  - Machine-readable output: `release/CODE_SIGNING_REPORT.json`.
  - Secret safety: zero passwords or keys in logs or repository files; `.pfx` files ignored in `.gitignore`.
- [x] **Task B.2: Development Self-Signed Cert Generator (`scripts/generate_test_cert.ps1`)**
  - Exports dev certificate with explicit non-production subject: `CN=Crypto Brain Terminal Development, OU=Development Only - Not For Production, O=CBT Dev`.

---

## 🌐 Phase C: Machine-Enforced Watch-Only Web3 & Multi-RPC Quorum Engine (COMPLETED ✅)

- [x] **Task C.1: Multi-RPC Quorum Client (`core/web3/rpc_client.py`)**
  - Redundant RPC pools across Ethereum, Arbitrum, BSC, Polygon, and Solana.
  - Mathematical consensus: requires $\ge 2$ agreeing nodes to confirm state.
  - Freshness monitoring: `FRESH`, `STALE`, `DEGRADED`, `DISAGREEMENT`, `UNAVAILABLE`.
  - Read-only queries: `eth_getBalance`, `getBalance`, and ERC-20 `balanceOf`. Zero transaction signing/broadcast routines.
- [x] **Task C.2: Watch-Only Wallet Storage with Anti-Key Invariant (`core/web3/wallet_store.py`)**
  - Stores public addresses in SQLite `web3_watch_wallets` with hard constraint `is_watch_only = 1`.
  - Rejects private keys (64-char hex) and seed phrase mnemonics with `Web3SecurityViolationError`.
- [x] **Task C.3: Capital Isolation Firewall & Portfolio Aggregator (`core/web3/portfolio_aggregator.py`)**
  - Strict separation: `OBSERVED_TOTAL_EQUITY` = `EXECUTION_AVAILABLE_CAPITAL` (exchange margin) + `WATCH_ONLY_EQUITY`.
  - Guarantees external wallet capital cannot be used by the Capital Governor for order sizing.
- [x] **Task C.4: FastAPI REST Router (`core/web3/web3_routes.py`, `app.py`)**
  - `/api/web3/wallets`, `/api/web3/balances`, `/api/web3/rpc-status`, `/api/portfolio/aggregated-equity`.
- [x] **Task C.5: Adversarial Unit & Invariant Suite (`tests/test_web3_watch_only_invariant.py`)**
  - 15/15 tests passing: AST scan for zero signing routines, 3-of-3 consensus, 2-of-3 fault tolerance, split-brain disagreement, key rejection, and capital firewall isolation.

---

## ⚡ Phase D: 1,000-Slice Stress Matrix & Destructive Crash-Recovery Lab (COMPLETED ✅)

- [x] **Task D.1: 1,000-Slice Fault Injection Stress Harness (`scripts/run_testnet_stress_drills.py`)**
  - 1,000 micro-slices across Binance, Bybit, and Hyperliquid with synthetic fault matrix (jitter, packet loss, duplicate ACKs, out-of-order execution, partial fills).
  - Verified: $\sum q_i = Q_{\text{target}}$ (100% quantity conservation), zero duplicate economic fills, zero orphaned slices, zero negative inventory.
  - Emits `release/STRESS_DRILL_REPORT.json`.
- [x] **Task D.2: Destructive Crash-Recovery Invariant (`tests/test_testnet_stress_drills.py`)**
  - Tested: Order accepted on exchange $\to$ CTB process killed before ACK $\to$ CTB restarts $\to$ startup reconciliation queries exchange $\to$ zero duplicate order submitted.

---

## 📦 Phase E: Installer Lab, 17-Point Blocker Matrix & Release Candidate Certification (COMPLETED ✅)

- [x] **Task E.1: Installer Lab Verification Engine (`scripts/verify_installer.py`)**
  - Validates PE architecture (x64 application binary and NSIS bootstrap stub), file sizing, and Authenticode signature.
- [x] **Task E.2: Cryptographic Checksum Generator (`scripts/generate_release_checksums.py`)**
  - Produces standard GNU `release/SHA256SUMS.txt` for all release assets.
- [x] **Task E.3: Master Production Release Orchestrator (`scripts/build_windows_app.py`)**
  - Automates end-to-end release pipeline across all 17 gates.
  - Evaluates 17-point `RELEASE_BLOCKER_MATRIX`.
  - Produces `release/RELEASE_MANIFEST.json` and `release/RELEASE_CERTIFICATION.json`.
  - Built binaries: `release/CTB_Setup_v3.0.0.exe` (113 MB) and `release/win-unpacked/ctb.exe` (234 MB).
  - **Release State Machine**: Successfully advanced to `RELEASE_CANDIDATE`.
  - **Institutional Rule Enforced**: State machine paused awaiting explicit Human Release Approval Gate before transitioning to `PRODUCTION_RELEASED`.


---

## 🔬 Milestone 31: Continuous Forward Validation & Research League (COMPLETED ✅)

- [x] **Task 31.1: Strategy League Registry & SQLite Store (`core/intelligence/forward_validation/strategy_league.py`)**
  - Append-only SQLite WAL persistence with zero survivorship bias.
  - Parameter hashing and admission state machine (`PENDING_APPROVAL`, `ADMITTED`, `ACTIVE_EVALUATION`, `SUSPENDED`, `REJECTED`, `GRADUATED`).
- [x] **Task 31.2: Live Market Data Gateway & Normalizer (`core/intelligence/forward_validation/gateway.py`, `orderbook_tracker.py`)**
  - Multi-venue normalization (Binance, Hyperliquid) with 6-tier nanosecond timestamps.
  - Reconnect boundary detection and sequence gap quarantine.
- [x] **Task 31.3: Realistic Paper Fill Simulator (`core/intelligence/forward_validation/paper_fill_simulator.py`)**
  - `APPROXIMATE_AGGREGATED_L2` execution model with VWAP depth walking.
  - Zero-bypass simulation isolation (`SIMULATION_ONLY_CANCEL`).
- [x] **Task 31.4: Microstructure Markout Engine (`core/intelligence/forward_validation/markout_engine.py`)**
  - Evaluates 100ms, 1s, 5s, 30s horizons across mid-price, executable, and net markout trajectories.
- [x] **Task 31.5: Forward Performance Ledger & Drift Detector (`core/intelligence/forward_validation/forward_ledger.py`, `drift_detector.py`)**
  - 5-axis drift detection with Kolmogorov-Smirnov statistical tests.
- [x] **Task 31.6: Automated Suspension Controller (`core/intelligence/forward_validation/suspension_controller.py`)**
  - Instant containment for adverse markouts, drawdown limit breaches, and feed dropouts.
- [x] **Task 31.7: Adversarial Verification Battery (`tests/intelligence/test_milestone31_forward_validation.py`)**
  - 40/40 tests passing green; 174/174 intelligence regression suite passing.

---

## 🏛️ Milestone 31-R: Forward Evidence Hardening & Qualification Decision Engine (COMPLETED ✅)

- [x] **Task 31-R.1: Sealed Strategy Constitution Manifest (`core/intelligence/forward_validation/strategy_manifest.py`)**
  - Cryptographically hashed YAML/JSON specification binding genome ID, research hash, dataset manifest, and microstructure execution parameters.
  - Permanent firewall invariant: `real_capital_enabled = False`.
- [x] **Task 31-R.2: Structured Failure Memory Store (`core/intelligence/forward_validation/failure_memory.py`)**
  - Append-only SQLite WAL store recording observed failure boundaries, trigger classifications, and adverse markout bps.
- [x] **Task 31-R.3: Machine-Readable Evidence Ledger & 4-Denominator Gate (`core/intelligence/forward_validation/evidence_ledger.py`)**
  - Enforces the strict **4-Denominator Rule**: $\text{raw\_observations} = \text{eligible\_observations} + \text{excluded\_observations}, \text{eligible} \ge \text{executed}$.
  - Zero silent drop filtering; feeds telemetry, monotonic clock verification, and chained SHA-256 hash manifest.
- [x] **Task 31-R.4: Multi-Gate Institutional Qualification Engine (`core/intelligence/forward_validation/qualification_engine.py`)**
  - 5-state verdict: `QUALIFIED | CONDITIONAL | QUARANTINED | REJECTED | INSUFFICIENT_DATA`.
  - Evaluates 8 institutional proof obligations including denominator conservation, $N \ge 30$ minimum sample power, positive 95% markout CI lower bound, feed continuity $\ge 99.5\%$, and zero capital bypass.
- [x] **Task 31-R.5: Emitted Qualification Dossiers & Verification (`docs/research/`, `scripts/research/run_m31_r_qualification.py`)**
  - Emitted `M31_R_EVIDENCE.json`, `M31_R_DECISION.json`, `M31_R_HASH_MANIFEST.json`, `M31_R_FORWARD_EVIDENCE_DOSSIER.md`.
  - 12/12 dedicated tests passing in `tests/intelligence/test_milestone31_r_evidence_hardening.py` (186/186 intelligence suite green).

---

## 🔒 Milestone 31.5: Qualification Parameter Freeze Gate (COMPLETED ✅)

- [x] **Task 31.5.1: Qualification Freeze Registry (`core/intelligence/forward_validation/qualification_freeze.py`)**
  - Locks qualified strategy parameters and manifests with immutable SHA-256 freeze tokens (`FREEZE-SHA256`).
  - Blocks runtime parameter mutation, lookahead back-patching, and unfreezing without re-qualification.
  - Emitted `docs/research/M31_5_FREEZE_MANIFEST.json`.

---

## 🤖 Milestone 32: Physical Testnet Burn-In Campaign & Multi-Strategy Allocation (COMPLETED ✅)

- [x] **Task 32-A: Deterministic Daemon Engineering (`core/execution/testnet/daemon_orchestrator.py`)**
  - Non-adaptive testnet daemon orchestrator with strict admission control requiring M31.5 freeze tokens.
  - Multi-dimensional health monitor: Heartbeat, Feed Quality, Execution Venue, Risk Gate, and Clock Drift.
  - Dual monotonic clocks (`wall_clock` vs `effective_qualified_time`) enforcing exact time conservation:
    $$H_{\text{elapsed}} = H_{\text{qualified}} + H_{\text{disqualified}}$$
  - Lost-ACK finite state recovery matrix (`SUBMITTED` $\to$ `UNKNOWN` $\to$ `RECONCILING` $\to$ `CONFIRMED_FILLED` / `CONFIRMED_REJECTED` / `PARTIALLY_FILLED` / `RECOVERY_FAILED` $\to$ `EMERGENCY_HALT`).
  - Tested in `tests/execution/test_milestone32_a_daemon.py` (10/10 tests passing).
- [x] **Task 32-B: Multi-Strategy Ensemble Allocator (`core/execution/strategy_gateway/ensemble_allocator.py`)**
  - Dual operating modes: `RESEARCH_MODE` (strictly static equal weights) vs `TESTNET_MODE` (bounded adaptation via empirical markouts).
  - Decomposed 1.5% equity cap into 7 asset-quantity ceilings:
    $$Q_{\text{approved}} = \min(Q_{\text{quantity}}, Q_{\text{notional}}, Q_{\text{margin}}, Q_{\text{loss}}, Q_{\text{strat\_risk}}, Q_{\text{port\_risk}}, Q_{\text{liquidity}})$$
  - Monotonic risk gating ($Q_{\text{approved}} \le Q_{\text{requested}}$), unverified freeze token rejection, and SQLite WAL allocation ledger.
  - Tested in `tests/execution/test_milestone32_b_allocator.py` (9/9 tests passing).
- [x] **Task 32-C: 336-Hour Campaign Integrator (`core/execution/testnet/campaign_daemon_integrator.py`)**
  - Autonomous coordinator simulating a 14-day (336-hour) continuous burn-in campaign.
  - Integrates freeze registry, daemon orchestrator, ensemble allocator, and simulated market/order streams.
  - Tested in `tests/execution/test_milestone32_c_campaign.py` (6/6 tests passing).
- [x] **Task 32-R: Burn-In Evidence Review & Qualification Dossier (`core/execution/testnet/burn_in_evaluator.py`, `scripts/execution/run_m32_burn_in_evaluation.py`)**
  - Evaluates the 7 physical burn-in proof obligations (Time conservation, $\ge 300\text{h}$ qualified uptime, zero lost ACK ambiguity, zero overfills, 1.5% equity cap preservation, checkpoint durability, permanent capital isolation).
  - Emits formal machine-readable dossiers in `docs/execution/`:
    - `M32_R_BURN_IN_DOSSIER.md` (`🟢 QUALIFIED`, 310h/336h qualified uptime, 100% time conservation).
    - `M32_R_DECISION.json`
    - `M32_R_EXECUTION_QUALITY_REPORT.json`
    - `M32_R_RECONCILIATION_REPORT.json`
  - Tested in `tests/execution/test_milestone32_r_burn_in_review.py` (7/7 tests passing). Full M32 battery: 32/32 tests passing.
  - Milestone 18 Production Pass certified untouched and active (149/149 tests).

---

## ⚡ Milestone 33: Multi-Venue Synthetic Cross-Arbitrage & Basis Dispersion Engine (COMPLETED ✅)

- [x] **Task 33.1: Cross-Venue Synthetic Basis & Spread Model (`core/intelligence/synthetic_basis_engine.py`)**
  - Spot vs Perpetual basis modeling across Binance, Bybit, and Hyperliquid L1.
  - Real-time funding rate carry dispersion, borrow rate surface estimation, and cointegration testing ($p < 0.01$).
  - Ornstein-Uhlenbeck mean-reversion speed ($\kappa$) and half-life estimation ($\tau = \ln(2)/\kappa$).
  - Epistemic taxonomy tagging (`[FACT]`, `[INFERENCE]`, `[HYPOTHESIS]`).
- [x] **Task 33.2: Dual-Leg Execution & Synthetic Fill Reconciliation (`core/execution/strategy_gateway/synthetic_router.py`)**
  - Two-phase commit atomic dual-leg execution with Leg-Risk Fail-Safe.
  - Immediate automated protective unwind of Leg 1 if Leg 2 fails/times out.
  - High-resolution synthetic fill reconciliation, basis slippage attribution, and 4-denominator accounting.
  - SQLite WAL persistence in `synthetic_execution_ledger`.
- [x] **Task 33.3: Basis Risk Governor & Dynamic Delta Neutralizer (`core/risk_engine/basis_governor.py`)**
  - Basis dislocation shock breaker ($|\text{basis}| \le 300\text{ bps}$).
  - Toxic funding inversion alert (blocks negative carry entry).
  - Collateral imbalance shield preventing asymmetric margin depletion.
  - Monotonic 1.5% equity risk cap clamping ($Q_{\text{approved}} \le Q_{\text{risk\_cap}}$).
- [x] **Task 33.4: Adversarial Test Suite (`tests/execution/test_milestone33_synthetic_basis.py`)**
  - 12/12 dedicated adversarial tests passing green; full 56-test regression suite green.
  - Milestone 18 Production Pass certified untouched and active (149/149 tests).

---

## 🌊 Milestone 34: Cross-Venue Collateral Telemetry & Dynamic Liquidity Topology (COMPLETED ✅)

- [x] **Task 34.1: High-Frequency Margin & Collateral Heartbeat Monitor (`core/risk_engine/collateral_monitor.py`)**
  - Sub-second margin level polling and Liquidation Distance Buffer (LDB) estimation across all venues:
    $$\text{LDB} = \frac{|P_{\text{mark}} - P_{\text{liq}}|}{P_{\text{mark}}} \times 10^4$$
  - Multi-tier alert state machine: `NORMAL` $\to$ `ELEVATED_RISK` $\to$ `MARGIN_CALL_WARNING` $\to$ `CRITICAL_EMERGENCY`.
  - Asymmetric liquidation hazard warning when delta-hedged position approaches margin call on one venue while profitable on counter-leg.
- [x] **Task 34.2: Automated Internal Rebalancing Advisory (`core/risk_engine/rebalancing_advisor.py`)**
  - Optimal off-chain / cross-venue transfer trajectory calculator minimizing funding drag and transfer fees.
  - Safe source capacity constraints and projected post-rebalance margin utilization simulation.
  - Constitutional permanent firewall (`real_capital_enabled = False`) emitting advisory plans only.
- [x] **Task 34.3: Dedicated Adversarial Test Suite (`tests/execution/test_milestone34_collateral_topology.py`)**
  - 9/9 tests passing green covering exact LDB math, hazard alerts, rebalancing plans, and M18 isolation.
  - Full 65-test regression suite green (M31-R through M34).

---

## 🚀 Milestone 35: Generation 6 Institutional Platform Release & Packaging (v4.0.0) (PLANNED 🚀)

- [ ] **Task 35.1: 17-Point Production Release Blocker Matrix Audit (`scripts/build_windows_app.py`)**
  - Comprehensive pre-flight check across all 17 release blockers.
- [ ] **Task 35.2: Dual-Profile Authenticode Signing & Timestamping (`scripts/sign_windows_binaries.py`)**
  - Development self-signed vs production Authenticode certificate validation.
- [ ] **Task 35.3: Native Windows Installer Compilation (`release/CTB_Setup_v4.0.0.exe`)**
  - Generate production binary assets and GNU `release/SHA256SUMS.txt`.



---

## 📝 Rules for Updating This Document
1. Mark items `[x]` only when implementation is complete **AND** unit tests are written and passing.
2. Link modified and created files directly.



