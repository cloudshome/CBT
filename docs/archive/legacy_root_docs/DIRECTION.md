# CTB — Technical Direction

**Owner:** engineering lead
**Date:** 2026-09-05
**Status:** active

This document sets priorities against the project's *actual* aim, not its
backlog. It supersedes the audit's priority ordering where the two conflict,
and it says why.

---

## 1. What this project is actually for

From `TODO.md`, the stated contract:

> Position sizing, stop-loss calculation, daily loss limits, portfolio heat, and
> hard kill switches are **100% deterministic** Python code. AI never places
> unrestricted orders.

And the evidence ladder:

> Idea → Formalized → Backtested → Out-of-Sample → Paper Trading → Human
> Approval → Live

So the product is not "a trading bot." The product is **a machine that refuses
to trade unless the evidence justifies it.** The ~70% NO_TRADE baseline is not
a limitation; it is the entire value proposition. Everything else — SMC
engines, Kronos, the debate council, the PWA — is instrumentation around that
single promise.

**This reframes what "production-ready" means.** The audit scored production
readiness at 5.5/10 based on branch protection, CI, and CORS. Those matter, but
they are the readiness criteria for *a web service*. For **this** product there
is exactly one criterion that dominates:

> Can the system distinguish a real edge from a fabricated one, and refuse to
> commit capital when it cannot?

Until that is true, branch protection is a lock on a door that has no walls.

---

## 2. What I found, and why it outranked the audit's P0

The audit's P0 list was: branch protection, required checks, stale branch
cleanup, green CI. Three of those four were already done or are
admin-only (see §5). So I went looking at the decision path instead.

### The finding

Multiple engines **fabricate data when real data is missing**, and the
fabricated values were **indistinguishable from real ones downstream**.

Measured on a cold database, before the fix:

```
real historical states available : 0
k_samples_found                  : 50        <- all from np.random.seed(1337)
sample_adequacy_score            : 1.00      <- "fully adequate"
uncertainty_penalty              : 0.00      <- "no penalty"
expected_r_multiple              : 6467.56   <- divide-by-epsilon
```

The system reported **maximum confidence in pure noise**, and that number fed:

```
analogue_engine.p_tp_hit
   └─> ev_engine.calculate_net_ev()
         └─> conservative_kelly.calculate_allocation()
               └─> recommended_position_units   <-- real money
```

This is the worst failure mode a risk system can have. It is worse than
crashing. A crash is honest. This produced a confident, precise,
well-formatted position size derived from a random number generator — and the
uncertainty engine, whose entire job is to catch this, was handed
`uncertainty_penalty = 0.0` and therefore reported LOW uncertainty.

It also **directly violates the project's own constitution**, which rejects
"fabricating backtest win rates."

Worth noting: a pre-existing test, `test_hierarchical_analogue_ensemble`,
asserted `sample_adequacy_score > 0` on a cold database. The suite was
**locking the bug in**. A green suite was providing false assurance — which is
why I rate "make CI green" below "make CI meaningful."

### The fix (shipped, PR #46)

A provenance layer — `core/evidence_integrity.py`:

- **`EvidenceGrade`**: `FABRICATED < SIMULATED < IMPUTED < EMPIRICAL`.
  Only `EMPIRICAL` may authorize risk. Note that `SIMULATED` (Monte Carlo,
  bootstrap) is deliberately **not** tradeable-grade: model output is not
  observation.
- **`EvidenceLedger`**: weakest-link semantics. One fabricated input
  contaminates the verdict and the ledger will not let that fact get lost
  between layers. An *empty* ledger grades as `FABRICATED` — absence of
  evidence is not evidence of safety.
- **`require_live_evidence()`**: raises rather than returning a boolean,
  because a boolean is too easy to ignore at a call site.

Enforcement at three chokepoints:

| Layer | Behaviour |
|---|---|
| `analogue_engine` | adequacy/penalty computed from **real** samples only; tags `evidence_grade` + `real_sample_count`; R-multiple clamped |
| `debate_committee` | **RULE 0** — non-empirical evidence forces `NO_TRADE` before any directional branch, non-overridable by confidence |
| `conservative_kelly` | refuses to size on non-empirical `p` |

Verified live on the API:

```json
{ "final_decision": "NO_TRADE",
  "evidence_grade": "FABRICATED",
  "primary_execution_thesis": "EVIDENCE INTEGRITY HALT: analogue distribution
     is FABRICATED, not empirically observed (real samples: 0)." }

{ "recommended_position_units": 0.0,
  "summary": "Zero allocation: Evidence integrity halt: win probability is
     FABRICATED, not empirically observed. Kelly sizing refused." }
```

13 regression tests, including the load-bearing one: **a maximally bullish EV
(`net_ev_r=5.0`, `win_probability=0.95`, zero uncertainty) still yields
`NO_TRADE`** when evidence is fabricated. Full suite: 237 passed.

---

## 3. Priorities

### P0 — Finish making fabricated data structurally inert

The analogue path is sealed. **The same pattern exists in at least four other
modules** and each is an open hole into the same funnel:

| Module | Fabrication |
|---|---|
| `core/institutional_alpha.py:280` | `np.random.normal` OHLC fallback |
| `core/lead_lag_correlator.py:54` | fabricated DXY / US10Y return series |
| `core/market_providers.py:402` | seeded random OHLCV fallback |
| `core/strategy_selection_guard.py:65` | random return series |
| `core/data_streamer.py:216` | synthetic candles (tagged, but grade not propagated) |

Work: thread `EvidenceLedger` through each, so the grade travels with the data
instead of being inferred at the end. `data_streamer` already sets
`is_synthetic` — that flag needs to *become* an `EvidenceGrade` rather than
dying at the DB boundary.

**Exit criterion:** a system-level test that wipes every database, hits every
decision endpoint, and asserts **no endpoint returns a non-zero position size
or a directional verdict.** Cold start must be provably inert.

### P0 — Delete the strategy league's fake track record

`core/strategy_league.py:_seed_default_strategies()` hardcodes:

```python
forward_trades_count=320,
historical_win_rate=0.64,
rolling_sharpe_30d=2.15,
monte_carlo_ruin_prob=0.002,
quarantine_tier=QuarantineTier.TIER_4_PRODUCTION,
allocation_weight=0.60,
```

Three strategies are **born at Tier 4 "Production" with invented Sharpe ratios
and 320 imaginary trades**, and `rebalance_capital_weights()` allocates capital
on those numbers. The 4-tier quarantine ladder — the mechanism that is supposed
to *prevent* untested strategies from receiving capital — ships pre-defeated.

This is the same class of bug as the analogue engine and I consider it equally
severe. Strategies must **start at Tier 0 with zero trades** and earn
promotion through `evaluate_promotion()` against real accumulated evidence.

### P1 — Make CI meaningful, then make it required

Ordering here is deliberate and I'd push back on the audit's sequencing.
Requiring a check that asserts wrong behaviour just enforces the wrong
behaviour. Sequence:

1. Add the cold-start inertness test above to CI.
2. Audit the suite for other tests that assert fabricated-data behaviour.
3. *Then* make `Lint, Test & Build` a required check.

Also: `pytest` currently runs against whatever `data/` state exists. Tests must
run against a **wiped** database in CI so the cold-start path is the default
tested path, not an edge case.

### P1 — Resolve the dual backend, by deletion

The audit called this HIGH architectural debt and offered Express-or-FastAPI.
I'll be more specific, because for *this* product the choice is forced.

The risk layer — `conservative_kelly`, `debate_committee`, `evidence_integrity`
— is **Python only**. Express has 29 routes including `/api/paper` (executes
paper trades) and its own `riskGate.ts`, which means there are **two risk
implementations** and only one of them now has evidence integrity. The Express
paper-trade path can still size a position with no evidence gate at all.

**Decision: FastAPI is authoritative. Express is reduced to nothing, or to a
thin proxy.** Any endpoint that touches risk or capital moves to Python first.
This is not a style preference — it is the only way to have one enforceable
risk perimeter, and it closes a live gap.

### P2 — Then the audit's infrastructure items

CORS fail-closed, CodeQL, and dependency scanning are **shipped** (PR #46).
Remaining, in order: non-root containers, Caddy healthcheck hitting a real
backend (it currently probes nginx, which returns 200 with both backends
down — a permanently green light), rate limiting on all public endpoints,
committed Prisma migrations, PostgreSQL when concurrency demands it.

SQLite is genuinely fine for single-node paper trading. Migrating it now is
not the highest-value work and I'd defer it behind everything above.

---

## 4. Scoring, revised

The audit scored against generic web-service criteria. Scored against *this
product's* actual promise:

| Dimension | Audit | Mine | Why |
|---|---|---|---|
| Architecture | 7/10 | 6/10 | Two risk implementations, only one gated |
| CI/CD | 6/10 | 5/10 | Green, but was asserting a bug |
| Security | 6/10 | 7/10 | CORS + scanning shipped |
| Evidence integrity | *not scored* | **was 1/10 → now 6/10** | The dimension that decides whether this product works |
| Production readiness | 5.5/10 | **4/10 → 5/10** | Lower than audit: the blocker was worse than branch protection |

I scored it *down* before scoring it up. The audit's 5.5 was too generous
because it never opened the decision path. The single most important number
here is that evidence integrity was **1/10** — the system could not tell noise
from signal — and no amount of branch protection compensates for that.

**Do not deploy against live capital until P0 is complete.** With P0 done, the
honest posture is: a paper-trading research platform whose refusals can be
trusted.

---

## 5. Requires a human (I cannot do these)

Both blocked by integration permissions, not by effort:

1. **Branch protection on `main`** requiring `Lint, Test & Build` —
   `403 Resource not accessible by integration`. Settings → Branches.
   *Do this after P1, per the sequencing above.*
2. **Enable Code scanning** — Settings → Code security. The CodeQL workflow is
   live and will start producing alerts the moment it is enabled; its upload
   step is currently advisory so it does not block PRs.

Corrections to the audit, verified against the live repo:

- `feature/agent-constitution` **no longer exists** — cleanup already happened.
- CI on `main` is **already green** (run 33874154203).
- Commit *statuses* are empty, but the **check-run** `Lint, Test & Build`
  reports success. The audit read the legacy statuses API.
