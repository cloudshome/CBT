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

**Last updated:** 2026-08-15 (this session: **P12.5 Strategy Score on the calibrator shipped** — `data/strategy_score.py`: `E_R × sample-quality × regime-fit × execution` per calibration key (weighted geometric mean, NET of costs; sample-quality = P12.4's `backtest_quality_score()` in full); calibrator multiplier is now a trust dial `mult = clamp(1 + E_gross × gain × trust, …)`, `trust = clamp(score/50, 0.6, 1.5)`; surfaces: `learn` CLI / `/api/learning` / dashboard Calibration card)
**Branch:** `arena/01a00446-sky` (session branch fixed by Arena; branched from `origin/main` @ `fd4aa51`, the merged P12.4 PR #25)
**HEAD commit:** `fd4aa51` (P12.4 Backtest Quality Score) — this session's P12.5 work commits on top of it.
**Python:** 3.11 (venv `.venv` — system Python is PEP 668 externally managed) — suite green (613 pass / 1 skip)

> **This session (`arena/01a00446-sky`): P12.5 — Strategy Score on the calibrator.**
> The scorecard (P12.3/P12.6) reports the numbers, P12.4 judges the curve's
> robustness, and the calibrator turns a setup's observed expectancy into
> the confidence multiplier the engine applies. Before P12.5 the calibrator
> trusted **gross expectancy alone** — a fragile, weakly-sampled, or
> cost-doomed curve earned the same boost as a robust one. P12.5 closes
> that with the audits' formula (`docs/FREQTRADE_REVIEW.md` F25 /
> `docs/BACKTRADER_REVIEW.md` BT12): **`E_R × Stability × SampleConfidence`**
> — landed on the calibrator as a 0–100 **strategy score** per key:
> - **`data/strategy_score.py`** — pure `strategy_score(rows, …)`, four
>   multiplicative components composited as a **weighted geometric mean**
>   (the "×" is literal — zero on any axis zeroes the score):
>   - **e_r** (35%) — P12.4's `edge_score` verbatim (E_net vs bar,
>     shape-discounted on WR/PF misses);
>   - **sample_quality** (35%) — **P12.4's `backtest_quality_score()` in
>     full** (curve robustness + sample confidence + plateau) — read,
>     never reimplemented;
>   - **regime_fit** (15%) — base `plan_type` key: sample-weighted fraction
>     of regimes with positive E_net (a one-regime edge is real, but the
>     base key cannot know which regime is next); `plan_type::regime` key:
>     the regime's E_net vs the setup's all-regime E_net (100 = ≥1.5×
>     stronger, 66.7 = average, 0 = no edge in this regime);
>   - **execution** (15%) — share of the gross edge surviving the P12.6
>     cost model (`1 − avg_cost_r / avg_gross_r`).
> - **`multiplier_from_score()`** — the trust dial:
>   `mult = clamp(1 + E_gross × gain × trust, min, max)` with
>   `trust = clamp(score/50, 0.6, 1.5)`: score 50 = pre-P12.5 formula;
>   robust edge trusted up to 1.5×; fragile/net-negative shrunk to the
>   0.6 floor. Sign anchor stays gross expectancy → losing setups are
>   always dampened or filtered.
> - **`brain/calibrator.py`** — `build_profile` pulls the key's decided
>   rows (`_decided_rows_by_key`, reusing the scorecard's row adapters),
>   computes + persists the score; entries gain `strategy_score`,
>   `strategy_band`, `strategy_components`, `expectancy_net`.
> - **Surfaces (invariant #10):** `learn` CLI (`describe` + `--json`),
>   `GET /api/learning`, dashboard Calibration card (`Score` column).
> - **DB:** additive migration `calibration.strategy_score REAL` +
>   `strategy_band TEXT`; `save/load_calibration` round-trip them.
> Version **2.15.0 → 2.16.0** (also fixed: `config.VERSION` was still
> 2.14.0 after P12.4 — both `config.py` and `pyproject.toml` now 2.16.0).
> Suite **598 → 613 pass / 1 skip** (+15: `tests/test_strategy_score.py`).

> **Prior session (`arena/01a003f9-sky`, merged as PR #23): P12.6 — fees-first `E_net` & conditioned expectancy.**
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
data imported and verified; research validation proof — 🔄 P12.1–P12.6 &
P12.3.3 & P12.4 & P12.5 shipped;
next is **P12.7 Monte Carlo ruin / risk-of-ruin**, then micro-live). Every
phase below is ordered by how directly it moves those two lines.

---

## Current phase

**P12 (SKY Quant Validation Engine) — P12.5 strategy score on the calibrator shipped.**
P10 (data infrastructure) is fully shipped (P10.1–P10.12, PR #18); P11 grind
re-run on real data and the graduation gate is honestly closed (+0.348R gross,
negative net on 1h/4h primary). Freqtrade rejected (F1–F8); Backtrader
rejected (BT1–BT8). Open items: TODO-7, TODO-8; **P12.7 (MC ruin / worst
streak / risk-of-ruin table)** → micro-live.

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
| **P12** | **Quant Validation Engine** | 🔄 In progress | **P12.5 shipped — Strategy Score on the calibrator** (P12.1 locked protocol; P12.2 lookahead guard; P12.3 scorecard; P12.3.1 tie-break unified; P12.3.2 real market data; P12.6 fees-first `E_net`; P12.3.3 `N_eff`/CI; P12.4 Backtest Quality Score + plateau sweep; **P12.5: `data/strategy_score.py` `E_R × sample-quality × regime-fit × execution` on the calibrator — sample-quality reads P12.4 in full; multiplier is now a trust dial**). Next: **P12.7 MC ruin / worst streak / risk-of-ruin**. |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-15 (this branch `arena/01a00446-sky`): P12.5 — Strategy Score on the calibrator

Branched from `main` @ `fd4aa51` (PR #25 merged). 0 regressions.
Tests **598 → 613 pass / 1 skip** (+15). Version **2.15.0 → 2.16.0**.
(`config.VERSION` was still 2.14.0 after P12.4 — fixed; `config.py` and
`pyproject.toml` are now in step.)

**What shipped:**
- `data/strategy_score.py` (new module) — pure `strategy_score(rows, …)`:
  `E_R × sample-quality × regime-fit × execution` per calibration key,
  each component 0–100, composited as a **weighted geometric mean** (the
  audits' "×" is literal — zero on any axis zeroes the score), evaluated
  NET of costs (P12.6) with overlap-corrected samples (P12.3.3):
  - e_r (35%) = P12.4's `edge_score`; sample_quality (35%) = **P12.4's
    `backtest_quality_score()` in full**; regime_fit (15%) = positive-
    regime fraction (base key) or regime-vs-setup-average ratio (regime
    key); execution (15%) = share of gross edge surviving the P12.6 cost
    model.
  - Empty books degrade to `score: None`; bands ≥80 robust / ≥60
    acceptable / ≥40 borderline / else fragile.
  - `multiplier_from_score()` — the calibrator's trust dial:
    `mult = clamp(1 + E_gross × gain × trust, min, max)`,
    `trust = clamp(score/50, 0.6, 1.5)`.
- `brain/calibrator.py` — `_decided_rows_by_key()` (reuses the scorecard's
  row adapters, invariant #10), `build_profile` computes + persists the
  score per key; entries gain `strategy_score`, `strategy_band`,
  `strategy_components`, `expectancy_net`; `describe()` prints the score.
- `data/database.py` — additive migration `calibration.strategy_score
  REAL` + `strategy_band TEXT`; `save/load_calibration` round-trip them.
- `web/app.py` — dashboard `LEARNING` card: band-coloured `Score` column
  + P12.5 legend line.
- `main.py` — `learn` CLI prints the score via `describe()` (no signature
  change); `--json` dumps components.
- Tests: 15 new (`tests/test_strategy_score.py`).

**Measured on a demo book (120 Buy Pullback / 60 Breakout Buy rows):**
- `Buy Pullback::TRENDING_BULL` → **65.9/100 acceptable** (E +0.667R →
  net +0.547R, win 67%) → multiplier **1.22** (trust dial, capped).
- `Breakout Buy::TRENDING_BULL` (net-negative) → **0.0/100 fragile** →
  multiplier 0.85 (dampened, never boosted).

**Files changed:** `data/strategy_score.py` (new), `brain/calibrator.py`,
`data/database.py`, `web/app.py`, `config.py`, `pyproject.toml`,
`tests/test_strategy_score.py` (new), `CHANGELOG.md`, `TODO.md`,
`README.md`, `ARCHITECTURE.md`, `AI_ANATOMY_ROADMAP.md`,
`docs/HANDOVER_2026-08-15_P12_5.md` (new), `SESSION_STATE.md`.

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

1. **TODO-13 (P12.7) — Monte Carlo ruin / worst streak / risk-of-ruin
   table.** `risk% × expected DD × ruin probability`, longest losing
   streak, time-to-recovery on the existing resampler (`+` BT5/BT16) —
   graduation can then see survivability, not just mean E.
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
    fixed to 2.16.0 in this session; `config.py` and `pyproject.toml` are
    now in step.

---

## Next recommended action

1. Next *code* session: **P12.7 — Monte Carlo ruin / worst streak /
   risk-of-ruin table.** Extend the existing resampler
   (`brain/analytics.monte_carlo_equity`) into
   `risk% × expected DD × ruin probability` + longest losing streak +
   time-to-recovery (`+` BT5/BT16) so graduation can see survivability,
   not just mean E. One command, one boxed block (CLI / HTTP / MCP /
   dashboard — invariant #10).
2. A human does TODO-7 + TODO-8 from [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
3. Do **not** install Freqtrade or Backtrader. Do not loosen the graduation bar.

Narrative handover for this session: [`docs/HANDOVER_2026-08-15_P12_5.md`](docs/HANDOVER_2026-08-15_P12_5.md).

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md. Fetch and diff origin/main first,
> and confirm the P12.5 PR merged. P12.1, P12.2, P12.3, P12.3.1, P12.3.2,
> P12.6, P12.3.3, P12.4, and P12.5 are shipped: do not redo the locked
> protocol, the negative-shift guard, the boxed scorecard, the tie-break,
> the real data import, trade cost modeling, the overlap-corrected
> effective sample size, the Backtest Quality Score, or the strategy score
> on the calibrator. Implement **P12.7 — Monte Carlo ruin / worst streak /
> risk-of-ruin table**: on the existing resampler
> (`brain/analytics.monte_carlo_equity`), add `risk% × expected DD × ruin
> probability`, longest losing streak and time-to-recovery. Keep the
> existing grader/store, do not adopt Freqtrade or Backtrader, and do not
> loosen the graduation bar.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# 613 passed, 1 skipped
```

Wheel gate:
```bash
DEMO_MODE=1 .venv/bin/python ci/wheel_gate.py
# builds cryptobrain-2.16.0-py3-none-any.whl ; no duplicate entries
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
(THIS SESSION) feat(P12.5): strategy score on the calibrator — E_R × sample-quality × regime-fit × execution
fd4aa51 feat(P12.4): backtest quality score 0-100, plateau sweep & scorecard surfaces (#25)
e07fa43 feat(P12.3.3): effective sample size in the scorecard (#24)
```

P12.5 is committed on `arena/01a00446-sky`, pushed to origin, and the
session PR is open against `main` — the human merges it. See
`git log --oneline -3`.

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

1. [x] Finish or safely stop the current task. — **P12.5 shipped**
   (Strategy Score on the calibrator: `E_R × sample-quality × regime-fit ×
   execution`, `data/strategy_score.py`, trust-dial multiplier,
   `learn` / `/api/learning` / dashboard surfaces).
2. [x] Run `.venv/bin/python -m pytest tests/ -q` — **613 pass / 1 skip**
   (+15: `tests/test_strategy_score.py`).
3. [x] Fix any obvious failures. — none left open.
4. [x] Update `SESSION_STATE.md` with the exact current state.
5. [x] Update `TODO.md` — P12.5 marked shipped; P12.7 is next.
6. [x] Update `CHANGELOG.md` — 2.16.0 P12.5 entry.
7. [x] Record all files changed in `SESSION_STATE.md`.
8. [x] Record the last successful test command.
9. [x] Record the last commit reference.
10. [x] Record any known bugs or unresolved issues.
11. [x] `git add` / `git commit` — commit and push to `origin/arena/01a00446-sky`.
12. [x] Open the session PR as the closing step — PR from
    `arena/01a00446-sky` → `main` (P12.5).
