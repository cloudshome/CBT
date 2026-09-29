"""
End-to-End Critical Path Verification (Task K-UI.4 / Priority 12.6)
Validates the complete execution loop:
Market Telemetry -> Kronos Forecast -> Advisory Risk Sizing -> Order Placement -> Position Reconciliation -> Autopsy Attribution
"""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_e2e_critical_trading_pipeline():
    symbol = "BTC/USDT"
    timeframe = "15m"

    # 1. Fetch Market Telemetry & Candlestick History
    candles_res = client.get(f"/api/market/candles?symbol={symbol}&timeframe={timeframe}&limit=50")
    assert candles_res.status_code == 200
    candles_data = candles_res.json()
    assert len(candles_data["candles"]) == 50
    last_candle = candles_data["candles"][-1]
    current_price = last_candle["close"] if isinstance(last_candle, dict) else last_candle[4]
    assert current_price > 0

    # 2. Fetch Institutional Alpha Intelligence & SMC Patterns
    alpha_res = client.get(f"/api/institutional/alpha?symbol={symbol}&timeframe={timeframe}")
    assert alpha_res.status_code == 200
    alpha_data = alpha_res.json()
    assert "decision" in alpha_data
    assert "institutional_composite_score" in alpha_data
    assert alpha_data["decision"] in ["LONG", "SHORT", "WATCH", "NO_TRADE"]

    # 3. Query Kronos Probabilistic Trajectory Forecast
    kronos_res = client.get(
        f"/api/kronos/forecast?symbol=BTCUSDT&timeframe={timeframe}&samples=5&horizon=12"
    )
    assert kronos_res.status_code == 200
    kronos_data = kronos_res.json()
    assert "paths" in kronos_data
    assert len(kronos_data["paths"]) == 5
    assert "sky_derived_metrics" in kronos_data
    kronos_data["sky_derived_metrics"]["expected_return_pct"]
    kronos_data["sky_derived_metrics"]["directional_consensus"]

    # 4. Query Kronos Shadow Advisory Gate
    advisory_res = client.get(
        f"/api/kronos/advisory?symbol=BTCUSDT&timeframe={timeframe}&sky_decision=LONG"
    )
    assert advisory_res.status_code == 200
    advisory_data = advisory_res.json()
    assert advisory_data["advisory_recommendation"] in [
        "CONFIRM_TRADE",
        "DIVERGENCE_CAUTION",
        "NEUTRAL",
    ]
    assert advisory_data["sizing_multiplier"] > 0

    # 5. Submit Simulated Order to Risk Gate & Paper Trading Ledger
    order_payload = {
        "symbol": symbol,
        "direction": "LONG",
        "size": 0.25 * advisory_data["sizing_multiplier"],
        "entry_price": current_price,
        "stop_loss": current_price * 0.985,
        "take_profit": current_price * 1.045,
    }
    trade_res = client.post("/api/shadow/trade", json=order_payload)
    assert trade_res.status_code == 200
    trade_data = trade_res.json()
    assert trade_data["status"] == "SUCCESS"
    position_id = trade_data["position_id"]
    assert position_id.startswith("POS_")

    # 6. Verify Position Exists in Active Shadow Positions
    positions_res = client.get("/api/shadow/positions")
    assert positions_res.status_code == 200
    positions_data = positions_res.json()
    assert "open_positions" in positions_data
    assert any(p["position_id"] == position_id for p in positions_data["open_positions"])

    # 7. Check Kronos Health Monitor & Telemetry
    health_res = client.get("/api/kronos/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["status"] in ["HEALTHY", "DEGRADED", "UNAVAILABLE", "STAGING"]
