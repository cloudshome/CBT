"""P20 Windows companion — pairing, URL/TLS, token privacy, no-order."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from ops.windows_companion import (
    CompanionError,
    TokenStore,
    companion_spec,
    format_spec,
    mutation_headers,
    negotiate_version,
    pair_with_hub,
    pairing_payload,
    tray_status,
    validate_hub_url,
)
from web.api_v1 import version_info
from web.auth import AuthManager


def test_https_required_for_remote():
    with pytest.raises(CompanionError):
        validate_hub_url("http://desk.example.com")
    assert validate_hub_url("https://desk.example.com") == "https://desk.example.com"
    assert validate_hub_url("http://127.0.0.1:8050").startswith("http://127.0.0.1")


def test_rejects_url_path():
    with pytest.raises(CompanionError):
        validate_hub_url("https://desk.example.com/api/v1")


def test_negotiate_refuses_live_execution():
    info = version_info()
    info = dict(info)
    info["capabilities"] = dict(info["capabilities"], live_exchange_execution=True)
    with pytest.raises(CompanionError):
        negotiate_version(info)


def test_negotiate_accepts_current_hub():
    out = negotiate_version(version_info())
    assert out["ok"] and out["live_exchange_execution"] is False


def test_pairing_payload_qr():
    p = pairing_payload(hub_url="https://hub.local", code="ABCD1234")
    assert p["v"] == 1 and p["live_exchange_execution"] is False
    assert p["code"] == "ABCD-1234"


def test_token_store_refuses_without_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("SKY_COMPANION_ALLOW_FILE_TOKEN", raising=False)
    store = TokenStore(tmp_path / "c.json")
    with pytest.raises(CompanionError):
        store.save(
            hub_url="https://hub.local",
            token="secret-token-value",
            scope="viewer",
            name="pc",
        )


def test_token_store_private_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SKY_COMPANION_ALLOW_FILE_TOKEN", "1")
    store = TokenStore(tmp_path / "c.json")
    rec = store.save(
        hub_url="https://hub.local",
        token="secret-token-value",
        scope="viewer",
        name="pc",
    )
    assert rec["stored"] == "file"
    mode = store.path.stat().st_mode
    assert not (mode & stat.S_IROTH)
    loaded = store.load()
    assert loaded["token"] == "secret-token-value"
    assert "secret-token-value" not in json.dumps(
        {k: v for k, v in rec.items() if k != "token"}
    )


def test_pair_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKY_COMPANION_ALLOW_FILE_TOKEN", "1")
    monkeypatch.setenv("SKY_AUTH_MODE", "disabled")
    db = tmp_path / "s.db"
    monkeypatch.setattr("config.DB_PATH", str(db), raising=False)
    import config

    monkeypatch.setattr(config, "DB_PATH", str(db))
    mgr = AuthManager(db)
    owner = mgr.create_owner("azim", "password12")
    minted = mgr.create_pairing_code(owner["id"], name="laptop")

    def transport(method, url, json=None, headers=None):
        assert method == "POST" and url.endswith("/api/v1/pair")
        result = mgr.redeem_pairing_code(json["code"], json["name"])
        return {"ok": True, "data": result, "error": None}

    store = TokenStore(tmp_path / "state.json")
    out = pair_with_hub(
        hub_url="https://hub.local",
        code=minted["code"],
        device_name="laptop",
        transport=transport,
        store=store,
    )
    assert out["paired"] is True
    with pytest.raises(PermissionError):
        mgr.redeem_pairing_code(minted["raw"], "again")


def test_flask_pair_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("SKY_AUTH_MODE", "required")
    monkeypatch.setenv("SKY_NO_AUTO_INSTALL", "1")
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "web.db"))
    monkeypatch.setattr(config, "SKY_AUTH_MODE", "required")
    from web.app import make_app
    from web.jobs import JobManager

    app = make_app(job_manager=JobManager(db_path=str(tmp_path / "web.db")))
    client = app.test_client()
    setup = client.post(
        "/api/auth/setup", json={"username": "azim", "password": "password12"}
    )
    assert setup.status_code == 200
    csrf = setup.get_json().get("csrf") or ""
    minted = client.post(
        "/api/v1/pair/code",
        json={"name": "win-pc", "hub_url": "https://hub.local"},
        headers={"X-CSRF-Token": csrf},
    )
    assert minted.status_code == 201
    body = minted.get_json()
    assert body["ok"] and body["data"]["code"]
    redeem = client.post(
        "/api/v1/pair", json={"code": body["data"]["code"], "name": "win-pc"}
    )
    assert redeem.status_code == 201
    token = redeem.get_json()["data"]["token"]
    assert token
    again = client.post(
        "/api/v1/pair", json={"code": body["data"]["code"], "name": "win-pc"}
    )
    assert again.status_code == 403


def test_tray_offline_blocks_mutations():
    snap = tray_status({}, {}, connected=False)
    assert snap["stale"] and not snap["mutations_allowed"]
    assert snap["live_exchange_execution"] is False


def test_idempotency_headers():
    h = mutation_headers(token="abc")
    assert h["Authorization"] == "Bearer abc"
    assert "Idempotency-Key" in h


def test_spec_is_unsigned():
    spec = companion_spec()
    assert spec["signed"] is False
    assert spec["live_exchange_execution"] is False
    assert "NO" in format_spec(spec)


def test_no_order_path_in_companion():
    src = (
        Path(__file__)
        .resolve()
        .parent.parent.joinpath("ops/windows_companion.py")
        .read_text()
    )
    for banned in ("create_order", "newOrder", "/api/v3/order", "place_order"):
        assert banned not in src


def test_cli_companion_spec(monkeypatch):
    monkeypatch.setenv("SKY_NO_AUTO_INSTALL", "1")
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main

    assert main(["companion", "spec", "--json"]) == 0
    assert main(["companion", "validate-url", "--hub", "https://hub.example"]) == 0


def test_packaging_windows_exists():
    root = Path(__file__).resolve().parent.parent
    assert (root / "packaging" / "windows" / "README.md").is_file()
    text = (root / "packaging" / "windows" / "README.md").read_text()
    assert "unsigned" in text.lower()
    assert "credential manager" in text.lower()
