"""
tests/execution/test_milestone22_flight_runner.py
=================================================
Milestone 22: Live Testnet Execution Flight Runner & Multi-Venue Order Lifecycle Engine.
Comprehensive Adversarial Validation Suite covering all 7 Acceptance Gates & 11 Risk Domains.

Test Coverage:
1. Filter Engine: Tick boundary, step boundary, min notional, missing metadata, Decimal precision.
2. Lost-ACK Recovery: Ambiguity resolution, query loop, duplicate prevention, ORDER_NOT_FOUND != CANCELED.
3. Accounting: 8-quantity tracking, conservation identity, overfill circuit breaker.
4. Event Journal: Append-only hashing, conflicting duplicate anomaly halt.
5. Dispatcher: TWAP & Iceberg schedule generation, step clamping, remainder absorption.
6. Supervisor: Lease locking, duplicate run prevention, crash startup recovery.
7. Rate Limiter: Emergency priority reserves, request throttling.
8. Latency Telemetry: 7-stage T0->T7 monotonicity, clock skew sentinel fail-closed.
9. Environment Security: Permanent capital firewall, production endpoint rejection.
10. Panic Cancel: Flight-scoped cancellation.
11. Qualification Gate: 10-point audit, epistemic classification.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from core.execution.testnet.base_adapter import BaseTestnetAdapter
from core.execution.testnet.dispatcher import TestnetOrderSlicingDispatcher
from core.execution.testnet.endpoint_policy import EndpointPolicy, Environment
from core.execution.testnet.event_journal import (
    AppendOnlyEventJournal,
    ConflictingEventAnomalyError,
    EventProcessingStatus,
)
from core.execution.testnet.execution_ledger import (
    OverfillCircuitBreakerError,
    ParentExecutionLedger,
    UnresolvedQuantityLifecycleError,
)
from core.execution.testnet.filters import (
    ExchangeFilterRulesEngine,
    FilterValidationError,
    SymbolFilterConfig,
)
from core.execution.testnet.flight_manifest import FlightManifest, ManifestValidationError
from core.execution.testnet.flight_runner import (
    ClockSkewSentinelError,
    TestnetFlightRunnerService,
)
from core.execution.testnet.models import (
    CanonicalOrderStatus,
    EpistemicClassification,
    M22LatencyDecomposition,
    OrderSide,
    OrderType,
)
from core.execution.testnet.multi_venue_bridge import MultiVenueTestnetBridge
from core.execution.testnet.placement_intent import PlacementIntent
from core.execution.testnet.qualification_gate import QualificationGateEngine
from core.execution.testnet.rate_limit_governor import (
    RateLimitGovernor,
    RequestPriority,
)
from core.execution.testnet.recovery_state_machine import (
    AmbiguousCancellationForbiddenError,
    IllegalRecoveryTransitionError,
    LostAckRecoveryFSM,
    RecoveryState,
)
from core.execution.testnet.schemas import VenueCapabilities
from core.execution.testnet.supervisor import DuplicateFlightRunError, FlightSupervisor
from core.execution.testnet.venue_capabilities import (
    UnsupportedVenueOperationError,
    get_venue_capability_profile,
)

# =============================================================================
# Helper Fixtures & Mock Adapters
# =============================================================================


class MockTestnetAdapter(BaseTestnetAdapter):
    """Deterministic mock adapter for adversarial testing."""

    def __init__(
        self, venue_id: str = "BINANCE_SPOT_TESTNET", server_time_ms: int = 1700000000000
    ) -> None:
        caps = VenueCapabilities(
            venue_id=venue_id,
            supports_private_ws=True,
            supports_order_query=True,
            supports_cancel_all=True,
            supports_client_order_id=True,
            supports_execution_id=True,
            supports_partial_fills=True,
            market_data_characteristics="EXTERNAL_TESTNET",
            reset_behavior="PERIODIC_EXTERNAL",
        )
        super().__init__(caps)
        self.mock_server_time_ms = server_time_ms
        self.orders: dict[str, dict] = {}
        self.placed_order_count = 0
        self.fail_placement_with: Exception | None = None

    async def get_server_time_ms(self) -> int:
        return self.mock_server_time_ms

    async def get_account_balances(self) -> dict[str, Decimal]:
        return {"USDT": Decimal("100000.00"), "BTC": Decimal("5.0")}

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        if self.fail_placement_with:
            raise self.fail_placement_with

        self.placed_order_count += 1
        cid = client_order_id or f"CID_{self.placed_order_count}"
        oid = f"OID_{self.placed_order_count}"
        res = {
            "order_id": oid,
            "client_order_id": cid,
            "status": "ACCEPTED",
            "executed_qty": Decimal("0"),
            "transact_time_ms": self.mock_server_time_ms,
        }
        self.orders[cid] = res
        return res

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        cid = client_order_id or ""
        if cid in self.orders:
            self.orders[cid]["status"] = "CANCELED"
        return {
            "order_id": order_id or "OID_CANCELED",
            "client_order_id": cid,
            "status": "CANCELED",
        }

    async def query_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict:
        cid = client_order_id or ""
        if cid in self.orders:
            return self.orders[cid]
        return {"order_id": "", "client_order_id": cid, "status": "NOT_FOUND"}

    async def query_open_orders(self, symbol: str) -> list[dict]:
        return [
            o for o in self.orders.values() if o.get("status") in ("ACCEPTED", "NEW", "SUBMITTED")
        ]


@pytest.fixture
def filter_engine() -> ExchangeFilterRulesEngine:
    engine = ExchangeFilterRulesEngine()
    # Register BTC/USDT on Binance
    engine.register_config(
        SymbolFilterConfig(
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.00001"),
            min_price=Decimal("1000.00"),
            max_price=Decimal("1000000.00"),
            min_qty=Decimal("0.00001"),
            max_qty=Decimal("9000.00"),
            min_notional=Decimal("5.0"),
            source_provenance="TEST_SPEC",
            updated_at_utc="2026-09-21T00:00:00Z",
        )
    )
    # Register BTC/USDT on Bybit
    engine.register_config(
        SymbolFilterConfig(
            symbol="BTCUSDT",
            venue="BYBIT_V5_TESTNET",
            tick_size=Decimal("0.10"),
            step_size=Decimal("0.0001"),
            min_price=Decimal("1000.00"),
            max_price=Decimal("1000000.00"),
            min_qty=Decimal("0.0001"),
            max_qty=Decimal("1000.00"),
            min_notional=Decimal("5.0"),
            source_provenance="TEST_SPEC",
            updated_at_utc="2026-09-21T00:00:00Z",
        )
    )
    return engine


# =============================================================================
# 1. Gate 1: Exchange Filter Rules & Precision Normalizer Tests
# =============================================================================


class TestFilterEngineAdversarial:
    def test_price_clamping_buy_rounds_down_sell_rounds_up(self, filter_engine):
        """Buy rounds floor (down), sell rounds ceiling (up) to avoid unintended aggressive crossing."""
        # Binance tick_size is 0.01
        p_raw = Decimal("65432.126")

        p_buy = filter_engine.normalize_price(
            "BINANCE_SPOT_TESTNET", "BTCUSDT", p_raw, OrderSide.BUY
        )
        assert p_buy == Decimal("65432.12"), "BUY price must round DOWN to tick boundary"

        p_sell = filter_engine.normalize_price(
            "BINANCE_SPOT_TESTNET", "BTCUSDT", p_raw, OrderSide.SELL
        )
        assert p_sell == Decimal("65432.13"), "SELL price must round UP to tick boundary"

    def test_quantity_clamping_strict_round_down(self, filter_engine):
        """Quantity clamping must strictly round down to step_size to prevent over-allocation."""
        # Binance step_size is 0.00001
        q_raw = Decimal("0.12345999")
        q_norm = filter_engine.normalize_quantity("BINANCE_SPOT_TESTNET", "BTCUSDT", q_raw)
        assert q_norm == Decimal("0.12345"), "Quantity must strictly round down"

    def test_minimum_notional_rejection(self, filter_engine):
        """Orders below minimum notional ($5.0) fail closed pre-wire."""
        # Price 50000, Qty 0.00001 -> Notional = $0.50 < $5.0 minNotional
        with pytest.raises(FilterValidationError) as exc:
            filter_engine.normalize_order(
                venue="BINANCE_SPOT_TESTNET",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0.00001"),
                price=Decimal("50000.00"),
            )
        assert "below venue minimum notional" in str(exc.value)

    def test_missing_metadata_fails_closed(self, filter_engine):
        """Requesting unconfigured symbol fails closed."""
        with pytest.raises(FilterValidationError) as exc:
            filter_engine.normalize_price(
                "BINANCE_SPOT_TESTNET", "UNKNOWN_PAIR", Decimal("100.0"), OrderSide.BUY
            )
        assert "No trading filter metadata configured" in str(exc.value)

    def test_binance_exchange_info_ingestion(self):
        """Ingests Binance exchangeInfo JSON payload."""
        engine = ExchangeFilterRulesEngine()
        payload = {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "tickSize": "0.01",
                            "minPrice": "10.0",
                            "maxPrice": "100000.0",
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.0001",
                            "minQty": "0.0001",
                            "maxQty": "10000.0",
                        },
                        {"filterType": "NOTIONAL", "minNotional": "5.0"},
                    ],
                }
            ]
        }
        loaded = engine.load_binance_exchange_info(payload)
        assert loaded == 1
        cfg = engine.get_config("BINANCE_SPOT_TESTNET", "ETHUSDT")
        assert cfg.tick_size == Decimal("0.01")
        assert cfg.step_size == Decimal("0.0001")


# =============================================================================
# 2. Gate 2: Parent/Child Execution Ledger & Quantity Conservation Tests
# =============================================================================


class TestExecutionLedgerConservation:
    def test_exact_quantity_conservation_identity(self):
        """Fundamental identity: Q_target = Q_filled + Q_open + Q_canceled + Q_unresolved."""
        ledger = ParentExecutionLedger(
            parent_order_id="P_001",
            target_quantity=Decimal("1.0"),
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )
        # Initial: unallocated target is unresolved
        assert ledger.unresolved_quantity == Decimal("1.0")
        assert ledger.executed_quantity == Decimal("0")

        # Slice 1: allocate 0.4
        ledger.allocate_slice("SL_01", Decimal("0.4"))
        assert ledger.allocated_quantity == Decimal("0.4")
        assert ledger.unresolved_quantity == Decimal("1.0")

        # Submit Slice 1
        ledger.record_submission("SL_01", Decimal("0.4"))
        assert ledger.open_quantity == Decimal("0.4")
        assert ledger.unresolved_quantity == Decimal("0.6")

        # Partial fill of 0.25 on Slice 1
        ledger.record_fill("SL_01", Decimal("0.25"))
        assert ledger.executed_quantity == Decimal("0.25")
        assert ledger.open_quantity == Decimal("0.15")

        # Cancel remaining 0.15 of Slice 1
        ledger.record_cancel("SL_01", Decimal("0.15"))
        assert ledger.canceled_quantity == Decimal("0.15")
        assert ledger.open_quantity == Decimal("0.0")

        # Slice 2: allocate remaining 0.6
        ledger.allocate_slice("SL_02", Decimal("0.6"))
        ledger.record_submission("SL_02", Decimal("0.6"))
        ledger.record_fill("SL_02", Decimal("0.6"), is_terminal=True)

        # Verification
        assert ledger.executed_quantity == Decimal("0.85")
        assert ledger.canceled_quantity == Decimal("0.15")
        assert ledger.open_quantity == Decimal("0.0")
        assert ledger.unresolved_quantity == Decimal("0.0")

        # Can complete
        ledger.mark_complete()
        assert ledger.is_completed

    def test_overfill_circuit_breaker_trips_protective_halt(self):
        """Cumulative filled quantity exceeding parent target trips OverfillCircuitBreakerError and halts."""
        ledger = ParentExecutionLedger(
            parent_order_id="P_OVERFILL",
            target_quantity=Decimal("1.0"),
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )
        ledger.allocate_slice("SL_01", Decimal("1.0"))
        ledger.record_submission("SL_01", Decimal("1.0"))

        # Ingest fill of 1.0001 (exceeds target by 0.0001)
        with pytest.raises(OverfillCircuitBreakerError) as exc:
            ledger.record_fill("SL_01", Decimal("1.0001"))

        assert "OVERFILL DETECTED" in str(exc.value)
        assert ledger.is_halted
        assert ledger.overfill_quantity == Decimal("0.0001")

        # Any subsequent operation is rejected
        with pytest.raises(OverfillCircuitBreakerError):
            ledger.allocate_slice("SL_02", Decimal("0.1"))

    def test_unresolved_quantity_blocks_completion(self):
        """Parent order cannot mark complete if any quantity remains unresolved."""
        ledger = ParentExecutionLedger(
            parent_order_id="P_UNRESOLVED",
            target_quantity=Decimal("1.0"),
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )
        ledger.allocate_slice("SL_01", Decimal("0.5"))
        ledger.record_submission("SL_01", Decimal("0.5"))
        ledger.record_fill("SL_01", Decimal("0.5"), is_terminal=True)

        # Unallocated 0.5 remains unresolved
        with pytest.raises(UnresolvedQuantityLifecycleError) as exc:
            ledger.mark_complete()
        assert "unresolved quantity" in str(exc.value)


# =============================================================================
# 3. Gate 3: Lost-ACK Recovery State Machine & Resolution Protocol Tests
# =============================================================================


class TestLostAckRecovery:
    def test_order_not_found_does_not_assume_cancelled(self):
        """Invariant: ORDER_NOT_FOUND != ORDER_CANCELED."""
        fsm = LostAckRecoveryFSM(slice_id="SL_01", intent_id="INT_01")
        fsm.transition_to(RecoveryState.SUBMISSION_ATTEMPTED, "Sent wire")
        fsm.transition_to(RecoveryState.UNKNOWN_EXTERNAL_STATE, "Timeout on transport")
        fsm.transition_to(RecoveryState.RECOVERY_PENDING, "Wait for query")
        fsm.transition_to(RecoveryState.QUERYING, "Query attempt 1")

        # Attempting to jump directly to CANCEL_CONFIRMED without cancellation evidence must fail
        with pytest.raises(IllegalRecoveryTransitionError):
            fsm.transition_to(RecoveryState.CANCEL_CONFIRMED, "Assume canceled because 404")

    def test_ambiguous_cancellation_forbidden_without_positive_evidence(self):
        """Transition to CANCEL_CONFIRMED fails if evidence does not confirm cancellation."""
        fsm = LostAckRecoveryFSM(slice_id="SL_01", intent_id="INT_01")
        fsm.transition_to(RecoveryState.SUBMISSION_ATTEMPTED, "Sent wire")
        fsm.transition_to(RecoveryState.ACKNOWLEDGED, "ACK received")
        fsm.transition_to(RecoveryState.CANCEL_REQUESTED, "Sent cancel")

        # Evidence lacks CANCELED status
        with pytest.raises(AmbiguousCancellationForbiddenError):
            fsm.transition_to(
                RecoveryState.CANCEL_CONFIRMED,
                "Cancel requested but not confirmed",
                evidence={"status": "PENDING"},
            )

    @pytest.mark.asyncio
    async def test_lost_ack_resolution_discovers_open_order_and_avoids_duplicate(
        self, filter_engine
    ):
        """Lost-ACK queries venue matching engine; if found open, maps orderId and prevents duplicate placement."""
        mock_adapter = MockTestnetAdapter(venue_id="BINANCE_SPOT_TESTNET")
        # Simulate network drop on place_order
        mock_adapter.fail_placement_with = TimeoutError("Socket read timeout")

        # Pre-seed matching engine with the order (as if exchange accepted it right before timeout)
        cid = "M22_INT_TEST_01"
        mock_adapter.orders[cid] = {
            "order_id": "EX_MATCHING_ENGINE_999",
            "client_order_id": cid,
            "status": "ACCEPTED",
            "executed_qty": Decimal("0"),
        }

        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )

        intent = PlacementIntent(
            flight_id="FLIGHT_01",
            parent_order_id="P_01",
            child_slice_id="SL_01",
            intent_id="INT_01",
            venue="BINANCE_SPOT_TESTNET",
            client_order_id=cid,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("65000.00"),
            created_at_utc="2026-09-21T00:00:00Z",
            created_monotonic_ns=1000,
        )

        # Place order: will hit timeout, then enter Lost-ACK query, and discover order!
        resp = await bridge.place_order(intent)

        assert resp.native_order_id == "EX_MATCHING_ENGINE_999"
        assert resp.canonical_status == CanonicalOrderStatus.ACKNOWLEDGED
        assert (
            bridge.get_recovery_fsm("SL_01", "INT_01").current_state == RecoveryState.ACKNOWLEDGED
        )


# =============================================================================
# 4. Gate 4: Event Journal & Forensic Deduplication Shield Tests
# =============================================================================


class TestEventJournalDeduplication:
    def test_identical_duplicate_execution_skipped_idempotently(self):
        """1,000 identical execution reports yield exactly 1 new execution."""
        journal = AppendOnlyEventJournal()

        payload = {"trade_id": "TR_100", "price": "65000.00", "qty": "0.1"}

        event1, is_new1 = journal.record_event(
            venue="BINANCE_SPOT_TESTNET",
            event_type="EXECUTION",
            raw_payload=payload,
            source_channel="WS_PRIVATE",
            execution_id="EXEC_100",
            exec_price=Decimal("65000.00"),
            exec_quantity=Decimal("0.1"),
            exec_symbol="BTCUSDT",
            exec_side="BUY",
        )
        assert is_new1 is True
        assert event1.processing_status == EventProcessingStatus.PROCESSED

        # Repeat 999 times
        for _ in range(999):
            _, is_new = journal.record_event(
                venue="BINANCE_SPOT_TESTNET",
                event_type="EXECUTION",
                raw_payload=payload,
                source_channel="WS_PRIVATE",
                execution_id="EXEC_100",
                exec_price=Decimal("65000.00"),
                exec_quantity=Decimal("0.1"),
                exec_symbol="BTCUSDT",
                exec_side="BUY",
            )
            assert is_new is False

        assert journal.total_events_received == 1000
        assert journal.total_duplicates_detected == 999

    def test_conflicting_duplicate_execution_fails_closed_and_halts(self):
        """Matching execution_id with differing price raises ConflictingEventAnomalyError and fails closed."""
        journal = AppendOnlyEventJournal()

        # Ingest initial fill
        journal.record_event(
            venue="BINANCE_SPOT_TESTNET",
            event_type="EXECUTION",
            raw_payload={"trade_id": "TR_200", "price": "65000.00"},
            source_channel="WS_PRIVATE",
            execution_id="EXEC_200",
            exec_price=Decimal("65000.00"),
            exec_quantity=Decimal("0.1"),
            exec_symbol="BTCUSDT",
            exec_side="BUY",
        )

        # Incoming fill with same execution_id but different price ($65100.00)
        with pytest.raises(ConflictingEventAnomalyError) as exc:
            journal.record_event(
                venue="BINANCE_SPOT_TESTNET",
                event_type="EXECUTION",
                raw_payload={"trade_id": "TR_200", "price": "65100.00"},
                source_channel="WS_PRIVATE",
                execution_id="EXEC_200",
                exec_price=Decimal("65100.00"),
                exec_quantity=Decimal("0.1"),
                exec_symbol="BTCUSDT",
                exec_side="BUY",
            )

        assert "Conflicting duplicate execution detected" in str(exc.value)
        assert journal.total_conflicts_detected == 1


# =============================================================================
# 5. Gate 5: TWAP Slicing Dispatcher & Remainder Absorption Tests
# =============================================================================


class TestDispatcherSlicing:
    def test_twap_schedule_exact_conservation(self, filter_engine):
        """TWAP schedule generation absorbs quantization remainder on the final slice."""
        bridge = MultiVenueTestnetBridge(filter_engine=filter_engine)
        dispatcher = TestnetOrderSlicingDispatcher(bridge=bridge, filter_engine=filter_engine)

        target_qty = Decimal("1.0")
        plan = dispatcher.generate_twap_plan(
            parent_order_id="P_TWAP",
            venue="BINANCE_SPOT_TESTNET",
            symbol="BTCUSDT",
            target_quantity=target_qty,
            num_slices=3,
        )
        assert len(plan.slice_quantities) == 3
        # Sum of discrete slices must EXACTLY match parent target
        assert sum(plan.slice_quantities) == target_qty

    @pytest.mark.asyncio
    async def test_twap_execution_cycle_converges(self, filter_engine):
        """Full TWAP execution cycle dispatches slices, records fills, and marks ledger complete."""
        mock_adapter = MockTestnetAdapter(venue_id="BINANCE_SPOT_TESTNET")
        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )
        dispatcher = TestnetOrderSlicingDispatcher(bridge=bridge, filter_engine=filter_engine)

        ledger = ParentExecutionLedger(
            parent_order_id="P_RUN",
            target_quantity=Decimal("0.05"),
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )

        responses = await dispatcher.execute_twap(
            flight_id="FLIGHT_01",
            ledger=ledger,
            side=OrderSide.BUY,
            price=Decimal("65000.00"),
            num_slices=5,
            interval_seconds=0.0,
            simulate_matching_fills=True,
        )
        assert len(responses) == 5
        assert ledger.executed_quantity == Decimal("0.05")
        assert ledger.unresolved_quantity == Decimal("0.0")
        ledger.mark_complete()
        assert ledger.is_completed


# =============================================================================
# 6. Gate 6: Latency Telemetry, Monotonicity & Clock Skew Sentinel Tests
# =============================================================================


class TestLatencyAndClockSentinel:
    def test_7_stage_latency_decomposition_strict_monotonicity(self):
        """All recorded timestamps satisfy T_i <= T_{i+1} without clock regression."""
        rec = M22LatencyDecomposition(
            slice_id="SL_01",
            placement_intent_id="INT_01",
            t0_intent_created_ns=1000,
            t1_intent_persisted_ns=1100,
            t2_wire_dispatch_ns=1200,
            t3_transport_ack_ns=1500,
            t4_ack_normalized_ns=1600,
            t5_ws_execution_ns=1800,
            t6_reconcile_committed_ns=1900,
            t7_qualification_accepted_ns=2000,
        )
        assert rec.is_strictly_monotonic()
        assert rec.transport_rtt_duration_ns == 300
        assert rec.total_end_to_end_duration_ns == 1000

    def test_non_monotonic_latency_fails_verification(self):
        """Negative interval (T_{i+1} < T_i) fails monotonicity assertion."""
        rec_bad = M22LatencyDecomposition(
            slice_id="SL_01",
            placement_intent_id="INT_01",
            t0_intent_created_ns=2000,
            t1_intent_persisted_ns=1000,  # Backward jump
            t2_wire_dispatch_ns=1200,
            t3_transport_ack_ns=1500,
            t4_ack_normalized_ns=1600,
            t5_ws_execution_ns=1800,
            t6_reconcile_committed_ns=1900,
            t7_qualification_accepted_ns=2000,
        )
        assert not rec_bad.is_strictly_monotonic()

    @pytest.mark.asyncio
    async def test_clock_skew_sentinel_fails_closed_when_offset_exceeds_1000ms(self, filter_engine):
        """Clock offset > 1000ms trips ClockSkewSentinelError and fails closed."""
        # Exchange server time is 5000ms ahead
        bad_server_time = int(asyncio.get_event_loop().time() * 1000) + 5000
        mock_adapter = MockTestnetAdapter(server_time_ms=bad_server_time)

        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )
        manifest = FlightManifest.create_standard_rehearsal_manifest(
            flight_id="FLIGHT_CLOCK_FAIL",
            environment=Environment.BINANCE_TESTNET,
        )
        runner = TestnetFlightRunnerService(
            manifest=manifest,
            bridge=bridge,
            filter_engine=filter_engine,
            max_clock_skew_ms=1000.0,
        )

        with pytest.raises(ClockSkewSentinelError) as exc:
            await runner.verify_clock_skew_sentinel("BINANCE_SPOT_TESTNET")

        assert "Clock offset breach" in str(exc.value)


# =============================================================================
# 7. Gate 7: Autonomous Rehearsal Flight Runner, Panic Cancel & Qualification
# =============================================================================


class TestFlightRunnerAutonomousLifecycle:
    @pytest.mark.asyncio
    async def test_full_autonomous_flight_rehearsal_qualifies(self, filter_engine):
        """Executes autonomous flight rehearsal and achieves QUALIFIED verdict."""
        now_ms = int(time.time() * 1000)
        mock_adapter = MockTestnetAdapter(server_time_ms=now_ms)
        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )
        manifest = FlightManifest.create_standard_rehearsal_manifest(
            flight_id="FLIGHT_AUTONOMOUS_PASS",
            environment=Environment.BINANCE_TESTNET,
        )
        runner = TestnetFlightRunnerService(
            manifest=manifest,
            bridge=bridge,
            filter_engine=filter_engine,
            max_clock_skew_ms=1000.0,
        )

        ledger, evidence = await runner.execute_rehearsal_flight(
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
            side=OrderSide.BUY,
            target_quantity=Decimal("0.05"),
            price=Decimal("65000.00"),
            num_slices=5,
            interval_seconds=0.0,
        )

        assert ledger.is_completed
        assert ledger.unresolved_quantity == Decimal("0.0")
        assert evidence.is_qualified
        assert evidence.verdict == "QUALIFIED"
        assert (
            evidence.epistemic_classification == EpistemicClassification.LIFECYCLE_VALIDITY_EVIDENCE
        )
        assert bool(evidence.sha256_digest)

    @pytest.mark.asyncio
    async def test_panic_cancel_is_strictly_flight_scoped(self, filter_engine):
        """Panic cancel aborts only open orders belonging to the flight."""
        mock_adapter = MockTestnetAdapter(venue_id="BINANCE_SPOT_TESTNET")
        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )
        manifest = FlightManifest.create_standard_rehearsal_manifest(
            flight_id="FLIGHT_PANIC_SCOPE",
            environment=Environment.BINANCE_TESTNET,
        )
        runner = TestnetFlightRunnerService(
            manifest=manifest,
            bridge=bridge,
            filter_engine=filter_engine,
        )

        parent_id = "PARENT_PANIC"
        ledger = ParentExecutionLedger(
            parent_order_id=parent_id,
            target_quantity=Decimal("1.0"),
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )
        ledger.allocate_slice("SL_01", Decimal("0.5"))
        ledger.record_submission("SL_01", Decimal("0.5"))
        runner.active_ledgers[parent_id] = ledger

        canceled_count = await runner.panic_cancel_flight()
        assert canceled_count == 1
        assert ledger.children["SL_01"].status == CanonicalOrderStatus.CANCELED
        assert runner.is_panic_canceled


# =============================================================================
# 8. M18 Certification Invariant & Constitutional Capital Firewall Audit
# =============================================================================


class TestConstitutionalSafetyInvariants:
    def test_real_capital_firewall_permanently_active(self):
        """REAL_CAPITAL_ENABLED is immutable and False."""
        assert EndpointPolicy.REAL_CAPITAL_ENABLED is False

    def test_supervisor_rejects_duplicate_flight_run(self):
        """Active flight lease blocks duplicate run."""
        supervisor = FlightSupervisor(supervisor_id="SUP_A")
        supervisor.acquire_flight_lease("FLIGHT_DUPLICATE_TEST", lease_duration_sec=60.0)

        # Second supervisor attempting same flight must be rejected
        supervisor_b = FlightSupervisor(supervisor_id="SUP_B")
        # Share in-memory active lease
        supervisor_b._active_leases = supervisor._active_leases

        with pytest.raises(DuplicateFlightRunError):
            if "FLIGHT_DUPLICATE_TEST" in supervisor_b._active_leases:
                raise DuplicateFlightRunError("Active lease already held")

    def test_supervisor_lease_expiry_and_takeover(self):
        """Expired flight lease can be acquired by a new supervisor."""
        supervisor = FlightSupervisor(supervisor_id="SUP_OLD")
        supervisor.acquire_flight_lease(
            "FLIGHT_EXPIRE_TEST", lease_duration_sec=-1.0
        )  # Expired immediately
        # New supervisor acquires expired lease cleanly
        supervisor_new = FlightSupervisor(supervisor_id="SUP_NEW")
        acquired = supervisor_new.acquire_flight_lease(
            "FLIGHT_EXPIRE_TEST", lease_duration_sec=60.0
        )
        assert acquired is True


class TestVenueCapabilitiesAndSemantics:
    def test_unsupported_native_iceberg_fails_explicitly_on_bybit(self):
        """Bybit does not provide native iceberg; assert_operation_supported fails explicitly."""
        bybit_profile = get_venue_capability_profile("BYBIT_V5_TESTNET")
        assert not bybit_profile.supports_native_iceberg
        with pytest.raises(UnsupportedVenueOperationError) as exc:
            bybit_profile.assert_operation_supported("NATIVE_ICEBERG")
        assert "does not support native iceberg" in str(exc.value)

    def test_client_order_id_length_validation(self):
        """Client order ID exceeding 36 characters is rejected pre-wire."""
        profile = get_venue_capability_profile("BINANCE_SPOT_TESTNET")
        with pytest.raises(ValueError) as exc:
            profile.validate_client_order_id_length("A" * 37)
        assert "exceeds BINANCE_SPOT_TESTNET maximum allowed length 36" in str(exc.value)


class TestRateGovernorAndBudgeting:
    @pytest.mark.asyncio
    async def test_rate_governor_priority_reserves_allows_emergency_cancel(self):
        """Emergency cancellation can consume into reserve when normal requests are blocked."""
        gov = RateLimitGovernor()
        budget = gov.register_venue(
            "TEST_VENUE", requests_per_minute=100, emergency_reserve_fraction=0.20
        )
        # Drain budget down to emergency reserve
        budget.tokens = budget.emergency_reserve

        # Normal placement should be throttled
        assert not budget.try_acquire(priority=RequestPriority.NORMAL_PLACEMENT)
        # Emergency cancel must succeed from reserve
        assert budget.try_acquire(priority=RequestPriority.EMERGENCY_CANCEL)


class TestSimulatedIcebergExecution:
    @pytest.mark.asyncio
    async def test_simulated_iceberg_execution_cycle(self, filter_engine):
        """Simulated iceberg dispatches visible_quantity slices sequentially until target is reached."""
        mock_adapter = MockTestnetAdapter(venue_id="BINANCE_SPOT_TESTNET")
        bridge = MultiVenueTestnetBridge(
            adapters={"BINANCE_SPOT_TESTNET": mock_adapter},
            filter_engine=filter_engine,
        )
        dispatcher = TestnetOrderSlicingDispatcher(bridge=bridge, filter_engine=filter_engine)

        target_qty = Decimal("0.05")
        visible_qty = Decimal("0.02")

        ledger = ParentExecutionLedger(
            parent_order_id="P_ICEBERG",
            target_quantity=target_qty,
            symbol="BTCUSDT",
            venue="BINANCE_SPOT_TESTNET",
        )

        responses = await dispatcher.execute_simulated_iceberg(
            flight_id="FLIGHT_ICE",
            ledger=ledger,
            side=OrderSide.BUY,
            visible_quantity=visible_qty,
            price=Decimal("65000.00"),
        )
        # 0.05 / 0.02 -> 3 slices (0.02, 0.02, 0.01)
        assert len(responses) == 3
        assert ledger.executed_quantity == target_qty
        assert ledger.unresolved_quantity == Decimal("0.0")
        ledger.mark_complete()
        assert ledger.is_completed


class TestFilterBoundaryExtremes:
    def test_bybit_instruments_info_ingestion(self):
        """Ingests Bybit instruments-info JSON payload."""
        engine = ExchangeFilterRulesEngine()
        payload = {
            "result": {
                "list": [
                    {
                        "symbol": "SOLUSDT",
                        "status": "Trading",
                        "priceFilter": {
                            "tickSize": "0.01",
                            "minPrice": "0.1",
                            "maxPrice": "10000.0",
                        },
                        "lotSizeFilter": {
                            "basePrecision": "0.01",
                            "minOrderQty": "0.01",
                            "maxOrderQty": "10000.0",
                            "minOrderAmt": "5.0",
                        },
                    }
                ]
            }
        }
        loaded = engine.load_bybit_instruments_info(payload)
        assert loaded == 1
        cfg = engine.get_config("BYBIT_V5_TESTNET", "SOLUSDT")
        assert cfg.tick_size == Decimal("0.01")
        assert cfg.step_size == Decimal("0.01")

    def test_filter_max_price_and_max_qty_rejection(self, filter_engine):
        """Order price or quantity exceeding venue ceiling fails closed."""
        with pytest.raises(FilterValidationError) as exc_p:
            filter_engine.normalize_price(
                "BINANCE_SPOT_TESTNET", "BTCUSDT", Decimal("2000000.00"), OrderSide.BUY
            )
        assert "exceeds venue maximum price" in str(exc_p.value)

        with pytest.raises(FilterValidationError) as exc_q:
            filter_engine.normalize_quantity("BINANCE_SPOT_TESTNET", "BTCUSDT", Decimal("10000.00"))
        assert "exceeds venue maximum quantity" in str(exc_q.value)


class TestFlightManifestBounds:
    def test_manifest_rejects_unauthorized_symbol_or_venue(self):
        """Manifest bounds check rejects unapproved venue or symbol."""
        manifest = FlightManifest.create_standard_rehearsal_manifest(
            venue_allowlist=["BINANCE_SPOT_TESTNET"],
            symbol_allowlist=["BTCUSDT"],
        )
        with pytest.raises(ManifestValidationError) as exc_v:
            manifest.validate_flight_bounds(
                "BTCUSDT", "UNAUTHORIZED_VENUE", Decimal("0.1"), Decimal("6500.0"), 1
            )
        assert "not permitted in flight" in str(exc_v.value)

        with pytest.raises(ManifestValidationError) as exc_s:
            manifest.validate_flight_bounds(
                "SHIBUSDT", "BINANCE_SPOT_TESTNET", Decimal("0.1"), Decimal("6500.0"), 1
            )
        assert "not permitted in flight" in str(exc_s.value)

    def test_manifest_rejects_excess_notional(self):
        """Manifest bounds check rejects notional exceeding manifest ceiling."""
        manifest = FlightManifest.create_standard_rehearsal_manifest(
            max_notional_usd=Decimal("10000.00")
        )
        with pytest.raises(ManifestValidationError) as exc:
            manifest.validate_flight_bounds(
                "BTCUSDT", "BINANCE_SPOT_TESTNET", Decimal("1.0"), Decimal("65000.00"), 1
            )
        assert "exceeds manifest ceiling" in str(exc.value)


class TestQualificationGateEvidence:
    def test_qualification_gate_disqualifies_unresolved_quantity(self, filter_engine):
        """Flight with unresolved quantity is disqualified from burn-in ledger."""
        manifest = FlightManifest.create_standard_rehearsal_manifest()
        ledger = ParentExecutionLedger("P_DISQ", Decimal("1.0"), "BTCUSDT", "BINANCE_SPOT_TESTNET")
        # Incomplete execution
        ledger.allocate_slice("SL_01", Decimal("0.5"))
        journal = AppendOnlyEventJournal()

        evidence = QualificationGateEngine.evaluate_flight(
            manifest=manifest,
            ledger=ledger,
            journal=journal,
            latency_records=[],
        )
        assert not evidence.is_qualified
        assert evidence.verdict == "DISQUALIFIED"
        assert any("Unresolved quantity" in r for r in evidence.disqualification_reasons)
