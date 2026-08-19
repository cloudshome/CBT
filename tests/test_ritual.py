"""Tests for W3.2/W3.3 — the daily ritual with memory and the journal-first
approval gate.

The ritual is memory, not permission: ticks persist per UTC day and a new day
starts empty. The journal-first gate is a trainer-side delay on *commitments*
only — it never opens anything, never bypasses the risk gate, and rejects,
closes and skips are unaffected.
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from data.database import SignalDB
from brain.ritual import ritual_today, ritual_set, RITUAL_STEPS


DAY = 86_400_000


@pytest.fixture
def db(tmp_path):
    _db = SignalDB(tmp_path / "r.db")
    yield _db
    _db.close()


def _seed_scan(db: SignalDB, sig_id: str = "SIG-P1") -> int:
    return db.save_scan({
        "signal": {"signal_id": sig_id, "signal_type": "SIGNAL",
                   "asset": "BTCUSDT", "timeframe": "15m",
                   "action": "BUY", "entry": 100.0, "stop_loss": 99.0,
                   "take_profit": 101.0, "risk_reward": 1.0, "confidence": 70},
        "plans": [{"type": "Buy Pullback", "entry": 100.0, "stop": 99.0,
                   "tps": [101.0]}],
        "snapshot": {"features": {}},
    })


def _seed_unjournaled_decided(db: SignalDB, sid: int = 900) -> None:
    now = int(time.time() * 1000)
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
             action, entry, stop_loss, take_profit, risk_reward, confidence_pct,
             status, created_ts, opened_ts, closed_ts, entry_price, exit_price,
             outcome, rr_achieved, rr_net, close_reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, f"SIG{sid}", "Buy Pullback", "BTCUSDT", "15m", "BUY", 100.0, 99.0,
         101.5, 1.5, 70, "CLOSED", now, now, now, 100.0, 101.5, "TP_HIT",
         1.5, 1.5, "test"))
    db.conn.commit()


# ── ritual persistence ───────────────────────────────────────────────────

def test_ritual_steps_canonical_vocabulary():
    assert RITUAL_STEPS == ("readiness", "loop", "gate", "act")


def test_fresh_day_starts_empty(db):
    payload = ritual_today(db)
    assert payload["done"] == 0
    assert payload["total"] == 4
    assert payload["complete"] is False
    assert {s["name"] for s in payload["steps"]} == set(RITUAL_STEPS)
    assert all(s["done"] is False for s in payload["steps"])
    # the payload says what ticks are NOT: not permission, not a threshold
    assert "not permission" in payload["note"]


def test_tick_persists_and_unticks(db):
    ritual_set(db, "readiness", True)
    ritual_set(db, "loop", True)
    today = ritual_today(db)
    assert today["done"] == 2
    assert today["complete"] is False
    by_name = {s["name"]: s for s in today["steps"]}
    assert by_name["readiness"]["done"] is True
    assert by_name["readiness"]["done_ts"]
    # unticking removes the mark
    ritual_set(db, "loop", False)
    assert ritual_today(db)["done"] == 1
    # completing all four flags the day complete
    for step in RITUAL_STEPS:
        ritual_set(db, step, True)
    assert ritual_today(db)["complete"] is True


def test_new_day_starts_fresh(db):
    yesterday = time.time() - 86400
    for step in RITUAL_STEPS:
        ritual_set(db, step, True, now=yesterday)
    assert ritual_today(db, now=yesterday)["complete"] is True
    today = ritual_today(db)  # real today
    assert today["done"] == 0, "yesterday's discipline must not pretend to be today's"
    assert today["complete"] is False


def test_unknown_step_fails_closed(db):
    with pytest.raises(ValueError, match="unknown ritual step"):
        ritual_set(db, "trade_anyway", True)
    # a rejected name writes nothing
    assert db.ritual_state(ritual_today(db)["day"]) == {}


def test_ritual_state_raw_db_roundtrip(db):
    day = time.strftime("%Y-%m-%d", time.gmtime())
    db.ritual_mark(day, "gate", True)
    db.ritual_mark(day, "gate", True)      # idempotent
    db.ritual_mark(day, "gate", False)
    assert db.ritual_state(day) == {}      # undone rows do not count


# ── web endpoints ────────────────────────────────────────────────────────

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


def test_ritual_api_roundtrip(client):
    r = client.get("/api/ritual")
    assert r.status_code == 200
    body = r.get_json()
    assert body["done"] == 0 and body["total"] == 4
    r = client.post("/api/ritual", json={"step": "readiness", "done": True})
    assert r.status_code == 200
    assert r.get_json()["done"] == 1
    # persists across requests
    assert client.get("/api/ritual").get_json()["done"] == 1
    # unknown step → 400, and nothing was written
    r = client.post("/api/ritual", json={"step": "trade_anyway", "done": True})
    assert r.status_code == 400
    assert client.get("/api/ritual").get_json()["done"] == 1


def test_weekly_api_and_export(client):
    r = client.get("/api/weekly")
    assert r.status_code == 200
    body = r.get_json()
    for key in ("window", "week", "all_time", "r_distribution", "violations",
                "graduation_tracker", "next_practice_task", "grade",
                "journal_gate", "equity_curve", "bar"):
        assert key in body, key
    assert body["bar"]["expectancy"] == pytest.approx(0.50)
    r = client.get("/api/weekly/export")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert "sky-weekly-review" in r.headers["Content-Disposition"]
    json.loads(r.get_data(as_text=True))  # real JSON


# ── W3.3 journal-first approval gate (web) ───────────────────────────────

def _allow_gate(monkeypatch):
    """Make the risk gate allow so the journal gate is the only hold."""
    import brain.risk_gate as gate
    monkeypatch.setattr(
        gate, "evaluate",
        lambda db, **kw: {"allowed": True, "blocked_by": [], "profile": "test",
                          "risk_pct": 0.25, "trader_flags": []})


def test_approve_held_while_unjournaled(client, monkeypatch):
    _allow_gate(monkeypatch)
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=901)
    scan_id = _seed_scan(db)
    db.close()
    r = client.post("/api/review",
                    json={"scan_id": scan_id, "decision": "APPROVED"})
    assert r.status_code == 409
    body = r.get_json()
    assert "journal" in body["error"].lower()
    assert body["journal_block"]["missing"] == 1
    assert body["acknowledge_available"] is True
    # the scan is still pending — the hold delayed, never decided
    db = SignalDB()
    assert db.get_scan(scan_id)["status"] == "PENDING_REVIEW"
    db.close()


def test_approve_acknowledge_is_audited_and_passes(client, monkeypatch):
    _allow_gate(monkeypatch)
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=902)
    scan_id = _seed_scan(db)
    db.close()
    r = client.post("/api/review",
                    json={"scan_id": scan_id, "decision": "APPROVED",
                          "acknowledge_journal": True})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True
    db = SignalDB()
    assert db.get_scan(scan_id)["status"] == "APPROVED"
    db.close()


def test_approve_unblocked_once_journaled(client, monkeypatch):
    _allow_gate(monkeypatch)
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=903)
    db.save_journal(903, followed_rules=True, emotion="calm", mistake="none")
    scan_id = _seed_scan(db)
    db.close()
    r = client.post("/api/review",
                    json={"scan_id": scan_id, "decision": "APPROVED"})
    assert r.status_code == 200, r.get_json()


def test_reject_never_held_by_journal_gate(client):
    """The hold applies to commitments (approve) — clearing the queue with a
    reject stays free, even with an unprocessed journal debt."""
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=904)
    scan_id = _seed_scan(db)
    db.close()
    r = client.post("/api/review",
                    json={"scan_id": scan_id, "decision": "REJECTED"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True


def test_simulator_and_research_debt_do_not_hold(client, monkeypatch):
    """Only canonical live decided trades create journal debt (P12.15). A
    simulator grind or a research-book trade must not hold real approvals."""
    _allow_gate(monkeypatch)
    db = SignalDB()
    now = int(time.time() * 1000)
    for sid, sim_key, src in ((905, "sim:905", None), (906, None, "dukascopy:spot:bid")):
        db.conn.execute(
            """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                 action, entry, stop_loss, take_profit, risk_reward, confidence_pct,
                 status, created_ts, opened_ts, closed_ts, entry_price, exit_price,
                 outcome, rr_achieved, rr_net, close_reason, sim_key, source_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, f"SIG{sid}", "Buy Pullback", "BTCUSDT", "15m", "BUY", 100.0, 99.0,
             101.5, 1.5, 70, "CLOSED", now, now, now, 100.0, 101.5, "TP_HIT",
             1.5, 1.5, "test", sim_key, src))
    db.conn.commit()
    scan_id = _seed_scan(db)
    db.close()
    r = client.post("/api/review",
                    json={"scan_id": scan_id, "decision": "APPROVED"})
    assert r.status_code == 200, r.get_json()


# ── W3.3 journal-first approval gate (CLI approve) ───────────────────────

def _cli_args(scan_id, **kw):
    base = dict(scan_id=scan_id, note="", force=False,
                acknowledge_journal=False, json=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_cli_approve_held_while_unjournaled(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "c.db"))
    _allow_gate(monkeypatch)
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=907)
    scan_id = _seed_scan(db)
    db.close()
    import main
    rc = main.cmd_approve(_cli_args(scan_id))
    assert rc == 2
    err = capsys.readouterr().err
    assert "journal-first" in err
    assert "#907" in err
    # scan still pending
    db = SignalDB()
    assert db.get_scan(scan_id)["status"] == "PENDING_REVIEW"
    db.close()


def test_cli_approve_acknowledge_journals(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "c.db"))
    _allow_gate(monkeypatch)
    db = SignalDB()
    _seed_unjournaled_decided(db, sid=908)
    scan_id = _seed_scan(db)
    db.close()
    import main
    rc = main.cmd_approve(_cli_args(scan_id, acknowledge_journal=True))
    assert rc == 0
    db = SignalDB()
    assert db.get_scan(scan_id)["status"] == "APPROVED"
    db.close()


# ── CLI weekly ───────────────────────────────────────────────────────────

def test_cli_weekly_json_and_export(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "c.db"))
    import main
    out = tmp_path / "review.json"
    rc = main.cmd_weekly(SimpleNamespace(json=True, days=7, export=str(out)))
    assert rc == 0
    printed = capsys.readouterr().out
    # the export notice prints above the JSON; parse from the first '{'
    payload = json.loads(printed[printed.index("{"):])
    assert payload["window"]["days"] == 7
    assert json.loads(out.read_text())["week"]["n"] == payload["week"]["n"]


def test_cli_weekly_text_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "c.db"))
    import main
    rc = main.cmd_weekly(SimpleNamespace(json=False, days=7, export=None))
    assert rc == 0
    out = capsys.readouterr().out
    assert "WEEKLY TRADER REVIEW" in out
    assert "NEXT PRACTICE TASK" in out
