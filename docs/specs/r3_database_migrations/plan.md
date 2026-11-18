# IMPLEMENTATION PLAN — R3: Deterministic SQLite Database Migrations
**Change Class:** Class C  

---

## 1. ARCHITECTURAL APPROACH

1. **`core/database_migrations.py`:**
   - Define data models: `MigrationDefinition`, `MigrationRecord`, `MigrationStatus`
   - Define exceptions: `MigrationError`, `MigrationTamperingError`, `MigrationSequenceError`
   - Implement `DatabaseMigrationEngine`:
     - `_ensure_ledger_table(conn)`
     - `get_applied_migrations(conn)`
     - `verify_applied_checksums(conn, registered_migrations)`
     - `apply_migration(conn, migration)`
     - `migrate_database(db_path_or_conn, migrations)`
     - `checkpoint_wal(conn)`
2. **Standard Initial Migrations for SKY Databases:**
   - Register initial migration set for trading logs and market databases.
3. **`scripts/migrate_databases.py`:**
   - Standalone CLI utility for operator-driven schema migrations and verification audits.
4. **`tests/test_database_migrations.py`:**
   - Comprehensive test suite in temporary sandbox verifying:
     1. Fresh database migration from scratch
     2. Existing database upgrade
     3. Repeated idempotent rerun (no duplicate execution)
     4. Checksum mismatch / tampering detection
     5. Atomic rollback on failed migration statement
     6. WAL checkpoint coordination
     7. Concurrency / lock protection
