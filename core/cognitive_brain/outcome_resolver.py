"""
core/cognitive_brain/outcome_resolver.py
========================================
Deterministic Outcome Resolution & Calibration Scoring Engine.

Implements:
1. Directional MFE (Maximum Favorable Excursion) & signed MAE (Maximum Adverse Excursion).
2. Explicit intrabar touch ambiguity handling (AMBIGUOUS_INTRABAR_ORDER).
3. Probabilistic Brier score and log-loss calculation.
4. Clean separation between market path, forecast accuracy, and net trading PnL.
5. Counterfactual policy for DISCIPLINED_NO_TRADE and RISK_VETO records.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from core.cognitive_brain.schema import (
    DiagnosticCategory,
    ExecutionStatus,
    ObservationType,
    OutcomePayload,
    ResolutionStatus,
    TradingExperienceRecord,
)
from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger("ai_quant_sentinel.cognitive_brain.outcome_resolver")


class DeterministicOutcomeResolver:
    """
    Pure, deterministic resolution engine evaluating post-freeze price action
    against pre-frozen targets, invalidations, and forecast horizons.
    """

    def __init__(self, conservative_intrabar_resolution: bool = True) -> None:
        self.conservative_intrabar_resolution = conservative_intrabar_resolution

    def resolve_experience(
        self,
        record: TradingExperienceRecord,
        future_candles: list[dict[str, Any]],
    ) -> OutcomePayload:
        """
        Resolves an experience record against chronological future candles.
        Guarantees:
        - Only candles with timestamp >= observation_timestamp_ms are used.
        - Computes true MFE/MAE and detects intrabar target/invalidation touches.
        """
        obs_ts = record.observation.observation_timestamp_ms
        p0 = record.observation.entry_reference_price

        if p0 <= 0:
            return OutcomePayload(
                status=ResolutionStatus.UNRESOLVED_DATA,
                diagnostic_category=DiagnosticCategory.UNRESOLVED,
                diagnostic_summary="Invalid entry reference price (P0 <= 0)",
            )

        # Filter and sort future candles chronologically
        valid_candles = [c for c in future_candles if c.get("timestamp", 0) >= obs_ts]
        valid_candles.sort(key=lambda x: x["timestamp"])

        if not valid_candles:
            return OutcomePayload(
                status=ResolutionStatus.UNRESOLVED_DATA,
                diagnostic_category=DiagnosticCategory.UNRESOLVED,
                diagnostic_summary="No valid forward candles found after observation timestamp",
            )

        horizon_bars = max(1, record.forecast.horizon_bars)
        eval_candles = valid_candles[:horizon_bars]

        direction = record.forecast.direction
        target_p = record.forecast.target_price
        inval_p = record.forecast.invalidation_price

        # Track mathematical excursions
        # Long: favorable = (high - P0) / P0, adverse = (low - P0) / P0
        # Short: favorable = (P0 - low) / P0, adverse = (P0 - high) / P0
        max_favorable_ratio = 0.0
        max_adverse_ratio = 0.0

        hit_target_first = False
        hit_invalidation_first = False
        is_ambiguous = False
        resolution_status = ResolutionStatus.PENDING
        resolved_price = float(eval_candles[-1].get("close", p0))
        resolved_at_ms = int(eval_candles[-1].get("timestamp", obs_ts))

        for idx, bar in enumerate(eval_candles):
            h = float(bar.get("high", bar.get("close", p0)))
            l = float(bar.get("low", bar.get("close", p0)))
            c = float(bar.get("close", p0))

            if direction == DecisionAction.LONG:
                fav = (h - p0) / p0
                adv = (l - p0) / p0
                bar_hits_target = h >= target_p
                bar_hits_inval = l <= inval_p
            elif direction == DecisionAction.SHORT:
                fav = (p0 - l) / p0
                adv = (p0 - h) / p0
                bar_hits_target = l <= target_p
                bar_hits_inval = h >= inval_p
            else:
                # Neutral / WATCH / NO_SETUP
                fav = abs(c - p0) / p0
                adv = -abs(c - p0) / p0
                bar_hits_target = False
                bar_hits_inval = False

            max_favorable_ratio = max(max_favorable_ratio, fav)
            max_adverse_ratio = min(max_adverse_ratio, adv)

            # Check intrabar ambiguity (both touched in same candle)
            if bar_hits_target and bar_hits_inval:
                is_ambiguous = True
                resolution_status = ResolutionStatus.AMBIGUOUS_INTRABAR_ORDER
                resolved_price = inval_p if self.conservative_intrabar_resolution else target_p
                resolved_at_ms = int(bar.get("timestamp", obs_ts))
                hit_invalidation_first = True
                hit_target_first = False
                break

            if bar_hits_target:
                hit_target_first = True
                resolution_status = ResolutionStatus.HIT_TARGET
                resolved_price = target_p
                resolved_at_ms = int(bar.get("timestamp", obs_ts))
                break

            if bar_hits_inval:
                hit_invalidation_first = True
                resolution_status = ResolutionStatus.HIT_INVALIDATION
                resolved_price = inval_p
                resolved_at_ms = int(bar.get("timestamp", obs_ts))
                break

        if resolution_status == ResolutionStatus.PENDING:
            resolution_status = ResolutionStatus.TIME_EXPIRED

        # Excursion in basis points
        mfe_bps = round(max_favorable_ratio * 10_000.0, 2)
        mae_bps = round(max_adverse_ratio * 10_000.0, 2)  # Signed (<= 0)

        # Probabilistic scoring (Brier score & log-loss)
        p = record.forecast.calibrated_probability
        if p is None:
            p = record.forecast.raw_confidence
        p = max(0.0001, min(0.9999, float(p)))

        # Define binary outcome y: 1 if target hit or expired favorably, 0 if invalidation hit
        if resolution_status == ResolutionStatus.HIT_TARGET:
            y = 1.0
        elif resolution_status == ResolutionStatus.HIT_INVALIDATION:
            y = 0.0
        elif resolution_status == ResolutionStatus.AMBIGUOUS_INTRABAR_ORDER:
            y = 0.0 if self.conservative_intrabar_resolution else 0.5
        else:
            # TIME_EXPIRED: 1.0 if closed in forecast direction, else 0.0
            if direction == DecisionAction.LONG:
                y = 1.0 if resolved_price > p0 else 0.0
            elif direction == DecisionAction.SHORT:
                y = 1.0 if resolved_price < p0 else 0.0
            else:
                y = 0.5

        brier_score = round(float((p - y) ** 2), 4)
        log_loss = round(float(-(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))), 4)

        # Calculate Financial Outcomes
        # Directional Gross return in bps
        if direction == DecisionAction.LONG:
            gross_pnl_bps = ((resolved_price - p0) / p0) * 10_000.0
        elif direction == DecisionAction.SHORT:
            gross_pnl_bps = ((p0 - resolved_price) / p0) * 10_000.0
        else:
            gross_pnl_bps = 0.0

        # Total roundtrip friction (fees + slippage)
        fee_bps = record.execution.taker_fee_bps if record.execution else 5.0
        slip_bps = record.execution.est_slippage_bps if record.execution else 1.0
        roundtrip_friction_bps = (fee_bps * 2.0) + (slip_bps * 2.0)

        realized_net_pnl_bps = None
        counterfactual_net_pnl_bps = None

        if record.execution and record.execution.status == ExecutionStatus.PAPER_FILLED:
            # Actual paper trade took place
            realized_net_pnl_bps = round(gross_pnl_bps - roundtrip_friction_bps, 2)
        else:
            # NO_TRADE or RISK_VETO: Track counterfactual ONLY (never pretend a fill occurred)
            counterfactual_net_pnl_bps = round(gross_pnl_bps - roundtrip_friction_bps, 2)

        # Determine diagnostic category
        diag_category, diag_summary = self._classify_diagnostic(
            record=record,
            resolution_status=resolution_status,
            gross_pnl_bps=gross_pnl_bps,
            realized_net_pnl_bps=realized_net_pnl_bps,
            counterfactual_net_pnl_bps=counterfactual_net_pnl_bps,
            is_ambiguous=is_ambiguous,
        )

        return OutcomePayload(
            status=resolution_status,
            resolved_at_ms=resolved_at_ms,
            realization_path_length=len(eval_candles),
            final_price=resolved_price,
            mfe_bps=mfe_bps,
            mae_bps=mae_bps,
            hit_target_first=hit_target_first,
            hit_invalidation_first=hit_invalidation_first,
            brier_score=brier_score,
            log_loss=log_loss,
            realized_net_pnl_bps=realized_net_pnl_bps,
            counterfactual_net_pnl_bps=counterfactual_net_pnl_bps,
            friction_drag_bps=roundtrip_friction_bps,
            diagnostic_category=diag_category,
            diagnostic_summary=diag_summary,
        )

    def _classify_diagnostic(
        self,
        record: TradingExperienceRecord,
        resolution_status: ResolutionStatus,
        gross_pnl_bps: float,
        realized_net_pnl_bps: float | None,
        counterfactual_net_pnl_bps: float | None,
        is_ambiguous: bool,
    ) -> tuple[DiagnosticCategory, str]:
        """Synthesizes an institutional diagnostic autopsy."""
        if is_ambiguous:
            return (
                DiagnosticCategory.AMBIGUOUS,
                "Both target and invalidation price levels were breached in the same bar; resolved conservatively.",
            )

        if record.observation_type == ObservationType.DISCIPLINED_NO_TRADE:
            cf = counterfactual_net_pnl_bps or 0.0
            if cf <= 0.0:
                return (
                    DiagnosticCategory.ABSTENTION_JUSTIFIED,
                    f"Disciplined NO_TRADE justified: hypothetical position would have lost {cf:.1f} bps.",
                )
            else:
                return (
                    DiagnosticCategory.ABSTENTION_MISSED_OPPORTUNITY,
                    f"Disciplined NO_TRADE missed gain: hypothetical position would have gained {cf:.1f} bps.",
                )

        # For proposals / executed trades:
        net = realized_net_pnl_bps if realized_net_pnl_bps is not None else (counterfactual_net_pnl_bps or 0.0)

        if resolution_status == ResolutionStatus.HIT_TARGET or gross_pnl_bps > 0:
            if net > 0:
                return (
                    DiagnosticCategory.ACCURATE_PROFITABLE,
                    f"Directional forecast verified and net profitable (+{net:.1f} bps).",
                )
            else:
                return (
                    DiagnosticCategory.ACCURATE_COST_EROSION,
                    f"Directional forecast verified (+{gross_pnl_bps:.1f} bps gross) but wiped out by friction ({net:.1f} bps net).",
                )

        return (
            DiagnosticCategory.DIRECTION_FAILURE,
            f"Forecast failed: price hit invalidation ({net:.1f} bps net loss).",
        )

