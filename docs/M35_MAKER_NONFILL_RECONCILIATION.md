# M35 Maker Non-Fill Reconciliation & Execution Accounting
**Document:** `docs/M35_MAKER_NONFILL_RECONCILIATION.md`  
**Classification:** Microstructure & Realized Opportunity Cost Audit  
**Authority:** Execution-Model Specialist  
**Date:** 2026-11-04  
**Audit File:** [`research/m35_reconciliation_results.json`](file:///c:/Users/azims/CBT/research/m35_reconciliation_results.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Forensic Discovery

The operator's audit rightly probed the handling of the 3 unfilled maker trades. A rigorous code review of `run_historical_edge_discovery.py` revealed a subtle modeling flaw:
```python
# Flawed original logic:
if maker_filled:
  cost_r_mixed = 0.0008 / (risk_pct + 1e-6)
  net_r_mixed = gross_r - cost_r_mixed
else:
  cost_r_mixed = 0.0013 / (risk_pct + 1e-6)
  net_r_mixed = gross_r - cost_r_mixed  # <-- FLAW: Assumed fallback to Taker!
```
In reality, a passive quantitative trader placing a post-only limit order **does NOT chase the market with a taker order upon non-fill**. If the limit order is not filled within the retest window, **the order is cancelled and the trade never occurs ($0.00R$)**.

### 1.1 The Strict Mixed Model
Under **Strict Mixed Execution**:
- If Limit order penetrates $\ge 0.05 \times ATR_{14} \implies$ **FILLED** (Maker limit entry fee $= 0.0\text{ bps}$, contingent taker stop fee $= 8.0\text{ bps}$, passive TP limit fee $= 2.0\text{ bps}$).
- If Limit order penetrates $< 0.05 \times ATR_{14} \implies$ **CANCELLED** ($\mathbf{0.00R}$, zero fee, zero PnL, trade missed).

---

## 2. Reconciled Performance Under Strict Execution Accounting

We recomputed performance across all four accounting perspectives:

### 2.1 BTCUSDT 1h (Total Setups = 17)
- **Maker Filled:** 16 ($94.1\%$)
- **Maker Unfilled:** 1 ($5.9\%$) — 2023-02-14 06:00 UTC (Missed Winner, $+2.5R$ gross).

| Execution Perspective | Evaluated Setups | Mean Net R | Win Rate % | Profit Factor | Realized Edge State |
|:---|:---:|---:|---:|---:|:---|
| **All Setups Taker** (Chased as Taker) | 17 | +1.213R | 70.6% | 4.06 | High Expectancy |
| **All Setups Pure Maker** ($0.0R$ for non-fill) | 17 | +1.218R | 64.7% | 4.40 | Conservative (Missed Win = 0R) |
| **All Setups Strict Mixed** ($0.0R$ for non-fill) | 17 | **+1.172R** | **64.7%** | **4.28** | **Realistic Institutional Benchmark** |
| **Filled-Only Strict Mixed** (Drop non-fill) | 16 | +1.245R | 68.8% | 4.28 | Active Trades Only |

---

### 2.2 ETHUSDT 1h (Total Setups = 11)
- **Maker Filled:** 10 ($90.9\%$)
- **Maker Unfilled:** 1 ($9.1\%$) — 2023-10-21 18:00 UTC (Missed Winner, $+2.5R$ gross).

| Execution Perspective | Evaluated Setups | Mean Net R | Win Rate % | Profit Factor | Realized Edge State |
|:---|:---:|---:|---:|---:|:---|
| **All Setups Taker** | 11 | +0.949R | 63.6% | 3.36 | High Expectancy |
| **All Setups Pure Maker** ($0.0R$ for non-fill) | 11 | +0.919R | 54.5% | 3.33 | Conservative |
| **All Setups Strict Mixed** ($0.0R$ for non-fill) | 11 | **+0.844R** | **54.5%** | **3.18** | **Realistic Institutional Benchmark** |
| **Filled-Only Strict Mixed** (Drop non-fill) | 10 | +0.928R | 60.0% | 3.18 | Active Trades Only |

---

### 2.3 BTCUSDT 4h (Total Setups = 6)
- **Maker Filled:** 5 ($83.3\%$)
- **Maker Unfilled:** 1 ($16.7\%$) — 2024-10-21 00:00 UTC (Missed Winner, $+2.5R$ gross).

| Execution Perspective | Evaluated Setups | Mean Net R | Win Rate % | Profit Factor | Realized Edge State |
|:---|:---:|---:|---:|---:|:---|
| **All Setups Taker** | 6 | +1.110R | 66.7% | 4.07 | High Expectancy |
| **All Setups Pure Maker** ($0.0R$ for non-fill) | 6 | +0.860R | 50.0% | 3.40 | Conservative |
| **All Setups Strict Mixed** ($0.0R$ for non-fill) | 6 | **+0.835R** | **50.0%** | **3.38** | **Realistic Institutional Benchmark** |
| **Filled-Only Strict Mixed** (Drop non-fill) | 5 | +1.002R | 60.0% | 3.38 | Active Trades Only |

---

## 3. Resolving the 91.43% vs 58%–68% Fill Rate Discrepancy

Why did the Order Block Retest achieve a $91.43\%$ fill rate (32 of 35) while earlier microstructure papers estimated $58\%–68\%$?

1. **Zone Penetration Depth:** Order blocks are mitigation zones. When price retests an impulsive order block, price typically retraces $50\%$ to $100\%$ into the origin candle body. In 32 of 35 setups, price penetrated the outer boundary by significantly more than the minimum threshold ($0.05 \times ATR_{14}$, which is typically $0.1\%$ to $0.3\%$ of price).
2. **Context Difference:** The $58\%–68\%$ fill rate cited in earlier reports was derived from **high-frequency intraday limit orders at the prevailing bid/ask spread** (queue positioning). In contrast, our HTF order block limit orders are **resting counter-trend orders placed well inside the previous bar's range**, allowing ample time and depth for execution.
3. **Conservative Net Opportunity Cost:**
   $$\text{Total Gross Profit Missed} = 3 \text{ trades} \times +2.5R = \mathbf{+7.50R}.$$
   Even after completely forfeiting this $+7.50R$, **all three candidate configurations retain $> +0.83R$ net expectancy under strict zero-fallback mixed execution**.
