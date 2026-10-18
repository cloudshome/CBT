"""Read-only review probe for P12.15 — live-book source isolation.

Regression harness for the failure modes found in the post-PR-#37 safety
review of the live risk controls. P12.13/P12.14 isolated the *graduation*
gate (performance, then discipline) to the canonical live book, but every
live *risk* control still read ``decided_paper_rows(exclude_sim=True)`` with
no provenance filter — the P12.11 source boundary never reached them:

  A. daily/weekly loss limits fail OPEN: research-book wins pool into
     ``closed_pnl()`` and mask real canonical losses past the daily limit
  B. the drawdown ladder fails OPEN: research wins interleave into the
     equity sequence and refill a real losing streak before it can trip
     ``reduce_risk`` / ``stop_and_review``
  C. a research-only book moves live controls it has no authority over:
     research losses trip the daily limit, and the Monte Carlo ruin table /
     business scorecard report a "live" book that does not exist
     (research must neither unlock nor block — P12.13)
  D. the Kelly advisory was silently dead: ``kelly_from_progress()`` expects
     ``paper_progress()`` aggregates but was fed raw ``paper_trades`` rows,
     so any non-empty book raised ``KeyError('wins')`` into a blanket
     ``except`` → permanently "unavailable" (and never source-isolated)
  E. legacy NULL-provenance rows ARE the canonical book and must keep
     counting (P12.11 convention)
  F. control: a canonical-only book must read exactly as before

Each case is built in a throwaway SQLite database and measured through the
real surfaces (``brain.risk_gate.daily_weekly`` / ``drawdown``,
``brain.analytics.monte_carlo_ruin_table``, ``brain.metrics.business_metrics``,
``engine.hidden_alpha.kelly_from_rows`` over ``SignalDB.live_book_rows``).
It exits non-zero if any case is not answered as specified.

The probe writes nothing to the repository, never touches a real store, and
places no orders. Run:

    .venv/bin/python ops/probes/p12_15_livebook_probe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brain.analytics import monte_carlo_ruin_table
from brain.metrics import business_metrics
from brain.risk_gate import daily_weekly, drawdown
from data.database import SignalDB
from engine.hidden_alpha import kelly_from_rows

LIVE = ""  # canonical Binance spot source key
RESEARCH = "dukascopy:spot:bid"  # research-only book (XAU)


def _decided_paper(
    db: SignalDB,
    scan_id: int,
    *,
    rr: float = 2.0,
    sim_key: str | None = None,
    source_key: str | None = LIVE,
    ts: int | None = None,
) -> None:
    """Insert one decided (CLOSED) paper trade with explicit provenance."""
    ts = ts if ts is not None else int(time.time() * 1000)
    outcome = "TP_HIT" if rr > 0 else "STOP_LOSS"
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    closed_ts, entry_price, exit_price, outcome,
                                    rr_achieved, close_reason, sim_key, source_key)
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
            ts,
            ts,
            ts,
            100.0,
            102.0 if rr > 0 else 99.0,
            outcome,
            rr,
            "probe",
            sim_key,
            source_key,
        ),
    )
    db.conn.commit()


def _pooled_r_sum(db: SignalDB, since_ts: int = 0) -> float:
    """Exactly what closed_pnl() summed before P12.15 (no source filter)."""
    rows = db.decided_paper_rows(since_ts=since_ts, exclude_sim=True)
    return round(sum(float(r["rr_achieved"] or 0.0) for r in rows), 3)


def case(title: str, fn) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = SignalDB(Path(d) / "probe.db")
        try:
            observed = fn(db)
        finally:
            db.close()
    expected = observed.pop("expected_after_P12_15")
    got = observed.get("observed") or {}
    fixed = all(got.get(k) == v for k, v in expected.items())
    return {"case": title, "fixed": fixed, "expected": expected, **observed}


# ── A. daily loss limit: research wins mask real canonical losses ─────────
def case_daily_masked(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(5):  # −1.25% at student risk 0.25%
        _decided_paper(db, 100 + i, rr=-1.0, source_key=LIVE, ts=now)
    for i in range(6):  # research "profit" the desk never made
        _decided_paper(db, 200 + i, rr=2.0, source_key=RESEARCH, ts=now)
    dw = daily_weekly(db)
    return {
        "canonical_reality": "5 real losses today (−1.25% ≤ −1.0% limit)",
        "pooled_r_sum_pre_P12_15": _pooled_r_sum(db),  # +7.0 → not blocked
        "observed": {
            "daily_blocked": dw["daily_blocked"],
            "n": dw["today"]["n"],
            "r_sum": dw["today"]["r_sum"],
        },
        "expected_after_P12_15": {"daily_blocked": True, "n": 5, "r_sum": -5.0},
    }


# ── B. drawdown ladder: research wins refill a real losing streak ─────────
def case_drawdown_masked(db: SignalDB) -> dict:
    t = int(time.time() * 1000) - 10_000_000
    for i in range(24):  # 24 × 0.25% = 6.0% canonical dd
        _decided_paper(db, 300 + i, rr=-1.0, source_key=LIVE, ts=t)
        t += 10
        _decided_paper(db, 400 + i, rr=2.0, source_key=RESEARCH, ts=t)
        t += 10
    dd = drawdown(db)
    return {
        "canonical_reality": "24-loss streak → 6.0% dd → reduce_risk",
        "observed": {"max_drawdown_pct": dd["max_drawdown_pct"], "level": dd["level"]},
        "expected_after_P12_15": {"max_drawdown_pct": 6.0, "level": "reduce_risk"},
    }


# ── C. a research-only book must move NO live control ─────────────────────
def case_research_only(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(8):
        _decided_paper(db, 500 + i, rr=-1.0, source_key=RESEARCH, ts=now)
    dw = daily_weekly(db)
    dd = drawdown(db)
    mc = monte_carlo_ruin_table(db, samples=50, seed=1)
    bm = business_metrics(db)
    return {
        "canonical_reality": "the live desk has not traded at all",
        "pooled_r_sum_pre_P12_15": _pooled_r_sum(db),  # −8.0 → blocked
        "observed": {
            "daily_blocked": dw["daily_blocked"],
            "n": dw["today"]["n"],
            "dd_level": dd["level"],
            "mc_available": bool(mc.get("available")),
            "business_n": bm["overall"]["n"],
        },
        "expected_after_P12_15": {
            "daily_blocked": False,
            "n": 0,
            "dd_level": "normal",
            "mc_available": False,
            "business_n": 0,
        },
    }


# ── D. kelly advisory: alive again, and canonical-live only ───────────────
def case_kelly(db: SignalDB) -> dict:
    t = int(time.time() * 1000) - 10_000_000
    for i in range(12):
        _decided_paper(db, 700 + i, rr=2.0, source_key=LIVE, ts=t + i)
    for i in range(8):
        _decided_paper(db, 800 + i, rr=-1.0, source_key=LIVE, ts=t + 100 + i)
    for i in range(30):  # research wins must not inflate it
        _decided_paper(db, 900 + i, rr=2.0, source_key=RESEARCH, ts=t + 200 + i)
    legacy_error = None
    try:  # the pre-P12.15 wiring, verbatim
        from engine.hidden_alpha import kelly_from_progress

        kelly_from_progress(db.decided_paper_rows(exclude_sim=True))
    except Exception as exc:
        legacy_error = f"{type(exc).__name__}: {exc}"
    k = kelly_from_rows(db.live_book_rows())
    return {
        "canonical_reality": "12W/8L live book (+30 research wins to ignore)",
        "legacy_call_pre_P12_15": legacy_error,
        "observed": {
            "n_trades": k.get("n_trades"),
            "kelly_size": k.get("kelly_size"),
            "stand_aside": k.get("stand_aside"),
        },
        "expected_after_P12_15": {
            "n_trades": 20,
            "kelly_size": 1.0,
            "stand_aside": False,
        },
    }


# ── E. legacy NULL provenance IS the canonical book ────────────────────────
def case_legacy_null(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(5):
        _decided_paper(db, 1000 + i, rr=-1.0, source_key=None, ts=now)
    dw = daily_weekly(db)
    return {
        "canonical_reality": "5 real losses saved before source_key existed",
        "observed": {"daily_blocked": dw["daily_blocked"], "n": dw["today"]["n"]},
        "expected_after_P12_15": {"daily_blocked": True, "n": 5},
    }


# ── F. control: canonical-only book reads exactly as before ───────────────
def case_control(db: SignalDB) -> dict:
    now = int(time.time() * 1000)
    for i in range(3):
        _decided_paper(db, 1100 + i, rr=2.0, source_key=LIVE, ts=now)
    for i in range(2):
        _decided_paper(db, 1200 + i, rr=-1.0, source_key=LIVE, ts=now)
    dw = daily_weekly(db)
    return {
        "canonical_reality": "3W/2L canonical book, nothing to isolate",
        "pooled_r_sum_pre_P12_15": _pooled_r_sum(db),  # identical: +4.0
        "observed": {
            "daily_blocked": dw["daily_blocked"],
            "n": dw["today"]["n"],
            "r_sum": dw["today"]["r_sum"],
        },
        "expected_after_P12_15": {"daily_blocked": False, "n": 5, "r_sum": 4.0},
    }


CASES = [
    ("A: research wins mask real losses past the daily limit", case_daily_masked),
    ("B: research wins hide a real drawdown from the ladder", case_drawdown_masked),
    ("C: a research-only book moves live controls", case_research_only),
    ("D: kelly advisory dead on any populated book, and unisolated", case_kelly),
    ("E: legacy NULL-provenance rows keep counting as canonical", case_legacy_null),
    ("F: control — canonical-only book is unchanged", case_control),
]


def main() -> int:
    results = [case(t, f) for t, f in CASES]
    print(json.dumps(results, indent=2, sort_keys=False))
    print("\n" + "-" * 78)
    for r in results:
        print(
            f"{'PASS' if r['fixed'] else 'FAIL'}  {r['case']}\n"
            f"      observed: {r['observed']}   expected: {r['expected']}"
        )
    ok = all(r["fixed"] for r in results)
    print("-" * 78)
    print("ALL CASES BEHAVE AS SPECIFIED" if ok else "SOME LIVE CONTROLS STILL POOL SOURCES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
