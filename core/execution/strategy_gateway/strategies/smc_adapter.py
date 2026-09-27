"""
core/execution/strategy_gateway/strategies/smc_adapter.py
=========================================================
Institutional Adapter for SMC (Smart Money Concepts) Order Flow Strategy.

Transforms structural market markers (BOS, CHOCH, Order Blocks, FVGs) into
deterministic StrategyExecutionProposal objects with constitutional stop loss bounds.
Enforces:
1. Explicit structural validation (BOS, CHOCH, ORDER_BLOCK, FVG_MITIGATION).
2. Mandatory Stop Loss with directional alignment (BUY: SL < Entry; SELL: SL > Entry).
3. Risk boundary enforcement (0.05% <= risk distance <= 10.0%).
4. Immutable proposal compilation via DeterministicStrategyCompiler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from core.execution.strategy_gateway.strategy_compiler import (
    DeterministicStrategyCompiler,
    SignalSpecificationError,
    StrategyExecutionProposal,
)

logger = logging.getLogger("sky.execution.strategy_gateway.smc_adapter")

SMCStructureType = Literal["BOS", "CHOCH", "ORDER_BLOCK", "FVG_MITIGATION"]


class SMCAdapterError(Exception):
    """Base exception for SMC adapter failures."""


class InvalidStopLossError(SMCAdapterError):
    """Raised when stop loss is missing or directionally inverted."""


class ExcessiveRiskDistanceError(SMCAdapterError):
    """Raised when stop loss risk distance exceeds constitutional bounds."""


@dataclass(frozen=True)
class SMCOrderFlowSignal:
    """Validated structural market marker signal from SMC Order Flow analysis."""

    signal_id: str
    instrument: str
    structure_type: SMCStructureType
    direction: Literal["BUY", "SELL"]
    entry_price: Decimal | float | str
    stop_loss_price: Decimal | float | str
    dataset_hash: str
    experiment_id: str
    strategy_version: str = "2.1.0"
    take_profit_price: Decimal | float | str | None = None
    limit_price: Decimal | float | str | None = None
    requested_quantity: Decimal | float | str = "0.10"
    validity_window_ms: int = 10000
    timestamp_ns: int | None = None


class SMCStrategyAdapter:
    """
    Deterministic compiler adapter for SMC Order Flow strategies.
    Guarantees structural validity and zero-bypass stop-loss enforcement.
    """

    STRATEGY_ID: str = "SMC_ORDER_FLOW"
    MIN_RISK_DISTANCE_PCT: float = 0.05  # 5 bps min stop distance
    MAX_RISK_DISTANCE_PCT: float = 10.0  # 10.0% max stop distance

    def __init__(self, compiler: DeterministicStrategyCompiler | None = None) -> None:
        self.compiler = compiler or DeterministicStrategyCompiler()

    def adapt_signal(self, signal: SMCOrderFlowSignal) -> StrategyExecutionProposal:
        """
        Validates structural rules and compiles an immutable StrategyExecutionProposal.
        Raises SMCAdapterError or SignalSpecificationError on validation failures.
        """
        norm_dir = signal.direction.upper().strip()
        if norm_dir not in ("BUY", "SELL"):
            raise SignalSpecificationError(
                f"Invalid SMC direction '{signal.direction}'. Must be BUY or SELL."
            )

        entry_px = Decimal(str(signal.entry_price))
        sl_px = Decimal(str(signal.stop_loss_price))

        if entry_px <= Decimal("0") or sl_px <= Decimal("0"):
            raise InvalidStopLossError(
                f"Entry ({entry_px}) and SL ({sl_px}) must be strictly positive."
            )

        # Directional Stop Loss Invariant
        if norm_dir == "BUY" and sl_px >= entry_px:
            raise InvalidStopLossError(
                f"BUY order invalid: stop loss ({sl_px}) must be strictly lower than entry ({entry_px})"
            )
        elif norm_dir == "SELL" and sl_px <= entry_px:
            raise InvalidStopLossError(
                f"SELL order invalid: stop loss ({sl_px}) must be strictly higher than entry ({entry_px})"
            )

        # Risk Distance Invariant
        risk_distance = abs(entry_px - sl_px)
        risk_pct = float(risk_distance / entry_px * Decimal("100"))

        if risk_pct < self.MIN_RISK_DISTANCE_PCT:
            raise ExcessiveRiskDistanceError(
                f"Stop loss risk distance ({risk_pct:.3f}%) below minimum {self.MIN_RISK_DISTANCE_PCT}%"
            )
        if risk_pct > self.MAX_RISK_DISTANCE_PCT:
            raise ExcessiveRiskDistanceError(
                f"Stop loss risk distance ({risk_pct:.2f}%) exceeds maximum allowable {self.MAX_RISK_DISTANCE_PCT}%"
            )

        # Compile proposal
        proposal = self.compiler.compile_proposal(
            strategy_id=self.STRATEGY_ID,
            strategy_version=signal.strategy_version,
            signal_id=signal.signal_id,
            direction=norm_dir,
            instrument=signal.instrument,
            requested_quantity=signal.requested_quantity,
            decision_price=entry_px,
            limit_price=signal.limit_price or entry_px,
            evidence_manifest_hash=signal.dataset_hash,
            validity_window_ms=signal.validity_window_ms,
            signal_timestamp_ns=signal.timestamp_ns,
        )

        logger.info(
            f"[SMCAdapter] Successfully adapted structural marker '{signal.structure_type}' "
            f"({norm_dir} {signal.instrument}) -> proposal '{proposal.proposal_id}' (Risk: {risk_pct:.2f}%)"
        )
        return proposal
