# 🧠 AI Trading Brain Anatomy Roadmap & Status Tracker

```
Progress: [████████████████████████████████████████] 100% (Phases P1–P6 Complete)
Tests:    488 passed / 1 skip (offline, DEMO_MODE=1)
Status:   Production-Ready Institutional Desk & Autonomous Architecture
Note:     This repo consolidates Cloudslover/AI + cloudshome/AI (see MERGE_NOTES.md)
```

---

## 🏛️ System Architecture Overview

```
                          ┌──────────────────────────────────────────────┐
                          │            User & External Clients          │
                          │   CLI / Dashboard / MCP Client (Claude, etc) │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                     ┌───────────┴───────────┐
                                     │   JSON-RPC MCP Server │
                                     │      mcp_server.py    │
                                     └───────────┬───────────┘
                                                 │
  ┌──────────────────────────────────────────────┼──────────────────────────────────────────────┐
  │                                              │                                              │
┌─▼──────────────────────────┐     ┌─────────────▼────────────┐     ┌──────────────────────────▼─┐
│     P1: RAG Library        │     │    P2: LLM Reasoning     │     │     P3: Autonomous Hands   │
│  brain/library.py          │     │    brain/brief.py        │     │     brain/agents.py        │
│  brain/ask.py              │     │    ai/llm_brain.py       │     │     agent_runs (DB)        │
│  Grounded Q&A + Citations  │     │    Morning Brief/Review  │     │     Brief / Watchdog / etc │
└─────────────┬──────────────┘     └─────────────┬────────────┘     └─────────────┬──────────────┘
              │                                  │                                │
              └──────────────────────────────────┼────────────────────────────────┘
                                                 │
                                   ┌─────────────▼────────────┐
                                   │   P5: Immune System      │
                                   │   brain/immune.py        │
                                   │   Staleness/Risk Alarms  │
                                   └─────────────┬────────────┘
                                                 │
                                   ┌─────────────▼────────────┐
                                   │   Risk Gate & Playbooks  │
                                   │   SQLite Learning Store  │
                                   └──────────────────────────┘
```

---

## 📊 Phase Matrix & Live Verification

| Phase | Layer | Implemented Modules | Capabilities & Proof | Status |
|---|---|---|---|:---:|
| **P1** | **RAG — Library** | `brain/library.py`<br>`brain/ask.py` | Grounded retrieval with strict source citations:<br>`ask "which setups have positive expectancy in ranging markets?"`<br>↳ *"Buy Pullback: bt n=120 exp=+0.88R (win 75%) — cited: backtest_results"* | ✅ Complete |
| **P2** | **LLM — Reasoning** | `brain/brief.py`<br>`ai/llm_brain.py` | Pre-market briefing + post-mortem reasoning:<br>`postreview <scan_id>`<br>↳ *"TP_HIT · 1.5R · MAE 30.0 · MFE 1200.0 · Followed rules: YES"* | ✅ Complete |
| **P3** | **Agents — Hands** | `brain/agents.py`<br>`data/database.py` (`agent_runs`) | Autonomous desk agents:<br>• `MorningBriefAgent`: BTC/ETH/GOLD posture + session windows<br>• `WatchdogAgent`: Paper trade monitoring & stale cleanup<br>• `PaperReviewerAgent`: Post-mortem aggregation<br>• `WeeklyReviewAgent`: Metrics & change detection | ✅ Complete |
| **P4** | **MCP — Nervous System** | `mcp_server.py` | Zero-dependency stdio JSON-RPC MCP server:<br>`initialize` ↔ `tools/list` ↔ `tools/call ask`<br>Enforced security: Read-only & analysis tools only (no order placement or approval bypass). | ✅ Complete |
| **P5** | **Immune System** | `brain/immune.py` | Real-time diagnostic alarms & staleness detection:<br>`health`<br>↳ Catches stale candle data (>2 days old), DB corruption, risk limit breaches, behavioral blocks (angry/tired/revenge/chasing). | ✅ Complete |
| **P6** | **Hidden Alpha & Variance** | `engine/hidden_alpha.py`<br>`engine/execution.py`<br>`engine/correlation.py`<br>`brain/analytics.py` | • Markov-smoothed HMM latent regimes (Bull/Bear/Range/Expansion)<br>• CVD order flow: absorption & exhaustion detection<br>• Bayesian fractional Kelly sizing (`NEGATIVE_EDGE_STAND_ASIDE`)<br>• 8D state fingerprint + historical similarity search<br>• Realistic spread/slippage execution model (`EXECUTION_MODEL=simple`)<br>• Monte Carlo equity + drawdown distribution (`hidden analytics mc`)<br>• Measured BTC/ETH/GOLD correlation matrix + ETH/BTC beta (`correlation`) | ✅ Complete |

---

## 💻 Complete CLI Command Reference

### Quantitative Alpha & Risk Variance
```bash
# Monte Carlo resampling of realized paper outcomes (terminal equity + drawdown):
python main.py hidden analytics mc --samples 2000

# MAE/MFE summary per setup (are stops too tight? targets unreachable?):
python main.py hidden analytics mae

# HMM latent regimes + CVD order flow + Bayesian Kelly + 8D fingerprint:
python main.py hidden chart_read BTC

# Measured rolling BTC/ETH/GOLD correlation matrix + ETH/BTC beta:
python main.py correlation
```

### RAG & Intelligence
```bash
# Ask questions grounded in backtests, playbooks, risk rules, and SMC concepts:
python main.py ask "which setups have positive expectancy in ranging markets?"
python main.py ask "what is the ETH playbook rule?"
python main.py ask "what are the daily and weekly loss limits?"
```

### Briefing & Post-Trade Reviews
```bash
# Generate cross-asset morning brief (BTC, ETH, GOLD):
python main.py brief

# Run post-trade review on a closed trade:
python main.py postreview <scan_id>
```

### Autonomous Desk Agents
```bash
# Run all agents or an individual agent:
python main.py agent all
python main.py agent morning
python main.py agent watchdog
python main.py agent paper-reviewer
python main.py agent weekly-review
```

### Immune Diagnostics & Health
```bash
# Run full system diagnostic check:
python main.py health
python main.py health --json
```

### Model Context Protocol (MCP) Server
```bash
# Start stdio MCP JSON-RPC server (connect via Claude Desktop or MCP Client):
python mcp_server.py
```

---

## 🔄 Repository Consolidation & Ownership

This repository is the **consolidated production build** of the same project
ecosystem, merged from both of the author's repositories:

1. [`https://github.com/Cloudslover/AI`](https://github.com/Cloudslover/AI) —
   engine + professional mode (hidden-alpha quant layer, execution model,
   analytics, risk gate).
2. [`https://github.com/cloudshome/AI`](https://github.com/cloudshome/AI) —
   the AI Anatomy layer (RAG library, ask, brief, agents, immune, MCP).

Canonical consolidated repo: [`https://github.com/Azimshawon/SKY`](https://github.com/Azimshawon/SKY).
The merge strategy, file-level provenance and verification results are in
`MERGE_NOTES.md`.  Both upstream repos remain as read-only history sources.

---

## 🚀 HOW WE CONTINUE — Durable Handoff Protocol

When continuing in a new session or machine:

1. **5-Minute Orientation Recipe**:
   ```bash
   # 1. Recreate virtual environment (.venv is excluded from persistent snapshots)
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt

   # 2. Verify all tests pass
   .venv/bin/pytest

   # 3. Check immune system
   .venv/bin/python main.py health
   ```

2. **Remaining Progression Ladder**:
   - **Step 1: Live Market Feed**: Public Binance REST (no keys). Never add trading credentials.
   - **Step 2: Collect 100–200 Paper Samples**: Run `python main.py paper --watch` in `PROGRESSION=simulator` mode to accumulate statistical sample size.
   - **Step 3: Self-Calibration**: Run `python main.py learn` to update proven setups from real paper-trade outcomes.
   - **Step 4: Transition to Micro**: Set `PROGRESSION=micro` in `.env` once setup expectancy is mathematically proven.
   - **Step 5: Dashboard Expansion**: Embed RAG chat panel and Agent activity log into `web/app.py`.

3. **Core Operating Rules**:
   - 🛡️ **Never bypass the human approval gate**: Machine proposes, Human approves, Paper-runner executes.
   - 📚 **Grounded answers only**: Every query response must carry explicit citations (`[cited: ...]`).
   - 🧪 **Test-driven integrity**: Keep all 171+ tests passing across all changes.

---

## 🛰️ Next Phases — Agent-Reach-Inspired Upgrade (P7–P9)

Adopting the **operational patterns** of
[`Panniantong/Agent-Reach`](https://github.com/Panniantong/Agent-Reach)
(70.5k★, MIT) — *not* its web-scraping surface — so any AI agent
(Claude, Cursor, Arena, MCP client) can discover, install, doctor, and
route commands through CryptoBrain.

| Phase | Theme | Deliverables | Status |
|---|---|---|:---:|
| **P7** | **Agent surface** | `SKILL.md` (≤ 250 lines) · `python main.py doctor` (alias of `health`) · `python main.py skill --install` · `docs/agent_install.md` | ✅ Complete |
| **P8** | **Source channels** | `brain/channels.py` ordered-backend router (CryptoDada/Discord/news/LLM) · `python main.py channels` · dashboard "Channels" panel | ✅ Complete |
| **P9** | **Capability endpoints** | MCP `tools/list` = 13 read-only tools (deny list visible) · `desk_status()` advisory · `readiness_strip()` combined doctor verdict (`doctor --strip` / `/api/readiness` / MCP `readiness`) · wheel-gate (`ci/wheel_gate.py` + `pyproject.toml`) | ✅ Complete (CI activation still TODO-7) |

**Out of scope (deliberate):** web scraping, social-platform logins,
cookie extraction, audio transcription, third-party CLIs (`gh`,
`mcporter`, `twitter-cli`, `rdt-cli`, `bili-cli`, `OpenCLI`,
`ffmpeg`). CryptoBrain's universe is exchange market data + private
CryptoDada + private Discord + RSS news. The 8 social-platform
cookie formats Agent-Reach manages are *never used* by a trading
engine.

**Invariant preserved in every phase:** the engine can never place a
real exchange order. Deny list enforced at the top of
`mcp_server.handle_tool_call()`; the human-approval gate remains
between the machine and any action.

---

## 🛰️ Next Phases — Data Independence (P10–P12)

P1–P9 built **decision independence**: our own engine, our own risk
gate, our own approval loop. P10 built **data independence**: our own
stored, gap-repaired, quality-quarantined market history — shipped in
full (P10.1–P10.12). P12 now builds **validation independence**: the
research-grade proof that the edge is real, on our backtester + our
store.

| Phase | Theme | Deliverables | Status |
|---|---|---|:---:|
| **P11** | **Paper-book proof** | First grind shipped (38,439 decided; 100/20 on all four primary setups; compliance 100%; sell-R bug fixed). Graduation gate **honestly CLOSED** (+0.263R / 34.1% / PF 1.40). Keep grinding live data; do not move the bar. | 🔄 In progress |
| **P10** | **Data infrastructure + market terminal** | **P10.1–P10.12 shipped** (PR #18): schema, Binance backfill, gaps/rollups, derivatives series, quality pillar, Bybit adapter, cross-exchange series, Lightweight Charts, futures/flow cards, WS tier, store-backed backtest, feature store. | ✅ Complete — [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **SKY Quant Validation Engine** | Walk-forward / OOS / lookahead / boxed scorecard / quality score / strategy score / conditioned + net-of-costs expectancy / MC ruin + risk-of-ruin table — on **our** backtester + **our** store. Starts after P10.11. | 🔄 **P12.1 shipped** (locked train/val/OOS/recent protocol, sealed OOS — `data/validation.py`, `python main.py validate`); next **P12.2** lookahead — [`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md) §8, extended by [`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md) §8 |

**P11 runs alongside P10.** The first grind is done; the gate is still
closed on the blueprint bar. Do not let the data project become a
reason to stop proving the edge, and do not loosen the bar.

**P10's definition of done:** *"How did this setup perform when price
rose, OI rose, funding was negative, and CVD was positive?"* answered
with a number computed from our own stored data (P10.12 + P12.6).

**P12 is not Freqtrade, and it is not Backtrader.** A 2026-08-13
review rejected Freqtrade / Hyperopt / FreqAI as a SKY dependency
(F1–F3); a second same-day review rejected Backtrader as dependency,
adapter, or second grader (BT1–BT4, BT7). The useful research-
integrity ideas from both notes *are* P12, built on
`data/backtester.py` and the P10 store.

**Out of scope for P10 (deliberate):** exchange trading credentials or
signed endpoints (forever — a collector that can authenticate is a
collector that can trade), paid data vendors, PostgreSQL/Redis/Docker/
FastAPI/React (SKY stays single-process with five runtime deps —
see roadmap §1), alt-coins beyond BTC then ETH, **Freqtrade / any
exchange-order bot**, **Backtrader / any second backtest engine**.

**Full planning document:** [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md)
— includes honest alignment check, per-phase risk + rollback,
definition-of-done per phase, and the D1–D5 decision list to
confirm before coding starts.
