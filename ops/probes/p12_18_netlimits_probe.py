"""Read-only review probe for P12.18 — the net anchor at the hard limits.

P12.6 restated the desk's numbers net of costs (``E_net = E_gross − fees −
slip − funding``) and P12.8 stated the doctrine that matters here:

    "A measurement only matters where something acts on it."

P12.8 then walked the net anchor into the two *decision* sites it found —
``multiplier_from_score()`` and ``setup_proven()``. It missed the others. The
**hard risk limits** in decision B6 are decision sites too — arguably the most
consequential ones, because they are the desk's stop-loss on itself — and they
still judge **gross** ``rr_achieved``:

  * ``closed_pnl()``  → the daily and weekly loss limits
  * ``drawdown()``    → the reduce_risk / stop_and_review / full_review ladder
  * ``brain.metrics._equity_curve()`` / ``_metrics()`` → the scorecard's
    equity, expectancy, profit factor and max-drawdown reads

This matters most on the **live paper book**, because the live runner never
writes ``rr_net``: ``close_paper_trade()`` stores ``rr_achieved`` only, so
every live row has ``rr_net IS NULL``. Costs for those rows exist solely as a
compute-on-read step (``brain.analytics._net_outcome()``, which the Monte
Carlo surfaces already use). The limits never take that step.

Cases measured here, all using the repo's own cost model — nothing hypothesised:

  A. the daily loss limit fails OPEN: a book that is past the limit net of
     costs reads inside it gross, and the gate stays open
  B. the weekly loss limit fails OPEN the same way
  C. the drawdown ladder under-reports: the net equity curve is deeper than
     the gross one, so the ladder can sit a rung lower than reality
  D. the business scorecard's equity/expectancy/PF are gross-anchored, so the
     scorecard disagrees with the net-anchored P12.6 strategy scorecard
  E. live rows really do have rr_net IS NULL, so this is the normal live path
     and not an edge case
  F. control: on a zero-cost book gross and net agree exactly, so the fix must
     move nothing

Each case is built in a throwaway SQLite database and measured through the
real surfaces. It exits non-zero if any case is not answered as specified.

The probe writes nothing to the repository, never touches a real store, and
places no orders. Run:

    .venv/bin/python ops/probes/p12_18_netlimits_probe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brain import risk_gate
from brain.analytics import _net_outcome
from brain.metrics import business_metrics
from brain.risk_gate import daily_weekly, drawdown
from data.database import SignalDB

RISK_PCT = 0.25  # student progression risk per trade
DAILY_LIMIT = 1.0  # student daily loss limit (%)
WEEKLY_LIMIT = 2.0  # student weekly loss limit (%)


def _paper(
    db: SignalDB,
    scan_id: int,
    *,
    rr: float,
    ts: int,
    hold_hours: float = 6.0,
    rr_net: float | None = None,
) -> None:
    """Insert one decided live paper trade. rr_net defaults to NULL, which is
    what the live runner actually writes (close_paper_trade stores gross only)."""
    outcome = "TP_HIT" if rr > 0 else "STOP_LOSS"
    opened = ts - int(hold_hours * 3_600_000)
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    closed_ts, entry_price, exit_price, outcome,
                                    rr_achieved, rr_net, close_reason, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"SIG{scan_id}",
            "Buy Pullback",
            "BTCUSDT",
            "15m",
            "BUY",
            100.0,
            99.0,
            102.0,
            2.0,
            70,
            "CLOSED",
            opened,
            opened,
            ts,
            100.0,
            102.0 if rr > 0 else 99.0,
            outcome,
            rr,
            rr_net,
            "probe",
            "",
        ),
    )
    db.conn.commit()


def _sums(db: SignalDB) -> tuple[float, float]:
    """(gross R, net R) over the live book, using the repo's own cost model."""
    rows = db.live_book_rows()
    gross = sum(float(r["rr_achieved"] or 0.0) for r in rows)
    net = sum(_net_outcome(r) for r in rows)
    return round(gross, 3), round(net, 3)


def case(title: str, fn) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = SignalDB(Path(d) / "probe.db")
        try:
            observed = fn(db)
        finally:
            db.close()
    expected = observed.pop("expected_after_P12_18")
    got = observed.get("observed") or {}
    fixed = all(got.get(k) == v for k, v in expected.items())
    return {"case": title, "fixed": fixed, "expected": expected, **observed}


# ── A. the daily loss limit ───────────────────────────────────────────────
def case_daily_limit(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(8):  # scratch losses: small gross, real net
        _paper(db, i, rr=-0.4, ts=now)
    gross, net = _sums(db)
    dw = daily_weekly(db)
    return {
        "canonical_reality": f"8 live losses: {gross:+.3f}R gross "
        f"({gross * RISK_PCT:+.3f}%) but {net:+.3f}R net "
        f"({net * RISK_PCT:+.3f}%) once fees are paid",
        "net_breaches_limit": round(net * RISK_PCT, 3) <= -DAILY_LIMIT,
        "observed": {
            "daily_blocked": dw["daily_blocked"],
            "reported_pct": dw["today"]["pct"],
        },
        "expected_after_P12_18": {
            "daily_blocked": True,
            "reported_pct": round(net * RISK_PCT, 3),
        },
    }


# ── B. the weekly loss limit ──────────────────────────────────────────────
def case_weekly_limit(db: SignalDB) -> dict:
    # Spread across this week but before today, so only the weekly limit is in play.
    now = int(time.time() * 1000)
    monday = risk_gate._week_start_utc()
    ts = monday + 3_600_000
    day_start = risk_gate._day_start_utc()
    if ts >= day_start:  # keep the rows out of "today"
        ts = monday + 60_000
    for i in range(16):
        _paper(db, i, rr=-0.4, ts=min(ts + i * 60_000, max(monday, day_start - 60_000)))
    gross, net = _sums(db)
    dw = daily_weekly(db)
    return {
        "canonical_reality": f"16 live losses this week: {gross:+.3f}R gross "
        f"vs {net:+.3f}R net",
        "net_breaches_limit": round(net * RISK_PCT, 3) <= -WEEKLY_LIMIT,
        "observed": {
            "weekly_blocked": dw["weekly_blocked"],
            "reported_pct": dw["week"]["pct"],
        },
        "expected_after_P12_18": {
            "weekly_blocked": True,
            "reported_pct": round(net * RISK_PCT, 3),
        },
    }


# ── C. the drawdown ladder ────────────────────────────────────────────────
def case_drawdown_ladder(db: SignalDB) -> dict:
    """Size the run so the NET curve trips reduce_risk (>=5%) but gross does not."""
    ts = int(time.time() * 1000) - 50_000_000
    for i in range(32):
        _paper(db, i, rr=-0.5, ts=ts + i * 600_000)
    dd = drawdown(db)
    gross, net = _sums(db)
    # The true (net) ladder reading, computed the same way drawdown() does.
    from config import ACCOUNT_BALANCE

    balance = ACCOUNT_BALANCE or 10_000.0
    equity = peak = balance
    net_dd = 0.0
    for r in db.live_book_rows():
        equity += balance * (_net_outcome(r) * RISK_PCT / 100.0)
        peak = max(peak, equity)
        net_dd = max(net_dd, (peak - equity) / peak * 100.0 if peak else 0.0)
    return {
        "canonical_reality": f"a 32-trade losing run: {gross:+.3f}R gross vs "
        f"{net:+.3f}R net — the true curve is deeper",
        "gross_r": gross,
        "net_r": net,
        "gross_drawdown_pct": round(abs(gross) * RISK_PCT, 2),
        "net_drawdown_pct": round(net_dd, 2),
        "observed": {
            "reported_drawdown_pct": dd["max_drawdown_pct"],
            "level": dd["level"],
        },
        "expected_after_P12_18": {
            "reported_drawdown_pct": round(net_dd, 2),
            "level": "reduce_risk",
        },
    }


# ── D. the business scorecard ─────────────────────────────────────────────
def case_scorecard(db: SignalDB) -> dict:
    ts = int(time.time() * 1000) - 20_000_000
    for i in range(6):
        _paper(db, i, rr=1.5, ts=ts + i * 600_000)
    for i in range(6, 14):
        _paper(db, i, rr=-1.0, ts=ts + i * 600_000)
    gross, net = _sums(db)
    overall = business_metrics(db)["overall"]
    return {
        "canonical_reality": f"6 wins / 8 losses: {gross:+.3f}R gross vs "
        f"{net:+.3f}R net",
        "observed": {
            "expectancy_is_net": abs(overall["expectancy_r"] - round(net / 14.0, 3))
            < 5e-4
        },
        "reported_expectancy_r": overall["expectancy_r"],
        "gross_expectancy_r": round(gross / 14.0, 3),
        "net_expectancy_r": round(net / 14.0, 3),
        "expected_after_P12_18": {"expectancy_is_net": True},
    }


# ── E. live rows really do carry rr_net IS NULL ───────────────────────────
def case_live_rows_have_no_net(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    _paper(db, 1, rr=-1.0, ts=now)
    row = db.live_book_rows()[0]
    return {
        "canonical_reality": "close_paper_trade() writes rr_achieved only, "
        "so costs must be computed on read",
        "observed": {
            "rr_net_is_null": row["rr_net"] is None,
            "net_differs_from_gross": abs(_net_outcome(row) - float(row["rr_achieved"]))
            > 1e-9,
        },
        "expected_after_P12_18": {
            "rr_net_is_null": True,
            "net_differs_from_gross": True,
        },
    }


# ── F. control: a zero-cost book must be untouched ────────────────────────
def case_control_zero_cost(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(4):
        # rr_net explicitly equal to gross = a book with no costs recorded
        _paper(db, i, rr=-0.5, ts=now, rr_net=-0.5)
    dw = daily_weekly(db)
    gross, net = _sums(db)
    return {
        "canonical_reality": "rr_net == rr_achieved, so nothing may move",
        "observed": {
            "gross_equals_net": gross == net,
            "reported_pct": dw["today"]["pct"],
            "daily_blocked": dw["daily_blocked"],
        },
        "expected_after_P12_18": {
            "gross_equals_net": True,
            "reported_pct": -0.5,
            "daily_blocked": False,
        },
    }


CASES = [
    ("A. daily loss limit fails OPEN on a net-breaching book", case_daily_limit),
    ("B. weekly loss limit fails OPEN on a net-breaching book", case_weekly_limit),
    (
        "C. drawdown ladder under-reports the true (net) equity curve",
        case_drawdown_ladder,
    ),
    ("D. business scorecard expectancy/PF are gross-anchored", case_scorecard),
    (
        "E. live paper rows carry rr_net IS NULL (the normal path)",
        case_live_rows_have_no_net,
    ),
    ("F. control: a zero-cost book is unchanged", case_control_zero_cost),
]


def main() -> int:
    results = [case(title, fn) for title, fn in CASES]
    print(
        json.dumps(
            {
                "probe": "P12.18 net anchor at the hard limits",
                "results": results,
                "all_fixed": all(r["fixed"] for r in results),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if all(r["fixed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
