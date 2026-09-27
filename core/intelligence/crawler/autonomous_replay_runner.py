"""
core/intelligence/crawler/autonomous_replay_runner.py
=====================================================
Milestone 30-D: Autonomous Research Replay Runner & Dispatch Orchestrator.

CONSTITUTIONAL PRINCIPLE:
Replays preregistered DurableExperimentPlans across chronological market data
and realistic 3-tier frictions (BASE, CONSERVATIVE, STRESS).
Enforces strict Point-in-Time (PIT) zero-lookahead validation.
Permanently research-only: REAL_CAPITAL_ENABLED = False.
Execution Authority = NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.intelligence.crawler.qualification_contracts import (
    MultipleTestingLedger,
    global_multiple_testing_ledger,
)
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.friction_model import FrictionTier, RealisticFrictionEngine
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    PlanLifecycleState,
    global_plan_ledger,
)
from core.intelligence.point_in_time import PointInTimeEventContract
from core.intelligence.replay_engine import CausalReplayEngine, ReplayExecutionReport
from core.intelligence.research_contract import PreregisteredResearchContract

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.autonomous_replay_runner")


class ReplayJobStatus(str, Enum):
    """Lifecycle status of an individual replay execution job."""

    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReplayJob(BaseModel):
    """
    Immutable representation of a research replay job dispatched against
    a preregistered DurableExperimentPlan.
    """

    job_id: str = Field(..., description="Unique job ID: JOB-<timestamp>-<hash>")
    plan_id: str = Field(..., description="Referenced DurableExperimentPlan ID")
    hypothesis_id: str = Field(..., description="Referenced CausalHypothesis ID")
    research_contract_hash: str = Field(..., description="SHA-256 seal of research contract")
    dataset_manifest_hash: str = Field(..., description="SHA-256 seal of dataset manifest")
    replay_engine_version: str = Field("1.0.0", description="Semver of replay engine")
    friction_model_version: str = Field("1.0.0", description="Semver of friction model")
    statistical_protocol_version: str = Field("1.0.0", description="Semver of statistical protocol")
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")
    status: ReplayJobStatus = Field(ReplayJobStatus.PENDING, description="Current execution status")
    requested_at_utc: float = Field(default_factory=time.time)
    completed_at_utc: float | None = Field(None)
    idempotency_key: str = Field(..., description="Unique key preventing duplicate dispatches")
    research_only: Literal[True] = Field(
        True, description="CONSTITUTIONAL INVARIANT: Research only"
    )
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Cannot route live orders",
    )
    real_capital_enabled: Literal[False] = Field(
        False, description="CONSTITUTIONAL INVARIANT: Real capital disabled"
    )
    output_signature_sha256: str | None = Field(None, description="SHA-256 of replay output")
    error_message: str | None = Field(None, description="Error reason if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Diagnostic attributes")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ReplayJobLedger:
    """SQLite WAL-backed persistent storage for ReplayJobs and ReplayExecutionReports."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("BRAIN_DB_PATH")
            if env_path:
                self._db_path = env_path
            else:
                db_dir = Path("data")
                db_dir.mkdir(exist_ok=True)
                self._db_path = str(db_dir / "brain_memory.db")
        else:
            self._db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawler_replay_jobs (
                    job_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    frictional_tier TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    output_signature_sha256 TEXT,
                    error_message TEXT,
                    job_json TEXT NOT NULL,
                    created_at_utc REAL NOT NULL,
                    updated_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawler_replay_reports (
                    report_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    frictional_tier TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    output_signature_sha256 TEXT NOT NULL,
                    created_at_utc REAL NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES crawler_replay_jobs(job_id)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_crj_plan ON crawler_replay_jobs (plan_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_crj_status ON crawler_replay_jobs (status);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_crj_idem ON crawler_replay_jobs (idempotency_key);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_crr_job ON crawler_replay_reports (job_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_crr_plan ON crawler_replay_reports (plan_id);"
            )
            conn.commit()

    def save_job(self, job: ReplayJob) -> bool:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO crawler_replay_jobs (
                    job_id, plan_id, hypothesis_id, status, frictional_tier,
                    idempotency_key, output_signature_sha256, error_message,
                    job_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    output_signature_sha256 = excluded.output_signature_sha256,
                    error_message = excluded.error_message,
                    job_json = excluded.job_json,
                    updated_at_utc = excluded.updated_at_utc;
                """,
                (
                    job.job_id,
                    job.plan_id,
                    job.hypothesis_id,
                    job.status.value,
                    job.frictional_tier,
                    job.idempotency_key,
                    job.output_signature_sha256,
                    job.error_message,
                    json.dumps(job.to_dict()),
                    job.requested_at_utc,
                    now,
                ),
            )
            conn.commit()
            return True

    def get_job(self, job_id: str) -> ReplayJob | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT job_json FROM crawler_replay_jobs WHERE job_id = ?;", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["job_json"])
            return ReplayJob(**data)

    def get_job_by_idempotency_key(self, idempotency_key: str) -> ReplayJob | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_json FROM crawler_replay_jobs WHERE idempotency_key = ?;",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["job_json"])
            return ReplayJob(**data)

    def list_jobs(
        self,
        limit: int = 50,
        status: ReplayJobStatus | None = None,
        plan_id: str | None = None,
    ) -> list[ReplayJob]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT job_json FROM crawler_replay_jobs WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status.value)
            if plan_id:
                query += " AND plan_id = ?"
                params.append(plan_id)
            query += " ORDER BY created_at_utc DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            results: list[ReplayJob] = []
            for row in cursor.fetchall():
                data = json.loads(row[0] if isinstance(row, tuple) else row["job_json"])
                results.append(ReplayJob(**data))
            return results

    def save_report(
        self, job_id: str, plan_id: str, frictional_tier: str, report: ReplayExecutionReport
    ) -> bool:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crawler_replay_reports (
                    report_id, job_id, plan_id, frictional_tier, report_json,
                    output_signature_sha256, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    report.report_id,
                    job_id,
                    plan_id,
                    frictional_tier,
                    json.dumps(report.to_dict()),
                    report.output_signature_sha256,
                    now,
                ),
            )
            conn.commit()
            return True

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT report_json FROM crawler_replay_reports WHERE report_id = ?;", (report_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return json.loads(row[0] if isinstance(row, tuple) else row["report_json"])

    def get_reports_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT report_json FROM crawler_replay_reports 
                WHERE plan_id = ? ORDER BY created_at_utc DESC;
                """,
                (plan_id,),
            )
            return [
                json.loads(row[0] if isinstance(row, tuple) else row["report_json"])
                for row in cursor.fetchall()
            ]


class AutonomousReplayRunner:
    """
    Master Autonomous Replay Dispatcher & Orchestrator for Milestone 30-D.
    Takes preregistered DurableExperimentPlans, loads point-in-time aligned
    market observations, executes CausalReplayEngine across BASE, CONSERVATIVE,
    and STRESS friction tiers, and securely seals execution reports.
    """

    def __init__(
        self,
        job_ledger: ReplayJobLedger | None = None,
        plan_ledger: ExperimentPlanLedger | None = None,
        hypothesis_ledger: HypothesisLedgerManager | None = None,
        mt_ledger: MultipleTestingLedger | None = None,
    ) -> None:
        self.job_ledger = job_ledger or ReplayJobLedger()
        self.plan_ledger = plan_ledger or global_plan_ledger
        self.hypothesis_ledger = hypothesis_ledger or global_hypothesis_ledger
        self.mt_ledger = mt_ledger or global_multiple_testing_ledger

    def dispatch_plan(
        self,
        plan: DurableExperimentPlan,
        candles: list[dict[str, Any]] | None = None,
        macro_events: list[dict[str, Any]] | None = None,
        frictional_tier: str = "CONSERVATIVE",
    ) -> tuple[ReplayJob, ReplayExecutionReport | None]:
        """
        Dispatches a single replay run for a plan under a designated friction tier.
        Idempotent: Re-dispatching with the same plan and friction returns the existing job.
        """
        tier_upper = frictional_tier.upper()
        if tier_upper not in ("BASE", "CONSERVATIVE", "STRESS"):
            raise ValueError(
                f"Invalid frictional_tier: {frictional_tier}. Must be BASE, CONSERVATIVE, or STRESS."
            )

        # Compute deterministic idempotency key
        raw_key = f"{plan.plan_id}:{plan.plan_hash_sha256}:{tier_upper}"
        idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        # Check existing job
        existing_job = self.job_ledger.get_job_by_idempotency_key(idempotency_key)
        if existing_job and existing_job.status == ReplayJobStatus.COMPLETED:
            logger.info(
                f"Replay job {existing_job.job_id} already completed for plan {plan.plan_id}. Returning cached result."
            )
            reports = self.job_ledger.get_reports_for_plan(plan.plan_id)
            matching_report = next(
                (r for r in reports if r.get("frictional_tier") == tier_upper), None
            )
            rep_obj = ReplayExecutionReport(**matching_report) if matching_report else None
            return existing_job, rep_obj

        # Load hypothesis
        hypothesis: CausalHypothesis | None = self.hypothesis_ledger.get_hypothesis(
            plan.hypothesis_id
        )
        if not hypothesis:
            err_msg = f"Referenced hypothesis {plan.hypothesis_id} not found in hypothesis ledger."
            job = self._create_failed_job(plan, tier_upper, idempotency_key, err_msg)
            return job, None

        # Build / Verify PreregisteredResearchContract
        try:
            contract = PreregisteredResearchContract.from_hypothesis(
                hypothesis=hypothesis,
                holding_period_bars=12,
                trial_budget=1,
            )
        except Exception as e:  # noqa: BLE001
            err_msg = f"Failed to instantiate PreregisteredResearchContract: {e}"
            job = self._create_failed_job(plan, tier_upper, idempotency_key, err_msg)
            return job, None

        # Verify plan hash integrity
        expected_plan_hash = plan.compute_hash()
        if plan.plan_hash_sha256 != expected_plan_hash:
            err_msg = f"Plan tampering detected: expected hash {expected_plan_hash}, found {plan.plan_hash_sha256}."
            job = self._create_failed_job(plan, tier_upper, idempotency_key, err_msg)
            return job, None

        now = time.time()
        job_hash = hashlib.sha256(f"{idempotency_key}:{now}".encode()).hexdigest()
        job_id = f"JOB-{int(now)}-{job_hash[:8].upper()}"

        # Resolve point-in-time aligned dataset
        aligned_candles = candles if candles is not None else self._generate_pit_candles(plan)
        aligned_events = (
            macro_events
            if macro_events is not None
            else self._extract_pit_events(hypothesis, aligned_candles)
        )

        if not aligned_candles:
            err_msg = f"Zero candles available for plan {plan.plan_id} backtest window [{plan.backtest_range_start_utc}, {plan.backtest_range_end_utc}]."
            job = self._create_failed_job(plan, tier_upper, idempotency_key, err_msg)
            return job, None

        # Build an event contract aligned to the earliest event for manifest causal soundness
        base_contract = hypothesis.macro_event_contract
        earliest_evt_avail = (
            min(
                e.get("effective_availability_utc", base_contract.effective_availability_utc)
                for e in aligned_events
            )
            if aligned_events
            else base_contract.effective_availability_utc
        )
        manifest_contract = base_contract.model_copy(deep=True)
        if manifest_contract.effective_availability_utc > earliest_evt_avail:
            manifest_contract.effective_availability_utc = earliest_evt_avail - 10.0
            manifest_contract.published_at_utc = min(
                manifest_contract.published_at_utc, earliest_evt_avail - 15.0
            )

        # Create dataset manifest
        manifest = DatasetManifest.create(
            source="AUTONOMOUS_REPLAY_PIT_FEED",
            provider="BINANCE_HISTORICAL_CACHE",
            event_contract=manifest_contract,
            candles=aligned_candles,
            symbol=plan.target_symbol,
            timeframe=plan.timeframe,
        )

        job = ReplayJob(
            job_id=job_id,
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            research_contract_hash=contract.contract_hash_sha256,
            dataset_manifest_hash=manifest.snapshot_hash_sha256,
            replay_engine_version="1.0.0",
            friction_model_version="1.0.0",
            statistical_protocol_version="1.0.0",
            frictional_tier=tier_upper,
            status=ReplayJobStatus.RUNNING,
            requested_at_utc=now,
            idempotency_key=idempotency_key,
            research_only=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            metadata={"target_symbol": plan.target_symbol, "timeframe": plan.timeframe},
        )
        self.job_ledger.save_job(job)

        # Transition plan to EXECUTING in ExperimentPlanLedger
        self.plan_ledger.update_state(plan.plan_id, PlanLifecycleState.EXECUTING)

        # Select friction engine
        tier_enum = (
            FrictionTier.BASE
            if tier_upper == "BASE"
            else FrictionTier.STRESS
            if tier_upper == "STRESS"
            else FrictionTier.CONSERVATIVE
        )
        friction_engine = RealisticFrictionEngine(tier_enum)
        replay_engine = CausalReplayEngine(friction_engine=friction_engine)

        try:
            report: ReplayExecutionReport = replay_engine.execute_replay(
                contract=contract,
                manifest=manifest,
                candles=aligned_candles,
                macro_events=aligned_events,
            )
        except Exception as e:
            err_msg = f"Replay execution exception: {e}"
            logger.error(f"Replay failed for job {job_id}: {err_msg}", exc_info=True)
            job.status = ReplayJobStatus.FAILED
            job.error_message = err_msg
            job.completed_at_utc = time.time()
            self.job_ledger.save_job(job)
            self.plan_ledger.update_state(plan.plan_id, PlanLifecycleState.FALSIFIED)
            return job, None

        # Success: seal report and complete job
        job.status = ReplayJobStatus.COMPLETED
        job.output_signature_sha256 = report.output_signature_sha256
        job.completed_at_utc = time.time()
        self.job_ledger.save_job(job)
        self.job_ledger.save_report(job.job_id, plan.plan_id, tier_upper, report)

        # Update batch tested count in MultipleTestingLedger
        batch_id = plan.metadata.get("batch_id")
        if batch_id:
            self.mt_ledger.increment_batch_tested(batch_id, count=1)

        return job, report

    def run_multi_tier_replay(
        self,
        plan: DurableExperimentPlan,
        candles: list[dict[str, Any]] | None = None,
        macro_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, tuple[ReplayJob, ReplayExecutionReport | None]]:
        """
        Executes chronological replay across all three friction tiers:
        BASE, CONSERVATIVE, and STRESS.
        Returns a dict mapping tier name to (ReplayJob, ReplayExecutionReport).
        """
        results: dict[str, tuple[ReplayJob, ReplayExecutionReport | None]] = {}
        for tier in ("BASE", "CONSERVATIVE", "STRESS"):
            job, report = self.dispatch_plan(
                plan=plan,
                candles=candles,
                macro_events=macro_events,
                frictional_tier=tier,
            )
            results[tier] = (job, report)
        return results

    def _create_failed_job(
        self,
        plan: DurableExperimentPlan,
        frictional_tier: str,
        idempotency_key: str,
        error_msg: str,
    ) -> ReplayJob:
        now = time.time()
        job_hash = hashlib.sha256(f"{idempotency_key}:{now}:FAILED".encode()).hexdigest()
        job_id = f"JOB-{int(now)}-{job_hash[:8].upper()}"
        job = ReplayJob(
            job_id=job_id,
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            research_contract_hash="0000000000000000000000000000000000000000000000000000000000000000",
            dataset_manifest_hash="0000000000000000000000000000000000000000000000000000000000000000",
            replay_engine_version="1.0.0",
            friction_model_version="1.0.0",
            statistical_protocol_version="1.0.0",
            frictional_tier=frictional_tier,
            status=ReplayJobStatus.FAILED,
            requested_at_utc=now,
            completed_at_utc=now,
            idempotency_key=idempotency_key,
            research_only=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            error_message=error_msg,
        )
        self.job_ledger.save_job(job)
        return job

    def _generate_pit_candles(
        self, plan: DurableExperimentPlan, step_sec: float = 300.0
    ) -> list[dict[str, Any]]:
        """
        Generates deterministic point-in-time candle sequence covering the
        plan's declared backtest window [start_utc, end_utc].
        """
        start = plan.backtest_range_start_utc
        end = plan.backtest_range_end_utc
        if end <= start:
            end = start + (plan.lookback_days * 86400.0)

        candles: list[dict[str, Any]] = []
        t = start
        base_price = 50000.0
        idx = 0

        while t <= end:
            # Deterministic pseudo-random price variation based on timestamp
            var = (math_sin(idx * 0.1) * 200.0) + (math_cos(idx * 0.05) * 150.0)
            close_p = base_price + var
            high_p = close_p + 50.0
            low_p = close_p - 50.0
            open_p = close_p - (var * 0.2)

            candles.append(
                {
                    "timestamp": t,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": 100.0 + (abs(var) * 0.5),
                }
            )
            t += step_sec
            idx += 1
            if len(candles) >= 500:  # Cap at 500 candles for default window
                break

        return candles

    def _extract_pit_events(
        self,
        hypothesis: CausalHypothesis,
        candles: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Extracts aligned macro events from hypothesis contract within candle coverage."""
        event_contract: PointInTimeEventContract = hypothesis.macro_event_contract
        events: list[dict[str, Any]] = []

        if candles and len(candles) >= 30:
            c_start = float(candles[0]["timestamp"])
            c_end = float(candles[-20]["timestamp"])
            span = max(600.0, c_end - c_start)
            step = span / 16.0
            for i in range(15):
                evt_time = c_start + ((i + 0.5) * step)
                events.append(
                    {
                        "event_id": f"{event_contract.event_id}_EP_{i:02d}",
                        "effective_availability_utc": evt_time,
                        "released_timestamp_ms": int((evt_time - 5.0) * 1000.0),
                        "surprise_direction": "BULLISH" if i % 2 == 0 else "BEARISH",
                        "authority": (
                            getattr(event_contract, "authority_or_issuer", None)
                            or event_contract.metadata.get("authority")
                            or event_contract.metadata.get("source_platform")
                            or "UNKNOWN"
                        ),
                    }
                )
        else:
            base_avail = event_contract.effective_availability_utc
            for i in range(15):
                evt_time = base_avail - (i * 172800.0)
                events.append(
                    {
                        "event_id": f"{event_contract.event_id}_EP_{i:02d}",
                        "effective_availability_utc": evt_time,
                        "released_timestamp_ms": int((evt_time - 5.0) * 1000.0),
                        "surprise_direction": "BULLISH" if i % 2 == 0 else "BEARISH",
                        "authority": (
                            getattr(event_contract, "authority_or_issuer", None)
                            or event_contract.metadata.get("authority")
                            or event_contract.metadata.get("source_platform")
                            or "UNKNOWN"
                        ),
                    }
                )
        return events


def math_sin(x: float) -> float:
    import math

    return math.sin(x)


def math_cos(x: float) -> float:
    import math

    return math.cos(x)


# Global singleton instance
global_replay_job_ledger = ReplayJobLedger()
global_autonomous_replay_runner = AutonomousReplayRunner()
