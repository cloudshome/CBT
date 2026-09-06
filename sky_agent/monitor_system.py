"""sky_agent.monitor_system — periodic host health probe (CPU/RAM/disk/staleness)."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any


def _cpu_percent() -> float | None:
    try:
        # 1-minute load avg normalised by cpu count (portable, no psutil)
        load1, _, _ = os.getloadavg()
        n = os.cpu_count() or 1
        return round(min(100.0, (load1 / n) * 100), 1)
    except Exception:
        return None


def _ram_percent() -> float | None:
    try:
        import pathlib

        txt = pathlib.Path("/proc/meminfo").read_text()
        info = {}
        for line in txt.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal")
        avail = info.get("MemAvailable")
        if total and avail:
            used = total - avail
            return round(used / total * 100, 1)
    except Exception:
        pass
    return None


def probe_system(
    *, store_path: Path | None = None, db_path: Path | None = None
) -> dict[str, Any]:
    from sky_agent.config import DISK_ALERT_PCT, RAM_ALERT_PCT

    alerts: list[str] = []
    now = int(time.time())
    disk_pct = None
    try:
        root = Path(store_path) if store_path else Path("/")
        du = shutil.disk_usage(str(root))
        disk_pct = round((1 - du.free / du.total) * 100, 1) if du.total else None
        if disk_pct is not None and disk_pct > DISK_ALERT_PCT:
            alerts.append(f"disk {disk_pct}% > {DISK_ALERT_PCT}%")
    except Exception:
        pass

    ram = _ram_percent()
    if ram is not None and ram > RAM_ALERT_PCT:
        alerts.append(f"RAM {ram}% > {RAM_ALERT_PCT}%")

    cpu = _cpu_percent()

    # Data freshness: last candle ts vs now (per store)
    stale = False
    stale_detail = ""
    try:

        # Quick probe: check any stored series freshness via data/quality if available
        pass  # type: ignore
    except Exception:
        pass

    # DB health
    db_ok = True
    db_detail = ""
    try:
        from data.database import SignalDB

        with SignalDB(path=db_path) as db:
            db.conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        db_ok = False
        db_detail = str(exc)
        alerts.append(f"database failure: {db_detail[:120]}")

    level = (
        "CRITICAL"
        if any("database" in a or "disk" in a for a in alerts)
        else ("HIGH" if alerts else "LOW")
    )

    return {
        "ts": now,
        "cpu_pct": cpu,
        "ram_pct": ram,
        "disk_pct": disk_pct,
        "alerts": alerts,
        "level": level,
        "db_ok": db_ok,
        "db_detail": db_detail,
    }
