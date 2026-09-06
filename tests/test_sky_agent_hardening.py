"""tests/test_sky_agent_hardening.py — P7 hardening drills (offline, idempotent)."""

import os
import tempfile
from pathlib import Path

os.environ["SKY_NO_AUTO_INSTALL"] = "1"
os.environ["DEMO_MODE"] = "1"


def test_edgar_duplicate_accession_is_idempotent():
    from data.database import SignalDB
    from sky_agent.collectors.edgar import ingest_recent_filings, upsert_filings

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "hard1.db"
        os.environ["DB_PATH"] = str(db_path)
        rows = ingest_recent_filings(demo=True)
        with SignalDB(path=db_path) as db:
            n1 = upsert_filings(rows, db=db)
            n2 = upsert_filings(rows, db=db)  # duplicate
            # sec_events will insert a second event row per filing (append-only log),
            # but sec_filings PK prevents duplicate filings — count stays 1
            filings = db.conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
            assert filings == 1
            assert n1 == 1 and n2 == 1
        del os.environ["DB_PATH"]


def test_edgar_acceptance_datetime_is_preserved():
    """Look-ahead bias guard: acceptance_datetime is stored and not collapsed into filing_date/period."""
    from sky_agent.collectors.edgar import ingest_recent_filings

    rows = ingest_recent_filings(demo=True)
    assert rows[0]["acceptance_datetime"] != rows[0]["period_of_report"]
    assert "T" in rows[0]["acceptance_datetime"]  # ISO datetime, not just date


def test_recommendation_never_bypasses_risk_gate():
    from sky_agent.recommendation import build_recommendation

    # Even with huge expectancy, FAIL still yields AVOID
    rec = build_recommendation(
        asset="BTCUSDT",
        timeframe="1H",
        regime="bullish",
        detected="x",
        evidence=[],
        expectancy_R=5.0,
        sample_n=5000,
        risk_status="FAIL",
        confidence="HIGH",
    )
    assert rec["recommendation"] == "AVOID"
    assert rec["recommendation"] != "BUY NOW"


def test_scoring_never_produces_trading_order():
    from sky_agent.scoring import Scores

    # Scoring is pure — it cannot emit a trade string
    s = Scores(10, 10, 10, 10, 10, 10, 10)
    assert "BUY" not in s.level()
    assert "SELL" not in s.level()


def test_notifications_deduplicate():
    from sky_agent.notifications import dispatch

    payload = {"id": "dup-test", "kind": "crash drill"}
    r1 = dispatch(
        level="CRITICAL",
        title="CRITICAL test",
        body="first",
        payload=payload,
        minimum="HIGH",
    )
    r2 = dispatch(
        level="CRITICAL",
        title="CRITICAL test",
        body="first",
        payload=payload,
        minimum="HIGH",
    )
    assert r1["sent"] is True
    assert r2["sent"] is False
    assert r2["reason"] == "deduplicated"


def test_notifications_respect_level_gate():
    from sky_agent.notifications import dispatch

    r = dispatch(
        level="LOW",
        title="low",
        body="quiet",
        payload={"id": "low-gate"},
        minimum="HIGH",
    )
    assert r["sent"] is False


def test_daemon_survives_api_failure_stub():
    """Daemon tick wrappers degrade to {error:...} rather than raising, so one failing poll doesn't kill the loop."""
    from sky_agent.daemon import _tick_edgar, _tick_market, _tick_system

    # All three are exception-isolated and return a dict even in demo
    for fn in (_tick_market, _tick_edgar, _tick_system):
        out = fn(demo=True)
        assert isinstance(out, dict)


def test_system_probe_does_not_crash_on_missing_paths():
    from pathlib import Path

    from sky_agent.monitor_system import probe_system

    # nonsense store path — should still return a snap with level LOW/HIGH/CRITICAL
    snap = probe_system(store_path=Path("/tmp/nonexistent_sky_store_xyz"))
    assert snap["level"] in ("LOW", "HIGH", "CRITICAL")
    assert "ts" in snap


def test_memory_schema_survives_repeated_ensure():
    from data.database import SignalDB
    from sky_agent.memory import ensure_memory_schema

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "hard2.db"
        os.environ["DB_PATH"] = str(db_path)
        with SignalDB(path=db_path) as db:
            for _ in range(3):
                ensure_memory_schema(db)
            assert (
                db.conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='intelligence_reports'"
                ).fetchone()[0]
                == 1
            )
        del os.environ["DB_PATH"]


def test_hypothesis_backtest_is_stub_in_demo_and_shows_fact_tags():
    from sky_agent.hypothesis import run_hypothesis_backtest

    res = run_hypothesis_backtest("H-001")
    assert res["ok"] is True
    assert res["tag"] == "HYPOTHESIS"
    assert "baseline" in res and "filtered" in res


def test_daily_report_distinguishes_fact_interpretation_hypothesis():
    from sky_agent.daily_report import build_daily_report

    report = build_daily_report(demo=True)
    rec = report["recommendations"][0]
    assert rec["kind"] in ("FACT", "INTERPRETATION", "HYPOTHESIS")
