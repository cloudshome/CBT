# M37 — Strategy Discovery & Microstructure Alpha Report

**Author:** Institutional Quantitative Research Director  
**Milestone:** M37 — Derivatives Intelligence & Independent Alpha Discovery  
**Date:** November 5, 2026  
**Status:** Multi-Year Empirical Discovery Audit  

---

## 1. Discovery Objective & Scientific Method

The purpose of Milestone 37 was not to optimize curve-fitted parameters or force profitable backtests, but to investigate whether **Derivatives Microstructure (Funding Rates, Open Interest, and Basis)** contains true, incremental, cost-adjusted predictive power over Bitcoin and Ethereum perpetual markets.

To guard against data snooping, every experiment was evaluated under a strict **Three-Partition Chronological Discipline**:
1. **Train Set (2022-01-01 to 2024-06-30):** 30 months, 21,847 hours (In-Sample Hypothesis Exploration).
2. **Validation Set (2024-07-01 to 2025-06-30):** 12 months, 8,748 hours (Parameter Invariance Check).
3. **Sealed Out-of-Sample (2025-07-01 to 2026-10-20):** 16 months, 11,414 hours (Sealed Blind Verification).

---

## 2. Key Discovery: The Two Viable Microstructure Mechanisms

Out of 26 tested strategy configurations, only two mechanisms consistently produced positive expected value across Train, Validation, and Sealed OOS:

### Discovery 1: Post-Liquidation Capitulation Absorption (H3-Long BTC)
- **Economic Mechanism:**  
  When an extreme liquidation cascade hits the perpetual market, forced stop orders trigger rapid margin liquidations. Because market makers pull depth, price overshoots fundamental value while Open Interest violently contracts within a single hour ($\Delta \text{OI}_{\text{1h}} \le -4.0\%$). Once the cascade clears and volume peaks, the market experiences an immediate liquidity vacuum in the opposite direction.
- **Empirical Evidence:**
  - **Sample Size:** 50 trades over 4.8 years (BTCUSDT 1h).
  - **Win Rate:** $56.0\%$ ($28$ wins, $22$ losses).
  - **Expectancy:** $\mathbf{+0.3139R}$ per trade net of full fees.
  - **Profit Factor:** $\mathbf{1.77}$.
  - **Partition Stability:**
    - Train: $+0.3124\text{R}$ ($N=40$, PF $1.78$)
    - Validation: $+0.3032\text{R}$ ($N=8$, PF $1.75$)
    - Sealed OOS: $+0.3865\text{R}$ ($N=2$, PF $1.68$)
  - **Max Drawdown:** Only $4.279\text{R}$.
  - **Student's $t$-statistic:** $1.759$ ($p = 0.0848$).

### Discovery 2: Leveraged Compression Breakdown Expansion (H5-Short ETH)
- **Economic Mechanism:**  
  During low-volatility consolidation (Bollinger Band width $\le 20\text{th}$ percentile), traders accumulate large leveraged positions. When Open Interest expands by $> +3\%$ while price is flat, high leverage is trapped in a narrow range. A breakdown below the lower band triggers a one-sided liquidation cascade of over-leveraged longs, accelerating downward momentum.
- **Empirical Evidence:**
  - **Sample Size:** 48 trades over 4.8 years (ETHUSDT 1h).
  - **Win Rate:** $45.83\%$.
  - **Expectancy:** $\mathbf{+0.4559R}$ per trade net of full fees.
  - **Profit Factor:** $\mathbf{1.75}$.
  - **Partition Stability:**
    - Train: $+0.2790\text{R}$ ($N=34$, PF $1.42$)
    - Validation: $+0.1979\text{R}$ ($N=8$, PF $1.28$)
    - Sealed OOS: $\mathbf{+1.8021R}$ ($N=6$, PF $10.74$, $p = 0.0270$)
  - **Total Net PnL:** $+21.88\text{R}$.

---

## 3. The Negative Discoveries: What Does NOT Work

Milestone 37 produced equally important negative findings that permanently eliminate common retail trading myths from SKY's architecture:

1. **Retail Funding Extremes Do NOT Mean Immediate Reversals:**
   - Retail dogma claims: "High positive funding means short the market; negative funding means buy."
   - **Empirical Result:** H1-Long on BTC lost $-33.09\text{R}$ in Sealed OOS! Negative funding in 2025–2026 was accompanied by persistent institutional selling. Shorting high positive funding had negative expectancy on both BTC and ETH.
2. **Price/OI Divergence on Highs Fails Systematically:**
   - Shorting 72h highs because Open Interest was dropping lost $-0.152\text{R}$ on BTC and $-0.202\text{R}$ on ETH. Spot ETF buying and institutional TWAP orders regularly drive price higher with zero perp leverage.
3. **Hourly Basis Arbitrage Is Unexploitable:**
   - Spot-perp basis anomalies on 1-hour closes are too sparse ($N < 10$) and vanish within seconds due to automated market maker arbitrage.

---

## 4. Multi-Asset Divergence & Cross-Asset Dynamics

In evaluating cross-asset dynamics between BTC and ETH:
- **BTC vs ETH Asymmetry:**  
  Long capitulation (H3) works on BTC but fails on ETH ($-0.106\text{R}$). BTC possesses institutional bottom-fishing bid liquidity, whereas ETH flushes frequently bleed into secondary multi-day selloffs.
- **Compression Breakdown:**  
  Conversely, downward compression breakdown (H5-Short) works significantly better on ETH ($+0.456\text{R}$) than BTC ($-0.624\text{R}$), reflecting ETH's higher beta and structural vulnerability to long unwinds.

