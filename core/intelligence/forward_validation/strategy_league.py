"""
core/intelligence/forward_validation/strategy_league.py
=======================================================
Immutable Strategy League Registry & Forward Validation State Machine for Milestone 31.

Enforces:
1. Anti-Survivorship Bias: The registry is strictly append-only. Underperforming,
   failed, or suspended strategies remain permanently recorded and visible with full denominators.
2. Parameter Immutability: Rejects attempts to alter frozen parameter vectors during evaluation.
3. Mandatory Human Review Gate: Verifies explicit human operator approval before admission.
4. Comprehensive Audit Trail: Durable state transitions and suspension logs stored in SQLite WAL.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.intelligence.forward_validation.models import (
    AdmissionStatus,
    EvaluationMode,
    HumanApprovalRequiredError,
    LeagueStrategyRecord,
    ParameterImmutabilityError,
    StrategyAdmission,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.strategy_league")


class DuplicateAdmissionError(ValueError):
    """Raised when an identical strategy genome/parameter hash is already active in the league."""


class StrategyNotFoundError(KeyError):
    """Raised when an operation targets an unknown admission ID."""


class StrategyLeagueRegistry:
    """
    Durable, append-only registry governing admitted forward-validation strategies.
    Guarantees denominator transparency and complete auditability across all lifecycle stages.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = "data/forward_league.db"
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None
        elif str(db_path) == ":memory:":
            self._db_path = ":memory:"
            self._is_memory = True
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._is_memory = False
            self._mem_conn = None

        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        if self._is_memory and self._mem_conn is not None:
            with self._mem_conn:
                yield self._mem_conn
        else:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_admissions (
                    admission_id TEXT PRIMARY KEY,
                    dossier_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    strategy_genome_id TEXT NOT NULL,
                    research_protocol_hash TEXT NOT NULL,
                    parameter_hash TEXT NOT NULL,
                    frozen_parameters TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    admission_timestamp_utc REAL NOT NULL,
                    evaluation_start_utc REAL NOT NULL,
                    evaluation_end_utc REAL NOT NULL,
                    evaluation_mode TEXT NOT NULL,
                    market_universe TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    expected_holding_period_sec REAL NOT NULL,
                    suspension_policy_version TEXT NOT NULL,
                    human_approval_reference TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_authority TEXT NOT NULL,
                    real_capital_enabled INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forward_strategy_registry (
                    admission_id TEXT PRIMARY KEY,
                    strategy_genome_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_observations INTEGER NOT NULL DEFAULT 0,
                    winning_observations INTEGER NOT NULL DEFAULT 0,
                    losing_observations INTEGER NOT NULL DEFAULT 0,
                    gross_pnl_bps REAL NOT NULL DEFAULT 0.0,
                    net_pnl_bps REAL NOT NULL DEFAULT 0.0,
                    max_drawdown_bps REAL NOT NULL DEFAULT 0.0,
                    high_water_mark_bps REAL NOT NULL DEFAULT 0.0,
                    avg_markout_5s_bps REAL NOT NULL DEFAULT 0.0,
                    last_observation_utc REAL,
                    suspension_reason TEXT,
                    updated_at_utc REAL NOT NULL,
                    FOREIGN KEY(admission_id) REFERENCES strategy_admissions(admission_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_state_transitions (
                    transition_id TEXT PRIMARY KEY,
                    admission_id TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator_or_system TEXT NOT NULL,
                    timestamp_utc REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_suspension_logs (
                    suspension_id TEXT PRIMARY KEY,
                    admission_id TEXT NOT NULL,
                    trigger_name TEXT NOT NULL,
                    threshold_val REAL NOT NULL,
                    observed_val REAL NOT NULL,
                    policy_version TEXT NOT NULL,
                    details TEXT NOT NULL,
                    timestamp_utc REAL NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reg_genome_status ON forward_strategy_registry(strategy_genome_id, status);"
            )
            conn.commit()

    def admit_strategy(self, admission: StrategyAdmission) -> StrategyAdmission:
        """
        Registers an approved strategy admission into the league.
        Enforces human authorization, parameter integrity, and active deduplication.
        """
        if not admission.human_approval_reference.strip():
            raise HumanApprovalRequiredError(
                f"Admission {admission.admission_id} requires explicit human operator signature."
            )

        with self._get_connection() as conn:
            # Check for existing active admission of identical genome and parameter hash
            cursor = conn.execute(
                """
                SELECT a.admission_id FROM strategy_admissions a
                JOIN forward_strategy_registry r ON a.admission_id = r.admission_id
                WHERE a.strategy_genome_id = ? AND a.parameter_hash = ?
                AND r.status IN ('ADMITTED', 'ACTIVE')
                """,
                (admission.strategy_genome_id, admission.parameter_hash),
            )
            row = cursor.fetchone()
            if row:
                raise DuplicateAdmissionError(
                    f"Strategy genome {admission.strategy_genome_id} with parameter hash {admission.parameter_hash[:10]} "
                    f"is already active under admission ID {row['admission_id']}."
                )

            # Insert admission record
            conn.execute(
                """
                INSERT INTO strategy_admissions (
                    admission_id, dossier_id, hypothesis_id, plan_id, strategy_genome_id,
                    research_protocol_hash, parameter_hash, frozen_parameters, dataset_hash,
                    admission_timestamp_utc, evaluation_start_utc, evaluation_end_utc,
                    evaluation_mode, market_universe, timeframe, expected_holding_period_sec,
                    suspension_policy_version, human_approval_reference, status,
                    execution_authority, real_capital_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admission.admission_id,
                    admission.dossier_id,
                    admission.hypothesis_id,
                    admission.plan_id,
                    admission.strategy_genome_id,
                    admission.research_protocol_hash,
                    admission.parameter_hash,
                    json.dumps(admission.frozen_parameters, sort_keys=True),
                    admission.dataset_hash,
                    admission.admission_timestamp_utc,
                    admission.evaluation_start_utc,
                    admission.evaluation_end_utc,
                    admission.evaluation_mode.value,
                    json.dumps(admission.market_universe),
                    admission.timeframe,
                    admission.expected_holding_period_sec,
                    admission.suspension_policy_version,
                    admission.human_approval_reference,
                    admission.status.value,
                    admission.execution_authority,
                    0,  # real_capital_enabled strictly False
                ),
            )

            # Initialize registry record
            now = time.time()
            conn.execute(
                """
                INSERT INTO forward_strategy_registry (
                    admission_id, strategy_genome_id, status, total_observations,
                    winning_observations, losing_observations, gross_pnl_bps, net_pnl_bps,
                    max_drawdown_bps, high_water_mark_bps, avg_markout_5s_bps,
                    last_observation_utc, suspension_reason, updated_at_utc
                ) VALUES (?, ?, ?, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, NULL, NULL, ?)
                """,
                (admission.admission_id, admission.strategy_genome_id, admission.status.value, now),
            )

            # Record initial transition
            trans_id = f"TR-{int(now)}-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO strategy_state_transitions (
                    transition_id, admission_id, old_status, new_status, reason,
                    operator_or_system, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trans_id,
                    admission.admission_id,
                    "PENDING_REVIEW",
                    admission.status.value,
                    f"Human admission approved ({admission.human_approval_reference[:16]}...)",
                    "HUMAN_OPERATOR",
                    now,
                ),
            )
            conn.commit()

        logger.info(
            "Admitted strategy %s (%s) into forward league.",
            admission.admission_id,
            admission.strategy_genome_id,
        )
        return admission

    def get_admission(self, admission_id: str) -> StrategyAdmission | None:
        """Retrieves raw StrategyAdmission contract."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM strategy_admissions WHERE admission_id = ?", (admission_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StrategyAdmission(
                admission_id=row["admission_id"],
                dossier_id=row["dossier_id"],
                hypothesis_id=row["hypothesis_id"],
                plan_id=row["plan_id"],
                strategy_genome_id=row["strategy_genome_id"],
                research_protocol_hash=row["research_protocol_hash"],
                parameter_hash=row["parameter_hash"],
                frozen_parameters=json.loads(row["frozen_parameters"]),
                dataset_hash=row["dataset_hash"],
                admission_timestamp_utc=row["admission_timestamp_utc"],
                evaluation_start_utc=row["evaluation_start_utc"],
                evaluation_end_utc=row["evaluation_end_utc"],
                evaluation_mode=EvaluationMode(row["evaluation_mode"]),
                market_universe=json.loads(row["market_universe"]),
                timeframe=row["timeframe"],
                expected_holding_period_sec=row["expected_holding_period_sec"],
                suspension_policy_version=row["suspension_policy_version"],
                human_approval_reference=row["human_approval_reference"],
                status=AdmissionStatus(row["status"]),
                execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
                real_capital_enabled=False,
            )

    def get_strategy(self, admission_id: str) -> LeagueStrategyRecord | None:
        """Retrieves active strategy record including metrics."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT a.*, r.status AS reg_status, r.total_observations, r.winning_observations,
                       r.losing_observations, r.gross_pnl_bps, r.net_pnl_bps, r.max_drawdown_bps,
                       r.high_water_mark_bps, r.avg_markout_5s_bps, r.last_observation_utc,
                       r.suspension_reason
                FROM strategy_admissions a
                JOIN forward_strategy_registry r ON a.admission_id = r.admission_id
                WHERE a.admission_id = ?
                """,
                (admission_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return LeagueStrategyRecord(
                admission_id=row["admission_id"],
                strategy_genome_id=row["strategy_genome_id"],
                dossier_id=row["dossier_id"],
                hypothesis_id=row["hypothesis_id"],
                plan_id=row["plan_id"],
                parameter_hash=row["parameter_hash"],
                status=AdmissionStatus(row["reg_status"]),
                evaluation_mode=EvaluationMode(row["evaluation_mode"]),
                market_universe=json.loads(row["market_universe"]),
                timeframe=row["timeframe"],
                admission_timestamp_utc=row["admission_timestamp_utc"],
                evaluation_start_utc=row["evaluation_start_utc"],
                evaluation_end_utc=row["evaluation_end_utc"],
                total_observations=row["total_observations"],
                winning_observations=row["winning_observations"],
                losing_observations=row["losing_observations"],
                gross_pnl_bps=row["gross_pnl_bps"],
                net_pnl_bps=row["net_pnl_bps"],
                max_drawdown_bps=row["max_drawdown_bps"],
                high_water_mark_bps=row["high_water_mark_bps"],
                avg_markout_5s_bps=row["avg_markout_5s_bps"],
                last_observation_utc=row["last_observation_utc"],
                suspension_reason=row["suspension_reason"],
            )

    def list_strategies(
        self,
        status: AdmissionStatus | None = None,
        include_historical: bool = True,
    ) -> list[LeagueStrategyRecord]:
        """
        Lists strategies in the league.
        By default, include_historical=True returns ALL strategies (active, suspended, failed)
        to prevent survivorship bias.
        """
        with self._get_connection() as conn:
            query = """
                SELECT a.*, r.status AS reg_status, r.total_observations, r.winning_observations,
                       r.losing_observations, r.gross_pnl_bps, r.net_pnl_bps, r.max_drawdown_bps,
                       r.high_water_mark_bps, r.avg_markout_5s_bps, r.last_observation_utc,
                       r.suspension_reason
                FROM strategy_admissions a
                JOIN forward_strategy_registry r ON a.admission_id = r.admission_id
            """
            params: list[Any] = []
            conditions: list[str] = []

            if status is not None:
                conditions.append("r.status = ?")
                params.append(status.value)
            elif not include_historical:
                conditions.append("r.status IN ('ADMITTED', 'ACTIVE')")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY r.updated_at_utc DESC;"
            cursor = conn.execute(query, params)

            records: list[LeagueStrategyRecord] = []
            for row in cursor.fetchall():
                records.append(
                    LeagueStrategyRecord(
                        admission_id=row["admission_id"],
                        strategy_genome_id=row["strategy_genome_id"],
                        dossier_id=row["dossier_id"],
                        hypothesis_id=row["hypothesis_id"],
                        plan_id=row["plan_id"],
                        parameter_hash=row["parameter_hash"],
                        status=AdmissionStatus(row["reg_status"]),
                        evaluation_mode=EvaluationMode(row["evaluation_mode"]),
                        market_universe=json.loads(row["market_universe"]),
                        timeframe=row["timeframe"],
                        admission_timestamp_utc=row["admission_timestamp_utc"],
                        evaluation_start_utc=row["evaluation_start_utc"],
                        evaluation_end_utc=row["evaluation_end_utc"],
                        total_observations=row["total_observations"],
                        winning_observations=row["winning_observations"],
                        losing_observations=row["losing_observations"],
                        gross_pnl_bps=row["gross_pnl_bps"],
                        net_pnl_bps=row["net_pnl_bps"],
                        max_drawdown_bps=row["max_drawdown_bps"],
                        high_water_mark_bps=row["high_water_mark_bps"],
                        avg_markout_5s_bps=row["avg_markout_5s_bps"],
                        last_observation_utc=row["last_observation_utc"],
                        suspension_reason=row["suspension_reason"],
                    )
                )
            return records

    def update_strategy_status(
        self,
        admission_id: str,
        new_status: AdmissionStatus,
        reason: str,
        operator_or_system: str = "SYSTEM",
    ) -> None:
        """Transitions strategy to a new lifecycle state with full audit trail."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM forward_strategy_registry WHERE admission_id = ?",
                (admission_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise StrategyNotFoundError(f"Strategy {admission_id} not found in registry.")

            old_status = row["status"]
            if old_status == new_status.value:
                return  # No-op

            # Update registry status
            suspension_reason = (
                reason
                if new_status
                in {AdmissionStatus.SUSPENDED, AdmissionStatus.FAILED, AdmissionStatus.QUARANTINED}
                else None
            )
            conn.execute(
                """
                UPDATE forward_strategy_registry
                SET status = ?, suspension_reason = COALESCE(?, suspension_reason), updated_at_utc = ?
                WHERE admission_id = ?
                """,
                (new_status.value, suspension_reason, now, admission_id),
            )
            conn.execute(
                "UPDATE strategy_admissions SET status = ? WHERE admission_id = ?",
                (new_status.value, admission_id),
            )

            # Record audit transition
            trans_id = f"TR-{int(now)}-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO strategy_state_transitions (
                    transition_id, admission_id, old_status, new_status, reason,
                    operator_or_system, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trans_id,
                    admission_id,
                    old_status,
                    new_status.value,
                    reason,
                    operator_or_system,
                    now,
                ),
            )
            conn.commit()

        logger.info(
            "Transitioned %s: %s -> %s (Reason: %s)",
            admission_id,
            old_status,
            new_status.value,
            reason,
        )

    # Alias for lifecycle transition
    transition_status = update_strategy_status

    def record_observation_update(
        self,
        admission_id: str,
        trade_gross_pnl_bps: float,
        trade_net_pnl_bps: float,
        is_win: bool,
        markout_5s_bps: float,
        timestamp_utc: float | None = None,
    ) -> None:
        """
        Atomically updates a strategy's forward performance metrics after an observed paper trade.
        Recomputes high-water mark, max drawdown, and running markout average.
        """
        now = timestamp_utc or time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT total_observations, winning_observations, losing_observations,
                       gross_pnl_bps, net_pnl_bps, max_drawdown_bps, high_water_mark_bps,
                       avg_markout_5s_bps
                FROM forward_strategy_registry
                WHERE admission_id = ?
                """,
                (admission_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise StrategyNotFoundError(f"Strategy {admission_id} not found in registry.")

            n = row["total_observations"] + 1
            wins = row["winning_observations"] + (1 if is_win else 0)
            losses = row["losing_observations"] + (0 if is_win else 1)
            new_gross = row["gross_pnl_bps"] + trade_gross_pnl_bps
            new_net = row["net_pnl_bps"] + trade_net_pnl_bps

            # High-water mark & drawdown
            new_hwm = max(row["high_water_mark_bps"], new_net)
            current_dd = max(0.0, new_hwm - new_net)
            new_mdd = max(row["max_drawdown_bps"], current_dd)

            # Incremental moving average for markout
            old_avg_markout = row["avg_markout_5s_bps"]
            new_avg_markout = old_avg_markout + ((markout_5s_bps - old_avg_markout) / n)

            conn.execute(
                """
                UPDATE forward_strategy_registry
                SET total_observations = ?, winning_observations = ?, losing_observations = ?,
                    gross_pnl_bps = ?, net_pnl_bps = ?, max_drawdown_bps = ?,
                    high_water_mark_bps = ?, avg_markout_5s_bps = ?,
                    last_observation_utc = ?, updated_at_utc = ?
                WHERE admission_id = ?
                """,
                (
                    n,
                    wins,
                    losses,
                    new_gross,
                    new_net,
                    new_mdd,
                    new_hwm,
                    new_avg_markout,
                    now,
                    now,
                    admission_id,
                ),
            )
            conn.commit()

    def log_suspension(
        self,
        admission_id: str,
        trigger_name: str,
        threshold_val: float,
        observed_val: float,
        details: str = "",
        policy_version: str = "v1.0",
    ) -> None:
        """Records a structured circuit-breaker suspension event into SQLite WAL."""
        now = time.time()
        susp_id = f"SUSP-{int(now)}-{uuid.uuid4().hex[:8]}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO strategy_suspension_logs (
                    suspension_id, admission_id, trigger_name, threshold_val,
                    observed_val, policy_version, details, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    susp_id,
                    admission_id,
                    trigger_name,
                    threshold_val,
                    observed_val,
                    policy_version,
                    details,
                    now,
                ),
            )
            conn.commit()

        logger.warning(
            "Logged suspension for %s: %s (Threshold: %s, Observed: %s)",
            admission_id,
            trigger_name,
            threshold_val,
            observed_val,
        )

    def get_suspension_logs(self, admission_id: str) -> list[dict[str, Any]]:
        """Retrieves immutable suspension event logs for an admission ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM strategy_suspension_logs
                WHERE admission_id = ?
                ORDER BY timestamp_utc DESC
                """,
                (admission_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def check_parameter_immutability(
        self, admission_id: str, candidate_params: dict[str, Any]
    ) -> bool:
        """
        Verifies whether candidate parameters match the admitted frozen parameter hash.
        Returns True if identical; raises ParameterImmutabilityError if altered.
        """
        admission = self.get_admission(admission_id)
        if not admission:
            raise StrategyNotFoundError(f"Strategy {admission_id} not found.")

        cand_hash = StrategyAdmission.compute_parameter_hash(candidate_params)
        if cand_hash != admission.parameter_hash:
            raise ParameterImmutabilityError(
                f"Candidate parameter hash {cand_hash} deviates from frozen hash {admission.parameter_hash} "
                f"for admission {admission_id}. Modifying parameters requires a new strategy admission."
            )
        return True
