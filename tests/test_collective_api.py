"""
tests/test_collective_api.py
============================
Integration tests for SDCC FastAPI REST endpoints and status telemetry.
"""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_collective_status(client):
    res = client.get("/api/collective/status")
    assert res.status_code == 200
    data = res.json()
    assert "node_id" in data
    assert "protocol_version" in data
    assert "status" in data
    assert data["status"] == "ONLINE"
    assert "unresolved_conflicts" in data


def test_get_collective_nodes(client):
    res = client.get("/api/collective/nodes")
    assert res.status_code == 200
    data = res.json()
    assert "local_node" in data
    assert "peer_nodes" in data
    assert data["local_node"]["is_self"] is True


def test_get_collective_conflicts(client):
    res = client.get("/api/collective/conflicts")
    assert res.status_code == 200
    data = res.json()
    assert "conflicts" in data
    assert "count" in data


def test_trigger_verify_and_rebuild(client):
    # Verify endpoint
    res_v = client.post("/api/collective/verify")
    assert res_v.status_code == 200
    assert res_v.json()["status"] == "PASS"

    # Rebuild endpoint
    res_r = client.post("/api/collective/rebuild")
    assert res_r.status_code == 200
    data_r = res_r.json()
    assert data_r["status"] == "SUCCESS"
    assert "state_hash" in data_r


def test_trigger_sync(client):
    res = client.post("/api/collective/sync")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "receipts" in data
