"""tests/test_m69_gui_desk_endpoints.py — Milestone 69 Backend Test Suite.

Verifies:
1. test_m69_shadow_history_endpoint_schema: GET /api/desk/shadow/history returns
   valid bars and fills arrays with real_capital_enabled is False.
2. test_m69_shadow_run_endpoint_idempotent_and_paper_only: POST /api/desk/shadow/run?source=parquet
   runs idempotently under TIER_0_PAPER without placing exchange orders.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import app


def test_m69_shadow_history_endpoint_schema():
    """GET /api/desk/shadow/history returns valid schema and real_capital_enabled is False."""
    client = TestClient(app)
    resp = client.get("/api/desk/shadow/history?limit_bars=100&limit_fills=20")
    assert resp.status_code == 200
    data = resp.json()

    assert "bars" in data
    assert "fills" in data
    assert isinstance(data["bars"], list)
    assert isinstance(data["fills"], list)
    assert data["capital_mode"] == "TIER_0_PAPER"
    assert data["real_capital_enabled"] is False

    # If bars exist in the database, verify bar item schema
    if data["bars"]:
        bar = data["bars"][0]
        assert "bar_ts_utc" in bar
        assert "equity_usd" in bar
        assert "bnh_equity_usd" in bar
        assert "gross_exposure" in bar
        assert "regime_label" in bar

    # If fills exist in the database, verify fill item schema
    if data["fills"]:
        fill = data["fills"][0]
        assert "bar_ts_utc" in fill
        assert "symbol" in fill
        assert "side" in fill
        assert "units" in fill
        assert "live_exec_price" in fill
        assert "slippage_bps" in fill
        assert "fee_usd" in fill


def test_m69_shadow_run_endpoint_idempotent_and_paper_only():
    """POST /api/desk/shadow/run?source=parquet runs idempotently under TIER_0_PAPER."""
    client = TestClient(app)

    # First execution run
    resp1 = client.post("/api/desk/shadow/run?source=parquet")
    assert resp1.status_code == 200
    data1 = resp1.json()

    assert data1["capital_mode"] == "TIER_0_PAPER"
    assert data1["real_capital_enabled"] is False
    assert "cycle" in data1
    assert "scorecard" in data1
    assert data1["cycle"]["status"] in ("SUCCESS", "ALREADY_PROCESSED")
    assert data1["scorecard"]["real_capital_enabled"] is False

    # Second immediate run should be idempotent (ALREADY_PROCESSED)
    resp2 = client.post("/api/desk/shadow/run?source=parquet")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data2["cycle"]["status"] == "ALREADY_PROCESSED"
    assert data2["cycle"]["fills"] == 0
    assert data2["cycle"]["notified"] is False
    assert data2["capital_mode"] == "TIER_0_PAPER"
    assert data2["real_capital_enabled"] is False
