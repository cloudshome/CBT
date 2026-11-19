# SPECIFICATION — R3: Deterministic SQLite Database Migrations
**Change Class:** Class C (Small Engineering Feature / Database Architecture)  
**Governance Authority:** Level 0 (`AGENTS.md`) & Level 1 (`constitution.md`)  
**Target Subsystem:** `core/database_migrations.py`, `scripts/migrate_databases.py`, `tests/test_database_migrations.py`  

---

## 1. OBJECTIVE & ARCHITECTURAL MOTIVATION

Establish an institutional, deterministic, lightweight migration framework tailored specifically for SQLite in WAL mode.
Rather than introducing heavy external dependencies like Alembic (which is designed for PostgreSQL/MySQL ORMs and adds significant overhead and locking complexity with SQLite WAL), we implement a purpose-built, transactional, checksum-verified migration engine: `DatabaseMigrationEngine`.

---

## 2. FUNCTIONAL REQUIREMENTS

### 2.1 Central Migration Ledger (`_schema_migrations`)
Every migrated SQLite database must maintain an internal append-only migration tracking ledger:
```sql
CREATE TABLE IF NOT EXISTS _schema_migrations (
    migration_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL,
    description TEXT NOT NULL,
    sha256_checksum TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_duration_ms REAL NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_migration_seq ON _schema_migrations(sequence);
```

### 2.2 Sequential Migration Definitions
- Each migration is an immutable object or script with:
  - `migration_id`: E.g. `001_initial_core_schema`, `002_add_correlation_and_risk_indices`
  - `sequence`: Strictly monotonic positive integer (`1`, `2`, `3`, ...)
  - `description`: Human-readable summary of structural changes
  - `up_sql`: Declarative SQL statements executed on upgrade
  - `verify_sql`: Optional verification query ensuring post-migration integrity

### 2.3 Checksum Integrity & Tamper Detection
- The engine calculates the SHA-256 digest of each migration definition (`migration_id + sequence + up_sql`).
- On every run, previously applied migrations are verified against their stored checksum in `_schema_migrations`.
- If an applied migration's checksum differs from the registered definition, execution halts immediately with `MigrationTamperingError` (fail-closed).

### 2.4 Transactional Execution & WAL Coordination
- Each migration executes within an atomic SQLite transaction (`BEGIN IMMEDIATE`).
- On success: updates `_schema_migrations`, bumps `PRAGMA user_version`, and commits.
- On error: rolls back the transaction, logs error, and leaves the database at its previous consistent version.
- Coordinates WAL checkpoints (`PRAGMA wal_checkpoint(PASSIVE)`) to ensure write consistency without blocking concurrent readers.

### 2.5 Duplicate & Concurrent Protection
- Idempotent: previously applied migrations are skipped automatically.
- Concurrent lock: Uses `BEGIN IMMEDIATE` transaction locking to guarantee only one migration worker can modify the schema at a time.

---

## 3. INVARIANTS & SAFETY CONSTRAINTS
1. **Zero Modification to Protected M18 Files:** All migration logic is externalized in `core/database_migrations.py`, preserving `core/database.py` without touching M18 certified surfaces.
2. **Database Isolation:** All automated tests execute in temporary sandboxes (`tests/conftest.py` / `tmp_path`), never mutating live SQLite databases in `data/`.
3. **Fail-Closed Semantics:** Any schema corruption, syntax error, or checksum mismatch aborts the migration atomically.
