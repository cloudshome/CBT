# Milestone 31: Pre-Implementation Forensic Audit & Specification

## Continuous Forward Validation, Paper Execution & Microstructure Markout Research League

**Document Version:** 1.0.0  
**Audit Date:** September 24, 2026  
**Governance Tier:** Level 0 (AGENTS.md) / Level 1 (.specify/memory/constitution.md) / Level 2 (docs/QUANT_RESEARCH_PROTOCOL.md)  
**Execution Authority:** `NON_EXECUTABLE_RESEARCH_HYPOTHESIS`  
**Capital Authorization:** `REAL_CAPITAL_ENABLED = False` (Permanent Capital Firewall)  
**M18 Certified Surface:** 100% Frozen & Untouched  

---

## 1. Executive Summary & Forensic Audit Scope

In strict adherence to the **Milestone 31 Master Implementation Directive**, this pre-implementation forensic audit investigates the active repository architecture before a single line of production code is written.

Milestone 31 establishes an **empirical forward-validation and falsification laboratory**. Its sole purpose is to observe how human-approved research strategies behave when subjected to live market data streams, realistic queue/fill constraints, and microsecond adverse selection—without deploying real capital or granting execution authority.

---

## 2. Forensic Codebase Reconnaissance

| Subsystem | Existing Files Audited | Findings & Structural Interfaces | M31 Architectural Decision |
|:---|:---|:---|:---|
| **Causal Synthesis** | `core/intelligence/causal_synthesizer.py`<br>`core/intelligence/causal_mechanisms.py` | 7 registered research families with dynamic lookbacks and parameter bounds. | Admitted strategies inherit immutable `family_id` and parameter bounds. |
| **Preregistration** | `core/intelligence/research_contract.py`<br>`core/intelligence/plan_store.py` | `PreregisteredResearchContract` and `DurableExperimentPlan` use cryptographic SHA-256 seals. | Strategy admission validates contract seal against tampering. |
| **Replay & Audit** | `core/intelligence/crawler/autonomous_replay_runner.py`<br>`core/intelligence/crawler/statistical_auditor.py`<br>`core/intelligence/crawler/dossier_generator.py` | M30-D produces sealed Markdown dossiers at `data/research_dossiers/{plan_id}.md` with `AWAITING_HUMAN_OPERATOR_REVIEW`. | Admission requires verified dossier path and valid cryptographic digest. |
| **Failure Memory** | `core/autonomous_research/failure_memory.py`<br>`core/intelligence/crawler/replay_autopsy_bridge.py` | 5-stage `QuarantineLevel` (`NONE` to `PERMANENT_REJECTION`) persisted in SQLite. | League checks mechanism quarantine status before admission. |
| **M18 Execution** | `core/execution/*` (14 certified files) | Frozen under Milestone 18 Production Pass certification (`2acbff25...`). | **STRICT ISOLATION:** M31 modules MUST reside in `core/intelligence/forward_validation/`. Zero imports of `core/execution/*`. |
| **Market Data** | `core/mbo/feed_adapter.py`<br>`core/mbo/order_book_l3.py` | L3 discrete queue and depth reconstruction utilities exist in `core/mbo/`. | M31 will build a decoupled `LiveMarketDataGateway` in `core/intelligence/forward_validation/gateway.py` with multi-venue feed support (Binance, Hyperliquid). |

---

## 3. Concrete Contract Specification: `StrategyAdmission`

No strategy may enter forward paper validation automatically. Admission requires a formal, immutable admission contract signed by a human operator.

### 3.1 Pydantic Model (`core/intelligence/forward_validation/models.py`)

```python
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

class AdmissionStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ADMITTED = "ADMITTED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"

class EvaluationMode(str, Enum):
    SHADOW_ONLY = "SHADOW_ONLY"
    PAPER_EXECUTION = "PAPER_EXECUTION"

class StrategyAdmission(BaseModel):
    """
    Formal, immutable contract freezing strategy identity, parameters,
    and evaluation window before forward live data observation.
    """
    admission_id: str = Field(..., description="Unique immutable admission ID: ADM-<timestamp>-<hash>")
    dossier_id: str = Field(..., description="Path or ID of approved research dossier")
    hypothesis_id: str = Field(..., description="Source CausalHypothesis ID")
    plan_id: str = Field(..., description="Preregistered DurableExperimentPlan ID")
    strategy_genome_id: str = Field(..., description="Mechanism/genome identifier (e.g. MEC_MOMENTUM_EXP_v1)")
    research_protocol_hash: str = Field(..., description="SHA-256 of governing research protocol")
    parameter_hash: str = Field(..., description="SHA-256 digest of frozen parameter dictionary")
    frozen_parameters: dict[str, Any] = Field(..., description="Immutable strategy parameters")
    dataset_hash: str = Field(..., description="SHA-256 of historical validation dataset")
    admission_timestamp_utc: float = Field(..., description="Timestamp of human admission approval")
    evaluation_start_utc: float = Field(..., description="Start timestamp of forward evaluation window")
    evaluation_end_utc: float = Field(..., description="End timestamp of forward evaluation window")
    evaluation_mode: EvaluationMode = Field(default=EvaluationMode.PAPER_EXECUTION)
    market_universe: list[str] = Field(..., description="Approved trading pairs (e.g. ['BTCUSDT', 'ETHUSDT'])")
    timeframe: str = Field(default="1m", description="Primary candle timeframe")
    expected_holding_period_sec: float = Field(..., description="Target trade horizon in seconds")
    suspension_policy_version: str = Field(default="v1.0", description="Predefined circuit breaker policy ID")
    human_approval_reference: str = Field(..., description="Cryptographic human signature or authorization token")
    status: AdmissionStatus = Field(default=AdmissionStatus.ADMITTED)
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: Literal[False] = False
```

---

## 4. Live Market Data Gateway & Feed Integrity Protocol

### 4.1 Timestamp Granularity
Every market event processed by the forward gateway must record six explicit timestamps:
1. `exchange_event_time_utc`: Exchange matching engine matching timestamp.
2. `exchange_transaction_time_utc`: Exchange broadcast timestamp.
3. `local_receive_time_utc`: Timestamp when packet arrived at local NIC.
4. `processing_time_utc`: Timestamp when normalizer completed parsing.
5. `feature_available_time_utc`: Timestamp when features became available for strategy evaluation.
6. `decision_time_utc`: Timestamp when strategy generated a hypothetical action.

### 4.2 Order Book Integrity Invariants
The gateway tracks orderbook snapshots and delta updates, enforcing:
- **Monotonic Sequence:** If `u <= last_u` or `pu != prev_u`, trigger immediate resynchronization.
- **Crossed Book Guard:** If $\text{best\_bid} \ge \text{best\_ask}$, flag `DATA_QUALITY_DEGRADED` and suspend markout recording.
- **Stale Book Guard:** If no update received for $> 5000\text{ms}$, set status `STALE_FEED` and reject paper orders.

---

## 5. Realistic Paper Fill Simulator

Hypothetical fills must never assume infinite liquidity or instantaneous execution at mid-price.

### 5.1 Market Order Simulation
1. **Depth Walking:** Order walks the live order book depth up to requested quantity.
2. **Effective Price:** Weighted average fill price across touched price levels.
3. **Latency Slippage:** Apply adverse selection slippage penalty based on order size and volatility.
4. **Exchange Fees:** Apply Tier 2 taker fee (e.g. 5 bps for Binance Futures, 4.5 bps for Hyperliquid).
5. **Partial Fill:** If requested size > cumulative book depth within 100 bps, fill only available depth and mark remainder cancelled.

### 5.2 Limit Order Simulation
1. **Queue Position Modeling:** When placed, order is assigned queue depth behind existing resting liquidity at that price.
2. **Trade-Through Requirement:** A limit order is NOT filled simply because market trades at limit price. It requires cumulative trading volume at or through that price level exceeding its queue position.
3. **Cancellation Latency:** Model 50ms cancel/replace propagation delay.

---

## 6. Microstructure Markout Engine

Markouts measure price movement conditional on trade reference events across 4 horizons:
- **Horizons:** $h \in \{100\text{ms}, 1000\text{ms}, 5000\text{ms}, 30000\text{ms}\}$

### 6.1 Markout Formulations (For Buy Direction)
- **Mid-Price Markout ($M_{\text{mid}, h}$):**
  $$M_{\text{mid}, h} = \frac{P_{\text{mid}, t+h} - P_{\text{mid}, t}}{P_{\text{mid}, t}} \times 10^4 \quad (\text{bps})$$
- **Executable Markout ($M_{\text{exec}, h}$):**
  $$M_{\text{exec}, h} = \frac{P_{\text{bid}, t+h} - P_{\text{fill}, t}}{P_{\text{fill}, t}} \times 10^4 \quad (\text{bps})$$
- **Net Markout ($M_{\text{net}, h}$):**
  $$M_{\text{net}, h} = M_{\text{exec}, h} - \text{Fee}_{\text{bps}} - \text{EstimatedSlippage}_{\text{bps}}$$

If the book snapshot is stale or missing at $t+h$, markout status is recorded as `DATA_UNAVAILABLE` rather than fabricating zero drift.

---

## 7. Multi-Dimensional Drift Matrix (Backtest vs Forward)

To avoid naive Kolmogorov-Smirnov fallacies, drift is evaluated across 5 orthogonal dimensions:

| Dimension | Metric / Test | Threshold for `WATCH` | Threshold for `DEGRADED` / `SEVERE` |
|:---|:---|:---:|:---:|
| **Return Distribution** | 2-Sample KS test on returns | $p < 0.05$ | $p < 0.001$ with $D > 0.25$ |
| **Volatility Realization** | Ratio $\sigma_{\text{live}} / \sigma_{\text{backtest}}$ | $< 0.7$ or $> 1.5$ | $< 0.4$ or $> 2.5$ |
| **Markout Decay** | Forward $M_{\text{net}, 5\text{s}}$ vs Backtest Expectancy | Decay $> 30\%$ | Negative net markout ($M_{\text{net}} < 0$) |
| **Friction / Slippage** | Realized spread vs Modeled spread | Spread $> 1.5\times$ modeled | Spread $> 2.5\times$ modeled |
| **Regime Shift** | Dominant regime mismatch duration | $> 30\%$ time in unexpected regime | $> 70\%$ time in hostile regime |

---

## 8. Anti-Survivorship Bias & Immutability Rules

1. **All Strategies Persist:** The League Registry table (`forward_strategy_league`) is strictly append-only. Underperforming strategies transition to `SUSPENDED` or `FAILED` and remain permanently visible on the dashboard with their sample size and failure reason.
2. **Denominator Transparency:** Every dashboard display, API response, and report must include:
   - Total observation count ($N$)
   - Observation age (days in forward validation)
   - Estimated standard error of the mean return
3. **No In-Flight Tuning:** If parameters are adjusted, a new `StrategyAdmission` record must be created. The prior strategy's track record is never overwritten or merged.

---

## 9. Conflict Analysis & The Golden Conflict Protocol

- **Conflict Check:** Does M31 touch `core/execution/*`? **NO.**
- **Conflict Check:** Does M31 enable live trading? **NO.**
- **Conflict Check:** Does M31 mutate production databases? **NO.** All tests run against in-memory or sandbox SQLite databases (`test_tmp_forward_*.db`).

**Conclusion:** Zero constitutional conflicts detected.

---

## 10. Pre-Implementation Audit Signoff

The forensic audit confirms that the architecture is sound, interfaces are cleanly decoupled, and the project is authorized to proceed to **Phase 1: Strategy League Registry Implementation**.
