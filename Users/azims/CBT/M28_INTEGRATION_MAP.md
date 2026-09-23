# M28 INTEGRATION MAP: SUBSYSTEM CONNECTIVITY & DATA FLOW

**Document ID:** `M28-MAP-001`  
**Repository:** SKY / Crypto Brain Terminal (CBT)  
**Target Milestone:** Milestone 28 — Cross-Domain Macro-Micro Causal Synthesis  
**Status:** ARCHITECTURALLY VERIFIED  

---

## 1. System Integration Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MILESTONE 27: INTELLIGENCE FABRIC                      │
│                                                                             │
│   global_intelligence_records (SQLite WAL)  •  NarrativeRadar Clusters      │
│   (Published At, Collected At, Domain, Entities, Epistemic Grade, Content)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│           POINT-IN-TIME AVAILABILITY & CAUSAL FIREWALL (MILESTONE 28)       │
│                                                                             │
│   - PointInTimeEventContract: Asserts published_at <= cutoff_utc            │
│   - Zero-Lookahead Verifier: Prevents future-event leakage                  │
│   - Epistemic Prior Scaler: VERIFIED_PRIMARY (1.0) -> SPECULATION (0.3)     │
│   - Failure Memory Pre-Screener: Queries failure_memory.db (Jaccard check)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 CROSS-DOMAIN CAUSAL SYNTHESIZER (MILESTONE 28)              │
│                                                                             │
│   - Causal Mechanism Registry: Versioned economic transmission mechanisms   │
│   - Research Family Registry: Preregistered hypothesis families & endpoints │
│   - Microstructure Gates:                                                   │
│       * CVDAbsorptionEngine (core/cvd_absorption.py)                       │
│       * OrderBookImbalanceEngine (core/orderbook_imbalance.py)              │
│       * SMCEngine (core/smc_engine.py: FVG, Order Blocks, Liquidity Sweeps) │
│   - Formulates Structured CausalHypothesis (H0 vs H1, Falsification)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               RESEARCH LAB DISPATCH & EXPERIMENT LEDGER                     │
│                                                                             │
│   - ResearchStorage (core/autonomous_research/storage/)                     │
│   - MultipleTestingRecord (Deflated Sharpe, WRC, Family-Wise Trial Count)   │
│   - EmpiricalTester: Chronological walk-forward replay & 3-tier frictions   │
│   - CONSTITUTIONAL ISOLATION: Stamped NON_EXECUTABLE_RESEARCH_HYPOTHESIS    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   REST API & FRONTEND VISUAL COCKPIT                        │
│                                                                             │
│   - Routes: /api/v1/intelligence/hypotheses/* (core/intelligence/routes.py) │
│   - UI: IntelligenceCockpit.tsx -> Causal Hypothesis Lab Subview            │
│   - UI Invariant: Live Execution Authority = STRICTLY NONE                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Integration Matrix

| Source Subsystem | Target Subsystem | Interaction Type | Data Contract | Causal / Security Guard |
|:---|:---|:---|:---|:---|
| `core/intelligence/schema.py` (`global_intelligence_store`) | `core/intelligence/causal_synthesizer.py` | Query records | `IntelligenceRecord` with content hash & published timestamp | Zero-lookahead cutoff: `published_at_utc <= observation_t` |
| `core/intelligence/narrative_radar.py` | `core/intelligence/causal_synthesizer.py` | Query clusters | `NarrativeCluster` (velocity, entities, credibility tag) | Hype-driven clusters require mandatory mean-reversion framing |
| `core/cvd_absorption.py` | `core/intelligence/causal_synthesizer.py` | Condition gate | `CVDAnalysisResult` (`absorption_type`, `volume_ratio`) | Evaluated on closed candle $t-1$ |
| `core/orderbook_imbalance.py` | `core/intelligence/causal_synthesizer.py` | Condition gate | `OBIAnalysisResult` (`obi_score`, `vpin`, `regime`) | Microstructure depth snapshots strictly point-in-time |
| `core/smc_engine.py` | `core/intelligence/causal_synthesizer.py` | Structural zone | `SMCPattern` (FVG, Order Block, Liquidity Sweep) | Invalidation price & empirical baseline expectancy |
| `core/autonomous_research/failure_memory.py` | `core/intelligence/causal_firewall.py` | Pre-screen | `check_prior_failures(text, symbol, tf, params)` | Jaccard $\ge 0.50$ with exact context rejects formulation |
| `core/statistical_defense.py` | `core/intelligence/hypothesis_schema.py` | Multiplicity audit | `StatisticalPolicy` (`dsr_tier1_threshold`, trial budgets) | Daily trial budget (200) & batch trial budget (50) |
| `core/intelligence/routes.py` | `app.py` | FastAPI inclusion | `/api/v1/intelligence/hypotheses/*` | Protected by `Depends(require_api_key)` |
| `frontend/src/services/api.ts` | `frontend/src/components/IntelligenceCockpit.tsx` | Typed REST client | `CausalHypothesis`, `HypothesisSynthesisResponse` | Immutable watermark: `NON_EXECUTABLE_RESEARCH_HYPOTHESIS` |

---

## 3. Reusable Code vs. New Code Separation

To prevent code bloat and protect architectural stability:

### What We REUSE (DO NOT RE-IMPLEMENT):
1. **Microstructure Algorithms:** Do not rewrite CVD, OBI, or SMC calculations. Use `cvd_absorption_engine`, `orderbook_imbalance_engine`, and `smc_engine`.
2. **Failure Memory Engine:** Use existing `failure_memory.check_prior_failures()` and `failure_memory.record_failure_autopsy()`.
3. **Statistical Defense:** Use existing `StatisticalPolicy`, `calculate_deflated_sharpe_ratio`, and Politis-Romano block bootstrap.
4. **FastAPI Route Mount:** Mount all hypothesis endpoints under `core/intelligence/routes.py` without modifying the M18 certified core of `app.py`.

### What We BUILD NEW in Milestone 28:
1. `core/intelligence/point_in_time.py`: `PointInTimeEventContract` with revision lineage and strict timezone/timestamp verification.
2. `core/intelligence/causal_mechanisms.py`: Structured, versioned Causal Mechanism Registry and Research Family Registry.
3. `core/intelligence/hypothesis_schema.py`: Canonical `CausalHypothesis` dataclass and SQLite ledger `causal_hypotheses_ledger`.
4. `core/intelligence/causal_firewall.py`: 9-gate Causal Firewall Validator returning structured audit decisions.
5. `core/intelligence/causal_synthesizer.py`: Cross-domain compiler formulating testable $H_0 \text{ vs } H_1$ hypotheses.
6. `frontend/src/components/CausalHypothesisLab.tsx`: Interactive research interface in `IntelligenceCockpit.tsx`.
