"""P21 Android companion — pairing, allowlist, Keystore privacy, no-order."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from ops.android_companion import (
    CompanionError,
    KeystoreTokenStore,
    android_spec,
    biometric_policy,
    connection_snapshot,
    deep_link,
    deep_link_surface,
    format_spec,
    host_allowed,
    mutation_headers,
    negotiate_version,
    pair_with_hub,
    pairing_payload,
    read_headers,
    requires_biometric,
    validate_hub_url,
)
from web.api_v1 import version_info
from web.auth import AuthManager


def test_https_required_for_remote():
    with pytest.raises(CompanionError):
        validate_hub_url("http://desk.example.com")
    assert validate_hub_url("https://desk.example.com") == "https://desk.example.com"
    assert validate_hub_url("http://127.0.0.1:8050").startswith("http://127.0.0.1")


def test_host_allowlist_fails_closed():
    assert host_allowed("https://desk.example.com", None) is False
    assert host_allowed("https://desk.example.com", "") is False
    assert host_allowed("https://evil.net", "desk.example.com") is False
    assert host_allowed("https://desk.example.com", "desk.example.com") is True
    assert host_allowed("https://x.example.com", ".example.com") is True
    assert host_allowed("https://example.com", ".example.com") is False


def test_negotiate_refuses_live_execution():
    info = dict(version_info())
    info["capabilities"] = dict(info["capabilities"], live_exchange_execution=True)
    with pytest.raises(CompanionError):
        negotiate_version(info)


def test_negotiate_accepts_current_hub():
    out = negotiate_version(version_info())
    assert out["ok"] and out["live_exchange_execution"] is False
    assert out["client_name"] == "sky-android"


def test_pairing_payload_android():
    p = pairing_payload(hub_url="https://hub.local", code="ABCD1234")
    assert p["v"] == 1 and p["client"] == "sky-android"
    assert p["platform"] == "android"
    assert p["code"] == "ABCD-1234"
    assert p["live_exchange_execution"] is False


def test_keystore_store_refuses_without_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("SKY_ANDROID_ALLOW_FILE_TOKEN", raising=False)
    store = KeystoreTokenStore(tmp_path / "k.json")
    with pytest.raises(CompanionError):
        store.save(hub_url="https://hub.local", token="secret-token-value",
                   scope="viewer", name="phone")


def test_keystore_store_private_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SKY_ANDROID_ALLOW_FILE_TOKEN", "1")
    store = KeystoreTokenStore(tmp_path / "k.json")
    rec = store.save(hub_url="https://hub.local", token="secret-token-value",
                     scope="viewer", name="phone")
    assert rec["stored"] == "file"
    mode = store.path.stat().st_mode
    assert not (mode & stat.S_IROTH)
    loaded = store.load()
    assert loaded["token"] == "secret-token-value"
    assert "secret-token-value" not in json.dumps({k: v for k, v in rec.items() if k != "token"})


def test_pair_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKY_ANDROID_ALLOW_FILE_TOKEN", "1")
    monkeypatch.setenv("SKY_AUTH_MODE", "disabled")
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "s.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "s.db"))
    mgr = AuthManager(tmp_path / "s.db")
    owner = mgr.create_owner("azim", "password12")
    minted = mgr.create_pairing_code(owner["id"], name="phone")

    def transport(method, url, json=None, headers=None):
        assert method == "POST" and url.endswith("/api/v1/pair")
        result = mgr.redeem_pairing_code(json["code"], json["name"])
        return {"ok": True, "data": result, "error": None}

    store = KeystoreTokenStore(tmp_path / "state.json")
    out = pair_with_hub(hub_url="https://hub.local", code=minted["code"],
                        device_name="phone", transport=transport, store=store)
    assert out["paired"] is True
    with pytest.raises(PermissionError):
        mgr.redeem_pairing_code(minted["raw"], "again")


def test_biometric_policy():
    policy = biometric_policy()
    assert policy["enabled"] is True and policy["scope"] == "operator"
    assert policy["live_exchange_execution"] is False
    assert requires_biometric("approve_paper") is True
    assert requires_biometric("journal_write") is True
    assert requires_biometric("approve_paper", scope="viewer") is False


def test_connection_snapshot_offline_blocks_mutations():
    snap = connection_snapshot(connected=False)
    assert snap["stale"] and not snap["mutations_allowed"]
    assert snap["offline_queue"] == "never"
    assert snap["live_exchange_execution"] is False


def test_connection_snapshot_stale_blocks_mutations():
    snap = connection_snapshot(connected=True, last_ok_ts=0)
    assert snap["stale"] and not snap["mutations_allowed"]


def test_deep_links():
    assert deep_link("paper", 42) == "sky://record/paper/42"
    assert deep_link("signal", "abc") == "sky://record/signal/abc"
    assert deep_link("dashboard") == "sky://record/dashboard"
    assert deep_link_surface("paper") == "/api/v1/paper/approvals/{id}"
    with pytest.raises(CompanionError):
        deep_link("nope", 1)


def test_mutation_read_headers():
    h = mutation_headers(token="abc")
    assert h["Authorization"] == "Bearer abc"
    assert "Idempotency-Key" in h
    r = read_headers(token="abc")
    assert r["Authorization"] == "Bearer abc"


def test_spec_is_unsigned():
    spec = android_spec()
    assert spec["signed"] is False
    assert spec["live_exchange_execution"] is False
    assert "Android Keystore" == spec["storage"]
    assert "NO" in format_spec(spec)


def test_no_order_path_in_companion():
    src = Path(__file__).resolve().parent.parent.joinpath("ops/android_companion.py").read_text()
    for banned in ("create_order", "newOrder", "/api/v3/order", "place_order"):
        assert banned not in src


def test_cli_companion_android_spec(monkeypatch):
    monkeypatch.setenv("SKY_NO_AUTO_INSTALL", "1")
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main
    assert main(["companion", "spec", "--platform", "android", "--json"]) == 0
    assert main(["companion", "validate-url", "--platform", "android",
                 "--hub", "https://hub.example"]) == 0


def test_packaging_android_exists():
    root = Path(__file__).resolve().parent.parent
    assert (root / "packaging" / "android" / "README.md").is_file()
    text = (root / "packaging" / "android" / "README.md").read_text()
    assert "unsigned" in text.lower()
    assert "android keystore" in text.lower()
