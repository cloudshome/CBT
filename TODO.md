# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-16 (**v2.23.3 / P12.15 shipped — live-book source
isolation**. Every live risk control — daily/weekly loss limits, drawdown
ladder, Kelly advisory, MC ruin/equity, MAE/MFE, business scorecard — now
reads `SignalDB.live_book_rows()`: decided, non-simulator, canonical-live
only. Research books can neither mask real losses (fail-open) nor trip live
limits. The silently-dead Kelly advisory (KeyError swallowed into
"unavailable" since wiring) was repaired: net-anchored, clamped,
advisory-only. Thresholds unchanged. Suite green: **748 pass / 1 skip**
(+12). To be delivered as this session's PR.)

**Previous:** 2026-08-16 (**v2.23.2 / P12.14 shipped — graduation
discipline isolation**. Compliance is now computed once, over decided,
non-simulator, canonical-live paper trades only, and missing or blank journals
fail closed. Simulator grinds and research books can no longer prove human
discipline. Threshold, performance criteria and source-key algebra unchanged.
Suite green: **736 pass / 1 skip** (+10). Merged as **PR #37**.)

**Previous:** 2026-08-16 (**v2.23.1 / P12.13 shipped — global
graduation source isolation**). Review found that P12.11 isolated calibration
and per-setup proof, but `paper_progress()` still pooled all sources into the
global micro-live gate. Graduation now counts canonical Binance spot evidence
only (legacy NULL rows included) and fails closed on explicit research
progress. Research wins/losses can neither unlock nor block live graduation.
Suite green: **726 pass / 1 skip**. TODO-7 was also reconciled as complete.

**Previous:** 2026-08-16 (**P12.12 shipped — read-only PAXG-vs-XAU
promotion-evidence dossier**. `data/gold_basis.py` exact-time aligns the
separately stored series, measures basis/deviation, fingerprints the
observations, and verifies the current XAU sealed-OOS envelope without
pooling, calibrating, approving, or trading. The clean checkout correctly
finds no real evidence. Suite green: **723 pass / 1 skip**.)

**Earlier:** 2026-08-15 (**P12.10 shipped — XAU bid/ask cost model**
(Dukascopy blocker #2): gold auto-detection in `data/costs.py`. Suite green:
**681 pass / 1 skip**.)

**Earlier:** 2026-08-15 (**P12.9 shipped — market calendars**: `data/calendar.py` gives each venue a trading calendar, so scheduled OTC-gold closure is no longer read as missing data. Suite green: **671 pass / 1 skip**.)

**Earlier:** 2026-08-15 (**P12.8 shipped — the net anchor**: the calibrator multiplier and the setup-proven gate now judge `E_net` instead of `E_gross`, so a setup that only profits before costs is dampened and never called proven. Suite green: **631 pass / 1 skip**.)

**Previous:** 2026-08-15 (**P12.7 shipped — Monte Carlo risk-of-ruin table**: `brain/analytics.monte_carlo_ruin_table()` resamples NET realised paper outcomes to produce a `risk% × expected DD × ruin probability` sweep plus longest losing streak and time-to-recovery, surfaced through CLI `monte`, HTTP `/api/monte` + embedded in `/api/risk`, MCP `cryptobrain_monte` + `cryptobrain_risk.ruin_table`, and the dashboard Risk card. Suite green: **620 pass / 1 skip**.)

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
4. Implement it; keep the suite green (≥ 748 pass / 1 skip)
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
| **Validation independence** | Research-grade proof on our own data | ✅ **P12.1–P12.15 shipped** — locked/sealed validation, fees-first `E_net`, effective sample size, quality/strategy scores, MC risk, calendars, gold costs, source isolation (graduation **and** live risk controls), and the read-only XAU promotion-evidence dossier |

Everything below is ordered by how directly it moves those two lines.
Anything that moves neither is out of scope. Two 2026-08-13 audits are
recorded and **decided**: the Freqtrade audit
([`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md), **F1–F8**) and
the Backtrader audit
([`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md), **BT1–BT8**).
Do not reopen them to install a bot or a second backtest engine.

---

## 🔥 Top priority — start here in the next session

### TODO-17 / P12.15 · Live-book source isolation · ✅ SHIPPED (v2.23.3)

**Report:** [`docs/HANDOVER_2026-08-16_P12_15.md`](docs/HANDOVER_2026-08-16_P12_15.md)
**Harness:** `.venv/bin/python ops/probes/p12_15_livebook_probe.py`

P12.13/P12.14 isolated the graduation gate to the canonical live book, but
every live *risk control* still read `decided_paper_rows(exclude_sim=True)`
with no provenance filter. On `fdfc9f4` that meant 5 real canonical losses
today (−1.25%, past the 1.0% daily limit) plus 6 research wins read
`+7R / not blocked` — the loss limit failed **open**; a 24-loss canonical
streak (6.0% dd) interleaved with research wins read `0.25% / normal`; 8
research-only losses **blocked** a desk that had not traded; and the Kelly
advisory was silently dead on any populated book (`KeyError('wins')`
swallowed into "unavailable" — it was fed raw rows but expects
`paper_progress()` aggregates).

Now `SignalDB.live_book_rows()` is the single definition of the live book
(decided, `sim_key IS NULL`, canonical-live, legacy NULL rows kept) and every
live control reads it: `closed_pnl()` (daily/weekly limits), `drawdown()`
(ladder), both Kelly call sites (via the new
`engine.hidden_alpha.kelly_from_rows()`, net-anchored per P12.8),
`monte_carlo_ruin_table()` / `monte_carlo_equity()` / `mae_mfe_summary()`,
and `business_metrics()`. The scorecard keeps its explicit `source_key` /
`by_source` research surfaces. No threshold moved in either direction.

**Next executable work is unchanged by this build:** run the real-host XAU
evidence procedure, and keep grinding the canonical paper book — journaling
every decided real trade.

### TODO-16 / P12.14 · Graduation discipline isolation · ✅ SHIPPED (v2.23.2)

**Report:** [`docs/HANDOVER_2026-08-16_P12_14.md`](docs/HANDOVER_2026-08-16_P12_14.md)
**Harness:** `.venv/bin/python ops/probes/p12_14_discipline_probe.py`

P12.13 isolated graduation *performance* evidence by source and left the
*discipline* criterion pooled: compliance came from `violation_rate(db)`, which
reads every `journal_entries` row with no join and no provenance filter. On
`60b61e5` that meant 20 simulator journals with zero real trades read `1.0`
PASS; 19 clean research journals outvoted the one real canonical trade that
broke the rules; `followed_rules=None` read as 100%; and 30 real trades with
one journaled read `1.0` — missing journals failed **open**.

Now `brain.journal.graduation_discipline()` (over `SignalDB.discipline_rows()`)
is the single computation: decided, `sim_key IS NULL`, canonical-live (legacy
NULL rows kept), journaled only when `followed_rules` is 0 or 1,
`compliance = compliant / eligible`, `None` on an empty book. The CLI simulator
gate, `agent ask`, `graduation_report()` and `desk_status()` (desk, `/api/desk`,
dashboard, MCP) all read it, and the desk/gate text shows the population behind
the number. `violation_rate()` still serves the general journal report.

**Next executable work is unchanged by this build:** run the real-host XAU
evidence procedure, and keep grinding the canonical paper book — *journaling
every decided real trade*, which now genuinely matters, since an unjournaled
trade lowers graduation compliance exactly like a violation.

> **Prior order note (2026-08-15):** **P12.9 shipped — market calendars.**
> Every data-quality check in SKY assumed a 24/7 market, so
> "the venue was shut" and "our collection broke" were indistinguishable. A
> complete week of spot gold holds ~53h of scheduled closure — read as a 30%+
> gap fraction and a dead feed, which **quarantined a healthy series** and
> rolled the desk to *not ready*. `data/calendar.py` adds a `MarketCalendar`
> protocol with `crypto-24x7` and the DST-aware `xau-otc` gold week; gaps, the
> quality pillar, readiness, the CSV import report and a new
> `python main.py calendar` command all judge a session venue in **trading
> time**. It is opt-in by venue and can only remove false alarms — unknown
> venues and Binance `PAXGUSDT` keep 24/7 rules, crypto output is unchanged,
> and in-session holes / stale-during-session / corrupt OHLC still quarantine.
> Docs: `docs/MARKET_CALENDAR.md`. Suite green: **671 pass / 1 skip** (+35).
>
> **P12.10 shipped — XAU bid/ask cost model** (Dukascopy blocker #2).
> `calculate_trade_cost()` now auto-detects gold instruments (XAU*/GOLD*)
> and applies a spot-market model: no funding, small ECN commission
> (0.005%/side), spread as the primary cost. An explicit `CostModel` still
> overrides auto-detection. Crypto costs are unchanged.
>
> **P12.11 shipped — source provenance in saved keys** (Dukascopy blocker #3,
> **the last one**). A graded row's calibration key carried `plan_type` and
> `regime` but not the price series that produced it, so a bid-only Dukascopy
> XAUUSD backtest pooled into the same entry as the live Binance book and
> could raise the multiplier applied to live signals. `data/provenance.py`
> adds a source key (`exchange:market[:price_type]`) with the canonical live
> series as the **empty string** — so every pre-existing key is byte-identical
> and legacy NULL-provenance rows read as the live series. Non-canonical
> series get `…@dukascopy:spot:bid` keys; the live calibration hook resolves
> canonical keys only (boost **and** filter isolated); `setup_proven()` counts
> one series and never proves a one-sided one; the scorecard splits
> `by_source` and warns when a book pools series. `--save` on the XAU adapter
> is unblocked. Docs: `docs/SOURCE_PROVENANCE.md`. Suite: **704 pass / 1 skip**
> (+23).
>
> **P12.12 shipped — PAXG-vs-XAU promotion-evidence dossier.**
> `python main.py xau-evidence` reads only the separately keyed Binance PAXG
> and Dukascopy XAU books, aligns exact timestamps without filling, measures
> basis/tracking deviation, and inspects the current XAU seal against the
> unchanged bar. It has no approve/promote option and hard-reports approval
> open, XAU non-tradeable, and micro-live locked. Synthetic tests establish
> mechanics only; the actual measurement remains to be run on the real-data
> host. Docs: `docs/XAU_PROMOTION_EVIDENCE.md`. Suite: **723 pass / 1 skip**.
>
> **P12.13 shipped — graduation source isolation.** P12.11's source boundary
> now reaches the global permission path: `paper_progress()` filters both
> backtest and paper outcomes to canonical Binance spot (`source_key=""`),
> preserving legacy NULL rows; `grind_verdict()` / `graduation_status()` reject
> explicitly non-canonical progress even when every performance threshold is
> met. Research remains reportable via source-filtered scorecards. Thresholds
> are unchanged. Suite: **726 pass / 1 skip**.
>
> **Next executable work:** run the real-host evidence procedure: rerun
> `learn` so saved rows adopt source keys, run the locked Dukascopy XAU
> validation, then archive `xau-evidence --json`. Continue the live paper
> proof until the unchanged repository graduation report says READY.
>
> **Next code build, still BLOCKED:** **micro-live at trivial size**. It may
> begin only after the graduation bar opens **and** the user explicitly
> approves it. `xau-evidence` is neither condition. Do not build order
> placement while either gate is open.
>
> **Prior order note (2026-08-15):** **P12.8 shipped — the net
> anchor.** P12.6 made every *measurement* net of costs; P12.8 fixes the two
> places that *act* on one and were still reading **gross**.
> `data.strategy_score.multiplier_from_score()` anchored on `E_gross`, so a
> setup at `E_gross +0.055R` / `E_net −0.118R` was boosted **×1.008** — the
> engine raised confidence on a setup that loses money (now **×0.982**).
> `brain.risk_gate.setup_proven()` likewise called setups proven on gross
> expectancy and now requires positive **net** expectancy where available
> (`proven_on` reports which anchor was used; sample floors unchanged).
> Strictly tighter, never looser — the graduation bar is untouched.
> Suite green: **631 pass / 1 skip** (+11).
>
> **Prior order note (2026-08-15):** **P12.7 shipped — Monte
> Carlo risk-of-ruin table.** `brain/analytics.monte_carlo_ruin_table()`
> resamples the NET realised paper book (costs included) and sweeps
> position size so the desk can read off expected max drawdown, ruin
> probability, longest losing streak and time-to-recovery for any risk
> %/trade. Surfaces: CLI `python main.py monte`, HTTP `GET /api/monte`
> (also embedded in `/api/risk`), MCP `cryptobrain_monte` plus
> `ruin_table` inside `cryptobrain_risk`, and the dashboard Risk card.
> One computation (`brain/analytics.py`), many surfaces (invariant #10).
> Suite green: **620 pass / 1 skip**. Next *code* build TBD from backlog.

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
| **P12.3.3** | effective sample size in the scorecard | ✅ **shipped** — `N_eff = N / overlap`, widened CI/SE, `step` stored | S |
| **P12.4** | backtest quality score 0–100 | ✅ **shipped** — `data/quality_score.py` + `python main.py quality` (plateau sweep) + `scorecard --quality` on all surfaces | M |
| P12.5 | strategy score on the calibrator | ✅ **shipped** — `data/strategy_score.py` + trust-dial multiplier on the calibrator; `learn` / `/api/learning` / dashboard | M |
| **P12.7** | **MC ruin / worst streak / risk-of-ruin table** | ✅ **shipped** — `brain/analytics.monte_carlo_ruin_table()` (NET outcomes); CLI `monte`; HTTP `/api/monte`; MCP `cryptobrain_monte` + `ruin_table`; dashboard Risk card | M |
| **P12.8** | **net decision anchor** | ✅ **shipped** — calibrator multiplier and setup-proven gate judge `E_net`, never a gross-only edge | S |
| **P12.9** | **market calendars** | ✅ **shipped** — `data/calendar.py` (`crypto-24x7` / `xau-otc`); calendar-aware gaps, quality pillar, readiness, CSV import; CLI `calendar`; `docs/MARKET_CALENDAR.md` | S |
| **P12.10** | **XAU bid/ask cost model** | ✅ **shipped** — gold auto-detection in `data/costs.py`; spot market model with spread-based costs, no funding, ECN commission; Dukascopy blocker #2 closed | M |
| **P12.11** | **source provenance in saved keys** | ✅ **shipped** — `data/provenance.py`; source-keyed calibration, live-path isolation, `by_source` scorecard split, `--source-key`; Dukascopy blocker #3 closed; `docs/SOURCE_PROVENANCE.md` | S |
| **P12.12** | **PAXG-vs-XAU promotion evidence** | ✅ **tooling shipped** — `data/gold_basis.py`, CLI `xau-evidence`, exact-time basis/tracking report + current sealed-OOS inspection; real-host evidence remains open; never approves or trades | S |
| **P12.13** | **graduation source isolation** | ✅ **shipped** — global progress is canonical-live-only; direct research progress fails closed; scorecards retain research visibility | XS |
| **P12.14** | **graduation discipline isolation** | ✅ **shipped** — one canonical-live, non-simulator, decided-paper `graduation_discipline(db)`; missing/blank journals fail closed; all four graduation surfaces share it (`docs/HANDOVER_2026-08-16_P12_14.md`) | S |
| **P12.15** | **live-book source isolation** | ✅ **shipped** — `SignalDB.live_book_rows()` behind every live risk control (loss limits, drawdown ladder, Kelly, MC ruin/equity, MAE/MFE, business scorecard); Kelly advisory repaired, net-anchored (`docs/HANDOVER_2026-08-16_P12_15.md`) | S |
| micro-live | trivial size | ⛔ **blocked** — only after unchanged graduation bar says READY and explicit user approval; slippage / partial fills / latency can then be measured | L |

**The bar is restated, not loosened.** `≥ +0.50R` was always meant to be
real and tradeable; measuring it *gross* quietly made it ~40% easier.
Thresholds are unchanged (≥ +0.50R, > 55% WR, PF ≥ 1.5) and are enforced
on `E_net` wherever costs are available (P12.6/P12.8).

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

### TODO-7 · Activate GitHub Actions wheel-gate · ✅ DONE

The executable job now lives in the root
**`.github/workflows/ci.yml`** beside the offline suite. GitHub Actions run
`31907327643` on merged P12.12/`main` passed both jobs on 2026-08-15:
**Offline test suite** and **Wheel gate**. The obsolete nested job-spec copy
under `docs/` was removed during the 2026-08-16 reconciliation.

Local equivalents remain:

```bash
python ci/wheel_gate.py            # build + duplicate-entry check
python ci/wheel_gate.py --install  # also smoke-test a clean venv
```

### TODO-8 · Protect `main` · human / repo admin

The integration gets HTTP 403 on the branch-protection read API, so current
protection is **unverified**, not assumed false. A repo admin should confirm
required PRs and both active status checks. Click-path is in
[`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
A trading risk-calc change must never land on `main` unreviewed.

---

## ⏸ Parked — do not start until the gate says so

Full rationale: [`docs/INFRASTRUCTURE_LAYERS.md`](docs/INFRASTRUCTURE_LAYERS.md).

**Both are now behind P10 as well as the graduation gate.** Owning our
data moves the aim; wrapping the engine in another chat UI does not.

### TODO-13 · P12 · SKY Quant Validation Engine · ✅ P12.1–P12.15 shipped

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
| **P12.3.3** | Effective sample size | Overlapping walk-forward windows divided down; confidence intervals widened honestly | ✅ **shipped** — `N_eff = N / overlap` (≈30×), `SE = σ / √N_eff`, `step` column on `backtest_results`; `min_decided` floor flagged but unchanged (revisit next) |
| P12.4 | Backtest Quality Score 0–100 | Fragile high-PnL curves score low; parameter-plateau test caps isolated-peak parameters (`+` BT5) | ✅ **shipped** — `data/quality_score.py`, `python main.py quality`, `scorecard --quality`, MCP `scorecard quality` (v1.8.0), 25 tests |
| P12.5 | Strategy score on the calibrator | `E_R × sample-quality × regime-fit × execution` (≡ the audits' `E × Stability × SampleConfidence − penalties`) | ✅ **shipped** — `data/strategy_score.py` (weighted geometric mean, NET of costs; sample-quality = P12.4 in full) + `multiplier_from_score()` trust dial on `brain/calibrator.py`; `learn` CLI / `/api/learning` / dashboard Calibration card; 15 tests |
| **P12.6** | Conditioned + net-of-costs expectancy | **Fees/spread first** (≈ 40× funding at a 1.8h hold), then OI / funding / CVD / regime from our store: `E_net = E_gross − fees − slip − funding`, funding joined as-of-T (`+` BT5) | ✅ **shipped** — `data/costs.py`, `E_net` on all surfaces, net bar |
| **P12.7** | MC ruin / worst streak / recovery / risk-of-ruin table | Graduation can see survivability, not just mean E: risk% × expected DD × ruin probability (`+` BT5) | ✅ **shipped** — `brain/analytics.monte_carlo_ruin_table()` (NET outcomes); CLI `monte`; HTTP `/api/monte` + embedded in `/api/risk`; MCP `cryptobrain_monte` + `ruin_table` in `cryptobrain_risk`; dashboard Risk card; 7 tests |
| **P12.8** | Net decision anchor | Setup proof and confidence calibration cannot promote on gross-only expectancy | ✅ **shipped** — setup-proven and calibrator gates judge `E_net`; missing costs fail closed |
| **P12.9** | Market calendars | Gap/coverage semantics distinguish continuous crypto from XAU FX sessions | ✅ **shipped** — calendar-aware quality, gaps, validation, and CLI surfaces |
| **P12.10** | Gold transaction costs | XAU evidence uses the correct point size and one-sided quote limitations | ✅ **shipped** — bid/ask-aware gold cost model and evidence surfaces |
| **P12.11** | Source-separated saved keys | Research histories cannot pool into or recalibrate the canonical live profile | ✅ **shipped** — canonical provenance keys throughout save/learn/scorecard paths |
| **P12.12** | PAXG-vs-XAU promotion-evidence dossier | Exact-time basis and sealed-OOS evidence are inspectable without self-promotion | ✅ **tooling shipped** — `data/gold_basis.py`, `xau-evidence`, operator guide; real-host run and approval remain open |
| **P12.13** | Graduation source isolation | Research histories can neither unlock nor block canonical live graduation | ✅ **shipped** — canonical-only `paper_progress`; evaluator provenance veto; 3 regression tests |

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
| TODO-8 | Verify/protect `main` (require PR, no direct push, require both CI jobs) | human / recommend yes |

**Completed:** TODO-7 — root CI runs both the offline suite and wheel gate.

D1–D5, **F1–F8** and **BT1–BT8** are already recorded. P12 is complete;
no further quant-engine TODOs are active. Do **not** reopen F1–F3 or
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
