"""Tests for the desk agent layer (brain/agent.py): health report, morning
briefing, natural-language ask.  All offline via DEMO_MODE=1 + temp DB."""

from __future__ import annotations

import pytest


@pytest.fixture
def desk_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "agent.db"))
    yield tmp_path


def test_health_report_ok(desk_env):
    from brain.agent import health_report

    report = health_report()
    assert report["ok"] is True
    assert report["data"]["mode"] == "demo"
    assert report["database"]["ok"] is True
    assert report["risk_gate"]["allowed"] is True
    assert report["pending_reviews"] == 0
    assert report["mcp"]["available"] is True
    assert report["llm"]["provider"] == "off"
    # every watchlist symbol has a data probe
    assert set(report["data"]["probe"]) == {"BTCUSDT", "ETHUSDT", "XAUUSD"}
    assert all(p["ok"] for p in report["data"]["probe"].values())
    assert all(p.get("last_ts") is not None for p in report["data"]["probe"].values())
    assert all(
        p.get("age_seconds") is not None for p in report["data"]["probe"].values()
    )


def test_health_report_format(desk_env):
    from brain.agent import format_health, health_report

    text = format_health(health_report())
    assert "VERDICT      : OK" in text
    assert "data mode" in text
    assert "BTCUSDT" in text


def test_data_probe_preserves_material_future_skew(monkeypatch):
    """Only tiny clock skew is clamped; preflight needs larger skew to fail."""
    import pandas as pd

    from brain import agent

    class Client:
        def klines(self, symbol, timeframe, limit):
            assert (symbol, timeframe, limit) == ("BTCUSDT", "15m", 60)
            return pd.DataFrame({"ts": [1120] * 10, "close": [100.0] * 10})

    monkeypatch.setattr(agent, "SYMBOLS", ["BTCUSDT"])
    monkeypatch.setattr(agent.time, "time", lambda: 1000)
    probe = agent._probe_data(Client())["BTCUSDT"]
    assert probe["age_seconds"] == -120.0


def test_morning_briefing_assets_and_gate(desk_env):
    from brain.agent import morning_briefing

    b = morning_briefing(bars=200)
    assert len(b["assets"]) == 3
    for a in b["assets"]:
        assert a["ok"] is True
        assert a["desk_action"] in ("BUY", "SELL", "NO TRADE")
        assert a["signal_id"]
        assert a["confidence_pct"] is None or a["confidence_pct"] > 0
    assert b["risk_gate"]["allowed"] is True
    assert b["pending_reviews"] == 0
    assert b["narrative"]  # rule-based narrative always present
    assert "Risk gate OPEN" in b["narrative"]


def test_morning_briefing_json_safe(desk_env):
    """The briefing must be JSON-serializable (dashboard + MCP render it)."""
    import json

    from brain.agent import morning_briefing

    json.dumps(morning_briefing(bars=200), default=str)


def test_ask_risk_intent(desk_env):
    from brain.agent import ask

    r = ask("is the risk gate open?")
    assert r["intent"] == "risk"
    assert r["data"]["allowed"] is True
    assert any("GATE: OPEN" in line for line in r["answer"])


def test_ask_pending_and_journal(desk_env):
    from brain.agent import ask

    assert ask("what's pending review?").get("intent") == "pending"
    assert ask("how is my journal discipline?").get("intent") == "journal"
    assert ask("show me the paper book").get("intent") == "paper"
    assert ask("any exposure right now?").get("intent") == "exposure"


def test_ask_market_scan(desk_env):
    from brain.agent import ask

    r = ask("scan BTC", symbol="BTCUSDT", bars=200)
    assert r["intent"] == "market"
    assert r["data"]["signal"]["asset"] == "BTCUSDT"
    assert r["data"]["decision"]["action"] in ("BUY", "SELL", "NO TRADE")


def test_ask_help_fallback(desk_env):
    from brain.agent import ask

    r = ask("what can you do?")
    assert r["intent"] == "help"
    assert "calibration" in r["data"]["intents"]


def test_ask_graduation_intent(desk_env):
    """'am i ready for micro?' hits the graduation gate (BLUEPRINT Step 2→3)."""
    from brain.agent import ask

    r = ask("am i ready for micro?")
    assert r["intent"] == "graduation"
    assert "GRADUATION GATE" in "\n".join(r["answer"])
    g = r["data"]["graduation"]
    assert set(g["criteria"]) == {"expectancy", "win_rate", "pf", "compliance"}
    assert set(g["met"]) == {"expectancy", "win_rate", "pf", "compliance"}
    assert "ready" in g and "samples_proven" in g


def test_graduation_report_shape(desk_env):
    from brain.agent import graduation_report

    rep = graduation_report()
    assert set(rep) == {"progress", "graduation", "journal", "discipline"}
    assert "ready" in rep["graduation"] and "stats" in rep["graduation"]
    assert rep["journal"]["violation_rate"] is None  # no journal entries yet
    # P12.14 — the graduation criterion is the isolated discipline payload,
    # unproven (never a pass) until real canonical paper trades exist.
    assert rep["discipline"]["eligible"] == 0
    assert rep["discipline"]["compliance"] is None
    assert rep["graduation"]["stats"]["compliance"] is None
    assert rep["graduation"]["met"]["compliance"] is False


def test_desk_status_shape_and_json(desk_env):
    """desk_status() is the one-call advisory: required keys, JSON-safe."""
    import json

    from brain.agent import desk_status

    status = desk_status()
    for key in (
        "time",
        "version",
        "progression",
        "risk_gate",
        "pnl",
        "scorecard",
        "graduation",
        "pending_reviews",
        "open_exposure",
        "next_agent",
        "advice",
    ):
        assert key in status, f"desk_status missing {key!r}"
    assert status["risk_gate"]["allowed"] is True
    assert status["pending_reviews"] == 0
    assert status["next_agent"]["name"] in {
        "morning_brief",
        "watchdog",
        "paper_reviewer",
        "weekly_review",
    }
    advice = status["advice"]
    assert advice["action"] in {
        "CLEAR_STATE",
        "STAND_ASIDE",
        "REVIEW_QUEUE",
        "JOURNAL",
        "PAPER_GRIND",
        "SCAN",
    }
    assert advice["headline"]
    # empty book + student progression → grind samples, don't scan live
    assert advice["action"] == "PAPER_GRIND"
    json.dumps(status)  # must not raise


def test_desk_status_format(desk_env):
    from brain.agent import desk_status, format_desk_status

    text = format_desk_status(desk_status())
    assert "DESK STATUS" in text
    assert "ADVICE" in text
    assert "risk gate" in text.lower()


def test_desk_status_clear_state_when_angry(desk_env):
    """Behavioral flags outrank everything — a professional stands aside."""
    from brain.agent import desk_status
    from data.database import SignalDB

    with SignalDB() as db:
        db.set_trader_state(angry=True, note="tilted")
    status = desk_status()
    assert status["risk_gate"]["allowed"] is False
    assert "angry" in status["risk_gate"]["trader_flags"]
    assert status["advice"]["action"] == "CLEAR_STATE"


# ── readiness strip (TODO-1.bis) ─────────────────────────────────────────


def test_readiness_strip_shape_and_json(desk_env):
    """readiness_strip() rolls four pillars into one verdict, JSON-safe."""
    import json

    from brain.agent import readiness_strip

    strip = readiness_strip()
    for key in ("time", "version", "level", "ready", "headline", "pillars", "advice"):
        assert key in strip, f"readiness_strip missing {key!r}"
    assert strip["level"] in {"ok", "degraded", "blocked", "down"}
    assert strip["ready"] == (strip["level"] == "ok")
    assert {p["name"] for p in strip["pillars"]} == {
        "channels",
        "immune",
        "risk_gate",
        "data",
    }
    for p in strip["pillars"]:
        assert p["level"] in {"ok", "degraded", "blocked", "down"}
        assert p["headline"]
    json.dumps(strip)  # must not raise


def test_readiness_strip_rolls_up_worst_pillar(desk_env, monkeypatch):
    """The verdict is the WORST pillar, never an average."""
    from brain import agent

    monkeypatch.setattr(
        agent,
        "_channels_pillar",
        lambda: {
            "name": "channels",
            "level": "ok",
            "headline": "4/4 live",
            "detail": "",
        },
    )
    monkeypatch.setattr(
        agent,
        "_immune_pillar",
        lambda: {
            "name": "immune",
            "level": "ok",
            "headline": "4 check(s) ok",
            "detail": "",
        },
    )
    monkeypatch.setattr(
        agent,
        "_data_pillar",
        lambda: {
            "name": "data",
            "level": "ok",
            "headline": "1 series fresh",
            "detail": "",
        },
    )
    assert agent.readiness_strip()["level"] == "ok"

    monkeypatch.setattr(
        agent,
        "_immune_pillar",
        lambda: {
            "name": "immune",
            "level": "degraded",
            "headline": "1 warning(s)",
            "detail": "stale data",
        },
    )
    strip = agent.readiness_strip()
    assert strip["level"] == "degraded"
    assert "immune" in strip["headline"]

    monkeypatch.setattr(
        agent,
        "_channels_pillar",
        lambda: {
            "name": "channels",
            "level": "down",
            "headline": "1 channel(s) down",
            "detail": "",
        },
    )
    strip = agent.readiness_strip()
    assert strip["level"] == "down"
    assert strip["ready"] is False


def test_readiness_strip_reports_closed_gate_as_blocked(desk_env):
    """A closed gate is 'blocked' — worse than degraded, better than down."""
    from brain import agent
    from data.database import SignalDB

    with SignalDB() as db:
        db.set_trader_state(angry=True, note="tilted")
    pillar = agent._gate_pillar(agent.desk_status())
    assert pillar["level"] == "blocked"
    assert pillar["open"] is False


def test_readiness_strip_survives_broken_pillar(desk_env, monkeypatch):
    """A crashing probe degrades its own pillar, never the whole strip."""
    from brain import agent, channels

    def boom():
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(channels, "probe_all", boom)
    strip = agent.readiness_strip()
    assert strip["level"] == "down"
    ch = next(p for p in strip["pillars"] if p["name"] == "channels")
    assert ch["level"] == "down"
    assert "RuntimeError" in ch["detail"]
    # the other pillars still reported
    assert {p["name"] for p in strip["pillars"]} == {
        "channels",
        "immune",
        "risk_gate",
        "data",
    }


def test_format_readiness_strip(desk_env):
    from brain.agent import format_readiness_strip, readiness_strip

    text = format_readiness_strip(readiness_strip())
    assert "READINESS" in text
    for pillar in ("channels", "immune", "risk_gate", "data"):
        assert pillar in text


def test_ask_desk_intent(desk_env):
    from brain.agent import ask

    r = ask("what should I do right now?")
    assert r["intent"] == "desk"
    assert r["data"]["advice"]["action"]
    assert any("ADVICE" in line or "DESK STATUS" in line for line in r["answer"])


# ── loop_health (P14) ────────────────────────────────────────────────────


def test_loop_health_shape_and_json(desk_env):
    """loop_health() is the one daily number: required keys, JSON-safe."""
    import json

    from brain.agent import loop_health

    health = loop_health()
    for key in (
        "time",
        "version",
        "data_mode",
        "ready",
        "readiness",
        "gate",
        "advice",
        "loop",
        "graduation",
        "journal_prompt",
        "ritual",
        "next_step",
    ):
        assert key in health, f"loop_health missing {key!r}"
    loop = health["loop"]
    for key in (
        "real_paper_n",
        "expectancy_net",
        "win_rate",
        "profit_factor",
        "compliance",
        "eligible",
        "pending_reviews",
        "open_exposure",
    ):
        assert key in loop, f"loop missing {key!r}"
    assert loop["real_paper_n"] == 0
    assert health["gate"]["open"] is True
    assert health["advice"]["action"] in {
        "CLEAR_STATE",
        "STAND_ASIDE",
        "REVIEW_QUEUE",
        "JOURNAL",
        "PAPER_GRIND",
        "SCAN",
    }
    assert health["advice"]["action"] == "PAPER_GRIND"
    assert health["graduation"]["ready"] is False
    assert isinstance(health["graduation"]["criteria"], list)
    assert isinstance(health["graduation"]["by_setup"], list)
    ritual_names = [s["name"] for s in health["ritual"]]
    assert ritual_names == ["readiness", "loop", "gate", "act"]
    assert health["journal_prompt"]["question"]
    json.dumps(health)  # must not raise


def test_loop_health_format(desk_env):
    from brain.agent import format_loop_health, loop_health

    text = format_loop_health(loop_health())
    assert "DAILY RITUAL" in text
    assert "LOOP HEALTH" in text
    assert "GRADUATION BAR" in text
    assert "JOURNAL PROMPT" in text
    assert "Did I follow the system today?" in text


def test_ask_loop_intent(desk_env):
    from brain.agent import ask

    r = ask("how is the loop?")
    assert r["intent"] == "loop"
    assert r["data"]["loop"]["real_paper_n"] == 0
    assert any("LOOP HEALTH" in line or "DAILY RITUAL" in line for line in r["answer"])


def test_health_report_skips_cross_exchange_in_demo(desk_env):
    """Demo mode has no live Binance prices, so the multi-exchange
    cross-check must degrade to a note instead of running."""
    from brain.agent import health_report

    report = health_report()
    cross = report["data"]["cross_exchange"]
    assert cross["ok"] is False
    assert "demo" in cross["note"]
    assert "exchanges" not in cross


def test_cross_exchange_probe_uses_newest_candle(monkeypatch):
    """KuCoin, OKX and Bybit return newest-first; never compare an old candle.

    P10.7 generalised the probe (Bybit added) but the contract is the
    same function: brain.agent._cross_exchange_probe → snapshot_prices.
    """
    from brain.agent import _cross_exchange_probe

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, timeout):
        assert timeout == 6
        if "kucoin" in url:
            # KuCoin close is index 2.  The older row is intentionally far off.
            return Response(
                {
                    "data": [
                        ["200", "99", "100", "101", "98", "1", "100"],
                        ["100", "49", "50", "51", "48", "1", "50"],
                    ]
                }
            )
        if "okx" in url:
            # OKX close is index 4 and is also newest-first.
            return Response(
                {
                    "data": [
                        ["200", "99", "101", "98", "100", "1"],
                        ["100", "49", "51", "48", "50", "1"],
                    ]
                }
            )
        # Bybit V5: result.list, close index 4, newest-first.
        return Response(
            {
                "result": {
                    "list": [
                        ["200", "99", "101", "98", "100", "1", "1"],
                        ["100", "49", "51", "48", "50", "1", "1"],
                    ]
                }
            }
        )

    monkeypatch.setattr("requests.get", fake_get)
    cross = _cross_exchange_probe({"BTCUSDT": 100.0})

    assert cross["ok"] is True
    assert set(cross["exchanges"]) >= {"kucoin", "okx", "bybit"}
    assert cross["exchanges"]["kucoin"]["symbols"]["BTCUSDT"] == {
        "price": 100.0,
        "deviation_pct": 0.0,
        "flag": False,
    }
    assert cross["exchanges"]["okx"]["symbols"]["BTCUSDT"] == {
        "price": 100.0,
        "deviation_pct": 0.0,
        "flag": False,
    }
    assert cross["exchanges"]["bybit"]["symbols"]["BTCUSDT"] == {
        "price": 100.0,
        "deviation_pct": 0.0,
        "flag": False,
    }


# ── T2 — AI Copilot: structured sections + grounding sources ─────────────


def test_ask_results_carry_sections_and_sources(desk_env):
    """The Copilot contract: every ask() answer names its grounding sources
    and ships structured sections without changing the plain answer list."""
    from brain.agent import ask

    for question, intent in [
        ("is the risk gate open?", "risk"),
        ("how is the loop?", "loop"),
        ("what should I do right now?", "desk"),
        ("am i ready for micro?", "graduation"),
    ]:
        r = ask(question)
        assert r["intent"] == intent
        assert isinstance(r["answer"], list) and r["answer"]
        assert r["sources"], f"{intent} must cite its grounding surfaces"
        assert all(isinstance(s, str) and s for s in r["sources"])
        assert r["sections"]
        assert all("title" in s and "body" in s for s in r["sections"])
        assert r["sections"][0]["body"]


def test_ask_market_splits_read_and_decision_sections(desk_env):
    """'scan BTC' answers in two titled sections: the market read and the
    desk decision (with its vetoes), not one undifferentiated blob."""
    from brain.agent import ask

    r = ask("scan BTC", symbol="BTCUSDT", bars=200)
    assert r["intent"] == "market"
    titles = [s["title"] for s in r["sections"]]
    assert titles == ["Market read", "Desk decision"]
    assert "BTCUSDT" in r["sections"][0]["body"]
    assert r["sections"][1]["body"]


def test_ask_exposure_reports_measured_evidence_and_live_book(desk_env):
    """Open-position answers carry the calibrated (measured) expectancy and
    split the canonical live book from planned exposure."""
    from brain.agent import ask

    r = ask("any exposure right now?")
    assert r["intent"] == "exposure"
    assert r["sections"][0]["title"] == "Open positions"
    assert "flat" in r["sections"][0]["body"].lower()
    assert "live_open" in r["data"]
    assert "calibration" in r["data"]
