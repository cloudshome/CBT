# ChatGPT 6-Idea Triage — what SKY takes, parks, rejects (2026-08-18)

**Branch:** `arena/01a0135d-sky` · **Base:** `97725e7` (`v2.33.0` W2 live streaming+drawings)  
**Status:** advisory triage only. No code shipped, no threshold moved, no package added, no `requirements.txt` change.  
**Next code is still `P18.4 PWA`** per `ROADMAP.md:5` + `TODO.md` + `HANDOVER.md`. This file just stops the next session re-debating the same 6 external ideas.

> **If you are the next Arena session and the user forgot to mention this:** read this file + `SESSION_STATE.md##Next recommended action` + `HANDOVER.md` before coding. The decision below is *passed through* — do not re-install LMRing/OpenDataLoader/AirLLM, do not add new families/tools, continue `P18.4 -> P19 -> P11 real-paper grind`.

---

## 1. One-line scorecard for SKY (paper-first, single Hub, 5 deps, no live orders)

| # | Idea (as sent) | One-sentence | Value for SKY desk | Verdict | Where it would live *if* taken |
|---|---|---|---|---:|---|
| `*01` | **LMRing** Crypto/Trading deep dive | 50+ LLM jury votes `LONG/SHORT/NO TRADE` on same snapshot | ⭐ | **REJECT as engine** — model-comparison, not market data / backtester / execution | External prompt-lab only: `frozen feature_store row -> 4 models -> measure OOS net expectancy` |
| `*02` | **Personal desk 10 items** | `backup/init/notify/ritual/standby/scorecard/alert/block-out/autostart/confidence` | ⭐⭐⭐⭐ | **80% DONE, 20% = P18.4/P19** | `P18.4 PWA` (push/offline/compact ritual) + `P19 Ubuntu Hub` (`sky backup/restore/setup`, hardened systemd) |
| `*03` | **Evidence engine 5 layers** | `event log -> regime posterior -> families -> Bayesian edge -> OOS ledger + human overlay` | ⭐⭐⭐⭐⭐ | **ADOPT philosophy, DEFER code** | Already `P10+P12`. Remaining: `weekly OOS truth-ledger cron + regime posterior/stability` after `P19` |
| `*04` | **OpenDataLoader PDF** | `PDF -> Markdown/JSON/HTML + tables/bbox/OCR/hybrid -> research DB` | ⭐⭐ | **PARK outside venv** | Standalone `research_pdfs/` converter -> curated `yaml -> backtester` — `P23+` lab, not `P18.x` |
| `*05` | **AGENTS.md/CLAUDE.md + harness/sandbox/log** | `plugin + sandbox + append-only log + one CLAUDE.md` | ⭐⭐⭐ | **DONE** | `SKILL.md` *is* the compat entry, `mcp_server.py` deny list, `web/jobs.py` persisted jobs+SSE, `/api/v1` |
| `*06` | **AirLLM 671B on 4GB VRAM** | `layer-streaming: 70B~4GB, 405B~8GB, 671B~12GB via disk` | ⭐⭐ | **PARK as optional remote** | `ai/airllm_provider.py` behind `AIProvider` for `1H/4H` reasoning only — after graduation, never in fast loop |

**Rule that killed 4 of 6:** every trading hypothesis must survive `stored Parquet (P10) -> deterministic engine (scorer/rules) -> locked walk-forward + sealed OOS (P12.1) -> costs net (P12.6) -> regime split (P12.3) -> paper book (P11)` before a human sees it. Anything that invents the signal (LLM vote, PDF claim, giant model) without that pipeline is not evidence.

---

## 2. Why `*01` LMRing is not the edge

* Correct description in the prompt: *not* a trading platform/backtester. Good as **Strategy Jury**, terrible as **Strategy**.
* SKY already made the call: `ai/llm_brain.py` is *narrative* (off/openai/gemini/auto + rule-based fallback), `engine/scorer.py + engine/rules.py` is *decision*, `brain/risk_gate.py + data/validation.py` is *truth*. Sending every 15m candle to 4 billed APIs creates cost × leak × version-drift with no `expectancy` gain until proven.
* If you want the experiment, do it outside SKY: freeze a `data/feature_store.py` row (`regime`, `funding`, `OI`, `structure`, `hist expectancy +0.3R, n=1284`), ask 4 models for `{direction, confidence, expected_R, invalidation}` JSON, store it, later grade it like a paper trade. Compare `baseline vs baseline+consensus vs baseline+disagreement-filter` on **OOS net**. That is `P12` work, not product work.

## 3. `*02` — the 10 personal-desk wishes, mapped to SKY

| Prompt # | Wish | SKY today | Action |
|---|---|---|---|
| 1 | `backup --dest` | **Planned `P19` deliverable #5** `sky backup/restore` + `/var/lib/sky` + retention/rollback — no package yet by design | Take as `P19`, not now |
| 2 | `init / first-boot` | **Planned `P19 #4`** `sky setup` wizard + `python main.py backfill --repair --rollup` | Take as `P19` |
| 3 | `notify push` | `TELEGRAM/DISCORD_WEBHOOK` ships; `P18.4` adds PWA push abstraction (never cache `/api/*`) | Take as `P18.4` |
| 4 | `ritual journal` | **DONE** `brain/journal.py` + `python main.py daily` (`loop-health`) + `GET /api/loop-health` + dashboard `LOOP HEALTH` (`P14`) | Done |
| 5 | `TA lock-in / Desk Standby` | **DONE** `SIGNAL_COOLDOWN=30m + MAX_FLIPS=2/h + FLIP_PCT=0.8% + brain/state_memory.py + TRADER_STATE_BLOCK` | Done; `P18.4` can add a compact button |
| 6 | `weekly scorecard / paper equity` | **DONE** `data/scorecard.py + simulator + Monte Carlo + quality + GET /api/scorecard` | Done — needs *real canonical* `n` |
| 7 | `alert-on-approval / paper exit` | **DONE** `data/paper_trading.py` poll + webhook + `brain/agent.py::paper-reviewer` | Done; PWA deep-link in `P18.4` |
| 8 | `block-out calendar NO_TRADE_WINDOWS` | `GOLD_SESSION_MODE + data/calendar.py` + `TRADER_STATE_BLOCK` cover it | **Park** until after graduation |
| 9 | `systemd autostart` | **DONE** `ops/systemd/` `gunicorn + scan + paper` — hardening is `P19 #3` | Done -> harden in `P19` |
| 10 | `confidence mode: show ignored NO TRADE hit-rate` | **DONE** `graduation_discipline()` + `brain/coach.py::five_levels` `⚠️ desk says NO TRADE` | Done |

Add nothing new this week.

## 4. `*03` — the only idea that moves the desk, and why we mostly already have it

| `*03` layer | Prompt wants | SKY has | Still missing |
|---|---|---|---|
| L1 Total event log | immutable `{ts, regime, feature_vector 53 cols, engine_signal, human_decision, bias_flags, outcome_1h/4h/24h}` | `data/store.py` Parquet + `data/database.py` SQLite + `data/feature_store.py` wide row + `brain/journal.py` decisions | Just keep appending **canonical live** `binance/spot/BTCUSDT 15m` |
| L2 Regime as posterior | `{bull_exp:0.62, bear_corr:0.18, ...} + stability + flip` | `engine/regime.py` label + `engine/hidden_alpha.py` HMM + `data/derivatives.py` | Posterior distribution + entropy is `post-P19` upgrade |
| L3 Competing families | `ict_smc vs statistical/flow vs hybrid` weighted vote | **Intentionally one family** `PRIMARY_SETUP_FAMILY=sweep_trend_continuation` (`A1`) + `data/provenance.py` isolates | Don't add before primary clears `+0.50R/55%/PF1.5` on real paper (`F4`) |
| L4 Edge estimator | `E[R|features,regime]` with CI + shrinkage | `brain/calibrator.py` `CALIBRATE_MIN_N=100/20 + GAIN + 0.6-1.25x` + `data/costs.py net` + `N_eff` correction | Full Bayesian `mu/sigma/CI` after `n>500` real |
| L5 OOS truth ledger | `weekly refit -> apply to next 3w blind -> ledger` | `data/validation.py` locked `train/val/OOS/recent + shift(-n) lookahead guard` | `cron` automation is `P12.19` after `P19` |
| Bonus Human overlay | `E[R|approved] vs E[R|you rejected] + tired/angry` | `brain/metrics.py + graduation_discipline + business_metrics` | None — already a gate |

*` *03`§5 stolen by design:* shrinkage + `N_eff` + lagged OOS + plateau test (`BT5`) + `CI excludes 0` or no trade.

## 5. `*04` OpenDataLoader — good parser, wrong layer

**Good:** tables stay tables, `bbox/page` traceability, prompt-injection filters — `8.5/10` as research ingestion, `2/10` as trading system. Right architecture in prompt `§16/§24` is right: `raw_pdfs/ -> parsed/ -> normalized/ -> research_db/` -> `hypothesis -> YOUR backtester -> scorecard -> paper`.

**Why park for SKY:** edge comes from *your* collected `OHLCV+funding/OI/mark/basis + liquidations ws` (P10), not someone's `BTC report Jan-2024`. PDF claim `funding > X -> correction` without `walk-forward + regime + fees/slippage/funding OOS` is hindsight. Heavy dep `hybrid: TEDS 0.489->0.928` vs `~2-4GB RAM + 1-2GB disk + GPU optional` breaks the `pyarrow` `P10` budget and `5-dep` invariant for a pre-graduation desk. OCR `0.012% -> 0.12%` corrupts conclusions — needs `page+unit+date` validation gate the prompt describes, which is `P23` work.

**If you ever take it:** run it *outside* SKY venv pinned to a version, output `markdown/json + tables/`, curate into `docs/research/` + `brain/library.py` citations manually, each `RESEARCH_ID` with `UNTESTED->TESTING->FAILED/PROMISING->OOS->PAPER->CANDIDATE`. Keep `OpenDataLoader` out of `requirements.txt`.

## 6. `*05` Harness/CLAUDE.md — we shipped the portable version

Claim `Everything is a plugin + sealed car` is ElizaOS marketing; `AGENTS.md/CLAUDE.md + sandbox + replay` *are* real in harnesses (Grok Landlock/Seatbelt, agentkit sessions, claude-harness). Prompt's correction is right: one huge `CLAUDE.md` is not memory — progressive disclosure `small entry -> docs/` is the pattern.

SKY already follows it: `SKILL.md` (≤250L, per `ROADMAP_AGENT_REACH_UPGRADE.md`) points to `ARCHITECTURE.md/BLUEPRINT.md/ROADMAP.md/docs/*`, `mcp_server.py ALLOWED_TOOLS` is the deny list (`approve/reject/execute/place_order` never there), `/api/v1` is the portable contract (P18.2), `web/jobs.py` is the persisted `append-only` queue with `id: job:status` SSE replay, `ops/systemd/` is the topology. No `Needle` router — reviewed `docs/NEEDLE_REVIEW.md N1-8` and parked. Keep it.

## 7. `*06` AirLLM — local 671B is a research server, not a trading engine

**What it does:** `layer-wise streaming from storage -> VRAM` so `70B~4GB, 405B~8GB, 671B~12GB, Qwen3-235B~3GB` — trades VRAM for latency/disk I/O (`README: layers saved on disk`). Good for `1H/4H/Daily` reasoning, bad for `HFT/1m` (`§12-§13` in prompt).

**Why park for SKY:** SKY `ai/llm_brain.py` chose `requests`-only portability precisely so `GT 710` / Hub without GPU still runs rule-based narrative. Adding `torch/transformers/accelerate/safetensors` contradicts `pyproject.toml` `5 deps + no Docker` and `P10` already heavy with `pyarrow`. And `LLM -> BUY` skips `E[Pw*Win - Pl*Loss]` + `risk_gate.py (MAX_RISK 0.25-0.5%, MAX_DAILY 1-2%, MAX_OPEN 1%)` — golden rule `machine proposes, human approves, paper-runner executes`. AirLLM belongs as *optional* `ai/airllm_provider.py` behind `AIProvider` for agents `Market Regime / Setup Validation / MTF / Journal Analyst / Strategy Researcher` (§9 in prompt), each measured `baseline vs +small LLM vs +AirLLM` OOS — `P23` after `graduation = READY`.

On `GT 710` per AirLLM docs: keep trading = `fast Python/C++ quant engine` on Hub; research = `larger model + AirLLM` on a separate stronger box, never in the `tick -> layer-load -> trade` loop.

## 8. Decision — what survives into the roadmap

**TAKE now (no new dep):**
* `*03 philosophy` — operate the existing evidence engine. No refactor.
* Treat `*02/#3/#5` + `*05 compact ritual` as **P18.4 acceptance criteria**, not new tickets.

**PARK until `P19 stable + graduation real-paper gate == READY`:**
* `*04` as external research converter.
* `*05` extra harness/sandbox frameworks.
* `*06` as local inference backend.
* `*01` as external jury lab.
* `*03 L2 posterior + L4 Bayesian + L5 cron` automation.

**REJECT:**
* `*01 -> BUY`, `*04 -> strategy`, `*06 -> position size/SL/leverage/API keys/order execution`. Deterministic `risk_gate.py` + `data/costs.py net` + `graduation bar +0.50R/55%/PF1.5 + compliance100%` never loosened.

## 9. Three concrete actions this week (unchanged)

1. `data/event_log` is `data/store + SignalDB` — append every `scan/approve/reject/paper fill` today; retro-import what exists. Tomorrow you have `30d`.
2. Read the **truth ledger** every Sunday: `python main.py validate --source store --tf 15m` + `python main.py scorecard --conditioned --source store` net, not the dashboard signal.
3. Code `P18.4` — manifest + owned icons + install prompt + offline shell + service worker that *never* caches `/api/*`, `/api/v1/*`, `auth`, `/api/chart/stream`, `/api/v1/jobs/*/events`, private state or mutations; label `live/waiting/stale/error/disconnected` honestly; keep `String.fromCharCode(10)` fix (`tests/test_dashboard_js.py::test_served_script_is_valid_javascript`).

## 10. Guardrails for the next session (copy this)

* Do not add `opendataloader-pdf`, `airllm`, `torch`, or `70B` model downloads to `requirements.txt / config.py / .env.example` before their code exists (`ROADMAP.md:7`).
* Do not change `PRIMARY_SETUP_FAMILY`, lower the graduation bar, pool `binance/spot` with `dukascopy/spot/XAUUSD`, or create live-order code.
* Real-data host: `python main.py learn` must be rerun; `python main.py xau-evidence --json` archived verbatim; `DEMO_MODE=1` stays green offline; `data/store/**` stays gitignored.
* Paper proof continues on **canonical live** only — simulator excluded from `live_book_rows()` + `open_exposure()` + `business_metrics()`.

---
*Sources this triage read:* `ROADMAP.md P18-P22`, `TODO.md`, `HANDOVER.md`, `SESSION_STATE.md v2.33.0`, `AI_ANATOMY_ROADMAP.md`, `ARCHITECTURE.md`, `config.py (N_LEVELS, PRIMARY_FAMILIES, TP_RR_MIN/MAX, calibration, paper, risk)`, `engine/{scorer,signal_engine,regime,hidden_alpha} `, `brain/{library,calibrator,journal,agent}`, `ai/llm_brain.py`, `data/{store,backfill,gaps,derivatives,quality,costs,simulator,validation,scorecard}`, `web/{app,jobs,live_stream}`, `docs/{FREQTRADE_REVIEW,BACKTRADER_REVIEW,NEEDLE_REVIEW,HANDOVER_2026-08-17_W2_part2}` + the six ChatGPT idea texts (LMRing, Personal Desk, Evidence Engine, OpenDataLoader, Harness/CLAUDE.md, AirLLM).
