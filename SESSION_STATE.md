# SESSION_STATE.md — CryptoBrain / SKY

> **Purpose:** the *single* handoff file a new Arena session reads first
> to resume work without re-deriving context. **Update at the end of
> every session** (see "End-of-session checklist" at the bottom).
> **Read first** at the start of every new session (see "Start-of-session
> recipe" at the bottom).
>
> **Contract:** do a **full-document reconciliation pass every time** —
> re-read the entire file, fix pre-existing placeholders and stale
> status lines, not just append new sections.

**Last updated:** 2026-08-15 (this session: **v2.21.0 — P12.10 XAU bid/ask
cost model**: `data/costs.py` auto-detects gold instruments and applies a
spot-market model with spread-based costs, no funding, and a small ECN
commission. Closes Dukascopy blocker #2. Two of three blockers closed.)

**Previous:** 2026-08-15 (**v2.20.0 P12.9 — market calendars**: scheduled
closure is no longer a gap.)
**Branch:** `arena/01a0069a-sky` (this session's branch)
**HEAD commit:** `d9410b9` feat(P12.9): market calendars — a scheduled closure is not a gap (#32)
**Python:** 3.11 (venv `.venv`) — suite green (**681 pass / 1 skip**)

> **This session (`arena/01a0069a-sky`): v2.21.0 — P12.10 XAU bid/ask cost model.**
> **Verified first:** rebuilt `.venv`, ran the inherited suite → **671 pass /
> 1 skip** (the P12.9 baseline). Then built the next item.
>
> **The problem.** `calculate_trade_cost()` used a default `CostModel()` with
> `market="perp"`, taker fees (0.05%/side) and funding — appropriate for crypto
> perps but not for spot gold. A bid-only XAUUSD backtest was costed with
> crypto assumptions. The existing `SPREADS["XAUUSD"]` entry existed but was
> never auto-selected. This was blocker #2 of the three recorded against the
> Dukascopy XAU research book.
>
> - **`cost_model_for_symbol()`** — symbol-based cost model resolver. When no
>   explicit `CostModel` is passed, gold instruments (XAU*/GOLD*) get a
>   spot-market model with zero funding, `DEFAULT_GOLD_COMMISSION_PCT = 0.005%`
>   per side ECN commission, and spread as the primary cost.
> - **`is_gold_symbol()`** / **`GOLD_SYMBOL_PREFIXES`** — prefix-based gold
>   detection.
> - **`DEFAULT_GOLD_COMMISSION_PCT`** — 0.005% per side (~$5 per $100k notional).
> - **Auto-detection** — `calculate_trade_cost()` now calls
>   `cost_model_for_symbol(symbol)` when `cost_model` is None, so every XAUUSD
>   call automatically uses gold-specific costs. An explicit `CostModel`
>   argument still overrides auto-detection.
> - **Safety direction — it can only make costs more accurate for gold.**
>   Opt-in by symbol prefix (XAU/GOLD); BTCUSDT, ETHUSDT, PAXGUSDT keep the
>   crypto-perp default unchanged. An explicit `CostModel` always wins over
>   auto-detection. Crypto numbers are byte-identical.
> - **Docs:** `docs/DUKASCOPY_XAU_ADAPTER.md` blocker #2 closed.
> - **Versions:** `config.py` / `pyproject.toml` **2.20.0 → 2.21.0**;
>   wheel gate green.
> - **Tests:** +10 in `tests/test_costs.py` → **681 pass / 1 skip**.

> **This session (`arena/01a004b0-sky`): v2.19.0 — optional Dukascopy XAU adapter.**
> - `dukascopy-node` remains an external, version-pinned CSV producer. SKY
>   does not install, vendor, or execute it at runtime.
> - `backfill --from-csv --csv-source dukascopy --price-type bid|ask` accepts
>   its documented epoch-ms OHLC CSV through the existing SHA/sanity/dedupe/gap
>   boundary and stores a separate `dukascopy/spot/XAUUSD` series.
> - Canonical candles now carry `price_type`; old Parquet partitions are
>   additively coerced, rollups preserve the side, and mixed bid/ask imports
>   into one series fail closed.
> - `backtest` / `simulator` store mode now accept `--exchange`, matching
>   validate/scorecard/quality.
> - Existing Binance BTC/ETH and live XAU→PAXG behavior is unchanged. Saving
>   Dukascopy grades into calibration remains prohibited until market-calendar,
>   gold spread/cost, and learning-key provenance work is complete.
> - Guide: `docs/DUKASCOPY_XAU_ADAPTER.md`.
>
> **Earlier this session: P12.8.1 — expectancy-anchor class audit.**
> - **Sweep:** all executable expectancy comparisons against zero or a bar are
>   inventoried in `docs/EXPECTANCY_ANCHOR_AUDIT_2026-08-15.md`.
> - **Remaining path fixed:** `data.simulator.grind_verdict()` now recomputes
>   the micro-live sample proof from counts + `E_net`; a stale `proven=True`
>   cannot override a cost-flipped book, and the gap says `positive net
>   expectancy` rather than the contradictory `all targets met`.
> - **Zero is data:** `paper_progress()` uses `None`-only net→gross fallback;
>   exact-zero net expectancy/wins/R no longer inherit positive gross values.
> - **Surface aligned:** simulator grind output displays labelled `E_NET`.
> - **Operational blocker:** this checkout has neither `data/store/**` nor
>   `data/cryptobrain.db`, so the requested real `backtest --save` + `learn`
>   was not faked with demo data. Commands are recorded in the audit.
> - **Version/tests:** 2.18.0 → **2.18.1**; **633 pass / 1 skip**.

> **Prior session (`arena/01a00490-sky`): P12.8 — the net anchor.**
> P12.6 made every *measurement* net of costs. P12.8 closes the gap it left:
> the two places that **act** on a measurement still read the **gross**
> number, so the desk measured honestly and then decided on the wrong figure.
> - **`data/strategy_score.multiplier_from_score()`** anchored its sign on
>   `E_gross`. Measured: a setup at `E_gross = +0.055R` / `E_net = −0.118R`
>   got multiplier **×1.008** — the engine *raised* confidence on a setup that
>   loses money. Now anchored on `expectancy_net` (gross only as fallback when
>   costs are unknown) → **×0.982**, dampened.
> - **`brain/calibrator.build_profile()`** passes the net anchor; the
>   `CALIBRATE_FILTER` negative filter judges net too.
> - **`brain/risk_gate.setup_proven()`** (A6/B10) now requires positive
>   expectancy **net of costs**; sample floors unchanged. The block message
>   names the failing condition instead of only reprinting sample counts.
> - **`data/database.setup_stats()`** returns `backtest_expectancy_net` /
>   `paper_expectancy_net` (`None` → caller falls back to gross, never guesses);
>   `setup_proven` reports `proven_on: "net" | "gross"`.
> - **Strictly tighter, never looser** — it can only dampen a multiplier or
>   withdraw a "proven". The graduation bar is untouched.
> - **Tests:** +11 in `tests/test_net_anchor.py` (incl. a monotonicity property:
>   the net anchor can never raise a multiplier). Suite **620 → 631 / 1 skip**.
> - **Versions:** `config.py` / `pyproject.toml` **2.17.0 → 2.18.0**.

> **Prior session (`arena/01a0046d-sky`): P12.7 — Monte Carlo risk-of-ruin table.**
> The scorecard says whether the live book is profitable net of costs;
> P12.7 answers *how much size it can survive*. It resamples the decided
> paper-trade outcomes **NET of costs** (filling missing `rr_net` via
> `data.costs.calculate_trade_cost`) and sweeps position size to expose
> expected maximum drawdown, ruin probability, longest losing streak and
> time-to-recovery.
> - **`brain/analytics.py` → `monte_carlo_ruin_table()`** — one computation
>   (invariant #10). Returns `table[]` per risk-% plus a `historical`
>   block from the actual net sequence.
> - **CLI:** `python main.py monte [--risk-pcts ...] [--ruin-threshold 50]
>   [--samples N] [--seed N] [--json]`; `python main.py risk` points to it.
> - **HTTP:** `GET /api/monte`; `monte` key embedded in `GET /api/risk`.
> - **MCP:** root `mcp_server.py` risk tool embeds `ruin_table`;
>   `ai/mcp_server.py` exposes `cryptobrain_monte` and adds `ruin_table`
>   to `cryptobrain_risk`.
> - **Dashboard:** Risk gate card renders the Monte Carlo sweep table.
> - **Versions:** `config.py` / `pyproject.toml` **2.16.0 → 2.17.0**;
>   root MCP server **1.8.0 → 1.9.0**.
> - **Tests:** +7 in `tests/test_monte_carlo.py`; suite **613 → 620 pass
>   / 1 skip**.

> **Prior session (`arena/01a00446-sky`, P12.5): Strategy Score on the calibrator.**
> `data/strategy_score.py` scores each calibration key 0–100 as
> `E_R × sample-quality × regime-fit × execution` (weighted geometric
> mean, NET of costs), where sample-quality is P12.4's
> `backtest_quality_score()` in full; the calibrator multiplier is now a
> trust dial (`mult = clamp(1 + E_gross × gain × trust, …)`,
> `trust = clamp(score/50, 0.6, 1.5)`). Surfaces: `learn` CLI,
> `/api/learning`, dashboard Calibration card. Version 2.15.0 → 2.16.0.
> Costs are now integrated into every performance measurement across the desk:
> `E_net = E_gross − fees − slip − funding`, where every term is expressed
> in **R units per trade**.
>
> `data/costs.py` implements `CostModel` and `calculate_trade_cost()`:
> - **Fees + spread lead the cost calculation**: at the measured BTC median
>   stop distance (0.823% of entry), standard taker round-trip fee (0.05%/side =
>   0.10% total) costs **0.1215R** per trade (~35% of gross expectancy), and
>   at typical 1.8h holds **fees are ~45× funding**.
> - **Funding as-of-T**: direction-aware funding looked up from stored
>   derivatives series (`data/derivatives.py`) as of signal timestamp $T$
>   (long pays positive funding, short receives positive funding credit;
>   spot has 0 funding).
> - **Grader & Database Net R**: `GradedPlan` and `backtest_results` /
>   `paper_trades` DB tables gained `rr_net`, `fee_r`, `slip_r`, `funding_r`,
>   `cost_r` via additive migrations in `data/database.py`.
> - **Scorecard Net Metrics & Conditioned Splits**: `data/scorecard.py`
>   computes both gross and net metrics (`expectancy_net`, `win_rate_net`,
>   `pf_net`, `total_r_net`, `max_drawdown_r_net`, `sharpe_net`, `sortino_net`,
>   `calmar_net`, `cost_r`, `fee_r`, `slip_r`, `funding_r`), and conditioned
>   splits by funding regime and CVD order flow (`--conditioned`).
> - **Net Bar Enforcement**: `meets_bar()` in `data/validation.py` and
>   `build_scorecard()` evaluate performance against the restated **NET**
>   bar: $E_{\text{net}} \ge +0.50\text{R}$, $WR_{\text{net}} > 55\%$, $PF_{\text{net}} \ge 1.5$.
> - **Surfaces**: CLI `python main.py scorecard [--no-costs] [--maker] [--conditioned]`,
>   HTTP `GET /api/scorecard`, MCP `scorecard` tool (v1.6.0), and dashboard
>   learning card displaying net expectancy and cost drag breakdown.
> Version **2.12.0 → 2.13.0**. Suite **552 → 567 pass / 1 skip** (+15).

> **Prior session (`arena/01a00034-sky`, merged as PR #22): P12.3.2 — real market data.**
> The first real market data entered the project: Binance spot BTCUSDT 1m,
> 2025-01-01 → 2026-04-30, 696,960 bars, from Binance's official public archive
> (`data.binance.vision`), sha256-pinned and verified on import (`c4ad6029…b934b7`).
> Transported offline via `backfill --from-csv`, rolled up to 15m/1h/4h/1d by P10.3
> rollups. P11, P12.1, and P12.3 re-run on real data: primary 1h horizon loses
> money in every window (train −0.452R, oos −0.101R); 24h horizon is +0.400R gross
> (≈ +0.28R net, below the net bar); Breakout Buy confirmed as prune candidate (−0.630R);
> graduation gate stays honestly closed (+0.348R / 36.8% WR / PF 1.55).
> Version **2.11.1 → 2.12.0**. Suite **539 → 552 pass / 1 skip** (+13).

> **Prior session (`arena/019fffe5-sky`, merged as PR #21): P12.3 — the boxed strategy scorecard.**
> `data/scorecard.py` turns outcomes the grader already decided into **one block**:
> expectancy, win rate, PF, total R, max drawdown, streaks, Sharpe/Sortino/Calmar
> and holding time, split by **long/short**, **regime**, **session** and **setup**.
> Three surfaces read the identical report (invariant #10): CLI, HTTP, and read-only MCP.
> Holding time is captured at grading time: `GradedPlan.holding_bars` / `holding_hours`.
> P12.3.1 unified same-bar tie-break (conservative stop-first).
> Version **2.10.0 → 2.11.1**. Suite **492 → 539 pass / 1 skip** (+47).

> **Prior session (`arena/019ffb14-sky`, merged as PR #20): P12.2 — lookahead validation.**
> Added `data.validation.scan_lookahead()` and `python main.py validate lookahead`:
> deterministic stdlib-AST scan that fails closed on explicit future-peeking `shift(-n)`
> calls. Version **2.9.0 → 2.10.0**. Suite **488 → 492 pass / 1 skip**.

> **Prior session (`arena/019ffad5-sky`, merged as PR #18): P10.8–P10.12.**
> P10 data infrastructure fully delivered: Lightweight Charts candlestick/volume pane,
> FUTURES/FLOW market-tab cards, WebSocket tier with reconnect/backoff, store-backed
> backtester (`run_backtest_on_store`), feature store (`data/feature_store.py`).

---

## Project

**CryptoBrain / SKY** — multi-source, multi-indicator, conditional-signal
trading engine for BTC, ETH, and XAUUSD/GOLD with a strict human-approval
gate. **Read-only by design** — the engine *cannot* place a real exchange
order; the human approves, the paper-runner executes, the engine proposes.
The full proposition, sources, and progression ladder are in
[`BLUEPRINT.md`](./BLUEPRINT.md). The history of the two-upstream merge
is in [`MERGE_NOTES.md`](./MERGE_NOTES.md). The professional trading
plan (18 phases, 15-item rulebook) is in
[`PROFESSIONAL_PLAN_DECISIONS.md`](./PROFESSIONAL_PLAN_DECISIONS.md).

---

## The aim (never changes)

**Become a fully independent, consistently profitable trader.**
Independence has two halves: **decision independence** (our own engine
+ risk gate + approval loop — ✅ done, P1–P9) and **data independence**
(our own stored market history — ✅ P10.1–P10.12 shipped, with real market
data imported and verified; research validation proof — 🔄 P12.1–P12.7
shipped; next is **micro-live**, then scale). Every
phase below is ordered by how directly it moves those two lines.

---

## Current phase

**P12 (SKY Quant Validation Engine) — P12.10 XAU bid/ask cost model shipped.**
P10 (data infrastructure) is fully shipped (P10.1–P10.12, PR #18); P11 grind
re-run on real data and the graduation gate is honestly closed (+0.348R gross,
negative net on 1h/4h primary). Freqtrade rejected (F1–F8); Backtrader
rejected (BT1–BT8). The Dukascopy XAU research book (v2.21.0) has calendar-aware
gap detection (P12.9) and a gold-specific cost model (P12.10); one of its three
blockers remains (calibration-key source provenance). Open items: TODO-7,
TODO-8; next phase after the XAU blockers: **micro-live**.

| Phase | Theme | Status | Notes |
|---|---|---|---|
| P1 | RAG Library | ✅ Complete | `brain/library.py`, `brain/ask.py` |
| P2 | LLM Reasoning | ✅ Complete | `brain/brief.py`, `ai/llm_brain.py` |
| P3 | Autonomous Hands | ✅ Complete | `brain/agents.py`, `agent_runs` table |
| P4 | MCP Nervous System | ✅ Complete | `mcp_server.py` (zero-dep stdio JSON-RPC 2.0) |
| P5 | Immune System | ✅ Complete | `brain/immune.py` |
| P6 | Hidden Alpha & Variance | ✅ Complete | `engine/hidden_alpha.py`, `engine/execution.py`, `engine/correlation.py`, `brain/analytics.py` |
| P7 | Agent Surface (SKILL + CLI) | ✅ Complete | `SKILL.md`, `python main.py doctor`, `python main.py skill` |
| P8 | Source Channels (router) | ✅ Complete | `brain/channels.py` + `/api/channels` + dashboard "Channels" panel |
| **P9** | **Capability Endpoints** | **✅ Complete** | MCP 13 tools (incl. `desk_status`, `readiness`); readiness strip on all surfaces; wheel-gate content landed (CI activation = TODO-7) |
| **P11** | **Paper-book proof** | 🔄 In progress | First grind shipped (38,439 decided; all four primary setups ≥100/20; compliance 100%); first real-data grind shipped (+8,300 bt / +494 paper). Gate honestly closed. |
| **P10** | **Data infrastructure + market terminal** | ✅ Complete | **P10.1–P10.12 shipped** (PR #18): store, backfill, gaps/rollups, derivatives, quality pillar, Bybit, cross-exchange, Lightweight Charts, futures/flow cards, WS tier, store-backtester, feature store. [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **Quant Validation Engine** | ✅ Complete | **P12.10 shipped — XAU bid/ask cost model** (P12.1 locked protocol; P12.2 lookahead guard; P12.3 scorecard; P12.3.1 tie-break unified; P12.3.2 real market data; P12.6 fees-first `E_net`; P12.3.3 `N_eff`/CI; P12.4 Backtest Quality Score + plateau sweep; P12.5 strategy score on the calibrator; P12.7 Monte Carlo ruin/streak/TTR table; P12.8 the net anchor — the calibrator multiplier and the setup-proven gate judge `E_net`, not `E_gross`; P12.9 market calendars — `data/calendar.py` gives each venue a trading calendar, so scheduled OTC-gold closures stop being read as missing data; **P12.10 XAU bid/ask cost model — `data/costs.py` auto-detects gold instruments and applies a spot-market model with spread-based costs, no funding, ECN commission; Dukascopy blocker #2 closed**). Next: **calibration-key source provenance**, then micro-live. |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-15 (this branch `arena/01a0069a-sky`): P12.10 — XAU bid/ask cost model

Branched from `main` @ `d9410b90` (P12.9 merged). Inherited suite re-verified at
**671 pass / 1 skip** before any change. 0 regressions.
Tests **671 → 681 pass / 1 skip** (+10). Version **2.20.0 → 2.21.0**.
(`config.py` and `pyproject.toml` bumped in step; wheel gate green.)

**Why:** `calculate_trade_cost()` used a default `CostModel()` with
`market="perp"`, taker fees (0.05%/side) and funding — appropriate for crypto
perps but not for spot gold. A bid-only XAUUSD backtest was costed with crypto
assumptions, giving a misleading cost picture. This was blocker #2 of three
against the v2.19.0 Dukascopy XAU research book.

**What shipped:**
- `data/costs.py` — new `cost_model_for_symbol()` resolver auto-selects a
  spot-market model for gold instruments (symbols starting with `XAU` or `GOLD`):
  no funding, `DEFAULT_GOLD_COMMISSION_PCT = 0.005%` per side ECN commission,
  spread as the primary cost via the existing `SPREADS["XAUUSD"]` entry.
- `is_gold_symbol()` / `GOLD_SYMBOL_PREFIXES` — prefix-based detection.
- `calculate_trade_cost()` — when `cost_model` is None, calls
  `cost_model_for_symbol(symbol)` so every XAUUSD call auto-uses gold costs.
  An explicit `CostModel` argument still overrides auto-detection.
- `docs/DUKASCOPY_XAU_ADAPTER.md` — blocker #2 marked closed.

**Invariant kept:** Opt-in by symbol prefix, never by guess. BTCUSDT, ETHUSDT,
PAXGUSDT keep the crypto-perp default unchanged. An explicit `CostModel` always
wins over auto-detection. Crypto numbers are byte-identical.

**Files changed:** `data/costs.py`, `tests/test_costs.py`, `config.py`,
`pyproject.toml`, `CHANGELOG.md`, `TODO.md`, `SESSION_STATE.md`,
`docs/DUKASCOPY_XAU_ADAPTER.md`.

### Session 2026-08-15 (this branch `arena/01a00521-sky`): P12.9 — market calendars

Branched from `arena/01a004b0-sky` @ `94a6de0`. Inherited suite re-verified at
**636 pass / 1 skip** before any change. 0 regressions.
Tests **636 → 671 pass / 1 skip** (+35). Version **2.19.0 → 2.20.0**.
(`config.py` and `pyproject.toml` bumped in step; wheel gate green.)

**Why:** every quality check assumed a 24/7 market, so "the venue was shut" and
"our collection broke" were the same event. A complete week of spot gold holds
~53h of scheduled closure, which the crypto-first logic read as a 30%+ gap
fraction and a dead feed — quarantining a *healthy* series. This was blocker #1
of three against the v2.19.0 Dukascopy XAU research book.

**What shipped:**
- `data/calendar.py` (new) — `MarketCalendar` protocol; `crypto-24x7` and
  `xau-otc` (Sun 18:00 ET open, Fri 17:00 ET close, 17:00–18:00 ET daily break,
  1 Jan / 25 Dec closed), DST-aware via stdlib `zoneinfo`; `expected_bars`,
  `open_bars_between`, `closed_bar_count`, `split_by_session`, `calendar_for`,
  `get_calendar`, `describe`.
- `data/gaps.py` — `detect_gaps(frame, tf, calendar=None)` skips spans that are
  entirely scheduled closure and counts only owed OPENs in partial ones.
- `data/quality.py` — `checks_on_frame(..., calendar=None)` measures `expected`
  and `age_mult` in trading bars, adds `calendar` / `market_open` /
  `closed_bars`; `series_health` / `series_item` resolve the calendar from the
  series identity; `verdict_for` reports `market closed — clean`.
- `data/backfill.py` — CSV import report carries `calendar` and
  `closed_session_bars`; `gaps_found` no longer counts the gold weekend.
- `main.py` — new `calendar` subcommand (`--symbol --tf --exchange --market
  --calendar --at --series --root --json`); the `backfill --from-csv` output
  prints the calendar and a calendar-aware `gaps_remaining`.
- `docs/MARKET_CALENDAR.md` (new); blocker #1 closed in
  `docs/DUKASCOPY_XAU_ADAPTER.md`.

**Invariant kept:** it can only remove false alarms. Opt-in by venue (unknown
venues, unknown symbols and Binance `PAXGUSDT` all keep 24/7 rules), crypto
outputs byte-identical, and in-session holes / stale-during-session / corrupt
OHLC all still quarantine. The graduation bar is untouched.

**Files changed:** `data/calendar.py` (new), `data/gaps.py`, `data/quality.py`,
`data/backfill.py`, `main.py`, `tests/test_calendar.py` (new), `config.py`,
`pyproject.toml`, `ARCHITECTURE.md`, `docs/MARKET_CALENDAR.md` (new),
`docs/DUKASCOPY_XAU_ADAPTER.md`, `CHANGELOG.md`, `SESSION_STATE.md`, `TODO.md`.

### Session 2026-08-15 (this branch `arena/01a00490-sky`): P12.8 — the net anchor

Branched from `main` @ `2dd49a6`. 0 regressions.
Tests **620 → 631 pass / 1 skip** (+11). Version **2.17.0 → 2.18.0**.

**The gap this closed.** P12.6 made every measurement net of costs, and the
desk has been reporting `E_net` honestly ever since. But the two places that
*act* on a measurement were never migrated, so the project measured with one
number and decided with another:

| site | read | consequence |
|---|---|---|
| `multiplier_from_score()` | `E_gross` | `+0.055R` gross / `−0.118R` net → **×1.008 boost** on a losing setup |
| `setup_proven()` (A6/B10) | `backtest_expectancy`, `paper_expectancy` (gross) | a cost-flipped setup could be called **proven** |

**What shipped:**
- `data/strategy_score.py` — `multiplier_from_score(..., expectancy_net=None)`;
  the sign anchor is the net number when known, gross only as fallback.
  The cost-flipped case now yields **×0.982** instead of ×1.008.
- `brain/calibrator.py` — `build_profile()` passes `expectancy_net`; the
  `CALIBRATE_FILTER` negative-expectancy filter judges net too; `describe()`
  states which anchor is in use.
- `brain/risk_gate.py` — `setup_proven()` requires positive **net** expectancy
  where available, returns `proven_on: "net" | "gross"`, and the gate's block
  message names the failing condition (expectancy vs. sample floors).
- `data/database.py` — `setup_stats()` returns `backtest_expectancy_net` /
  `paper_expectancy_net` from the stored `rr_net` column; `None` when absent.
- `tests/test_net_anchor.py` (new) — 11 tests, including a monotonicity
  property: the net anchor can only lower a multiplier, never raise one.

**Invariant kept:** strictly tighter, never looser. No change to the
graduation bar, the sample floors, or any read-only guarantee.

**Files changed:** `data/strategy_score.py`, `brain/calibrator.py`,
`brain/risk_gate.py`, `data/database.py`, `tests/test_net_anchor.py` (new),
`config.py`, `pyproject.toml`, `CHANGELOG.md`, `SESSION_STATE.md`, `TODO.md`.

### Session 2026-08-15 (branch `arena/01a0046d-sky`): P12.7 — Monte Carlo risk-of-ruin table

Branched from `main` @ `5384a84`. 0 regressions.
Tests **613 → 620 pass / 1 skip** (+7). Version **2.16.0 → 2.17.0**.
(`config.py` and `pyproject.toml` bumped in step.)

**What shipped:**
- `brain/analytics.py` → `monte_carlo_ruin_table()` — resamples the NET
  realised paper book (costs included; missing `rr_net` is computed via
  `data.costs.calculate_trade_cost`). For each swept risk %/trade it
  returns expected max drawdown, ruin probability, prob final equity below
  start, terminal median/p5/p95, median longest losing streak and
  median/mean time-to-recovery (trades). A `historical` block records the
  actual sequence's longest loss streak, median/max TTR and max drawdown.
- `main.py` — new `monte` subcommand prints the boxed table (human or
  `--json`); `python main.py risk` points the user to it.
- `web/app.py` — `GET /api/monte` + `monte` key embedded in `GET /api/risk`;
  dashboard Risk card renders the sweep table and historical metrics.
- `mcp_server.py` — root `risk` tool embeds `ruin_table`.
- `ai/mcp_server.py` — new `cryptobrain_monte` tool; `cryptobrain_risk`
  also returns `ruin_table`.
- `tests/test_mcp_server.py` — `TOOL_NAMES` updated for the new tool.
- `tests/test_monte_carlo.py` (new) — 7 tests covering empty book,
  structure, drawdown scaling with size, seed determinism, historical
  streak, sim-sample exclusion, direct `rows=` input.
- Versions: `config.py` / `pyproject.toml` **2.16.0 → 2.17.0**; root MCP
  server **1.8.0 → 1.9.0**.

**Files changed:** `brain/analytics.py`, `main.py`, `web/app.py`,
`mcp_server.py`, `ai/mcp_server.py`, `tests/test_mcp_server.py`,
`tests/test_monte_carlo.py` (new), `config.py`, `pyproject.toml`,
`CHANGELOG.md`, `TODO.md`, `SESSION_STATE.md`.

### Session 2026-08-15 (this branch `arena/01a00446-sky`): P12.5 — Strategy Score on the calibrator

Branched from `main` @ `fd4aa51` (PR #25 merged). 0 regressions.
Tests **598 → 613 pass / 1 skip** (+15). Version **2.15.0 → 2.16.0**.

**What shipped:**
- `data/strategy_score.py` — strategy score 0–100 per calibration key as
  `E_R × sample-quality × regime-fit × execution` (weighted geometric
  mean, NET of costs; sample-quality = P12.4's
  `backtest_quality_score()` in full).
- `brain/calibrator.py` — trust dial multiplier from score; profile entries
  gain `strategy_score`, `strategy_band`, `strategy_components`,
  `expectancy_net`.
- Surfaces: `learn` CLI, `GET /api/learning`, dashboard Calibration card.
- Tests: 15 new (`tests/test_strategy_score.py`).

### Session 2026-08-15 (this branch `arena/01a00431-sky`): P12.4 — Backtest Quality Score 0–100

Branched from `main` @ `e07fa43` (PR #24 merged). 0 regressions.
Tests **573 → 598 pass / 1 skip** (+25). Version **2.14.0 → 2.15.0**.
MCP `SERVER_VERSION` **1.7.0 → 1.8.0**.

**What shipped:**
- `data/quality_score.py` (new module) — pure `backtest_quality_score(rows, …)`:
  edge (E_net vs bar, shape-discounted), curve robustness (top-5
  concentration / max-DD ÷ |total R| / chronological segments), sample
  confidence (N_eff vs min_decided + CI95 significance), and the BT5
  parameter-plateau test that caps an isolated-peak edge at 50. Empty
  books degrade to `quality: None` with a reason.
- `run_quality_sweep()` + `python main.py quality` — store-only plateau
  sweep re-grading `min_confidence ± 5` (clamped [40, 90], deduplicated,
  base point guaranteed; `grade_fn` injectable for offline tests).
- `data/scorecard.py` — `build_scorecard(..., quality=True)` embeds the
  block; `scorecard_from_db` / `scorecard_from_store` forward the flag;
  `print_scorecard` prints it.
- `main.py` — `scorecard --quality`; new `quality` subcommand.
- `web/app.py` — `/api/scorecard?quality=1`; dashboard `STRATEGY SCORECARD`
  card renders the quality block.
- `mcp_server.py` — `scorecard` tool `quality` argument; v1.8.0.
- Tests: 25 new (`tests/test_quality_score.py`).

**Measured on the demo store (sample CSV, 500 × 15m bars, spot):**
- `scorecard --source store --quality` → **25.9/100 fragile** (edge 0,
  robustness 38, sample 50, plateau n/a) — a losing book scores like a
  losing book.
- `quality` → **23.3/100 fragile**, plateau 0.0 (0/3 conf points
  positive), `plateau_cap: True` — the isolated-peak guard is live.

**Files changed:** `data/quality_score.py` (new), `data/scorecard.py`,
`main.py`, `web/app.py`, `mcp_server.py`, `tests/test_quality_score.py`
(new), `pyproject.toml`, `CHANGELOG.md`, `TODO.md`, `README.md`,
`docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `docs/HANDOVER_2026-08-15_P12_4.md`
(new), `SESSION_STATE.md`.

### Session 2026-08-15 (this branch `arena/01a003f9-sky`): P12.6 — fees-first `E_net` & conditioned expectancy

Branched from `main` @ `58ed864` (PR #22 merged). 0 regressions.
Tests **552 → 567 pass / 1 skip** (+15). Version **2.12.0 → 2.13.0**.
MCP `SERVER_VERSION` **1.5.0 → 1.6.0**.

**What shipped:**
- `data/costs.py` (new module) — `CostModel` and `calculate_trade_cost()`,
  `get_funding_rate_as_of_t()`. Models taker/maker/spot fees, spreads,
  slippage, and direction-aware funding in R units scaled to stop distance.
- `data/backtester.py` — `GradedPlan` and `_evaluate()` attach `rr_net`,
  `fee_r`, `slip_r`, `funding_r`, `cost_r`. `_aggregate()` computes gross
  and net metrics.
- `data/database.py` — `_migrate()` adds `rr_net`, `fee_r`, `slip_r`,
  `funding_r`, `cost_r` to `backtest_results` and `paper_trades`.
  `save_backtest_rows()` persists all net metrics.
- `data/scorecard.py` — `trade_stats()` and `build_scorecard()` calculate
  gross and net performance (`expectancy_net`, `win_rate_net`, `pf_net`,
  `total_r_net`, `max_drawdown_r_net`, `sharpe_net`, `sortino_net`,
  `calmar_net`, `cost_r`, `fee_r`, `slip_r`, `funding_r`).
  `conditioned_splits()` supports funding regime and CVD order-flow splits.
  `print_scorecard()` prints the boxed gross-vs-net comparison and cost drag.
- `data/validation.py` & `data/simulator.py` — `meets_bar()` and
  `graduation_status()` evaluate against the restated **NET** bar.
- `main.py` — `python main.py scorecard [--no-costs] [--maker] [--conditioned] [--json]`.
- `web/app.py` & `mcp_server.py` — `/api/scorecard` and MCP `scorecard` tool
  exposing net metrics, cost drag, and conditioned splits.

**Measured cost impact on real BTCUSDT 15m data:**
- Expectancy: **+0.001R gross → −0.369R net** (cost drag −0.370R: fee 0.262R, slip 0.105R, funding 0.004R).
- `Sell Pullback` (+0.974R net, PF 3.99 net) and `FVG Retest Sell` (+1.161R net, PF 6.43 net) survive net.
- `Breakout Buy` (−0.904R net, PF 0.225 net) confirmed as heavy drag.

---

## Remaining work (prioritised)

1. **Calibration-key source provenance** (Dukascopy blocker #3) — saved
   calibration keys do not carry candle-source provenance. A Dukascopy XAU
   backtest must not silently recalibrate the live PAXG proxy.
2. **TODO-7** — human pastes the wheel-gate job into the **real**
   `.github/workflows/ci.yml` (the `docs/` copy is inert).
3. **TODO-8** — human protects `main` (require PR). Token: HTTP 403.
4. **TODO-11 (P11)** — continue the paper-book grind/live-data proof;
   the graduation bar remains closed and unchanged.
5. **TODO-9 / TODO-10** — Dify then LibreChat (parked).

---

## Known problems / caveats

1. **D1–D5 are answered.** See `ROADMAP_AGENT_REACH_UPGRADE.md` §4.
2. **Arena's GitHub integration: one PR per chat session.** Do the work,
   then open **one** PR as the closing step.
3. **`mcp>=1.0` is listed in `requirements.txt` but not required**
   for the zero-dep `mcp_server.py`.
4. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   committed sample data is stale by design. Expected offline.
5. **Arena cannot push under `.github/workflows/`.** The wheel-gate
   job spec lives at `docs/.github/workflows/ci.yml` (TODO-7).
6. **`CHANGELOG.md` is current** through v2.16.0.
7. **Real market data is imported offline**: Binance spot BTCUSDT 1m
   (696,960 bars, sha256-pinned `c4ad6029…b934b7`). The store is
   gitignored; re-import with `backfill --from-csv` if starting in a clean sandbox.
8. **Costs are now integrated via P12.6**: `E_net = E_gross − fees − slip − funding`.
   The graduation bar is enforced NET of costs.
9. **Sample counts are now overlap-corrected (P12.3.3)**: the scorecard
   reports `N_eff = N / overlap` and widened CI/SE. The `min_decided`
   floor still reads raw N (flagged via `n_eff_below_min_decided`) — the
   floor revisit is the next decision, not this one.
10. **P12.4 quality scores what P12.6/P12.3.3 made real**: the plateau
    sweep (`python main.py quality`) re-grades the stored series at
    `min_confidence ± 5` — on a clean sandbox with no store it returns a
    clear error, never a score. The `scorecard --quality` block shows
    "plateau n/a" without that re-grade sweep.
11. **P12.5 scores what the calibrator already gates**: only keys with
    `n >= min_n` (default 100) get a strategy score — below the gate there
    is no entry at all, exactly as before. The score is a report on what
    passed the gate, never a gate-bypass. It is computed from the key's
    decided rows via the scorecard's row adapters; the multiplier keeps
    the gross-expectancy sign anchor and is only *modulated* by the score
    (trust floor 0.6) — a deliberate middle ground between the old formula
    and a hard score-only gate.
12. **Freqtrade was reviewed and rejected (F1–F8)** (`docs/FREQTRADE_REVIEW.md`).
13. **Backtrader was reviewed and rejected (BT1–BT8)** (`docs/BACKTRADER_REVIEW.md`).
14. **`config.VERSION` was stale after P12.4** (2.14.0 instead of 2.15.0) —
    fixed to **2.17.0** in this session; `config.py` and `pyproject.toml` are
    now in step.
16. **P12.8 changed decisions, not measurements.** The scorecard, quality
    score and strategy score were already net-correct; only the calibrator
    multiplier and the proven gate were reading gross. If a setup's
    multiplier or `proven` flag looks *worse* than in a pre-2.18.0 run, that
    is the fix working — the earlier value was measuring the wrong number.
    Where `rr_net` is absent (old rows, costs disabled) behaviour falls back
    to gross exactly as before, so historical books do not silently change
    meaning; `proven_on` says which anchor was used.
15. **P12.7 is a report, not a gate-bypass**: the Monte Carlo ruin table
    reads the decided paper book NET of costs and surfaces survivability
    estimates. It does not approve trades, loosen the graduation bar, or
    replace the risk gate.
17. **Dukascopy XAU is still research-only — but for one reason now, not
    three.** P12.9 closed the market-calendar blocker; P12.10 closed the XAU
    bid/ask cost model blocker. Open: saved calibration keys do not carry
    candle-source provenance (blocker #3). Do not use `backtest --save` on this
    book yet.
18. **A calendar can only remove false alarms, never hide a hole.** It is
    opt-in by venue: anything not explicitly `dukascopy` + an XAU symbol keeps
    the 24/7 crypto calendar, including Binance `PAXGUSDT`, which really does
    trade 24/7. If a gold series ever *should* be quarantined, it still is —
    stale-during-session, in-session holes and corrupt OHLC are unaffected.
19. **Early/partial closes are deliberately unmodelled.** Only 1 Jan and
    25 Dec are holidays. An unmodelled early close shows up as a real gap
    (visible, safe); an over-broad holiday list would silently swallow one.

---

## Next recommended action

1. **Next code build — calibration-key source provenance** (Dukascopy blocker
   #3): saved calibration keys do not carry candle-source provenance, so a
   Dukascopy XAU backtest `--save` could silently recalibrate the live PAXG
   proxy. Add a `source` dimension to the calibration table and gate the
   calibrator on source match.
2. **On the host holding the real BTC store/DB**, re-run `backtest --save` +
   `learn`; the calibration profile remains stale in this clean checkout. Do
   not substitute demo data.
3. Optionally acquire version-pinned Dukascopy XAU m1 **bid** or **ask** CSV
   and import it with a SHA pin using `docs/DUKASCOPY_XAU_ADAPTER.md`; the
   import, quality checks and now cost model are all gold-aware
   (`python main.py calendar --symbol XAUUSD --tf 1h --series`). Run
   validate/backtest/quality **without `--save`**.
4. **Micro-live** only after the existing graduation bar opens and a human
   explicitly approves progression. This work does not move that bar.
5. A human does TODO-7 + TODO-8 from [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
6. Do not install Freqtrade or Backtrader and do not loosen the graduation bar.

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md. Fetch and diff origin/main first,
> and confirm the P12.10 PR merged. P12.1–P12.9, the Dukascopy XAU adapter,
> market calendars and **P12.10 XAU bid/ask cost model** are shipped — do not
> rewrite `data/calendar.py`, re-derive the gold week, make the calendar apply
> to Binance, or rework the gold cost model. The next build is
> **calibration-key source provenance** (Dukascopy blocker #3). All earlier
> P12 milestones are shipped: do not redo the locked protocol, the
> negative-shift guard, the boxed scorecard, the tie-break, the real data
> import, trade cost modeling, the overlap-corrected effective sample size,
> the Backtest Quality Score, the strategy score on the calibrator, the Monte
> Carlo ruin/streak/TTR table, or the net anchor on the calibrator/proven gate.
> Keep the existing grader/store, do not adopt Freqtrade or Backtrader, and do
> not loosen the graduation bar.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# 681 passed, 1 skipped
```

XAU cost model (P12.10):
```bash
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_costs.py -q
# 22 passed  (12 original P12.6 + 10 new P12.10 gold tests)
```

Wheel gate:
```bash
DEMO_MODE=1 .venv/bin/python ci/wheel_gate.py
# builds cryptobrain-2.21.0-py3-none-any.whl ; no duplicate entries
```

Market calendar (P12.9):
```bash
python main.py calendar                                   # is spot gold open?
python main.py calendar --at 1783684800000 --json         # a specific instant
python main.py calendar --symbol XAUUSD --tf 1h --series  # stored-series health
python main.py calendar --exchange binance --market perp --symbol BTCUSDT
```

Monte Carlo risk-of-ruin table (P12.7):
```bash
python main.py monte                          # boxed human table
python main.py monte --json --samples 5000    # machine-readable
python main.py monte --risk-pcts 0.5,1,2      # custom sweep
curl -s localhost:8080/api/monte              # HTTP
curl -s localhost:8080/api/risk               # includes monte block
```

Calibration with the P12.5 strategy score:
```bash
python main.py learn                          # profile + strategy score per key
python main.py learn --json                   # full profile incl. strategy_components
curl -s localhost:8080/api/learning           # HTTP (dashboard Calibration card reads it)
```

Readiness strip:
```bash
DEMO_MODE=1 python main.py doctor --strip          # CLI text
DEMO_MODE=1 python main.py doctor --strip --json   # CLI JSON
curl -s localhost:8080/api/readiness               # HTTP
# MCP: tools/call {"name": "readiness", "arguments": {}}
```

Scorecard with costs (P12.6) + quality (P12.4):
```bash
python main.py scorecard --source store --market spot --symbol BTCUSDT --tf 15m --bars 1000
python main.py scorecard --source store --market spot --symbol BTCUSDT --tf 15m --bars 500 --conditioned
python main.py scorecard --source db --quality        # embed the quality block (no plateau)
python main.py quality --symbol BTCUSDT --tf 15m --bars 500   # full plateau sweep (store-only)
```

## Last commit

```
(THIS SESSION) feat(P12.10): XAU bid/ask cost model — gold auto-detection in data/costs.py
d9410b9  feat(P12.9): market calendars — a scheduled closure is not a gap (#32)   # parent
```

P12.10 work sits on `arena/01a0069a-sky` and will be pushed to origin as a
session branch. See `git log --oneline -3`.

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, on your Arena session branch.

First, inspect the GitHub repository before making changes:
- git fetch origin, and diff your branch against origin/main —
  parallel sessions merge while you work; reconcile before building.

Read in this order:
1. SESSION_STATE.md         (current state, current TODO, last commit)
2. TODO.md                  (prioritised remaining work)
3. ARCHITECTURE.md          (module map + invariants)
4. CHANGELOG.md             (what shipped, when)
5. README.md                (user-facing overview)
6. ROADMAP_AGENT_REACH_UPGRADE.md  (the P7/P8/P9 plan + D1–D5 decisions)
7. docs/FREQTRADE_REVIEW.md        (F1–F8 — do not install a bot)
8. docs/BACKTRADER_REVIEW.md       (BT1–BT8 — do not add a second grader)

Then inspect the relevant source files and tests.

Your job is to continue from the exact state left by the previous
session, starting with the top-priority item in TODO.md.

Rules:
- Do NOT recreate or redesign completed components.
- Do NOT assume anything that is not present in the repository.
- Preserve existing architecture unless there is a demonstrated
  reason to change it.
- Before modifying code, explain briefly what you found and what
  the next implementation step is.
- Implement the next highest-priority task from TODO.md.
- Run the relevant tests after implementation.
- Fix failures before considering the task complete.
- Maintain test count at ≥ 567 pass / 1 skip.
- Update SESSION_STATE.md with completed/current/remaining/known/
  next action. Full-document reconciliation, not append-only.
- Update CHANGELOG.md.
- Commit and push.

If the task is too large for the remaining session, split it into a
safe checkpoint rather than leaving the repository in an undocumented
state.

Before ending the session, open ONE pull request from this branch to
main (Arena allows one PR per chat session). Do not merge it yourself.
```

## End-of-session checklist (run before closing this session)

1. [x] Finish or safely stop the current task. — **P12.10 shipped**
   (XAU bid/ask cost model in `data/costs.py`, gold auto-detection,
   Dukascopy blocker #2 closed).
2. [x] Run `DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q` —
   **681 pass / 1 skip** (+10: `tests/test_costs.py`). Inherited baseline
   re-verified at 671/1 before any change.
3. [x] Fix any obvious failures. — none left open.
4. [x] Update `SESSION_STATE.md` with the exact current state.
5. [x] Update `TODO.md` — P12.10 marked shipped; next is calibration-key
   source provenance (Dukascopy blocker #3).
6. [x] Update `CHANGELOG.md` — 2.21.0 P12.10 entry.
7. [x] Record all files changed in `SESSION_STATE.md`.
8. [x] Record the last successful test command.
9. [x] Record the last commit reference.
10. [x] Record any known bugs or unresolved issues.
11. [ ] `git add` / `git commit` — commit and push to `origin/arena/01a0069a-sky`.
12. [ ] Open the session PR as the closing step — PR from
    `arena/01a0069a-sky` (P12.10).
