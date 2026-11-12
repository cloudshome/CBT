"""
tests/test_daemon_lease_revocation.py
======================================
Verifies Cryptographic Operator Daemon Lease lifecycle:
1. Registration & issuance of Daemon Lease for Tier 1 / Tier 2.
2. Successful validation of active lease for matching PID and host fingerprint.
3. Fail-closed rejection when tier cap is exceeded.
4. Irrevocable revocation when emergency kill switch is activated.
5. Verification that live_gatekeeper respects daemon lease for autonomous execution.
"""

import os

import pytest

from core.auth.hardware_key import get_host_fingerprint, hardware_key_manager
from core.auth.security_store import security_store
from core.execution.kill_switch import live_kill_switch
from core.execution.live_gatekeeper import live_gatekeeper


@pytest.fixture(autouse=True)
def clean_security_state():
    """Ensure clean security state for test run."""
    hardware_key_manager.revoke_all_daemon_leases(reason="TEST_SETUP")
    hardware_key_manager.revoke_clearance(reason="TEST_SETUP")
    yield
    hardware_key_manager.revoke_all_daemon_leases(reason="TEST_TEARDOWN")
    live_kill_switch.deactivate(reason="TEST_TEARDOWN")


def test_daemon_lease_creation_and_validation():
    """Test issuing and validating a 24-hour cryptographic daemon lease."""
    # Ensure dummy credential exists
    cred = security_store.save_credential(
        credential_id="test_cred_daemon_1",
        user_id="test_operator",
        public_key_cose=b"dummy_cose_key_32_bytes_long_1234",
        sign_counter=0,
        rp_id=hardware_key_manager.rp_id,
        label="Test YubiKey 5C",
    )
    assert cred.is_active

    # Issue lease for Tier 1 Canary
    lease = hardware_key_manager.create_daemon_lease(
        credential_id="test_cred_daemon_1",
        operator_id="test_operator",
        tier_cap="TIER_1_CANARY",
        max_daily_loss_pct=0.03,
        ttl_seconds=3600,
    )
    assert lease.is_valid()
    assert lease.tier_cap == "TIER_1_CANARY"
    assert lease.pid == os.getpid()
    assert lease.host_fingerprint == get_host_fingerprint()

    # Validate active lease for TIER_1_CANARY
    is_valid, active_lease, err = hardware_key_manager.check_daemon_lease(tier="TIER_1_CANARY")
    assert is_valid is True
    assert active_lease is not None
    assert err is None

    # Validate tier cap rejection: requesting TIER_2 when capped at TIER_1 must fail closed
    is_valid_t2, _, err_t2 = hardware_key_manager.check_daemon_lease(tier="TIER_2_MICRO_LIVE")
    assert is_valid_t2 is False
    assert "TIER_CAP_EXCEEDED" in str(err_t2) or "TIER_EXCEEDED" in str(err_t2)


def test_daemon_lease_revocation_on_kill_switch():
    """Emergency kill switch activation must immediately and irrevocably revoke daemon leases."""
    security_store.save_credential(
        credential_id="test_cred_daemon_ks",
        user_id="test_operator",
        public_key_cose=b"dummy_cose_key_32_bytes_long_1234",
        sign_counter=0,
        rp_id=hardware_key_manager.rp_id,
        label="Test Key",
    )

    lease = hardware_key_manager.create_daemon_lease(
        credential_id="test_cred_daemon_ks",
        operator_id="test_operator",
        tier_cap="TIER_2_MICRO_LIVE",
        ttl_seconds=3600,
    )
    assert lease.is_valid()

    # Verify active lease is valid
    is_valid, _, _ = hardware_key_manager.check_daemon_lease(tier="TIER_2_MICRO_LIVE")
    assert is_valid is True

    # TRIGGER KILL SWITCH
    live_kill_switch.activate(reason="EMERGENCY_ANOMALY_TEST", operator_id="TEST_SENTINEL")

    # Verify daemon lease is now IMMEDIATELY REVOKED
    is_valid_after, revoked_lease, err = hardware_key_manager.check_daemon_lease(
        tier="TIER_2_MICRO_LIVE"
    )
    assert is_valid_after is False
    assert "REVOKED" in str(err)
    if revoked_lease:
        assert revoked_lease.is_revoked is True
        assert "KILL_SWITCH" in str(revoked_lease.revocation_reason)


@pytest.mark.asyncio
async def test_live_gatekeeper_respects_daemon_lease():
    """live_gatekeeper Check #8 evaluates autonomous orders against daemon lease."""
    security_store.save_credential(
        credential_id="test_cred_gatekeeper",
        user_id="test_operator",
        public_key_cose=b"dummy_cose_key_32_bytes_long_1234",
        sign_counter=0,
        rp_id=hardware_key_manager.rp_id,
        label="Test Key",
    )

    # Issue Tier 1 Canary Lease
    hardware_key_manager.create_daemon_lease(
        credential_id="test_cred_gatekeeper",
        tier_cap="TIER_1_CANARY",
        ttl_seconds=3600,
    )

    # Test autonomous canary order evaluation ($10 notional)
    verdict = await live_gatekeeper.evaluate_order_clearance(
        exchange="BINANCE",
        order_notional_usd=10.0,
        environment="PRODUCTION",
        session_id="AUTONOMOUS_DAEMON_LOOP",
    )

    # Check #8 should pass via the active daemon lease!
    assert verdict.checks["hardware_clearance_active"] is True
