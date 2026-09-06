"""Tests for W3 — the weekly trader review (brain/weekly.py).

Same population rules the whole P12 arc fought for: the review reads the
canonical live book only (simulator and research books excluded, P12.15),
every judgement is NET of costs (P12.18), and the graduation bar is quoted,
never moved. The next-practice-task ladder is deterministic and honest —
journals before discipline before samples before expectancy.
"""

from __future__ import annotations

import json
import time

import pytest

from brain.weekly import format_weekly_review, missing_journals, weekly_review
from data.database import SignalDB

DAY = 86_400_000


def _trade(
    db: SignalDB,
    sid: int,
    rr: float,
    days_ago: float,
    *,
    now: int,
    sim_key: str | None = None,
    source_key: str | None = None,
    plan: str = "Buy Pullback",
) -> None:
    """Insert one decided paper row. Cost-free (rr_net == rr) so the review's
    arithmetic is pinned independently of the cost model."""
    ts = int(now - days_ago * DAY)
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
             action, entry, stop_loss, take_profit, risk_reward, confidence_pct,
             status, created_ts, opened_ts, closed_ts, entry_price, exit_price,
             outcome, rr_achieved, rr_net, close_reason, sim_key, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            sid,
            f"SIG{sid}",
            plan,
            "BTCUSDT",
            "15m",
            "BUY",
            100.0,
            99.0,
            102.0,
            2.0,
            70,
            "CLOSED",
            ts,
            ts,
            ts,
            100.0,
            99.0 if rr < 0 else 102.0,
            "TP_HIT" if rr > 0 else "STOP_LOSS",
            rr,
            rr,
            "test",
            sim_key,
            source_key,
        ),
    )


@pytest.fixture
def now() -> int:
    return int(time.time() * 1000)


@pytest.fixture
def empty_db(tmp_path):
    db = SignalDB(tmp_path / "w.db")
    yield db
    db.close()


@pytest.fixture
def seeded_db(tmp_path, now):
    """5 canonical live trades (3 this week, 2 older), 1 simulator row,
    1 research row. Journals: scan 1 compliant, scan 2 violation → 3 missing."""
    db = SignalDB(tmp_path / "w.db")
    _trade(db, 1, 2.0, 6, now=now)
    _trade(db, 2, -1.0, 3, now=now)
    _trade(db, 3, 1.5, 1, now=now)
    _trade(db, 4, -1.0, 10, now=now)
    _trade(db, 5, 1.0, 20, now=now)
    _trade(db, 6, 3.0, 2, now=now, sim_key="sim:6")  # simulator
    _trade(db, 7, 4.0, 2, now=now, source_key="dukascopy:spot:bid")  # research
    db.conn.commit()
    db.save_journal(1, followed_rules=True, emotion="calm", mistake="none")
    db.save_journal(2, followed_rules=False, emotion="greedy", mistake="entered early")
    yield db
    db.close()


def test_empty_book_is_honest(empty_db, now):
    r = weekly_review(empty_db, now_ms=now)
    assert r["week"]["n"] == 0 and r["all_time"]["n"] == 0
    assert r["week"]["expectancy_net"] is None
    assert r["grade"]["grade"] == "—"
    # honest starter task, and never a fake equity curve
    assert r["next_practice_task"]["name"] in {
        "no_activity",
        "build_evidence",
        "journal_first",
        "discipline",
    }
    assert r["equity_curve"] == []
    assert all(b["n"] == 0 for b in r["r_distribution"])
    assert r["violations"]["compliance"] is None
    # the bar is quoted, not moved
    assert r["bar"]["expectancy"] == pytest.approx(0.50)
    assert r["bar"]["compliance"] == pytest.approx(0.90)


def test_json_safe_without_default_str(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    json.dumps(r)  # must not raise — the API has a sanitizer, the CLI does not


def test_week_window_vs_all_time(seeded_db, now):
    r = weekly_review(seeded_db, days=7, now_ms=now)
    assert r["week"]["n"] == 3, "only trades closed within the window"
    assert r["all_time"]["n"] == 5
    # net of costs == gross here (cost-free fixture): week = (2.0 -1.0 +1.5)/3
    assert r["week"]["expectancy_net"] == pytest.approx((2.0 - 1.0 + 1.5) / 3, rel=1e-3)
    assert r["all_time"]["total_r_net"] == pytest.approx(2.0 - 1.0 + 1.5 - 1.0 + 1.0)
    assert r["all_time"]["profit_factor"] == pytest.approx(4.5 / 2.0, rel=1e-3)
    # a custom window changes the week, never the all-time book
    r30 = weekly_review(seeded_db, days=30, now_ms=now)
    assert r30["week"]["n"] == 5
    assert r30["all_time"]["n"] == 5


def test_simulator_and_research_rows_never_count(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    # the +3R simulator row and +4R research row would double the book if pooled
    assert r["all_time"]["n"] == 5
    assert r["all_time"]["best_r"] == pytest.approx(2.0)
    assert r["source"].startswith("canonical live book")
    assert "simulator excluded" in r["source"]


def test_r_distribution_buckets_cover_the_book(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    total = sum(b["n"] for b in r["r_distribution"])
    assert total == r["all_time"]["n"]
    by_label = {b["bucket"]: b["n"] for b in r["r_distribution"]}
    assert by_label["(-2R,-1R]"] == 2  # 2 × -1.0R
    assert by_label["(+1R,+2R]"] == 2  # 2.0R and 1.5R
    assert by_label["(+0.5R,+1R]"] == 1  # 1.0R
    week_total = sum(b["n"] for b in r["r_distribution_week"])
    assert week_total == r["week"]["n"]


def test_equity_curve_matches_business_metrics(seeded_db, now):
    """One computation, many surfaces: the page cannot disagree with the
    Risk center's business scorecard."""
    from brain.metrics import business_metrics

    r = weekly_review(seeded_db, now_ms=now)
    m = business_metrics(seeded_db)
    assert r["equity_curve"] == m["equity_curve"]
    assert len(r["equity_curve"]) == 5  # never the simulator/research rows


def test_missing_journals_drive_task_and_gate(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    assert r["violations"]["missing_journals"] == 3
    assert set(r["violations"]["missing_scan_ids"]) == {3, 4, 5}
    assert r["next_practice_task"]["name"] == "journal_first"
    jg = missing_journals(seeded_db)
    assert jg["missing"] == 3
    assert set(jg["scan_ids"]) == {3, 4, 5}
    # finishing the journals lifts the hold
    for sid in (3, 4, 5):
        seeded_db.save_journal(sid, followed_rules=True, emotion="calm", mistake="none")
    assert missing_journals(seeded_db)["missing"] == 0
    r2 = weekly_review(seeded_db, now_ms=now)
    assert r2["next_practice_task"]["name"] != "journal_first"


def test_violations_breakdown_and_compliance(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    v = r["violations"]
    assert v["violations"] == 1
    assert v["by_mistake"] == {"entered early": 1}
    assert v["by_emotion"] == {"greedy": 1}
    # 1 compliant of 5 eligible → compliance 0.2; 3 missing count against it
    assert v["compliance"] == pytest.approx(0.2)
    assert v["eligible"] == 5
    assert v["compliance_bar"] == pytest.approx(0.90)


def test_graduation_tracker_names_the_gap(empty_db, now):
    _trade(empty_db, 1, 1.0, 1, now=now)
    empty_db.conn.commit()
    r = weekly_review(empty_db, now_ms=now)
    tracker = [t for t in r["graduation_tracker"] if t["plan_type"] == "Buy Pullback"]
    assert tracker, "the traded setup must appear in the tracker"
    t = tracker[0]
    assert t["paper_n"] == 1 and t["paper_target"] == 20
    assert any("backtest" in m for m in t["missing"])
    assert any("paper" in m for m in t["missing"])
    assert t["proven"] is False
    assert 0 <= t["paper_pct"] <= 100


def test_next_task_order_is_deterministic(empty_db, now):
    """journals → discipline → samples → expectancy → maintain."""
    # 1. no trades yet → build_evidence (samples missing) or no_activity
    r = weekly_review(empty_db, now_ms=now)
    assert r["next_practice_task"]["name"] in {"build_evidence", "no_activity"}
    # 2. one unjournaled violation-free trade → journal first
    _trade(empty_db, 1, 1.0, 1, now=now)
    empty_db.conn.commit()
    r = weekly_review(empty_db, now_ms=now)
    assert r["next_practice_task"]["name"] == "journal_first"
    # 3. journaled, compliant, but samples below floors → build evidence
    empty_db.save_journal(1, followed_rules=True, emotion="calm", mistake="none")
    r = weekly_review(empty_db, now_ms=now)
    assert r["next_practice_task"]["name"] == "build_evidence"


def test_protect_capital_task_on_losing_week(tmp_path, now):
    db = SignalDB(tmp_path / "w.db")
    # three net losses this week, all journaled compliant
    for i, sid in enumerate((11, 12, 13)):
        _trade(db, sid, -1.0, i + 1, now=now)
    db.conn.commit()
    for sid in (11, 12, 13):
        db.save_journal(sid, followed_rules=True, emotion="calm", mistake="none")

    # pretend all primary setups are already proven so the ladder reaches
    # the expectancy step honestly instead of asking for more samples
    from brain import weekly

    monkey_tracker = [
        {
            "plan_type": "Buy Pullback",
            "primary": True,
            "backtest_n": 100,
            "backtest_target": 100,
            "backtest_pct": 100.0,
            "paper_n": 20,
            "paper_target": 20,
            "paper_pct": 100.0,
            "expectancy_net": 0.6,
            "win_rate_net": 0.6,
            "proven": True,
            "missing": [],
        }
    ]
    orig = weekly._graduation_tracker
    weekly._graduation_tracker = lambda _db: monkey_tracker
    try:
        r = weekly_review(db, now_ms=now)
    finally:
        weekly._graduation_tracker = orig
    assert r["week"]["expectancy_net"] is not None
    assert r["week"]["expectancy_net"] < 0
    assert r["next_practice_task"]["name"] == "protect_capital"
    db.close()


def test_grade_components_sum_to_score(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    g = r["grade"]
    assert sum(c["points"] for c in g["components"]) == g["score"]
    assert 0 <= g["score"] <= 100
    assert g["grade"] in {"A", "B", "C", "D", "E", "—"}
    assert "not" in g["note"]  # honest: advisory, never the real gate


def test_weekly_agent_carries_the_same_payload(tmp_path, now):
    """WeeklyReviewAgent archives the same computation (invariant #10)."""
    from brain.agents import WeeklyReviewAgent

    db = SignalDB(tmp_path / "w.db")
    _trade(db, 1, 1.0, 1, now=now)
    db.conn.commit()
    res = WeeklyReviewAgent(db=db).run()
    assert res["status"] == "COMPLETED"
    assert "weekly" in res["data"], res["data"].keys()
    assert res["data"]["weekly"]["all_time"]["n"] == 1
    # and the archived agent run holds it too
    runs = db.latest_agent_runs(limit=1, agent="weekly_review")
    assert runs and "weekly" in (runs[0].get("payload") or {})
    db.close()


def test_format_contains_the_key_blocks(seeded_db, now):
    r = weekly_review(seeded_db, now_ms=now)
    text = format_weekly_review(r)
    assert "WEEKLY TRADER REVIEW" in text
    assert "graduation bar (unchanged, net)" in text
    assert "R distribution" in text
    assert "discipline" in text
    assert "NEXT PRACTICE TASK" in text
    assert "entered early" in text
    # missing journal scan ids appear where the trader looks for them
    assert "#3" in text
    assert "#4" in text


def test_root_mcp_weekly_review_tool(tmp_path, monkeypatch, now):
    """The MCP tool is the same computation, read-only, clamped 1..90 days."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "mcp.db"))
    import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "mcp.db"))
    db = SignalDB()
    _trade(db, 1, 1.0, 1, now=now)
    db.conn.commit()
    db.close()
    import mcp_server

    assert "weekly_review" in mcp_server.ALLOWED_TOOLS
    res = mcp_server.handle_tool_call("weekly_review", {"days": 7})
    assert res["all_time"]["n"] == 1
    assert res["next_practice_task"]["name"]
    # days clamp, never a crash on hostile input
    res2 = mcp_server.handle_tool_call("weekly_review", {"days": 9999})
    assert res2["window"]["days"] == 90
