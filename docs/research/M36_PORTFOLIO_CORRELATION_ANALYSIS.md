# M36 Multi-Family Correlation & Portfolio Architecture
**Document:** `docs/research/M36_PORTFOLIO_CORRELATION_ANALYSIS.md`  
**Classification:** Quantitative Portfolio Construction & Return Diversification  
**Authority:** Chief Quantitative Research Scientist  
**Date:** 2026-11-04  
**Audit File:** [`research/m36_independent_edges_manifest.json`](file:///c:/Users/azims/CBT/research/m36_independent_edges_manifest.json)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Correlation Matrix

The central mandate of the Post-M35 Directive is:
> **"Do not optimize for the highest historical profit. Optimize for independent sources of return, robustness across regimes, and low correlation with existing candidate strategies."**

We computed the monthly return correlation matrix across the **Frozen M35 Order Block Benchmark** and the **Three New Research Families** evaluated on continuous 2022–2026 BTC 1H data:

```
┌─────────────────┬───────────────┬──────────────┬──────────────┬──────────────┐
│ Return Stream   │ BENCHMARK_OB  │ FAMILY_1     │ FAMILY_2     │ FAMILY_3     │
├─────────────────┼───────────────┼──────────────┼──────────────┼──────────────┤
│ BENCHMARK_OB    │    +1.000     │    +0.338    │    +0.457    │   -0.219     │
│ FAMILY_1 (Pull) │    +0.338     │    +1.000    │    +0.173    │   -0.279     │
│ FAMILY_2 (Vol)  │    +0.457     │    +0.173    │    +1.000    │   -0.349     │
│ FAMILY_3 (Sweep)│   -0.219     │   -0.279    │   -0.349    │   +1.000     │
└─────────────────┴───────────────┴──────────────┴──────────────┴──────────────┘
```

---

## 2. Key Portfolio Construction Insights

### 2.1 The Value of Negative Correlation
- **Family 3 (Liquidity Sweep) is negatively correlated with all trend and momentum strategies**:
  - $\rho(\text{Family 3}, \text{Benchmark OB}) = \mathbf{-0.219}$
  - $\rho(\text{Family 3}, \text{Family 1}) = \mathbf{-0.279}$
  - $\rho(\text{Family 3}, \text{Family 2}) = \mathbf{-0.349}$
- **Economic Explanation:** In chopping, range-bound markets, breakout and pullback strategies get whipsawed repeatedly. In contrast, liquidity sweep strategies capitalize on these exact false breakouts to enter reversals.
- Even if a mean-reverting liquidity sweep strategy operates at near break-even ($PF \approx 1.0$), when paired with a trend strategy in an equal-risk portfolio, it drastically dampens portfolio drawdowns and increases the composite Sharpe ratio.

### 2.2 Preserving the Frozen M35 Benchmark
In strict accordance with the Post-M35 Research Directive:
- The `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` candidate configuration ($P > 0.55, \sigma < 0.55$) and its historical results remain **permanently frozen**.
- Zero parameters were tuned or modified during the execution of M36.

---

## 3. Decision Summary & Next Research Phase

| Research Track | Strategy Name | Sample Count (BTC 1h) | Full Series Net R | Correlation with Benchmark | Decision Status |
|:---|:---|:---:|:---:|:---:|:---|
| **Benchmark** | `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` | 17 | +1.172R | +1.000 | **FROZEN CANDIDATE** |
| **Track 1** | Trend Continuation & Pullback | 1,040 | -0.175R | +0.338 | **REJECTED** |
| **Track 2** | Volatility Squeeze & Expansion | 606 | -0.090R | +0.457 | **NEEDS_MORE_DATA (Regime Filter Required)** |
| **Track 3** | Liquidity Sweep & Reclaim | 908 | -0.104R | **-0.219** | **NEEDS_MORE_DATA (High-Value Diversifier)** |

### Next Step:
Proceed to **Phase 2 Data Ingestion**:
1. Ingest Binance funding rates and Open Interest for **Family 5 (Funding/OI Dislocation)**.
2. Ingest `SOLUSDT` and `BNBUSDT` for **Family 6 (Cross-Asset Relative Strength)**.
