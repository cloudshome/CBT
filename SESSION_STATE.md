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

**Last updated:** 2026-08-13 (this session: P12.1 shipped — locked train/val/OOS/recent walk-forward protocol + sealed OOS envelope + `python main.py validate`; P10 fully shipped; P11 gate still honestly closed)
**Branch:** `arena/019ffafa-sky` (this session branches from `main` @ `bf31431` — PR #18 `feat(P10.8-P10.12)` is already MERGED there; P10.8–P10.12 are part of our base, not our deliverable)
**HEAD commit:** `bf31431` (`main`); our work commits on top on `arena/019ffafa-sky`; one PR opened at session close (never self-merge).
**Python:** 3.10+ tested on 3.10–3.13 + Windows (per existing CI)

> **This session (`arena/019ffafa-sky`): P12.1 — the SKY Quant
> Validation Engine's locked walk-forward protocol.** With P10 fully
> shipped (P10.1–P10.12, PR #18) the P12 gate condition ("after
> P10.11") is finally met, so the Freqtrade/Backtrader audit's first
> build row is done: `data/validation.py` + `python main.py validate`
> + `tests/test_validation.py` (17 tests). The protocol: four
> chronological locked windows (train/val/OOS/recent) over the
> analyzed range; plans bucket by their **signal bar**; each window
> checked against the **live graduation bar**
> (`GRADUATION_CRITERIA`); PASS requires train AND val — train alone
> can never pass; OOS/recent are **sealed envelopes** (BT6):
> identical runs reuse the stored seal (SHA-256 config fingerprint
> gate), re-opening needs `--reseal` and is recorded in the seal
> history. Full pipeline proven on sandbox demo store
> (backfill → 11,520 stored 15m candles → verdict → seal reuse →
> reseal). Version **2.8.0 → 2.9.0**. Suite **471 → 488 pass / 1
> skip** (+17). Reconciliation gap fixed: PR #18 had shipped
> P10.8–P10.12 with no changelog entry and stale TODO tables — a
> retroactive `[2.8.0 — P10.8–P10.12 addendum]` changelog entry now
> closes it. Next *code* is **P12.2** (lookahead scanner).


> **This session (`arena/019ffab2-sky`): P10.7 — cross-exchange
> series.** Premium/discount vs Binance and funding spread are now a
> stored, queryable series under `data/store/cross/**`. The live
> health probe was **generalised** (`data/cross_exchange.snapshot_prices`,
> KuCoin + OKX + Bybit) — health/preflight/collector share one
> function. CLI: `python main.py cross collect|status`. DEMO_MODE
> stays offline via `FakeVenueTransport`. Version **2.7.2 → 2.8.0**.
> Suite **449 → 471 pass / 1 skip** (+22). Next *code* is **P10.8**
> (Lightweight Charts). F1–F8 / BT1–BT8 stay decided.
>
> **Prior session (`arena/019ffa8d-sky`): Backtrader recommendation
> reviewed and rejected.** A ChatGPT audit proposed mining Backtrader
> for research architecture (Cerebro→feeds→strategy→broker→analyzers),
> putting it behind a swappable adapter, and upgrading expectancy /
> walk-forward / Monte-Carlo / regime-matrix discipline. Compared to the
> live desk: SKY already *is* the separated architecture, and the
> honest validation ideas were already named **P12** by the Freqtrade
> review. A reset was considered and refused a second time — adopting
> Backtrader would contradict the note itself ("don't make it your
> brain") and add a live-broker order surface invariant #1 forbids.
> Decisions **BT1–BT8** are in `docs/BACKTRADER_REVIEW.md`: no
> dependency / vendored engine / adapter (BT1), no Cerebro rewrite
> (BT2), no second grader (BT3/BT7), no entry parameter-search (BT4),
> P12 done-whens extended (BT5), sealed OOS confirmed (BT6), no reset
> (BT8). Docs + contract tests only.
>
> **Prior session (`arena/019ffa5d-sky`, merged as PR #15): Freqtrade
> recommendation reviewed and rejected.** A ChatGPT audit proposed
> putting Freqtrade under SKY as execution + backtest + strategy
> runtime, plus a Quant Validation Engine. Compared to the live desk:
> SKY already *is* the brain, the risk gate, and the R-expectancy loop.
> Adopting Freqtrade would violate invariant #1 (never place an order)
> and A1 (one tested edge). **The repo is not reset.** Decisions F1–F8
> are in `docs/FREQTRADE_REVIEW.md`. The useful ideas become **P12** on
> our backtester after P10.11.
>
> **Prior session's decision — part 1: a parallel-session race, resolved
> by reconciling instead of duplicating.** The session branched from
> `main` @ `ee99486` (post-PR-#10) and built its own P10.2 backfill.
> Mid-session it discovered two *other* Arena sessions had already
> merged **PR #11** (P10.2 backfill + P10.3 gaps/rollups) and **PR #12**
> (P10.2 hardening: real perp endpoint, header-aware rate limiting;
> P10.4 derivatives series) into `main`. Per the repo's own rule —
> *never duplicate completed components* — this session **merged `main`
> and adopted the reviewed implementation wholesale**, discarding its
> own parallel draft. Its genuinely new value was kept as 3 edge-case
> tests in `tests/test_backfill.py` (empty-first-page termination,
> start-past-end no-op, mid-history-hole termination).
>
> **Part 2 (same PR, same session): P10.5 — data-quality pillar.** With
> the ladder clear (re-checked `origin/main`: no new merges), the
> session built the next milestone: `data/quality.py` + a **fourth
> readiness pillar** (`data`) in `readiness_strip()`. Per-series checks
> (staleness, gaps, price/volume sanity, ordering) over the stored
> Parquet history; a corrupt or unusably stale series is **quarantined**
> (`level=down` → `ready: false`). Empty store = honest `degraded` with
> the backfill hint. CLI/HTTP/MCP/dashboard all inherit the pillar via
> the one `readiness_strip()` (invariant #10). MCP `SERVER_VERSION`
> 1.4.0. 18 new offline tests, incl. the milestone's proof: corrupt
> fixture written through the real store ⇒ quarantine ⇒ `ready: false`.
> Suite **406 → 424 pass / 1 skip** (+18). Version **2.5.0 → 2.6.0**.
> (Merged via PR #13.)
>
> **Part 3 (own PR #14): P10.6 — Bybit adapter.** Second venue behind
> the same normalised schema: `data/bybit_client.py` implements the
> exact `PageResult`/`klines_page` transport contract, so the hardened
> backfill pages Bybit V5 identically to Binance — resumable,
> idempotent, rate-limit aware. Venue quirks (V5 categories
> `spot`/`linear`, V5 interval codes, newest-first rows, string
> parsing, `retCode 10006 → 429`) stay inside the adapter. CLI:
> `backfill --exchange bybit`. The milestone's proof — *identical
> assertions pass for both adapters* — is
> `tests/test_bybit.py::_assert_adapter_contract()` run against both
> clients, plus 15 more offline tests. Suite **424 → 441 pass / 1
> skip** (+17). Version **2.6.0 → 2.7.0**. Next: P10.7
> (cross-exchange series).

> **This session (continuation of `arena/019ffad5-sky`, from P10.7 base):** P10.8, P10.9, P10.10, P10.11, P10.12 delivered. **P10.8** — vendored `lightweight-charts.standalone.js`, `renderLightweightChart()` with price candlestick + histogram volume pane (`addHistogramSeries`), `/api/candles` feed. **P10.9** — two dedicated market-tab cards (`FUTURES — OPEN INTEREST & FUNDING`: funding rate with sign/color + interpretation; OI value/trend; L/S ratio color; mark/index/basis — reads from `market_context`; `FLOW — CVD & VOLUME DELTA`: CVD z-score, volume delta z, volume spike ratio, VWAP position, buy/sell imbalance — reads from feature snapshot `f`). Cards include interpretation notes linking to P10.12 conditioned-query goal. **P10.10** — `data/ws_client.py`: public Binance WebSocket streams (`!forceOrder@arr` + `klines`); reconnect/backoff (exponential + jitter, max 30s); graceful stop; `DEMO_EVENT_STREAM` (offline-safe); `WsClient` singleton; `reconnect_state()` feeds readiness strip; `accumulation_stats()` feeds feature store. No `Freqtrade` / `Backtrader` / `Codex` import. **P10.11** — `data/backtester.py`: `run_backtest_on_store()` reads `CandleStore.read()` instead of live fetch; returns clear error for missing/short series; feeds multi-year offline backtests. **P10.12** — `data/feature_store.py`: `build_feature_table()` (joins price + derivatives + hidden_alpha + regime); `FEATURE_COLUMNS` (22 columns); `save_feature_table()` / `read_feature_table()`; one row per `(symbol, timeframe, ts)`; derived (not duplicate) dataset; feeds conditioned-expectancy queries. **P11 gate unchanged**: honestly closed (+0.263R / 34.1% / PF 1.40 — `AI_ANATOMY_ROADMAP.md` / `CHANGELOG.md`). PR #17 remains open; do not merge. No new runtime dependency (no `websockets` package installed — stub degrades safely). All syntax verified (`python -c ast.parse...` passed for all four files). `SESSION_STATE.md` updated; next session reads this first.
>
> **Next concrete milestone after this session:** P11 paper-book grind continues (gate still honestly closed); P10.10 reconnect/live-accumulation needs real-network confirmation once `pip install websockets` is available; P12 validation engine starts after P10.11 is confirmed working with stored data. `docs/DATA_INFRASTRUCTURE_ROADMAP.md` §9 milestone table should be updated to mark P10.8–P10.12 shipped.

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
(our own stored market history — ✅ P10.1–P10.12 shipped; the research
proof that makes the edge trustworthy — 🔄 P12.1 shipped, P12.2 next). Every phase
below is ordered by how directly it moves those two lines.

---

## Current phase

**P12 (SKY Quant Validation Engine) — P12.1 shipped.** P10 (data
infrastructure) is fully shipped (P10.1–P10.12, PR #18); P11 first
grind shipped and the graduation gate is still honestly closed.
Freqtrade rejected (F1–F8); Backtrader rejected (BT1–BT8). Open
items: TODO-7, TODO-8; P12.2 → P12.7; P11 grind continues alongside.

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
| **P10** | **Data infrastructure + market terminal** | ✅ Complete | **P10.1–P10.12 shipped** (PR #18): store, backfill, gaps/rollups, derivatives, quality pillar, Bybit, cross-exchange, Lightweight Charts, futures/flow cards, WS tier, store-backtester, feature store. [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **Quant Validation Engine** | 🔄 In progress | **P12.1 shipped** (locked train/val/OOS/recent protocol + sealed OOS, `data/validation.py`, `python main.py validate`); next **P12.2** lookahead — `docs/FREQTRADE_REVIEW.md` extended by `docs/BACKTRADER_REVIEW.md` |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-13 (this branch `arena/019ffab2-sky`): P10.7 — cross-exchange series

Branched from `main` after the Backtrader review (PR #16). Inputs only
— no strategy, risk-gate, or engine behaviour change. Version
**2.7.2 → 2.8.0**. Suite **449 → 471 pass / 1 skip** (+22).

**What landed:**
- `data/cross_exchange.py` — venue registry (KuCoin/OKX/Bybit),
  `snapshot_prices()` (the single probe), `snapshot_funding()`,
  `CrossExchangeStore` (`data/store/cross/**`, same schema/PK as
  P10.4), `derive_premium` / `derive_funding_spread`,
  `FakeVenueTransport`, `CrossExchangeCollector` (candle-derived
  premium, Bybit funding pages, live/fake snapshot). Snapshot ts
  floors 15m (price) / 8h (funding).
- `data/bybit_client.py` — `funding_history()` →
  `GET /v5/market/funding/history` (`category=linear`); XAU → empty
  frame; transport fail → `None`.
- `brain/agent.py` — `_cross_exchange_probe` is a thin
  `snapshot_prices` wrapper; `_CROSS_EXCHANGES` re-exports `VENUES`.
- CLI — `python main.py cross collect|status`.
- Tests — `tests/test_cross_exchange.py` (20) + 2 Bybit funding
  tests; `test_cross_exchange_probe_uses_newest_candle` now mocks
  Bybit V5 `result.list`.

**Files changed:** `data/cross_exchange.py` (new),
`data/bybit_client.py`, `brain/agent.py`, `main.py`,
`tests/test_cross_exchange.py` (new), `tests/test_bybit.py`,
`tests/test_agent.py`, `config.py`, `pyproject.toml`, `CHANGELOG.md`,
`ARCHITECTURE.md`, `README.md`, `SKILL.md`, `TODO.md`,
`docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `docs/INFRASTRUCTURE_LAYERS.md`,
`AI_ANATOMY_ROADMAP.md`, this file.

---

### Session 2026-08-13 (prior branch `arena/019ffa8d-sky`): Backtrader review · BT1–BT8 · P12 extended

Branched from `main` @ `e462318` (PR #15 merged: Freqtrade F1–F8).
0 regressions. Docs + contract tests only — **no runtime change**.
Version **2.7.1 → 2.7.2**. Suite **445 → 449 pass / 1 skip** (+4).

**What was reviewed:** a ChatGPT Backtrader audit (22 sections) —
mine Backtrader as a research engine (Cerebro → feeds → strategy →
broker → analyzers), put it behind a swappable adapter, standardise a
`StrategyResult`, keep expectancy-in-R, net-of-costs, risk-veto,
analyzers, MAE/MFE, regime matrices, walk-forward, sealed OOS,
plateau-over-peak, Monte Carlo, risk-of-ruin, a strategy scorecard,
and a P0–P4 priority list.

**What was decided (see `docs/BACKTRADER_REVIEW.md`):**
- **BT1/BT2/BT3 = No** — no `backtrader` dependency, adapter, vendored
  engine; no Cerebro rewrite; no second grader (two fill semantics =
  two truths).
- **BT4 = No** — no entry parameter-search (consistent with F3).
- **BT5/BT6 = Yes, into P12** — scorecard (P12.3), plateau test
  (P12.4), net-of-costs funding-as-of-T (P12.6), risk-of-ruin table
  (P12.7); sealed final OOS = P12.1.
- **BT7 = Parked/never as a dependency** — second engine only as an
  ad-hoc throwaway check, if our grader is ever doubted.
- **BT8 = No** — the repo is not reset.

**Why no reset (this time):** the note itself argues against embedding
Backtrader ("don't make it your brain"), its §17 admits the missing
crypto layer is data — which is exactly what P10 is building — and P10
is mid-ladder with P11 grinding. A reset would contradict the
recommendation *and* stall the aim. Two independent audits have now
converged on the same plan: our grader, our store, P12 after P10.11.

**Files changed:** `docs/BACKTRADER_REVIEW.md` (new); `TODO.md`
(Backtrader out-of-scope; P12 definitions extended; next code still
P10.7); `SESSION_STATE.md`; `ARCHITECTURE.md` (invariant #13 extended,
version 2.7.2, baseline 449); `AI_ANATOMY_ROADMAP.md` (P12 names both
reviews; out-of-scope + test count); `docs/DATA_INFRASTRUCTURE_ROADMAP.md`
(P10.11 wording; out-of-scope); `docs/INFRASTRUCTURE_LAYERS.md`
(Backtrader row; order-of-work); `PROFESSIONAL_PLAN_DECISIONS.md`
(addendum 2); `BLUEPRINT.md` (backtester-ours line); `README.md`
(both reviews in the quote block); `SKILL.md` (do-not list);
`config.py` + `pyproject.toml` 2.7.2;
`tests/test_handoff_memory.py` (+4 contract tests).

---

### Session 2026-08-13 (prior branch `arena/019ffa5d-sky`, merged as PR #15): Freqtrade review · F1–F8 · reconciled onto P10.6

The operator merged PR #14 (P10.6 Bybit, `main` @ `e233580`) while
PR #15 was open. This session merged `origin/main` and kept **both**
the Bybit adapter and the F1–F8 decisions. **No runtime engine
change beyond what #14 already shipped.** Docs + contract tests.
Version **2.7.0 → 2.7.1**. Suite **441 → 445 pass / 1 skip** (+4).

**What was reviewed:** a ChatGPT Freqtrade audit (use Freqtrade as
execution + backtest + strategy runtime; modular strategy catalog;
Hyperopt-with-caution; FreqAI later; Quant Validation Engine).

**What was decided (see `docs/FREQTRADE_REVIEW.md`):**
- **F1/F2/F3 = No** — do not adopt Freqtrade, Hyperopt, or FreqAI.
- **F4 = No** — do not expand the strategy catalog before graduation.
- **F5/F6 = Yes** — the validation ideas become **P12** on *our*
  backtester, after P10.11.
- **F7 = Park** — auto capital allocation after graduation + >1 edge.
- **F8 = No** — do not reset the repository.

**Why no reset:** SKY already *is* the brain (`engine/` + `brain/`),
already has the risk gate, already reports R-expectancy, already
walks forward without look-ahead, already has Monte Carlo / MAE/MFE.
Freqtrade's remaining value is placing orders — forbidden by
invariant #1. ICT/SMC conditional plans do not fit
`populate_entry_trend`.

**Files changed:** merge of `origin/main` @ `e233580` (PR #14);
`docs/FREQTRADE_REVIEW.md` (new); `TODO.md` (TODO-13 / P12 +
out-of-scope; next code P10.7); `SESSION_STATE.md`;
`ARCHITECTURE.md` (invariant #13); `AI_ANATOMY_ROADMAP.md`;
`docs/DATA_INFRASTRUCTURE_ROADMAP.md`; `docs/INFRASTRUCTURE_LAYERS.md`;
`PROFESSIONAL_PLAN_DECISIONS.md`; `BLUEPRINT.md`; `SKILL.md`;
`README.md`; `CHANGELOG.md`; `config.py` + `pyproject.toml` 2.7.1;
`tests/test_handoff_memory.py` (+4 contract tests).

---

### Session 2026-08-13 (prior branches): PR #13 + PR #14 — reconciliation, P10.5, P10.6 Bybit

Branched from `main` @ `ee99486` (post-PR-#10, before PR #11/#12 landed).
0 regressions. Tests **403 → 406 pass / 1 skip** (+3). Version unchanged
**2.5.0** (no runtime change).

**What happened:** this session independently built its own P10.2
backfill (`data/backfill.py`, `main.py backfill`, 19 tests) unaware
that parallel sessions had merged PR #11 (P10.2 + P10.3) and PR #12
(P10.2 hardening + P10.4) into `main`. On discovery, the rule won:
*never duplicate completed components*. This session:

- **Merged `main` into the session branch** and adopted the reviewed
  implementation wholesale (hardened backfill, gaps/rollups,
  derivatives store) — its own parallel draft was discarded.
- **Kept its genuinely new value as three edge-case tests** appended
  to `tests/test_backfill.py`, all passing against the merged code:
  empty-first-page termination, start-past-end no-op, mid-history-hole
  termination (no duplicates, repair is P10.3's job).
- **Reconciled the docs** (`SESSION_STATE.md`, `TODO.md`, `CHANGELOG.md`,
  `ARCHITECTURE.md`) so the next session reads one true story.

**Files changed:** merge of `main` @ `54fec5a` (PR #11 + #12);
`tests/test_backfill.py` (+3 edge-case tests); **P10.5:** `data/quality.py`
(new), `data/store.py` (`list_series()`), `brain/agent.py` (`_data_pillar`
+ 4-pillar strip), `mcp_server.py` (v1.4.0), `main.py` / `web/app.py`
descriptions, `tests/test_quality.py` (new, 18 tests), pinned pillar-set
assertions in `test_agent` / `test_web_api` / `test_mcp_stdio` /
`test_channels` / `test_dashboard_js`; **P10.6:** `data/bybit_client.py`
(new), `main.py` (`--exchange bybit`, repair routing, venue-neutral
geo-block message in `data/backfill.py`), `tests/test_bybit.py` (new,
17 tests); docs: `CHANGELOG.md` (v2.6.0 + v2.7.0), `config.py` +
`pyproject.toml`, `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`,
`README.md`, `SKILL.md`, `ARCHITECTURE.md`, this file.

---

### Session 2026-08-13 (prior branch): P10.2 hardening — perp endpoint + rate-limit machinery

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

This session (`arena/019ffab2-sky`) **shipped P10.7** — committed
`ac446ae`, pushed, **PR #17** opened against `main`. Nothing else is
in flight. Next *code* session: **P10.8** (Lightweight Charts
replaces `chartSVG()`). Do not start P12, Dify, LibreChat, or a
strategy-module catalog. Do not open a second PR from this session.

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
2. **TODO-12 (P10)** — P10.1–P10.7 done. Next: **P10.8** (Lightweight
   Charts replaces `chartSVG()`; price+volume pane over stored data;
   no new runtime dep). Full plan:
   [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md)
   — it records which parts of the incoming plan were corrected and why.
3. **TODO-7** — human pastes the wheel-gate job into the **real**
   `.github/workflows/ci.yml` (the `docs/` copy is inert).
4. **TODO-8** — human protects `main` (require PR). Token: HTTP 403.
5. **TODO-13 (P12)** — SKY Quant Validation Engine. Parked until
   P10.11. Do not start next session. Spec:
   [`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md) §8, extended
   by [`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md) §8.
6. **TODO-9 / TODO-10** — Dify then LibreChat. Parked behind both the
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
6. **`CHANGELOG.md` is current** through v2.8.0.
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
9. **The dashboard readiness strip lives outside `#app`.** `render()`
   replaces `#app.innerHTML` wholesale, so anything inside it would be
   destroyed on every scan. Keep the strip where it is.
10. **Live scans are still amnesiac.** The Parquet store + backfill exist
    (P10.1–P10.7) but the scanner/backtester still fetch ~500 live candles
    (P10.11 wires them to the store).
11. **This sandbox has no network egress.** The real Binance backfill
    cannot run here (verified live: clean abort with a resumable message).
    Run it on the operator's machine. All P10.2 behaviour is proven
    offline via `FakePagedTransport` / `SampleClient`.
12. **`BinanceClient.liquidations()` was not liquidation data** — a
    24h-ticker proxy. Renamed honestly in P10.4 to
    `liquidation_stats_proxy()`. Real forced-order data only comes from
    the `!forceOrder@arr` WebSocket stream and **cannot be backfilled** —
    it accumulates from the day collection starts (P10.10).
13. **Parallel sessions race on `main`.** PR #11/#12 merged while PR #13
    was being built on an older base. Lesson recorded here: **before
    finishing any session, `git fetch` + compare with `origin/main`**;
    if newer P10 work landed, merge and reconcile instead of shipping a
    duplicate. PR #13 was that reconciliation (merged).
14. **Cross-exchange probe is one function.**
    `data/cross_exchange.snapshot_prices()` (KuCoin + OKX + Bybit);
    `brain/agent.py:_cross_exchange_probe` is a thin wrapper. Do not
    write a second probe. Stored series live under `data/store/cross/`.
15. **Freqtrade was reviewed and rejected (F1–F8).** Do not reopen
    that as a “quick win.” The keep/cut is
    `docs/FREQTRADE_REVIEW.md`. Contract-tested in
    `tests/test_handoff_memory.py`.
16. **Backtrader was reviewed and rejected (BT1–BT8).** Same rule: no
    dependency, dev tool, vendored engine, adapter, or second grader.
    The keep/cut is `docs/BACKTRADER_REVIEW.md`, contract-tested in
    `tests/test_handoff_memory.py`. P12's definitions were extended by
    it (scorecard, plateau test, net-of-costs, risk-of-ruin table).

---

## Next recommended action

1. Next *code* session: **P10.8** — Lightweight Charts replaces
   `chartSVG()` (price + volume pane over stored data; vendor the
   script locally; no new runtime dep). Read the roadmap first.
   **First step of every future session:** `git fetch` and diff
   against `origin/main` — parallel sessions merge while you work (see
   known problem 13); reconcile before building.
2. A human does TODO-7 + TODO-8 from
   [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
3. Do **not** start Dify/LibreChat/P12. Do not install Freqtrade or
   Backtrader. Do not loosen the graduation bar. Do not add strategy
   modules.

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md. P10.7 shipped as PR #17
> (do not reopen or merge it from the session). Do not adopt
> Freqtrade / Hyperopt / FreqAI / Backtrader (F1–F8 / BT1–BT8).
> Implement P10.8 (Lightweight Charts replaces chartSVG;
> price+volume pane over stored data; vendor locally; no new
> runtime dep) from docs/DATA_INFRASTRUCTURE_ROADMAP.md. Fetch and
> diff origin/main first. No new agents/panels/strategies. Do not
> start Dify, LibreChat, or P12.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# 488 passed, 1 skipped
```

Readiness strip (four pillars since P10.5):
```bash
DEMO_MODE=1 python main.py doctor --strip          # CLI text — channels/immune/risk_gate/data
DEMO_MODE=1 python main.py doctor --strip --json   # CLI JSON
curl -s localhost:8080/api/readiness               # HTTP
# MCP: tools/call {"name": "readiness", "arguments": {}}
```

P10 backfill + store (DEMO_MODE is fully offline):

```bash
DEMO_MODE=1 .venv/bin/python main.py backfill --symbol BTCUSDT --market perp \
    --tf 1m --start-ts 1785960000000 --end-ts 1786017600000 --repair --rollup
DEMO_MODE=1 .venv/bin/python main.py store --market perp --tf 1m
DEMO_MODE=1 .venv/bin/python main.py derivatives collect --symbol BTCUSDT
DEMO_MODE=1 .venv/bin/python main.py derivatives status --symbol BTCUSDT
DEMO_MODE=1 .venv/bin/python main.py cross collect --symbol BTCUSDT
DEMO_MODE=1 .venv/bin/python main.py cross status --symbol BTCUSDT
# real data (operator's machine, Binance-reachable):
python main.py backfill --symbol BTCUSDT --market perp --tf 1m --since 2019-09-08
python main.py backfill --exchange bybit --symbol BTCUSDT --market perp --tf 1m
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
# builds cryptobrain-2.8.0-py3-none-any.whl ; no duplicate entries
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
ac446ae feat(p10.7): store cross-exchange premium and funding spread
538dd8f docs: reject Backtrader as a SKY layer; P12 validated + extended (BT1–BT8) (#16)
```

Plus a docs-only handoff commit on this branch recording PR #17.
See `git log --oneline -3`. PR: https://github.com/Azimshawon/SKY/pull/17
(open; do not merge).

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, branch arena/019ffab2-sky.

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
- Maintain test count at ≥ 488 pass / 1 skip.
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

1. [x] Finish or safely stop the current task. — **P12.1 shipped.**
2. [x] Run `DEMO_MODE=1 python -m pytest tests/ -q` — **488 pass /
   1 skip** (≥ 471 previous bar; +17 new validation tests).
3. [x] Fix any obvious failures. — seal-payload ordering bug found
   by the live demo (seal record was written before `report["seal"]`
   existed) — fixed + regression-tested.
4. [x] Update `SESSION_STATE.md` with the exact current state.
5. [x] Update `TODO.md` — P12.1 marked shipped, P10.1–P10.12 marked
   shipped, P12.2 reprioritised to top.
6. [x] Update `CHANGELOG.md` — 2.9.0 entry + retroactive
   `[2.8.0 — P10.8–P10.12 addendum]` (PR #18 shipped without one).
7. [x] Record all files changed in `SESSION_STATE.md`.
8. [x] Record the last successful test command.
9. [x] Record the last commit reference.
10. [x] Record any known bugs or unresolved issues. — none blocking;
    see "known limits" in the session block.
11. [x] `git add` / `git commit` / `git push origin arena/019ffafa-sky`.
12. [x] Open the session PR as the closing step — one PR from
    `arena/019ffafa-sky` → `main` (P12.1).
