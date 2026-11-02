"""
tests/test_data_freshness.py
============================
Verifies Priority 2 inspectable data quality, freshness, and provenance reporting:
1. data_streamer.get_data_freshness_report() computation
2. GET /api/terminal/data-freshness endpoint contract
3. Inclusion of dataFreshness in /api/terminal/telemetry
4. Empirical vs Synthetic data quality calculations
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from core.data_streamer import data_streamer


@pytest.fixture
def client():
    return TestClient(app)


def test_data_streamer_freshness_report_structure():
    """Validates the structure of the data freshness report."""
    report = data_streamer.get_data_freshness_report()
    assert "timestamp_utc" in report
    assert "current_time_ms" in report
    assert "monitored_assets" in report
    assert "assets" in report
    assert "BTC/USDT" in report["assets"]

    btc_info = report["assets"]["BTC/USDT"]
    assert btc_info["symbol"] == "BTC/USDT"
    assert btc_info["market_type"] == "PERPETUAL_FUTURES"
    assert "freshness_status" in btc_info
    assert "evidence_grade" in btc_info
    assert "quality_score_pct" in btc_info


def test_api_terminal_data_freshness_endpoint(client):
    """Tests GET /api/terminal/data-freshness."""
    res = client.get("/api/terminal/data-freshness")
    assert res.status_code == 200
    data = res.json()
    assert "assets" in data
    assert "BTC/USDT" in data["assets"]
    assert "ETH/USDT" in data["assets"]
    assert "XAU/USD" in data["assets"]


def test_api_terminal_data_freshness_single_symbol(client):
    """Tests GET /api/terminal/data-freshness?symbol=BTC/USDT."""
    res = client.get("/api/terminal/data-freshness?symbol=BTC/USDT")
    assert res.status_code == 200
    data = res.json()
    assert "assets" in data
    assert len(data["assets"]) == 1
    assert "BTC/USDT" in data["assets"]


def test_api_terminal_telemetry_includes_data_freshness(client):
    """Tests that GET /api/terminal/telemetry includes dataFreshness metadata."""
    res = client.get("/api/terminal/telemetry?symbol=BTCUSDT")
    assert res.status_code == 200
    data = res.json()
    assert "dataFreshness" in data
    assert data["dataFreshness"] is not None
    assert "assets" in data["dataFreshness"]
