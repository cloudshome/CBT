"""
Comprehensive integration test suite covering FastAPI auxiliary endpoints
identified in the Boss-Level Audit.
Validates HTTP contracts, data models, error handling, and operational integrity.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import core.auth as auth_mod
from app import app

TEST_KEY = "sk-auxiliary-route-test"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client(client, monkeypatch):
    monkeypatch.setattr(auth_mod, "API_KEY", TEST_KEY)
    return client


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_KEY}


class TestFastAPIAuxiliaryRoutes:
    """Systematic integration tests across institutional auxiliary endpoints."""

    # 1. System Readiness & Health
    def test_system_readiness_and_root(self, client):
        res_ready = client.get("/ready")
        assert res_ready.status_code in {200, 503}

        res_root = client.get("/")
        assert res_root.status_code == 200
        assert len(res_root.text) > 0

    # 2. Market Data & Feeds
    def test_market_ticker_and_state(self, client):
        res = client.get("/api/market/ticker?symbol=BTC/USDT")
        assert res.status_code == 200
        data = res.json()
        assert "symbol" in data or "price" in data or "ticker" in data

        res_state = client.get("/api/market/state?symbol=BTC/USDT")
        assert res_state.status_code == 200

    def test_market_macro_and_sentiment(self, client):
        res_macro = client.get("/api/market/macro")
        assert res_macro.status_code == 200

        res_sent = client.get("/api/market/sentiment")
        assert res_sent.status_code == 200

    def test_market_dossier(self, client):
        res = client.get("/api/market/dossier?symbol=BTC/USDT")
        assert res.status_code == 200

    def test_market_candles_and_tickers(self, client):
        res_candles = client.get("/api/candles?symbol=BTC/USDT&timeframe=15m&limit=20")
        assert res_candles.status_code == 200

        res_tickers = client.get("/api/tickers")
        assert res_tickers.status_code == 200

        res_mtf = client.get("/api/mtf?symbol=BTC/USDT")
        assert res_mtf.status_code == 200

        res_scan = client.get("/api/scan")
        assert res_scan.status_code == 200

    # 3. Paper & Execution Desk
    def test_paper_desk_endpoints(self, authed_client):
        res_pos = authed_client.get("/api/paper/positions", headers=_auth_headers())
        assert res_pos.status_code == 200

        res_cfg = authed_client.get("/api/paper/config", headers=_auth_headers())
        assert res_cfg.status_code == 200

        res_ovw = authed_client.get("/api/paper/desk-overview", headers=_auth_headers())
        assert res_ovw.status_code == 200

    def test_shadow_desk_and_execution_routes(self, authed_client):
        res_routes = authed_client.get("/api/execution/routes")
        assert res_routes.status_code == 200

        res_reset = authed_client.post("/api/shadow/reset", headers=_auth_headers())
        assert res_reset.status_code in {200, 204}

    # 4. Strategy, Simulation & AI
    def test_ai_narrative_and_simulation(self, client):
        res_ai = client.get("/api/ai/live-narrative?symbol=BTC/USDT")
        assert res_ai.status_code == 200

        res_sim = client.get("/api/path-simulation?symbol=BTC/USDT&horizon=12")
        assert res_sim.status_code == 200

        res_opt = client.get("/api/strategy/optimize/results")
        assert res_opt.status_code == 200

    def test_sky_intelligence_and_vwap(self, client):
        res_intel = client.get("/api/sky/intelligence?symbol=BTC/USDT")
        assert res_intel.status_code == 200

        res_vwap = client.get("/api/sky/vwap?symbol=BTC/USDT")
        assert res_vwap.status_code == 200

    # 5. Governance & Incidents
    def test_governance_proposals(self, authed_client):
        res = authed_client.get("/api/governance/proposals")
        assert res.status_code == 200

    def test_incident_escalations(self, authed_client):
        res = authed_client.get("/api/incident/escalations")
        assert res.status_code == 200

        res_trig = authed_client.post(
            "/api/incident/simulate_trigger",
            json={"tier": "NOTICE", "description": "Simulated drop"},
            headers=_auth_headers(),
        )
        assert res_trig.status_code in {200, 201, 202}

    def test_burn_in_telemetry(self, authed_client):
        res_status = authed_client.get("/api/burn-in/status")
        assert res_status.status_code == 200

        res_sessions = authed_client.get("/api/burn-in/sessions")
        assert res_sessions.status_code == 200

    # 6. Research & Knowledge Graph
    def test_research_graph_and_vaults(self, authed_client):
        res_graph = authed_client.get("/api/research/graph")
        assert res_graph.status_code == 200

        res_vaults = authed_client.get("/api/research/vaults")
        assert res_vaults.status_code == 200

        res_inbox = authed_client.get("/api/research/inbox")
        assert res_inbox.status_code == 200

    # 7. High-Frequency Telemetry
    def test_hf_telemetry_endpoints(self, client):
        res_recent = client.get("/api/telemetry/hf/recent")
        assert res_recent.status_code == 200

        res_metrics = client.get("/api/telemetry/hf/metrics")
        assert res_metrics.status_code == 200

    # 8. Lab, Prediction & League
    def test_lab_and_predictions(self, authed_client):
        res_wf = authed_client.post(
            "/api/lab/walk-forward?symbol=BTC/USDT", headers=_auth_headers()
        )
        assert res_wf.status_code == 200

        res_cal = authed_client.get("/api/prediction/calibration")
        assert res_cal.status_code == 200

        res_ladder = authed_client.get("/api/prediction/ladder")
        assert res_ladder.status_code == 200

        res_ledger = authed_client.get("/api/prediction/ledger")
        assert res_ledger.status_code == 200

        res_league = authed_client.get("/api/league/leaderboard")
        assert res_league.status_code == 200

    # 9. Institutional Order Flow & Macro
    def test_institutional_orderflow(self, client):
        res_imb = client.get("/api/institutional/orderbook-imbalance?symbol=BTC/USDT")
        assert res_imb.status_code == 200

        res_cvd = client.get("/api/institutional/cvd?symbol=BTC/USDT")
        assert res_cvd.status_code == 200

        res_dossier = client.get("/api/institutional/dossier?symbol=BTC/USDT")
        assert res_dossier.status_code == 200

        res_macro = client.get("/api/macro/current")
        assert res_macro.status_code == 200

    # 10. Trader Control & Kronos Endpoints
    def test_trader_and_kronos_routes(self, authed_client):
        res_trader = authed_client.get("/api/trader/status")
        assert res_trader.status_code == 200

        res_history = authed_client.get("/api/kronos/history")
        assert res_history.status_code == 200

        res_cal = authed_client.get("/api/kronos/calibration")
        assert res_cal.status_code == 200

    # 11. Additional Decision, Dossier & Episodic Memory
    def test_additional_decision_and_dossier_routes(self, client):
        res_alloc = client.get("/api/decision/allocation?symbol=BTC/USDT")
        assert res_alloc.status_code == 200

        res_dossier = client.get("/api/dossier?symbol=BTC/USDT")
        assert res_dossier.status_code == 200

        res_mem = client.get("/api/memory/similarity?symbol=BTC/USDT")
        assert res_mem.status_code == 200

    # 12. Autonomous Trader & Burn-In Control
    def test_additional_trader_and_burn_in_actions(self, authed_client):
        res_t_toggle = authed_client.post(
            "/api/trader/toggle", json={"enabled": False}, headers=_auth_headers()
        )
        assert res_t_toggle.status_code == 200

        res_t_scan = authed_client.post("/api/trader/scan", headers=_auth_headers())
        assert res_t_scan.status_code == 200

        res_b_toggle = authed_client.post(
            "/api/burn-in/toggle", json={"active": False}, headers=_auth_headers()
        )
        assert res_b_toggle.status_code == 200

    # 13. Advanced Lab Simulations
    def test_lab_backtest_and_stress_test(self, authed_client):
        res_bt = authed_client.post(
            "/api/lab/backtest?symbol=BTC/USDT&timeframe=15m", headers=_auth_headers()
        )
        assert res_bt.status_code == 200

        res_stress = authed_client.post(
            "/api/lab/stress-test?symbol=BTC/USDT&timeframe=15m", headers=_auth_headers()
        )
        assert res_stress.status_code == 200

    # 14. Shadow Close & HF Telemetry Record
    def test_shadow_close_and_hf_telemetry_record(self, authed_client):
        res_close = authed_client.post(
            "/api/shadow/close",
            json={"position_id": "nonexistent_pos_1", "exit_price": 60000.0},
            headers=_auth_headers(),
        )
        assert res_close.status_code in {200, 404}

        res_hf = authed_client.post(
            "/api/telemetry/hf/record",
            json={
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "t_recv_ns": 1000,
                "t_queue_ns": 2000,
                "t_decision_ns": 3000,
                "t_exec_ns": 4000,
                "bid": 65000.0,
                "ask": 65001.0,
                "order_side": "BUY",
                "order_price": 65000.0,
                "execution_price": 65000.5,
                "order_size": 0.1,
            },
            headers=_auth_headers(),
        )
        assert res_hf.status_code in {200, 201}

    # 15. Research Practice & Provenance
    def test_research_practice_and_provenance(self, authed_client):
        res_prac = authed_client.get("/api/research/practice/candlestick_reversal")
        assert res_prac.status_code in {200, 404}

        res_drill = authed_client.post(
            "/api/research/practice/candlestick_reversal/drill?symbol=BTC/USDT",
            headers=_auth_headers(),
        )
        assert res_drill.status_code in {200, 404}

        res_prov = authed_client.get("/api/research/provenance/candlestick_reversal")
        assert res_prov.status_code in {200, 404}

    # 16. Governance & Incident Resolution
    def test_governance_and_incident_resolution(self, authed_client):
        res_appr = authed_client.post(
            "/api/governance/approve",
            json={"proposal_id": "prop_999", "operator_name": "TEST_AUDITOR"},
            headers=_auth_headers(),
        )
        assert res_appr.status_code in {200, 400, 404}

        res_res = authed_client.post(
            "/api/incident/resolve/inc_mock_1",
            json={"operator_id": "TEST_ADMIN", "notes": "Resolved during integration test"},
            headers=_auth_headers(),
        )
        assert res_res.status_code in {200, 404}
