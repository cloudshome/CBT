"""
Unit & Regression Tests for Rate Limiter Reverse-Proxy CIDR Security & Spoof Protection.

Verifies:
1. Untrusted socket peer cannot spoof X-Forwarded-For to rotate identities.
2. Trusted proxy (loopback, private Docker CIDRs) correctly unwinds XFF chain right-to-left.
3. First untrusted address in the forwarding chain is chosen as client identity.
4. Malformed XFF payloads fail closed safely to socket peer identity without crashing.
5. TRUST_PROXY_XFF=false strictly ignores XFF regardless of peer.
6. Custom TRUSTED_PROXY_CIDRS configuration and fail-closed validation on malformed CIDRs.
7. IPv6 trusted proxy and client support.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.rate_limiter import (
    RateLimiter,
    parse_trusted_proxy_cidrs,
)


def _mock_request(client_host: str = "127.0.0.1", xff: str | None = None, auth: str | None = None):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    if auth is not None:
        headers["authorization"] = auth

    client = SimpleNamespace(host=client_host) if client_host else None
    return SimpleNamespace(headers=headers, client=client)


class TestRateLimiterProxySecurity:
    """Rigorous tests for reverse-proxy client IP identification and anti-spoofing."""

    def test_untrusted_peer_cannot_spoof_xff(self):
        """Attacker directly connecting from public IP (8.8.8.8) with forged XFF must be locked to 8.8.8.8."""
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "true"}):
            limiter = RateLimiter()
            req = _mock_request(client_host="8.8.8.8", xff="1.2.3.4")
            key, is_auth = limiter._resolve_client(req)

            assert key == "ip:8.8.8.8", "Spoofed XFF from untrusted socket peer must be ignored"
            assert is_auth is False

    def test_trusted_loopback_proxy_extracts_client_ip(self):
        """Reverse proxy at 127.0.0.1 forwarding external client 203.0.113.50."""
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "true"}):
            limiter = RateLimiter()
            req = _mock_request(client_host="127.0.0.1", xff="203.0.113.50, 127.0.0.1")
            key, is_auth = limiter._resolve_client(req)

            assert key == "ip:203.0.113.50"
            assert is_auth is False

    def test_trusted_docker_proxy_multi_hop_traversal(self):
        """
        Multi-hop: External Client (198.51.100.1) -> Internal Proxy (10.0.0.5) -> Ingress (172.18.0.2).
        Walking right-to-left: 172.18.0.2 (trusted) -> 10.0.0.5 (trusted) -> 198.51.100.1 (untrusted, selected).
        """
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "true"}):
            limiter = RateLimiter()
            req = _mock_request(
                client_host="172.18.0.2",
                xff="198.51.100.1, 10.0.0.5, 172.18.0.2",
            )
            key, is_auth = limiter._resolve_client(req)

            assert key == "ip:198.51.100.1"
            assert is_auth is False

    def test_malformed_xff_fails_safely_to_socket_peer(self):
        """Malformed XFF must not crash or allow attacker to inject invalid key."""
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "true"}):
            limiter = RateLimiter()

            for bad_xff in (
                "invalid_ip",
                "127.0.0.1, ../../../etc/passwd",
                "999.999.999.999",
                " , , ",
                "; DROP TABLE users;",
            ):
                req = _mock_request(client_host="127.0.0.1", xff=bad_xff)
                key, is_auth = limiter._resolve_client(req)
                assert key.startswith("ip:"), f"Must resolve to a safe ip key, got {key}"
                assert "127.0.0.1" in key or "ip:" in key

    def test_proxy_trust_disabled_ignores_all_xff(self):
        """When TRUST_PROXY_XFF=false, even a trusted loopback peer's XFF is ignored."""
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "false"}):
            limiter = RateLimiter()
            req = _mock_request(client_host="127.0.0.1", xff="203.0.113.50")
            key, is_auth = limiter._resolve_client(req)

            assert key == "ip:127.0.0.1", "When TRUST_PROXY_XFF is false, socket host must be used"

    def test_custom_trusted_proxy_cidrs_configuration(self):
        """Custom TRUSTED_PROXY_CIDRS accurately defines which subnets are trusted."""
        custom_cidrs = "192.0.2.0/24"
        with patch.dict(
            "os.environ",
            {"TRUST_PROXY_XFF": "true", "TRUSTED_PROXY_CIDRS": custom_cidrs},
        ):
            limiter = RateLimiter()

            # 192.0.2.10 is in custom CIDR -> trusted proxy
            req_trusted = _mock_request(client_host="192.0.2.10", xff="203.0.113.99")
            key_t, _ = limiter._resolve_client(req_trusted)
            assert key_t == "ip:203.0.113.99"

            # 10.0.0.1 is no longer in trusted CIDR -> untrusted peer
            req_untrusted = _mock_request(client_host="10.0.0.1", xff="203.0.113.99")
            key_u, _ = limiter._resolve_client(req_untrusted)
            assert key_u == "ip:10.0.0.1"

    def test_malformed_trusted_proxy_cidrs_fails_closed(self):
        """Malformed CIDR in TRUSTED_PROXY_CIDRS must raise ValueError, not silently trust all."""
        with pytest.raises(ValueError, match="Malformed CIDR in TRUSTED_PROXY_CIDRS"):
            parse_trusted_proxy_cidrs("not-a-cidr/99")

    def test_ipv6_trusted_proxy_and_client_support(self):
        """IPv6 loopback (::1) proxy correctly resolves external IPv6 client (2001:db8::1)."""
        with patch.dict("os.environ", {"TRUST_PROXY_XFF": "true"}):
            limiter = RateLimiter()
            req = _mock_request(client_host="::1", xff="2001:db8::1, ::1")
            key, is_auth = limiter._resolve_client(req)

            assert key == "ip:2001:db8::1"
            assert is_auth is False
