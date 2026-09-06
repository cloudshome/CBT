"""
Asynchronous Job Management & Polling Tracker for Telegram V5.
Enforces Section 40 of the Master Directive:
- Decouples heavy workloads (PDF OCR, Walk-Forward Tests, Chart Renders) from the Telegram polling loop
- Issues instant Job ID receipts
- Exposes /job <id> tracking and automatic completion callbacks
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.telegram.jobs")


@dataclass
class TelegramJob:
    """Represents a long-running asynchronous background job."""
    job_id: str
    job_type: str  # 'RESEARCH_INGEST', 'WALK_FORWARD_BACKTEST', 'MULTIMODAL_OCR', 'CHART_SNAPSHOT'
    user_id: str
    chat_id: str
    title: str
    status: str = "PENDING"  # 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'
    progress_pct: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result_json: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelegramJobManager:
    """Coordinates and queries persistent asynchronous jobs."""

    def __init__(self):
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_jobs (
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        chat_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress_pct INTEGER DEFAULT 0,
                        created_at REAL NOT NULL,
                        completed_at REAL,
                        result_json TEXT,
                        error_message TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tg_jobs_user ON telegram_jobs (user_id);")
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Could not initialize telegram_jobs table: {e}")

    def create_job(
        self,
        job_type: str,
        user_id: int | str,
        chat_id: int | str,
        title: str,
    ) -> TelegramJob:
        """Initializes a tracked background job."""
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        job = TelegramJob(
            job_id=job_id,
            job_type=job_type,
            user_id=str(user_id),
            chat_id=str(chat_id),
            title=title,
            status="RUNNING",
        )

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO telegram_jobs
                    (job_id, job_type, user_id, chat_id, title, status, progress_pct, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job.job_id, job.job_type, job.user_id, job.chat_id, job.title, job.status, job.progress_pct, job.created_at),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Error creating telegram job {job_id}: {e}")

        return job

    def update_job(
        self,
        job_id: str,
        status: str,
        progress_pct: int | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Updates status, progress, or completion metrics."""
        now = time.time() if status in ("COMPLETED", "FAILED") else None
        res_str = json.dumps(result) if result is not None else None
        prog = progress_pct if progress_pct is not None else (100 if status == "COMPLETED" else None)

        try:
            with db_manager.get_trading_conn() as conn:
                if prog is not None:
                    conn.execute(
                        """
                        UPDATE telegram_jobs
                        SET status = ?, progress_pct = ?, completed_at = COALESCE(?, completed_at),
                            result_json = COALESCE(?, result_json), error_message = COALESCE(?, error_message)
                        WHERE job_id = ?
                        """,
                        (status, prog, now, res_str, error, job_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE telegram_jobs
                        SET status = ?, completed_at = COALESCE(?, completed_at),
                            result_json = COALESCE(?, result_json), error_message = COALESCE(?, error_message)
                        WHERE job_id = ?
                        """,
                        (status, now, res_str, error, job_id),
                    )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Error updating job {job_id}: {e}")

    def get_job(self, job_id: str) -> TelegramJob | None:
        """Queries a job by ID."""
        clean_id = job_id.strip().upper()
        try:
            with db_manager.get_trading_conn() as conn:
                cur = conn.execute("SELECT * FROM telegram_jobs WHERE job_id = ?", (clean_id,))
                row = cur.fetchone()
                if row:
                    return TelegramJob(
                        job_id=row["job_id"],
                        job_type=row["job_type"],
                        user_id=row["user_id"],
                        chat_id=row["chat_id"],
                        title=row["title"],
                        status=row["status"],
                        progress_pct=row["progress_pct"],
                        created_at=row["created_at"],
                        completed_at=row["completed_at"],
                        result_json=row["result_json"] or "",
                        error_message=row["error_message"] or "",
                    )
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Error querying job {clean_id}: {e}")
        return None

    def format_job_status(self, job: TelegramJob) -> str:
        """Formats an institutional status response for Telegram."""
        emoji = "⏳" if job.status == "RUNNING" else "✅" if job.status == "COMPLETED" else "❌" if job.status == "FAILED" else "⚪"
        lines = [
            f"{emoji} **SKY ASYNC JOB STATUS**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🆔 **Job ID:** `{job.job_id}`",
            f"🏷️ **Task:** `{job.title}`",
            f"📊 **Status:** `{job.status}` ({job.progress_pct}%)",
        ]
        if job.error_message:
            lines.append(f"⚠️ **Error:** `{job.error_message}`")
        if job.completed_at and job.created_at:
            duration = job.completed_at - job.created_at
            lines.append(f"⏱️ **Duration:** `{duration:.1f}s`")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


# Global Job Manager Singleton
job_manager = TelegramJobManager()
