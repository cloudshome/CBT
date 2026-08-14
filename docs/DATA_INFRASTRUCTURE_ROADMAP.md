# DATA_INFRASTRUCTURE_ROADMAP.md — P10 · SKY Market Terminal

> **Status:** ✅ **COMPLETE — P10.1–P10.12 delivered** (P10.1–P10.3 on
> 2026-08-12; P10.4 derivatives + P10.2 hardening + P10.5 data-quality
> + P10.6 Bybit adapter + P10.7 cross-exchange series + P10.8 charts
> + P10.9 futures/CVD panes + P10.10 WS tier + P10.11 store-backtest
> + P10.12 feature store delivered 2026-08-13 — PR #18).
> The P10.2 backfill pages the real perp endpoint and its rate-limit
> handling is weight-header pacing + exponential backoff + geo-block
> abort.
> Next: P12 — the SKY Quant Validation Engine now runs on this stack
> (**P12.1 + P12.2 shipped 2026-08-13**: locked walk-forward protocol,
> sealed OOS, and `python main.py validate lookahead` negative-shift guard
> in `data/validation.py`; **P12.3 shipped 2026-08-14**: the boxed
> strategy scorecard in `data/scorecard.py`, on CLI + `/api/scorecard`
> + MCP; **P12.3.1 shipped**: the backtester's same-bar SL/TP tie-break now
> matches the paper trader's conservative stop-first rule; **P12.3.2
> shipped 2026-08-14 — real market data**: real Binance spot BTCUSDT 1m
> (2025-01-01 → 2026-04-30, 696,960 bars, sha256-pinned from Binance's
> official public archive) imported offline via `backfill --from-csv`
> through the same adapter boundary this doc specifies, rolled up with
> the P10.3 rollups, and P11/P12.1/P12.3 re-run on it — every number is
> in `docs/REAL_DATA_RUN_2026-08-14.md`. Next: fees-first P12.6.
> **Phase:** P10 — the next *major* milestone after the paper-book proof.
> **Owner doc:** this file. `TODO.md` links here; don't duplicate detail there.
> **Created:** 2026-08-12
>
> **One-line goal:** build SKY's own BTC research terminal on free/public
> exchange APIs — collect the raw data ourselves, store it ourselves,
> and let the engine reason over stored evidence instead of one live
> candle fetch.

---

## 0. Why this phase exists (the straight line to the aim)

The aim never moves: **become a fully independent, consistently
profitable trader.** Independence has two halves, and SKY currently
only has one.

| Half | Meaning | Status |
|---|---|---|
| **Decision independence** | Our own engine, our own risk gate, our own approval loop — not somebody's signal group | ✅ Done (P1–P9) |
| **Data independence** | Our own stored market history — not a live API call we re-issue and forget | ❌ **This phase** |

Right now every scan is amnesiac: SKY fetches ~500 candles, decides,
and throws the candles away. That is the single biggest structural
limit on the project. It caps backtests at whatever the exchange will
hand us in one request, it makes "how did this setup behave when OI
rose and funding was negative?" unanswerable, and it means our edge is
re-derived from scratch every run.

**P10 fixes the input side of the funnel, not the brain.** No new
agents, no new AI wrapping. Store evidence, then reason over it.

### Where P10 sits in the order of work

```text
DONE     P10.1 → P10.12 · data infrastructure + market terminal  ← THIS DOC
           ↓  shipped (PR #18) — unlocks real backtesting on stored data
ALONG    P11 · prove the paper book (counts done; gate still closed)
           ↓  do not loosen the bar
NOW      P12 · SKY Quant Validation Engine  (P12.3 + P12.3.1 +
           P12.3.2 REAL DATA shipped 2026-08-14 — see
           docs/REAL_DATA_RUN_2026-08-14.md; P12.6 fees-first next,
           ladder in docs/PATH_TO_REAL_MONEY.md)
           (walk-forward / OOS / lookahead / quality score /
            funding-OI-CVD-conditioned + net-of-costs expectancy /
            risk-of-ruin table)
           ↓  see docs/FREQTRADE_REVIEW.md §8 + docs/BACKTRADER_REVIEW.md §8
PARKED   Dify (TODO-9) → LibreChat (TODO-10), after graduation
NEVER    Freqtrade / Hyperopt / FreqAI / Backtrader — not our backtester,
         not our runtime, not an adapter
```

**P11 still runs alongside P10.** The first grind shipped (counts
cleared; graduation gate honestly closed). P10.1–P10.6 are also
shipped. Do not let the data project become a reason to stop proving
the edge, and do not loosen the graduation bar to make the gate pass.

---

## 1. What SKY already has (do NOT rebuild these)

A repo inspection on 2026-08-12 found the following already shipped.
**Any P10 work must extend these, not replace them.**

| Capability | Where | Note for P10 |
|---|---|---|
| Binance REST klines, geo-fallback hosts, retries | `data/binance_client.py` | **Reuse as the Binance adapter's transport.** Already handles `limit` cap 1000 + `start_time`. |
| Funding rate, open interest, long/short ratio | `data/binance_client.py` | Already fetched — but **never stored**. P10 persists them. |
| Liquidations (proxy via 24h stats) | `data/binance_client.py:liquidations()` | Currently a *proxy*, not real forced-order data. P10 upgrades this honestly. |
| Cross-exchange price check (KuCoin + OKX + Bybit) | `data/cross_exchange.py:snapshot_prices()` (health wraps it) | ✅ P10.7 generalised the probe into a stored series. Do not write a second one. |
| Symbol aliasing (BTC→BTCUSDT, GOLD→XAUUSD) | `data/symbols.py` | The normalisation layer already has a home. |
| Offline determinism (`DEMO_MODE=1`) | `data/sample_client.py` | **Every P10 collector must have a DEMO_MODE path** or the test suite stops being offline. |
| SQLite store + `SignalDB` context manager | `data/database.py` | 10 tables, none of them candles. See §5 on storage. |
| Indicators, structure, MTF, regime, CVD, Kelly | `engine/` | The analytics in the source plan's "Phase 4" are **largely already built**. See §6. |
| Data-quality instinct | `brain/immune.py` | Freshness/staleness checks exist. P10 extends them per-source. |
| Dashboard with tabs + SVG candles | `web/app.py` | A chart exists. Lightweight Charts replaces the *renderer*, not the app. |

### Corrections to the incoming plan

The plan I was given is directionally right, and these are the places
where it double-counts work SKY has already done, or would cost us
something we already own:

1. **"Phase 4 — Analytics" is ~80% already done.** EMA, SMA, RSI,
   MACD, ATR, VWAP, Bollinger, volume profile/POC, OBV, CVD, and OI
   change all exist in `engine/indicators.py`, `engine/hidden_alpha.py`
   and `engine/features.py`. P10 should **feed them stored data**, not
   reimplement them. Genuinely new: realized volatility, funding
   pressure index, liquidation metrics, order-book imbalance.

2. **PostgreSQL + Redis is over-engineered for a single-user desk.**
   `ARCHITECTURE.md` states the invariant: *single-process,
   single-user, single-machine*. The plan itself says "do not
   introduce a new database technology if SKY already has an
   appropriate storage layer" — so we take it at its word. **SQLite +
   Parquet** covers this workload completely (see §5). Redis solves a
   multi-process cache-coherency problem we do not have. Revisit only
   if we ever run collectors as separate services.

3. **A React/Next.js frontend is a second app to maintain.** The
   dashboard is one self-contained Flask file today and the whole repo
   has five runtime dependencies. Lightweight Charts is a ~45 KB
   standalone script that works from a plain `<script>` tag — we get
   the TradingView-grade chart **without** adopting Node, a bundler,
   and a second deployment. See §7.

4. **FastAPI is unnecessary.** Flask already serves `/api/*` and the
   dashboard. Adding a second web framework splits the surface for no
   user-visible gain.

5. **Docker is not a P10 concern.** `ops/systemd/` already deploys
   this. Out of scope.

6. **The liquidation feed needs an honesty note.** Binance's
   `allForceOrders` REST endpoint is effectively unusable for history;
   real liquidation data comes from the `!forceOrder@arr` **WebSocket
   stream**, which only emits *going forward*. So: liquidation history
   can only be accumulated from the day we start collecting. It cannot
   be backfilled. Any liquidation-based feature is therefore gated on
   collection uptime — and the current `liquidations()` proxy must be
   renamed so nobody mistakes 24h stats for liquidation data.

7. **The plan's "open a pull request, don't merge to main" instruction
   conflicts with Arena's one-PR-per-session limit.** Keep the
   existing convention: one PR per session, only when the user asks.

---

## 2. Non-negotiable constraints

These carry over from `ARCHITECTURE.md` and do not bend for P10:

1. **Read-only.** Collectors use public market-data endpoints only.
   No API keys, no signed requests, no trading credentials, ever.
   A collector that can authenticate is a collector that can trade.
2. **Offline-first.** `DEMO_MODE=1` must keep the full suite green
   with zero network. Every adapter needs a deterministic fake.
3. **Bad data must never produce a signal.** Quarantine beats
   guessing. This extends the existing immune system.
4. **One computation, many surfaces** (invariant #10). Collector
   status appears in `doctor`/`readiness` via the *same* function the
   CLI, MCP, and dashboard already call.
5. **No new heavy dependencies without a demonstrated need.** Current
   runtime deps: numpy, pandas, requests, flask, python-dotenv.
   P10 adds at most: `pyarrow` (Parquet) and `websockets`.
6. **Data files never enter Git.** `data/store/**` goes in
   `.gitignore`. The repo stays small; the dataset lives on disk.

---

## 3. Data layers — collect in this order

Do **not** start by collecting 100 datasets. Each layer must be
storing clean, tested, deduplicated data before the next begins.

### Layer 1 — OHLCV backfill + incremental maintenance (the foundation)

The single highest-value piece of the whole phase. Everything else
depends on it.

```text
Symbols:     BTCUSDT perp (primary), BTCUSDT spot, ETHUSDT perp
Timeframes:  1m 5m 15m 1h 4h 1d      (1m is the master; rest derive)
Exchanges:   Binance first, Bybit second
Depth:       as far back as the public API allows, then maintain
```

**Master-timeframe rule:** store 1m as the source of truth and
*aggregate* 5m/15m/1h/4h/1d from it. Storing each timeframe
independently invites the two to disagree, and a disagreement between
your 15m and your 1m is a silent backtest corruption.

Flow:

```text
FIRST RUN → paginated REST backfill → Parquet (immutable history)
STEADY    → incremental REST top-up  → gap detector → repair
LATER     → WebSocket kline stream   → hot tail in SQLite
```

### Layer 2 — Derivatives state (SKY's real edge over a retail chart)

Already *fetched* by `binance_client.py`, never *stored*. Storing them
as a time series is what makes them analysable.

```text
funding rate       (current + historical + cross-exchange spread)
open interest      (level + change + velocity + divergence vs price)
mark / index price (→ basis = mark − index)
long/short ratio
```

The OI/price interaction is the point:

```text
price ↑ + OI ↑  →  new money entering the move
price ↑ + OI ↓  →  short covering — weaker, fades more often
```

**Store first. Do not turn these into trading rules until the data
proves them.** That is the whole discipline of this project.

### Layer 3 — Order flow & liquidations (accumulate-only)

```text
aggTrades       → CVD, buy/sell imbalance, trade-size distribution
liquidations    → WS !forceOrder@arr; CANNOT be backfilled
order book      → derived metrics continuously, raw snapshots sparsely
```

**Order-book storage rule:** never persist every full snapshot — it
is gigabytes/day of mostly-noise. Persist *derived features* at a
fixed cadence (bid/ask imbalance at 5/10/25 levels, spread, depth,
microprice) plus a raw snapshot every N minutes for spot-checking.

### Layer 4 — Cross-exchange

Generalise the existing `_cross_exchange_probe()` into a stored series:
per-exchange price, premium/discount vs Binance, funding spread. This
is where genuine independence shows up — a single-venue view is how
retail gets wicked out.

---

## 4. Unified schema (the most important design decision)

Exchange-specific shapes must **never** reach the analytics layer.
One normalised record, one meaning, regardless of origin.

```text
Candle
  ts              int    epoch ms, UTC, candle OPEN time, inclusive
  exchange        str    'binance' | 'bybit' | ...
  market          str    'spot' | 'perp'
  symbol          str    SKY-canonical (via data/symbols.py)
  timeframe       str    '1m' | '5m' | ...
  open high low close    float
  volume          float  base asset
  quote_volume    float  quote asset
  trades          int    when the venue provides it
  closed          bool   false = still-forming candle
  source          str    'rest' | 'ws' | 'aggregated'
  ingested_at     int    epoch ms — when WE saw it
```

Three rules that prevent the classic silent corruptions:

1. **`ts` is always the candle OPEN, always UTC, always ms.** Bybit
   and Binance differ here; normalise at the adapter boundary.
2. **Never persist an unclosed candle into history.** A forming candle
   changes; a stored one must not. `closed=false` lives in the hot
   cache only.
3. **`ingested_at` is separate from `ts`.** Lets us detect a venue
   backfilling or revising data after the fact.

Primary key: `(exchange, market, symbol, timeframe, ts)`. Upsert on
conflict — that alone kills the duplicate-row class of bug.

---

## 5. Storage — SQLite + Parquet (corrected from the source plan)

```text
data/store/                        # gitignored
├── parquet/                       # immutable history, the archive
│   └── candles/
│       exchange=binance/market=perp/symbol=BTCUSDT/timeframe=1m/
│           year=2024/month=01/part-000.parquet
├── derivatives/                   # funding / OI / basis series
├── flow/                          # trades, liquidations, OB features
└── sky.db                         # existing SQLite: hot tail + app state
```

**Why Parquet:** columnar, compressed ~10:1 vs CSV, and pandas reads a
single partition without touching the rest. Years of 1m BTC candles
land in a few hundred MB and load in milliseconds. Hive-style
partitioning means a query for one month reads one file.

**Why not Postgres/Redis:** see §1 correction 2. If we later run
collectors as separate processes and hit SQLite write contention, that
is the moment to revisit — with evidence, not in advance.

**Retention:** Parquet history is permanent (it is the asset). Raw
order-book snapshots and raw trades get a retention window; their
derived features are permanent.

---

## 6. Analytics — mostly wiring, not writing

Because `engine/` already implements the indicator suite, P10's
analytics work is largely **pointing existing functions at stored data
instead of a live fetch**.

| Metric | Status |
|---|---|
| EMA, SMA, RSI, MACD, ATR, VWAP, Bollinger, Supertrend, ADX, Stoch, OBV, POC | ✅ `engine/indicators.py` |
| BOS/CHOCH, order blocks, FVG, liquidity sweeps, premium/discount | ✅ `engine/structure.py` |
| CVD, HMM regime, Bayesian Kelly, 8D fingerprint | ✅ `engine/hidden_alpha.py` |
| Rolling correlation, ETH/BTC beta | ✅ `engine/correlation.py` |
| **Realized volatility** | ❌ new |
| **Funding pressure index** (cross-exchange) | ❌ new |
| **OI velocity / OI-price divergence** | ❌ new |
| **Liquidation clustering** | ❌ new (needs Layer 3 uptime) |
| **Order-book imbalance / microprice** | ❌ new |

The unlock is not new indicators. It is that a backtest can finally
run over **years** instead of 500 bars, and can be **conditioned** on
derivatives state.

---

## 7. The terminal UI — Lightweight Charts, no framework

TradingView's Lightweight Charts is Apache-2.0, ~45 KB, and purpose-built
for streaming custom data. Crucially it ships as a standalone UMD build
usable from a plain `<script>` tag — **no React, no Next.js, no bundler,
no second app.** It replaces the hand-rolled `chartSVG()` renderer in
`web/app.py` and keeps SKY a single Flask process.

Panes, in build order:

```text
1. Price      candles + EMA + VWAP + volume        (replaces chartSVG)
2. Momentum   RSI / MACD
3. Futures    open interest + funding vs price     ← the differentiator
4. Flow       CVD, buy/sell volume
5. Liquidations                                    (after Layer 3 uptime)
6. Cross-exchange premium/discount
```

Vendor the script locally (`web/static/`) rather than a CDN — the
dashboard must work on a box with no outbound internet, same as
`DEMO_MODE`.

---

## 8. Data-quality engine (extends `brain/immune.py`)

Per-source, per-symbol, per-timeframe. Feeds the existing readiness
strip as a fourth pillar so a stale feed is visible in one glance.

```text
gap detection        expected vs actual candle count in a window
duplicate ts         prevented by the upsert PK, asserted by tests
price sanity         |Δ| beyond N×ATR without volume → quarantine
volume sanity        negative / absurd → reject
monotonic ts         out-of-order arrival → reject
clock skew           venue ts vs local now (already exists for probes)
staleness            last-ingest age per source
ws health            connected / reconnecting / dead, uptime %
rate-limit budget    remaining weight, backoff state
```

Verdict flows into the existing ladder: `ok → degraded → blocked → down`.

```text
GOOD  → analytics → signal
BAD   → quarantine → NO signal, and say why
```

This is the safety property that matters most: **the engine must
prefer silence to a signal built on corrupt data.**

---

## 9. Milestones (each independently shippable)

Each row is roughly one session, ends green, and leaves the repo in a
documented state. Ordered by value-per-session, same as `TODO.md`.

| # | Milestone | Deliverable | Done when |
|---|---|---|---|
| **P10.1** | Schema + store | `data/store.py` + `data/store/**` (gitignored): normalised `Candle`, Parquet read/write, upsert PK | ✅ shipped — 1m round-trips; dedup + ordering tested offline |
| **P10.2** | Binance backfill | paginated REST backfill reusing `binance_client`, resumable, rate-limit aware | ✅ shipped (`data/backfill.py`; re-run adds zero rows). **Hardened 2026-08-13:** real perp endpoint (`/fapi/v1/klines`), weight-header pacing, exponential backoff, geo-block abort, forming-candle rule, `--max-requests` cap |
| **P10.3** | Gaps + aggregation | gap detector, repair, 1m→5m/15m/1h/4h/1d rollups | ✅ shipped — synthetic gaps detected+repaired; rollups match venue candles |
| **P10.4** | Derivatives series | persist funding / OI / mark / index / basis over time | ✅ shipped — `data/derivatives.py` (store + collector + fake transport), `python main.py derivatives collect/status`; series queryable; `liquidations()` renamed honestly to `liquidation_stats_proxy()` |
| **P10.5** | Quality pillar | per-source checks wired into `readiness_strip()` | ✅ shipped (`data/quality.py`, fourth readiness pillar; corrupt data ⇒ quarantine ⇒ `ready: false`) |
| **P10.6** | Bybit adapter | second exchange behind the same normalised schema | ✅ shipped (2026-08-13, PR #14) — `data/bybit_client.py` behind the same `PageResult` contract; identical assertions pass for both adapters (17 tests) |
| **P10.7** | Cross-exchange | generalise `_cross_exchange_probe()` into a stored series | ✅ shipped — `data/cross_exchange.py`; `python main.py cross collect/status`; premium/discount + funding spread queryable; one probe |
| **P10.8** | Lightweight Charts | vendored chart replaces `chartSVG()`; price+volume pane | ✅ delivered (2026-08-13 session) — `web/app.py` uses `/static/lightweight-charts.standalone.js`; `renderLightweightChart()` with `addHistogramSeries()`; `/api/candles` feeds chart |
| **P10.9** | Futures panes | OI + funding + CVD panes | ✅ delivered (2026-08-13 session) — two new market-tab cards (`FUTURES — OPEN INTEREST & FUNDING`, `FLOW — CVD & VOLUME DELTA`) reading from `market_context` (`futuresCtx`) and feature snapshot (`f`) |
| **P10.10** | WebSocket tier | live klines + `!forceOrder@arr`, reconnect/backoff | ✅ delivered (2026-08-13 session) — `data/ws_client.py` (public streams only, reconnect/backoff, `DEMO_EVENT_STREAM`, singleton); no `Freqtrade`/`Backtrader` import; graceful degradation without `websockets` package |
| **P10.11** | Backtest on store | backtester reads Parquet instead of a live fetch | ✅ delivered (2026-08-13 session) — `run_backtest_on_store()` in `data/backtester.py` reads `CandleStore.read()`; returns honest error for missing/short series |
| **P10.12** | Feature store | one wide table per timestamp (price+deriv+flow+regime) | ✅ delivered (2026-08-13 session) — `data/feature_store.py`: `build_feature_table()` (joins price + derivatives + hidden_alpha + regime); `FEATURE_COLUMNS` (22 cols); `save_feature_table()` / `read_feature_table()`; feeds P12 conditioned queries |

**Definition of done for the phase:** we can ask *"how did this setup
perform when price rose, OI rose, funding was negative, and CVD was
positive?"* and get a number computed from our own stored data.

That question is answered by **P10.12 + P12**, on **our** grader
(`data/backtester.py`), not by importing Freqtrade or Backtrader. Two
2026-08-13 reviews rejected both: `docs/FREQTRADE_REVIEW.md` (F1/F2 —
backtester, strategy runtime, execution layer) and
`docs/BACKTRADER_REVIEW.md` (BT1–BT3, BT7 — dependency, dev tool,
vendored engine, adapter, second grader). P10.11 still
means: point *this* backtester at *this* Parquet store.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| **Data collection replaces trading progress** | P11 (paper proof) ships first. P10 is infrastructure for a *proven* edge, not a substitute for proving one. |
| Scope creep into a TradingView clone | Milestones are independently shippable; stop whenever the data is enough. |
| Rate limits / IP bans | Backfill once, maintain incrementally. Respect weight headers, exponential backoff. Never re-request months of candles on start. |
| Geo-blocking (already hit in this repo) | Existing multi-host fallback in `binance_client.py`; Bybit as a second venue. |
| Disk growth | Parquet + compression; retention windows on raw trades/OB; features are permanent, raw is not. |
| Offline suite breaks | Every adapter needs a `DEMO_MODE` fake. Non-negotiable. |
| Overfitting on richer data | More features = more ways to fool yourself. The graduation gate and out-of-sample discipline still rule. |

---

## 11. Explicitly out of scope for P10

- Trading credentials, signed endpoints, order placement — **forever**.
- Paid data vendors.
- OpenHands / Dify / LibreChat (TODO-9/10, still parked).
- **Freqtrade, Hyperopt, FreqAI, or any exchange-order bot** — reviewed
  and rejected (F1–F3 in `docs/FREQTRADE_REVIEW.md`). P10.11 is our
  grader reading our store, not a Freqtrade strategy runtime.
- **Backtrader — dependency, vendored engine, or adapter** — reviewed
  and rejected (BT1–BT3, BT7 in `docs/BACKTRADER_REVIEW.md`). Two fill
  semantics would be two truths; there is one grader and it is ours.
- PostgreSQL, Redis, Docker, FastAPI, React/Next.js — see §1.
- Changing the trading strategy or the risk gate. P10 changes *inputs*.
- Alt-coin expansion. BTC first, ETH second, nothing else.
- Social-platform scraping (unchanged, per `ROADMAP_AGENT_REACH_UPGRADE.md` §5).

---

## 12. Reference

- Binance public market-data REST + WebSocket (no credentials needed
  for public data; documented rate/connection limits).
- Bybit V5: klines (spot/USDT/USDC/inverse), index & mark klines,
  funding history, open interest, order book, trades; WS public
  streams with snapshot + incremental deltas.
- Coinbase Advanced Trade REST/WS — optional third reference price,
  deprioritised behind Binance + Bybit for a BTC-futures focus.
- TradingView Lightweight Charts — Apache-2.0, standalone build,
  streams custom data.

**Rate-limit reality:** "free public API" ≠ unlimited. Backfill once,
store locally, maintain incrementally. That constraint is precisely
why owning the data matters.
