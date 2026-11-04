# M35 Cross-Platform Data Parity & Node Protocol
**Document:** `docs/M35_CROSS_PLATFORM_DATA_PARITY.md`  
**Classification:** Distributed Data Engineering & Integrity Protocol  
**Authority:** Chief Market-Data Engineer  
**Date:** 2026-11-04  
**Audit File:** [`research/manifests/`](file:///c:/Users/azims/CBT/research/manifests/)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary: Git Parity $\neq$ Data Parity

The operator made an essential observation:
> **"Git sync মানেই Parquet data sync নয়।"**

Because Parquet directories (`data/store/parquet/candles/`) and SQLite database ledgers (`data/trading_logs.db`) are excluded from Git via `.gitignore` to prevent repository bloat, a successful Git commit (`3a47aa9`) guarantees code parity, **but does NOT prove local dataset parity**.

---

## 2. Parquet Data Manifest Verification Protocol

To verify that Ubuntu has byte-for-byte identical historical market data to Windows:
1. **Windows Generated Manifests:** We generated 9 cryptographic manifest files under [`research/manifests/`](file:///c:/Users/azims/CBT/research/manifests/), recording partition-level SHA-256 digests, row counts, and timestamp bounds.
2. **Ubuntu Verification Command:**
   The operator should execute the following verification script on Ubuntu:
   ```bash
   cd ~/CBT
   python3 scripts/research/generate_dataset_manifests.py
   git status research/manifests/
   ```
   - If `git status` reports **nothing to commit, working tree clean**, then Ubuntu's local Parquet files are **100% byte-for-byte identical** to Windows!
   - If any `.json` manifest is modified, the Git diff will pinpoint the exact partition file with missing bars or timestamp discrepancies.

---

## 3. SQLite Database Isolation Protocol

- **Absolute Prohibition:** Active SQLite databases must **NEVER** be synchronized via Dropbox, OneDrive, Google Drive, or shared network folders. Shared concurrent access corrupts SQLite WAL (Write-Ahead Logging) headers and leads to fatal database locks.
- **Single-Writer Flow:**
  - Ubuntu operates as the **Exclusive Event Writer** to [`research/live_paper_practice_manifest.jsonl`](file:///c:/Users/azims/CBT/research/live_paper_practice_manifest.jsonl).
  - Windows accesses this ledger purely via Git pull as a **Read-Only Auditor**.

