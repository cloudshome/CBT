"""Read-only review probe for P12.16 — open-book source isolation.

P12.11 → P12.15 walked the source boundary through every surface that reads
**decided** paper trades: calibration and setup-proof (P12.11), the global
graduation gate (P12.13), the discipline criterion (P12.14), and finally every
live *risk control* plus the scorecard execution metric (P12.15 / v2.23.4).

That work stopped at the closed book. The **open** book — the positions the
desk is carrying *right now* — was never isolated. ``open_exposure()`` and
``active_paper_trades()`` select on ``status IN ('WAITING_ENTRY','OPEN')`` with
no ``sim_key`` filter and no ``source_key`` filter, so:

  A. **portfolio veto fails CLOSED**: a research-book (e.g.
     ``dukascopy:spot:bid``) position occupies a slot in the live crypto risk
     bucket, so the correlated-exposure veto blocks a real live trade the desk
     is entitled to take — research must neither unlock nor block (P12.13).
  B. **the bucket risk cap fails CLOSED** the same way: research positions
     consume ``MAX_CRYPTO_EXPOSURE_RISK_PCT``.
  C. **an interrupted simulator run leaks live exposure**: simulator rows are
     inserted ``status='OPEN'`` before being closed in the same pass, so a
     crash/interrupt leaves ``sim_key IS NOT NULL`` rows that read as live
     positions forever — machine walk-forward samples holding real risk slots.
  D. **the paper runner polls research/simulator rows as live work**: it
     fetches candles for them from the *canonical live* client and can open,
     close and journal them onto the live book under a research source key.
  E. **desk/briefing counts overstate the book**: "open exposure N" and the
     paper stats card mix research and simulator rows into the live count.
  F. **control**: a canonical-only open book must read exactly as before,
     including legacy NULL-provenance rows (P12.11 convention).

Each case is built in a throwaway SQLite database and measured through the
real surfaces (``SignalDB.open_exposure`` / ``active_paper_trades`` /
``live_open_rows``, ``brain.portfolio.portfolio_veto`` / ``bucket_state``).
It exits non-zero if any case is not answered as specified.

The probe writes nothing to the repository, never touches a real store, and
places no orders. Run:

    .venv/bin/python ops/probes/p12_16_openbook_probe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from brain.portfolio import bucket_state, portfolio_veto
from data.database import SignalDB

LIVE = ""  # canonical Binance spot source key
RESEARCH = "dukascopy:spot:bid"  # research-only book (XAU import)


def _open_paper(
    db: SignalDB,
    scan_id: int,
    *,
    symbol: str = "BTCUSDT",
    action: str = "BUY",
    status: str = "OPEN",
    sim_key: str | None = None,
    source_key: str | None = LIVE,
) -> None:
    """Insert one ACTIVE (WAITING_ENTRY/OPEN) paper trade with provenance."""
    ts = int(time.time() * 1000)
    db.conn.execute(
        """INSERT INTO scans(id, signal_id, ts, symbol, timeframe, action, entry,
                             stop_loss, take_profit, risk_reward, status, lifecycle_ts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"SIG{scan_id}",
            ts,
            symbol,
            "15m",
            action,
            100.0,
            99.0,
            102.0,
            2.0,
            "EXECUTED",
            ts,
        ),
    )
    db.conn.execute(
        """INSERT INTO paper_trades(scan_id, signal_id, plan_type, symbol, timeframe,
                                    action, entry, stop_loss, take_profit, risk_reward,
                                    confidence_pct, status, created_ts, opened_ts,
                                    entry_price, sim_key, source_key)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id,
            f"SIG{scan_id}",
            "Buy Pullback",
            symbol,
            "15m",
            action,
            100.0,
            99.0,
            102.0,
            2.0,
            70,
            status,
            ts,
            ts if status == "OPEN" else None,
            100.0 if status == "OPEN" else None,
            sim_key,
            source_key,
        ),
    )
    db.conn.commit()


def _pooled_open(db: SignalDB) -> int:
    """Exactly what open_exposure() counted before P12.16 (no filters)."""
    return len(
        db.conn.execute(
            "SELECT id FROM paper_trades WHERE status IN ('WAITING_ENTRY','OPEN')"
        ).fetchall()
    )


def case(title: str, fn) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = SignalDB(Path(d) / "probe.db")
        try:
            observed = fn(db)
        finally:
            db.close()
    expected = observed.pop("expected_after_P12_16")
    got = observed.get("observed") or {}
    fixed = all(got.get(k) == v for k, v in expected.items())
    return {"case": title, "fixed": fixed, "expected": expected, **observed}


# ── A. portfolio veto: a research position blocks a real live trade ───────
def case_research_blocks_live(db: SignalDB) -> dict:
    _open_paper(db, 1, symbol="BTCUSDT", action="BUY", source_key=RESEARCH)
    veto = portfolio_veto(db, "BTCUSDT", "BUY")
    return {
        "canonical_reality": "the live crypto bucket is FLAT — "
        "the only open row is a research import",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 1 → vetoed
        "observed": {
            "allowed": veto["allowed"],
            "n_open": veto["exposure"]["n_open"],
            "reasons": len(veto["reasons"]),
        },
        "expected_after_P12_16": {"allowed": True, "n_open": 0, "reasons": 0},
    }


# ── B. bucket risk cap: research positions must not consume live capacity ─
def case_research_fills_bucket(db: SignalDB) -> dict:
    _open_paper(db, 10, symbol="BTCUSDT", action="BUY", source_key=RESEARCH)
    _open_paper(db, 11, symbol="ETHUSDT", action="SELL", source_key=RESEARCH)
    state = bucket_state(db, "BTCUSDT")
    veto = portfolio_veto(db, "BTCUSDT", "SELL")
    return {
        "canonical_reality": "2 research positions, 0 live — the live "
        "bucket is neither full nor at its risk cap",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 2 → bucket full
        "observed": {
            "n_open": state.n_open,
            "planned_risk_pct": state.planned_risk_pct,
            "allowed": veto["allowed"],
        },
        "expected_after_P12_16": {
            "n_open": 0,
            "planned_risk_pct": 0.0,
            "allowed": True,
        },
    }


# ── C. an interrupted simulator run must not hold live risk slots ─────────
def case_simulator_leak(db: SignalDB) -> dict:
    for i in range(2):
        _open_paper(
            db,
            20 + i,
            symbol="BTCUSDT",
            action="BUY",
            sim_key=f"BTCUSDT:15m:{i}:Buy Pullback:BUY",
        )
    veto = portfolio_veto(db, "BTCUSDT", "BUY")
    return {
        "canonical_reality": "2 orphaned simulator samples (sim_key set) "
        "from an interrupted walk-forward run",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 2 → vetoed
        "observed": {
            "live_open": len(db.live_open_rows()),
            "allowed": veto["allowed"],
            "n_open": veto["exposure"]["n_open"],
        },
        "expected_after_P12_16": {"live_open": 0, "allowed": True, "n_open": 0},
    }


# ── D. the runner must not poll research/simulator rows as live work ──────
def case_runner_population(db: SignalDB) -> dict:
    _open_paper(db, 30, symbol="BTCUSDT", action="BUY", source_key=LIVE)
    _open_paper(db, 31, symbol="XAUUSD", action="SELL", source_key=RESEARCH)
    _open_paper(
        db,
        32,
        symbol="BTCUSDT",
        action="SELL",
        sim_key="BTCUSDT:15m:9:Buy Pullback:SELL",
    )
    active = db.active_paper_trades()
    return {
        "canonical_reality": "only scan #30 is a real live position; the "
        "runner fetches canonical live candles",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 3 → all polled
        "observed": {
            "n_polled": len(active),
            "scan_ids": sorted(int(t["scan_id"]) for t in active),
        },
        "expected_after_P12_16": {"n_polled": 1, "scan_ids": [30]},
    }


# ── E. desk/briefing exposure counts must report the live book ────────────
def case_reported_counts(db: SignalDB) -> dict:
    _open_paper(db, 40, symbol="BTCUSDT", action="BUY", source_key=LIVE)
    for i in range(4):
        _open_paper(db, 41 + i, symbol="XAUUSD", action="BUY", source_key=RESEARCH)
    _open_paper(db, 50, symbol="ETHUSDT", action="BUY", sim_key="ETHUSDT:15m:3:Buy Pullback:BUY")
    return {
        "canonical_reality": "the desk carries exactly 1 live position",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 6 → overstated
        "observed": {
            "open_exposure": len(db.open_exposure()),
            "live_open_rows": len(db.live_open_rows()),
        },
        "expected_after_P12_16": {"open_exposure": 1, "live_open_rows": 1},
    }


# ── F. control: canonical-only + legacy NULL provenance are unchanged ─────
def case_control(db: SignalDB) -> dict:
    _open_paper(db, 60, symbol="BTCUSDT", action="BUY", source_key=LIVE)
    _open_paper(
        db, 61, symbol="ETHUSDT", action="SELL", source_key=None, status="WAITING_ENTRY"
    )  # legacy NULL provenance
    state = bucket_state(db, "BTCUSDT")
    veto = portfolio_veto(db, "BTCUSDT", "BUY")
    return {
        "canonical_reality": "2 genuine live rows (one legacy NULL) — the "
        "bucket IS full and the duplicate IS vetoed",
        "pooled_open_pre_P12_16": _pooled_open(db),  # 2 → same
        "observed": {
            "n_open": state.n_open,
            "allowed": veto["allowed"],
            "live_open_rows": len(db.live_open_rows()),
        },
        "expected_after_P12_16": {"n_open": 2, "allowed": False, "live_open_rows": 2},
    }


CASES = [
    (
        "A. research position blocks a real live trade (veto fails CLOSED)",
        case_research_blocks_live,
    ),
    (
        "B. research positions consume the live bucket's risk cap",
        case_research_fills_bucket,
    ),
    ("C. orphaned simulator rows hold live risk slots", case_simulator_leak),
    (
        "D. the paper runner polls research/simulator rows as live work",
        case_runner_population,
    ),
    ("E. reported open exposure overstates the live book", case_reported_counts),
    ("F. control: canonical-only book (incl. legacy NULL) is unchanged", case_control),
]


def main() -> int:
    results = [case(title, fn) for title, fn in CASES]
    print(
        json.dumps(
            {
                "probe": "P12.16 open-book source isolation",
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
