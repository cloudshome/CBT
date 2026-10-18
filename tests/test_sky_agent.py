"""tests/test_sky_agent.py — 24/7 Intelligence Agent tests (offline, DEMO_MODE)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

os.environ["SKY_NO_AUTO_INSTALL"] = "1"
os.environ["DEMO_MODE"] = "1"


def test_scoring_levels():
    from sky_agent.scoring import LEVEL_ORDER, Scores

    assert Scores(10, 10, 10, 10, 10, 10, 10).level() == "CRITICAL"
    assert Scores(5, 5, 5, 5, 5, 5, 5).level() == "HIGH"
    assert Scores(3, 3, 3, 3, 3, 3, 3).level() == "MEDIUM"
    assert Scores(1, 1, 1, 1, 1, 1, 1).level() == "LOW"
    assert LEVEL_ORDER["CRITICAL"] > LEVEL_ORDER["LOW"]


def test_score_edgar_event():
    from sky_agent.scoring import score_edgar_event

    s = score_edgar_event(severity=5, novel=True)
    assert s.level() in ("HIGH", "CRITICAL")
    assert s.reliability == 10


def test_memory_schema_idempotent():
    from data.database import SignalDB
    from sky_agent.memory import ensure_memory_schema

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        os.environ["DB_PATH"] = str(db_path)
        with SignalDB(path=db_path) as db:
            ensure_memory_schema(db)
            ensure_memory_schema(db)  # idempotent
            # tables exist
            rows = db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sec_filings'"
            ).fetchall()
            assert len(rows) == 1
        del os.environ["DB_PATH"]


def test_edgar_ingest_demo():
    from data.database import SignalDB
    from sky_agent.collectors.edgar import ingest_recent_filings, upsert_filings

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test2.db"
        os.environ["DB_PATH"] = str(db_path)
        rows = ingest_recent_filings(demo=True)
        assert len(rows) == 1
        assert rows[0]["form"] == "8-K"
        with SignalDB(path=db_path) as db:
            n = upsert_filings(rows, db=db)
            assert n == 1
            # idempotent second upsert
            n2 = upsert_filings(rows, db=db)
            assert n2 == 1
            cnt = db.conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
            assert cnt == 1
        del os.environ["DB_PATH"]


def test_event_classification():
    from sky_agent.collectors.edgar import classify_event_text

    etype, sev, direction = classify_event_text("bankruptcy filing chapter 11")
    assert etype == "bankruptcy"
    assert sev == 5


def test_recommendation_shape():
    from sky_agent.recommendation import RECOMMENDATIONS, build_recommendation

    rec = build_recommendation(
        asset="BTCUSDT",
        timeframe="15m",
        regime="bullish",
        detected="Buy Pullback at OB",
        evidence=["4H bullish", "1H BOS"],
        expectancy_R=0.31,
        sample_n=412,
        risk_status="PASS",
        confidence="MEDIUM",
        kind="HYPOTHESIS",
        invalidation="break below OB",
        sources=["SKY store"],
    )
    assert rec["recommendation"] in RECOMMENDATIONS
    assert rec["kind"] == "HYPOTHESIS"
    assert "BTCUSDT" in rec["asset"]


def test_recommendation_avoid_on_negative_expectancy():
    from sky_agent.recommendation import build_recommendation

    rec = build_recommendation(
        asset="BTCUSDT",
        timeframe="15m",
        regime="ranging",
        detected="x",
        evidence=[],
        expectancy_R=-0.1,
        sample_n=500,
        risk_status="PASS",
        confidence="LOW",
    )
    assert rec["recommendation"] == "AVOID"


def test_recommendation_avoid_on_risk_fail():
    from sky_agent.recommendation import build_recommendation

    rec = build_recommendation(
        asset="BTCUSDT",
        timeframe="15m",
        regime="bullish",
        detected="x",
        evidence=[],
        expectancy_R=0.5,
        sample_n=500,
        risk_status="FAIL",
        confidence="HIGH",
    )
    assert rec["recommendation"] == "AVOID"


def test_notifications_gate():
    from sky_agent.notifications import should_notify

    assert should_notify("CRITICAL", minimum="HIGH") is True
    assert should_notify("LOW", minimum="HIGH") is False
    assert should_notify("HIGH", minimum="HIGH") is True


def test_system_probe():
    from sky_agent.monitor_system import probe_system

    snap = probe_system()
    assert "ts" in snap
    assert "level" in snap
    assert snap["level"] in ("LOW", "HIGH", "CRITICAL")


def test_daily_report_build():
    from sky_agent.daily_report import build_daily_report

    report = build_daily_report(demo=True)
    assert "generated_at" in report
    assert "recommendations" in report
    assert len(report["recommendations"]) == 1
    assert report["recommendations"][0]["recommendation"] in (
        "WATCH",
        "CONSIDER",
        "WAIT",
        "AVOID",
    )


def test_hypothesis_propose_and_run():
    from data.database import SignalDB
    from sky_agent.hypothesis import propose_hypotheses, run_hypothesis_backtest

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test3.db"
        os.environ["DB_PATH"] = str(db_path)
        with SignalDB(path=db_path) as db:
            hyps = propose_hypotheses(db=db)
            assert len(hyps) == 3
            cnt = db.conn.execute("SELECT COUNT(*) FROM research_hypotheses").fetchone()[0]
            assert cnt == 3
        result = run_hypothesis_backtest("H-001", symbol="BTCUSDT", timeframe="15m")
        assert result["ok"] is True
        assert "hypothesis_id" in result
        del os.environ["DB_PATH"]


def test_daemon_one_tick():
    from sky_agent.daemon import run_forever

    result = run_forever(demo=True, max_ticks=1)
    assert result["ticks"] == 1
    assert "last_results" in result


def test_cli_sky_agent_health():
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "main.py"), "sky-agent", "health", "--json"],
        env={**os.environ, "DEMO_MODE": "1", "SKY_NO_AUTO_INSTALL": "1"},
        text=True,
    )
    payload = json.loads(out)
    assert "system" in payload
    assert "readiness" in payload


def test_cli_sky_agent_report():
    out = subprocess.check_output(
        [
            sys.executable,
            str(ROOT / "main.py"),
            "sky-agent",
            "report",
            "--demo",
            "--json",
        ],
        env={**os.environ, "DEMO_MODE": "1", "SKY_NO_AUTO_INSTALL": "1"},
        text=True,
    )
    payload = json.loads(out)
    assert "recommendations" in payload


def test_systemd_unit_exists():
    assert Path("ops/systemd/sky-agent.service").exists()
    txt = Path("ops/systemd/sky-agent.service").read_text()
    assert "EnvironmentFile=-/etc/sky/sky.env" in txt
    assert "PYTHONUNBUFFERED=1" in txt
    assert "Restart=always" in txt
    assert "sky_agent.daemon" in txt
    assert "NoNewPrivileges=yes" in txt


def test_discovery_doc_exists():
    assert Path("docs/DISCOVERY_2026-08-19_AGENT.md").exists()
    txt = Path("docs/DISCOVERY_2026-08-19_AGENT.md").read_text(encoding="utf-8")
    assert "24/7" in txt
    assert "SEC EDGAR" in txt
    assert "Hermes" in txt


def test_score_never_trades():
    """Agent never produces a BUY NOW — only WATCH/CONSIDER/WAIT/AVOID."""
    from sky_agent.recommendation import build_recommendation

    for rr in [0.5, 1.0, 5.0]:
        rec = build_recommendation(
            asset="BTCUSDT",
            timeframe="15m",
            regime="bullish",
            detected="x",
            evidence=[],
            expectancy_R=rr,
            sample_n=1000,
            risk_status="PASS",
            confidence="HIGH",
        )
        assert rec["recommendation"] != "BUY NOW"
        assert "BUY NOW" not in str(rec)
