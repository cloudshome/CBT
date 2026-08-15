# Changelog

All notable changes to **CryptoBrain / SKY** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> **Note:** this changelog was created on 2026-08-11. Pre-v2.0.0 history
> lives in the `MERGE_NOTES.md` provenance document. The `pyproject.toml`
> `version` is the source of truth; this file documents what shipped.

---

## [2.14.0] — 2026-08-15 · branch `arena/01a00417-sky`

MINOR bump: **P12.3.3 — effective sample size in the scorecard.**
A walk-forward grade steps `step` bars and follows each plan over
`horizon_bars` future bars, so consecutive samples overlap heavily — a
24h horizon on 15m bars graded at step 3 shares 96/3 ≈ 32 windows, so
"384 decided" was really ~12 independent observations. The scorecard now
reports the honest independent sample size `N_eff = N / overlap`
(`overlap = horizon_bars / step`) alongside the raw trade count, and
widens every standard error and 95% confidence interval with
`SE = σ / √N_eff` instead of `σ / √N`. The graduation-bar *floor* is
unchanged for now (`min_decided` still reads raw N); the report flags
`n_eff_below_min_decided` so the desk can see when the overlap-corrected
sample is thin — the floor revisit is the next decision, not this one.

### Added
- **`overlap_factor()` / `effective_sample_size()`** in `data/scorecard.py`
  — per-row window-overlap factor (`horizon_bars / step` for walk-forward
  backtest rows; 1.0 for paper trades, which are real non-overlapping
  positions; 1.0 when horizon/timeframe/step are unrecorded, rather than
  inventing a divisor).
- **`step` column** on `backtest_results` (additive migration + save path)
  so the scorecard computes the overlap factor exactly instead of assuming
  the default; `python main.py backtest --save` records it.
- **`n_eff`, `overlap`, `expectancy_se`, `expectancy_ci95`,
  `expectancy_net_se`, `expectancy_net_ci95`** on every scorecard stats
  block (overall and each split), threaded through `trade_stats()`,
  `_split()`, `conditioned_splits()`, `build_scorecard()`,
  `scorecard_from_db()`, and `scorecard_from_store()`.
- **CLI** `python main.py scorecard --step` now applies to the stored-book
  path too (overlap correction); the printed block shows
  `(~N_eff independent, overlap ×K)` and the net 95% CI, plus a warning
  when `N_eff < min_decided`.
- Tests: 6 new (`test_overlap_factor_*`, `test_effective_sample_size_*`,
  `test_trade_stats_reports_honest_n_eff_and_widens_ci`,
  `test_build_scorecard_flags_n_eff_below_min_decided`,
  `test_backtest_rows_roundtrip_step_and_horizon`).
  Suite **567 → 573 pass / 1 skip** (+6).

No trading orders or private credentials added (invariant #1 preserved).
Next on the ladder: **P12.4 backtest quality score** (now scoring something
real), then P12.5, then P12.7 Monte Carlo ruin.

---

## [2.13.0] — 2026-08-15 · branch `arena/01a003f9-sky`

MINOR bump: **P12.6 — fees-first `E_net` & conditioned expectancy.**
Costs are now integrated into every performance measurement in SKY:
`E_net = E_gross − fees − slip − funding`, where every term is scaled
into R units per trade. Fees + spread lead the cost calculation (at
measured median stop distances of 0.823%, a 0.10% round-trip taker fee
costs **0.1215R**, ~40× funding at typical 1.8h holds). Funding is joined
as-of-T from stored derivatives series (or default 0.01%/8h). The
graduation bar is enforced **NET of costs** ($E_{\text{net}} \ge +0.50\text{R}$,
$WR_{\text{net}} > 55\%$, $PF_{\text{net}} \ge 1.5$), turning previously
cosmetic gross numbers into actionable trading evidence.

### Added
- **`data/costs.py`** — `CostModel` and `calculate_trade_cost()`,
  `get_funding_rate_as_of_t()`, supporting taker/maker/spot fee
  schedules, spread & slippage, and direction-aware funding (long pays
  positive funding, short receives positive funding credit).
- **Grader & Database Net R** — `GradedPlan` and `backtest_results` /
  `paper_trades` tables gained `rr_net`, `fee_r`, `slip_r`, `funding_r`,
  and `cost_r` columns through additive migrations.
- **Scorecard Net Metrics & Conditioned Splits** — `trade_stats()` and
  `build_scorecard()` report both gross and net metrics (`expectancy_net`,
  `win_rate_net`, `pf_net`, `total_r_net`, `max_drawdown_r_net`,
  `sharpe_net`, `sortino_net`, `calmar_net`, `cost_r`, `fee_r`,
  `slip_r`, `funding_r`), and conditioned splits by funding regime
  and CVD order flow (`--conditioned`).
- **Surfaces** — CLI `python main.py scorecard [--no-costs] [--maker] [--conditioned]`,
  HTTP `GET /api/scorecard`, MCP `scorecard` tool (v1.6.0), and the
  dashboard learning card showing cost drag and net expectancy.
- Tests: `tests/test_costs.py` (12 new tests) + scorecard net metric &
  conditioned split tests (3 new tests). Suite **552 → 567 pass / 1 skip** (+15).

No trading orders or private credentials added (invariant #1 strictly preserved).
Next on the ladder: **P12.3.3 effective sample size**.

---

## [2.12.0] — 2026-08-14 · branch `arena/01a00034-sky`

MINOR bump: **P12.3.2 — real market data.** The first real market data
ever entered the project: Binance spot BTCUSDT 1m, 2025-01-01 →
2026-04-30, 696,960 bars, from Binance's official public archive
(`data.binance.vision`), sha256-pinned and verified on import. P11,
P12.1 and P12.3 were re-run on it and the published numbers moved —
down, as `docs/PATH_TO_REAL_MONEY.md` predicted. The graduation bar was
not touched; the sealed protocol now fails every window on real data.

### Added
- **`data/backfill.py::backfill_from_csv`** — offline CSV import through
  the same adapter boundary as the REST backfill (validate → sort →
  `normalise_klines` → `CandleStore.write`). Idempotent by the store's
  upsert PK; reports duplicates, sanity-dropped rows, misalignment and
  gaps; `--csv-sha256` pins provenance and refuses mismatches.
- **`data/store.py::StoreClient`** — `klines()`-shaped reader over the
  Parquet store, so the offline walkers run on stored real candles.
- **CLI** — `backfill --from-csv PATH [--csv-sha256 HEX] [--rollup]`;
  `backtest --source store --market spot [--step N]`;
  `simulator --source store --market spot`; `scorecard --since/--until`
  (epoch-ms or YYYY-MM-DD) so one book can hold several data eras.
- **`docs/REAL_DATA_RUN_2026-08-14.md`** — provenance, repro commands,
  and the side-by-side synthetic-vs-real numbers.
- Tests: `tests/test_backfill_csv.py` (11) + scorecard era-filter tests
  (2). Suite **539 → 552 pass / 1 skip** (+13).

### Measured (the milestone's deliverable)
- **P12.1 sealed protocol, first real run** (12,000 real 15m bars, 1h
  primary): train −0.452R, val −0.251R, **oos −0.101R**, recent −0.429R
  — FAIL on every window (seal `1223819609d75213`).
- **P12.3 scorecard, first real run** (24,215 decided): +0.180R / 32.2%
  WR / PF 1.266 all-horizon; per horizon 1h −0.326R, 4h −0.032R,
  **24h +0.400R gross** (≈ +0.28R net at measured taker costs — below
  the restated +0.50R net bar). **Breakout Buy −0.630R** (6,062
  decided, negative at every horizon) — real-data confirmation of the
  prune case.
- **P11 grind, first real run**: +8,300 backtest + 494 paper samples;
  gate still closed (+0.348R / 36.8% WR / PF 1.55 / compliance 100%).

No strategy, risk-gate, graduation-bar, OOS-seal, order, or dependency
behavior changed. P12.6 (costs) is next on the ladder.

---

## [2.11.1] — 2026-08-14 · branch `arena/019fffe5-sky`

PATCH bump: **the two graders now agree on an ambiguous candle**, plus
`docs/PATH_TO_REAL_MONEY.md` — a measured audit against the project's
actual aim, and a proposed reordering of the P12 ladder.

### Fixed
- **`data/backtester.py::_evaluate()` — same-bar SL/TP ties graded 3R too
  generously.** When one candle touches both the stop and the target the
  ordering is undecidable from bar data. `data/paper_trading.py::exit_event`
  has always resolved this conservatively (stop wins, `ambiguous: True`),
  and `docs/BACKTRADER_REVIEW.md` §7.1 cites that written-down rule as a
  reason SKY needs no second engine. The backtester did **not** implement
  it: the first-touch comparison used a strict `<`, so on a tie
  (`first_sl == first_tp1`) control fell through to the take-profit branch
  and the candle was graded `PARTIAL_WIN +2.0R` where the paper trader
  graded `STOP_LOSS -1.0R`. Now `<=`, so the stop wins the tie on both
  sides of the book and the two graders can never disagree again.
  - Measured no-op on current data: **0 ties across 3,263 decided
    synthetic trades** (5 seeds). Random-walk candles are too small to
    span a 1R stop and a 2R target in one bar, which is exactly why this
    survived undetected. Real wick/liquidation candles hit it routinely,
    so the fix lands *before* real data rather than after.
  - **Expect measured expectancy to fall once real data arrives.** That
    fall is the correction, not a regression.

### Added
- **`GradedPlan.ambiguous_bar`** — in-memory diagnostic flag, `True` when
  the outcome was resolved by the conservative rule rather than observed
  ordering. Not persisted; on real data its rate tells you how much of a
  book rests on that assumption.
- **`docs/PATH_TO_REAL_MONEY.md`** — audit of the repo against the aim,
  with every figure measured at commit `342c66b`, not estimated:
  1. **No real market data has ever entered the project** — 0 `.parquet`
     files, 0 `paper_trades` rows; all 1,049 graded rows come from a
     seeded Gaussian random walk with no autocorrelation, fat tails,
     regime persistence or stop-hunt structure.
  2. **Costs are absent** (`EXECUTION_MODEL` defaults to `"none"`).
     Median stop distance is **0.823% of entry**, so a taker round trip
     costs **0.121R**: P12.3's +0.341R gross is ≈ **+0.22R net**. At the
     measured 1.8h median hold, **fees are ~40× funding** — which
     reverses P12.6's current emphasis.
  3. The same-bar disagreement fixed above.
  4. **Sample counts are inflated ~30×** — `step=3` against a 96-bar
     horizon overlaps ~32 neighbours, so 384 decided ≈ 12 independent.
- **5 regression tests** (`tests/test_backtester.py`) pinning the tie-break
  on both sides, asserting the backtester and paper trader return the
  identical verdict on identical input, and proving unambiguous candles
  are untouched.

### Changed
- **P12 ladder reordered** (`TODO.md`, `AI_ANATOMY_ROADMAP.md`,
  `docs/DATA_INFRASTRUCTURE_ROADMAP.md`). P12.4 would have scored a
  fiction — a robustness grade over a gross, cost-free number measured on
  a random walk. New order: **P12.3.1** tie-break (this release) →
  **P12.3.2 real data** → **P12.6 pulled forward, fees-first** →
  **P12.3.3 effective sample size** → P12.4 / P12.5 → micro-live last.
- **Graduation bar restated as net, not loosened.** The intent was always
  a real, tradeable +0.50R; measuring it gross quietly made it ~40%
  easier. The thresholds themselves (≥ +0.50R, > 55% WR, PF ≥ 1.5) are
  unchanged and remain enforced gross until P12.6 lands `E_net`.

### Unchanged
No signal, risk, execution, OOS-seal, order or dependency behavior. No
new dependency. F1–F8 and BT1–BT8 stay decided; still one grader.
Suite **534 → 539 pass / 1 skip**.

---

## [2.11.0] — 2026-08-14 · branch `arena/019fffe5-sky`

MINOR bump: **P12.3 — the boxed strategy scorecard**. One command, one
block: long/short, regime, session, Sharpe/Sortino/Calmar and holding
time over outcomes the grader already decided. This is a **report layer**
— it re-reads stored results and never re-grades, never re-optimises, and
never loosens the graduation bar.

### Added
- **`data/scorecard.py`** (new) — the P12.3 report engine:
  - `build_scorecard()` assembles one block from decided rows: overall
    stats plus `by_side`, `by_regime`, `by_session`, `by_setup` splits.
  - `trade_stats()` — expectancy, win rate, PF, avg win/loss, total R,
    max drawdown, win/loss streaks, best/worst, Sharpe, Sortino, Calmar,
    average/median holding time and how many trades were actually timed.
  - Row adapters, one honest shape per source: `rows_from_graded()`
    (in-memory `GradedPlan`s, single horizon), `rows_from_backtest_db()`
    (stored `backtest_results`), `rows_from_paper_db()` (the live paper
    book; holding time measured as `closed_ts - opened_ts`).
  - `scorecard_from_db()` (`backtest` | `paper` | `all`) and
    `scorecard_from_store()`; `print_scorecard()` renders the boxed block.
  - `session_of_hour()` / `session_of_ts()` bucket trades into
    asia / london / newyork from the existing `config` session windows.
- **CLI** — `python main.py scorecard` with `--source db|backtest|paper|store`,
  `--symbol`, `--tf`, `--min-decided`, `--exclude-sim`, `--json` and the
  backtest knobs. An empty book prints an actionable refusal and exits 1.
- **Web** — `GET /api/scorecard` and a `STRATEGY SCORECARD` dashboard card
  rendering the same block; the endpoint never 500s.
- **MCP** — read-only `scorecard` tool (`SERVER_VERSION` 1.4.0 → 1.5.0),
  so an agent reads the identical report the CLI prints.
- **Holding time is now recorded at grading time**: `GradedPlan` carries
  `holding_bars` / `holding_hours` (`None` while `OPEN`), both persisted by
  `save_backtest_rows()` into new `backtest_results` columns.

### Changed
- `data/database.py` — `backtest_results` gains `holding_bars` and
  `holding_hours`, added by the existing additive `_migrate()` path; rows
  written before this release read back as `NULL` and are reported as
  "not recorded" rather than silently counted as zero.
- `tests/test_web_api.py` — the `client` fixture now patches
  `config.DB_PATH` as well as the environment variable. `setenv` alone is
  read too late once `config` is imported, so these endpoint tests could
  reach the developer's real database; they are now genuinely isolated.

### Deliberately not done
- **No annualised Sharpe.** Scaling by `sqrt(trades_per_year)` on
  overlapping walk-forward samples inflated Sharpe from 0.27 to 36.7 in
  testing. The report states `span_days` and `trades_per_day` and labels
  every ratio per-trade.
- **No second grader, no new engine, no new dependency.**
  `data/backtester.py` remains the only grader (BT3/BT7).
- **The graduation bar is unchanged** (≥ +0.50R, > 55% WR, PF ≥ 1.5). The
  scorecard prints a verdict; it does not grant permission.

### Tests
- `tests/test_scorecard.py` (new, 37) — metric arithmetic, drawdown,
  streaks, session bucketing, split partitioning, DB adapters, sim-sample
  exclusion, PASS/FAIL/INSUFFICIENT_DATA verdicts, purity, and both CLI
  paths. `tests/test_web_api.py` +4, `tests/test_backtester.py` +1
  (holding-time contract), `tests/test_mcp_stdio.py` / `test_dashboard_js.py`
  inventories updated.
- Suite **492 → 534 pass / 1 skip**.

---

## [2.10.0] — 2026-08-13 · branch `arena/019ffb14-sky`

MINOR bump: **P12.2 — lookahead validation**. The validation engine
now has a deterministic, offline source guard for explicit future-peeking
row shifts, covered by the existing CI unit form. This is a research-integrity
check only: it does not change signal logic, grading semantics, the sealed
OOS protocol, or the graduation bar.

### Added
- **`data/validation.py`** — P12.2 AST scanner:
  - `scan_lookahead()` scans first-party `engine/`, `brain/`, and `data/`
    Python sources (or caller-supplied paths) and fails closed on
    `shift(-n)`, `shift(-1)`, and `shift(periods=-n)` style row offsets.
  - Source locations, offending expression, syntax/read errors, and a
    stable `PASS`/`FAIL` JSON report are returned; comments/docstrings are
    not executed or falsely reported.
  - `assert_no_lookahead()` provides the unit/CI assertion form;
    recursive-state analysis remains a later extension, as specified by
    P12.2's `(+ recursive later)` scope.
  - `print_lookahead()` renders the boxed `LOOKAHEAD VALIDATION — P12.2`
    report.
- **CLI** — `python main.py validate lookahead` (and `--json`; repeatable
  `--path` for a focused file/directory scan). The existing store-backed
  `python main.py validate` protocol is unchanged.
- **Tests** — four offline guards in `tests/test_validation.py`: the
  first-party source tree passes, a deliberately leaking `shift(-n)` /
  `shift(periods=-n)` feature fails, a causal `shift(1)` plus a
  docstring mention passes, and the CLI returns PASS/FAIL exit codes.
- **CI** — the existing `.github/workflows/ci.yml` offline pytest job
  runs the P12.2 unit form as part of the complete suite.

### Changed
- Version **2.9.0 → 2.10.0** (`config.py`, `pyproject.toml`).
- P12 status docs now mark P12.2 shipped and P12.3 as next; no recursive
  analysis is claimed early.

---

## [2.9.0] — 2026-08-13 · branch `arena/019ffafa-sky`

MINOR bump: **P12.1 — the SKY Quant Validation Engine's locked
walk-forward protocol (train / val / OOS / recent)** on our own
backtester + store. Report-only: nothing here places orders or feeds
`learn`.

### Added
- **`data/validation.py`** — the first P12 milestone
  ([`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md) §8 F5/F6,
  [`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md) §8 BT5/BT6):
  - `walk_forward_windows()` — chronologically locked, contiguous
    four-way split of the analyzed range. The engine warm-up belongs
    to no window; train absorbs the rounding remainder; bad fractions
    or a too-short series raise `ValidationWindowError`.
  - `bucket_by_window()` — a plan counts toward the window its
    **signal bar** (timestamp) belongs to; exits never re-bucket it.
  - `window_stats()` / `meets_bar()` — decided-trade statistics
    including profit factor, checked against the **live graduation
    bar** (`data.simulator.GRADUATION_CRITERIA` — E ≥ +0.50R,
    WR > 55%, PF ≥ 1.5) plus a per-window decided floor.
  - `protocol_verdict()` — the P12.1 done-when: a setup **cannot
    pass on the training window alone** (`FAIL`); passing requires
    train AND val; the sealed OOS/recent windows can only confirm
    (`PASS`) or warn (`PASS_WITH_WARNINGS`); too few samples is
    `INSUFFICIENT_DATA`, never a pass.
  - Sealed envelope (BT6): identical runs **reuse the stored seal**
    instead of silently re-deriving OOS; a config-fingerprint
    mismatch never reuses an old seal; `--reseal` re-opens it and
    the re-opening is appended to the seal history with a timestamp.
  - `run_validation()` / `run_validation_on_store()` — one
    walk-forward pass over the frame / stored Parquet series
    (P10.11's path), then per-window and per-setup verdicts.
  - `print_verdict()` — the boxed protocol report.
- **CLI `python main.py validate`** — store-only by design (four
  locked windows need history only the store can provide; a live
  500-candle fetch cannot hold them). Flags: `--exchange/--market/
  --bars/--step/--min-bars/--min-conf/--min-decided/--horizons/
  --train/--val/--oos/--recent/--json/--store-root/--seal-dir/
  --reseal`. Exit code 1 on error, 0 on a run.
- **`tests/test_validation.py`** — 17 offline tests: split tiling /
  fraction and length rejection, signal-bar bucketing, bar checks
  (including "silence is not an edge"), train-only FAIL,
  PASS_WITH_WARNINGS, INSUFFICIENT_DATA, seal round-trip +
  fingerprint gate + reseal history, end-to-end protocol run with
  seal reuse/reseal, and a guard test that `VALIDATION_CRITERIA`
  stays identical to `GRADUATION_CRITERIA`.
- **P11 gate unchanged** — still honestly closed (+0.263R / 34.1% /
  PF 1.40, below the ≥ +0.50R / > 55% / ≥ 1.5 bar). P12.1 does not
  loosen it; it adds the research-grade protocol around it.

### Changed
- Version **2.8.0 → 2.9.0** (`config.py`, `pyproject.toml`).
- Dashboard banner lists `validate`.
- Docs reconciliation: TODO-13 / SESSION_STATE / AI_ANATOMY_ROADMAP /
  FREQTRADE_REVIEW §8 / BACKTRADER_REVIEW §8 / README / ARCHITECTURE.

---

## [2.8.0 — P10.8–P10.12 addendum] · PR #18 — 2026-08-13

> Retroactive entry, added in the 2.9.0 session's reconciliation pass:
> PR #18 shipped five more P10 milestones without a changelog entry or
> version bump (`config.VERSION` stayed 2.8.0). Recorded here so the
> gap is closed.

### Added (PR #18)
- **P10.8** — vendored `lightweight-charts.standalone.js`;
  `renderLightweightChart()` (candlestick + histogram volume pane,
  `addHistogramSeries`); `/api/candles` feed.
- **P10.9** — market-tab cards `FUTURES — OPEN INTEREST & FUNDING`
  and `FLOW — CVD & VOLUME DELTA`, reading from `market_context` and
  the feature snapshot.
- **P10.10** — `data/ws_client.py`: public Binance WebSocket streams
  (`!forceOrder@arr` + klines), reconnect/backoff, graceful stop,
  offline-safe `DEMO_EVENT_STREAM`, singleton `get_client()`;
  `reconnect_state()` / `accumulation_stats()` feed the readiness
  strip and feature store. No `websockets` runtime dependency.
- **P10.11** — `data/backtester.py::run_backtest_on_store()` reads
  `CandleStore.read()` instead of a live fetch; honest error for
  missing/short series.
- **P10.12** — `data/feature_store.py`: `build_feature_table()`
  (price + derivatives + hidden_alpha + regime; 22 `FEATURE_COLUMNS`),
  `save_feature_table()` / `read_feature_table()`; one derived row
  per `(symbol, timeframe, ts)`.
- **P11 gate unchanged** — honestly closed (+0.263R / 34.1% /
  PF 1.40).

---

## [2.8.0] — 2026-08-13 · branch `arena/019ffab2-sky`

MINOR bump: **P10.7 — cross-exchange premium/discount + funding spread
as a stored series.** The live health probe is the same function
(generalised, not rewritten). Inputs only — no strategy, risk-gate, or
engine behaviour change.

### Added
- **`data/cross_exchange.py`** — Layer-4 series layer.
  - Venue registry (KuCoin + OKX + Bybit) + `snapshot_prices()` — the
    **single** probe health, preflight, and the collector all call.
    Output contract unchanged (`price` / `deviation_pct` / `flag`).
  - `snapshot_funding()` — public funding rates vs a Binance
    reference; kept separate so a missing funding endpoint cannot
    change the price-probe contract.
  - `CrossExchangeStore` — partitioned Parquet under
    `data/store/cross/**` (gitignored), same normalised row shape and
    upsert PK as P10.4. Metrics: `price`, `premium_pct`,
    `funding_rate`, `funding_spread`. Snapshot timestamps floor to
    15m (price) / 8h (funding).
  - `derive_premium()` = `(other / ref − 1) × 100` on common `ts`
    (zero-ref dropped). `derive_funding_spread()` = `other − ref`.
  - `FakeVenueTransport` + `DEMO_MODE=1` stay fully offline.
  - `CrossExchangeCollector` — derive Binance-vs-Bybit premium from
    the candle store, page Bybit funding history, persist one live/fake
    probe snapshot. Resumable, idempotent (a completed re-run adds
    zero rows).
- **`BybitClient.funding_history()`** — `GET /v5/market/funding/history`
  (`category=linear`). XAU / no perp → empty frame; transport fail →
  `None`.
- **CLI** — `python main.py cross collect|status` (`--since/--until/
  --no-snapshot/--dry-run/--json/--root`).
- **Tests** — `tests/test_cross_exchange.py` (20 offline) + 2 Bybit
  funding-page tests. The agent probe test now mocks Bybit V5
  `result.list` as well as KuCoin/OKX.

### Changed
- `brain/agent.py:_cross_exchange_probe` is a thin wrapper around
  `snapshot_prices`. `_CROSS_EXCHANGES` re-exports `VENUES`.
- Version 2.7.2 → **2.8.0** (`config.py`, `pyproject.toml`).
- Suite **449 → 471 pass / 1 skip** (+22), fully offline.

### Notes
- Health still skips the live probe in `DEMO_MODE`; the collector
  still writes offline via `FakeVenueTransport` / `SampleClient`.
- Store first. Do not turn a premium or a funding spread into a
  trading rule until the data proves it.

---

## [2.7.2] — 2026-08-13 · branch `arena/019ffa8d-sky`

PATCH bump: **Backtrader recommendation reviewed and rejected**.
Docs + contract tests only. No engine, risk-gate, or strategy
behaviour change. The desk is not rebuilt around a third-party
backtester, and the repo is not reset (considered, refused — second
time in a day).

### Added
- **`docs/BACKTRADER_REVIEW.md`** — keep/cut of a 22-section ChatGPT
  Backtrader audit against the live SKY desk. Decisions **BT1–BT8**:
  no `backtrader` dependency / vendored engine / adapter (BT1);
  no Cerebro rewrite (BT2); no second grader — “two fill semantics =
  two truths” (BT3, BT7); no entry parameter search (BT4, consistent
  with F3); the audit’s research discipline **confirms the F-named
  P12** and extends four done-whens — boxed strategy scorecard with
  Sharpe/Sortino/Calmar + session/L-S (P12.3), parameter-plateau test
  (P12.4), net-of-costs `E_net = E_gross − fees − slip − funding` with
  funding joined as-of-T (P12.6), risk-of-ruin table / worst-streak /
  recovery on the MC resampler (P12.7); sealed final-OOS (BT6 = F6);
  **no repo reset** (BT8).
- Contract tests in `tests/test_handoff_memory.py` so a future session
  cannot quietly add a second backtest engine or re-open BT1–BT8.

### Changed
- `TODO.md` — Backtrader added to out-of-scope; TODO-13 / P12
  definitions extended per BT5; next *code* is still **P10.7**.
- `SESSION_STATE.md`, `ARCHITECTURE.md` (invariant #13 extended),
  `AI_ANATOMY_ROADMAP.md`, `docs/DATA_INFRASTRUCTURE_ROADMAP.md`,
  `docs/INFRASTRUCTURE_LAYERS.md`, `PROFESSIONAL_PLAN_DECISIONS.md`,
  `BLUEPRINT.md`, `SKILL.md`, `README.md` — BT1–BT8 recorded.
- Version 2.7.1 → **2.7.2** (`config.py`, `pyproject.toml`).
- Suite **445 → 449 pass / 1 skip** (+4), fully offline.

---

## [2.7.1] — 2026-08-13 · branch `arena/019ffa5d-sky`

PATCH bump: **Freqtrade recommendation reviewed and rejected**,
reconciled onto merged P10.6 (PR #14). Docs + contract tests only.
No engine, risk-gate, or strategy behaviour change. The desk is not
rebuilt around a bot.

### Added
- **`docs/FREQTRADE_REVIEW.md`** — keep/cut of a 31-section ChatGPT
  Freqtrade audit against the live SKY desk. Decisions **F1–F8**:
  Freqtrade / Hyperopt / FreqAI out; strategy-catalog expansion out;
  repo reset out; the useful research-integrity ideas become **P12**
  (walk-forward / OOS / lookahead / quality score / strategy score /
  conditioned expectancy / MC ruin) on *our* backtester after P10.11.
- **TODO-13 / P12** — SKY Quant Validation Engine, parked until
  P10.11. Next *code* is **P10.7** (P10.6 Bybit already on `main`).
- **Invariant #13** in `ARCHITECTURE.md`: SKY is the brain, not a
  trading bot.
- Contract tests in `tests/test_handoff_memory.py` so a future
  session cannot quietly re-adopt Freqtrade.

### Changed
- Reconciled onto `origin/main` @ `e233580` (PR #14 / P10.6) so PR #15
  can merge: both the Bybit adapter and the F1–F8 decisions are kept.
- `TODO.md`, `SESSION_STATE.md`, `AI_ANATOMY_ROADMAP.md`,
  `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `docs/INFRASTRUCTURE_LAYERS.md`,
  `PROFESSIONAL_PLAN_DECISIONS.md`, `BLUEPRINT.md`, `SKILL.md`,
  `README.md` — F1–F8 recorded; next code pointed at P10.7.
- Version 2.7.0 → **2.7.1** (`config.py`, `pyproject.toml`).
- Suite **441 → 445 pass / 1 skip** (+4), fully offline.

---

## [Unreleased] — PR #14 · branch `arena/019ff9cf-sky` (merged as 2.7.0)

**Two parts, two PRs.** (1) Parallel-session reconciliation: this
session built its own P10.2 backfill on a base that predated PR #11
(P10.2 + P10.3) and PR #12 (P10.2 hardening + P10.4); on discovery the
repo rule won — never duplicate completed components — so PR #13
(merged by the operator) adopts the reviewed implementation wholesale,
keeping the session's genuinely new value as **3 edge-case tests** in
`tests/test_backfill.py` (empty-first-page termination, start-past-end
no-op, mid-history-hole termination without duplicates), and records
the lesson for future sessions: **fetch and diff `origin/main` before
finishing any session** — parallel Arena sessions merge while you work.
(2) **P10.5** (v2.6.0) rode PR #13; **P10.6** (v2.7.0) goes out as
PR #14 — see its entry below. Suite ends at **441 pass / 1 skip**.

---

## [2.7.0] — 2026-08-13 · branch `arena/019ff9cf-sky`

MINOR bump: **P10.6 — Bybit adapter behind the same normalised schema**.
The second venue pages through the exact same backfill machinery: one
`Candle` record, one meaning, regardless of exchange.

### Added
- **`data/bybit_client.py`** — read-only Bybit V5 public market-data
  transport (no keys, ever):
  - `klines_page()` implements the P10.2 `PageResult` contract
    (data + HTTP status + headers), so the hardened backfill treats
    Bybit pages identically to Binance pages — resumable, idempotent,
    rate-limit aware, geo-block aware.
  - Venue quirks stay at the boundary: V5 categories (`spot`/`linear`),
    V5 interval codes (`1m→"1"` … `1d→"D"`), newest-first response rows
    reversed to ascending `ts`, string rows parsed to float, `turnover`
    carried as `quote_volume`, `retCode 10006` mapped to HTTP 429
    (backoff engages), other non-zero retCodes to 400, HTTP 403/451
    passed through for the backfill's immediate geo-block abort.
  - XAUUSD has no Bybit perp → honest empty result (same rule as Binance).
  - `klines()` convenience wrapper (with `market=`) so the `--repair`
    path works unchanged.
- **`main.py backfill`** — `--exchange binance|bybit`; live Bybit runs
  route to `BybitClient`, DEMO_MODE stays on the offline demo fetcher
  (synthetic series labelled with the requested exchange, same
  convention the Binance demo already used).
- **Tests** — `tests/test_bybit.py`: 17 offline tests. The milestone's
  proof: `_assert_adapter_contract()` runs the **identical assertions**
  against `BinanceClient` and `BybitClient` (page shape, ascending ts,
  float OHLCV, perp/spot routing, status contract), plus V5-specific
  parsing/routing tests, bybit series partition separation from
  binance, idempotent re-run, and the offline CLI end-to-end.

### Changed
- `data/backfill.py` — geo-block message is venue-neutral ("the venue
  blocked this request"); module history notes the transport is now an
  interface (any `klines_page` client), not a class.
- Suite: **424 → 441 pass / 1 skip** (+17), fully offline.

---

## [2.6.0] — 2026-08-13 · branch `arena/019ff9cf-sky`

MINOR bump: **P10.5 — data-quality pillar wired into the readiness
strip**. SKY now answers *"can I trust my own stored market history?"*
with the same one-line verdict it already gives for channels, immune
system, and risk gate. Corrupt or unusably stale data **quarantines**
the desk — `ready` goes False — because the engine prefers silence to a
signal built on corrupt data.

### Added
- **`data/quality.py`** — per-series market-data checks:
  - `checks_on_frame()` — staleness (timeframe-scaled: ≤3×step fresh,
    ≤30×step lagging, older = unusable), gaps in the recent window
    (reuses P10.3 `detect_gaps`), price sanity (non-positive OHLC,
    high below body, low above body), volume sanity (negative = corrupt,
    zero-volume-with-range = suspicious), ts ordering (defensive).
  - `verdict_for()` — maps health onto the readiness ladder with an
    explicit `quarantined` flag.
  - `series_health()` / `series_item()` — read a stored series through
    the real store boundary and produce a pillar item.
- **`CandleStore.list_series()`** — enumerate stored series so the
  pillar inspects every series without knowing keys up front.
- **`brain/agent.py`** — fourth pillar `_data_pillar()` in
  `readiness_strip()`; exception-isolated like the other three; an
  empty store is honest `degraded` with the backfill hint, a
  quarantined series rolls the strip to `down` (`ready: false`).
- **`mcp_server.py`** — `readiness` tool description updated to four
  pillars; `SERVER_VERSION` 1.3.0 → 1.4.0.
- **Tests** — `tests/test_quality.py`: 18 offline tests (fresh/lagging/
  stale ladder, gap bands, negative-close / inverted-high / inverted-low
  / negative-volume / non-monotonic-ts quarantine, zero-volume suspicion,
  corrupt fixture written through the real store ⇒ quarantine, healthy
  series, `list_series`, empty-store degraded, quarantine ⇒
  `ready: false` integration, pillar exception isolation). Pinned
  pillar-set assertions updated across `test_agent`, `test_web_api`,
  `test_mcp_stdio`, `test_channels`, `test_dashboard_js`.

### Changed
- `main.py` doctor help, `web/app.py` strip comments, `SKILL.md` /
  `README.md` / `TODO.md` pillar descriptions — all say **four** pillars.
- Suite: **406 → 424 pass / 1 skip** (+18), fully offline.

---

## [2.5.0] — 2026-08-13 · branch `arena/019ff948-sky`

MINOR bump: **P10.4 — derivatives as time series**. Funding, open
interest, mark, index and basis are now persisted into the Parquet store
(the roadmap's Layer 2) instead of existing only as one live snapshot;
the `liquidations()` 24h-stats proxy is renamed honestly. Inputs only —
no strategy, risk-gate, or engine behaviour change.

### Added
- **`data/derivatives.py`** — the Layer-2 series layer.
  - `DerivativesStore` — partitioned Parquet store under
    `data/store/derivatives/**` (gitignored) with the normalised row shape
    `(ts, exchange, market, symbol, metric, value, ingested_at)` and upsert
    PK `(exchange, market, symbol, metric, ts)`.
  - `derive_basis()` — basis = mark − index at timestamps where both are
    known (accepts raw fetch frames or canonical store frames).
  - `BinanceDerivativesTransport` — adapter over the new client endpoints
    with retry/backoff and geo-block awareness; `FakeDerivativesTransport`
    — deterministic offline stand-in with fault injection.
  - `DerivativesCollector` — resumable per metric (re-runs continue at the
    last stored timestamp), idempotent (upsert PK → a completed re-run
    adds zero rows), pages with rate-limit courtesy, derives basis from
    the stored mark/index after each run.
- **`data/binance_client.py`** — derivatives history endpoints:
  `funding_rate_history()` (`/fapi/v1/fundingRate`), `open_interest_history()`
  (`/futures/data/openInterestHist`), `mark_price_klines()` and
  `index_price_klines()` (`/fapi/v1/markPriceKlines` + `/fapi/v1/indexPriceKlines`),
  `premium_index()` (current mark/index/basis snapshot).
- **`liquidations()` renamed honestly** → `liquidation_stats_proxy()`: the
  roadmap's P10.4 done-when ("proxy renamed honestly"). Real forced-order
  data cannot be backfilled (WS `!forceOrder@arr` only); the method's
  docstring now says so and no misleading alias remains.
- **CLI** — `python main.py derivatives collect --symbol BTCUSDT`
  (paginated history into the store; `--since/--until/--metrics/--dry-run/
  --json`) and `python main.py derivatives status` (per-metric counts +
  UTC span).
- **Tests** — `tests/test_derivatives.py`: 20 offline tests (schema/store,
  upsert, metric isolation, basis derivation + join semantics, fake
  transport shape, collect-all, idempotent re-run, resume, metric
  selection, basis ⇒ mark+index, dry-run, XAU rejection, unknown metric,
  transient-fault retry, honest-rename assertion). `SampleClient` gained
  the four demo history methods so `DEMO_MODE=1` stays fully offline.

### Changed
- Version 2.4.1 → 2.5.0 (`config.py`, `pyproject.toml`).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.4 marked shipped; next milestone P10.5 (quality pillar).

### Notes
- Tests **383 → 403 pass / 1 skip** (+20), fully offline.
- The sandbox has no network egress; the real derivatives fetch runs on a
  Binance-reachable machine:
  `python main.py derivatives collect --symbol BTCUSDT` (resumes on re-run;
  inspect with `python main.py derivatives status`).

---

## [2.4.1] — 2026-08-13 · branch `arena/019ff948-sky`

PATCH bump: **P10.2 hardening** — fixes two real defects in the P10.2
first cut (2.4.0) so the data-independence layer cannot silently corrupt
itself. Inputs only; no strategy, risk-gate, or engine behaviour change.

### Fixed
- **Perp backfill was storing spot candles labelled `market=perp`.**
  The first cut paged `/api/v3/klines` (spot) for every market. The
  default transport now routes `market="perp"` through `/fapi/v1/klines`
  (`BinanceClient.klines_page()`, geo-friendly mirror first) so the
  roadmap's primary series is actually perp. Spot candles are never
  labelled perp; XAUUSD (no perp market) fails with an honest message
  instead of writing mislabelled data.

### Added
- `data/binance_client.py` — `klines_page()`: one raw 1000-candle page
  for `spot` or `perp`, returning a `PageResult` with rate-limit headers
  and HTTP status. Header-aware `_get_with_headers` /
  `_get_first_host_with_headers`; existing `klines()` behaviour unchanged
  (routes through the same seam).
- `data/store.py` — `normalise_klines()` honours an input `closed`
  column (forming candles stay out of history; default remains closed).
- **Real rate-limit handling** in `data/backfill.py` (the 2.4.0 cut only
  slept `sleep_s` between pages):
  - exponential backoff on 429/network errors (`backoff_attempts` /
    `backoff_base`),
  - pacing on Binance's `x-mbx-remaining-weight` header (low budget →
    extra sleep; exhausted → longer),
  - immediate abort on geo-blocks (403/451) instead of hammering a wall,
  - `max_requests` cap (default 5000 on the CLI; 0 = unlimited) — an
    interrupted run resumes where it stopped,
  - forming-tail-candle rule: `ts + timeframe ≤ now` is the definition of
    closed; the still-forming candle is skipped and picked up next run.
- CLI — `backfill` gains `--since`/`--until` (epoch ms, ISO date, or `90d`
  style), `--max-requests`, `--dry-run`; output shows hardening stats
  (rate-limit stalls, retries, forming skipped) and a
  "✓ idempotent re-run — zero rows added" line. New `python main.py store`
  command inspects the store (count, UTC span, year/month partitions).
- `tests/test_backfill.py` — 2.4.0's 7 tests retained; +13 hardening tests
  (perp routing, forming-candle drop + top-up, 429 backoff + exhaustion,
  network-error retry, geo-block abort, weight-header pacing,
  max-requests cap + resume, dry-run, ts parsing).

### Changed
- Version 2.4.0 → 2.4.1 (`config.py`, `pyproject.toml`).
- `.gitignore` — `data/store_demo/` (explicit demo sandbox for `store --demo`).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.2 marked hardened; P10.3 marked shipped; next milestone P10.4.

### Notes
- Tests **368 → 383 pass / 1 skip** (+15: 13 hardening + 1 store closed-column
  + 1 unbounded-backfill regression), fully offline.
- The sandbox has no network egress; the real perp fetch runs on a
  Binance-reachable machine:
  `python main.py backfill --symbol BTCUSDT --market perp --tf 1m`.

---

## [2.4.0] — 2026-08-12 · branch `arena/019ff5b1-sky`

MINOR bump: **P10.2** (Binance paginated REST backfill) + **P10.3**
(gap detection, repair, 1m→higher-TF aggregation). Inputs only — no
strategy, risk-gate, or engine behaviour change.

### Added
- **`data/backfill.py`** — resumable, rate-limit-aware REST backfill.
  Pages through `klines` (Binance cap 1000), writes via
  `CandleStore.write()` / `normalise_klines()`. Resume cursor is
  `last_stored_ts + step`. A re-run of the same range adds **zero**
  unique rows. `DEMO_MODE=1` uses `SampleClient` (offline).
- **`data/gaps.py`** — `detect_gaps()`, `repair_gaps()`,
  `aggregate_ohlcv()`, `rollup()`. Incomplete trailing buckets are
  dropped (same rule as unclosed candles). Rollups tagged
  `source=aggregated`.
- **`python main.py backfill`** — `--repair` / `--rollup` / `--json`.
- **`tests/test_backfill.py`** + **`tests/test_gaps.py`** — 13 offline
  tests (paging, idempotent re-run, resume, sleep courtesy, CLI,
  synthetic holes, 5m OHLC match, incomplete-bucket drop, 2-day rollup).

### Changed
- `data/sample_client.py` — `klines()` honours `start_time`/`end_time`
  so DEMO pagination works.
- `config.py` + `pyproject.toml` — version **2.3.0 → 2.4.0**.

### Notes
- Tests **355 → 368 pass / 1 skip** (+13).
- Next milestone: **P10.4** — derivatives as time series.

---

## [Unreleased]

### Added — planning only, no runtime change
- **`docs/DATA_INFRASTRUCTURE_ROADMAP.md`** — P10, the market-data
  independence phase: collect BTC data from free/public exchange APIs,
  store it ourselves (normalised schema + Parquet), and let the engine
  reason over stored evidence instead of a 500-candle amnesiac fetch.
  12 independently shippable milestones (P10.1 → P10.12).

  Reconciles a user-supplied plan against what SKY already has. Seven
  corrections recorded so a future session doesn't re-litigate them:
  analytics are ~80% already built in `engine/`; SQLite + Parquet
  instead of PostgreSQL + Redis (SKY is single-process by invariant);
  Lightweight Charts standalone instead of React/Next.js; no FastAPI
  (Flask already serves `/api/*`); no Docker (`ops/systemd/` deploys);
  liquidations cannot be backfilled (WS-only, accumulates from day one)
  and today's `liquidations()` is a 24h-stats proxy; reuse the existing
  `_cross_exchange_probe()` rather than writing a second one.
- `tests/test_handoff_memory.py` — two tests guarding the P10 plan's
  load-bearing constraints (milestone ladder, credential-free posture,
  `DEMO_MODE`, and the rejected-dependency list).

### Changed
- `TODO.md` — records the project aim explicitly (decision
  independence ✅ / data independence ❌), adds **TODO-12 (P10)**, and
  moves Dify/LibreChat behind P10 as well as the graduation gate.
- `AI_ANATOMY_ROADMAP.md` — new P10–P12 phase table.
- `docs/INFRASTRUCTURE_LAYERS.md` — order of work now
  `P11 → P10 → Dify → LibreChat`.
- `.gitignore` — `data/store/**` excluded ahead of P10.1.

### Planned
- TODO-12 (P10): data infrastructure. Next major milestone.
- TODO-7: human pastes the wheel-gate job into
  `.github/workflows/ci.yml` (the spec currently sits inert at
  `docs/.github/workflows/ci.yml` — nested under `docs/`, so GitHub
  never runs it).
- TODO-8: human protects `main` (require PR). Token gets 403.

---

## [2.4.0] — 2026-08-13 · branch `arena/019ff948-sky`

MINOR bump: **P10.2 — Binance paginated REST backfill**, the second
shippable milestone of P10 (data independence). Reuses the existing
`BinanceClient` transport, pages 1m history into the P10.1 store, and is
resumable + rate-limit aware; a completed re-run adds **zero rows**
(the milestone's done-when, proven offline). No strategy, risk-gate, or
engine behaviour changed — this fills the input-side storage layer.

### Added
- **`data/backfill.py`** — `BinanceBackfiller`: paginated, resumable,
  rate-limit-aware OHLCV backfill.
  - Resumes at the last stored candle + 1 timeframe; an interrupted run
    (`--max-requests` cap, network drop, Ctrl+C) continues where it stopped.
  - Idempotent: the store's upsert PK makes re-runs and `--since` repairs
    add zero rows by construction.
  - Rate-limit aware: paced `--interval` between pages, exponential backoff
    on 429/network errors, extra sleep when Binance's
    `x-mbx-remaining-weight` header reports a low budget, immediate abort on
    geo-blocks (403/451) — nothing is hammered and nothing is half-written.
  - Forming-candle safety: a candle is only closed when
    `ts + timeframe ≤ now`; the still-forming tail is skipped and picked up
    by the next run once closed (incremental top-up).
  - `FakePagedTransport` — deterministic offline stand-in (fault/weight
    injection) so the milestone is fully testable with zero network, and
    `DEMO_MODE=1` runs into the gitignored `data/store_demo/` root.
- **`data/binance_client.py`** — `klines_page()`: one raw 1000-candle page
  for `spot` (`/api/v3/klines`, geo-friendly mirror first) or `perp`
  (`/fapi/v1/klines`), returning a `PageResult` with rate-limit headers and
  HTTP status. Existing `klines()` behaviour unchanged (routes through the
  same seam). Header-aware `_get_with_headers` /
  `_get_first_host_with_headers` helpers added; `_get` semantics preserved.
- **`data/store.py`** — `normalise_klines()` honours an input `closed`
  column (forming candles marked by the backfill stay out of history;
  default remains closed).
- **CLI** — `python main.py backfill` (paged fetch into the Parquet store;
  `--symbol/--market/--tf/--since/--until/--page-size/--interval/--max-requests/
  --dry-run/--demo/--json`) and `python main.py store` (count, UTC span,
  year/month partitions, `--json`).
- **Tests** — `tests/test_backfill.py`: 21 offline tests (fresh backfill,
  re-run zero-rows, resume, `--since` repair, dry-run, forming-candle skip
  + top-up, 429 backoff, geo-block abort, weight-header pacing,
  max-requests cap + resume, input validation, ts parsing). Plus a
  `closed`-column test in `tests/test_store.py` and the XAU routing test
  updated to the new transport seam.

### Changed
- Version 2.3.0 → 2.4.0 (`config.py`, `pyproject.toml`).
- `.gitignore` — `data/store_demo/` (DEMO_MODE backfill sandbox).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.2 marked shipped; next milestone P10.3 (gaps + aggregation).

---

## [2.3.0] — 2026-08-12 · branch `arena/019ff579-sky`

MINOR bump: **P10.1 — normalised Candle schema + Parquet store**, the
first shippable milestone of P10 (data independence). No strategy,
risk-gate, or engine behaviour changes — this adds the input-side storage
layer the rest of P10 feeds.

### Added
- **`data/store.py`** — `CandleStore`: partitioned Parquet candle store.
  - Normalised `Candle` schema (the roadmap §4 fields): `ts` (UTC epoch-ms
    candle OPEN, inclusive), `exchange`, `market`, `symbol`, `timeframe`,
    `open/high/low/close/volume/quote_volume`, `trades`, `closed`,
    `source`, `ingested_at`.
  - Upsert primary key `(exchange, market, symbol, timeframe, ts)` — the
    duplicate-row class of bug is prevented by construction.
  - `normalise_klines()` — the single adapter boundary; exchange-specific
    shapes never reach the analytics layer.
  - `coerce_candle_frame()` / `empty_frame()` — canonical schema + dtypes.
  - Hive-style partitioning `data/store/parquet/candles/exchange=…/market=…
    /symbol=…/timeframe=…/year=…/month=…/part-000.parquet` — one month, one
    file; `data/store/**` stays gitignored.
  - Safety rule enforced: an **unclosed** candle (`closed=False`) is never
    persisted into immutable history.
  - `read()` returns deduplicated rows ordered by `ts` ascending, with
    optional `start_ts`/`end_ts` filtering; `count()` / `series()` helpers.
- **`tests/test_store.py`** — 13 offline, deterministic tests: schema +
  dtypes, upsert dedup (last write wins), out-of-order input returned
  sorted, duplicate-ts collapse, unclosed-candle drop, year/month partition
  boundary, range filtering, empty-read, series isolation, normalise/coerce.
- `pyarrow` runtime dep (`requirements.txt` + `pyproject.toml`).

### Changed
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md` — status header updated; P10.1
  marked shipped.
- `config.py` + `pyproject.toml` — version 2.2.1 → **2.3.0**.

### Notes
- Tests **342 → 355 pass / 1 skip** (+13). `DEMO_MODE=1` suite stays green;
  the store is fully offline.
- Next milestone: **P10.2** — Binance paginated REST backfill (resumable,
  rate-limit aware) reusing `data/binance_client.py`, writing via
  `CandleStore.write()`.

---

## [2.2.1] — 2026-08-12 · branch `arena/019ff530-sky`

PATCH bump: TODO-11 (P11) paper-book proof — first grind + a real
engine bug the graduation report revealed.

### Fixed — sell-side R sign inversion (the graduation report's reveal)
`data/backtester.py::_evaluate()` computed a **SELL** win's realized R
as `(tp - entry) / risk`. For a short, `tp < entry`, so every sell
`FULL_WIN` / `PARTIAL_WIN` was recorded with **negative** R — sell-side
expectancy, win-R and profit factor were systematically destroyed.
Before the fix the primary family's sell setups measured −1.6R…−1.9R;
after the fix the same data shows Sell Pullback **+0.540R** and FVG
Retest Sell **+0.636R** (Sweep Reversal Sell is honestly breakeven at
−0.033R on synthetic data — no edge, gate correctly stays closed).
The paper runner already used `abs()` correctly; only the backtester
was wrong. Regression tests: `test_evaluate_sell_win_full` (+2.0R),
`test_evaluate_sell_win_partial` (+1.0R).

### Added — TODO-11 grind + journal loop
- **Simulator journals every closed paper sample.** `_persist_paper_samples`
  now records a journal entry per closed simulator paper trade with
  `followed_rules=1` (mechanical execution of the engine's own plan) and a
  transparent note. The graduation gate's `compliance` criterion
  (1 − journal violation rate) stopped being `None` — it now reads
  **100.0%** from real journal rows. `tests/test_simulator.py`
  `test_simulate_round_journals_closed_paper_samples`.
- **Precise graduation-gap reporting.** `graduation_status()` exposes
  `sample_gaps` (the grind_verdict missing list); `python main.py desk`
  now says `samples counts short` / `samples expectancy short` instead of
  the blanket `samples short`, and the PAPER_GRIND advice names the exact
  primary setup + missing item (e.g. "Sweep Reversal Sell sample proof
  (positive expectancy)"). `brain/agent._sample_proof_word()`.

### Changed
- `config.VERSION` 2.2.0 → **2.2.1**; `pyproject.toml` to match.
- First real grind ran on the sandbox's offline sample/synthetic data:
  **38,439 decided primary-family samples** (all four setups ≥ 100
  backtest / ≥ 20 paper unique samples), `learn` produced a full
  per-setup × regime calibration profile (proven setups boosted
  ×1.1–1.2, losing Breakout Buy dampened ×0.83), and the desk line
  moved from "samples short · 0 decided" to "expectancy short ·
  38,439 decided". The blueprint graduation gate remains honestly
  CLOSED (family expectancy +0.263R < +0.50R, win rate 34.1% < 55%,
  PF 1.40 < 1.50) — as designed until the edge clears the bar.

### Known characteristics (documented, not bugs)
- FVG Retest Buy/Sell carry thousands of backtest samples but **0 paper
  samples**: the simulator takes one paper sample per window (the
  highest-confidence plan), so setups that rarely win the confidence
  contest are starved of paper proof. Outside the primary family today;
  noted for a future collection-strategy decision.

---

## [2.2.0] — 2026-08-12 · branch `arena/019ff4c3-sky`

MINOR bump: new readiness surface across CLI, HTTP, MCP, and dashboard.

### Added — TODO-1.bis combined doctor strip

One verdict answering "can I trust the desk right now?", rolled up
**worst-first** across the three readiness pillars the desk already
reported separately:

| Pillar | Source of truth | Levels |
|---|---|---|
| `channels` | `brain.channels.probe_all()` | ok / degraded / down |
| `immune` | `brain.immune.run_health_check()` | ok / degraded / down |
| `risk_gate` | the gate inside `desk_status()` | ok / degraded / blocked |

Rollup ladder: `ok < degraded < blocked < down`. The strip never
invents a fourth source of truth — every pillar reads the same library
function the CLI, MCP, and dashboard already read, so no surface can
drift from another.

- **`brain/agent.readiness_strip()`** + `format_readiness_strip()`.
  Each pillar is exception-isolated: a crashing probe degrades that
  pillar to `down` instead of failing the whole strip.
- **`python main.py doctor --strip`** (`--json` for the machine blob).
  Plain `doctor` now leads with the strip before the per-channel
  detail; `doctor --json` gained a `readiness` key.
- **`GET /api/readiness`** — never 500s; degrades to
  `{ok: false, level: "down", error: …}`.
- **MCP `readiness` tool** — `SERVER_VERSION` 1.2.0 → 1.3.0
  (13 read-only tools). Deny list unchanged.
- **Dashboard readiness strip** above every tab (`loadReadiness()`),
  colour-coded by level with one chip per pillar and the current desk
  advice. Lives outside `#app`, so it resolves before the first scan
  does; refreshes on the 5-minute diagnostic cadence, not the 30s
  scan tick.

### Changed
- `config.VERSION` 2.1.0 → **2.2.0**; `pyproject.toml` to match.

### Test count
- 324 → **337 pass / 1 skip** (+13). 0 regressions.

New coverage: pillar rollup order, closed-gate → `blocked`, crashing
probe isolation, `/api/readiness` shape + never-500, node-executed
dashboard render of the strip (verdict, chips, error payload), and
the three new CLI paths.

### Prior unreleased entries folded in
- `docs/INFRASTRUCTURE_LAYERS.md` — SKY-only map of OpenHands / Dify /
  LibreChat. Study patterns; never vendor. Dify after graduation;
  LibreChat last.
- `tests/test_handoff_memory.py` — SESSION_STATE / TODO / layers-doc
  contract so a dead Arena session cannot ship a rotting handoff.

---

## [2.1.0] — 2026-08-12 · branch `arena/019ff483-sky`

MINOR bump: new CLI command, new MCP tool, installable package.

### Added — TODO-4 desk_status advisory
- **`brain/agent.desk_status()`** — one-call snapshot aggregating
  the risk gate, today's/week's P&L, business scorecard, graduation
  gate, next scheduled autonomous agent, and a single
  "what would a professional do right now?" action.
- **`brain/agents.next_scheduled_agent()`** — cadence-based pick
  from `agent_runs` (morning_brief 24h / watchdog 4h /
  paper_reviewer 24h / weekly_review 168h). Never starts an agent.
- **`python main.py desk`** (`--json` for the machine blob).
- **MCP `desk_status` tool** — `SERVER_VERSION` 1.1.0 → 1.2.0
  (12 read-only tools). Deny list unchanged.
- **`GET /api/desk`** + dashboard "DESK STATUS" card on the System
  tab (`loadDesk()`, 5-minute diagnostic refresh).
- **`ask("what should I do?")`** routes to the same snapshot.

Advice is priority-ordered and capital-first:
`CLEAR_STATE → STAND_ASIDE → REVIEW_QUEUE → JOURNAL → PAPER_GRIND → SCAN`.

### Added — TODO-3 wheel-gate (D4 = yes)
- **`pyproject.toml`** — package `cryptobrain` 2.1.0, console script
  `cryptobrain = main:main`.
- **`cryptobrain/__init__.py`** — `import cryptobrain` facade
  (`__version__` from `config.VERSION`).
- **`ci/wheel_gate.py`** — build the wheel, reject duplicate zip
  entries, optional `--install` smoke test
  (`import cryptobrain` + `cryptobrain doctor --json`).
- **`wheel-gate` job** in `.github/workflows/ci.yml`.
- **`tests/test_wheel_gate.py`**.

### Changed
- `config.VERSION` 2.0.0 → **2.1.0**.
- `main.main()` now accepts an optional `argv` list (wheel-gate
  smoke-test contract; `python main.py …` unchanged).
- D1–D5 in `ROADMAP_AGENT_REACH_UPGRADE.md` §4 recorded as decided
  (recommended defaults). D5 URL documented in `docs/agent_install.md`.

### Test count
- 306 → **320 pass / 1 skip** (+14). 0 regressions.

### Pushed
- Branch `arena/019ff483-sky` → `origin`.

---

## [2.0.4] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — PR #5 conflict resolution (this session)

PR #5 (`feat(agent-surface): P7+P8+P9 — SKILL, channels, MCP
capability endpoints`) was `CONFLICTING` because `main` was
independently updated (commit `0940452` modern-dashboard) while the
P7/P8/P9 work was in flight. This session resolves the conflicts.

**main.py** (4 conflict hunks):
- Kept BOTH sides' additions: branch's `cmd_doctor / channels /
  skill` AND main's `cmd_preflight` + the preflight gate in
  `cmd_paper --watch`.
- Default banner updated to list all new commands.

**web/app.py** (3 conflict hunks):
- Took main's full modern tabbed dashboard wholesale (the branch's
  old `html += card(...)` block was obsolete; main's tabbed
  architecture IS the design).
- Re-applied the branch's `loadChannels()` JS function.
- Re-added the `/api/channels` and `/api/doctor` Flask endpoints
  (main did not have them — they were a P8 deliverable on the
  branch).
- Added the CHANNELS card to the system tab.
- Added a 5-minute diagnostic auto-refresh (channels + mcp),
  distinct from the existing 30s scan tick.

### Test count
- 285 → **306 pass / 1 skip** (+21 from main's modern-dashboard work
  including `tests/test_preflight.py`).
- 0 regressions on the branch side.

### Live verification
After resolving the conflicts, started `python main.py web` and
hit every new endpoint via curl:
- `/` → 200
- `/api/health` → 200
- `/api/channels` → 200 (returns proper JSON with 4 channels)
- `/api/doctor` → 200
- `/api/mcp` → 200

### PR status
PR #5 went from `CONFLICTING` to `MERGEABLE`. Reviewer can now merge.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No new PR (PR #5 already
  exists).

---

## [2.0.3] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — P9 MCP capability endpoints (TODO-2 complete)

`mcp_server.py` (the zero-dep stdio JSON-RPC server) now exposes 5
new read-only tools, bringing the total from 6 to 11:

| Tool | Wraps | What you get |
|---|---|---|
| `channels` | `brain.channels.list_channels(as_json=True)` | Ordered-backend registry (cryptodada / discord / news / llm) — same data the dashboard "CHANNELS" card and `python main.py channels --json` return |
| `correlation` | `engine.correlation.fetch_report` | Measured BTC/ETH/GOLD rolling correlation matrix + ETH/BTC beta |
| `hidden_chart_read` | `engine.hidden_alpha.hidden_alpha_report` | HMM latent regime + CVD order flow + Bayesian Kelly for one symbol |
| `hidden_analytics_mae` | `brain.analytics.mae_mfe_summary` | MAE/MFE summary per setup from the paper-trade DB |
| `hidden_analytics_mc` | `brain.analytics.monte_carlo_equity` | Monte Carlo equity + drawdown distribution from realized paper outcomes |

### Changed
- `mcp_server.py:SERVER_VERSION` bumped `1.0.0 → 1.1.0` (capability
  surface expansion).
- `mcp_server.py` docstring now explicitly names the deny list
  (`approve | reject | execute | close | place_order | sign |
  withdraw | transfer`) so the invariant is self-documenting.
- `SKILL.md` tool table updated: 5 rows that previously had `—` in
  the MCP column now list the new tool name.
- `tests/test_mcp_stdio.py:ROOT_TOOLS` extended to 11 names.

### Tests
- 6 new tests in `tests/test_mcp_stdio.py`:
  - `test_root_mcp_channels_tool`
  - `test_root_mcp_correlation_tool`
  - `test_root_mcp_hidden_chart_read_tool`
  - `test_root_mcp_hidden_analytics_mae_tool`
  - `test_root_mcp_hidden_analytics_mc_tool`
  - `test_root_mcp_deny_list_still_enforced` — checks 8 forbidden
    names both in `tools/list` AND by direct call
- Test count: 289 → **295 pass / 1 skip** (0 regressions).

### Self-reflection (in-session)
- The previous session's end-of-session `SESSION_STATE.md` update
  recorded new SHAs but left two pre-existing inconsistencies
  unrepaired (a `<new-sha>` placeholder and a stale "P8 dashboard
  panel pending" status line). The refined rule: when updating
  `SESSION_STATE.md`, do a full-document reconciliation pass — not
  just append new sections.
- TODO-2 followed the **library-function-not-subprocess** design
  pattern. The existing tools (`ask`, `risk`, `health`, etc.) all
  call library functions directly, not `cmd_*` functions via
  subprocess; the new tools follow the same pattern. This keeps the
  surface consistent and avoids the overhead of a process per call.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened.

---

## [2.0.2] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — P8 dashboard "Channels" panel (TODO-1 complete)
- **`GET /api/channels`** in `web/app.py` — JSON endpoint wrapping
  `brain.channels.probe_all()`. Exception-isolated (a broken probe
  in one channel cannot crash the endpoint); goes through
  `_sanitize_for_json` to preserve the numpy-leak fix from
  `MERGE_NOTES.md`. Returns `{channels: {name: {status, active,
  backends: [...]}, ...}}`.
- **`GET /api/doctor`** — JSON-wrapped text report. Same output
  as `python main.py doctor`; the dashboard panel could call it
  but uses `/api/channels` directly for the structured view.
- **Dashboard HTML: new "CHANNELS — ordered-backend registry (P8)"
  full-width card.** Renders a status pill row (one per channel:
  `cryptodada / discord / news / llm`) plus a per-channel table
  with `configured / ok / detail / (active)` columns. Visual design
  matches the existing `MCP SERVER` card.
- **JS: `loadChannels()`** — fetches `/api/channels`, renders the
  card. Wired into the post-render init block.
- **Separate 5-minute auto-refresh for diagnostic panels** (channels
  + MCP), distinct from the 30s signal-scan tick. Channels are
  diagnostic state, not signal state, so a slower cadence is
  correct.
- **4 new tests** in `tests/test_web_api.py`:
  `test_channels_endpoint_returns_registry`,
  `test_channels_endpoint_is_json_serializable_under_numpy_leak`,
  `test_channels_endpoint_isolates_probe_exceptions`,
  `test_doctor_endpoint_returns_text_report`.

### Test count
- 285 → **289 pass / 1 skip** (0 regressions).

### Self-reflection (in-session)
This session caught a stale handoff: the previous session's
`SESSION_STATE.md` said "Last commit: b0fe82f" but the actual HEAD
was already `498d753` (the docs commit). The handoff memory went
stale inside the same chat. The lesson: **update SESSION_STATE.md
at the START of every session, not just at the end.** This entry
is the first to be documented with the rule.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened.

---

## [2.0.1] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — Agent-Reach-inspired surface (P7 + P8 code layer)
- **`SKILL.md`** at repo root — the 155-line agent-facing skill file
  that any AI agent (Claude, Cursor, Arena, MCP client) can read to
  learn the tool surface, the safety contract, and the citation
  pattern. Mirrors the Agent-Reach pattern of "one URL the agent
  reads."
- **`ROADMAP_AGENT_REACH_UPGRADE.md`** — the P7/P8/P9 plan with
  per-phase risk + rollback + definition-of-done + D1–D5 decision
  list. Honest about what is *adopted* (operational patterns) and
  what is *not adopted* (web scraping, social logins, audio
  transcription, third-party CLIs).
- **`docs/agent_install.md`** — the one-pager an agent fetches when
  told "install CryptoBrain."
- **`brain/channels.py`** — the ordered-backend router. Four channels
  (`cryptodada`, `discord`, `news`, `llm`), each with a primary →
  fallback chain ending in an always-available tail (`none` or
  `rule_based`). Probes are exception-isolated so a broken channel
  can't crash `doctor`.
- **`python main.py doctor`** — the non-mutating readiness report
  (channels layer + immune system).
- **`python main.py channels`** — compact per-source backend
  registry listing.
- **`python main.py skill`** — print / install / uninstall the
  `SKILL.md` (default inspect-only; `--system` required for
  `$HOME` writes).
- **`tests/test_channels.py`** — 27 new tests covering registry
  shape, probe isolation, fallback ordering, each source's "off"
  state, SKILL.md content contract, every new CLI subcommand
  including the `--install` / `--system` / `--dry-run` safety
  postures.

### Changed
- **`main.py`** — three new subcommands (`cmd_doctor`, `cmd_channels`,
  `cmd_skill`); default banner updated. +184 lines, additive only.
- **`AI_ANATOMY_ROADMAP.md`** — short P7/P8/P9 summary table linked
  to the new planning document. +34 lines, additive only.

### Test count
- 258 pass / 1 skip → **285 pass / 1 skip**. 0 regressions.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened (user
  explicitly chose Option B: branch only).

### Notes
- Inspired by [`Panniantong/Agent-Reach`](https://github.com/Panniantong/Agent-Reach)
  (v1.5.0, 70.5k★, MIT). Operational patterns adopted; web-scraping
  surface explicitly not adopted per
  `ROADMAP_AGENT_REACH_UPGRADE.md` §5.

---

## [2.0.0] — 2026-08-10 · commits `35ad758…99ace0d`

### Added — Consolidated production build (merged Cloudslover/AI + cloudshome/AI)
- **Engine layer (`Cloudslover/AI` @ `ea50e54`):**
  - Hidden-alpha quant: Markov-smoothed HMM latent regimes
    (Bull/Bear/Range/Expansion).
  - CVD order flow: absorption & exhaustion detection.
  - Bayesian fractional Kelly sizing (`NEGATIVE_EDGE_STAND_ASIDE`).
  - 8D state fingerprint + historical similarity search.
  - Realistic spread/slippage execution model (`EXECUTION_MODEL=simple`).
  - Monte Carlo equity + drawdown distribution.
- **Anatomy layer (`cloudshome/AI` @ `ba7a35c`):**
  - `brain/library.py` + `brain/ask.py` — RAG knowledge index +
    grounded Q&A with strict citations.
  - `brain/brief.py` — cross-asset morning brief + post-trade
    reviews (MAE/MFE + rule-compliance headline).
  - `brain/agents.py` — autonomous desk agents (morning brief,
    watchdog, paper reviewer, weekly review), audit-logged to
    `agent_runs`.
  - `brain/immune.py` — system diagnostics (staleness, DB integrity,
    risk gates, behavioral flags, calibration drift).
  - `mcp_server.py` — **zero-dependency** stdio JSON-RPC 2.0
    server.
  - `AI_ANATOMY_ROADMAP.md` — architecture/status tracker.
- **`engine/correlation.py`** + `python main.py correlation` —
  measured rolling BTC/ETH/GOLD correlation matrix and ETH/BTC
  beta, with explicit check of the static "BTC+ETH = one bucket"
  portfolio rule.
- **CLI parity with `AI_ANATOMY_ROADMAP.md`:** top-level `ask` (RAG
  library with citations), `postreview <scan_id>`, and
  `agent watchdog | paper-reviewer | weekly-review` (autonomous
  agents, audit-logged).
- **Tests:** 38 test modules. `tests/test_correlation.py`,
  `tests/test_mcp_stdio.py` (root MCP server: handshake, tool
  permission map, trader-state round-trip, health check),
  `tests/test_web_api.py` — Flask endpoint regression tests.

### Changed
- **Grafted modules:** `ai/llm_brain.py`, `brain/metrics.py`,
  `brain/risk_gate.py`, `data/database.py`. See `MERGE_NOTES.md` §2
  for the file-level decisions.
- **Production bug fix:** `/api/scan` and `/api/intelligence`
  returned HTTP 500 ("Object of type bool is not JSON serializable")
  whenever numpy scalars from the quant layer leaked into the
  payload. All engine endpoints now pass through `_sanitize_for_json`.

### Test count
- Pre-merge: 171 / 258 / 0 across the two sources (per source READMEs).
- Post-merge: **258 pass, 1 skip, 100% offline** (`DEMO_MODE=1
  python -m pytest tests/ -q`).

### Pushed
- Branches `arena/019febaf-sky` and `arena/019fefc9-sky` → `main`
  via PRs #1–#4 (all merged). The CI workflow file was renamed to
  `.github/workflows/ci.yml` (commit `8b16923`) to activate it —
  but see TODO-7 for the manual activation step.

### Notes
- Canonical consolidated repo:
  [`https://github.com/Azimshawon/SKY`](https://github.com/Azimshawon/SKY).
- Both upstream repos remain as read-only history sources.

---

## Pre-2.0.0 history

The pre-2.0.0 history lives in the two source repositories:

- [`Cloudslover/AI`](https://github.com/Cloudslover/AI) — engine +
  professional mode (hidden-alpha quant layer, execution model,
  analytics, risk gate).
- [`cloudshome/AI`](https://github.com/cloudshome/AI) — AI anatomy
  layer (RAG library, ask, brief, agents, immune, MCP).

File-level provenance of the merge is in
[`MERGE_NOTES.md`](./MERGE_NOTES.md).

---

## Versioning policy

- **MAJOR** bump for breaking changes to the engine JSON contract
  (`output/signal_schema.py`) or the MCP `tools/list` interface.
- **MINOR** bump for additive, backwards-compatible features (new
  CLI subcommands, new brain modules, new MCP tools, new
  dashboard panels).
- **PATCH** bump for bug fixes, test additions, documentation,
  refactors with no API change.

The current `pyproject.toml` (when added — see TODO-3) will be the
source of truth for the version number; this changelog is the
source of truth for *what* shipped.
