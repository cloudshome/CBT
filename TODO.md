# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-12 (TODO-12/P10 started — **P10.1 shipped**: normalised Candle schema + Parquet store)

---

## 🔁 Session rhythm (how we work)

We go session by session. Each Arena session is one self-contained
unit of work that ends in a reviewable PR:

```text
1. Read SESSION_STATE.md → TODO.md → the relevant docs
2. Pick the top unblocked item
3. Implement it; keep the suite green (≥ 339 pass / 1 skip)
4. Reconcile SESSION_STATE.md + TODO.md + CHANGELOG.md (full pass)
5. Commit + push to the session branch
6. Open ONE PR as the closing step  ← Arena allows one PR per session
7. A human reviews and merges; the next session branches from main
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
| **Data independence** | Our own stored market history | ❌ **P10** |

Everything below is ordered by how directly it moves those two lines.
Anything that moves neither is out of scope.

---

## 🔥 Top priority — start here in the next session

> **Order note (2026-08-12):** the active major milestone is now **P10**
> and its first step shipped. The paper book (TODO-11) first-grind is
> done; what remains there is ongoing data collection/grinding that can
> run alongside P10. P10.2 is the concrete next build below.

### TODO-12 / P10.2 · Binance backfill · the next P10 milestone

**P10.1 (schema + store) is shipped.** Next milestone from the roadmap:
**P10.2 — Binance paginated REST backfill** — reuse `data/binance_client.py`
as the transport, page through 1m history (resumable, rate-limit aware),
write via `CandleStore.write()`/`normalise_klines()`. Done when 1m
BTCUSDT perp history is on disk under `data/store/**` and a re-run adds
**zero** rows (idempotent upsert). Full plan: `docs/DATA_INFRASTRUCTURE_ROADMAP.md`.

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

### TODO-12 · P10 · Data infrastructure + market terminal · the next MAJOR milestone

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

Twelve independently shippable milestones (P10.1 → P10.12). **P10.1 is
shipped** (this session). Do not start milestone N+1 until N is green.

| # | Milestone | Status |
|---|---|---|
| P10.1 | Normalised `Candle` schema + Parquet store + upsert PK | ✅ shipped (`data/store.py`) |
| P10.2 | Binance paginated REST backfill (resumable, rate-limit aware) | ⏭ **next** |
| P10.3 | Gap detection + repair + 1m→higher-TF aggregation | ⏳ |
| P10.4 | Derivatives as time series (funding / OI / mark / index / basis) | ⏳ |
| P10.5 | Data-quality pillar wired into `readiness_strip()` | ⏳ |
| P10.6 | Bybit adapter behind the same schema | ⏳ |
| P10.7 | Cross-exchange premium/discount + funding spread | ⏳ |
| P10.8 | Lightweight Charts replaces `chartSVG()` | ⏳ |
| P10.9 | OI / funding / CVD panes | ⏳ |
| P10.10 | WebSocket tier (live klines + liquidations) | ⏳ |
| P10.11 | Backtester reads the store, not a live fetch | ⏳ |
| P10.12 | Feature store — one wide row per timestamp | ⏳ |

**Phase done when** we can ask *"how did this setup perform when price
rose, OI rose, funding was negative, and CVD was positive?"* and get a
number computed from our own data.

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
- **Reuse `_cross_exchange_probe()`.** Cross-exchange comparison
  already exists in `brain/agent.py`; generalise it, don't write a
  second one.
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

### TODO-9 · Dify as a *separate* research layer · AFTER graduation + P10

Not a SKY dependency. Deploy Dify elsewhere and point it at SKY's
read-only surfaces (`desk`, `readiness`, `ask`, MCP). Start only when
`python main.py agent ask "am i ready for micro?"` reports READY.

### TODO-10 · LibreChat-style chat UI · AFTER TODO-9

Not a SKY dependency. The dashboard already exists. Only if a
multi-model chat panel is still wanted after Dify.

---

## ✅ Done this session (2026-08-12 · `arena/019ff579-sky`)

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

**Next (P10.2):** Binance paginated REST backfill reusing
`data/binance_client.py`, resumable + rate-limit aware, writing via
`CandleStore.write()`.

---

### TODO-1.bis · combined dashboard doctor strip · ✅ DONE (prior session)

One readiness verdict across channels + immune system + risk gate,
rolled up **worst-first** (`ok → degraded → blocked → down`).

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

D1–D5 are already recorded. Do **not** start TODO-9/TODO-10 this
session or the next.

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
