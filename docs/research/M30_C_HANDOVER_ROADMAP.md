# Milestone 30-C Handover & Resumption Roadmap

**Project:** SKY / Crypto Brain Terminal (CBT)  
**Date:** 2026-09-23  
**Status at Close of Session:**
- **Milestone 30-A (Dependency & Supply-Chain Stabilization):** 100% Complete (All 8 Dependabot PRs safely resolved & verified, M18 certified surface preserved).
- **Milestone 30-B (Evidence-Grade Multi-Source Ingestion Foundation):** 100% Complete & Certified (14/14 tests passing, 59/59 full intelligence suite green, 7/7 preflight gates green).
- **Repository State:** Branch `main` clean, fully synchronized with `origin/main` (Commit: `64adb9e`).

---

## 1. What Was Completed Today

1. **Dependabot PR Remediation (PRs #64–#71):**
   * Batch 1 (`pypdf`, `cbor2`, `yt-dlp`, `youtube-transcript-api`): Cleanly updated.
   * Batch 2 (`scikit-learn`): Audited TF-IDF & HDBSCAN clustering; 45/45 tests green.
   * Batch 3 (`uvicorn`): ASGI event loop, WebSocket protocol, and HTTP/1.1 verified; 51/51 route tests green.
   * Batch 4 (`ccxt`): Upgraded to `4.5.82`. Full Milestone 18 adversarial suite verified (149/149 passed in 124s).
   * Ruff 0.16.8 Isolation: Preserved Ruff pinned at `0.9.10` in `requirements-dev.txt` to avoid invalidating the certified M18 SHA-256 test identity hash. Closed PR #70 on GitHub with audit rationale.
2. **Milestone 30-B Ingestion Foundation Subsystem (`core/intelligence/crawler/`):**
   * `source_registry.py`: 10 institutional publishers, officiality weighting, and fair access rates.
   * `raw_evidence_vault.py`: Immutable SQLite WAL storage with SHA-256 cryptographic seal & tamper detection.
   * `event_identity.py`: Canonical event naming and deterministic payload hashing.
   * `entity_resolver.py`: Fine-grained disambiguation (BTC vs MSTR, IBIT vs BlackRock, USDT vs Tether).
   * `conflict_ledger.py`: SQLite store tracking revisions, contradictory reports, and resolution workflows.
   * `base_adapter.py` & `adapters/`: Single transparent institutional User-Agent, token-bucket throttling, circuit breakers, and 5 specialized domain adapters (Macro, SEC EDGAR, On-chain, Academic, News wire).
   * `quality_firewall.py`: Multi-Layer Intelligence Quality Firewall (Source Quality, Evidence Integrity, Point-in-Time Causality).
   * `scout_controller.py`: Crawl run lifecycle orchestrator, pause/resume, and diagnostic health metrics.
   * `routes.py`: 9 crawler endpoints under `/api/v1/intelligence/crawler/*`.
3. **Verification Scorecard:**
   * `pytest tests/intelligence/test_milestone30_ingestion.py`: **14/14 PASSED**
   * `pytest tests/intelligence/`: **59/59 PASSED**
   * `scripts/system_preflight.py`: **7/7 GATES PASSED (100% GREEN)**

---

## 2. Next Day Work Plan: Milestone 30-C (Intelligence Qualification & Research Integration)

The objective for the next session is to connect the evidence-grade crawler foundation from M30-B directly into the scientific research pipeline of M28 and M29.

### Task 1: Fact Extraction & Empirical Qualification Pipeline (`core/intelligence/crawler/fact_extractor.py`)
* Extract structured numeric facts from approved `CanonicalEvent` instances:
  * Indicator actual print vs consensus estimate surprise $\Delta$.
  * Corporate bitcoin balance sheet accumulation numbers.
  * Stablecoin net mint/burn notional flows in USD.
* Assign probabilistic confidence weights based on source officiality and syndication confirmation.

### Task 2: Causal Synthesis Automatic Bridge (`core/intelligence/crawler/causal_bridge.py`)
* Automatically translate qualified facts into candidate Milestone 28 `CausalHypothesis` structures:
  * Select relevant `ResearchFamilyId` (e.g. `MACRO_LIQUIDITY_TRANSMISSION`, `MICROSTRUCTURE_ORDER_FLOW`).
  * Instantiate `PointInTimeEventContract` with publication timestamp cutoffs.
  * Evaluate candidate hypothesis across the 9-Gate Causal Firewall.
  * Write approved hypotheses into `HypothesisLedgerManager`.

### Task 3: Walk-Forward Replay Automatic Plan Generator (`core/intelligence/crawler/plan_generator.py`)
* For hypotheses passing the Causal Firewall, generate preregistered research contracts:
  * Create `PreregisteredResearchContract` and `DurableExperimentPlan`.
  * Commit plan into `ExperimentPlanLedger` in `PlanLifecycleState.PENDING` state.
  * Enforce `REAL_CAPITAL_ENABLED = False` and `NON_EXECUTABLE_RESEARCH_HYPOTHESIS`.

### Task 4: Frontend Intelligence Cockpit "Autonomous Scout" Tab (`frontend/src/components/IntelligenceCockpit.tsx`)
* Add dedicated "🌐 Autonomous Scout" tab in the cockpit:
  * Live status indicator (`IDLE`, `CRAWLING`, `PAUSED`).
  * Run controls (Trigger crawl, Pause, Resume).
  * Recent crawl runs telemetry table (Seen, Accepted, Rejected, Quarantined).
  * Evidence Vault inspector: view raw wire payloads and cryptographic SHA-256 seals.
  * Discrepancies & Conflicts panel: inspect multi-source disagreements with resolution buttons.

### Task 5: Milestone 30-C Adversarial Test Suite
* Create `tests/intelligence/test_milestone30_qualification.py`.
* Verify end-to-end flow from raw wire observation $\to$ fact extraction $\to$ M28 hypothesis $\to$ M29 replay plan $\to$ constitutional execution boundary.

---

## 3. Resumption Quickstart Commands (For Tomorrow)

```bash
# 1. Verify working branch and remote synchronization
git status
git log -1 --oneline

# 2. Run quick test check to ensure sandbox is green
.venv\Scripts\pytest tests/intelligence/ -q

# 3. Check system preflight status
.venv\Scripts\python scripts/system_preflight.py

# 4. Begin Milestone 30-C implementation
```
