# PLAN — R5: Automated Database Backup Verification & Disaster Recovery Drill
**Authority:** Senior Quantitative Systems Architect  
**Role:** Lead Quantitative Systems Engineer  
**Change Class:** Class C  

---

## 1. Architecture & Design
We introduce `core/database_recovery.py`:
- `DisasterRecoveryEngine`:
  - `inspect_archive(archive_path: Path) -> ArchiveMetadata`: Inspects tar entries, checks for path traversal, computes SHA-256.
  - `verify_database_integrity(db_path: Path) -> DatabaseIntegrityReport`: Runs `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, row counts, and schema version.
  - `restore_from_archive(archive_path: Path, target_dir: Path, staging_dir: Optional[Path] = None, dry_run: bool = False) -> RestorationResult`: Executes staging $\to$ full integrity audit $\to$ atomic placement $\to$ rollback on failure.
  - `run_disaster_recovery_drill(data_dir: Path, backup_archive: Path) -> DrillReport`: Executes an end-to-end simulated disaster recovery drill, measures wall-clock RTO and RPO metrics, and reports pass/fail against institutional thresholds ($\text{RTO} \le 30s$, $\text{RPO} \le 1s$).

## 2. Testing Strategy
- Unit tests:
  - Valid backup creation, inspection, and verification.
  - Foreign key validation passes and catches broken FK references.
  - Corrupt SQLite page detection fails closed.
  - Path traversal attack in tar archive is blocked.
  - Corrupt or truncated tar.gz archive is rejected.
  - Atomic restore rollbacks target if staging verification fails.
  - Measure RTO and RPO in automated drill simulation.
