# Changelog

All notable changes to **CryptoBrain / SKY** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> **Note:** this changelog was created on 2026-08-11. Pre-v2.0.0 history
> lives in the `MERGE_NOTES.md` provenance document. The `pyproject.toml`
> `version` is the source of truth; this file documents what shipped.

---

## [Unreleased] — PR #14 · branch `arena/019ff9cf-sky`

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
