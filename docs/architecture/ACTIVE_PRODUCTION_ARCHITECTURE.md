# CBT / SKY Active Production Architecture (Milestone 74)

> **Document Status:** Active Canonical Reference  
> **Milestone Alignment:** Milestone 74 (Gate 3 — Codebase Cleanup, Active Surface Manifest & Architecture Alignment)  
> **Last Updated:** 2026-11-21  
> **Capital State:** `REAL_CAPITAL_ENABLED = False` | `CAPITAL_MODE = "TIER_0_PAPER"` (Permanently Locked)  
> **Active Surface Manifest:** [`core/governance/active_surface_manifest.json`](file:///c:/Users/azims/CBT/core/governance/active_surface_manifest.json)  

---

## 1. Executive Summary & Core Philosophy

The Crypto Brain Terminal (CBT / SKY) is a quantitative cryptocurrency market-intelligence, strategy discovery, and risk-governed decision system. Following the **M62 Institutional Audit Remediation** and empirical research milestones (M63–M74), the system strictly decouples **Research & Falsification** from **Active Production Execution**.

Architecture Priority:
$$\text{DATA QUALITY} > \text{RISK} > \text{EXECUTION SAFETY} > \text{STATISTICAL VALIDITY} > \text{SIGNAL QUALITY} > \text{UX}$$

In accordance with Level 0 AI Governance (`AGENTS.md`) and Level 1 Constitution (`.specify/memory/constitution.md`):
1. **Real capital is permanently disabled** (`REAL_CAPITAL_ENABLED = False`, `CAPITAL_MODE = "TIER_0_PAPER"`).
2. **Zero Lookahead Bias:** Every signal is evaluated at bar close $t$, executed at $open[t+1]$ (or $open[t+2]$ under delay stress).
3. **Causal Failure Memory:** Hypotheses that fail CP-2 institutional hurdles are permanently archived in `core/autonomous_research/failure_memory.py` to prevent redundant capital allocation or re-testing.

---

## 2. Active Production Architecture & Operational Tiers

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 4-HOUR MARKET UNIVERSE                                 │
│                       [BTCUSDT, ETHUSDT, SOLUSDT, PAXGUSDT]                            │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ (CCXT / Binance REST 4h Candles)
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        TIER 1: ACTIVE PRODUCTION DESK & SHADOW                         │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│  P2_RP Frozen Strategy Engine            │  24/7 Isolated Shadow Runner                │
│  `core/strategies/p2_risk_parity.py`     │  `core/strategies/p2_shadow_runner.py`      │
│  - 4h Snapshot & Regimes                 │  - Evaluates candles after each 4h close    │
│  - Inverse Volatility Weights            │  - Fills paper orders at next bar open      │
│  - Trigger Explainer (EN + BN)           │  - Dedicated ledger: `p2_shadow_ledger.db`  │
└───────────────────────┬──────────────────┴──────────────────────┬──────────────────────┘
                        │ Read-Only Snapshots                     │ Read-Only Telemetry
                        ▼                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      TIER 2: 24/7 OPS & TRADER SURVEILLANCE COMPANIONS                 │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│  P2 Shadow Ops Watchdog (M71)            │  Market Radar & Trader Copilot (M73)        │
│  `core/ops/p2_shadow_watchdog.py`        │  `core/ops/market_radar.py`                 │
│  - Health audit & ledger drift check     │  - Realtime setup & breakout proximity      │
│  - Alert cooldown state engine           │  - EMA200 & Donchian distance tracking      │
│  - Automated daily `.db.gz` backup       │  - Zero-spam 4h cooldown per alert key      │
│  - State DB: `p2_shadow_watchdog_state.db│  - State DB: `market_radar_state.db`        │
└───────────────────────┬──────────────────┴──────────────────────┬──────────────────────┘
                        │ Read-Only JSON / Formatted Payloads
                        ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                       TIER 3: PRESENTATION, APIS & ALERT ROUTING                       │
├─────────────────────┬─────────────────────┬─────────────────────┬──────────────────────┤
│  CLI Commands       │  FastAPI Endpoints  │  Telegram Bot (EN+BN│  Today's Desk GUI    │
│  `cli/daily.py`     │  `app.py`           │  `core/telegram_bot`│  `frontend/src/...`  │
│  - `cbt today`      │  - `/api/desk/today`│  - `/today`         │  - `P2ShadowDesk`    │
│  - `cbt shadow`     │  - `/api/desk/shadow│  - `/shadow`        │  - Watchdog Pill     │
│  - `cbt watchdog`   │  - `/api/desk/watchd│  - `/ops`           │  - Radar Alert Pill  │
│  - `cbt radar`      │  - `/api/desk/radar`│  - `/radar`         │  - Trigger Explainer │
└─────────────────────┴─────────────────────┴─────────────────────┴──────────────────────┘
```

---

## 3. Detailed Component Invariants

### 3.1 Strategy P2_RP (Risk Parity Multi-Asset Macro Engine)
- **File:** `core/strategies/p2_risk_parity.py`
- **Status:** Active Production Benchmark (`ACTIVE_PRODUCTION`).
- **Universe:** 4 assets (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `PAXGUSDT`).
- **Components:**
  - **S1 (Macro Trend):** Donchian-48 Breakout Channel with 200 EMA Regime Filter.
  - **S2-Div (Dual Momentum):** 7-Day Asset Cross-Sectional Momentum.
  - **Allocation:** Inverse-variance (20-day annualized realized volatility) sizing, cash-drag preservation when assets fail trend filters.
- **Trigger Explainer:** Integrated bilingual (English + Bengali) condition explainer evaluating exact breakout bounds, distance to 200 EMA, and volatility allocations.

### 3.2 24/7 Isolated Shadow Runner
- **File:** `core/strategies/p2_shadow_runner.py`
- **Database:** `data/p2_shadow_ledger.db` (Dedicated SQLite ledger, isolated from legacy `data/trading_logs.db`).
- **Mode:** `TIER_0_PAPER` (`REAL_CAPITAL_ENABLED = False`).
- **Lifecycle:**
  - Fired every 4 hours via `cbt-p2-shadow.timer` (10 minutes past bar close: 00:10, 04:10, 08:10, 12:10, 16:10, 20:10 UTC).
  - Fetches fresh closed 4h candles, evaluates `TodayDeskSnapshot`, identifies allocation changes.
  - Computes target units based on current virtual NAV ($10,000 baseline paper capital).
  - Executes fills at actual next bar open with realistic 10 bps slippage + maker/taker cost model.
  - Persists portfolio snapshots and trades with cryptographic row hashes.

### 3.3 24/7 Ops Watchdog & Backup Engine (Milestone 71)
- **File:** `core/ops/p2_shadow_watchdog.py`
- **State Database:** `data/p2_shadow_watchdog_state.db`
- **Backup Directory:** `data/backups/p2_shadow/`
- **Functions:**
  - Performs non-mutating integrity audits on `p2_shadow_ledger.db`.
  - Verifies data freshness (warns if latest snapshot $> 5\text{ hours}$ old).
  - Performs atomic gzip archive of `data/p2_shadow_ledger.db` once every 24 hours, retaining the last 30 daily backups.
  - Sends bilingual (EN + BN) health alerts via Telegram with strict 4h per-incident cooldowns.

### 3.4 24/7 Proactive Market Radar & Trader Copilot (Milestone 73)
- **File:** `core/ops/market_radar.py`
- **State Database:** `data/market_radar_state.db`
- **Nature:** Strictly **Read-Only Pre-Trade Surveillance** (`FORECAST != SIGNAL`).
- **Functions:**
  - Evaluates proximity to Donchian-48 breakout bands (`distance_to_breakout_pct <= 2.0%`).
  - Evaluates EMA200 structural reclaim / cross proximity (`distance_to_ema200_pct <= 1.5%`).
  - Detects volatility compression (20d annualized vol $< 35\%$).
  - Emits structured setup alerts with bilingual (EN + BN) commentary.
  - Enforces a 4-hour per-symbol-per-event cooldown to eliminate telegram noise and spam.

---

## 4. Strategy Lifecycle & Status Table

All quantitative hypotheses tested within SKY are categorized strictly by their empirical qualification status:

| Strategy / Family | Description | Operational Status | Evidence & Reason |
|:---|:---|:---:|:---|
| **Strategy S1** | Donchian-48 Macro Trend + 200 EMA Filter | `ACTIVE_PRODUCTION` | CP-2 Certified in M65 as defensive trend component of `P2_RP`. |
| **Strategy S2-Div** | 7-Day Dual Momentum Rotation | `ACTIVE_PRODUCTION` | CP-2 Certified in M65 as cross-sectional relative strength sleeve of `P2_RP`. |
| **Portfolio P2_RP** | Inverse-Volatility Risk Parity Ensemble | `ACTIVE_PRODUCTION` | Survived multi-year walk-forward stress test across 2022–2026 out-of-sample data. |
| **SMC 15m / Scalping** | Smart Money Concepts order-block scalping | `LEGACY_QUARANTINED` | M62 Institutional Audit eliminated lookahead survivorship bias; degraded expectancy. |
| **Family 2 (Derivatives)** | Funding rate crowding & OI divergence (M63) | `FALSIFIED_M63` | Falsified across 2022–2026 data: negative Sharpe (-0.42), excessive turnover, fee bleed. |
| **Sleeve 3 (Funding Carry)** | Delta-neutral spot/perp funding arbitrage (M67) | `FALSIFIED_M67` | Falsified: DSR 0.0000, 2022 bear regime yield compression (1.2% net vs 8.4% cost drag). |
| **Strategy S4 (Shorting)** | Asymmetric Shorting Engine (M72) | `FALSIFIED_M72` | S4-A & S4-B failed 6/6 CP-2 hurdles (DSR 0.0000, severe squeeze whipsaws during bear rallies). |

---

## 5. Automation & Systemd Timers

The system runs 24/7 on Ubuntu Linux (and supports background service execution on development nodes) via three isolated systemd service/timer pairs located in `deploy/systemd/`:

| Service & Timer | Schedule | Command | Function |
|:---|:---|:---|:---|
| `cbt-p2-shadow.timer` | `00:10, 04:10, 08:10, 12:10, 16:10, 20:10 UTC` | `python -m cli.daily shadow --step` | Advances the 4h shadow ledger and records paper fills. |
| `cbt-p2-watchdog.timer`| `Every 30 minutes` | `python -m cli.daily watchdog --alert` | Audits shadow runner health, manages backups, alerts on drift. |
| `cbt-market-radar.timer`| `Every 1 hour` | `python -m cli.daily radar --alert` | Scans market for pre-breakout setups and sends radar copilot alerts. |

---

## 6. Machine-Verifiable Interfaces (CLI, API, Telegram)

### 6.1 Unified CLI (`cli/daily.py` & `main.py`)
```bash
# Today's Desk snapshot & trigger explanation
cbt today
cbt today --json
cbt today --asset BTCUSDT

# 24/7 Shadow Runner execution
cbt shadow --status
cbt shadow --step

# Ops Watchdog health & backup
cbt watchdog --status
cbt watchdog --alert
cbt watchdog --backup

# Proactive Market Radar
cbt radar --scan
cbt radar --alert
```

### 6.2 FastAPI Endpoints (`app.py`)
- `GET /api/desk/today`: Returns `TodayDeskSnapshot` with current weights, regimes, metrics, and bilingual trigger explanation.
- `GET /api/desk/shadow`: Returns latest shadow portfolio NAV, cash balance, active positions, and recent trades from `p2_shadow_ledger.db`.
- `GET /api/desk/watchdog`: Returns operational health score, freshness status, backup status, and recent watchdog incidents.
- `GET /api/desk/radar`: Returns active market radar status, asset proximity metrics, and triggered setup alerts.

### 6.3 Telegram Bot Commands (`core/telegram/handlers.py`)
- `/today`: Formatted bilingual summary of today's desk allocations and market regimes.
- `/shadow`: Current shadow portfolio NAV, allocation weights, and PnL.
- `/ops`: Operational health report, shadow runner freshness, and last backup status.
- `/radar`: Proactive market radar scan highlighting imminent breakouts and regime shifts.

---

## 7. Certified Protected Surface (Milestone 18)

The Milestone 18 Smart Order Router & Fill Reconciliation execution engine remains certified, cryptographically frozen, and protected:
- **Manifest:** `core/execution/m18_certification_manifest.json`
- **14 Certified Files:** Frozen against modifications.
- **Verification Script:** `python scripts/verify_m18_certification.py`
- **Test Suite:** 149/149 passing adversarial tests (`test_milestone18_sor_and_slicing.py`, `test_milestone18_boss_adversarial.py`, `test_milestone18_final_certification.py`).
- **Rule:** Any change to M18 files invalidates production certification until all 14 gates re-pass.

---

## 8. Machine-Verifiable Active Surface Audit

Governance integrity is maintained via `scripts/audit_active_surface.py` which runs against `core/governance/active_surface_manifest.json`:
```bash
python scripts/audit_active_surface.py
```
This script asserts:
1. Every file in `ACTIVE_PRODUCTION` and `RESEARCH_LAB` exists on disk.
2. `REAL_CAPITAL_ENABLED = False` and `CAPITAL_MODE = "TIER_0_PAPER"` across all operational modules.
3. `STATIC_FALSIFIED_RECORDS` in `core/autonomous_research/failure_memory.py` contains `FALSIFIED_M63`, `FALSIFIED_M67`, and `FALSIFIED_M72`.
