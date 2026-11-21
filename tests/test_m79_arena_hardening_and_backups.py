"""tests/test_m79_arena_hardening_and_backups.py — Milestone 79 Hardening & Telemetry Tests.

Verifies:
1. test_m79_forward_bnh_telemetry_anchoring:
   - Forward BnH equity is anchored strictly to $10,000.00 at first_bar_ts.
   - Rejects multi-year cumulative figures (e.g. > $30,000 or historical 2020 prices).
   - Returns 0.00% / $10,000.00 when < 2 bars or timestamps invalid.
2. test_m79_arena_independent_days_and_proof_progress:
   - Champion and Challenger compute days_tracked and proof_progress_pct independently.
   - days_tracked is 0.0 when bars_ticked <= 1.
   - Strict read-only isolation (?mode=ro): Champion DB is never modified.
3. test_m79_watchdog_challenger_db_integrity_failure_injection:
   - Corrupt Challenger SQLite DB triggers CHALLENGER_DB_INTEGRITY_ALERT (CRITICAL).
   - Fails-closed without crashing.
4. test_m79_watchdog_challenger_missed_bar_and_cooldown:
   - Challenger bar age > 5.0h triggers CHALLENGER_MISSED_BAR_ALERT (DEGRADED).
   - 4-hour anti-spam cooldown prevents duplicate notifications.
5. test_m79_watchdog_challenger_safe_backup_and_retention:
   - Creates verified .db.gz archive for Challenger ledger.
   - Prunes older archives beyond keep_days.
6. test_m79_watchdog_backward_compatibility_uninitialized:
   - Uninitialized Challenger DB sets challenger_status="NOT_INITIALIZED" cleanly.
7. test_m79_constitutional_governance_locks:
   - REAL_CAPITAL_ENABLED is False and CAPITAL_MODE == "TIER_0_PAPER" across modules.
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.ops.p2_shadow_watchdog as watchdog  # noqa: E402
import core.strategies.v2b_challenger_shadow as challenger  # noqa: E402
from core.ops.p2_shadow_watchdog import (  # noqa: E402
    backup_shadow_ledger,
    get_backup_metadata,
    run_watchdog_check,
)
from core.strategies.p2_risk_parity import UNIVERSE  # noqa: E402
from core.strategies.p2_shadow_runner import init_shadow_db  # noqa: E402
from core.strategies.v2b_challenger_shadow import (  # noqa: E402
    compute_forward_bnh_telemetry,
    get_arena_comparison,
    init_challenger_db,
)


def _create_mock_challenger_ledger(
    db_path: Path,
    n_bars: int = 1,
    bar_age_hours: float = 1.0,
    equity: float = 10050.0,
) -> list[int]:
    """Helper: Creates an isolated test Challenger ledger with specified bars."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    init_challenger_db(conn)

    now_utc = datetime.now(UTC)
    ts_list = []
    step_ms = 4 * 3600 * 1000

    end_dt = now_utc - timedelta(hours=bar_age_hours)
    end_ts = int(end_dt.timestamp() * 1000)

    for i in range(n_bars):
        bar_ts = end_ts - (n_bars - 1 - i) * step_ms
        ts_list.append(bar_ts)
        bar_dt = datetime.fromtimestamp(bar_ts / 1000.0, tz=UTC)
        conn.execute(
            """
            INSERT INTO shadow_bars (
                bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
                equity_usd, cash_usd, bnh_equity_usd, gross_exposure,
                s1_weight, h5_weight, h1_weight, pvt_scalar, stale_warning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bar_ts,
                bar_dt.isoformat(),
                "PARQUET_TEST",
                "MIXED",
                "HOLD",
                equity,
                5000.0,
                10000.0,
                0.5,
                0.33,
                0.33,
                0.33,
                1.0,
                0,
            ),
        )

    conn.commit()
    conn.close()
    return ts_list


def _create_mock_champion_ledger(
    db_path: Path,
    n_bars: int = 1,
    bar_age_hours: float = 1.0,
    equity: float = 10020.0,
) -> list[int]:
    """Helper: Creates an isolated test Champion ledger."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    init_shadow_db(conn)

    now_utc = datetime.now(UTC)
    ts_list = []
    step_ms = 4 * 3600 * 1000

    end_dt = now_utc - timedelta(hours=bar_age_hours)
    end_ts = int(end_dt.timestamp() * 1000)

    for i in range(n_bars):
        bar_ts = end_ts - (n_bars - 1 - i) * step_ms
        ts_list.append(bar_ts)
        bar_dt = datetime.fromtimestamp(bar_ts / 1000.0, tz=UTC)
        conn.execute(
            """
            INSERT INTO shadow_bars (
                bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
                equity_usd, cash_usd, bnh_equity_usd, gross_exposure,
                s1_weight, s2_weight, stale_warning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bar_ts,
                bar_dt.isoformat(),
                "PARQUET_TEST",
                "MIXED",
                "HOLD",
                equity,
                5000.0,
                10000.0,
                0.5,
                0.25,
                0.25,
                0,
            ),
        )

    conn.commit()
    conn.close()
    return ts_list


# ==============================================================================
# TEST 1: Forward BnH Telemetry Anchoring
# ==============================================================================
def test_m79_forward_bnh_telemetry_anchoring():
    """Verify BnH telemetry is strictly anchored to $10,000.00 and rejects historical distortion."""
    t0 = 1770000000000
    t1 = t0 + 4 * 3600 * 1000

    # 1. Invalid or < 2 bars
    eq, ret = compute_forward_bnh_telemetry(None, None)
    assert eq == 10000.0
    assert ret == 0.0

    eq, ret = compute_forward_bnh_telemetry(t0, t0)
    assert eq == 10000.0
    assert ret == 0.0

    eq, ret = compute_forward_bnh_telemetry(t1, t0)
    assert eq == 10000.0
    assert ret == 0.0

    # 2. Candle mock with +5% return across all 4 assets
    mock_candles = {}
    for s in UNIVERSE:
        df = pd.DataFrame({
            "ts": [t0, t1],
            "open": [100.0, 105.0],
            "high": [106.0, 106.0],
            "low": [99.0, 104.0],
            "close": [100.0, 105.0],  # +5%
            "volume": [10.0, 10.0],
        })
        mock_candles[s] = df

    eq, ret = compute_forward_bnh_telemetry(t0, t1, candles_by_symbol=mock_candles)
    assert eq == 10500.0
    assert ret == 5.0

    # 3. Reject multi-year cumulative figure (> $30,000)
    eq_distorted, ret_distorted = compute_forward_bnh_telemetry(
        t0, t1, fallback_bnh_equity=111730.0, candles_by_symbol={}
    )
    assert eq_distorted == 10000.0
    assert ret_distorted == 0.0


# ==============================================================================
# TEST 2: Independent Days Tracked & Proof Progress
# ==============================================================================
def test_m79_arena_independent_days_and_proof_progress(tmp_path: Path):
    """Verify Champion and Challenger compute days_tracked and progress independently with read-only isolation."""
    champ_db = tmp_path / "champ.db"
    chall_db = tmp_path / "chall.db"

    # Champion has 13 bars (2 days: 12 * 4h = 48h)
    _create_mock_champion_ledger(champ_db, n_bars=13, bar_age_hours=1.0)
    # Challenger has 1 bar (0 days)
    _create_mock_challenger_ledger(chall_db, n_bars=1, bar_age_hours=1.0)

    res = get_arena_comparison(champion_db_path=champ_db, challenger_db_path=chall_db)

    # Independent days and progress
    assert res["champion_proof_days"] == 2.0
    assert res["challenger_proof_days"] == 0.0
    assert res["champion_proof_progress_pct"] == round((2.0 / 60.0) * 100.0, 1)
    assert res["challenger_proof_progress_pct"] == 0.0

    # Overall proof days is min(champ, chall)
    assert res["proof_days_elapsed"] == 0.0
    assert res["proof_progress_pct"] == 0.0

    # Verify Champion DB was accessed read-only (zero schema or data mutation)
    conn = sqlite3.connect(champ_db)
    cur = conn.cursor()
    cnt = cur.execute("SELECT COUNT(*) FROM shadow_bars").fetchone()[0]
    conn.close()
    assert cnt == 13


# ==============================================================================
# TEST 3: Challenger SQLite Integrity Failure Injection
# ==============================================================================
def test_m79_watchdog_challenger_db_integrity_failure_injection(tmp_path: Path):
    """Corrupt Challenger SQLite DB triggers CHALLENGER_DB_INTEGRITY_ALERT (CRITICAL) without crashing."""
    champ_db = tmp_path / "champ.db"
    chall_db = tmp_path / "chall_corrupt.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    _create_mock_champion_ledger(champ_db, n_bars=2, bar_age_hours=1.0)

    # Create corrupt file
    chall_db.parent.mkdir(parents=True, exist_ok=True)
    with open(chall_db, "wb") as f:
        f.write(b"CORRUPTED_SQLITE_GARBAGE_HEADER_DATA_1234567890")

    notifications = []

    def _notify(payload: Any) -> None:
        notifications.append(payload)

    report = run_watchdog_check(
        db_path=champ_db,
        backup_dir=backup_dir,
        state_path=state_path,
        challenger_db_path=chall_db,
        auto_backup=False,
        notify_callback=_notify,
    )

    assert report.challenger_status == "CRITICAL"
    assert report.challenger_db_integrity is False
    assert any(a.code == "CHALLENGER_DB_INTEGRITY_ALERT" for a in report.active_alerts)
    assert any(n["code"] == "CHALLENGER_DB_INTEGRITY_ALERT" for n in notifications)


# ==============================================================================
# TEST 4: Challenger Missed Bar Alert & 4h Cooldown
# ==============================================================================
def test_m79_watchdog_challenger_missed_bar_and_cooldown(tmp_path: Path):
    """Challenger bar age > 5.0h triggers alert and respects 4h anti-spam cooldown."""
    champ_db = tmp_path / "champ.db"
    chall_db = tmp_path / "chall_stale.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    # Champion is fresh (1h)
    _create_mock_champion_ledger(champ_db, n_bars=2, bar_age_hours=1.0)
    # Challenger is missed/stale (6.5h > 5.0h)
    _create_mock_challenger_ledger(chall_db, n_bars=2, bar_age_hours=6.5)

    notifications: list[Any] = []

    def _notify(payload: Any) -> None:
        notifications.append(payload)

    now1 = datetime.now(UTC)
    report1 = run_watchdog_check(
        db_path=champ_db,
        backup_dir=backup_dir,
        state_path=state_path,
        challenger_db_path=chall_db,
        now_utc=now1,
        auto_backup=False,
        notify_callback=_notify,
    )

    assert report1.challenger_status == "DEGRADED"
    assert report1.challenger_last_bar_age_hours is not None
    assert report1.challenger_last_bar_age_hours >= 6.0
    assert any(a.code == "CHALLENGER_MISSED_BAR_ALERT" for a in report1.active_alerts)
    assert len(notifications) == 1
    assert notifications[0]["code"] == "CHALLENGER_MISSED_BAR_ALERT"

    # Run again 30 minutes later (within 4h cooldown): notification must be suppressed
    now2 = now1 + timedelta(minutes=30)
    notifications.clear()

    report2 = run_watchdog_check(
        db_path=champ_db,
        backup_dir=backup_dir,
        state_path=state_path,
        challenger_db_path=chall_db,
        now_utc=now2,
        auto_backup=False,
        notify_callback=_notify,
    )

    assert report2.challenger_status == "DEGRADED"
    # Alert is active in report
    assert any(a.code == "CHALLENGER_MISSED_BAR_ALERT" for a in report2.active_alerts)
    # But notification is suppressed by cooldown
    assert len(notifications) == 0


# ==============================================================================
# TEST 5: Challenger Safe SQLite Backup & Retention Pruning
# ==============================================================================
def test_m79_watchdog_challenger_safe_backup_and_retention(tmp_path: Path):
    """Verify Challenger ledger backup creates verified .db.gz and prunes past keep_days."""
    chall_db = tmp_path / "v2b_challenger_shadow_ledger.db"
    backup_dir = tmp_path / "backups"

    _create_mock_challenger_ledger(chall_db, n_bars=5, bar_age_hours=1.0)

    now_base = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)

    # Create 3 daily backups
    for i in range(3):
        cur_date = now_base + timedelta(days=i)
        gz_path = backup_shadow_ledger(
            db_path=chall_db,
            backup_dir=backup_dir,
            keep_days=2,  # Retain at most 2
            now_utc=cur_date,
            prefix="v2b_challenger_shadow_ledger",
        )
        assert gz_path is not None and gz_path.exists()

    # Metadata check
    _, _, count = get_backup_metadata(backup_dir, prefix="v2b_challenger_shadow_ledger")
    assert count == 2, f"Expected 2 backups retained after pruning, found {count}"

    # Verify decompressed DB integrity
    latest_gz = sorted(backup_dir.glob("v2b_challenger_shadow_ledger_*.db.gz"))[-1]
    with gzip.open(latest_gz, "rb") as f_in:
        decompressed_data = f_in.read()

    decomp_path = tmp_path / "decompressed_chall.db"
    with open(decomp_path, "wb") as f_out:
        f_out.write(decompressed_data)

    chk_conn = sqlite3.connect(decomp_path)
    res = chk_conn.execute("PRAGMA integrity_check").fetchone()
    bar_cnt = chk_conn.execute("SELECT COUNT(*) FROM shadow_bars").fetchone()[0]
    chk_conn.close()

    assert res[0].lower() == "ok"
    assert bar_cnt == 5


# ==============================================================================
# TEST 6: Backward Compatibility When Challenger Uninitialized
# ==============================================================================
def test_m79_watchdog_backward_compatibility_uninitialized(tmp_path: Path):
    """Verify run_watchdog_check works cleanly without crashing when Challenger DB is uninitialized."""
    champ_db = tmp_path / "champ.db"
    missing_chall_db = tmp_path / "nonexistent_chall.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    _create_mock_champion_ledger(champ_db, n_bars=2, bar_age_hours=1.0)

    report = run_watchdog_check(
        db_path=champ_db,
        backup_dir=backup_dir,
        state_path=state_path,
        challenger_db_path=missing_chall_db,
        auto_backup=False,
    )

    assert report.status == "HEALTHY"
    assert report.challenger_status == "NOT_INITIALIZED"
    assert report.challenger_db_integrity is True
    assert report.challenger_last_bar_age_hours is None


# ==============================================================================
# TEST 7: Constitutional Governance Locks
# ==============================================================================
def test_m79_constitutional_governance_locks():
    """Verify non-negotiable capital safety and tier 0 locks across modules."""
    assert challenger.REAL_CAPITAL_ENABLED is False
    assert challenger.CAPITAL_MODE == "TIER_0_PAPER"
    assert watchdog.REAL_CAPITAL_ENABLED is False
    assert watchdog.CAPITAL_MODE == "TIER_0_PAPER"
