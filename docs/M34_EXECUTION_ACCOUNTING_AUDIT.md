# M34 Execution Accounting & Maker Reconciliation Audit
**Document:** `docs/M34_EXECUTION_ACCOUNTING_AUDIT.md`  
**Classification:** Microstructure & Execution Realism Audit  
**Authority:** Execution-Model Specialist  
**Date:** 2026-11-04  
**Audit Source:** [`research/m34_trade_level_ledger.jsonl`](file:///c:/Users/azims/CBT/research/m34_trade_level_ledger.jsonl)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Reconciliation of Prior Discrepancy

A critical mandate of the M34 Directive was resolving the glaring contradiction in prior reports:
- *One section reported a maker fill rate of 58%–68%.*
- *Another section reported `Non-Fill Opportunity Cost: 0.00R (no fill missed)`.*

### The Forensically Reconstructed Reality:
We audited all 35 `ORDER_BLOCK_RETEST` setups across BTC 1h, BTC 4h, ETH 1h, and ETH 4h using direction-aware penetration:
$$\text{Long Fill Condition:} \quad Low_t \le \text{Limit Entry} - 0.05 \times ATR_{14}(t)$$
$$\text{Short Fill Condition:} \quad High_t \ge \text{Limit Entry} + 0.05 \times ATR_{14}(t)$$

### Exact Reconciled Accounting:
- **Total Historical Setups Submitted:** 35
- **Maker Filled Setups ($\ge 0.05 \times ATR$):** 32 ($91.43\%$)
- **Maker Non-Filled Setups ($< 0.05 \times ATR$):** 3 ($8.57\%$)
- **Breakdown of the 3 Non-Filled Setups:**
  1. `BTCUSDT 4h` (Timestamp `1729468800000`): Price touched limit but lacked $0.05 \times ATR$ penetration; subsequently reached `TAKE_PROFIT` (+2.5R gross).
  2. `BTCUSDT 1h` (Timestamp `1676386800000`): Price touched limit but lacked penetration; subsequently reached `TAKE_PROFIT` (+2.5R gross).
  3. `ETHUSDT 1h` (Timestamp `1697911200000`): Price touched limit but lacked penetration; subsequently reached `TAKE_PROFIT` (+2.5R gross).
- **Non-Fill Opportunity Cost:**
  - **Missed Winners:** 3 trades $\times +2.5R = \mathbf{+7.50R}$ gross profit missed.
  - **Avoided Losers:** 0 trades ($0.00R$).
  - **Net Non-Fill Opportunity Cost:** $\mathbf{+7.50R}$ total ($\approx \mathbf{0.214R}$ per setup across all 35 setups).

**Conclusion:** The claim that `Non-Fill Opportunity Cost: 0.00R` was false. The conservative penetration requirement caused 3 profitable trades to be missed. However, **even with these 3 winners excluded, the maker fill strategy still delivers $+1.22R$ net expectancy on BTC 1h**.

---

## 2. Versioned 3-Tier Friction Models

All experiments evaluate 3 explicit friction tiers:

### 2.1 Taker Model (High Friction Benchmark)
- **Entry:** 5.0 bps fee + 1.5 bps half-spread crossing = 6.5 bps
- **Exit:** 5.0 bps fee + 1.5 bps half-spread crossing = 6.5 bps
- **Total Round-Trip Friction:** $13.0\text{ bps}$ ($0.0013$)
- **Formula in R-Units:**
  $$\text{Cost}_R = \frac{0.0013}{\text{Risk}_{\%}}, \quad \text{where } \text{Risk}_{\%} = \frac{|\text{Entry} - \text{Stop}|}{\text{Entry}}$$
  On 1H/4H candles, $\text{Risk}_{\%} \approx 2.5\% \implies \text{Cost}_R \approx 0.052R$.

### 2.2 Maker Model (Passive Post-Only Limit)
- **Entry:** 0.0 bps fee + 0.0 bps spread (passive liquidity provider)
- **Take-Profit Exit:** 2.0 bps fee (passive limit fill)
- **Stop-Loss Exit:** 5.0 bps taker fee + 2.0 bps adverse spread slippage = 7.0 bps
- **Adverse Selection Penalty:** Fixed $-0.03R$ applied to every filled maker trade to model post-fill adverse flow.
- **Non-Fill Rule:** If penetration $< 0.05 \times ATR$, trade is marked as non-filled ($0.00R$).

### 2.3 Mixed Execution Model (Target Production Architecture)
- **Entry:** Passive post-only limit entry at order block retest boundary. If filled, fee $= 0.0\text{ bps}$.
- **Stop Exit:** Contingent taker stop order triggering market execution with 5.0 bps fee + 3.0 bps slippage buffer ($8.0\text{ bps}$ total).
- **Take-Profit Exit:** Passive limit exit resting at $+2.5R$ target ($2.0\text{ bps}$ fee).

---

## 3. Same-Candle Ambiguity Resolution

When a single historical candle's range encompasses both the stop-loss and take-profit levels:
- **Zero Optimism Policy:** The simulation enforces a **Stop-First Assumption**:
  $$\text{If } Low_t \le Stop \text{ and } High_t \ge TP \implies \text{Trade marked as } \mathbf{STOP\_LOSS} \ (-1.0R).$$
- No lookahead intrabar guessing. Take-profit is only awarded if the candle does not breach the stop level.

---

## 4. Friction Stress Testing

We subjected the primary candidate (`BTCUSDT 1h ORDER_BLOCK_RETEST`) to friction scaling:

| Friction Scenario | Round-Trip Cost | Net Expectancy (R) | Profit Factor | Status |
|:---|:---:|:---:|:---:|:---|
| **Base Taker** | 13.0 bps | +1.220R | 4.35 | PASS |
| **Base Maker** | 2-7 bps + 0.03R adv | +1.228R | 4.38 | PASS |
| **Base Mixed** | 8.0 bps | +1.246R | 4.40 | PASS |
| **Stress 1.5x Frictions** | 19.5 bps | +1.168R | 4.12 | PASS |
| **Stress 2.5x Frictions** | 32.5 bps | +1.064R | 3.75 | PASS |
| **Extreme 5.0x Frictions** | 65.0 bps | +0.804R | 2.95 | PASS |

**Finding:** Because Higher-Timeframe (1H/4H) trade risk envelopes average $200\text{ to }400\text{ bps}$, the edge is highly robust against transaction friction spikes, maintaining $> +1.0R$ net expectancy even under $2.5\times$ stressed fees.

