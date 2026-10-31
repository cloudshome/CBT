"""
Phase 40: End-to-End Decision Architecture & Master Pipeline Orchestrator.
Executes the full pipeline:
DATA -> DATA QUALITY -> STRUCTURE -> LIQUIDITY -> VOLUME -> VOLATILITY ->
DERIVATIVES -> MTF CONTEXT -> REGIME -> SETUPS -> EXPECTANCY -> RISK GATE -> FINAL DECISION
Emits LONG, SHORT, WATCH, or NO_TRADE with structured explanation dossiers.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.data_quality_gate import data_quality_gate
from core.sky_intelligence.derivatives_intelligence import derivatives_engine
from core.sky_intelligence.displacement_engine import displacement_engine
from core.sky_intelligence.fvg_engine import fvg_engine
from core.sky_intelligence.liquidity_engine import liquidity_engine
from core.sky_intelligence.market_regime import market_regime_engine
from core.sky_intelligence.market_structure import market_structure_engine
from core.sky_intelligence.multi_timeframe import multi_timeframe_engine
from core.sky_intelligence.order_block_engine import order_block_engine
from core.sky_intelligence.setup_engine import setup_engine
from core.sky_intelligence.types import (
    DecisionAction,
    DecisionOutput,
)
from core.sky_intelligence.volatility_engine import volatility_engine
from core.sky_intelligence.volume_engine import volume_engine
from core.sky_intelligence.vwap_engine import vwap_engine

logger = logging.getLogger("sky_intelligence.orchestrator")


class SKYIntelligenceOrchestrator:
    """
    SKY Professional Market Intelligence Engine Orchestrator.
    """

    def __init__(self, default_symbol: str = "BTC/USDT"):
        self.default_symbol = default_symbol
        self._bayesian_cache: dict[str, tuple[float, float, int, float]] = {}

    def get_bayesian_setup_stats(
        self, symbol: str, setup_type_str: str, epoch_ms: int = 1793469018542
    ) -> tuple[float, float, int]:
        """
        Computes dynamic Bayesian posterior win rate (p_hat) and empirical win expectancy (R_win_hat).
        Backed by closed trades in shadow_positions after epoch_ms.
        Returns:
            (p_win_hat, r_win_hat, sample_size)
        """
        cache_key = f"{symbol}_{setup_type_str}"
        now_sec = time.time()
        if cache_key in self._bayesian_cache:
            p_hat, r_hat, n_samples, exp_time = self._bayesian_cache[cache_key]
            if now_sec < exp_time:
                return p_hat, r_hat, n_samples

        # Conservative prior: alpha_0 = 6.0, beta_0 = 6.0 (p_0 = 0.50), prior average win = 1.45R
        alpha_0 = 6.0
        beta_0 = 6.0
        r_win_0 = 1.45

        n_wins = 0
        n_total = 0
        sum_win_r = 0.0

        try:
            from core.database import db_manager

            with db_manager.get_trading_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT realized_pnl, size, entry_price, stop_loss
                    FROM shadow_positions
                    WHERE status = 'CLOSED'
                      AND opened_at >= ?
                      AND (entry_reason LIKE ? OR symbol = ?);
                    """,
                    (epoch_ms, f"%{setup_type_str}%", symbol),
                ).fetchall()

                for r in rows:
                    pnl = float(r["realized_pnl"] or 0.0)
                    sz = float(r["size"] or 0.0)
                    ep = float(r["entry_price"] or 0.0)
                    sl = float(r["stop_loss"] or 0.0)
                    risk_usd = sz * abs(ep - sl) if (sz > 0 and abs(ep - sl) > 0) else 100.0
                    n_total += 1
                    if pnl > 0:
                        n_wins += 1
                        sum_win_r += (pnl / max(1.0, risk_usd))
        except Exception as ex:
            logger.debug("Bayesian stats fallback to prior: %s", ex)

        p_win_hat = (alpha_0 + n_wins) / (alpha_0 + beta_0 + n_total)
        r_win_hat = (alpha_0 * r_win_0 + sum_win_r) / (alpha_0 + n_wins)

        self._bayesian_cache[cache_key] = (p_win_hat, r_win_hat, n_total, now_sec + 60.0)
        return p_win_hat, r_win_hat, n_total

    def analyze_market(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        candles_by_tf: dict[str, list[dict[str, Any]]] | None = None,
        bid_price: float | None = None,
        ask_price: float | None = None,
        latest_tick_time_ms: float | None = None,
        open_interest: float = 50000.0,
        prev_open_interest: float = 49200.0,
        funding_rate: float = 0.0001,
        account_equity_usd: float = 100_000.0,
    ) -> DecisionOutput:
        """
        Runs the full 12-stage sequential quantitative evaluation.
        """
        now_ms = time.time() * 1000
        tick_time = latest_tick_time_ms or now_ms

        if not candles:
            return DecisionOutput(
                decision=DecisionAction.NO_TRADE,
                symbol=symbol,
                timestamp=int(now_ms),
                setup_qualified=None,
                net_ev_r=0.0,
                kelly_fraction=0.0,
                suggested_position_size_usd=0.0,
                risk_gate_passed=False,
                explanation_dossier={"error": "Empty candlestick series"},
                no_trade_reason="EMPTY_DATA_FEED",
            )

        curr_close = float(candles[-1]["close"])
        bid = bid_price or (curr_close * 0.99999)
        ask = ask_price or (curr_close * 1.00001)

        # ----------------------------------------------------
        # STAGE 1: DATA QUALITY GATE
        # ----------------------------------------------------
        gate_res = data_quality_gate.validate_feed(
            symbol=symbol,
            latest_tick_time_ms=tick_time,
            server_now_ms=now_ms,
            bid_price=bid,
            ask_price=ask,
        )
        if not gate_res.is_valid or gate_res.forced_action == "NO_TRADE":
            return DecisionOutput(
                decision=DecisionAction.NO_TRADE,
                symbol=symbol,
                timestamp=int(now_ms),
                setup_qualified=None,
                net_ev_r=0.0,
                kelly_fraction=0.0,
                suggested_position_size_usd=0.0,
                risk_gate_passed=False,
                explanation_dossier={
                    "gate_score": gate_res.quality_score,
                    "reason": gate_res.reason,
                },
                no_trade_reason=f"DATA_QUALITY_FAILURE: {gate_res.reason}",
            )

        # ----------------------------------------------------
        # STAGE 2: VOLATILITY & VOLUME ENGINES
        # ----------------------------------------------------
        vol_state = volatility_engine.compute_volatility(candles)
        volume_feat = volume_engine.analyze_volume(candles)
        atr_val = vol_state.atr

        # ----------------------------------------------------
        # STAGE 3: MARKET STRUCTURE & SWINGS (Phase 1)
        # ----------------------------------------------------
        swings, structure_events = market_structure_engine.analyze_structure(
            candles, timeframe=timeframe, atr=atr_val
        )

        # ----------------------------------------------------
        # STAGE 4: LIQUIDITY ENGINE (Phase 2)
        # ----------------------------------------------------
        pools = liquidity_engine.identify_liquidity_pools(
            symbol=symbol, timeframe=timeframe, candles=candles, swings=swings
        )
        sweeps = liquidity_engine.detect_sweeps(
            symbol=symbol, timeframe=timeframe, candles=candles, pools=pools, atr=atr_val
        )

        # ----------------------------------------------------
        # STAGE 5: FAIR VALUE GAPS & CANDIDATE ORDER BLOCKS (Phases 5 & 6)
        # ----------------------------------------------------
        fvgs = fvg_engine.detect_fvgs(
            symbol=symbol, timeframe=timeframe, candles=candles, atr=atr_val
        )
        order_blocks = order_block_engine.detect_candidate_order_blocks(
            symbol=symbol, timeframe=timeframe, candles=candles, atr=atr_val
        )

        # ----------------------------------------------------
        # STAGE 6: DISPLACEMENT ENGINE (Phase 7)
        # ----------------------------------------------------
        disp_feat = displacement_engine.calculate_displacement(candles=candles, atr=atr_val)

        # ----------------------------------------------------
        # STAGE 7: DERIVATIVES INTELLIGENCE (Phase 9)
        # ----------------------------------------------------
        price_chg = (
            ((curr_close - float(candles[0]["close"])) / float(candles[0]["close"])) * 100.0
            if len(candles) > 1
            else 0.0
        )
        derivs_state = derivatives_engine.analyze_derivatives(
            symbol=symbol,
            current_price=curr_close,
            price_change_pct=price_chg,
            open_interest=open_interest,
            prev_open_interest=prev_open_interest,
            current_funding_rate=funding_rate,
        )

        # ----------------------------------------------------
        # STAGE 8: VWAP ENGINE & BANDS (Phase 8)
        # ----------------------------------------------------
        vwap_feat = vwap_engine.compute_vwap(candles)

        # ----------------------------------------------------
        # STAGE 9: MULTI-TIMEFRAME CONTEXT (Phase 11)
        # ----------------------------------------------------
        tf_map = candles_by_tf or {timeframe: candles}
        mtf_context = multi_timeframe_engine.compile_mtf_context(tf_map)

        # ----------------------------------------------------
        # STAGE 10: MARKET REGIME (Phase 12)
        # ----------------------------------------------------
        regime_state = market_regime_engine.classify_regime(candles, vol_state)

        # ----------------------------------------------------
        # STAGE 11: SETUP DETECTION & QUALIFICATION (Phase 13)
        # ----------------------------------------------------
        candidate_setups = setup_engine.scan_setups(
            symbol=symbol,
            timeframe=timeframe,
            current_price=curr_close,
            candles=candles,
            structure_events=structure_events,
            liquidity_sweeps=sweeps,
            fvgs=fvgs,
            order_blocks=order_blocks,
            displacement=disp_feat,
            volume_feat=volume_feat,
            derivatives_state=derivs_state,
            mtf_context=mtf_context,
            regime_state=regime_state,
            atr=atr_val,
            vwap_feat=vwap_feat,
        )

        qualified_setups = [s for s in candidate_setups if s.is_qualified]

        # ----------------------------------------------------
        # STAGE 12: STATISTICAL EDGE, NET EV & RISK GATE
        # ----------------------------------------------------
        if not qualified_setups:
            # Check if there are unqualified candidate setups for WATCH status
            if candidate_setups:
                top_cand = candidate_setups[0]
                reason = f"Candidate {top_cand.setup_type.value} rejected: {'; '.join(top_cand.rejection_reasons)}"
                decision = DecisionAction.WATCH
            else:
                reason = "NO_CONFLUENT_SMC_SETUP_FOUND"
                decision = DecisionAction.NO_TRADE

            return DecisionOutput(
                decision=decision,
                symbol=symbol,
                timestamp=int(now_ms),
                setup_qualified=None,
                net_ev_r=0.0,
                kelly_fraction=0.0,
                suggested_position_size_usd=0.0,
                risk_gate_passed=False,
                explanation_dossier={
                    "regime": regime_state.regime_type.value,
                    "mtf_alignment": mtf_context.stack_alignment,
                    "volatility": vol_state.regime.value,
                    "displacement_score": disp_feat.displacement_score,
                    "active_pools": len(pools),
                    "active_fvgs": len(fvgs),
                    "candidate_obs": len(order_blocks),
                    "vwap": {
                        "vwap": vwap_feat.vwap,
                        "deviation_sigmas": vwap_feat.deviation_sigmas,
                        "mean_reversion_prob": vwap_feat.mean_reversion_prob,
                    },
                },
                no_trade_reason=reason,
            )

        # Qualified setup selected
        best_setup = qualified_setups[0]
        direction = best_setup.direction

        # Dynamic Bayesian Setup Expectancy & Win Rate (Backed by post-patch shadow_positions)
        p_win_hat, r_win_hat, sample_size = self.get_bayesian_setup_stats(
            symbol=symbol,
            setup_type_str=best_setup.setup_type.value,
        )

        # Nudge win probability slightly by confluence score deviation from 75.0 baseline
        confluence = best_setup.confluence_score
        p_effective = min(0.72, max(0.35, p_win_hat + 0.004 * (confluence - 75.0)))

        # Dynamic Fee + Spread Friction in R (Realistic ~8 bps round-trip execution cost)
        stop_dist_pct = (
            abs(best_setup.entry_price - best_setup.invalidation_sl) / best_setup.entry_price
            if best_setup.entry_price > 0
            else 0.005
        )
        c_friction_r = max(0.08, 0.0008 / max(stop_dist_pct, 0.001))

        # True Net EV in R-multiples
        net_ev = (p_effective * r_win_hat) - ((1.0 - p_effective) * 1.0) - c_friction_r

        # Conservative Half-Kelly Sizing using Empirical Posterior Probability
        b_ratio = max(1.5, best_setup.risk_reward_ratio)
        q_loss = 1.0 - p_effective
        full_kelly = ((b_ratio * p_effective) - q_loss) / b_ratio
        half_kelly = max(0.0, min(0.015, full_kelly * 0.5))  # Capped at 1.5% max account risk

        risk_budget_usd = account_equity_usd * half_kelly
        raw_position_size_usd = risk_budget_usd / max(stop_dist_pct, 0.005)
        # Cap single-position notional size to 1.0x account equity (max 100% portfolio allocation per setup)
        position_size_usd = min(raw_position_size_usd, account_equity_usd * 1.0)

        # Risk Gate hurdle: Net EV must exceed +0.25R
        risk_passed = net_ev >= 0.25

        final_decision = direction if risk_passed else DecisionAction.NO_TRADE
        no_trade_reason = None if risk_passed else f"NET_EV_HURDLE_FAILED (+{net_ev:.2f}R < +0.25R)"

        dossier = {
            "setup_type": best_setup.setup_type.value,
            "direction": direction.value,
            "entry_price": best_setup.entry_price,
            "invalidation_sl": best_setup.invalidation_sl,
            "target_tp": best_setup.target_tp,
            "risk_reward_ratio": best_setup.risk_reward_ratio,
            "displacement_score": best_setup.displacement_score,
            "regime": regime_state.regime_type.value,
            "historical_expectancy_r": round(r_win_hat, 3),
            "historical_win_rate": round(p_effective, 3),
            "confluence_score": best_setup.confluence_score,
            "net_ev_r": round(net_ev, 3),
            "friction_r": round(c_friction_r, 4),
            "bayesian_samples": sample_size,
            "kelly_fraction": round(half_kelly, 4),
            "vwap": {
                "vwap": vwap_feat.vwap,
                "deviation_sigmas": vwap_feat.deviation_sigmas,
                "mean_reversion_prob": vwap_feat.mean_reversion_prob,
            },
            "explanation": best_setup.explanation_text,
        }

        return DecisionOutput(
            decision=final_decision,
            symbol=symbol,
            timestamp=int(now_ms),
            setup_qualified=best_setup if risk_passed else None,
            net_ev_r=round(net_ev, 3),
            kelly_fraction=round(half_kelly, 4),
            suggested_position_size_usd=round(position_size_usd, 2),
            risk_gate_passed=risk_passed,
            explanation_dossier=dossier,
            no_trade_reason=no_trade_reason,
        )


# Global singleton instance
sky_orchestrator = SKYIntelligenceOrchestrator()
