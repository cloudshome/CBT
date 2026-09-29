# SKY × KRONOS — Research Protocol & Validation Standard

> **Document Version:** 1.0.0 (Research Protocol)  
> **Status:** ACTIVE  
> **Standard:** P0 Zero Lookahead & Anti-Fabrication Guarantee  

---

## 1. Experimental Methodology

To determine whether Kronos provides genuine statistical value to SKY, every research run must evaluate three competing configurations on identical data and transaction cost assumptions:

### The 3-Way Ablation Benchmark
1. **Mode A — SKY Baseline:** Pure 12-layer empirical institutional alpha (SMC + CVD + VPIN + 10k Bootstrap Monte Carlo).
2. **Mode B — Kronos Standalone:** Pure autoregressive neural time-series forecasting.
3. **Mode C — SKY + Kronos Fusion:** Empirical structure filtered and modulated by neural probabilistic paths.

---

## 2. Evaluation Scorecard Metrics

### 2.1 Forecast Accuracy Metrics (Statistical Layer)
* **Directional Accuracy (DA):** $\text{DA} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(\text{sign}(\hat{y}_i) == \text{sign}(y_i))$
* **Root Mean Squared Error (RMSE):** Normalized against ATR.
* **Forecast Calibration:** Brier score on directional forecasts partitioned into 10 deciles.

### 2.2 Trading Performance Metrics (Economic Layer)
* **Mathematical Expectancy ($E$):** $E = (P_{\text{win}} \times W) - (P_{\text{loss}} \times L) - \text{Frictions}$
* **Profit Factor (PF):** $\text{Gross Profits} / \text{Gross Losses}$
* **Max Drawdown (MDD):** Peak-to-trough equity drop.
* **Sharpe & Sortino Ratios:** Annualized risk-adjusted returns net of 0.04% maker/taker fee and 1.5 bps slippage.

### 2.3 Incremental Value Delta ($\Delta$)
Kronos is only considered beneficial if:
$$\Delta \text{Expectancy} > +0.10R \quad \text{AND} \quad \Delta \text{MDD} \le 0.0\% \quad \text{AND} \quad \text{p-value} < 0.05$$

---

## 3. Walk-Forward Chronological Partitioning

```
[--- Train / Calibration (60%) ---] [--- Validation (20%) ---] [--- Out-of-Sample Test (20%) ---]
                                                                ^ Sealed (No Future Peek)
```

1. Train window: Anchor historical parameters and Platt calibration curves.
2. Validation window: Tune horizon weights and consensus threshold.
3. Out-of-Sample window: Evaluated strictly once without parameter retraining.

---

## 4. Operational Safety Constraints

* **Advisory Mode:** In all initial experiments and paper trading, Kronos runs in advisory mode.
* **Deterministic Risk Gate:** No trade may execute without passing maximum open position limits (3), single-trade risk caps (2%), and daily portfolio drawdown locks (3.0%).
