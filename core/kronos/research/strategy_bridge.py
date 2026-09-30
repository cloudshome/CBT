"""
core/kronos/research/strategy_bridge.py
=======================================
Milestone K10 Phase 4: One-Way Paper Strategy League Bridge & Half-Kelly Sizing Engine.
Converts calibrated, cost-sensitive model outputs into paper research signals
governed by volatility-adjusted Half-Kelly position sizing.

Security & Architectural Guardrail:
This bridge is strictly ONE-WAY into paper / strategy evaluation.
Hardcoded invariants:
- is_tradeable: False
- live_execution_permitted: False
- execution_mode: "PAPER_ONLY"
Any attempt to route signals from this bridge to live execution gates raises
a fatal PermissionError.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.kronos.research.cost_sensitive_engine import ActionType, CostSensitiveDecision


@dataclass(frozen=True)
class ResearchSignal:
    signal_id: str
    symbol: str
    timestamp: int
    raw_probability: float
    calibrated_probability: float
    action: ActionType
    half_kelly_fraction: float
    volatility_scalar: float
    target_allocation_pct: float
    policy_tier: str
    is_tradeable: bool = False  # IMMUTABLE GUARDRAIL
    live_execution_permitted: bool = False  # IMMUTABLE GUARDRAIL
    execution_mode: str = "PAPER_ONLY"  # IMMUTABLE GUARDRAIL
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_tradeable"] = False
        d["live_execution_permitted"] = False
        d["execution_mode"] = "PAPER_ONLY"
        return d


class StrategyBridge:
    """
    One-way Strategy League paper bridge for Kronos research signals.
    Enforces Half-Kelly sizing and permanent isolation from live execution.
    """

    MAX_ALLOCATION_CAP = 0.25  # Never risk more than 25% single-asset leverage

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        target_volatility_annualized: float = 0.40,
        win_loss_payoff_ratio: float = 1.0,
    ):
        self.symbol = symbol
        self.target_volatility = target_volatility_annualized
        self.win_loss_ratio = win_loss_payoff_ratio

    def compute_half_kelly(
        self,
        calibrated_prob: float,
        realized_volatility_annualized: float = 0.50,
    ) -> tuple[float, float, float]:
        """
        Calculates volatility-adjusted Half-Kelly sizing.
        Full Kelly: f* = (b * p - q) / b
        Half Kelly: f_half = 0.5 * f*
        Volatility scalar: target_vol / max(realized_vol, 1e-4) capped at 1.0
        Final fraction: clip(f_half * vol_scalar, 0.0, MAX_ALLOCATION_CAP)
        """
        p = float(np.clip(calibrated_prob, 0.0, 1.0))
        q = 1.0 - p
        b = max(self.win_loss_ratio, 1e-4)

        full_kelly = (b * p - q) / b
        if full_kelly <= 0.0:
            return 0.0, 1.0, 0.0

        half_kelly = 0.5 * full_kelly

        # Volatility scalar
        vol_scalar = min(1.0, self.target_volatility / max(realized_volatility_annualized, 1e-4))
        target_alloc = float(np.clip(half_kelly * vol_scalar, 0.0, self.MAX_ALLOCATION_CAP))

        return half_kelly, vol_scalar, target_alloc

    def generate_paper_signal(
        self,
        decision: CostSensitiveDecision,
        realized_volatility_annualized: float = 0.50,
        context_metadata: dict[str, Any] | None = None,
    ) -> ResearchSignal:
        """
        Generates a sealed, non-tradeable paper signal from a cost-sensitive decision.
        """
        if decision.action == "HOLD":
            half_kelly, vol_scalar, target_alloc = 0.0, 1.0, 0.0
        else:
            # For LONG, confidence is p; for SHORT, confidence is (1 - p)
            effective_prob = (
                decision.calibrated_probability
                if decision.action == "LONG"
                else (1.0 - decision.calibrated_probability)
            )
            half_kelly, vol_scalar, target_alloc = self.compute_half_kelly(
                effective_prob, realized_volatility_annualized
            )

        signal = ResearchSignal(
            signal_id=f"SIG_{uuid.uuid4().hex[:12]}",
            symbol=self.symbol,
            timestamp=decision.timestamp,
            raw_probability=round(decision.raw_probability, 6),
            calibrated_probability=round(decision.calibrated_probability, 6),
            action=decision.action,
            half_kelly_fraction=round(half_kelly, 6),
            volatility_scalar=round(vol_scalar, 4),
            target_allocation_pct=round(target_alloc * 100.0, 4),
            policy_tier=decision.tier,
            is_tradeable=False,
            live_execution_permitted=False,
            execution_mode="PAPER_ONLY",
            metadata=context_metadata or {},
        )
        return signal

    def assert_no_live_dispatch(self, signal: ResearchSignal) -> None:
        """
        Firewall assertion: Rejects any attempt to dispatch paper signals to live routes.
        """
        if (
            signal.is_tradeable
            or signal.live_execution_permitted
            or signal.execution_mode != "PAPER_ONLY"
        ):
            raise PermissionError(
                f"FATAL CAUSAL BREACH: Attempted to route research signal {signal.signal_id} "
                f"with live_execution_permitted={signal.live_execution_permitted} or is_tradeable={signal.is_tradeable}!"
            )
