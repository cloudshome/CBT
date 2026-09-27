# Milestone 30-D Pre-Implementation Forensic Audit Report

**Date:** 2026-09-24  
**Project:** SKY / Crypto Brain Terminal (CBT)  
**Classification:** Class D (Major Architecture Change) / Class E (Quantitative Research Infrastructure)  
**Governance:** SKY Agent Operating Manual (`AGENTS.md`) + System Constitution (`.specify/memory/constitution.md`)  
**Mission:** Close the M30-C → M29 Empirical Research Loop  
**Execution Authority:** ZERO  
**Capital Authority:** ZERO  
**Baseline Verified Commit:** `1109193`  

---

## 1. Executive Summary & Verification of Baseline

Prior to authoring any production code for **Milestone 30-D** (*Autonomous Research Replay Runner & Statistical Audit Loop*), a complete forensic repository inspection was conducted across the 15 required audit vectors.

### 1.1 Verified Baseline Claims
* **Git Status:** Clean working tree on branch `main` (commit `1109193`, 1 commit ahead of `origin/main`).
* **Milestone 18 Certified Execution Surface:** 100% Intact. Verified via `scripts/verify_m18_certification.py` (Exit Code: 0, Invariants 9, 2, and 10 passed, Cryptographic Test Identity SHA-256 `2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b` confirmed).
* **Existing Intelligence Test Suite:** **92/92 tests passed** in 26.04s (`tests/intelligence/`).
* **Milestone 30-C Qualification Tests:** **33/33 tests passed** in `tests/intelligence/test_milestone30_qualification.py`.
* **Total Pytest Suite:** 1,470 tests green across the repository.

---

## 2. Forensic Architectural Assessment Matrix

| Area | Current Implementation | Reusable Contract | Architectural Gap | Severity | Proposed Resolution |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **Plan Lifecycle** | `core/intelligence/plan_store.py` (`DurableExperimentPlan`, `PlanLifecycleState`) | `PlanLifecycleState`: `QUEUED`, `EXECUTING`, `COMPLETED`, `FALSIFIED`, `CANCELLED` | Plans created in M30-C remain in `QUEUED` state indefinitely; no autonomous runner dequeues them. | **High** | Implement `AutonomousReplayRunner` that retrieves `QUEUED` plans via `ExperimentPlanLedger.get_pending_queue()` and coordinates execution and audit. |
| **Replay Engine** | `core/intelligence/replay_engine.py` (`CausalReplayEngine`, `ReplayExecutionReport`, `ReplayEpisode`) | `CausalReplayEngine.execute_replay(...)` with `RealisticFrictionEngine` | Replay evaluates one friction tier per run; does not automatically run all 3 tiers (`BASE`, `CONSERVATIVE`, `STRESS`) in batch. | **Medium** | Replay runner orchestrates 3 deterministic passes across `FrictionTier.BASE`, `CONSERVATIVE`, and `STRESS`, computing differential cost erosion. |
| **PIT Alignment** | `core/intelligence/point_in_time.py`, `dataset_manifest.py` | `PointInTimeEventContract`, `DatasetManifest.assert_causal_soundness(...)` | Event timestamps must align with historical candle feeds without lookahead leakage. | **Critical** | Replay runner strictly validates $T_{\text{entry}} > T_{\text{available}} + \tau_{\text{lead}}$ using existing `PointInTimeEventContract`. |
| **Statistical Audit** | `core/intelligence/statistical_validator.py` (`StatisticalValidator`), `qualification_contracts.py` (`MultipleTestingLedger`) | Bailey & López de Prado DSR, WRC bootstrap p-value, 8-attribute scorecard | `MultipleTestingLedger` only records batch-level counts; lacks per-trial parameter vector tracking for Holm-Bonferroni ordering. | **High** | Augment `MultipleTestingLedger` with granular trial tracking; implement `StatisticalAuditor` enforcing exact step-down correction. |
| **Failure Memory** | `core/intelligence/failure_autopsy.py` (`CausalFailureAutopsy`), `core/autonomous_research/failure_memory.py` | `FailureAutopsyCompiler.compile_autopsy(...)`, `FailureMemoryEngine` | Falsified replay results are not automatically converted into autopsies and fed back into failure memory. | **High** | Implement `ReplayAutopsyBridge` to automatically index failed replays into `FailureMemoryEngine` with graduated quarantine policies. |
| **Research Dossiers** | Unstructured reports in `docs/` | `CausalValidationResult`, `PreregisteredResearchContract` | No standardized, sealed Markdown artifact generator for hypotheses surviving research audit. | **Medium** | Implement `ResearchDossierGenerator` writing immutable dossiers to `data/research_dossiers/{plan_id}.md` with cryptographic SHA-256 seal. |
| **UI Telemetry & API** | `core/intelligence/routes.py`, `frontend/src/components/IntelligenceCockpit.tsx` | FastAPI `/api/v1/intelligence/*`, React Tab 4 (`AUTONOMOUS_SCOUT`) | No REST endpoints or UI panels for observing replay execution queue, DSR distributions, or autopsy streams. | **Medium** | Mount `/crawler/replay/*` endpoints and add Replay Queue, Statistical Scorecard, and Autopsy cards to Tab 4 of the cockpit. |

---

## 3. Surface Area Integrity & Frozen Boundaries

### 3.1 Frozen Milestone 18 Surface Area
The following 14 files must remain strictly **UNTOUCHED** during Milestone 30-D:
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

### 3.2 Forbidden Dependency Direction (Architectural Firewall)
* `core/intelligence/crawler/*` $\not\to$ `core/execution/*`
* `core/intelligence/crawler/*` $\not\to$ `core/risk/*` (No live risk changes)
* `REAL_CAPITAL_ENABLED = False` permanently across all research modules.
* `execution_authority = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"` permanently across all plan outputs.

---

## 4. Key Architectural Nuances & Resolutions

1. **State Machine Compatibility (`PlanLifecycleState`):**
   * Existing states in `core/intelligence/plan_store.py`: `QUEUED`, `EXECUTING`, `COMPLETED`, `FALSIFIED`, `CANCELLED`.
   * Resolution: We preserve these exact 5 enum values in `PlanLifecycleState`. A plan progresses from `QUEUED` $\to$ `EXECUTING` $\to$ `COMPLETED` (if replay succeeds) or `FALSIFIED` (if the statistical scorecard or friction test rejects $H_0$). The granular epistemic verdict is captured in `CausalValidationResult.status` (`ResearchValidationStatus.OOS_VALIDATED`, `COST_INVALIDATED`, `REGIME_DEPENDENT`, etc.).
2. **Deflated Sharpe Ratio (DSR) & Multiple-Testing Formulation:**
   * Existing implementation in `StatisticalValidator._calculate_dsr`:
     $$\text{DSR} = \Phi\left(\frac{\widehat{\text{SR}} - E[\max(\text{SR})]}{\sqrt{\text{Var}(\widehat{\text{SR}})}}\right)$$
     where $E[\max(\text{SR})]$ utilizes Euler's constant $\gamma \approx 0.5772$ and asymptotic extreme value theory:
     $$E[\max(\text{SR})] \approx (1-\gamma) \Phi^{-1}\left(1 - \frac{1}{N}\right) + \gamma \Phi^{-1}\left(1 - \frac{1}{Ne}\right)$$
   * Resolution: The DSR formula in `core/intelligence/statistical_validator.py` is mathematically rigorous and directly reusable. We will expose parameter $N$ driven dynamically by `MultipleTestingLedger.get_family_trials_count(family_id)`.
3. **Graduated Quarantine vs Blind Family Suppression:**
   * A single failed hypothesis must not automatically blacklist an entire `ResearchFamilyId`.
   * Resolution: The `ReplayAutopsyBridge` will index the specific parameter/mechanism signature into `FailureMemoryEngine`. A template is only quarantined if $\ge 3$ consecutive falsifications occur under conservative frictions.
4. **Performance & SQLite Write Contention:**
   * Replay runs can produce large numbers of simulated trades.
   * Resolution: Replay results are serialized with atomic SQLite transactions under WAL mode (`PRAGMA synchronous=NORMAL;`).

---

## 5. Pre-Implementation Audit Verdict

* [x] Baseline test suites verified green (92/92 intelligence, 33/33 qualification).
* [x] Certified M18 surface verified active and untampered.
* [x] Contracts for M29 Replay Engine and M30-C Qualification Pipeline inspected and verified compatible.
* [x] Gaps identified with precise, non-breaking resolutions.
* [x] **VERDICT: PROCEED TO PHASE 1 (CONTRACT HARDENING & REPLAY RUNNER IMPLEMENTATION).**
