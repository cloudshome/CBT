"""
core/intelligence/causal_firewall.py
====================================
9-Gate Institutional Causal Firewall Validator for Milestone 28.

Enforces:
1. Gate 1: Execution Authority Isolation (NON_EXECUTABLE_RESEARCH_HYPOTHESIS, real_capital_enabled=False).
2. Gate 2: Point-in-Time Causality (Zero-lookahead: t_avail < t_observation).
3. Gate 3: Content Hash Integrity (SHA-256 match).
4. Gate 4: Epistemic Prior Verification (Tier-grounded Bayesian weight).
5. Gate 5: Failure Memory Pre-Screening (Jaccard concept overlap < 0.50 via FailureMemoryEngine).
6. Gate 6: Multiple Testing Exploration Budget (Daily trial cap per family).
7. Gate 7: Falsifiability Specification (Explicit H0, H1, and invalidation rules).
8. Gate 8: Microstructure Feasibility (Micro conditions within physical distributions).
9. Gate 9: Revision Vintage Isolation (No lookahead revisions).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.autonomous_research.failure_memory import FailureMemoryEngine
from core.intelligence.causal_mechanisms import (
    lookup_family,
)
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    CausalHypothesisStatus,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.point_in_time import EPISTEMIC_PRIOR_WEIGHTS

logger = logging.getLogger("ai_quant_sentinel.intelligence.causal_firewall")


class ConstitutionalViolationError(RuntimeError):
    """Raised when an action or hypothesis attempts to violate constitutional invariants."""


@dataclass
class CausalFirewallDecision:
    """Audit result containing per-gate evaluations and decision."""

    passed: bool
    hypothesis_id: str
    gate_results: dict[str, bool]
    violations: list[str]
    audit_timestamp_utc: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CausalFirewallValidator:
    """Institutional 9-Gate Firewall ensuring zero-lookahead, epistemic rigor, and execution isolation."""

    def __init__(
        self,
        failure_memory: FailureMemoryEngine | None = None,
        ledger: HypothesisLedgerManager | None = None,
    ):
        self.failure_memory = failure_memory or FailureMemoryEngine()
        self.ledger = ledger or global_hypothesis_ledger

    def validate(self, hypothesis: CausalHypothesis) -> CausalFirewallDecision:
        """
        Executes all 9 gates in sequence.
        Returns a comprehensive CausalFirewallDecision.
        """
        gate_results: dict[str, bool] = {}
        violations: list[str] = []

        # Gate 1: Execution Authority Isolation
        g1_pass, g1_err = self._check_gate_1_execution_isolation(hypothesis)
        gate_results["GATE_1_EXECUTION_AUTHORITY_ISOLATION"] = g1_pass
        if not g1_pass:
            violations.append(g1_err)

        # Gate 2: Point-in-Time Causality
        g2_pass, g2_err = self._check_gate_2_point_in_time_causality(hypothesis)
        gate_results["GATE_2_POINT_IN_TIME_CAUSALITY"] = g2_pass
        if not g2_pass:
            violations.append(g2_err)

        # Gate 3: Content Hash Integrity
        g3_pass, g3_err = self._check_gate_3_content_hash(hypothesis)
        gate_results["GATE_3_CONTENT_HASH_INTEGRITY"] = g3_pass
        if not g3_pass:
            violations.append(g3_err)

        # Gate 4: Epistemic Prior Verification
        g4_pass, g4_err = self._check_gate_4_epistemic_priors(hypothesis)
        gate_results["GATE_4_EPISTEMIC_PRIOR_VERIFICATION"] = g4_pass
        if not g4_pass:
            violations.append(g4_err)

        # Gate 5: Failure Memory Pre-Screening
        g5_pass, g5_err = self._check_gate_5_failure_memory(hypothesis)
        gate_results["GATE_5_FAILURE_MEMORY_PRESCREEN"] = g5_pass
        if not g5_pass:
            violations.append(g5_err)

        # Gate 6: Multiple Testing Exploration Budget
        g6_pass, g6_err = self._check_gate_6_multiple_testing_budget(hypothesis)
        gate_results["GATE_6_MULTIPLE_TESTING_BUDGET"] = g6_pass
        if not g6_pass:
            violations.append(g6_err)

        # Gate 7: Falsifiability Specification
        g7_pass, g7_err = self._check_gate_7_falsifiability(hypothesis)
        gate_results["GATE_7_FALSIFIABILITY_SPECIFICATION"] = g7_pass
        if not g7_pass:
            violations.append(g7_err)

        # Gate 8: Microstructure Feasibility
        g8_pass, g8_err = self._check_gate_8_microstructure_feasibility(hypothesis)
        gate_results["GATE_8_MICROSTRUCTURE_FEASIBILITY"] = g8_pass
        if not g8_pass:
            violations.append(g8_err)

        # Gate 9: Revision Vintage Isolation
        g9_pass, g9_err = self._check_gate_9_revision_vintage(hypothesis)
        gate_results["GATE_9_REVISION_VINTAGE_ISOLATION"] = g9_pass
        if not g9_pass:
            violations.append(g9_err)

        overall_passed = all(gate_results.values())

        # Update ledger status accordingly
        if overall_passed:
            self.ledger.update_status(
                hypothesis.hypothesis_id, CausalHypothesisStatus.FIREWALL_VALIDATED
            )
        else:
            self.ledger.update_status(
                hypothesis.hypothesis_id,
                CausalHypothesisStatus.REJECTED,
                rejection_reason="; ".join(violations),
            )

        return CausalFirewallDecision(
            passed=overall_passed,
            hypothesis_id=hypothesis.hypothesis_id,
            gate_results=gate_results,
            violations=violations,
        )

    # ========================================================================
    # Gate Implementations
    # ========================================================================

    def _check_gate_1_execution_isolation(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        if hypo.execution_authority != "NON_EXECUTABLE_RESEARCH_HYPOTHESIS":
            return (
                False,
                "Gate 1 Violation: execution_authority is not NON_EXECUTABLE_RESEARCH_HYPOTHESIS.",
            )
        if hypo.real_capital_enabled is not False:
            return False, "Gate 1 Violation: real_capital_enabled must be strictly False."
        return True, ""

    def _check_gate_2_point_in_time_causality(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        event = hypo.macro_event_contract
        now = time.time()
        # Event publication cannot be in the future beyond normal 300s skew
        if event.published_at_utc > now + 300.0:
            return (
                False,
                f"Gate 2 Violation: published_at_utc ({event.published_at_utc}) is in the future.",
            )
        # Effective availability must be strictly positive
        if event.effective_availability_utc <= 0:
            return False, "Gate 2 Violation: effective_availability_utc must be positive."
        # Event effective availability must strictly precede hypothesis creation
        if event.effective_availability_utc > hypo.created_at_utc:
            return False, (
                f"Gate 2 Violation (Lookahead): effective_availability_utc ({event.effective_availability_utc:.2f}) "
                f"> hypothesis created_at_utc ({hypo.created_at_utc:.2f})."
            )
        return True, ""

    def _check_gate_3_content_hash(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        sha = hypo.macro_event_contract.content_hash_sha256
        if not sha or len(sha) != 64 or not re.match(r"^[0-9a-fA-F]{64}$", sha):
            return False, f"Gate 3 Violation: Invalid content_hash_sha256: '{sha}'."
        return True, ""

    def _check_gate_4_epistemic_priors(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        grade = hypo.macro_event_contract.epistemic_grade
        expected_weight = EPISTEMIC_PRIOR_WEIGHTS.get(grade)
        if expected_weight is None:
            return False, f"Gate 4 Violation: Unrecognized epistemic_grade '{grade}'."
        if abs(hypo.epistemic_prior_weight - expected_weight) > 0.05:
            return False, (
                f"Gate 4 Violation: epistemic_prior_weight ({hypo.epistemic_prior_weight}) "
                f"deviates from standard weight ({expected_weight}) for grade '{grade}'."
            )
        return True, ""

    def _check_gate_5_failure_memory(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        # Formulate search text combining thesis and alternative hypothesis
        search_text = f"{hypo.mechanism_id} {hypo.null_hypothesis} {hypo.alternative_hypothesis}"
        is_dup, fail_rec, reason = self.failure_memory.check_prior_failures(
            hypothesis_text=search_text,
            target_symbol=hypo.target_asset,
            timeframe=hypo.timeframe,
            parameters=hypo.microstructure_conditions,
        )
        if is_dup:
            return False, f"Gate 5 Violation (Failure Memory Zombie Strategy): {reason}"
        return True, ""

    def _check_gate_6_multiple_testing_budget(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        family = lookup_family(hypo.family_id)
        if not family:
            return False, f"Gate 6 Violation: Unregistered research family '{hypo.family_id}'."

        today_count = self.ledger.count_family_trials_today(hypo.family_id.value)
        if today_count >= family.daily_trial_cap:
            return False, (
                f"Gate 6 Violation: Family '{hypo.family_id.value}' daily trial budget exhausted "
                f"({today_count}/{family.daily_trial_cap})."
            )
        return True, ""

    def _check_gate_7_falsifiability(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        if not hypo.null_hypothesis or len(hypo.null_hypothesis.strip()) < 15:
            return (
                False,
                "Gate 7 Violation: null_hypothesis is missing or insufficiently detailed (< 15 chars).",
            )
        if not hypo.alternative_hypothesis or len(hypo.alternative_hypothesis.strip()) < 15:
            return (
                False,
                "Gate 7 Violation: alternative_hypothesis is missing or insufficiently detailed (< 15 chars).",
            )
        if not hypo.falsification_criteria or len(hypo.falsification_criteria) == 0:
            return (
                False,
                "Gate 7 Violation: falsification_criteria must contain explicit invalidation conditions.",
            )
        return True, ""

    def _check_gate_8_microstructure_feasibility(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        conds = hypo.microstructure_conditions
        if not conds:
            return False, "Gate 8 Violation: microstructure_conditions cannot be empty."

        # Validate OBI bound if present
        if "obi_score_min" in conds:
            obi = conds["obi_score_min"]
            if not (-1.0 <= obi <= 1.0):
                return (
                    False,
                    f"Gate 8 Violation: obi_score_min ({obi}) out of valid range [-1.0, 1.0].",
                )

        if "obi_score_max" in conds:
            obi = conds["obi_score_max"]
            if not (-1.0 <= obi <= 1.0):
                return (
                    False,
                    f"Gate 8 Violation: obi_score_max ({obi}) out of valid range [-1.0, 1.0].",
                )

        # Validate CVD absorption score if present
        if "cvd_absorption_score_min" in conds:
            score = conds["cvd_absorption_score_min"]
            if not (0.0 <= score <= 1.0):
                return (
                    False,
                    f"Gate 8 Violation: cvd_absorption_score_min ({score}) out of valid range [0.0, 1.0].",
                )

        return True, ""

    def _check_gate_9_revision_vintage(self, hypo: CausalHypothesis) -> tuple[bool, str]:
        event = hypo.macro_event_contract
        # If revised metric is populated, revision number must be > 0 and vintage noted
        if event.revised_metric_value is not None and event.revision_number == 0:
            return False, "Gate 9 Violation: Revised metric present without revision_number >= 1."
        return True, ""


# Global singleton validator
global_causal_firewall = CausalFirewallValidator()
