"""
tests/test_hyperliquid_connector.py
===================================
Adversarial and functional test suite for Native Hyperliquid Perpetual Futures L1 Connector.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from core.execution.connectors.hyperliquid_connector import HyperliquidPerpConnector
from core.execution.connectors.base import ExchangeAuthenticationError


def test_hyperliquid_initialization_validation():
    """Requires valid EVM master address format."""
    with pytest.raises(ExchangeAuthenticationError, match="Invalid EVM master address format"):
        HyperliquidPerpConnector(
            master_address="invalid_not_0x",
            agent_private_key="0x" + "a" * 64,
            is_paper_trading=True,
        )


def test_hyperliquid_valid_initialization():
    """Validates successful initialization with EVM address and agent key."""
    master = "0x1111111111111111111111111111111111111111"
    key = "0x" + "1" * 64
    conn = HyperliquidPerpConnector(
        master_address=master,
        agent_private_key=key,
        is_paper_trading=True,
    )
    assert conn.exchange_name == "HYPERLIQUID"
    assert conn.master_address == master
    assert conn.is_paper_trading is True
    assert conn._agent_account is not None


def test_hyperliquid_zero_withdrawal_invariant():
    """Enforces that Hyperliquid connector has zero withdrawal APIs by design."""
    master = "0x1111111111111111111111111111111111111111"
    conn = HyperliquidPerpConnector(
        master_address=master,
        is_paper_trading=True,
    )
    # The connector does not implement or allow withdrawals
    assert not hasattr(conn, "withdraw")
    assert not hasattr(conn, "transfer_out")


def test_hyperliquid_eip712_action_hashing():
    """Verifies that EIP-712 structured order signing produces valid signature."""
    master = "0x1111111111111111111111111111111111111111"
    key = "0x" + "2" * 64
    conn = HyperliquidPerpConnector(
        master_address=master,
        agent_private_key=key,
        is_paper_trading=True,
    )
    action = {
        "type": "order",
        "orders": [
            {
                "asset": 0,
                "isBuy": True,
                "limitPx": "50000.0",
                "sz": "0.1",
                "reduceOnly": False,
                "orderType": {"limit": {"tif": "Gtc"}},
            }
        ],
    }
    sig = conn.sign_l1_action(action, nonce=1700000000000)
    assert isinstance(sig, dict)
    assert "r" in sig
    assert "s" in sig
    assert "v" in sig
    assert sig["r"].startswith("0x")
    assert sig["s"].startswith("0x")
