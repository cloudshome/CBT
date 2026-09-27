"""
Unit tests for FastAPI Prometheus Metrics Endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_prometheus_metrics_endpoint(client):
    """GET /metrics returns 200 with standard Prometheus text output."""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert "sky_shadow_open_positions" in res.text
    assert "sky_provenance_records_total" in res.text
    assert "sky_audit_events_total" in res.text
    assert "sky_db_storage_mb" in res.text
    assert "sky_uptime_seconds" in res.text


def test_api_metrics_alias_endpoint(client):
    """GET /api/metrics alias also returns 200 with metrics."""
    res = client.get("/api/metrics")
    assert res.status_code == 200
    assert "sky_uptime_seconds" in res.text
