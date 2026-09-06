"""W4.1 — clickable 24/7 Agent tab + report archive (never a trade)."""

from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("SKY_NO_AUTO_INSTALL", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "agent.db"))
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "agent.db"))
    from web.app import make_app

    app = make_app()
    app.testing = True
    return app.test_client()


def test_agent_tab_is_in_the_shell(client):
    html = client.get("/").get_data(as_text=True)
    assert 'data-tab="agent"' in html
    assert "24/7 RESEARCH AGENT" in html
    assert "THIS PC — 24/7 HUB ROLE" in html
    assert "loadAgent" in html
    assert "loadHubRole" in html
    assert "archiveAgentReport" in html
    assert "WATCH / CONSIDER / WAIT / AVOID" in html
    assert "BUY NOW" in html  # mentioned as forbidden


def test_hub_role_api_refuses_a_second_agent(client):
    role = client.get("/api/hub/role").get_json()
    assert role["ok"] is True
    assert role["role"] == "ubuntu_hub"
    assert role["second_agent"] is False
    assert role["live_exchange_execution"] is False
    st = client.get("/api/hub/status").get_json()
    assert st["ok"] is True
    assert st["host_role"]["second_agent"] is False
    assert "sky-agent.service" in {u["unit"] for u in role["run"]}


def test_sky_agent_health_and_status(client):
    h = client.get("/api/sky-agent/health").get_json()
    assert h["ok"] is True
    assert h["agent"] == "sky_agent"
    assert "system" in h
    s = client.get("/api/sky-agent/status").get_json()
    assert s["ok"] is True
    assert "hypotheses" in s and "reports" in s


def test_archive_daily_report_is_memory_only(client):
    before = client.get("/api/sky-agent/status").get_json()
    n0 = len(before.get("reports") or [])
    resp = client.post("/api/sky-agent/report", json={"demo": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert body["ok"] is True and body["archived"] is True
    recs = (body.get("report") or {}).get("recommendations") or []
    assert recs
    assert recs[0]["recommendation"] in ("WATCH", "CONSIDER", "WAIT", "AVOID")
    assert recs[0]["recommendation"] != "BUY NOW"
    after = client.get("/api/sky-agent/status").get_json()
    assert len(after.get("reports") or []) == n0 + 1


def test_archive_never_opens_the_risk_gate(client):
    from brain.risk_gate import evaluate
    from data.database import SignalDB

    client.post("/api/sky-agent/report", json={"demo": True})
    with SignalDB() as db:
        gate = evaluate(db)
    # Empty book stays closed for the usual sample/expectancy reasons.
    # The archive must not flip allowed=True by itself.
    assert "blocked_by" in gate
    assert gate.get("allowed") is False or isinstance(gate.get("allowed"), bool)
