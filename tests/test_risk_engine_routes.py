"""
tests/test_risk_engine_routes.py
================================
Adversarial & Integration Test Suite for Generation 7 Risk Engine & Multi-Strategy Ensemble REST API.

Validates:
1. GET  /api/v1/risk/ensemble/weights
2. POST /api/v1/risk/ensemble/evaluate
3. POST /api/v1/risk/stress-engine/simulate
4. POST /api/v1/risk/hrp/optimize
5. Authentication and error boundary handling
6. Constitutional capital isolation: real_capital_enabled = False
"""

import pytest
from fastapi.testclient import TestClient

import core.auth as auth_mod
from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_01_ensemble_weights_default_regime(client, monkeypatch):
    """Verifies default regime returns 5 strategy weights summing to 100%."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    resp = client.get("/api/v1/risk/ensemble/weights")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["regime"] == "TRENDING_HIGH_VOL"
    assert "HRP_RISK_PARITY" in data["weights"]
    assert "DIRECTIONAL_TREND" in data["weights"]
    assert "AVELLANEDA_STOIKOV_MM" in data["weights"]
    assert "CEX_DEX_LATENCY_ARB" in data["weights"]
    assert "RL_EXECUTION_PACER" in data["weights"]
    assert data["sum_weights"] == 1.0
    assert data["real_capital_enabled"] is False
    assert data["watermark"] == "NON_EXECUTABLE_RESEARCH_PREVIEW"


def test_02_ensemble_weights_crisis_regime(client, monkeypatch):
    """Verifies TOXIC_CRISIS_SURGE throttles MM & Arb to 5% and boosts HRP to 50%."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    resp = client.get("/api/v1/risk/ensemble/weights?regime=TOXIC_CRISIS_SURGE")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["regime"] == "TOXIC_CRISIS_SURGE"
    assert data["weights"]["HRP_RISK_PARITY"] == 0.50
    assert data["weights"]["AVELLANEDA_STOIKOV_MM"] == 0.05
    assert data["weights"]["CEX_DEX_LATENCY_ARB"] == 0.05
    assert data["weights"]["RL_EXECUTION_PACER"] == 0.30
    assert data["sum_weights"] == 1.0


def test_03_evaluate_ensemble_allocation_compliant(client, monkeypatch):
    """Verifies ensemble evaluation with compliant conservative positions."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    payload = {
        "portfolio_equity_usd": 50000.0,
        "regime": "TRENDING_HIGH_VOL",
        "positions": [
            {
                "symbol": "BTC/USDT",
                "quantity": 0.01,
                "entry_price": 60000.0,
                "current_mark_price": 61000.0,
                "initial_margin_rate": 0.05,
                "maintenance_margin_rate": 0.025,
                "asset_volatility": 0.025,
            }
        ],
        "estimated_portfolio_volatility": 0.02,
    }
    resp = client.post("/api/v1/risk/ensemble/evaluate", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["regime"] == "TRENDING_HIGH_VOL"
    assert data["total_portfolio_equity_usd"] == 50000.0
    assert "HRP_RISK_PARITY" in data["strategy_allocations"]
    assert data["is_constitutionally_compliant"] is True
    assert data["stress_profile"]["all_stress_scenarios_passed"] is True
    assert data["real_capital_enabled"] is False


def test_04_evaluate_ensemble_allocation_invalid_equity(client, monkeypatch):
    """Verifies that non-positive equity is rejected with HTTP 422/400."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    payload = {
        "portfolio_equity_usd": -1000.0,
        "regime": "TRENDING_HIGH_VOL",
        "positions": [],
    }
    resp = client.post("/api/v1/risk/ensemble/evaluate", json=payload)
    assert resp.status_code in (400, 422)


def test_05_stress_engine_simulation(client, monkeypatch):
    """Verifies extreme scenario stress simulation across Black Thursday, FTX, and Flash Crash."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    payload = {
        "collateral_cash_usd": 20000.0,
        "positions": [
            {
                "symbol": "BTC/USDT",
                "quantity": 0.05,
                "entry_price": 60000.0,
                "current_mark_price": 60000.0,
                "initial_margin_rate": 0.05,
                "maintenance_margin_rate": 0.025,
                "asset_volatility": 0.03,
            },
            {
                "symbol": "ETH/USDT",
                "quantity": 0.5,
                "entry_price": 3000.0,
                "current_mark_price": 3000.0,
                "initial_margin_rate": 0.05,
                "maintenance_margin_rate": 0.025,
                "asset_volatility": 0.04,
            },
        ],
        "estimated_portfolio_volatility": 0.025,
    }
    resp = client.post("/api/v1/risk/stress-engine/simulate", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_portfolio_equity_usd"] == 20000.0
    assert data["total_notional_usd"] == 4500.0
    assert data["effective_leverage"] == pytest.approx(4500.0 / 20000.0, abs=1e-4)
    assert data["analytical_var_99_usd"] > 0
    assert data["analytical_cvar_99_usd"] > data["analytical_var_99_usd"]
    assert len(data["scenario_results"]) == 3

    scenario_ids = [s["scenario_id"] for s in data["scenario_results"]]
    assert "BLACK_THURSDAY_2020" in scenario_ids
    assert "FTX_CONTAGION_2022" in scenario_ids
    assert "FLASH_CRASH_CASCADE" in scenario_ids
    assert data["all_stress_scenarios_passed"] is True
    assert data["real_capital_enabled"] is False


def test_06_hrp_optimize(client, monkeypatch):
    """Verifies Ledoit-Wolf shrinkage and Hierarchical Risk Parity optimization."""
    monkeypatch.setattr(auth_mod, "API_KEY", "")
    payload = {
        "account_equity_usd": 100000.0,
        "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"],
        "market_regime": "TRENDING_BULL",
        "invalidation_distances": {
            "BTC/USDT": 0.04,
            "ETH/USDT": 0.05,
            "SOL/USDT": 0.08,
            "PAXG/USDT": 0.02,
        },
    }
    resp = client.post("/api/v1/risk/hrp/optimize", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["account_equity_usd"] == 100000.0 or len(data["symbols"]) == 4
    assert data["market_regime"] == "TRENDING_BULL"
    assert data["portfolio_volatility_annualized"] > 0
    assert data["diversification_ratio"] > 1.0  # Proves risk reduction
    assert len(data["allocations"]) == 4

    # Check shrinkage report
    sr = data["shrinkage_report"]
    assert sr["is_positive_definite"] is True
    assert sr["shrunk_condition_number"] <= sr["sample_condition_number"]

    # Verify constitutional limits
    assert data["total_portfolio_heat_pct"] <= 0.0601  # <= 6.0% heat
    assert data["is_within_risk_caps"] is True
    assert data["real_capital_enabled"] is False


def test_07_auth_enforcement_when_key_configured(client, monkeypatch):
    """Verifies endpoints reject requests without valid key when API_KEY is set."""
    test_key = "test-secret-key-12345"
    monkeypatch.setattr(auth_mod, "API_KEY", test_key)

    # Missing header -> 401
    resp_missing = client.get("/api/v1/risk/ensemble/weights")
    assert resp_missing.status_code == 401

    # Wrong header -> 403
    resp_wrong = client.get(
        "/api/v1/risk/ensemble/weights",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp_wrong.status_code == 403

    # Valid header -> 200
    resp_valid = client.get(
        "/api/v1/risk/ensemble/weights",
        headers={"X-API-Key": test_key},
    )
    assert resp_valid.status_code == 200
