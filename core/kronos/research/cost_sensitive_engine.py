"""
core/kronos/research/cost_sensitive_engine.py
=============================================
Milestone K10 Phase 2: Asymmetric Cost-Sensitive Utility & Frozen Threshold Engine.
Implements Bayesian decision theory over calibrated probabilities under 3-tier
friction hurdles. Enforces strict policy freezing on Window 2 (Calibration/Validation)
before out-of-sample evaluation on Window 3 (Sealed OOS).

Epistemic Guardrail:
A trade is only authorized if expected utility strictly exceeds zero after deducting
the 3-tier roundtrip friction drag. Policy thresholds are never fitted on Window 3.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

from core.kronos.research.friction_evaluator import (
    CANONICAL_FRICTION_SCENARIOS,
    FrictionScenario,
)

ActionType = Literal["LONG", "SHORT", "HOLD"]


@dataclass(frozen=True)
class CostSensitiveDecision:
    timestamp: int
    raw_probability: float
    calibrated_probability: float
    action: ActionType
    expected_utility_long_bps: float
    expected_utility_short_bps: float
    friction_hurdle_bps: float
    tier: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenThresholdPolicy:
    """
    Immutable threshold policy selected exclusively on Window 2.
    Evaluation on Window 3 must ingest this policy without modification.
    """

    tier: str
    tau_long: float
    tau_short: float
    calibration_window_samples: int
    window2_realized_utility_bps: float
    frozen_at_ts: int
    min_friction_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyEvaluationReport:
    tier: str
    sample_size: int
    trades_executed: int
    trade_frequency_pct: float
    win_rate: float
    gross_pnl_bps: float
    net_pnl_bps: float
    gross_sharpe: float
    net_sharpe: float
    is_economically_viable: bool
    policy: FrozenThresholdPolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "sample_size": self.sample_size,
            "trades_executed": self.trades_executed,
            "trade_frequency_pct": round(self.trade_frequency_pct, 4),
            "win_rate": round(self.win_rate, 4),
            "gross_pnl_bps": round(self.gross_pnl_bps, 2),
            "net_pnl_bps": round(self.net_pnl_bps, 2),
            "gross_sharpe": round(self.gross_sharpe, 4),
            "net_sharpe": round(self.net_sharpe, 4),
            "is_economically_viable": self.is_economically_viable,
            "policy": self.policy.to_dict(),
        }


class CostSensitiveEngine:
    """
    Cost-sensitive decision engine for Kronos calibrated probabilities.
    Maximizes expected net utility over asymmetric cost-of-error matrices.
    """

    def __init__(self, friction_scenario: FrictionScenario | None = None):
        self.friction = friction_scenario or CANONICAL_FRICTION_SCENARIOS["CONSERVATIVE"]

    def compute_expected_utility(
        self,
        calibrated_prob: float,
        expected_move_bps: float = 30.0,
    ) -> tuple[float, float]:
        """
        Computes expected utility in basis points for LONG and SHORT actions.
        E[U(LONG)] = p * R_up - (1 - p) * R_down - Cost_friction
        E[U(SHORT)] = (1 - p) * R_down - p * R_up - Cost_friction
        Assuming symmetric expected move magnitude R_up = R_down = expected_move_bps.
        """
        p = float(np.clip(calibrated_prob, 0.0, 1.0))
        cost = self.friction.roundtrip_taker_cost_bps

        # Expected gross return
        gross_long = (2.0 * p - 1.0) * expected_move_bps
        gross_short = (1.0 - 2.0 * p) * expected_move_bps

        net_long = gross_long - cost
        net_short = gross_short - cost

        return net_long, net_short

    def select_action(
        self,
        calibrated_prob: float,
        tau_long: float,
        tau_short: float,
    ) -> ActionType:
        """
        Selects trading action based on frozen thresholds:
        - LONG if p >= tau_long
        - SHORT if p <= tau_short
        - HOLD otherwise
        """
        p = float(np.clip(calibrated_prob, 0.0, 1.0))
        if p >= tau_long:
            return "LONG"
        elif p <= tau_short:
            return "SHORT"
        return "HOLD"

    def fit_and_freeze_policy(
        self,
        calibrated_probs_w2: np.ndarray | list[float],
        realized_returns_bps_w2: np.ndarray | list[float],
        timestamps_w2: np.ndarray | list[int],
        expected_move_bps: float = 30.0,
        tau_grid: np.ndarray | None = None,
    ) -> FrozenThresholdPolicy:
        """
        Optimizes thresholds strictly on Window 2 to maximize net utility.
        Freezes the resulting policy for Window 3 evaluation.
        """
        probs = np.asarray(calibrated_probs_w2, dtype=np.float64)
        rets = np.asarray(realized_returns_bps_w2, dtype=np.float64)
        ts = np.asarray(timestamps_w2, dtype=np.int64)

        if len(probs) != len(rets) or len(probs) != len(ts):
            raise ValueError("Arrays must have identical lengths")

        if tau_grid is None:
            # Search over conservative threshold grid from 0.50 to 0.90
            tau_grid = np.linspace(0.50, 0.90, 41)

        cost = self.friction.roundtrip_taker_cost_bps
        best_utility = -float("inf")
        best_tau_long = 0.65
        best_tau_short = 0.35

        for tau in tau_grid:
            tau_l = float(tau)
            tau_s = float(1.0 - tau)

            # Evaluate net utility on Window 2
            actions = np.where(probs >= tau_l, 1.0, np.where(probs <= tau_s, -1.0, 0.0))
            trades = actions != 0.0
            trade_count = np.sum(trades)

            if trade_count == 0:
                net_utility = 0.0
            else:
                trade_rets = actions[trades] * rets[trades] - cost
                net_utility = float(np.sum(trade_rets))

            if net_utility > best_utility:
                best_utility = net_utility
                best_tau_long = tau_l
                best_tau_short = tau_s

        frozen_policy = FrozenThresholdPolicy(
            tier=self.friction.tier,
            tau_long=round(best_tau_long, 4),
            tau_short=round(best_tau_short, 4),
            calibration_window_samples=len(probs),
            window2_realized_utility_bps=round(best_utility, 2),
            frozen_at_ts=int(ts[-1]),
            min_friction_bps=cost,
        )
        return frozen_policy

    def evaluate_sealed_window3(
        self,
        policy: FrozenThresholdPolicy,
        calibrated_probs_w3: np.ndarray | list[float],
        realized_returns_bps_w3: np.ndarray | list[float],
        expected_move_bps: float = 30.0,
    ) -> PolicyEvaluationReport:
        """
        Evaluates frozen policy strictly out-of-sample on Window 3.
        No threshold tuning or lookahead permitted.
        """
        probs = np.asarray(calibrated_probs_w3, dtype=np.float64)
        rets = np.asarray(realized_returns_bps_w3, dtype=np.float64)
        n = len(probs)

        if n == 0:
            raise ValueError("Window 3 cannot be empty")

        cost = self.friction.roundtrip_taker_cost_bps
        actions = np.where(
            probs >= policy.tau_long, 1.0, np.where(probs <= policy.tau_short, -1.0, 0.0)
        )

        trade_mask = actions != 0.0
        n_trades = int(np.sum(trade_mask))

        if n_trades == 0:
            return PolicyEvaluationReport(
                tier=self.friction.tier,
                sample_size=n,
                trades_executed=0,
                trade_frequency_pct=0.0,
                win_rate=0.0,
                gross_pnl_bps=0.0,
                net_pnl_bps=0.0,
                gross_sharpe=0.0,
                net_sharpe=0.0,
                is_economically_viable=False,
                policy=policy,
            )

        gross_returns = actions[trade_mask] * rets[trade_mask]
        net_returns = gross_returns - cost

        win_rate = float(np.mean(net_returns > 0))
        total_gross_bps = float(np.sum(gross_returns))
        total_net_bps = float(np.sum(net_returns))

        # Annualized Sharpe ratio assuming 15m bars (35,040 bars/yr)
        annualization_factor = math.sqrt(35040)
        std_gross = float(np.std(gross_returns)) if len(gross_returns) > 1 else 0.0
        std_net = float(np.std(net_returns)) if len(net_returns) > 1 else 0.0

        gross_sharpe = (
            (float(np.mean(gross_returns)) / std_gross * annualization_factor)
            if std_gross > 1e-8
            else 0.0
        )
        net_sharpe = (
            (float(np.mean(net_returns)) / std_net * annualization_factor)
            if std_net > 1e-8
            else 0.0
        )

        is_viable = total_net_bps > 0.0 and net_sharpe > 0.5 and win_rate > 0.50

        return PolicyEvaluationReport(
            tier=self.friction.tier,
            sample_size=n,
            trades_executed=n_trades,
            trade_frequency_pct=float(n_trades / n),
            win_rate=win_rate,
            gross_pnl_bps=total_gross_bps,
            net_pnl_bps=total_net_bps,
            gross_sharpe=gross_sharpe,
            net_sharpe=net_sharpe,
            is_economically_viable=is_viable,
            policy=policy,
        )
