"""
tests/test_sovereign_master_agent.py
====================================
Verification test battery for the Sovereign Master Trading Agent.
Tests:
- Strict Tier-1 Asset Restrictions (BTC, ETH, GOLD only)
- Five-Pillar Synthetic Reasoning Engine (Memory, Vault, Structure, Online, Decision)
- Empirical Memory Guard & Chop Filter Application
- Concurrent Multi-Asset Dashboard Aggregation
- FastAPI REST Endpoints & Instant Execution Clearance
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from core.mastermind.sovereign_master_agent import sovereign_master_agent


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_sovereign_master_agent_restricts_to_tier1_assets():
    """Validates that the Sovereign Agent only accepts Tier-1 assets."""
    # Permitted assets
    for valid_sym in ["BTC/USDT", "BTCUSDT", "ETH/USDT", "ETHUSDT", "XAU/USD", "XAUUSD"]:
        dec = await sovereign_master_agent.synthesize_asset(valid_sym)
        assert dec.decision in ("BUY", "SELL", "CASH")
        assert dec.symbol in ("BTC/USDT", "ETH/USDT", "XAU/USD", "PAXG/USDT")

    # Rejected non-tier-1 assets
    for invalid_sym in ["SOL/USDT", "DOGE/USDT", "PEPE/USDT", "ADA/USDT"]:
        with pytest.raises(ValueError, match="Sovereign Master Agent is locked to Tier-1 assets only"):
            await sovereign_master_agent.synthesize_asset(invalid_sym)


@pytest.mark.asyncio
async def test_sovereign_master_agent_memory_and_research_pillars():
    """Validates that memory and research vault context are actively integrated."""
    btc_dec = await sovereign_master_agent.synthesize_asset("BTC/USDT")
    assert "memory_guidance" in btc_dec.memory_dossier
    assert "macro_regime" in btc_dec.research_dossier
    assert len(btc_dec.research_dossier["vault_citations"]) >= 1

    eth_dec = await sovereign_master_agent.synthesize_asset("ETH/USDT")
    # ETH memory must include the drawdown caution and risk adjustment factor
    assert eth_dec.memory_dossier["risk_adjustment_factor"] < 1.0
    assert "Historical Drawdown Caution" in eth_dec.memory_dossier["memory_guidance"]

    gold_dec = await sovereign_master_agent.synthesize_asset("XAU/USD")
    assert gold_dec.memory_dossier["win_rate_pct"] >= 0.0
    assert "Historical Edge Validated" in gold_dec.memory_dossier["memory_guidance"]


@pytest.mark.asyncio
async def test_sovereign_master_agent_get_all_decisions():
    """Validates concurrent parallel dashboard synthesis for all 3 assets."""
    dashboard = await sovereign_master_agent.get_all_sovereign_decisions()
    assert dashboard["status"] == "ONLINE_ACTIVE"
    assert "BTC/USDT" in dashboard["decisions"]
    assert "ETH/USDT" in dashboard["decisions"]
    assert "XAU/USD" in dashboard["decisions"]


def test_api_sovereign_agent_dashboard_endpoint(client):
    """Tests GET /api/terminal/sovereign-agent/dashboard."""
    res = client.get("/api/terminal/sovereign-agent/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ONLINE_ACTIVE"
    assert "BTC/USDT" in data["decisions"]


def test_api_sovereign_agent_decision_endpoint(client):
    """Tests GET /api/terminal/sovereign-agent/decision?symbol=BTCUSDT."""
    res = client.get("/api/terminal/sovereign-agent/decision?symbol=BTCUSDT")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTC/USDT"
    assert data["decision"] in ("BUY", "SELL", "CASH")
    assert "confidence_pct" in data
    assert "expected_value_r" in data
    assert "thesis" in data


def test_api_sovereign_agent_decision_invalid_symbol(client):
    """Tests that querying a non-tier-1 asset fails closed with HTTP 400."""
    res = client.get("/api/terminal/sovereign-agent/decision?symbol=DOGEUSDT")
    assert res.status_code == 400
    assert "Sovereign Master Agent is locked to Tier-1 assets only" in res.json()["detail"]
