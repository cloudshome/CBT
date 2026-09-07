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

## 🔮 Phase 18: Multi-Venue Smart Execution & Microsecond Fill Reconciliation (Upcoming Pipeline)

- [ ] **Task 18.1: Multi-Venue Smart Order Routing (SOR)**
  - Dynamic liquidity-weighted order splitting across Binance Spot and Bybit V5 based on real-time top-of-book depth and fee tier schedules.
- [ ] **Task 18.2: Almgren-Chriss Optimal Execution Schedule Engine**
  - Trajectory optimizer balancing market risk vs execution price impact under volatility and liquidity drift.
- [ ] **Task 18.3: Sub-Millisecond Fill Reconciliation & Slippage Ledger**
  - Persistent SQLite WAL ledger (`reconciliation_ledger.db`) auditing expected vs realized fill price, exchange fee attribution, and post-trade venue latency.
- [ ] **Task 18.4: Production Live-Order Terminal UI Controls**
  - Controlled Live Execution interface in `frontend/src/components/RiskFirstOrderDesk.tsx` guarded by dual-confirmation modal and credential status indicator.
- [ ] **Task 18.5: Pre-Merge Quality Gate & System Preflight Suite Expansion (500+ Tests Target)**

---

## 📝 Rules for Updating This Document
1. Mark items `[x]` only when implementation is complete **AND** unit tests are written and passing.
2. Link modified and created files directly.
3. If new requirements arise, evaluate them against `AGENTS.md` before adding to the Todo list.



