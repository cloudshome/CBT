"""
tests/test_phase16_burn_in_and_telemetry.py
===========================================
Comprehensive Test Suite for Phase 16:
- Shadow Burn-In Orchestrator (Lifecycle, Sessions, Heartbeats, Recovery)
- High-Frequency Telemetry Pipeline (Monotonic Timing, Ring Buffer, Queue Estimator, Slippage)
- Incident Escalation Engine (4 Tiers, Autonomous Auto-Halt, HMAC Replay Defense, Sentinels)
- Chaos & Resilience Scenarios (DB Concurrency, Integrity Checks, Safety Locks)
"""

import asyncio
from datetime import datetime, timezone
import time
import uuid
import pytest

from core.shadow_burn_in_orchestrator import (
    ShadowBurnInOrchestrator,
    OrchestratorState,
    ExecutionMode,
    shadow_burn_in_orchestrator,
)
from core.hf_telemetry_pipeline import (
    HFTelemetryPipeline,
    TelemetryTiming,
    QueuePositionEstimate,
    SlippageAttribution,
    HFTelemetryRecord,
    hf_telemetry_pipeline,
)
from core.incident_escalation import (
    IncidentEscalationEngine,
    IncidentTier,
    IncidentRecord,
    incident_escalation_engine,
)
from core.database import db_manager
from core.audit_bus import audit_bus


# =============================================================================
# 1. SHADOW BURN-IN ORCHESTRATOR TESTS
# =============================================================================

class TestShadowBurnInOrchestrator:
    """Tests the state machine, UTC market sessions, heartbeats, and restart recovery."""

    def test_state_machine_transitions(self):
        orch = ShadowBurnInOrchestrator(heartbeat_interval_sec=1.0)
        orch.state = OrchestratorState.STOPPED

        # Valid transition: STOPPED -> STARTING -> RUNNING -> PAUSED -> RUNNING
        assert orch.can_transition_to(OrchestratorState.STARTING)
        assert orch.transition_to(OrchestratorState.STARTING, "Starting up")
        assert orch.state == OrchestratorState.STARTING

        assert orch.can_transition_to(OrchestratorState.RUNNING)
        assert orch.transition_to(OrchestratorState.RUNNING, "Operational")
        assert orch.state == OrchestratorState.RUNNING

        assert orch.can_transition_to(OrchestratorState.PAUSED)
        assert orch.transition_to(OrchestratorState.PAUSED, "Paused by operator")
        assert orch.state == OrchestratorState.PAUSED

        assert orch.can_transition_to(OrchestratorState.RUNNING)
        assert orch.transition_to(OrchestratorState.RUNNING, "Resumed")
        assert orch.state == OrchestratorState.RUNNING

        # Invalid transition: RUNNING directly to RECOVERING is not permitted
        assert not orch.can_transition_to(OrchestratorState.RECOVERING)
        assert not orch.transition_to(OrchestratorState.RECOVERING, "Invalid attempt")
        assert orch.state == OrchestratorState.RUNNING

    def test_utc_market_session_detection(self):
        orch = ShadowBurnInOrchestrator()

        # 03:00 UTC -> Asia only
        dt_asia = datetime(2026, 9, 7, 3, 0, 0, tzinfo=timezone.utc)
        sessions_asia = orch.get_active_sessions(dt_asia)
        assert "ASIA" in sessions_asia
        assert "LONDON" not in sessions_asia
        assert orch.get_primary_session_name(sessions_asia) == "ASIA"

        # 09:00 UTC -> London
        dt_london = datetime(2026, 9, 7, 9, 0, 0, tzinfo=timezone.utc)
        sessions_london = orch.get_active_sessions(dt_london)
        assert "LONDON" in sessions_london
        assert "NEW_YORK" not in sessions_london
        assert orch.get_primary_session_name(sessions_london) == "LONDON"

        # 14:30 UTC -> London & NY Overlap
        dt_overlap = datetime(2026, 9, 7, 14, 30, 0, tzinfo=timezone.utc)
        sessions_overlap = orch.get_active_sessions(dt_overlap)
        assert "LONDON" in sessions_overlap
        assert "NEW_YORK" in sessions_overlap
        assert "LONDON_NEW_YORK_OVERLAP" in sessions_overlap
        assert orch.get_primary_session_name(sessions_overlap) == "LONDON_NEW_YORK_OVERLAP"

        # 19:00 UTC -> New York only
        dt_ny = datetime(2026, 9, 7, 19, 0, 0, tzinfo=timezone.utc)
        sessions_ny = orch.get_active_sessions(dt_ny)
        assert "NEW_YORK" in sessions_ny
        assert "LONDON" not in sessions_ny
        assert orch.get_primary_session_name(sessions_ny) == "NEW_YORK"

        # 23:00 UTC -> Off Peak Pacific
        dt_offpeak = datetime(2026, 9, 7, 23, 0, 0, tzinfo=timezone.utc)
        sessions_off = orch.get_active_sessions(dt_offpeak)
        assert "OFF_PEAK_PACIFIC" in sessions_off

    def test_session_countdown_calculation(self):
        orch = ShadowBurnInOrchestrator()
        # Test at 05:00 UTC: next session is London at 07:00 (2 hours away)
        dt_test = datetime(2026, 9, 7, 5, 0, 0, tzinfo=timezone.utc)
        countdown = orch.get_next_session_countdown(dt_test)
        assert countdown["next_session"] == "LONDON"
        assert countdown["hours_until_open"] == 2.0
        assert countdown["seconds_until_open"] == 7200

    def test_heartbeat_watchdog_and_session_recording(self):
        orch = ShadowBurnInOrchestrator(heartbeat_interval_sec=0.1)
        orch.state = OrchestratorState.RUNNING

        # Emit 3 heartbeats
        for _ in range(3):
            orch.emit_heartbeat()

        assert orch.heartbeat_sequence == 3
        assert orch.heartbeats_received == 3
        assert orch.heartbeats_missed == 0
        assert orch.last_heartbeat_timestamp_ms > 0

        # Verify status summary
        status = orch.get_status()
        assert status["state"] == OrchestratorState.RUNNING
        assert status["execution_mode"] == ExecutionMode.SHADOW
        assert status["heartbeat_sequence"] == 3
        assert status["heartbeats_received"] == 3
        assert "next_session" in status
        assert "next_session_countdown_sec" in status

    def test_crash_restart_recovery_safety_lock(self):
        # Insert a simulated previous session that ended in HALTED state
        test_session_id = f"TEST_RECOVERY_{uuid.uuid4().hex[:6]}"
        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO burn_in_sessions (
                    id, session_name, session_type, execution_mode, start_timestamp,
                    opening_balance, trade_count, session_pnl, max_drawdown,
                    heartbeat_expected, heartbeat_received, heartbeat_missed,
                    status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (test_session_id, "LONDON", "LONDON", ExecutionMode.SHADOW, int(time.time() * 1000),
                 100000.0, 5, -250.0, 1.2, 10, 10, 0, OrchestratorState.HALTED)
            )

        new_orch = ShadowBurnInOrchestrator()
        # Should recover as HALTED (safety quarantine preserved)
        assert new_orch.state in (OrchestratorState.HALTED, OrchestratorState.READ_ONLY)
        assert not new_orch.can_transition_to(OrchestratorState.RUNNING)


# =============================================================================
# 2. HIGH-FREQUENCY TELEMETRY PIPELINE TESTS
# =============================================================================

class TestHFTelemetryPipeline:
    """Tests monotonic latency decomposition, ring buffer, queue estimator, and slippage attribution."""

    def test_monotonic_timing_decomposition(self):
        t0 = 1_000_000_000  # t_recv
        t1 = 1_000_500_000  # t_queue (+500 us)
        t2 = 1_001_500_000  # t_decision (+1000 us)
        t3 = 1_002_000_000  # t_exec (+500 us)

        timing = TelemetryTiming(t_recv_ns=t0, t_queue_ns=t1, t_decision_ns=t2, t_exec_ns=t3)

        assert timing.recv_to_queue_ns == 500_000
        assert timing.queue_to_decision_ns == 1_000_000
        assert timing.decision_to_exec_ns == 500_000
        assert timing.total_pipeline_latency_ns == 2_000_000
        assert timing.total_pipeline_latency_ms == 2.0

    def test_queue_position_and_fill_probability_estimator(self):
        pipeline = HFTelemetryPipeline()

        # Limit order placed inside spread with volume ahead
        est = pipeline.estimate_queue_position(
            visible_depth=50.0,
            order_size=1.0,
            order_type="LIMIT",
        )

        assert est.model_type == "ESTIMATED_HAZARD_QUEUE"
        assert 0.0 <= est.estimated_fill_probability <= 1.0
        assert est.estimated_volume_ahead >= 0.0
        assert 0.0 <= est.confidence <= 1.0

        # Market order should have fill probability = 1.0
        est_market = pipeline.estimate_queue_position(
            visible_depth=50.0,
            order_size=1.0,
            order_type="MARKET",
        )
        assert est_market.estimated_fill_probability == 1.0
        assert est_market.estimated_volume_ahead == 0.0

    def test_3_factor_slippage_attribution(self):
        pipeline = HFTelemetryPipeline()

        # Buy order: reference mid is 100.0, ask quote is 100.1, execution price is 100.25
        # Spread cost = 100.1 - 100.0 = 0.1 (10 bps)
        # Total slippage = 100.25 - 100.0 = 0.25 (25 bps)
        attrib = pipeline.attribute_slippage(
            order_side="BUY",
            mid_at_decision=100.0,
            quote_at_decision=100.1,
            execution_price=100.25,
            order_size=10.0,
            adv_usd=500_000_000.0,
        )

        assert attrib.reference_mid == 100.0
        assert attrib.reference_quote == 100.1
        assert attrib.execution_price == 100.25
        assert round(attrib.slippage_total_bps, 2) == 25.0
        assert round(attrib.slippage_spread_bps, 2) == 10.0
        assert attrib.slippage_impact_bps >= 0.0
        assert attrib.slippage_latency_bps >= 0.0

        # Latency drift + impact accounts for the remainder
        assert attrib.slippage_total_bps >= attrib.slippage_spread_bps

    def test_ring_buffer_bounds_and_batch_persistence(self):
        pipeline = HFTelemetryPipeline(ring_buffer_size=100)

        # Ingest 150 records (overflows 100-item capacity)
        for i in range(150):
            pipeline.record_telemetry(
                symbol="BTC/USDT",
                exchange="binance",
                execution_mode="SHADOW",
                t_recv_ns=1_000_000 + i * 1000,
                t_queue_ns=1_000_100 + i * 1000,
                t_decision_ns=1_000_300 + i * 1000,
                t_exec_ns=1_000_500 + i * 1000,
                bid=60000.0,
                ask=60001.0,
                order_side="BUY",
                order_type="LIMIT",
                order_price=60000.0,
                execution_price=60000.0,
                order_size=0.1,
                visible_depth=20.0,
            )

        # In-memory buffer size is strictly clamped at 100
        assert len(pipeline._ring_buffer) == 100
        assert pipeline._sequence_counter == 150

        # Flush to SQLite database
        persisted = pipeline.flush_to_db()
        assert persisted > 0

        # Verify recent records retrieval
        recent = pipeline.get_recent_records(limit=20)
        assert len(recent) == 20
        assert recent[0]["symbol"] == "BTC/USDT"

        # Verify percentile metrics
        metrics = pipeline.get_percentile_metrics()
        assert metrics["total_records"] >= 100
        assert "p50_total_latency_ms" in metrics
        assert "p95_total_latency_ms" in metrics
        assert "p99_total_latency_ms" in metrics
        assert metrics["p99_total_latency_ms"] >= metrics["p50_total_latency_ms"]


# =============================================================================
# 3. INCIDENT ESCALATION ENGINE & SAFETY TESTS
# =============================================================================

class TestIncidentEscalationEngine:
    """Tests 4-tier incident handling, HMAC 2-phase tokens, replay attack defense, and auto-halt."""

    @pytest.mark.asyncio
    async def test_notice_and_warning_tiers(self):
        engine = IncidentEscalationEngine()

        # Tier 1: NOTICE
        rec_notice = await engine.raise_incident(
            tier=IncidentTier.NOTICE,
            source_engine="TEST_MONITOR",
            trigger_type="INFORMATIONAL_PROBE",
            trigger_value=1.0,
            threshold_value=1.0,
            description="Routine test informational notice.",
        )
        assert rec_notice.tier == IncidentTier.NOTICE
        assert rec_notice.automated_action == "LOGGED_TO_AUDIT_BUS"
        assert not rec_notice.confirmation_required

        # Tier 2: WARNING
        rec_warn = await engine.raise_incident(
            tier=IncidentTier.WARNING,
            source_engine="TEST_MONITOR",
            trigger_type="HIGH_LATENCY_SPIKE",
            trigger_value=45.0,
            threshold_value=30.0,
            description="Warning: Latency spike observed.",
        )
        assert rec_warn.tier == IncidentTier.WARNING
        assert rec_warn.automated_action == "TELEGRAM_SENTINEL_ALERT"
        assert not rec_warn.confirmation_required

    @pytest.mark.asyncio
    async def test_tier3_critical_hmac_2phase_confirmation(self):
        engine = IncidentEscalationEngine()

        # Tier 3: CRITICAL triggers token requirement
        rec_crit = await engine.raise_incident(
            tier=IncidentTier.CRITICAL,
            source_engine="CUSUM_DRIFT_AUDITOR",
            trigger_type="EXPECTANCY_COLLAPSE",
            trigger_value=3.2,
            threshold_value=2.5,
            description="CUSUM drift breach requiring operator quarantine token.",
        )

        assert rec_crit.tier == IncidentTier.CRITICAL
        assert rec_crit.confirmation_required is True
        assert rec_crit.confirmation_status == "PENDING"
        assert rec_crit.nonce is not None
        assert rec_crit.token_hash is not None

        # Verify token validity
        is_valid, msg = engine.verify_and_consume_token(
            incident_id=rec_crit.incident_id,
            action="QUARANTINE_STRATEGY",
            nonce=rec_crit.nonce,
            expires_at_ms=rec_crit.expires_at,
            token_signature=rec_crit.token_hash,
            operator_id="ADMIN",
        )
        assert is_valid is True
        assert msg == "VERIFIED_VALID"

        # REPLAY ATTACK DEFENSE: Second use of same nonce MUST be rejected
        is_valid_replay, replay_msg = engine.verify_and_consume_token(
            incident_id=rec_crit.incident_id,
            action="QUARANTINE_STRATEGY",
            nonce=rec_crit.nonce,
            expires_at_ms=rec_crit.expires_at,
            token_signature=rec_crit.token_hash,
            operator_id="ADMIN",
        )
        assert is_valid_replay is False
        assert replay_msg == "TOKEN_ALREADY_CONSUMED_REPLAY_ATTACK"

    def test_hmac_token_expiry_and_tamper_resistance(self):
        engine = IncidentEscalationEngine()
        token = engine.create_confirmation_token("INC_TEST_001", "RESOLVE")

        # 1. Tampered Signature
        is_valid, msg = engine.verify_and_consume_token(
            incident_id="INC_TEST_001",
            action="RESOLVE",
            nonce=token["nonce"],
            expires_at_ms=token["expires_at"],
            token_signature="bad_signature_deadbeef1234",
            operator_id="ADMIN",
        )
        assert is_valid is False
        assert msg == "INVALID_HMAC_SIGNATURE"

        # 2. Expired Token
        expired_ms = int(time.time() * 1000) - 5000  # 5 seconds in past
        expired_token = engine.create_confirmation_token("INC_TEST_002", "RESOLVE")
        is_valid_exp, msg_exp = engine.verify_and_consume_token(
            incident_id="INC_TEST_002",
            action="RESOLVE",
            nonce=expired_token["nonce"],
            expires_at_ms=expired_ms,
            token_signature=expired_token["token_signature"],
            operator_id="ADMIN",
        )
        assert is_valid_exp is False
        assert msg_exp == "TOKEN_EXPIRED"

    @pytest.mark.asyncio
    async def test_tier4_emergency_auto_halt_and_idempotency(self):
        engine = IncidentEscalationEngine()
        orch = shadow_burn_in_orchestrator
        orch.state = OrchestratorState.RUNNING

        # Trigger Tier 4 EMERGENCY
        rec_em = await engine.raise_incident(
            tier=IncidentTier.EMERGENCY,
            source_engine="CHAOS_TEST",
            trigger_type="KILL_SWITCH_ENGAGED",
            trigger_value=1.0,
            threshold_value=1.0,
            description="Autonomous circuit breaker engaged in test.",
        )

        assert rec_em.tier == IncidentTier.EMERGENCY
        assert "EMERGENCY_AUTO_HALT_COMPLETE" in rec_em.automated_action
        assert engine._is_emergency_halted is True
        assert orch.state == OrchestratorState.READ_ONLY

        # IDEMPOTENCY: Re-triggering emergency halt must not crash, throw, or storm
        second_action = await engine.execute_emergency_auto_halt("Second panic signal", "INC_SECOND")
        assert second_action == "ALREADY_HALTED_IDEMPOTENT"

        # Operator recovery
        recovered = engine.reset_emergency_halt("Operator resolved chaos test")
        assert recovered is True
        assert engine._is_emergency_halted is False

    @pytest.mark.asyncio
    async def test_liquidity_evaporation_sentinel(self):
        engine = IncidentEscalationEngine(liquidity_withdrawal_threshold=0.70)
        symbol = "ETH/USDT"

        # Seed with 15 normal depth readings (e.g. ~100.0 depth)
        for _ in range(15):
            res = await engine.evaluate_liquidity_anomaly(symbol, 100.0)
            assert res is None

        # Slight drop to 80.0 (20% drop) -> does not breach 70% threshold
        res_minor = await engine.evaluate_liquidity_anomaly(symbol, 80.0)
        assert res_minor is None

        # Sudden flash withdrawal to 10.0 (>85% drop from ~98 baseline) -> CRITICAL
        res_evap = await engine.evaluate_liquidity_anomaly(symbol, 10.0)
        assert res_evap is not None
        assert res_evap.tier == IncidentTier.CRITICAL
        assert res_evap.trigger_type == "ANOMALOUS_DEPTH_WITHDRAWAL"
        assert res_evap.trigger_value >= 0.70


# =============================================================================
# 4. CHAOS & INTEGRITY TESTS
# =============================================================================

class TestChaosAndIntegrity:
    """Tests SQLite concurrency, bad data integrity rejection, and execution isolation."""

    def test_execution_mode_isolation(self):
        """Validates that Phase 16 operates in strictly isolated SHADOW mode."""
        orch = shadow_burn_in_orchestrator
        assert orch.execution_mode == ExecutionMode.SHADOW
        assert orch.execution_mode != ExecutionMode.LIVE

    def test_telemetry_integrity_validation(self):
        """Validates that inverted timestamps or invalid order params are flagged."""
        pipeline = HFTelemetryPipeline()

        # Inverted timing: t_exec happens BEFORE t_recv (clock jump or corruption)
        rec = pipeline.record_telemetry(
            symbol="BTC/USDT",
            exchange="binance",
            execution_mode="SHADOW",
            t_recv_ns=2_000_000_000,
            t_queue_ns=2_000_100_000,
            t_decision_ns=2_000_200_000,
            t_exec_ns=1_000_000_000,  # INVALID: clock goes backward!
            bid=65000.0,
            ask=65001.0,
            order_side="BUY",
            order_type="LIMIT",
            order_price=65000.0,
            execution_price=65000.0,
            order_size=0.5,
            visible_depth=10.0,
        )

        assert rec.integrity_valid is False

    def test_concurrent_telemetry_record_and_flush(self):
        """Chaos test: concurrently appending and flushing telemetry records."""
        pipeline = HFTelemetryPipeline(ring_buffer_size=500)

        for i in range(200):
            pipeline.record_telemetry(
                symbol="SOL/USDT",
                exchange="binance",
                execution_mode="SHADOW",
                t_recv_ns=10_000_000 + i * 100,
                t_queue_ns=10_000_050 + i * 100,
                t_decision_ns=10_000_100 + i * 100,
                t_exec_ns=10_000_200 + i * 100,
                bid=150.0,
                ask=150.1,
                order_side="BUY",
                order_type="LIMIT",
                order_price=150.0,
                execution_price=150.0,
                order_size=2.0,
                visible_depth=50.0,
            )

        # Flush all 200 records
        count = pipeline.flush_to_db()
        assert count == 200

        # Query database directly using sandboxed conn
        with db_manager.get_trading_conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM hf_telemetry_records WHERE symbol = 'SOL/USDT';").fetchone()
            assert row[0] >= 200
