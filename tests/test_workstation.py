"""Trading Workstation regression tests.

These guard the browser-first control centre the trader actually uses:

  * ``/api/chart`` and ``/api/candles`` must never leak a Pandas/NumPy value
    into Flask's strict jsonify — that exact failure blanked the chart;
  * the command catalog must be executable, allow-listed and shell-free;
  * the position sizer must respect the progression cap and refuse to size a
    trade when the risk gate is closed;
  * the journal form endpoints must round-trip an entry;
  * every workstation tab the dashboard advertises must exist in the HTML.
"""
from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ws.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "ws.db"))
    from web.app import make_app
    app = make_app()
    app.testing = True
    return app.test_client()


# ── chart feed ────────────────────────────────────────────────────────
def test_candles_are_json_serializable(client):
    """The old endpoint handed raw df.to_dict("records") to jsonify."""
    resp = client.get("/api/candles?symbol=BTCUSDT&tf=15m&limit=50")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body["candles"], "no candles returned"
    first = body["candles"][0]
    for key in ("time", "open", "high", "low", "close"):
        assert isinstance(first[key], (int, float)), f"{key} is {type(first[key])}"
    # must survive a strict re-serialization (what jsonify does internally)
    json.dumps(body)


def test_chart_workspace_payload(client):
    resp = client.get("/api/chart?symbol=BTCUSDT&tf=15m&limit=200")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    d = resp.get_json()
    assert d["candles"], "chart returned no candles"
    assert d["count"] == len(d["candles"])
    # Lightweight Charts needs strictly ascending epoch-SECOND timestamps
    times = [c["time"] for c in d["candles"]]
    assert times == sorted(times)
    assert all(t < 1e11 for t in times), "timestamps must be seconds, not ms"
    assert d["overlays"]["ema20"], "EMA overlay missing"
    assert d["panes"]["volume"], "volume pane missing"
    assert d["panes"]["rsi"], "RSI pane missing"
    assert "levels" in d and "plan" in d
    json.dumps(d)


def test_chart_numbers_are_native_python():
    """_num() converts every NumPy/Pandas scalar and drops NaN/inf."""
    import numpy as np
    import pandas as pd
    from web.chart_data import _epoch_seconds, _num
    assert _num(np.float64(1.5)) == 1.5
    assert _num(np.int64(7)) == 7.0
    assert _num(np.bool_(True)) == 1.0
    assert _num(float("nan")) is None
    assert _num(float("inf")) is None
    assert _num(pd.NA) is None
    assert _num(None) is None
    assert isinstance(_num(np.float64(2.25)), float)
    # milliseconds are normalized to seconds
    assert _epoch_seconds(1_780_000_000_000) == 1_780_000_000
    assert _epoch_seconds(1_780_000_000) == 1_780_000_000


# ── command center ────────────────────────────────────────────────────
def test_command_catalog_is_complete_and_documented(client):
    resp = client.get("/api/commands")
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["count"] > 40, "the catalog should expose the whole CLI surface"
    ids = set()
    for group in d["categories"]:
        assert group["commands"]
        for cmd in group["commands"]:
            assert cmd["what"], f"{cmd['id']} has no explanation"
            assert cmd["cli"].startswith("python main.py")
            assert cmd["safety"] in ("read", "write", "long", "blocked")
            ids.add(cmd["id"])
    # the categories the trader asked to see as clickable actions
    for expected in ("scan", "risk", "desk", "daily", "review", "approve",
                     "backtest", "scorecard", "journal_new", "backfill",
                     "channels", "coach", "doctor", "simulator"):
        assert expected in ids, f"missing clickable action: {expected}"


def test_command_argv_is_built_safely():
    from web.command_center import CommandError, build_argv
    assert build_argv("scan", {"symbol": "ETHUSDT", "tf": "1h", "json": True}) == [
        "scan", "--symbol", "ETHUSDT", "--tf", "1h", "--json"]
    # positionals land directly after the subcommand
    assert build_argv("approve", {"scan_id": 5, "force": True})[:2] == ["approve", "5"]
    assert build_argv("agent_morning", {})[:2] == ["agent", "morning"]
    # unknown ids and blocked long-lived processes are refused
    with pytest.raises(CommandError):
        build_argv("rm -rf /", {})
    with pytest.raises(CommandError):
        build_argv("mcp", {})
    with pytest.raises(CommandError):
        build_argv("watch", {})


def test_command_inputs_are_validated():
    from web.command_center import CommandError, build_argv
    with pytest.raises(CommandError):
        build_argv("approve", {"scan_id": "not-a-number"})
    with pytest.raises(CommandError):
        build_argv("scorecard", {"source": "; rm -rf /"})
    # shell metacharacters stay inert: they are one argv element, never a shell string
    argv = build_argv("scan", {"symbol": "BTC; rm -rf /"})
    assert "BTC; rm -rf /" in argv


def test_blocked_command_is_refused_by_the_api(client):
    resp = client.post("/api/commands/run", json={"id": "mcp"})
    assert resp.status_code == 400
    assert "terminal" in resp.get_json()["error"]


def test_unknown_command_is_refused_by_the_api(client):
    resp = client.post("/api/commands/run", json={"id": "definitely-not-a-command"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_a_read_only_command_actually_runs(client):
    resp = client.post("/api/commands/run", json={"id": "glossary"})
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["ok"] is True, d.get("output")
    assert d["exit_code"] == 0
    assert d["output"] and d["output"] != "(no output)"


# ── position sizer ────────────────────────────────────────────────────
def test_position_size_respects_the_progression_cap(client):
    resp = client.post("/api/position-size", json={
        "balance": 10000, "risk_pct": 5.0, "entry": 63000,
        "stop_loss": 62700, "take_profit": 63900})
    assert resp.status_code == 200
    d = resp.get_json()
    assert d["ok"] is True
    assert d["risk_pct_applied"] <= d["ladder_cap_pct"] < 5.0
    assert d["risk_amount"] == pytest.approx(10000 * d["risk_pct_applied"] / 100)
    assert d["units"] == pytest.approx(d["risk_amount"] / 300)
    assert d["risk_reward"] == pytest.approx(3.0)
    assert d["losses_to_daily_limit"] >= 1
    assert any("risk reduced" in w for w in d["warnings"])


def test_position_size_requires_entry_and_stop(client):
    d = client.post("/api/position-size", json={"balance": 1000}).get_json()
    assert d["ok"] is False and "stop-loss" in d["error"].lower()
    d = client.post("/api/position-size", json={
        "balance": 1000, "entry": 100, "stop_loss": 100}).get_json()
    assert d["ok"] is False


def test_position_size_is_zero_when_the_gate_is_closed():
    from web.position_sizer import calculate
    d = calculate(balance=10000, risk_pct=0.25, entry=100, stop=99,
                  gate={"allowed": False, "blocked_by": ["trader state: tired"]})
    assert d["recommended_units"] == 0.0
    assert "CLOSED" in d["verdict"] and "tired" in d["verdict"]


# ── journal form ──────────────────────────────────────────────────────
def test_journal_round_trip(client):
    # create a scan to journal against
    assert client.get("/api/scan?symbol=BTCUSDT&tf=15m&force=1").status_code == 200
    listing = client.get("/api/journal").get_json()
    assert listing["ok"] and listing["emotions"]
    assert listing["journalable"], "no scans offered for journalling"
    scan_id = listing["journalable"][0]["id"]

    saved = client.post("/api/journal", json={
        "scan_id": scan_id, "followed_rules": "1", "emotion": "calm",
        "mistake": "none", "notes": "test entry",
        "would_change": "size smaller"}).get_json()
    assert saved["ok"] is True
    assert saved["entry"]["emotion"] == "calm"
    assert saved["entry"]["followed_rules"] == 1

    read = client.get(f"/api/journal?scan_id={scan_id}").get_json()
    assert read["entry"]["notes"] == "test entry"
    assert read["quality"]["recorded"] is True
    # the pre-trade checklist must be populated from the stored scan,
    # not left blank by the flat-row / nested-payload mismatch
    assert read["checklist"]["asset"] == "BTCUSDT"
    assert read["checklist"]["action"] in ("BUY", "SELL", "NO TRADE")


def test_journal_requires_a_scan_id(client):
    resp = client.post("/api/journal", json={"emotion": "calm"})
    assert resp.status_code == 400


# ── trade manager ─────────────────────────────────────────────────────
def test_trade_manager_reports_live_r(client):
    from data.database import SignalDB
    assert client.get("/api/scan?symbol=BTCUSDT&tf=15m&force=1").status_code == 200
    now = int(time.time() * 1000)
    with SignalDB() as db:
        scan = db.latest_scans(limit=1)[0]
        trade, _ = db.create_paper_trade({
            "scan_id": scan["id"], "signal_id": scan["signal_id"], "plan_id": "p1",
            "plan_type": "Sweep Reversal Sell", "symbol": "BTCUSDT",
            "timeframe": "15m", "action": "BUY", "entry": 60000.0,
            "stop_loss": 59000.0, "take_profit": 62000.0, "risk_reward": 2.0,
            "confidence_pct": 70, "status": "WAITING_ENTRY",
            "created_ts": now - 3_600_000})
        db.open_paper_trade(trade["id"], 60000.0, now - 1_800_000, mae=-0.4, mfe=0.9)

    d = client.get("/api/trades").get_json()
    assert d["ok"] is True and d["count"] == 1
    row = d["open"][0]
    assert row["current_price"] is not None
    assert row["current_r"] is not None
    assert row["minutes_in_trade"] >= 29
    assert row["management"], "no management instruction for an open trade"
    assert row["mae"] == -0.4 and row["mfe"] == 0.9


# ── module catalog + page shell ───────────────────────────────────────
def test_module_catalog_lists_the_engine(client):
    d = client.get("/api/modules").get_json()
    assert d["count"] > 50
    names = {m["name"] for p in d["packages"] for m in p["modules"]}
    assert "engine/signal_engine.py" in names
    assert "brain/risk_gate.py" in names
    for pkg in d["packages"]:
        for mod in pkg["modules"]:
            # the summary must be an explanation, not the filename echoed back
            assert mod["summary"] != mod["name"]


def test_dashboard_exposes_every_workstation_tab(client):
    html = client.get("/").get_data(as_text=True)
    for tab in ("chart", "market", "intelligence", "trades", "manage",
                "risk", "journal", "learn", "commands", "modules", "system"):
        assert f'data-tab="{tab}"' in html, f"tab {tab} missing from the shell"
    # the clickable panels the trader asked for
    for anchor in ("chartMain", "tradeManager", "riskCenterGate", "psResult",
                   "jScan", "commandList", "moduleList",
                   "drawTrendline", "drawRay", "drawBox", "drawList", "drawStatus",
                   "liveBtn", "liveState"):
        assert f'id="{anchor}"' in html, f"panel {anchor} missing"


def test_lightweight_charts_is_the_real_vendored_build():
    """The stub silently drew nothing; the real build must be vendored."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "web" / "static"
          / "lightweight-charts.standalone.js")
    text = js.read_text()
    assert len(text) > 100_000, "the vendored chart build looks like the old stub"
    assert "Minimal working stub" not in text
    assert "LightweightCharts" in text
