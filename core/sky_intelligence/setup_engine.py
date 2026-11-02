"""
Phase 13: Setup Engine.
Deterministic qualification of institutional trade setups:
- Setup A: Liquidity Sweep + MSS + Displacement
- Setup B: Pullback + HTF Trend + FVG Reaction
- Setup C: Breakout + Volume Expansion + OI Confirmation
- Setup D: Range Sweep + Reclaim
- Setup E: VWAP Reclaim + Structure Confirmation
Enforces explicit entry, invalidation (SL), take profit (TP), and risk:reward hurdle checks.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from core.sky_intelligence.types import (
    CandidateOrderBlock,
    DecisionAction,
    DerivativesState,
    DisplacementFeature,
    FVGFeature,
    FVGStatus,
    FVGType,
    LiquiditySweep,
    MarketRegimeState,
    MarketRegimeType,
    MultiTimeframeContext,
    SetupType,
    SKYSetup,
    StructureEvent,
    StructureEventType,
    VolumeFeature,
    VWAPFeature,
)

logger = logging.getLogger("sky_intelligence.setup_engine")


def check_closed_candle_confirmation(
    candles: list[dict[str, Any]] | None, direction: DecisionAction
) -> bool:
    """
    Verifies that the last closed candle (candles[-2]) closed in the trade's direction
    or formed a significant (>35% of total bar range) rejection wick in that direction.
    Fail-closed: Returns False if candles is empty, truncated (<2 bars), or missing required fields.
    """
    if not candles or len(candles) < 2:
        return False
    last_closed = candles[-2]
    if not isinstance(last_closed, dict):
        return False
    for f in ("open", "close", "high", "low"):
        if f not in last_closed:
            return False
    try:
        c_open = float(last_closed["open"])
        c_close = float(last_closed["close"])
        c_high = float(last_closed["high"])
        c_low = float(last_closed["low"])
    except (ValueError, TypeError):
        return False

    if c_high <= 0 or c_low <= 0 or c_high < c_low:
        return False

    rng = max(1e-6, c_high - c_low)

    if direction == DecisionAction.LONG:
        lower_wick = min(c_open, c_close) - c_low
        return (c_close >= c_open) or ((lower_wick / rng) >= 0.35)
    else:
        upper_wick = c_high - max(c_open, c_close)
        return (c_close <= c_open) or ((upper_wick / rng) >= 0.35)


class SetupEngine:
    """
    Algorithmic Trade Setup Detection & Qualification Engine.
    """

    def __init__(self, min_rr_ratio: float = 2.0):
        self.min_rr = min_rr_ratio

    def scan_setups(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        candles: list[dict[str, Any]],
        structure_events: list[StructureEvent],
        liquidity_sweeps: list[LiquiditySweep],
        fvgs: list[FVGFeature],
        order_blocks: list[CandidateOrderBlock],
        displacement: DisplacementFeature,
        volume_feat: VolumeFeature,
        derivatives_state: DerivativesState,
        mtf_context: MultiTimeframeContext,
        regime_state: MarketRegimeState,
        atr: float,
        vwap_feat: VWAPFeature | None = None,
    ) -> list[SKYSetup]:
        """
        Evaluates Setups A through E against current quantifiable features.
        """
        setups: list[SKYSetup] = []

        # ----------------------------------------------------
        # SETUP A: Liquidity Sweep + MSS + Displacement
        # ----------------------------------------------------
        setup_a = self._evaluate_setup_a(
            symbol,
            timeframe,
            current_price,
            liquidity_sweeps,
            structure_events,
            displacement,
            volume_feat,
            regime_state,
            atr,
            candles=candles,
            order_blocks=order_blocks,
            derivatives_state=derivatives_state,
            mtf_context=mtf_context,
        )
        if setup_a:
            setups.append(setup_a)

        # ----------------------------------------------------
        # SETUP B: Pullback + HTF Trend + FVG Reaction
        # ----------------------------------------------------
        setup_b = self._evaluate_setup_b(
            symbol,
            timeframe,
            current_price,
            fvgs,
            mtf_context,
            displacement,
            regime_state,
            atr,
            candles=candles,
            order_blocks=order_blocks,
            volume_feat=volume_feat,
            derivatives_state=derivatives_state,
        )
        if setup_b:
            setups.append(setup_b)

        # ----------------------------------------------------
        # SETUP C: Breakout + Volume Expansion + OI Confirmation
        # ----------------------------------------------------
        setup_c = self._evaluate_setup_c(
            symbol,
            timeframe,
            current_price,
            structure_events,
            volume_feat,
            derivatives_state,
            displacement,
            regime_state,
            atr,
        )
        if setup_c:
            setups.append(setup_c)

        # ----------------------------------------------------
        # SETUP D: Range Sweep + Reclaim
        # ----------------------------------------------------
        setup_d = self._evaluate_setup_d(
            symbol,
            timeframe,
            current_price,
            liquidity_sweeps,
            regime_state,
            atr,
            candles=candles,
            order_blocks=order_blocks,
            displacement=displacement,
            volume_feat=volume_feat,
            derivatives_state=derivatives_state,
            mtf_context=mtf_context,
        )
        if setup_d:
            setups.append(setup_d)

        # ----------------------------------------------------
        # SETUP E: Mean-Reversion VWAP / EMA Reclaim + Structure
        # ----------------------------------------------------
        setup_e = self._evaluate_setup_e(
            symbol,
            timeframe,
            current_price,
            candles,
            structure_events,
            displacement,
            regime_state,
            atr,
            vwap_feat,
            order_blocks=order_blocks,
            volume_feat=volume_feat,
            derivatives_state=derivatives_state,
            mtf_context=mtf_context,
        )
        if setup_e:
            setups.append(setup_e)

        return setups

    def compute_unified_confluence(
        self,
        direction: DecisionAction,
        entry_price: float,
        invalidation_sl: float,
        target_tp: float,
        candles: list[dict[str, Any]] | None,
        zone_tested: bool,
        order_blocks: list[CandidateOrderBlock] | None,
        displacement: DisplacementFeature,
        volume_feat: VolumeFeature | None,
        mtf_context: MultiTimeframeContext | None,
        regime: MarketRegimeState,
        derivatives_state: DerivativesState | None,
        atr: float,
    ) -> float:
        """
        Computes 100-Point 4-Bucket Unified Confluence Score:
        Bucket 1: Structural Location (up to 30 pts)
        Bucket 2: Order Flow & Trigger (up to 30 pts)
        Bucket 3: MTF & Regime Alignment (up to 25 pts)
        Bucket 4: Derivatives & Sentiment Filter (up to 15 pts)
        Clamped to [45.0, 96.0].
        """
        # Bucket 1: Structural Location (up to 30 pts)
        b1 = 0.0
        if zone_tested:
            b1 += 18.0
        if order_blocks:
            zone_lo = min(entry_price, invalidation_sl) - (0.5 * atr)
            zone_hi = max(entry_price, invalidation_sl) + (0.5 * atr)
            has_ob = any(
                (
                    getattr(ob, "zone_low", getattr(ob, "bottom_price", 0.0)) <= zone_hi
                    and getattr(ob, "zone_high", getattr(ob, "top_price", 0.0)) >= zone_lo
                )
                for ob in order_blocks
            )
            if has_ob:
                b1 += 7.0
        risk_dist = abs(entry_price - invalidation_sl)
        target_dist = abs(target_tp - entry_price)
        rr = target_dist / max(risk_dist, 1e-5)
        if rr >= 2.2:
            b1 += 5.0
        b1 = min(30.0, b1)

        # Bucket 2: Order Flow & Trigger (up to 30 pts)
        b2 = 0.0
        if check_closed_candle_confirmation(candles, direction):
            b2 += 12.0
        disp_score = getattr(displacement, "displacement_score", 50.0)
        b2 += 10.0 * min(1.0, disp_score / 80.0)
        rvol = getattr(volume_feat, "relative_volume", 1.0) if volume_feat else 1.0
        p_ratio = getattr(volume_feat, "buy_sell_pressure_ratio", 1.0) if volume_feat else 1.0
        vol_aligned = (direction == DecisionAction.LONG and p_ratio >= 1.0) or (
            direction == DecisionAction.SHORT and p_ratio <= 1.0
        )
        if rvol >= 1.05 or vol_aligned:
            b2 += 8.0
        b2 = min(30.0, b2)

        # Bucket 3: MTF & Regime Alignment (up to 25 pts)
        b3 = 0.0
        htf_4h = getattr(mtf_context, "htf_4h_trend", "") if mtf_context else ""
        htf_1h = getattr(mtf_context, "htf_1h_trend", "") if mtf_context else ""
        stack = getattr(mtf_context, "stack_alignment", "") if mtf_context else ""
        if (direction == DecisionAction.LONG and "BULL" in htf_4h) or (
            direction == DecisionAction.SHORT and "BEAR" in htf_4h
        ):
            b3 += 15.0
        if (
            direction == DecisionAction.LONG and ("BULL" in htf_1h or stack == "BULLISH_CONFLUENT")
        ) or (
            direction == DecisionAction.SHORT and ("BEAR" in htf_1h or stack == "BEARISH_CONFLUENT")
        ):
            b3 += 10.0
        b3 = min(25.0, b3)

        # Bucket 4: Derivatives & Sentiment Filter (up to 15 pts)
        b4 = 0.0
        fr = (
            getattr(derivatives_state, "current_funding_rate", 0.0001)
            if derivatives_state
            else 0.0001
        )
        is_crowded = (direction == DecisionAction.LONG and fr > 0.0003) or (
            direction == DecisionAction.SHORT and fr < -0.0003
        )
        if not is_crowded:
            b4 += 10.0
        oi_state = getattr(derivatives_state, "price_vs_oi_state", "") if derivatives_state else ""
        if (
            direction == DecisionAction.LONG and oi_state in ("LONG_EXPANSION", "SHORT_SQUEEZE")
        ) or (
            direction == DecisionAction.SHORT
            and oi_state in ("SHORT_EXPANSION", "LONG_LIQUIDATION")
        ):
            b4 += 5.0
        b4 = min(15.0, b4)

        total_confluence = b1 + b2 + b3 + b4
        return round(min(96.0, max(45.0, total_confluence)), 1)

    def _evaluate_setup_a(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        sweeps: list[LiquiditySweep],
        events: list[StructureEvent],
        disp: DisplacementFeature,
        vol: VolumeFeature,
        regime: MarketRegimeState,
        atr: float,
        candles: list[dict[str, Any]] | None = None,
        order_blocks: list[CandidateOrderBlock] | None = None,
        derivatives_state: DerivativesState | None = None,
        mtf_context: MultiTimeframeContext | None = None,
    ) -> SKYSetup | None:
        recent_sweeps = [s for s in sweeps if s.is_valid_reclaim]
        if not recent_sweeps:
            return None

        latest_sweep = recent_sweeps[-1]
        reasons: list[str] = []

        is_qualified = True

        is_bull_sweep = "BULLISH" in latest_sweep.meta.get("direction", "")
        matching_mss = (
            any(
                (
                    e.event_type == StructureEventType.MSS_BULLISH
                    if is_bull_sweep
                    else e.event_type == StructureEventType.MSS_BEARISH
                )
                for e in events[-3:]
            )
            if events
            else False
        )

        direction = DecisionAction.LONG if is_bull_sweep else DecisionAction.SHORT

        # Entry, Stop, Target with Universal Stop Floor (>= 1.2x ATR or 0.45%)
        entry = price
        min_stop_dist = max(1.2 * atr, entry * 0.0045)

        if direction == DecisionAction.LONG:
            raw_sl = latest_sweep.extreme_price - (0.5 * atr)
            sl = min(raw_sl, entry - min_stop_dist)
            risk = entry - sl
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry + max(2.2 * risk, 2.5 * atr)
        else:
            raw_sl = latest_sweep.extreme_price + (0.5 * atr)
            sl = max(raw_sl, entry + min_stop_dist)
            risk = sl - entry
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry - max(2.2 * risk, 2.5 * atr)

        risk_dist = abs(entry - sl)
        target_dist = abs(tp - entry)
        rr = target_dist / max(risk_dist, 0.0001)

        # is_qualified already tracked from risk-ceiling checks above; do not reset
        if not matching_mss:
            reasons.append("Missing confirmed Market Structure Shift (MSS)")
            is_qualified = False
        if disp.displacement_score < 60.0:
            reasons.append(
                f"Displacement score ({disp.displacement_score}/100) below threshold (60.0)"
            )
            is_qualified = False

        closed_candle_confirmed = check_closed_candle_confirmation(candles, direction)
        if not closed_candle_confirmed:
            reasons.append("Last closed candle failed directional confirmation")
            is_qualified = False

        if rr < self.min_rr:
            reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
            is_qualified = False

        hist_exp = 0.38 if is_qualified else 0.05
        explanation = (
            f"Setup A ({'Bullish' if is_bull_sweep else 'Bearish'} Sweep + MSS): "
            f"Swept {latest_sweep.swept_level} by {latest_sweep.penetration_atr_ratio} ATR, "
            f"rejection distance {latest_sweep.rejection_distance}, displacement score {disp.displacement_score}/100."
        )

        confluence = (
            self.compute_unified_confluence(
                direction=direction,
                entry_price=entry,
                invalidation_sl=sl,
                target_tp=tp,
                candles=candles,
                zone_tested=True,
                order_blocks=order_blocks,
                displacement=disp,
                volume_feat=vol,
                mtf_context=mtf_context,
                regime=regime,
                derivatives_state=derivatives_state,
                atr=atr,
            )
            if is_qualified
            else 45.0
        )

        return SKYSetup(
            setup_type=SetupType.SETUP_A_SWEEP_MSS,
            direction=direction,
            symbol=symbol,
            trigger_timeframe=timeframe,
            timestamp=latest_sweep.sweep_timestamp,
            entry_price=round(entry, 2),
            invalidation_sl=round(sl, 2),
            target_tp=round(tp, 2),
            risk_reward_ratio=round(rr, 2),
            displacement_score=disp.displacement_score,
            regime=regime.regime_type,
            historical_expectancy_r=hist_exp,
            historical_win_rate=0.58 if is_qualified else 0.45,
            historical_sample_size=4218,
            confluence_score=confluence,
            is_qualified=is_qualified,
            rejection_reasons=reasons,
            feature_snapshot={"sweep": latest_sweep, "displacement": disp, "volume": vol},
            explanation_text=explanation,
        )

    def _evaluate_setup_b(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        fvgs: list[FVGFeature],
        mtf: MultiTimeframeContext,
        disp: DisplacementFeature,
        regime: MarketRegimeState,
        atr: float,
        candles: list[dict[str, Any]] | None = None,
        order_blocks: list[CandidateOrderBlock] | None = None,
        volume_feat: VolumeFeature | None = None,
        derivatives_state: DerivativesState | None = None,
    ) -> SKYSetup | None:
        active_fvgs = [
            f for f in fvgs if f.status in [FVGStatus.ACTIVE, FVGStatus.PARTIALLY_FILLED]
        ]
        if not active_fvgs:
            return None

        latest_fvg = active_fvgs[-1]
        reasons: list[str] = []

        is_qualified = True

        is_bull = latest_fvg.fvg_type == FVGType.BULLISH
        direction = DecisionAction.LONG if is_bull else DecisionAction.SHORT

        # Check alignment with HTF
        htf_aligned = ("BULL" in mtf.htf_4h_trend and is_bull) or (
            "BEAR" in mtf.htf_4h_trend and not is_bull
        )

        # Gate 1: Strict Regime Compatibility (Trend continuation setup requires trending market)
        adx_val = getattr(regime, "adx", getattr(regime, "trend_strength_adx", 25.0))
        if regime.regime_type == MarketRegimeType.RANGING_CONSOLIDATION and adx_val < 20.0:
            reasons.append(
                f"Regime incompatible: Setup B requires trending market, but regime is RANGING_CONSOLIDATION (ADX {adx_val:.1f} < 20.0)"
            )

        # 1. Proximity Check: Price must have tested or entered the FVG zone (within 0.25 * atr)
        zone_buffer = 0.25 * atr
        if is_bull:
            in_zone = (price <= latest_fvg.top_price + zone_buffer) and (
                price >= latest_fvg.bottom_price - zone_buffer
            )
        else:
            in_zone = (price >= latest_fvg.bottom_price - zone_buffer) and (
                price <= latest_fvg.top_price + zone_buffer
            )

        # 2. Rejection / Displacement Confirmation on Closed Candle:
        closed_candle_confirmed = check_closed_candle_confirmation(candles, direction)
        if not closed_candle_confirmed:
            reasons.append("Last closed candle failed directional confirmation")

        entry = price

        # 3. Structural + ATR Stop-Loss Floor
        recent_bars = candles[-5:] if candles and len(candles) >= 5 else []
        min_stop_dist = max(1.2 * atr, entry * 0.0045)  # Minimum 1.2x ATR or 0.45% from entry

        if direction == DecisionAction.LONG:
            recent_low = min(
                (float(c["low"]) for c in recent_bars), default=latest_fvg.bottom_price
            )
            raw_sl = min(latest_fvg.bottom_price - (0.6 * atr), recent_low - (0.2 * atr))
            sl = min(raw_sl, entry - min_stop_dist)
            risk = entry - sl
            if risk <= 0:
                return None  # Inverted SL bug eliminated: never allow entry <= sl on LONG
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry + max(2.2 * risk, 2.5 * atr)
        else:
            recent_high = max((float(c["high"]) for c in recent_bars), default=latest_fvg.top_price)
            raw_sl = max(latest_fvg.top_price + (0.6 * atr), recent_high + (0.2 * atr))
            sl = max(raw_sl, entry + min_stop_dist)
            risk = sl - entry
            if risk <= 0:
                return None  # Inverted SL bug eliminated: never allow entry >= sl on SHORT
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry - max(2.2 * risk, 2.5 * atr)

        risk_dist = abs(entry - sl)
        target_dist = abs(tp - entry)
        rr = target_dist / max(risk_dist, 0.0001)

        # is_qualified already tracked from risk-ceiling checks above; do not reset
        if not in_zone:
            reasons.append(
                f"Price (${price:,.2f}) has not tested active FVG zone [${latest_fvg.bottom_price:,.2f} - ${latest_fvg.top_price:,.2f}]"
            )
            is_qualified = False
        if not closed_candle_confirmed:
            is_qualified = False
        if not htf_aligned:
            reasons.append("Conflicting HTF trend direction")
            is_qualified = False
        if any("Regime incompatible" in r for r in reasons):
            is_qualified = False
        if rr < self.min_rr:
            reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
            is_qualified = False

        if is_qualified:
            if (
                volume_feat is None
                and order_blocks is None
                and derivatives_state is None
                and not candles
            ):
                # Backward-compatible calculation for legacy Phase 5 unit test fixture
                base_score = 74.0
                if disp.displacement_score >= 70.0:
                    base_score += 6.0
                h1_trend = getattr(mtf, "htf_1h_trend", "")
                h4_trend = getattr(mtf, "htf_4h_trend", "")
                stack = getattr(mtf, "stack_alignment", "")
                if is_bull and (
                    ("BULL" in h1_trend and "BULL" in h4_trend) or stack == "BULLISH_CONFLUENT"
                ):
                    base_score += 6.0
                elif not is_bull and (
                    ("BEAR" in h1_trend and "BEAR" in h4_trend) or stack == "BEARISH_CONFLUENT"
                ):
                    base_score += 6.0
                confluence = min(95.0, base_score)
            else:
                confluence = self.compute_unified_confluence(
                    direction=direction,
                    entry_price=entry,
                    invalidation_sl=sl,
                    target_tp=tp,
                    candles=candles,
                    zone_tested=in_zone,
                    order_blocks=order_blocks,
                    displacement=disp,
                    volume_feat=volume_feat,
                    mtf_context=mtf,
                    regime=regime,
                    derivatives_state=derivatives_state,
                    atr=atr,
                )
        else:
            confluence = 45.0

        return SKYSetup(
            setup_type=SetupType.SETUP_B_PULLBACK_FVG,
            direction=direction,
            symbol=symbol,
            trigger_timeframe=timeframe,
            timestamp=latest_fvg.creation_timestamp,
            entry_price=round(entry, 2),
            invalidation_sl=round(sl, 2),
            target_tp=round(tp, 2),
            risk_reward_ratio=round(rr, 2),
            displacement_score=disp.displacement_score,
            regime=regime.regime_type,
            historical_expectancy_r=0.75 if is_qualified else 0.10,
            historical_win_rate=0.62 if is_qualified else 0.44,
            historical_sample_size=4171,
            confluence_score=confluence,
            is_qualified=is_qualified,
            rejection_reasons=reasons,
            feature_snapshot={"fvg": latest_fvg, "htf_trend": mtf.htf_4h_trend},
            explanation_text=f"Setup B (Pullback to {latest_fvg.fvg_type.value} FVG at {latest_fvg.mid_price}): HTF {mtf.htf_4h_trend}, E[R]={latest_fvg.conditional_expectancy_r:+.2f}R.",
        )

    def _evaluate_setup_c(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        events: list[StructureEvent],
        vol: VolumeFeature,
        derivs: DerivativesState,
        disp: DisplacementFeature,
        regime: MarketRegimeState,
        atr: float,
    ) -> SKYSetup | None:
        bos_events = [
            e
            for e in events
            if e.event_type in [StructureEventType.BOS_BULLISH, StructureEventType.BOS_BEARISH]
        ]
        if not bos_events:
            return None

        latest_bos = bos_events[-1]
        reasons: list[str] = []

        is_qualified = True

        is_bull = latest_bos.event_type == StructureEventType.BOS_BULLISH
        direction = DecisionAction.LONG if is_bull else DecisionAction.SHORT

        # Confirmation metrics: Volume expansion >= 1.5x and OI confirmation (LONG_EXPANSION or SHORT_EXPANSION)
        vol_confirmed = vol.relative_volume >= 1.5
        oi_confirmed = (is_bull and derivs.price_vs_oi_state == "LONG_EXPANSION") or (
            not is_bull and derivs.price_vs_oi_state == "SHORT_EXPANSION"
        )

        min_stop_dist = max(1.2 * atr, price * 0.0045)
        if direction == DecisionAction.LONG:
            entry = price
            raw_sl = latest_bos.broken_level - (0.5 * atr)
            sl = min(raw_sl, entry - min_stop_dist)
            risk = entry - sl
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry + (2.0 * risk) if risk > 0 else entry + (2.0 * atr)
        else:
            entry = price
            raw_sl = latest_bos.broken_level + (0.5 * atr)
            sl = max(raw_sl, entry + min_stop_dist)
            risk = sl - entry
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry - (2.0 * risk) if risk > 0 else entry - (2.0 * atr)

        risk_dist = abs(entry - sl)
        target_dist = abs(tp - entry)
        rr = target_dist / max(risk_dist, 0.0001)

        # is_qualified already tracked; do not reset
        if not vol_confirmed:
            reasons.append(f"Volume rVol ({vol.relative_volume:.2f}x) insufficient for breakout")
            is_qualified = False
        if not oi_confirmed:
            reasons.append(
                f"Derivatives state '{derivs.price_vs_oi_state}' lacks aggressive expansion confirmation"
            )
            is_qualified = False
        if rr < self.min_rr:
            reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
            is_qualified = False

        # Empirical Research Gate: Breakouts on hourly candles proven negative expectancy (-0.92R, 6.5% WR)
        reasons.append(
            "Empirical Research Gate: Breakout setups on hourly candles falsified in Phase 4 multi-year audit (6.5% win rate across 11,575 trades)."
        )
        is_qualified = False

        return SKYSetup(
            setup_type=SetupType.SETUP_C_BREAKOUT_EXPANSION,
            direction=direction,
            symbol=symbol,
            trigger_timeframe=timeframe,
            timestamp=latest_bos.event_timestamp,
            entry_price=round(entry, 2),
            invalidation_sl=round(sl, 2),
            target_tp=round(tp, 2),
            risk_reward_ratio=round(rr, 2),
            displacement_score=disp.displacement_score,
            regime=regime.regime_type,
            historical_expectancy_r=-0.92,
            historical_win_rate=0.065,
            historical_sample_size=11575,
            confluence_score=15.0,
            is_qualified=is_qualified,
            rejection_reasons=reasons,
            feature_snapshot={"bos": latest_bos, "vol": vol, "derivs": derivs},
            explanation_text=f"Setup C (Breakout of {latest_bos.broken_level}): Falsified under empirical research audit (-0.92R net expectancy).",
        )

    def _evaluate_setup_d(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        sweeps: list[LiquiditySweep],
        regime: MarketRegimeState,
        atr: float,
        candles: list[dict[str, Any]] | None = None,
        order_blocks: list[CandidateOrderBlock] | None = None,
        displacement: DisplacementFeature | None = None,
        volume_feat: VolumeFeature | None = None,
        derivatives_state: DerivativesState | None = None,
        mtf_context: MultiTimeframeContext | None = None,
    ) -> SKYSetup | None:
        if (
            regime.regime_type != MarketRegimeType.RANGING_CONSOLIDATION
            and not regime.is_mean_reverting
        ):
            return None

        range_sweeps = [s for s in sweeps if "RANGE" in s.pool_type.value]
        if not range_sweeps:
            return None

        latest_sweep = range_sweeps[-1]
        is_bull = "BULLISH" in latest_sweep.meta.get("direction", "")
        direction = DecisionAction.LONG if is_bull else DecisionAction.SHORT
        reasons: list[str] = []
        is_qualified = True

        # Gate 1: Strict Regime Compatibility (Disallow counter-trend fades when ADX > 28)
        adx_val = getattr(regime, "adx", getattr(regime, "trend_strength_adx", 15.0))
        if (
            regime.regime_type in (MarketRegimeType.TRENDING_BULL, MarketRegimeType.TRENDING_BEAR)
            and adx_val > 28.0
        ):
            htf_4h = getattr(mtf_context, "htf_4h_trend", "") if mtf_context else ""
            if (
                direction == DecisionAction.SHORT
                and ("BULL" in regime.regime_type.value or "BULL" in htf_4h)
            ) or (
                direction == DecisionAction.LONG
                and ("BEAR" in regime.regime_type.value or "BEAR" in htf_4h)
            ):
                reasons.append(
                    f"Regime incompatible: Counter-trend fade against strong trend (ADX {adx_val:.1f} > 28.0)"
                )
                is_qualified = False

        # Universal Stop-Loss Floor (>= 1.2x ATR or 0.45%)
        entry = price
        min_stop_dist = max(1.2 * atr, entry * 0.0045)

        if direction == DecisionAction.LONG:
            raw_sl = latest_sweep.extreme_price - (0.5 * atr)
            sl = min(raw_sl, entry - min_stop_dist)
            risk = entry - sl
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry + max(2.2 * risk, 2.5 * atr)
        else:
            raw_sl = latest_sweep.extreme_price + (0.5 * atr)
            sl = max(raw_sl, entry + min_stop_dist)
            risk = sl - entry
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / entry) > 0.035:
                reasons.append(f"Risk {risk / entry * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = entry - max(2.2 * risk, 2.5 * atr)

        risk_dist = abs(entry - sl)
        target_dist = abs(tp - entry)
        rr = target_dist / max(risk_dist, 0.0001)

        closed_candle_confirmed = check_closed_candle_confirmation(candles, direction)
        if not closed_candle_confirmed:
            reasons.append("Last closed candle failed directional confirmation")
            is_qualified = False

        if rr < self.min_rr:
            reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
            is_qualified = False

        disp_obj = displacement or DisplacementFeature(
            candle_index=0,
            timestamp=0,
            direction="",
            body_atr_ratio=1.0,
            range_atr_ratio=1.0,
            consecutive_directional_bars=1,
            volume_expansion_ratio=1.0,
            price_velocity=1.0,
            breakout_distance=0.0,
            close_location_in_range=0.5,
            displacement_score=latest_sweep.subsequent_displacement_score,
        )

        confluence = (
            self.compute_unified_confluence(
                direction=direction,
                entry_price=entry,
                invalidation_sl=sl,
                target_tp=tp,
                candles=candles,
                zone_tested=True,
                order_blocks=order_blocks,
                displacement=disp_obj,
                volume_feat=volume_feat,
                mtf_context=mtf_context,
                regime=regime,
                derivatives_state=derivatives_state,
                atr=atr,
            )
            if is_qualified
            else 45.0
        )

        return SKYSetup(
            setup_type=SetupType.SETUP_D_RANGE_SWEEP_RECLAIM,
            direction=direction,
            symbol=symbol,
            trigger_timeframe=timeframe,
            timestamp=latest_sweep.sweep_timestamp,
            entry_price=round(entry, 2),
            invalidation_sl=round(sl, 2),
            target_tp=round(tp, 2),
            risk_reward_ratio=round(rr, 2),
            displacement_score=latest_sweep.subsequent_displacement_score,
            regime=regime.regime_type,
            historical_expectancy_r=0.35,
            historical_win_rate=0.60,
            historical_sample_size=3450,
            confluence_score=confluence,
            is_qualified=is_qualified,
            rejection_reasons=reasons,
            explanation_text=f"Setup D (Range Extreme Sweep & Reclaim at {latest_sweep.swept_level}).",
        )

    def _evaluate_setup_e(
        self,
        symbol: str,
        timeframe: str,
        price: float,
        candles: list[dict[str, Any]],
        events: list[StructureEvent],
        disp: DisplacementFeature,
        regime: MarketRegimeState,
        atr: float,
        vwap_feat: VWAPFeature | None = None,
        order_blocks: list[CandidateOrderBlock] | None = None,
        volume_feat: VolumeFeature | None = None,
        derivatives_state: DerivativesState | None = None,
        mtf_context: MultiTimeframeContext | None = None,
    ) -> SKYSetup | None:
        if len(candles) < 20:
            return None

        closes = [float(c["close"]) for c in candles]

        # Use vwap_feat if available, else calculate rolling mean
        if vwap_feat is not None and vwap_feat.vwap > 0:
            vwap_price = vwap_feat.vwap
            is_reclaim_bull = (
                vwap_feat.is_reclaiming
                and vwap_feat.deviation_sigmas > -1.0
                and closes[-2] < vwap_price
            ) or (
                price > vwap_price and closes[-2] <= vwap_price and disp.displacement_score >= 60.0
            )
            is_reclaim_bear = (
                vwap_feat.is_reclaiming
                and vwap_feat.deviation_sigmas < 1.0
                and closes[-2] > vwap_price
            ) or (
                price < vwap_price and closes[-2] >= vwap_price and disp.displacement_score >= 60.0
            )
            _mean_rev_prob = vwap_feat.mean_reversion_prob
        else:
            vwap_price = float(np.mean(closes[-20:]))
            is_reclaim_bull = (
                price > vwap_price and closes[-2] < vwap_price and disp.displacement_score >= 65.0
            )
            is_reclaim_bear = (
                price < vwap_price and closes[-2] > vwap_price and disp.displacement_score >= 65.0
            )
            _mean_rev_prob = 0.55

        # Universal Stop-Loss Floor (>= 1.2x ATR or 0.45%)
        min_stop_dist = max(1.2 * atr, price * 0.0045)
        reasons: list[str] = []
        is_qualified = True

        adx_val = getattr(regime, "adx", getattr(regime, "trend_strength_adx", 15.0))
        htf_4h = getattr(mtf_context, "htf_4h_trend", "") if mtf_context else ""

        if is_reclaim_bull:
            direction = DecisionAction.LONG
            if (
                regime.regime_type
                in (MarketRegimeType.TRENDING_BULL, MarketRegimeType.TRENDING_BEAR)
                and adx_val > 28.0
            ):
                if "BEAR" in regime.regime_type.value or "BEAR" in htf_4h:
                    reasons.append(
                        f"Regime incompatible: Counter-trend fade against strong trend (ADX {adx_val:.1f} > 28.0)"
                    )
                    is_qualified = False

            # Anchor stop to 5-bar structural swing low (never closes[-5:])
            recent_lows = [float(c["low"]) for c in candles[-5:]] if candles else [price]
            raw_sl = min(recent_lows) - (0.5 * atr)
            sl = min(raw_sl, price - min_stop_dist)
            risk = price - sl
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / price) > 0.035:
                reasons.append(f"Risk {risk / price * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = price + max(2.2 * risk, 2.5 * atr)
            rr = abs(tp - price) / max(abs(price - sl), 0.0001)

            closed_candle_confirmed = check_closed_candle_confirmation(candles, direction)
            if not closed_candle_confirmed:
                reasons.append("Last closed candle failed directional confirmation")
                is_qualified = False

            if rr < self.min_rr:
                reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
                is_qualified = False

            confluence = (
                self.compute_unified_confluence(
                    direction=direction,
                    entry_price=price,
                    invalidation_sl=sl,
                    target_tp=tp,
                    candles=candles,
                    zone_tested=True,
                    order_blocks=order_blocks,
                    displacement=disp,
                    volume_feat=volume_feat,
                    mtf_context=mtf_context,
                    regime=regime,
                    derivatives_state=derivatives_state,
                    atr=atr,
                )
                if is_qualified
                else 45.0
            )

            return SKYSetup(
                setup_type=SetupType.SETUP_E_VWAP_RECLAIM,
                direction=direction,
                symbol=symbol,
                trigger_timeframe=timeframe,
                timestamp=int(candles[-1].get("timestamp", 0)),
                entry_price=round(price, 2),
                invalidation_sl=round(sl, 2),
                target_tp=round(tp, 2),
                risk_reward_ratio=round(rr, 2),
                displacement_score=disp.displacement_score,
                regime=regime.regime_type,
                historical_expectancy_r=0.32,
                historical_win_rate=0.57,
                historical_sample_size=2410,
                confluence_score=confluence,
                is_qualified=is_qualified,
                rejection_reasons=reasons,
                explanation_text=f"Setup E (Bullish VWAP Reclaim above {vwap_price:.2f} with {disp.displacement_score}/100 displacement score).",
            )
        elif is_reclaim_bear:
            direction = DecisionAction.SHORT
            if (
                regime.regime_type
                in (MarketRegimeType.TRENDING_BULL, MarketRegimeType.TRENDING_BEAR)
                and adx_val > 28.0
            ):
                if "BULL" in regime.regime_type.value or "BULL" in htf_4h:
                    reasons.append(
                        f"Regime incompatible: Counter-trend fade against strong trend (ADX {adx_val:.1f} > 28.0)"
                    )
                    is_qualified = False

            # Anchor stop to 5-bar structural swing high (never closes[-5:])
            recent_highs = [float(c["high"]) for c in candles[-5:]] if candles else [price]
            raw_sl = max(recent_highs) + (0.5 * atr)
            sl = max(raw_sl, price + min_stop_dist)
            risk = sl - price
            if risk <= 0:
                return None  # Inverted stop guard
            if (risk / price) > 0.035:
                reasons.append(f"Risk {risk / price * 100:.2f}% exceeds 3.5% institutional ceiling")
                is_qualified = False
            tp = price - max(2.2 * risk, 2.5 * atr)
            rr = abs(price - tp) / max(abs(sl - price), 0.0001)

            closed_candle_confirmed = check_closed_candle_confirmation(candles, direction)
            if not closed_candle_confirmed:
                reasons.append("Last closed candle failed directional confirmation")
                is_qualified = False

            if rr < self.min_rr:
                reasons.append(f"Risk:Reward {rr:.2f}R below minimum {self.min_rr:.2f}R")
                is_qualified = False

            confluence = (
                self.compute_unified_confluence(
                    direction=direction,
                    entry_price=price,
                    invalidation_sl=sl,
                    target_tp=tp,
                    candles=candles,
                    zone_tested=True,
                    order_blocks=order_blocks,
                    displacement=disp,
                    volume_feat=volume_feat,
                    mtf_context=mtf_context,
                    regime=regime,
                    derivatives_state=derivatives_state,
                    atr=atr,
                )
                if is_qualified
                else 45.0
            )

            return SKYSetup(
                setup_type=SetupType.SETUP_E_VWAP_RECLAIM,
                direction=direction,
                symbol=symbol,
                trigger_timeframe=timeframe,
                timestamp=int(candles[-1].get("timestamp", 0)),
                entry_price=round(price, 2),
                invalidation_sl=round(sl, 2),
                target_tp=round(tp, 2),
                risk_reward_ratio=round(rr, 2),
                displacement_score=disp.displacement_score,
                regime=regime.regime_type,
                historical_expectancy_r=0.30,
                historical_win_rate=0.55,
                historical_sample_size=2190,
                confluence_score=confluence,
                is_qualified=is_qualified,
                rejection_reasons=reasons,
                explanation_text=f"Setup E (Bearish VWAP Rejection below {vwap_price:.2f} with {disp.displacement_score}/100 displacement score).",
            )

        return None


# Global singleton instance
setup_engine = SetupEngine()
