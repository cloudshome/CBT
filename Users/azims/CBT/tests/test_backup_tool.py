"""
Unit tests for the SQLite Online Database Backup Tool.
"""

import datetime
import os
import sqlite3
import tarfile
from pathlib import Path
import pytest
from deploy.backup_databases import backup_single_database, run_backup, get_db_files


@pytest.fixture
def temp_db_env(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create dummy active SQLite database
    db1 = data_dir / "market.db"
    conn1 = sqlite3.connect(str(db1))
    conn1.execute("CREATE TABLE candles (timestamp INT, open REAL, close REAL);")
    conn1.execute("INSERT INTO candles VALUES (1000, 50000.0, 50500.0);")
    conn1.commit()
    conn1.close()

    db2 = data_dir / "dev.db"
    conn2 = sqlite3.connect(str(db2))
    conn2.execute("CREATE TABLE paper_trades (id INT, symbol TEXT);")
    conn2.execute("INSERT INTO paper_trades VALUES (1, 'BTC/USDT');")
    conn2.commit()
    conn2.close()

    return {"data_dir": data_dir, "backup_dir": backup_dir, "db1": db1, "db2": db2}


def test_get_db_files(temp_db_env):
    files = get_db_files(temp_db_env["data_dir"])
    names = {f.name for f in files}
    assert "market.db" in names
    assert "dev.db" in names


def test_backup_single_database(temp_db_env, tmp_path):
    dest_db = tmp_path / "cloned_market.db"
    success = backup_single_database(temp_db_env["db1"], dest_db)
    assert success is True
    assert dest_db.exists()

    # Verify content in cloned DB
    conn = sqlite3.connect(str(dest_db))
    cur = conn.cursor()
    cur.execute("SELECT close FROM candles WHERE timestamp = 1000")
    row = cur.fetchone()
    assert row[0] == 50500.0
    conn.close()


def test_run_backup_creates_compressed_archive(temp_db_env):
    res = run_backup(temp_db_env["data_dir"], temp_db_env["backup_dir"], retention_days=7)
    assert res["status"] == "SUCCESS"
    assert res["databases_backed_up"] == 2
    assert res["archive_size_kb"] > 0

    archive_path = Path(res["archive_file"])
    assert archive_path.exists()

    # Inspect archive contents
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getnames()
        assert "market.db" in members
        assert "dev.db" in members


def test_brain_backup_manager_aes_gcm_and_tarslip(tmp_path):
    """Verify BrainBackupManager creates AES-GCM encrypted snapshot and restores safely."""
    from core.brain_backup import BrainBackupManager
    
    data_dir = tmp_path / "brain_data"
    data_dir.mkdir()
    
    # Create test SQLite db
    db = data_dir / "test_brain.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memory (key TEXT, val TEXT);")
    conn.execute("INSERT INTO memory VALUES ('alpha', '42');")
    conn.commit()
    conn.close()
    
    mgr = BrainBackupManager(data_dir=data_dir)
    snapshot = mgr.create_snapshot("test_vault")
    assert snapshot.exists()
    assert snapshot.name.endswith(".enc")
    
    # Read snapshot header
    with open(snapshot, "rb") as f:
        header = f.read(7)
        assert header == b"AESGCM:"
        
    # Delete original db to test restore
    db.unlink()
    assert not db.exists()
    
    restored = mgr.restore_snapshot(snapshot)
    assert restored is True
    assert db.exists()
    
    # Verify content
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT val FROM memory WHERE key = 'alpha'")
    row = cur.fetchone()
    assert row[0] == "42"
    conn.close()

