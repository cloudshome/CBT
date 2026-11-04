# M34 Strategy Logic & Market-Structure Causality Audit
**Document:** `docs/M34_STRATEGY_CAUSALITY_AUDIT.md`  
**Classification:** Causal Architecture & Zero-Lookahead Audit  
**Authority:** Chief Quantitative Research Architect  
**Date:** 2026-11-04  
**Audit File:** [`scripts/research/run_historical_edge_discovery.py`](file:///c:/Users/azims/CBT/scripts/research/run_historical_edge_discovery.py)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary

This audit examines the exact deterministic mechanics of `ORDER_BLOCK_RETEST` to guarantee zero lookahead bias, point-in-time causality, and strict rule enforcement across the entire 4.8-year backtest.

---

## 2. Deterministic Setup Specification

### 2.1 Causal Swing Pivot Detection
- **Lookback Window:** 10 bars left, 10 bars right ($2 \times \text{lookback} = 20\text{ bars}$).
- **Confirmation Mechanism:** A swing high is confirmed at bar $i$ if and only if bar $i - 10$ was the maximum high over $[i - 20, i]$:
  $$\text{At bar } i: \quad \text{If } High[i-10] == \max(High[i-20 \dots i]) \implies SwingHigh[i] = High[i-10]$$
- **Zero Lookahead Proof:** Bar $i$ evaluates only closed past bars. Bar $i - 10$ is not labeled as a pivot until 10 subsequent bars have fully closed. No unconfirmed pivots are referenced.

### 2.2 Break of Structure (BOS) & Displacement
- **Displacement Bar ($i-1$):** Must be an impulsive candle whose range $(Close - Open)$ exceeds $1.2 \times ATR_{14}(i-1)$.
- **Structure Break:** $Close[i-1] > SwingHigh[i-3]$ (for Bullish OB) or $Close[i-1] < SwingLow[i-3]$ (for Bearish OB).

### 2.3 Order Block Selection & Boundary Definition
- **Origin Candle ($i-2$):** The last opposite-colored candle preceding the displacement bar ($Close[i-2] < Open[i-2]$ for bullish; $Close[i-2] > Open[i-2]$ for bearish).
- **Zone Boundaries:**
  - $OB_{High} = \max(Open[i-2], Close[i-2])$
  - $OB_{Low} = \min(Open[i-2], Close[i-2])$

### 2.4 Retest & Entry Condition
- At bar $i$, price must retest the zone:
  - Bullish: $Low[i] \le OB_{High}$ and $Close[i] \ge OB_{Low}$
  - Bearish: $High[i] \ge OB_{Low}$ and $Close[i] \le OB_{High}$
- **Limit Entry Price:** Set exactly at the outer boundary ($OB_{High}$ for Long, $OB_{Low}$ for Short).

### 2.5 Stop Loss, Take Profit & Risk Unit
- **Bullish Stop:** $Stop = OB_{Low} - 0.1 \times ATR_{14}(i)$
- **Bearish Stop:** $Stop = OB_{High} + 0.1 \times ATR_{14}(i)$
- **Risk Unit ($R$):** $R_{unit} = |Entry - Stop|$. Minimum filter: $R_{unit} > 0.2 \times ATR_{14}$.
- **Take Profit:** Fixed institutional $2.5R$ multiple ($Target = Entry \pm 2.5 \times R_{unit}$).

---

## 3. Position Stacking & Overlap Governance

To eliminate overlapping position bias and double-counting:
- **One-Trade-Per-Zone Policy:** When a setup triggers at bar $i$ and resolves at bar $exit\_idx$, the backtest pointer advances:
  $$i = exit\_idx$$
- No multiple concurrent positions in the same instrument/strategy.
- No duplicate entries from repeated polling.

---

## 4. Causal Verification Checklist

| Invariant Checklist | Verification Result | Traceable Source |
|:---|:---:|:---|
| Pivot lookback uses closed bars only | **VERIFIED** | Lines 137–157 |
| Displacement requires closed candle close | **VERIFIED** | Lines 305, 318 |
| OB boundary derived strictly from bar $i-2$ | **VERIFIED** | Lines 306–307, 319–320 |
| ATR uses past closed bars ($i-1$) | **VERIFIED** | Lines 125–130 |
| Same-candle stop/target ambiguity resolves stop-first | **VERIFIED** | Lines 422–442 |
| Zero future price data accessible at bar $i$ | **VERIFIED** | Replay walk-forward loop |

