# M28 ARCHITECTURE AUDIT: INSTITUTIONAL SYSTEM REVIEW

**Document ID:** `M28-AUDIT-001`  
**Repository:** SKY / Crypto Brain Terminal (CBT)  
**Target Milestone:** Milestone 28 — Cross-Domain Macro-Micro Causal Synthesis & Autonomous Strategy Hypothesis Generation  
**Auditor:** Senior Quantitative Systems Architect & Research Governance Reviewer  
**Commit Baseline:** `4cd8c45` (HEAD of `main`)  
**Status:** AUDIT PASSED — ARCHITECTURE APPROVED FOR IMPLEMENTATION  

---

## 1. Executive Summary & Audit Mandate

In strict compliance with **PART II of the Master Antigravity Prompt** and the SKY System Constitution (`.specify/memory/constitution.md`), this audit evaluates the existing 18 infrastructural touchpoints across the repository before authoring any functional Milestone 28 code.

The goal of Milestone 28 is to construct an institutional **Causal Research Compiler**:
$$\text{External Intelligence (M27)} \times \text{Microstructure Dynamics (M1–26)} \longrightarrow \text{Preregistered Causal Hypotheses } (H_0 \text{ vs } H_1)$$
while enforcing absolute point-in-time causality ($\Delta t_{\text{event}} < t_{\text{market}}$), Multiple-Testing Protection (DSR, WRC), Failure Memory pre-screening, and zero live execution authority.

---

## 2. Forensic Review of the 18 Inspection Points

### 1. Repository Structure
- **Backend Core (`core/`):** 70+ institutional quantitative modules including `microstructure_engine.py`, `smc_engine.py`, `orderbook_imbalance.py`, `cvd_absorption.py`, `statistical_defense.py`, `walk_forward_cpcv.py`, `research_firewall.py`, `provenance_engine.py`, `macro_cognitive_engine.py`.
- **Integrations (`integrations/agent_reach/`):** Unified access fabric containing `adapter.py`, `policy.py`, `capability_registry.py`, `health.py`.
- **Intelligence Fabric (`core/intelligence/`):** Milestone 27 subsystem containing `schema.py`, `relevance_gate.py`, `evidence_classifier.py`, `narrative_radar.py`, `scout_daemon.py`, `routes.py`.
- **Autonomous Research Engine (`core/autonomous_research/`):** 11 core modules including `pipeline.py`, `hypothesis_generator.py`, `failure_memory.py`, `contradiction_engine.py`, `empirical_tester.py`, `storage/`.
- **Execution & Risk (`core/execution/`):** Frozen Milestone 18 smart order router, reconciliation ledger, live router, and kill switch.

### 2. Git Status and Baseline Verification
- Current branch: `main` at commit `4cd8c45`.
- Ancestor verification: Confirmed unbroken descendant of Milestone 18 certified commit `c9cc1cad` via `git merge-base --is-ancestor`.
- Working tree is 100% clean with zero staged/unstaged uncommitted files.

### 3. Existing Milestones 1–27 Implementation
- Milestones 1–17: Core analytics, indicators, L2 OBI, CVD absorption, SMC, volatility surfaces, arbitrage.
- Milestone 18: Smart Order Router (SOR) & Almgren-Chriss slicing (149/149 tests green, certified).
- Milestone 19: KMS key enclave & WebSocket fill stream reconciliation.
- Milestones 20–23: Live testnet burn-in campaign, rehearsal runner, and recovery state machines.
- Milestones 24–26: Strategy reality gateway, cross-venue collateral governor, and Strategy Reality Cockpit.
- Milestone 27: SKY Global Intelligence Fabric & Autonomous Web Scout (14/14 tests green, verified).

### 4. Global Intelligence Fabric Interfaces (`core/intelligence/`)
- **`IntelligenceRecord`:** Stored in SQLite WAL table `global_intelligence_records` (`trading_logs.db`).
- **`RelevanceGate`:** Clamps noise $< 0.70$ across 5 domains (`MACRO`, `CRYPTO`, `EQUITIES`, `QUANT_RESEARCH`, `SOCIAL`).
- **`EvidenceClassifier`:** Assigns epistemic tiers: `VERIFIED_PRIMARY`, `CORROBORATED_REPORT`, `UNVERIFIED_CLAIM`, `SPECULATION`.
- **`NarrativeRadar`:** Analyzes thematic clusters, propagation velocity, and cross-platform spread.
- **`AutonomousWebScout`:** 24/7 polite crawler running a prioritized frontier queue.

### 5. Ingestion and Provenance Schemas
- `core/provenance_engine.py`: Defines 4-vault architecture:
  1. `research_provenance_ledger` (Knowledge IDs: `K-00XXXX`)
  2. `knowledge_vault` (Conceptual mental models)
  3. `strategy_candidates` (Untested algorithmic rules)
  4. `evidence_vault` / `rejected_claims` (Empirical verification vs. autopsies)
- `core/autonomous_research/storage/research_storage.py`: Implements `ImmutableSourceRecord` with SHA-256 hash preservation.

### 6. Event Timestamps and Revision Handling
- **Current State:** `IntelligenceRecord` contains `published_at_utc: float` and `collected_at_utc: float`.
- **Audit Finding:** While UTC floats are stored, the codebase currently lacks a strict point-in-time availability contract distinguishing *provider first-availability time*, *event effective time*, and *source snapshot revision IDs*.
- **M28 Action:** Implement `PointInTimeEventContract` with explicit release vs. observation timestamps and revision tracking.

### 7. Microstructure Feature Schemas
- `core/microstructure_engine.py`: Computes L2 slope elasticity, depth ratio, order book imbalance, micro-price drift.
- `core/kronos/feature_schema.py`: Formats 8 normalized microstructure features (`ofi_norm`, `vpin`, `mid_return`, `spread_bps`, `depth_imb`, `trade_sign`, `vol_clock`, `resting_wall`) with causal clipping.

### 8. CVD, OBI, SMC, FVG Implementations
- `core/cvd_absorption.py`: `CVDAbsorptionEngine` detects `BULLISH_ABSORPTION` and `BEARISH_ABSORPTION` with intensity scores.
- `core/orderbook_imbalance.py`: `OrderBookImbalanceEngine` calculates depth-weighted OBI (`[-1.0, 1.0]`) and VPIN flow toxicity.
- `core/smc_engine.py`: `SMCEngine` detects Fair Value Gaps (`BULLISH_FVG`, `BEARISH_FVG`), Order Blocks (`BULLISH_OB`, `BEARISH_OB`), and Liquidity Sweeps (`BULLISH_SWEEP`, `BEARISH_SWEEP`).

### 9. Autonomous Research Pipeline
- `core/autonomous_research/pipeline.py`: Master coordinator executing `ingest_and_process`.
- Enforces 10 Anti-False-Knowledge Invariants.
- Coordinates between `hypothesis_generator.py`, `empirical_tester.py`, and `promotion_engine.py`.

### 10. Failure Memory
- `core/autonomous_research/failure_memory.py`: `FailureMemoryEngine` checks Jaccard concept keyword overlap, parameter clashing, and stores autopsy writeups in `FailureMemoryRecord`.
- Enforces Invariant 7: Rejected hypotheses must never be re-tested without explicit differential justification.

### 11. Existing Hypothesis & Strategy Registries
- `strategy_candidates` in `brain_memory.db`: Stores strategy entry/exit rules and validation stages.
- `strategy_lineage` in `experiment_store.db`: Full evolutionary DAG tracking ancestor-child mutations.
- `core/research_firewall.py`: In-memory and persistent `ExperimentRecord` registry with partition locking.

### 12. SQLite Migrations and Persistence Conventions
- Multi-database domain partitioning:
  - `data/market_data.db`: Candles, ticks.
  - `data/brain_memory.db`: Knowledge graph, concepts, strategy candidates.
  - `data/trading_logs.db`: Provenance, shadow trades, global intelligence records.
  - `data/experiment_store.db`: Backtest experiments, lineage graphs.
- Idempotent schema creation (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) and WAL mode configuration.

### 13. API Authentication & Route Patterns
- FastAPI `APIRouter` protected by `Depends(require_api_key)`.
- Rejects unauthenticated requests with HTTP 401/403.
- All intelligence routes mounted under `/api/v1/intelligence/`.

### 14. Frontend State-Management Conventions
- React component architecture using persistent viewport state (Zero-Shake UI).
- Real-time polling via `setInterval` with clean unmount timers.
- Typed client functions in `frontend/src/services/api.ts`.

### 15. Existing Execution Isolation
- Permanent assertion across all files: `REAL_CAPITAL_ENABLED = False`.
- Non-executable watermarks: `THEORETICAL_PREVIEW_EXECUTION_PROHIBITED` and `UNTRUSTED_EXTERNAL_DATA_EXECUTION_PROHIBITED`.
- Smart Order Router circuit breakers prevent order placement when live execution is unauthenticated or kill switch is active.

### 16. Existing Test and Certification Suites
- Milestone 27 test suite: 14/14 passed.
- Milestone 18 certification script (`scripts/verify_m18_certification.py`): 149/149 passed.
- Execution regression suite (`tests/execution/`): 187/187 passed.
- Jest test suite (`npm test`): 147/147 passed (23 suites).

### 17. Model / Version Provenance Infrastructure
- `core/autonomous_research/storage/storage_manifest.py` & `content_hasher.py`: Computes deterministic SHA-256 digests over datasets and models.

### 18. Research Experiment Ledger
- `core/autonomous_research/storage/research_storage.py`: `MultipleTestingRecord` tracks total trials, variants tested, selection method (`PRE_REGISTERED` vs `DATA_MINED`), Deflated Sharpe Ratio, and p-values.
- `core/statistical_defense.py`: `StatisticalPolicy` defines thresholds for Tier 1 qualification (`dsr_tier1_threshold = 0.95`, `wrc_significance_alpha = 0.05`).

---

## 3. Audit Verdict

**VERDICT: APPROVED FOR IMPLEMENTATION**  
The existing CBT infrastructure provides high-quality receptors for CVD, OBI, SMC, and Failure Memory. Milestone 28 does NOT require reinventing microstructure calculations or statistical defense; it requires a **strictly governed Causal Research Compiler** bridging these existing subsystems under Point-in-Time availability contracts.
