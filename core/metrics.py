"""
Prometheus Metrics Engine for SKY / CTB FastAPI Application.
Exposes real-time quantitative, memory, and operational system metrics.
"""

from __future__ import annotations

import time

from core.audit_bus import audit_bus
from core.database import db_manager
from core.portfolio_shadow import portfolio_shadow
from core.provenance_engine import provenance_engine


def generate_prometheus_metrics() -> str:
    """Generates standard Prometheus format plaintext telemetry metrics."""
    open_positions = portfolio_shadow.get_open_positions()
    total_audit_events = len(audit_bus.get_recent_events(limit=1000))
    total_provenance = len(provenance_engine.list_records(limit=1000))
    db_info = db_manager.get_engine_info()

    lines = [
        "# HELP sky_shadow_open_positions Number of active shadow paper trading positions",
        "# TYPE sky_shadow_open_positions gauge",
        f"sky_shadow_open_positions {len(open_positions)}",
        "",
        "# HELP sky_provenance_records_total Total cryptographic source provenance records indexed",
        "# TYPE sky_provenance_records_total counter",
        f"sky_provenance_records_total {total_provenance}",
        "",
        "# HELP sky_audit_events_total Total forensic and governance audit events captured",
        "# TYPE sky_audit_events_total counter",
        f"sky_audit_events_total {total_audit_events}",
        "",
        "# HELP sky_db_storage_mb Total SQLite WAL database storage footprint in megabytes",
        "# TYPE sky_db_storage_mb gauge",
        f"sky_db_storage_mb {db_info.get('total_storage_mb', 0.0)}",
        "",
        "# HELP sky_uptime_seconds System process uptime in seconds",
        "# TYPE sky_uptime_seconds gauge",
        f"sky_uptime_seconds {round(time.time() - getattr(generate_prometheus_metrics, '_start_time', time.time()), 2)}",
        "",
    ]
    return "\n".join(lines)


generate_prometheus_metrics._start_time = time.time()
