"""
core/intelligence/hypothesis_schema.py
======================================
Canonical CausalHypothesis Schema, Experiment Plan, and SQLite Persistence Ledger.

Enforces:
1. Strict Pydantic v2 validation with deterministic JSON serialization.
2. Invariant: execution_authority is permanently NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
3. Invariant: real_capital_enabled is permanently False.
4. SQLite WAL persistence in `causal_hypotheses_ledger` with secondary indexes.
"""

from __future__ import annotations

import datetime
import json
import logging
import sqlite3
import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.database import db_manager
from core.intelligence.causal_mechanisms import ResearchFamilyId
from core.intelligence.point_in_time import PointInTimeEventContract

logger = logging.getLogger("ai_quant_sentinel.intelligence.hypothesis_schema")


class CausalHypothesisStatus(StrEnum):
    DRAFT = "DRAFT"
    FIREWALL_VALIDATED = "FIREWALL_VALIDATED"
    REJECTED = "REJECTED"
    QUEUED_FOR_LAB = "QUEUED_FOR_LAB"
    TESTING = "TESTING"
    VALIDATED = "VALIDATED"
    FALSIFIED = "FALSIFIED"
    QUARANTINED = "QUARANTINED"


class CausalHypothesis(BaseModel):
    """
    Formal, testable research hypothesis synthesizing an external macro event
    with deterministic microstructure triggers and Popperian falsification criteria.
    """

    hypothesis_id: str = Field(..., description="Unique ID: HYPO-YYYYMMDD-<uuid>")
    family_id: ResearchFamilyId = Field(..., description="Preregistered Research Family ID")
    mechanism_id: str = Field(..., description="Causal Mechanism ID")
    macro_event_contract: PointInTimeEventContract = Field(
        ..., description="Point-in-Time Event Envelope"
    )
    target_asset: str = Field("BTC/USDT", description="Target market symbol")
    timeframe: str = Field("5m", description="Observation candle resolution")
    null_hypothesis: str = Field(
        ..., description="H0: Empirical negative or zero expectancy condition"
    )
    alternative_hypothesis: str = Field(
        ..., description="H1: Proposed directional edge and minimum effect size"
    )
    microstructure_conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Exact quantitative thresholds for CVD, OBI, or SMC markers",
    )
    falsification_criteria: dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit stop criteria and conditions that falsify H1",
    )
    epistemic_prior_weight: float = Field(0.40, description="Bayesian prior weight [0.20, 1.00]")
    status: CausalHypothesisStatus = Field(
        CausalHypothesisStatus.DRAFT, description="Hypothesis lifecycle status"
    )
    rejection_reason: str | None = Field(None, description="Reason if rejected by Causal Firewall")
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Cannot execute real orders",
    )
    real_capital_enabled: Literal[False] = Field(
        False,
        description="CONSTITUTIONAL INVARIANT: Real capital routing is strictly disabled",
    )
    created_at_utc: float = Field(default_factory=time.time)
    updated_at_utc: float = Field(default_factory=time.time)

    def summary(self) -> str:
        return (
            f"[{self.hypothesis_id}] ({self.status.value}) Family: {self.family_id.value} | "
            f"Asset: {self.target_asset} ({self.timeframe}) | Mech: {self.mechanism_id}"
        )


class SynthesizedExperimentPlan(BaseModel):
    """
    Compilation artifact dispatched from Causal Compiler to Autonomous Research Lab.
    Contains parameters for walk-forward out-of-sample backtesting.
    """

    plan_id: str
    hypothesis_id: str
    family_id: str
    target_symbol: str
    timeframe: str
    backtest_range_start_utc: float
    backtest_range_end_utc: float
    frictional_tier: str = "CONSERVATIVE"
    min_oos_trades: int = 30
    required_dsr: float = 0.95
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False
    created_at_utc: float = Field(default_factory=time.time)


class HypothesisLedgerManager:
    """Manages SQLite persistence for synthesized causal hypotheses."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        return db_manager.get_connection()

    def _init_db(self) -> None:
        """Initializes the causal_hypotheses_ledger table with secondary indexes."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS causal_hypotheses_ledger (
                        hypothesis_id TEXT PRIMARY KEY,
                        family_id TEXT NOT NULL,
                        mechanism_id TEXT NOT NULL,
                        macro_event_id TEXT NOT NULL,
                        source_record_id TEXT NOT NULL,
                        target_asset TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        null_hypothesis TEXT NOT NULL,
                        alternative_hypothesis TEXT NOT NULL,
                        microstructure_conditions_json TEXT NOT NULL,
                        falsification_criteria_json TEXT NOT NULL,
                        epistemic_prior_weight REAL NOT NULL,
                        status TEXT NOT NULL,
                        rejection_reason TEXT,
                        execution_authority TEXT NOT NULL,
                        real_capital_enabled INTEGER NOT NULL,
                        event_contract_json TEXT NOT NULL,
                        created_at_utc REAL NOT NULL,
                        updated_at_utc REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_causal_hypo_family ON causal_hypotheses_ledger(family_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_causal_hypo_status ON causal_hypotheses_ledger(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_causal_hypo_asset ON causal_hypotheses_ledger(target_asset)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_causal_hypo_created ON causal_hypotheses_ledger(created_at_utc)"
                )
        finally:
            if self.db_path:
                conn.close()

    def save_hypothesis(self, hypothesis: CausalHypothesis) -> bool:
        """Persists or updates a CausalHypothesis."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO causal_hypotheses_ledger (
                        hypothesis_id, family_id, mechanism_id, macro_event_id, source_record_id,
                        target_asset, timeframe, null_hypothesis, alternative_hypothesis,
                        microstructure_conditions_json, falsification_criteria_json,
                        epistemic_prior_weight, status, rejection_reason,
                        execution_authority, real_capital_enabled, event_contract_json,
                        created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hypothesis_id) DO UPDATE SET
                        status = excluded.status,
                        rejection_reason = excluded.rejection_reason,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        hypothesis.hypothesis_id,
                        hypothesis.family_id.value,
                        hypothesis.mechanism_id,
                        hypothesis.macro_event_contract.event_id,
                        hypothesis.macro_event_contract.source_record_id,
                        hypothesis.target_asset,
                        hypothesis.timeframe,
                        hypothesis.null_hypothesis,
                        hypothesis.alternative_hypothesis,
                        json.dumps(hypothesis.microstructure_conditions),
                        json.dumps(hypothesis.falsification_criteria),
                        hypothesis.epistemic_prior_weight,
                        hypothesis.status.value,
                        hypothesis.rejection_reason,
                        hypothesis.execution_authority,
                        0,  # real_capital_enabled permanently 0
                        json.dumps(hypothesis.macro_event_contract.model_dump()),
                        hypothesis.created_at_utc,
                        hypothesis.updated_at_utc,
                    ),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to save hypothesis {hypothesis.hypothesis_id}: {e}")
            return False
        finally:
            if self.db_path:
                conn.close()

    def get_hypothesis(self, hypothesis_id: str) -> CausalHypothesis | None:
        """Loads a hypothesis by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM causal_hypotheses_ledger WHERE hypothesis_id = ?",
                (hypothesis_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_hypothesis(row)
        finally:
            if self.db_path:
                conn.close()

    def list_hypotheses(
        self,
        family_id: str | None = None,
        status: str | None = None,
        target_asset: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CausalHypothesis], int]:
        """Lists hypotheses matching filters with total count."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM causal_hypotheses_ledger WHERE 1=1"
            params: list[Any] = []

            if family_id:
                query += " AND family_id = ?"
                params.append(family_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            if target_asset:
                query += " AND target_asset = ?"
                params.append(target_asset)

            count_query = query.replace("SELECT *", "SELECT COUNT(*)")
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            query += " ORDER BY created_at_utc DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            items = [self._row_to_hypothesis(row) for row in rows]
            return items, total
        finally:
            if self.db_path:
                conn.close()

    def update_status(
        self,
        hypothesis_id: str,
        new_status: CausalHypothesisStatus,
        rejection_reason: str | None = None,
    ) -> bool:
        """Updates hypothesis status and timestamp."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE causal_hypotheses_ledger
                    SET status = ?, rejection_reason = ?, updated_at_utc = ?
                    WHERE hypothesis_id = ?
                    """,
                    (new_status.value, rejection_reason, time.time(), hypothesis_id),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update status for {hypothesis_id}: {e}")
            return False
        finally:
            if self.db_path:
                conn.close()

    def count_family_trials_today(self, family_id: str) -> int:
        """Returns the number of hypotheses generated in the current UTC calendar day."""
        today_start = (
            datetime.datetime.now(datetime.UTC)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM causal_hypotheses_ledger
                WHERE family_id = ? AND created_at_utc >= ?
                """,
                (family_id, today_start),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            if self.db_path:
                conn.close()

    def _row_to_hypothesis(self, row: Any) -> CausalHypothesis:
        """Converts an SQLite row to a CausalHypothesis instance."""
        event_dict = json.loads(row["event_contract_json"])
        event_contract = PointInTimeEventContract(**event_dict)

        return CausalHypothesis(
            hypothesis_id=row["hypothesis_id"],
            family_id=ResearchFamilyId(row["family_id"]),
            mechanism_id=row["mechanism_id"],
            macro_event_contract=event_contract,
            target_asset=row["target_asset"],
            timeframe=row["timeframe"],
            null_hypothesis=row["null_hypothesis"],
            alternative_hypothesis=row["alternative_hypothesis"],
            microstructure_conditions=json.loads(row["microstructure_conditions_json"]),
            falsification_criteria=json.loads(row["falsification_criteria_json"]),
            epistemic_prior_weight=row["epistemic_prior_weight"],
            status=CausalHypothesisStatus(row["status"]),
            rejection_reason=row["rejection_reason"],
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )


# Global singleton ledger manager
global_hypothesis_ledger = HypothesisLedgerManager()
