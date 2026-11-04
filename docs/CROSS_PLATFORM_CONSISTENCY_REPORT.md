# CROSS-PLATFORM RESEARCH CONTINUITY & SYNCHRONIZATION REPORT

**Generated:** 2026-11-04T11:38:00Z  
**Authority:** Chief Quantitative Research Officer & Independent Backtesting Auditor  
**Scope:** Reconciling the 24/7 Ubuntu Research Machine and the Local Windows Development Environment

---

## 1. Executive Summary & Problem Diagnosis

The project owner operates two primary compute environments:
1. **Ubuntu Linux Node (Home Server):** Running 24/7 for approximately 3 months.
2. **Windows 10 Node (`NODE-WIN-CLOUDSLO-A859`):** Interactive development workstation.

### The Disconnect Identified:
- **Git vs Runtime Isolation:** While Git synchronizes source code across both remotes (`github.com/Azimshawon/SKY` and `github.com/cloudshome/CBT`), the `.gitignore` policy correctly excludes local SQLite databases (`data/*.db`), Parquet cache partitions, and local conversation transcripts.
- **Agent Context Amnesia:** When an Antigravity agent session is initiated on Windows, it possesses zero visibility into previous conversational scratchpads or uncommitted files generated on Ubuntu unless explicitly tracked in the canonical research ledger.
- **Duplicate/Divergent Experimentation:** Without a centralized, shared experiment registry, agents on Windows risked duplicating or misinterpreting compute workloads running on Ubuntu.

---

## 2. Environment Comparison Matrix

| Component / Layer | Windows Workstation (`cloudslover`) | Ubuntu Server (24/7 Node) | Canonical Reconciled State |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10 (Build 19045) | Ubuntu Linux 22.04 / 24.04 LTS | Cross-platform Python 3.13 |
| **Git Commit (HEAD)** | `4265549` (`main`) | Tracked via `cloudshome/main` | Strict Git Fast-Forward Sync |
| **Parquet Candle Store** | Complete (42,078 1h, 10,519 4h bars) | Complete / Continuously Ingesting | Verified Cryptographic Parity |
| **Canonical Experiment Ledger** | `research/historical_discovery_results.json` | Local experiment databases | Exportable JSON Manifest |
| **Database Schema Version** | SQLite v3 (M18 + M33.1 hardened) | SQLite v3 | Unified Schema via `tests/conftest.py` |
| **Risk Guardian State** | `NORMAL` ($10,000 baseline) | `NORMAL` | Isolated from unit tests |
| **Worker Allocation** | Interactive Development & Audit | Heavy Research & Continuous Ingestion | Dedicated Worker Roles |

---

## 3. Protocol for Cross-Platform Continuity

1. **Canonical Experiment Provenance (`research/experiment_provenance_manifest.json`):**
   - Every historical experiment must generate an immutable, machine-readable record carrying:
     - `experiment_id`
     - `dataset_fingerprint` (SHA-256)
     - `git_commit_hash`
     - `execution_timestamp_utc`
     - `performance_metrics`
   - This manifest is committed directly to Git, ensuring that both Ubuntu and Windows immediately recognize completed experiments without re-running them.
2. **Dedicated Worker Roles:**
   - **Ubuntu Node (Compute Worker):** Dedicated to high-iteration compute jobs: multi-horizon walk-forward parameter sweeps, neural model training, and continuous live WebSocket ingestion.
   - **Windows Node (Auditor & Interface):** Dedicated to independent code review, risk governance validation, live terminal UI inspection, and strategic decision synthesis.
3. **Prevention of Database Clashes:**
   - Never use direct cloud-folder sync (e.g. OneDrive, Dropbox, Google Drive desktop sync) to synchronize active SQLite `.db` files across operating systems, as concurrent writes cause database corruption. Use Git-tracked JSON/manifest exports and structured SQLite backups.
