"""
Unit tests for FastAPI In-Memory Sliding-Window Rate Limiter.
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from core.rate_limiter import fastapi_rate_limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    fastapi_rate_limiter.reset()
    yield
    fastapi_rate_limiter.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_rate_limit_headers_injected(client):
    """Verifies that RateLimit headers are injected on normal API responses."""
    res = client.get("/api/telegram/status")
    assert res.status_code == 200
    assert "ratelimit-limit" in res.headers
    assert "ratelimit-remaining" in res.headers
    assert "ratelimit-reset" in res.headers


def test_rate_limit_blocking_on_public_quota_exhaustion(client, monkeypatch):
    """When public request count exceeds limit, returns 429 with standard headers."""
    monkeypatch.setattr(fastapi_rate_limiter, "public_max", 3)
    fastapi_rate_limiter.reset()

    # 3 allowed requests
    for _i in range(3):
        r = client.get("/api/telegram/status")
        assert r.status_code == 200

    # 4th request -> 429 Too Many Requests
    r_blocked = client.get("/api/telegram/status")
    assert r_blocked.status_code == 429
    assert r_blocked.json()["error"] == "Too many requests, please try again later."
    assert "retry-after" in r_blocked.headers
    assert r_blocked.headers["ratelimit-remaining"] == "0"


def test_authenticated_requests_receive_higher_quota(client, monkeypatch):
    """Requests with X-API-Key receive the higher auth_max quota."""
    monkeypatch.setattr(fastapi_rate_limiter, "public_max", 2)
    monkeypatch.setattr(fastapi_rate_limiter, "auth_max", 5)
    fastapi_rate_limiter.reset()

    headers = {"X-API-Key": "my-quant-key"}

    # Authenticated client can make 5 requests
    for _i in range(5):
        r = client.get("/api/telegram/status", headers=headers)
        assert r.status_code == 200
        assert r.headers["ratelimit-limit"] == "5"

    # 6th request breaches quota -> 429
    r_blocked = client.get("/api/telegram/status", headers=headers)
    assert r_blocked.status_code == 429


def test_health_and_root_endpoints_excluded_from_rate_limiting(client, monkeypatch):
    """Health probes must not be throttled to prevent false-positive liveness failure."""
    monkeypatch.setattr(fastapi_rate_limiter, "public_max", 1)
    fastapi_rate_limiter.reset()

    # Hit 5 times
    for _ in range(5):
        r = client.get("/health")
        assert r.status_code == 200
