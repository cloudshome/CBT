# SKY × KRONOS — Architecture & Quantitative Integration Review

> **Document Version:** 1.0.0 (Research Specification)  
> **Status:** MILESTONE K0 COMPLETE (Discovery & Integration Design)  
> **Author:** Antigravity (Senior Quantitative Architect & Guardian)  
> **Reference Repository:** `https://github.com/shiyu-coder/Kronos`  
> **Integration Target:** SKY 12-Layer Quantitative Architecture  

---

## 1. Executive Summary

This document establishes the official architectural review and integration boundaries for incorporating **Kronos** (an open-source autoregressive financial time-series foundation model) into the **SKY quantitative trading and market intelligence system**.

The integration does **not** treat Kronos as a trading bot or decision oracle. Instead, Kronos serves strictly as an **autoregressive probabilistic path forecasting engine** operating within **Layer 5 (Probabilistic Path Simulation & Scenario Engine)** of SKY.

---

## 2. Core Non-Negotiable Integration Principles

### 2.1 Principle 1: Forecast $\neq$ Signal
Upstream Kronos outputs raw predicted financial sequences $\hat{Y} = [\hat{y}_{t+1}, \dots, \hat{y}_{t+H}]$ (OHLCV values). It does not know transaction costs, slippage, liquidity constraints, or regime-conditional expectancy.

The mandatory processing pipeline is:
```
RAW KRONOS FORECAST
        ↓
SKY FORECAST INTERPRETER (Expected Return, Dispersion, Consensus)
        ↓
EVIDENCE DOSSIER FUSION (8-Pillar Microstructure + Macro Beta)
        ↓
PROBABILITY CALIBRATOR (Platt Scaling & Brier Score)
        ↓
DECISION COMMITTEE (Bull / Bear / Skeptic ~70% NO-TRADE baseline)
        ↓
DETERMINISTIC RISK GATE (Drawdown, Exposure, Max Risk)
        ↓
PAPER TRADING / SMART ORDER ROUTER
```

### 2.2 Principle 2: Zero Lookahead & Strict Causal Isolation
* Kronos inputs must be supplied exclusively through SKY's [`CausalFirewall`](file:///c:/Users/azims/CBT/core/causal_firewall.py) and [`DataStreamer`](file:///c:/Users/azims/CBT/core/data_streamer.py).
* Input timestamps must strictly precede the point-in-time boundary $T$.
* Normalization parameters must use only historical statistics $[T - \text{lookback}, T]$.
* Kronos is never permitted to independently fetch external exchange data.

### 2.3 Principle 3: Graceful Degradation & 24/7 Resilience
* Kronos operates with lazy model loading and CPU fallback.
* If weights are unavailable, CUDA OOM occurs, or inference times out, the system emits `KRONOS_UNAVAILABLE`.
* SKY core trading logic and deterministic risk management continue operating uninterrupted.

---

## 3. System Architecture & Component Mapping

```
SKY SYSTEM ARCHITECTURE
│
├── core/                                   # Authoritative Quantitative Core (FastAPI :8000)
│   ├── models/kronos/                      # Isolated Kronos Adapter Module
│   │   ├── __init__.py                     # Clean package exports
│   │   ├── adapter.py                      # Hugging Face / PyTorch model wrapper
│   │   ├── schemas.py                      # KronosForecast & KronosConfig contracts
│   │   ├── preprocessing.py                # Causal input validation & tensor transforms
│   │   ├── interpretation.py              # Expected return, path dispersion, consensus
│   │   └── health.py                       # Latency monitor, memory bounds, fallback states
│   │
│   ├── causal_firewall.py                  # Point-in-time boundary enforcement
│   ├── market_path_simulator.py            # Combined Neural + Empirical Bootstrap Simulator
│   ├── expectancy_engine.py                # Friction-deducted Net EV calculation
│   └── risk_engine/                        # Deterministic risk guards (Master Authority)
│
├── src/                                    # Node.js Express Market Desk (:3000)
│   ├── services/marketDataService.ts       # Multi-exchange L2 tick collector
│   └── services/reconciliationService.ts   # Paper trade auto-reconciler
│
└── frontend/                               # React 18 + Vite PWA Terminal (:5173)
    └── src/components/TradingViewChart.tsx # Lightweight Charts v4 with forecast path cone
```

---

## 4. Derived Metric Mathematical Definitions

All metrics calculated from raw Kronos predicted trajectories must be explicitly identified as **SKY-derived**:

1. **Expected Return ($\mu_{\text{ret}}$):**
   $$\mu_{\text{ret}} = \frac{\hat{P}_{\text{horizon}} - P_{\text{current}}}{P_{\text{current}}}$$

2. **Median Path Return ($\tilde{\mu}_{\text{ret}}$):**
   $$\tilde{\mu}_{\text{ret}} = \text{median}\left(\left\{ \frac{\hat{P}^{(k)}_{\text{horizon}} - P_{\text{current}}}{P_{\text{current}}} \right\}_{k=1}^{K}\right)$$

3. **Forecast Path Dispersion ($\sigma_{\text{path}}$):**
   $$\sigma_{\text{path}} = \sqrt{\frac{1}{K}\sum_{k=1}^K \left( \hat{P}^{(k)}_{\text{horizon}} - \bar{P}_{\text{horizon}} \right)^2}$$

4. **Directional Consensus ($C_{\text{dir}}$):**
   $$C_{\text{dir}} = \frac{\max(N_{\text{bull}}, N_{\text{bear}})}{K} \in [0.5, 1.0]$$

5. **Model Uncertainty Metric ($U_{\text{model}}$):**
   $$U_{\text{model}} = 1.0 - (C_{\text{dir}} \times (1.0 - \min(1.0, \sigma_{\text{path}} / \text{ATR})))$$

---

## 5. Forecast Persistence & Replay Schema

Forecasts are stored in SQLite `experiment_store.db` under table `kronos_forecast_ledger`:

| Column | Type | Description |
| :--- | :--- | :--- |
| `forecast_id` | `TEXT PRIMARY KEY` | Unique UUID with timestamp prefix |
| `timestamp_ms` | `INTEGER` | Point-in-time calculation time $T$ |
| `symbol` | `TEXT` | Normalized symbol (`BTC/USDT`, `ETH/USDT`, `PAXG/USDT`) |
| `timeframe` | `TEXT` | Canonical timeframe (`5m`, `15m`, `1h`, `4h`) |
| `model_variant` | `TEXT` | `kronos-mini`, `kronos-small`, `kronos-base` |
| `lookback_bars` | `INTEGER` | Number of historical input candles |
| `horizon_bars` | `INTEGER` | Forward forecast horizon |
| `raw_forecast_json` | `TEXT` | Serialized predicted OHLCV matrix |
| `expected_return` | `REAL` | Point forecast return % |
| `path_dispersion` | `REAL` | Multi-sample trajectory variance |
| `consensus_score` | `REAL` | Directional agreement fraction |
| `realized_outcome_5m`| `TEXT` | Post-hoc verified outcome (`WIN`, `LOSS`, `INVALIDATED`) |
| `realized_pnl_usd` | `REAL` | Counterfactual hypothetical return |

---

## 6. Staged Implementation Plan (Milestones K0–K8)

* [x] **K0 — Discovery & Architecture Review** (`docs/KRONOS_ARCHITECTURE_REVIEW.md`)
* [ ] **K1 — Model Adapter & Schemas** (`core/models/kronos/`)
* [ ] **K2 — Causal Data Pipeline & OHLC Validator**
* [ ] **K3 — Research CLI & Forecast Freeze Ledger**
* [ ] **K4 — 3-Way Ablation Benchmark (SKY vs Kronos vs SKY+Kronos)**
* [ ] **K5 — Chronological Walk-Forward Out-of-Sample Validation**
* [ ] **K6 — Advisory Paper Trading Integration**
* [ ] **K7 — Reliability Calibration & Brier Score Scoring**
* [ ] **K8 — Optional Domain Adaptation Fine-Tuning**

---
