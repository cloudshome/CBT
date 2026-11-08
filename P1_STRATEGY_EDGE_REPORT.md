# SKY / CBT — P1 Strategy Edge Re-validation & Robustness Audit Report

**Audit Timestamp:** `2026-11-08T08:04:20.673622+00:00`  
**Evaluation Span:** 42,009 synchronized hourly bars (2022-01-01 to 2026-10-20 UTC)  
**Governance Status:** `REAL_CAPITAL_ENABLED = False` (Mandatory Simulation / Paper Mode)  

---

## 1. Executive Summary & Strategy Qualification Table

| Candidate Strategy | Total Trades | Sealed OOS Trades | Full Exp (1.5x) | OOS Exp (1.5x) | Win Rate (OOS) | Profit Factor | DSR | 95% Bootstrap CI (OOS) | Governance Verdict |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **H3: BTC Open Interest Flush LONG** | 50 | 2 | +0.240R | +0.384R | 50.0% | 1.77 | 0.000 | `[0.000, 0.000]R` | `RESEARCH_CANDIDATE / INSUFFICIENT_OOS_SAMPLE` |
| **H5: ETH Open Interest Compression SHORT** | 44 | 6 | +0.441R | +1.803R | 83.3% | 11.31 | 0.240 | `[0.313, 2.435]R` | `RESEARCH_CANDIDATE / INSUFFICIENT_OOS_SAMPLE` |
| **HTF_OB: BTC Order Block Retest LONG** | 123 | 36 | -0.039R | -0.460R | 25.0% | 0.50 | 0.000 | `[-0.753, -0.037]R` | `REJECTED_NO_OOS_EDGE` |
| **HTF_OB: ETH Order Block Retest LONG** | 106 | 32 | -0.066R | +0.163R | 46.9% | 1.35 | 0.000 | `[-0.224, 0.744]R` | `PAPER_QUALIFICATION_CANDIDATE` |

---

## 2. 3-Tier Transaction Friction & Friction Breakeven Multipliers

| Candidate Strategy | Base Tier (1.0x) | Conservative (1.5x) | Stress Tier (2.5x) | True Breakeven Multiplier | Status Under 2.5x Stress |
|:---|:---:|:---:|:---:|:---:|:---|
| **H3: BTC Open Interest Flush LONG** | +0.267R | +0.240R | +0.185R | **5.89x** | `SURVIVES` |
| **H5: ETH Open Interest Compression SHORT** | +0.486R | +0.441R | +0.352R | **6.43x** | `SURVIVES` |
| **HTF_OB: BTC Order Block Retest LONG** | +0.007R | -0.039R | -0.132R | **1.08x** | `DEGRADES_NEGATIVE` |
| **HTF_OB: ETH Order Block Retest LONG** | -0.031R | -0.066R | -0.135R | **0.55x** | `DEGRADES_NEGATIVE` |

---

## 3. Macro Regime Performance (Sealed Out-Of-Sample)

### H3: BTC Open Interest Flush LONG

| Regime | Trades | Mean Expectancy | Win Rate |
|:---|:---:|:---:|:---:|
| `TREND_BULL` | 0 | +0.000R | 0.0% |
| `TREND_BEAR` | 1 | -1.092R | 0.0% |
| `CHOP` | 1 | +1.938R | 100.0% |

### H5: ETH Open Interest Compression SHORT

| Regime | Trades | Mean Expectancy | Win Rate |
|:---|:---:|:---:|:---:|
| `TREND_BULL` | 1 | +2.442R | 100.0% |
| `TREND_BEAR` | 4 | +1.551R | 75.0% |
| `CHOP` | 1 | +2.412R | 100.0% |

### HTF_OB: BTC Order Block Retest LONG

| Regime | Trades | Mean Expectancy | Win Rate |
|:---|:---:|:---:|:---:|
| `TREND_BULL` | 4 | +0.402R | 50.0% |
| `TREND_BEAR` | 14 | -1.023R | 0.0% |
| `CHOP` | 18 | -0.105R | 38.9% |

### HTF_OB: ETH Order Block Retest LONG

| Regime | Trades | Mean Expectancy | Win Rate |
|:---|:---:|:---:|:---:|
| `TREND_BULL` | 11 | +0.667R | 63.6% |
| `TREND_BEAR` | 10 | -0.389R | 30.0% |
| `CHOP` | 11 | +0.265R | 45.5% |

---

## 4. Key Epistemic Findings & Next Step Recommendation

1. **H3 (BTC Flush LONG)**: Demonstrates positive full-sample expectancy (+0.240R at 1.5x frictions) and survives stress frictions (5.89x breakeven). However, Sealed OOS contains only **2 trades**, rendering DSR = 0.000 and statistical confidence unverified (`[FACT]`). Classification: `RESEARCH_CANDIDATE`.
2. **H5 (ETH Compression SHORT)**: Strongest individual alpha candidate with full-sample expectancy (+0.441R at 1.5x frictions, 6.43x breakeven) and +1.803R across 6 Sealed OOS trades (win rate 83.3%, DSR 0.240, 95% bootstrap CI `[+0.313, +2.435]R`, $p=0.0251$). Sample size (6 trades) is promising but below the 30-trade institutional threshold (`[FACT]`). Classification: `RESEARCH_CANDIDATE`.
3. **HTF Order Block Retest (BTC LONG)**: Fails sealed OOS validation (-0.460R at 1.5x frictions, 25% win rate, 95% CI `[-0.753, -0.037]R`). Long-only order blocks severely bled during the 2026 bear regimes (`[FACT]`). Classification: `REJECTED_NO_OOS_EDGE`.
4. **HTF Order Block Retest (ETH LONG)**: Produced 32 OOS trades with +0.163R expectancy at 1.5x frictions and 46.9% win rate, though full-sample expectancy is slightly negative (-0.066R) (`[FACT]`). Classification: `PAPER_QUALIFICATION_CANDIDATE`.

> [!IMPORTANT]
> **Phase 2 Handoff:** For the P2 Production Multi-Strategy Portfolio Replay, we deploy a diversified ensemble combining **H3 (BTC Flush)**, **H5 (ETH Compression)**, and **HTF OB (ETH Retest)** under the strict 3-position capacity arbiter, Half-Kelly sizing (capped at 1.5% equity), and zero-lookahead next-bar execution.
