"""tests/test_m71_ops_watchdog_and_backup.py — Milestone 71 Automated Test Suite.

Verifies:
1. test_m71_healthy_ledger_passes_watchdog: Fresh shadow bar + healthy DB + ample disk
   returns HEALTHY with 0 active alerts and real_capital_enabled is False.
2. test_m71_missed_bar_triggers_alert_with_cooldown_and_recovery (Failure Injection):
   >5h missed bar triggers MISSED_BAR_ALERT, suppresses duplicate within 4h cooldown,
   and emits RECOVERED when a fresh bar arrives.
3. test_m71_corrupt_db_fails_closed (Failure Injection):
   Corrupted SQLite file triggers DB_INTEGRITY_ALERT (CRITICAL) without crashing.
4. test_m71_safe_sqlite_backup_and_retention_pruning:
   Backup creates a valid .db.gz that decompresses to a verified SQLite DB and prunes files beyond keep_days.
5. test_m71_api_cli_and_telegram_ops_en_bn:
   Verifies GET /api/desk/watchdog, main.py watchdog --check, and Telegram /ops (EN + BN).
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import app
from cli.daily import cmd_watchdog
from core.ops.p2_shadow_watchdog import (
    backup_shadow_ledger,
    get_backup_metadata,
    run_watchdog_check,
)
from core.strategies.p2_shadow_runner import init_shadow_db
from core.telegram.handlers import handle_ops, register_all_v5_commands
from core.telegram_bot import telegram_bot


def _create_test_ledger(db_path: Path, bar_age_hours: float = 1.0, stale_warning: int = 0) -> int:
    """Helper: Creates an isolated test shadow ledger with 1 bar of specified age."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    init_shadow_db(conn)

    now_utc = datetime.now(UTC)
    bar_dt = now_utc - timedelta(hours=bar_age_hours)
    bar_ts_utc = int(bar_dt.timestamp() * 1000)

    conn.execute(
        """
        INSERT INTO shadow_bars (
            bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
            equity_usd, cash_usd, bnh_equity_usd, gross_exposure, s1_weight, s2_weight, stale_warning
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bar_ts_utc,
            bar_dt.isoformat(),
            "PARQUET_TEST",
            "MIXED",
            "HOLD",
            10050.0,
            5000.0,
            10010.0,
            0.5,
            0.25,
            0.25,
            stale_warning,
        ),
    )
    conn.commit()
    conn.close()
    return bar_ts_utc


# ==============================================================================
# TEST 1: Healthy Ledger Passes Watchdog
# ==============================================================================
def test_m71_healthy_ledger_passes_watchdog(tmp_path):
    """Fresh shadow bar + healthy DB + ample disk returns HEALTHY with 0 active alerts."""
    db_path = tmp_path / "shadow_healthy.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    bar_ts = _create_test_ledger(db_path, bar_age_hours=1.5, stale_warning=0)
    now_utc = datetime.now(UTC)

    report = run_watchdog_check(
        db_path=db_path,
        backup_dir=backup_dir,
        state_path=state_path,
        now_utc=now_utc,
        auto_backup=True,
    )

    assert report.status == "HEALTHY"
    assert len(report.active_alerts) == 0
    assert report.db_integrity is True
    assert report.last_bar_ts_utc == bar_ts
    assert report.last_bar_age_hours is not None
    assert 1.0 <= report.last_bar_age_hours <= 2.0
    assert report.real_capital_enabled is False
    assert report.capital_mode == "TIER_0_PAPER"
    assert report.backup_count == 1
    assert report.last_backup_file is not None
    assert report.last_backup_file.endswith(".db.gz")


# ==============================================================================
# TEST 2: Missed Bar Triggers Alert with 4h Cooldown and Auto-Recovery
# ==============================================================================
def test_m71_missed_bar_triggers_alert_with_cooldown_and_recovery(tmp_path):
    """Failure Injection: >5h missed bar triggers MISSED_BAR_ALERT, suppresses duplicate

    within 4h cooldown, and emits RECOVERED when a fresh bar arrives.
    """
    db_path = tmp_path / "shadow_missed.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    t0 = datetime(2026, 11, 20, 0, 0, 0, tzinfo=UTC)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    init_shadow_db(conn)
    t0_bar_ts = int(t0.timestamp() * 1000)
    conn.execute(
        """
        INSERT INTO shadow_bars (
            bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
            equity_usd, cash_usd, bnh_equity_usd, gross_exposure, s1_weight, s2_weight, stale_warning
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t0_bar_ts,
            t0.isoformat(),
            "PARQUET_TEST",
            "MIXED",
            "HOLD",
            10000.0,
            10000.0,
            10000.0,
            0.0,
            0.0,
            0.0,
            0,
        ),
    )
    conn.commit()
    conn.close()

    notified: list[Any] = []

    # Step A: At t0 + 6.0h (> 5.0h threshold), evaluate watchdog
    now_step_a = t0 + timedelta(hours=6, minutes=10)
    report_a = run_watchdog_check(
        db_path=db_path,
        backup_dir=backup_dir,
        state_path=state_path,
        now_utc=now_step_a,
        notify_callback=notified.append,
        auto_backup=False,
    )

    assert report_a.status == "DEGRADED"
    assert any(a.code == "MISSED_BAR_ALERT" for a in report_a.active_alerts)
    assert len(notified) == 1
    assert notified[0]["code"] == "MISSED_BAR_ALERT"
    assert notified[0]["event_type"] == "ALERT"

    # Step B: At t0 + 7.0h (1h after notification, within 4h cooldown), evaluate again
    now_step_b = t0 + timedelta(hours=7, minutes=10)
    report_b = run_watchdog_check(
        db_path=db_path,
        backup_dir=backup_dir,
        state_path=state_path,
        now_utc=now_step_b,
        notify_callback=notified.append,
        auto_backup=False,
    )

    assert report_b.status == "DEGRADED"
    # Duplicate alert must be suppressed by 4h cooldown
    assert len(notified) == 1

    # Step C: Recovery — a fresh bar arrives at t0 + 7.5h
    conn = sqlite3.connect(db_path)
    fresh_ts = int((t0 + timedelta(hours=7, minutes=30)).timestamp() * 1000)
    conn.execute(
        """
        INSERT INTO shadow_bars (
            bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
            equity_usd, cash_usd, bnh_equity_usd, gross_exposure, s1_weight, s2_weight, stale_warning
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fresh_ts,
            (t0 + timedelta(hours=7, minutes=30)).isoformat(),
            "PARQUET_TEST",
            "MIXED",
            "HOLD",
            10010.0,
            10010.0,
            10005.0,
            0.0,
            0.0,
            0.0,
            0,
        ),
    )
    conn.commit()
    conn.close()

    now_step_c = t0 + timedelta(hours=8, minutes=0)  # fresh bar is 0.5h old
    report_c = run_watchdog_check(
        db_path=db_path,
        backup_dir=backup_dir,
        state_path=state_path,
        now_utc=now_step_c,
        notify_callback=notified.append,
        auto_backup=False,
    )

    assert report_c.status == "HEALTHY"
    assert len(report_c.active_alerts) == 0
    # Auto-recovery notification must be triggered
    assert len(notified) == 2
    assert notified[1]["event_type"] == "RECOVERY"
    assert notified[1]["code"] == "OPS_RECOVERED"


# ==============================================================================
# TEST 3: Corrupt DB Fails Closed
# ==============================================================================
def test_m71_corrupt_db_fails_closed(tmp_path):
    """Failure Injection: Corrupted SQLite file triggers DB_INTEGRITY_ALERT (CRITICAL)."""
    db_path = tmp_path / "corrupted_shadow.db"
    backup_dir = tmp_path / "backups"
    state_path = tmp_path / "watchdog_state.json"

    # Write corrupt non-SQLite bytes
    db_path.write_bytes(b"INVALID_HEADER_GARBAGE_PAYLOAD_NOT_A_SQLITE_DATABASE_123456789")

    report = run_watchdog_check(
        db_path=db_path,
        backup_dir=backup_dir,
        state_path=state_path,
        auto_backup=False,
    )

    assert report.status == "CRITICAL"
    assert report.db_integrity is False
    assert any(a.code == "DB_INTEGRITY_ALERT" for a in report.active_alerts)
    assert report.real_capital_enabled is False
    assert report.capital_mode == "TIER_0_PAPER"


# ==============================================================================
# TEST 4: Safe SQLite Backup and Retention Pruning
# ==============================================================================
def test_m71_safe_sqlite_backup_and_retention_pruning(tmp_path):
    """Backup creates a valid .db.gz that decompresses to a verified SQLite DB and prunes."""
    db_path = tmp_path / "shadow_backup_src.db"
    backup_dir = tmp_path / "backups"

    _create_test_ledger(db_path, bar_age_hours=0.5, stale_warning=0)

    backup_time = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)
    gz_file = backup_shadow_ledger(
        db_path=db_path,
        backup_dir=backup_dir,
        keep_days=3,
        now_utc=backup_time,
    )

    assert gz_file is not None
    assert gz_file.exists()
    assert gz_file.name == "p2_shadow_ledger_20261120.db.gz"

    # Decompress and verify SQLite PRAGMA integrity_check
    restored_db_path = tmp_path / "restored.db"
    with gzip.open(gz_file, "rb") as f_in, open(restored_db_path, "wb") as f_out:
        f_out.write(f_in.read())

    chk_conn = sqlite3.connect(restored_db_path)
    res = chk_conn.execute("PRAGMA integrity_check").fetchone()
    assert res is not None and str(res[0]).lower() == "ok"
    count = chk_conn.execute("SELECT COUNT(*) FROM shadow_bars").fetchone()[0]
    assert count == 1
    chk_conn.close()

    # Test retention pruning: create 5 older mock backup archives
    for day in range(1, 6):
        old_gz = backup_dir / f"p2_shadow_ledger_2026110{day}.db.gz"
        with gzip.open(old_gz, "wb") as f_gz:
            f_gz.write(b"MOCK_SQLITE_COMPRESSED_DATA")

    # Run backup with keep_days=3
    backup_shadow_ledger(
        db_path=db_path,
        backup_dir=backup_dir,
        keep_days=3,
        now_utc=backup_time,
    )

    remaining_backups = sorted(backup_dir.glob("p2_shadow_ledger_*.db.gz"))
    assert len(remaining_backups) == 3
    # Check get_backup_metadata
    last_file, last_at, count_backups = get_backup_metadata(backup_dir)
    assert count_backups == 3
    assert last_file is not None


# ==============================================================================
# TEST 5: API, CLI, and Telegram Ops EN/BN
# ==============================================================================
def test_m71_api_cli_and_telegram_ops_en_bn():
    """Verifies GET /api/desk/watchdog, main.py watchdog --check, and Telegram /ops."""
    # 1. FastAPI Endpoint Test
    client = TestClient(app)
    res = client.get("/api/desk/watchdog")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["capital_mode"] == "TIER_0_PAPER"
    assert data["real_capital_enabled"] is False
    assert "db_integrity" in data
    assert "disk_free_mb" in data
    assert isinstance(data["active_alerts"], list)

    # 2. CLI Test (JSON and Bengali text output)
    args_json = argparse.Namespace(check=True, backup=False, json=True, lang="en")
    buf_json = io.StringIO()
    orig_stdout = sys.stdout
    try:
        sys.stdout = buf_json
        cmd_watchdog(args_json)
    finally:
        sys.stdout = orig_stdout
    cli_json = json.loads(buf_json.getvalue())
    assert "status" in cli_json
    assert cli_json["real_capital_enabled"] is False

    args_bn = argparse.Namespace(check=True, backup=False, json=False, lang="bn")
    buf_bn = io.StringIO()
    try:
        sys.stdout = buf_bn
        cmd_watchdog(args_bn)
    finally:
        sys.stdout = orig_stdout
    out_bn = buf_bn.getvalue()
    assert "CBT ২৪/৭ অপস ওয়াচডগ হেলথ রিপোর্ট" in out_bn
    assert "স্ট্যাটাস" in out_bn

    # 3. Telegram /ops and Natural Language Trigger Test
    register_all_v5_commands()

    # Typed handler in English
    en_msg = asyncio.run(handle_ops(args="en"))
    assert "CBT 24/7 OPS WATCHDOG REPORT" in en_msg
    assert "TIER_0_PAPER" in en_msg

    # Typed handler in Bengali
    bn_msg = asyncio.run(handle_ops(args="bn"))
    assert "CBT ২৪/৭ অপস ওয়াচডগ হেলথ রিপোর্ট" in bn_msg
    assert "নিষ্ক্রিয়" in bn_msg

    # Natural Language Telegram Trigger
    update = {
        "update_id": 9991,
        "message": {
            "text": "সিস্টেম চেক",
            "chat": {"id": 12345},
            "from": {"id": 12345, "first_name": "Trader"},
        },
    }
    bot_res = asyncio.run(telegram_bot.handle_webhook_update(update))
    assert bot_res.get("status") == "EXECUTED"
    assert bot_res.get("command") == "/ops"
