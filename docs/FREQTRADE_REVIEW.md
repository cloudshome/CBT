# Freqtrade recommendation — review & decision

> **Status:** decided. No code rewrite. No Freqtrade dependency.
> **Date:** 2026-08-13
> **Branch that recorded it:** `arena/019ffa5d-sky`
> **Reviewed against:** the ChatGPT Freqtrade audit (31 sections) **and**
> the live SKY repo (v2.6.x), `BLUEPRINT.md`, `PROFESSIONAL_PLAN_DECISIONS.md`,
> `ARCHITECTURE.md` invariants, and the current graduation numbers.
>
> **One-line verdict:** SKY is already the brain. Freqtrade is a trading
> *bot*. We do not put a bot under a desk that is forbidden to place
> orders. We keep the research-integrity ideas and build them on **our**
> stack as P12 — after we own the data.

This file is load-bearing. A future session that wants to `pip install
freqtrade`, fork it, or rebuild SKY around `populate_entry_trend` must
re-open **F1–F8** below in writing, not “just start coding.”

---

## 0. What was actually recommended

The incoming note is a competent *generic* trading-engineering audit of
Freqtrade, then grafted onto SKY as:

```text
SKY BRAIN  →  RISK ENGINE  →  FREQTRADE (runtime + orders + backtest)  →  exchange
```

It also recommends: modular strategy files, R-multiple expectancy,
walk-forward / OOS / Monte Carlo, no giant Hyperopt, lookahead CI,
leverage-downstream-of-risk, a Risk Gate, FreqAI later, and a
“SKY Quant Validation Engine.”

The *research discipline* is good. The *architecture* is a category
error. SKY is not a bot that is missing an execution engine. SKY is a
**human-in-the-loop trading desk** whose first invariant is that the
machine never places an exchange order.

---

## 1. The aim (the only scoreboard)

From `BLUEPRINT.md` and `TODO.md`, unchanged:

> Become a **fully independent, consistently profitable trader** —
> consistent profits, steadily accumulating real BTC, ETH, and GOLD,
> with capital preservation first.

Independence has two halves:

| Half | Meaning | Status |
|---|---|---|
| **Decision independence** | Our own engine, risk gate, approval loop — not a signal group | ✅ P1–P9 |
| **Data independence** | Our own stored market history — not a 500-candle amnesiac fetch | 🔄 P10.1–P10.6 shipped (Bybit via PR #14); P10.7 next |

The graduation gate (the only promotion to real capital) is:

```text
expectancy ≥ +0.50R
win rate   >  55%
profit factor ≥ 1.5
rule compliance ≥ 90%
≥ 100 backtest + ≥ 20 paper per primary setup
```

Current honest state (offline grind): **+0.263R / 34.1% / PF 1.40 /
compliance 100% / 38,439 decided samples — gate CLOSED.**

Nothing in the Freqtrade note moves those two halves, and several of
its proposals would move us *away* from them (API keys, order-placement
surface, strategy sprawl, overfitting).

---

## 2. I considered a reset. I refused it.

The operator said: *if you have to reset everything, don't be afraid.*
I took that seriously. A reset around Freqtrade would mean:

1. Vendoring or pinning `freqtrade` as the strategy runtime.
2. Rewriting ICT/SMC **conditional plans** (`IF sweep AND CHOCH → SELL`)
   into `populate_entry_trend` / `populate_exit_trend` boolean columns.
3. Giving the process exchange API keys and a `place_order` path.
4. Throwing away the human-approval gate, the paper runner, the
   progression ladder, and the “machine proposes / human approves”
   contract.
5. Making every upstream Freqtrade release a merge risk on our desk.

That would not make us a better trader. It would make us a worse copy
of a bot we are not trying to be. **The repo is not reset.** The
brain, the gate, the plans, the paper loop, and P10 stay.

---

## 3. Keep / already ours / no need

Legend:

| Tag | Meaning |
|---|---|
| **KEEP** | Principle is right. Absorb into SKY (usually as P12). |
| **OURS** | Already implemented, often more strictly than the note. Do not rebuild. |
| **NO** | Conflicts with the aim, the invariants, or the professional plan. Out of scope. |
| **PARK** | Right idea, wrong decade. After graduation *and* more than one proven edge. |

### 3.1 Architecture

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 1 | SKY = brain, Freqtrade = execution + backtest + strategy runtime | **NO** (brain half is **OURS**) | SKY *is* the brain (`brain/`, `engine/`). Freqtrade’s job is to place orders. Invariant #1 forbids that. Our runtime is `signal_engine` → `decision` → `risk_gate` → **human** → `paper_trading`. |
| 2 | Put Freqtrade between the risk engine and Binance/Bybit/OKX | **NO** | That slot is the human-approval gate. A bot there deletes the desk. |
| 3 | Don’t use Freqtrade as the “brain” | **KEEP** | Agreed — and therefore we don’t need Freqtrade at all. |
| 4 | Don’t fork / don’t copy the Freqtrade repo; pin `freqtrade==X.Y.Z` | **NO** (stronger) | We don’t pin it either. A pinned bot is still a bot. Same rule as OpenHands / Dify / LibreChat: study, never vendor. |
| 5 | Proposed `execution/freqtrade_adapter.py` | **NO** | Post-graduation live micro, *if ever*, is a **SKY-owned thin adapter** with no third-party strategy runtime. Not this year. |
| 6 | Rebuild the tree as `brain/ risk/ strategies/ backtest/ data/ execution/freqtrade` | **NO** | We already have `brain/`, `engine/`, `data/`, `output/`. Renaming to match a blog diagram is churn. |

### 3.2 What Freqtrade “gives you” (their star table)

| Freqtrade component | Their stars | SKY already | Verdict |
|---|---|---|---|
| Strategy engine | 5 | `engine/rules.py` IF/THEN plans + `signal_engine.py` | **OURS** — and it can express SMC conditions Freqtrade’s column API cannot |
| Backtesting | 5 | `data/backtester.py` bar-by-bar, no look-ahead, R, regime-tagged | **OURS**; P10.11 points it at the Parquet store |
| Hyperopt | 5 | — | **NO** — see §3.5 |
| Futures trading | 5 | Public perp *data* (P10.2/P10.4). No futures *orders* | **NO** for trading; data stays ours |
| Risk / sizing / stoploss | 4–5 | `risk_gate.py`, `_position_size()`, plan SL/TP ladder, paper SL/TP1 | **OURS** |
| Protections | 5 | Daily/weekly stop, −5/−8/−10 drawdown ladder, trader-state, cooldowns | **OURS** (stronger) |
| FreqAI | 4 | LLM desk narrative, not ML entries | **NO** |
| WebUI / Telegram | 3–4 | Flask dashboard + Telegram + Discord | **OURS** |
| Exchange integration | 5 | Public Binance + Bybit (P10.6) **data** adapters | **KEEP** the data-adapter idea; **NO** to signed trading APIs |
| Lookahead / recursive analysis | 5 | Walk-forward already uses `df.iloc[:i+1]`; indicator tests exist | **KEEP** as a first-class P12 command on *our* backtester |
| Trade database | 5 | SQLite `scans/plans/backtest_results/paper_trades/journal` | **OURS** |
| AI reasoning | 2 | `intelligence`, `ask`, `coach`, `brief` | **OURS** — this is the differentiator they themselves named |

### 3.3 Strategy

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 7 | Don’t build one 5,000-line `SKYStrategy.py` soup | **KEEP** / **OURS** | Decision **A1** already soft-narrowed to `sweep_trend_continuation` (Sweep Reversal + Pullback). Other plans are watch-items. |
| 8 | Stand up `strategies/trend/`, `mean_reversion/`, `liquidity/`, `momentum/`, `regime/` now | **NO** | That is the radar-vs-sniper problem A1 solved. The primary family is not yet at +0.50R. More modules = more half-learned edges. |
| 9 | SKY picks a strategy from the regime | **PARK** | Right *after* more than one setup is proven. Today the desk already stands aside in bad regimes (`regime.py` + intelligence filter). |
| 10 | Auto strategy allocation / “which strategy deserves capital” | **PARK** | ChatGPT’s own P7. We do not have one proven edge yet. |

### 3.4 Expectancy & reporting

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 11 | Judge setups by **R expectancy**, not “+143%” | **OURS** | `brain/metrics.py`: `E = P(W)×AvgWinR − P(L)×|AvgLossR|`. Graduation is in R. Calibrator is in R. |
| 12 | 70% win rate can still lose money | **OURS** | Coach + calibrator already dampen high-WR / negative-E setups (Breakout Buy is the worked example in the README). |
| 13 | Strategy report box (WR, avg win/loss R, E, PF, DD, Sharpe, long/short) | **KEEP** (polish) | `stats` already prints WR / avg R / E / PF / DD / streaks / rolling 50/100. Sharpe/Sortino and a single boxed report are P12.3, not a new engine. |
| 14 | Break down by asset / side / regime / session / vol | **OURS** + **KEEP** | `by_regime` and `by_action` already exist. Session / vol / long-vs-short as a first-class report is P12.3. |
| 15 | Don’t optimise for max total profit | **OURS** | Graduation is E + PF + WR + compliance + sample size. 800% with 60% DD would fail the gate. |

### 3.5 Validation protocol (the valuable part)

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 16 | Don’t trust one backtest | **KEEP** | Formalise as P12.1. Today we walk forward, but we do not lock train / validate / OOS / recent-regime windows. |
| 17 | Dev 2020–22 / val 2023 / OOS 2024 / recent 2025–26 | **KEEP** | P12.1 — **after P10.11** (backtester reads the store). Useless on a 500-candle fetch. |
| 18 | Walk-forward rather than one global fit | **OURS** (partial) | `run_backtest` already re-runs the engine on `df.iloc[:i+1]`. Missing: locked period splits + a pass/fail protocol. |
| 19 | Hyperopt / Optuna | **NO** | The note’s own warning is the reason: 100 parameters × millions of combinations = a strategy that predicts the past. Conflicts with “one tested edge” and A2 (data-derived, not grid-searched). |
| 20 | Optimise structure → entry → exit → stop → size → protections, in that order | **KEEP** (discipline, not a feature) | Write it into P12. Do not build an optimiser. |
| 21 | Lookahead-analysis as CI | **KEEP** | P12.2 on *our* grader. Already structurally no-lookahead; we want a dedicated command + a failing test if a feature uses `shift(-n)`. **Not** Freqtrade’s CLI. |
| 22 | Recursive-analysis (`startup_candle_count`) | **KEEP** (later in P12.2) | Real, but lower value than OOS + lookahead. |
| 23 | Monte Carlo trade-sequence shuffle | **OURS** | `brain/analytics.monte_carlo_equity` — terminal equity + DD distribution. P12.7 adds ruin / worst-streak / recovery-time on the same resampler. |
| 24 | Backtest Quality Score (sample, OOS, E, DD, PF, regime, execution, stability) | **KEEP** | P12.4. Composite 0–100 so a fragile +800% curve cannot look like a pass. |
| 25 | Strategy score `E_R × Quality × RegimeFit × ExecutionQuality` | **KEEP** | P12.5 — an upgrade to `brain/calibrator.py`, not a new brain. |
| 26 | Expectancy-fail / DD-fail in **PR CI** | **NO** (as a PR gate) | CI is offline and deterministic. Live expectancy is data-dependent; failing PRs on last week’s BTC would be chaos. Unit-test the *protocol*; run the score on the operator’s store. |
| 27 | Historical funding only (never “today’s funding on old candles”) | **OURS** + **KEEP** | P10.4 stores funding/OI/mark/index/basis. P10.11/P12 must join them **as-of T**. The rule “at timestamp T, only information available at T” is already how the backtester slices. |
| 28 | “SKY Quant Validation Engine” as the next build | **KEEP** — **this is P12** | Built on `data/backtester.py` + the Parquet store. Not on Freqtrade. Not before P10.11. |

### 3.6 Risk

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 29 | Risk % of equity, not “I use 10x” | **OURS** | `RISK_PCT` → stop distance → size. Leverage is downstream (A3 / B6). |
| 30 | Risk Gate before every order | **OURS** | `brain/risk_gate.py`: daily, weekly, drawdown ladder, trader state, setup-proven, progression. Enforced at approve **and** paper enroll. |
| 31 | Example $10k policy (0.25% / 1% / 3% / 10% DD) | **OURS** | Student is 0.25 / 1.0 / 2.0. Simulator/micro is 0.5 / 1.5 / 3.0. Ladder −5% reduce / −8% stop / −10% review. |
| 32 | Freqtrade `StoplossGuard` / `MaxDrawdown` / `CooldownPeriod` | **NO** | Weaker duplicate of the gate + `state_memory` whipsaw guard. |
| 33 | `custom_stake_amount` / `leverage()` callbacks | **NO** | Bot API. Our sizing already lives in the intelligence report + gate. |
| 34 | Funding / liquidation-distance / slippage checks in the gate | **KEEP** (later) | Sensible once P10.4/P10.10 series are joined into the live snapshot. Not a reason to import Freqtrade. |

### 3.7 AI / ML / data

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 35 | Don’t start with FreqAI | **NO** (stronger) | Don’t start with it, don’t schedule it. SKY’s AI is a **research analyst** (brief, ask, coach), never an ML entry generator. |
| 36 | Stage order: deterministic → backtest → risk → expectancy → regime → ML → LLM | **KEEP** the first five (done or in flight); **NO** to ML-as-entry | LLM narrative already exists and is optional. ML prediction of direction is how you get “beautiful backtest, live failure.” |
| 37 | Advanced data: OI, funding, liquidations, orderbook, basis | **OURS** (in progress) | This **is** P10. Do not rebuild it inside a Freqtrade strategy. |

### 3.8 Their priority list vs ours

| Their stage | Their item | Ours |
|---|---|---|
| P0 Safety | Risk engine, kill switch, daily loss, DD, sizing, leverage caps | **Done** (`risk_gate`, progression, B6/B7) |
| P1 Research integrity | Lookahead, recursive, funding, fees, slip, walk-forward | **Partial.** Slip model exists (`execution.py`). Funding stored (P10.4). Formal WF/OOS/lookahead command = **P12** after P10.11 |
| P2 Strategy framework | Pullback, sweep, breakout, trend, mean-reversion | **Done, then narrowed.** Pullback + sweep are the primary family. Breakout is measured negative and dampened. Do not add more. |
| P3 Expectancy | R, E, MAE/MFE, PF, stability | **Done** (`metrics`, `analytics`, `stats`, graduation) |
| P4 Regime | Trend / range / vol / bull / bear | **Done** (`regime.py`, HMM, calibration keyed `setup × regime`) |
| P5 Advanced data | OI / funding / liq / book / basis | **This is P10.** P10.6 Bybit shipped; next code: P10.7 |
| P6 AI | ML + LLM reasoning + news + sentiment | LLM + news = **done**. ML entries = **NO** |
| P7 Autonomous allocation | Which strategy, how much risk | **PARK** until graduation + >1 proven edge |

Their “start here” (P0–P4) is already the desk. Starting over at P0 to install Freqtrade would be walking backwards.

---

## 4. Decision list (F1–F8)

Same shape as `PROFESSIONAL_PLAN_DECISIONS.md`. These are **decided**.

| ID | Question | Decision | Binding consequence |
|---|---|---|---|
| **F1** | Adopt Freqtrade as the execution / exchange / order layer? | **No.** | No `freqtrade` dependency, submodule, vendor copy, or adapter. Invariant #1 and #13. |
| **F2** | Adopt Freqtrade as the backtester / strategy runtime? | **No.** | Keep `data/backtester.py` + `engine/rules.py`. P10.11 wires **our** grader to **our** store. |
| **F3** | Adopt Hyperopt / Optuna / FreqAI? | **No. Forever for entries.** | Parameter search and ML direction-prediction are out of scope. LLM narrative stays optional. |
| **F4** | Expand to a catalog of strategy modules now? | **No.** | A1 stands. Primary family = sweep + pullback. New families only after that one clears the graduation bar. |
| **F5** | Build a SKY Quant Validation Engine? | **Yes — as P12, on our stack.** | Walk-forward / OOS / lookahead / quality score / strategy score / funding-as-of-T. Starts after P10.11. |
| **F6** | Formal train / validate / OOS / recent-regime protocol? | **Yes — P12.1.** | Locked windows. No retuning on OOS. Requires years of stored candles. |
| **F7** | Auto-allocate capital across strategies? | **Parked.** | Needs ≥2 proven edges and a passing graduation gate. Not a 2026-Q3 item. |
| **F8** | Reset the repository around this note? | **No.** | The desk, the gate, the paper loop, and P10 stay. Docs + contract tests record the refusal. |

---

## 5. What changes in the roadmap (and what does not)

### Changes

- **P12 is promoted** from a one-liner (“regime-conditional backtests”)
  to the **SKY Quant Validation Engine**:
  P12.1 walk-forward protocol → P12.2 lookahead/recursive →
  P12.3 R-report polish → P12.4 quality score → P12.5 strategy score →
  P12.6 funding/OI/CVD-conditioned expectancy → P12.7 MC ruin/streaks.
- **Freqtrade / Hyperopt / FreqAI / trading-bot frameworks** are added
  to the explicit out-of-scope lists (`TODO.md`, this file,
  `INFRASTRUCTURE_LAYERS.md`, invariant #13).
- Contract tests in `tests/test_handoff_memory.py` so a future session
  cannot quietly re-adopt the bot.

### Does **not** change

- Next *code* session is **P10.7** (P10.6 Bybit shipped via PR #14).
- P11 grind continues alongside (do not loosen the graduation bar).
- Dify / LibreChat stay parked.
- No new agents, no new dashboard tab, no new strategy file, no
  exchange credentials.
- The 4-step BLUEPRINT path (paper → prove → micro → accumulate) is
  untouched.

```text
NOW      P10.7 → P10.12   own the data (cross-exchange, charts, WS, store-backed backtest)
ALONG    P11              grind live paper; do not move the bar
THEN     P12              Quant Validation Engine on OUR backtester + OUR store
PARKED   F7 allocation, Dify, LibreChat
NEVER    Freqtrade, Hyperopt, FreqAI, signed order APIs
```

---

## 6. Mapping their “ideal SKY research loop” onto what we have

```text
MARKET DATA                 P10 store + backfill + derivatives
     ↓
Feature Generation          engine/indicators + structure + features
     ↓
Regime Detection            engine/regime + hidden_alpha HMM
     ↓
Setup Detection             engine/rules (IF/THEN plans)
     ↓
Signal Generator            engine/signal_engine
     ↓
Expectancy Model            brain/calibrator + brain/metrics
     ↓
Risk Gate                   brain/risk_gate + brain/portfolio
     ↓
Position Size               intelligence _position_size (risk → stop → units)
     ↓
Leverage                    downstream of risk — not a bot callback
     ↓
Freqtrade                   ✗  DOES NOT EXIST HERE
     ↓
Human approval              engine/lifecycle  ← this is the real next box
     ↓
Paper runner                data/paper_trading  (never an exchange)
     ↓
Trade Result → Analytics    journal + metrics + analytics MC/MAE
     ↓
Expectancy Update           python main.py learn
     ↓
Strategy Score              P12.5 (calibrator upgrade)
     ↓
Strategy Selector           PARKED (F7)
```

The loop they drew is already the product, minus the Freqtrade box
and plus the human. That is not a gap. That is the point.

---

## 7. Why Freqtrade specifically fails SKY’s invariants

1. **Invariant #1 — never place a real exchange order.** Freqtrade’s
   reason to exist is placing orders. Importing it is how the deny
   list dies.
2. **No trading credentials, ever** (P10 constraint, invariant #12).
   Freqtrade wants API keys. A collector that can authenticate is a
   collector that can trade.
3. **Human approves; machine proposes.** A strategy-runtime bot is
   designed to skip that.
4. **One tested edge, not many half-learned strategies (A1).**
   Freqtrade’s culture is “write another strategy file.” Ours is
   “prove this family to +0.50R.”
5. **ICT/SMC conditional plans.** `IF price sweeps buy-side liquidity
   AND prints bearish CHOCH → SELL` is a *plan with a trigger*, not a
   column of `1`/`0` on every candle. Forcing it into Freqtrade
   destroys the representation.
6. **Upstream merge tax.** They said this themselves. We already
   refused that tax for OpenHands / Dify / LibreChat.

---

## 8. What a future session may build (P12 sketch)

Do **not** start these until P10.11 is green (backtester reads
Parquet). Each row is one session.

| # | Milestone | Done when |
|---|---|---|
| **P12.1** | Locked walk-forward protocol (train / val / OOS / recent) | A strategy cannot be “passed” on the training window alone |
| **P12.2** | `python main.py validate lookahead` (+ recursive later) | A `shift(-n)` feature fails a test; CI runs the unit form |
| **P12.3** | Single boxed R-report (long/short, regime, session) | One command, one block, no new math |
| **P12.4** | Backtest Quality Score 0–100 | Fragile high-PnL curves score low |
| **P12.5** | Strategy score on the calibrator | `E_R × sample-quality × regime-fit × execution` |
| **P12.6** | Conditioned expectancy (OI / funding / CVD / regime) | *“how did this setup do when price ↑, OI ↑, funding < 0?”* — the original P10/P12 done-when |
| **P12.7** | MC ruin / worst streak / recovery on the existing resampler | Graduation can see survivability, not just mean E |

Until then, the operator already has: `backtest`, `stats`, `learn`,
`hidden analytics mae`, `hidden analytics mc`, `simulator`,
`agent ask "am i ready for micro?"`.

---

## 9. TL;DR for the next session

- **Do not install Freqtrade.**
- **Do not reset the repo.**
- **Do not add strategy modules.**
- **Do not loosen the graduation bar.**
- Next code: **P10.7 cross-exchange series** (`docs/DATA_INFRASTRUCTURE_ROADMAP.md`).
- The only ideas worth keeping from the note are already named
  **P12.1–P12.7** above.

```text
SKY = Data + Regime + Strategy + Expectancy + Risk + Human + Feedback

Freqtrade = a bot we are not building
```
