# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-15 (this session: **P12.6 shipped — fees-first `E_net` & conditioned expectancy**: `E_net = E_gross − fees − slip − funding`, funding joined as-of-T, net graduation bar enforced; next *code* is **P12.3.3 — effective sample size in the scorecard**)

---

## 🔁 Session rhythm (how we work)

We go session by session. Each Arena session is one self-contained
unit of work that ends in a reviewable PR:

```text
1. Read SESSION_STATE.md → TODO.md → the relevant docs
2. git fetch origin; diff your branch vs origin/main — parallel
   sessions merge while you work (PR #13 learned this the hard way);
   reconcile BEFORE building
3. Pick the top unblocked item
4. Implement it; keep the suite green (≥ 567 pass / 1 skip)
5. Reconcile SESSION_STATE.md + TODO.md + CHANGELOG.md (full pass)
6. Commit + push to the session branch
7. Open ONE PR as the closing step  ← Arena allows one PR per session
8. A human reviews and merges; the next session branches from main
```

The PR is the session boundary. Never merge your own PR, and never
leave a session's work sitting on a branch with no PR — a future
session then cannot tell what was finished from what was abandoned.

---

## 🎯 The aim (never changes)

**Become a fully independent, consistently profitable trader.**

Independence has two halves. SKY currently owns one of them:

| Half | Meaning | Status |
|---|---|---|
| **Decision independence** | Our own engine, risk gate, approval loop | ✅ P1–P9 |
| **Data independence** | Our own stored market history | ✅ **P10** (P10.1–P10.12 shipped, PR #18) |
| **Validation independence** | Research-grade proof on our own data | 🔄 **P12** (P12.1–P12.3.2 shipped; **P12.6 shipped 2026-08-15** — fees-first `E_net` & net bar; next P12.3.3) |

Everything below is ordered by how directly it moves those two lines.
Anything that moves neither is out of scope. Two 2026-08-13 audits are
recorded and **decided**: the Freqtrade audit
([`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md), **F1–F8**) and
the Backtrader audit
([`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md), **BT1–BT8**).
Do not reopen them to install a bot or a second backtest engine.

---

## 🔥 Top priority — start here in the next session

> **Order note (2026-08-15, this session):** **P12.6 shipped — fees-first
> `E_net` & conditioned expectancy.** `data/costs.py` integrates realistic
> taker/maker fees, spread/slippage, and direction-aware funding into the
> grader, backtest DB, paper book, and scorecard (`E_net = E_gross − fees − slip − funding`).
> The graduation bar is enforced **NET of costs** (+0.50R net, >55% WR net,
> PF >= 1.5 net). Next *code* build is **P12.3.3 — effective sample size in the
> scorecard** (divide walk-forward trade counts by window overlap factor ~30×
> to report honest independent sample size and widen confidence intervals).

### TODO-15 / P12.6 · Fees-first `E_net` & conditioned expectancy · ✅ shipped

**P12.6 is shipped**: `data/costs.py` provides `CostModel` and
`calculate_trade_cost()`. Real trade cost drag is now computed in R units
per trade. At measured BTC median stop distance (0.823%), taker round-trip
costs −0.1215R (~35% of gross expectancy), and fees are ~40× funding at a
1.8h hold. `GradedPlan` and `backtest_results`/`paper_trades` DB tables
persist `rr_net`, `fee_r`, `slip_r`, `funding_r`, `cost_r`.
`data/scorecard.py` displays gross and net expectancy, cost drag, and
conditioned splits (`--conditioned`). The graduation bar evaluates NET
metrics on all surfaces (CLI, HTTP `/api/scorecard`, MCP `scorecard` v1.6.0).

### The ladder was reordered — P12.4 is no longer next

`docs/PATH_TO_REAL_MONEY.md` (2026-08-14) measured four things and the
order changed as a result.

| # | step | why here | size |
|---|---|---|---|
| **P12.3.1** | unify the same-bar tie-break | ✅ shipped; honest *before* real data | XS |
| **P12.3.2** | **real market data** — backfill real BTCUSDT 1m with the P10 machinery, re-run P11 / P12.1 / P12.3 | ✅ **shipped** — see `docs/REAL_DATA_RUN_2026-08-14.md` | M |
| **P12.6** | pulled forward, **fees-first** — `E_net` becomes the number the gate reads | ✅ **shipped** — `data/costs.py`, `E_net`, net bar | M |
| **P12.3.3** | effective sample size in the scorecard | **next.** overlap inflates counts ~30× (384 decided ≈ 12 independent) | S |
| P12.4 / P12.5 | as originally specced | now scoring something real | M |
| micro-live | trivial size | slippage / partial fills / latency can only be measured | L |

**The bar is restated, not loosened.** `≥ +0.50R` was always meant to be
real and tradeable; measuring it *gross* quietly made it ~40% easier.
Thresholds are unchanged (≥ +0.50R, > 55% WR, PF ≥ 1.5) and stay enforced
gross until P12.6 lands `E_net`.

---

### TODO-11 · Prove the paper book · first grind shipped · P11

**Done this session (2026-08-12, PR #9):** the grind, the journal
loop, and the graduation-report bug are all in:

- **Grind to a real 100/20 — done.** All four primary setups now hold
  thousands of unique backtest samples and 100+ unique paper samples
  (well past 100/20): Buy Pullback 9936/367, Sell Pullback 4276/184,
  Sweep Reversal Buy 18711/1600, Sweep Reversal Sell 3085/280 —
  **38,439 decided** primary-family samples on the sandbox's offline
  sample/synthetic data.
- **Journal loop — done.** Every closed simulator paper trade gets a
  journal entry (`followed_rules=1`, mechanical execution), so
  graduation `compliance` reads **100%** instead of `None`.
- **Bug the report revealed — fixed.** Sell-side wins were graded with
  inverted R (`(tp-entry)/risk` is negative for shorts), destroying
  sell expectancy/PF. Fixed + regression tests; Sell Pullback flipped
  from −1.9R to **+0.54R**.
- Desk label precision: `samples expectancy short` instead of the
  blanket `samples short`; PAPER_GRIND advice names the exact setup
  and missing item.

**Still open — the graduation gate is honestly CLOSED.** The primary
family as a whole is +0.263R expectancy / 34.1% win rate / PF 1.40 /
compliance 100% — positive but below the blueprint bar (≥ +0.50R,
> 55%, ≥ 1.5). Sweep Reversal Sell is breakeven (−0.033R); sweep
reversals show no edge on smooth synthetic data (no real stop-hunt
structure). The pullback setups carry the real edge (+0.54…+0.70R).

Next session options, in order:
1. Grind more/live data (`python main.py simulator --bars N --step 1`
   as new bars arrive; live Binance data once network is available) —
   watch whether Sweep Reversal Sell crosses above zero and the
   family expectancy climbs.
2. Consider the paper-sample collection strategy: FVG Retest types
   carry thousands of backtest samples but **0 paper samples** because
   the simulator takes one paper sample per window (best plan only).
   A per-plan-type paper book would complete the store for `learn`.
3. Do **not** change the blueprint graduation criteria to make the
   gate pass — the bar is the plan, not a knob.

**Why this comes before P10:** P11 keeps the graduation ladder moving
and gives P10's backfill a working proof-loop to feed. Do not let the
data project become a reason to stop proving the edge.

### TODO-12 · P10 · Data infrastructure + market terminal · ✅ SHIPPED (PR #18)

📄 **Full plan: [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md)** —
read that before touching any of it. Summary only here.

**The problem it solves:** every scan today is amnesiac. SKY fetches
~500 candles, decides, and throws them away. That caps backtests at
one API response, makes "how did this setup behave when OI rose and
funding was negative?" unanswerable, and means the edge is re-derived
from scratch every run.

**The goal:** collect BTC market data ourselves from free/public
exchange APIs, store it ourselves, and let the engine reason over
stored evidence.

Twelve independently shippable milestones (P10.1 → P10.12). **All
twelve are shipped** (PR #18, 2026-08-13). Do not start milestone N+1
until N is green — held to the end.

| # | Milestone | Status |
|---|---|---|
| P10.1 | Normalised `Candle` schema + Parquet store + upsert PK | ✅ shipped (`data/store.py`) |
| P10.2 | Binance paginated REST backfill (resumable, rate-limit aware) | ✅ shipped (`data/backfill.py`; hardened 2026-08-13: real perp endpoint + weight-header/backoff handling) |
| P10.3 | Gap detection + repair + 1m→higher-TF aggregation | ✅ shipped (`data/gaps.py`) |
| P10.4 | Derivatives as time series (funding / OI / mark / index / basis) | ✅ shipped (`data/derivatives.py`) |
| P10.5 | Data-quality pillar wired into `readiness_strip()` | ✅ shipped (`data/quality.py`, fourth pillar; corrupt data ⇒ quarantine ⇒ `ready: false`) |
| P10.6 | Bybit adapter behind the same schema | ✅ shipped (`data/bybit_client.py`; `--exchange bybit`) |
| P10.7 | Cross-exchange premium/discount + funding spread | ✅ shipped (`data/cross_exchange.py`; `python main.py cross`) |
| P10.8 | Lightweight Charts replaces `chartSVG()` | ✅ shipped (vendored standalone script + `/api/candles`) |
| P10.9 | OI / funding / CVD panes | ✅ shipped (FUTURES + FLOW market-tab cards) |
| P10.10 | WebSocket tier (live klines + liquidations) | ✅ shipped (`data/ws_client.py`; offline-safe stub) |
| P10.11 | Backtester reads the store, not a live fetch | ✅ shipped (`run_backtest_on_store()`) |
| P10.12 | Feature store — one wide row per timestamp | ✅ shipped (`data/feature_store.py`) |

**Phase done when** we can ask *"how did this setup perform when price
rose, OI rose, funding was negative, and CVD was positive?"* and get a
number computed from our own data. That number is produced by
**P10.11/P10.12 + P12 on `data/backtester.py`**, not by Freqtrade.

**Corrections already applied to the incoming plan** (detail in §1 of
the roadmap doc — these are the load-bearing ones):

- **Analytics are ~80% built.** EMA/RSI/MACD/ATR/VWAP/Bollinger/CVD/
  volume-profile all exist in `engine/`. P10 feeds them stored data;
  it does not reimplement them.
- **SQLite + Parquet, not PostgreSQL + Redis.** `ARCHITECTURE.md`
  fixes SKY as single-process/single-user/single-machine. Redis solves
  a cache-coherency problem we don't have.
- **Lightweight Charts standalone, not React/Next.js.** ~45 KB from a
  `<script>` tag keeps SKY one Flask process with five runtime deps.
- **No FastAPI, no Docker.** Flask already serves `/api/*`;
  `ops/systemd/` already deploys.
- **Liquidations cannot be backfilled.** Real data comes from the
  `!forceOrder@arr` WebSocket stream and only accumulates from the day
  we start. The current `liquidations()` is a 24h-stats *proxy* and
  must be renamed so nobody mistakes it for the real thing.
- **Reuse `_cross_exchange_probe()`.** ✅ P10.7: the probe now lives
  in `data/cross_exchange.snapshot_prices()`; health is a thin
  wrapper. Do not write a second one.
- **One PR per session** (Arena limit) overrides the incoming plan's
  "always open a PR" step.

**Hard constraints:** public endpoints only — no API keys, ever;
`DEMO_MODE=1` must keep the suite green offline; bad data quarantines
instead of producing a signal; `data/store/**` is gitignored.

### TODO-7 · Activate GitHub Actions wheel-gate · human action

The job spec sits at **`docs/.github/workflows/ci.yml`**, which is
**inert** — nested under `docs/`, so GitHub Actions never reads it.
Only the repository-root `.github/workflows/ci.yml` is executed, and
Arena's GitHub App token cannot write that path (push rejected twice:
`d40ff00`, and again this session's predecessor).

A human with the `workflows` permission pastes the `wheel-gate` job
from the GitHub UI. Click-path: [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).

Until then, run the gate locally:

```bash
python ci/wheel_gate.py            # build + duplicate-entry check
python ci/wheel_gate.py --install  # also smoke-test a clean venv
```

### TODO-8 · Protect `main` · human / repo admin

GitHub reports `main.protected = false`. Arena token gets HTTP 403
on the branch-protection API. Click-path is in
[`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
A trading risk-calc change must never land on `main` unreviewed.

---

## ⏸ Parked — do not start until the gate says so

Full rationale: [`docs/INFRASTRUCTURE_LAYERS.md`](docs/INFRASTRUCTURE_LAYERS.md).

**Both are now behind P10 as well as the graduation gate.** Owning our
data moves the aim; wrapping the engine in another chat UI does not.

### TODO-13 · P12 · SKY Quant Validation Engine · P12.2 shipped

📄 **Full keep/cut: [`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md) §8,
extended by [`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md) §8.**

This is the part of both external audits worth building — and we build
it **on our grader + our store**, not on a bot and not on Backtrader.
The Backtrader audit (BT5) confirmed all seven milestones and extended
four done-whens (marked `+`).

The gate condition is met: P10.11 is green (backtester reads Parquet)
and the full P10 store stack (P10.1–P10.12) is shipped, so the locked
train/val/OOS windows have real multi-window history to split.

| # | Milestone | Done when | Status |
|---|---|---|---|
| P12.1 | Locked walk-forward protocol (train / val / OOS / recent) | A setup cannot “pass” on the training window alone; the final OOS set is sealed (`+` BT6) | ✅ **shipped** — `data/validation.py`, `python main.py validate`, 17 tests |
| P12.2 | `python main.py validate lookahead` (+ recursive later) | A `shift(-n)` feature fails a test; CI runs the unit form | ✅ **shipped** — AST guard, source locations, 4 tests; existing CI full-suite job runs the lookahead unit form; recursive analysis remains later |
| P12.3 | Single boxed R-report / strategy scorecard | One command, one block — long/short, regime, session, Sharpe/Sortino/Calmar, holding time (`+` BT5) | ✅ **shipped** — `data/scorecard.py`, `python main.py scorecard`, `/api/scorecard`, MCP `scorecard`, 42 tests |
| **P12.3.1** | Same-bar SL/TP tie-break unified with the paper trader | One ambiguous candle grades identically in both graders; conservative stop-first (`+` BT7 §7.1) | ✅ **shipped** — `data/backtester.py` `<` → `<=`, `ambiguous_bar`, 5 tests |
| **P12.3.2** | **Real market data** | Real BTCUSDT 1m backfilled with the P10 machinery; P11 / P12.1 / P12.3 re-run and re-reported on it | ✅ **shipped** — `backfill --from-csv`, `StoreClient`, `docs/REAL_DATA_RUN_2026-08-14.md` |
| **P12.3.3** | Effective sample size | Overlapping walk-forward windows divided down; confidence intervals widened honestly | ▶ **next** — overlap inflates counts ~30× |
| P12.4 | Backtest Quality Score 0–100 | Fragile high-PnL curves score low; parameter-plateau test caps isolated-peak parameters (`+` BT5) | ⏳ **deferred** — after P12.3.3 |
| P12.5 | Strategy score on the calibrator | `E_R × sample-quality × regime-fit × execution` (≡ the audits' `E × Stability × SampleConfidence − penalties`) | ⏳ |
| **P12.6** | Conditioned + net-of-costs expectancy | **Fees/spread first** (≈ 40× funding at a 1.8h hold), then OI / funding / CVD / regime from our store: `E_net = E_gross − fees − slip − funding`, funding joined as-of-T (`+` BT5) | ✅ **shipped** — `data/costs.py`, `E_net` on all surfaces, net bar |
| P12.7 | MC ruin / worst streak / recovery / risk-of-ruin table | Graduation can see survivability, not just mean E: risk% × expected DD × ruin probability (`+` BT5) | ⏳ |

**Not in P12:** Hyperopt, FreqAI, Backtrader optimization or a second
backtest engine (BT4/BT7), ML direction-prediction, a strategy-module
catalog, auto capital allocation (F7 — parked until graduation + >1
proven edge).

### TODO-9 · Dify as a *separate* research layer · AFTER graduation + P10

Not a SKY dependency. Deploy Dify elsewhere and point it at SKY's
read-only surfaces (`desk`, `readiness`, `ask`, MCP). Start only when
`python main.py agent ask "am i ready for micro?"` reports READY.

### TODO-10 · LibreChat-style chat UI · AFTER TODO-9

Not a SKY dependency. The dashboard already exists. Only if a
multi-model chat panel is still wanted after Dify.

---

## ✅ Done this session (2026-08-13 · `arena/019ffab2-sky`)

### TODO-12 / P10.7 · Cross-exchange series · ✅ DONE

Premium/discount vs Binance and funding spread are now a stored,
queryable series. The live probe was **generalised, not rewritten**.

**What landed:**
- `data/cross_exchange.py` — venue registry (KuCoin/OKX/Bybit),
  `snapshot_prices()` (the one probe), `snapshot_funding()`,
  `CrossExchangeStore` (`data/store/cross/**`), `derive_premium` /
  `derive_funding_spread`, `FakeVenueTransport`, collector.
- `data/bybit_client.py` — `funding_history()` (`/v5/market/funding/history`).
- `brain/agent.py:_cross_exchange_probe` → thin `snapshot_prices` wrapper.
- CLI — `python main.py cross collect|status`.
- Tests — `tests/test_cross_exchange.py` (20) + 2 Bybit funding tests;
  agent probe now mocks Bybit V5.
- Version **2.7.2 → 2.8.0**. Suite 449 → **471 pass / 1 skip** (+22).

**Next (P10.8):** Lightweight Charts replaces `chartSVG()`.

---

## ✅ Done in a prior session (2026-08-13 · `arena/019ffa8d-sky`)

### Backtrader recommendation reviewed · BT1–BT8 decided · no reset

A ChatGPT Backtrader audit (mine it as a research engine; separate
data / signal / risk / execution / performance; expectancy + costs +
regime matrices + walk-forward + Monte Carlo + risk of ruin; adapter,
never fork) was compared to the live SKY desk. **The repo is not
rebuilt.** SKY already implements the separation, the R-expectancy
loop, the risk veto, MAE/MFE, Monte Carlo and regime-tagged grading;
the remaining good ideas were already named **P12** by the Freqtrade
review, and this audit's additions just extended them.

**Kept (into P12, after P10.11):** boxed strategy scorecard with
Sharpe/Sortino + session/L-S (P12.3 — ✅ shipped), parameter-plateau test (P12.4),
net-of-costs `E_net` with funding-as-of-T (P12.6), risk-of-ruin table
on the MC resampler (P12.7). **Rejected:** the `backtrader` dependency
(runtime/dev/adapter — BT1), a Cerebro rewrite (BT2), second grader
(BT3/BT7), entry parameter-search (BT4), repo reset (BT8).

Load-bearing doc: `docs/BACKTRADER_REVIEW.md`. Next *code* is still
**P10.7**. Version **2.7.1 → 2.7.2**. Suite 445 → **449 pass / 1 skip**
(+4 contract tests).

---

## ✅ Done in a prior session (2026-08-13 · `arena/019ffa5d-sky`)

### Freqtrade recommendation reviewed · F1–F8 decided · no reset

A full ChatGPT Freqtrade audit (use it as execution + backtest +
strategy runtime; build a Quant Validation Engine) was compared to
the live SKY desk. **The repo is not rebuilt.** SKY already *is*
the brain + risk gate + R-expectancy loop. Freqtrade would violate
invariant #1 (never place an order) and A1 (one tested edge).

**Kept (as P12, after P10.11):** walk-forward / OOS protocol,
lookahead command, boxed R-report polish, Backtest Quality Score,
strategy score on the calibrator, funding-as-of-T, MC ruin/streaks.

**Rejected:** Freqtrade itself, Hyperopt, FreqAI, a strategy-module
catalog, auto capital allocation, resetting the repo.

Load-bearing doc: `docs/FREQTRADE_REVIEW.md`. Reconciled onto
merged P10.6 (PR #14). Next *code* is **P10.7**. Version **2.7.0 →
2.7.1**. Suite 441 → **445 pass / 1 skip** (+4 contract tests).

---

## ✅ Done in a prior session (2026-08-12 · `arena/019ff579-sky`)

### TODO-12 / P10.1 · Schema + Parquet store · ✅ DONE

The first shippable milestone of P10 (data independence): a normalised
`Candle` schema and a partitioned Parquet store, fully offline.

**What landed:**
- `data/store.py` — `CandleStore`: normalised `Candle` schema (roadmap §4),
  partitioned Parquet under `data/store/**` (gitignored), upsert PK
  `(exchange, market, symbol, timeframe, ts)`, `normalise_klines()` adapter
  boundary, `coerce_candle_frame()` / `empty_frame()`.
- Unclosed-candle safety rule enforced in code.
- `tests/test_store.py` — 13 offline tests (round-trip, dedup last-write-wins,
  ordering, partition boundary, range filter, empty read, series isolation).
- Deps: `pyarrow>=15.0`; version 2.2.1 → **2.3.0**.
- Docs: CHANGELOG, DATA_INFRASTRUCTURE_ROADMAP (P10.1 shipped), SESSION_STATE.
- Tests 342 → **355 pass / 1 skip** (+13).

**P10.2 shipped (2026-08-13, this session):** `data/backfill.py`
(`BinanceBackfiller`, `FakePagedTransport`) + `klines_page()` on the
Binance client + `backfill`/`store` CLI commands; resumable, rate-limit
aware, idempotent re-run (zero rows); 21 offline tests;
suite 355 → **377 pass / 1 skip**; version **2.4.0**.

**Next (P10.3):** gap detection + repair + 1m→5m/15m/1h/4h/1d aggregation
(the master-timeframe rule — derive, don't store duplicates).

---

### TODO-1.bis · combined dashboard doctor strip · ✅ DONE (prior session)

One readiness verdict across channels + immune system + risk gate
(+ stored-data quality since P10.5), rolled up **worst-first**
(`ok → degraded → blocked → down`).

**What landed:**
- `brain/agent.readiness_strip()` + `format_readiness_strip()`, with
  `_channels_pillar()` / `_immune_pillar()` / `_gate_pillar()` each
  exception-isolated.
- CLI: `python main.py doctor --strip` (+ `--json`); plain `doctor`
  now leads with the strip; `doctor --json` gained a `readiness` key.
- `GET /api/readiness` (never 500s — degrades to a JSON error).
- MCP tool `readiness`; `SERVER_VERSION` 1.2.0 → 1.3.0 (13 tools).
- Dashboard: colour-coded strip above **every** tab, one chip per
  pillar, refreshed on the 5-minute diagnostic cadence.
- Docs: SKILL.md, README, ARCHITECTURE (new invariant #10 "one
  computation, many surfaces"), AI_ANATOMY_ROADMAP, CHANGELOG.
- Version 2.1.0 → **2.2.0**.
- Tests 324 → **337 pass / 1 skip** (+13).

---

## ✅ Done in prior sessions

- **TODO-4** `desk_status()` advisory (v2.1.0)
- **TODO-6** D1–D5 answered — `ROADMAP_AGENT_REACH_UPGRADE.md` §4
- **TODO-3** wheel-gate *content* (`ci/wheel_gate.py`, `pyproject.toml`)
- **TODO-0** PR #5 merged; **PR #6** merged 2026-08-12
- **TODO-1** P8 dashboard Channels panel
- **TODO-2** MCP capability endpoints
- **TODO-5** CHANGELOG backfill

---

## 📋 Decisions waiting on user

| ID | Decision | Default |
|---|---|---|
| TODO-7 | Paste the wheel-gate job into the real `.github/workflows/ci.yml` | human |
| TODO-8 | Protect `main` (require PR, no direct push) | human / recommend yes |

D1–D5, **F1–F8** and **BT1–BT8** are already recorded. Do **not**
start TODO-9/TODO-10/TODO-13 this session. Do **not** reopen F1–F3 or
BT1–BT4 to install a trading bot or a second backtest engine.

---

## 🚫 Explicitly out of scope (do NOT add to TODO)

- Web scraping of social platforms (Twitter / Reddit / Bilibili /
  Xiaohongshu / etc.) — out of scope per
  `ROADMAP_AGENT_REACH_UPGRADE.md` §5.
- Audio/video transcription — no audio source.
- Browser cookie extraction, third-party CLI orchestration
  (`gh` / `mcporter` / `twitter-cli` / `rdt-cli` / `bili-cli` /
  `OpenCLI` / `ffmpeg`) — CryptoBrain has zero of these dependencies.
- Autonomous exchange order placement — explicitly forbidden by
  `MERGE_NOTES.md` safety statement.
- Multi-language READMEs (CN/JP/KR) — single-language repo is fine.
- Vendoring / forking / `pip install` of **OpenHands, Dify, or
  LibreChat** into this repo. Study patterns only. See
  `docs/INFRASTRUCTURE_LAYERS.md`.
- Splitting the desk into new "Market Analyst / Risk Manager /
  News Analyst / Code Maintenance" agents. The four existing desk
  agents + `desk_status()` + `readiness_strip()` already cover that job.
- A *fourth* readiness surface. Channels, immune, gate, desk advice,
  and the strip are enough; anything new reads `readiness_strip()`.
- **Exchange trading credentials / signed endpoints / live order
  placement** — forever, not just during P10. A collector that can
  authenticate is a collector that can trade.
- **Paid data vendors.** P10 is explicitly a free/public-API phase.
- **Alt-coin expansion during P10.** BTC first, ETH second, nothing
  else until the pipeline is proven.
- **PostgreSQL, Redis, Docker, FastAPI, React/Next.js.** See the
  corrections in TODO-12 / roadmap §1.
- **Freqtrade, Hyperopt, FreqAI, or any exchange-order bot.**
  Reviewed 2026-08-13 and rejected (F1–F3 in
  `docs/FREQTRADE_REVIEW.md`). Do not `pip install freqtrade`, do not
  vendor it, do not write `execution/freqtrade_adapter.py`. SKY is
  the brain; the strategy runtime is `engine/rules.py`; the
  backtester is `data/backtester.py`.
- **Backtrader — as dependency, dev tool, vendored engine, or
  adapter.** Reviewed 2026-08-13 and rejected (BT1–BT8 in
  `docs/BACKTRADER_REVIEW.md`). Do not `pip install backtrader`; do
  not re-express plans as Cerebro strategies; do not add a second
  backtest engine "for cross-validation" (two fill semantics = two
  truths). The audit's good ideas are already ours or named P12 on
  *our* grader.
- **A new catalog of strategy modules** (trend / mean-reversion /
  momentum / …) before the primary family clears the graduation bar
  (F4). A1 stands: `sweep_trend_continuation` only.
- **Auto strategy-allocation / capital routing across strategies**
  (F7). Parked until graduation *and* more than one proven edge.
- **Resetting the repository around a third-party bot** (F8). The
  desk, the gate, the paper loop, and P10 stay.
