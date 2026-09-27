# Grade-E1 Repository Reconnaissance & Microstructure Architecture Audit

**Document Version:** 1.0.0  
**Certified Date:** 2026-09-19  
**Target Module:** `core/research/grade_e1/`  
**Classification:** Research Only / Empirical Microstructure Measurement Engine  

---

## 1. Executive Summary & Research Mandate

The Grade-E1 Institutional Maker Execution Reality Engine is designed as an empirical measurement system to test whether passive maker execution assumptions survive real-world adverse selection, queue priority, latency, fee schedules, and regime transitions.

This reconnaissance audits the existing repository architecture, inventories reusable components, confirms the certified surface boundaries that must remain untouched, and establishes explicit scientific boundaries regarding data sufficiency.

---

## 2. Repository Architecture & Component Map

The SKY / Crypto Trading Brain (CBT) codebase operates on a multi-tier quantitative architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MARKET DATA INGESTION                           │
│  core/data_streamer.py  |  data/research/datasets/manifest_k9.json     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        RESEARCH ENVIRONMENT                            │
│  core/kronos/research/                                                 │
│    ├── dataset_freeze.py       (DatasetFreezeManager, manifest)        │
│    ├── baseline_registry.py    (Competitive benchmark models)          │
│    ├── friction_evaluator.py   (Canonical 3-tier fee/slippage)         │
│    ├── experiment_ledger.py    (Append-only research ledger)           │
│    └── maker_execution_simulator.py (K10 preliminary prototype)        │
│                                                                        │
│  core/research/grade_e1/       [NEW GRADE-E1 MICROSTRUCTURE ENGINE]   │
│    ├── contracts.py            (Canonical immutable types & enums)     │
│    ├── dataset_registry.py     (Frozen dataset loader & validator)     │
│    ├── market_replay.py        (Sequential causal event generator)     │
│    ├── hypothetical_order.py   (Passive order state machine)           │
│    ├── latency_model.py        (Network & matching delay models)       │
│    ├── queue_model.py          (Q0, Q1, Q2 queue penetration models)   │
│    ├── fill_engine.py          (Conservative, Central, Optimistic)     │
│    ├── adverse_selection.py    (Multi-horizon markout engine)          │
│    ├── execution_cost.py       (Multi-tier exchange fee profiles)      │
│    ├── calibration.py          (Out-of-sample cost calibration)        │
│    ├── statistical_tests.py    (Block bootstrap & cluster SEs)         │
│    ├── strategy_adapter.py     (Strategy signal bridge)                │
│    ├── experiment_runner.py    (Factorial matrix test runner)          │
│    ├── evidence_ledger.py      (Append-only cryptographic ledger)      │
│    └── verdict_engine.py       (Pre-registered decision engine)        │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼  [FIREWALLED / READ-ONLY QUOTE QUERY ONLY]
┌────────────────────────────────────────────────────────────────────────┐
│                    CERTIFIED EXECUTION SURFACE (M18)                   │
│                        >>> 100% UNTOUCHED <<<                          │
│  core/execution/live_router.py                                         │
│  core/execution/smart_order_router.py                                  │
│  core/execution/reconciliation_ledger.py                               │
│  core/execution/almgren_chriss.py                                      │
│  core/execution/kill_switch.py                                         │
│  core/execution/connectors/ (binance_connector.py, bybit_connector.py) │
│  app.py                                                                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Protected Surface Area Boundary (Milestone 18 Certification)

Milestone 18 holds a cryptographic **PRODUCTION PASS** across 149 adversarial tests. Per the **M18 Certified Surface Invalidation Rule**, modifying any of the certified files invalidates the production certification.

### Frozen Protected Files (Strict Zero Modification)
1. `core/execution/live_router.py`
2. `core/execution/smart_order_router.py`
3. `core/execution/reconciliation_ledger.py`
4. `core/execution/almgren_chriss.py`
5. `core/execution/idempotency.py`
6. `core/execution/kill_switch.py`
7. `core/execution/connectors/base.py`
8. `core/execution/connectors/binance_connector.py`
9. `core/execution/connectors/bybit_connector.py`
10. `core/database.py`
11. `app.py`
12. `tests/test_milestone18_sor_and_slicing.py`
13. `tests/test_milestone18_boss_adversarial.py`
14. `tests/test_milestone18_final_certification.py`

**Grade-E1 Isolation Guarantee:**
- All Grade-E1 code resides in `core/research/grade_e1/`.
- All Grade-E1 unit, adversarial, and integration tests reside in `tests/research/grade_e1/`.
- All Grade-E1 documentation and evidence reports reside in `docs/grade_e1/`.
- Zero live execution paths, zero database mutation of `data/trading_logs.db`, and zero connector calls will occur.

---

## 4. Reusable Infrastructure & Assets

The following existing modules provide battle-tested logic that Grade-E1 can interface with or reference:

| Module | Reusable Component | Purpose in Grade-E1 |
|---|---|---|
| `core/kronos/research/dataset_freeze.py` | `DatasetFreezeManager` | Validating sha256 checksums of the 9 frozen K9 datasets |
| `core/kronos/research/friction_evaluator.py` | `FrictionScenario`, `CANONICAL_FRICTION_SCENARIOS` | Baseline maker/taker fee tiers and conservative cost comparisons |
| `core/kronos/research/experiment_ledger.py` | `ExperimentLedger`, `ExperimentRecord` | Pattern for tamper-evident JSONL experiment recording |
| `core/statistical_defense.py` | `DeflatedSharpeEngine` | Statistical haircut calculations against multi-hypothesis selection bias |
| `core/data_streamer.py` | `generate_synthetic_candles` | Fallback synthetic candle verification if required |

---

## 5. Data Sufficiency & Microstructure Truth Audit

### Ingested Dataset Inventory (`data/research/datasets/manifest_k9.json`)
The repository contains 9 frozen datasets:
1. `K9_BTCUSDT_15m_464d2ff4`: 9,008 rows (15m spot candles, Binance)
2. `K9_BTCUSDT_1h_17250393`: 658 rows (1h resampled spot candles)
3. `K9_BTCUSDT_4h_5ee3b6a8`: 165 rows (4h resampled spot candles)
4. `K9_ETHUSDT_15m_1fb09fb3`: 7,179 rows (15m spot candles, Binance, with 12 documented missing intervals)
5. `K9_ETHUSDT_1h_41c0c757`: 267 rows (1h resampled spot candles)
6. `K9_ETHUSDT_4h_8e1a6bb7`: 74 rows (4h resampled spot candles)
7. `K9_SOLUSDT_15m_a016fbed`: 9,008 rows (15m spot candles, Binance)
8. `K9_SOLUSDT_1h_942a3153`: 658 rows (1h resampled spot candles)
9. `K9_SOLUSDT_4h_a09673a1`: 165 rows (4h resampled spot candles)

### Critical Epistemic Classification: `OHLCV_APPROXIMATION`
- **Fact:** The 9 frozen K9 datasets are discrete OHLCV candle records containing `[timestamp, open, high, low, close, volume]`.
- **Microstructure Reality:** They do **not** contain Level-2 (order book depth deltas, order queue sizes, quote cancellations) or Level-3 (individual trade messages with tick tags).
- **Mandatory Epistemic Label:** Under the SKY Epistemic Taxonomy, any queue position, fill estimation, or execution simulation built using this data must be explicitly labeled and reported as:
  $$\text{Evidence Grade} = \text{GRADE-E1: OHLCV\_APPROXIMATION}$$
- **Anti-Hallucination Invariant:** Under no circumstances will any component of Grade-E1 represent, claim, or serialize its outputs as `EMPIRICAL_L2_REPLAY` or `MATCHING_ENGINE_GROUND_TRUTH`. Doing so would violate the SKY Constitution and scientific integrity standards.

---

## 6. Microstructure Modeling Design Decisions

To provide rigorous, conservative, and mathematically sound maker simulation on OHLCV data without overstating alpha, Grade-E1 incorporates:

1. **Volume-Clock Queue Hurdle (Model Q1):**
   A passive limit order placed at the inside spread does not fill merely because `Low <= limit_price <= High`. It requires that a cumulative threshold of volume passes through that price level:
   $$V_{\text{threshold}} = \alpha \cdot V_{\text{bar}}$$
   where $\alpha \in [0.10, 0.30]$ models the queue ahead of our order.

2. **Empirical Penetration Depth Model (Model Q2):**
   Fill probability is modeled as a non-linear function of how deeply the candle penetrated past the limit price relative to the candle's total range:
   $$\text{Penetration Depth} = \frac{P_{\text{limit}} - \text{Low}}{\text{High} - \text{Low}} \quad (\text{for BUY orders})$$
   $$P(\text{Fill}) = \min\left(1.0, \max\left(0.0, \left(\frac{\text{Penetration Depth}}{\kappa}\right)^\gamma\right)\right)$$

3. **Causal Latency Models (L0, L1, L2):**
   - L0: Immediate placement (optimistic baseline).
   - L1: 50 ms deterministic network transit time.
   - L2: Stochastic log-normal delay with tail spikes simulating exchange congestion.

4. **Multi-Horizon Adverse Selection Markout ($\tau \in \{1, 5, 12, 24\}$ bars):**
   Direct measurement of post-fill price drift to capture adverse selection:
   $$\text{Markout}_\tau = \text{side\_sign} \cdot \left(\frac{P_{t+\tau} - P_{\text{fill}}}{P_{\text{fill}}}\right) \times 10{,}000 \text{ bps}$$
   A negative markout indicates that fills disproportionately occur right before the market moves against the order (toxic flow).

5. **Opportunity Cost Accounting:**
   Unfilled passive orders are tracked to measure missed alpha when the market runs away from the limit price, ensuring maker strategies are penalized for non-execution.

---

## 7. Conclusion & Gate 0 Sign-Off

Reconnaissance is complete:
- Architecture is mapped.
- Protected surface boundaries are verified and locked.
- Data realities and epistemic bounds (`OHLCV_APPROXIMATION`) are explicitly certified.
- Ready to proceed to Phase 1: Research Contract & Protected Surface Manifest.
