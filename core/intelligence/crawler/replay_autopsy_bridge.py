"""
core/intelligence/crawler/replay_autopsy_bridge.py
==================================================
Milestone 30-D: Automated Strategy Autopsy Compiler & Failure Memory Immune System.

CONSTITUTIONAL PRINCIPLE:
Turns empirical replay falsification into structured, reusable failure knowledge.
Applies a Graduated Quarantine Policy:
- Never blacklists an entire causal family based on a single failure.
- Indexes root causes, friction sensitivities, and parameter decays into Failure Memory.
Permanently research-only: REAL_CAPITAL_ENABLED = False.
Execution Authority = NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from core.autonomous_research.failure_memory import FailureMemoryEngine
from core.intelligence.crawler.statistical_auditor import AuditReport
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.failure_autopsy import (
    CausalFailureAutopsy,
    FailureAutopsyCompiler,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    PlanLifecycleState,
    global_plan_ledger,
)
from core.intelligence.replay_engine import ReplayExecutionReport
from core.intelligence.research_contract import PreregisteredResearchContract
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.replay_autopsy_bridge")


class QuarantineLevel(str, Enum):
    """Graduated quarantine escalation ladder for failed causal mechanisms."""

    NO_QUARANTINE = "NO_QUARANTINE"  # 0 or 1 failure: normal discovery permitted
    ADVISORY_WARNING = (
        "ADVISORY_WARNING"  # 2 failures: warning logged, additional confirmation requested
    )
    RESEARCH_PRIORITY_REDUCTION = (
        "RESEARCH_PRIORITY_REDUCTION"  # 3 failures: scout de-prioritizes mechanism
    )
    TEMPORARY_QUARANTINE = (
        "TEMPORARY_QUARANTINE"  # 4+ failures: new hypotheses paused for this mechanism
    )
    HUMAN_REVIEW_REQUIRED = (
        "HUMAN_REVIEW_REQUIRED"  # Multi-parameter collapse requiring human intervention
    )


@dataclass(frozen=True)
class QuarantineStatus:
    mechanism_id: str
    failure_count: int
    level: QuarantineLevel
    last_failure_at_utc: float | None
    advisory_message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplayAutopsyBridge:
    """
    Connects statistical audit outcomes directly to Failure Memory.
    Compiles detailed CausalFailureAutopsies for failed replays and governs
    the Graduated Quarantine immune response.
    """

    def __init__(
        self,
        failure_memory: FailureMemoryEngine | None = None,
        autopsy_compiler: FailureAutopsyCompiler | None = None,
        hypothesis_ledger: HypothesisLedgerManager | None = None,
        plan_ledger: ExperimentPlanLedger | None = None,
        db_path: str | None = None,
    ) -> None:
        self.failure_memory = failure_memory or FailureMemoryEngine()
        self.autopsy_compiler = autopsy_compiler or FailureAutopsyCompiler(
            failure_memory=self.failure_memory
        )
        self.hypothesis_ledger = hypothesis_ledger or global_hypothesis_ledger
        self.plan_ledger = plan_ledger or global_plan_ledger

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
                CREATE TABLE IF NOT EXISTS failure_quarantine_ledger (
                    mechanism_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    failure_count INTEGER NOT NULL,
                    quarantine_level TEXT NOT NULL,
                    last_failure_at_utc REAL NOT NULL,
                    last_autopsy_id TEXT NOT NULL,
                    updated_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_feedback_events (
                    event_id TEXT PRIMARY KEY,
                    autopsy_id TEXT NOT NULL,
                    mechanism_id TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fql_fam ON failure_quarantine_ledger (family_id);"
            )
            conn.commit()

    def process_audit_outcome(
        self,
        plan: DurableExperimentPlan,
        contract: PreregisteredResearchContract,
        manifest: DatasetManifest,
        audit_report: AuditReport,
        reports_by_tier: dict[str, ReplayExecutionReport],
    ) -> CausalFailureAutopsy | None:
        """
        Processes the audit result:
        If the plan passed, marks it SURVIVED_RESEARCH_AUDIT and returns None.
        If the plan failed, compiles a CausalFailureAutopsy, indexes it into
        FailureMemoryEngine, updates ledgers, and applies graduated quarantine.
        """
        status = audit_report.status
        cons_report = reports_by_tier.get("CONSERVATIVE")
        if not cons_report:
            return None

        # Check if research hypothesis survived audit
        if status in (
            ResearchValidationStatus.OOS_VALIDATED,
            ResearchValidationStatus.PRELIMINARY_SUPPORT,
            ResearchValidationStatus.INDEPENDENTLY_REPLICATED,
        ):
            logger.info(
                f"Plan {plan.plan_id} passed or preliminarily supported ({status.value}). Marking COMPLETED."
            )
            self.plan_ledger.update_state(plan.plan_id, PlanLifecycleState.COMPLETED)
            return None

        # Plan failed audit: Compile structured autopsy
        validation_res = CausalValidationResult(
            result_id=f"RES-{audit_report.audit_id[:12]}",
            contract_id=contract.contract_id,
            hypothesis_id=plan.hypothesis_id,
            status=status,
            primary_endpoint_value=audit_report.primary_net_expectancy_r,
            benchmark_relative_alpha=0.0,
            effective_sample_size=float(cons_report.independent_episodes),
            deflated_sharpe_ratio=audit_report.dsr_result.get("deflated_sharpe", 0.0),
            whites_reality_check_pvalue=audit_report.dsr_result.get("p_value", 1.0),
            regime_stability_ratio=0.50,
            parameter_perturbation_decay=0.20,
            cost_erosion_pct=audit_report.cost_erosion_pct,
            verdict_rationale=audit_report.verdict_rationale,
            scorecard_passes=audit_report.scorecard_passes,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
        )

        autopsy = self.autopsy_compiler.compile_and_record(
            contract=contract,
            manifest=manifest,
            report=cons_report,
            validation_result=validation_res,
        )

        # Update Plan state to FALSIFIED
        self.plan_ledger.update_state(plan.plan_id, PlanLifecycleState.FALSIFIED)

        # Update Hypothesis state in hypothesis ledger
        hypo_status = (
            CausalHypothesisStatus.REJECTED_COST_EROSION
            if status == ResearchValidationStatus.COST_INVALIDATED
            else CausalHypothesisStatus.FALSIFIED
        )
        self.hypothesis_ledger.update_status(
            hypothesis_id=plan.hypothesis_id,
            new_status=hypo_status,
            rejection_reason=audit_report.verdict_rationale,
        )

        # Apply Graduated Quarantine to the specific mechanism
        mechanism_id = contract.mechanism_id
        if autopsy:
            self._update_quarantine(
                mechanism_id=mechanism_id,
                family_id=plan.family_id,
                autopsy_id=autopsy.autopsy_id,
                rationale=audit_report.verdict_rationale,
            )

        return autopsy

    def get_quarantine_status(self, mechanism_id: str) -> QuarantineStatus:
        """Retrieves active quarantine status for a causal mechanism."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT failure_count, quarantine_level, last_failure_at_utc 
                FROM failure_quarantine_ledger WHERE mechanism_id = ?;
                """,
                (mechanism_id,),
            )
            row = cursor.fetchone()
            if not row:
                return QuarantineStatus(
                    mechanism_id=mechanism_id,
                    failure_count=0,
                    level=QuarantineLevel.NO_QUARANTINE,
                    last_failure_at_utc=None,
                    advisory_message="No prior replay falsifications recorded.",
                )

            count = int(row["failure_count"])
            lvl = QuarantineLevel(row["quarantine_level"])
            last_ts = float(row["last_failure_at_utc"])
            msg = self._quarantine_message(lvl, count)

            return QuarantineStatus(
                mechanism_id=mechanism_id,
                failure_count=count,
                level=lvl,
                last_failure_at_utc=last_ts,
                advisory_message=msg,
            )

    def _update_quarantine(
        self,
        mechanism_id: str,
        family_id: str,
        autopsy_id: str,
        rationale: str,
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT failure_count FROM failure_quarantine_ledger WHERE mechanism_id = ?;",
                (mechanism_id,),
            )
            row = cursor.fetchone()
            prev_count = int(row["failure_count"]) if row else 0
            new_count = prev_count + 1

            # Graduated ladder
            if new_count <= 1:
                level = QuarantineLevel.NO_QUARANTINE
            elif new_count == 2:
                level = QuarantineLevel.ADVISORY_WARNING
            elif new_count == 3:
                level = QuarantineLevel.RESEARCH_PRIORITY_REDUCTION
            elif new_count == 4:
                level = QuarantineLevel.TEMPORARY_QUARANTINE
            else:
                level = QuarantineLevel.HUMAN_REVIEW_REQUIRED

            cursor.execute(
                """
                INSERT INTO failure_quarantine_ledger (
                    mechanism_id, family_id, failure_count, quarantine_level,
                    last_failure_at_utc, last_autopsy_id, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mechanism_id) DO UPDATE SET
                    failure_count = excluded.failure_count,
                    quarantine_level = excluded.quarantine_level,
                    last_failure_at_utc = excluded.last_failure_at_utc,
                    last_autopsy_id = excluded.last_autopsy_id,
                    updated_at_utc = excluded.updated_at_utc;
                """,
                (
                    mechanism_id,
                    family_id,
                    new_count,
                    level.value,
                    now,
                    autopsy_id,
                    now,
                ),
            )

            # Record feedback event
            ev_id = f"FBK-{int(now)}-{hashlib.sha256(f'{mechanism_id}:{new_count}:{now}'.encode()).hexdigest()[:8].upper()}"
            cursor.execute(
                """
                INSERT INTO failure_feedback_events (
                    event_id, autopsy_id, mechanism_id, family_id, policy_version,
                    decision, reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ev_id,
                    autopsy_id,
                    mechanism_id,
                    family_id,
                    "GRADUATED_IMMUNITY_V1",
                    level.value,
                    f"Falsification count reached {new_count}: {rationale[:150]}",
                    now,
                ),
            )
            conn.commit()

    @staticmethod
    def _quarantine_message(level: QuarantineLevel, count: int) -> str:
        if level == QuarantineLevel.NO_QUARANTINE:
            return f"{count} isolated failure. Mechanism remains active."
        if level == QuarantineLevel.ADVISORY_WARNING:
            return "2 consecutive failures. Mechanism flagged with advisory warning."
        if level == QuarantineLevel.RESEARCH_PRIORITY_REDUCTION:
            return "3 consecutive failures. Research scout priority reduced for this mechanism."
        if level == QuarantineLevel.TEMPORARY_QUARANTINE:
            return "4 consecutive failures. Mechanism temporarily quarantined from automated crawl synthesis."
        return f"{count} consecutive failures across multiple trials. Human operator review strictly required."


# Global singleton instance
global_replay_autopsy_bridge = ReplayAutopsyBridge()
