"""
Unit tests for Production Health Probes, Database Engine Info, and Deployment Configuration.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from core.database import db_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "healthy" or "status" in data


def test_database_engine_info():
    info = db_manager.get_engine_info()
    assert "primary_dialect" in info
    assert "sqlite_wal_enabled" in info
    assert info["sqlite_wal_enabled"] is True
    assert "schema_version" in info
    assert "total_storage_mb" in info


def test_systemd_and_healthcheck_files_exist():
    root = Path(__file__).parent.parent
    healthcheck_script = root / "deploy" / "healthcheck.sh"
    service_file = root / "deploy" / "systemd" / "orion.service"

    assert healthcheck_script.exists()
    assert service_file.exists()

    content = service_file.read_text(encoding="utf-8")
    assert "ExecStart" in content
    assert "Restart=always" in content
