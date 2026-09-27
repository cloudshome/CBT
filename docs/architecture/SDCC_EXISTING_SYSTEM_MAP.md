# SDCC Existing System Map

**Status:** Authoritative Architectural Baseline
**Repository:** SKY / CBT (Crypto Brain Terminal)
**Target Phase:** Phase SDCC-1 Discovery
**Branch:** `feature/sdcc-collective-core`

---

## 1. Executive Summary

This document maps all existing subsystems, databases, domain engines, schemas, and API endpoints in the SKY / CBT codebase to define how the **SKY Distributed Collective Core (SDCC)** integrates without duplication or regression.

SDCC adopts the fundamental doctrine:
> **The local database is a projection; the collective event ledger is authoritative.**

---

## 2. Database Architecture & Existing SQLite Storage

The CBT platform currently utilizes 4 domain-partitioned SQLite databases located in `data/` managed by `core/database.py` (`DatabaseManager`):

| Database File | Path | Key Tables & Responsibilities | SDCC Materialized Projection Role |
| :--- | :--- | :--- | :--- |
| `brain_memory.db` | `data/brain_memory.db` | `research_provenance_ledger`, `knowledge_vault`, `strategy_candidates`, `evidence_vault`, `rejected_claims_vault`, `epistemic_sources`, `concept_relationships` | **Class B & D**: Rebuilt deterministically from `RESEARCH_*`, `CLAIM_*`, `EVIDENCE_*`, and `KNOWLEDGE_*` events. |
| `trading_logs.db` | `data/trading_logs.db` | `shadow_positions`, `system_audit_events`, `closed_trades`, `trade_executions` | **Class D**: Rebuilt deterministically from `PAPER_*` events. `system_audit_events` mirrors critical collective decisions. |
| `market_data.db` | `data/market_data.db` | `tickers`, `candles`, `orderbook_l2`, `cvd_ticks`, `microstructure_metrics` | **Local / Ephemeral**: Local exchange ingest & caching. Not synchronized across nodes. |
| `experiment_store.db`| `data/experiment_store.db` | `experiments`, `features`, `autonomous_tasks`, `failure_memories`, `practice_sessions` | **Class D**: Derived from `EXPERIMENT_*` and `RESEARCH_*` events. |

### Database Integrity Rules
1. **Never synchronize whole `.db` files**: SQLite files are written with WAL mode (`PRAGMA journal_mode=WAL`) and contain node-local cache and lock state. Syncing `.db` files causes database lockups and corrupts WAL indexes.
2. **Deterministic Rebuild**: Given the canonical collective event stream, any node can execute `python main.py collective rebuild` to reconstruct `brain_memory.db` and `trading_logs.db`.

---

## 3. Paper Trading Architecture

### Current Implementation
- **Manager**: `core/portfolio_shadow.py` (`PortfolioShadowManager`)
- **Key Methods**:
  - `open_position(symbol, direction, size, entry_price, stop_loss, take_profit) -> str`
  - `close_position(position_id, exit_price) -> bool`
  - `update_live_price(symbol, current_price) -> list[dict]` (triggers breakeven +1.5R and automated trailing stop)
  - `get_open_positions()`, `get_portfolio_accounting()`
- **Autonomous Trader**: `core/autonomous_trader.py` (`AutonomousTrader.scan_and_execute()`)
- **REST Endpoints**:
  - `GET /api/paper/positions`
  - `GET /api/paper/desk-overview`
  - `GET /api/paper/config`
  - `POST /api/paper/trade`
  - `POST /api/paper/close`
- **Frontend**: `frontend/src/components/DedicatedPaperTradingDesk.tsx` and `PaperTradingPanel.tsx`

### SDCC Integration Strategy
1. **Non-Invasive Event Adapter**: `core/collective/adapters/paper_trade_adapter.py` wraps `PortfolioShadowManager`.
2. **Global Trade Identity**: Positions receive node-scoped IDs `PT-<node_id>-<timestamp>-<uuid8>` preventing cross-node ID collisions.
3. **Event Stream**: State mutations generate immutable canonical events:
   - `PAPER_ACCOUNT_CREATED`
   - `PAPER_ORDER_CREATED`
   - `PAPER_ORDER_FILLED`
   - `PAPER_POSITION_OPENED`
   - `PAPER_POSITION_MODIFIED`
   - `PAPER_POSITION_CLOSED`
   - `PAPER_STOP_TRIGGERED`
   - `PAPER_TP_TRIGGERED`
   - `PAPER_RISK_REJECTED`
4. **Multi-Node Simulation Merge**: When `HOME-01` and `OFFICE-01` trade concurrently, both trade sequences are preserved with complete node provenance and aggregated in the collective analytics layer.

---

## 4. Research Lab & Knowledge Ingestion Pipeline

### Current Implementation
- **Ingestion Coordinators**:
  - `core/universal_ingestor.py` (`UniversalIngestor`): Ingests YouTube, PDFs, Github, Articles, Notes.
  - `core/multimodal_ingestor.py`: Audio, visual, and transcript extraction.
  - `core/knowledge_os/`:
    - `epistemic_system.py`: Claims, observations, mental models.
    - `project_brain.py`: Cross-domain synthesis & contextual lookup.
    - `library_ingestor.py`: Batch library ingestion and deduping.
    - `research_automation_orchestrator.py`: Zero-touch research cycles.
- **Provenance Engine**: `core/provenance_engine.py` (`ProvenanceEngine`)
  - 4-Vault Ledger:
    1. Research Provenance Ledger (`research_provenance_ledger`)
    2. Knowledge Vault (`knowledge_vault`)
    3. Strategy Candidates (`strategy_candidates`)
    4. Evidence Vault (`evidence_vault`)
    5. Rejected Claims Vault (`rejected_claims_vault`)
- **Frontend**: `frontend/src/components/ResearchIngestLab.tsx`

### SDCC Integration Strategy
1. **Do NOT Create a Second Research Lab**: `UniversalIngestor` and `ResearchIngestLab.tsx` remain the front door for knowledge ingestion.
2. **Research Event Adapter**: `core/collective/adapters/research_adapter.py` intercepts vault operations and emits:
   - `RESEARCH_SOURCE_REGISTERED`
   - `KNOWLEDGE_OBJECT_CREATED`
   - `CLAIM_CREATED`
   - `EVIDENCE_ATTACHED`
   - `HYPOTHESIS_CREATED`
   - `HYPOTHESIS_REJECTED`
   - `RESEARCH_AUTOPSY_CREATED`
3. **Semantic Conflict Preservation**: If two nodes extract contradictory claims, SDCC records a `KNOWLEDGE_CONTRADICTION` conflict set preserving both claims and datasets rather than overwriting.

---

## 5. Evidence Precedence & Risk Perimeter

### Current Implementation
- **Evidence Integrity**: `core/evidence_integrity.py`
  - `EvidenceGrade` hierarchy:
    - `FABRICATED` (0) — Random/synthetic walk; forbidden for live sizing.
    - `SIMULATED` (1) — Monte Carlo or bootstrap paths.
    - `IMPUTED` (2) — Small sample or gap-filled.
    - `EMPIRICAL` (3) — Verified real market data.
  - `EvidenceLedger`: Weakest-link semantics across pipelines.
  - `require_live_evidence()`: Hard gate throwing `EvidenceViolation`.
- **Risk Gate**: `core/risk_manager.py`, `core/execution/kill_switch.py` (`live_kill_switch`).
- **Strategy League**: `core/strategy_league.py` (`QuarantineTier`: Smoke -> Preliminary -> Robust -> Production).
- **Strategy Compiler**: `core/strategy_compiler.py` (`StrategyGenome`).

### SDCC Boundary Rules
1. **Sync != Trading Authorization**: Receiving an approved strategy or high-confidence claim from another node never automatically grants live trading authority.
2. **Weakest-Link Inheritance**: Synchronized knowledge retains its exact original `EvidenceGrade`. An AI confidence score on an incoming node cannot elevate `E1` to `E7`.
3. **Deterministic Promotion**: Live capital allocation remains strictly governed by the local node's risk gate and `StrategyLeagueManager`.

---

## 6. Cold Storage & Storage Abstractions

### Current Implementation
- **Storage Subsystem**: `core/autonomous_research/storage/`
  - `content_hasher.py`: `ContentHasher` with SHA-256 calculation.
  - `drive_backend.py`: `DriveBackendProtocol`, `SimulatedDriveBackend`, `GoogleDriveAPIBackend`.
  - `deduplication.py`: `DeduplicationManager`.
  - `storage_manifest.py`: `StorageManifest`.
  - `archive_manager.py`: Hot -> Warm -> Cold transitions.

### SDCC Integration Strategy
1. **Reuse `ContentHasher`**: For content-addressable artifact identity (`data/artifacts/objects/ab/cd/<sha256>`).
2. **Reuse `DriveBackendProtocol`**: In `core/collective/gdrive_archive.py` for Tier 3 Google Drive periodic snapshots, recovery manifests, and disaster recovery restore without code duplication.

---

## 7. Audit & Event Streaming

### Current Implementation
- `core/audit_bus.py` (`AuditBus`, `AuditEvent`, `system_audit_events` table).
- Memory ring buffer and SQLite append logging for system events.

### SDCC Integration Strategy
- The collective synchronization engine and conflict engine route notable lifecycle events (e.g. `SYNC_COMPLETED`, `CONFLICT_QUARANTINED`, `PROJECTION_REBUILT`) to `audit_bus` for operational visibility.

---

## 8. API & Frontend Architecture

### Current Implementation
- **API**: FastAPI in `app.py`.
- **Frontend**: React 18, Vite 6, TailwindCSS, Lucide-React icons in `frontend/src/`.
- **Main Views**: `App.tsx` multiplexes between `TERMINAL` and `PAPER_DESK`, with bottom tabs (`DOSSIER`, `HEDGE_FUND`, `QUANT`, `MTF_SMC`, `FRONTIERS`, `RESEARCH_LAB`).

### SDCC Integration Strategy
1. **REST Router**: `core/collective/routes.py` mounted as `/api/collective/*` in `app.py`.
2. **Frontend View**: `frontend/src/components/CollectiveCoreDashboard.tsx` added to `App.tsx` tab navigation.
3. **Non-Intrusive Polling**: Polling uses background intervals with cached state to prevent UI flicker or focus loss.

---

## 9. Required CLI Architecture

- **Entrypoint**: Root `main.py` delegating to `core/collective/cli.py`.
- **Subcommands**:
  - `python main.py collective init`
  - `python main.py collective status`
  - `python main.py collective sync`
  - `python main.py collective verify`
  - `python main.py collective rebuild`
  - `python main.py collective reconcile`
  - `python main.py collective conflicts`
  - `python main.py collective nodes`
  - `python main.py collective export`
  - `python main.py collective import`
