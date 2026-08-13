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

**Last updated:** 2026-08-13 (P10.4 shipped: derivatives as time series; P10.2 hardened)
**Branch:** `arena/019ff948-sky`
**HEAD commit:** see "Last commit" below
**Default branch:** `main` @ `5736ee8` (PR #11 merged 2026-08-12: P10.2 + P10.3)
**PR:** [#13](https://github.com/Azimshawon/SKY/pull/12) — this branch → `main`.
**Python:** 3.10+ tested on 3.10–3.13 + Windows (per existing CI)

> **This session's decision:** the operator picked "P10.2 — Binance
> backfill" for the day. A remote check showed P10.2 *and* P10.3 had
> already shipped on `main` (PR #11) — the local checkout predated the
> merge — and the freshly drafted backfill turned out to fix two real
> defects in the shipped one:
> 1. **The shipped backfill labelled spot candles as `market=perp`** —
>    `client.klines()` always pages `/api/v3/klines` (spot) even for
>    `--market perp`, silently mislabelling the roadmap's primary series.
> 2. **"Rate-limit aware" was only a nap** — no weight-header pacing, no
>    exponential backoff, no geo-block abort, no request cap, and no
>    forming-candle rule (the still-forming tail candle could be stored).
>
> The operator chose: **merge main, harden P10.2** (keep the shipped
> `backfill()` API/CLI so P10.3's `--repair`/`--rollup` keep working).
> With time left in the session (and the operator asking for more), the
> natural next milestone **P10.4 (derivatives as time series)** was then
> built too — funding / OI / mark / index / basis now persist, and the
> `liquidations()` 24h-stats proxy is renamed honestly. Suite
> **368 → 383 → 403**. Version **2.4.0 → 2.4.1 → 2.5.0**.
> Next: P10.5.

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
(our own stored market history — 🔄 P10.1–P10.3 shipped). Every phase
below is ordered by how directly it moves those two lines.

---

## Current phase

**P10 (data infrastructure + market terminal) — P10.1–P10.4 shipped;
P10.2 hardened (2026-08-13).** P9 complete; P11 first grind shipped;
graduation gate still closed. Open items: TODO-7, TODO-8; P10.5 → P10.12.

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
| **P11** | **Paper-book proof** | 🔄 In progress | First grind shipped (38,439 decided, all four primary setups ≥100/20, compliance 100%, sell-R bug fixed); gate still closed on the blueprint bar |
| **P10** | **Data infrastructure + market terminal** | 🔄 In progress | **P10.1–P10.4 shipped**; P10.2 hardened 2026-08-13 (real perp endpoint + rate-limit machinery); P10.5 (quality pillar) next. [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **Regime-conditional backtests** | ⏸ After P10 | Years of stored data, conditioned on OI / funding / CVD |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-13 (this branch): P10.2 hardening — perp endpoint + rate-limit machinery

Rebased the session branch onto `main` @ `5736ee8` (PR #11: P10.2 + P10.3).
0 regressions. Tests **368 → 383 pass / 1 skip** (+15). Version **2.4.0 → 2.4.1**.

**What landed (fixes to the shipped P10.2):**
- **Perp is actually perp.** `data/binance_client.py` gains `klines_page()`
  (raw 1000-candle page for `spot` `/api/v3/klines` or `perp`
  `/fapi/v1/klines`, `PageResult` with rate-limit headers + HTTP status;
  header-aware `_get_with_headers` / `_get_first_host_with_headers`).
  The default backfill transport routes `market="perp"` through the perp
  endpoint — previously `client.klines()` stored **spot candles labelled
  `market=perp`**. XAUUSD (no perp market) now fails with an honest
  message instead of writing mislabelled data. Existing `klines()`
  behaviour unchanged (routes through the same seam).
- **Real rate-limit handling** in `data/backfill.py` (the first cut only
  slept `sleep_s` between pages): exponential backoff on 429/network
  errors (`backoff_attempts`/`backoff_base`), pacing on Binance's
  `x-mbx-remaining-weight` header (low budget → extra sleep; exhausted →
  longer), immediate abort on geo-blocks (403/451), `max_requests` cap
  (CLI default 5000; 0 = unlimited) that bounds *pages* not retries, and
  a forming-tail-candle rule (`ts + timeframe ≤ now`; the forming candle
  is skipped and picked up by the next run). `normalise_klines()` now
  honours an input `closed` column (store drops forming rows).
- **Write-as-you-fetch.** `backfill()` now consumes a generator
  (`_iter_klines_pages`) so every page is persisted the moment it
  arrives — an interrupted run keeps everything fetched so far, and the
  next run resumes from the last stored candle. (The first cut collected
  all pages first and would lose hours of fetching on a mid-run error.)
- **Unbounded-backfill hang fixed.** `end_ts` now defaults to `now`: the
  offline `SampleClient`'s synthetic venue never runs out of history, so
  an unbounded demo backfill used to page forever.
- **CLI:** `backfill` gains `--since`/`--until` (epoch ms, ISO date, or
  `90d` style), `--max-requests`, `--dry-run`; text output shows
  hardening stats (rate-limit stalls, retries, forming skipped) and a
  "✓ idempotent re-run — zero rows added" line. New `python main.py
  store` command (count, UTC span, year/month partitions; `--root`/
  `--demo`/`--json`).
- **Tests:** `tests/test_backfill.py` retains the first cut's 7 tests
  and adds 14 (perp routing, XAU perp rejection, forming-candle drop +
  top-up, 429 backoff + exhaustion, network-error retry, geo-block
  abort, weight-header pacing, max-requests cap + resume, dry-run,
  unbounded-backfill regression, ts parsing). `tests/test_store.py` +1
  (closed-column), `tests/test_symbols.py` updated to the new seam.

**Sandbox note:** this sandbox has **no network egress** (verified:
example.com, Binance, KuCoin, OKX all fail). The real perp fetch runs on
the operator's machine (Dhaka, BD — Binance spot mirror should work;
fapi may geo-block; the client degrades honestly either way):
`python main.py backfill --symbol BTCUSDT --market perp --tf 1m`.
A live attempt here aborts cleanly: "transport failed after 4 attempts
(last status None) — re-run resumes where it stopped."

**Last successful test command:**
`DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q` → **383 passed / 1 skipped**.

### Session 2026-08-13 (this branch, second half): P10.4 — derivatives as time series

Same branch (`arena/019ff948-sky`, PR #12). 0 regressions.
Tests **383 → 403 pass / 1 skip** (+20). Version **2.4.1 → 2.5.0**.

**What landed (roadmap Layer 2 — store first, prove later):**
- `data/derivatives.py` — `DerivativesStore` (partitioned Parquet under
  `data/store/derivatives/**`, gitignored; normalised row shape
  `(ts, exchange, market, symbol, metric, value, ingested_at)`; upsert PK
  `(exchange, market, symbol, metric, ts)`), `derive_basis()`
  (basis = mark − index on common timestamps; accepts raw or canonical
  frames), `BinanceDerivativesTransport` (retry/backoff, geo-block
  awareness), `FakeDerivativesTransport` (deterministic offline fake with
  fault injection), `DerivativesCollector` (resumable per metric,
  idempotent, pages with rate-limit courtesy, derives basis from stored
  mark/index after each run).
- `data/binance_client.py` — `funding_rate_history()`
  (`/fapi/v1/fundingRate`), `open_interest_history()`
  (`/futures/data/openInterestHist`), `mark_price_klines()` /
  `index_price_klines()` (`/fapi/v1/markPriceKlines` +
  `/fapi/v1/indexPriceKlines`), `premium_index()` snapshot; and the
  P10.4 done-when: **`liquidations()` renamed honestly to
  `liquidation_stats_proxy()`** — no misleading alias remains.
- CLI — `python main.py derivatives collect` (`--since/--until/--metrics/
  --dry-run/--json`) + `python main.py derivatives status`.
- `SampleClient` — four demo history methods (deterministic synthetic
  funding/OI/mark/index) so `DEMO_MODE=1` stays fully offline.
- `tests/test_derivatives.py` — 20 offline tests (schema/store, upsert,
  metric isolation, basis derivation + join semantics, fake transport,
  collect-all, idempotent re-run, resume, metric selection, basis ⇒
  mark+index, dry-run, XAU rejection, unknown metric, transient-fault
  retry, honest-rename assertion).

**Verified end-to-end offline:** a DEMO collect stored 3,006 funding +
24,055 each of OI/OI-value/mark/index + 24,055 derived basis rows; a
re-run added **zero** rows; `derivatives status` lists all six series.

**Last successful test command:**
`DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q` → **403 passed / 1 skipped**.

### Session 2026-08-12 (this branch): P10.2 + P10.3 — backfill + gaps/rollups

Branched from `arena/019ff579-sky` @ `ee99486`. 0 regressions.
Tests **355 → 368 pass / 1 skip** (+13). Version **2.3.0 → 2.4.0**.

**What landed:**
- `data/backfill.py` — `backfill()` / `iter_klines_pages()` / `BackfillResult`.
- `data/gaps.py` — `detect_gaps` / `repair_gaps` / `aggregate_ohlcv` / `rollup`.
- `python main.py backfill` with `--repair` / `--rollup`.
- SampleClient pagination; 13 new tests.

**Last successful test command:**
`DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q` → **368 passed / 1 skipped**.

### Session 2026-08-12 (prior branch): P10.1 — schema + Parquet store

Branched from `main` @ `d0ddb42` (PR #9). 0 regressions.
Tests **342 → 355 pass / 1 skip** (+13). Version **2.2.1 → 2.3.0**.

**What landed:**
- `data/store.py` — `CandleStore`: normalised `Candle` schema (§4 of the
  roadmap), partitioned Parquet store under `data/store/**` (gitignored),
  upsert PK `(exchange, market, symbol, timeframe, ts)`, `normalise_klines()`
  adapter boundary, `coerce_candle_frame()` / `empty_frame()`.
- Unclosed-candle rule enforced in code: `closed=False` rows never persist.
- `tests/test_store.py` — 13 offline deterministic tests (round-trip, dedup
  last-write-wins, ordering, partition boundary, range filter, etc.).
- Deps: `pyarrow>=15.0` added (`requirements.txt`, `pyproject.toml`).
- Docs: `CHANGELOG.md` (v2.3.0), `docs/DATA_INFRASTRUCTURE_ROADMAP.md`
  (P10.1 shipped), `TODO.md`, this file.

**Files changed:** `data/store.py` (new), `tests/test_store.py` (new),
`requirements.txt`, `pyproject.toml`, `config.py`, `CHANGELOG.md`,
`docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md`.

**Last successful test command:**
`DEMO_MODE=1 python -m pytest tests/ -q` → **355 passed / 1 skipped**.

**Known open issues (unchanged):** P11 graduation gate honestly closed;
TODO-7 (human pastes wheel-gate job into real `.github/workflows/ci.yml`);
TODO-8 (human protects `main`).

---

### Session 2026-08-12 (prior branch): TODO-1.bis readiness strip

Branched from `main` @ `f0eff12`. 0 regressions.
Tests **324 → 339 pass / 1 skip** (+15). Version **2.1.0 → 2.2.0**.

One verdict answering "can I trust the desk right now?", rolled up
**worst-first** across three pillars that already existed separately:

| Pillar | Source of truth | Levels |
|---|---|---|
| `channels` | `brain.channels.probe_all()` | ok / degraded / down |
| `immune` | `brain.immune.run_health_check()` | ok / degraded / down |
| `risk_gate` | the gate inside `desk_status()` | ok / degraded / blocked |

Ladder: `ok < degraded < blocked < down`; only `ok` sets `ready: true`.

**Files changed:**
- `brain/agent.py` — `readiness_strip()`, `format_readiness_strip()`,
  `_channels_pillar()`, `_immune_pillar()`, `_gate_pillar()`,
  `_worst()`, plus the `_READINESS_ORDER` / `_IMMUNE_TO_LEVEL` /
  `_CHANNEL_TO_LEVEL` maps. Every pillar is exception-isolated.
- `main.py` — `doctor --strip` flag; `cmd_doctor` leads with the strip
  in text mode and adds a `readiness` key in `--json` mode.
- `web/app.py` — `GET /api/readiness` (never 500s), `.strip` CSS,
  the `#readiness` element above every tab, `loadReadiness()`, wired
  into `render()`, the init IIFE, and the 5-minute diagnostic timer.
- `mcp_server.py` — `readiness` tool; `SERVER_VERSION` 1.2.0 → 1.3.0.
- `config.py` + `pyproject.toml` — version 2.2.0.
- Tests: `test_agent.py` (+5), `test_web_api.py` (+2),
  `test_dashboard_js.py` (+2, node-executed), `test_channels.py` (+3),
  `test_mcp_stdio.py` (+1 and `ROOT_TOOLS` updated).
- Docs: `SKILL.md`, `README.md`, `ARCHITECTURE.md` (new invariant #10),
  `AI_ANATOMY_ROADMAP.md`, `CHANGELOG.md` (v2.2.0), `TODO.md`,
  `docs/HUMAN_ACTIONS.md` (corrected the dead `wheel-gate-job.yml` link).

**Also found and documented:** `main`'s last commit renamed the
wheel-gate spec to `docs/.github/workflows/ci.yml`. That path is
**inert** — nested under `docs/`, GitHub Actions never reads it. TODO-7
is still open and `docs/HUMAN_ACTIONS.md` now says so explicitly.

### Session 2026-08-12 (this branch): TODO-11 paper-book proof — first grind

Branched from `main` @ `f0eff12`. 0 regressions.
Tests **339 → 342 pass / 1 skip** (+3). Version **2.2.0 → 2.2.1**.

**The one bug the graduation report revealed (this is why we grind):**
`data/backtester.py::_evaluate()` graded a SELL win's realized R as
`(tp - entry) / risk` — negative for a short, so every sell
FULL_WIN/PARTIAL_WIN was stored as a negative-R trade. Sell-side
expectancy, win-R and PF were systematically destroyed (first report:
Sell Pullback −1.855R, Sweep Reversal Sell −1.596R). After the fix,
the same data shows Sell Pullback **+0.540R**, Sweep Reversal Sell
**−0.033R** (honestly breakeven), FVG Retest Sell **+0.636R**. The
paper runner already used `abs()`; only the backtester was wrong.

**Files changed:**
- `data/backtester.py` — `realized_r()`: side-aware R for
  FULL_WIN/PARTIAL_WIN (BUY `(exit-entry)/risk`, SELL
  `(entry-exit)/risk`); LOSS stays −1.0.
- `data/simulator.py` — `_persist_paper_samples()` journals every
  closed paper sample (`followed_rules=1`, note "simulator paper
  sample — mechanical rule-following execution"); `graduation_status()`
  exposes `sample_gaps`.
- `brain/agent.py` — `_sample_proof_word()` (precise `counts short` /
  `expectancy short` / `counts+expectancy short` label) and PAPER_GRIND
  advice that names the exact primary setup + missing item.
- `tests/test_backtester.py` — `test_evaluate_sell_win_full` (+2.0R),
  `test_evaluate_sell_win_partial` (+1.0R).
- `tests/test_simulator.py` — `test_simulate_round_journals_closed_paper_samples`.
- `config.py` + `pyproject.toml` — version 2.2.1.
- Docs: `TODO.md`, `CHANGELOG.md` (v2.2.1), this file.

**First grind numbers (sandbox offline sample/synthetic data):**
all four primary setups ≥ 100 backtest / ≥ 20 paper unique samples —
Buy Pullback 9936/367, Sell Pullback 4276/184, Sweep Reversal Buy
18711/1600, Sweep Reversal Sell 3085/280; **38,439 decided**
primary-family samples. Graduation gate: expectancy +0.263R,
win rate 34.1%, PF 1.40, compliance 100% — honestly below the
blueprint bar, so the gate stays closed. `learn` now calibrates
every setup × regime (proven pullbacks ×1.12–1.19, Breakout Buy
dampened ×0.83).

### Prior sessions (already on `main`)

- **v2.1.0 / PR #6** — `desk_status()` advisory, `next_scheduled_agent()`,
  `python main.py desk`, MCP `desk_status`, `/api/desk`, wheel-gate
  content (`ci/wheel_gate.py` + `pyproject.toml`), D1–D5 recorded.
- **v2.0.x / PR #5** — P7 SKILL + doctor/skill CLI, P8 channels router
  + dashboard panel, P9 MCP 11-tool surface, handoff memory files.

See CHANGELOG v2.0.1–v2.2.0 for file-level detail.

---

## Currently working on

P10.2 hardening shipped on `arena/019ff948-sky` (PR #12 open). Nothing
in flight. Next code session: **P10.4** (derivatives time series).

The paper book's **counts** are done (100/20 for every primary setup,
38,439 decided samples) and the **journal loop** is done (compliance
100%). What is still open is the graduation gate itself: the primary
family (+0.263R, 34.1% win, PF 1.40) is below the blueprint bar, and
Sweep Reversal Sell (−0.033R) is the last sample-proof gap. That is
the honest, intended state of the ladder — the next session's job is
to grind more (ideally live) data, not to loosen the bar.

**P10 planning (no code):**
`docs/DATA_INFRASTRUCTURE_ROADMAP.md` — the market-data independence
phase. It reconciles a user-supplied plan against what SKY already
has, and records seven corrections (analytics ~80% already built;
SQLite+Parquet not Postgres+Redis; Lightweight Charts standalone not
React/Next; no FastAPI/Docker; liquidations can't be backfilled;
reuse the existing cross-exchange probe; one-PR-per-session).

---

## Remaining work (prioritised)

1. **TODO-11 (P11) — continue, not start.** Counts (100/20), the
   journal loop, and the sell-R bug fix are DONE. What remains:
   grind more (ideally live) data and watch whether Sweep Reversal
   Sell crosses above zero and the family expectancy climbs; decide
   on the paper-sample collection strategy (FVG Retest types have
   0 paper samples because the simulator takes one paper sample per
   window — best plan only). Do **not** change the blueprint
   graduation criteria.
2. **TODO-12 (P10)** — P10.1–P10.4 done; P10.2 hardened 2026-08-13.
   Next: **P10.5** (per-source data-quality checks wired into
   `readiness_strip()` — corrupt/stale feed ⇒ quarantine ⇒ no signal,
   proven by test). Roadmap:
   it records which parts of the incoming plan were corrected and why.
3. **TODO-7** — human pastes the wheel-gate job into the **real**
   `.github/workflows/ci.yml` (the `docs/` copy is inert).
4. **TODO-8** — human protects `main` (require PR). Token: HTTP 403.
5. **TODO-9 / TODO-10** — Dify then LibreChat. Parked behind both the
   graduation gate *and* P10. Do not start next session.

Full list and rationale: see [`TODO.md`](./TODO.md).

---

## Known problems / caveats

1. **D1–D5 are answered.** See `ROADMAP_AGENT_REACH_UPGRADE.md` §4.
2. **Arena's GitHub integration: one PR per chat session.** The
   session convention is: do the work, then open **one** PR as the
   closing step.
3. **`mcp>=1.0` is listed in `requirements.txt` but not required**
   for the zero-dep `mcp_server.py`. It is only needed for the
   SDK-based `python main.py mcp` server.
4. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   committed sample data is stale by design. Expected, not a bug —
   and it is why `doctor --strip` reports `down` offline. On live
   data the same pillar goes green.
5. **Arena cannot push under `.github/workflows/`.** The wheel-gate
   job spec therefore lives at `docs/.github/workflows/ci.yml`, which
   GitHub Actions does **not** execute. Source of truth for running
   the gate is `ci/wheel_gate.py` locally (TODO-7).
6. **`CHANGELOG.md` is current** through v2.5.0.
7. **Sweep-reversal setups are breakeven on synthetic data.** The
   sandbox's deterministic series are smooth random walks with drift —
   they have no real stop-hunt structure, so sweep plans land near
   zero expectancy (Sweep Reversal Buy +0.028R, Sell −0.033R) while
   pullbacks carry the edge (+0.54…+0.70R). Data character, not a bug;
   the sweep detector was audited and is symmetric/correct.
8. **FVG Retest types have 0 paper samples.** `_persist_paper_samples`
   takes one paper sample per window (the highest-confidence plan), so
   setups that rarely win the confidence contest never earn paper
   proof (FVG Retest Buy 7,480 bt / 0 pp). Outside the primary family
   today; noted for a future collection-strategy decision.
7. **The dashboard readiness strip lives outside `#app`.** `render()`
   replaces `#app.innerHTML` wholesale, so anything inside it would be
   destroyed on every scan. Keep the strip where it is.
8. **Live scans are still amnesiac.** The Parquet store + backfill exist
   (P10.1–P10.3) but the scanner/backtester still fetch ~500 live candles
   (P10.11 wires them to the store).
8b. **This sandbox has no network egress.** The real Binance backfill
   cannot run here (verified live: clean abort with a resumable message).
   Run it on the operator's machine. All P10.2 behaviour is proven
   offline via `FakePagedTransport` / `SampleClient`.
9. **`BinanceClient.liquidations()` was not liquidation data** — a
   24h-ticker proxy. Renamed honestly in P10.4 to
   `liquidation_stats_proxy()`. Real forced-order data only comes from
   the `!forceOrder@arr` WebSocket stream and **cannot be backfilled** —
   it accumulates from the day collection starts (P10.10).
10. **Cross-exchange logic already exists** in
    `brain/agent.py:_cross_exchange_probe()` (KuCoin + OKX). P10.7
    generalises it into a stored series — do not write a second one.

---

## Next recommended action

1. Next *code* session: **P10.5** — per-source data-quality checks
   wired into `readiness_strip()` (gap detection per window, price/volume
   sanity, staleness, rate-limit budget). Read the roadmap first.
2. A human does TODO-7 + TODO-8 from
   [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
3. Do **not** start Dify/LibreChat. Do not loosen the graduation bar.

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md, branch arena/019ff948-sky.
> P10.1–P10.3 are shipped and P10.2 was hardened (PR #12 merged):
> perp pages the real perp endpoint, rate-limit handling is real
> (weight headers, backoff, geo-block abort, request cap), forming
> candles never enter history, and the unbounded-demo hang is fixed.
> Implement P10.4 (derivatives time series: funding / OI / mark /
> index / basis + honest liquidations rename) from
> docs/DATA_INFRASTRUCTURE_ROADMAP.md. No new agents/panels.
> Do not start Dify or LibreChat.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# 403 passed, 1 skipped
```

P10 backfill + store (DEMO_MODE is fully offline):

```bash
DEMO_MODE=1 .venv/bin/python main.py backfill --symbol BTCUSDT --market perp \
    --tf 1m --start-ts 1785960000000 --end-ts 1786017600000 --repair --rollup
DEMO_MODE=1 .venv/bin/python main.py store --market perp --tf 1m
DEMO_MODE=1 .venv/bin/python main.py derivatives collect --symbol BTCUSDT
DEMO_MODE=1 .venv/bin/python main.py derivatives status --symbol BTCUSDT
# real data (operator's machine, Binance-reachable):
python main.py backfill --symbol BTCUSDT --market perp --tf 1m --since 2019-09-08
python main.py derivatives collect --symbol BTCUSDT
```

Paper-book grind + graduation (offline sample/synthetic data):

```bash
DEMO_MODE=1 .venv/bin/python main.py simulator --bars 3000 --step 1   # grind
DEMO_MODE=1 .venv/bin/python main.py desk                             # watch the line
DEMO_MODE=1 .venv/bin/python main.py learn                            # calibrate from the store
```

Local wheel-gate (build + dup-check, no install):

```bash
DEMO_MODE=1 .venv/bin/python ci/wheel_gate.py
# builds cryptobrain-2.5.0-py3-none-any.whl ; no duplicate entries
```

Readiness strip, all four surfaces:

```bash
DEMO_MODE=1 python main.py doctor --strip          # CLI text
DEMO_MODE=1 python main.py doctor --strip --json   # CLI JSON
curl -s localhost:8080/api/readiness                # HTTP
# MCP: tools/call {"name": "readiness", "arguments": {}}
```

(The 1 skipped test is the SDK-already-installed fallback, present
since the consolidated build per `MERGE_NOTES.md`.)

## Last commit

```
see `git log --oneline -3` on arena/019ff948-sky
(this session: P10.2 hardening — perp endpoint + rate-limit machinery)
```

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, branch arena/019ff948-sky.

First, inspect the GitHub repository before making changes.

Read in this order:
1. SESSION_STATE.md         (current state, current TODO, last commit)
2. TODO.md                  (prioritised remaining work)
3. ARCHITECTURE.md          (module map + invariants)
4. CHANGELOG.md             (what shipped, when)
5. README.md                (user-facing overview)
6. ROADMAP_AGENT_REACH_UPGRADE.md  (the P7/P8/P9 plan + D1–D5 decisions)

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
- Maintain test count at ≥ 403 pass.
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

1. [x] Finish or safely stop the current task.
2. [x] Run `DEMO_MODE=1 python -m pytest tests/ -q` — must stay
   ≥ 403 pass (383 previous bar).
3. [x] Fix any obvious failures.
4. [x] Update `SESSION_STATE.md` with the exact current state.
5. [x] Update `TODO.md` — mark finished items done, reprioritise.
6. [x] Update `CHANGELOG.md`.
7. [x] Record all files changed in `SESSION_STATE.md`.
8. [x] Record the last successful test command.
9. [x] Record the last commit reference.
10. [x] Record any known bugs or unresolved issues.
11. [x] `git add` / `git commit` / `git push origin arena/019ff948-sky`.
12. [x] Open the session PR as the closing step — **PR #12**.
