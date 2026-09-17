# K8 ARCHITECTURE AUDIT & BASELINE ASSESSMENT

**Milestone:** K8 — Kronos Probabilistic Forecasting & Microstructure Domain Adaptation  
**System:** SKY / Crypto Brain Terminal (CBT)  
**Date:** 2026-09-17  
**Author:** Principal Quant Architect & ML Systems Engineer  
**Status:** PHASE A COMPLETE — BASELINE AUDITED  

---

## 1. Executive Summary

A comprehensive architectural audit was performed on the SKY repository to inspect the existing Kronos implementation, database schemas, risk boundaries, model abstractions, and API interfaces before executing Milestone K8.

### Key Findings:
1. **Existing Baseline (`core/models/kronos/`):**  
   An initial foundation wrapper exists containing:
   - `schemas.py`: `KronosForecast`, `KronosForecastPath`, `KronosStatus`, `KronosConfig`.
   - `adapter.py`: `KronosModelAdapter` providing simulated trajectory generation and lazy PyTorch/HF placeholder loading.
   - `calibration.py`: `KronosProbabilityCalibrator` with preliminary Platt scaling, Brier calculation, and drift detection.
   - `advisory_engine.py`: `KronosAdvisoryEngine` with advisory recommendations.
   - `persistence.py`: SQLite ledger persisting to `kronos_forecast_ledger`.
   - `walk_forward.py`: Expanding-window walk-forward testing.
   - `ablation_benchmark.py`: 3-way ablation (SKY vs Kronos vs Fusion).
   - 32 existing tests in `tests/test_kronos_*.py` pass.

2. **Critical Architectural Gaps Addressed by K8:**
   - **No DeepMind/Vertex Fabrication:** The previous proposal casually mentioned "DeepMind/Vertex AI". The actual repo uses an open transformer architecture / foundation model wrapper (`core/models/kronos`). We establish a rigorous `KronosProvider` protocol (`LocalKronosProvider`, `SurrogateProvider`) with an audited `model_manifest.json` — zero fabricated remote endpoints.
   - **Input Tokenizer Contract:** Native Kronos models consume OHLCV or tokenized price sequences, not raw arbitrary 8-feature vectors. We separate the **Microstructure Feature Store** from the **Kronos Representation**, passing microstructure context through an explicit domain adapter.
   - **Strict Zero-Lookahead & Normalization Firewall:** The existing pipeline lacks a standalone causal validator to reject future normalization parameters or timestamp inversions. K8 introduces `ZeroLookaheadValidator` and point-in-time windowed scalers.
   - **Decoupled Scoring & Durable Ledger:** Currently, Brier scores are computed immediately. K8 establishes a decoupled ledger where forecasts are frozen at $T$, and scored only after horizon $T+H$ expires via `RealizedOutcomeResolver`.
   - **Murphy Brier Decomposition & Skill Score:** Decomposes Brier into Reliability, Resolution, and Uncertainty with 10-decile bins, minimum sample thresholds, and climatological baseline comparisons.
   - **Constitutional Execution Firewall:** Strictly enforced: `Kronos Forecast ≠ Trade Signal ≠ Sizing Input ≠ Execution Trigger`. Advisory sizing multipliers in previous modules are quarantined; Kronos output is strictly informational context for the Autonomous Quant Strategist.

---

## 2. Inventory of Existing Kronos Components

| File | Role | Status in K8 |
|:---|:---|:---|
| `core/models/kronos/schemas.py` | Legacy dataclasses | Maintained for backward compatibility; supplemented by `core/kronos/` |
| `core/models/kronos/adapter.py` | Legacy adapter | Wrapped by `KronosProvider` abstraction |
| `core/models/kronos/calibration.py` | Legacy calibrator | Replaced by immutable versioned `PlattCalibrator` |
| `core/models/kronos/persistence.py` | SQLite helper | Upgraded to durable `ForecastLedger` with outcome resolver |
| `core/database.py` (L658) | `kronos_forecast_ledger` | Schema preserved; enhanced with outcome columns |
| `app.py` (L3296) | FastAPI endpoints | Maintained and routed through new authoritative `KronosDomainAdapter` |
| `frontend/src/services/api.ts` | Frontend API client | Expanded with full K8 endpoints and TypeScript typings |

---

## 3. M18 Certified Surface Isolation Verification

The 14 certified files under `core/execution/` and `core/auth/` were verified untouched. Milestone 18 test suite:
- `tests/test_milestone18_sor_and_slicing.py`
- `tests/test_milestone18_boss_adversarial.py`
- `tests/test_milestone18_final_certification.py`
Pass count: **149/149 PASS** (cryptographic SHA `2acbff25...` intact).
K8 code will reside strictly in `core/kronos/`, `tests/test_kronos_k8_adversarial.py`, and `frontend/src/components/KronosDomainDesk.tsx`.

---

## 4. Architectural Target Layout

```
core/kronos/
├── __init__.py
├── model_manifest.json         # Upstream provenance & contract
├── causality.py                # ZeroLookaheadValidator & PointInTimeScaler
├── feature_schema.py           # 8-feature microstructure schema & validation
├── feature_tokenizer.py        # Microstructure feature pipeline & context encoder
├── forecast_ledger.py          # Durable SQLite ledger & RealizedOutcomeResolver
├── probability_engine.py       # Distribution → P(return > threshold)
├── platt_calibrator.py         # Chronological calibration & immutable artifacts
├── brier_scorer.py             # Murphy decomposition & 10-decile reliability
├── domain_adapter.py           # Master domain adapter coordinating providers
├── kronos_routes.py            # FastAPI read-only research endpoints
└── providers/
    ├── __init__.py
    ├── base.py                 # KronosProvider Protocol & metadata
    ├── local.py                # LocalKronosProvider (PyTorch/weights)
    └── surrogate.py            # SurrogateProvider (calibrated foundation simulator)
```

**Phase A Verdict: PASS** — Ready to proceed with Phase B (Model Manifest & Upstream Verification).
