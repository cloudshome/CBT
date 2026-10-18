"""
core/intelligence/plan_store.py
===============================
Durable Experiment Plan Store & Lifecycle State Machine for Milestone 29.

Closes the Milestone 28 Dispatch Gap by providing:
1. Dedicated SQLite table `experiment_plans_ledger` in `data/brain_memory.db`.
2. Immutable plan ID with cryptographic SHA-256 payload integrity.
3. Canonical serialization and deterministic JSON persistence.
4. Hypothesis lineage tracking (`hypothesis_id`, `family_id`, `target_symbol`).
5. Idempotent dispatch and atomic state transitions:
   QUEUED -> EXECUTING -> COMPLETED / FALSIFIED / CANCELLED.
6. Restart-safe crash recovery and pending queue retrieval.
7. Strict constitutional invariants:
   execution_authority = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
   real_capital_enabled = False
8. Zero execution-router imports or trading authority.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.intelligence.plan_store")


class PlanTamperingError(ValueError):
    """Raised when an experiment plan's payload or parameters fail cryptographic verification."""


class PlanLifecycleState(StrEnum):
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FALSIFIED = "FALSIFIED"
    CANCELLED = "CANCELLED"


# Backward-compatible alias
ExperimentPlanStatus = PlanLifecycleState


class DurableExperimentPlan(BaseModel):
    """
    Immutable research experiment plan persisted durably in SQLite.
    Guarantees hypothesis lineage and cryptographic payload integrity.
    """

    plan_id: str = Field(..., description="Unique immutable plan ID: PLAN-<timestamp>-<hash>")
    hypothesis_id: str = Field(..., description="Lineage reference to CausalHypothesis")
    family_id: str = Field(..., description="Preregistered Research Family ID")
    target_symbol: str = Field("BTC/USDT", description="Target market asset")
    timeframe: str = Field("5m", description="Bar aggregation timeframe")
    backtest_range_start_utc: float = Field(
        ..., description="Chronological start timestamp (seconds)"
    )
    backtest_range_end_utc: float = Field(..., description="Chronological end timestamp (seconds)")
    lookback_days: int = Field(90, description="Dynamic lookback duration in days")
    frictional_tier: str = Field("CONSERVATIVE", description="BASE, CONSERVATIVE, or STRESS")
    min_oos_trades: int = Field(30, description="Minimum out-of-sample trades required")
    required_dsr: float = Field(0.95, description="Deflated Sharpe Ratio hurdle")
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Cannot route orders",
    )
    real_capital_enabled: Literal[False] = Field(
        False,
        description="CONSTITUTIONAL INVARIANT: Real capital routing is strictly prohibited",
    )
    plan_hash_sha256: str = Field(
        ..., description="Cryptographic SHA-256 of canonical plan specification"
    )
    state: PlanLifecycleState = Field(PlanLifecycleState.QUEUED, description="Lifecycle state")
    created_at_utc: float = Field(default_factory=time.time)
    updated_at_utc: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Contract and replay metadata"
    )

    @classmethod
    def create(
        cls,
        hypothesis_id: str,
        family_id: str,
        target_symbol: str,
        timeframe: str,
        backtest_range_start_utc: float,
        backtest_range_end_utc: float,
        lookback_days: int = 90,
        frictional_tier: str = "CONSERVATIVE",
        min_oos_trades: int = 30,
        required_dsr: float = 0.95,
        metadata: dict[str, Any] | None = None,
    ) -> DurableExperimentPlan:
        """Constructs a DurableExperimentPlan with deterministic SHA-256 integrity hash."""
        now = time.time()
        meta = metadata or {}
        canonical_str = (
            f"{hypothesis_id}:{family_id}:{target_symbol}:{timeframe}:"
            f"{backtest_range_start_utc:.3f}:{backtest_range_end_utc:.3f}:{lookback_days}:"
            f"{frictional_tier}:{min_oos_trades}:{required_dsr:.2f}"
        )
        plan_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        plan_id = f"PLAN-{int(now)}-{plan_hash[:10].upper()}"

        return cls(
            plan_id=plan_id,
            hypothesis_id=hypothesis_id,
            family_id=family_id,
            target_symbol=target_symbol,
            timeframe=timeframe,
            backtest_range_start_utc=backtest_range_start_utc,
            backtest_range_end_utc=backtest_range_end_utc,
            lookback_days=lookback_days,
            frictional_tier=frictional_tier,
            min_oos_trades=min_oos_trades,
            required_dsr=required_dsr,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            plan_hash_sha256=plan_hash,
            state=PlanLifecycleState.QUEUED,
            created_at_utc=now,
            updated_at_utc=now,
            metadata=meta,
        )

    def compute_hash(self) -> str:
        """Calculates deterministic SHA-256 hash across canonical parameters."""
        canonical_str = (
            f"{self.hypothesis_id}:{self.family_id}:{self.target_symbol}:{self.timeframe}:"
            f"{self.backtest_range_start_utc:.3f}:{self.backtest_range_end_utc:.3f}:{self.lookback_days}:"
            f"{self.frictional_tier}:{self.min_oos_trades}:{self.required_dsr:.2f}"
        )
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Verifies cryptographic hash of plan specification."""
        expected = self.compute_hash()
        if self.plan_hash_sha256 != expected:
            raise PlanTamperingError(
                f"PLAN_TAMPERING_DETECTED: expected {expected}, got {self.plan_hash_sha256}"
            )
        return True

    @classmethod
    def from_hypothesis(
        cls,
        hypothesis: Any,
        lookback_days: int = 90,
        frictional_tier: str = "CONSERVATIVE",
        timeframe: str = "5m",
        min_oos_trades: int = 30,
        required_dsr: float = 0.95,
    ) -> DurableExperimentPlan:
        """Builds a DurableExperimentPlan from a CausalHypothesis."""
        now = time.time()
        start_utc = now - (lookback_days * 86400.0)
        end_utc = now
        hypo_id = getattr(hypothesis, "hypothesis_id", str(hypothesis))
        family_id = getattr(hypothesis, "family_id", "MACRO_LIQUIDITY_SURGE")
        if hasattr(family_id, "value"):
            family_id = family_id.value
        candidate_asset = getattr(hypothesis, "candidate_asset", "BTC/USDT")
        meta = {
            "predicted_direction": getattr(hypothesis, "predicted_direction", "LONG"),
            "mechanism_id": getattr(hypothesis, "mechanism_id", "UNKNOWN"),
        }
        return cls.create(
            hypothesis_id=hypo_id,
            family_id=str(family_id),
            target_symbol=candidate_asset,
            timeframe=timeframe,
            backtest_range_start_utc=start_utc,
            backtest_range_end_utc=end_utc,
            lookback_days=lookback_days,
            frictional_tier=frictional_tier,
            min_oos_trades=min_oos_trades,
            required_dsr=required_dsr,
            metadata=meta,
        )


class ExperimentPlanLedger:
    """Manages SQLite persistence and atomic state transitions for DurableExperimentPlan."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self._init_db()

    def record_plan(self, plan: DurableExperimentPlan) -> bool:
        """Alias for save_plan."""
        return self.save_plan(plan)

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        return db_manager.get_connection()

    def _init_db(self) -> None:
        """Initializes the experiment_plans_ledger table with secondary indexes."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS experiment_plans_ledger (
                        plan_id TEXT PRIMARY KEY,
                        hypothesis_id TEXT NOT NULL,
                        family_id TEXT NOT NULL,
                        target_symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        backtest_range_start_utc REAL NOT NULL,
                        backtest_range_end_utc REAL NOT NULL,
                        lookback_days INTEGER NOT NULL,
                        frictional_tier TEXT NOT NULL,
                        min_oos_trades INTEGER NOT NULL,
                        required_dsr REAL NOT NULL,
                        execution_authority TEXT NOT NULL,
                        real_capital_enabled INTEGER NOT NULL,
                        plan_hash_sha256 TEXT NOT NULL,
                        state TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        created_at_utc REAL NOT NULL,
                        updated_at_utc REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_plan_hypo ON experiment_plans_ledger(hypothesis_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_plan_state ON experiment_plans_ledger(state)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_plan_family ON experiment_plans_ledger(family_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_plan_created ON experiment_plans_ledger(created_at_utc)"
                )
        finally:
            if self.db_path:
                conn.close()

    def save_plan(self, plan: DurableExperimentPlan) -> bool:
        """Persists or updates an experiment plan idempotently."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO experiment_plans_ledger (
                        plan_id, hypothesis_id, family_id, target_symbol, timeframe,
                        backtest_range_start_utc, backtest_range_end_utc, lookback_days,
                        frictional_tier, min_oos_trades, required_dsr,
                        execution_authority, real_capital_enabled, plan_hash_sha256,
                        state, plan_json, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(plan_id) DO UPDATE SET
                        state = excluded.state,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        plan.plan_id,
                        plan.hypothesis_id,
                        plan.family_id,
                        plan.target_symbol,
                        plan.timeframe,
                        plan.backtest_range_start_utc,
                        plan.backtest_range_end_utc,
                        plan.lookback_days,
                        plan.frictional_tier,
                        plan.min_oos_trades,
                        plan.required_dsr,
                        plan.execution_authority,
                        0,  # real_capital_enabled permanently 0
                        plan.plan_hash_sha256,
                        plan.state.value,
                        json.dumps(plan.model_dump()),
                        plan.created_at_utc,
                        plan.updated_at_utc,
                    ),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to persist experiment plan {plan.plan_id}: {e}")
            return False
        finally:
            if self.db_path:
                conn.close()

    def get_plan(self, plan_id: str) -> DurableExperimentPlan | None:
        """Loads an experiment plan by plan_id."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plan_json FROM experiment_plans_ledger WHERE plan_id = ?",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["plan_json"])
            return DurableExperimentPlan(**data)
        finally:
            if self.db_path:
                conn.close()

    def get_plan_by_hypothesis(self, hypothesis_id: str) -> DurableExperimentPlan | None:
        """Loads the most recent experiment plan for a given hypothesis."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT plan_json FROM experiment_plans_ledger 
                WHERE hypothesis_id = ? 
                ORDER BY created_at_utc DESC LIMIT 1
                """,
                (hypothesis_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["plan_json"])
            return DurableExperimentPlan(**data)
        finally:
            if self.db_path:
                conn.close()

    def update_state(self, plan_id: str, new_state: PlanLifecycleState) -> bool:
        """Atomically transitions plan state."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE experiment_plans_ledger 
                    SET state = ?, updated_at_utc = ? 
                    WHERE plan_id = ?
                    """,
                    (new_state.value, time.time(), plan_id),
                )
                if cursor.rowcount > 0:
                    # Also update plan_json so stored model stays consistent
                    cursor.execute(
                        "SELECT plan_json FROM experiment_plans_ledger WHERE plan_id = ?",
                        (plan_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        data = json.loads(row[0] if isinstance(row, tuple) else row["plan_json"])
                        data["state"] = new_state.value
                        data["updated_at_utc"] = time.time()
                        cursor.execute(
                            "UPDATE experiment_plans_ledger SET plan_json = ? WHERE plan_id = ?",
                            (json.dumps(data), plan_id),
                        )
                    return True
                return False
        except sqlite3.Error as e:
            logger.error(f"Failed to update plan state {plan_id} -> {new_state}: {e}")
            return False
        finally:
            if self.db_path:
                conn.close()

    def list_plans(
        self,
        state: PlanLifecycleState | None = None,
        family_id: str | None = None,
        limit: int = 50,
    ) -> list[DurableExperimentPlan]:
        """Lists plans filtered by state and family."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT plan_json FROM experiment_plans_ledger WHERE 1=1"
            params: list[Any] = []
            if state:
                query += " AND state = ?"
                params.append(state.value)
            if family_id:
                query += " AND family_id = ?"
                params.append(family_id)
            query += " ORDER BY created_at_utc DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            results: list[DurableExperimentPlan] = []
            for row in cursor.fetchall():
                data = json.loads(row[0] if isinstance(row, tuple) else row["plan_json"])
                results.append(DurableExperimentPlan(**data))
            return results
        finally:
            if self.db_path:
                conn.close()

    def get_pending_queue(self) -> list[DurableExperimentPlan]:
        """Restart-safe recovery: retrieves all plans currently in QUEUED state."""
        return self.list_plans(state=PlanLifecycleState.QUEUED, limit=100)


# Global singleton instance
global_plan_ledger = ExperimentPlanLedger()
