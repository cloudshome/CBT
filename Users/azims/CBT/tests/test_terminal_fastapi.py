"""
tests/test_terminal_fastapi.py
==============================
Pytest verification for the authoritative Python FastAPI Institutional Master Terminal endpoints.
Tests:
- GET  /api/terminal/telemetry
- POST /api/terminal/approval-action
- GET  /api/terminal/glossary
- GET  /api/terminal/provenance
- GET  /api/terminal/replay
- POST /api/desk/ai-brief
- GET  / (Vite HTML root distribution)
- GET  /assets/index-DJYJDuLM.js (Vite asset static distribution)
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_get_terminal_telemetry(client):
    res = client.get("/api/terminal/telemetry?symbol=BTCUSDT&timeframe=15m")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert "currentPrice" in data
    assert "system" in data
    assert data["system"]["service"] == "CTB-INSTITUTIONAL-COCKPIT"
    assert "market" in data
    assert len(data["market"]["mtfMatrix"]) == 9
    assert "orderFlow" in data
    assert "derivativesVitals" in data["orderFlow"]
    assert "confluence" in data
    assert len(data["styleSignals"]) == 5
    assert "executionAndRisk" in data
    assert "macroAndContext" in data
    assert "learningAndCoach" in data
    assert "provenance" in data


def test_post_terminal_approval_action(client):
    res = client.post(
        "/api/terminal/approval-action",
        json={"signalId": "SIG-BTC-SWING-01", "action": "APPROVE", "notes": "Approved in test"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["newState"] == "APPROVED"


def test_get_terminal_glossary(client):
    res = client.get("/api/terminal/glossary?q=BOS")
    assert res.status_code == 200
    data = res.json()
    assert data["totalCount"] >= 1
    assert any("BOS" in item["term"] for item in data["items"])


def test_get_terminal_provenance(client):
    res = client.get("/api/terminal/provenance?thesisId=TEST-1")
    assert res.status_code == 200
    data = res.json()
    assert data["thesisId"] == "TEST-1"
    assert len(data["nodes"]) >= 7


def test_get_terminal_replay(client):
    res = client.get("/api/terminal/replay?offset=T-30m&symbol=BTCUSDT")
    assert res.status_code == 200
    data = res.json()
    assert data["offset"] == "T-30m"
    assert "replayPrice" in data
    assert "replayScore" in data


def test_post_desk_ai_brief(client):
    res = client.post("/api/desk/ai-brief", json={"symbol": "BTCUSDT", "timeframe": "15m"})
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["bias"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert len(data["executiveSummary"]) > 20
    assert "keyLevels" in data
    assert "metrics" in data


def test_root_view_serves_vite_distribution(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "<html" in res.text.lower()


def test_vite_assets_served_statically(client):
    dist_assets = list(Path("frontend/dist/assets").glob("index-*.js"))
    assert len(dist_assets) > 0, "No built index js asset found in frontend/dist/assets"
    asset_name = dist_assets[0].name
    res = client.get(f"/assets/{asset_name}")
    assert res.status_code == 200
    assert len(res.content) > 10000
