"""P18.2 — stable application API (`/api/v1`) tests.

The roadmap's "done when": *web, Windows, and Android can use one documented
contract and an old client receives a clear upgrade message instead of corrupt
behavior.*

So these tests pin the four promises a companion client is allowed to rely on:

1. **One envelope** — every v1 response, success or failure, is
   ``{ok, data, error, meta}``. No endpoint is allowed a bespoke shape.
2. **Typed error codes** — a client branches on ``error.code``, never on
   prose. Legacy handlers that answer with loose text still surface a code.
3. **Compatibility** — an out-of-range client gets ``CLIENT_TOO_OLD`` /
   ``CLIENT_TOO_NEW``, not a 401 it will misreport as a login failure.
4. **Idempotency** — a retried human mutation replays the first result rather
   than applying twice; the same key with a different body is a hard error.

Plus the P18.1 security invariants, re-asserted against the *new* surface
(mirroring ``tests/test_auth.py``), because a new API is exactly where an
authorization hole gets introduced.
"""

from __future__ import annotations

import time
import uuid

import pytest

import config
from web import api_v1 as apiv1

OWNER = "owner"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "v1.db"))
    monkeypatch.delenv("SKY_ALLOW_FORCE_APPROVE", raising=False)
    monkeypatch.delenv("SKY_TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("SKY_SECRET_KEY", raising=False)
    import config as _c

    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "v1.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "auto")
    monkeypatch.setattr(_c, "SKY_ALLOW_FORCE_APPROVE", False)
    monkeypatch.setattr(_c, "SKY_TRUSTED_PROXY_IPS", [])
    from web.app import make_app

    application = make_app()
    application.testing = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def open_client(monkeypatch, tmp_path):
    """A client with auth disabled — for contract tests that are not about auth."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "open.db"))
    import config as _c

    monkeypatch.setattr(_c, "DB_PATH", str(tmp_path / "open.db"))
    monkeypatch.setattr(_c, "SKY_AUTH_MODE", "disabled")
    monkeypatch.setattr(_c, "SKY_ALLOW_FORCE_APPROVE", False)
    from web.app import make_app

    application = make_app()
    application.testing = True
    return application.test_client()


def _setup_owner(client):
    r = client.post("/api/auth/setup", json={"username": OWNER, "password": PASSWORD})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["csrf"]


def _mint(client, csrf, name, scope):
    r = client.post(
        "/api/v1/devices",
        json={"name": name, "scope": scope},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["data"]["token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _insert_scan(signal_id="V1", status="PENDING_REVIEW", action="BUY"):
    from data.database import SignalDB

    with SignalDB() as db:
        cur = db.conn.execute(
            "INSERT INTO scans(signal_id, ts, symbol, timeframe, price, action, "
            "entry, stop_loss, take_profit, confidence_label, status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"{signal_id}_{uuid.uuid4().hex[:6]}",
                int(time.time() * 1000),
                "BTCUSDT",
                "15m",
                60000.0,
                action,
                60000.0,
                59000.0,
                62000.0,
                "MEDIUM",
                status,
            ),
        )
        db.conn.commit()
        return cur.lastrowid


def _assert_envelope(payload):
    """Every v1 response — success or failure — has exactly this shape."""
    assert isinstance(payload, dict), payload
    assert set(payload.keys()) == {"ok", "data", "error", "meta"}, payload.keys()
    assert isinstance(payload["ok"], bool)
    meta = payload["meta"]
    assert meta["api_version"] == apiv1.API_VERSION
    assert meta["server_version"] == config.VERSION
    assert isinstance(meta["request_id"], str) and meta["request_id"]
    if payload["ok"]:
        assert payload["error"] is None
    else:
        assert payload["data"] is None
        err = payload["error"]
        assert set(err.keys()) == {"code", "message", "details"}
        assert err["code"] in apiv1.route_catalog()["error_codes"]
        assert isinstance(err["message"], str) and err["message"]


# ══════════════════════════════════════════════════════════════════════════
# 1. the envelope
# ══════════════════════════════════════════════════════════════════════════
def test_version_is_public_and_enveloped(client):
    """A client must discover compatibility *before* it can authenticate."""
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.get_json()
    _assert_envelope(body)
    data = body["data"]
    assert data["api_version"] == apiv1.API_VERSION
    assert data["min_client_version"] <= data["max_client_version"]


def test_version_advertises_no_live_execution(client):
    """SKY cannot place an exchange order. A companion client must be able to
    discover that, rather than shipping a Trade button that can never work."""
    caps = client.get("/api/v1/version").get_json()["data"]["capabilities"]
    assert caps["live_exchange_execution"] is False
    assert caps["paper_trading"] is True


def test_route_catalog_is_machine_readable(open_client):
    body = open_client.get("/api/v1/routes").get_json()
    _assert_envelope(body)
    routes = body["data"]["routes"]
    assert body["data"]["count"] == len(routes)
    for route in routes:
        assert route["path"].startswith("/api/v1")
        assert route["method"] in ("GET", "POST")
        assert route["role"] in ("public", "viewer", "operator")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/risk",
        "/api/v1/pending",
        "/api/v1/paper",
        "/api/v1/loop-health",
        "/api/v1/health",
        "/api/v1/modules",
        "/api/v1/commands",
        "/api/v1/unlock",
        "/api/v1/trades",
        "/api/v1/journal",
        "/api/v1/routes",
        "/api/v1/me",
    ],
)
def test_read_endpoints_share_one_envelope(open_client, path):
    """No endpoint gets a bespoke shape — this is the whole point of v1."""
    r = open_client.get(path)
    assert r.status_code == 200, f"{path} -> {r.get_data(as_text=True)[:200]}"
    _assert_envelope(r.get_json())
    assert r.get_json()["ok"] is True


def test_unknown_v1_endpoint_is_typed_not_html(open_client):
    r = open_client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    body = r.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == apiv1.ErrorCode.NOT_FOUND


def test_wrong_method_is_typed(open_client):
    r = open_client.post("/api/v1/risk", json={})
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.METHOD_NOT_ALLOWED


def test_legacy_endpoints_keep_their_old_shape(open_client):
    """v1 must not break the shipped dashboard mid-migration."""
    body = open_client.get("/api/pending").get_json()
    assert "pending" in body  # legacy: bare payload
    assert "meta" not in body  # legacy: no v1 envelope


# ══════════════════════════════════════════════════════════════════════════
# 2. typed error codes
# ══════════════════════════════════════════════════════════════════════════
def test_legacy_400_becomes_typed_code(open_client):
    scan_id = _insert_scan("BAD")
    r = open_client.post("/api/v1/review", json={"scan_id": scan_id, "decision": "NONSENSE"})
    assert r.status_code == 400
    body = r.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == apiv1.ErrorCode.BAD_REQUEST


def test_missing_scan_is_not_found(open_client):
    r = open_client.post("/api/v1/review", json={"scan_id": 999999, "decision": "REJECTED"})
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.NOT_FOUND


def test_illegal_lifecycle_transition_has_its_own_code(open_client):
    """A retried decision without a key must be distinguishable from bad input."""
    scan_id = _insert_scan("LIFE")
    assert (
        open_client.post(
            "/api/v1/review", json={"scan_id": scan_id, "decision": "REJECTED"}
        ).status_code
        == 200
    )
    r = open_client.post("/api/v1/review", json={"scan_id": scan_id, "decision": "REJECTED"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.LIFECYCLE_INVALID


def test_risk_gate_refusal_is_typed_and_structured(open_client):
    """The desk refusing on risk is a *domain* answer, not a malformed request:
    the client must be able to render the reasons."""
    from data.database import SignalDB

    with SignalDB() as db:
        db.set_trader_state(angry=True, note="tilted")
    scan_id = _insert_scan("GATE")
    r = open_client.post("/api/v1/review", json={"scan_id": scan_id, "decision": "APPROVED"})
    assert r.status_code == 409
    body = r.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == apiv1.ErrorCode.RISK_GATE_CLOSED
    assert body["error"]["details"]["blocked_by"]


def test_code_for_status_covers_the_common_statuses():
    assert apiv1.code_for_status(404) == apiv1.ErrorCode.NOT_FOUND
    assert apiv1.code_for_status(403) == apiv1.ErrorCode.FORBIDDEN
    assert apiv1.code_for_status(502) == apiv1.ErrorCode.UPSTREAM_UNAVAILABLE
    assert apiv1.code_for_status(418) == apiv1.ErrorCode.INTERNAL


# ══════════════════════════════════════════════════════════════════════════
# 3. client compatibility
# ══════════════════════════════════════════════════════════════════════════
def test_client_too_old_gets_upgrade_message_not_a_401(client):
    """An old client must be told to upgrade. If this returned 401 the app
    would tell the user their password was wrong — the exact 'corrupt
    behavior' the roadmap requires we avoid."""
    r = client.get(
        "/api/v1/risk",
        headers={apiv1.CLIENT_VERSION_HEADER: str(apiv1.MIN_CLIENT_VERSION - 1)},
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == apiv1.ErrorCode.CLIENT_TOO_OLD
    assert "update" in body["error"]["message"].lower()
    assert body["error"]["details"]["min_client_version"] == apiv1.MIN_CLIENT_VERSION


def test_client_too_new_is_told_to_upgrade_the_hub(client):
    r = client.get(
        "/api/v1/risk",
        headers={apiv1.CLIENT_VERSION_HEADER: str(apiv1.MAX_CLIENT_VERSION + 1)},
    )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.CLIENT_TOO_NEW


def test_version_check_precedes_authentication(client):
    """Compatibility is checked before auth so the message is never masked."""
    _setup_owner(client)
    anon = client.application.test_client()
    r = anon.get("/api/v1/risk", headers={apiv1.CLIENT_VERSION_HEADER: "0"})
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.CLIENT_TOO_OLD


def test_garbage_client_version_is_rejected(open_client):
    r = open_client.get("/api/v1/risk", headers={apiv1.CLIENT_VERSION_HEADER: "not-a-number"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.BAD_REQUEST


def test_declaring_no_version_is_allowed(open_client):
    assert open_client.get("/api/v1/risk").status_code == 200


def test_check_client_version_unit():
    assert apiv1.check_client_version(None) is None
    assert apiv1.check_client_version("") is None
    assert apiv1.check_client_version(str(apiv1.API_VERSION)) is None
    assert apiv1.check_client_version("0")[0] == apiv1.ErrorCode.CLIENT_TOO_OLD
    assert apiv1.check_client_version("9999")[0] == apiv1.ErrorCode.CLIENT_TOO_NEW


# ══════════════════════════════════════════════════════════════════════════
# 4. idempotency
# ══════════════════════════════════════════════════════════════════════════
def test_retry_with_same_key_replays_instead_of_reapplying(open_client):
    """The core promise: a flaky connection retrying must not double-apply."""
    scan_id = _insert_scan("IDEM")
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    body = {"scan_id": scan_id, "decision": "REJECTED", "note": "first"}

    first = open_client.post("/api/v1/review", json=body, headers=key)
    assert first.status_code == 200
    assert first.get_json()["data"]["status"] == "REJECTED"
    assert not first.get_json()["meta"].get("idempotent_replay")

    second = open_client.post("/api/v1/review", json=body, headers=key)
    assert second.status_code == 200
    assert second.get_json()["ok"] is True
    assert second.get_json()["data"] == first.get_json()["data"]
    assert second.get_json()["meta"]["idempotent_replay"] is True


def test_without_a_key_the_retry_is_not_protected(open_client):
    """Control: proves the replay above is the key working, not the endpoint
    being harmlessly repeatable."""
    scan_id = _insert_scan("NOKEY")
    body = {"scan_id": scan_id, "decision": "REJECTED"}
    assert open_client.post("/api/v1/review", json=body).status_code == 200
    again = open_client.post("/api/v1/review", json=body)
    assert again.status_code == 400
    assert again.get_json()["error"]["code"] == apiv1.ErrorCode.LIFECYCLE_INVALID


def test_only_one_decision_is_recorded_for_a_replayed_key(open_client):
    """The replay must not write a second decision row."""
    from data.database import SignalDB

    scan_id = _insert_scan("ONCE")
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    body = {"scan_id": scan_id, "decision": "REJECTED", "note": "only once"}
    for _ in range(4):
        assert open_client.post("/api/v1/review", json=body, headers=key).status_code == 200
    with SignalDB() as db:
        n = db.conn.execute(
            "SELECT COUNT(*) n FROM decisions WHERE scan_id=?", (scan_id,)
        ).fetchone()["n"]
    assert n == 1, f"expected exactly one decision row, got {n}"


def test_same_key_different_body_is_rejected(open_client):
    """Silently returning the old result for a *different* request would hide
    a real client bug — and could hide a wrong trade decision."""
    scan_id = _insert_scan("REUSE")
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    assert (
        open_client.post(
            "/api/v1/review",
            json={"scan_id": scan_id, "decision": "REJECTED"},
            headers=key,
        ).status_code
        == 200
    )
    r = open_client.post(
        "/api/v1/review", json={"scan_id": scan_id, "decision": "APPROVED"}, headers=key
    )
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.IDEMPOTENCY_KEY_REUSED


def test_too_short_key_is_refused_not_ignored(open_client):
    """A client sending a weak key believes it has retry safety. Ignoring the
    key silently would leave it exposed to exactly the double-apply it tried
    to prevent."""
    r = open_client.post(
        "/api/v1/review",
        json={"scan_id": _insert_scan("SHORT"), "decision": "REJECTED"},
        headers={apiv1.IDEMPOTENCY_HEADER: "abc"},
    )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.BAD_REQUEST


def test_a_failed_call_does_not_poison_the_key(open_client):
    """If the first attempt failed, the same key must still be usable — the
    user has not yet had their action applied."""
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    bad = open_client.post(
        "/api/v1/review", json={"scan_id": 999999, "decision": "REJECTED"}, headers=key
    )
    assert bad.status_code == 404
    # A failure is a real, cacheable outcome for the *same* request...
    again = open_client.post(
        "/api/v1/review", json={"scan_id": 999999, "decision": "REJECTED"}, headers=key
    )
    assert again.status_code == 404
    assert again.get_json()["error"]["code"] == apiv1.ErrorCode.NOT_FOUND


def test_journal_is_idempotent(open_client):
    scan_id = _insert_scan("JRN")
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    body = {"scan_id": scan_id, "followed_rules": True, "emotion": "calm"}
    first = open_client.post("/api/v1/journal", json=body, headers=key)
    assert first.status_code == 200
    second = open_client.post("/api/v1/journal", json=body, headers=key)
    assert second.get_json()["meta"]["idempotent_replay"] is True


def test_paper_run_is_idempotent(open_client):
    key = {apiv1.IDEMPOTENCY_HEADER: str(uuid.uuid4())}
    first = open_client.post("/api/v1/paper/run", json={}, headers=key)
    assert first.status_code == 200
    second = open_client.post("/api/v1/paper/run", json={}, headers=key)
    assert second.get_json()["meta"]["idempotent_replay"] is True
    assert second.get_json()["data"] == first.get_json()["data"]


def test_declared_idempotent_routes_are_the_human_mutations():
    """Guard against a future mutation being added without retry safety."""
    assert apiv1.idempotent_paths() == {
        "/review",
        "/journal",
        "/paper/run",
        "/trader-state",
    }


def test_validate_key_unit():
    assert apiv1.validate_key(None) is None
    assert apiv1.validate_key("   ") is None
    assert apiv1.validate_key("a" * 12) == "a" * 12
    with pytest.raises(ValueError):
        apiv1.validate_key("short")
    with pytest.raises(ValueError):
        apiv1.validate_key("x" * (apiv1.MAX_IDEMPOTENCY_KEY_LEN + 1))


def test_fingerprint_is_order_insensitive_but_value_sensitive():
    a = apiv1.request_fingerprint("/review", {"scan_id": 1, "decision": "APPROVED"})
    b = apiv1.request_fingerprint("/review", {"decision": "APPROVED", "scan_id": 1})
    c = apiv1.request_fingerprint("/review", {"scan_id": 2, "decision": "APPROVED"})
    assert a == b and a != c


def test_idempotency_store_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "idem.db"))
    store = apiv1.IdempotencyStore()
    fp = apiv1.request_fingerprint("/review", {"a": 1})
    assert store.lookup("k" * 10, 1, "/review", fp)[0] == "miss"
    assert store.reserve("k" * 10, 1, "/review", fp) is True
    assert store.reserve("k" * 10, 1, "/review", fp) is False
    assert store.lookup("k" * 10, 1, "/review", fp)[0] == "in_progress"
    store.complete("k" * 10, 1, "/review", 200, {"ok": True})
    state, cached = store.lookup("k" * 10, 1, "/review", fp)
    assert state == "replay" and cached == (200, {"ok": True})
    other = apiv1.request_fingerprint("/review", {"a": 2})
    assert store.lookup("k" * 10, 1, "/review", other)[0] == "conflict"


def test_keys_are_scoped_per_user(monkeypatch, tmp_path):
    """Two operators using the same key string must not collide."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "idem2.db"))
    store = apiv1.IdempotencyStore()
    fp = apiv1.request_fingerprint("/review", {"a": 1})
    assert store.reserve("shared-key-1", 1, "/review", fp) is True
    assert store.reserve("shared-key-1", 2, "/review", fp) is True


def test_expired_key_is_reusable(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "idem3.db"))
    store = apiv1.IdempotencyStore()
    fp = apiv1.request_fingerprint("/review", {"a": 1})
    store.reserve("expiring-key-1", 1, "/review", fp)
    store.complete("expiring-key-1", 1, "/review", 200, {"ok": True})
    from data.database import SignalDB

    with SignalDB() as db:
        db.conn.execute(
            "UPDATE idempotency_keys SET created_ts=?",
            (int(time.time()) - apiv1.IDEMPOTENCY_TTL_SECONDS - 10,),
        )
        db.conn.commit()
    assert store.lookup("expiring-key-1", 1, "/review", fp)[0] == "miss"


# ══════════════════════════════════════════════════════════════════════════
# 5. security invariants on the new surface (mirrors tests/test_auth.py)
# ══════════════════════════════════════════════════════════════════════════
def test_unauthenticated_cannot_read_private_state(client):
    _setup_owner(client)
    anon = client.application.test_client()
    for path in (
        "/api/v1/risk",
        "/api/v1/pending",
        "/api/v1/trades",
        "/api/v1/audit",
        "/api/v1/me",
    ):
        r = anon.get(path)
        assert r.status_code == 401, path
        body = r.get_json()
        _assert_envelope(body)
        assert body["error"]["code"] == apiv1.ErrorCode.UNAUTHENTICATED


def test_unauthenticated_cannot_mutate(client):
    _setup_owner(client)
    anon = client.application.test_client()
    for path, payload in (
        ("/api/v1/review", {"scan_id": 1, "decision": "APPROVED"}),
        ("/api/v1/journal", {"scan_id": 1}),
        ("/api/v1/paper/run", {}),
        ("/api/v1/trader-state", {"angry": True}),
        ("/api/v1/devices", {"name": "x"}),
    ):
        r = anon.post(path, json=payload)
        assert r.status_code == 401, path
        assert r.get_json()["error"]["code"] == apiv1.ErrorCode.UNAUTHENTICATED


def test_viewer_token_cannot_approve_reject_or_close(client):
    csrf = _setup_owner(client)
    viewer = _mint(client, csrf, "phone", "viewer")
    anon = client.application.test_client()
    scan_id = _insert_scan("VIEW")
    for decision in ("APPROVED", "REJECTED", "CLOSED"):
        r = anon.post(
            "/api/v1/review",
            json={"scan_id": scan_id, "decision": decision},
            headers=_bearer(viewer),
        )
        assert r.status_code == 403, decision
        body = r.get_json()
        assert body["error"]["code"] == apiv1.ErrorCode.FORBIDDEN
        assert body["error"]["details"]["required_role"] == "operator"


def test_viewer_token_can_read(client):
    csrf = _setup_owner(client)
    viewer = _mint(client, csrf, "phone", "viewer")
    anon = client.application.test_client()
    r = anon.get("/api/v1/risk", headers=_bearer(viewer))
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_viewer_token_cannot_mint_or_revoke_devices(client):
    """Privilege escalation check: a viewer-scoped token must not be able to
    mint an operator-scoped one."""
    csrf = _setup_owner(client)
    viewer = _mint(client, csrf, "phone", "viewer")
    anon = client.application.test_client()
    r = anon.post(
        "/api/v1/devices",
        json={"name": "evil", "scope": "operator"},
        headers=_bearer(viewer),
    )
    assert r.status_code == 403
    r = anon.post("/api/v1/devices/revoke", json={"id": "whatever"}, headers=_bearer(viewer))
    assert r.status_code == 403


def test_viewer_cannot_read_the_audit_log(client):
    csrf = _setup_owner(client)
    viewer = _mint(client, csrf, "phone", "viewer")
    anon = client.application.test_client()
    r = anon.get("/api/v1/audit", headers=_bearer(viewer))
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.FORBIDDEN


def test_operator_cannot_bypass_the_risk_gate(client):
    """The P18.1 invariant must survive the new surface."""
    csrf = _setup_owner(client)
    operator = _mint(client, csrf, "laptop", "operator")
    anon = client.application.test_client()
    from data.database import SignalDB

    with SignalDB() as db:
        db.set_trader_state(angry=True, note="tilted")
    scan_id = _insert_scan("BYPASS")
    r = anon.post(
        "/api/v1/review",
        json={"scan_id": scan_id, "decision": "APPROVED"},
        headers=_bearer(operator),
    )
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.RISK_GATE_CLOSED
    # ...and force-approve is still disabled
    r = anon.post(
        "/api/v1/review",
        json={"scan_id": scan_id, "decision": "APPROVED", "force": True},
        headers=_bearer(operator),
    )
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.FORBIDDEN


def test_cookie_mutations_require_csrf(client):
    """v1 inherits CSRF protection — and reports it in the v1 envelope."""
    _setup_owner(client)
    r = client.post("/api/v1/paper/run", json={})
    assert r.status_code == 403
    body = r.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == apiv1.ErrorCode.CSRF


def test_bearer_tokens_do_not_need_csrf(client):
    """Companion clients have no cookie, so CSRF does not apply to them."""
    csrf = _setup_owner(client)
    operator = _mint(client, csrf, "laptop", "operator")
    anon = client.application.test_client()
    r = anon.post("/api/v1/paper/run", json={}, headers=_bearer(operator))
    assert r.status_code == 200


def test_revoked_device_token_is_refused(client):
    csrf = _setup_owner(client)
    operator = _mint(client, csrf, "laptop", "operator")
    anon = client.application.test_client()
    assert anon.get("/api/v1/risk", headers=_bearer(operator)).status_code == 200
    devices = client.get("/api/v1/devices").get_json()["data"]["devices"]
    handle = next(d["id"] for d in devices if d["name"] == "laptop")
    r = client.post("/api/v1/devices/revoke", json={"id": handle}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert anon.get("/api/v1/risk", headers=_bearer(operator)).status_code == 401


def test_revoking_an_unknown_device_is_not_found(client):
    csrf = _setup_owner(client)
    r = client.post("/api/v1/devices/revoke", json={"id": "nope"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.NOT_FOUND


def test_device_registration_requires_a_name(client):
    csrf = _setup_owner(client)
    r = client.post("/api/v1/devices", json={"scope": "viewer"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.VALIDATION_FAILED


def test_device_scope_must_be_a_known_role(client):
    csrf = _setup_owner(client)
    r = client.post(
        "/api/v1/devices",
        json={"name": "x", "scope": "admin"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == apiv1.ErrorCode.VALIDATION_FAILED


def test_connected_device_list_is_visible(client):
    csrf = _setup_owner(client)
    _mint(client, csrf, "phone", "viewer")
    _mint(client, csrf, "laptop", "operator")
    data = client.get("/api/v1/devices").get_json()["data"]
    assert data["count"] == 2
    names = {d["name"] for d in data["devices"]}
    assert names == {"phone", "laptop"}
    # the raw token must never be listed back
    for device in data["devices"]:
        assert "token" not in device


def test_every_mutating_v1_route_is_declared_with_a_role():
    """Fail-closed guard: an undeclared mutating route defaults to operator,
    but it should never be undeclared in the first place.

    Pairing redeem (``POST /pair``) is the only public mutation: the device
    does not have a token yet. The one-time code is the credential. Every
    other POST stays viewer/operator.
    """
    public_posts = set()
    for route in apiv1.ROUTES + apiv1.NATIVE_ROUTES:
        if route["method"] != "POST":
            continue
        role = route.get("role")
        if role == "public":
            public_posts.add(route["path"])
            continue
        assert role in ("viewer", "operator"), route
    assert public_posts == {"/pair"}


def test_v1_adds_no_route_the_legacy_api_did_not_have():
    """v1 is a contract over existing behaviour. A v1-only *capability* would
    mean the security review of the legacy surface no longer covers us."""
    from web.app import make_app

    app = make_app()
    legacy = {
        str(r.rule)
        for r in app.url_map.iter_rules()
        if str(r.rule).startswith("/api/") and "/v1/" not in str(r.rule)
    }
    for route in apiv1.ROUTES:
        assert route["legacy"] in legacy, route
