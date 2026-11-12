# M36.1 — Downside Correlation Sensitivity & Small-Sample Audit

**Auditor:** Independent Quantitative Research Auditor  
**Investigation:** Audit of the reported $\rho_{\text{downside}} = -0.989$ between Benchmark OB and Family 3 (Liquidity Sweep)  
**Date:** November 5, 2026

---

## 1. Executive Summary: The Myth of the "-0.989 Hedge"

Milestone 36.1 reported that Family 3 exhibited a "near-perfect downside correlation of -0.989" during Benchmark drawdown days.

This independent audit evaluated the underlying sample data and revealed a critical statistical reality:
> **The reported $-0.989$ downside correlation is based on only FIVE calendar days, during which Family 3 was active on EXACTLY ONE DAY.**

The correlation is almost purely a mathematical artifact of a single data point. When that single point is removed, the downside correlation is **completely undefined (`NaN`)**. 

**Verdict:** The downside correlation is **statistically inconclusive**. Family 3 must NOT be classified as a portfolio hedge or reliable diversifier.

---

## 2. Downside Sample Data Inspection

Across 1,754 calendar days (January 1, 2022 to October 20, 2026), the Benchmark Order Block strategy closed trades on only 17 days. Of those 17 days, exactly **5 days** had negative net returns.

### The Complete Set of Benchmark Losing Days:
| Date (UTC) | Benchmark Net Return ($R_{\text{BM}}$) | Family 3 Net Return ($R_{\text{F3}}$) | Family 3 Active? | Notes |
| :---: | :---: | :---: | :---: | :--- |
| **2022-05-22** | $-1.0770\text{R}$ | $0.0000\text{R}$ | No | Idle day for F3 |
| **2023-07-30** | $\mathbf{-1.5990\text{R}}$ | $\mathbf{+4.4050\text{R}}$ | **Yes** | **The ONLY simultaneous active day!** |
| **2024-11-26** | $-1.0980\text{R}$ | $0.0000\text{R}$ | No | Idle day for F3 |
| **2025-04-03** | $-1.1350\text{R}$ | $0.0000\text{R}$ | No | Idle day for F3 |
| **2025-05-05** | $-1.1580\text{R}$ | $0.0000\text{R}$ | No | Idle day for F3 |

### Sample Characteristics:
- **Total Calendar Days:** 1,754
- **Benchmark Negative Days ($N$):** 5
- **Family 3 Active Days in Subset:** 1 (20.0%)
- **Family 3 Inactive Days in Subset:** 4 (80.0%)

---

## 3. Mathematical Mechanism of the "-0.989" Artifact

Consider the two vectors being correlated:
$$X = [-1.0770, \mathbf{-1.5990}, -1.0980, -1.1350, -1.1580]$$
$$Y = [0.0000, \mathbf{+4.4050}, 0.0000, 0.0000, 0.0000]$$

1. **Mean of $X$:** $\bar{X} = -1.2134\text{R}$
2. **Mean of $Y$:** $\bar{Y} = +0.8810\text{R}$
3. **Deviations from Mean:**
   - On day 2 (`2023-07-30`), $X_2 - \bar{X} = -1.5990 - (-1.2134) = \mathbf{-0.3856}$ (a large negative deviation from mean).
   - On day 2, $Y_2 - \bar{Y} = +4.4050 - 0.8810 = \mathbf{+3.5240}$ (a massive positive deviation from mean).
   - The product $(X_2 - \bar{X})(Y_2 - \bar{Y}) = (-0.3856)(+3.5240) = \mathbf{-1.3589}$.
   - On all other four days, $Y_i - \bar{Y} = -0.8810$, and $X_i - \bar{X}$ are small positive numbers ($+0.136, +0.115, +0.078, +0.055$), resulting in small negative products.
4. **Resulting Pearson Correlation:**
   $$r = \frac{\sum (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum (X_i - \bar{X})^2 \sum (Y_i - \bar{Y})^2}} = \mathbf{-0.9895} \quad (p = 0.0013)$$

Although the $p$-value appears small, this is a standard small-sample pathology when $Y$ contains four identical zeros and one extreme non-zero outlier.

---

## 4. Sensitivity & Leave-One-Out (LOO) Analysis

| Scenario | $N$ | Pearson $r$ | Spearman $\rho$ | Statistical Meaning |
| :--- | :---: | :---: | :---: | :--- |
| **All 5 Losing Days** | 5 | -0.9895 | -0.7071 | Driven by 2023-07-30 |
| **Excluding 2022-05-22** | 4 | -0.9945 | -0.7746 | Driven by 2023-07-30 |
| **Excluding 2023-07-30** | 4 | **NaN** | **NaN** | **F3 vector is $[0, 0, 0, 0]$ (zero variance)!** |
| **Excluding 2024-11-26** | 4 | -0.9899 | -0.7746 | Driven by 2023-07-30 |
| **Excluding 2025-04-03** | 4 | -0.9903 | -0.7746 | Driven by 2023-07-30 |
| **Excluding 2025-05-05** | 4 | -0.9954 | -0.7746 | Driven by 2023-07-30 |

### Outlier Sensitivity:
If the return of Family 3 on 2023-07-30 were $0.00\text{R}$ instead of $+4.405\text{R}$, the correlation would be undefined. If it were $-1.00\text{R}$ (a losing sweep), the correlation would flip to **$+0.989$ positive**!

---

## 5. Alternative Downside Thresholds

If we test alternative definitions of "downside":
- **Benchmark Return $< -0.5\text{R}$:** Same 5 days (all 5 losses were $< -1.0\text{R}$).
- **Benchmark Active Days ($N=17$):**
  - Over all 17 active Benchmark days, Family 3 was active on 4 days.
  - Overall correlation on Benchmark active days: $\mathbf{+0.124}$ (Positive correlation!).
- **Full Daily Series (1,754 days):**
  - Overall Pearson correlation: $\mathbf{-0.085}$ (Negligible negative correlation).
  - Overall Spearman correlation: $\mathbf{-0.065}$.

---

## 6. Audit Conclusion

The claim that Family 3 provides a $-0.989$ downside hedge is **statistically invalid**.
1. The effective sample size of simultaneous negative events is $N = 1$.
2. Relying on $N = 1$ to guide portfolio allocation violates every principle of empirical quantitative research.
3. Family 3 is confirmed as **`REJECTED_AS_STANDALONE / CONDITIONAL_RESEARCH_ONLY`**. It cannot be treated as a hedge.
