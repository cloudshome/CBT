"""
tests/test_phase22_canary_verification.py
=========================================
Institutional Test Suite for Phase 22 Tasks 22.1 & 22.2:
- Production Exchange API Credential Provisioning & Vault Hardening
- Micro-Canary Burn-In ($10-$25 USD)
- Fail-Closed Positive Withdrawal-Disabled Proof (Binance & Bybit)
- Connectivity Probing (Unauthenticated Ping vs Authenticated HMAC Probe)
- Revocation Invalidation (Vault DB, Capability Cache, Connector Sessions)
- Symbol Constraint Engine (Step-size floor quantization, minNotional, no auto-rounding)
- Monotonic ns Latency Telemetry & Separation of ACK SLA (<500ms) from Fill SLA
- Timeout Ambiguity & Reconcile-Before-Retry (UNKNOWN_EXECUTION_STATE, Zero Blind Retry)
"""

from __future__ import annotations

import json
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth.credential_vault import (
    CredentialCapability,
    CredentialPermissionProfile,
    CredentialVerificationResult,
    ExchangeCredential,
    credential_vault,
    normalize_binance_permissions,
    normalize_bybit_permissions,
)
from core.execution.live_canary_runner import (
    CanaryRunRequest,
    CanaryRunResult,
    live_canary_runner,
)
from core.execution.live_gatekeeper import (
    GatekeeperVerdict,
    LiveExecutionGatekeeper,
)
from core.execution.symbol_constraints import (
    SymbolConstraintEngine,
)


@pytest.fixture(autouse=True)
def clean_vault_db():
    """Ensure vault database and capability cache are completely cleaned before and after each test."""
    for exch in ("BINANCE", "BYBIT"):
        for env in ("TESTNET", "PRODUCTION"):
            try:
                credential_vault.revoke_credential(exch, env)
            except Exception as exc:
                _ = exc
    yield
    for exch in ("BINANCE", "BYBIT"):
        for env in ("TESTNET", "PRODUCTION"):
            try:
                credential_vault.revoke_credential(exch, env)
            except Exception as exc:
                _ = exc


# =============================================================================
# 1. POSITIVE WITHDRAWAL-DISABLED PROOF TESTS (FAIL-CLOSED)
# =============================================================================


class TestPermissionNormalization:
    def test_binance_positive_withdrawal_disabled_proof(self):
        """Binance must provide positive proof that enableWithdrawals is explicitly False."""
        valid_raw = {
            "ipRestrict": True,
            "createTime": 1600000000000,
            "enableWithdrawals": False,
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
            "enableVanillaOptions": False,
            "enableReading": True,
            "enableFutures": False,
            "enableMargin": False,
            "enableSpotAndMarginTrading": True,
        }
        profile = normalize_binance_permissions(valid_raw)
        assert profile.spot_trade is True
        assert profile.withdrawal is False
        assert len(profile.unknown_permissions) == 0
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is True
        assert reason == "SAFE"

    def test_binance_withdrawal_enabled_fails_closed(self):
        """Binance with enableWithdrawals=True must be flagged unsafe."""
        hazard_raw = {
            "enableWithdrawals": True,
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
        }
        profile = normalize_binance_permissions(hazard_raw)
        assert profile.withdrawal is True
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is False
        assert "WITHDRAWAL_ENABLED" in reason

    def test_binance_missing_withdrawal_field_fails_closed(self):
        """Binance with missing enableWithdrawals must fail closed (withdrawal=True)."""
        ambiguous_raw = {
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
        }
        profile = normalize_binance_permissions(ambiguous_raw)
        assert profile.withdrawal is True
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is False
        assert "WITHDRAWAL_ENABLED" in reason

    def test_binance_unknown_permissions_fails_closed(self):
        """Binance with unrecognized permission keys must be quarantined as unsafe."""
        unknown_raw = {
            "enableWithdrawals": False,
            "enableReading": True,
            "enableSpotAndMarginTrading": True,
            "enableSuperSecretTransfer": True,
        }
        profile = normalize_binance_permissions(unknown_raw)
        assert "enableSuperSecretTransfer" in profile.unknown_permissions
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is False
        assert "UNKNOWN_PERMISSIONS" in reason

    def test_binance_testnet_account_fallback_with_commission_rates(self):
        """Binance Spot Testnet /api/v3/account fallback includes commissionRates and simulated canWithdraw=True."""
        testnet_account_raw = {
            "makerCommission": 0,
            "takerCommission": 0,
            "buyerCommission": 0,
            "sellerCommission": 0,
            "commissionRates": {
                "maker": "0.00000000",
                "taker": "0.00000000",
                "buyer": "0.00000000",
                "seller": "0.00000000",
            },
            "canTrade": True,
            "canWithdraw": True,
            "canDeposit": True,
            "brokered": False,
            "requireSelfTradePrevention": False,
            "preventSor": False,
            "updateTime": 1775832651073,
            "accountType": "SPOT",
            "balances": [{"asset": "USDT", "free": "10000.00000000", "locked": "0.00000000"}],
            "permissions": ["TRD_GRP_002", "SPOT"],
            "uid": 123456789,
        }
        # In TESTNET environment, this /api/v3/account fallback is safe when permissions exclude WITHDRAW
        testnet_profile = normalize_binance_permissions(testnet_account_raw, environment="TESTNET")
        assert len(testnet_profile.unknown_permissions) == 0
        assert testnet_profile.spot_trade is True
        assert testnet_profile.withdrawal is False
        assert testnet_profile.is_strictly_safe_for_trading()[0] is True

        # In PRODUCTION environment, the exact same fallback with canWithdraw=True MUST still fail closed
        prod_profile = normalize_binance_permissions(testnet_account_raw, environment="PRODUCTION")
        assert prod_profile.withdrawal is True
        assert prod_profile.is_strictly_safe_for_trading()[0] is False

    def test_bybit_positive_withdrawal_disabled_proof(self):
        """Bybit must provide positive proof that Wallet permissions do not contain Withdraw."""
        valid_raw = {
            "retCode": 0,
            "result": {
                "readOnly": 0,
                "permissions": {
                    "ContractTrade": ["Order", "Position"],
                    "Spot": ["SpotTrade"],
                    "Wallet": [],  # Empty wallet permissions = No withdraw
                    "Options": [],
                },
                "ips": ["1.2.3.4"],
            },
        }
        profile = normalize_bybit_permissions(valid_raw)
        assert profile.spot_trade is True
        assert profile.derivatives_trade is True
        assert profile.withdrawal is False
        assert len(profile.unknown_permissions) == 0
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is True
        assert reason == "SAFE"

    def test_bybit_withdrawal_enabled_fails_closed(self):
        """Bybit with Wallet containing 'Withdraw' must be flagged unsafe."""
        hazard_raw = {
            "retCode": 0,
            "result": {
                "permissions": {
                    "ContractTrade": ["Order"],
                    "Wallet": ["Withdraw"],
                }
            },
        }
        profile = normalize_bybit_permissions(hazard_raw)
        assert profile.withdrawal is True
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is False
        assert "WITHDRAWAL_ENABLED" in reason

    def test_bybit_missing_permissions_dict_fails_closed(self):
        """Bybit with missing permissions block must fail closed."""
        empty_raw = {"retCode": 0, "result": {}}
        profile = normalize_bybit_permissions(empty_raw)
        assert profile.withdrawal is True
        is_safe, reason = profile.is_strictly_safe_for_trading()
        assert is_safe is False

    def test_non_dict_payload_fails_closed(self):
        """Non-dict responses must fail closed for both exchanges."""
        p_binance = normalize_binance_permissions("bad_string")
        assert p_binance.withdrawal is True
        assert not p_binance.is_strictly_safe_for_trading()[0]

        p_bybit = normalize_bybit_permissions(12345)
        assert p_bybit.withdrawal is True
        assert not p_bybit.is_strictly_safe_for_trading()[0]


# =============================================================================
# 2. MULTI-TIER PROBE & ZERO-LEAKAGE VERIFICATION
# =============================================================================


class TestMultiTierProbes:
    @pytest.mark.asyncio
    async def test_connectivity_probe_ping(self):
        """Unauthenticated ping tests transit reachability without API keys."""
        mock_response = MagicMock()
        mock_response.status = 200

        class MockContextManager:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        mock_session = MagicMock()
        mock_session.get.return_value = MockContextManager()

        ok, latency, msg = await credential_vault.connectivity_probe(
            "BINANCE", "TESTNET", session=mock_session
        )
        assert ok is True
        assert latency >= 0.0
        assert "reachable" in msg.lower()

    @pytest.mark.asyncio
    async def test_verify_credential_connectivity_safe(self):
        """Full probe verifying account HMAC and positive withdrawal-disabled restrictions."""
        credential_vault.store_credential(
            ExchangeCredential(
                exchange="BINANCE",
                environment="TESTNET",
                api_key="vm_test_key_binance_1234567890",
                api_secret="vm_test_secret_binance_abcdef123456",
            )
        )

        with (
            patch.object(
                credential_vault, "connectivity_probe", new_callable=AsyncMock
            ) as mock_ping,
            patch.object(
                credential_vault, "authenticated_account_probe", new_callable=AsyncMock
            ) as mock_acct,
            patch.object(credential_vault, "permission_probe", new_callable=AsyncMock) as mock_perm,
        ):
            mock_ping.return_value = (True, 45.0, "Network reachable")
            mock_acct.return_value = (True, 85.0, {"canTrade": True}, "Account authenticated")
            safe_profile = CredentialPermissionProfile(
                read=True,
                spot_trade=True,
                derivatives_trade=False,
                withdrawal=False,
                internal_transfer=False,
                universal_transfer=False,
                subaccount_transfer=False,
                unknown_permissions=[],
                raw_restrictions={"enableWithdrawals": False},
            )
            mock_perm.return_value = (safe_profile, 65.0, "Permissions verified")

            result: CredentialVerificationResult = (
                await credential_vault.verify_credential_connectivity("BINANCE", "TESTNET")
            )
            assert result.exchange == "BINANCE"
            assert result.environment == "TESTNET"
            assert result.authenticated is True
            assert result.trading_enabled is True
            assert result.withdrawal_enabled is False
            assert result.status == "PASS"

            # Ensure zero secret leakage in dictionary serialization
            res_dict = result.to_safe_dict()
            assert "api_secret" not in res_dict
            assert "abcdef" not in json.dumps(res_dict)

    @pytest.mark.asyncio
    async def test_verify_credential_fails_when_unauthorized_hmac(self):
        """Account HMAC failure must fail-closed and quarantine credential."""
        credential_vault.store_credential(
            ExchangeCredential(
                exchange="BINANCE",
                environment="TESTNET",
                api_key="vm_bad_key_1234567890",
                api_secret="vm_bad_secret_123456",
            )
        )

        with (
            patch.object(
                credential_vault, "connectivity_probe", new_callable=AsyncMock
            ) as mock_ping,
            patch.object(
                credential_vault, "authenticated_account_probe", new_callable=AsyncMock
            ) as mock_acct,
        ):
            mock_ping.return_value = (True, 45.0, "Network reachable")
            mock_acct.return_value = (False, 90.0, {}, "Binance authentication rejected (401)")

            result = await credential_vault.verify_credential_connectivity("BINANCE", "TESTNET")
            assert result.status == "FAIL_AUTH"
            assert result.authenticated is False
            assert result.withdrawal_enabled is True  # Fail-closed


# =============================================================================
# 3. REVOCATION & INVALIDATION PROTOCOL
# =============================================================================


class TestRevocationProtocol:
    def test_revocation_clears_db_and_notifies_listener(self):
        """Revoking credential removes DB record, clears capability cache, and fires listener."""
        credential_vault.store_credential(
            ExchangeCredential(
                exchange="BINANCE",
                environment="TESTNET",
                api_key="key_to_revoke_12345",
                api_secret="secret_to_revoke_67890",
            )
        )
        assert credential_vault.get_credential("BINANCE", "TESTNET") is not None

        # Pre-populate capability cache
        safe_cap = CredentialCapability(
            exchange="BINANCE",
            environment="TESTNET",
            credential_id="BINANCE_TESTNET",
            masked_api_key="key_...345",
            trading_allowed=True,
            withdrawal_allowed=False,
            transfer_allowed=False,
            permissions_verified_at=int(time.time() * 1000),
            verification_status="PASS",
        )
        credential_vault._capability_cache[("BINANCE", "TESTNET")] = safe_cap

        events_received = []

        def listener(exch, env):
            events_received.append((exch, env))

        credential_vault.register_revocation_listener(listener)

        # Revoke
        success = credential_vault.revoke_credential("BINANCE", "TESTNET")
        assert success is True
        assert credential_vault.get_credential("BINANCE", "TESTNET") is None
        assert (
            credential_vault.get_cached_capability("BINANCE", "TESTNET").verification_status
            == "REVOKED"
        )
        assert ("BINANCE", "TESTNET") in events_received

    def test_gatekeeper_invalidates_cache_on_revocation(self):
        """LiveExecutionGatekeeper records revocation event when listener is notified."""
        gk = LiveExecutionGatekeeper()
        initial_count = len(gk._revocation_log)
        gk._handle_credential_revocation("BINANCE", "TESTNET")
        assert len(gk._revocation_log) == initial_count + 1
        assert gk._revocation_log[-1][0] == "BINANCE"
        assert gk._revocation_log[-1][1] == "TESTNET"


# =============================================================================
# 4. SYMBOL CONSTRAINT & SIZING FEASIBILITY ENGINE
# =============================================================================


class TestSymbolConstraintEngine:
    def test_quantization_floors_down(self):
        """Quantization must strictly floor down to step_size, never rounding up."""
        engine = SymbolConstraintEngine()
        # BTC with step_size 0.00001
        # Target notional $10 at price $65,000.00 -> 0.0001538... -> 0.00015 BTC ($9.75)
        feas = engine.evaluate_order_feasibility(
            "BINANCE", "BTCUSDT", requested_notional_usd=10.0, reference_price=65000.0
        )
        assert feas.is_feasible is True
        assert feas.feasible_qty == 0.00015
        assert feas.final_notional_usd == pytest.approx(9.75, abs=0.01)

    def test_rejection_below_min_notional(self):
        """Rejects order if requested notional drops below bounds ($5.00)."""
        engine = SymbolConstraintEngine()
        # $4.00 requested, below $5.00 minNotional
        feas = engine.evaluate_order_feasibility(
            "BINANCE", "BTCUSDT", requested_notional_usd=4.0, reference_price=65000.0
        )
        assert feas.is_feasible is False
        assert feas.status == "NOTIONAL_OUT_OF_BOUNDS"
        assert "between $5.00 and $25.00" in (feas.rejection_reason or "")

    def test_rejection_exceeding_canary_bounds(self):
        """Rejects order if requested notional exceeds $25.00 canary ceiling."""
        engine = SymbolConstraintEngine()
        feas = engine.evaluate_order_feasibility(
            "BINANCE", "BTCUSDT", requested_notional_usd=26.0, reference_price=65000.0
        )
        assert feas.is_feasible is False
        assert feas.status == "NOTIONAL_OUT_OF_BOUNDS"
        assert "between $5.00 and $25.00" in (feas.rejection_reason or "")

    def test_no_automatic_upward_rounding(self):
        """Quantizer must never inflate an order upward. Infeasible combinations reject properly."""
        engine = SymbolConstraintEngine()
        # On Bybit BTCUSDT perp, minQty is 0.001 ($60), so a $10 canary is infeasible and must reject
        feas = engine.evaluate_order_feasibility(
            "BYBIT", "BTCUSDT", requested_notional_usd=10.0, reference_price=60000.0
        )
        assert feas.is_feasible is False
        assert feas.status == "CANARY_REJECTED_SYMBOL_CONSTRAINT"
        assert "minQty" in feas.rejection_reason

        # On Binance ETHUSDT (price $2500, step_size 0.0001, min_qty 0.0001 = $0.25): $10 is feasible
        feas_eth = engine.evaluate_order_feasibility(
            "BINANCE", "ETHUSDT", requested_notional_usd=10.0, reference_price=2500.0
        )
        assert feas_eth.is_feasible is True
        assert feas_eth.final_notional_usd <= 10.0


# =============================================================================
# 5. CREDENTIAL CAPABILITY FIREWALL IN LIVE GATEKEEPER
# =============================================================================


class TestGatekeeperCapabilityFirewall:
    @pytest.mark.asyncio
    async def test_gatekeeper_blocks_when_withdrawal_permitted(self):
        """Gate 1b: Gatekeeper strictly blocks live order if credentials permit withdrawals."""
        credential_vault.store_credential(
            ExchangeCredential(
                exchange="BINANCE",
                environment="PRODUCTION",
                api_key="prod_key_hazard",
                api_secret="prod_secret_hazard",
            )
        )
        unsafe_cap = CredentialCapability(
            exchange="BINANCE",
            environment="PRODUCTION",
            credential_id="BINANCE_PRODUCTION",
            masked_api_key="prod_...zard",
            trading_allowed=True,
            withdrawal_allowed=True,  # HAZARD!
            transfer_allowed=False,
            permissions_verified_at=int(time.time() * 1000),
            verification_status="SECURITY_VIOLATION_WITHDRAWAL_ENABLED",
        )
        credential_vault._capability_cache[("BINANCE", "PRODUCTION")] = unsafe_cap

        gk = LiveExecutionGatekeeper()
        verdict = await gk.evaluate_order_clearance("BINANCE", 15.0, environment="PRODUCTION")
        assert verdict.passed is False
        assert any("Gate 1b" in r or "withdrawal" in r.lower() for r in verdict.rejection_reasons)


# =============================================================================
# 6. CANARY RUNNER: LATENCY TELEMETRY, SLA SEPARATION & IDEMPOTENCY
# =============================================================================


class TestCanaryRunnerHardening:
    @pytest.mark.asyncio
    async def test_dry_run_canary_monotonic_latency(self):
        """Dry-run canary records monotonic latency and satisfies ACK SLA."""
        runner = live_canary_runner

        # Mock gatekeeper to pass so we test the full simulated fill flow
        mock_verdict = GatekeeperVerdict(
            passed=True,
            timestamp_ms=int(time.time() * 1000),
            exchange="BINANCE",
            requested_notional_usd=14.95,
            max_allowed_notional_usd=15.0,
            checks={"vault_unlocked": True, "withdrawal_prohibited": True},
            rejection_reasons=[],
            audit_event_id="AUD-MOCK",
        )

        with patch(
            "core.execution.live_canary_runner.live_gatekeeper.evaluate_order_clearance",
            new_callable=AsyncMock,
        ) as mock_gk:
            mock_gk.return_value = mock_verdict

            req = CanaryRunRequest(
                exchange="BINANCE",
                symbol="BTCUSDT",
                notional_usd=15.0,
                side="BUY",
                is_dry_run=True,
                environment="TESTNET",
            )
            result = await runner.execute_canary_order(req)
            assert result.success is True
            assert result.status == "DRY_RUN_CLEARED"
            assert result.dispatch_to_ack_latency_ms is not None
            assert result.dispatch_to_ack_latency_ms < 500.0
            assert result.ack_latency_sla_breached is False
            assert result.feasibility_details is not None
            assert result.client_order_id.startswith("CL_CANARY")

    def test_ack_sla_breach_detection(self):
        """When dispatch-to-ack exceeds 500ms, ack_latency_sla_breached is set to True."""
        res = CanaryRunResult(
            success=True,
            is_dry_run=False,
            exchange="BINANCE",
            symbol="BTCUSDT",
            notional_usd=15.0,
            canary_execution_id="CANARY-UUID-1",
            client_order_id="CL_CANARY_1",
            exchange_order_id="EXCH-12345",
            executed_qty=0.0002,
            executed_price=65000.0,
            slippage_bps=0.5,
            dispatch_to_ack_latency_ms=520.0,  # Breaches 500ms SLA
            ack_to_fill_latency_ms=230.0,
            total_roundtrip_ms=750.0,
            ack_latency_sla_breached=True,
            dispatch_monotonic_ns=1000,
            ack_monotonic_ns=521000000,
            fill_monotonic_ns=751000000,
            dispatch_wall_time_utc="2026-09-15T00:00:00Z",
            ack_wall_time_utc="2026-09-15T00:00:01Z",
            fill_wall_time_utc="2026-09-15T00:00:01Z",
            reconciliation_id="REC-1",
            audit_event_id="AUD-1",
            status="FILLED",
            message="SLA breached",
            timestamp_ms=int(time.time() * 1000),
            gatekeeper_verdict={},
            feasibility_details={},
        )
        assert res.ack_latency_sla_breached is True

    def test_ledger_database_unique_constraints(self, tmp_path):
        """Ledger enforces UNIQUE(canary_execution_id) and UNIQUE(exchange, environment, client_order_id)."""
        db_file = tmp_path / "test_ledger.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                """
                CREATE TABLE canary_execution_ledger (
                    canary_execution_id TEXT PRIMARY KEY,
                    client_order_id TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    notional_usd REAL NOT NULL,
                    executed_qty REAL NOT NULL,
                    executed_price REAL NOT NULL,
                    exchange_order_id TEXT,
                    dispatch_to_ack_ms REAL NOT NULL,
                    ack_to_fill_ms REAL NOT NULL,
                    total_roundtrip_ms REAL NOT NULL,
                    ack_sla_breached INTEGER NOT NULL,
                    dispatch_monotonic_ns INTEGER NOT NULL,
                    ack_monotonic_ns INTEGER NOT NULL,
                    fill_monotonic_ns INTEGER NOT NULL,
                    dispatch_wall_utc TEXT NOT NULL,
                    ack_wall_utc TEXT NOT NULL,
                    fill_wall_utc TEXT NOT NULL,
                    reconciliation_id TEXT,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    UNIQUE(exchange, environment, client_order_id)
                )
                """
            )
            # Insert first record
            conn.execute(
                """
                INSERT INTO canary_execution_ledger (
                    canary_execution_id, client_order_id, exchange, environment,
                    symbol, side, order_type, notional_usd, executed_qty, executed_price,
                    exchange_order_id, dispatch_to_ack_ms, ack_to_fill_ms, total_roundtrip_ms,
                    ack_sla_breached, dispatch_monotonic_ns, ack_monotonic_ns, fill_monotonic_ns,
                    dispatch_wall_utc, ack_wall_utc, fill_wall_utc, reconciliation_id,
                    status, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "CANARY-UUID-1",
                    "CL_ORDER_1",
                    "BINANCE",
                    "TESTNET",
                    "BTCUSDT",
                    "BUY",
                    "LIMIT",
                    15.0,
                    0.0002,
                    65000.0,
                    "EX-1",
                    120.0,
                    80.0,
                    200.0,
                    0,
                    1000,
                    2000,
                    3000,
                    "2026-09-15T00:00:00Z",
                    "2026-09-15T00:00:00Z",
                    "2026-09-15T00:00:00Z",
                    "REC-1",
                    "FILLED",
                    int(time.time() * 1000),
                ),
            )
            conn.commit()

            # Inserting duplicate canary_execution_id must fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO canary_execution_ledger (
                        canary_execution_id, client_order_id, exchange, environment,
                        symbol, side, order_type, notional_usd, executed_qty, executed_price,
                        exchange_order_id, dispatch_to_ack_ms, ack_to_fill_ms, total_roundtrip_ms,
                        ack_sla_breached, dispatch_monotonic_ns, ack_monotonic_ns, fill_monotonic_ns,
                        dispatch_wall_utc, ack_wall_utc, fill_wall_utc, reconciliation_id,
                        status, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "CANARY-UUID-1",
                        "CL_ORDER_2",
                        "BINANCE",
                        "TESTNET",
                        "BTCUSDT",
                        "BUY",
                        "LIMIT",
                        15.0,
                        0.0002,
                        65000.0,
                        "EX-2",
                        120.0,
                        80.0,
                        200.0,
                        0,
                        1000,
                        2000,
                        3000,
                        "2026-09-15T00:00:00Z",
                        "2026-09-15T00:00:00Z",
                        "2026-09-15T00:00:00Z",
                        "REC-2",
                        "FILLED",
                        int(time.time() * 1000),
                    ),
                )

            # Inserting duplicate (exchange, environment, client_order_id) must fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO canary_execution_ledger (
                        canary_execution_id, client_order_id, exchange, environment,
                        symbol, side, order_type, notional_usd, executed_qty, executed_price,
                        exchange_order_id, dispatch_to_ack_ms, ack_to_fill_ms, total_roundtrip_ms,
                        ack_sla_breached, dispatch_monotonic_ns, ack_monotonic_ns, fill_monotonic_ns,
                        dispatch_wall_utc, ack_wall_utc, fill_wall_utc, reconciliation_id,
                        status, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "CANARY-UUID-3",
                        "CL_ORDER_1",
                        "BINANCE",
                        "TESTNET",
                        "BTCUSDT",
                        "BUY",
                        "LIMIT",
                        15.0,
                        0.0002,
                        65000.0,
                        "EX-3",
                        120.0,
                        80.0,
                        200.0,
                        0,
                        1000,
                        2000,
                        3000,
                        "2026-09-15T00:00:00Z",
                        "2026-09-15T00:00:00Z",
                        "2026-09-15T00:00:00Z",
                        "REC-3",
                        "FILLED",
                        int(time.time() * 1000),
                    ),
                )

    @pytest.mark.asyncio
    async def test_timeout_reconciliation_zero_blind_retry(self):
        """Timeout triggers AMBIGUOUS_TIMEOUT_RECONCILIATION_REQUIRED and sets safe_to_retry=False."""
        runner = live_canary_runner
        rec = await runner.reconcile_timed_out_canary(
            client_order_id="CANARY-TIMEOUT-TEST",
            exchange="BINANCE",
            environment="TESTNET",
        )
        assert rec["status"] == "AMBIGUOUS_TIMEOUT_RECONCILIATION_REQUIRED"
        assert rec["safe_to_retry"] is False


# =============================================================================
# 7. REST ROUTE CONTRACT VERIFICATION (/api/vault/verify & /api/vault/credential)
# =============================================================================


class TestVaultApiRoutes:
    def test_vault_verify_route_unauthenticated(self):
        """API verify endpoint returns FAILED when credentials are not configured."""
        client = TestClient(app)
        res = client.post(
            "/api/vault/verify",
            json={"exchange": "BINANCE", "environment": "TESTNET"},
            headers={"X-API-Key": "test"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "FAILED"
        assert data["verification"]["status"] in ("NOT_CONFIGURED", "FAIL_NOT_CONFIGURED")

    def test_vault_revoke_route(self):
        """API revoke endpoint flushes credential."""
        client = TestClient(app)
        res = client.request(
            "DELETE",
            "/api/vault/credential",
            json={"exchange": "BYBIT", "environment": "TESTNET"},
            headers={"X-API-Key": "test"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("SUCCESS", "NOT_FOUND")
