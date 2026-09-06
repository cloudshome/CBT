"""Real-world connection + unlock-path tests.

Two features are guarded here:

**Connections** — the registry that tells the trader what SKY is actually
plugged into. The critical property is that the READ-ONLY exchange client can
only ever read: its endpoint allow-list must reject anything else, and a key
carrying trade/withdraw permission must be reported as unsafe.

**Unlock** — the gate blocking a trade is correct, but it must explain itself
and be *earnable*. These tests prove the evidence bars move as samples
accumulate and that the gate actually opens once a setup is proven.
"""

from __future__ import annotations

import time

import pytest


# ── READ-ONLY exchange account safety ────────────────────────────────────
def test_order_endpoints_are_refused():
    """The signer must reject anything outside the read-only allow-list."""
    from data.exchange_account import ExchangeAccount, ExchangeAccountError

    acct = ExchangeAccount(api_key="k", api_secret="s")
    for path in (
        "/api/v3/order",
        "/api/v3/order/test",
        "/sapi/v1/capital/withdraw/apply",
        "/fapi/v1/order",
        "/api/v3/openOrders/cancelAll",
    ):
        with pytest.raises(ExchangeAccountError, match="allow-list"):
            acct._signed_get(path, {"symbol": "BTCUSDT"})


def test_module_has_no_write_http_verb():
    """There must be no POST/PUT/DELETE call anywhere in the account client."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent / "data" / "exchange_account.py"
    ).read_text()
    for verb in (
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.patch",
        "session.post",
    ):
        assert verb not in src, f"{verb} must not exist in the read-only client"


def test_allow_list_is_read_only():
    from data.exchange_account import READ_ONLY_PATHS

    for path in READ_ONLY_PATHS:
        assert "order" not in path or "openOrders" in path
        assert "withdraw" not in path.lower()


def test_a_trading_key_is_flagged_as_unsafe():
    from data.exchange_account import ExchangeAccountError, assert_read_only_key

    with pytest.raises(ExchangeAccountError, match="Enable Reading"):
        assert_read_only_key(
            {"canTrade": True, "canWithdraw": False, "permissions": ["SPOT_TRADING"]}
        )
    with pytest.raises(ExchangeAccountError):
        assert_read_only_key({"permissions": ["WITHDRAWALS"]})
    # a genuinely read-only key passes
    assert_read_only_key(
        {"canTrade": False, "canWithdraw": False, "permissions": ["SPOT_READ"]}
    ) is None


def test_unconfigured_account_degrades_quietly():
    from data.exchange_account import ExchangeAccount

    snap = ExchangeAccount(api_key="", api_secret="").snapshot()
    assert snap["configured"] is False
    assert snap["connected"] is False
    assert snap["balances"] == []
    assert "no read-only API key" in snap["note"]


def test_demo_account_snapshot(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from data.exchange_account import ExchangeAccount

    snap = ExchangeAccount(api_key="demo", api_secret="demo").snapshot()
    assert snap["connected"] is True
    assert snap["read_only"] is True
    assert snap["can_trade"] is False
    assert snap["balance_count"] == 3


# ── connection registry ──────────────────────────────────────────────────
def test_every_connection_is_documented():
    from brain.connections import CONNECTIONS, TIER_LABELS

    ids = set()
    for c in CONNECTIONS:
        assert c["gives"], f"{c['id']} does not say what it gives the trader"
        assert c["needs"], f"{c['id']} does not say what it needs"
        assert c["how"], f"{c['id']} has no setup steps"
        assert c["tier"] in TIER_LABELS
        assert callable(c["probe"])
        ids.add(c["id"])
    # the links the user asked for
    for expected in (
        "market_data",
        "derivatives",
        "news",
        "telegram",
        "discord",
        "llm",
        "account",
    ):
        assert expected in ids


def test_probe_all_reports_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from brain.connections import probe_all

    d = probe_all(ids=["market_data", "derivatives"])
    assert d["demo_mode"] is True
    assert "DEMO" in d["headline"].upper()
    assert d["level"] == "degraded", "demo data must never be reported as live"
    assert len(d["connections"]) == 2


def test_probe_survives_a_crashing_probe(monkeypatch):
    """A broken probe degrades one card, never the page."""
    import brain.connections as conns

    def boom():
        raise RuntimeError("network on fire")

    entry = next(c for c in conns.CONNECTIONS if c["id"] == "news")
    monkeypatch.setitem(entry, "probe", boom)
    result = conns.probe_one("news")
    assert result["live"] is False
    assert "probe crashed" in result["detail"]


def test_unknown_connection_raises():
    from brain.connections import probe_one

    with pytest.raises(ValueError):
        probe_one("not-a-connection")


def test_alert_test_reports_missing_config(monkeypatch):
    import output.notifiers as n

    monkeypatch.setattr(n, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(n, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(n, "DISCORD_ANNOUNCE_WEBHOOK", "")
    assert n.send_test_alert("telegram")["ok"] is False
    assert "TELEGRAM_BOT_TOKEN" in n.send_test_alert("telegram")["error"]
    assert n.send_test_alert("discord")["ok"] is False
    assert n.send_test_alert("carrier-pigeon")["ok"] is False


# ── the unlock path ──────────────────────────────────────────────────────
@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "unlock.db"))
    from data.database import SignalDB

    with SignalDB() as conn:
        yield conn


def _add_backtest(db, plan_type: str, n: int, winning: bool = True):
    rows = [
        {
            "run_id": "t",
            "ts": 1_780_000_000_000 + i * 900_000,
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "plan_type": plan_type,
            "action": "BUY",
            "confidence_pct": 70,
            "horizon_hours": 4,
            "step": 3,
            "outcome": "FULL_WIN" if (i % 3 and winning) else "LOSS",
            "rr_achieved": 2.0 if (i % 3 and winning) else -1.0,
            "rr_net": 1.9 if (i % 3 and winning) else -1.05,
            "entry": 60000.0,
            "regime": "TRENDING",
        }
        for i in range(n)
    ]
    db.save_backtest_rows(rows, "t")


def _add_paper(db, plan_type: str, n: int, winning: bool = True):
    now = int(time.time() * 1000)
    for i in range(n):
        db.conn.execute(
            """INSERT INTO paper_trades (scan_id, plan_type, symbol, timeframe,
                 action, entry, stop_loss, take_profit, status, outcome,
                 rr_achieved, rr_net, created_ts, closed_ts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                9000 + i,
                plan_type,
                "BTCUSDT",
                "15m",
                "BUY",
                60000,
                59500,
                61000,
                "CLOSED",
                "TP_HIT" if (i % 3 and winning) else "STOP_LOSS",
                2.0 if (i % 3 and winning) else -1.0,
                1.9 if (i % 3 and winning) else -1.05,
                now,
                now,
            ),
        )
    db.conn.commit()


def test_block_is_explained_in_plain_language(db):
    from brain.unlock import explain

    d = explain(db, plan_type="Buy Pullback")
    assert d["allowed"] is False
    assert d["has_earnable"] is True
    block = next(b for b in d["blocks"] if b["kind"] == "earn")
    assert "proven" in block["title"].lower()
    assert block["action"] == "backtest", "no clickable action offered"
    # the raw rule text is kept for transparency, but a plain explanation leads
    assert block["plain"] and block["plain"] != block["reason"]
    assert "100" in block["plain"] and "20" in block["plain"]


def test_evidence_bars_move_as_samples_accumulate(db):
    from brain.unlock import setup_progress

    start = setup_progress(db, "Buy Pullback")
    assert start["pct"] == 0.0 and start["proven"] is False
    assert start["next_action"]["action"] == "backtest"

    _add_backtest(db, "Buy Pullback", 110)
    half = setup_progress(db, "Buy Pullback")
    assert half["pct"] > start["pct"], "the bar did not move after a backtest"
    assert half["criteria"][0]["met"] is True
    assert half["proven"] is False, "backtest alone must not prove a setup"
    assert half["next_action"]["action"] == "simulator"

    _add_paper(db, "Buy Pullback", 22)
    done = setup_progress(db, "Buy Pullback")
    assert done["pct"] == 100.0
    assert done["proven"] is True
    assert done["next_action"] is None


def test_the_gate_actually_opens_once_earned(db):
    """The unlock path is real: proven evidence → the gate allows the trade."""
    from brain.risk_gate import evaluate
    from brain.unlock import explain

    assert evaluate(db, plan_type="Buy Pullback")["allowed"] is False

    _add_backtest(db, "Buy Pullback", 110)
    _add_paper(db, "Buy Pullback", 22)

    assert evaluate(db, plan_type="Buy Pullback")["allowed"] is True
    assert explain(db, plan_type="Buy Pullback")["allowed"] is True
    # a different, unproven setup is still correctly blocked
    assert evaluate(db, plan_type="Sweep Reversal Sell")["allowed"] is False


def test_losing_evidence_does_not_prove_a_setup(db):
    """Enough samples is not enough — it must also make money net of costs."""
    from brain.risk_gate import evaluate
    from brain.unlock import setup_progress

    _add_backtest(db, "Buy Pullback", 110, winning=False)
    _add_paper(db, "Buy Pullback", 22, winning=False)
    p = setup_progress(db, "Buy Pullback")
    assert p["criteria"][0]["met"] is True  # sample floors met
    assert p["criteria"][1]["met"] is True
    assert p["criteria"][2]["met"] is False  # expectancy is not
    assert p["proven"] is False
    assert evaluate(db, plan_type="Buy Pullback")["allowed"] is False


def test_evidence_overview_lists_setups(db):
    from brain.unlock import evidence_overview

    _add_backtest(db, "Buy Pullback", 110)
    d = evidence_overview(db)
    assert d["count"] >= 1
    assert any(s["plan_type"] == "Buy Pullback" for s in d["setups"])
    assert d["proven_count"] == 0
    assert "Backfill" in d["next_step"] or "backtest" in d["next_step"].lower()
    # best-progressed setup is listed first
    assert d["setups"][0]["pct"] >= d["setups"][-1]["pct"]


def test_wait_blocks_are_distinguished_from_earn_blocks(db):
    """A trader-state flag is a 'wait', not something you grind samples for."""
    from brain.unlock import explain

    db.set_trader_state(tired=True, note="test")
    d = explain(db, plan_type="Buy Pullback")
    kinds = {b["kind"] for b in d["blocks"]}
    assert "wait" in kinds
    tired = next(b for b in d["blocks"] if "state" in b["reason"].lower())
    assert tired["kind"] == "wait"
    assert tired["ui_hint"] == "risk"


# ── API surface ──────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "api.db"))
    from web.app import make_app

    app = make_app()
    app.testing = True
    return app.test_client()


def test_connections_endpoint(client):
    d = client.get("/api/connections").get_json()
    assert d["connections"], "no connections reported"
    assert d["level"] in ("ok", "degraded", "down")
    assert d["headline"]
    for c in d["connections"]:
        assert "gives" in c and "how" in c


def test_connection_test_endpoint(client):
    d = client.post("/api/connections/test", json={"id": "market_data"}).get_json()
    assert d["id"] == "market_data"
    assert "live" in d
    bad = client.post("/api/connections/test", json={"id": "nope"})
    assert bad.status_code == 400


def test_account_endpoint_is_safe_when_unconfigured(client):
    d = client.get("/api/account").get_json()
    assert d["configured"] is False
    assert d["balances"] == []


def test_unlock_endpoint(client):
    d = client.get("/api/unlock?plan_type=Buy%20Pullback").get_json()
    assert "headline" in d and "blocks" in d
    assert isinstance(d["blocks"], list)


def test_evidence_endpoint(client):
    d = client.get("/api/evidence").get_json()
    assert "setups" in d and "headline" in d


def test_dashboard_exposes_the_new_tabs(client):
    html = client.get("/").get_data(as_text=True)
    for tab in ("connections", "evidence"):
        assert f'data-tab="{tab}"' in html
    for anchor in ("connectionList", "accountPanel", "unlockWhy", "evidenceBoard"):
        assert f'id="{anchor}"' in html
