"""tests/test_pwa_push_and_analytics.py — Test PWA Web Push (VAPID), Veto Timeline & R-Distribution Analytics."""

import os
import tempfile
from pathlib import Path

import pytest

from brain.analytics import r_distribution
from brain.connections import _probe_webpush
from data.database import SignalDB
from data.push_notifications import (
    create_vapid_jwt,
    get_or_create_vapid_keys,
)
from web.app import make_app


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = SignalDB(db_path)
    yield db
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def tmp_vapid_key():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        key_path = Path(f.name)
    yield key_path
    if key_path.exists():
        os.remove(key_path)


@pytest.fixture
def app_client(tmp_db):
    app = make_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_vapid_key_generation(tmp_vapid_key):
    priv_key, pub_b64 = get_or_create_vapid_keys(tmp_vapid_key)
    assert priv_key is not None
    assert len(pub_b64) == 87 or len(pub_b64) == 88  # urlsafe b64 65 bytes

    # Calling again loads same key
    priv_key2, pub_b64_2 = get_or_create_vapid_keys(tmp_vapid_key)
    assert pub_b64 == pub_b64_2


def test_vapid_jwt_creation(tmp_vapid_key):
    endpoint = "https://fcm.googleapis.com/fcm/send/test123"
    jwt = create_vapid_jwt(endpoint, key_path=tmp_vapid_key)
    parts = jwt.split(".")
    assert len(parts) == 3
    assert parts[0].startswith("eyJ")


def test_push_subscriptions_db(tmp_db):
    ep = "https://push.example.com/sub/1"
    res = tmp_db.save_push_subscription(
        ep, p256dh="test_p256dh", auth="test_auth", user_agent="PyTest"
    )
    assert res["ok"] is True

    subs = tmp_db.list_push_subscriptions()
    assert len(subs) == 1
    assert subs[0]["endpoint"] == ep
    assert subs[0]["p256dh"] == "test_p256dh"

    removed = tmp_db.remove_push_subscription(ep)
    assert removed is True
    assert len(tmp_db.list_push_subscriptions()) == 0


def test_risk_veto_db_and_decision(tmp_db):
    res = tmp_db.record_risk_veto(
        symbol="BTCUSDT",
        setup="breakout",
        action="BUY",
        reason="Daily loss limit reached",
        veto_type="risk_gate",
    )
    assert res["id"] > 0

    vetoes = tmp_db.get_risk_vetoes(symbol="BTCUSDT")
    assert len(vetoes) == 1
    assert vetoes[0]["reason"] == "Daily loss limit reached"
    assert vetoes[0]["veto_type"] == "risk_gate"


def test_r_distribution_empty(tmp_db):
    dist = r_distribution(tmp_db)
    assert dist["available"] is False
    assert dist["total_trades"] == 0


def test_r_distribution_with_trades(tmp_db):
    # Insert decided paper trades directly into paper_trades table
    now = 1700000000
    tmp_db.conn.execute(
        "INSERT INTO paper_trades (scan_id, plan_type, symbol, timeframe, action, entry, stop_loss, take_profit, status, outcome, rr_achieved, closed_ts, source_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "trend",
            "BTCUSDT",
            "15m",
            "BUY",
            50000,
            49000,
            52000,
            "CLOSED",
            "TP_HIT",
            2.0,
            now,
            "",
        ),
    )
    tmp_db.conn.execute(
        "INSERT INTO paper_trades (scan_id, plan_type, symbol, timeframe, action, entry, stop_loss, take_profit, status, outcome, rr_achieved, closed_ts, source_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            2,
            "reversal",
            "ETHUSDT",
            "15m",
            "SELL",
            3000,
            3100,
            2800,
            "CLOSED",
            "STOP_LOSS",
            -1.0,
            now + 100,
            "",
        ),
    )
    tmp_db.conn.commit()

    dist = r_distribution(tmp_db)
    assert dist["available"] is True
    assert dist["total_trades"] == 2
    assert dist["wins_count"] == 1
    assert dist["losses_count"] == 1
    assert len(dist["bins"]) == 7


def test_push_endpoints(app_client):
    resp = app_client.get("/api/push/vapid-key")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert len(data["public_key"]) > 50

    # Subscribe endpoint
    sub_payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/client_test_123",
        "keys": {"p256dh": "dummy_p256dh_key", "auth": "dummy_auth_key"},
    }
    sub_resp = app_client.post("/api/push/subscribe", json=sub_payload)
    assert sub_resp.status_code == 200
    assert sub_resp.get_json()["ok"] is True

    # Test endpoint
    test_resp = app_client.post("/api/push/test")
    assert test_resp.status_code == 200
    assert test_resp.get_json()["ok"] is True

    # Unsubscribe endpoint
    unsub_resp = app_client.post(
        "/api/push/unsubscribe", json={"endpoint": sub_payload["endpoint"]}
    )
    assert unsub_resp.status_code == 200
    assert unsub_resp.get_json()["ok"] is True


def test_veto_timeline_endpoint(app_client):
    resp = app_client.get("/api/risk/veto-timeline")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert isinstance(data["vetoes"], list)


def test_r_distribution_endpoint(app_client):
    resp = app_client.get("/api/analytics/r-distribution")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "r_distribution" in data


def test_connection_probe_webpush():
    probe = _probe_webpush()
    assert probe["configured"] is True
    assert probe["live"] is True
    assert "VAPID active" in probe["detail"]


def test_generated_pwa_icons_exist():
    icons_dir = Path(__file__).parent.parent / "web" / "static" / "icons"
    for icon_name in [
        "icon-180.png",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
    ]:
        p = icons_dir / icon_name
        assert p.exists()
        assert p.stat().st_size > 1000
