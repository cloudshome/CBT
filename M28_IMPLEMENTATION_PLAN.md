# M28 IMPLEMENTATION PLAN & TECHNICAL BLUEPRINT

**Document ID:** `M28-PLAN-001`  
**Repository:** SKY / Crypto Brain Terminal (CBT)  
**Target Milestone:** Milestone 28 — Cross-Domain Macro-Micro Causal Synthesis & Autonomous Strategy Hypothesis Generation  
**Architect:** Senior Quantitative Systems Architect & Principal Python Engineer  
**Commit Baseline:** `4cd8c45`  
**Status:** READY FOR SURGICAL EXECUTION  

---

## 1. Architectural Scope & Implementation Goals

Milestone 28 delivers the institutional **Causal Research Compiler** bridging Milestone 27 Global Intelligence Fabric with existing microstructure engines (`CVDAbsorptionEngine`, `OrderBookImbalanceEngine`, `SMCEngine`), Failure Memory, and the Autonomous Research Lab.

### Core Objectives:
1. **Point-in-Time Causality Engine (`core/intelligence/point_in_time.py`):** Immutable event envelopes enforcing strict publication vs. observation timestamps and cryptographic verification.
2. **Causal Mechanism & Research Family Registry (`core/intelligence/causal_mechanisms.py`):** Formal economic transmission channels and 5 preregistered research families.
3. **Canonical Hypothesis Schema & Ledger (`core/intelligence/hypothesis_schema.py`):** Pydantic v2 schemas and SQLite WAL persistence in `causal_hypotheses_ledger`.
4. **9-Gate Causal Firewall Validator (`core/intelligence/causal_firewall.py`):** Deterministic pre-screening covering temporal integrity, epistemic priors, failure memory, and execution isolation.
5. **Cross-Domain Causal Synthesizer (`core/intelligence/causal_synthesizer.py`):** Algorithmic compilation of testable hypotheses ($H_0 \text{ vs } H_1$) with concrete microstructure gates and falsification criteria.
6. **REST API Surface (`core/intelligence/routes.py`):** Typed endpoints registered without touching `app.py`.
7. **Frontend Causal Hypothesis Lab (`frontend/src/components/IntelligenceCockpit.tsx`):** Interactive UI for exploring, synthesizing, and auditing hypotheses.
8. **Adversarial Test Battery (`tests/intelligence/test_milestone28_causal_synthesis.py`):** Full coverage of causality, isolation, multi-testing, and fail-closed behaviors.

---

## 2. File-by-File Technical Specification

### 2.1 [NEW] `core/intelligence/point_in_time.py`
- **Class:** `PointInTimeEventContract` (Pydantic v2 BaseModel)
  - Fields: `event_id`, `source_record_id`, `event_type`, `domain`, `headline`, `published_at_utc`, `collected_at_utc`, `effective_availability_utc`, `dissemination_buffer_seconds`, `initial_metric_value`, `revised_metric_value`, `revision_number`, `content_hash_sha256`, `epistemic_grade`, `metadata`.
  - Methods:
    - `from_intelligence_record(record: IntelligenceRecord, dissemination_buffer_seconds: float = 5.0) -> PointInTimeEventContract`
    - `verify_temporal_precedence(market_observation_start_utc: float) -> bool`
    - `effective_cutoff() -> float`

### 2.2 [NEW] `core/intelligence/causal_mechanisms.py`
- **Enums & Registries:**
  - `ResearchFamilyId`: `MACRO_LIQUIDITY_TRANSMISSION`, `INFLATION_GROWTH_SURPRISE`, `REGULATORY_POLICY_SHOCK`, `ONCHAIN_STABLECOIN_DISLOCATION`, `CROSS_ASSET_CONTAGION`.
  - `CausalTransmissionType`: `LIQUIDITY_WITHDRAWAL`, `VOLATILITY_EXPANSION`, `MOMENTUM_ACCELERATION`, `MEAN_REVERSION_DISLOCATION`, `ABSORPTION_EXHAUSTION`.
  - `MicrostructureReceptorType`: `CVD_ABSORPTION`, `L2_ORDERBOOK_IMBALANCE`, `SMC_ORDER_BLOCK`, `SMC_FVG`, `SMC_LIQUIDITY_SWEEP`.
  - `CausalMechanism`: Structured descriptor linking family, transmission channel, economic rationale, and microstructure receptor.
  - `CAUSAL_MECHANISM_REGISTRY`: Preregistered institutional dictionary of valid mechanisms.
  - `RESEARCH_FAMILY_REGISTRY`: Preregistered definitions with trial limits and target assets.

### 2.3 [NEW] `core/intelligence/hypothesis_schema.py`
- **Models:**
  - `CausalHypothesis`:
    - `hypothesis_id`: str (`HYPO-YYYYMMDD-UUID`)
    - `family_id`: ResearchFamilyId
    - `mechanism_id`: str
    - `macro_event_contract`: PointInTimeEventContract
    - `target_asset`: str (e.g. `BTC/USDT`, `ETH/USDT`)
    - `timeframe`: str (e.g. `1m`, `5m`, `15m`)
    - `null_hypothesis`: str ($H_0$)
    - `alternative_hypothesis`: str ($H_1$)
    - `microstructure_conditions`: Dict[str, Any] (exact CVD/OBI/SMC thresholds)
    - `falsification_criteria`: Dict[str, Any] (metrics that prove $H_1$ false)
    - `epistemic_prior_weight`: float ($0.20 \text{ to } 1.00$)
    - `status`: `DRAFT`, `FIREWALL_VALIDATED`, `REJECTED`, `SUBMITTED_TO_LAB`, `FAILED_VALIDATION`, `CERTIFIED_EXPLORATORY`
    - `rejection_reason`: Optional[str]
    - `execution_authority`: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"]
    - `real_capital_enabled`: Literal[False]
    - `created_at_utc`: float
  - `SynthesizedExperimentPlan`: Plan ready for Autonomous Research Lab dispatch.
  - `HypothesisLedgerManager`: SQLite WAL manager for `causal_hypotheses_ledger`.

### 2.4 [NEW] `core/intelligence/causal_firewall.py`
- **Class:** `CausalFirewallValidator`
  - 9 Deterministic Gates:
    1. `GATE_1_EXECUTION_AUTHORITY_ISOLATION`: Asserts `real_capital_enabled == False` and `execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"`.
    2. `GATE_2_POINT_IN_TIME_CAUSALITY`: Asserts $t_{\text{effective\_availability}} < t_{\text{microstructure\_start}}$.
    3. `GATE_3_CONTENT_HASH_INTEGRITY`: Verifies SHA-256 matches payload.
    4. `GATE_4_EPISTEMIC_PRIOR_VERIFICATION`: Verifies source epistemic tier and prior weight.
    5. `GATE_5_FAILURE_MEMORY_PRESCREEN`: Checks Jaccard similarity against `FailureMemoryEngine` ($< 0.50$).
    6. `GATE_6_MULTIPLE_TESTING_BUDGET`: Verifies family daily trial budget has not been exhausted.
    7. `GATE_7_FALSIFIABILITY_SPECIFICATION`: Ensures $H_0$, $H_1$, and falsification criteria are non-empty and mathematically testable.
    8. `GATE_8_MICROSTRUCTURE_FEASIBILITY`: Validates thresholds against historical engine distributions.
    9. `GATE_9_REVISION_VINTAGE_ISOLATION`: Flags unverified revisions or lookahead vintages.
  - Return: `CausalFirewallDecision(passed: bool, gate_results: Dict[str, bool], violations: List[str])`.

### 2.5 [NEW] `core/intelligence/causal_synthesizer.py`
- **Class:** `CausalHypothesisSynthesizer`
  - Bridges `IntelligenceRecord` / `NarrativeCluster` with `CVDAbsorptionEngine`, `OrderBookImbalanceEngine`, and `SMCEngine`.
  - Methods:
    - `synthesize_from_event(record: IntelligenceRecord, target_asset: str = "BTC/USDT", timeframe: str = "5m") -> Optional[CausalHypothesis]`
    - `synthesize_from_narrative_cluster(cluster_id: str, target_asset: str = "BTC/USDT") -> List[CausalHypothesis]`
    - `batch_synthesize(records: List[IntelligenceRecord]) -> List[CausalHypothesis]`
    - `submit_to_research_lab(hypothesis: CausalHypothesis) -> SynthesizedExperimentPlan`

### 2.6 [MODIFY] `core/intelligence/routes.py`
- Mount Milestone 28 REST endpoints:
  - `GET /api/v1/intelligence/hypotheses`: List synthesized hypotheses (filtered by family, status, asset).
  - `POST /api/v1/intelligence/hypotheses/synthesize`: Trigger causal synthesis on specified intelligence records.
  - `GET /api/v1/intelligence/hypotheses/families`: Return preregistered research families and mechanisms.
  - `GET /api/v1/intelligence/hypotheses/stats`: Return trial budget stats and multiple-testing records.
  - `POST /api/v1/intelligence/hypotheses/{hypothesis_id}/validate`: Run the 9-gate Causal Firewall on a hypothesis.

### 2.7 [MODIFY] `frontend/src/types.ts`
- Add TypeScript interfaces:
  - `CausalHypothesis`, `PointInTimeEventContract`, `ResearchFamily`, `CausalMechanism`, `CausalFirewallDecision`, `HypothesisStats`.

### 2.8 [MODIFY] `frontend/src/services/api.ts`
- Add API methods:
  - `getHypotheses()`, `synthesizeHypotheses()`, `getResearchFamilies()`, `getHypothesisStats()`, `validateHypothesis()`.

### 2.9 [MODIFY] `frontend/src/components/IntelligenceCockpit.tsx`
- Add interactive `Causal Hypothesis Lab` subtab:
  - Preregistered Family Cards & mechanism selector.
  - Synthesized Hypotheses Table (Status, Epistemic Prior, Mechanism, $H_0/H_1$, Firewall Check).
  - Interactive Firewall Audit Modal showing passing/failing gates.
  - Strict UI Banner: `RESEARCH ISOLATION ACTIVE • REAL CAPITAL DISABLED`.

### 2.10 [NEW] `tests/intelligence/test_milestone28_causal_synthesis.py`
- 20+ comprehensive unit and integration tests:
  - Temporal causality & lookahead failure detection.
  - Point-in-time contract vintage verification.
  - Causal mechanism registry integrity.
  - 9-Gate Firewall validation (all pass, execution breach rejected, failure memory overlap rejected).
  - Cross-domain synthesizer logic with mock microstructure signals.
  - REST route testing and database persistence.
  - Multi-testing trial budget increment testing.

---

## 3. Pre-Merge Verification Checklist

- [ ] All 6 Milestone 28 Audit Deliverables in place.
- [ ] 14 Milestone 18 certified files untouched (`scripts/verify_m18_certification.py` passes 149/149).
- [ ] `app.py` untouched.
- [ ] Pytest suite green (`tests/intelligence/test_milestone28_causal_synthesis.py` 100% pass).
- [ ] All intelligence tests green (`pytest tests/intelligence/`).
- [ ] All execution tests green (`pytest tests/execution/`).
- [ ] Ruff linting green (0 errors).
- [ ] Ruff format check green (100% compliant).
- [ ] Frontend ESLint green (0 errors).
- [ ] Frontend build green (`npm --prefix frontend run build`).
- [ ] `M28_FINAL_IMPLEMENTATION_REPORT.md` authored and verified.
