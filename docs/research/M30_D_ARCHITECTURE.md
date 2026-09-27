# Milestone 30-D: Architecture Specification

## Autonomous Research Replay Runner & Statistical Audit Loop

**Status:** IMPLEMENTED & CERTIFIED  
**Governance Tier:** Level 0 (AGENTS.md) / Level 1 (.specify/memory/constitution.md) / Level 2 (docs/QUANT_RESEARCH_PROTOCOL.md)  
**Execution Authority:** `NON_EXECUTABLE_RESEARCH_HYPOTHESIS`  
**Capital Authority:** `REAL_CAPITAL_ENABLED = False`  
**Certified Surface Integrity:** 100% Frozen (`core/execution/*` untouched)  

---

## 1. System Overview

Milestone 30-D closes the autonomous empirical research loop between preregistered experiment plans (from Milestone 30-C) and the causal replay & statistical audit engines (from Milestone 29). It provides a deterministic, multi-tier historical replay orchestrator, an institutional multiple-testing auditor, an automated autopsy & quarantine bridge, and a cryptographically sealed Markdown Research Dossier generator.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         M30-C Research Subsystems                           │
│  Evidence Lineage Ledger ──► Hypothesis Ledger ──► Experiment Plan Ledger  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Preregistered DurableExperimentPlan
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 AutonomousReplayRunner (core/intelligence/crawler)          │
│  - ReplayJobLedger (SQLite WAL: crawler_replay_jobs, crawler_replay_reports)│
│  - Idempotent Dispatch: rejects tampered hash or duplicate execution        │
│  - Point-in-Time Resolution: strict availability & lead-time checks         │
│  - Multi-Tier Simulation: BASE, CONSERVATIVE, STRESS friction models        │
└──────────────────┬───────────────────────────────────────┬──────────────────┘
                   │ ReplayExecutionReport (x3)            │
                   ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│     StatisticalAuditor Engine        │  │     ReplayAutopsyBridge           │
│  - Deflated Sharpe Ratio (DSR)       │  │  - FailureAutopsyCompiler         │
│  - Holm-Bonferroni Step-Down         │  │  - FailureMemoryEngine            │
│  - Cost Erosion & Stress Collapse    │  │  - Graduated Immune Quarantine    │
│  - AuditReport & MultipleTestingLogs │  │    (5-Stage Mechanism Penalty)    │
└──────────────────┬───────────────────┘  └─────────────────┬─────────────────┘
                   │                                        │
                   └───────────────────┬────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 ResearchDossierGenerator (Cryptographically Sealed)          │
│  - Path: data/research_dossiers/{plan_id}.md                                │
│  - SHA-256 Content Digest & Pre-registered Lineage Provenance               │
│  - Mandatory Human Review Gate: AWAITING_HUMAN_OPERATOR_REVIEW             │
│  - Zero Live Execution Authority Guarantee                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Components & Responsibilities

### 2.1 Autonomous Replay Dispatcher (`autonomous_replay_runner.py`)
- **`ReplayJob` & `ReplayJobStatus`:** Models lifecycle states: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.
- **`ReplayJobLedger`:** Persistent SQLite storage with tables `crawler_replay_jobs` and `crawler_replay_reports`, indexed for fast status lookup and restart recovery.
- **`AutonomousReplayRunner`:**
  - `dispatch_plan(plan)`: Verifies plan hash against source hypothesis, prevents duplicate runs, generates `DatasetManifest` with causal availability bounds, and dispatches simulations across `BASE`, `CONSERVATIVE`, and `STRESS` tiers.
  - `_extract_pit_events()`: Maps hypothesis and evidence records to point-in-time timestamped events within candle coverage.
  - `get_restart_queue()`: Rehydrates uncompleted jobs upon system restart.

### 2.2 Statistical Audit Engine (`statistical_auditor.py`)
- **`DSRResult` & `AuditReport`:** Immutable audit payloads recording statistical metrics and falsification verdicts.
- **`StatisticalAuditor`:**
  - `audit_replay(plan, reports)`: Runs Bailey & López de Prado Deflated Sharpe Ratio with skewness, kurtosis, and Euler's constant adjustment.
  - Computes Holm-Bonferroni adjusted $p$-values across historical trials.
  - Evaluates cost erosion ($(\mu_{\text{base}} - \mu_{\text{cons}}) / \mu_{\text{base}}$) and detects stress collapse.
  - Returns `AuditReport` with definitive research verdict (`PASSED`, `FALSIFIED`, `COST_INVALIDATED`, `INCONCLUSIVE`, `STRESS_COLLAPSED`).

### 2.3 Failure Autopsy & Graduated Quarantine Bridge (`replay_autopsy_bridge.py`)
- **`QuarantineLevel`:** 5-stage institutional immune response:
  1. `NONE`: Initial discovery phase.
  2. `ADVISORY_WARNING`: 1 recorded falsification.
  3. `PRIORITY_REDUCTION`: 2 recorded falsifications (deprioritized scheduling).
  4. `TEMPORARY_QUARANTINE`: 3 recorded falsifications (30-day suspension).
  5. `PERMANENT_REJECTION`: 5+ recorded falsifications (permanent mechanism retirement).
- **`ReplayAutopsyBridge`:** Automatically compiles structured causal failure autopsies into `failure_memory` table and applies mechanism-level quarantine without blacklisting unrelated mechanisms in the same family.

### 2.4 Research Dossier Generator (`dossier_generator.py`)
- **`ResearchDossierGenerator`:** Formats complete research provenance into an immutable Markdown dossier stored at `data/research_dossiers/{plan_id}.md`.
- Cryptographically seals the document with SHA-256 digest.
- Affixes permanent warnings: `AWAITING_HUMAN_OPERATOR_REVIEW`, zero automated capital routing, non-executable research classification.

---

## 3. Data Flow & Security Boundaries

1. **Constitutional Guard:** AST import scanners verify zero imports of live order routers, execution gateways, or API key modules in `core/intelligence/crawler/*`.
2. **Causal Firewall:** `PointInTimeEventContract.from_intelligence_record` enforces `effective_utc = max(pub_utc, col_utc) + buffer_sec`. Any backtest attempt with $T_{\text{entry}} \le T_{\text{available}}$ immediately raises `CausalLeakageDetectedError`.
3. **Database Isolation:** All tests run strictly against `:memory:` or temporary sandbox paths (`test_tmp_*.db`). Production SQLite ledgers (`data/trading_logs.db`) are never touched.
