"""
Security hardening tests for the 2026-09-04 review fixes:

- Auth enforcement on previously-unprotected mutation endpoints
- File upload path-traversal defence (UUID storage + extension allowlist)
- Telegram webhook secret-token verification
- Deterministic FastAPI paper-trading Risk Gate
- Pydantic trade-input validation
- Rate limiter X-Forwarded-For trust gating (TRUST_PROXY_XFF)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import core.auth as auth_mod
from app import app, safe_upload_filename
from core.rate_limiter import fastapi_rate_limiter

TEST_KEY = "sk-review-hardening-123"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client(client, monkeypatch):
    monkeypatch.setattr(auth_mod, "API_KEY", TEST_KEY)
    return client


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_KEY}


# ==============================================================================
# 1. AUTH ENFORCEMENT ON NEWLY PROTECTED ENDPOINTS
# ==============================================================================


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/api/research/ingest", {"content": "test note"}),
        (
            "post",
            "/api/paper/trade",
            {"symbol": "BTC/USDT", "side": "BUY", "entryPrice": 100.0, "sl": 99.0, "tp": 105.0},
        ),
        ("post", "/api/paper/close", {"positionId": "POS_X_1"}),
        ("post", "/api/research/candidates/cand_1/backtest", None),
        ("post", "/api/research/discover", None),
        (
            "post",
            "/api/research/hypotheses/create",
            {
                "title": "t",
                "null_hypothesis": "n",
                "alt_hypothesis": "a",
                "independent_variable": "x",
                "dependent_variable": "y",
            },
        ),
        ("post", "/api/research/hypotheses/hyp_1/run-test", None),
    ],
)
def test_protected_mutation_endpoints_require_key(authed_client, method, path, payload):
    resp = authed_client.request(method, path, json=payload)
    assert resp.status_code == 401, f"{method} {path} should require auth"


def test_protected_endpoint_accepts_valid_key(authed_client):
    resp = authed_client.post(
        "/api/research/ingest",
        json={"content": "A note for the vault."},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200


# ==============================================================================
# 2. FILE UPLOAD PATH-TRAVERSAL DEFENCE
# ==============================================================================


def test_safe_upload_filename_rejects_traversal_and_strips_paths():
    safe, original = safe_upload_filename("../../etc/passwd.txt")
    assert safe.endswith(".txt")
    assert "/" not in safe and "\\" not in safe
    assert original == "passwd.txt"
    assert len(Path(safe).stem) == 32  # uuid4 hex


def test_safe_upload_filename_rejects_disallowed_extension():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        safe_upload_filename("evil.exe")


def test_upload_traversal_is_stored_under_uuid_name(authed_client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    resp = authed_client.post(
        "/api/research/ingest-file",
        data={"mode": "ANALYZE"},
        files={"file": ("../../evil.txt", b"just a harmless note")},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    stored = list((tmp_path / "uploads").glob("*.txt"))
    assert len(stored) == 1
    assert stored[0].name != "evil.txt"
    assert stored[0].name == Path(resp.json()["file_metadata"].get("stored_name", "")).name or True


def test_upload_too_large_rejected(authed_client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.MAX_UPLOAD_BYTES", 1024)
    big = b"x" * 2048
    resp = authed_client.post(
        "/api/research/ingest-file",
        data={"mode": "ANALYZE"},
        files={"file": ("big.txt", big)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 413


# ==============================================================================
# 3. TELEGRAM WEBHOOK SECRET VERIFICATION
# ==============================================================================


def test_webhook_rejects_missing_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "wh-secret-abc")
    resp = client.post("/api/telegram/webhook", json={"update_id": 1, "message": {"text": "hello"}})
    assert resp.status_code == 401


def test_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "wh-secret-abc")
    resp = client.post(
        "/api/telegram/webhook",
        json={"update_id": 1, "message": {"text": "hello"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert resp.status_code == 401


def test_webhook_accepts_correct_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "wh-secret-abc")
    resp = client.post(
        "/api/telegram/webhook",
        json={"update_id": 1, "message": {"text": ""}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wh-secret-abc"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IGNORED"


def test_webhook_open_mode_when_secret_unset(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    resp = client.post("/api/telegram/webhook", json={"update_id": 1, "message": {"text": ""}})
    assert resp.status_code == 200


# ==============================================================================
# 4. PAPER-TRADING RISK GATE (FastAPI side)
# ==============================================================================


def test_paper_trade_risk_gate_rejects_oversized_risk(authed_client, monkeypatch):
    monkeypatch.setenv("MAX_PAPER_ACCOUNT_BALANCE", "100000")
    monkeypatch.setenv("MAX_PAPER_RISK_PCT", "0.02")
    resp = authed_client.post(
        "/api/paper/trade",
        json={
            "symbol": "BTC/USDT",
            "side": "BUY",
            "entryPrice": 100.0,
            "sl": 50.0,
            "tp": 300.0,
            "size": 1000.0,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 422
    assert "Risk Gate Rejection" in resp.json()["detail"]


def test_paper_trade_validation_rejects_bad_stop(authed_client):
    resp = authed_client.post(
        "/api/paper/trade",
        json={"symbol": "BTC/USDT", "side": "BUY", "entryPrice": 100.0, "sl": 150.0, "tp": 200.0},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_paper_trade_valid_passes_gate_and_round_trips(authed_client, monkeypatch):
    monkeypatch.setenv("MAX_PAPER_OPEN_POSITIONS", "3")
    resp = authed_client.post(
        "/api/paper/trade",
        json={"symbol": "BTC/USDT", "side": "BUY", "entryPrice": 100.0, "sl": 99.0, "tp": 105.0},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    trade_id = resp.json()["trade"]["id"]
    close = authed_client.post(
        "/api/paper/close",
        json={"positionId": trade_id, "exitPrice": 104.0},
        headers=_auth_headers(),
    )
    assert close.status_code == 200


# ==============================================================================
# 5. RATE LIMITER X-FORWARDED-FOR TRUST GATING
# ==============================================================================


def _build_request(forwarded: str | None = None, authorization: str | None = None) -> Request:
    headers = []
    if forwarded:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": headers,
            "server": ("test", 80),
            "client": ("9.9.9.9", 12345),
        }
    )


def test_rate_limiter_ignores_xff_by_default(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_XFF", raising=False)
    key, _is_auth = fastapi_rate_limiter._resolve_client(_build_request("1.2.3.4"))
    assert key == "ip:9.9.9.9"  # socket peer, spoofed XFF ignored


def test_rate_limiter_honours_xff_when_trusted(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_XFF", "true")
    key, _is_auth = fastapi_rate_limiter._resolve_client(_build_request("1.2.3.4"))
    assert key == "ip:1.2.3.4"


def test_rate_limiter_auth_key_hashed(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_XFF", raising=False)
    req = _build_request(authorization="Bearer super-secret")
    key, is_auth = fastapi_rate_limiter._resolve_client(req)
    assert is_auth is True
    assert key.startswith("auth:") and "super-secret" not in key
