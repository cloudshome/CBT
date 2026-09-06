"""tests/test_agents.py — Unit tests for autonomous desk agents and agent runs store."""

from brain.agents import (
    MorningBriefAgent,
    PaperReviewerAgent,
    WatchdogAgent,
    WeeklyReviewAgent,
    run_agent,
    run_all_agents,
)
from data.database import SignalDB


def test_agent_runs_db_recording(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        run_id = db.record_agent_run(
            "test_agent", "COMPLETED", summary="Test summary", payload={"k": "v"}
        )
        assert run_id > 0
        latest = db.latest_agent_runs(limit=5)
        assert len(latest) == 1
        assert latest[0]["agent"] == "test_agent"
        assert latest[0]["status"] == "COMPLETED"
        assert latest[0]["payload"]["k"] == "v"


def test_morning_brief_agent(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        agent = MorningBriefAgent(db=db)
        res = agent.run()
        assert res["agent"] == "morning_brief"
        assert res["status"] == "COMPLETED"
        assert "data" in res


def test_watchdog_agent(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        agent = WatchdogAgent(db=db)
        res = agent.run()
        assert res["agent"] == "watchdog"
        assert res["status"] in ("COMPLETED", "WARN")


def test_paper_reviewer_agent(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        agent = PaperReviewerAgent(db=db)
        res = agent.run()
        assert res["agent"] == "paper_reviewer"
        assert res["status"] == "COMPLETED"


def test_weekly_review_agent(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        agent = WeeklyReviewAgent(db=db)
        res = agent.run()
        assert res["agent"] == "weekly_review"
        assert res["status"] == "COMPLETED"


def test_run_agent_dispatcher(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        res1 = run_agent("morning", db=db)
        assert res1["status"] == "COMPLETED"
        res2 = run_agent("unknown_agent_xyz", db=db)
        assert res2["status"] == "ERROR"


def test_run_all_agents(tmp_path):
    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        all_res = run_all_agents(db=db)
        assert all_res["status"] == "COMPLETED"
        assert len(all_res["agents"]) == 4


def test_next_scheduled_agent_never_run(tmp_path):
    """With an empty agent_runs table, morning_brief is the first recommendation."""
    from brain.agents import next_scheduled_agent

    db_path = tmp_path / "test.db"
    with SignalDB(db_path) as db:
        nxt = next_scheduled_agent(db)
    assert nxt["name"] == "morning_brief"
    assert nxt["never_run"] is True
    assert nxt["overdue_hours"] == 24.0
    assert len(nxt["candidates"]) == 4


def test_next_scheduled_agent_picks_most_overdue(tmp_path):
    """A stale weekly_review beats a fresh morning_brief."""
    import time

    from brain.agents import next_scheduled_agent

    db_path = tmp_path / "test.db"
    now = int(time.time())
    with SignalDB(db_path) as db:
        db.record_agent_run("morning_brief", "COMPLETED", summary="fresh")
        # Backdate weekly_review far past its 168h cadence.
        db.conn.execute(
            "INSERT INTO agent_runs(agent, status, summary, payload_json, ts) "
            "VALUES(?,?,?,?,?)",
            ("weekly_review", "COMPLETED", "stale", "{}", now - 200 * 3600),
        )
        db.conn.commit()
        nxt = next_scheduled_agent(db)
    assert nxt["name"] == "weekly_review"
    assert nxt["overdue_hours"] > 0
