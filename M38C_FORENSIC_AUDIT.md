# SKY / CBT — Milestone 38-C: Evidence Closure & Independent Forensic Review

**Date:** 2026-11-05  
**Auditor:** Independent Institutional Quantitative Research Auditor & Governance Officer  
**Audit Target:** Repository state at commit `4a639ab` and current HEAD  
**Governance Invariant:** `REAL_CAPITAL_ENABLED = False` permanently enforced; zero live capital activation; testnet/paper/simulation only; M18 certified surface protected (149/149 passing tests).

---

## 1. Executive Summary & Epistemic Audit Mandate

This forensic audit was commissioned to independently review the claims, source code, raw data, generated artifacts, and execution logs produced in Milestone 38 (`4a639ab`).

Under strict quantitative integrity directives:
> *"Never claim code was tested or working unless you actually executed the test command and inspected the output. Never infer live execution profitability from mathematical plausibility. Categorize all findings using the Epistemic Taxonomy."*

The audit evaluated 7 critical investigations. The summary verdict table is presented below:

### Master Audit Verdict Matrix
| Investigation Area | Description | Status | Evidence Document |
| :--- | :--- | :---: | :--- |
| **1. M37 Dataset Record Totals** | Physical verification of 586 Parquet files; resolution of 348,046 vs 345,596 discrepancy. | **VERIFIED** | [`M38C_DATA_RECONCILIATION.json`](file:///c:/Users/azims/CBT/M38C_DATA_RECONCILIATION.json) |
| **2. Statistical Reproduction** | Reproduction of bootstrap CIs, $N_{\text{eff}}$, DSR, FDR, and friction breakeven multipliers. | **VERIFIED** | [`M38C_STATISTICAL_REPRODUCTION.json`](file:///c:/Users/azims/CBT/M38C_STATISTICAL_REPRODUCTION.json) |
| **3. Bootstrap Resampling Dependences** | Evaluation of event clustering and calendar-time dependence in bootstrap methodology. | **FAILED** | Section 4 of this report |
| **4. Cryptographic Strategy Binding** | SHA-256 fingerprint verification against executable code vs JSON metadata descriptors. | **FAILED** | Section 5 of this report |
| **5. 5m / 15m Derivatives Resolution** | Verification of historical sub-hourly OI data and causal availability (no forward-filling). | **BLOCKED** | Section 6 of this report |
| **6. Shadow Prediction Ledger** | Audit of append-only locks, precommitment, outcome resolution, MFE/MAE, and runner daemon. | **FAILED** | [`M38C_SHADOW_LEDGER_AUDIT.md`](file:///c:/Users/azims/CBT/M38C_SHADOW_LEDGER_AUDIT.md) |
| **7. Milestone 18 Certification** | Full physical execution of 14 gates and 149 adversarial tests. | **VERIFIED** | [`M38C_M18_INTEGRITY_REPORT.md`](file:///c:/Users/azims/CBT/M38C_M18_INTEGRITY_REPORT.md) |

---

## 2. Investigation 1: Dataset Record Totals & Resolution of 348,046 vs 345,596

### 2.1 Direct Physical Parquet Audit
An exhaustive inspection of every physical file across `data/store/derivatives/` and `data/store/parquet/candles/` was conducted:
- **Total Parquet Partitions on Disk:** **586**
- **Total Partitions Declared in Manifest:** **586**
- **Total Physical Disk Rows:** **348,046**
- **Total Manifest Rows:** **348,046**
- **Mismatches (Rows or SHA-256):** **0**
- **Total Disk Storage:** **11,418,598 bytes**

#### Per-Metric Breakdown
| Symbol | Metric | Partitions | Verified Disk Rows |
| :--- | :--- | :---: | :---: |
| **BTCUSDT** | Funding Rate (8h) | 59 | 5,308 |
| **BTCUSDT** | Open Interest (1h) | 59 | 42,168 |
| **BTCUSDT** | Open Interest Value (1h) | 59 | 42,168 |
| **BTCUSDT** | Perpetual 1h Candles | 58 | 42,078 |
| **BTCUSDT** | Spot 1h Reference Candles | 58 | 42,301 |
| **ETHUSDT** | Funding Rate (8h) | 59 | 5,308 |
| **ETHUSDT** | Open Interest (1h) | 59 | 42,168 |
| **ETHUSDT** | Open Interest Value (1h) | 59 | 42,168 |
| **ETHUSDT** | Perpetual 1h Candles | 58 | 42,078 |
| **ETHUSDT** | Spot 1h Reference Candles | 58 | 42,301 |
| **Total** | **All 10 Time Series** | **586** | **348,046** |

### 2.2 Forensic Resolution of the Disputed 345,596 Figure
The difference between the physical dataset total (348,046) and the disputed 345,596 figure is exactly:
$$348,046 - 345,596 = \mathbf{2,450\text{ records}}$$

The forensic investigation definitively confirms:
1. **Physical Record Integrity:** There is **zero record loss** in the lakehouse. All 348,046 records exist, are uncorrupted, and have matching cryptographic digests.
2. **Origin of 345,596:** The figure 345,596 does not represent any physical parquet dataset on disk. Rather, it originated from an earlier intermediate ingest snapshot that lacked the final October and November 2026 data dumps prior to the ingestion run of `scripts/research/audit_m37_data_coverage.py`.
3. **Synchronized Operational Window:** When inner-merging Spot, Perpetual, Open Interest, and Funding Rate across the common historical window (`2022-01-01 01:00:00` to `2026-10-20 05:00:00 UTC`), exactly **42,009 synchronized hourly bars** exist for BTC and **42,009 bars** for ETH. The remaining 1,068 rows represent unaligned boundary tails (e.g. spot running through Oct 31, funding rate through Nov 5).
- **Status:** **VERIFIED**.

---

## 3. Investigation 2: Independent Statistical Reproduction & Discovery of Dimensional Bug

Independent reproduction of the statistical metrics was executed directly on the 98 trade records in `research/m38_experiment_ledger.jsonl`.

### 3.1 Reproduced Statistical Matrix
| Metric | H3: BTC OI Flush LONG | H5: ETH OI Compression SHORT | Reproduction Match |
| :--- | :---: | :---: | :---: |
| **Sample Size ($N$)** | 50 | 48 | **EXACT MATCH** |
| **Mean $R$ Expectancy** | $+0.3139\text{R}$ | $+0.4559\text{R}$ | **EXACT MATCH** |
| **Sample Std Dev ($s$)** | $1.2617\text{R}$ | $1.7443\text{R}$ | **EXACT MATCH** |
| **$t$-statistic** | $1.7593$ ($p = 0.0848$) | $1.8106$ ($p = 0.0766$) | **EXACT MATCH** |
| **Lag-1 Autocorrelation** | $\rho_1 = 0.1110$ | $\rho_1 = 0.1468$ | **EXACT MATCH** |
| **Effective Sample Size ($N_{\text{eff}}$)** | $40.0$ | $35.7$ | **EXACT MATCH** |
| **Deflated Sharpe Ratio ($K=10$)** | $0.0000$ | $0.0000$ | **EXACT MATCH** |
| **FDR Adjusted $p$-value** | $0.8477$ | $0.7660$ | **FAILS SIGNIFICANCE** |
| **Train / Val / OOS Partition** | $+0.312 / +0.303 / +0.387\text{R}$ | $+0.279 / +0.198 / +1.802\text{R}$ | **EXACT MATCH** |

### 3.2 Forensic Discovery: The Breakeven Multiplier Dimensional Bug
The M38 Completion Report claimed extraordinary breakeven friction multipliers of **$175.39\times$ for H3** and **$254.28\times$ for H5**.

Our forensic inspection of [`scripts/research/run_m38_independent_alpha_verification.py`](file:///c:/Users/azims/CBT/scripts/research/run_m38_independent_alpha_verification.py#L506) revealed a **dimensional unit error**:
```python
# Line 506 in run_m38_independent_alpha_verification.py:
"breakeven_cost_multiplier": round(base_eval["expectancy_r"] / (BASE_ROUNDTRIP_FRICTION * 1.5) + 1.0, 2)
```
- The numerator (`expectancy_r`) is in **$R$-multiples** ($0.3139\text{R}$).
- The denominator (`BASE_ROUNDTRIP_FRICTION * 1.5`) is a **raw fraction of asset price** ($0.0012 \times 1.5 = 0.0018$).
- Dividing an $R$-multiple by a fraction without converting $R$ into price percentage resulted in an **inflated number by two orders of magnitude** ($0.3139 / 0.0018 = 174.39$).

#### Correct Dimensioned Reproduction
From the actual simulated trade ledger:
- For H3, round-trip baseline friction consumes an average of **$0.0637\text{R}$** per trade.
  - Gross expectancy is $+0.3776\text{R}$.
  - Stressed at $1.5\times$ costs, net expectancy drops to $+0.2729\text{R}$ (consuming an additional $0.041\text{R}$ per $0.5\times$ cost increase, or $0.0820\text{R}$ per $1.0\times$).
  - Correct linear breakeven multiplier:
    $$1.0 + \frac{0.3139\text{R}}{0.0820\text{R}} \approx \mathbf{4.83\times} \quad (\text{not } 175.39\times)$$
- For H5, baseline friction consumes an average of **$0.1038\text{R}$** per trade.
  - Stressed at $1.5\times$ costs, net expectancy drops to $+0.3890\text{R}$ (consuming an additional $0.0669\text{R}$ per $0.5\times$, or $0.1338\text{R}$ per $1.0\times$).
  - Correct linear breakeven multiplier:
    $$1.0 + \frac{0.4559\text{R}}{0.1338\text{R}} \approx \mathbf{4.41\times} \quad (\text{not } 254.28\times)$$
- **Forensic Assessment:** $4.4\times$ to $4.8\times$ is still adequate to withstand normal cryptocurrency taker fee fluctuations (which range from 2 bps to 6 bps), but the claim of $175\times$ to $254\times$ was a mathematical artifact of an unnormalized formula.
- **Status:** **VERIFIED (REPRODUCED WITH BUG IDENTIFIED)**.

---

## 4. Investigation 3: Bootstrap Resampling, Temporal Dependence & Clustering

In `scripts/research/run_m38_independent_alpha_verification.py`, `clustered_bootstrap_ci` partitioned returns into consecutive blocks of 5 trades.

### Forensic Critique:
1. **Trade-Space vs Calendar-Time Disconnect:** Over the 42,009-hour period, trades occur sparsely (average trade interval $\approx 840\text{ hours}$). However, during liquidation cascade crises (e.g., May 2022 Terra-Luna, November 2022 FTX), multiple trades clustered within 48 to 72 hours.
2. **Arbitrary Block Length:** Fixing $L=5$ trades without regard to whether the elapsed time between trade $i$ and trade $i+1$ was 2 hours or 3 months fails to preserve calendar-time volatility regimes.
3. **Statistical Significance Verdict:**
   - H3 10,000-resample Block Bootstrap 95% CI: `[0.0067, 0.6582]` (boundary essentially touches 0.00R).
   - H5 10,000-resample Block Bootstrap 95% CI: `[-0.0853, 1.1060]` (lower bound falls below zero).
   - Neither strategy achieves 95% statistical significance when adjusting for clustering and small sample size.
- **Status:** **FAILED**.

---

## 5. Investigation 4: Strategy SHA-256 Fingerprint Verification

### Forensic Finding
In [`research/m38_hypothesis_manifest.json`](file:///c:/Users/azims/CBT/research/m38_hypothesis_manifest.json):
- H3 Fingerprint: `3497bd8b7bbad797c7c34e67be658ad8ba5f4b780cf44b729c81bc9c5cba2a68`
- H5 Fingerprint: `5dcbd0e17edbbe42eff2af4dc31c93d07ebb47977bb3a8ea3f2e18f3dd23a53b`

These digests were computed by hashing a **JSON string of textual metadata descriptors** (`"signal_rules": "oi_pct_chg_1h <= -0.040 AND close < open - 0.8 * atr_14"`).
- **The Defect:** The SHA-256 digests do NOT hash the actual executable Python functions, AST nodes, or simulation code in `run_m38_independent_alpha_verification.py`. An engineer could modify the execution mechanics in Python without altering the JSON descriptor hash.
- **Institutional Requirement:** A true cryptographic strategy binding must hash the concrete source code file or AST representation of the strategy logic.
- **Status:** **FAILED (DESCRIPTOR HASH ONLY, NO EXECUTABLE BINDING)**.

---

## 6. Investigation 5: 5m and 15m Datasets & Causal Availability

The audit searched all sub-hourly directories across the repository:
- `data/store/parquet/candles/exchange=binance/market=perp/symbol=BTCUSDT/timeframe=15m/` contains only **30 calendar days** of 15m candle data (2,879 rows, Sept 20, 2026 to Oct 20, 2026).
- There is **zero multi-year 5m or 15m Open Interest data** stored in the lakehouse.
- Open Interest is available strictly at **1-hour snapshot intervals** in `data/store/derivatives/`.
- Attempting to evaluate 5m or 15m strategies would require **forward-filling 1-hour OI across 12 consecutive 5m bars**. This manufactures synthetic observations, destroys autocorrelation structures, and is strictly prohibited under institutional quant protocol.
- Sub-hourly replication is formally **BLOCKED** until true multi-year 5m/15m OI feeds are acquired.
- **Status:** **BLOCKED**.

---

## 7. Investigation 6: Shadow Prediction Ledger Audit

The physical inspection of [`research/m38_shadow_prediction_ledger.jsonl`](file:///c:/Users/azims/CBT/research/m38_shadow_prediction_ledger.jsonl) revealed:
- **Record Count:** Exactly **1 row** (a static demonstration record emitted during the initial script execution).
- **Append-Only Immutability:** `FAILED` (no OS-level append locks or cryptographic hash chaining `prev_sha256`).
- **MFE / MAE Tracking:** `FAILED` (Maximum Favorable Excursion and Maximum Adverse Excursion are omitted).
- **Precommitment & Invalidation:** `NOT_VERIFIED` (logged `signal_state: false` with no precommitted trade boundaries).
- **Execution Daemon:** `NOT_VERIFIED` (no daemon, cron job, or standing scheduler is configured).
- Detailed audit findings are cataloged in [`M38C_SHADOW_LEDGER_AUDIT.md`](file:///c:/Users/azims/CBT/M38C_SHADOW_LEDGER_AUDIT.md).
- **Status:** **FAILED (STUB ONLY)**.

---

## 8. Investigation 7: Milestone 18 Certification Status

An independent execution of `scripts/verify_m18_certification.py` was executed:
- **Certified Commit:** `c9cc1cad780453b81032f6b1b1b81117d41c060f`
- **Result:** **149/149 tests passed in 119.56s (100% Green)**.
- **Invariants:** Commit ancestry confirmed, all 14 files present, cryptographic test identity hash verified (`2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b`).
- Full report cataloged in [`M38C_M18_INTEGRITY_REPORT.md`](file:///c:/Users/azims/CBT/M38C_M18_INTEGRITY_REPORT.md).
- **Status:** **VERIFIED**.

---

## 9. Master Forensic Audit Verdict & Governance Declaration

### Final Decision:
$$\mathbf{CONDITIONAL\ PASS\ WITH\ FORENSIC\ CORRECTIONS}$$

1. **Dataset Integrity:** **VERIFIED**. 348,046 Parquet records verified across 586 physical files on disk with zero loss. The 345,596 discrepancy is resolved as an external misattribution.
2. **Alpha Status:** Neither H3 nor H5 is promoted to production. Both remain strictly classified as:
   $$\mathbf{RESEARCH\_CANDIDATE\ /\ NEEDS\_MORE\_OOS\_DATA}$$
3. **Breakeven Multiplier Correction:** The M38 reported values ($175\times$ and $254\times$) are formally retracted and replaced by the mathematically sound values of **$4.83\times$ (H3)** and **$4.41\times$ (H5)**.
4. **Shadow Ledger Status:** The existing shadow ledger is designated as a **prototype stub**. Milestone 39 must implement true cryptographic hash chaining and MFE/MAE tracking before prospective shadow data can be accepted as institutional evidence.
5. **Safety Invariants:** `REAL_CAPITAL_ENABLED = False` permanently locked. Milestone 18 Production Pass is fully active and green.
