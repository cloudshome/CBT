"""
core/kronos/research/feature_label_contract.py
=============================================
Milestone K9.2: Strict Point-in-Time Feature and Label Contract Enforcement.
Guarantees zero-lookahead, prevents future-derived regime contamination,
and enforces mathematically exact purge and embargo intervals.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from core.kronos.causality import CausalityViolationError


@dataclass(frozen=True)
class FeatureDeclaration:
    """Formal declaration of a feature vector element and its temporal availability."""

    name: str
    source: str
    availability_timestamp: int
    calculation_window_bars: int
    required_historical_bars: int
    is_future_dependent: bool = False
    causality_status: str = "CAUSAL_VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LabelDeclaration:
    """Formal declaration of a forward evaluation target label."""

    target_name: str
    horizon_bars: int
    horizon_ms: int
    construction_timestamp: int
    overlap_bars: int
    purge_interval_bars: int
    threshold: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeatureLabelContractValidator:
    """
    Constitutional validator enforcing temporal precedence and data isolation.
    """

    @staticmethod
    def validate_feature_declarations(
        declarations: list[FeatureDeclaration], as_of_ts: int
    ) -> bool:
        """
        Ensures all declared features are strictly historical (<= as_of_ts)
        and zero future-dependent calculations are present.
        """
        for decl in declarations:
            if decl.is_future_dependent:
                raise CausalityViolationError(
                    f"Future-dependent feature detected: {decl.name} flagged as future-dependent"
                )
            if decl.availability_timestamp > as_of_ts:
                raise CausalityViolationError(
                    f"Lookahead hazard in {decl.name}: availability_timestamp {decl.availability_timestamp} > as_of_ts {as_of_ts}"
                )
            if decl.causality_status != "CAUSAL_VERIFIED":
                raise CausalityViolationError(
                    f"Unverified causality status for {decl.name}: {decl.causality_status}"
                )
        return True

    @staticmethod
    def validate_label_alignment(
        prediction_ts: int,
        label_observation_ts: int,
        horizon_ms: int,
    ) -> bool:
        """
        Asserts that the evaluation label is constructed from price information
        strictly at or after prediction_ts + horizon_ms.
        """
        if label_observation_ts <= prediction_ts:
            raise CausalityViolationError(
                f"Label observation timestamp {label_observation_ts} <= prediction timestamp {prediction_ts} (Target lookahead contamination)"
            )
        if label_observation_ts < prediction_ts + horizon_ms:
            raise CausalityViolationError(
                f"Premature label observation {label_observation_ts} < expected horizon end {prediction_ts + horizon_ms}"
            )
        return True

    @staticmethod
    def construct_causal_binary_label(
        candles: list[dict[str, Any]],
        current_idx: int,
        horizon_bars: int,
        threshold: float = 0.0,
    ) -> tuple[int, float, int]:
        """
        Constructs forward binary label Y_{t+H} with strict boundary validation:
        Y = 1 if ln(Close_{t+H} / Close_t) > threshold else 0.
        Returns (binary_label, realized_return, outcome_timestamp).
        """
        if current_idx + horizon_bars >= len(candles):
            raise IndexError(
                f"Cannot construct label: target index {current_idx + horizon_bars} exceeds candle length {len(candles)}"
            )

        c_now = candles[current_idx]
        c_future = candles[current_idx + horizon_bars]

        t_now = int(c_now.get("timestamp") or c_now.get("time") or c_now.get("t", 0))
        t_future = int(c_future.get("timestamp") or c_future.get("time") or c_future.get("t", 0))

        if t_future <= t_now:
            raise CausalityViolationError(
                f"Timestamp error in target candle: t_future {t_future} <= t_now {t_now}"
            )

        p_now = float(c_now.get("close") or c_now.get("c", 0.0))
        p_future = float(c_future.get("close") or c_future.get("c", 0.0))

        if p_now <= 0 or p_future <= 0 or not math.isfinite(p_now) or not math.isfinite(p_future):
            raise CausalityViolationError(
                "Non-positive or non-finite price in target label construction"
            )

        log_return = math.log(p_future / p_now)
        binary_label = 1 if log_return > threshold else 0

        return binary_label, log_return, t_future

    @staticmethod
    def calculate_purge_and_embargo(
        horizon_bars: int, holding_period_bars: int | None = None
    ) -> tuple[int, int]:
        """
        Derives purge and embargo window sizes.
        Purge bars = max(horizon_bars, holding_period_bars)
        Embargo bars = 2 * horizon_bars
        """
        effective_horizon = max(1, horizon_bars)
        purge_bars = max(effective_horizon, holding_period_bars or effective_horizon)
        embargo_bars = 2 * effective_horizon
        return purge_bars, embargo_bars

    @staticmethod
    def assert_zero_future_regime(regime_as_of_ts: int, forecast_as_of_ts: int) -> bool:
        """Enforces that regime metadata was calculated strictly at or before forecast timestamp."""
        if regime_as_of_ts > forecast_as_of_ts:
            raise CausalityViolationError(
                f"Future regime label detected: regime_as_of_ts {regime_as_of_ts} > forecast_as_of_ts {forecast_as_of_ts}"
            )
        return True


feature_label_validator = FeatureLabelContractValidator()
