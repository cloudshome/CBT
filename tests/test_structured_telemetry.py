"""
tests/test_structured_telemetry.py
==================================
Comprehensive End-to-End Verification of Request Correlation & Structured Telemetry.
Enforces the mandatory 5-hop traceability chain:
  HTTP Request -> Orchestrator -> Sizer -> Shadow Portfolio -> Audit Bus
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.audit_bus import audit_bus
from core.correlation_context import (
    CorrelationIdMiddleware,
    correlation_scope,
    get_correlation_id,
    sanitize_correlation_id,
)
from core.half_kelly_sizer import half_kelly_position_sizer
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.orchestrator import sky_orchestrator


def _create_synthetic_candles(n: int = 40, base_price: float = 60000.0) -> list[dict[str, float]]:
    """Creates a deterministic list of OHLCV candles for testing."""
    candles = []
    p = base_price
    for i in range(n):
        c = p + (10.0 if i % 2 == 0 else -8.0)
        candles.append(
            {
                "timestamp": 1700000000000 + i * 900000,
                "open": p,
                "high": max(p, c) + 5.0,
                "low": min(p, c) - 5.0,
                "close": c,
                "volume": 100.0 + i,
            }
        )
        p = c
    return candles


class TestCorrelationIdSanitizationAndScope:
    """Verifies correlation ID generation, sanitization, and context scoping."""

    def test_valid_custom_correlation_id_preserved(self):
        valid_cid = "TRACE-ORDER-2026_09:12345"
        sanitized = sanitize_correlation_id(valid_cid)
        assert sanitized == valid_cid

    def test_malformed_correlation_id_rejected_and_regenerated(self):
        # Header injection attempt with newline and spaces
        malicious_cid = "BAD\r\nHeader: Injection <script>alert(1)</script>"
        sanitized = sanitize_correlation_id(malicious_cid)
        assert sanitized != malicious_cid
        assert sanitized.startswith("CID-")
        # Overly long ID
        long_cid = "X" * 128
        assert sanitize_correlation_id(long_cid).startswith("CID-")

    def test_missing_correlation_id_generates_safe_default(self):
        cid = sanitize_correlation_id(None)
        assert cid.startswith("CID-")

    def test_correlation_scope_binds_and_unwinds(self):
        assert get_correlation_id() is None
        with correlation_scope("CID-MANUAL-SCOPE-01") as bound_id:
            assert bound_id == "CID-MANUAL-SCOPE-01"
            assert get_correlation_id() == "CID-MANUAL-SCOPE-01"
        assert get_correlation_id() is None


class TestFiveHopEndToEndTraceability:
    """
    Demonstrates unbroken correlation identity across the complete institutional pipeline:
    HTTP Request -> Orchestrator -> Sizer -> Shadow Portfolio -> Audit Bus
    """

    def test_complete_five_hop_trace_unbroken(self):
        test_app = FastAPI()
        test_app.add_middleware(CorrelationIdMiddleware)

        trace_log = {}

        @test_app.post("/api/test/pipeline-trace")
        async def run_pipeline_endpoint():
            # 1. HTTP Hop: Correlation ID bound by middleware
            http_cid = get_correlation_id()
            assert http_cid is not None
            trace_log["http_cid"] = http_cid

            # 2. Orchestrator Hop: Market evaluation
            candles = _create_synthetic_candles(35)
            decision = sky_orchestrator.analyze_market(
                symbol="BTC/USDT",
                timeframe="15m",
                candles=candles,
                account_equity_usd=10_000.0,
            )
            trace_log["orchestrator_cid"] = decision.correlation_id
            trace_log["dossier_cid"] = decision.explanation_dossier.get("correlation_id")

            # 3. Sizer Hop: Half-Kelly position sizing
            sizing = half_kelly_position_sizer.calculate_sizing(
                account_equity=10_000.0,
                entry_price=60_000.0,
                stop_loss=59_500.0,
                take_profit=61_500.0,
                win_probability=0.60,
                symbol="BTC/USDT",
            )
            trace_log["sizer_cid"] = sizing.correlation_id

            # 4. Shadow Portfolio Hop: Virtual execution in shadow book
            pos_id = portfolio_shadow.open_position(
                symbol="BTC/USDT",
                direction="LONG",
                size=sizing.position_size_base,
                entry_price=60_000.0,
                stop_loss=59_500.0,
                take_profit=61_500.0,
                entry_reason="R2 End-to-End Correlation Trace Test",
            )
            open_positions = portfolio_shadow.get_open_positions()
            target_pos = next((p for p in open_positions if p["position_id"] == pos_id), None)
            trace_log["shadow_pos_cid"] = target_pos.get("correlation_id") if target_pos else None

            # 5. Audit Bus Hop: Event emitted and queryable by correlation_id
            audit_events = audit_bus.get_events_by_correlation_id(http_cid)
            trace_log["audit_event_count"] = len(audit_events)
            trace_log["audit_cid"] = audit_events[0].correlation_id if audit_events else None

            return {"status": "SUCCESS", "trace": trace_log}

        client = TestClient(test_app)
        target_cid = "CID-TEST-TRACE-9999-STABLE"

        response = client.post(
            "/api/test/pipeline-trace",
            headers={"X-Correlation-ID": target_cid},
        )

        assert response.status_code == 200
        # HTTP response header echoes the exact correlation ID
        assert response.headers.get("X-Correlation-ID") == target_cid

        payload = response.json()
        trace = payload["trace"]

        # Assert unbroken consistency across all 5 hops:
        assert trace["http_cid"] == target_cid, "Hop 1 (HTTP) failed correlation binding"
        assert trace["orchestrator_cid"] == target_cid, (
            "Hop 2 (Orchestrator) failed correlation propagation"
        )
        assert trace["dossier_cid"] == target_cid, "Hop 2b (Explanation Dossier) failed correlation"
        assert trace["sizer_cid"] == target_cid, "Hop 3 (Sizer) failed correlation propagation"
        assert trace["shadow_pos_cid"] == target_cid, (
            "Hop 4 (Shadow Portfolio) failed correlation persistence"
        )
        assert trace["audit_event_count"] >= 1, "Hop 5 (Audit Bus) failed to record audit event"
        assert trace["audit_cid"] == target_cid, "Hop 5 (Audit Bus) correlation ID mismatch"


class TestConcurrentContextIsolation:
    """Verifies that concurrent requests with distinct correlation IDs do not cross-contaminate."""

    def test_concurrent_async_correlation_isolation(self):
        async def worker(cid_in: str) -> tuple[str, str | None, str | None]:
            with correlation_scope(cid_in) as bound_cid:
                await asyncio.sleep(0.01)  # Context switch
                cur_cid = get_correlation_id()
                # Run sizing in context
                res = half_kelly_position_sizer.calculate_sizing(
                    account_equity=10_000.0,
                    entry_price=50_000.0,
                    stop_loss=49_000.0,
                    take_profit=52_000.0,
                    symbol="BTC/USDT",
                )
                return bound_cid, cur_cid, res.correlation_id

        async def run_all():
            tasks = [worker(f"CID-CONCURRENT-{i:03d}") for i in range(10)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_all())
        for bound_cid, cur_cid, res_cid in results:
            assert bound_cid == cur_cid, "Context leaked across concurrent coroutines"
            assert bound_cid == res_cid, "Component failed to inherit isolated coroutine context"
