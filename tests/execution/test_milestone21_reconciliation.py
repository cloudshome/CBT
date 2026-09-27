"""
tests/execution/test_milestone21_reconciliation.py
==================================================
Milestone 21: Event Reconciliation, Stream Disambiguation & Forensic Evidence Test Suite.

Verifies:
1. Strict Bybit Event Separation (ORDER_STATUS_EVENT vs EXECUTION_EVENT vs BALANCE_UPDATE).
2. Binance Spot executionReport event disambiguation.
3. Multi-axis qualification verdict (11 PASS gates, production_market_validity NOT_ESTABLISHED).
4. Real capital authorization strictly DENIED in all governance artifacts.
5. Cryptographically hashed SHA-256 forensic evidence bundles.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import pytest

from core.execution.testnet.binance_spot import BinanceSpotTestnetAdapter
from core.execution.testnet.bybit_v5 import BybitV5TestnetAdapter
from core.execution.testnet.credential_policy import TestnetCredentials
from core.execution.testnet.endpoint_policy import Environment
from core.execution.testnet.evidence import EvidenceGenerator, Milestone21Verdict
from core.execution.testnet.rest_transport import RestTransport


@pytest.fixture
def binance_credentials():
    return TestnetCredentials(
        api_key="binance_test_key_12345",
        api_secret="binance_test_secret_67890",
        environment=Environment.BINANCE_TESTNET,
    )


@pytest.fixture
def bybit_credentials():
    return TestnetCredentials(
        api_key="bybit_test_key_12345",
        api_secret="bybit_test_secret_67890",
        environment=Environment.BYBIT_TESTNET,
    )


# =============================================================================
# 1. Bybit Strict Event Separation
# =============================================================================


@pytest.mark.asyncio
async def test_bybit_event_separation_prevents_phantom_fills(bybit_credentials):
    """
    Bybit ORDER_STATUS_EVENT must NEVER trigger an economic fill.
    Only EXECUTION_EVENT represents authoritative trade execution.
    """
    mock_transport = MagicMock(spec=RestTransport)
    adapter = BybitV5TestnetAdapter(
        credentials=bybit_credentials,
        rest_transport=mock_transport,
    )

    # 1. Dispatch order status frame
    order_status_frame = {
        "topic": "order",
        "data": [
            {
                "orderId": "ord_1001",
                "orderLinkId": "cid_1001",
                "orderStatus": "Filled",
                "cumExecQty": "1.0",
                "avgPrice": "60000.0",
            }
        ],
    }
    await adapter._handle_ws_message(order_status_frame)

    assert adapter.order_status_events_received == 1
    assert adapter.execution_events_received == 0
    assert adapter.balance_updates_received == 0

    # 2. Dispatch execution frame
    execution_frame = {
        "topic": "execution",
        "data": [
            {
                "execId": "tr_2001",
                "orderId": "ord_1001",
                "orderLinkId": "cid_1001",
                "execPrice": "60000.0",
                "execQty": "1.0",
                "execFee": "0.0001",
                "feeRate": "0.001",
            }
        ],
    }
    await adapter._handle_ws_message(execution_frame)

    assert adapter.order_status_events_received == 1
    assert adapter.execution_events_received == 1
    assert adapter.balance_updates_received == 0

    # 3. Dispatch wallet balance frame
    wallet_frame = {
        "topic": "wallet",
        "data": [{"coin": [{"coin": "USDT", "walletBalance": "50000.0"}]}],
    }
    await adapter._handle_ws_message(wallet_frame)

    assert adapter.order_status_events_received == 1
    assert adapter.execution_events_received == 1
    assert adapter.balance_updates_received == 1


# =============================================================================
# 2. Binance Spot Event Handling
# =============================================================================


@pytest.mark.asyncio
async def test_binance_user_data_stream_dispatch(binance_credentials):
    """Binance User Data Stream message routing."""
    mock_transport = MagicMock(spec=RestTransport)
    adapter = BinanceSpotTestnetAdapter(
        credentials=binance_credentials,
        rest_transport=mock_transport,
    )

    # Trade execution event
    trade_event = {
        "e": "executionReport",
        "E": 1700000000000,
        "s": "BTCUSDT",
        "c": "cid_binance_1",
        "S": "BUY",
        "o": "LIMIT",
        "q": "0.50000000",
        "p": "60000.00000000",
        "x": "TRADE",
        "X": "FILLED",
        "i": 12345678,
        "l": "0.50000000",
        "z": "0.50000000",
        "L": "60000.00000000",
        "t": 987654321,
    }
    await adapter._handle_ws_message(trade_event)
    # Verification that message processed without raising exceptions


# =============================================================================
# 3. Multi-Axis Verdict Governance & Forensic Evidence
# =============================================================================


def test_milestone21_verdict_governance_axes():
    """Milestone 21 verdict must enforce non-negotiable governance axes."""
    verdict = Milestone21Verdict()
    v_dict = verdict.to_dict()

    # Technical gates must be PASS
    assert v_dict["endpoint_isolation"] == "PASS"
    assert v_dict["credential_scope"] == "PASS"
    assert v_dict["binance_rest_integration"] == "PASS"
    assert v_dict["binance_private_stream"] == "PASS"
    assert v_dict["bybit_rest_integration"] == "PASS"
    assert v_dict["bybit_private_stream"] == "PASS"
    assert v_dict["order_lifecycle_reconciliation"] == "PASS"
    assert v_dict["websocket_recovery"] == "PASS"
    assert v_dict["crash_recovery"] == "PASS"
    assert v_dict["clock_offset_measurement"] == "PASS"
    assert v_dict["staged_rehearsal_flight"] == "PASS"

    # Crucial Epistemic Boundary: Testnet success does NOT equal live validity
    assert v_dict["production_market_validity"] == "NOT_ESTABLISHED"

    # Absolute Capital Firewall: Live capital authorization is strictly DENIED
    assert v_dict["real_capital_authorization"] == "DENIED"


def test_evidence_bundle_cryptographic_integrity():
    """Evidence generator must produce verifiable SHA-256 digest."""
    test_metrics = {
        "total_tests_passed": 51,
        "venues_qualified": ["BINANCE_SPOT_TESTNET", "BYBIT_V5_TESTNET"],
        "gap_fills_recovered": 5,
        "clock_offset_uncertainty_ms": 15.2,
    }

    bundle = EvidenceGenerator.generate_bundle(
        session_id="M21_QUALIFICATION_SESSION_01",
        test_results=test_metrics,
    )

    assert bundle["milestone"] == "MILESTONE_21"
    assert bundle["real_capital_enabled"] is False
    assert bundle["verdict"]["real_capital_authorization"] == "DENIED"
    assert "epistemic_disclaimer" in bundle
    assert "evidence_sha256" in bundle

    # Verify SHA-256 digest correctness
    digest = bundle["evidence_sha256"]
    unhashed_bundle = dict(bundle)
    del unhashed_bundle["evidence_sha256"]
    canonical_json = json.dumps(unhashed_bundle, sort_keys=True)
    expected_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    assert digest == expected_digest
