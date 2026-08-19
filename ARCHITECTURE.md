# ARCHITECTURE.md — CryptoBrain / SKY

> **Purpose:** the module map + invariants a new Arena session reads
> to understand the codebase without re-deriving it. Companion to
> `SESSION_STATE.md` (current state) and `TODO.md` (next work).
> **Update when:** the module map or the invariants change.
> **Read when:** starting work on a module you haven't touched in
> ≥1 session.

**Last updated:** 2026-08-17
**Stack:** Python 3.10+, Flask 3, SQLite, stdlib JSON-RPC MCP server.
**Current runtime:** single-user and one authoritative machine; Gunicorn plus
separate supervised scan/paper workers are supported on Ubuntu.
**Version:** `config.VERSION` = `2.29.2` (also `pyproject.toml`).

---

## Production distribution direction (P18–P22)

[`ROADMAP.md`](ROADMAP.md) is the active merged roadmap. The target topology is
one Ubuntu SKY Hub owning the database, market workers, evidence, risk gate,
and audit history. Browser/PWA, Windows `.exe`, and Android `.apk` are clients
of a secured, versioned API—not independent trading engines.

This topology is a **plan, not a current capability**. Before any remote/native
client ships, P18 must add authentication/roles, CSRF and revocable device
tokens, `/api/v1` compatibility, idempotent mutations, and persisted jobs/SSE.
Remote access requires HTTPS. No package or client adds live exchange-order
code or weakens server-side risk enforcement.

---

## Module map (one-line each)

### Top level
| File | Purpose |
|---|---|
| `main.py` | argparse CLI dispatcher (~30 `cmd_*` subcommands) |
| `config.py` | Env-driven config; `VERSION = "2.27.0"`; exports `SYMBOL`, `SYMBOLS`, `TIMEFRAME`, risk caps, progression ladder |
| `mcp_server.py` | Zero-dep stdio JSON-RPC 2.0 MCP server (read-only tool permission map) |
| `SKILL.md` | Agent-facing skill file (the one AI agents read first) |
| `SESSION_STATE.md` | Handoff memory between Arena sessions |
| `TODO.md` | Prioritised remaining work |
| `ARCHITECTURE.md` | This file |
| `ROADMAP.md` | Canonical merged P1–P22 product roadmap; production install/security/distribution source of truth |
| `CHANGELOG.md` | What shipped, when |
| `BLUEPRINT.md` | The 4-step path from paper to real capital |
| `PROFESSIONAL_PLAN_DECISIONS.md` | The 18-phase professional plan + D-list |
| `ROADMAP_AGENT_REACH_UPGRADE.md` | The P7/P8/P9 Agent-Reach-inspired plan |
| `MERGE_NOTES.md` | Provenance of the Cloudslover + cloudshome merge |
| `AI_ANATOMY_ROADMAP.md` | Live status of P1–P12 |
| `docs/FREQTRADE_REVIEW.md` | **F1–F8** — Freqtrade rejected; P12 is our validation engine |
| `docs/BACKTRADER_REVIEW.md` | **BT1–BT8** — Backtrader rejected as dependency/grader; P12 definitions extended |
| `docs/NEEDLE_REVIEW.md` | **N1–N8** — Needle 2 parked as a conditional external read-only MCP client; not a brain or authority |

### `brain/` — the desk brain
| Module | Purpose | Used by |
|---|---|---|
| `agent.py` | `health_report`, `format_health`, `desk_status`, `format_desk_status`, `readiness_strip`, `format_readiness_strip`, `loop_health`, `format_loop_health` | `cmd_health`, `cmd_desk`, `cmd_daily`, `cmd_doctor`, MCP `desk_status` / `readiness` / `loop_health`, `/api/desk`, `/api/readiness`, `/api/loop-health` |
| `agents.py` | Autonomous desk agents (morning, watchdog, paper-reviewer, weekly-review), audit-logged to `agent_runs` | `cmd_agent` |
| `analytics.py` | MAE/MFE summary, Monte Carlo equity/drawdown over the canonical live book (P12.15) | `hidden analytics mae/mc` |
| `ask.py` | RAG query with grounded citations | `cmd_ask`, MCP `ask` |
| `brief.py` | Cross-asset morning brief + post-trade reviews | `cmd_brief`, `cmd_postreview`, `cmd_agent morning` |
| `calibrator.py` | Self-improvement profile from graded backtests | `cmd_learn` |
| `channels.py` | **P8** ordered-backend router for cryptodada / discord / news / llm | `cmd_doctor`, `cmd_channels`, `readiness_strip` |
| `coach.py` | Why-the-engine-said-what teaching mode | `cmd_coach` |
| `context.py` | Macro, FOMC/CPI/NFP, fear&greed, BTC dominance, equities | `analyze_full` |
| `decision.py` | BUY/SELL/NO_TRADE decision logic | `analyze_full` |
| `full_pipeline.py` | The end-to-end analysis pipeline | `cmd_scan`, `cmd_intelligence` |
| `immune.py` | Staleness, DB integrity, risk gates, behavioral flags, calibration drift | `cmd_health`, `cmd_doctor`, `readiness_strip` |
| `institutional_score.py` | Institutional desk-style scoring | `intelligence` |
| `journal.py` | Professional trading journal + `graduation_discipline()` + `live_execution_stats()` (P12.14/P12.15) | `cmd_journal`, business scorecard |
| `library.py` | RAG knowledge index | `ask` |
| `metrics.py` | Win-rate, expectancy, profit factor, drawdown, streaks and source-correct execution discipline over the canonical live book (P12.15) | `agents`, `metrics` |
| `playbooks.py` | Per-asset playbooks (BTC / ETH / GOLD) | `library`, `ask` |
| `portfolio.py` | Portfolio-level risk (BTC+ETH = one bucket) | `intelligence` |
| `risk_gate.py` | **The gate.** Canonical-live Kelly advisory, daily/weekly stop, drawdown ladder, progression | `cmd_approve`, `cmd_risk` |
| `ritual.py` | **W3.2** daily ritual with memory — four canonical steps + per-day persisted ticks (`ritual_checks`) | `/api/ritual`, Review tab |
| `state_memory.py` | 8D state fingerprint + historical similarity | `cmd_state` |
| `styles.py` | Scalp/Day/Swing/Momentum/Position style routing | `analyze_full` |
| `trading_intelligence.py` | The institutional desk report | `cmd_intelligence`, `cmd_card` |
| `weekly.py` | **W3** weekly trader review — week vs all-time (NET), R-distribution, violations + mistakes, graduation tracker, `missing_journals()` journal-first gate, next practice task, advisory grade | `cmd_weekly`, `/api/weekly`, MCP `weekly_review`, Review tab, `WeeklyReviewAgent` |
| `practice.py` | **W3.4** practice mode — freeze the desk read at commit time, score the trader's read deterministically (bias/call/ladder components, renorm without ladder, A–E grade), calibration scorecard. Coaching memory ONLY: no live/gate/graduation surface reads it | `cmd_practice`, `GET/POST /api/practice`, MCP `practice_scorecard`, Chart + Review tabs |

### `data/` — sources + persistence
| Module | Purpose |
|---|---|
| `binance_client.py` | Public market data (OHLCV spot + perp, funding, OI, L/S, liq) with geo-friendly fallbacks |
| `sample_client.py` | Offline deterministic synthetic data (DEMO_MODE=1) |
| `store.py` | P10.1 — normalised `Candle` schema + partitioned Parquet store (upsert PK, unclosed-candle rule); P12.3.2 — `StoreClient` klines-shaped reader so offline walkers run on stored real candles |
| `backfill.py` | P10.2 — paginated, resumable, rate-limit-aware backfill into the store (hardened: real perp endpoint, weight-header pacing, geo-block abort); P12.3.2 — `backfill_from_csv` offline CSV import (same adapter boundary, sha256 provenance pin); `python main.py backfill [--from-csv PATH]` |
| `gaps.py` | P10.3 — gap detection + repair + 1m→5m/15m/1h/4h/1d rollups (`--repair` / `--rollup`); `detect_gaps(..., calendar)` skips scheduled closures (P12.9) |
| `derivatives.py` | P10.4 — funding / OI / mark / index / basis as stored time series; `python main.py derivatives` |
| `quality.py` | P10.5 — per-series data-quality pillar (staleness, gaps, price/volume sanity); corrupt data quarantines the desk via `readiness_strip`. P12.9: calendar-aware — a session venue is judged in trading time |
| `calendar.py` | **P12.9** — venue trading calendars (`crypto-24x7` always open; `xau-otc` the DST-aware OTC gold week). `calendar_for()` opts in by venue only; scheduled closure stops counting as missing data |
| `bybit_client.py` | P10.6 — Bybit V5 klines transport behind the same `PageResult` contract; P10.7 also pages `/v5/market/funding/history`. Venue quirks stay at the boundary. |
| `cross_exchange.py` | P10.7 — venue registry + one `snapshot_prices()` probe + stored premium/discount + funding spread; `python main.py cross collect\|status` |
| `costs.py` | P12.6 — fees-first trade cost modeling (`E_net = E_gross − fees − slip − funding`, funding joined as-of-T) |
| `scorecard.py` | P12.3/P12.6 — boxed strategy scorecard reporting gross + net metrics, Sharpe/Sortino/Calmar, holding time, split by side/regime/session/setup/conditions |
| `quality_score.py` | P12.4 — Backtest Quality Score 0–100 (edge / curve robustness / sample confidence / BT5 parameter-plateau with isolated-peak cap at 50); `python main.py quality` store sweep |
| `strategy_score.py` | P12.5 — strategy score on the calibrator: `E_R × sample-quality × regime-fit × execution` (weighted geometric mean, NET of costs), `multiplier_from_score()` trust dial |
| `database.py` | SQLite schema (scans, plans, backtest_results, paper_trades, agent_runs, journal_entries, trader_state, ritual_checks W3.2, practice_attempts W3.4 — coaching memory, never joined into the live book); `SignalDB.live_book_rows()` defines the P12.15 live (closed) book and `SignalDB.live_open_rows()` the P12.16 live open book |
| `backtester.py` | Walk-forward grading of plans at +1h/+4h/+24h; P10.11 `run_backtest_on_store()` reads the Parquet store instead of a live fetch |
| `paper_trading.py` | Approved-signal lifecycle: monitor + auto-close at SL/TP1 (no real orders) |
| `ws_client.py` | P10.10 — public Binance WebSocket streams (`!forceOrder@arr` + klines) with reconnect/backoff; offline-safe demo stream; feeds readiness + feature store |
| `feature_store.py` | P10.12 — one derived wide row per `(symbol, timeframe, ts)`: price + derivatives + hidden_alpha + regime (22 columns) |
| `validation.py` | P12.1 locked train/val/OOS/recent protocol + sealed OOS envelope; P12.2 AST guard rejects negative `shift(-n)` feature code; `python main.py validate [lookahead]` |
| `provenance.py` | P12.11 source-series identity for graded rows and calibration keys; canonical live rows remain backward-compatible while one-sided imports stay unreachable from live calibration |
| `gold_basis.py` | P12.12 read-only exact-time PAXGUSDT/XAUUSD basis measurement + current sealed-OOS inspection; always reports XAU research-only and leaves human approval open; `python main.py xau-evidence` |
| `simulator.py` | The paper-sample grind (100/20 sample proof); canonical-live-only `paper_progress`, fail-closed `graduation_status` (discipline payload from `brain.journal`) |
| `symbols.py` | Alias resolution (BTC → BTCUSDT, ETH → ETHUSDT, GOLD → XAUUSD) |
| `sources/cryptodada_website.py` | Connector for the private CryptoDada site (api/browser modes) |
| `sources/discord_reader.py` | Connector for the private Discord group (read + webhook push) |
| `sources/news.py` | RSS headlines from CoinTelegraph / CoinDesk / Decrypt + naive sentiment |

### `engine/` — quant layer
| Module | Purpose |
|---|---|
| `indicators.py` | RSI, MACD, EMA/SMA stack, Supertrend, ADX, Stochastic, WaveTrend, Bollinger, ATR, ROC, VWAP, POC, OBV, volume spike |
| `structure.py` | Fractal swings, BOS/CHOCH, order blocks, FVGs, liquidity sweeps, equal highs/lows, premium/discount |
| `features.py` | Labeled market snapshot (HTF bias, LTF setup, alignment score) |
| `scorer.py` | Weighted condition scoring (Trend +15, Structure +15, OB/FVG +20, Liquidity +15, Volume +10, Divergence +10, Momentum +10, Location +5 = 100) → HIGH/MEDIUM/LOW/NO TRADE |
| `rules.py` | IF/THEN conditional plans (pullback / breakout / sweep-reversal / FVG retest) |
| `signal_engine.py` | Final signal JSON + best signal selection |
| `regime.py` | Volatility / trend regime classification |
| `mtf.py` | Multi-timeframe (Monthly → 1M) alignment |
| `lifecycle.py` | Signal status transitions (CREATED → PENDING_REVIEW → APPROVED → EXECUTED → CLOSED) |
| `execution.py` | Realistic spread/slippage execution model (`EXECUTION_MODEL=simple`) |
| `hidden_alpha.py` | Markov-smoothed HMM regimes, CVD order flow, Bayesian Kelly, 8D fingerprint + similarity search; `kelly_from_rows()` for P12.15 |
| `correlation.py` | Measured BTC/ETH/GOLD rolling correlation + ETH/BTC beta |
| `calibration_hook.py` | Plugs the `brain/calibrator` into the engine output |

### `output/` — rendering + delivery
| Module | Purpose |
|---|---|
| `signal_schema.py` | The exact JSON contract (`signal_id`, `timestamp`, `asset`, `action`, `entry`, `stop_loss`, `take_profit`, `risk_reward`, `confidence`, `timeframe`, `reason`) + `validate_output` |
| `notifiers.py` | Telegram + Discord webhook push |

### `web/` — Flask dashboard + client API
| Module | Purpose |
|---|---|
| `app.py` | Flask app factory `make_app()`, all `/api/*` and `/api/v1/*` routes, `serve()` runner |
| `auth.py` | **P18.1** owner account, `viewer`/`operator` roles, cookie sessions, scoped device tokens, CSRF, login throttling, audit, remote-deployment guard |
| `api_v1.py` | **P18.2** the stable client contract: response envelope, typed `ErrorCode` vocabulary, version negotiation, `IdempotencyStore`, and the declared route table |
| `command_center.py` | Allow-listed CLI catalog behind `/api/commands` |
| `position_sizer.py` | Position-size calculator bounded by the risk gate |
| `chart_data.py` | Chart payload: candles, overlays, panes, levels |

**The `/api/v1` boundary (P18.2).** Two API surfaces coexist deliberately:

* `/api/*` — the original endpoints. Shapes are historical and inconsistent
  (some bare payloads, some `{ok, error}`, some 200-with-a-failure). The
  shipped dashboard uses these, and they are frozen so it cannot break.
* `/api/v1/*` — the contract for *external* clients (PWA, Windows, Android).
  Every response is `{ok, data, error{code,message,details}, meta}`.

Each delegating v1 route calls the **same view function** the legacy route
uses and re-renders the result. This is the load-bearing design decision: v1
is a contract, not a second implementation, so it cannot drift from the
dashboard's behaviour, cannot acquire its own bugs, and cannot need its own
security review. `tests/test_api_v1.py` enforces that every v1 route maps to a
legacy route that already existed.

Authorization for v1 mutations is read from `api_v1.ROUTES`, so the enforced
policy and the catalog published at `/api/v1/routes` cannot disagree; an
undeclared mutating route defaults to `operator` (fails closed).

### `tests/` — 61 test modules, 750 pass / 1 skip
- Most modules have a matching `test_*.py`.
- `tests/test_calendar.py` — **NEW (P12.9)** gold-week boundaries + DST, holidays, trading-time counting,
  calendar-aware gaps/quality, Dukascopy import gap report, `calendar` CLI.
- `tests/test_costs.py` — **NEW (P12.6)** fee scaling, spread, funding direction, net R conversion.
- `tests/test_scorecard.py` — P12.3 scorecard + P12.6 net-of-costs & conditioned splits.
- `tests/test_web_api.py` — Flask endpoint regression tests (catches the
  `_sanitize_for_json` numpy-bool-500 bug fixed in the consolidated
  build per `MERGE_NOTES.md`).
- `tests/test_mcp_stdio.py` — Root MCP server handshake, tool
  permission map, trader-state round-trip, health check.
- `tests/test_channels.py` — P8 channels router + SKILL.md content
  contract + CLI subcommands (`doctor` / `channels` / `skill` / `desk`).
- `tests/test_wheel_gate.py` — **NEW (P9)** pyproject + `import cryptobrain`
  + duplicate-entry detection + `main(argv)` contract.

### `docs/`
- `agent_install.md` — **NEW (P7)** the one-pager an agent fetches when
  told "install CryptoBrain."
- `INFRASTRUCTURE_LAYERS.md` — OpenHands / Dify / LibreChat / **Freqtrade**
  / **Backtrader** vs SKY. Study only; never vendor. Freqtrade never;
  Backtrader never (not even as an “optional research engine”). Dify
  after graduation *and* P10; LibreChat last.
- `DATA_INFRASTRUCTURE_ROADMAP.md` — **P10**, the next major
  milestone: own the market data (normalised schema → Parquet store →
  Binance/Bybit backfill (✅ P10.6) → derivatives series → quality pillar (✅ P10.5) →
  Lightweight Charts terminal → WebSocket tier → feature store).
  12 shippable milestones. Read it in full before writing any P10 code.
- `FREQTRADE_REVIEW.md` — 2026-08-13 audit of a “use Freqtrade as
  the execution + backtest layer” recommendation. Verdict: reject the
  bot, keep the research-integrity ideas as P12 on our stack.
- `BACKTRADER_REVIEW.md` — 2026-08-13 audit of a “mine Backtrader as
  research architecture / put it behind an adapter” recommendation.
  Verdict: reject the dependency and the second grader; the good
  ideas were already ours or already P12 — definitions extended
  (BT1–BT8).
- `PATH_TO_REAL_MONEY.md` — 2026-08-14 audit: real market data before P12.4, fees-first P12.6, net bar.
- `REAL_DATA_RUN_2026-08-14.md` — first real BTCUSDT 1m imported and re-run.
- `DUKASCOPY_XAU_ADAPTER.md` / `SOURCE_PROVENANCE.md` — external XAU import and source-separated learning contract.
- `XAU_PROMOTION_EVIDENCE.md` — P12.12 real-host procedure, exact-time basis contract, and still-open promotion gates.
- `HANDOVER_2026-08-16_P12_15_1.md` — P12.15 follow-up: live execution-metric source isolation.
- `.github/workflows/ci.yml` — active offline-suite and wheel-gate jobs;
  both passed on merged P12.15 (`main`; later runs may use the same two-job contract).

---

## Invariants (do NOT break these)

1. **The engine never places a real exchange order.** Enforced in
   `mcp_server.handle_tool_call()` (no `approve | reject | execute |
   close | place_order` tool in `ALLOWED_TOOLS`) and in
   `data/paper_trading.py` (paper-only). The human-approval gate is
   mandatory and is enforced on every approval via
   `brain.risk_gate.evaluate_risk_gate`.

2. **MCP `tools/list` is a permission map, not a feature list.** Adding
   a tool = expanding what the agent can do. New tools must be
   read-only. Mutation paths go through the CLI / dashboard only.

3. **The risk gate is consulted on every approval.** Even if an agent
   fabricates a signal, `brain/risk_gate.evaluate_risk_gate` blocks
   approval when daily/weekly loss limits are reached, when
   `trader_state` shows behavioral flags, or when the progression
   ladder is at `student` / `researcher`.

4. **BTC + ETH = one correlated crypto-risk bucket.** Enforced in
   `brain/portfolio.py` and verified by
   `python main.py correlation`. The `engine/correlation.py` module
   measures the actual rolling correlation and reports whether the
   bucket rule is being honoured.

5. **The `ask` tool must always produce a citation.** Every answer
   carries `[cited: ...]` markers (enforced in `brain/ask.py`). This
   is the only way the operator can verify the engine's reasoning.

6. **The default install/setup is non-mutating.** Mirrors
   Agent-Reach's safety posture. `python main.py doctor`,
   `python main.py channels`, `python main.py skill --print` are all
   read-only. `python main.py skill --install` requires
   `--system` to write under `$HOME`.

7. **Tests must stay ≥ 750 pass / 1 skip.** The 1 skip is the
   SDK-already-installed fallback (pre-existing, per `MERGE_NOTES.md`).
   Any new feature must add at least as many tests as it adds source
   lines of complexity (rule of thumb: ≥ 1 test per non-trivial
   branch).

8. **Commits are checkpoints.** Every commit is a safe point a future
   Arena session can roll back to. Don't bundle unrelated changes
   into one commit.

9. **SESSION_STATE.md is updated at the end of every session.**
   See "End-of-session checklist" in SESSION_STATE.md.

10. **One computation, many surfaces.** A verdict the operator can
    read (readiness, desk advice, doctor, channels) is computed **once**
    in `brain/` and rendered by the CLI, `/api/*`, MCP, and the
    dashboard. No surface may compute its own version — that is how
    two screens start disagreeing about whether it is safe to trade.
    `brain.agent.readiness_strip()` is the reference example: CLI
    `doctor --strip`, `GET /api/readiness`, and MCP `readiness` all
    return the exact same payload.

11. **No web scraping of social platforms.** Out of scope per
    `ROADMAP_AGENT_REACH_UPGRADE.md` §5. Don't add dependencies on
    `browser-cookie3`, `playwright` (only for the CryptoDada
    connector, which already exists), `yt-dlp`, `ffmpeg`, or any
    Twitter/Reddit/Bilibili/Xiaohongshu/Facebook/Instagram/LinkedIn
    API/CLI.

12. **Stored history is immutable, closed-candle-only, and
    normalised at one boundary.** Every persisted candle passes
    through `data/store.py::normalise_klines()` (UTC epoch-ms OPEN
    times, upsert PK `(exchange, market, symbol, timeframe, ts)`);
    a still-forming candle (`ts + step > end boundary`) is never
    persisted — the P10.2 backfill drops it before the store sees
    it, and the store itself refuses `closed=False`. Market data
    collectors are read-only public endpoints: no keys, no signed
    requests, ever.

13. **SKY is the brain. SKY is not a trading bot.** Do not add
    Freqtrade, Hyperopt, FreqAI, or any exchange-order framework
    (`docs/FREQTRADE_REVIEW.md`, F1–F3). **SKY is also not a
    Backtrader host.** Do not add `backtrader` — dependency, dev
    tool, vendored copy, or adapter — and do not add a second
    backtest engine “for cross-validation”
    (`docs/BACKTRADER_REVIEW.md`, BT1–BT4/BT7). The strategy runtime is
    `engine/rules.py` + `engine/signal_engine.py`. The backtester is
    `data/backtester.py`. Live execution, if it ever exists, is a
    SKY-owned thin adapter *after* the graduation gate — never a
    third-party strategy runtime. Do not expand the strategy catalog
    until the primary family (`sweep_trend_continuation`) clears the
    graduation bar (F4).

14. **A tool router is a client, not an authority.** Cactus Needle 2 is not
    part of SKY's runtime and must not be installed merely to duplicate the
    existing typed MCP boundary (`docs/NEEDLE_REVIEW.md`, N1–N8). If a real
    offline/privacy/edge-device constraint justifies a pilot, Needle may only
    be evaluated as an external read-only MCP client. Its confidence can
    choose call / clarify / escalate / abstain; it can never approve, mutate,
    open the risk gate, count toward graduation, or reach an exchange.

15. **XAU evidence is source-separated and cannot self-promote.** Dukascopy
    XAU and Binance PAXG histories are never concatenated; P12.12 joins exact
    timestamps only for a read-only basis report. A measured basis and a
    passing sealed-OOS envelope make a dossier eligible for human review, not
    tradeable. Explicit human approval and the repository-wide graduation gate
    remain mandatory; no evidence command can unlock micro-live.

16. **Graduation is canonical-live-only.** `paper_progress()` is a permission
    input, not a pooled research report: it counts only the canonical Binance
    spot source key (`""`), including legacy NULL rows. Non-canonical histories
    remain visible through source-filtered scorecards but can neither unlock
    nor block micro-live. `grind_verdict()` / `graduation_status()` fail closed
    when a caller explicitly supplies research-source progress.

17. **Graduation discipline is earned, never inherited.** The 90% compliance
    criterion reads one computation — `brain.journal.graduation_discipline()` —
    over decided, non-simulator (`sim_key IS NULL`), canonical-live paper
    trades only. A trade counts as journaled only when `followed_rules` is 0 or
    1, and compliance is `compliant / eligible`, so every missing or blank
    journal counts against the desk exactly like a violation and an empty book
    reads `None` (unproven, never a pass). Simulator grinds and research books
    cannot contribute. The general journal report (`violation_rate()`) is a
    separate, deliberately broader number for the scorecard and risk card, and
    must never be substituted back into the gate.

18. **Live risk controls are canonical-live-only.** `SignalDB.live_book_rows()`
    is the one population for daily/weekly loss limits, drawdown, Kelly,
    Monte-Carlo risk, MAE/MFE and business metrics: decided, non-simulator,
    canonical-live rows, with legacy NULL provenance retained. Research rows
    remain inspectable through explicit scorecard/source queries but cannot
    mask, deepen or otherwise move a live risk reading.

19. **Live exposure is canonical-live-only** (P12.16).
    `SignalDB.live_open_rows()` is the open-side twin of #18 and the one
    population for the portfolio veto, the correlated-bucket risk cap, the
    paper runner's polling set, the watchdog agent and every reported
    "open exposure" count: active (`WAITING_ENTRY`/`OPEN`), non-simulator,
    canonical-live, with legacy NULL provenance retained. A research import
    must not occupy a slot in the live risk bucket (that fails **closed** —
    refusing real trades), an interrupted simulator run must not leave orphans
    holding live risk, and the runner must never price a research row off the
    canonical live candle client. The approved-scan half of `open_exposure()`
    stays unfiltered: a scan awaiting enrolment has no provenance yet and is a
    live intention.

20. **The hard limits judge NET P&L** (P12.18). `data.costs.net_r_of_row()` is
    the single definition of a decided row's net R — stored `rr_net` when
    present, otherwise costs computed from the row's own levels, symbol and
    holding time. The daily/weekly loss limits, the drawdown ladder and the
    business scorecard all read it, because P12.8's rule ("a measurement only
    matters where something acts on it") applies most of all to the controls
    that stop the desk trading. The live paper runner writes `rr_achieved`
    only, so live rows are NULL-net and the compute-on-read path is the normal
    one, not an edge case. A **win is a net win**: a trade that cleared its
    target but not its fees is not a winner. Thresholds are unchanged — only
    the number compared against them is honest.

---

## Data flow (end-to-end)

```
Binance (or sample) OHLCV
   ↓
engine/indicators.py → RSI MACD EMA VWAP ADX ...
   ↓
engine/structure.py → BOS/CHOCH OB FVG liquidity
   ↓
engine/regime.py + engine/mtf.py → HTF bias + LTF setup
   ↓
engine/features.py → labeled market snapshot
   ↓
engine/scorer.py → weighted condition score
   ↓
engine/rules.py → IF/THEN conditional plans
   ↓
engine/signal_engine.py → final JSON signal
   ↓
brain/decision.py → BUY/SELL/NO_TRADE
   ↓
brain/risk_gate.py → open/closed + position size
   ↓
brain/trading_intelligence.py → institutional desk report
   ↓
   ┌──────────────┬──────────────┬──────────────┐
   ↓              ↓              ↓              ↓
CLI scan/    Dashboard       Notifier       DB (scans table)
intelligence (web/app.py)    (Telegram/     → PENDING_REVIEW
                             Discord)         → human approves
                                             → paper_trading.py monitors
                                             → auto-close at SL/TP1
                                             → brain/analytics.py grades
                                             → brain/calibrator.py learns
```

The MCP server (`mcp_server.py`) and the `ask` RAG layer
(`brain/ask.py` over `brain/library.py`) are read-only side-channels
into the same DB and engine — they never write.

---

## Configuration cheatsheet

The full env-var list is in `.env.example`. The most commonly
touched ones:

| Var | Default | Purpose |
|---|---|---|
| `DEMO_MODE` | `0` | `1` = offline deterministic data; `0` = live Binance |
| `SYMBOLS` | `BTCUSDT,ETHUSDT,XAUUSD` | Dashboard watchlist |
| `TIMEFRAME` | `15m` | Default scan timeframe |
| `BARS` | `500` | Default history length |
| `MIN_CONFIDENCE` | `55` | Raw plan confidence floor |
| `INTELLIGENCE_MIN_CONFIDENCE` | `80` | Desk report confidence floor (stricter) |
| `INTELLIGENCE_MIN_RR` | `2.0` | Desk report R:R floor |
| `MAX_RISK_PCT` | `1.0` | Hard ceiling risk per trade |
| `KELLY_MAX_RISK_PCT` | `0.5` | Kelly-advisory ceiling |
| `MAX_DAILY_LOSS_PCT` | `1.5` | Daily stop |
| `MAX_WEEKLY_LOSS_PCT` | `3.0` | Weekly stop |
| `PROGRESSION` | `student` | `student → researcher → simulator → micro → consistent → scale` |
| `DESK_DEFAULT` | `true` | Desk-first output (raw engine plans visible as research) |
| `EXECUTION_MODEL` | (unset) | `simple` = realistic spread/slippage in backtests |

---

## Testing cheatsheet

```bash
# Full suite, offline
DEMO_MODE=1 python -m pytest tests/ -q

# Just the new channels layer
DEMO_MODE=1 python -m pytest tests/test_channels.py -v

# Just the dashboard regression tests
DEMO_MODE=1 python -m pytest tests/test_web_api.py -v

# The MCP server round-trip
DEMO_MODE=1 python -m pytest tests/test_mcp_stdio.py -v

# One module in isolation
DEMO_MODE=1 python -m pytest tests/test_risk_gate.py -v

# Coverage (optional, requires pytest-cov)
DEMO_MODE=1 python -m pytest tests/ --cov=brain --cov=engine --cov=data
```

The expected baseline is **750 pass, 1 skip**. Any new feature must
maintain or increase this count.
