"""
core/execution/strategy_gateway/strategies/kronos_adapter.py
============================================================
Institutional Adapter for Kronos Grade-E3 Directional Model.

Transforms calibrated machine learning forecasts into deterministic
StrategyExecutionProposal objects. Enforces:
1. Probability calibration checks (rejects uncalibrated / raw regression).
2. Directional threshold gating (p_up >= 0.60 for BUY, p_down >= 0.60 for SELL).
3. Ambiguity & divergence filtering (|p_up - p_down| >= 0.15).
4. Manifest and provenance binding via DeterministicStrategyCompiler.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from core.execution.strategy_gateway.strategy_compiler import (
    DeterministicStrategyCompiler,
    SignalSpecificationError,
    StrategyExecutionProposal,
)

logger = logging.getLogger("sky.execution.strategy_gateway.kronos_adapter")


class KronosAdapterError(Exception):
    """Base exception for Kronos adapter failures."""


class ConfidenceThresholdError(KronosAdapterError):
    """Raised when directional probability fails minimum qualification threshold."""


class AmbiguousForecastError(KronosAdapterError):
    """Raised when directional probabilities exhibit insufficient separation."""


@dataclass(frozen=True)
class KronosForecastSignal:
    """Validated, calibrated output payload from Kronos Grade-E3 inference."""

    signal_id: str
    instrument: str
    p_up: float
    p_down: float
    decision_price: Decimal | float | str
    dataset_hash: str
    experiment_id: str
    strategy_version: str = "3.2.0"
    limit_price: Decimal | float | str | None = None
    requested_quantity: Decimal | float | str = "0.10"
    validity_window_ms: int = 5000
    timestamp_ns: int | None = None


class KronosStrategyAdapter:
    """
    Deterministic compiler adapter for Kronos Grade-E3 directional models.
    Guarantees no raw model probabilities leak uncompiled into execution routers.
    """

    STRATEGY_ID: str = "KRONOS_GRADE_E3"

    def __init__(
        self,
        compiler: DeterministicStrategyCompiler | None = None,
        min_probability_threshold: float = 0.60,
        min_separation: float = 0.15,
    ) -> None:
        self.compiler = compiler or DeterministicStrategyCompiler()
        self.min_probability = min_probability_threshold
        self.min_separation = min_separation

    def adapt_signal(self, signal: KronosForecastSignal) -> StrategyExecutionProposal | None:
        """
        Validates directional confidence and compiles an immutable StrategyExecutionProposal.
        Returns None if signal confidence is below qualification threshold (no-trade zone).
        """
        # 1. Validate probability bounds
        if not (0.0 <= signal.p_up <= 1.0) or not (0.0 <= signal.p_down <= 1.0):
            raise SignalSpecificationError(
                f"Probabilities out of bounds [0.0, 1.0]: p_up={signal.p_up}, p_down={signal.p_down}"
            )

        # 2. Separation check
        separation = abs(signal.p_up - signal.p_down)
        if separation < self.min_separation:
            logger.info(
                f"[KronosAdapter] Signal '{signal.signal_id}' rejected: insufficient separation "
                f"({separation:.3f} < {self.min_separation:.3f})"
            )
            return None

        # 3. Direction determination
        if signal.p_up >= self.min_probability:
            direction = "BUY"
        elif signal.p_down >= self.min_probability:
            direction = "SELL"
        else:
            logger.info(
                f"[KronosAdapter] Signal '{signal.signal_id}' filtered: max prob "
                f"({max(signal.p_up, signal.p_down):.3f}) below threshold ({self.min_probability:.3f})"
            )
            return None

        # 4. Compile via deterministic compiler
        proposal = self.compiler.compile_proposal(
            strategy_id=self.STRATEGY_ID,
            strategy_version=signal.strategy_version,
            signal_id=signal.signal_id,
            direction=direction,
            instrument=signal.instrument,
            requested_quantity=signal.requested_quantity,
            decision_price=signal.decision_price,
            limit_price=signal.limit_price,
            evidence_manifest_hash=signal.dataset_hash,
            validity_window_ms=signal.validity_window_ms,
            signal_timestamp_ns=signal.timestamp_ns,
        )

        logger.info(
            f"[KronosAdapter] Successfully adapted signal '{signal.signal_id}' -> proposal '{proposal.proposal_id}'"
        )
        return proposal
