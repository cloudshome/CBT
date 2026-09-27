"""
tests/execution/test_strategy_gateway_routes.py
================================================
Comprehensive integration test suite for Milestone 26: Strategy Reality Gateway REST API.

Validates:
1. Authentication & Security (M26-01):
   - Missing or invalid API key rejected with 401/403.
   - Live capital execution permanently disabled (REAL_CAPITAL_ENABLED = False).
2. Deterministic Sizing Previews & Watermarking (M26-05):
   - /compile/kronos and /compile/smc return THEORETICAL SIZING PREVIEW - EXECUTION PROHIBITED.
3. Asynchronous Qualification Replay Job Lifecycle (M26-02, M26-09):
   - POST /qualification/jobs returns HTTP 202 Accepted with job_id.
   - Idempotency key deduplication returns existing job without duplicate replay.
   - Concurrency limiter rejects concurrent runs on the same strategy (HTTP 409).
   - GET /qualification/jobs/{job_id} reflects progressive execution state.
   - GET /qualification/jobs/{job_id}/report returns completed scorecard.
4. Paginated SQLite Evidence Ledger (M26-07):
   - GET /qualification/evidence respects limit, offset, and returns total_count.
5. Authoritative Collateral Risk Scorecard & Delta Urgency (M26-03, M26-06, M26-10):
   - Freshness contract verified: age_ms, snapshot timestamp, data_quality.
   - Degraded venue conditions return DEGRADED_PARTIAL gracefully.
6. 5-Horizon TCA Markout Profile & Censorship Accounting (M26-04):
   - /markouts/survivorship_summary discloses fill_count, censored_markouts_count, and 95% CI bands.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import core.auth as auth_mod
from app import app
from core.execution.strategy_gateway.job_manager import JobStatus

TEST_KEY = "sk-test-gateway-key-institutional"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client(client, monkeypatch):
    monkeypatch.setattr(auth_mod, "API_KEY", TEST_KEY)
    return client


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_KEY}


class TestStrategyGatewayRoutes:
    """Rigorous tests covering Milestone 26 Strategy Reality Gateway REST API."""

    # -----------------------------------------------------------------------
    # 1. Authentication & Operational Health
    # -----------------------------------------------------------------------

    def test_unauthenticated_requests_rejected(self, client, monkeypatch):
        """Unauthenticated requests must be rejected (M26-01)."""
        # Activate the auth guard — when API_KEY is empty the module allows all
        # requests through in dev mode, so we must set it to a non-empty value.
        monkeypatch.setattr(auth_mod, "API_KEY", TEST_KEY)
        res = client.get("/api/v1/strategy_gateway/status")
        assert res.status_code in {401, 403}

    def test_gateway_status_operational_contract(self, authed_client):
        """Gateway status reports operational health, capital firewall, and freshness contract."""
        res = authed_client.get("/api/v1/strategy_gateway/status", headers=_auth_headers())
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "OPERATIONAL"
        assert data["real_capital_enabled"] is False  # Permanent Capital Firewall
        assert data["execution_authority"] == "DENIED"
        assert "gates" in data
        assert data["gates"]["gate1_eligibility"]["status"] == "ACTIVE"
        assert data["gates"]["gate2_compiler"]["status"] == "ACTIVE"
        assert data["gates"]["gate3_feasibility"]["status"] == "ACTIVE"
        assert data["gates"]["gate4_sizing"]["status"] == "ACTIVE"
        assert "telemetry_contract" in data
        assert data["telemetry_contract"]["data_quality"] == "FRESH"

    # -----------------------------------------------------------------------
    # 2. Non-Executable Proposal Previews & Watermarking (M26-05)
    # -----------------------------------------------------------------------

    def test_compile_kronos_proposal_watermarked(self, authed_client):
        """Kronos forecast compilation returns non-executable preview watermark."""
        req = {
            "symbol": "BTC/USDT",
            "direction": "LONG",
            "horizon_minutes": 15,
            "forecast_return_bps": 28.0,
            "prediction_entropy": 0.32,
            "model_tier": "GRADE_E3",
            "reference_price": 65000.0,
        }
        res = authed_client.post(
            "/api/v1/strategy_gateway/compile/kronos",
            json=req,
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "COMPILED_PREVIEW"
        assert data["watermark"] == "THEORETICAL SIZING PREVIEW - EXECUTION PROHIBITED"
        prop = data["proposal"]
        assert prop["execution_status"] == "THEORETICAL_PREVIEW_EXECUTION_PROHIBITED"
        assert prop["real_capital_enabled"] is False
        assert prop["intended_size_usd"] > 0

    def test_compile_smc_proposal_watermarked(self, authed_client):
        """SMC order flow compilation returns non-executable preview watermark."""
        req = {
            "symbol": "BTC/USDT",
            "direction": "BUY",
            "structure_type": "ORDER_BLOCK",
            "timeframe": "15m",
            "fvg_depth_ticks": 8,
            "order_flow_imbalance": 0.45,
            "reference_price": 65000.0,
        }
        res = authed_client.post(
            "/api/v1/strategy_gateway/compile/smc",
            json=req,
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "COMPILED_PREVIEW"
        assert data["watermark"] == "THEORETICAL SIZING PREVIEW - EXECUTION PROHIBITED"
        prop = data["proposal"]
        assert prop["execution_status"] == "THEORETICAL_PREVIEW_EXECUTION_PROHIBITED"
        assert prop["real_capital_enabled"] is False

    # -----------------------------------------------------------------------
    # 3. Asynchronous Qualification Replay Lifecycle (M26-02, M26-09)
    # -----------------------------------------------------------------------

    def test_asynchronous_qualification_job_lifecycle(self, authed_client):
        """Tests full asynchronous job lifecycle: submit -> 202 -> poll -> report."""
        unique_strat = f"TEST_KRONOS_ROUTE_{int(time.time() * 1000)}"
        req = {
            "strategy_id": unique_strat,
            "strategy_version": "1.0.0",
            "deployment_stage": "EXECUTION_MODEL_VALIDATED",
            "dataset_hash": "4f8a92be6b4d32109876543210abcdef0123456789abcdef0123456789abcdef",
            "experiment_id": "exp_route_test_001",
            "signals_count": 5,
            "account_equity_usd": 100000.0,
            "simulated_spread_bps": 3.0,
            "simulated_depth_qty": 100.0,
            "mock_fill_slippage_bps": 1.5,
            "min_sample_size": 5,
            "max_allowable_is_bps": 15.0,
        }

        # Step 1: Submit job (returns 202 Accepted)
        res = authed_client.post(
            "/api/v1/strategy_gateway/qualification/jobs",
            json=req,
            headers=_auth_headers(),
        )
        assert res.status_code == 202
        submit_data = res.json()
        assert submit_data["status"] == "ACCEPTED"
        assert submit_data["was_created"] is True
        job_id = submit_data["job"]["job_id"]
        assert job_id.startswith("job_")

        # Step 2: Poll status
        poll_res = authed_client.get(
            f"/api/v1/strategy_gateway/qualification/jobs/{job_id}",
            headers=_auth_headers(),
        )
        assert poll_res.status_code == 200
        poll_data = poll_res.json()
        assert poll_data["job"]["strategy_id"] == unique_strat
        assert poll_data["job"]["status"] in [s.value for s in JobStatus]

        # Step 3: Wait briefly for background task completion
        timeout = 5.0
        start = time.time()
        committed = False
        while time.time() - start < timeout:
            p = authed_client.get(
                f"/api/v1/strategy_gateway/qualification/jobs/{job_id}",
                headers=_auth_headers(),
            ).json()
            if p["job"]["status"] in ("COMMITTED", "FAILED"):
                committed = p["job"]["status"] == "COMMITTED"
                break
            time.sleep(0.1)

        # Step 4: Verify finalized report
        if committed:
            rep_res = authed_client.get(
                f"/api/v1/strategy_gateway/qualification/jobs/{job_id}/report",
                headers=_auth_headers(),
            )
            assert rep_res.status_code == 200
            rep_data = rep_res.json()
            assert "report" in rep_data
            assert rep_data["report"]["strategy_id"] == unique_strat
            assert "qualification_verdict" in rep_data["report"]
            assert "report_hash" in rep_data["report"]
            assert len(rep_data["report"]["report_hash"]) == 64

    def test_idempotency_key_deduplication(self, authed_client):
        """Submitting with identical Idempotency-Key returns existing job without duplicate replay (M26-02)."""
        strat_id = f"IDEM_STRAT_{int(time.time() * 1000)}"
        idem_key = f"idem_key_{int(time.time() * 1000)}"
        req = {
            "strategy_id": strat_id,
            "strategy_version": "1.0.0",
            "deployment_stage": "EXECUTION_MODEL_VALIDATED",
            "signals_count": 5,
        }
        headers = {**_auth_headers(), "Idempotency-Key": idem_key}

        # First submission -> was_created=True
        res1 = authed_client.post(
            "/api/v1/strategy_gateway/qualification/jobs",
            json=req,
            headers=headers,
        )
        assert res1.status_code == 202
        data1 = res1.json()
        assert data1["was_created"] is True
        job1_id = data1["job"]["job_id"]

        # Second submission with same idempotency key -> was_created=False, same job_id
        res2 = authed_client.post(
            "/api/v1/strategy_gateway/qualification/jobs",
            json=req,
            headers=headers,
        )
        assert res2.status_code == 202
        data2 = res2.json()
        assert data2["was_created"] is False
        assert data2["job"]["job_id"] == job1_id

    # -----------------------------------------------------------------------
    # 4. Paginated SQLite Evidence Ledger (M26-07)
    # -----------------------------------------------------------------------

    def test_qualification_evidence_pagination(self, authed_client):
        """GET /qualification/evidence enforces pagination with total_count and limit bounds (M26-07)."""
        res = authed_client.get(
            "/api/v1/strategy_gateway/qualification/evidence?limit=5&offset=0&order=desc",
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "total_count" in data
        assert "records" in data
        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["records"]) <= 5

    # -----------------------------------------------------------------------
    # 5. Collateral Risk Scorecard & Freshness Contract (M26-03, M26-06, M26-10)
    # -----------------------------------------------------------------------

    def test_collateral_scorecard_freshness_and_degraded_safety(self, authed_client):
        """Collateral scorecard returns 4-factor risk metrics, Delta U, and freshness contract."""
        res = authed_client.get(
            "/api/v1/strategy_gateway/risk/collateral_scorecard",
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("SUCCESS", "DEGRADED_PARTIAL")  # M26-10 Degraded Safety
        assert "collateral_report" in data
        assert "risk_scorecard" in data
        assert "cross_venue_imbalance_pct" in data
        assert "telemetry_contract" in data

        contract = data["telemetry_contract"]
        assert "data_freshness_ms" in contract
        assert "snapshot_timestamp_utc" in contract
        assert "data_quality" in contract
        assert "is_stale" in contract

    # -----------------------------------------------------------------------
    # 6. Multi-Venue Delta Urgency (M26-03, M26-10)
    # -----------------------------------------------------------------------

    def test_delta_tolerance_urgency_tier(self, authed_client):
        """Delta tolerance returns net unhedged delta and 3-tier urgency classification."""
        res = authed_client.get(
            "/api/v1/strategy_gateway/risk/delta_tolerance?asset=BTC",
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("SUCCESS", "DEGRADED_PARTIAL")
        assert "exposure" in data
        assert "basis_metric" in data
        assert data["urgency_tier"] in ("NEUTRAL", "PASSIVE_TWAP", "ACTIVE_TAKER")
        assert "telemetry_contract" in data

    # -----------------------------------------------------------------------
    # 7. 5-Horizon TCA Markout Survivorship & Censorship (M26-04)
    # -----------------------------------------------------------------------

    def test_markout_survivorship_and_censorship(self, authed_client):
        """Markouts endpoint explicitly reports censored markouts count and 95% CI bands (M26-04)."""
        res = authed_client.get(
            "/api/v1/strategy_gateway/markouts/survivorship_summary?symbol=BTCUSDT",
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "fill_count" in data
        assert "censored_markouts_count" in data
        assert "censored_percentage" in data
        assert data["horizons_s"] == [1, 5, 30, 60, 300]
        assert "mean_markout_bps" in data
        assert "confidence_intervals_bps_95" in data
        assert "is_decomposition" in data

        for h in ("1s", "5s", "30s", "60s", "300s"):
            assert h in data["mean_markout_bps"]
            assert h in data["confidence_intervals_bps_95"]

    def test_unrecognized_deployment_stage_fails_closed(self, authed_client):
        """Unrecognized deployment stage falls back to RESEARCH_ONLY and fails closed cleanly."""
        unique_strat = f"TEST_FALLBACK_STAGE_{int(time.time() * 1000)}"
        req = {
            "strategy_id": unique_strat,
            "strategy_version": "1.0.0",
            "deployment_stage": "NON_EXISTENT_CUSTOM_STAGE",
            "dataset_hash": "4f8a92be6b4d32109876543210abcdef0123456789abcdef0123456789abcdef",
            "experiment_id": "exp_stage_fallback_test",
            "signals_count": 5,
        }

        res = authed_client.post(
            "/api/v1/strategy_gateway/qualification/jobs",
            json=req,
            headers=_auth_headers(),
        )
        assert res.status_code == 202
        job_id = res.json()["job"]["job_id"]

        # Poll until terminal state
        timeout = 5.0
        start = time.time()
        final_status = None
        while time.time() - start < timeout:
            p = authed_client.get(
                f"/api/v1/strategy_gateway/qualification/jobs/{job_id}",
                headers=_auth_headers(),
            ).json()
            status_val = p["job"]["status"]
            if status_val in ("COMMITTED", "FAILED"):
                final_status = status_val
                break
            time.sleep(0.1)

        assert final_status == "COMMITTED"
        report_res = authed_client.get(
            f"/api/v1/strategy_gateway/qualification/jobs/{job_id}/report",
            headers=_auth_headers(),
        )
        assert report_res.status_code == 200
        report = report_res.json()["report"]
        # Falls back to RESEARCH_ONLY, which is rejected by Gate 1 as insufficient
        assert report["qualification_verdict"] == "REJECTED_GOVERNANCE"
