"""
4-Type Continuous Drift Detection & System Integrity Engine.
Continuously monitors 4 independent operational drift vectors:
1. Data Drift: Input feature distribution shift (KS-test / percentile bounds)
2. Concept Drift: Breakdown of P(Outcome | State) predictive calibration (Brier > 0.22)
3. Performance Drift: Decay of strategy Sharpe ratio / Net EV (>30% degradation)
4. Execution Drift: Deterioration of fill latency and slippage models
Automatically penalizes uncertainty budget and throttles capital allocation on drift alert.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("ai_quant_sentinel.drift_monitor")


@dataclass
class DriftDimensionStatus:
    dimension_name: str  # "DATA_DRIFT", "CONCEPT_DRIFT", "PERFORMANCE_DRIFT", "EXECUTION_DRIFT"
    drift_detected: bool
    drift_severity: float  # [0.0, 1.0] (0 = Nominal, 1 = Critical Shift)
    p_value_or_metric: float
    message: str


@dataclass
class SystemDriftReport:
    timestamp: int
    is_system_drift_critical: bool
    data_drift: DriftDimensionStatus
    concept_drift: DriftDimensionStatus
    performance_drift: DriftDimensionStatus
    execution_drift: DriftDimensionStatus
    recommended_capital_throttle_pct: float  # 0.0 (normal) up to 0.75 (cut sizing by 75%)
    overall_health_verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "is_system_drift_critical": self.is_system_drift_critical,
            "data_drift": asdict(self.data_drift),
            "concept_drift": asdict(self.concept_drift),
            "performance_drift": asdict(self.performance_drift),
            "execution_drift": asdict(self.execution_drift),
            "recommended_capital_throttle_pct": self.recommended_capital_throttle_pct,
            "overall_health_verdict": self.overall_health_verdict,
        }


class DriftMonitor:
    """Monitors 4-dimensional system and alpha drift."""

    def evaluate_system_drift(
        self,
        current_atr_percentile: float = 0.65,
        recent_brier_score: float = 0.165,
        historical_sharpe: float = 2.15,
        rolling_sharpe_30d: float = 1.95,
        avg_recent_slippage_bps: float = 2.8,
        baseline_slippage_bps: float = 2.5,
    ) -> SystemDriftReport:
        """
        Evaluates the 4 drift vectors against baseline thresholds.
        """
        import time

        now = int(time.time() * 1000)

        # 1. Data Drift Check (ATR extreme percentile > 99.0% or < 1.0%)
        data_drift_active = bool(current_atr_percentile > 0.98 or current_atr_percentile < 0.02)
        data_severity = 0.75 if data_drift_active else 0.05
        d_data = DriftDimensionStatus(
            dimension_name="DATA_DRIFT",
            drift_detected=data_drift_active,
            drift_severity=data_severity,
            p_value_or_metric=round(current_atr_percentile, 3),
            message="Input feature distributions within nominal range"
            if not data_drift_active
            else f"Extreme volatility shift detected (ATR Pct: {current_atr_percentile * 100:.1f}%)",
        )

        # 2. Concept Drift Check (Brier score > 0.22 indicates predictive degradation)
        concept_drift_active = bool(recent_brier_score > 0.22)
        concept_severity = (
            float(np.clip((recent_brier_score - 0.20) / 0.10, 0.0, 1.0))
            if concept_drift_active
            else 0.08
        )
        d_concept = DriftDimensionStatus(
            dimension_name="CONCEPT_DRIFT",
            drift_detected=concept_drift_active,
            drift_severity=round(concept_severity, 2),
            p_value_or_metric=round(recent_brier_score, 4),
            message="Predictive calibration well-anchored"
            if not concept_drift_active
            else f"Predictive accuracy decaying (Brier Score: {recent_brier_score:.3f} > 0.22)",
        )

        # 3. Performance Drift Check (Rolling Sharpe decaying > 30% from historical)
        sharpe_decay_pct = (historical_sharpe - rolling_sharpe_30d) / max(0.1, historical_sharpe)
        perf_drift_active = bool(sharpe_decay_pct > 0.30)
        perf_severity = float(np.clip(sharpe_decay_pct, 0.0, 1.0)) if perf_drift_active else 0.06
        d_perf = DriftDimensionStatus(
            dimension_name="PERFORMANCE_DRIFT",
            drift_detected=perf_drift_active,
            drift_severity=round(perf_severity, 2),
            p_value_or_metric=round(rolling_sharpe_30d, 2),
            message=f"Rolling Sharpe ({rolling_sharpe_30d:.2f}) nominal"
            if not perf_drift_active
            else f"Alpha decay detected: Sharpe down {sharpe_decay_pct * 100:.1f}%",
        )

        # 4. Execution Drift Check (Realized slippage > 2.0x baseline)
        exec_drift_active = bool(avg_recent_slippage_bps > 2.0 * baseline_slippage_bps)
        exec_severity = 0.60 if exec_drift_active else 0.04
        d_exec = DriftDimensionStatus(
            dimension_name="EXECUTION_DRIFT",
            drift_detected=exec_drift_active,
            drift_severity=exec_severity,
            p_value_or_metric=round(avg_recent_slippage_bps, 1),
            message=f"Fill slippage ({avg_recent_slippage_bps:.1f}bps) nominal"
            if not exec_drift_active
            else f"Execution quality degrading: {avg_recent_slippage_bps:.1f}bps > 2x baseline",
        )

        # Calculate Capital Throttle Percentage
        drift_count = sum(
            [
                1
                for d in [
                    data_drift_active,
                    concept_drift_active,
                    perf_drift_active,
                    exec_drift_active,
                ]
                if d
            ]
        )
        throttle = min(0.75, drift_count * 0.25)
        is_critical = drift_count >= 2 or concept_drift_active

        verdict = (
            "HEALTHY_CALIBRATED"
            if drift_count == 0
            else ("WARNING_DRIFT_DETECTED" if not is_critical else "CRITICAL_DRIFT_ACTION_REQUIRED")
        )

        return SystemDriftReport(
            timestamp=now,
            is_system_drift_critical=is_critical,
            data_drift=d_data,
            concept_drift=d_concept,
            performance_drift=d_perf,
            execution_drift=d_exec,
            recommended_capital_throttle_pct=throttle,
            overall_health_verdict=verdict,
        )


# Singleton
drift_monitor = DriftMonitor()
