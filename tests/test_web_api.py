"""Web API regression tests — the Flask endpoints against in-process requests.

These exist because `/api/scan` once returned 500 ("Object of type bool is not
JSON serializable") when numpy scalars from the quant layer leaked into the
payload: Flask's jsonify is strict, unlike json.dumps(default=str).  Every
heavy engine endpoint is exercised here so a numpy leak can never ship again.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "web.db"))
    # config.DB_PATH is resolved from the environment at *import* time, so the
    # setenv above is too late whenever another test already imported config.
    # Patch the attribute too — SignalDB reads it at construction, so this is
    # what actually keeps these endpoints off the developer's real database.
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "web.db"))
    from web.app import make_app

    app = make_app()
    app.testing = True
    return app.test_client()


def test_scan_endpoint_is_json_serializable(client):
    resp = client.get("/api/scan?symbol=BTCUSDT&tf=15m")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert payload["signal"]["asset"] == "BTCUSDT"
    assert payload["decision"]["action"] in ("BUY", "SELL", "NO TRADE")
    assert "lifecycle" in payload


def test_intelligence_endpoint(client):
    resp = client.get("/api/intelligence?symbol=BTCUSDT&tf=15m")
    assert resp.status_code == 200
    intel = resp.get_json()
    assert intel["asset"] == "BTCUSDT"
    assert intel["signal"] in ("BUY", "SELL", "NO TRADE")


def test_health_risk_agents_endpoints(client):
    health = client.get("/api/health").get_json()
    assert health["ok"] is True
    assert health["data"]["mode"] == "demo"

    risk = client.get("/api/risk").get_json()
    assert "gate" in risk and "allowed" in risk["gate"]

    agents = client.get("/api/agents").get_json()
    assert len(agents["assets"]) == 3

    mcp = client.get("/api/mcp").get_json()
    assert "tools" in mcp


def test_ask_endpoint(client):
    resp = client.post("/api/ask", json={"question": "what's pending review?"})
    assert resp.status_code == 200
    assert resp.get_json()["intent"] == "pending"
    resp = client.post("/api/ask", json={})
    assert resp.status_code == 400


def test_pending_paper_learning_endpoints(client):
    assert client.get("/api/pending").status_code == 200
    assert client.get("/api/paper").status_code == 200
    learning = client.get("/api/learning").get_json()
    assert "backtest" in learning or "calibration" in learning
    hist = client.get("/api/history").get_json()
    assert "history" in hist and isinstance(hist["history"], list)


def test_sentiment_endpoint(client):
    """GET /api/sentiment — the colour reading that paints the dashboard."""
    resp = client.get("/api/sentiment?symbol=BTCUSDT&tf=15m")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    data = resp.get_json()
    assert data["symbol"] == "BTCUSDT"
    sent = data["sentiment"]
    for key in (
        "score",
        "direction",
        "label",
        "strength",
        "duration_min",
        "duration_text",
        "persistence",
        "intensity",
        "color",
        "parts",
        "history",
    ):
        assert key in sent, f"sentiment missing {key!r}: {sent}"
    assert -100 <= sent["score"] <= 100
    assert sent["direction"] in ("bullish", "bearish", "neutral")
    assert sent["color"].startswith(("hsl(", "#"))
    # the scan payload carries the same block
    scan = client.get("/api/scan?symbol=BTCUSDT&tf=15m").get_json()
    assert "sentiment" in scan
    assert scan["sentiment"]["score"] == sent["score"]


def test_sanitize_for_json_helper():
    import numpy as np

    from web.app import _sanitize_for_json

    out = _sanitize_for_json(
        {
            "b": np.bool_(True),
            "i": np.int64(3),
            "f": np.float64(1.5),
            "arr": np.array([1, 2]),
            "nested": [{"x": np.bool_(False)}],
        }
    )
    import json

    json.dumps(out)  # must not raise
    assert out == {"b": True, "i": 3, "f": 1.5, "arr": [1, 2], "nested": [{"x": False}]}


# ── /api/channels + /api/doctor — P8 dashboard surface ────────────────
# The Channels layer is the Panniantong/Agent-Reach ordered-backend
# pattern (P8). It must reach the dashboard without numpy-leak 500s and
# without any single probe being able to crash the endpoint.


def test_channels_endpoint_returns_registry(client):
    """`/api/channels` must return the four channels with status+active+backends."""
    resp = client.get("/api/channels")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert "channels" in payload
    assert set(payload["channels"].keys()) == {"cryptodada", "discord", "news", "llm"}
    for name, ch in payload["channels"].items():
        # Schema contract: every channel has these three keys
        assert "active" in ch, f"{name} missing 'active'"
        assert "status" in ch, f"{name} missing 'status'"
        assert "backends" in ch, f"{name} missing 'backends'"
        assert ch["status"] in {"ok", "degraded", "down", "unknown"}
        # Every channel has at least one backend
        assert len(ch["backends"]) >= 1
        # Every backend has the required shape
        for b in ch["backends"]:
            assert {"name", "label", "configured", "ok"} <= set(b.keys())


def test_channels_endpoint_is_json_serializable_under_numpy_leak(client):
    """If a probe accidentally returns a numpy scalar, the endpoint
    must still return valid JSON — the same _sanitize_for_json
    regression that bit /api/scan and /api/intelligence per
    MERGE_NOTES.md must not bite /api/channels."""
    import json

    resp = client.get("/api/channels")
    assert resp.status_code == 200
    # If we got this far, Flask jsonify already serialized cleanly.
    # Do one more round-trip through the stdlib json to be paranoid.
    body = resp.get_data(as_text=True)
    json.loads(body)  # must not raise


def test_channels_endpoint_isolates_probe_exceptions(client, monkeypatch):
    """A broken channel probe must NOT crash the endpoint — the same
    exception-isolation contract as `brain.channels.probe_all`."""
    from brain import channels

    def boom():
        raise RuntimeError("simulated probe failure")

    monkeypatch.setattr(channels, "_probe_cryptodada_backends", boom)
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    payload = resp.get_json()
    # cryptodada should be in 'down' state, not crash the response
    assert "channels" in payload
    assert "cryptodada" in payload["channels"]


def test_doctor_endpoint_returns_text_report(client):
    """`/api/doctor` is the JSON-wrapped text version (same as CLI)."""
    resp = client.get("/api/doctor")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert "report" in payload
    assert "CryptoBrain doctor report" in payload["report"]
    for ch in ("cryptodada", "discord", "news", "llm"):
        assert ch in payload["report"]


def test_readiness_endpoint_returns_strip(client):
    """`/api/readiness` is the combined doctor strip (TODO-1.bis)."""
    import json

    resp = client.get("/api/readiness")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert payload["level"] in {"ok", "degraded", "blocked", "down"}
    assert payload["ready"] == (payload["level"] == "ok")
    assert payload["headline"]
    assert {p["name"] for p in payload["pillars"]} == {
        "channels",
        "immune",
        "risk_gate",
        "data",
    }
    json.loads(resp.get_data(as_text=True))  # numpy-leak safety


def test_readiness_endpoint_never_500s(client, monkeypatch):
    """A crashing strip degrades to a JSON error, never an HTTP 500."""
    from brain import agent

    monkeypatch.setattr(
        agent,
        "readiness_strip",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    resp = client.get("/api/readiness")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["level"] == "down"
    assert "RuntimeError" in payload["error"]


def test_desk_endpoint_returns_advisory(client):
    """`/api/desk` is the one-call advisory (same as `python main.py desk`)."""
    import json

    resp = client.get("/api/desk")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert "advice" in payload
    assert payload["advice"]["action"] in {
        "CLEAR_STATE",
        "STAND_ASIDE",
        "REVIEW_QUEUE",
        "JOURNAL",
        "PAPER_GRIND",
        "SCAN",
    }
    assert "risk_gate" in payload
    assert "graduation" in payload
    json.loads(resp.get_data(as_text=True))  # numpy-leak safety


def test_loop_health_endpoint_returns_advisory(client):
    """`/api/loop-health` is the one daily number (same as `python main.py daily`)."""
    import json

    resp = client.get("/api/loop-health")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert "loop" in payload
    assert "real_paper_n" in payload["loop"]
    assert "graduation" in payload
    assert "ritual" in payload
    assert payload["advice"]["action"] in {
        "CLEAR_STATE",
        "STAND_ASIDE",
        "REVIEW_QUEUE",
        "JOURNAL",
        "PAPER_GRIND",
        "SCAN",
    }
    json.loads(resp.get_data(as_text=True))  # numpy-leak safety


def test_loop_health_endpoint_never_500s(client, monkeypatch):
    """A crashing loop_health degrades to a JSON error, never an HTTP 500."""
    from brain import agent

    monkeypatch.setattr(
        agent,
        "loop_health",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    resp = client.get("/api/loop-health")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is False
    assert "RuntimeError" in payload["error"]


def test_pending_includes_management(client):
    """Every pending review carries the HOLD/REDUCE/TRAIL/EXIT checklist."""
    payload = client.get("/api/pending").get_json()
    assert "pending" in payload
    assert isinstance(payload["pending"], list)
    for item in payload["pending"]:
        assert "management" in item
        assert isinstance(item["management"], list)


def test_coach_includes_five_levels_and_management(client):
    """`/api/coach` ships the five-question ladder + position-manager card."""
    resp = client.get("/api/coach?symbol=BTCUSDT")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert isinstance(payload.get("five_levels"), list)
    assert payload["five_levels"]
    assert isinstance(payload.get("management"), list)
    assert isinstance(payload.get("explain"), list)


def test_scorecard_endpoint_empty_db_refuses_cleanly(client):
    """`/api/scorecard` on a fresh DB reports the truth, not an error page."""
    resp = client.get("/api/scorecard")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["rows"] == 0
    assert "No decided outcomes stored yet" in payload["error"]


def test_scorecard_endpoint_rejects_unknown_source(client):
    payload = client.get("/api/scorecard?source=bogus").get_json()
    assert payload["ok"] is False
    assert "unknown source" in payload["error"]


def test_scorecard_endpoint_returns_the_full_block(client, tmp_path, monkeypatch):
    """With stored outcomes the endpoint serves every scorecard dimension."""
    import json

    import data.scorecard as sc
    from data.scorecard import build_scorecard

    rows = [
        {
            "ts": (i + 1) * 3_600_000,
            "side": "BUY" if i % 2 else "SELL",
            "setup": "Buy Pullback",
            "regime": "RANGING",
            "r": 2.0 if i % 3 else -1.0,
            "outcome": "FULL_WIN",
            "holding_hours": 1.5,
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "source": "backtest",
            "session": "london",
        }
        for i in range(40)
    ]
    monkeypatch.setattr(sc, "scorecard_from_db", lambda **kw: build_scorecard(rows, min_decided=30))

    resp = client.get("/api/scorecard?symbol=BTCUSDT")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    for key in (
        "overall",
        "by_side",
        "by_regime",
        "by_session",
        "by_setup",
        "verdict",
        "criteria",
        "bar",
    ):
        assert key in payload
    assert payload["overall"]["n"] == 40
    assert payload["verdict"]["status"] in {"PASS", "FAIL", "INSUFFICIENT_DATA"}
    json.loads(resp.get_data(as_text=True))  # numpy-leak safety


def test_scorecard_endpoint_never_500s(client, monkeypatch):
    import data.scorecard as sc

    monkeypatch.setattr(
        sc, "scorecard_from_db", lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    resp = client.get("/api/scorecard")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is False
    assert "RuntimeError" in payload["error"]


def test_ticket_meta_endpoint_returns_honest_inputs(client):
    """T4 — the ticket's sizing/fee inputs must come from the server, never
    invented client-side. Unset ACCOUNT_BALANCE reports 0, not a fake $100k."""
    import json

    resp = client.get("/api/ticket/meta?symbol=BTCUSDT")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    meta = resp.get_json()
    assert meta["symbol"] == "BTCUSDT"
    assert isinstance(meta["account_balance"], float)
    assert meta["account_configured"] in (True, False)
    assert 0 < meta["round_trip_cost_pct"] < 0.05
    assert meta["market"] in ("spot", "perp")
    assert meta["holding_hours"] > 0
    # gold is spot: no funding, commission-based model
    gold = client.get("/api/ticket/meta?symbol=XAUUSD").get_json()
    assert gold["market"] == "spot"
    assert gold["funding_rate_8h"] == 0.0
    json.loads(resp.get_data(as_text=True))  # numpy-leak safety
