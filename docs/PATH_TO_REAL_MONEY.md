# PATH_TO_REAL_MONEY.md — an honest audit against the actual aim

> **Status:** assessment + proposal. Nothing here is decided. It does not
> change the roadmaps, the graduation bar, or any invariant. It records
> four measured findings and argues for **reordering** the P12 ladder.
> **Written:** 2026-08-14, immediately after P12.3 shipped.
> **Author's note:** every number below was measured on this repo at
> commit `342c66b`, not estimated. Repro commands are included.

The aim in `SESSION_STATE.md` is *"become a fully independent,
consistently profitable trader"* — with real money, in the real market.
This document asks one question: **what actually stands between the
current repo and that?** Not what is unbuilt — what is *wrong*.

---

## 0. What the project gets right (so the rest is read correctly)

Three things here are genuinely above the norm and should not be
disturbed by anything below:

1. **It refuses to lie to itself.** The graduation gate is closed and has
   stayed closed across many sessions. P12.3's first real verdict was
   🔴 FAIL and nobody touched the bar. The sell-R sign bug was found
   *because* the discipline is grind-then-report.
2. **Rejecting Freqtrade (F1–F8) and Backtrader (BT1–BT8) was correct.**
   One grader means one truth. That decision should hold.
3. **The data layer (P10) is the most valuable asset in the repo** —
   more than the strategy logic. Owning your own history is what makes a
   future edge checkable rather than a story.

The findings below are not a reversal of any of that. They are the
consequence of taking the project's own honesty standard seriously.

---

## 1. Finding: SKY has never seen a real market

| check | result |
|---|---|
| `.parquet` files under `data/store/` | **0** |
| rows in `paper_trades` | **0** |
| rows in `backtest_results` | 1,049 (run `20260814_110407`) |
| origin of those rows | `tests/conftest.py::make_ohlcv()` — a seeded Gaussian random walk |

Every number the project has ever reported — the P11 grind's +0.263R,
P12.3's +0.341R, every per-regime and per-setup split — was measured on
synthetic series.

This matters more than "synthetic data is less realistic." A Gaussian
random walk has **no autocorrelation, no fat tails, no regime
persistence, and no stop-hunt structure**. Those are not cosmetic
details; they are the *only* things a technical edge can feed on. An
expectancy measured against a random walk is largely measuring the
grader's own geometry (R:R ratio, horizon, trigger rule), not a market
edge.

The repo already half-knows this. `SESSION_STATE.md` known-problem 7
says sweep setups are breakeven because "the sandbox's deterministic
series are smooth random walks with drift — they have no real stop-hunt
structure … data character, not a bug." That note is correct but
under-drawn: **the same caveat applies to every other number in the
project, including the ones the graduation gate reads.**

The P10 backfill machinery — rate-limit pacing, gap repair, rollups,
Bybit, cross-exchange — is well built and **has never been pointed at a
real exchange**.

```bash
# the evidence
find . -name '*.parquet' -not -path './.venv/*' | wc -l    # 0
sqlite3 data/cryptobrain.db 'select count(*) from paper_trades'   # 0
```

---

## 2. Finding: costs are not in the number

`config.py:130` — `EXECUTION_MODEL = os.getenv("EXECUTION_MODEL", "none")`.
The default is off, so the grader records raw fills. Measured against
SKY's *own* plan geometry:

**Median stop distance = 0.823% of entry** (mean 0.824%, p10 0.730%,
n≈876 plans).

Cost of one round trip, expressed in R:

| assumption | cost |
|---|---|
| taker both sides (0.05%/side, Binance USDT-perp) | **−0.121R** |
| taker + 1bp slip per side | −0.146R |
| maker in / taker out | −0.085R |

Applied to P12.3's headline: **+0.341R gross → ≈ +0.22R net.** A 35%
haircut on the exact number the graduation gate judges.

And the bar itself (`≥ +0.50R`) is a **gross** threshold. Restated
net, it is ~40% easier than it reads.

### The correction P12.6 needs

`docs/BACKTRADER_REVIEW.md` line 161 specs P12.6 as
`E_net = E_gross − fees − slip − funding − execution`, with emphasis on
funding joined as-of-T from P10.4. At P12.3's **1.8h median hold**:

- funding ≈ (1.8h / 8h) × 0.01% = 0.00225% of notional ≈ **0.003R**
- fees ≈ **0.121R**

**Fees are ~40× funding at this holding period.** P12.6 as written leads
with the smaller term. It should lead with fees + spread and treat
funding as a correction that only becomes material if median hold grows
past several hours.

```bash
# repro
DEMO_MODE=1 .venv/bin/python /tmp/cost.py   # see §6 for the script
```

---

## 3. Finding: the two graders disagree by 3R on the same candle

A candle that touches both stop and target is intrinsically ambiguous
without tick data. The repo has a documented rule for this — and one of
the two graders does not follow it.

```
BACKTESTER  same-bar SL+TP  ->  PARTIAL_WIN  +2.0R
PAPER       same-bar SL+TP  ->  STOP_LOSS    -1.0R   (ambiguous: True)
```

- `data/paper_trading.py:88` — *"A candle that reaches both levels is
  intrinsically ambiguous without tick data. We mark it as ambiguous and
  choose the stop (conservative outcome)."* Correct.
- `data/backtester.py` `_evaluate()` — resolves with
  `if first_sl is not None and (first_tp1 is None or first_sl < first_tp1)`.
  On a tie `first_sl < first_tp1` is **false**, so control falls through
  to the TP branch. **The optimistic outcome wins.**

This is not a hypothetical inconsistency. `docs/BACKTRADER_REVIEW.md`
§7.1 cites this very rule as a reason not to adopt another engine:

> *"Any bar-by-bar engine resolves ambiguous same-candle SL/TP touches
> implicitly. SKY's rule is written down and tested (conservative: SL
> wins). Importing another engine's default would create a number we
> would have to audit, not one we defined."*

The rule is written down. The backtester does not implement it. The
argument against Backtrader currently applies to SKY's own grader.

**Why it has stayed invisible:** I instrumented `_evaluate()` over 876
decided synthetic trades and counted **0 ties**. Random-walk candles are
too small to span a 1R stop and a 2R target in one bar. On real BTC data
— wicks, liquidations, news candles — ties are common, and every one of
them is currently graded 3R too generous.

```bash
DEMO_MODE=1 .venv/bin/python /tmp/tie.py     # see §6
```

---

## 4. Finding: the sample count is inflated roughly 30×

Walk-forward grading uses `step=3` with a 24h horizon on 15m bars. A 24h
horizon is 96 bars; stepping 3 bars at a time means each trade's
evaluation window **overlaps the next ~32 samples**.

Overlapping samples are not independent observations:

| reported | effective (≈ ÷32) |
|---|---|
| 384 decided (P12.3 run) | **~12** |
| 38,439 decided (P11 grind) | **~1,200** |

This was the reasoning that killed annualised Sharpe during P12.3
(`sqrt(trades_per_year)` inflated 0.269 → 36.74). But the overlap does
not only distort annualisation — it silently narrows **every** confidence
interval the project reports, and it inflates the graduation sample
floor (`min_decided`, `CALIBRATE_MIN_N`) against which "enough data" is
judged.

Nothing in the repo currently divides by the overlap factor.

---

## 5. Proposal: reorder the ladder

Current plan: **P12.4** (quality score) → P12.5 → P12.6 (net-of-costs) →
P12.7.

**The objection: P12.4 scores a fiction.** A quality score 0–100 grading
the robustness of a gross, cost-free expectancy measured on a random walk
is a precise measurement of the wrong object. Scoring should come after
the thing being scored is real.

Proposed order:

| # | step | why it comes here | size |
|---|---|---|---|
| **1** | **Unify the tie-break** — backtester adopts the documented stop-first rule | one condition + a test; removes a 3R optimism that only appears on real data. Do it *before* real data lands, so the first real numbers are already honest | XS |
| **2** | **Real data.** Backfill real BTCUSDT 1m with the P10 machinery; re-run P11, P12.1, P12.3 | tells you more than P12.4–P12.7 combined. Everything downstream is uninterpretable without it | M |
| **3** | **P12.6 pulled forward, fees-first.** `E_net` becomes the number the gate reads; bar restated as **+0.50R net** | costs are −0.12R, ~35% of current gross expectancy. Fees ≫ funding at 1.8h hold | M |
| **4** | **Effective sample size** in the scorecard — divide by overlap, widen intervals | cheap, and it corrects a ~30× overstatement in every report | S |
| **5** | P12.4 / P12.5 as originally specced | now scoring something real | M |
| **6** | Micro-live tier at trivial size | slippage, partial fills and latency cannot be simulated into existence — only measured | L |

Steps 1 and 4 are small. Step 2 is the one that actually matters.

---

## 6. Two strategic notes

### 6.1 The bar may be unreachable as currently stated

`≥ +0.50R expectancy, > 55% win rate, PF ≥ 1.5` is a **professional-grade**
standard — a 55% win rate at positive expectancy is genuinely hard, and
the three conditions must hold simultaneously. Stated *gross*, on
cost-blind data, it combines "very demanding" with "measuring the wrong
number."

The risk is a gate that can never open, which is exactly when the
temptation to loosen it arrives — and it arrives at the moment of maximum
sunk cost. Better to restate the bar as **+0.50R net** now, while nobody
wants anything from it, than to renegotiate it later under pressure.

Restating gross → net is **not** loosening. It is making the bar mean
what it was always intended to mean.

### 6.2 The scorecard's first job is pruning, not reporting

P12.3's own output:

> **Breakout Buy: −0.473R over 74 trades, PF 0.426.**

Removing one losing setup is a larger and far cheaper expectancy
improvement than the next three milestones produce. The scorecard was
built to inform decisions; its first decision is a deletion. (Caveat:
confirm on real data first — see §1 and §4. On a random walk, "which
setup is worst" is close to noise.)

---

## 7. Repro scripts

Both scripts referenced above are throwaway diagnostics, reproduced here
so the findings can be re-checked without re-deriving them.

**Same-bar tie direction (§3):**

```python
import sys; sys.path.insert(0, '.')
import pandas as pd
from data.backtester import _evaluate
from data.paper_trading import exit_event

df = pd.DataFrame([
    {"ts": 0,      "open": 100, "high": 100, "low": 100, "close": 100},
    {"ts": 900000, "open": 100, "high": 112, "low":  88, "close": 100},
])
df.attrs["timeframe"] = "15m"
plan = {"entry": 100, "stop_loss": 95, "take_profits": [110],
        "action": "BUY", "type": "X", "confidence": 80}

gp = _evaluate(plan, df, 0, horizon_bars=1)
print("BACKTESTER ->", gp.outcome, gp.rr_achieved)          # PARTIAL_WIN 2.0
ev = exit_event({"action": "BUY", "entry": 100, "stop_loss": 95,
                 "take_profit": 110}, {"high": 112, "low": 88})
print("PAPER      ->", ev["outcome"], ev["rr_achieved"])    # STOP_LOSS -1.0
```

**Cost in R (§2)** — instrument `_evaluate` to collect `|entry−sl|/entry`
over a normal `run_backtest()`, take the median, and divide each cost
assumption by it.

---

## 8. What this document does not propose

- No change to any invariant. Never place a real exchange order.
- No adoption of Freqtrade / Hyperopt / FreqAI / Backtrader (F1–F8,
  BT1–BT8 stay decided).
- No second grader — §3 argues the *existing* grader should match its
  own documented rule, which is the opposite of adding one.
- No strategy modules, no strategy-module catalog.
- **No loosening of the graduation bar.** §6.1 argues for restating it
  gross → net, which makes it harder in practice, not easier.
- No recursive-state lookahead work — still a later milestone.
