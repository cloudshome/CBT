"""
tests/test_web3_watch_only_invariant.py
=======================================
Institutional Test Suite for Machine-Enforced Watch-Only Web3 & Multi-RPC Quorum Engine.

Verifications:
1. AST & Symbol scan: zero signing functions, private key routines, or raw transaction broadcasters.
2. Multi-RPC consensus engine: 2-of-3 agreement, split-brain disagreement, degraded single-node, and unavailable.
3. Reject-closed wallet store: strictly rejects private keys and seed phrases.
4. Capital isolation firewall: proves watch-only capital cannot inflate execution-available capital.
5. REST API endpoint contract.
"""

import ast
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.web3.portfolio_aggregator import (
    WalletBalanceReport,
    portfolio_aggregator,
)
from core.web3.rpc_client import (
    MultiRpcQuorumClient,
    RpcFreshness,
    RpcNodeResponse,
)
from core.web3.wallet_store import (
    Web3SecurityViolationError,
    web3_wallet_store,
)


class TestWatchOnlyASTInvariant:
    """
    Forensic AST and symbol inspection verifying zero signing routines exist in core/web3.
    """

    FORBIDDEN_IDENTIFIERS: ClassVar[set[str]] = {
        "personal_sign",
        "eth_sign",
        "eth_sendRawTransaction",
        "send_raw_transaction",
        "sign_transaction",
        "sign_message",
        "from_key",
        "PrivateKey",
        "Account.from_key",
        "bip39",
        "mnemonic_to_seed",
    }

    def test_zero_signing_code_in_web3_subsystem(self):
        web3_dir = Path("core/web3")
        assert web3_dir.exists(), "core/web3 directory must exist"

        py_files = list(web3_dir.glob("*.py"))
        assert len(py_files) >= 3, "Expected at least 3 python modules in core/web3"

        violations = []
        for p in py_files:
            source = p.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(p))

            for node in ast.walk(tree):
                # Check function call names
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in self.FORBIDDEN_IDENTIFIERS:
                            violations.append(
                                f"{p.name}:{node.lineno}: function call {node.func.id}"
                            )
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in self.FORBIDDEN_IDENTIFIERS:
                            violations.append(
                                f"{p.name}:{node.lineno}: attribute call {node.func.attr}"
                            )

                # Check imported module names
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(f in alias.name for f in ("eth_account", "bip_utils", "mnemonic")):
                            violations.append(
                                f"{p.name}:{node.lineno}: forbidden import {alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if any(f in mod for f in ("eth_account", "bip_utils", "mnemonic")):
                        violations.append(f"{p.name}:{node.lineno}: forbidden from-import {mod}")

        assert not violations, (
            "CRITICAL WATCH-ONLY VIOLATION: Found signing logic in web3:\n" + "\n".join(violations)
        )


class TestMultiRpcQuorum:
    """
    Verifies multi-RPC consensus quorum and freshness state transitions.
    """

    @pytest.mark.asyncio
    async def test_perfect_three_of_three_consensus_returns_fresh(self):
        client = MultiRpcQuorumClient()

        # Mock 3 identical node responses
        mock_responses = [
            RpcNodeResponse(
                url="https://rpc1.com", success=True, data="0xde0b6b3a7640000", latency_ms=45.0
            ),  # 1.0 ETH
            RpcNodeResponse(
                url="https://rpc2.com", success=True, data="0xde0b6b3a7640000", latency_ms=55.0
            ),
            RpcNodeResponse(
                url="https://rpc3.com", success=True, data="0xde0b6b3a7640000", latency_ms=50.0
            ),
        ]

        with patch.object(client, "_post_json_rpc", side_effect=mock_responses):
            res = await client.get_native_balance(
                "ETHEREUM", "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            )
            assert res.quorum_status == RpcFreshness.FRESH
            assert res.value == 1.0
            assert res.responding_nodes == 3
            assert res.agreeing_nodes == 3

    @pytest.mark.asyncio
    async def test_two_of_three_majority_consensus_tolerates_one_failure(self):
        client = MultiRpcQuorumClient()

        # 2 nodes return 2.5 SOL, 1 node fails with 500 error
        mock_responses = [
            RpcNodeResponse(
                url="https://rpc1.solana.com",
                success=True,
                data={"value": 2500000000},
                latency_ms=60.0,
            ),
            RpcNodeResponse(
                url="https://rpc2.solana.com", success=False, error="HTTP 500", latency_ms=120.0
            ),
            RpcNodeResponse(
                url="https://rpc3.solana.com",
                success=True,
                data={"value": 2500000000},
                latency_ms=75.0,
            ),
        ]

        with patch.object(client, "_post_json_rpc", side_effect=mock_responses):
            res = await client.get_native_balance(
                "SOLANA", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
            )
            assert res.quorum_status == RpcFreshness.FRESH
            assert res.value == 2.5
            assert res.responding_nodes == 2
            assert res.agreeing_nodes == 2

    @pytest.mark.asyncio
    async def test_split_brain_disagreement_returns_disagreement_status(self):
        client = MultiRpcQuorumClient()

        # Node 1 says 100 ETH, Node 2 says 200 ETH, Node 3 says 300 ETH
        mock_responses = [
            RpcNodeResponse(
                url="https://rpc1.com", success=True, data="0x56bc75e2d63100000", latency_ms=40.0
            ),  # 100 ETH
            RpcNodeResponse(
                url="https://rpc2.com", success=True, data="0xad78ebc5ac6200000", latency_ms=45.0
            ),  # 200 ETH
            RpcNodeResponse(
                url="https://rpc3.com", success=True, data="0x1043561a829300000", latency_ms=50.0
            ),  # 300 ETH
        ]

        with patch.object(client, "_post_json_rpc", side_effect=mock_responses):
            res = await client.get_native_balance(
                "ETHEREUM", "0x0000000000000000000000000000000000000001"
            )
            assert res.quorum_status == RpcFreshness.DISAGREEMENT
            assert res.agreeing_nodes < 2

    @pytest.mark.asyncio
    async def test_single_responding_node_returns_degraded_status(self):
        client = MultiRpcQuorumClient()

        mock_responses = [
            RpcNodeResponse(
                url="https://rpc1.com", success=True, data="0xde0b6b3a7640000", latency_ms=50.0
            ),
            RpcNodeResponse(
                url="https://rpc2.com", success=False, error="Timeout", latency_ms=4000.0
            ),
            RpcNodeResponse(
                url="https://rpc3.com", success=False, error="ConnectionRefused", latency_ms=10.0
            ),
        ]

        with patch.object(client, "_post_json_rpc", side_effect=mock_responses):
            res = await client.get_native_balance(
                "ETHEREUM", "0x0000000000000000000000000000000000000002"
            )
            assert res.quorum_status == RpcFreshness.DEGRADED
            assert res.responding_nodes == 1
            assert res.agreeing_nodes == 1

    @pytest.mark.asyncio
    async def test_all_nodes_failing_returns_unavailable(self):
        client = MultiRpcQuorumClient()

        mock_responses = [
            RpcNodeResponse(url="https://rpc1.com", success=False, error="Timeout"),
            RpcNodeResponse(url="https://rpc2.com", success=False, error="Timeout"),
            RpcNodeResponse(url="https://rpc3.com", success=False, error="Timeout"),
        ]

        with patch.object(client, "_post_json_rpc", side_effect=mock_responses):
            res = await client.get_native_balance(
                "ETHEREUM", "0x0000000000000000000000000000000000000003"
            )
            assert res.quorum_status == RpcFreshness.UNAVAILABLE
            assert res.responding_nodes == 0


class TestWalletStoreAndKeyRejection:
    """
    Verifies input filtering, SQLite check constraints, and rejection of private keys.
    """

    def test_valid_evm_address_registration(self):
        addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        w = web3_wallet_store.add_wallet("ETHEREUM", addr, "Vitalik Cold")
        assert w.is_watch_only is True
        assert w.address == addr.lower()

        wallets = web3_wallet_store.list_wallets()
        stored = next((x for x in wallets if x.address == addr.lower()), None)
        assert stored is not None
        assert stored.is_watch_only is True

    def test_reject_raw_private_key(self):
        # 64-char hex private key
        raw_key = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        with pytest.raises(Web3SecurityViolationError, match="Raw 32-byte private key detected"):
            web3_wallet_store.add_wallet("ETHEREUM", raw_key, "Accidental Private Key")

    def test_reject_mnemonic_seed_phrase(self):
        seed_phrase = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        with pytest.raises(Web3SecurityViolationError, match="Seed phrase / mnemonic detected"):
            web3_wallet_store.add_wallet("ETHEREUM", seed_phrase, "Accidental Mnemonic")

    def test_delete_wallet(self):
        addr = "0x00000000000000000000000000000000000000aa"
        web3_wallet_store.add_wallet("ARBITRUM", addr, "Temp Wallet")
        assert web3_wallet_store.remove_wallet(addr) is True
        assert web3_wallet_store.remove_wallet(addr) is False


class TestCapitalIsolationFirewall:
    """
    Mathematical proof that watch-only capital CANNOT inflate execution-available capital.
    """

    @pytest.mark.asyncio
    async def test_watch_only_equity_isolated_from_execution_capital(self):
        # Simulate an exchange account with $5,000 margin
        exchange_balances = {"BINANCE_FUTURES": 5000.0}

        # Mock a wallet containing 10,000 ETH (approx $35,000,000)
        mock_report = WalletBalanceReport(
            address="0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
            chain="ETHEREUM",
            label="Whale Cold Storage",
            is_watch_only=True,
            native_asset="ETH",
            native_balance=10000.0,
            native_value_usd=35000000.0,
            tokens={},
            total_value_usd=35000000.0,
            quorum_status="FRESH",
            last_synced_ms=1700000000000,
        )

        with patch.object(portfolio_aggregator, "scan_watch_wallet", return_value=mock_report):
            scorecard = await portfolio_aggregator.get_aggregated_scorecard(exchange_balances)

            # 1. Execution Available Capital MUST REMAIN STRICTLY AT $5,000.00
            assert scorecard.execution_available_capital_usd == 5000.00

            # 2. Watch-Only Equity is tracked separately
            assert scorecard.watch_only_equity_usd >= 35000000.00

            # 3. Total Observed Equity is the sum
            assert scorecard.observed_total_equity_usd == 5000.00 + scorecard.watch_only_equity_usd

            # 4. Invariant: Execution capital is strictly <= exchange balances
            assert scorecard.execution_available_capital_usd <= sum(exchange_balances.values())
            assert scorecard.capital_firewall_verified is True


class TestWeb3ApiEndpoints:
    """
    Validates the REST API endpoints in app.py.
    """

    def test_list_wallets_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/web3/wallets")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["mode"] == "WATCH_ONLY_IMMUTABLE"

    def test_add_wallet_rejects_private_key(self):
        client = TestClient(app)
        res = client.post(
            "/api/web3/wallets",
            json={
                "chain": "ETHEREUM",
                "address": "4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d",
                "label": "Evil Private Key",
            },
        )
        assert res.status_code == 400
        assert "Raw 32-byte private key detected" in res.text

    def test_add_and_delete_valid_wallet(self):
        client = TestClient(app)
        addr = "0x1111111111111111111111111111111111111111"
        res = client.post(
            "/api/web3/wallets",
            json={"chain": "ETHEREUM", "address": addr, "label": "Test Add Valid"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "SUCCESS"

        del_res = client.delete(f"/api/web3/wallets/{addr}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "SUCCESS"

    def test_get_aggregated_equity_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/portfolio/aggregated-equity")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "scorecard" in data
        assert data["scorecard"]["capital_firewall_verified"] is True
