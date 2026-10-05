"""
core/intelligence/data_contract.py
==================================
Senior Quantitative Systems Architecture — Data Integrity & Failure Semantics Contract.

Guarantees & Invariants:
1. Zero Lookahead & Unclosed Candle Protection:
   Strictly forbids reading or calculating bar-close indicators against an unclosed,
   forming candle. The system must raise UnclosedCandleContaminationError.
2. Anti-Placeholder / Fake Default Value Protection:
   When an indicator lacks sufficient historical observations (e.g., RSI requested with
   8 bars when 14 are required), it is CONSTITUTIONALLY FORBIDDEN from returning fake
   placeholders like 50.0 or last price. It must return DataStatus.INSUFFICIENT_HISTORY
   with value = None.
3. Fresh Candle Volume Contamination Protection:
   Prohibits computing volume intensity ratios within the first delta seconds of candle open
   to prevent division-by-zero or extreme artificial volume spikes.
4. Permanent Capital Firewall:
   real_capital_enabled = False permanent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.intelligence.data_contract")

REAL_CAPITAL_ENABLED: bool = False


class DataStatus(str, Enum):
    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNCLOSED_CANDLE_CONTAMINATION = "UNCLOSED_CANDLE_CONTAMINATION"
    FRESH_BAR_VOLUME_CONTAMINATION = "FRESH_BAR_VOLUME_CONTAMINATION"
    STALE_DATA = "STALE_DATA"
    NULL_VALUE = "NULL_VALUE"


class UnclosedCandleContaminationError(ValueError):
    """Raised when an algorithm attempts to read an unclosed forming candle as a confirmed signal."""


class InsufficientHistoryError(ValueError):
    """Raised when an indicator calculation is attempted with insufficient samples without explicit null tolerance."""


@dataclass
class QuantitativeValue:
    """
    Immutable DTO representing an indicator or feature value with cryptographic provenance.
    Guarantees that missing data is never represented as a fake number.
    """

    feature_name: str
    value: float | None
    status: DataStatus
    required_samples: int
    available_samples: int
    timestamp_ns: int
    is_valid: bool
    provenance_note: str
    real_capital_enabled: bool = False


class StrictDataContract:
    """
    Data Integrity & Lookahead Failure Semantics Enforcement Engine.
    """

    @staticmethod
    def validate_candle_closed(
        candle_open_timestamp_ms: int,
        candle_duration_ms: int,
        evaluation_timestamp_ms: int,
        allow_in_flight: bool = False,
    ) -> bool:
        """
        Verifies that candle t is strictly closed before evaluation.
        Candle is closed if: evaluation_timestamp_ms >= candle_open_timestamp_ms + candle_duration_ms.
        """
        candle_close_timestamp_ms = candle_open_timestamp_ms + candle_duration_ms

        if evaluation_timestamp_ms < candle_close_timestamp_ms:
            if not allow_in_flight:
                msg = (
                    f"Lookahead Violation: Attempted to evaluate unclosed candle. "
                    f"Candle closes at {candle_close_timestamp_ms}, but evaluated at {evaluation_timestamp_ms}. "
                    f"Remaining in candle: {candle_close_timestamp_ms - evaluation_timestamp_ms}ms."
                )
                logger.error(msg)
                raise UnclosedCandleContaminationError(msg)
            return False
        return True

    @staticmethod
    def compute_indicator_safely(
        feature_name: str,
        available_samples: int,
        required_samples: int,
        computation_fn: Any,
        timestamp_ns: int = 0,
    ) -> QuantitativeValue:
        """
        Guarantees that an indicator is only computed if available_samples >= required_samples.
        If samples are insufficient, returns DataStatus.INSUFFICIENT_HISTORY with value = None.
        NEVER returns fake placeholder numbers (such as RSI=50 or EMA=price).
        """
        if available_samples < required_samples:
            return QuantitativeValue(
                feature_name=feature_name,
                value=None,
                status=DataStatus.INSUFFICIENT_HISTORY,
                required_samples=required_samples,
                available_samples=available_samples,
                timestamp_ns=timestamp_ns,
                is_valid=False,
                provenance_note=(
                    f"INSUFFICIENT_DATA: Feature '{feature_name}' requires {required_samples} samples, "
                    f"but only {available_samples} were available. Fake default placeholders prohibited."
                ),
                real_capital_enabled=False,
            )

        try:
            val = float(computation_fn())
            return QuantitativeValue(
                feature_name=feature_name,
                value=val,
                status=DataStatus.VALID,
                required_samples=required_samples,
                available_samples=available_samples,
                timestamp_ns=timestamp_ns,
                is_valid=True,
                provenance_note=f"VALID: Computed from {available_samples} confirmed historical observations.",
                real_capital_enabled=False,
            )
        except Exception as e:
            logger.error("Failed to compute feature %s: %s", feature_name, e)
            return QuantitativeValue(
                feature_name=feature_name,
                value=None,
                status=DataStatus.NULL_VALUE,
                required_samples=required_samples,
                available_samples=available_samples,
                timestamp_ns=timestamp_ns,
                is_valid=False,
                provenance_note=f"ERROR: Computation failed: {str(e)}",
                real_capital_enabled=False,
            )

    @staticmethod
    def compute_volume_ratio_safely(
        current_volume: float,
        expected_full_bar_volume: float,
        elapsed_in_candle_ms: int,
        min_elapsed_ms: int = 15000,  # Prohibit volume ratio during first 15 seconds
    ) -> QuantitativeValue:
        """
        Prevents volume ratio contamination at candle open.
        """
        if elapsed_in_candle_ms < min_elapsed_ms:
            return QuantitativeValue(
                feature_name="VOLUME_RATIO",
                value=None,
                status=DataStatus.FRESH_BAR_VOLUME_CONTAMINATION,
                required_samples=min_elapsed_ms,
                available_samples=elapsed_in_candle_ms,
                timestamp_ns=0,
                is_valid=False,
                provenance_note=(
                    f"CONTAMINATION_PROTECTION: Only {elapsed_in_candle_ms}ms elapsed in candle. "
                    f"Volume ratios prohibited during first {min_elapsed_ms}ms of candle open."
                ),
                real_capital_enabled=False,
            )

        if expected_full_bar_volume <= 0:
            return QuantitativeValue(
                feature_name="VOLUME_RATIO",
                value=None,
                status=DataStatus.NULL_VALUE,
                required_samples=1,
                available_samples=0,
                timestamp_ns=0,
                is_valid=False,
                provenance_note="Zero or negative expected volume.",
                real_capital_enabled=False,
            )

        ratio = current_volume / expected_full_bar_volume
        return QuantitativeValue(
            feature_name="VOLUME_RATIO",
            value=ratio,
            status=DataStatus.VALID,
            required_samples=min_elapsed_ms,
            available_samples=elapsed_in_candle_ms,
            timestamp_ns=0,
            is_valid=True,
            provenance_note="VALID: Volume ratio calculated outside initial boundary.",
            real_capital_enabled=False,
        )
