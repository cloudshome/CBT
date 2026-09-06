"""Read-only review probe for P12.14 — graduation discipline isolation.

Regression harness for the four failure modes found in the post-PR-#36 safety
review of the graduation compliance criterion. Each case is built in a
throwaway SQLite database and measured twice: with the pooled pre-P12.14
formula (``1 - violation_rate(db)``) and with
``brain.journal.graduation_discipline()``. It exits non-zero if any case is
not answered as specified. The failure modes are:

  A. simulator journals (``sim_key IS NOT NULL``) count toward compliance
  B. non-canonical research journals (``source_key='dukascopy:spot:bid'``)
     count toward canonical compliance
  C. ``followed_rules IS NULL`` is scored as a non-violation (100% compliance
     with no rule-following answer recorded)
  D. missing journals fail *open*: unjournaled decided trades are invisible to
     ``violation_rate(db)`` and therefore cannot lower compliance

The probe writes nothing to the repository, never touches a real store, and
places no orders. Run:

    .venv/bin/python ops/probes/p12_14_discipline_probe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brain.journal import graduation_discipline, save_journal, violation_rate
from data.database import SignalDB

LIVE = ""  # canonical Binance spot source key
RESEARCH = "dukascopy:spot:bid"  # research-only book (XAU)


def _decided_paper(
    db: SignalDB,
    scan_id: int,
    *,
    rr: float = 2.0,
    sim_key: str | None = None,
    source_key: str = LIVE,
) -> None:
    """Insert one decided (CLOSED) paper trade with explicit provenance."""
    ts = int(time.time() * 1000)
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


def _compliance(db: SignalDB) -> dict:
    """The pooled pre-P12.14 number vs. the isolated P12.14 computation.

    ``pooled_compliance`` is exactly what every graduation surface computed
    before P12.14 (``1 - violation_rate(db)``). ``discipline`` is
    :func:`brain.journal.graduation_discipline`, which every surface reads now.
    """
    j = violation_rate(db)
    rate = j["violation_rate"]
    return {
        "journal": j,
        "pooled_compliance": (1.0 - rate) if rate is not None else None,
        "discipline": graduation_discipline(db),
    }


def case(title: str, fn) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = SignalDB(Path(d) / "probe.db")
        try:
            observed = fn(db)
        finally:
            db.close()
    expected = observed.get("expected_after_P12_14") or {}
    got = observed.get("discipline") or {}
    fixed = all(got.get(k) == v for k, v in expected.items())
    return {"case": title, "fixed": fixed, **observed}


# ── A. simulator journals satisfy graduation compliance ──────────────────
def case_simulator(db: SignalDB) -> dict:
    for i in range(20):
        sid = 9000 + i
        _decided_paper(db, sid, sim_key=f"BTCUSDT:15m:{i}:pullback:BUY")
        save_journal(db, sid, followed_rules=True)  # simulator auto-journals
    return {
        "real_canonical_trades": 0,
        **_compliance(db),
        "expected_after_P12_14": {"eligible": 0, "compliance": None},
    }


# ── B. non-canonical research journals move canonical compliance ─────────
def case_non_canonical(db: SignalDB) -> dict:
    _decided_paper(db, 9100, source_key=LIVE)
    save_journal(db, 9100, followed_rules=False)  # the one real trade: a violation
    for i in range(19):
        sid = 9200 + i
        _decided_paper(db, sid, source_key=RESEARCH)
        save_journal(db, sid, followed_rules=True)  # research book, perfect
    return {
        "canonical_reality": "1 real canonical trade, and it broke the rules",
        **_compliance(db),
        "expected_after_P12_14": {
            "eligible": 1,
            "journaled": 1,
            "violations": 1,
            "compliance": 0.0,
        },
    }


# ── C. followed_rules=None scores as full compliance ─────────────────────
def case_null_followed_rules(db: SignalDB) -> dict:
    _decided_paper(db, 9300, source_key=LIVE)
    save_journal(db, 9300, followed_rules=None, notes="no answer recorded")
    return {
        "recorded_followed_rules": db.get_journal(9300)["followed_rules"],
        **_compliance(db),
        "expected_after_P12_14": {
            "eligible": 1,
            "journaled": 0,
            "missing_journals": 1,
            "compliance": 0.0,
        },
    }


# ── D. missing journals fail open ────────────────────────────────────────
def case_missing_journals(db: SignalDB) -> dict:
    for i in range(30):  # 30 decided canonical real trades
        _decided_paper(db, 9400 + i, source_key=LIVE)
    save_journal(db, 9400, followed_rules=True)  # exactly one journaled
    return {
        "decided_canonical_real_trades": 30,
        "journaled": 1,
        **_compliance(db),
        "expected_after_P12_14": {
            "eligible": 30,
            "journaled": 1,
            "missing_journals": 29,
            "compliance": round(1 / 30, 4),
        },
    }


# ── E. control: a fully journaled canonical real book computes correctly ──
def case_control(db: SignalDB) -> dict:
    for i in range(10):
        sid = 9500 + i
        _decided_paper(db, sid, source_key=LIVE)
        save_journal(db, sid, followed_rules=(i != 0))  # 1 honest violation
    return {
        "decided_canonical_real_trades": 10,
        **_compliance(db),
        "expected_after_P12_14": {
            "eligible": 10,
            "journaled": 10,
            "violations": 1,
            "compliance": 0.9,
        },
    }


CASES = [
    ("A: simulator journals satisfy graduation compliance", case_simulator),
    (
        "B: non-canonical research journals inflate canonical compliance",
        case_non_canonical,
    ),
    ("C: followed_rules=None counts as compliant", case_null_followed_rules),
    ("D: missing journals fail open", case_missing_journals),
    ("E: control — fully journaled canonical real book", case_control),
]


def main() -> int:
    results = [case(t, f) for t, f in CASES]
    print(json.dumps(results, indent=2, sort_keys=False))
    print("\n" + "-" * 78)
    for r in results:
        d = r["discipline"]
        pooled = r["pooled_compliance"]
        print(
            f"{'PASS' if r['fixed'] else 'FAIL'}  {r['case']}\n"
            f"      pooled (pre-P12.14): {pooled}"
            f"   →   isolated: {d['compliance']}"
            f"   (eligible={d['eligible']}, journaled={d['journaled']},"
            f" missing={d['missing_journals']}, violations={d['violations']})"
        )
    ok = all(r["fixed"] for r in results)
    print("-" * 78)
    print("ALL CASES BEHAVE AS SPECIFIED" if ok else "SOME CASES STILL FAIL OPEN")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
