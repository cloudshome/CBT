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

### Priority 12 (P12) — Testing & Quality Assurance

- [ ] **P12.1: Establish Frontend Test Framework**
  - Add Vitest and `@testing-library/react` to `frontend/package.json`.
  - Priority test targets: `TradingViewChart.tsx`, `RiskFirstOrderDesk.tsx`, `PaperTradingPanel.tsx`, `wsStateMachine.ts`, `api.ts`, `decimalMath.ts`.

- [ ] **P12.2: Unit Tests for 26 Untested Core Modules**
  - `api_health_guard.py`, `brain_backup.py`, `command_executor.py`, `data_streamer.py`, `debate_committee.py`, `gap_recovery.py`, `market_state.py`, `memory_vault.py`, `prediction_ladder.py`, `probability_calibrator.py`, `system_evolver.py`, `volatility_profile_regime.py`, `auth.py`, `audit_bus.py`, `multimodal_ingestor.py`, `derivatives_options.py`, `institutional_flows.py`, `macro_liquidity_beta.py`, `physical_supply_shock.py`, `seasonality_cyclical_dna.py`, `sentiment_engine.py`, `stablecoin_velocity.py`, `valuation_cost_basis.py`, `macro_gold_engine.py`, `metrics.py`, `empirical_accumulator.py`.

- [ ] **P12.3: WebSocket Real-Transport Integration Tests**
  - Test WebSocket endpoints (`/ws/terminal` in FastAPI, `/ws` in Express) with live duplex transport: connection drop, message framing, auto-reconnect backoff.

- [ ] **P12.4: Risk Gate Edge Case Tests**
  - `src/middleware/riskGate.ts` daily drawdown and daily loss limit logic is not covered by automated tests. `tests/paper.test.ts` only asserts max open trades and max risk per trade.

- [ ] **P12.5: Concurrent SQLite Write Contention Stress Tests**
  - No test simulates concurrent multi-thread transactions to assert WAL concurrency behavior under load.

- [ ] **P12.6: End-to-End Browser Tests (Playwright/Cypress)**
  - No E2E test suite exists for critical user flows (place paper trade → verify position → check risk desk → close position).

- [ ] **P12.7: Activate Placeholder CI Workflows**
  - `.github/workflows/jules-task.yml` and `.github/workflows/notify-antigravity-on-prototype.yml` contain only echo statements.

### Priority 13 (P13) — Documentation & Operational Polish

- [ ] **P13.1: Fix Port Discrepancy in `SKY_STATUS.md`**
  - Architecture diagram lists Node on `:3001`; `RUNBOOK.md`, `API_REFERENCE.md`, and `docker-compose.yml` all use `:3000`.

- [ ] **P13.2: Update Stale Test Count in `README.md`**
  - README references "pytest — 41 passed" from early development. Suite now spans 45 test files and 220+ tests.

- [ ] **P13.3: Remove Redundant Documentation Stub**
  - `docs/future_work/SKY_MARKET_INTELLIGENCE_ENGINE.md` is a 24-line stub duplicating the root specification's TOC.

- [ ] **P13.4: Add SSL/Certbot Production Setup Guide to `RUNBOOK.md`**
  - RUNBOOK covers cold boots and incident playbooks but lacks Let's Encrypt / Certbot certificate provisioning steps for Nginx.

- [ ] **P13.5: Update `README.md` Architecture Section**
  - Reflect current 45-test suite count, current module inventory, and updated port allocations.

---

## 📝 Rules for Updating This Document
1. Mark items `[x]` only when implementation is complete **AND** unit tests are written and passing.
2. Link modified and created files directly.
3. If new requirements arise, evaluate them against `AGENTS.md` before adding to the Todo list.

