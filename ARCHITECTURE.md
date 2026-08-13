# ARCHITECTURE.md — CryptoBrain / SKY

> **Purpose:** the module map + invariants a new Arena session reads
> to understand the codebase without re-deriving it. Companion to
> `SESSION_STATE.md` (current state) and `TODO.md` (next work).
> **Update when:** the module map or the invariants change.
> **Read when:** starting work on a module you haven't touched in
> ≥1 session.

**Last updated:** 2026-08-13
**Stack:** Python 3.10+, Flask 3, SQLite, stdlib JSON-RPC MCP server.
**Single-process, single-user, single-machine.**
**Version:** `config.VERSION` = `2.8.0` (also `pyproject.toml`).

---

## Module map (one-line each)

### Top level
| File | Purpose |
|---|---|
| `main.py` | argparse CLI dispatcher (~30 `cmd_*` subcommands) |
| `config.py` | Env-driven config; `VERSION = "2.8.0"`; exports `SYMBOL`, `SYMBOLS`, `TIMEFRAME`, risk caps, progression ladder |
| `mcp_server.py` | Zero-dep stdio JSON-RPC 2.0 MCP server (read-only tool permission map) |
| `SKILL.md` | Agent-facing skill file (the one AI agents read first) |
| `SESSION_STATE.md` | Handoff memory between Arena sessions |
| `TODO.md` | Prioritised remaining work |
| `ARCHITECTURE.md` | This file |
| `CHANGELOG.md` | What shipped, when (current through v2.8.0) |
| `BLUEPRINT.md` | The 4-step path from paper to real capital |
| `PROFESSIONAL_PLAN_DECISIONS.md` | The 18-phase professional plan + D-list |
| `ROADMAP_AGENT_REACH_UPGRADE.md` | The P7/P8/P9 Agent-Reach-inspired plan |
| `MERGE_NOTES.md` | Provenance of the Cloudslover + cloudshome merge |
| `AI_ANATOMY_ROADMAP.md` | Live status of P1–P12 |
| `docs/FREQTRADE_REVIEW.md` | **F1–F8** — Freqtrade rejected; P12 is our validation engine |
| `docs/BACKTRADER_REVIEW.md` | **BT1–BT8** — Backtrader rejected as dependency/grader; P12 definitions extended |

### `brain/` — the desk brain
| Module | Purpose | Used by |
|---|---|---|
| `agent.py` | `health_report`, `format_health`, `desk_status`, `format_desk_status`, `readiness_strip`, `format_readiness_strip` | `cmd_health`, `cmd_desk`, `cmd_doctor`, MCP `desk_status` / `readiness`, `/api/desk`, `/api/readiness` |
| `agents.py` | Autonomous desk agents (morning, watchdog, paper-reviewer, weekly-review), audit-logged to `agent_runs` | `cmd_agent` |
| `analytics.py` | MAE/MFE summary, Monte Carlo equity/drawdown | `hidden analytics mae/mc` |
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
| `journal.py` | Professional trading journal | `cmd_journal` |
| `library.py` | RAG knowledge index | `ask` |
| `metrics.py` | Win-rate, expectancy, profit factor, drawdown, streaks | `agents`, `metrics` |
| `playbooks.py` | Per-asset playbooks (BTC / ETH / GOLD) | `library`, `ask` |
| `portfolio.py` | Portfolio-level risk (BTC+ETH = one bucket) | `intelligence` |
| `risk_gate.py` | **The gate.** Kelly-advisory, daily/weekly stop, progression ladder | `cmd_approve`, `cmd_risk` |
| `state_memory.py` | 8D state fingerprint + historical similarity | `cmd_state` |
| `styles.py` | Scalp/Day/Swing/Momentum/Position style routing | `analyze_full` |
| `trading_intelligence.py` | The institutional desk report | `cmd_intelligence`, `cmd_card` |

### `data/` — sources + persistence
| Module | Purpose |
|---|---|
| `binance_client.py` | Public market data (OHLCV spot + perp, funding, OI, L/S, liq) with geo-friendly fallbacks |
| `sample_client.py` | Offline deterministic synthetic data (DEMO_MODE=1) |
| `store.py` | P10.1 — normalised `Candle` schema + partitioned Parquet store (upsert PK, unclosed-candle rule) |
| `backfill.py` | P10.2 — paginated, resumable, rate-limit-aware backfill into the store (hardened: real perp endpoint, weight-header pacing, geo-block abort); `python main.py backfill` |
| `gaps.py` | P10.3 — gap detection + repair + 1m→5m/15m/1h/4h/1d rollups (`--repair` / `--rollup`) |
| `derivatives.py` | P10.4 — funding / OI / mark / index / basis as stored time series; `python main.py derivatives` |
| `quality.py` | P10.5 — per-series data-quality pillar (staleness, gaps, price/volume sanity); corrupt data quarantines the desk via `readiness_strip` |
| `bybit_client.py` | P10.6 — Bybit V5 klines transport behind the same `PageResult` contract; P10.7 also pages `/v5/market/funding/history`. Venue quirks stay at the boundary. |
| `cross_exchange.py` | P10.7 — venue registry + one `snapshot_prices()` probe + stored premium/discount + funding spread; `python main.py cross collect\|status` |
| `database.py` | SQLite schema (scans, plans, backtest_results, paper_trades, agent_runs, journal_entries, trader_state); `SignalDB` context manager |
| `backtester.py` | Walk-forward grading of plans at +1h/+4h/+24h |
| `paper_trading.py` | Approved-signal lifecycle: monitor + auto-close at SL/TP1 (no real orders) |
| `simulator.py` | The paper-sample grind (100/20 sample proof); `graduation_status` |
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
| `hidden_alpha.py` | Markov-smoothed HMM regimes, CVD order flow, Bayesian Kelly, 8D fingerprint + similarity search |
| `correlation.py` | Measured BTC/ETH/GOLD rolling correlation + ETH/BTC beta |
| `calibration_hook.py` | Plugs the `brain/calibrator` into the engine output |

### `output/` — rendering + delivery
| Module | Purpose |
|---|---|
| `signal_schema.py` | The exact JSON contract (`signal_id`, `timestamp`, `asset`, `action`, `entry`, `stop_loss`, `take_profit`, `risk_reward`, `confidence`, `timeframe`, `reason`) + `validate_output` |
| `notifiers.py` | Telegram + Discord webhook push |

### `web/` — Flask dashboard
| Module | Purpose |
|---|---|
| `app.py` | Flask app factory `make_app()`, all `/api/*` routes, `serve()` runner |

### `tests/` — 48 test modules, 471 pass / 1 skip
- Most modules have a matching `test_*.py`.
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
- `wheel-gate-job.yml` — job spec a human pastes into
  `.github/workflows/ci.yml` (TODO-7).

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

7. **Tests must stay ≥ 471 pass / 1 skip.** The 1 skip is the
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

The expected baseline is **471 pass, 1 skip**. Any new feature must
maintain or increase this count.
