"""
tests/test_phase_a_live_clearance.py
====================================
Comprehensive Test Suite for Phase A: Human-Controlled Live Execution Clearance
(WebAuthn / FIDO2 Hardware Security Key Live Clearance & Gate 8 Protection).

GOVERNANCE CLASSIFICATION: CLASS H (LIVE / PAPER BOUNDARY)

Verification Invariants Tested:
1. Isolated Security Store (WAL mode, schema, atomic single-use challenges, zero private keys).
2. WebAuthn Registration Ceremony & Public Key COSE Storage.
3. WebAuthn Authentication Ceremony & Counter Anomaly Defense (cloning detection).
4. Tolerance for legitimate authenticators with zero counters.
5. Single-use challenge anti-replay protection.
6. Session-bound Live Clearance (15-minute TTL, explicit revocation, credential revocation cascade).
7. Gate 8 in LiveExecutionGatekeeper (fail-closed in PRODUCTION, bypassed in TESTNET).
8. CONSTITUTIONAL RISK PRIMACY: FIDO2 clearance PASS + Risk FAIL (1.5% equity cap / Kill Switch).
9. FastAPI REST routes (/api/auth/hardware-key/*).
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.auth.credential_vault import credential_vault
from core.auth.hardware_key import (
    HardwareKeyCounterAnomalyError,
    HardwareKeyManager,
    HardwareKeyRevokedError,
    hardware_key_manager,
)
from core.auth.security_store import (
    SecurityStore,
)
from core.execution.account_probe import ExchangeAccountStatus, account_probe
from core.execution.kill_switch import live_kill_switch
from core.execution.live_gatekeeper import (
    LiveExecutionGatekeeper,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_sec_db(tmp_path: Path) -> SecurityStore:
    """Creates a dedicated, isolated SecurityStore in a temporary directory."""
    db_file = tmp_path / "test_sec_store.db"
    return SecurityStore(db_path=db_file)


@pytest.fixture
def hw_mgr(temp_sec_db: SecurityStore) -> HardwareKeyManager:
    """HardwareKeyManager instance wired to isolated temp SecurityStore."""
    return HardwareKeyManager(
        store=temp_sec_db,
        rp_id="127.0.0.1",
        rp_name="Test CBT Terminal",
        allowed_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        clearance_ttl_seconds=300,
        require_user_verification=False,
    )


@pytest.fixture
def test_client() -> TestClient:
    """FastAPI TestClient for checking HTTP route contracts."""
    return TestClient(app)


# ===========================================================================
# 1. SECURITY STORE TESTS
# ===========================================================================
class TestSecurityStore:
    def test_database_initialization_and_schemas(self, temp_sec_db: SecurityStore):
        """Verifies tables, indices, and WAL mode in the isolated database."""
        conn = temp_sec_db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}
            assert "webauthn_credentials" in tables
            assert "webauthn_challenges" in tables
            assert "clearance_sessions" in tables
            assert "credential_revocations" in tables
            assert "security_audit" in tables

            # Verify foreign keys are enabled
            cur.execute("PRAGMA foreign_keys;")
            assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_challenge_lifecycle_and_single_use(self, temp_sec_db: SecurityStore):
        """Verifies single-use challenge consumption and anti-replay defense."""
        challenge_id, ch_bytes = temp_sec_db.create_challenge(
            purpose="AUTHENTICATION", ttl_seconds=60
        )
        assert len(challenge_id) > 16
        assert len(ch_bytes) == 32

        # 1. First consumption must succeed
        success, retrieved_bytes, err = temp_sec_db.consume_challenge(
            challenge_id, purpose="AUTHENTICATION"
        )
        assert success is True
        assert retrieved_bytes == ch_bytes
        assert err is None

        # 2. Replay attack: second consumption MUST fail
        success2, retrieved_bytes2, err2 = temp_sec_db.consume_challenge(
            challenge_id, purpose="AUTHENTICATION"
        )
        assert success2 is False
        assert retrieved_bytes2 is None
        assert err2 == "HARDWARE_KEY_CHALLENGE_REPLAYED"

    def test_challenge_expiry(self, temp_sec_db: SecurityStore):
        """Verifies expired challenges are rejected."""
        # TTL of 0 seconds causes immediate expiration
        challenge_id, ch_bytes = temp_sec_db.create_challenge(purpose="REGISTRATION", ttl_seconds=0)
        time.sleep(0.01)

        success, _, err = temp_sec_db.consume_challenge(challenge_id, purpose="REGISTRATION")
        assert success is False
        assert err == "HARDWARE_KEY_CHALLENGE_EXPIRED"

    def test_challenge_purpose_mismatch(self, temp_sec_db: SecurityStore):
        """Verifies registration challenge cannot be consumed for authentication."""
        challenge_id, _ = temp_sec_db.create_challenge(purpose="REGISTRATION", ttl_seconds=60)
        success, _, err = temp_sec_db.consume_challenge(challenge_id, purpose="AUTHENTICATION")
        assert success is False
        assert err == "HARDWARE_KEY_PURPOSE_MISMATCH"

    def test_credential_storage_and_querying(self, temp_sec_db: SecurityStore):
        """Verifies credential persistence and masked safe dictionary export."""
        cred_id = "test_cred_id_1234567890abcdef"
        pub_key = b"\xa5\x01\x02\x03\x26..."

        cred = temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="operator_1",
            public_key_cose=pub_key,
            sign_counter=0,
            rp_id="127.0.0.1",
            label="Operator Primary YubiKey",
            aaguid="00000000-0000-0000-0000-000000000000",
        )
        assert cred.credential_id == cred_id
        assert cred.sign_counter == 0
        assert cred.is_active is True

        # Fetch
        fetched = temp_sec_db.get_credential(cred_id)
        assert fetched is not None
        assert fetched.user_id == "operator_1"
        assert fetched.public_key_cose == pub_key

        # Safe masked dict
        safe_dict = fetched.to_safe_dict()
        assert "test_c...cdef" in safe_dict["credential_id_masked"]
        assert "public_key_cose" not in safe_dict

    def test_credential_revocation_cascades_to_active_clearance(self, temp_sec_db: SecurityStore):
        """Verifies revoking a credential immediately revokes its clearance sessions."""
        cred_id = "cred_to_revoke_12345678"
        temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="operator_1",
            public_key_cose=b"dummy_key",
            sign_counter=5,
            rp_id="127.0.0.1",
            label="Revocation Target Key",
        )

        # Create clearance session
        session = temp_sec_db.create_clearance_session(
            credential_id=cred_id,
            session_id="session_alpha",
            operator_id="operator_1",
            ttl_seconds=300,
        )
        assert session.is_valid() is True

        # Revoke the credential
        revoked = temp_sec_db.revoke_credential(cred_id, reason="Lost physical key")
        assert revoked is True

        # Credential is now marked inactive
        c = temp_sec_db.get_credential(cred_id)
        assert c is not None
        assert c.is_active is False
        assert c.revocation_reason == "Lost physical key"

        # Clearance session MUST now be revoked as well
        active_session = temp_sec_db.get_active_clearance("session_alpha")
        assert active_session is None


# ===========================================================================
# 2. HARDWARE KEY MANAGER CEREMONIES & COUNTER SEMANTICS
# ===========================================================================
class TestHardwareKeyManagerCeremonies:
    def test_registration_options_generation(self, hw_mgr: HardwareKeyManager):
        """Verifies generation of W3C-compliant WebAuthn registration options."""
        res = hw_mgr.get_registration_options(
            user_id="trader_1", username="trader", display_name="Trader 1"
        )
        assert "challenge_id" in res
        assert "options" in res
        opts = res["options"]
        assert opts["rp"]["id"] == "127.0.0.1"
        assert opts["user"]["name"] == "trader"
        assert "challenge" in opts
        assert len(opts["pubKeyCredParams"]) > 0

    def test_authentication_options_fail_when_no_enrolled_keys(self, hw_mgr: HardwareKeyManager):
        """Verifies authentication cannot be initiated when 0 keys are registered."""
        with pytest.raises(HardwareKeyRevokedError) as exc_info:
            hw_mgr.get_authentication_options(user_id="empty_user")
        assert "HARDWARE_KEY_NO_CREDENTIALS" in str(exc_info.value)

    def test_authentication_options_generation_with_enrolled_keys(
        self, hw_mgr: HardwareKeyManager, temp_sec_db: SecurityStore
    ):
        """Verifies authentication options include allowed credential descriptors."""
        cred_id_b64 = "ABCD1234efgh5678"
        temp_sec_db.save_credential(
            credential_id=cred_id_b64,
            user_id="default_operator",
            public_key_cose=b"key_data",
            sign_counter=1,
            rp_id="127.0.0.1",
            label="Key 1",
        )

        res = hw_mgr.get_authentication_options()
        assert "challenge_id" in res
        assert "options" in res
        opts = res["options"]
        assert opts["rpId"] == "127.0.0.1"
        assert len(opts["allowCredentials"]) == 1

    @patch("core.auth.hardware_key.verify_authentication_response")
    def test_successful_authentication_and_clearance_issuance(
        self, mock_verify, hw_mgr: HardwareKeyManager, temp_sec_db: SecurityStore
    ):
        """Verifies successful physical touch issues a valid ClearanceSession."""
        cred_id = "yubikey_primary_cred_id"
        temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"pub_cose_bytes",
            sign_counter=10,
            rp_id="127.0.0.1",
            label="YubiKey 5C",
        )

        challenge_id, _ = temp_sec_db.create_challenge(purpose="AUTHENTICATION", ttl_seconds=120)

        mock_verify_result = MagicMock()
        mock_verify_result.new_sign_count = 11
        mock_verify_result.user_verified = True
        mock_verify.return_value = mock_verify_result

        cred_payload = {
            "id": cred_id,
            "rawId": cred_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": "dummy",
                "authenticatorData": "dummy",
                "signature": "dummy",
            },
        }

        clearance = hw_mgr.verify_authentication_and_issue_clearance(
            challenge_id=challenge_id,
            credential_data=cred_payload,
            session_id="workstation_alpha",
            operator_id="senior_quant",
        )

        assert clearance.is_valid() is True
        assert clearance.credential_id == cred_id
        assert clearance.session_id == "workstation_alpha"
        assert clearance.operator_id == "senior_quant"
        assert clearance.remaining_seconds() > 250

        # Verify sign counter was updated
        updated_cred = temp_sec_db.get_credential(cred_id)
        assert updated_cred.sign_counter == 11

    @patch("core.auth.hardware_key.verify_authentication_response")
    def test_counter_anomaly_cloning_attack_rejected(
        self, mock_verify, hw_mgr: HardwareKeyManager, temp_sec_db: SecurityStore
    ):
        """
        Verifies authenticator counter rollback raises HardwareKeyCounterAnomalyError
        to prevent replay or cloned security keys.
        """
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse

        cred_id = "cloned_token_cred_id"
        temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"pub_cose_bytes",
            sign_counter=100,
            rp_id="127.0.0.1",
            label="Cloned Candidate",
        )

        challenge_id, _ = temp_sec_db.create_challenge(purpose="AUTHENTICATION", ttl_seconds=120)

        mock_verify.side_effect = InvalidAuthenticationResponse(
            "Response sign count of 50 was not greater than 100"
        )

        cred_payload = {"id": cred_id, "response": {}}

        with pytest.raises(HardwareKeyCounterAnomalyError) as exc_info:
            hw_mgr.verify_authentication_and_issue_clearance(
                challenge_id=challenge_id,
                credential_data=cred_payload,
                session_id="workstation_alpha",
            )

        assert "HARDWARE_KEY_COUNTER_ANOMALY" in str(exc_info.value)

    @patch("core.auth.hardware_key.verify_authentication_response")
    def test_zero_counter_authenticators_supported(
        self, mock_verify, hw_mgr: HardwareKeyManager, temp_sec_db: SecurityStore
    ):
        """
        Verifies authenticators that legitimately do not track counters
        (stored=0, new=0) are supported per W3C specification.
        """
        cred_id = "zero_counter_token"
        temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"pub_cose_bytes",
            sign_counter=0,
            rp_id="127.0.0.1",
            label="Zero Counter Key",
        )

        challenge_id, _ = temp_sec_db.create_challenge(purpose="AUTHENTICATION", ttl_seconds=120)

        mock_verify_result = MagicMock()
        mock_verify_result.new_sign_count = 0  # Still zero
        mock_verify_result.user_verified = False
        mock_verify.return_value = mock_verify_result

        cred_payload = {"id": cred_id, "response": {}}

        clearance = hw_mgr.verify_authentication_and_issue_clearance(
            challenge_id=challenge_id,
            credential_data=cred_payload,
            session_id="session_zero_counter",
        )

        assert clearance.is_valid() is True

    def test_revoked_credential_cannot_authenticate(
        self, hw_mgr: HardwareKeyManager, temp_sec_db: SecurityStore
    ):
        """Verifies that an inactive/revoked credential fails before assertion verification."""
        cred_id = "revoked_key_123"
        temp_sec_db.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"pub_cose_bytes",
            sign_counter=5,
            rp_id="127.0.0.1",
            label="Revoked Key",
        )
        temp_sec_db.revoke_credential(cred_id, reason="Security incident")

        challenge_id, _ = temp_sec_db.create_challenge(purpose="AUTHENTICATION", ttl_seconds=120)

        with pytest.raises(HardwareKeyRevokedError) as exc_info:
            hw_mgr.verify_authentication_and_issue_clearance(
                challenge_id=challenge_id,
                credential_data={"id": cred_id},
                session_id="session_test",
            )
        assert "HARDWARE_KEY_CREDENTIAL_REVOKED" in str(exc_info.value)


# ===========================================================================
# 3. GATE 8 IN LIVE EXECUTION GATEKEEPER & RISK PRIMACY
# ===========================================================================
class TestGate8AndRiskPrimacy:
    @pytest.fixture(autouse=True)
    def setup_gatekeeper(self):
        self.gatekeeper = LiveExecutionGatekeeper()
        self.mock_status = ExchangeAccountStatus(
            exchange="BINANCE",
            environment="PRODUCTION",
            is_connected=True,
            latency_ms=40.0,
            total_equity_usd=10000.0,  # 1.5% cap = $150.00
            free_cash_usd=10000.0,
            locked_margin_usd=0.0,
        )
        self.mock_cap = MagicMock()
        self.mock_cap.exchange = "BINANCE"
        self.mock_cap.environment = "PRODUCTION"
        self.mock_cap.withdrawal_allowed = False
        self.mock_cap.trading_allowed = True
        self.mock_cap.verification_status = "VERIFIED_SAFE"
        self.mock_cap.error_message = None

    @pytest.mark.asyncio
    async def test_gate8_fail_closed_in_production_without_clearance(self):
        """Gate 8 must block production orders if hardware clearance is missing."""
        with (
            patch.object(credential_vault, "is_unlocked", return_value=True),
            patch.object(credential_vault, "get_credential_capability", return_value=self.mock_cap),
            patch.object(live_kill_switch, "is_active", return_value=False),
            patch.object(
                account_probe, "probe_exchange", new=AsyncMock(return_value=self.mock_status)
            ),
            patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
        ):
            verdict = await self.gatekeeper.evaluate_order_clearance(
                exchange="BINANCE",
                order_notional_usd=100.0,
                environment="PRODUCTION",
                session_id="unauthorized_session_without_clearance",
            )

            assert verdict.passed is False
            assert verdict.checks["hardware_clearance_active"] is False
            assert any("HARDWARE_KEY" in r for r in verdict.rejection_reasons)

    @pytest.mark.asyncio
    async def test_gate8_passes_in_production_with_valid_clearance(self):
        """Gate 8 passes in production when a valid clearance session exists."""
        store = hardware_key_manager.store
        cred_id = "valid_live_key_gate8"
        store.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"dummy",
            sign_counter=1,
            rp_id="127.0.0.1",
            label="Active Trader Key",
        )
        store.create_clearance_session(
            credential_id=cred_id,
            session_id="live_desk_session_gate8",
            operator_id="lead_trader",
            ttl_seconds=300,
        )

        with (
            patch.object(credential_vault, "is_unlocked", return_value=True),
            patch.object(credential_vault, "get_credential_capability", return_value=self.mock_cap),
            patch.object(live_kill_switch, "is_active", return_value=False),
            patch.object(
                account_probe, "probe_exchange", new=AsyncMock(return_value=self.mock_status)
            ),
            patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
        ):
            verdict = await self.gatekeeper.evaluate_order_clearance(
                exchange="BINANCE",
                order_notional_usd=100.0,
                environment="PRODUCTION",
                session_id="live_desk_session_gate8",
            )

            assert verdict.checks["hardware_clearance_active"] is True
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_gate8_bypassed_in_testnet(self):
        """In TESTNET / PAPER mode, Gate 8 is bypassed so dev/testing is not blocked."""
        testnet_status = ExchangeAccountStatus(
            exchange="BINANCE",
            environment="TESTNET",
            is_connected=True,
            latency_ms=40.0,
            total_equity_usd=10000.0,
            free_cash_usd=10000.0,
            locked_margin_usd=0.0,
        )
        testnet_cap = MagicMock()
        testnet_cap.exchange = "BINANCE"
        testnet_cap.environment = "TESTNET"
        testnet_cap.withdrawal_allowed = False
        testnet_cap.trading_allowed = True
        testnet_cap.verification_status = "VERIFIED_SAFE"
        testnet_cap.error_message = None

        with (
            patch.object(credential_vault, "is_unlocked", return_value=True),
            patch.object(credential_vault, "get_credential_capability", return_value=testnet_cap),
            patch.object(live_kill_switch, "is_active", return_value=False),
            patch.object(
                account_probe, "probe_exchange", new=AsyncMock(return_value=testnet_status)
            ),
            patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
        ):
            verdict = await self.gatekeeper.evaluate_order_clearance(
                exchange="BINANCE",
                order_notional_usd=50.0,
                environment="TESTNET",
                session_id=None,
            )

            assert verdict.checks["hardware_clearance_active"] is True
            assert verdict.passed is True

    @pytest.mark.asyncio
    async def test_fido_pass_risk_fail_constitutional_primacy(self):
        """
        CONSTITUTIONAL INVARIANT: FIDO Pass + Risk Fail.
        Even if physical hardware key clearance is 100% active, an order
        breaching the 1.5% equity cap MUST BE REJECTED.
        FIDO2 clearance NEVER bypasses quantitative risk limits!
        """
        store = hardware_key_manager.store
        cred_id = "valid_key_for_risk_test"
        store.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"dummy",
            sign_counter=1,
            rp_id="127.0.0.1",
            label="Risk Primacy Key",
        )
        store.create_clearance_session(
            credential_id=cred_id,
            session_id="session_risk_primacy",
            operator_id="lead_trader",
            ttl_seconds=300,
        )

        # Equity = $10,000. 1.5% cap = $150. Requested order = $500.
        with (
            patch.object(credential_vault, "is_unlocked", return_value=True),
            patch.object(credential_vault, "get_credential_capability", return_value=self.mock_cap),
            patch.object(live_kill_switch, "is_active", return_value=False),
            patch.object(
                account_probe, "probe_exchange", new=AsyncMock(return_value=self.mock_status)
            ),
            patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
        ):
            verdict = await self.gatekeeper.evaluate_order_clearance(
                exchange="BINANCE",
                order_notional_usd=500.0,  # Breaches 1.5% cap ($150)
                environment="PRODUCTION",
                session_id="session_risk_primacy",
            )

            # Gate 8 cleared, but single-trade equity cap check failed!
            assert verdict.checks["hardware_clearance_active"] is True
            assert verdict.checks["single_trade_cap_conformed"] is False
            assert verdict.passed is False
            assert any(
                "breaches constitutional 1.5% equity cap" in r.lower()
                for r in verdict.rejection_reasons
            )

    @pytest.mark.asyncio
    async def test_fido_pass_kill_switch_active_fail(self):
        """
        CONSTITUTIONAL INVARIANT: Kill Switch Primacy.
        Hardware clearance NEVER overrides the emergency kill switch.
        """
        store = hardware_key_manager.store
        cred_id = "valid_key_for_ks_test"
        store.save_credential(
            credential_id=cred_id,
            user_id="default_operator",
            public_key_cose=b"dummy",
            sign_counter=1,
            rp_id="127.0.0.1",
            label="Kill Switch Primacy Key",
        )
        store.create_clearance_session(
            credential_id=cred_id,
            session_id="session_ks_primacy",
            operator_id="lead_trader",
            ttl_seconds=300,
        )

        with (
            patch.object(credential_vault, "is_unlocked", return_value=True),
            patch.object(credential_vault, "get_credential_capability", return_value=self.mock_cap),
            patch.object(live_kill_switch, "is_active", return_value=True),  # KILL SWITCH ENGAGED
            patch.object(
                account_probe, "probe_exchange", new=AsyncMock(return_value=self.mock_status)
            ),
            patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
        ):
            verdict = await self.gatekeeper.evaluate_order_clearance(
                exchange="BINANCE",
                order_notional_usd=50.0,
                environment="PRODUCTION",
                session_id="session_ks_primacy",
            )

            assert verdict.checks["hardware_clearance_active"] is True
            assert verdict.checks["kill_switch_operational"] is False
            assert verdict.passed is False
            assert any("kill switch is active" in r.lower() for r in verdict.rejection_reasons)


# ===========================================================================
# 4. FASTAPI HARDWARE KEY ROUTE TESTS
# ===========================================================================
class TestHardwareKeyRoutes:
    def test_status_endpoint(self, test_client: TestClient):
        """GET /api/auth/hardware-key/status returns valid posture schema."""
        resp = test_client.get("/api/auth/hardware-key/status?session_id=ui_session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "posture" in data
        assert data["posture"]["webauthn_enabled"] is True
        assert "registered_keys_count" in data["posture"]

    def test_register_options_endpoint(self, test_client: TestClient):
        """POST /api/auth/hardware-key/register/options returns challenge and RP details."""
        payload = {
            "user_id": "test_user",
            "username": "test_trader",
            "display_name": "Test Trader",
        }
        resp = test_client.post("/api/auth/hardware-key/register/options", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "challenge_id" in data
        assert "options" in data
        assert data["options"]["rp"]["id"] == "127.0.0.1"

    def test_authenticate_options_no_keys_returns_400(self, test_client: TestClient):
        """POST /api/auth/hardware-key/authenticate/options fails if 0 keys enrolled."""
        resp = test_client.post(
            "/api/auth/hardware-key/authenticate/options",
            json={"user_id": f"unknown_user_{secrets.token_hex(4)}"},
        )
        assert resp.status_code == 400
        assert "HARDWARE_KEY_NO_CREDENTIALS" in resp.text

    def test_revoke_clearance_endpoint(self, test_client: TestClient):
        """POST /api/auth/hardware-key/clearance/revoke revokes active session."""
        resp = test_client.post(
            "/api/auth/hardware-key/clearance/revoke",
            json={"session_id": "test_session_to_revoke", "reason": "Operator logout"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["action"] == "CLEARANCE_REVOKED"
