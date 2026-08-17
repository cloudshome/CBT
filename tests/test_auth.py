"""P18.1 authentication & authorization tests.

Security invariants, per the roadmap's "done when":

* an unauthenticated user cannot read private state or mutate anything;
* a viewer cannot approve/reject/close;
* an operator still cannot bypass the risk gate;
* security tests cover every write endpoint.

These run against the real Flask app in-process (like test_web_api.py) with a
throwaway database, plus unit tests for the auth primitives and the remote
deployment guard.
"""
from __future__ import annotations

import json

import pytest

import config
from web import auth as authmod
from web.auth import AuthManager, hash_password, verify_password, role_allows


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("SKY_AUTH_MODE", "auto")
    monkeypatch.delenv("SKY_ALLOW_FORCE_APPROVE", raising=False)
    monkeypatch.delenv("SKY_ALLOW_REMOTE_NO_TLS", raising=False)
    monkeypatch.delenv("SKY_TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("SKY_SECRET_KEY", raising=False)
    import config as _c
    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "auto")
    monkeypatch.setattr(_c, "SKY_ALLOW_FORCE_APPROVE", False)
    monkeypatch.setattr(_c, "SKY_ALLOW_REMOTE_NO_TLS", False)
    monkeypatch.setattr(_c, "SKY_TRUSTED_PROXY_IPS", [])
    from web.app import make_app
    app = make_app()
    app.testing = True
    return app.test_client()


OWNER = "owner"
PASSWORD = "correct horse battery staple"


def _setup(client, username=OWNER, password=PASSWORD):
    r = client.post("/api/auth/setup", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _login(client, username=OWNER, password=PASSWORD):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _insert_scan(status="PENDING_REVIEW", action="BUY"):
    import time
    from data.database import SignalDB
    with SignalDB() as db:
        cur = db.conn.execute(
            "INSERT INTO scans(signal_id, ts, symbol, timeframe, price, action, "
            "entry, stop_loss, take_profit, confidence_label, status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (f"TEST_{int(time.time()*1000)}", int(time.time()*1000), "BTCUSDT",
             "15m", 60000.0, action, 60000.0, 59000.0, 62000.0, "MEDIUM", status))
        db.conn.commit()
        return cur.lastrowid


# ── primitives ────────────────────────────────────────────────────────────
def test_password_hashing_is_not_plaintext():
    salt, pwhash = hash_password("hunter2-hunter2")
    assert pwhash != "hunter2-hunter2"
    assert len(salt) == 32 and len(pwhash) == 64
    assert verify_password("hunter2-hunter2", salt, pwhash)
    assert not verify_password("wrong-password", salt, pwhash)


def test_role_allows_ranking():
    assert role_allows("operator", "viewer")
    assert role_allows("operator", "operator")
    assert role_allows("viewer", "viewer")
    assert not role_allows("viewer", "operator")
    assert not role_allows(None, "operator")


def test_stored_owner_hash_is_hashed(client):
    _setup(client)
    mgr = AuthManager()
    user = mgr.get_user_by_name(OWNER)
    assert user is not None
    assert user["password_hash"] != PASSWORD
    assert verify_password(PASSWORD, user["salt"], user["password_hash"])


# ── first-run setup ───────────────────────────────────────────────────────
def test_first_run_setup_creates_owner_and_second_is_refused(client):
    body = _setup(client)
    assert body["user"] == OWNER and body["role"] == "operator"
    # second owner refused
    r = client.post("/api/auth/setup", json={"username": "other", "password": PASSWORD})
    assert r.status_code == 409


def test_setup_rejects_weak_password(client):
    r = client.post("/api/auth/setup", json={"username": "abc", "password": "short"})
    assert r.status_code == 400


# ── unauthenticated access ────────────────────────────────────────────────
def test_unauthenticated_cannot_read_or_mutate(client):
    _setup(client)  # now auth is enforced
    anon = _fresh_client(client)
    assert anon.get("/api/scan?symbol=BTCUSDT&tf=15m").status_code == 401
    assert anon.get("/api/pending").status_code == 401
    assert anon.get("/api/health").status_code == 401
    assert anon.post("/api/review", json={"scan_id": 1, "decision": "APPROVED"}).status_code == 401
    assert anon.post("/api/trader-state", json={"angry": True}).status_code == 401
    assert anon.post("/api/journal", json={"scan_id": 1}).status_code == 401
    assert anon.post("/api/commands/run", json={"id": "mcp"}).status_code == 401
    assert anon.post("/api/alerts/test", json={"channel": "telegram"}).status_code == 401
    assert anon.post("/api/learn").status_code == 401
    assert anon.post("/api/backtest", json={}).status_code == 401
    assert anon.post("/api/paper/run", json={}).status_code == 401
    # W2 live candle streaming is market data, but it is still private state
    assert anon.get("/api/chart/stream?frames=1").status_code == 401


def _fresh_client(client):
    """A new test client sharing the same app but no cookies."""
    # The secret key is persisted in the DB, so a fresh client against the same
    # app has no session cookie (i.e. is unauthenticated) yet would accept a
    # cookie forged by the authenticated client.
    return client.application.test_client()


def test_login_and_authenticated_read(client):
    _setup(client)
    body = _login(client)
    assert body["user"] == OWNER and body["role"] == "operator"
    assert "csrf" in body
    me = client.get("/api/auth/me").get_json()
    assert me["user"] == OWNER and me["role"] == "operator"
    assert client.get("/api/scan?symbol=BTCUSDT&tf=15m").status_code == 200


def test_login_wrong_password_and_throttle(client):
    _setup(client)
    anon = _fresh_client(client)
    for _ in range(config.SKY_LOGIN_MAX_ATTEMPTS):
        r = anon.post("/api/auth/login", json={"username": OWNER, "password": "wrong-password"})
        assert r.status_code == 401
    # now locked out — even the correct password is refused
    r = anon.post("/api/auth/login", json={"username": OWNER, "password": PASSWORD})
    assert r.status_code == 429


# ── roles ─────────────────────────────────────────────────────────────────
def test_viewer_device_token_reads_but_cannot_mutate(client):
    _setup(client)
    csrf = _login(client)["csrf"]
    tok = client.post("/api/auth/devices",
                      json={"name": "phone", "scope": "viewer"},
                      headers={"X-CSRF-Token": csrf}).get_json()["token"]
    anon = _fresh_client(client)
    # read allowed
    assert anon.get("/api/scan?symbol=BTCUSDT&tf=15m",
                    headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    # writes denied
    for path, payload in [
        ("/api/review", {"scan_id": 1, "decision": "APPROVED"}),
        ("/api/trader-state", {"angry": True}),
        ("/api/journal", {"scan_id": 1}),
        ("/api/commands/run", {"id": "mcp"}),
        ("/api/alerts/test", {"channel": "telegram"}),
        ("/api/learn", {}),
        ("/api/backtest", {}),
        ("/api/paper/run", {}),
    ]:
        r = anon.post(path, json=payload, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403, f"{path} should be forbidden for viewer"


def test_operator_can_reject_and_force_approve_is_disabled(client):
    _setup(client)
    _login(client)
    scan_id = _insert_scan(status="PENDING_REVIEW", action="BUY")
    csrf = _login(client)["csrf"]
    # operator can reject (write that skips the gate)
    r = client.post("/api/review", json={"scan_id": scan_id, "decision": "REJECTED"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "REJECTED"
    # operator cannot bypass the risk gate: APPROVED on an unproven setup is
    # blocked and force-approve is disabled by default.
    scan2 = _insert_scan(status="PENDING_REVIEW", action="BUY")
    r = client.post("/api/review", json={"scan_id": scan2, "decision": "APPROVED"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 409
    body = r.get_json()
    assert body["force_available"] is False
    # explicit force is refused outright
    r = client.post("/api/review", json={"scan_id": scan2, "decision": "APPROVED",
                                         "force": True},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


# ── CSRF ──────────────────────────────────────────────────────────────────
def test_csrf_required_for_cookie_mutations(client):
    _setup(client)
    _login(client)
    csrf = _login(client)["csrf"]
    # without the token: rejected
    r = client.post("/api/trader-state", json={"angry": True})
    assert r.status_code == 403
    assert r.get_json()["code"] == "CSRF"
    # with the token: accepted
    r = client.post("/api/trader-state", json={"angry": True},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    # GETs never need CSRF
    assert client.get("/api/risk").status_code == 200


def test_bearer_tokens_do_not_require_csrf(client):
    _setup(client)
    csrf = _login(client)["csrf"]
    tok = client.post("/api/auth/devices",
                      json={"name": "desktop", "scope": "operator"},
                      headers={"X-CSRF-Token": csrf}).get_json()["token"]
    anon = _fresh_client(client)
    r = anon.post("/api/trader-state", json={"angry": False},
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


# ── sessions / devices ────────────────────────────────────────────────────
def test_logout_and_logout_all(client):
    _setup(client)
    csrf = _login(client)["csrf"]
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/api/auth/me").status_code == 401

    csrf = _login(client)["csrf"]
    tok = client.post("/api/auth/devices",
                      json={"name": "phone", "scope": "viewer"},
                      headers={"X-CSRF-Token": csrf}).get_json()["token"]
    r = client.post("/api/auth/logout-all", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    anon = _fresh_client(client)
    assert anon.get("/api/scan?symbol=BTCUSDT&tf=15m",
                    headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_device_token_revoke(client):
    _setup(client)
    csrf = _login(client)["csrf"]
    tok = client.post("/api/auth/devices",
                      json={"name": "phone", "scope": "viewer"},
                      headers={"X-CSRF-Token": csrf}).get_json()["token"]
    devices = client.get("/api/auth/devices").get_json()["devices"]
    handle = devices[0]["id"]
    assert client.post("/api/auth/devices/revoke", json={"id": handle},
                       headers={"X-CSRF-Token": csrf}).status_code == 200
    anon = _fresh_client(client)
    assert anon.get("/api/scan?symbol=BTCUSDT&tf=15m",
                    headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_password_change(client):
    _setup(client)
    csrf = _login(client)["csrf"]
    r = client.post("/api/auth/password",
                    json={"current": PASSWORD, "new": "a brand new password 123"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.get_data(as_text=True)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.post("/api/auth/login",
                       json={"username": OWNER, "password": "a brand new password 123"}).status_code == 200


# ── audit log ─────────────────────────────────────────────────────────────
def test_sensitive_actions_are_audited(client):
    _setup(client)
    _login(client)
    csrf = _login(client)["csrf"]
    scan_id = _insert_scan(status="PENDING_REVIEW", action="BUY")
    client.post("/api/review", json={"scan_id": scan_id, "decision": "REJECTED"},
                headers={"X-CSRF-Token": csrf})
    client.post("/api/trader-state", json={"angry": True}, headers={"X-CSRF-Token": csrf})
    rows = client.get("/api/auth/audit").get_json()["rows"]
    actions = {r["action"] for r in rows}
    assert {"login", "review", "trader_state"} <= actions
    # every row carries the acting user
    assert all(r.get("username") == OWNER for r in rows if r.get("username"))


# ── remote deployment guard ───────────────────────────────────────────────
def test_deployment_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "deploy.db"))
    monkeypatch.setattr(config, "SKY_ALLOW_REMOTE_NO_TLS", False)
    monkeypatch.setattr(config, "SKY_TRUSTED_PROXY_IPS", [])

    # loopback always allowed
    authmod.enforce_deployment("127.0.0.1")
    authmod.enforce_deployment("localhost")

    # remote without owner -> refuse
    with pytest.raises(RuntimeError):
        authmod.enforce_deployment("0.0.0.0")

    # create an owner, remote without TLS proxy -> refuse
    mgr = AuthManager()
    mgr.create_owner(OWNER, PASSWORD)
    with pytest.raises(RuntimeError):
        authmod.enforce_deployment("0.0.0.0")

    # with a trusted proxy configured -> allowed
    monkeypatch.setattr(config, "SKY_TRUSTED_PROXY_IPS", ["10.0.0.1"])
    authmod.enforce_deployment("0.0.0.0")

    # explicit override -> allowed
    monkeypatch.setattr(config, "SKY_TRUSTED_PROXY_IPS", [])
    monkeypatch.setattr(config, "SKY_ALLOW_REMOTE_NO_TLS", True)
    authmod.enforce_deployment("0.0.0.0")
