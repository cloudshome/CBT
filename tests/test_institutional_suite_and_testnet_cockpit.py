"""
tests/test_institutional_suite_and_testnet_cockpit.py
=====================================================
Verification suite for institutional hedge fund brain suite,
testnet burn-in cockpit telemetry, and safe paper trade execution.
"""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_institutional_debate_endpoint(client):
    """Verifies that the Tri-Agent Adversarial Debate Council returns valid decisions."""
    res = client.get("/api/institutional/debate?symbol=BTC/USDT&timeframe=15m")
    assert res.status_code == 200
    data = res.json()
    assert "final_decision" in data
    assert data["final_decision"] in ("LONG", "SHORT", "NO_TRADE")
    assert "consensus_confidence" in data
    assert "bull_argument" in data
    assert "bear_argument" in data
    assert "skeptic_argument" in data


def test_institutional_whale_radar_endpoint(client):
    """Verifies that Whale Radar returns on-chain flows and liquidation clusters."""
    res = client.get("/api/institutional/whale-radar?symbol=BTC/USDT&price=65000.0")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTC/USDT"
    assert "liquidation_clusters" in data
    assert len(data["liquidation_clusters"]) > 0
    assert "top_100_whale_flow_24h_usd" in data
    assert "exchange_flow_sentiment" in data


def test_institutional_psychology_endpoint(client):
    """Verifies that the Behavioral Tilt Shield returns valid operator guardrails."""
    res = client.get("/api/institutional/psychology")
    assert res.status_code == 200
    data = res.json()
    assert "is_shield_locked" in data
    assert "allowed_to_execute" in data
    assert "guidance_message" in data
    assert "emotional_state_score" in data


def test_institutional_monte_carlo_endpoint(client):
    """Verifies that the 10,000-Path Monte Carlo stress tester returns ruin metrics."""
    res = client.post("/api/institutional/monte-carlo?symbol=BTC/USDT&timeframe=15m")
    assert res.status_code == 200
    data = res.json()
    assert "num_simulations" in data
    assert "probability_of_ruin" in data
    assert "p50_max_drawdown_pct" in data
    assert "p95_max_drawdown_pct" in data
    assert "is_safe" in data


def test_institutional_lead_lag_endpoint(client):
    """Verifies that the Cross-Asset Lead-Lag correlator projects macro latency signals."""
    res = client.get("/api/institutional/lead-lag?symbol=BTC/USDT")
    assert res.status_code == 200
    data = res.json()
    assert "signals" in data
    assert "dxy_price" in data
    assert "us10y_yield" in data
    assert "has_macro_shock" in data


def test_institutional_dynamic_hedge_endpoint(client):
    """Verifies that the Autonomous Dynamic Micro-Hedger evaluates portfolio delta."""
    res = client.get("/api/institutional/dynamic-hedge?symbol=BTC/USDT")
    assert res.status_code == 200
    data = res.json()
    assert "hedge_required" in data
    assert "target_symbol" in data
    assert "hedge_direction" in data
    assert "current_portfolio_delta_usd" in data


def test_testnet_burnin_report_endpoint(client):
    """Verifies that the Gate 5 Extended Testnet Burn-In telemetry report is active."""
    res = client.get("/api/testnet/burnin/report")
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "state" in data
    assert "durations" in data
    assert "invariants" in data
    assert len(data["invariants"]) >= 5


def test_testnet_campaign_status_endpoint(client):
    """Verifies that the sequence-monotonic campaign telemetry snapshot returns valid FSM state."""
    res = client.get("/api/testnet/campaign/status")
    assert res.status_code == 200
    data = res.json()
    assert "campaign_id" in data
    assert "state" in data
    assert "telemetry_seq" in data


def test_paper_trade_buy_and_sell_order_flow(client):
    """Verifies that paper trade Long and Short execution passes risk invariants."""
    # Long order
    res_long = client.post(
        "/api/paper/trade",
        json={
            "symbol": "BTC/USDT",
            "side": "BUY",
            "entryPrice": 65000.0,
            "sl": 64000.0,
            "tp": 67000.0,
            "size": 0.5,
        },
    )
    assert res_long.status_code == 200
    long_data = res_long.json()
    assert long_data["message"] == "Simulated order filled successfully"
    pos_id = long_data["trade"]["id"]

    # Close position
    res_close = client.post(
        "/api/paper/close",
        json={
            "positionId": pos_id,
            "exitPrice": 65500.0,
        },
    )
    assert res_close.status_code == 200
    assert res_close.json()["status"] == "SUCCESS"

    # Short order
    res_short = client.post(
        "/api/paper/trade",
        json={
            "symbol": "BTC/USDT",
            "side": "SELL",
            "entryPrice": 65000.0,
            "sl": 66000.0,
            "tp": 63000.0,
            "size": 0.5,
        },
    )
    assert res_short.status_code == 200
    assert res_short.json()["trade"]["side"] == "SELL"


def test_research_wikipedia_ingest_and_retrieval(client):
    """Verifies that Research Wikipedia ingests web links and extracts claims."""
    res = client.post(
        "/api/knowledge/wiki/ingest",
        json={
            "url_or_text": "https://arxiv.org/abs/1706.03762",
            "title": "Transformer Attention Paper",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    article = data["article"]
    assert "article_id" in article
    assert "key_claims" in article
    assert len(article["key_claims"]) > 0
    art_id = article["article_id"]

    # Retrieve article
    res_get = client.get(f"/api/knowledge/wiki/article/{art_id}")
    assert res_get.status_code == 200
    assert res_get.json()["article"]["article_id"] == art_id

    # Clean up test article
    client.delete(f"/api/knowledge/wiki/article/{art_id}")


def test_system_setup_and_vault_verification(client):
    """Verifies setup status telemetry and master password verification route."""
    res = client.get("/api/system/setup-status")
    assert res.status_code == 200
    data = res.json()
    assert "is_first_run" in data
    assert "supported_exchanges" in data

    # Verify vault password endpoint responds cleanly
    res_pwd = client.post(
        "/api/system/vault/verify-password",
        json={"password": "any_test_passphrase"},
    )
    # Either 200 (if no vault password set) or 401 (if password set and incorrect)
    assert res_pwd.status_code in (200, 401)

