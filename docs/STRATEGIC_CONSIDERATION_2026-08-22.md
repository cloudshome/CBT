# SKY — Strategic Consideration on the Accio Review (Second Opinion)

> **Status:** advisory — a decision-support document, not yet an accepted plan.
> **Date:** 2026-08-22
> **Subject:** a critical second opinion on the Accio review of SKY, and a
> recommended priority ordering that differs from the review's.
> **Reviewed against:** the SKY repo at the current checkout (v2.55.0 era) —
> `web/app.py` = **10,083 lines**, `main.py` = **3,334 lines**,
> `config.py` default `EXECUTION_MODEL = "none"`, MCP server(s), dashboard,
> paper-trading gate, and the 1,324-test suite.
> **One-line verdict:** SKY is a strong **research/validation platform** with
> ~8/10 engineering maturity, but **not yet** a proven live-trading engine
> (~6.5–7/10 trading maturity). The right next milestone is not "more trading
> intelligence" — it is **proving whether the existing intelligence survives
> increasingly realistic conditions.**

---

## TL;DR — the answer in 30 seconds

1. **SKY looks increasingly serious as a research/validation platform.** The
   no-lookahead grading, stop-first handling, cost inclusion, unified risk
   gate, human approval before paper trading, and AST protection against
   `shift(-n)` look-ahead are exactly the checks that separate real backtests
   from fake ones.

2. **But software quality ≠ trading profitability.** Engineering maturity and
   a validated *edge* are different claims. The review already says this, and
   it is the single most important caveat to keep.

3. **The review's findings are good; its priority order is not.** Do not
   follow the review's ordering blindly. Trading-validity work (realistic
   execution, out-of-sample, walk-forward, regime testing) outranks dashboard
   beauty, UI refactoring, and security hardening.

4. **The philosophy to protect most:** SKY reports **"no positive edge"**
   rather than tuning parameters to fake a green result. Keep that. It is more
   valuable than adding more AI agents.

---

## Ratings

| Dimension | Score | Why |
|---|---|---|
| **Engineering maturity** | ~8 / 10 | Large, coherent, tested; 1,324 offline tests; MCP; dashboard; risk gates. |
| **Trading-system maturity** | ~6.5–7 / 10 | Strong validation discipline, but live-edge proof not yet established. |
| **Production-readiness (real money)** | **not yet** | Graduation gate is correct; live capital is not justified before more realistic validation. |

**The distinction that matters:** SKY looks increasingly like a serious
trading *research/validation* platform, but that does **not** prove its edge is
profitable in live markets. The review is good precisely because it refuses to
conflate these.

---

## 1. What the review got RIGHT

### 1.1 The trading-validation architecture is the strongest asset — protect it

The review confirmed the properties that separate honest backtests from
overfit fantasy:

- **no look-ahead in grading** — outcomes are graded only *after* the signal bar;
- **stop-first handling** when SL/TP occur on the same candle;
- **fees / spread / funding included** in P&L;
- **unified risk gate** applied across the system;
- **human approval before paper trading**;
- **AST protection against `shift(-n)` look-ahead**.

**Action:** do **not** refactor the trading engine purely for cleanliness.
Preserve its behavior with regression tests *before* any architectural change.
The engine is the crown jewel; treat it as such.

### 1.2 `web/app.py` (10,083 lines) is the biggest maintainability debt

Routing, business logic, HTML, CSS, and thousands of lines of JavaScript mixed
in one file is a legitimate target — **but do not rewrite it in one shot.**

**Recommended structure (extract one domain at a time):**

```text
web/
├── app.py
├── routes/
│   ├── dashboard.py
│   ├── signals.py
│   ├── trading.py
│   ├── research.py
│   ├── system.py
│   └── api.py
├── templates/
├── static/
│   ├── css/
│   └── js/
└── services/
```

After **every** extraction:

```text
tests → behavior comparison → CI → commit
```

This keeps SKY stable while it grows. Move functionality **one domain at a
time**; never land a 10K-line rewrite as a single change.

### 1.3 The O(N²) backtester is potentially more important than the UI

Each walk step recomputing indicators/structure from bar 0 yields an **O(N²)**
process. This is **not merely** a software optimization — it is a research
throughput problem.

SKY's stated goals imply a huge experiment space:

```text
BTC · ETH · XAU        ×   1m · 5m · 15m · 1h · 4h
×  multiple years      ×   multiple market regimes      ×  multiple strategies
```

If each experiment is painfully slow, fewer experiments get run — and fewer
experiments means weaker validation. Put this **very high** on the roadmap.

### 1.4 The execution-model criticism is the most important trading finding

SKY currently defaults to `EXECUTION_MODEL = "none"`, and plans can fill at the
exact signal close. That is technically not look-ahead, but it is **optimistic**.

```text
Signal generated  →  candle closes  →  SKY assumes exact-close fill  →  SL/TP
```

Real trading is strictly less favorable:

```text
candle closes → signal detected → network/API latency → order submitted
  → order accepted → actual fill → slippage
```

For the eventual BTC-futures system, the simulator should model:

```text
signal close + latency + spread + slippage + fees + funding + partial-fill possibility
```

The review's recommendation to move toward `slip` / next-bar execution is
therefore **very sensible**.

---

## 2. Recommended priority order (differs from the review)

The report has many good findings, but its priority ordering should not be
followed blindly. Recommended prioritization:

### 🔴 P0 — Trading validity (do this first)

1. **Realistic execution** — next-bar / latency / slippage / fees / funding.
2. **Out-of-sample validation.**
3. **Walk-forward testing.**
4. **Regime testing:**

   ```text
   bull · bear · sideways
   high volatility · low volatility
   news / macro
   ```

5. **Paper trading** (human-approved, already gated).
6. **Compare the full ladder:**

   ```text
   Backtest → Out-of-sample → Paper → Live tiny capital
   ```

This is more important than making the dashboard beautiful.

### 🟠 P1 — Performance

**Backtester:** turn the O(N²) walk into:

```text
precompute indicators → incremental structure → walk-forward evaluation
```

This dramatically raises research throughput, which directly strengthens
validation.

### 🟡 P2 — Architecture

Split the two largest maintainability debts:

```text
web/app.py   (10,083 lines)
main.py      ( 3,334 lines)
```

One domain at a time, with `tests → behavior compare → CI → commit` per step.

### 🟢 P3 — Security / hardening

Worthwhile, but they do **not** determine whether the strategy has an edge:

- HTML escaping
- SQLite concurrency
- SSE worker consumption
- force-approve alarm
- remote no-TLS escape hatch
- UTC signal IDs
- systemd restart limits

---

## 3. The philosophy worth keeping above all else

From the review, this is the sentence to protect:

> SKY will report **"no positive edge"** rather than tune parameters to fake a
> green result.

SKY must be allowed to say:

```text
BTC 15m · Setup X
Sample: 8,423
Expectancy: -0.07R
After fees: -0.11R
VERDICT: NO EDGE
```

instead of producing:

```text
AI optimized parameters → +0.42R → BUY!!!
```

That is exactly how a research engine should behave. Preserve the honesty.

---

## 4. What NOT to do yet

**Do not** bolt on a large external AI/agent stack right now:

```text
SKY
 ├── OpenHands
 ├── Dify
 ├── LibreChat
 ├── multiple LLMs
 ├── autonomous agents
 ├── Discord agent
 └── 50 plugins
```

until the core statistical validation is finished. The risk is:

> **AI complexity > trading intelligence**

Instead, keep agents **around** a deterministic core — never replacing it:

```text
                     SKY CORE
                        │
        ┌───────────────┴───────────────┐
        ↓                               ↓
  Market / Data                 Research Engine
        ↓                               ↓
  Indicators                     Backtest
  Structure                     Walk-forward
  Orderflow                     Risk
        │                               │
        └───────────────┬───────────────┘
                        ↓
                   Validation
                        ↓
                  Paper Trading
                        ↓
                  Human Approval
                        ↓
                   Tiny Live
```

---

## 5. The immediate objective change

Shift the project's near-term goal from:

> **"Build more trading intelligence."**

to:

> **"Prove whether existing trading intelligence survives increasingly
> realistic conditions."**

That points to a single next milestone:

### SKY P13 — Edge Validation

```text
Historical data
      ↓
No-lookahead validation
      ↓
Costs
      ↓
Slippage
      ↓
Walk-forward
      ↓
Out-of-sample
      ↓
Regime segmentation
      ↓
Monte Carlo
      ↓
Paper trading
      ↓
Expectancy stability
      ↓
Risk-adjusted performance
```

Only after that should SKY decide:

```text
EDGE CONFIRMED
```

or

```text
NO EDGE
```

---

## 6. Final verdict

The Accio review is good — **~8.5/10 as a review**. It correctly sees that
SKY's biggest problem is not "bad trading code." It is that the project is now
large enough that **engineering debt and validation throughput are becoming the
bottleneck**.

The three things to attack first:

1. **Realistic execution model**
2. **O(N²) backtest performance**
3. **Evidence-driven walk-forward / out-of-sample validation**

Then refactor `web/app.py` and `main.py`.

And above all:

> **Don't let SKY become an impressive software project that happens to have a
> trading strategy. Make it a rigorous trading research engine that happens to
> have sophisticated software around it.**

---

## 7. Decisions pending

For this consideration to become actionable, the following still need to be
decided (each should be a tracked item, not this document):

- [ ] **Execution model:** confirm the move from `EXECUTION_MODEL="none"` →
      `"slip"` as the default, and define the latency/slippage/spread model.
- [ ] **Backtester:** approve an incremental / precomputed-indicator redesign
      with a performance budget (e.g. X faster) and a behavior-equivalence gate.
- [ ] **Web refactor:** ratify the `routes/ + templates/ + static/ + services/`
      layout and the per-domain extraction order (dashboard → signals → trading
      → research → system → api).
- [ ] **Milestone name:** adopt "P13 — Edge Validation" and its gate criteria
      (EDGE CONFIRMED / NO EDGE).
- [ ] **Agent scope freeze:** explicit list of external agents *not* to add
      until edge validation completes.
