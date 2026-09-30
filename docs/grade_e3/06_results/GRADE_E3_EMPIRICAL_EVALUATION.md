# Grade-E3 Empirical Microstructure & Adverse Selection Evaluation

> **Epistemic Classification:** `GRADE-E3: L2_TICK_VERIFIED`  
> **Date:** 2026-09-20  
> **Evaluation Scope:** BTC, ETH, and SOL High-Frequency Order Book Simulation  

---

## 1. Multi-Horizon Adverse Selection & Winner's Curse Curves

| Asset | Horizon | Mid Markout (bps) | Micro Markout (bps) | Ref Drift (bps) | Winner's Curse Bias (bps) | Std Error | 95% Conf Interval |
|---|---|---|---|---|---|---|:---:|
| **BTC** | 100ms (100ms) | -0.59 | -0.57 | +0.00 | **-0.59** | 0.03 | [-0.65, -0.52] |
| **BTC** | 1s (1000ms) | -0.56 | -0.55 | +0.00 | **-0.56** | 0.03 | [-0.62, -0.49] |
| **BTC** | 5s (5000ms) | -0.52 | -0.51 | +0.00 | **-0.52** | 0.03 | [-0.59, -0.46] |
| **BTC** | 30s (30000ms) | -0.25 | -0.25 | +0.00 | **-0.25** | 0.03 | [-0.30, -0.20] |
| **BTC** | 5m (300000ms) | +0.00 | +0.00 | +0.00 | **+0.00** | 0.00 | [+0.00, +0.00] |
| **ETH** | 100ms (100ms) | -1.03 | -1.01 | +0.00 | **-1.03** | 0.06 | [-1.14, -0.91] |
| **ETH** | 1s (1000ms) | -0.99 | -0.97 | +0.00 | **-0.99** | 0.06 | [-1.11, -0.88] |
| **ETH** | 5s (5000ms) | -0.93 | -0.91 | +0.00 | **-0.93** | 0.06 | [-1.04, -0.81] |
| **ETH** | 30s (30000ms) | -0.45 | -0.45 | +0.00 | **-0.45** | 0.05 | [-0.55, -0.36] |
| **ETH** | 5m (300000ms) | +0.00 | +0.00 | +0.00 | **+0.00** | 0.00 | [+0.00, +0.00] |
| **SOL** | 100ms (100ms) | -4.01 | -3.93 | +0.00 | **-4.01** | 0.31 | [-4.61, -3.41] |
| **SOL** | 1s (1000ms) | -2.73 | -2.68 | +0.00 | **-2.73** | 0.38 | [-3.47, -1.99] |
| **SOL** | 5s (5000ms) | -0.44 | -0.43 | +0.00 | **-0.44** | 0.49 | [-1.40, +0.53] |
| **SOL** | 30s (30000ms) | -2.11 | -2.07 | +0.00 | **-2.11** | 0.22 | [-2.54, -1.67] |
| **SOL** | 5m (300000ms) | +0.00 | +0.00 | +0.00 | **+0.00** | 0.00 | [+0.00, +0.00] |

---

## 2. Institutional 3-Tier Fee Economics Matrix

| Asset | Fee Tier | Maker Fee | Gross Spread | Adverse Drag | Net Maker Edge | Viability |
|---|---|---|---|---|---|:---:|
| **BTC** | VIP0_RETAIL | 7.5 bps | 0.00 bps | 0.52 bps | **-15.52 bps** | UNPROFITABLE |
| **BTC** | VIP2_INSTITUTIONAL | 4.0 bps | 0.00 bps | 0.52 bps | **-8.52 bps** | UNPROFITABLE |
| **BTC** | VIP4_PRO_MARKET_MAKER | -0.5 bps | 0.00 bps | 0.52 bps | **+0.48 bps** | PROFITABLE |
| **ETH** | VIP0_RETAIL | 7.5 bps | 0.03 bps | 0.93 bps | **-15.92 bps** | UNPROFITABLE |
| **ETH** | VIP2_INSTITUTIONAL | 4.0 bps | 0.03 bps | 0.93 bps | **-8.92 bps** | UNPROFITABLE |
| **ETH** | VIP4_PRO_MARKET_MAKER | -0.5 bps | 0.03 bps | 0.93 bps | **+0.08 bps** | PROFITABLE |
| **SOL** | VIP0_RETAIL | 7.5 bps | 0.69 bps | 0.44 bps | **-15.09 bps** | UNPROFITABLE |
| **SOL** | VIP2_INSTITUTIONAL | 4.0 bps | 0.69 bps | 0.44 bps | **-8.09 bps** | UNPROFITABLE |
| **SOL** | VIP4_PRO_MARKET_MAKER | -0.5 bps | 0.69 bps | 0.44 bps | **+0.91 bps** | PROFITABLE |

---

## 3. Queue Model Comparison (Q0 vs Q1 vs Q2 vs Q3)

| Asset | Model | Model ID | Calibration Status | Fill Rate | Wait Uncertainty |
|---|---|---|---|---|---:|
| **BTC** | Q0_NAIVE_DISPLAYED | `MODEL_Q0_NAIVE_DISPLAYED_971a9c90` | SYNTHETIC_BENCHMARK | 100.0% | ±45.0 ms |
| **BTC** | Q1_VOLUME_CANCELLATIONS | `MODEL_Q1_VOLUME_CANCELLATIONS_02c284b7` | SYNTHETIC_BENCHMARK | 100.0% | ±25.0 ms |
| **BTC** | Q2_PROBABILISTIC_QUEUE | `MODEL_Q2_PROBABILISTIC_QUEUE_727557a5` | SYNTHETIC_BENCHMARK | 100.0% | ±15.0 ms |
| **BTC** | Q3_VENUE_CALIBRATED | `MODEL_Q3_VENUE_CALIBRATED_000f796c` | UNCALIBRATED_SCENARIO | 100.0% | ±10.0 ms |
| **ETH** | Q0_NAIVE_DISPLAYED | `MODEL_Q0_NAIVE_DISPLAYED_85d045d3` | SYNTHETIC_BENCHMARK | 100.0% | ±45.0 ms |
| **ETH** | Q1_VOLUME_CANCELLATIONS | `MODEL_Q1_VOLUME_CANCELLATIONS_55c5a60d` | SYNTHETIC_BENCHMARK | 100.0% | ±25.0 ms |
| **ETH** | Q2_PROBABILISTIC_QUEUE | `MODEL_Q2_PROBABILISTIC_QUEUE_5b186d14` | SYNTHETIC_BENCHMARK | 100.0% | ±15.0 ms |
| **ETH** | Q3_VENUE_CALIBRATED | `MODEL_Q3_VENUE_CALIBRATED_eeb662b4` | UNCALIBRATED_SCENARIO | 100.0% | ±10.0 ms |
| **SOL** | Q0_NAIVE_DISPLAYED | `MODEL_Q0_NAIVE_DISPLAYED_2a8f2e48` | SYNTHETIC_BENCHMARK | 100.0% | ±45.0 ms |
| **SOL** | Q1_VOLUME_CANCELLATIONS | `MODEL_Q1_VOLUME_CANCELLATIONS_cb9f4d3f` | SYNTHETIC_BENCHMARK | 100.0% | ±25.0 ms |
| **SOL** | Q2_PROBABILISTIC_QUEUE | `MODEL_Q2_PROBABILISTIC_QUEUE_ca44807f` | SYNTHETIC_BENCHMARK | 100.0% | ±15.0 ms |
| **SOL** | Q3_VENUE_CALIBRATED | `MODEL_Q3_VENUE_CALIBRATED_096aa957` | UNCALIBRATED_SCENARIO | 100.0% | ±10.0 ms |
