"""
tests/test_heavy_data_sync.py
=============================
Unit tests for HeavyDataSyncManager and Google Drive synchronization abstraction.
Enforces:
1. Sandboxed directory scanning and manifest updates.
2. File hash verification and incremental skipping.
3. Bidirectional rehydration (download) validation without real external network calls.
"""

import json
from pathlib import Path
import tempfile
import pytest

from core.storage.heavy_data_sync import HeavyDataSyncManager
from core.autonomous_research.storage.drive_backend import SimulatedDriveBackend


@pytest.fixture
def temp_sync_env(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    uploads_dir = repo_dir / "data" / "uploads"
    uploads_dir.mkdir(parents=True)
    manifest_path = repo_dir / "data" / "research" / "vault" / "gdrive_sync_manifest.json"
    sim_backend_dir = tmp_path / "sim_drive"
    sim_backend_dir.mkdir()

    backend = SimulatedDriveBackend(root_dir=sim_backend_dir)
    manager = HeavyDataSyncManager(
        repo_root=repo_dir,
        manifest_path=manifest_path,
        drive_backend=backend,
    )
    return repo_dir, uploads_dir, manifest_path, manager, backend


def test_heavy_sync_upload_and_skip(temp_sync_env):
    repo_dir, uploads_dir, manifest_path, manager, backend = temp_sync_env

    # Create dummy heavy PDF
    dummy_pdf = uploads_dir / "test_research_paper.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 " + b"0" * (1024 * 100))

    # 1. First sync - should upload
    report1 = manager.sync_all_heavy_data()
    assert report1.scanned_count == 1
    assert report1.synced_count == 1
    assert report1.skipped_count == 0
    assert report1.error_count == 0
    assert manifest_path.exists()

    # 2. Second sync - should skip identical
    report2 = manager.sync_all_heavy_data()
    assert report2.scanned_count == 1
    assert report2.synced_count == 0
    assert report2.skipped_count == 1

    # 3. Status check
    status = manager.get_status()
    assert status["total_synced_files"] == 1


def test_heavy_sync_download_rehydration(temp_sync_env):
    repo_dir, uploads_dir, manifest_path, manager, backend = temp_sync_env

    # Create dummy heavy file and upload
    dummy_file = uploads_dir / "dataset.parquet"
    dummy_file.write_bytes(b"PARQUET_MAGIC_HEADER_TEST_BYTES")
    manager.sync_all_heavy_data()

    # Delete local copy to simulate a new machine (e.g. fresh clone on Ubuntu)
    dummy_file.unlink()
    assert not dummy_file.exists()

    # Rehydrate from simulated Drive
    download_report = manager.download_missing_heavy_files()
    assert download_report.synced_count == 1
    assert dummy_file.exists()
    assert dummy_file.read_bytes() == b"PARQUET_MAGIC_HEADER_TEST_BYTES"

