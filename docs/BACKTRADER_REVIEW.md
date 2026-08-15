# Backtrader recommendation — review & decision

> **Status:** decided. No code rewrite. No `backtrader` dependency.
> **Date:** 2026-08-13
> **Branch that recorded it:** `arena/019ffa8d-sky`
> **Reviewed against:** the ChatGPT Backtrader audit (22 sections) **and**
> the live SKY repo (v2.7.x), `BLUEPRINT.md`, `PROFESSIONAL_PLAN_DECISIONS.md`,
> `ARCHITECTURE.md` invariants, `docs/FREQTRADE_REVIEW.md` (F1–F8), and the
> current graduation numbers.
>
> **One-line verdict:** this audit is *closer* to SKY than the Freqtrade
> one — it says "don't make Backtrader your brain" itself. We agree with
> almost all of its research discipline, and almost every valuable idea in
> it is either **already ours** or **already named P12** by the Freqtrade
> review. What we do not take: the dependency, the Cerebro object model,
> the optimizer culture, or a second grader. The repo is not reset.

This file is load-bearing. A future session that wants to `pip install
backtrader`, vendor it, fork it, or re-express the desk as Cerebro
strategies must re-open **BT1–BT8** below in writing, not "just start
coding."

---

## 0. What was actually recommended

The incoming note is a competent, *self-aware* research-engineering
audit of Backtrader's architecture (**Cerebro → Data Feeds → Strategy →
Broker → Analyzers/Observers**), then mined for SKY as:

```text
MARKET DATA → SIGNAL/EDGE → RISK + POSITION SIZING → EXECUTION SIMULATION → EXPECTANCY
Backtrader = research engine (one of several, behind an adapter)
SKY        = trading intelligence + validation layer
```

Its concrete asks:

1. Keep the four-way separation (data / signal / risk / execution /
   performance) — never let "the AI agent" mix them.
2. A standardized `StrategyResult` schema for every strategy, a boxed
   strategy scorecard, and expectancy (R-multiples) as a primitive.
3. `E_net = E_gross − fees − slippage − funding − execution costs`.
4. A risk engine that can **veto** a strategy, with explicit limits.
5. A rich analyzer layer (Sharpe/Sortino/Calmar, MAE/MFE, session,
   long/short, cost analysis).
6. Regime-conditioned backtesting — a strategy × regime × timeframe ×
   session matrix, not "does Buy Pullback work?"
7. Walk-forward testing, a **three-way split** with a sealed final OOS
   set, parameter **plateau-not-peak** robustness, Monte Carlo, and a
   **risk-of-ruin** table.
8. "Don't blindly use Backtrader optimization" — a validation pipeline
   (robustness → walk-forward → MC → cost stress → regime stress →
   OOS → PASS/FAIL) instead.
9. An adapter pattern so Backtrader could be swapped for a vectorized
   / GPU / custom engine later; a warning that Backtrader provides no
   crypto data (funding/OI/liquidations/basis); a P0–P4 priority list.

Crucially, the note warns against the two things it describes:
"Don't make Backtrader your brain" and "Don't optimize for maximum
profit — that produces a beautiful backtest and a useless live
strategy." Taken at its own word, the note argues for keeping SKY
exactly where the Freqtrade review already put it: **our grader, our
store, P12 after P10.11.**

---

## 1. The aim (the only scoreboard)

Unchanged from `BLUEPRINT.md` / `TODO.md`:

> Become a **fully independent, consistently profitable trader** —
> consistent profits, steadily accumulating real BTC, ETH, and GOLD,
> with capital preservation first.

| Half | Meaning | Status |
|---|---|---|
| **Decision independence** | Own engine, risk gate, approval loop | ✅ P1–P9 |
| **Data independence** | Own stored market history | 🔄 P10.1–P10.6 shipped; P10.7 next |

Graduation gate (the only promotion to real capital):

```text
expectancy ≥ +0.50R · win rate > 55% · profit factor ≥ 1.5
rule compliance ≥ 90% · ≥ 100 backtest + ≥ 20 paper per primary setup
```

Current honest state: **+0.263R / 34.1% / PF 1.40 / compliance 100% /
38,439 decided samples — gate CLOSED.**

Nothing in this note moves those numbers; several of its
implementation paths (a second grader, grid-search optimization,
rewriting plans as Cerebro strategies) would move us *away* from them.

---

## 2. I considered a reset. I refused it.

The operator said again: *if you have to reset everything, don't be
afraid.* Considered seriously — and refused, for reasons stronger than
last time: **a reset around Backtrader would contradict the note
itself**, whose own §17/§20 say Backtrader is a general framework
missing the crypto layer (funding, OI, liquidations, basis) that P10 is
already building, and whose §20 says use an adapter, never fork.

A reset around Cerebro would mean:

1. Re-expressing ICT/SMC **conditional plans** (`IF price sweeps
   buy-side liquidity AND prints bearish CHOCH → SELL`) as bar-by-bar
   `Strategy.next()` state machines — deleting the trigger semantics
   the desk reasons over.
2. Replacing `data/backtester.py`'s regime-tagged, slip-aware grader
   (which the graduation report, the sell-R bug fix, and 38,439
   samples depend on) with an unproven second engine mid-ladder.
3. Importing Backtrader's **live-broker code paths** — APIs whose
   purpose is placing real orders. The fact that we would not call
   them does not matter: their presence enlarges the exact surface
   invariant #1 forbids.
4. Adopting an optimization pipeline whose stated culture (Cerebro
   `optstrategy`, millions of parameter combos) is the thing F3
   rejected. Running 50,000 backtests fast is still overfitting.
5. Stalling P10 (6 of 12 milestones shipped) and the P11 grind to
   chase par**ity** with what we already have.

**The repo is not reset.** The brain, the gate, the plans, the paper
loop, and P10 stay — a second consecutive external audit has now
independently confirmed that plan.

---

## 3. Keep / already ours / no need

Legend:

| Tag | Meaning |
|---|---|
| **KEEP** | Principle is right. Absorb into SKY (into P12, after P10.11). |
| **OURS** | Already implemented, often more strictly. Do not rebuild. |
| **NO** | Conflicts with the aim, the invariants, or F1–F8. Out of scope. |
| **PARK** | Right idea, wrong decade. After graduation *and* more than one proven edge. |

### 3.1 Architecture (their §1, §2, §18, §20, §22)

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 1 | Cerebro-style orchestrator (feeds → strategy → broker → analyzers) | **OURS** | `signal_engine → decision → risk_gate → human → paper_trading`; the grader is `run_backtest`. A broker object would simulate what our gate and paper runner already do — with semantics we would have to re-verify from scratch. |
| 2 | Four-way separation: data / signal / risk+size / execution / performance | **OURS** | That *is* the repo: `engine/indicators·structure·features` → `engine/rules·signal_engine` → `brain/risk_gate·portfolio` → `engine/execution` → `brain/metrics·analytics`. The note's diagram was drawn to match this shape. |
| 3 | Backtrader behind an adapter, swappable later | **NO** | A facade needs two engines before it earns its keep; with one grader it is indirection without a use. If a second engine is ever justified (BT7), define the interface then. |
| 4 | "SKY ⊃ Backtrader" layered architecture (their §18 diagram) | **OURS** | Data engine, intelligence, strategy, risk, execution, backtest, analytics, decision gate — the repo's module map. The one difference is deliberate: our gate is a *human*, not a Cerebro broker. |
| 5 | `class Strategy` with detect/invalidation/target/risk/size/evaluate methods | **OURS** | `engine/rules.py` plans already carry entry/SL/TP ladder, R:R, confidence, condition, reasons, status; invalidation is the plan's trigger semantics. Renaming to their method list is churn. |
| 6 | One standardized `StrategyResult` across every strategy | **OURS** | Every plan type (Buy Pullback, Sweep Reversal, FVG Retest, Breakout) already emits the **same** dict, validated by `output/signal_schema.py` / tests. Richer per-trade fields (expected_R, regime, scorecard) land in the report layer = P12.3/P12.5. |
| 7 | Backtrader repo activity (their §20: "61 open PRs") | **moot** | Maintenance state is unverified here and irrelevant: we need none of its releases. Decision rides on invariants, not on how alive upstream is. |

### 3.2 Backtesting money-math (their §4–§6, §14)

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 8 | Historical feeds + no-look-ahead bar-by-bar execution | **OURS** | `run_backtest` slices `df.iloc[:i+1]`; plans grade at +1h/+4h/+24h; P10.11 points the same grader at the Parquet store. |
| 9 | Commission / slippage / spread modeling | **OURS (partial)** | `engine/execution.py` (`EXECUTION_MODEL=simple`) is slip/spread-aware and the grader is slip-aware. Fees + funding + spread stress as one explicit net-of-costs report = **P12.6** (extended, see §8). |
| 10 | `E = P(w)·AvgWin − P(l)·AvgLoss`, better in **R** | **OURS** | `brain/metrics.py` reports `expectancy_r`; the graduation bar is stated in R; the calibrator acts on R expectancy. "+27%" is never the metric here. |
| 11 | `E_net = E_gross − fees − slip − funding − execution` | **KEEP** | P12.6, **after** P10.4's stored funding is joined *as of T*. Partial fills / liquidation distance / latency are recorded for the micro-live tier, not fabricated into paper math today. |
| 12 | Optimize for robustness, not profit: `Score = E_R × Stability × SampleConfidence − DD/Complexity penalties` | **KEEP** | This is the P12.4 quality score + P12.5 strategy score, named already by F5. The formula becomes the done-when, sharpened by their plateau test (next row). |
| 13 | Don't run blind parameter search → run the validation pipeline instead | **KEEP the pipeline / NO the search** | Pipeline (robustness → WF → MC → cost stress → regime stress → OOS → PASS/FAIL) = P12.1–P12.7 ordering. Grid search for entries stays out (F3): a faster optimiser still only predicts the past. |

### 3.3 Risk (their §7, §16)

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 14 | Risk engine between strategy and execution, able to **veto** | **OURS** | `risk_gate.evaluate` blocks approval *and* paper enroll; `portfolio.py` vetoes correlated duplicates; the behavioral gate closes the desk outright. The machine proposes, the human approves — a Cerebro broker does neither. |
| 15 | Limit list: per-trade, daily, weekly, streaks, open positions, exposure, leverage, drawdown | **OURS** | All of it: `MAX_RISK_PCT`, `MAX_DAILY_LOSS_PCT`, `MAX_WEEKLY_LOSS_PCT`, the −5/−8/−10 ladder, `CRYPTO_BUCKET_MAX_TRADES=2`, progression-scaled caps, whipsaw guard. |
| 16 | Risk of ruin: risk% × expected DD × ruin probability table | **KEEP** | Extends **P12.7** (MC ruin/streaks/recovery already named): turn the existing resampler into exactly this table so sizing is chosen against ruin probability, not vibes. |

### 3.4 Analytics (their §8, §9, §19)

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 17 | Analyzer layer (Return/WR/PF/DD/Sharpe/Sortino/Calmar/R-multiple/holding/trade-frequency/cost/…) | **OURS + KEEP (polish)** | `metrics.py` (WR, E, PF, DD, streaks, rolling 50/100) + `analytics.py` (MAE/MFE, MC) + per-regime stats. Sharpe/Sortino/Calmar, holding-time, session and long/short splits as one boxed report = **P12.3** (extended). |
| 18 | MAE / MFE per trade | **OURS** | Paper runner records MAE/MFE per trade; `hidden analytics mae` summarizes per setup ("stop too tight? TP unreachable?"). |
| 19 | Full **strategy scorecard** box → `🟢 APPROVED` / reject verdict | **KEEP (we have the live version)** | The graduation gate *is* a passing-verdict box with real numbers; P12.3 renders the research form (their 20-line scorecard); P12.5 folds it into the calibrator score. |
| 20 | Analyzer list as 17 new classes | **NO (form)** | SKY's analyzers are functions over the same tables, not a class zoo. We take the metrics, not the class hierarchy. |

### 3.5 Validation protocol (their §10–§15) — the valuable part

| # | Recommendation | Verdict | Why |
|---|---|---|---|
| 21 | Regime-conditioned expectancy matrix (strategy × regime × timeframe × session) | **OURS (partial) + KEEP** | Grader tags regime; `by_regime` + calibrator act per `setup × regime` (strategy = setup × regime × asset, decision B3). The full matrix over **stored, multi-year, funding/OI-joined** data = **P12.6**; the session/timeframe render = P12.3. Needs P10.11/P10.12 first. |
| 22 | Walk-forward, not one global fit | **OURS + KEEP** | Walk-forward already; locked train/val/OOS **windows** + a pass/fail protocol = **P12.1** (same as F6). |
| 23 | Three-way split; the final OOS is a sealed envelope | **KEEP** | P12.1's definition. Impossible honestly without stored history — another reason P10.11 comes first. |
| 24 | Parameter **plateau**, not peak (EMA 23…27 neighbourhood) | **KEEP** | Becomes P12.4's stability component: a setup that only wins at an isolated parameter point scores low. As a rule it already governs A2 (data-derived targets, not fitted constants). |
| 25 | Monte Carlo re-shuffle of the trade sequence | **OURS + KEEP** | `monte_carlo_equity` gives terminal-equity + DD distributions; P12.7 adds worst-streak / ruin / recovery-time on the same resampler — the note's exact ask. |
| 26 | Walk-forward research papers about BTC (their arXiv cite) | **gloss** | Encouraging background, not a build item. |

### 3.6 The priority list (their §21) vs ours

| Their stage | Their item | Ours |
|---|---|---|
| P0 Foundation | Trade/StrategyResult schemas, commission/slippage/funding models, sizing, R accounting | **Done** — plan schema + schema validation; slip model; funding stored (P10.4); risk%→stop→size; R everything |
| P1 Analytics | E, PF, DD, Sharpe, Sortino, MAE, MFE, win/loss distribution, streaks | **Done**, minus Sharpe/Sortino-in-one-report = P12.3 |
| P2 Robustness | WF, OOS, parameter sensitivity, MC, cost stress, regime analysis | WF + regime + MC = **done**; the locked protocol = **P12**, after P10.11 |
| P3 Intelligence | Regime classifier, setup quality, selection, ensemble, risk veto | **Done** (regime `engine/regime`+HMM, calibration quality, desk stands aside, veto) — ensemble/allocation stay **parked** (F7) |
| P4 Live/paper | Paper execution, live adapter, monitoring, kill switch, daily governor | Paper **done**; live adapter = SKY-owned thin adapter *after graduation* (F1 stance); kill switch ≈ drawdown ladder + behavioral gate (**done**) |

Their P0 is our last year. Their P2 is our P12. Their P4 keeps the
human in the loop where the note itself implies it ("TRADE / NO TRADE"
gate). The order of work needs zero change.

---

## 4. Decision list (BT1–BT8)

Same shape as F1–F8. These are **decided**.

| ID | Question | Decision | Binding consequence |
|---|---|---|---|
| **BT1** | Add `backtrader` as a dependency — runtime, dev, or "optional research engine"? | **No.** | No `pip install backtrader`, no vendored copy, no submodule, no adapter file. Our grader is `data/backtester.py`; P10.11 points it at our store. |
| **BT2** | Rebuild SKY around Cerebro/Strategy/Broker/Analyzers? | **No.** | The separation already exists (`engine/` + `brain/`); Cerebro's live-broker code is an order surface we forbid; conditional plans do not fit `next()`. |
| **BT3** | Use Backtrader's broker/commission/analyzer machinery for grading? | **No — ours equivalents exist.** | Slip/spread (`engine/execution.py`), the scorecard (`brain/metrics.py`), MAE/MFE + Monte Carlo (`brain/analytics.py`). Deeper net-of-costs is P12.6 on our stack. |
| **BT4** | Use its optimization/parameter-search machinery for entries? | **No (consistent with F3).** | P12's objective is *robustness by evaluation*, not fitted constants. A grid search of entries remains out of scope. |
| **BT5** | Keep the note's research discipline (expectancy, WF, OOS, MC, regime matrix, scorecard)? | **Yes — it is already P12.** | Confirms the F-named P12.1–P12.7 and extends four done-whens (P12.3 boxed scorecard + Sharpe/Sortino + session/L-S; P12.4 plateau test; P12.6 `E_net` with funding-as-of-T; P12.7 risk-of-ruin table). See §8. |
| **BT6** | Keep the sealed dev / validate / final-OOS split? | **Yes — P12.1.** | Same as F6. Locked windows, never retuned, only possible after the store holds years of candles. |
| **BT7** | Add a second independent backtest engine for cross-validation? | **Parked — never as a dependency.** | Two graders = two fill semantics = two truths. If our grader's correctness is ever doubted on a specific trade, verify that trade by hand or with a throwaway script — not an installed engine. |
| **BT8** | Reset the repository around this note? | **No.** | Desk, gate, plans, paper loop, and the P10 ladder stay. Docs + contract tests record the refusal, as with F8. |

---

## 5. What changes in the roadmap (and what does not)

### Changes

- **P12 definitions extended** (§8): P12.3 gains the boxed strategy
  scorecard with Sharpe / Sortino / Calmar + long-short + session
  splits; P12.4 gains the parameter-**plateau** robustness test;
  P12.6 gains the explicit `E_net = E_gross − fees − slip − funding`
  report with funding joined **as of T**; P12.7 gains the
  risk-of-ruin table (risk% × expected DD × ruin probability), worst
  losing streak, and time-to-recovery.
- **Backtrader** joins the explicit out-of-scope lists (`TODO.md`,
  `docs/INFRASTRUCTURE_LAYERS.md`, `docs/DATA_INFRASTRUCTURE_ROADMAP.md`,
  `ARCHITECTURE.md` invariant #13) — as dependency, vendored engine,
  or adapter.
- Contract tests in `tests/test_handoff_memory.py` so a future session
  cannot quietly re-adopt a second grader.

### Does **not** change

- Next *code* session is still **P10.7** (cross-exchange premium/
  discount + funding spread as stored series).
- P11 grind continues; the graduation bar is not moved.
- P12 still does not start until P10.11 is green.
- Dify / LibreChat stay parked; no new agents, panels, strategies, or
  exchange credentials.
- Nothing in `engine/`, `brain/`, `data/` changes in this session —
  this is a docs + contract-tests-only decision, exactly like the
  Freqtrade review.

```text
NOW      P10.7 → P10.12   own the data
ALONG    P11              grind live paper; do not move the bar
THEN     P12              Quant Validation Engine on OUR backtester + OUR store
                         (definitions confirmed + extended by this review)
PARKED   F7/BT7 allocation & second engines, Dify, LibreChat
NEVER    Freqtrade, Hyperopt, FreqAI, Backtrader, signed order APIs
```

---

## 6. Mapping their components onto what we have

| Backtrader piece | Their role | SKY's answer |
|---|---|---|
| `Cerebro` | Orchestrates runs | `cmd_backtest` → `run_backtest` (walk-forward, regime-tagged, slip-aware) |
| Data Feeds | Standardized market data | `data/store.py` normalised `Candle` schema + Binance/Bybit adapters (P10.1–P10.6) |
| `Strategy` / `next()` | Bar-by-bar logic | `engine/rules.py` IF/THEN conditional plans + `engine/signal_engine.py` — richer than a boolean column (F-review §7.5) |
| Indicators | Reusable feature layer | `engine/indicators.py` (RSI MACD EMA VWAP ADX … ) + `engine/structure.py` (BOS/CHOCH OB FVG sweeps) |
| Broker + Commission | Cash/positions/costs | `engine/execution.py` slip/spread; fee/funding depth = P12.6 on P10.4's stored series |
| Sizers | Position sizing abstraction | `trading_intelligence._position_size()` (risk% → stop → units) + Kelly advisory |
| Analyzers | Performance measurement | `brain/metrics.py` + `brain/analytics.py`; boxed multi-metric report = P12.3 |
| Observers | Equity/trade visualization | Dashboard + `stats` + equity curves in metrics |
| Optimization (optstrategy) | Parameter search | **Absent on purpose** (F3/BT4) |
| Resampling / replay | Multi-timeframe | `engine/mtf.py` (9 TFs) + `data/gaps.py` 1m→higher rollups (P10.3) |
| Live brokers | Real orders | **Absent on purpose** (invariant #1) |

The loop is complete without the framework. That is not a gap. That is
the point — same sentence as the Freqtrade review, and it is still
true.

## 7. Why a second grader is a liability (Backtrader-specific)

1. **Two fill models = two truths.** Any bar-by-bar engine resolves
   ambiguous same-candle SL/TP touches implicitly. SKY's rule is
   written down and tested (conservative: SL wins). Importing another
   engine's default would create a number we would have to audit, not
   one we defined.
2. **Live-broker surface.** Backtrader ships broker integrations —
   code whose only purpose is real orders. Presence widens the blast
   radius invariant #1 exists to eliminate.
3. **Representation mismatch (again).** Conditional plans with
   triggers are not `orders_created_on_every_bar`. Translating them
   loses the exact semantics the desk teaches from.
4. **Merge/maintenance tax.** Whatever its current PR count, adopting
   it means tracking its releases forever — the tax already refused
   for Freqtrade / OpenHands / Dify / LibreChat.
5. **Optimizer gravity.** Imports invite use. The Cerebro happy path
   (`optstrategy`) is the culture F3 rejected: fit to the past, fast.

## 8. P12 sketch — definitions as extended by this review

Do **not** start until P10.11 is green. Each row is one session. `+`
marks done-whens extended against the Freqtrade review's §8 table.

| # | Milestone | Done when |
|---|---|---|
| **P12.1** | Locked walk-forward / dev-validate-OOS protocol | ✅ **SHIPPED 2026-08-13** (`data/validation.py`, `python main.py validate`): a setup cannot “pass” on the training window alone; the final OOS set is **sealed** (BT6) — fingerprint-gated reuse, recorded reseals |
| **P12.2** | `python main.py validate lookahead` (+ recursive later) | ✅ **SHIPPED 2026-08-13** — deterministic AST guard fails on `shift(-n)` / `shift(periods=-n)` in first-party feature code; unit form runs in CI. Recursive-state analysis remains later. |
| **P12.3** | Single boxed R-report / **strategy scorecard** | One command, one block — long/short, regime, **session**, Sharpe/Sortino/Calmar, holding time (`+`) |
| **P12.4** | Backtest Quality Score 0–100 | Fragile high-PnL curves score low; **parameter-plateau test** — an isolated-peak parameter point caps the stability score (`+`) |
| **P12.5** | Strategy score on the calibrator | ✅ **SHIPPED 2026-08-15** (`data/strategy_score.py` + trust-dial multiplier on `brain/calibrator.py`): `E_R × sample-quality × regime-fit × execution` (the note's `Score = E × Stability × SampleConfidence − penalties` landed here) |
| **P12.6** | Conditioned + **net-of-costs** expectancy | OI / funding / CVD / regime matrix **and** `E_net = E_gross − fees − slip − funding` with funding joined **as of T** from P10.4 (`+`) |
| **P12.7** | MC ruin / worst streak / **risk-of-ruin table** | Survivability, not just mean E: risk% × expected DD × ruin probability, longest losing streak, time-to-recovery (`+`) |

**Not in P12 (unchanged):** an optimizer for entries, a second grader,
a strategy-module catalog, auto capital allocation (F7/BT7), ML
direction-prediction (F3).

---

## 9. TL;DR for the next session

- **Do not install Backtrader.** Not as a dependency, dev tool,
  vendored copy, or adapter — BT1.
- **Do not reset the repo.** A second external audit has now
  independently converged on our existing plan; the reset would
  contradict the note itself.
- **Do not add a second backtest engine** — two fill semantics, two
  truths (BT7).
- **Do not loosen the graduation bar.** +0.263R / 34.1% / PF 1.40.
- Next code remains **P10.7** (cross-exchange series per
  `docs/DATA_INFRASTRUCTURE_ROADMAP.md`). Fetch `origin/main` first.

```text
SKY = Data + Regime + Strategy + Expectancy + Risk + Human + Feedback

Backtrader = a general backtester whose good ideas are already named
             P12, and whose engine we do not need to run them
```
