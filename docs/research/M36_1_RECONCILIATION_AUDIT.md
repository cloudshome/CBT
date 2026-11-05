# SKY / CBT — M36.1 Quantitative Reconciliation Audit Report

**Auditor:** Independent Quantitative Research Auditor, Portfolio Statistician, Data Integrity Engineer  
**Audit Target:** M36.1 Portfolio Diversification Validation & Derivatives Intelligence Acquisition  
**Date of Audit:** November 5, 2026  
**Audit Invariant:** `REAL_CAPITAL_ENABLED = False` permanently locked; testnet/paper/shadow only; M18 certified surface protected (149/149 passing tests).

---

## 1. Executive Audit Summary

This independent quantitative audit was commissioned to rigorously reproduce and reconcile all reported findings, mathematical claims, and data partitions from Milestone 36.1. 

### Key Findings of the Audit:
1. **Reconciliation of Family 3 Arithmetic Contradiction:**
   - **Discrepancy:** The M36.1 report cited "98 trades" in one paragraph, "908 trades" in another, an expectancy of "-0.104R/trade", and a total loss of "-47.28R".
   - **Resolution:** A forensic audit of [`research/independent_edges_trade_ledger.jsonl`](file:///c:/Users/azims/CBT/research/independent_edges_trade_ledger.jsonl) revealed that the raw ledger strictly contains **908 BTCUSDT 1h trades**. "98" was a typographical transcription omission in Bengali prose (`৯৮` instead of `৯০৮`).
   - **Loss Discrepancy:** The raw total net loss of Family 3 across all 908 trades is **$-94.5700\text{R}$** ($-0.10415\text{R} \times 908$). The figure **$-47.285\text{R}$** represents the **allocated portfolio contribution** at a 50% equal-risk weight ($0.5 \times -94.5700\text{R} = -47.285\text{R}$). Both figures are mathematically reconciled.
2. **Reproduction of Portfolio Combination Metrics:**
   - Rebuilding all 7 portfolio configurations from the raw trade ledgers over 1,754 calendar days yielded **0.000 discrepancy** against [`research/m36_1_portfolio_results.json`](file:///c:/Users/azims/CBT/research/m36_1_portfolio_results.json).
3. **Audit of the -0.989 Downside Correlation:**
   - **Statistical Reality:** Over 1,754 calendar days, the Benchmark has only **5 negative-return days**. Within those 5 days, Family 3 was active on **exactly 1 day** (`2023-07-30`).
   - **Verdict:** The reported correlation of $-0.9895$ is driven almost entirely by a **single data point**. Excluding that single day makes the correlation undefined (`NaN`). This finding is **statistically inconclusive** and cannot be used to justify calling Family 3 a hedge or diversifier.
4. **Benchmark Reliability Audit:**
   - The Benchmark Order Block strategy has only **17 active trading days** in 1,754 days ($0.97\%$ utilization). While trade-level expectancy is strong ($+1.308\text{R}$, $p = 0.0055$), its annualized Sharpe ($1.178$) is heavily distorted by zero-return days and low sample frequency.
5. **Derivatives Data Audit:**
   - All 36 Parquet partitions (4,000 records) in [`data/store/derivatives/`](file:///c:/Users/azims/CBT/data/store/derivatives/) matched their SHA-256 digests perfectly with 0 gaps.
   - However, REST Open Interest is strictly limited to 500 hourly records (**21 days**). Multi-year OI research (2022–2026) requires bulk archive downloads from `data.binance.vision`.

---

## 2. Family 3 Arithmetic Reconciliation

### Raw Trade Ledger Breakdown (independent_edges_trade_ledger.jsonl)
| Slice | Symbol | Timeframe | Trades | Gross R | Net Strict R | Net Expectancy (R/trade) | Win Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Slice 1 (Used in M36.1)** | **BTCUSDT** | **1h** | **908** | **+39.00R** | **-94.57R** | **-0.1042R** | **44.05%** |
| Slice 2 | BTCUSDT | 4h | 209 | +25.50R | -17.42R | -0.0833R | 44.50% |
| Slice 3 | ETHUSDT | 1h | 879 | -4.50R | -98.28R | -0.1118R | 43.12% |
| Slice 4 | ETHUSDT | 4h | 205 | +12.00R | -30.15R | -0.1471R | 40.49% |
| **Total Family 3** | All | All | **2,201** | **+72.00R** | **-240.42R** | **-0.1092R** | **43.34%** |

### Mathematical Reconciliation Equation
$$\text{Raw Strategy Loss} = \sum_{i=1}^{908} R_{\text{net}, i} = -94.5700\text{R}$$
$$\text{Expectancy} = \frac{-94.5700\text{R}}{908} = -0.10415\text{R/trade}$$
$$\text{Portfolio Contribution (50\% Weight)} = 0.50 \times (-94.5700\text{R}) = \mathbf{-47.285\text{R}}$$

The Benchmark's allocated return at 50% weight is:
$$\text{Benchmark Portfolio Contribution} = 0.50 \times (+22.239\text{R}) = \mathbf{+11.120\text{R}}$$
$$\text{Total Equal-Risk Portfolio Return} = +11.120\text{R} + (-47.285\text{R}) = \mathbf{-36.165\text{R}}$$
This matches the reported `cumulative_return_r = -36.165` to three decimal places.

---

## 3. Independent Reproduction of Portfolio Combinations

Recomputed independently from raw trade logs over 1,754 calendar days (2022-01-01 to 2026-10-20):

| Configuration | Reported Return | Reproduced Return | Reported Max DD | Reproduced Max DD | Reported Sharpe | Reproduced Sharpe | Discrepancy |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. BM Alone** | +22.239R | +22.239R | 3.391R | 3.391R | +1.179 | +1.179 | **0.000** |
| **2. BM + F3 (Equal 50/50)** | -36.165R | -36.165R | 54.156R | 54.156R | -0.689 | -0.689 | **0.000** |
| **3. BM + F1 (Equal 50/50)** | -79.989R | -79.989R | 83.691R | 83.691R | -1.455 | -1.455 | **0.000** |
| **4. BM + F2 (Equal 50/50)** | -16.274R | -16.274R | 26.541R | 26.541R | -0.397 | -0.397 | **0.000** |
| **5. BM + F1 + F3** | -84.859R | -84.859R | 90.503R | 90.503R | -1.808 | -1.808 | **0.000** |
| **6. BM + F2 + F3** | -42.425R | -42.425R | 47.935R | 47.935R | -0.998 | -0.998 | **0.000** |
| **7. BM + F3 (70/30 Capped)** | -12.804R | -12.804R | 26.700R | 26.700R | -0.387 | -0.387 | **0.000** |

Every metric in [`research/M36_1_PORTFOLIO_METRIC_REPRODUCTION.json`](file:///c:/Users/azims/CBT/research/M36_1_PORTFOLIO_METRIC_REPRODUCTION.json) aligns identically with 0 discrepancies.

---

## 4. Frozen Research Classifications

To ensure quantitative discipline:
1. **M35 Benchmark Order Block (BTC 1h):** Preserved as **FROZEN HISTORICAL CANDIDATE** (+22.24R, 17 trades).
2. **Family 1 (Trend Pullback):** **CLASS F RESEARCH ONLY / REJECTED AS STANDALONE** (-79.99R portfolio drag).
3. **Family 2 (Volatility Squeeze):** **CLASS F RESEARCH ONLY / REJECTED AS STANDALONE** (-16.27R portfolio drag).
4. **Family 3 (Liquidity Sweep):** **REJECTED_AS_STANDALONE / CONDITIONAL_RESEARCH_ONLY** (-94.57R raw loss, downside correlation statistically inconclusive).
5. **Funding & OI Hypotheses H1–H6:** **UNTESTED HYPOTHESES**.

---

## 5. Audit Conclusion & Final Verdict

All arithmetic discrepancies and reporting anomalies have been forensicly diagnosed, explained, and reproduced. The system's underlying trade ledgers and portfolio engines are mathematically sound, but previous claims regarding Family 3's "downside hedging capability" must be formally retracted due to extreme small-sample fragility.

### Final Gate Verdict:
$$\mathbf{RECONCILED\ WITH\ LIMITATIONS\ —\ RESEARCH\ ONLY}$$

