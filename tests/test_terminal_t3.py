"""T3 — Trade Terminal paper-trade workflow wiring (backend).

The terminal Confirm button must run the *existing desk path*, not a new
order path: the ticket becomes a real scan row (PENDING_REVIEW), the risk &
discipline gate is freshly evaluated on the server immediately before the
APPROVED decision, the journal-first discipline applies exactly as in
``/api/review``, and the paper runner enrolls + fills the position. The
terminal Close records the real economic outcome into the same
``TP_HIT`` / ``STOP_LOSS`` buckets every discipline surface already counts,
so a manually closed trade still lands in win-rate, the journal gate and
graduation evidence. Still paper-only — no exchange order exists anywhere.
"""
from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t3.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t3.db"))
    # Simulator progression level: paper-trading levels may approve unproven
    # setups, so the happy path exercises the full desk flow.
    monkeypatch.setattr("brain.risk_gate.PROGRESSION", "simulator")
    from web.app import make_app
    app = make_app()
    app.testing = True
    return app.test_client()


def _market_ticket(symbol="BTCUSDT", **kw):
    ticket = {
        "ticket_id": kw.pop("ticket_id", "t3-market"),
        "symbol": symbol, "timeframe": "15m", "action": "BUY",
        "ticket_type": "market", "entry": 60000.0, "stop_loss": 59000.0,
        "take_profits": [62000.0, 63000.0], "risk_pct": 0.5,
        "plan_type": "Manual", "confidence": 70, "reason": "test ticket",
    }
    ticket.update(kw)
    return ticket


def _seed_decided_unjournaled_trade(tmp_path, monkeypatch) -> tuple[int, int]:
    """A closed, decided paper trade with no journal row (W3.3 trigger)."""
    from data.database import SignalDB
    now = int(time.time() * 1000)
    with SignalDB() as db:
        scan_id = db.save_scan({
            "signal": {"signal_id": f"seed_{now}", "timestamp": now,
                       "asset": "BTCUSDT", "timeframe": "15m", "action": "BUY",
                       "entry": 60000.0, "stop_loss": 59000.0,
                       "take_profit": 62000.0, "risk_reward": 2.0,
                       "confidence": "MEDIUM", "reason": "seed",
                       "signal_type": "SIGNAL"},
            "plans": [{"id": "p", "type": "Manual", "action": "BUY",
                       "entry": 60000.0, "stop_loss": 59000.0,
                       "take_profits": [62000.0], "status": "active"}],
            "snapshot": {"features": {"price": 60000.0}},
            "market_context": {},
        })
        db.update_status(scan_id, "APPROVED", reviewer="test")
        db.update_status(scan_id, "EXECUTED", reviewer="test")
        db.update_status(scan_id, "CLOSED", reviewer="test")
        trade, created = db.create_paper_trade({
            "scan_id": scan_id, "signal_id": f"seed_{now}", "plan_id": "p",
            "plan_type": "Manual", "symbol": "BTCUSDT", "timeframe": "15m",
            "action": "BUY", "entry": 60000.0, "stop_loss": 59000.0,
            "take_profit": 62000.0, "risk_reward": 2.0, "confidence_pct": 70,
            "status": "OPEN", "created_ts": now - 3_600_000,
            "entry_price": 60000.0, "opened_ts": now - 3_600_000})
        assert created
        ok = db.close_paper_trade(trade["id"], outcome="TP_HIT",
                                  exit_price=62000.0, rr_achieved=2.0,
                                  close_reason="seed", closed_ts=now)
        assert ok
        return scan_id, trade["id"]


# ── Confirm: the ticket runs the existing desk path ────────────────────

def test_confirm_market_ticket_runs_the_desk_path(client):
    res = client.post("/api/terminal/confirm", json=_market_ticket())
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["ok"] is True and d["gate"]["allowed"] is True
    scan_id = d["scan_id"]

    detail = client.get(f"/api/signal?id={scan_id}").get_json()
    # The scan row persisted exactly what the human confirmed.
    assert detail["scan"]["symbol"] == "BTCUSDT"
    assert detail["scan"]["action"] == "BUY"
    assert detail["scan"]["entry"] == 60000.0
    assert detail["scan"]["stop_loss"] == 59000.0
    assert detail["scan"]["status"] in ("APPROVED", "EXECUTED", "CLOSED")
    trail = [(x["from_state"], x["to_state"], x["reviewer"])
             for x in detail["decisions"]]
    assert ("PENDING_REVIEW", "APPROVED", "terminal") in trail
    # The paper runner enrolled a durable paper record for the same scan.
    paper = detail["paper_trade"]
    assert paper is not None
    assert paper["entry"] == 60000.0 and paper["take_profit"] == 62000.0
    assert paper["plan_type"] == "Manual"
    # The runner may have already filled/closed it against demo candles —
    # either way the lifecycle was advanced honestly by the runner.
    if d["status"] in ("EXECUTED", "CLOSED"):
        assert ("APPROVED", "EXECUTED", "paper_runner") in trail


def test_confirm_conditional_ticket_waits_for_entry(client):
    # Entry far below the demo price: the level never trades, so the position
    # stays WAITING_ENTRY — deterministic.
    res = client.post("/api/terminal/confirm", json=_market_ticket(
        ticket_id="t3-cond", ticket_type="conditional",
        entry=1000.0, stop_loss=900.0, take_profits=[1500.0]))
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["ok"] is True
    assert d["paper_trade"]["status"] == "WAITING_ENTRY"
    assert d["status"] == "APPROVED"

    trades = client.get("/api/trades").get_json()
    assert trades["count"] == 1
    row = trades["open"][0]
    assert row["status"] == "WAITING_ENTRY"
    assert row["management"], "no management advice for a waiting position"
    assert row["current_price"] is not None and row["current_r"] is not None

    # Closing a position that never filled cancels it; nothing to journal.
    res = client.post("/api/terminal/close",
                      json={"trade_id": row["id"]})
    assert res.status_code == 200, res.get_json()
    c = res.get_json()
    assert c["status"] == "CANCELLED" and c["journal_required"] is False
    detail = client.get(f"/api/signal?id={d['scan_id']}").get_json()
    assert detail["scan"]["status"] == "SKIPPED"


def test_confirm_retry_with_same_ticket_id_is_idempotent(client):
    ticket = _market_ticket(ticket_id="t3-idem", ticket_type="conditional",
                            entry=1000.0, stop_loss=900.0,
                            take_profits=[1500.0])
    first = client.post("/api/terminal/confirm", json=ticket)
    assert first.status_code == 200
    second = client.post("/api/terminal/confirm", json=ticket)
    assert second.status_code == 200, second.get_json()
    assert second.get_json()["duplicate"] is True
    assert second.get_json()["scan_id"] == first.get_json()["scan_id"]
    from data.database import SignalDB
    with SignalDB() as db:
        n = db.conn.execute("SELECT COUNT(*) n FROM paper_trades").fetchone()["n"]
    assert n == 1, "a retried confirm must not enroll a second position"


def test_confirm_validation_fails_closed(client):
    bad = [
        _market_ticket(action="HOLD"),
        _market_ticket(action="BUY", stop_loss=61000.0),   # inverted stop
        _market_ticket(action="SELL", entry=60000.0, stop_loss=59000.0),
        _market_ticket(entry=-5.0),
        _market_ticket(stop_loss=0),
        _market_ticket(risk_pct=0),
        _market_ticket(risk_pct=101),
        _market_ticket(take_profits=[62000.0, 61000.0]),   # decreasing
        _market_ticket(take_profits=["nope"]),
        _market_ticket(ticket_type="futures"),
    ]
    for ticket in bad:
        res = client.post("/api/terminal/confirm", json=ticket)
        assert res.status_code == 400, (ticket, res.get_json())
    from data.database import SignalDB
    with SignalDB() as db:
        n = db.conn.execute("SELECT COUNT(*) n FROM scans").fetchone()["n"]
    assert n == 0, "invalid tickets must not persist anything"


# ── The fresh server-side gate ─────────────────────────────────────────

def test_confirm_blocked_by_unproven_setup_at_student_level(client, monkeypatch):
    monkeypatch.setattr("brain.risk_gate.PROGRESSION", "student")
    res = client.post("/api/terminal/confirm", json=_market_ticket())
    assert res.status_code == 409, res.get_json()
    d = res.get_json()
    assert any("setup unproven" in b for b in d["blocked_by"])
    # The blocked ticket is still a review candidate in the human queue.
    pending = client.get("/api/pending").get_json()["pending"]
    assert any(p["entry"] == 60000.0 for p in pending)


def test_confirm_force_requires_the_opt_in_and_is_audited(client, monkeypatch):
    monkeypatch.setattr("brain.risk_gate.PROGRESSION", "student")
    import config
    monkeypatch.setattr(config, "SKY_ALLOW_FORCE_APPROVE", False)
    res = client.post("/api/terminal/confirm",
                      json=_market_ticket(ticket_id="t3-f1", force=True))
    assert res.status_code == 403, res.get_json()

    monkeypatch.setattr(config, "SKY_ALLOW_FORCE_APPROVE", True)
    res = client.post("/api/terminal/confirm",
                      json=_market_ticket(ticket_id="t3-f2", force=True))
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    # Same semantics as the desk force-approve: the scan is APPROVED but the
    # runner's own gate still refuses to enroll while the gate is shut.
    assert d["status"] == "APPROVED" and d["paper_trade"] is None
    assert any(e.get("event") == "GATE_BLOCKED" for e in d["run"]["events"])


def test_confirm_blocked_by_trader_state(client):
    from data.database import SignalDB
    with SignalDB() as db:
        db.set_trader_state(angry=True)
    res = client.post("/api/terminal/confirm",
                      json=_market_ticket(ticket_id="t3-angry"))
    assert res.status_code == 409, res.get_json()
    assert any("trader state" in b for b in res.get_json()["blocked_by"])
    with SignalDB() as db:
        db.set_trader_state(angry=False)


# ── Journal-first discipline (W3.3) ────────────────────────────────────

def test_confirm_journal_first_discipline(client, tmp_path, monkeypatch):
    _seed_decided_unjournaled_trade(tmp_path, monkeypatch)
    res = client.post("/api/terminal/confirm",
                      json=_market_ticket(ticket_id="t3-jg"))
    assert res.status_code == 409, res.get_json()
    d = res.get_json()
    assert d["journal_block"]["missing"] >= 1
    assert d["acknowledge_available"] is True

    res = client.post("/api/terminal/confirm",
                      json=_market_ticket(ticket_id="t3-jg2",
                                          acknowledge_journal=True))
    assert res.status_code == 200, res.get_json()


# ── Terminal close: outcome recorded, journal opens ────────────────────

def _seed_open_position(tmp_path, monkeypatch, entry=60000.0, stop=59000.0,
                        tp=62000.0, action="BUY") -> tuple[int, int]:
    from data.database import SignalDB
    now = int(time.time() * 1000)
    with SignalDB() as db:
        scan_id = db.save_scan({
            "signal": {"signal_id": f"open_{now}_{action}", "timestamp": now,
                       "asset": "BTCUSDT", "timeframe": "15m",
                       "action": action, "entry": entry, "stop_loss": stop,
                       "take_profit": tp, "risk_reward": 2.0,
                       "confidence": "MEDIUM", "reason": "open seed",
                       "signal_type": "SIGNAL"},
            "plans": [{"id": "p", "type": "Manual", "action": action,
                       "entry": entry, "stop_loss": stop,
                       "take_profits": [tp], "status": "active"}],
            "snapshot": {"features": {"price": entry}},
            "market_context": {},
        })
        db.update_status(scan_id, "APPROVED", reviewer="test")
        db.update_status(scan_id, "EXECUTED", reviewer="test")
        trade, created = db.create_paper_trade({
            "scan_id": scan_id, "signal_id": f"open_{now}_{action}",
            "plan_id": "p", "plan_type": "Manual", "symbol": "BTCUSDT",
            "timeframe": "15m", "action": action, "entry": entry,
            "stop_loss": stop, "take_profit": tp, "risk_reward": 2.0,
            "confidence_pct": 70, "status": "OPEN",
            "created_ts": now - 3_600_000, "entry_price": entry,
            "opened_ts": now - 3_600_000})
        assert created
        return scan_id, trade["id"]


def test_manual_close_records_profit_and_requires_journal(client, tmp_path,
                                                          monkeypatch):
    scan_id, trade_id = _seed_open_position(tmp_path, monkeypatch)
    res = client.post("/api/terminal/close",
                      json={"trade_id": trade_id, "exit_price": 61200.0})
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["status"] == "CLOSED"
    assert d["outcome"] == "TP_HIT"          # profit before target
    assert d["rr_achieved"] == 1.2
    assert d["journal_required"] is True

    from data.database import SignalDB
    with SignalDB() as db:
        trade = db.get_paper_trade(trade_id)
        scan = db.get_scan(scan_id)
    assert trade["status"] == "CLOSED"
    assert "manual terminal close" in trade["close_reason"]
    assert scan["status"] == "CLOSED"
    # The journal drawer's save path works on the closed scan.
    res = client.post("/api/journal", json={"scan_id": scan_id,
                                            "followed_rules": True,
                                            "emotion": "calm"})
    assert res.status_code == 200 and res.get_json()["ok"] is True


def test_manual_close_records_loss_in_the_stop_bucket(client, tmp_path,
                                                       monkeypatch):
    scan_id, trade_id = _seed_open_position(tmp_path, monkeypatch)
    res = client.post("/api/terminal/close",
                      json={"trade_id": trade_id, "exit_price": 58500.0})
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["outcome"] == "STOP_LOSS" and d["rr_achieved"] == -1.5
    # A manually closed loss still counts in the decided populations.
    from data.database import SignalDB
    with SignalDB() as db:
        rows = db.discipline_rows(source_key="")
    assert any(r["scan_id"] == scan_id for r in rows)


def test_manual_close_sell_side_math(client, tmp_path, monkeypatch):
    # SELL: profit when price falls. Exit 58500 → (60000-58500)/1000 = +1.5R.
    scan_id, trade_id = _seed_open_position(tmp_path, monkeypatch,
                                            action="SELL", entry=60000.0,
                                            stop=61000.0, tp=58000.0)
    res = client.post("/api/terminal/close",
                      json={"trade_id": trade_id, "exit_price": 58500.0})
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["outcome"] == "TP_HIT" and d["rr_achieved"] == 1.5


def test_manual_close_uses_last_price_when_none_passed(client, tmp_path,
                                                       monkeypatch):
    scan_id, trade_id = _seed_open_position(tmp_path, monkeypatch)
    from data.database import SignalDB
    now = int(time.time() * 1000)
    with SignalDB() as db:
        db.touch_paper_trade(trade_id, last_price=60100.0)
    res = client.post("/api/terminal/close", json={"trade_id": trade_id})
    assert res.status_code == 200, res.get_json()
    d = res.get_json()
    assert d["rr_achieved"] == 0.1


def test_close_unknown_or_already_closed_trade(client):
    res = client.post("/api/terminal/close", json={"trade_id": 999})
    assert res.status_code == 404
    res = client.post("/api/terminal/close", json={})
    assert res.status_code == 400

    # A closed trade refuses a second close and reports its real state.
    res = client.post("/api/terminal/confirm", json=_market_ticket(
        ticket_id="t3-reclose", ticket_type="conditional",
        entry=1000.0, stop_loss=900.0, take_profits=[1500.0]))
    trade_id = res.get_json()["paper_trade"]["id"]
    client.post("/api/terminal/close", json={"trade_id": trade_id})
    res = client.post("/api/terminal/close", json={"trade_id": trade_id})
    assert res.status_code == 409
    assert res.get_json()["status"] == "CANCELLED"


def test_confirm_response_is_json_serializable(client):
    res = client.post("/api/terminal/confirm", json=_market_ticket(
        ticket_id="t3-serial"))
    assert res.status_code == 200
    body = res.get_json()
    json.dumps(body)  # must not raise
    assert isinstance(body["paper_trade"]["rr_achieved"], (float, type(None)))
