# Handover — 2026-08-22 · P13 Edge Validation — plan + first code shipped

> This session converted a strategic second opinion (on the Accio review) into a
> **tracked milestone** and shipped the first honest edge-verdict surface.
> Next session: read this, then `docs/P13_EDGE_VALIDATION_SPEC.md`, then
> `TODO.md` (TODO-25) — and execute **P13.4** (the O(N²) backtest performance
> redesign).

## What this session produced

### 1. Strategic decision doc (the reason)
**`docs/STRATEGIC_CONSIDERATION_2026-08-22.md`** — a polished, decision-oriented
second opinion on the Accio review of SKY. Core thesis:

> SKY looks like a serious research/validation platform, but engineering
> maturity ≠ trading profitability. Priority P0 = trading validity
> (realistic execution → OOS → walk-forward → regime → paper) *before*
> dashboard beauty, web refactoring, or security hardening. Keep the
> "NO EDGE" honesty; don't add external AI agents until validation is done.

### 2. Milestone spec
**`docs/P13_EDGE_VALIDATION_SPEC.md`** — P13.1…P13.7 with acceptance criteria,
decision points, definition of done, and honest boundaries.

### 3. Code shipped (all green, +11 tests, suite 1348 → 1359 / 1)

- **`engine/execution.py`** — reconciled `none | slip | impact` with the code.
  Previously only `"simple"` applied the fill model, so the documented
  `slip`/`impact` values silently produced **zero** slippage. Now `slip` /
  `impact` / `simple` enable it; `none` (and only `none`) opts out. Added a
  conservative fill-by-default direction for unknown values + regression tests
  (`tests/test_execution.py`).
- **`engine/edge_validation.py`** (new) — the honest, regime-aware edge verdict:
  - `edge_validate_report(df, …)` — one no-look-ahead walk, buckets graded plans
    by window, restricts to the **decisive** `("oos","recent")` windows, segments
    by regime, returns a verdict.
  - `edge_verdict(report)` → **`EDGE_CONFIRMED` / `NO EDGE` /
    `INSUFFICIENT_DATA`**, all net-of-costs:
    1. < `min_decided` decided → `INSUFFICIENT_DATA`;
    2. overall net expectancy ≤ 0 → `NO EDGE`;
    3. net-positive in < `positive_regime_frac` of well-sampled regimes →
       `NO EDGE` (unstable);
    4. else `EDGE_CONFIRMED` (provisional note if regime coverage is thin).
  - `format_edge_verdict(...)` — human block in the exact "NO EDGE" style.
- **`main.py`** — new `python main.py edge-validate` (read-only). Flags:
  `--symbol --tf --bars --horizons --step --min-bars --min-conf
  --min-decided --regime-min-decided --positive-regime-frac
  --decisive-windows --execution {none,slip,impact} --source {auto,store}
  --exchange --market --train --val --oos --recent --json`. Switches the fill
  model via a scoped `EXECUTION_MODEL` override and restores it after.
- **`tests/test_edge_validation.py`** (new, 11 tests) — regime grouping, net
  stats, and the honesty matrix (thin→INSUFFICIENT, negative→NO EDGE,
  unstable-across-regimes→NO EDGE, stable→CONFIRMED, provisional coverage),
  plus an end-to-end run on synthetic candles.

**Verified offline:** `DEMO_MODE=1 python main.py edge-validate --bars 600
--horizons 1` runs end-to-end and honestly reports INSUFFICIENT_DATA on the
synthetic/sample series. Full suite green.

## How to run it

```bash
# honest verdict on the sealed OOS + recent windows (default fill model "none")
DEMO_MODE=1 python main.py edge-validate --bars 600 --horizons 1

# realistic fills
DEMO_MODE=1 python main.py edge-validate --bars 600 --horizons 1 --execution slip

# machine-readable (for the dashboard/compare-ladder work later)
DEMO_MODE=1 python main.py edge-validate --bars 600 --horizons 1 --json

# from the real-data store
python main.py edge-validate --source store --symbol BTCUSDT --tf 15m --bars 4000 --horizons 1,4,24 --execution slip
```

## Honest boundaries (do not cross)

- `edge-validate` is **read-only**: never places an order, never moves a
  threshold, never unlocks micro-live.
- The graduation gate and default `python main.py backtest` stay on
  `EXECUTION_MODEL="none"`. Realistic fills are a **research posture**, not a
  gate change.
- Sandbox verified mechanics on synthetic/sample data only. Verdict thresholds
  (`min_decided=30`, `regime_min_decided=10`, `positive_regime_frac=0.5`)
  must be reviewed on the real-data host.

## What's next (in order)

1. **P13.4 — O(N²) backtest performance (the big one).**
   - Baseline: profile `run_backtest` / `simulate_round` on a fixed multi-year
     frame (`bars/s`, `plans/s`).
   - Design: precompute indicator columns once, then incremental structure
     update per step instead of `df.iloc[:i+1]` + full `analyze_frame` at every
     `i`.
   - Prove **behaviour-identical** grading (same `GradedPlan` outcomes/R on a
     fixed frame) and a ≥ 3–10× speed-up; keep the suite green and graduation
     numbers unchanged.
2. **P13.5 — Monte-Carlo floor.** Resample the decisive-window R series
   (`brain/analytics.monte_carlo_*`) and require 5th-percentile net expectancy
   > 0 before `EDGE_CONFIRMED`.
3. **P13.1 acceptance** — add a monotonicity test: `slip` results are strictly
   worse-or-equal to `none` (never better).
4. **P13.6 — compare ladder** (backtest → OOS → paper) in one report.
5. Then refactor `web/app.py` (10,083 lines) and `main.py` (3,334) one domain
   at a time, `tests → behaviour compare → CI → commit` per step.

## Files touched this session

- `docs/STRATEGIC_CONSIDERATION_2026-08-22.md` (new)
- `docs/P13_EDGE_VALIDATION_SPEC.md` (new)
- `docs/HANDOVER_2026-08-22_EDGE_VALIDATION.md` (this file, new)
- `engine/edge_validation.py` (new)
- `engine/execution.py` (edit: model reconciliation)
- `main.py` (edit: `edge-validate` command + parser)
- `tests/test_edge_validation.py` (new, 11)
- `tests/test_execution.py` (edit: +2 regression tests)
- `TODO.md` (header entry + TODO-25 + out-of-scope guard)
- `ROADMAP.md` (snapshot row, Lane-B P13 section, binding decision 15,
  out-of-scope guard, suite count)
- `SESSION_STATE.md` (next entry), `CHANGELOG.md` (entry)

## Version note

This session made **no product version bump** — it is a research/planning +
validation layer, not a user-facing release. `config.VERSION` stays v2.55.0.
The suite count rose to 1359/1 purely from the new validation tests.
