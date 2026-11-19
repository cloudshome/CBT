# MILESTONE 63 RESEARCH REPORT
## First-Principles Causal Alpha Discovery Benchmark Across 3 Orthogonal Families

**Date:** 2026-11-19T10:29:20.661820+00:00  
**Final Campaign Verdict:** **`NO_CERTIFIED_EDGE_FOUND`**  
**Total Runtime:** 5.75 seconds  
**Real Capital Enabled:** `False` (PERMANENTLY LOCKED)  
**Execution Model:** `open[t+1]` taker market order (20 bps roundtrip + funding)  
**Campaign Trials Penalized ($M$):** `9`  

---

## 1. EXECUTIVE SUMMARY & CP-2 MANDATORY HURDLES VERIFICATION

| Gate / Hurdle | Required Metric | Combined OOS Result | Status |
|:---|:---:|:---:|:---:|
| **Hurdle 1** | $E[R_{net}] \ge +0.2000R$ | `+0.0234R` | ❌ FAIL |
| **Hurdle 2** | $PF_{net} \ge 1.3500$ | `1.0509` | ❌ FAIL |
| **Hurdle 3** | Continuous Calendar Daily Sharpe $\ge 1.0$ | `+0.2666` | ❌ FAIL |
| **Hurdle 4** | Deflated Sharpe Ratio ($M=9$) $\ge 0.9500$ | `0.1563` ($p = 0.8437$) | ❌ FAIL |
| **Hurdle 5** | Deduplicated OOS Trades $N \ge 100$ | `1058` decided trades | ✅ PASS |

**Overall Verdict:** **`NO_CERTIFIED_EDGE_FOUND`**

---

## 2. CROSS-HYPOTHESIS FAMILY SCORECARD (TRAIN VS. VALIDATION VS. SEALED OOS)

| Hypothesis Family | Split | Decided Trades ($N$) | Win Rate | Gross $E[R]$ | Net $E[R]$ | Net PF | Cost Drag | Max DD (R) | Calendar Daily Sharpe | DSR ($M=9$) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Hypothesis Family 1 | `TRAIN` | 531 | 36.5% | `+0.1262R` | `+0.0307R` | `1.0642` | `-50.8R` | `55.7R` | `+0.2120` | `0.1465` |
| Hypothesis Family 1 | `VALIDATION` | 268 | 38.1% | `+0.2191R` | `+0.1107R` | `1.2259` | `-29.1R` | `17.9R` | `+0.7847` | `0.3933` |
| Hypothesis Family 1 | `SEALED_OOS` | 309 | 31.4% | `+0.2155R` | `+0.0851R` | `1.1529` | `-40.3R` | `17.5R` | `+0.3351` | `0.2131` |
| Hypothesis Family 2 | `TRAIN` | 439 | 49.7% | `-0.1238R` | `-0.2031R` | `0.6016` | `-34.8R` | `90.7R` | `-2.7409` | `0.0000` |
| Hypothesis Family 2 | `VALIDATION` | 257 | 54.5% | `-0.0374R` | `-0.1175R` | `0.7385` | `-20.6R` | `36.1R` | `-1.5946` | `0.0002` |
| Hypothesis Family 2 | `SEALED_OOS` | 282 | 52.8% | `-0.0406R` | `-0.1410R` | `0.7125` | `-28.3R` | `46.1R` | `-1.7672` | `0.0000` |
| Hypothesis Family 3 | `TRAIN` | 889 | 48.5% | `+0.2512R` | `+0.2220R` | `1.3344` | `-26.0R` | `52.0R` | `+1.3839` | `0.8588` |
| Hypothesis Family 3 | `VALIDATION` | 489 | 51.9% | `+0.1419R` | `+0.1140R` | `1.2701` | `-13.6R` | `21.0R` | `+1.2490` | `0.5265` |
| Hypothesis Family 3 | `SEALED_OOS` | 473 | 52.6% | `+0.1024R` | `+0.0743R` | `1.1946` | `-13.3R` | `17.7R` | `+1.1018` | `0.4331` |

---

## 3. SEALED OOS DIRECTIONAL BREAKDOWN (LONG VS. SHORT)

| Hypothesis Family | Direction | OOS Trades ($N$) | Win Rate | Gross $E[R]$ | Net $E[R]$ | Net PF | Max DD (R) | Daily Sharpe |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Hypothesis Family 1 | `LONG` | 167 | 32.9% | `+0.4286R` | `+0.2899R` | `1.5411` | `11.7R` | `+0.6647` |
| Hypothesis Family 1 | `SHORT` | 142 | 29.6% | `-0.0352R` | `-0.1557R` | `0.7323` | `30.3R` | `-0.8107` |
| Hypothesis Family 2 | `LONG` | 141 | 56.7% | `+0.0303R` | `-0.0672R` | `0.8511` | `13.7R` | `-0.6541` |
| Hypothesis Family 2 | `SHORT` | 141 | 48.9% | `-0.1115R` | `-0.2149R` | `0.5943` | `34.6R` | `-1.8226` |
| Hypothesis Family 3 | `LONG` | 473 | 52.6% | `+0.1024R` | `+0.0743R` | `1.1946` | `17.7R` | `+1.1018` |

---

## 4. SEALED OOS MACRO REGIME ATTRIBUTION (BULL VS. BEAR VS. SIDEWAYS)

| Hypothesis Family | Macro Regime | OOS Trades ($N$) | Win Rate | Net $E[R]$ | Net PF | Max DD (R) | Daily Sharpe |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Hypothesis Family 1 | `BULL` | 167 | 32.9% | `+0.2899R` | `1.5411` | `11.7R` | `+0.6647` |
| Hypothesis Family 1 | `BEAR` | 142 | 29.6% | `-0.1557R` | `0.7323` | `30.3R` | `-0.8107` |
| Hypothesis Family 2 | `BULL` | 115 | 48.7% | `-0.2207R` | `0.5928` | `30.1R` | `-1.8555` |
| Hypothesis Family 2 | `BEAR` | 167 | 55.7% | `-0.0862R` | `0.8106` | `19.4R` | `-0.8831` |
| Hypothesis Family 3 | `BULL` | 35 | 48.6% | `-0.0017R` | `0.9973` | `6.0R` | `-0.0054` |
| Hypothesis Family 3 | `SIDEWAYS` | 438 | 53.0% | `+0.0804R` | `1.2223` | `16.7R` | `+1.1904` |

---

## 5. COMBINED MULTI-FAMILY SOVEREIGN PORTFOLIO (SEALED OOS)

- **Decided Trades ($N$):** `1058` (Deduplicated from overlapping bars)
- **Net Win Rate:** `46.6%`
- **Gross Expectancy:** `+0.1003R`
- **Net Expectancy ($E[R_{net}]$):** `+0.0234R`
- **Net Profit Factor ($PF_{net}$):** `1.0509`
- **Total Friction Drag:** `-81.3R`
- **Max Drawdown (R):** `66.2R`
- **Max Concurrent Positions:** `8`
- **Continuous Calendar-Day Daily Sharpe:** `+0.2666`
- **CPCV Median Fold Sharpe:** `+0.0175`
- **Deflated Sharpe Ratio ($M=9$):** `0.1563` ($p = 0.8437$)

---

## 6. SCIENTIFIC CONCLUSION & HONEST APPRAISAL

Milestone 63 evaluated three distinct, economically sound hypothesis families with zero lookahead bias and realistic taker+slippage friction.
Final Verification Outcome: **`NO_CERTIFIED_EDGE_FOUND`**.

**Key Findings:**
1. **Trend Continuation (Donchian-ATR on 4h):** Wider stops capture large right-tail moves, but false breakouts during chop and bear regimes erode capital.
2. **Derivatives Crowding (1h):** Extreme negative/positive funding rates identify local price exhaustion, but forced cascades frequently blow through 2.0x ATR stops before reverting.
3. **Cross-Asset Relative Strength (4h):** Rotation between BTC, ETH, SOL, and Gold (PAXG) reduces drawdown relative to buy-and-hold during severe drawdowns, but whipsaws during choppy rotation.

**Next Step:** In accordance with the AI Honesty Directive, Capital Governor remains locked at `TIER_0_PAPER` (`FAILED_REAUDIT`), and `REAL_CAPITAL_ENABLED = False` remains permanently in force until a genuinely robust alpha with positive causal expectancy is discovered.