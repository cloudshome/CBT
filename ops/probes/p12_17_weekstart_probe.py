"""Read-only review probe for P12.17 — the week-boundary risk-gate crash.

``brain.risk_gate._week_start_utc()`` computes Monday 00:00 UTC by subtracting
the weekday from the *day of month*:

    start = start.replace(day=start.day - start.weekday())   # Monday

``datetime.replace(day=...)`` cannot cross a month boundary. Whenever the
current week began in the previous month, ``start.day - start.weekday()`` is
zero or negative and the call raises ``ValueError: day is out of range for
month``. On a Monday-start week that is **every week spanning a month end** —
38 days of 2026, roughly one day in ten.

The weekly loss limit is one of the two hard limits in decision B6, so this is
not a cosmetic date bug: on those dates the entire risk gate raises instead of
answering, and the behaviour of each caller depends on whether it happens to
sit inside a ``try``.

Cases measured here:

  A. ``_week_start_utc()`` raises on a week that began in the previous month,
     and returns the correct Monday when the week is inside one month
  B. every ``brain.risk_gate`` entry point (``daily_weekly``, ``drawdown`` is
     unaffected, ``evaluate``, ``status_text``) raises on such a date
  C. the paper runner's enrolment gate fails CLOSED but reports the nonsense
     reason "day is out of range for month" instead of a risk reason
  D. ``brain.immune.check_risk_system()`` — the diagnostic whose whole job is
     to notice a broken risk system — has no ``except`` around the gate, so
     ``run_health_check()`` raises and reports nothing at all
  E. the CLI approval gate (``main.py approve``) propagates the ValueError
     instead of allowing or blocking
  F. control: on a date whose week does not cross a month boundary every
     surface answers normally

Each case is measured against a frozen clock in a throwaway SQLite database.
The probe exits non-zero if any case is not answered as specified.

It writes nothing to the repository, never touches a real store, and places no
orders. Run:

    .venv/bin/python ops/probes/p12_17_weekstart_probe.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import brain.risk_gate as risk_gate
from brain.immune import check_risk_system, run_health_check
from data.database import SignalDB
from data.paper_trading import PaperTradingRunner

# 2026-09-01 is a Tuesday; its week began Monday 2026-08-31 — previous month.
CROSSING = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
# 2026-08-16 is a Sunday; its week began Monday 2026-08-10 — same month.
SAFE = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)


def _frozen(now: datetime):
    """Patch brain.risk_gate's datetime so _day/_week_start_utc see `now`."""
    class FrozenDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    return mock.patch.object(risk_gate, "datetime", FrozenDT)


def _expected_monday(now: datetime) -> int:
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp() * 1000)


def _call(fn):
    """Return ('ok', value) or ('raised', 'ExcType: msg')."""
    try:
        return "ok", fn()
    except Exception as exc:  # noqa: BLE001 - the probe is measuring this
        return "raised", f"{type(exc).__name__}: {exc}"


def _seed_approved(db: SignalDB) -> None:
    ts = int(time.time() * 1000)
    db.conn.execute(
        """INSERT INTO scans(id, signal_id, ts, symbol, timeframe, action, entry,
                             stop_loss, take_profit, risk_reward, status,
                             lifecycle_ts, plans_json)
           VALUES (1,'SIG1',?,'BTCUSDT','15m','BUY',100.0,99.0,102.0,2.0,
                   'APPROVED',?,'[]')""", (ts, ts))
    db.conn.commit()


def case(title: str, fn) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = SignalDB(Path(d) / "probe.db")
        try:
            observed = fn(db)
        finally:
            db.close()
    expected = observed.pop("expected_after_P12_17")
    got = observed.get("observed") or {}
    fixed = all(got.get(k) == v for k, v in expected.items())
    return {"case": title, "fixed": fixed, "expected": expected, **observed}


# ── A. the helper itself ──────────────────────────────────────────────────
def case_helper(db: SignalDB) -> dict:
    with _frozen(CROSSING):
        crossing = _call(lambda: risk_gate._week_start_utc())
    with _frozen(SAFE):
        safe = _call(lambda: risk_gate._week_start_utc())
    return {"canonical_reality": "2026-09-01 (Tue) — its week began Mon 2026-08-31",
            "observed": {
                "crossing_status": crossing[0],
                "crossing_is_correct_monday":
                    crossing[0] == "ok" and crossing[1] == _expected_monday(CROSSING),
                "safe_is_correct_monday":
                    safe[0] == "ok" and safe[1] == _expected_monday(SAFE)},
            "detail_pre_fix": crossing[1] if crossing[0] == "raised" else None,
            "expected_after_P12_17": {"crossing_status": "ok",
                                      "crossing_is_correct_monday": True,
                                      "safe_is_correct_monday": True}}


# ── B. every risk-gate entry point ────────────────────────────────────────
def case_gate_surfaces(db: SignalDB) -> dict:
    with _frozen(CROSSING):
        dw = _call(lambda: risk_gate.daily_weekly(db))
        ev = _call(lambda: risk_gate.evaluate(db))
        st = _call(lambda: risk_gate.status_text(db))
    return {"canonical_reality": "an empty book on a month-crossing week: "
                                 "the gate should read 0 trades and be OPEN",
            "observed": {"daily_weekly": dw[0], "evaluate": ev[0],
                         "status_text": st[0],
                         "gate_allowed": (ev[1]["allowed"] if ev[0] == "ok"
                                          else None)},
            "detail_pre_fix": dw[1] if dw[0] == "raised" else None,
            "expected_after_P12_17": {"daily_weekly": "ok", "evaluate": "ok",
                                      "status_text": "ok",
                                      "gate_allowed": True}}


# ── C. the paper runner's enrolment gate ──────────────────────────────────
def case_runner_enrolment(db: SignalDB) -> dict:
    _seed_approved(db)
    runner = PaperTradingRunner(db=db, client=None)
    with _frozen(CROSSING):
        status, value = _call(runner.enroll_approved)
    errors = [] if status == "raised" else list(value.errors)
    events = [] if status == "raised" else list(value.events)
    date_error = any("day is out of range" in str(e.get("error", ""))
                     for e in errors)
    # Whatever the runner decides, it must decide it for a RISK reason. On an
    # empty book the standing B10 rule ("setup unproven" at the student level)
    # legitimately blocks enrolment on every date — that is not this bug and
    # must not be "fixed" here. The contract is: no date error, and any block
    # is stated as a risk reason.
    reasons = [str(e.get("reason", "")) for e in events]
    date_reason = any("day is out of range" in r for r in reasons)
    return {"canonical_reality": "the gate must answer for a RISK reason; on "
                                 "an empty book B10 'setup unproven' applies "
                                 "on every date",
            "observed": {"call": status,
                         "date_error_reported": date_error,
                         "date_reason_reported": date_reason,
                         "errors": len(errors)},
            "detail_post_fix": (reasons[0] if reasons else None),
            "expected_after_P12_17": {"call": "ok",
                                      "date_error_reported": False,
                                      "date_reason_reported": False,
                                      "errors": 0}}


# ── D. the immune system that should have caught this ─────────────────────
def case_immune(db: SignalDB) -> dict:
    with _frozen(CROSSING):
        chk = _call(lambda: check_risk_system(db))
        health = _call(lambda: run_health_check(db))
    # The risk_system check specifically must report OK (the gate is open on
    # an empty book). Overall health may still be CRITICAL for unrelated
    # reasons — e.g. stale sample candle data in a fresh checkout — so this
    # case asserts the risk verdict, not the aggregate.
    risk_check = None
    if health[0] == "ok":
        risk_check = next((c["status"] for c in health[1]["checks"]
                           if c["name"] == "risk_system"), None)
    return {"canonical_reality": "the diagnostic whose job is to notice a "
                                 "broken risk system must always answer",
            "observed": {"check_risk_system": chk[0],
                         "run_health_check": health[0],
                         "risk_verdict": (chk[1]["status"] if chk[0] == "ok"
                                          else None),
                         "risk_check_in_report": risk_check},
            "detail_pre_fix": chk[1] if chk[0] == "raised" else None,
            "expected_after_P12_17": {"check_risk_system": "ok",
                                      "run_health_check": "ok",
                                      "risk_verdict": "OK",
                                      "risk_check_in_report": "OK"}}


# ── E. the CLI approval gate ──────────────────────────────────────────────
def case_cli_approval(db: SignalDB) -> dict:
    _seed_approved(db)
    with _frozen(CROSSING):
        status, value = _call(lambda: risk_gate.evaluate(
            db, symbol="BTCUSDT", plan_type="Buy Pullback", action="BUY"))
    # `approve` must return a DECISION with reasons a human can act on. The
    # standing B10 "setup unproven" block is expected on an empty book; a date
    # error is not a decision at all.
    blocked = [] if status == "raised" else list(value.get("blocked_by", []))
    date_reason = any("day is out of range" in b for b in blocked)
    return {"canonical_reality": "`main.py approve` must return a decision, "
                                 "not raise a date error at the human",
            "observed": {"call": status,
                         "date_reason_reported": date_reason,
                         "weekly_read":
                             (value["details"]["daily_weekly"]["week"]["n"]
                              if status == "ok" else None)},
            "detail_pre_fix": value if status == "raised" else None,
            "detail_post_fix": (blocked[0] if blocked else None),
            "expected_after_P12_17": {"call": "ok",
                                      "date_reason_reported": False,
                                      "weekly_read": 0}}


# ── F. control: a week inside one month is unaffected ─────────────────────
def case_control(db: SignalDB) -> dict:
    with _frozen(SAFE):
        dw = _call(lambda: risk_gate.daily_weekly(db))
        ev = _call(lambda: risk_gate.evaluate(db))
        health = _call(lambda: run_health_check(db))
    return {"canonical_reality": "2026-08-16 (Sun), week began Mon 2026-08-10",
            "observed": {"daily_weekly": dw[0], "evaluate": ev[0],
                         "run_health_check": health[0],
                         "week_n": (dw[1]["week"]["n"] if dw[0] == "ok" else None)},
            "expected_after_P12_17": {"daily_weekly": "ok", "evaluate": "ok",
                                      "run_health_check": "ok", "week_n": 0}}


CASES = [
    ("A. _week_start_utc() raises when the week began last month", case_helper),
    ("B. every risk-gate entry point raises on such a date", case_gate_surfaces),
    ("C. paper enrolment reports a date error instead of a risk reason",
     case_runner_enrolment),
    ("D. the immune risk check dies, taking run_health_check() with it",
     case_immune),
    ("E. the CLI approval gate propagates a ValueError", case_cli_approval),
    ("F. control: a week inside one month is unaffected", case_control),
]


def main() -> int:
    results = [case(title, fn) for title, fn in CASES]
    print(json.dumps({"probe": "P12.17 week-boundary risk-gate crash",
                      "results": results,
                      "all_fixed": all(r["fixed"] for r in results)},
                     indent=2, default=str))
    return 0 if all(r["fixed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
