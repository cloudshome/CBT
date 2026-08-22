# SKY P13 — Edge Validation (milestone spec)

> **Status:** accepted objective, not yet shipped. This is the spec the next
> session executes against, item by item.
> **Date:** 2026-08-22
> **Origin:** the strategic consideration
> (`docs/STRATEGIC_CONSIDERATION_2026-08-22.md`) and the P0 priority it sets.
> **One-line objective:** *prove whether existing trading intelligence survives
> increasingly realistic conditions* — and only then decide **EDGE CONFIRMED**
> or **NO EDGE**. Never tune to a green result.

---

## 1. Why this milestone

The Accio review and its second opinion both agree SKY's bottleneck is no
longer "bad trading code." It is that the project is large enough that
**engineering debt and validation throughput** are becoming the constraint, and
that the trading edge is **not yet proven** on realistic, untouched data.

The milestone objective replaces:

> **"Build more trading intelligence."**

with:

> **"Prove whether existing trading intelligence survives increasingly
> realistic conditions."**

Everything below is ordered by value per session, exactly as the
consideration's P0 → P3 tiers.

## 2. The ladder this milestone feeds

```text
Backtest → Out-of-sample → Paper → Live tiny capital
```

P13 closes the first two rungs rigorously. Paper (P11) is a running lane, not
a P13 code deliverable.

## 3. Deliverables (ordered)

### P13.1 — Realistic execution model (default research posture) · PARTLY SHIPPED

**Goal:** the simulator/validation must be able to grade under realistic fills
(signal close + latency + spread + slippage + fees + funding), not just at the
optimistic exact close.

**What exists:**
- `engine/execution.py` — one-sided slippage = half-spread + size/volatility
  impact, gated by `config.EXECUTION_MODEL` (`none | slip | impact`).
- Costs already applied net-of-costs (P12.6) in `data/backtester._evaluate`.

**What this session shipped:**
- Reconciled the `none | slip | impact` config with the code: previously only
  `simple` applied the fill model, so `slip`/`impact` silently produced zero
  slippage. Now `slip`/`impact`/`simple` all enable the model; `none` (and only
  `none`) opts out. `--execution` flag on `edge-validate`.

**Acceptance criteria (P13.1):**
- [ ] `slip_amount(..., model="slip")` applies spread+impact; regression tests
      green (done).
- [ ] A research/validation run can be executed with `slip` and the results
      are strictly worse-or-equal to `none` (never better). Add an assertion
      test for this monotonicity on real graded output.
- [ ] The **graduation gate** and default `python main.py backtest` remain on
      `none` — the gate is not a research report. Document this decision.

### P13.2 — Walk-forward / out-of-sample protocol · ✅ EXISTS (verify + surface)

**Goal:** a locked train/val/OOS/recent protocol that only lets *untouched*
windows decide an edge claim.

**What exists:**
- `data/validation.py::walk_forward_windows`, `run_validation`,
  `protocol_verdict`, sealed OOS envelopes (BT6).
- `python main.py validate` (store-only) surfaces it.

**Acceptance criteria (P13.2):**
- [ ] Confirm the sealed-envelope behaviour is documented and the OOS/recent
      windows are never used to tune anything.
- [ ] `validate` continues to work on the real-data host; sandbox uses the
      store or synthetic series only.

### P13.3 — Regime-aware edge segmentation + honest verdict · ✅ SHIPPED (this session)

**Goal:** a single honest verdict — **EDGE CONFIRMED / NO EDGE /
INSUFFICIENT_DATA** — computed on the decisive (OOS + recent) windows and
segmented by market regime, so a single hot regime cannot carry an unstable
setup, and thin samples never get a green result.

**What this session shipped:**
- `engine/edge_validation.py`:
  - `segment_by_regime` / `regime_edge_report` / `edge_verdict` /
    `format_edge_verdict` / `edge_validate_report`.
  - Verdict rules (all net-of-costs):
    1. fewer than `min_decided` decided trades overall → `INSUFFICIENT_DATA`;
    2. overall net expectancy ≤ 0 → `NO EDGE`;
    3. net-positive in < `positive_regime_frac` of well-sampled regimes →
       `NO EDGE` (unstable);
    4. otherwise `EDGE_CONFIRMED` (provisional note if regime coverage is thin).
- `python main.py edge-validate` CLI (read-only; `--execution`, `--json`,
  window/regime knobs). It switches the fill model via a scoped
  `EXECUTION_MODEL` override and restores it after the run.
- `tests/test_edge_validation.py` (11 tests) + execution-alias regressions.

**Acceptance criteria (P13.3):**
- [x] Verdict is honest on thin/negative samples (tests).
- [x] Regime stability check rejects a single hot regime (test).
- [x] Offline run works under `DEMO_MODE=1` (verified).
- [ ] Review the verdict thresholds (`min_decided=30`,
      `regime_min_decided=10`, `positive_regime_frac=0.5`) on the real-data
      host and confirm they are not too lax.

### P13.4 — O(N²) backtest performance · ⏳ NEXT MAJOR CODE WORK

**Goal:** turn the walk (recompute indicators/structure from bar 0 every step)
into `precompute indicators → incremental structure → walk-forward evaluation`
so research throughput rises dramatically.

**Why it matters:** SKY wants BTC/ETH/XAU × 1m/5m/15m/1h/4h × multiple years ×
regimes × strategies. If every experiment is slow, fewer experiments run → weaker
validation.

**Acceptance criteria (P13.4):**
- [ ] Profile the current walk on a fixed multi-year frame and record a
      baseline (bars/s, plans/s).
- [ ] Implement precomputed indicator columns + incremental structure update;
      graded outcomes must be **behaviour-identical** to the current walk on a
      fixed frame (bit-for-bit or within a documented epsilon).
- [ ] Prove a concrete speed-up (e.g. ≥ 3–10× on the baseline) with a
      reproducible benchmark.
- [ ] Full suite stays green; graduation numbers unchanged.

### P13.5 — Edge stability / Monte Carlo on decisive windows · ✅ SHIPPED (v2.57.0)

**Goal:** report expectancy stability and risk-adjusted performance (drawdown,
ruin probability, longest losing streak) on the decisive windows, not just on
the pooled paper book.

**What this session shipped:**
- `engine/edge_validation.py::monte_carlo_decisive()` — bootstrap resampling
  of the decisive-window net R series. Reports expectancy p5/p50/p95,
  drawdown median/p95, ruin probability, equity range, longest loss streak.
- `edge_verdict()` gains `monte` (optional) and `monte_floor` (default True).
  The 5th-percentile net expectancy must be > 0 as a confirm condition.
- `edge_validate_report()` gains `monte`, `monte_samples`, `monte_risk_pct`,
  `monte_seed`.
- `format_edge_verdict()` prints the full MC table.
- CLI: `python main.py edge-validate --monte [--monte-samples N]
  [--monte-risk-pct P] [--monte-seed S]`.
- `tests/test_edge_validation_monte.py` (16 tests).

**Acceptance criteria (P13.5):**
- [x] A `edge-validate --monte` (or `--json` block) resamples the decisive-window
      R series and reports 5%/50%/95% expectancy, expected max DD, and ruin
      probability at the current risk %.
- [x] The EDGE verdict incorporates a Monte-Carlo floor (e.g. 5th-percentile
      net expectancy > 0) as a confirm condition.

### P13.6 — Paper + compare ladder surface · PARTLY (P11)

**Goal:** a single dashboard/CLI surface that juxtaposes
Backtest → Out-of-sample → Paper → (live tiny) so the owner can see the
degradation ladder honestly.

**Acceptance criteria (P13.6):**
- [ ] `edge-validate` output can be paired with the canonical paper
      `expectancy_net` in one report.
- [ ] No new endpoint required; compose from existing `/api/*` if surfaced.

### P13.7 — Agent-scope freeze (guardrail) · DOCUMENTED

**Goal:** do NOT add OpenHands / Dify / LibreChat / multiple LLMs / autonomous
agents / Discord agent / 50 plugins until the core statistical validation is
finished. AI sits **around** the deterministic core, never replaces it.

**Acceptance criteria (P13.7):**
- [ ] No new external agent framework is added to the queue while P13.1–P13.5
      are open. Enforced in ROADMAP "explicitly out of scope".

---

## 4. Decision points (open — need owner sign-off)

1. **Execution default for research:** keep `none` as the global default
   (gate stability) while `edge-validate --execution slip` and the P13.1
   monotonicity prove the realistic posture? **Recommended: yes.**
2. **Verdict thresholds:** confirm `min_decided=30 / regime_min_decided=10 /
   positive_regime_frac=0.5` once real data is available.
3. **P13.4 performance target:** pick the speed-up target (3–10×) and the
   frame to benchmark against.

## 5. Definition of done for P13

- [ ] P13.1 monotonicity + `--execution slip` proven by test.
- [ ] P13.3 verdict surfaced via `python main.py edge-validate` (done) and
      reviewed on real data.
- [x] P13.4 benchmarked speed-up, behaviour-identical grading, suite green.
- [x] P13.5 Monte-Carlo floor wired into the verdict.
- [ ] ROADMAP/TODO updated to mark P13 shipped; next milestone chosen
      (expected: return to Lane A paper grind or P13.4 continuation).

## 6. Honest boundaries (do not cross)

- `edge-validate` is **read-only** — never places an order, never moves a
  threshold, never unlocks micro-live.
- The graduation gate (BLUEPRINT Step 2 → 3) is **unchanged**. P13 proves or
  disproves the edge; it does not lower the bar.
- Sandbox has no real data: `edge-validate` mechanics are verified on the
  committed sample / synthetic series only; the real-data host must confirm.
