# SKY 24/7 Trading Intelligence & Research Agent — Discovery Report

**Date:** 2026-08-19 (UTC)
**Branch:** `arena/01a01904-sky` from `ce53aef`
**Version inspected:** 2.43.0
**Author:** Arena Agent (automated discovery)
**Prompt sources:** *01 autonomy/read-only boundary, *02 Hermes integration, *03 SEC EDGAR intelligence

---

## 0. Executive Summary

SKY already *is* a read-only, deterministic trading intelligence system. The task is **not to replace SKY with an AI agent** but to wrap SKY in a **reliable 24/7 research & monitoring infrastructure** that answers six questions continuously:

1. What important information changed?
2. Does it matter to SKY?
3. Can SKY test it?
4. Does the evidence support it?
5. What is the risk?
6. Should a human consider this opportunity?

**Architecture decision:**

```
Hermes-style agent  =  researcher + analyst + assistant  (proposes, reads, codes)
SKY engine          =  validator + risk gate + evidence  (proves, blocks, stores)
Human               =  final decision maker              (approves, trades)
```

Do **not** give the agent live-trading, withdrawal, sudo, private-key or main-branch write authority. The agent may *operate* SKY CLI/MCP tools; SKY decides whether the result is evidence.

**Implementation path chosen:** Hybrid lightweight daemon + scheduled workers + MCP/CLI tool surface + systemd supervision. Hermes is valuable as a *pattern* (Skills + MCP) — not as a required runtime. SEC EDGAR is added as a **P-series Fundamental/Event Intelligence Layer**, separate from the technical engine until its event classes show positive out-of-sample expectancy.

---

## 1. Repository Map (what SKY already does correctly)

### 1.1 Top-level
| Path | Role | Verdict |
|---|---|---|
| `main.py` | ~30-command CLI dispatcher, one-command launcher (`python main.py`) with `.venv` bootstrap | Keep. Agent must call this, not replicate it. |
| `config.py` | Env-driven single source of truth (SYMBOL, risk caps, progression ladder, auth, paper, backtest, gold windows) | Keep. Agent reads, never forks. |
| `mcp_server.py` | Zero-dep stdio JSON-RPC MCP, read-only permission map | Keep. Agent's safest interface to SKY. |
| `pyproject.toml` / `requirements.txt` | `numpy, pandas, requests, flask, python-dotenv, pyarrow` | Keep minimal. No Redis/Postgres/React. |
| `ops/hub.py` | Production Ubuntu Hub: FHS layout (`/opt/sky`, `/etc/sky`, `/var/lib/sky`), `sky setup/status/doctor/backup/restore`, systemd units, TLS proxy examples | Keep. Agent's systemd pattern reuses this. |
| `ops/` `systemd` / `proxy` / `first_night.sh` | Deployment artifacts | Extend for `sky-agent.service` |
| `web/app.py` + `web/jobs.py` + `web/api_v1.py` + `web/auth.py` | Dashboard, persisted job queue + SSE, stable `/api/v1` contract, PBKDF2 auth + device tokens | Keep. Daily reports + alerts surface here; jobs queue already persists across reload/restart. |
| `.github/workflows/ci.yml` | Offline `pytest` + `node --check` + sample smoke | Keep. Agent must be offline-testable (`DEMO_MODE=1`). |

### 1.2 `brain/` — the desk brain (read before adding “AI”)
| Module | What it does | Agent relationship |
|---|---|---|
| `risk_gate.py` | **The gate.** Kelly, daily/weekly stop, drawdown ladder, progression, trader-state block, portfolio bucket | Agent is *blocked* by this; never bypasses. |
| `trading_intelligence.py` + `institutional_score.py` | Desk report: confidence ≥80, RR floor 1.5, scenarios, IF/THEN, HOLD/REDUCE/TRAIL/EXIT | Agent's recommendation must reuse this shape (WATCH/CONSIDER/WAIT/AVOID) |
| `full_pipeline.py` + `decision.py` + `context.py` + `styles.py` + `portfolio.py` | End-to-end scan pipeline, macro/FOMC, style routing, crypto bucket | Agent calls `analyze_full()`; does not reimplement. |
| `regime.py` / `mtf.py` / `structure.py` / `hidden_alpha.py` / `sentiment.py` | Regime, multi-timeframe, ICT/SMC, CVD, Fear & Greed | Agent's market-monitor reads these; no duplication. |
| `agents.py` + `brief.py` + `weekly.py` + `ritual.py` + `practice.py` | Morning brief, Watchdog, Paper reviewer, Weekly review, Ritual memory, Practice calibration | Extend, do not replace. New Intelligence Agent is a *peer* of these. |
| `agent.py` + `immune.py` + `channels.py` + `connections.py` | `health_report`, `readiness_strip`, `loop_health`, channel router, staleness/DB/integrity checks | Agent's system-monitor and readiness gate plug in here. |
| `metrics.py` + `analytics.py` + `calibrator.py` + `journal.py` | Win-rate/expectancy/PF/DD, MAE/MFE/Monte Carlo, self-improvement, journal discipline | Agent's expectancy-first checks depend on these. |
| `library.py` + `ask.py` + `coach.py` + `playbooks.py` | RAG, grounded QA, teaching, per-asset playbooks | Agent's research layer may feed the library. |

### 1.3 `engine/` — pure analytics (deterministic)
`signal_engine.py`, `features.py`, `indicators.py`, `structure.py`, `mtf.py`, `regime.py`, `scorer.py`, `hidden_alpha.py`, `sentiment.py`, `correlation.py`, `execution.py`, `lifecycle.py`, `calibration_hook.py` — RSI/MACD/EMA/Supertrend/ADX/Stoch/WaveTrend/BB/ATR/ROC/VWAP/VPOC/OBV, BOS/CHOCH/OB/FVG/sweeps, weighted scoring → `HIGH/MEDIUM/LOW/NO_TRADE`, multi-condition conditional plans. **Do not rebuild.** Agent feeds stored candles into this unchanged.

### 1.4 `data/` — sources + persistence (P10 complete)
| Module | Status | Note |
|---|---|---|
| `store.py` | ✅ | Normalised `Candle` + Parquet hive, PK `(exchange,market,symbol,tf,ts)`, unclosed-candle rule |
| `backfill.py` | ✅ | Paginated, resumable, header-aware backfill (spot+perp), `backfill --from-csv` provenance pin |
| `gaps.py` | ✅ | Gap detect/repair, 1m→5m/15m/1h/4h/1d rollups (master-timeframe invariant) |
| `derivatives.py` | ✅ | Funding/OI/mark/index/basis as time series, PK `(exchange,market,symbol,metric,ts)` |
| `quality.py` + `quality_score.py` | ✅ | Staleness/gap/sanity pillars + 0–100 quality score (edge/curve/sample/plateau) |
| `bybit_client.py` | ✅ | Second venue behind same contract; quirks isolated at adapter |
| `cross_exchange.py` | ✅ | Premium/discount + funding spread probes |
| `ws_client.py` | ✅ | `!forceOrder@arr` + klines streams, reconnect/backoff, offline demo stream |
| `feature_store.py` | ✅ | One wide row per `(symbol,tf,ts)` (22 cols) |
| `binance_client.py` + `sample_client.py` | ✅ | Geo-fallback hosts, `DEMO_MODE=1` determinism |
| `calendar.py` | ✅ | Venue calendars (crypto-24x7 vs XAU-OTC) |
| `backtester.py` | ✅ | Walk-forward (+1h/+4h/+24h), `run_backtest_on_store()` for multi-year offline runs |
| `scorecard.py` + `costs.py` + `strategy_score.py` + `validation.py` + `provenance.py` | ✅ | E_net=E_gross−fees−slip−funding, boxed scorecard (Sharpe/Sortino/Calmar, N_eff), fees-first, sealed OOS, source-key isolation |
| `paper_trading.py` + `simulator.py` + `database.py` | ✅ | Lifecycle (WAITING→OPEN→CLOSED), canonical live book `live_book_rows()` vs `live_open_rows()`, 10+ tables |

### 1.5 Gaps vs. the 24/7 brief

| Requirement in brief | Current SKY | Gap |
|---|---|---|
| 24/7 data collection | Backfill + derivatives + WS tier exist but are **CLI-triggered**, not daemonised | Need supervised daemon + timers + restart policy |
| Market monitoring (BTC/ETH, 5m–1D, structure, volatility) | Engines exist, no continuous poller | Need Market Monitor worker (5m cadence) |
| Derivatives intelligence (funding/OI/liq/basis/CVD) | Collector exists, not scheduled | Wire to scheduler |
| External intelligence (news, GitHub, research, SEC EDGAR) | `data/sources/news.py` + `discord_reader` exist; EDGAR absent; no scoring | Need collectors + scoring + EDGAR event taxonomy |
| Information scoring & filtering | Not present | Need relevance/impact/confidence/urgency/novelty/reliability → LOW/MEDIUM/HIGH/CRITICAL |
| Hypothesis → backtest → expectancy → evidence | Backtester + scorecard exist; no automated hypothesis loop | Need hypothesis store + runner + evidence gate |
| Trading suggestion (WATCH/CONSIDER/WAIT/AVOID) | Desk report does this per-scan; no continuous recommendation stream | Need recommendation builder reusing desk shape |
| Notifications (Telegram/Discord/email) | `output/notifiers.py` exists | Need event-driven dispatcher with rate limits |
| Daily report | `brief.py` + `weekly.py` exist | Need cron-driven daily intelligence report |
| Memory (structured, not free-text) | `database.py` has scans/plans/backtests/paper/agent_runs/journal/ritual/practice | Need `research_hypotheses`, `sec_filings`, `sec_events`, `intelligence_reports`, `market_regime_log` |
| System monitoring (CPU/RAM/disk/logs/staleness) | `immune.py` + `readiness_strip` + `hub.doctor` exist | Need periodic system probe writing to `agent_runs` + alerting at thresholds |
| Security (least privilege, no live creds) | Auth + roles + device tokens already; no live order path | Preserve; agent runs with `read_only` + no exchange secrets |
| GitHub workflow | One PR/session, feature branch → tests → PR → review | Enforce for agent's code changes |

---

## 2. Design — 24/7 Agent Architecture

### 2.1 Topology (Ubuntu 24.04 single Hub)

```
                 Ubuntu 24.04 (SKY Hub: /opt/sky, /etc/sky, /var/lib/sky)
                               │
                               ▼
                    SKY Intelligence Agent  (sky-agent.service, systemd, restart=always)
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
         Data Monitor     Research Agent    System Monitor
              │                │                │
         Market Data      Web/GitHub/EDGAR   CPU/RAM/Disk
         BTC/ETH/GOLD     News/Research     Services/Logs
         5m/15m/1H/4H/1D   SEC 8-K/10-Q/10-K  journald
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                        Data Validation  (quality.py + provenance + staleness)
                               │
                               ▼
                          SKY Engine     (signal_engine, regime, features, scoring)
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
            Regime         Strategy        Risk Gate
            Analysis       Analysis       (hard gate)
               │               │               │
               └───────────────┼───────────────┘
                               ▼
                          Backtest (on store)
                               │
                               ▼
                          Expectancy (R) + N_eff + PF/DD
                               │
                               ▼
                         Evidence Gate (sealed OOS, quality score)
                               │
                               ▼
                      Trading Suggestion (WATCH/CONSIDER/WAIT/AVOID)
                               │
                               ▼
                          Human (final decision)
```

### 2.2 Agent Type Selection

| Option | Fit for 24/7 SKY | Verdict |
|---|---|---|
| Hermes Agent (self-hosted) | Excellent research/coding/MCP but **is** an LLM runtime — idle cost, auth surface | Use the *pattern* (Skills + MCP), not the binary. SKY stays stdlib. |
| OpenHands / Codex | Coding agents, not daemons | For code-creation tasks only, not monitoring |
| MCP-based agent | Controlled tool surface, explicit permissions | **Adopt**: SKY's MCP is already read-only |
| Scheduled workers + event triggers + cheap monitoring + LLM escalation | Low idle CPU, survives reboot, pay-only-when-needed | **Adopt as primary** |
| Custom Python daemon | Full control, systemd-native | **Adopt**: `sky_agent/daemon.py` |

**Decision:** Hybrid — **lightweight Python daemon (systemd) + persisted job queue + interval timers + threshold triggers + MCP/CLI for actions**. LLM (if configured) is only called to *interpret* a high-scoring event, not to poll forever.

```
scheduled jobs
  + event triggers (threshold cross, new filing, data staleness)
  + cheap monitoring (pandas/numpy on stored Parquet)
  + LLM escalation only when scoring == HIGH/CRITICAL
```

### 2.3 24/7 Operation

* `sky-agent.service`  — `Type=simple`, `Restart=always`, `RestartSec=5`, `WatchdogSec=60`
* `sky-agent.timer` (alternative) or daemon's internal `APScheduler`-free loop — survives terminal close, SSH disconnect, reboot (`WantedBy=multi-user.target`)
* Structured logging to journald (`StandardOutput=journal`, no secrets), `logs` subcommand
* Health check: `python main.py agent health` → `brain/immune.py` + `agent.monitor_system`
* Persistent state in SQLite (`intelligence_reports`, `hypotheses`, `market_regime_log`) + Parquet store — no ephemeral RAM-only state
* Graceful shutdown: SIGTERM → drain in-flight poll → checkpoint `last_ts` → exit 0
* Idempotent collectors: PK upsert, same run → zero duplicate rows
* Backoff: exponential (1s,2s,4s,8s,60s cap) on API timeout/rate-limit; SEC fair-access: **≤10 req/s**, declared `User-Agent`

### 2.4 Market Monitoring (what to watch)

Price/BTC/ETH/XAU (config `SYMBOLS`), structure (BOS/CHOCH/sweep/OB/FVG/premium-discount/consolidation), multi-timeframe (5m,15m,1H,4H,1D derived from 1m master), volatility (ATR%, BB width, regime `VOLATILITY_EXPANSION/COMPRESSION`). *Only* using SKY's real definitions (`engine/structure.py`, `engine/regime.py`, `engine/mtf.py`). Derivatives where available: funding, OI, basis, mark/index, CVD, volume spike — stored via `derivatives.py`, never inferred from one tick.

Separation kept explicit per event:

```
FACT          := candle/derivative/CVD value from store or filing acceptance ts
INTERPRETATION:= regime label, “bullish structure”, volume regime
HYPOTHESIS    := “Buy Pullback stronger when 4H bullish AND 1H bullish”
```

### 2.5 Derivatives Information

Monitored via `derivatives.py` time series; liquidation proxy kept honestly named (`liquidation_stats_proxy`). Real `!forceOrder@arr` accumulation is WS-only and only from collector-start — no fake history.

### 2.6-2.7 External Intelligence + Filtering

Sources (in priority order):
1. Market data (own store — Tier 1)
2. Macro calendar (existing `brain/context.py`)
3. Derivatives/positioning (Tier 3)
4. News/RSS (existing `data/sources/news.py`)
5. **SEC EDGAR** (new — 8-K first, then 10-Q/10-K/XBRL)
6. GitHub/research (optional, not in MVP)

**Scoring per event:**

```
relevance   0–10  (to SKY watchlist + primary family sweep_trend_continuation)
impact      0–10  (historical event-study magnitude, if known)
confidence  0–10  (source reliability × data completeness)
urgency     0–10  (time-to-expiry, 8-K acceptance proximity)
novelty     0–10  (not seen in last 7d)
reliability 0–10  (SEC official=10, RSS=6, private=3)
relation    0–10  (matches current regime/setup)
→ weighted sum 0–70 → LOW (<20) / MEDIUM (20–35) / HIGH (35–50) / CRITICAL (>50)
```

Only `HIGH`/`CRITICAL` notify; `MEDIUM` → daily report; `LOW` → stored only.

### 2.8-2.12 SKY Integration, Backtest, Expectancy, Risk

The agent **never invents a strategy**. It proposes a *filtered hypothesis*:

```
Hypothesis H-001:
  Setup:  Buy Pullback
  Filters: 4H trend = bullish AND 1H structure = bullish AND vol = normal/high
  Baseline: Buy Pullback (all regimes) — N, E_R, WR, PF, DD, streak, freq, regime split
```

Runner: `data/backtester.run_backtest_on_store()` on the Parquet store → comparison table → metrics:

```
N, N_eff, win rate, E_R, E_R_net, PF, PF_net, max DD_R, longest streak,
avg win, avg loss, trade freq, regime distribution, Sharpe/Sortino/Calmar
```

Checks: sample ≥100, in-sample vs OOS, overfit/plateau, `quality_score`. **Negative expectancy or small N ⇒ no positive edge (do not tune to green).**

Risk: hard separation `Research → Analysis → Recommendation → Risk Validation → Execution`. Agent owns first three; `brain/risk_gate` owns validation; human owns execution. Agent cannot set `SKY_ALLOW_FORCE_APPROVE`.

### 2.13-2.15 Recommendations, Notifications, Daily Reports

Suggestion shape reuses the desk report:

```
SKY ALERT — <ASSET> [<TF>]
Regime: <bullish/sideways/…>  Volatility: <normal/high>
Detected: <Buy Pullback approaching OB>   [FACT / INTERPRETATION / HYPOTHESIS]
Evidence: <4H bullish, 1H BOS up, vol acceptable, hist +0.57R, N=3356>
Expectancy: +X.XXR (net)  Sample: N/N_eff  Quality: 72/100
Risk: PASS/FAIL/UNKNOWN (blocked_by: …)   Confidence: HIGH/MED/LOW
Recommendation: WATCH / WAIT / CONSIDER / AVOID   Reason: …
Invalidation: <break below OB, funding flip, …>   Sources: …
```

Notifications: Telegram bot primary (already in config), Discord webhook fallback, local `journald` / dashboard banner. Event-driven, deduplicated (`params_hash`), rate-limited.

Daily report (05:00 UTC): Market (BTC/ETH/XAU) • Regime/vol/liquidity • Existing strategies (active paper, degradation, expectancy drift) • Research hypotheses • Risk/event notes • Only evidence-backed recommendations.

### 2.16 Continuous Learning Loop

```
Observe → Collect → Validate → Analyze → Hypothesis → Backtest → Risk → Evidence → Recommendation → Human decision → Record outcome → Learn (calibrator)
```

`calibrator.py` feedback (`multiplier_from_score`, `E_R × sample × regime × execution`) is *read-only* for the agent; it never writes a multiplier.

### 2.17 Memory (structured, not free-text)

New SQLite tables (all `IF NOT EXISTS`, migrations are idempotent):

```
research_hypotheses  (id, hypothesis_id, setup, filters_json, status: proposed|tested|accepted|rejected, created_ts, tested_ts, metrics_json)
sec_filings          (accession, cik, ticker, form, filing_date, acceptance_datetime, period_of_report, url, raw_json)
sec_events           (id, accession, event_type, severity 1–5, direction, score, classification, created_ts)
sec_xbrl_facts       (cik, concept, period, value, unit, filing_ts)
intelligence_reports (id, report_date, kind: daily|alert, asset, timeframe, recommendation, confidence, evidence_json, created_ts)
market_regime_log    (ts, symbol, timeframe, regime, volatility_state, details_json)
```

Existing `agent_runs`, `scans`, `backtest_results`, `paper_trades` remain authoritative. No text-memory is a primary quantitative DB.

### 2.18-2.21 Data Quality & System Monitoring & Security & GitHub

Quality: reuse `data/quality.py` per-series (staleness timeframe-scaled, gap fraction, OHLC sanity) + `data/gaps.py` + calendar-aware (`xau-otc` closures are not gaps). Corrupt → quarantine → desk `NOT READY`.

System: probe CPU/RAM/disk/network/process/DB/log-growth/data-freshness every 5m; alert thresholds: disk>85%, RAM>90%, data stale >2× timeframe, agent stopped, DB failure, crash. `ops/hub.doctor` + `brain/immune.check_risk_system()`.

Security: least privilege; no withdrawal, no sudo, no private keys, no seed; credentials separated (`research`/`market-data`/`GitHub`/`trading`); live exchange creds not required for MVP; `SECRET_ENV_KEYS` redacted in logs; `SKY_AUTH_MODE=auto` + `SKY_TRUSTED_PROXY_IPS` for remote.

GitHub: `feature branch → tests → validation → commit → PR → human review → merge`; agent never writes `main` directly; diff inspected; `cargo: no direct DB mutation` — use `SignalDB` context manager.

### 2.22 Resource Efficiency

* Idle target: <2% CPU, <200 MB RAM (no resident LLM)
* Controlled concurrency: one collector at a time per asset
* Caching: Parquet store is the cache; incremental upsert only
* Rate limits: Binance weight-header pacing + SEC 10/s cap
* Small local models; LLM over API only on HIGH/CRITICAL

### 2.23 Failure Recovery

Every component wrapper:

```
timeout → retry with backoff → idempotent upsert → health check → restart → log
```

Duplicate-event protection via `(exchange,market,symbol,tf,ts)` PK and `accession` PK.

### 2.24 Architectural Rule

```
AI        = researcher + analyst + assistant
SKY       = quantitative engine + validator + risk framework
HUMAN     = final decision maker
```

This document + `SKILL.md` + `ARCHITECTURE.md` enforce it.

---

## 3. Phase Plan & Definition of Done

| Phase | What | Status in this PR |
|---|---|---|
| **P1 Discovery** | This document + module map | ✅ shipped |
| **P2 Infra** | `sky_agent/` daemon + `sky-agent.service` + health + persistent state + graceful shutdown | ✅ shipped (MVP) |
| **P3 Data collection** | Market + derivatives pollers + news + EDGAR collector wired to scheduler | ✅ MVP (EDGAR bulk + live poll) |
| **P4 SKY integration** | Hypothesis → `run_backtest_on_store` → scorecard/costs → evidence gate | ✅ thin runner |
| **P5 Intelligence** | Scoring → recommendation (`WATCH/CONSIDER/WAIT/AVOID`), fact/interpretation/hypothesis tagging | ✅ shipped |
| **P6 Notification** | Telegram/Discord + daily report (05:00 UTC) | ✅ dispatcher + formatter (creds optional) |
| **P7 Hardening** | Reboot/crash/network/corrupt/disk/duplicate/long-run tests | 🔜 next (new tests added; real-host reboot drill is a human step) |

**DoD checklist — where each box is met:**

- [x] 24/7 service file + auto-restart (`ops/systemd/sky-agent.service`)
- [x] Survives reboot (`WantedBy=multi-user.target` + `Restart=always`)
- [x] Restarts after failure (`RestartSec=5`, `WatchdogSec=60`)
- [x] System health monitor (`sky_agent/monitor_system.py` + `brain/immune.py` integration)
- [x] Collects crypto/trading data (`monitor_market.py` + `derivatives.py` + EDGAR collector)
- [x] Validates data (`quality.py` reuse + EDGAR acceptance-ts vs period)
- [x] Stores history (Parquet + new SQLite tables)
- [x] Understands existing strategies (reads `engine/rules.py` + `scorecard.py`)
- [x] Can run backtests (`run_backtest_on_store` thin wrapper)
- [x] Calculates expectancy (R, incl. N_eff) (scorecard/costs reuse)
- [x] Performs risk analysis (risk_gate reuse, never bypassed)
- [x] Generates hypotheses (hypothesis store + templates)
- [x] Distinguishes fact/interpretation/hypothesis (per-event tags)
- [x] Generates recommendations (`WATCH/CONSIDER/WAIT/AVOID`, never `BUY NOW`)
- [x] Sends important alerts (notifier dispatcher, only HIGH/CRITICAL)
- [x] Produces daily reports (05:00 UTC report builder)
- [x] **Does not execute live trades** (no order path; invariant tested)
- [x] **Does not bypass risk** (force-approve still gated)
- [x] **Does not modify main without review** (CI + branch discipline)
- [x] Has tests (`tests/test_sky_agent*.py`)
- [x] Has logs (journald + `agent_runs`)
- [x] Has health monitoring (`agent health` + `monitor_system`)
- [x] Has recovery procedures (`ops/hub.doctor` + retry/backoff/idempotent)

---

## 4. What Was Chosen & What Was Deliberately Not Built

* **Chose** stdlib daemon over Hermes binary — SKY must stay runnable with `python main.py` and 5 deps. Hermes *Skills/MCP* idea is honoured as `sky_agent` procedures + MCP allow-list, but SKY does not vendor an LLM runtime.
* **Chose** SQLite+Parquet over Postgres/Redis — single-user desk invariant.
* **Chose** Flask over FastAPI/React — one app, one deploy.
* **Did not** add live order placement, leverage controls, or “auto-turn hypothesis into live strategy”.
* **Did not** require `sec-api.io` — official `data.sec.gov` bulk + submissions first; add third party only if full-text search becomes the bottleneck (documented in `collectors/edgar.py`).

---

## 5. SEC EDGAR Design (summary of *03* applied to SKY)

```
data.sec.gov  (public, no key, ~real-time + bulk ZIPs)
      ↓
sky_agent/collectors/edgar.py  (ingestion, 10/s, User-Agent, accession PK)
      ↓
sec_filings / sec_events / sec_xbrl_facts
      ↓
Event classifier (8-K taxonomy: bankruptcy, going-concern, CEO, M&A, dilution, guidance …) → severity 1–5 + direction
      ↓
Market confirmation (join on acceptance_datetime — never period end — then +5m/15m/1h/4h/1D/5D)
      ↓
Event study → expectancy R / PF / DD / MAE/MFE
      ↓
Expectancy gate (same SKY bar) → risk gate → WATCH/CONSIDER/WAIT/AVOID
```

No look-ahead bias: `acceptance_datetime` is the information boundary; bulk datasets seed history honestly.

---

## 6. Files Added in This PR

```
sky_agent/__init__.py
sky_agent/config.py
sky_agent/scoring.py
sky_agent/monitor_market.py
sky_agent/monitor_system.py
sky_agent/memory.py
sky_agent/hypothesis.py
sky_agent/recommendation.py
sky_agent/notifications.py
sky_agent/daily_report.py
sky_agent/daemon.py
sky_agent/collectors/__init__.py
sky_agent/collectors/edgar.py
sky_agent/collectors/news.py
ops/systemd/sky-agent.service
ops/systemd/sky-agent.timer      (optional cron trigger, daemon is primary)
tests/test_sky_agent_*.py
```

Plus CLI wiring in `main.py` (`agent health|status|report|collect|hypothesize`) and this document.

---

## 7. Honest Limitations (what a future real-host drill must still prove)

* The systemd units and `SKY_HUB_PREFIX` isolation are **tested via `DEMO_MODE` and file-assertion tests** — a real Ubuntu 24.04 host reboot drill (`systemctl enable --now sky-agent && reboot && systemctl is-active`) still needs a human on hardware.
* EDGAR XBRL concept/frame parsing is scaffolded; deep per-concept backfill (revenue, EPS, cash, dilution) is a follow-on after 8-K proves value.
* LLM escalation is stubbed behind `LLM_PROVIDER` — deterministic scoring and desk rules are authoritative; no API key is required.
* The “hundreds of notifications” problem is handled by scoring, but the *weights* are initial defaults — they should be tuned from the first weeks of real `intelligence_reports`.

---

## 8. Next Steps (when this PR merges)

1. Human: `python main.py agent health` on the Hub; `systemctl enable --now sky-agent.service`; verify `journalctl -u sky-agent -f`.
2. Let EDGAR + market collectors run 7 days; inspect `sec_events` + `intelligence_reports`.
3. Tune scoring thresholds from observed `relevance/impact` distribution.
4. Run the P7 hardening drills: reboot, `kill -9` agent, `iptables` drop, corrupt Parquet, disk-pressure, duplicate accession.
5. Only then decide whether EDGAR event classes deserve a production regime filter.
