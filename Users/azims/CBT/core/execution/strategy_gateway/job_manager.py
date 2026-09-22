"""
core/execution/strategy_gateway/job_manager.py
==============================================
Milestone 26: Asynchronous Qualification Replay Job Manager & Idempotency Engine.

Core Invariants (M26-02, M26-09):
1. ASYNCHRONOUS JOB LIFECYCLE:
   Long-running cohort replay campaigns run in background worker tasks without blocking HTTP event loops.
   Lifecycle State Machine: RECEIVED -> VALIDATING -> QUEUED -> RUNNING -> COMMITTED (terminal)
   Failure / Cancellation: FAILED (terminal), CANCELLED (terminal).
2. IDEMPOTENCY DEFENSE:
   Enforces idempotency keys with 15-minute TTL. Rapid double-clicks return existing active/completed jobs.
3. CONCURRENCY LIMITER:
   Strictly enforces max 1 concurrent active qualification job per strategy_id to prevent resource exhaustion.
4. DURABLE AUDIT RECORD:
   Job status and resulting reports are persisted to SQLite table `strategy_gateway_jobs`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager
from core.execution.strategy_gateway.qualification_campaign import (
    QualificationCampaignRunner,
    StrategyRealityQualificationReport,
)
from core.execution.strategy_gateway.strategies.kronos_adapter import (
    KronosForecastSignal,
)
from core.execution.strategy_gateway.strategies.smc_adapter import (
    SMCOrderFlowSignal,
)
from core.governance.institutional_deployment import DeploymentStage

logger = logging.getLogger("sky.execution.strategy_gateway.job_manager")


class JobStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobConcurrencyError(Exception):
    """Raised when a qualification job is already active for the target strategy."""

    def __init__(self, strategy_id: str, active_job_id: str) -> None:
        super().__init__(
            f"Strategy '{strategy_id}' already has an active qualification job (job_id: {active_job_id}). "
            "Concurrent replays for the same strategy are prohibited to protect compute and state integrity."
        )
        self.strategy_id = strategy_id
        self.active_job_id = active_job_id


@dataclass
class QualificationJob:
    """Immutable metadata and state for an asynchronous qualification replay job."""

    job_id: str
    idempotency_key: str
    strategy_id: str
    strategy_version: str
    deployment_stage: str
    status: JobStatus
    signals_count: int
    created_at_utc: str
    created_at_epoch_ms: int
    updated_at_epoch_ms: int
    error_message: str | None = None
    report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        return res


class QualificationJobManager:
    """
    Manages the lifecycle, concurrency, idempotency, and background execution
    of institutional Strategy Reality Qualification campaigns.
    """

    IDEMPOTENCY_TTL_MS: int = 15 * 60 * 1000  # 15 minutes

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        campaign_runner: QualificationCampaignRunner | None = None,
    ) -> None:
        self._db_conn = db_conn
        self._campaign_runner = campaign_runner
        self._jobs: dict[str, QualificationJob] = {}
        self._idempotency_map: dict[str, tuple[str, int]] = {}  # key -> (job_id, timestamp_ms)
        self._active_strategy_jobs: dict[str, str] = {}  # strategy_id -> job_id
        self._lock = asyncio.Lock()
        self._ensure_schema()

    def _get_runner(self) -> QualificationCampaignRunner:
        if self._campaign_runner is None:
            self._campaign_runner = QualificationCampaignRunner(db_conn=self._db_conn)
        return self._campaign_runner

    def _ensure_schema(self) -> None:
        """Initializes SQLite ledger for strategy qualification jobs."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS strategy_gateway_jobs (
                        job_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL,
                        strategy_id TEXT NOT NULL,
                        strategy_version TEXT NOT NULL,
                        deployment_stage TEXT NOT NULL,
                        status TEXT NOT NULL,
                        signals_count INTEGER NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        created_at_epoch_ms INTEGER NOT NULL,
                        updated_at_epoch_ms INTEGER NOT NULL,
                        error_message TEXT,
                        report_json TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sg_jobs_strategy ON strategy_gateway_jobs(strategy_id, created_at_epoch_ms DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sg_jobs_idempotency ON strategy_gateway_jobs(idempotency_key)"
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[JobManager] Failed to initialize SQLite schema: {exc}")

    def _persist_job(self, job: QualificationJob) -> None:
        """Persists or updates a job record in SQLite."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            report_json = json.dumps(job.report) if job.report else None
            with conn:
                conn.execute(
                    """
                    INSERT INTO strategy_gateway_jobs (
                        job_id, idempotency_key, strategy_id, strategy_version,
                        deployment_stage, status, signals_count, created_at_utc,
                        created_at_epoch_ms, updated_at_epoch_ms, error_message, report_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        status=excluded.status,
                        updated_at_epoch_ms=excluded.updated_at_epoch_ms,
                        error_message=excluded.error_message,
                        report_json=excluded.report_json
                    """,
                    (
                        job.job_id,
                        job.idempotency_key,
                        job.strategy_id,
                        job.strategy_version,
                        job.deployment_stage,
                        job.status.value,
                        job.signals_count,
                        job.created_at_utc,
                        job.created_at_epoch_ms,
                        job.updated_at_epoch_ms,
                        job.error_message,
                        report_json,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[JobManager] Failed to persist job {job.job_id}: {exc}")

    async def submit_job(
        self,
        strategy_id: str,
        strategy_version: str,
        deployment_stage: str,
        dataset_hash: str,
        experiment_id: str,
        signals: list[KronosForecastSignal | SMCOrderFlowSignal],
        idempotency_key: str | None = None,
        account_equity_usd: float = 100000.0,
        simulated_spread_bps: float = 3.0,
        simulated_depth_qty: float = 100.0,
        mock_fill_slippage_bps: float = 1.5,
        min_sample_size: int = 5,
        max_allowable_is_bps: float = 12.0,
    ) -> tuple[QualificationJob, bool]:
        """
        Submits a qualification replay campaign asynchronously.

        Returns:
            tuple[QualificationJob, bool]: (job, was_created)
            - was_created=True if new job was queued.
            - was_created=False if returned existing job via idempotency.

        Raises:
            JobConcurrencyError: If an active job is already running for the strategy.
        """
        now_ms = int(time.time() * 1000)
        idem_key = idempotency_key or f"idem_{uuid.uuid4().hex}"

        async with self._lock:
            # 1. Idempotency Check
            if idem_key in self._idempotency_map:
                existing_id, created_ms = self._idempotency_map[idem_key]
                if (now_ms - created_ms) < self.IDEMPOTENCY_TTL_MS:
                    existing_job = self.get_job(existing_id)
                    if existing_job:
                        logger.info(
                            f"[JobManager] Idempotent replay hit for key {idem_key} -> job {existing_id}"
                        )
                        return existing_job, False

            # 2. Concurrency Check (Max 1 active per strategy)
            active_id = self._active_strategy_jobs.get(strategy_id)
            if active_id:
                active_job = self.get_job(active_id)
                if active_job and active_job.status in (
                    JobStatus.RECEIVED,
                    JobStatus.VALIDATING,
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                ):
                    raise JobConcurrencyError(strategy_id=strategy_id, active_job_id=active_id)

            # 3. Create Job
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            created_at_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ms / 1000))
            job = QualificationJob(
                job_id=job_id,
                idempotency_key=idem_key,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                deployment_stage=deployment_stage,
                status=JobStatus.RECEIVED,
                signals_count=len(signals),
                created_at_utc=created_at_utc,
                created_at_epoch_ms=now_ms,
                updated_at_epoch_ms=now_ms,
            )

            self._jobs[job_id] = job
            self._idempotency_map[idem_key] = (job_id, now_ms)
            self._active_strategy_jobs[strategy_id] = job_id
            self._persist_job(job)

        # 4. Schedule Background Worker
        asyncio.create_task(
            self._execute_job_lifecycle(
                job_id=job_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                deployment_stage=deployment_stage,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                signals=signals,
                account_equity_usd=account_equity_usd,
                simulated_spread_bps=simulated_spread_bps,
                simulated_depth_qty=simulated_depth_qty,
                mock_fill_slippage_bps=mock_fill_slippage_bps,
                min_sample_size=min_sample_size,
                max_allowable_is_bps=max_allowable_is_bps,
            )
        )

        return job, True

    async def _execute_job_lifecycle(
        self,
        job_id: str,
        strategy_id: str,
        strategy_version: str,
        deployment_stage: str,
        dataset_hash: str,
        experiment_id: str,
        signals: list[KronosForecastSignal | SMCOrderFlowSignal],
        account_equity_usd: float,
        simulated_spread_bps: float,
        simulated_depth_qty: float,
        mock_fill_slippage_bps: float,
        min_sample_size: int,
        max_allowable_is_bps: float,
    ) -> None:
        """Asynchronous worker executing qualification campaign through lifecycle stages."""
        runner = self._get_runner()
        try:
            # Stage A: VALIDATING
            self._update_job_status(job_id, JobStatus.VALIDATING)
            if not signals:
                raise ValueError("Cannot execute qualification campaign with zero signals.")

            # Stage B: QUEUED -> RUNNING
            self._update_job_status(job_id, JobStatus.RUNNING)

            # Stage C: Execute Qualification Campaign
            stage_enum = (
                DeploymentStage(deployment_stage)
                if deployment_stage in DeploymentStage.__members__.values()
                else DeploymentStage.RESEARCH
            )
            report: StrategyRealityQualificationReport = await runner.execute_campaign(
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                deployment_stage=stage_enum,
                dataset_hash=dataset_hash,
                experiment_id=experiment_id,
                signals=signals,
                account_equity_usd=account_equity_usd,
                simulated_spread_bps=simulated_spread_bps,
                simulated_depth_qty=simulated_depth_qty,
                mock_fill_slippage_bps=mock_fill_slippage_bps,
                min_sample_size=min_sample_size,
                max_allowable_is_bps=max_allowable_is_bps,
            )

            # Stage D: COMMITTED
            self._update_job_status(
                job_id,
                JobStatus.COMMITTED,
                report=report.to_dict(),
            )
            audit_bus.publish_event(
                event_type="QUALIFICATION_JOB_COMMITTED",
                payload={
                    "job_id": job_id,
                    "strategy_id": strategy_id,
                    "verdict": report.qualification_verdict,
                    "report_hash": report.report_hash,
                },
            )
        except Exception as exc:
            logger.exception(f"[JobManager] Qualification job {job_id} failed: {exc}")
            self._update_job_status(job_id, JobStatus.FAILED, error_message=str(exc))
            audit_bus.publish_event(
                event_type="QUALIFICATION_JOB_FAILED",
                payload={"job_id": job_id, "strategy_id": strategy_id, "error": str(exc)},
            )
        finally:
            # Clear active strategy concurrency slot
            if self._active_strategy_jobs.get(strategy_id) == job_id:
                self._active_strategy_jobs.pop(strategy_id, None)

    def _update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        report: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Safely transitions job state and persists to database."""
        job = self._jobs.get(job_id)
        if not job:
            return
        now_ms = int(time.time() * 1000)
        job.status = status
        job.updated_at_epoch_ms = now_ms
        if report is not None:
            job.report = report
        if error_message is not None:
            job.error_message = error_message
        self._persist_job(job)

    def get_job(self, job_id: str) -> QualificationJob | None:
        """Retrieves job from memory cache or SQLite."""
        if job_id in self._jobs:
            return self._jobs[job_id]

        # SQLite fallback
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                row = conn.execute(
                    """
                    SELECT job_id, idempotency_key, strategy_id, strategy_version,
                           deployment_stage, status, signals_count, created_at_utc,
                           created_at_epoch_ms, updated_at_epoch_ms, error_message, report_json
                    FROM strategy_gateway_jobs
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()

            if row:
                report = json.loads(row[11]) if row[11] else None
                job = QualificationJob(
                    job_id=row[0],
                    idempotency_key=row[1],
                    strategy_id=row[2],
                    strategy_version=row[3],
                    deployment_stage=row[4],
                    status=JobStatus(row[5]),
                    signals_count=row[6],
                    created_at_utc=row[7],
                    created_at_epoch_ms=row[8],
                    updated_at_epoch_ms=row[9],
                    error_message=row[10],
                    report=report,
                )
                self._jobs[job_id] = job
                return job
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[JobManager] Error querying job {job_id} from SQLite: {exc}")
        return None

    def list_jobs(
        self, limit: int = 50, strategy_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Lists recent qualification jobs with optional strategy filter."""
        try:
            conn = self._db_conn or db_manager.get_trading_conn()
            with conn:
                if strategy_id:
                    rows = conn.execute(
                        """
                        SELECT job_id, idempotency_key, strategy_id, strategy_version,
                               deployment_stage, status, signals_count, created_at_utc,
                               created_at_epoch_ms, updated_at_epoch_ms, error_message
                        FROM strategy_gateway_jobs
                        WHERE strategy_id = ?
                        ORDER BY created_at_epoch_ms DESC
                        LIMIT ?
                        """,
                        (strategy_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT job_id, idempotency_key, strategy_id, strategy_version,
                               deployment_stage, status, signals_count, created_at_utc,
                               created_at_epoch_ms, updated_at_epoch_ms, error_message
                        FROM strategy_gateway_jobs
                        ORDER BY created_at_epoch_ms DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()

            return [
                {
                    "job_id": r[0],
                    "idempotency_key": r[1],
                    "strategy_id": r[2],
                    "strategy_version": r[3],
                    "deployment_stage": r[4],
                    "status": r[5],
                    "signals_count": r[6],
                    "created_at_utc": r[7],
                    "created_at_epoch_ms": r[8],
                    "updated_at_epoch_ms": r[9],
                    "error_message": r[10],
                }
                for r in rows
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[JobManager] Error listing jobs from SQLite: {exc}")
            return []


# Global singleton job manager
qualification_job_manager = QualificationJobManager()
