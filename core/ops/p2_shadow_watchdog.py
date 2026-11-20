"""core/ops/p2_shadow_watchdog.py — 24/7 CBT Ops Watchdog & Automated Ledger Backup.

Milestone 71: Operational resilience, automated SQLite ledger backup,
disk space monitoring, missed 4h bar alerting, and anti-spam Telegram alarms.

Constitutional Invariants:
1. REAL_CAPITAL_ENABLED = False (locked).
2. CapitalGovernor = "TIER_0_PAPER" (locked).
3. Zero-bypass risk audit: Fail-closed on database corruption or missing feeds.
"""

from __future__ import annotations

import gzip
import json
import logging
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.core.ops.p2_shadow_watchdog")

# Constitutional Locks
CAPITAL_MODE: str = "TIER_0_PAPER"
REAL_CAPITAL_ENABLED: bool = False
DEFAULT_MAX_BAR_AGE_HOURS: float = 5.0
DEFAULT_MIN_DISK_MB: float = 500.0
ALERT_COOLDOWN_SECONDS: float = 4.0 * 3600.0  # 4 hours


@dataclass
class WatchdogAlert:
    """Individual operational alarm event."""
    code: str
    severity: str  # "DEGRADED" | "CRITICAL" | "INFO"
    message_en: str
    message_bn: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message_en": self.message_en,
            "message_bn": self.message_bn,
        }

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class WatchdogNotification:
    """Notification payload sent to notify_callback."""
    def __init__(
        self,
        event_type: str,  # "ALERT" | "RECOVERY"
        code: str,
        severity: str,
        message_en: str,
        message_bn: str,
    ):
        self.event_type = event_type
        self.code = code
        self.severity = severity
        self.message_en = message_en
        self.message_bn = message_bn

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message_en}"

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "code": self.code,
            "severity": self.severity,
            "message_en": self.message_en,
            "message_bn": self.message_bn,
        }


@dataclass
class WatchdogReport:
    """Full operational health report for CBT shadow desk."""
    status: str  # "HEALTHY" | "DEGRADED" | "CRITICAL" | "NOT_INITIALIZED"
    checked_at_utc: str
    last_bar_ts_utc: int | None
    last_bar_age_hours: float | None
    db_integrity: bool
    disk_free_mb: float
    last_backup_file: str | None
    last_backup_at_utc: str | None
    backup_count: int
    active_alerts: list[WatchdogAlert]
    capital_mode: str = CAPITAL_MODE
    real_capital_enabled: bool = REAL_CAPITAL_ENABLED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at_utc": self.checked_at_utc,
            "last_bar_ts_utc": self.last_bar_ts_utc,
            "last_bar_age_hours": self.last_bar_age_hours,
            "db_integrity": self.db_integrity,
            "disk_free_mb": self.disk_free_mb,
            "last_backup_file": self.last_backup_file,
            "last_backup_at_utc": self.last_backup_at_utc,
            "backup_count": self.backup_count,
            "active_alerts": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.active_alerts],
            "capital_mode": self.capital_mode,
            "real_capital_enabled": self.real_capital_enabled,
        }


def get_default_paths() -> tuple[Path, Path, Path]:
    """Returns (default_db_path, default_backup_dir, default_state_path)."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    db_path = base_dir / "data" / "p2_shadow_ledger.db"
    backup_dir = base_dir / "data" / "backups"
    state_path = base_dir / "data" / "watchdog_state.json"
    return db_path, backup_dir, state_path


def get_backup_metadata(backup_dir: Path | str | None = None) -> tuple[str | None, str | None, int]:
    """Inspects backup directory and returns (last_backup_file, last_backup_at_utc, backup_count)."""
    if backup_dir is None:
        _, backup_dir, _ = get_default_paths()
    d = Path(backup_dir)
    if not d.exists():
        return None, None, 0

    gz_files = sorted(d.glob("p2_shadow_ledger_*.db.gz"))
    if not gz_files:
        return None, None, 0

    latest = gz_files[-1]
    mtime_utc = datetime.fromtimestamp(latest.stat().st_mtime, tz=UTC).isoformat()
    return latest.name, mtime_utc, len(gz_files)


def backup_shadow_ledger(
    db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    keep_days: int = 30,
    now_utc: datetime | None = None,
) -> Path | None:
    """Safe online SQLite backup using sqlite3.Connection.backup() into a verified .db.gz archive.

    Steps:
    1. Connects read-only to source SQLite database.
    2. Performs online backup into a temporary .db file.
    3. Runs PRAGMA integrity_check on the backup file.
    4. Compresses with gzip to data/backups/p2_shadow_ledger_YYYYMMDD.db.gz.
    5. Prunes backup files older than keep_days (keeping at most keep_days files).
    """
    default_db, default_backup, _ = get_default_paths()
    src_path = Path(db_path) if db_path is not None else default_db
    dst_dir = Path(backup_dir) if backup_dir is not None else default_backup
    dst_dir.mkdir(parents=True, exist_ok=True)

    if not src_path.exists():
        logger.warning(f"backup_shadow_ledger: Source DB {src_path} does not exist.")
        return None

    now = now_utc if now_utc is not None else datetime.now(UTC)
    date_str = now.strftime("%Y%m%d")
    final_gz_path = dst_dir / f"p2_shadow_ledger_{date_str}.db.gz"
    temp_db_path = dst_dir / f"p2_shadow_ledger_{date_str}.tmp.db"

    # 1. Native online SQLite backup in read-only mode
    try:
        src_uri = f"file:{src_path.resolve().as_posix()}?mode=ro"
        src_conn = sqlite3.connect(src_uri, uri=True, timeout=10.0)
        dst_conn = sqlite3.connect(temp_db_path)
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
    except Exception as exc:
        if temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)
        raise RuntimeError(f"Online SQLite backup failed for {src_path}: {exc}") from exc

    # 2. PRAGMA integrity_check on the backup database
    try:
        chk_conn = sqlite3.connect(temp_db_path)
        res = chk_conn.execute("PRAGMA integrity_check").fetchone()
        chk_conn.close()
        if not res or str(res[0]).lower() != "ok":
            temp_db_path.unlink(missing_ok=True)
            raise RuntimeError(f"Integrity check failed on backup DB: {res}")
    except Exception as exc:
        if temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)
        raise RuntimeError(f"Integrity verification failed on backup: {exc}") from exc

    # 3. Gzip compression to target archive
    try:
        with open(temp_db_path, "rb") as f_in, gzip.open(final_gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    finally:
        temp_db_path.unlink(missing_ok=True)

    # 4. Prune backups older than keep_days
    all_backups = sorted(dst_dir.glob("p2_shadow_ledger_*.db.gz"))
    if len(all_backups) > keep_days:
        prune_count = len(all_backups) - keep_days
        for old_backup in all_backups[:prune_count]:
            try:
                old_backup.unlink(missing_ok=True)
                logger.info(f"Pruned old shadow ledger backup: {old_backup.name}")
            except OSError as err:
                logger.warning(f"Failed to prune old backup {old_backup.name}: {err}")

    logger.info(f"Successfully created verified backup: {final_gz_path}")
    return final_gz_path


def run_watchdog_check(
    db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    state_path: Path | str | None = None,
    now_utc: datetime | None = None,
    notify_callback: Callable[[Any], Any] | None = None,
    auto_backup: bool = True,
    max_bar_age_hours: float = DEFAULT_MAX_BAR_AGE_HOURS,
    min_disk_mb: float = DEFAULT_MIN_DISK_MB,
    keep_days: int = 30,
) -> WatchdogReport:
    """Evaluates 4 hard operational health checks:

    1. SQLite Integrity (DB_INTEGRITY_ALERT - CRITICAL)
    2. Missed 4h Bar (MISSED_BAR_ALERT - DEGRADED)
    3. Stale Market Data Feed (STALE_FEED_ALERT - DEGRADED)
    4. Disk Capacity (LOW_DISK_ALERT - CRITICAL)

    Handles anti-spam cooldowns (4h) and auto-recovery notifications via state_path.
    """
    default_db, default_backup, default_state = get_default_paths()
    resolved_db = Path(db_path) if db_path is not None else default_db
    resolved_backup = Path(backup_dir) if backup_dir is not None else default_backup
    resolved_state = Path(state_path) if state_path is not None else default_state

    now = now_utc if now_utc is not None else datetime.now(UTC)
    checked_at_iso = now.isoformat()
    now_ts = now.timestamp()

    active_alerts: list[WatchdogAlert] = []
    db_integrity: bool = False
    last_bar_ts_utc: int | None = None
    last_bar_age_hours: float | None = None

    # --------------------------------------------------------------------------
    # Check 1: SQLite DB Integrity & Initialization
    # --------------------------------------------------------------------------
    db_exists = resolved_db.exists()
    if not db_exists:
        # Day 0 state: DB does not exist yet
        db_integrity = True  # Not corrupted, simply uninitialized
    else:
        try:
            uri = f"file:{resolved_db.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            res = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if not res or str(res[0]).lower() != "ok":
                db_integrity = False
                active_alerts.append(
                    WatchdogAlert(
                        code="DB_INTEGRITY_ALERT",
                        severity="CRITICAL",
                        message_en=f"SQLite integrity check failed: {res[0] if res else 'Unknown'}",
                        message_bn=f"SQLite ইন্টিগ্রিটি চেক ব্যর্থ হয়েছে: {res[0] if res else 'অজানা'}",
                    )
                )
            else:
                db_integrity = True
        except Exception as exc:
            db_integrity = False
            active_alerts.append(
                WatchdogAlert(
                    code="DB_INTEGRITY_ALERT",
                    severity="CRITICAL",
                    message_en=f"SQLite database is unreadable or corrupt: {exc}",
                    message_bn=f"SQLite ডাটাবেস পাঠযোগ্য নয় বা ক্ষতিগ্রস্ত: {exc}",
                )
            )

    # --------------------------------------------------------------------------
    # Check 2 & 3: Missed 4h Bar & Stale Data Feed
    # --------------------------------------------------------------------------
    if db_exists and db_integrity:
        try:
            uri = f"file:{resolved_db.resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Check if shadow_bars table exists
            table_exists = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_bars'"
            ).fetchone()

            if table_exists:
                row = cur.execute(
                    "SELECT bar_ts_utc, stale_warning FROM shadow_bars ORDER BY bar_ts_utc DESC LIMIT 1"
                ).fetchone()

                if row is not None:
                    last_bar_ts_utc = int(row["bar_ts_utc"])
                    stale_warning = int(row["stale_warning"])

                    # Normalize timestamp (milliseconds vs seconds)
                    bar_ts_sec = (
                        last_bar_ts_utc / 1000.0 if last_bar_ts_utc > 1e11 else float(last_bar_ts_utc)
                    )
                    last_bar_age_hours = max(0.0, round((now_ts - bar_ts_sec) / 3600.0, 2))

                    # Missed 4h bar check (> 5.0h)
                    if last_bar_age_hours > max_bar_age_hours:
                        active_alerts.append(
                            WatchdogAlert(
                                code="MISSED_BAR_ALERT",
                                severity="DEGRADED",
                                message_en=(
                                    f"Missed 4h bar: last bar age is {last_bar_age_hours:.1f}h "
                                    f"(> {max_bar_age_hours:.1f}h limit)"
                                ),
                                message_bn=(
                                    f"৪ ঘণ্টার বার মিস হয়েছে: সর্বশেষ বারের বয়স {last_bar_age_hours:.1f} ঘণ্টা "
                                    f"(> {max_bar_age_hours:.1f} ঘণ্টা সীমা)"
                                ),
                            )
                        )

                    # Stale feed check
                    if stale_warning == 1:
                        active_alerts.append(
                            WatchdogAlert(
                                code="STALE_FEED_ALERT",
                                severity="DEGRADED",
                                message_en="Stale market data feed detected on latest shadow bar",
                                message_bn="সর্বশেষ শ্যাডো বারে বাসি/স্থবির মার্কেট ডাটা ফিড সনাক্ত করা হয়েছে",
                            )
                        )
            conn.close()
        except Exception as exc:
            active_alerts.append(
                WatchdogAlert(
                    code="DB_INTEGRITY_ALERT",
                    severity="CRITICAL",
                    message_en=f"Failed to query shadow_bars: {exc}",
                    message_bn=f"shadow_bars টেবিল কুয়েরি করতে ব্যর্থ: {exc}",
                )
            )

    # --------------------------------------------------------------------------
    # Check 4: Free Disk Space
    # --------------------------------------------------------------------------
    try:
        target_dir = resolved_db.parent if resolved_db.parent.exists() else Path(".")
        usage = shutil.disk_usage(target_dir)
        disk_free_mb = round(usage.free / (1024.0 * 1024.0), 2)
        if disk_free_mb < min_disk_mb:
            active_alerts.append(
                WatchdogAlert(
                    code="LOW_DISK_ALERT",
                    severity="CRITICAL",
                    message_en=f"Low disk space: {disk_free_mb:.1f} MB remaining (< {min_disk_mb:.1f} MB limit)",
                    message_bn=f"কম ডিস্ক স্পেস: {disk_free_mb:.1f} MB অবশিষ্ট (< {min_disk_mb:.1f} MB সীমা)",
                )
            )
    except Exception as exc:
        logger.warning(f"Watchdog could not check disk space: {exc}")
        disk_free_mb = 0.0

    # --------------------------------------------------------------------------
    # Status Determination
    # --------------------------------------------------------------------------
    if not db_exists or (last_bar_ts_utc is None and not active_alerts):
        status = "NOT_INITIALIZED"
    elif any(a.severity == "CRITICAL" for a in active_alerts):
        status = "CRITICAL"
    elif any(a.severity == "DEGRADED" for a in active_alerts):
        status = "DEGRADED"
    else:
        status = "HEALTHY"

    # --------------------------------------------------------------------------
    # Automated Daily Backup (if enabled, DB healthy, and not yet backed up today)
    # --------------------------------------------------------------------------
    if auto_backup and db_exists and db_integrity and status != "CRITICAL":
        today_date_str = now.strftime("%Y%m%d")
        expected_today_gz = resolved_backup / f"p2_shadow_ledger_{today_date_str}.db.gz"
        if not expected_today_gz.exists():
            try:
                backup_shadow_ledger(
                    db_path=resolved_db,
                    backup_dir=resolved_backup,
                    keep_days=keep_days,
                    now_utc=now,
                )
            except Exception as b_err:
                logger.error(f"Automated daily backup failed: {b_err}")

    # Inspect backup directory metadata
    last_backup_file, last_backup_at_utc, backup_count = get_backup_metadata(resolved_backup)

    # --------------------------------------------------------------------------
    # Anti-Spam Notification Cooldown & Auto-Recovery Handling
    # --------------------------------------------------------------------------
    state_data: dict[str, Any] = {}
    if resolved_state.exists():
        try:
            with open(resolved_state, encoding="utf-8") as sf:
                state_data = json.load(sf)
        except Exception as s_err:
            logger.warning(f"Could not read watchdog state file {resolved_state}: {s_err}")

    last_status = state_data.get("last_status", "HEALTHY")
    alerts_last_notified = state_data.get("alerts_last_notified", {})

    # Trigger notifications for active alerts if not in cooldown
    for alert in active_alerts:
        last_notified_ts = alerts_last_notified.get(alert.code)
        if last_notified_ts is None or (now_ts - float(last_notified_ts)) >= ALERT_COOLDOWN_SECONDS:
            if notify_callback is not None:
                try:
                    notif = WatchdogNotification(
                        event_type="ALERT",
                        code=alert.code,
                        severity=alert.severity,
                        message_en=alert.message_en,
                        message_bn=alert.message_bn,
                    )
                    notify_callback(notif)
                except Exception as n_err:
                    logger.error(f"Error in watchdog notify_callback: {n_err}")
            alerts_last_notified[alert.code] = now_ts

    # Check for recovery notification: transitioning from DEGRADED/CRITICAL to HEALTHY
    if status == "HEALTHY" and last_status in ("DEGRADED", "CRITICAL"):
        if notify_callback is not None:
            try:
                rec_notif = WatchdogNotification(
                    event_type="RECOVERY",
                    code="OPS_RECOVERED",
                    severity="INFO",
                    message_en="All systems green. CBT Ops Watchdog recovered to HEALTHY.",
                    message_bn="সব সিস্টেম স্বাভাবিক। CBT অপস ওয়াচডগ পুনরায় সুস্থ (HEALTHY) অবস্থায় ফিরে এসেছে।",
                )
                notify_callback(rec_notif)
            except Exception as n_err:
                logger.error(f"Error in watchdog recovery notify_callback: {n_err}")
        # Clear cooldowns on recovery
        alerts_last_notified = {}

    # Save state
    new_state = {
        "last_status": status,
        "alerts_last_notified": alerts_last_notified,
        "last_checked_utc": checked_at_iso,
    }
    try:
        resolved_state.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_state, "w", encoding="utf-8") as sf:
            json.dump(new_state, sf, indent=2)
    except Exception as sw_err:
        logger.warning(f"Could not persist watchdog state to {resolved_state}: {sw_err}")

    return WatchdogReport(
        status=status,
        checked_at_utc=checked_at_iso,
        last_bar_ts_utc=last_bar_ts_utc,
        last_bar_age_hours=last_bar_age_hours,
        db_integrity=db_integrity,
        disk_free_mb=disk_free_mb,
        last_backup_file=last_backup_file,
        last_backup_at_utc=last_backup_at_utc,
        backup_count=backup_count,
        active_alerts=active_alerts,
        capital_mode=CAPITAL_MODE,
        real_capital_enabled=REAL_CAPITAL_ENABLED,
    )


def format_watchdog_report(report: WatchdogReport | dict[str, Any], lang: str = "en") -> str:
    """Renders human-readable boxed terminal/Telegram ops health report in English or Bengali."""
    data = report.to_dict() if hasattr(report, "to_dict") else report
    status = data.get("status", "UNKNOWN")
    checked_at = data.get("checked_at_utc", "N/A")
    db_integrity = "OK" if data.get("db_integrity") else "FAIL"
    bar_age = data.get("last_bar_age_hours")
    disk_free = data.get("disk_free_mb", 0.0)
    backup_file = data.get("last_backup_file") or "None"
    backup_count = data.get("backup_count", 0)
    capital_mode = data.get("capital_mode", "TIER_0_PAPER")
    real_cap = data.get("real_capital_enabled", False)
    active_alerts = data.get("active_alerts", [])

    if lang.lower() == "bn":
        bar_age_str_bn = f"{bar_age:.1f} ঘণ্টা আগে" if bar_age is not None else "অনুপস্থিত"
        lines = [
            "==================================================================",
            "             CBT ২৪/৭ অপস ওয়াচডগ হেলথ রিপোর্ট                     ",
            "==================================================================",
            f"স্ট্যাটাস         : {status}",
            f"যাচাইয়ের সময়     : {checked_at}",
            f"ডাটাবেস ইন্টিগ্রিটি : {db_integrity}",
            f"সর্বশেষ শ্যাডো বার : {bar_age_str_bn}",
            f"ফ্রি ডিস্ক স্পেস   : {disk_free:,.1f} MB",
            f"সর্বশেষ ব্যাকআপ   : {backup_file} (মোট: {backup_count}টি)",
            f"ক্যাপিটাল মোড     : {capital_mode} (রিয়েল ক্যাপিটাল: {'সক্রিয়' if real_cap else 'নিষ্ক্রিয়'})",
            "------------------------------------------------------------------",
        ]
        if not active_alerts:
            lines.append("সক্রিয় অ্যালার্ট   : কোনো অ্যালার্ট নেই (সব সিস্টেম স্বাভাবিক)")
        else:
            lines.append(f"সক্রিয় অ্যালার্ট ({len(active_alerts)}টি):")
            for alert in active_alerts:
                code = alert.get("code")
                sev = alert.get("severity")
                msg = alert.get("message_bn") or alert.get("message_en")
                lines.append(f"  • [{sev}] {code}: {msg}")
        lines.append("==================================================================")
        return "\n".join(lines)

    bar_age_str_en = f"{bar_age:.1f}h ago" if bar_age is not None else "N/A"
    lines = [
        "==================================================================",
        "                 CBT 24/7 OPS WATCHDOG REPORT                     ",
        "==================================================================",
        f"Status          : {status}",
        f"Checked At (UTC): {checked_at}",
        f"DB Integrity    : {db_integrity}",
        f"Last Shadow Bar : {bar_age_str_en}",
        f"Disk Free Space : {disk_free:,.1f} MB",
        f"Last Backup File: {backup_file} (Total: {backup_count})",
        f"Capital Mode    : {capital_mode} (Real Capital: {real_cap})",
        "------------------------------------------------------------------",
    ]
    if not active_alerts:
        lines.append("Active Alerts   : None (All systems green)")
    else:
        lines.append(f"Active Alerts ({len(active_alerts)}):")
        for alert in active_alerts:
            code = alert.get("code")
            sev = alert.get("severity")
            msg = alert.get("message_en")
            lines.append(f"  • [{sev}] {code}: {msg}")
    lines.append("==================================================================")
    return "\n".join(lines)
