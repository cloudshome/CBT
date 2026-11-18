# SPEC — R5: Automated Database Backup Verification & Disaster Recovery Drill
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C (Small Engineering Feature / Reliability)  
**Status:** DRAFT  

---

## 1. Context & Business Value
While `deploy/backup_databases.py` creates `.tar.gz` snapshots using the SQLite Online Backup API, backups that have not been tested for restoration are unverified assumptions. In institutional trading environments, disaster recovery procedures must be automated, deterministic, and proven via regular automated drills.

## 2. Requirements & Acceptance Criteria
1. **Archive Verification:**
   - Verify archive format (`.tar.gz`) and compute cryptographic SHA-256 digest.
   - Inspect tar contents safely without path traversal vulnerabilities (guard against `../` or absolute path escapes).
2. **Deep Database Integrity Audit:**
   - For every restored SQLite database file:
     - Execute `PRAGMA integrity_check` (must equal `ok`).
     - Execute `PRAGMA foreign_key_check` (must return zero violations).
     - Audit table inventory and verify row counts.
     - Extract schema version (`PRAGMA user_version`).
3. **Safe Staging & Atomic Restoration:**
   - Restoration must unpack into an isolated sandbox staging directory first.
   - Deep integrity check must pass on all databases in staging *before* any production data is touched.
   - If target directory already exists, create an rollback snapshot of target before swapping.
4. **SLO Targets for Disaster Recovery:**
   - **RTO (Recovery Time Objective):** Unpack + Integrity Check + Restoration must complete in $\le$ 30.0 seconds for standard datasets.
   - **RPO (Recovery Point Objective):** Captured backup timestamp vs snapshot point must demonstrate $\le$ 1.0 second data loss window for consistent WAL snapshots.
5. **Adversarial Resilience:**
   - Corrupted archives (truncated gzip, bad checksum, corrupted SQLite headers) must fail closed with explicit, actionable error types (`BackupCorruptionError`, `IntegrityCheckFailedError`).
   - Partial failures in multi-database archives must reject the entire restoration batch and leave target state unchanged.
6. **Milestone 18 Certification Invariant:**
   - Zero modifications to the 14 M18 certified files. All recovery logic resides in dedicated `core/database_recovery.py` and test harnesses.
