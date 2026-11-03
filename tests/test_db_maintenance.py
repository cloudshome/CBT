"""
Unit tests for the SQLite Database Maintenance & Vacuum Tool.
"""

import sqlite3

import pytest

from deploy.db_maintenance import optimize_database, run_maintenance


@pytest.fixture
def temp_db_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create dummy database with records, then delete some to create fragmented pages for vacuum
    db_path = data_dir / "market.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE ohlcv (timestamp INT, open REAL, high REAL, low REAL, close REAL, volume REAL);"
    )
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


def test_optimize_database_handles_corrupt_db_without_unbound_local_error(tmp_path):
    """Corrupt database file fails gracefully without UnboundLocalError."""
    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_bytes(b"NOT_A_VALID_SQLITE_DATABASE_HEADER_CORRUPT_BYTES_XYZ")

    res = optimize_database(corrupt_db)
    assert res["status"] == "FAILED"
    assert "error" in res
    assert res["size_before_kb"] > 0
    assert "size_after_kb" in res
    assert res["reclaimed_kb"] == 0.0


def test_prune_old_uploads_respects_ttl(tmp_path):
    """Old upload files exceeding TTL are pruned; recent files are preserved."""
    import os
    import time

    from deploy.db_maintenance import prune_old_uploads

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    old_file = uploads_dir / "old_doc.pdf"
    old_file.write_text("historical research document content")
    # Set mtime to 20 days ago
    past_time = time.time() - (20 * 86400)
    os.utime(str(old_file), (past_time, past_time))

    recent_file = uploads_dir / "recent_doc.pdf"
    recent_file.write_text("fresh research document content")
    # Set mtime to 1 day ago
    recent_time = time.time() - (1 * 86400)
    os.utime(str(recent_file), (recent_time, recent_time))

    stats = prune_old_uploads(uploads_dir, max_age_days=14, require_provenance=False)
    assert stats["pruned_count"] == 1
    assert stats["reclaimed_kb"] > 0
    assert not old_file.exists()
    assert recent_file.exists()

