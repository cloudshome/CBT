"""
Integration test suite for Phase 14 Frontier API endpoints in app.py.
Verifies microstructure, macro network, genetic optimization, smart execution, and autonomous auditor routes.
"""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_microstructure_analytics(client):
    res = client.get("/api/microstructure/analytics?symbol=BTC/USDT")
    assert res.status_code == 200
    data = res.json()
    assert "mid_price" in data
    assert "depth_tiers" in data
    assert "slope_elasticity" in data
    assert "flow_toxicity" in data


def test_api_microstructure_toxicity(client):
    res = client.get("/api/microstructure/toxicity?symbol=ETH/USDT")
    assert res.status_code == 200
    data = res.json()
    assert "flow_toxicity" in data
    assert "slope_elasticity" in data


def test_api_macro_network_and_spillover(client):
    res_net = client.get("/api/macro/network")
    assert res_net.status_code == 200
    data_net = res_net.json()
    assert "correlation_network" in data_net
    assert "pca_absorption" in data_net

    res_spill = client.get("/api/macro/spillover")
    assert res_spill.status_code == 200
    data_spill = res_spill.json()
    assert "systemic_fragility_index" in data_spill


def test_api_genetic_optimization(client):
    req_body = {
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "bars": 100,
        "generations": 2,
        "population_size": 8,
    }
    res = client.post("/api/strategy/optimize/genetic", json=req_body)
    assert res.status_code == 200
    data = res.json()
    assert "best_genome" in data
    assert "whites_reality_check" in data


def test_api_execution_slice_and_impact(client):
    slice_req = {
        "qty": 5.0,
        "algo_type": "TWAP",
        "duration_sec": 300,
        "num_slices": 5,
        "mid_price": 60000.0,
    }
    res_slice = client.post("/api/execution/slice", json=slice_req)
    assert res_slice.status_code == 200
    data_slice = res_slice.json()
    assert "schedule" in data_slice
    assert len(data_slice["schedule"]) == 5

    impact_req = {
        "order_size": 2.0,
        "order_side": "BUY",
        "symbol": "BTC/USDT",
        "mid_price": 60000.0,
        "urgency": "MEDIUM",
    }
    res_impact = client.post("/api/execution/simulate_impact", json=impact_req)
    assert res_impact.status_code == 200
    data_impact = res_impact.json()
    assert "recommended_route" in data_impact


def test_api_auditor_telemetry_and_record_trade(client):
    # Record paper trade
    trade_req = {
        "trade_id": "test_api_t1",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 60000.0,
        "exit_price": 61000.0,
        "qty": 0.5,
        "entry_time_ms": 1000,
        "exit_time_ms": 60000,
        "market_regime": "TRENDING_BULL",
        "risk_per_trade_usd": 200.0,
    }
    res_record = client.post("/api/auditor/record_trade", json=trade_req)
    assert res_record.status_code == 200

    # Fetch telemetry
    res_telem = client.get("/api/auditor/telemetry")
    assert res_telem.status_code == 200
    data_telem = res_telem.json()
    assert data_telem["total_trades_logged"] >= 1

    # Fetch drift
    res_drift = client.get("/api/auditor/drift")
    assert res_drift.status_code == 200
    data_drift = res_drift.json()
    assert "cusum_drift_score" in data_drift
