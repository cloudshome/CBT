"""
End-to-End System Integration Tests for FastAPI Web Terminal & REST APIs.
"""

import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_api_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OPERATIONAL"
    assert "api_vitals" in data
    assert "drift_report" in data


def test_api_market_candles():
    response = client.get("/api/market/candles?symbol=BTC/USDT&timeframe=15m&limit=50")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTC/USDT"
    assert len(data["candles"]) == 50


def test_api_smc_scan():
    response = client.get("/api/smc/scan?symbol=BTC/USDT&timeframe=15m")
    assert response.status_code == 200
    data = response.json()
    assert "smc_patterns" in data
    assert "regime" in data


def test_api_scenarios():
    response = client.get("/api/scenarios?symbol=BTC/USDT")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) == 3


def test_api_decision_council():
    response = client.get("/api/decision/council?symbol=BTC/USDT")
    assert response.status_code == 200
    data = response.json()
    assert "final_decision" in data
    assert data["final_decision"] in ["LONG", "SHORT", "NO_TRADE"]


def test_api_shadow_trade_and_ledger():
    response = client.post(
        "/api/shadow/trade",
        json={
            "symbol": "BTC/USDT",
            "direction": "LONG",
            "size": 0.5,
            "entry_price": 88450.0,
            "stop_loss": 87200.0,
            "take_profit": 90500.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["position_id"].startswith("POS_")


def test_api_command_parser():
    response = client.post(
        "/api/command/parse",
        json={"command_text": "Entered Gold Long at 2675, SL 2668, TP 2695, 0.5 lot"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid_command"]
    assert data["symbol"] == "XAU/USD"
    assert data["direction"] == "LONG"


def test_api_desk_copilot_fallback():
    response = client.post(
        "/api/desk/ask",
        json={"message": "What is the current market bias?", "symbol": "BTC/USDT"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 10


def test_api_chart_memory_save_and_retrieve():
    # 1. Save chart memory
    save_payload = {
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "drawings": [
            {
                "id": "draw_101",
                "type": "box",
                "t1": 1740000000,
                "p1": 88000.0,
                "t2": 1740003600,
                "p2": 88500.0,
                "color": "#38bdf8",
                "width": 2,
            },
            {
                "id": "draw_102",
                "type": "hline",
                "p1": 89000.0,
                "color": "#10b981",
                "width": 2,
            },
        ],
        "indicators": {"fvg": True, "ob": True, "sweeps": False, "cvd": True},
        "chart_config": {"activeColor": "#38bdf8", "activeWidth": 2},
    }
    save_res = client.post("/api/chart/memory", json=save_payload)
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "SUCCESS"

    # 2. Retrieve saved chart memory
    get_res = client.get("/api/chart/memory?symbol=BTC/USDT&timeframe=15m")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["symbol"] == "BTC/USDT"
    assert get_data["timeframe"] == "15m"
    assert len(get_data["drawings"]) == 2
    assert get_data["drawings"][0]["id"] == "draw_101"
    assert get_data["indicators"]["sweeps"] is False
    assert get_data["chart_config"]["activeColor"] == "#38bdf8"

    # 3. Clear chart memory
    del_res = client.delete("/api/chart/memory?symbol=BTC/USDT&timeframe=15m")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "SUCCESS"

    # 4. Verify cleared
    get_cleared = client.get("/api/chart/memory?symbol=BTC/USDT&timeframe=15m")
    assert get_cleared.status_code == 200
    assert len(get_cleared.json()["drawings"]) == 0

