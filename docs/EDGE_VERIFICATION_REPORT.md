# SKY — Out-of-Sample Quantitative Edge Verification Report (M45 Certification)

**Authoritative Hash Digest:** `59558f1`  
**Audit Timestamp:** `2026-11-12T17:23:23.484166+00:00`  
**Dataset Reference:** `data/research/datasets/derivatives_expanded_2022_2026.parquet` (125,820 bars, 1h timeframe, 2022–2026)  
**Execution Models Evaluated:**
1. **Naive SMC Baseline (M40):** Unprotected limit fades, zero orderflow confirmation, 20.5 bps taker friction.
2. **Unified M41–M43 Engine (M44):** `evaluate_ladder_tick` knife-catch guard + `AWAITING_RECLAIM` + MTF Confluence + +1.5R breakeven ratchet.
3. **M45 Refined Engine:** Passive Limit-Maker entry on `IN_ZONE_CONFIRMED` + Fee-Covered Breakeven (+0.10R) + 100% position size to TP2 (+3.1R).

---

## 1. Multi-Year Derivatives OOS Evaluation (2022–2026)

| Asset Symbol | M44 Expectancy | M45 Net Expectancy | M45 Trades ($N$) | M45 Win Rate % | M45 Profit Factor | M45 Sharpe | M45 DSR | Universe Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **BTCUSDT** | `+0.2043R` | **`+0.2648R`** | 225 | 42.2% | 1.40 | +0.153 | 0.7904 | Tier-1 Canary Approved |
| **ETHUSDT** | `+0.1830R` | **`+0.2300R`** | 207 | 42.5% | 1.35 | +0.137 | 0.6795 | Tier-1 Canary Approved |
| **SOLUSDT** | `+0.0709R` | **`+0.2843R`** | 189 | 43.4% | 1.43 | +0.167 | 0.7856 | Paper Observation Only |
| **Pooled Tier-1 Canary** | `+0.1936R` | **`+0.2481R`** | **432** | **42.4%** | **1.38** | **+0.146** | **0.9415** | **Tier-1 Canary Eligible** |
| **Pooled Multi-Asset** | `+0.1573R` | **`+0.2591R`** | **621** | **42.7%** | **1.39** | **+0.152** | **0.9908** | **Research Pooled** |

---

## 2. The 5 Mandatory CP-2 Hurdles Scorecard

| Hurdle | Standard | M45 Pooled Result | Status |
|:---|:---|:---:|:---:|
| **Hurdle 2a: Sample Size** | $N \ge 100$ executed OOS trades | $N = 621$ trades | **PASS** |
| **Hurdle 2b: Causality** | Zero look-ahead leakage | Evaluated on closed bars $t \\le \\tau$ (`causal_firewall.py`) | **PASS** |
| **Hurdle 2c: CPCV Sharpe** | Median Annualized Sharpe $\ge 1.0$ | Annualized Median Sharpe = `7.1696` | **PASS** |
| **Hurdle 2d: Deflated Sharpe** | $\\text{DSR} \\ge 0.9500$ ($p < 0.05$) | $\\text{DSR} = \\mathbf{0.9908}$ ($p = 0.0092$) | **PASS** |
| **Hurdle 2e: Friction Survival** | $E[R_{\\text{net}}] > +0.25R$, $\\text{PF} \\ge 1.45$ | $E[R] = \\mathbf{+0.2591R}$, $\\text{PF} = 1.39$ | **FELL SHORT (PF)** |

---

## 3. Constitutional Governance Decision

### Policy Decision: `BLOCKED_BY_POLICY`
1. **Mathematical Honesty Invariant:** Under M45 Maker-Reclaim & Payoff Asymmetry, the Deflated Sharpe Ratio achieved **`0.9908`** (clearing the 0.9500 hurdle at 99.08% statistical significance) across $N = 621$ trades, and Net Expectancy reached **`+0.2591R`** (clearing the +0.2500R hurdle).
2. **Profit Factor Assessment:** While Profit Factor achieved **`1.39`** (a massive turnaround from M40 baseline 0.55 and M44 baseline 1.24), it remains slightly shy of the conservative 1.45 threshold.
3. **Perimeter Status:** Checkpoint 2 (`CP-2`) status is governed fail-closed as **`BLOCKED_BY_POLICY`**. Capital Governor remains at **`TIER_0_PAPER`** until Checkpoint 3 (`CP-3`: 20 decided forward paper trades) completes.
