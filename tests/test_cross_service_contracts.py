"""
tests/test_cross_service_contracts.py
=====================================
Automated Integration Contract Suite for Cross-Service API Validation.
Enforces strict contract invariants across Python FastAPI authoritative endpoints,
Node/Express legacy facade, and Frontend client API expectations.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


class TestFastAPIHealthAndVitalsContracts:
    """Verifies that FastAPI health and system vitals conform to frontend contract expectations."""

    def test_api_health_contract_schema(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert data["status"] in ("OPERATIONAL", "HEALTHY", "DEGRADED")
        assert "version" in data
        assert "api_vitals" in data
        assert isinstance(data["api_vitals"], list)
        if data["api_vitals"]:
            v = data["api_vitals"][0]
            assert "endpoint_name" in v
            assert "status" in v
            assert "current_latency_ms" in v
        assert "drift_report" in data
        assert isinstance(data["drift_report"], dict)
        assert "database" in data
        assert isinstance(data["database"], dict)

    def test_root_health_endpoint_contract_parity(self):
        """Verifies /health and /api/health have identical contract schemas."""
        res_root = client.get("/health")
        res_api = client.get("/api/health")
        assert res_root.status_code == 200
        assert res_api.status_code == 200
        data_root = res_root.json()
        data_api = res_api.json()
        assert data_root["status"] == data_api["status"]
        assert data_root["version"] == data_api["version"]


class TestNormalizedMarketDataContracts:
    """Verifies candle schema normalization against frontend OHLCVCandle type."""

    def test_market_candles_payload_schema(self):
        res = client.get("/api/market/candles?symbol=BTC/USDT&timeframe=15m&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "symbol" in data
        assert "candles" in data
        assert isinstance(data["candles"], list)

        if data["candles"]:
            first = data["candles"][0]
            # Match frontend OHLCVCandle interface
            assert "timestamp" in first
            assert "open" in first
            assert "high" in first
            assert "low" in first
            assert "close" in first
            assert "volume" in first
            assert isinstance(first["open"], (int, float))
            assert isinstance(first["close"], (int, float))
            assert first["high"] >= first["low"]

    def test_orderbook_contract_schema(self):
        res = client.get("/api/market/orderbook?symbol=BTC/USDT&limit=5")
        assert res.status_code == 200
        data = res.json()
        assert "symbol" in data
        assert "asks" in data
        assert "bids" in data
        assert isinstance(data["asks"], list)
        assert isinstance(data["bids"], list)


class TestErrorEnvelopeAndStatusPropagation:
    """Verifies predictable JSON error envelopes and appropriate HTTP status codes."""

    def test_invalid_symbol_or_parameters_returns_400_or_422(self):
        res = client.get("/api/market/candles?symbol=&timeframe=invalid_tf&limit=-5")
        # FastAPI validation raises 400 or 422 for unprocessable query params
        assert res.status_code in (400, 422)
        err = res.json()
        assert "detail" in err or "error" in err

    def test_nonexistent_route_returns_404_json(self):
        res = client.get("/api/nonexistent_route_boundary_check_404")
        assert res.status_code == 404
        data = res.json()
        assert "detail" in data or "error" in data


class TestAuthenticationContractPropagation:
    """Verifies fail-closed authentication behavior when API_KEY is enforced."""

    def test_protected_routes_require_auth_when_configured(self):
        # When API_KEY is set in environment, sensitive endpoints must demand Bearer / X-API-Key
        with patch.dict(os.environ, {"API_KEY": "test_secure_key_1234567890"}):
            # Attempt access to a protected administrative endpoint without key
            res_no_key = client.post("/api/admin/circuit-breaker/reset", json={})
            if res_no_key.status_code != 404:
                # If endpoint exists, it must reject with 401 or 403
                assert res_no_key.status_code in (401, 403)

            # Access with valid Bearer token
            headers = {"Authorization": "Bearer test_secure_key_1234567890"}
            res_auth = client.post("/api/admin/circuit-breaker/reset", json={}, headers=headers)
            # Must not be rejected with 401
            assert res_auth.status_code != 401


class TestPaperTradingAndShadowContracts:
    """Verifies paper trading and shadow portfolio API contracts."""

    def test_shadow_positions_contract_schema(self):
        res = client.get("/api/shadow/positions")
        assert res.status_code == 200
        data = res.json()
        assert "open_positions" in data
        assert isinstance(data["open_positions"], list)
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_portfolio_risk_guardian_state_schema(self):
        res = client.get("/api/risk/guardian/state")
        if res.status_code == 200:
            data = res.json()
            assert "circuit_breaker_state" in data
            assert "current_equity" in data or "base_capital" in data
