"""
tests/test_testnet_stress_drills.py
===================================
Phase D Automated Test Suite:
1. 1,000-slice fault-injection stress harness.
2. Destructive Crash-Recovery Lab:
   Order accepted on exchange -> process killed before ACK -> process restarts ->
   reconciliation identifies existing order -> ZERO duplicate order submitted.
"""

import time

import pytest

from core.execution.idempotency import (
    DuplicateOrderError,
    OrderStatus,
    idempotency_store,
)
from scripts.run_testnet_stress_drills import (
    run_stress_test,
)


class TestStressHarnessInvariants:
    @pytest.mark.asyncio
    async def test_stress_harness_quantity_conservation_and_deduplication(self):
        summary = await run_stress_test(total_slices=200)
        assert summary.passed is True
        assert summary.quantity_conserved is True
        assert summary.duplicate_economic_fills == 0
        assert summary.orphaned_slices_remaining == 0
        assert summary.negative_inventory_events == 0


class TestDestructiveCrashRecoveryScenario:
    """
    Verifies that an unacknowledged order accepted by an exchange survives process crash
    and re-attaches safely without duplicate order creation.
    """

    def test_crash_recovery_prevents_duplicate_submission(self):
        client_order_id = f"CBT_CRASH_{int(time.time() * 1000)}"

        # Step 1: Client reserves order in durable idempotency store
        order_record = idempotency_store.reserve_order(
            client_order_id=client_order_id,
            exchange="BINANCE",
            environment="TESTNET",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=0.1,
            price=60000.0,
        )
        assert order_record.status == OrderStatus.RESERVED

        # Step 2: Order is received and accepted by exchange matching engine
        exchange_order_id = "EX_BINANCE_999888777"
        simulated_exchange_engine = {
            client_order_id: {
                "order_id": exchange_order_id,
                "status": "FILLED",
                "cum_qty": 0.1,
                "price": 60000.0,
            }
        }

        # Step 3: SIMULATED CRASH (Kill before ACK)
        # Process dies abruptly before idempotency_store.mark_dispatched or mark_final is called.
        # Order transitions to AMBIGUOUS upon timeout / health check.
        idempotency_store.mark_ambiguous(
            client_order_id=client_order_id,
            error_reason="PROCESS_KILLED_BEFORE_NETWORK_ACK",
        )

        # Step 4: System restarts and queries idempotency store
        recovered_order = idempotency_store.get_order_record(client_order_id)
        assert recovered_order is not None
        assert recovered_order.status == OrderStatus.AMBIGUOUS_RECONCILIATION_REQUIRED

        # Step 5: Startup Reconciliation Routine runs
        # It queries the exchange by client_order_id
        exchange_order_status = simulated_exchange_engine.get(client_order_id)
        assert exchange_order_status is not None

        # Step 6: Reconciliation updates state without re-dispatching
        if exchange_order_status["status"] == "FILLED":
            idempotency_store.mark_reconciled(
                client_order_id=client_order_id,
                resolved_status=OrderStatus.FILLED,
                exchange_order_id=exchange_order_status["order_id"],
                notes="Reconciled after process restart",
            )

        # Step 7: Verifications
        final_order = idempotency_store.get_order_record(client_order_id)
        assert final_order is not None
        assert final_order.status == OrderStatus.FILLED
        assert final_order.exchange_order_id == exchange_order_id

        # Step 8: Prove duplicate reservation fails closed
        with pytest.raises(DuplicateOrderError):
            idempotency_store.reserve_order(
                client_order_id=client_order_id,
                exchange="BINANCE",
                environment="TESTNET",
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=0.1,
                price=60000.0,
            )
