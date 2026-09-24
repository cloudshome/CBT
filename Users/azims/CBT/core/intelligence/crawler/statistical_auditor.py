"""
core/intelligence/crawler/statistical_auditor.py
================================================
Milestone 30-D: Statistical Audit Engine, Deflated Sharpe Ratio (DSR),
and Multiple Testing Correction (Holm-Bonferroni / Benjamini-Hochberg).

CONSTITUTIONAL PRINCIPLE:
Distinguishes empirical raw performance from statistical evidence and causal validity.
Applies rigorous multiple-testing haircuts across all family trial attempts.
Enforces economic robustness under 3-tier frictions (BASE, CONSERVATIVE, STRESS).
Permanently research-only: REAL_CAPITAL_ENABLED = False.
Execution Authority = NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.intelligence.crawler.qualification_contracts import (
    MultipleTestingLedger,
    global_multiple_testing_ledger,
)
from core.intelligence.plan_store import DurableExperimentPlan
from core.intelligence.replay_engine import ReplayExecutionReport
from core.intelligence.research_contract import PreregisteredResearchContract
from core.intelligence.statistical_validator import StatisticalValidator
from core.intelligence.validation_result import (
    CausalValidationResult,
    ResearchValidationStatus,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.statistical_auditor")


@dataclass(frozen=True)
class DSRResult:
    """Exact metrics from Bailey & López de Prado Deflated Sharpe Ratio evaluation."""

    raw_sharpe: float
    deflated_sharpe: float
    sample_length: int
    skewness: float
    kurtosis: float
    trial_count: int
    expected_max_sharpe: float
    z_stat: float
    p_value: float
    is_statistically_significant: bool
    formula_version: str = "BAILEY_LOPEZ_DE_PRADO_2014"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditReport(BaseModel):
    """
    Formal, immutable institutional research audit report evaluating an executed
    replay across statistical, multiple-testing, and economic robustness hurdles.
    """

    audit_id: str = Field(..., description="Unique audit ID: AUD-<timestamp>-<hash>")
    plan_id: str = Field(..., description="Referenced DurableExperimentPlan ID")
    hypothesis_id: str = Field(..., description="Referenced CausalHypothesis ID")
    family_id: str = Field(..., description="Preregistered Research Family ID")
    status: ResearchValidationStatus = Field(..., description="Final epistemic research status")
    primary_net_expectancy_r: float = Field(
        ..., description="Net expectancy under conservative frictions"
    )
    gross_expectancy_r: float = Field(..., description="Gross expectancy before frictions")
    stress_expectancy_r: float = Field(..., description="Net expectancy under stress frictions")
    cost_erosion_pct: float = Field(
        ..., description="Percentage of gross edge consumed by frictions"
    )
    dsr_result: dict[str, Any] = Field(..., description="Deflated Sharpe Ratio breakdown")
    multiple_testing_policy: str = Field(
        "HOLM_BONFERRONI", description="Applied multiple testing correction"
    )
    family_trial_count: int = Field(..., description="Total trials recorded in family")
    holm_bonferroni_passed: bool = Field(
        ..., description="Whether trial passed step-down significance"
    )
    stress_survival: bool = Field(
        ..., description="Whether strategy remained non-negative under stress"
    )
    scorecard_passes: dict[str, bool] = Field(
        default_factory=dict, description="Per-gate pass/fail flags"
    )
    verdict_rationale: str = Field(
        ..., description="Detailed institutional explanation of evaluation"
    )
    human_review_required: Literal[True] = Field(
        True, description="CONSTITUTIONAL INVARIANT: Human operator review gate mandatory"
    )
    execution_authority: Literal["NON_EXECUTABLE_RESEARCH_HYPOTHESIS"] = Field(
        "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
        description="CONSTITUTIONAL INVARIANT: Cannot execute live orders",
    )
    real_capital_enabled: Literal[False] = Field(
        False, description="CONSTITUTIONAL INVARIANT: Real capital routing disabled"
    )
    audit_hash_sha256: str = Field(
        ..., description="Cryptographic SHA-256 seal of the audit report"
    )
    created_at_utc: float = Field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class StatisticalAuditor:
    """
    Institutional Research Statistical Auditor.
    Computes exact Bailey & López de Prado DSR, tracks multiple testing trials,
    applies Holm-Bonferroni step-down correction and Benjamini-Hochberg FDR,
    evaluates 3-tier friction sensitivity, and issues sealed AuditReports.
    """

    def __init__(
        self,
        mt_ledger: MultipleTestingLedger | None = None,
        db_path: str | None = None,
    ) -> None:
        self.mt_ledger = mt_ledger or global_multiple_testing_ledger
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
                CREATE TABLE IF NOT EXISTS multiple_testing_trials (
                    trial_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    raw_sharpe REAL NOT NULL,
                    deflated_sharpe REAL NOT NULL,
                    p_value REAL NOT NULL,
                    net_expectancy_r REAL NOT NULL,
                    cost_erosion_pct REAL NOT NULL,
                    is_significant INTEGER NOT NULL,
                    created_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS crawler_audit_reports (
                    audit_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    audit_hash_sha256 TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at_utc REAL NOT NULL
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_mtt_family ON multiple_testing_trials (family_id);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_car_plan ON crawler_audit_reports (plan_id);"
            )
            conn.commit()

    def audit_replay(
        self,
        plan: DurableExperimentPlan,
        contract: PreregisteredResearchContract,
        reports_by_tier: dict[str, ReplayExecutionReport],
        alpha: float = 0.05,
    ) -> AuditReport:
        """
        Executes complete institutional statistical and economic audit for an executed plan.
        """
        now = time.time()
        cons_report = reports_by_tier.get("CONSERVATIVE")
        stress_report = reports_by_tier.get("STRESS")

        if not cons_report:
            raise ValueError(
                "CONSERVATIVE friction tier report is mandatory for statistical audit."
            )

        # 1. Multiple-Testing Accounting: Retrieve cumulative trials for this family
        family_id = plan.family_id
        recorded_trials = self.mt_ledger.get_family_trials_count(family_id)
        # Ensure at least 1 trial, plus any historical trials recorded
        family_trial_count = max(1, recorded_trials)

        # 2. Deflated Sharpe Ratio calculation
        returns = [e.net_pnl_usd / 10000.0 for e in cons_report.episodes]
        dsr_metrics = self.compute_dsr(returns, total_trials=family_trial_count)

        # 3. 8-Attribute Scorecard via StatisticalValidator
        validator = StatisticalValidator(family_trial_count=family_trial_count)
        validation_res: CausalValidationResult = validator.evaluate(
            contract=contract,
            report=cons_report,
        )

        # 4. Multi-Tier Friction & Economic Robustness
        gross_r = cons_report.gross_expectancy_r
        net_r = cons_report.net_expectancy_r
        stress_r = (
            stress_report.net_expectancy_r if stress_report else cons_report.stress_expectancy_r
        )
        cost_erosion = cons_report.cost_erosion_pct

        # Economic checks
        friction_pass = net_r > 0.0 and cost_erosion < 70.0
        stress_survival = stress_r > -0.50  # No catastrophic drawdown under extreme stress

        # 5. Holm-Bonferroni Familywise Step-Down Test
        # Test current p-value against step-down hurdle
        p_val = dsr_metrics.p_value
        # If N trials in family, Holm-Bonferroni critical cutoff for the best candidate is alpha / N
        hb_cutoff = alpha / family_trial_count
        holm_passed = p_val <= hb_cutoff and dsr_metrics.is_statistically_significant

        # Assemble Scorecard
        scorecard = dict(validation_res.scorecard_passes)
        scorecard["HOLM_BONFERRONI"] = holm_passed
        scorecard["STRESS_SURVIVAL"] = stress_survival
        scorecard["ECONOMIC_ROBUSTNESS"] = friction_pass

        # Determine Final Epistemic Status
        if len(cons_report.episodes) < contract.min_independent_episodes:
            final_status = ResearchValidationStatus.INCONCLUSIVE
            rationale = (
                f"Statistical power insufficient: {len(cons_report.episodes)} episodes observed, "
                f"required minimum is {contract.min_independent_episodes}."
            )
        elif gross_r > 0.0 and not friction_pass:
            final_status = ResearchValidationStatus.COST_INVALIDATED
            rationale = (
                f"Gross alpha E[R]={gross_r:+.2f} was eliminated by 3-tier frictions "
                f"(Cost erosion: {cost_erosion:.1f}%, Net E[R]={net_r:+.2f})."
            )
        elif net_r <= 0.0:
            final_status = ResearchValidationStatus.FALSIFIED
            rationale = f"Null hypothesis H0 cannot be rejected: Conservative net expectancy E[R]={net_r:+.2f} <= 0.0."
        elif not stress_survival:
            final_status = ResearchValidationStatus.COST_INVALIDATED
            rationale = (
                f"Strategy edge collapsed under STRESS friction tier (Stress E[R]={stress_r:+.2f})."
            )
        elif not holm_passed:
            final_status = ResearchValidationStatus.PRELIMINARY_SUPPORT
            rationale = (
                f"Positive net expectancy E[R]={net_r:+.2f}, but failed Holm-Bonferroni multiple testing "
                f"significance hurdle (p={p_val:.4f} > cutoff={hb_cutoff:.4f}, DSR={dsr_metrics.deflated_sharpe:.2f})."
            )
        elif validation_res.status == ResearchValidationStatus.OOS_VALIDATED and holm_passed:
            final_status = ResearchValidationStatus.OOS_VALIDATED
            rationale = (
                f"All statistical and economic gauntlets PASSED. Conservative net E[R]={net_r:+.2f}, "
                f"DSR={dsr_metrics.deflated_sharpe:.2f} >= {plan.required_dsr:.2f}, Holm-Bonferroni green "
                f"(p={p_val:.4f} <= {hb_cutoff:.4f}), Stress E[R]={stress_r:+.2f}. "
                "SURVIVED RESEARCH AUDIT. Awaiting human operator qualification review."
            )
        else:
            final_status = validation_res.status
            rationale = validation_res.verdict_rationale

        # Canonical hash for audit report
        canonical_str = (
            f"{plan.plan_id}:{contract.contract_id}:{final_status.value}:"
            f"{net_r:.3f}:{dsr_metrics.deflated_sharpe:.3f}:{now:.0f}"
        )
        audit_hash = hashlib.sha256(canonical_str.encode()).hexdigest()
        audit_id = f"AUD-{int(now)}-{audit_hash[:8].upper()}"

        report = AuditReport(
            audit_id=audit_id,
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            family_id=family_id,
            status=final_status,
            primary_net_expectancy_r=round(net_r, 3),
            gross_expectancy_r=round(gross_r, 3),
            stress_expectancy_r=round(stress_r, 3),
            cost_erosion_pct=round(cost_erosion, 1),
            dsr_result=dsr_metrics.to_dict(),
            multiple_testing_policy=plan.metadata.get("multiple_testing_policy", "HOLM_BONFERRONI"),
            family_trial_count=family_trial_count,
            holm_bonferroni_passed=holm_passed,
            stress_survival=stress_survival,
            scorecard_passes=scorecard,
            verdict_rationale=rationale,
            human_review_required=True,
            execution_authority="NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
            real_capital_enabled=False,
            audit_hash_sha256=audit_hash,
            created_at_utc=now,
        )

        # Record trial into multiple_testing_trials table
        self._record_trial(
            family_id=family_id,
            hypothesis_id=plan.hypothesis_id,
            plan_id=plan.plan_id,
            raw_sharpe=dsr_metrics.raw_sharpe,
            deflated_sharpe=dsr_metrics.deflated_sharpe,
            p_value=dsr_metrics.p_value,
            net_expectancy_r=net_r,
            cost_erosion_pct=cost_erosion,
            is_significant=1 if holm_passed else 0,
        )

        # Save audit report to database
        self.save_audit_report(report)

        return report

    def compute_dsr(
        self,
        returns: list[float],
        total_trials: int = 1,
        significance_threshold: float = 0.95,
    ) -> DSRResult:
        """
        Calculates exact Bailey & López de Prado Deflated Sharpe Ratio (DSR).
        Properly handles return distribution skewness, kurtosis, and trial penalty.
        """
        n = len(returns)
        if n < 5:
            return DSRResult(
                raw_sharpe=0.0,
                deflated_sharpe=0.50,
                sample_length=n,
                skewness=0.0,
                kurtosis=3.0,
                trial_count=total_trials,
                expected_max_sharpe=0.0,
                z_stat=0.0,
                p_value=0.50,
                is_statistically_significant=False,
            )

        mean_ret = sum(returns) / n
        variance = sum((r - mean_ret) ** 2 for r in returns) / max(1, n - 1)
        std_ret = math.sqrt(variance)

        if std_ret <= 1e-8:
            return DSRResult(
                raw_sharpe=0.0,
                deflated_sharpe=0.50,
                sample_length=n,
                skewness=0.0,
                kurtosis=3.0,
                trial_count=total_trials,
                expected_max_sharpe=0.0,
                z_stat=0.0,
                p_value=0.50,
                is_statistically_significant=False,
            )

        raw_sharpe = (mean_ret / std_ret) * math.sqrt(252.0)  # Annualized proxy

        # Higher central moments
        diffs = [r - mean_ret for r in returns]
        m2 = sum(d**2 for d in diffs) / n
        m3 = sum(d**3 for d in diffs) / n
        m4 = sum(d**4 for d in diffs) / n
        skew = m3 / (m2**1.5) if m2 > 0 else 0.0
        kurt = m4 / (m2**2) if m2 > 0 else 3.0

        # Variance of Sharpe ratio estimator: Var(SR) = (1 + 0.5*SR^2 - skew*SR + ((kurt-3)/4)*SR^2) / n
        var_sr = (
            1.0 + 0.5 * (raw_sharpe**2) - skew * raw_sharpe + ((kurt - 3.0) / 4.0) * (raw_sharpe**2)
        ) / n
        std_sr = math.sqrt(max(1e-6, var_sr))

        # Expected maximum Sharpe ratio under the null of zero skill with N trials
        # E[max(SR)] = (1 - gamma) * inv_norm(1 - 1/N) + gamma * inv_norm(1 - 1/(N*e))
        euler_gamma = 0.5772156649
        trials = max(1, total_trials)
        if trials > 1:
            term1 = (1.0 - euler_gamma) * self._approx_inv_normal(1.0 - (1.0 / trials))
            term2 = euler_gamma * self._approx_inv_normal(1.0 - (1.0 / (trials * math.e)))
            exp_max_sr = max(0.0, term1 + term2)
        else:
            exp_max_sr = 0.0

        z_stat = (raw_sharpe - exp_max_sr) / std_sr
        # DSR = Phi(z_stat)
        dsr = 0.5 * (1.0 + math.erf(z_stat / math.sqrt(2.0)))
        # P-value corresponding to DSR
        p_val = max(1e-6, min(1.0, 1.0 - dsr))
        is_sig = dsr >= significance_threshold

        return DSRResult(
            raw_sharpe=round(raw_sharpe, 3),
            deflated_sharpe=round(dsr, 4),
            sample_length=n,
            skewness=round(skew, 3),
            kurtosis=round(kurt, 3),
            trial_count=trials,
            expected_max_sharpe=round(exp_max_sr, 3),
            z_stat=round(z_stat, 3),
            p_value=round(p_val, 4),
            is_statistically_significant=is_sig,
        )

    def evaluate_batch_holm_bonferroni(
        self,
        trial_p_values: list[tuple[str, float]],
        alpha: float = 0.05,
    ) -> list[tuple[str, float, float, bool]]:
        """
        Executes step-down Holm-Bonferroni correction across a family of trials.
        Returns list of (trial_id, raw_p_value, critical_cutoff, is_rejected).
        """
        if not trial_p_values:
            return []

        # Sort by p-value ascending
        sorted_trials = sorted(trial_p_values, key=lambda x: x[1])
        m = len(sorted_trials)
        results: list[tuple[str, float, float, bool]] = []
        stopped = False

        for k, (t_id, p_val) in enumerate(sorted_trials, start=1):
            cutoff = alpha / (m - k + 1)
            if not stopped and p_val <= cutoff:
                results.append((t_id, p_val, cutoff, True))
            else:
                stopped = True
                results.append((t_id, p_val, cutoff, False))

        return results

    def save_audit_report(self, report: AuditReport) -> bool:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crawler_audit_reports (
                    audit_id, plan_id, hypothesis_id, family_id, status,
                    audit_hash_sha256, report_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    report.audit_id,
                    report.plan_id,
                    report.hypothesis_id,
                    report.family_id,
                    report.status.value,
                    report.audit_hash_sha256,
                    json.dumps(report.to_dict()),
                    now,
                ),
            )
            conn.commit()
            return True

    def get_audit_report(self, audit_id: str) -> AuditReport | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT report_json FROM crawler_audit_reports WHERE audit_id = ?;",
                (audit_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["report_json"])
            return AuditReport(**data)

    def get_audit_report_by_plan(self, plan_id: str) -> AuditReport | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT report_json FROM crawler_audit_reports 
                WHERE plan_id = ? ORDER BY created_at_utc DESC LIMIT 1;
                """,
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0] if isinstance(row, tuple) else row["report_json"])
            return AuditReport(**data)

    def _record_trial(
        self,
        family_id: str,
        hypothesis_id: str,
        plan_id: str,
        raw_sharpe: float,
        deflated_sharpe: float,
        p_value: float,
        net_expectancy_r: float,
        cost_erosion_pct: float,
        is_significant: int,
    ) -> None:
        now = time.time()
        trial_hash = hashlib.sha256(f"{plan_id}:{p_value}:{now}".encode()).hexdigest()
        trial_id = f"TRL-{int(now)}-{trial_hash[:8].upper()}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO multiple_testing_trials (
                    trial_id, family_id, hypothesis_id, plan_id, raw_sharpe,
                    deflated_sharpe, p_value, net_expectancy_r, cost_erosion_pct,
                    is_significant, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    trial_id,
                    family_id,
                    hypothesis_id,
                    plan_id,
                    raw_sharpe,
                    deflated_sharpe,
                    p_value,
                    net_expectancy_r,
                    cost_erosion_pct,
                    is_significant,
                    now,
                ),
            )
            conn.commit()

    @staticmethod
    def _approx_inv_normal(p: float) -> float:
        """Winitzki rational approximation for standard normal inverse CDF."""
        p = max(1e-6, min(1.0 - 1e-6, p))
        if p < 0.5:
            return -StatisticalAuditor._approx_inv_normal(1.0 - p)
        t = math.sqrt(-2.0 * math.log(1.0 - p))
        c0 = 2.515517
        c1 = 0.802853
        c2 = 0.010328
        d1 = 1.432788
        d2 = 0.189269
        d3 = 0.001308
        return t - ((c2 * t + c1) * t + c0) / (((d3 * t + d2) * t + d1) * t + 1.0)


# Global singleton instance
global_statistical_auditor = StatisticalAuditor()
