"""
tests/execution/test_milestone21_endpoint_safety.py
===================================================
Milestone 21: Endpoint Safety & Credential Scope Validation Suite.

Verifies:
1. BLOCKER 1 (P0): Structural endpoint isolation via canonical hostname allowlist.
2. Immediate rejection of production hostnames across REST & WebSocket transports.
3. Strict rejection of arbitrary, spoofed, or unencrypted endpoints.
4. Cross-environment venue isolation (Binance endpoints rejected under Bybit env).
5. Immutable capital firewall: EndpointPolicy.REAL_CAPITAL_ENABLED is permanently False.
6. Credential scope enforcement: Zero withdrawal or transfer permissions allowed.
7. Secret masking and credential permission auditor.
"""

from __future__ import annotations

import pytest

from core.execution.testnet.credential_policy import (
    CredentialPolicy,
    CredentialScopeError,
    TestnetCredentials,
    mask_secret,
)
from core.execution.testnet.endpoint_policy import (
    EndpointPolicy,
    EndpointSecurityBreachError,
    Environment,
)
from core.execution.testnet.rest_transport import RestTransport
from core.execution.testnet.websocket_transport import WebSocketTransport

# =============================================================================
# 1. Structural Endpoint Isolation & Canonical Allowlist (Blocker 1)
# =============================================================================


def test_real_capital_permanently_disabled():
    """Capital firewall invariant: REAL_CAPITAL_ENABLED must be structurally False."""
    assert EndpointPolicy.REAL_CAPITAL_ENABLED is False
    with pytest.raises(AttributeError):
        # Attribute is class-level constant; attempting mutation should fail or remain False
        EndpointPolicy.REAL_CAPITAL_ENABLED = True  # type: ignore[misc]
    assert EndpointPolicy.REAL_CAPITAL_ENABLED is False


def test_binance_testnet_valid_endpoints():
    """Approved Binance testnet REST and WS endpoints must pass validation."""
    valid_urls = [
        "https://testnet.binance.vision/api/v3/time",
        "https://testnet.binance.vision/api/v3/order",
        "https://testnet.binance.vision/api/v3/userDataStream",
        "wss://testnet.binance.vision/ws",
        "wss://testnet.binance.vision/ws/test-listen-key",
        "wss://stream.testnet.binance.vision/ws",
        "wss://ws-api.testnet.binance.vision/ws-api/v3",
    ]
    for url in valid_urls:
        assert EndpointPolicy.validate_url(Environment.BINANCE_TESTNET, url) == url


def test_bybit_testnet_valid_endpoints():
    """Approved Bybit V5 testnet REST and WS endpoints must pass validation."""
    valid_urls = [
        "https://api-testnet.bybit.com/v5/market/time",
        "https://api-testnet.bybit.com/v5/order/create",
        "https://api-testnet.bybit.com/v5/order/realtime",
        "https://api-testnet.bybit.com/v5/execution/list",
        "wss://stream-testnet.bybit.com/v5/private",
        "wss://stream-testnet.bybit.com/v5/public/spot",
    ]
    for url in valid_urls:
        assert EndpointPolicy.validate_url(Environment.BYBIT_TESTNET, url) == url


@pytest.mark.parametrize(
    "prod_url",
    [
        "https://api.binance.com/api/v3/order",
        "https://api1.binance.com/api/v3/order",
        "https://api2.binance.com/api/v3/order",
        "https://api3.binance.com/api/v3/order",
        "https://api4.binance.com/api/v3/order",
        "https://fapi.binance.com/fapi/v1/order",
        "https://dapi.binance.com/dapi/v1/order",
        "wss://stream.binance.com:9443/ws",
        "wss://stream.binance.com/ws",
        "wss://ws-api.binance.com:443/ws-api/v3",
    ],
)
def test_rejection_of_binance_production_endpoints(prod_url: str):
    """Production Binance hostnames must be rejected immediately with EndpointSecurityBreachError."""
    with pytest.raises(EndpointSecurityBreachError) as exc_info:
        EndpointPolicy.validate_url(Environment.BINANCE_TESTNET, prod_url)
    assert (
        "PROD_HOST_REJECTED" in str(exc_info.value) or "production" in str(exc_info.value).lower()
    )


@pytest.mark.parametrize(
    "prod_url",
    [
        "https://api.bybit.com/v5/order/create",
        "https://api.bytick.com/v5/order/create",
        "wss://stream.bybit.com/v5/private",
        "wss://stream.bybit.com/v5/public/spot",
        "wss://stream.bytick.com/v5/private",
    ],
)
def test_rejection_of_bybit_production_endpoints(prod_url: str):
    """Production Bybit hostnames must be rejected immediately with EndpointSecurityBreachError."""
    with pytest.raises(EndpointSecurityBreachError) as exc_info:
        EndpointPolicy.validate_url(Environment.BYBIT_TESTNET, prod_url)
    assert (
        "PROD_HOST_REJECTED" in str(exc_info.value) or "production" in str(exc_info.value).lower()
    )


@pytest.mark.parametrize(
    "spoofed_url",
    [
        "https://testnet.binance.vision.attacker.com/api/v3/time",
        "https://attacker.testnet.binance.vision.com/api/v3/time",
        "https://api-testnet.bybit.com.phishing.net/v5/order/create",
        "https://notbybit.com/api-testnet.bybit.com",
        "https://google.com",
        "https://1.1.1.1/api",
    ],
)
def test_rejection_of_spoofed_or_arbitrary_hostnames(spoofed_url: str):
    """Arbitrary or suffix-spoofed hostnames must be rejected."""
    with pytest.raises(EndpointSecurityBreachError):
        EndpointPolicy.validate_url(Environment.BINANCE_TESTNET, spoofed_url)

    with pytest.raises(EndpointSecurityBreachError):
        EndpointPolicy.validate_url(Environment.BYBIT_TESTNET, spoofed_url)


def test_rejection_of_unencrypted_protocols():
    """Plain HTTP or WS (non-TLS) URLs must be rejected unconditionally."""
    insecure_urls = [
        ("http://testnet.binance.vision/api/v3/time", Environment.BINANCE_TESTNET),
        ("ws://testnet.binance.vision/ws", Environment.BINANCE_TESTNET),
        ("http://api-testnet.bybit.com/v5/market/time", Environment.BYBIT_TESTNET),
        ("ws://stream-testnet.bybit.com/v5/private", Environment.BYBIT_TESTNET),
    ]
    for url, env in insecure_urls:
        with pytest.raises(EndpointSecurityBreachError) as exc_info:
            EndpointPolicy.validate_url(env, url)
        assert (
            "UNENCRYPTED_SCHEME_REJECTED" in str(exc_info.value)
            or "tls" in str(exc_info.value).lower()
        )


def test_cross_environment_isolation():
    """Binance endpoints must be rejected under Bybit environment, and vice versa."""
    binance_url = "https://testnet.binance.vision/api/v3/time"
    bybit_url = "https://api-testnet.bybit.com/v5/market/time"

    with pytest.raises(EndpointSecurityBreachError):
        EndpointPolicy.validate_url(Environment.BYBIT_TESTNET, binance_url)

    with pytest.raises(EndpointSecurityBreachError):
        EndpointPolicy.validate_url(Environment.BINANCE_TESTNET, bybit_url)


# =============================================================================
# 2. Transport Pre-flight Endpoint Guard
# =============================================================================


@pytest.mark.asyncio
async def test_rest_transport_blocks_production_url_before_socket():
    """RestTransport must reject production URL before any socket creation."""
    transport = RestTransport(Environment.BINANCE_TESTNET)
    with pytest.raises(EndpointSecurityBreachError):
        await transport.request("GET", "https://api.binance.com/api/v3/time")


def test_websocket_transport_blocks_production_url_before_socket():
    """WebSocketTransport must reject production URL before any socket creation."""
    with pytest.raises(EndpointSecurityBreachError):
        WebSocketTransport(
            environment=Environment.BYBIT_TESTNET,
            url="wss://stream.bybit.com/v5/private",
            on_message_callback=lambda msg: None,
        )


# =============================================================================
# 3. Credential Scope & Isolation Enforcement
# =============================================================================


def test_credential_withdrawal_permission_rejected():
    """Credentials with can_withdraw=True must raise CredentialScopeError."""
    with pytest.raises(CredentialScopeError) as exc_info:
        TestnetCredentials(
            api_key="test_key_12345",
            api_secret="test_secret_67890",
            environment=Environment.BINANCE_TESTNET,
            can_withdraw=True,
        )
    assert "withdrawal" in str(exc_info.value).lower()


def test_credential_transfer_permission_rejected():
    """Credentials with can_transfer=True must raise CredentialScopeError."""
    with pytest.raises(CredentialScopeError) as exc_info:
        TestnetCredentials(
            api_key="test_key_12345",
            api_secret="test_secret_67890",
            environment=Environment.BYBIT_TESTNET,
            can_transfer=True,
        )
    assert "transfer" in str(exc_info.value).lower()


def test_empty_credential_rejected():
    """Empty API key or secret must raise CredentialScopeError."""
    with pytest.raises(CredentialScopeError):
        TestnetCredentials(
            api_key="",
            api_secret="secret",
            environment=Environment.BINANCE_TESTNET,
        )
    with pytest.raises(CredentialScopeError):
        TestnetCredentials(
            api_key="key",
            api_secret="",
            environment=Environment.BINANCE_TESTNET,
        )


def test_secret_masking_utility():
    """mask_secret must prevent secret exposure in logs and telemetry."""
    assert mask_secret(None) == "[EMPTY]"
    assert mask_secret("") == "[EMPTY]"
    assert mask_secret("short") == "***"
    assert mask_secret("12345678") == "***"
    masked = mask_secret("abcdef1234567890ghijkl")
    assert masked == "abcd...ijkl"
    assert "1234567890" not in masked


def test_credential_to_safe_dict():
    """to_safe_dict must produce masked diagnostic dictionary."""
    creds = TestnetCredentials(
        api_key="my_secret_api_key_for_testing",
        api_secret="very_secret_key_that_must_not_leak",
        environment=Environment.BINANCE_TESTNET,
    )
    safe_info = creds.to_safe_dict()
    assert safe_info["api_key_masked"] == "my_s...ting"
    assert safe_info["environment"] == "BINANCE_TESTNET"
    assert safe_info["can_withdraw"] is False
    assert "very_secret_key" not in str(safe_info)


def test_account_permission_auditor():
    """CredentialPolicy.validate_account_permissions must detect withdrawal capabilities."""
    # Safe Binance account
    safe_binance = {"canTrade": True, "canWithdraw": False, "canDeposit": True}
    CredentialPolicy.validate_account_permissions(safe_binance, "BINANCE_TESTNET")

    # Hazardous Binance account with withdrawal capability
    hazard_binance = {"canTrade": True, "canWithdraw": True}
    with pytest.raises(CredentialScopeError):
        CredentialPolicy.validate_account_permissions(hazard_binance, "BINANCE_TESTNET")

    # Safe Bybit account
    safe_bybit = {"permissions": {"SpotTrade": True, "DerivativesTrade": True}}
    CredentialPolicy.validate_account_permissions(safe_bybit, "BYBIT_TESTNET")

    # Hazardous Bybit account
    hazard_bybit = {"permissions": {"SpotTrade": True, "Withdrawal": True}}
    with pytest.raises(CredentialScopeError):
        CredentialPolicy.validate_account_permissions(hazard_bybit, "BYBIT_TESTNET")
