"""P12.17 — the week-boundary risk-gate crash.

``_week_start_utc()`` computed Monday 00:00 UTC as
``start.replace(day=start.day - start.weekday())``. ``datetime.replace()``
cannot cross a month boundary, so whenever the current week began in the
previous month the expression went to zero or negative and raised
``ValueError: day is out of range for month`` — 38 days of 2026, about one day
in ten.

The weekly loss limit is a hard B6 control, so this was not cosmetic: on those
dates the entire risk gate raised instead of answering, and each caller's
behaviour depended on whether it happened to sit inside a ``try``. A gate that
raises is neither open nor closed, which is the most dangerous state a risk
control can be in.

These tests pin the arithmetic (always the correct Monday, on every date of a
six-year sweep), pin the gate surfaces to answering across a month boundary,
and pin the immune check to always returning a verdict rather than dying.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

import brain.risk_gate as risk_gate
from brain.immune import check_risk_system, run_health_check
from brain.risk_gate import _day_start_utc, _week_start_utc, daily_weekly, evaluate, status_text
from data.database import SignalDB

# 2026-09-01 is a Tuesday; its week began Monday 2026-08-31 (previous month).
CROSSING = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
# 2026-08-16 is a Sunday; its week began Monday 2026-08-10 (same month).
SAFE = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def _frozen(now: datetime):
    class FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    return mock.patch.object(risk_gate, "datetime", FrozenDT)


def _monday_of(now: datetime) -> datetime:
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)


# ── 1. the arithmetic ──────────────────────────────────────────────────────
@pytest.mark.parametrize("stamp", [
    "2026-01-01",  # Thu, week began Mon 2025-12-29 (previous YEAR)
    "2026-02-01",  # Sun, week began Mon 2026-01-26
    "2026-03-01",  # Sun, week began Mon 2026-02-23
    "2026-09-01",  # Tue, week began Mon 2026-08-31
    "2026-11-01",  # Sun, week began Mon 2026-10-26
    "2027-01-01",  # Fri, week began Mon 2026-12-28
])
def test_week_start_survives_month_and_year_boundaries(stamp):
    now = datetime.fromisoformat(stamp).replace(hour=12, tzinfo=timezone.utc)
    got = datetime.fromtimestamp(_week_start_utc(now) / 1000, timezone.utc)
    assert got == _monday_of(now)
    assert got.weekday() == 0


def test_week_start_is_always_the_correct_monday_over_six_years():
    """Exhaustive sweep: the previous implementation failed 38 days a year."""
    day = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2030, 1, 1, tzinfo=timezone.utc)
    while day < end:
        for hour in (0, 12, 23):
            now = day.replace(hour=hour)
            got = datetime.fromtimestamp(_week_start_utc(now) / 1000, timezone.utc)
            assert got == _monday_of(now), now.isoformat()
            assert got.weekday() == 0, now.isoformat()
        day += timedelta(days=1)


def test_week_start_is_idempotent_on_monday_itself():
    monday = datetime(2026, 8, 31, 0, 0, 0, tzinfo=timezone.utc)
    assert monday.weekday() == 0
    got = datetime.fromtimestamp(_week_start_utc(monday) / 1000, timezone.utc)
    assert got == monday


def test_week_start_is_never_after_now_and_within_seven_days():
    for stamp in ("2026-09-01", "2026-08-16", "2027-01-01", "2026-03-01"):
        now = datetime.fromisoformat(stamp).replace(hour=12, tzinfo=timezone.utc)
        got = datetime.fromtimestamp(_week_start_utc(now) / 1000, timezone.utc)
        assert got <= now
        assert (now - got) < timedelta(days=7)


def test_day_start_is_unchanged_across_a_month_boundary():
    now = CROSSING
    got = datetime.fromtimestamp(_day_start_utc(now) / 1000, timezone.utc)
    assert got == now.replace(hour=0, minute=0, second=0, microsecond=0)


# ── 2. the gate surfaces answer across a month boundary ───────────────────
def test_daily_weekly_answers_on_a_month_crossing_week(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(CROSSING):
        dw = daily_weekly(db)
    assert dw["today"]["n"] == 0
    assert dw["week"]["n"] == 0
    assert dw["daily_blocked"] is False
    assert dw["weekly_blocked"] is False
    db.close()


def test_evaluate_answers_on_a_month_crossing_week(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(CROSSING):
        gate = evaluate(db)
    assert gate["allowed"] is True
    assert gate["blocked_by"] == []
    db.close()


def test_status_text_renders_on_a_month_crossing_week(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(CROSSING):
        text = status_text(db)
    assert "RISK & DISCIPLINE GATE" in text
    assert "day is out of range" not in text
    db.close()


def test_weekly_limit_still_blocks_across_a_month_boundary(tmp_path):
    """The fix must not weaken the weekly limit: losses in the part of the
    week that fell in the PREVIOUS month must still count."""
    db = SignalDB(tmp_path / "d.db")
    monday = _monday_of(CROSSING)                      # 2026-08-31, last month
    ts = int((monday + timedelta(hours=6)).timestamp() * 1000)
    for i in range(9):                                 # 9 x -0.25% = -2.25%
        db.conn.execute(
            """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol,
                                        timeframe, action, entry, stop_loss,
                                        take_profit, risk_reward, confidence_pct,
                                        status, created_ts, opened_ts, closed_ts,
                                        entry_price, exit_price, outcome,
                                        rr_achieved, rr_net, close_reason,
                                        source_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            # rr_net == rr_achieved: this test is about DATE arithmetic, so the
            # row is deliberately cost-free and the -2.25% figure stays exact
            # under the P12.18 net anchor.
            (i, f"SIG{i}", "Buy Pullback", "BTCUSDT", "15m", "BUY", 100.0, 99.0,
             102.0, 2.0, 70, "CLOSED", ts, ts, ts, 100.0, 99.0, "STOP_LOSS",
             -1.0, -1.0, "test", ""))
    db.conn.commit()
    with _frozen(CROSSING):
        dw = daily_weekly(db)
    assert dw["week"]["n"] == 9
    assert dw["week"]["pct"] == pytest.approx(-2.25)
    assert dw["weekly_blocked"] is True                # limit is 2.0%
    db.close()


# ── 3. the immune check always returns a verdict ──────────────────────────
def test_immune_risk_check_reports_ok_across_a_month_boundary(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(CROSSING):
        check = check_risk_system(db)
    assert check["status"] == "OK"
    db.close()


def test_immune_risk_check_reports_critical_when_the_gate_raises(tmp_path):
    """Defence in depth: an unanswerable gate must read CRITICAL, not crash."""
    db = SignalDB(tmp_path / "d.db")
    with mock.patch("brain.immune.evaluate_risk_gate",
                    side_effect=ValueError("day is out of range for month")):
        check = check_risk_system(db)
    assert check["status"] == "CRITICAL"
    assert "could not be evaluated" in check["detail"]
    assert "day is out of range for month" in check["detail"]
    db.close()


def test_health_report_survives_a_raising_risk_gate(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with mock.patch("brain.immune.evaluate_risk_gate",
                    side_effect=ValueError("boom")):
        report = run_health_check(db)
    assert report["status"] == "CRITICAL"
    risk = next(c for c in report["checks"] if c["name"] == "risk_system")
    assert risk["status"] == "CRITICAL"
    db.close()


def test_health_report_risk_check_is_ok_across_a_month_boundary(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(CROSSING):
        report = run_health_check(db)
    risk = next(c for c in report["checks"] if c["name"] == "risk_system")
    assert risk["status"] == "OK"
    db.close()


# ── 4. control: an ordinary week is unchanged ─────────────────────────────
def test_ordinary_week_is_unaffected(tmp_path):
    db = SignalDB(tmp_path / "d.db")
    with _frozen(SAFE):
        dw = daily_weekly(db)
        gate = evaluate(db)
    assert dw["week"]["n"] == 0
    assert gate["allowed"] is True
    got = datetime.fromtimestamp(_week_start_utc(SAFE) / 1000, timezone.utc)
    assert got == datetime(2026, 8, 10, tzinfo=timezone.utc)
    db.close()
