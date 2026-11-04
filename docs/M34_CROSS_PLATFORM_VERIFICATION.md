# M34 Cross-Platform Verification & Reconciliation Report
**Document:** `docs/M34_CROSS_PLATFORM_VERIFICATION.md`  
**Classification:** Distributed Systems Architecture & Node Reconciliation  
**Authority:** Chief Quantitative Research Architect & Systems Auditor  
**Date:** 2026-11-04  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary

This report establishes the distributed operational division and data parity between:
1. **Ubuntu 24/7 Server Node:** Primary dedicated worker for continuous market data ingestion, live WebSocket streaming, and single-writer paper-shadow signal evaluation.
2. **Windows Workstation Node:** Independent quantitative auditor, development harness, read-only ledger inspector, and strategy research verification desk.

---

## 2. Git Synchronization & Commit Lineage

### 2.1 Branch and Commit Verification
- **Active Branch:** `main`
- **Current Synchronized HEAD:** `10497857b6d7088142b36ed49ff21d7d5a8ee2eb`
- **Reconciliation of Prior Reported Mismatch:**
  - A prior report noted divergence between `1049785` and `4265549`.
  - Forensic inspection reveals that commit `4265549` (`fix(risk): isolate guardian state file in tests and restore paper trading state to NORMAL`) is the direct parent of `1049785` (`feat(research): multi-year historical edge discovery, kronos fusion validation, and backtest recovery`).
  - Both remotes (`origin/main` and `cloudshome/main`) have been cleanly fast-forwarded to `1049785`. There is zero branch divergence.

---

## 3. Data Parity & Anti-Corruption Protocol

### 3.1 Parquet Storage Isolation
- Parquet candle stores (`data/store/parquet/`) and SQLite databases (`data/trading_logs.db`) are excluded from Git `.gitignore` to prevent repository bloat and locking conflicts.
- **Cryptographic Parity Verification:**
  - Parity between Ubuntu and Windows is verified by comparing SHA-256 digests in [`research/manifests/`](file:///c:/Users/azims/CBT/research/manifests/).
  - Both nodes must match the exact row count (42,078 for 1h, 10,519 for 4h) and dataset SHA-256 digests.

### 3.2 Single-Writer Rule (No Cloud Sync of SQLite)
- **Strict Prohibition:** Active SQLite databases (`.db` files) must NEVER be shared via Dropbox, OneDrive, Google Drive, or bidirectional cloud sync tools. Doing so causes lock contention, partial write corruptions, and corrupted journals.
- **Authoritative Flow:**
  - Ubuntu is the **Single Authoritative Writer** of prospective paper trades.
  - It writes to an append-only JSON Lines ledger: `research/live_paper_practice_manifest.jsonl`.
  - Windows operates strictly as a **Read-Only Auditor**.

---

## 4. Cross-Platform Health & Clock Synchronization

- Both nodes must sync via NTP (Network Time Protocol) to within $\pm 100\text{ ms}$ of standard UTC.
- All ledger timestamps, trade outcomes, and candle finality marks are serialized in ISO 8601 UTC format.
