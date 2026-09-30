"""
core/intelligence/forward_validation/suspension_controller.py
=============================================================
Strategy Health Monitor & Predefined Suspension Controller for Milestone 31.

Enforces zero-discretion automated circuit breakers:
1. Maximum Drawdown Breach: Suspends strategy when drawdown exceeds predeclared threshold.
2. Consecutive Negative Net Markouts: Quarantines strategy when execution persistently underperforms across horizons.
3. Persistent Feed Degradation: Quarantines strategy when market data integrity is compromised.
4. Severe Statistical Drift: Suspends strategy when 5-axis drift detector identifies radical structural divergence.

Zero Survivorship Bias Directive:
Suspension NEVER deletes or conceals a strategy. The strategy remains permanently queryable
in the registry with complete autopsy lineage and immutable audit logs.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from core.intelligence.forward_validation.drift_detector import (
    DriftStatus,
    MultiDimensionalDriftReport,
)
from core.intelligence.forward_validation.models import (
    AdmissionStatus,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    RealisticPaperFillSimulator,
)
from core.intelligence.forward_validation.strategy_league import (
    StrategyLeagueRegistry,
)

logger = logging.getLogger("ai_quant_sentinel.intelligence.suspension_controller")


class SuspensionPolicy(BaseModel):
    """Predeclared circuit breaker thresholds for forward validation."""

    max_drawdown_bps: float = Field(
        default=300.0, description="Max cumulative drawdown limit in bps"
    )
    consecutive_negative_markouts_limit: int = Field(
        default=5, description="Consecutive negative net markouts"
    )
    consecutive_feed_degradations_limit: int = Field(
        default=3, description="Consecutive corrupted feed ticks"
    )
    policy_version: str = "v1.0"
    auto_cancel_resting_orders: bool = True


class SuspensionController:
    """
    Automated watchdog enforcing deterministic circuit breakers, order cancellations,
    and immutable suspension logging for forward league strategies.
    """

    def __init__(
        self,
        registry: StrategyLeagueRegistry,
        policy: SuspensionPolicy | None = None,
        fill_simulator: RealisticPaperFillSimulator | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy or SuspensionPolicy()
        self.fill_simulator = fill_simulator
        self._consecutive_neg_markouts: dict[str, int] = {}
        self._consecutive_feed_errors: dict[str, int] = {}

    def check_drawdown(self, admission_id: str, current_drawdown_bps: float) -> bool:
        """
        Evaluates cumulative drawdown against the policy limit.
        Suspends strategy and cancels all resting orders if breached.
        """
        if current_drawdown_bps >= self.policy.max_drawdown_bps:
            reason = (
                f"Automated Circuit Breaker: Max drawdown breached "
                f"({current_drawdown_bps:.1f} bps >= {self.policy.max_drawdown_bps:.1f} bps limit)"
            )
            self._execute_suspension(
                admission_id=admission_id,
                target_status=AdmissionStatus.SUSPENDED,
                trigger_name="MAX_DRAWDOWN_BREACH",
                threshold_val=self.policy.max_drawdown_bps,
                observed_val=current_drawdown_bps,
                reason=reason,
            )
            return True
        return False

    def check_markout_feedback(self, admission_id: str, net_markout_bps: float) -> bool:
        """
        Monitors post-trade microstructure execution quality.
        Quarantines strategy if negative net markouts occur consecutively.
        """
        if net_markout_bps < 0.0:
            count = self._consecutive_neg_markouts.get(admission_id, 0) + 1
            self._consecutive_neg_markouts[admission_id] = count
            if count >= self.policy.consecutive_negative_markouts_limit:
                reason = (
                    f"Automated Circuit Breaker: Persistent negative execution quality "
                    f"({count} consecutive negative net markouts >= limit {self.policy.consecutive_negative_markouts_limit})"
                )
                self._execute_suspension(
                    admission_id=admission_id,
                    target_status=AdmissionStatus.QUARANTINED,
                    trigger_name="CONSECUTIVE_NEGATIVE_MARKOUTS",
                    threshold_val=float(self.policy.consecutive_negative_markouts_limit),
                    observed_val=float(count),
                    reason=reason,
                )
                return True
        else:
            self._consecutive_neg_markouts[admission_id] = 0
        return False

    def check_feed_integrity(self, admission_id: str, is_feed_healthy: bool) -> bool:
        """
        Monitors input data feed quality during strategy execution.
        Quarantines strategy if feeds are persistently corrupted.
        """
        if not is_feed_healthy:
            count = self._consecutive_feed_errors.get(admission_id, 0) + 1
            self._consecutive_feed_errors[admission_id] = count
            if count >= self.policy.consecutive_feed_degradations_limit:
                reason = (
                    f"Automated Circuit Breaker: Persistent feed corruption "
                    f"({count} consecutive corrupted snapshots >= limit {self.policy.consecutive_feed_degradations_limit})"
                )
                self._execute_suspension(
                    admission_id=admission_id,
                    target_status=AdmissionStatus.QUARANTINED,
                    trigger_name="FEED_DEGRADATION_QUARANTINE",
                    threshold_val=float(self.policy.consecutive_feed_degradations_limit),
                    observed_val=float(count),
                    reason=reason,
                )
                return True
        else:
            self._consecutive_feed_errors[admission_id] = 0
        return False

    def check_drift_report(
        self,
        admission_id: str,
        drift_report: MultiDimensionalDriftReport,
    ) -> bool:
        """
        Suspends strategy if 5-axis drift detector reports SEVERE structural divergence.
        """
        if drift_report.overall_status == DriftStatus.SEVERE:
            reason = f"Automated Circuit Breaker: Severe statistical drift detected ({drift_report.drift_summary})"
            self._execute_suspension(
                admission_id=admission_id,
                target_status=AdmissionStatus.SUSPENDED,
                trigger_name="SEVERE_STATISTICAL_DRIFT",
                threshold_val=1.0,
                observed_val=2.0,
                reason=reason,
                details={"drift_summary": drift_report.drift_summary},
            )
            return True
        return False

    def manual_halt(self, admission_id: str, reason: str, operator_id: str) -> None:
        """Operator-initiated emergency suspension."""
        full_reason = f"Manual Operator Halt by {operator_id}: {reason}"
        self._execute_suspension(
            admission_id=admission_id,
            target_status=AdmissionStatus.SUSPENDED,
            trigger_name="MANUAL_OPERATOR_HALT",
            threshold_val=0.0,
            observed_val=1.0,
            reason=full_reason,
            operator_or_system=operator_id,
        )

    def manual_resume(self, admission_id: str, reason: str, operator_id: str) -> None:
        """Operator-initiated resumption after review."""
        self._consecutive_neg_markouts[admission_id] = 0
        self._consecutive_feed_errors[admission_id] = 0
        self.registry.transition_status(
            admission_id=admission_id,
            new_status=AdmissionStatus.ACTIVE,
            reason=f"Manual Operator Resume by {operator_id}: {reason}",
            operator_or_system=operator_id,
        )

    def _execute_suspension(
        self,
        admission_id: str,
        target_status: AdmissionStatus,
        trigger_name: str,
        threshold_val: float,
        observed_val: float,
        reason: str,
        operator_or_system: str = "SYSTEM_WATCHDOG",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Atomically executes status transition, logs suspension event,
        and cancels outstanding resting limit orders.
        """
        # 1. Transition registry state
        self.registry.transition_status(
            admission_id=admission_id,
            new_status=target_status,
            reason=reason,
            operator_or_system=operator_or_system,
        )

        # 2. Log immutable circuit breaker event
        import json

        details_str = json.dumps(details or {"reason": reason})
        self.registry.log_suspension(
            admission_id=admission_id,
            trigger_name=trigger_name,
            threshold_val=threshold_val,
            observed_val=observed_val,
            details=details_str,
            policy_version=self.policy.policy_version,
        )

        # 3. Cancel resting limit orders in simulated fill environment (SIMULATION_ONLY_CANCEL)
        if self.fill_simulator and self.policy.auto_cancel_resting_orders:
            cancelled = self.fill_simulator.cancel_all_orders_for_admission(admission_id)
            if cancelled:
                logger.info(
                    "[SIMULATION_ONLY_CANCEL] Cancelled %d simulated resting orders for suspended strategy %s",
                    len(cancelled),
                    admission_id,
                )
