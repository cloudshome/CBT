"""
Unit tests for the SQLite Database Maintenance & Vacuum Tool.
"""

import sqlite3
import pytest
from pathlib import Path
from deploy.db_maintenance import optimize_database, run_maintenance, get_db_files


@pytest.fixture
def temp_db_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create dummy database with records, then delete some to create fragmented pages for vacuum
    db_path = data_dir / "market.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ohlcv (timestamp INT, open REAL, high REAL, low REAL, close REAL, volume REAL);")
    for i in range(100):
        conn.execute(f"INSERT INTO ohlcv VALUES ({1000 + i}, 100.0, 105.0, 95.0, 102.0, 50.0);")
    conn.commit()

    # Delete 50% of records to create reclaimable space
    conn.execute("DELETE FROM ohlcv WHERE timestamp < 1050;")
    conn.commit()
    conn.close()

    return data_dir


def test_optimize_single_database(temp_db_dir):
    db_path = temp_db_dir / "market.db"
    res = optimize_database(db_path)
    assert res["status"] == "OPTIMIZED"
    assert res["integrity"] == "ok"
    assert res["size_after_kb"] > 0


def test_run_maintenance_all_databases(temp_db_dir):
    res = run_maintenance(temp_db_dir)
    assert res["status"] == "SUCCESS"
    assert res["total_databases"] == 1
    assert len(res["results"]) == 1
