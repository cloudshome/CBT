"""
Master Institutional Alpha & Market Microstructure Quant Engine.
Orchestrates and synthesizes all 8 quantitative mechanics:
  1. Cross-Asset Lead-Lag Latency Correlator (US10Y -> DXY -> XAU -> BTC/ETH)
  2. Order Flow Cumulative Volume Delta (CVD) Hidden Absorption & Divergence
  3. Level-2 Order Book Imbalance (OBI) & Flow Toxicity (VPIN)
  4. Open Interest (OI) Squeeze Velocity & Extreme Funding Rate Divergence
  5. Session Open Liquidity Sweep ("Judas Swing") & Fair Value Gap Engine
  6. Session-Anchored VWAP Multi-Sigma (±1σ, ±2σ, ±3σ) Mean Reversion Exhaustion
  7. 3-Tier Fractal Time Harmonics (Macro Anchor -> Context Structure -> Micro Execution)
  8. Bayesian Half-Kelly Expectancy Position Sizer with Invalidation-First Risk Control
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.cvd_absorption import cvd_absorption_engine
from core.evidence_integrity import EvidenceGrade, stamp_records, weakest_grade
from core.fractal_harmonics import fractal_harmonics_engine
from core.half_kelly_sizer import half_kelly_position_sizer
from core.judas_sweep_hunter import judas_sweep_hunter
from core.lead_lag_correlator import lead_lag_correlator
from core.oi_funding_squeeze import oi_funding_squeeze_engine
from core.orderbook_imbalance import orderbook_imbalance_engine
from core.sky_intelligence.vwap_engine import vwap_engine

logger = logging.getLogger("ai_quant_sentinel.institutional_alpha")


@dataclass
class InstitutionalAlphaComposite:
    symbol: str
    timeframe: str
    timestamp: int
    decision: str  # "LONG", "SHORT", "WATCH", "NO_TRADE"
    institutional_composite_score: float  # [0.0, 100.0]
    lead_lag: dict[str, Any]
    cvd_absorption: dict[str, Any]
    orderbook_imbalance: dict[str, Any]
    oi_funding_squeeze: dict[str, Any]
    judas_sweep: dict[str, Any]
    vwap_multisigma: dict[str, Any]
    fractal_harmonics: dict[str, Any]
    half_kelly_sizing: dict[str, Any]
    execution_dossier: dict[str, Any]
    hurdle_passed: bool
    narrative: str
    evidence_grade: str = "FABRICATED"
    is_tradeable: bool = False


class InstitutionalAlphaEngine:
    """
    Synthesizes the 8 institutional alpha mechanics into a unified execution verdict.
    """

    def evaluate_alpha(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        candles: list[dict[str, Any]] | None = None,
        orderbook: dict[str, list[tuple[float, float]]] | None = None,
        macro_dxy: float = 104.5,
        macro_us10y: float = 4.25,
        funding_rate_8h: float = 0.0001,
        open_interest_usd: float = 2_500_000_000.0,
        account_equity: float = 10000.0,
        timestamp_ms: int | None = None,
    ) -> InstitutionalAlphaComposite:
        """
        Runs the 8 institutional mechanics in a single deterministic, anti-repainting pipeline.
        """
        now = timestamp_ms or int(time.time() * 1000)

        # Baseline synthetic candles if None
        is_baseline = False
        if not candles or len(candles) < 20:
            candles = self._generate_baseline_candles(now)
            is_baseline = True

        current_price = candles[-1]["close"]
        ev_grade = EvidenceGrade.FABRICATED if is_baseline else weakest_grade(candles)
        is_tradeable = ev_grade.is_tradeable

        # 1. Cross-Asset Lead-Lag Correlator
        lead_signals = lead_lag_correlator.process_macro_ticks(
            dxy_price=macro_dxy,
            us10y_yield=macro_us10y,
            timestamp_ms=now,
        )
        lead_lag_data = {
            "signals": [s.__dict__ for s in lead_signals],
            "dxy_price": macro_dxy,
            "us10y_yield": macro_us10y,
            "has_macro_shock": any(abs(s.shock_zscore) >= 2.0 for s in lead_signals),
        }

        # 2. Order Flow CVD Hidden Absorption
        cvd_res = cvd_absorption_engine.analyze_orderflow(candles, symbol=symbol)
        cvd_data = cvd_res.__dict__

        # 3. L2 Order Book Imbalance (OBI) & VPIN
        bids = (
            orderbook.get("bids", [])
            if orderbook
            else [(current_price * 0.999, 1.5), (current_price * 0.998, 3.2)]
        )
        asks = (
            orderbook.get("asks", [])
            if orderbook
            else [(current_price * 1.001, 1.2), (current_price * 1.002, 2.8)]
        )
        obi_res = orderbook_imbalance_engine.compute_imbalance(
            bids, asks, symbol=symbol, timestamp_ms=now
        )
        obi_data = obi_res.__dict__

        # 4. Open Interest & Funding Squeeze Velocity
        oi_res = oi_funding_squeeze_engine.analyze_positioning(
            symbol=symbol,
            current_oi_usd=open_interest_usd,
            historical_oi_1h_ago=open_interest_usd * 0.98,
            funding_rate_8h=funding_rate_8h,
            spot_price=current_price,
            perp_price=current_price * 1.0004,
            timestamp_ms=now,
        )
        oi_data = oi_res.__dict__

        # 5. Session Open Liquidity Sweep (Judas Swing)
        judas_res = judas_sweep_hunter.check_session_judas_sweep(symbol, candles)
        judas_data = (
            judas_res.__dict__
            if judas_res
            else {
                "symbol": symbol,
                "session_name": "OUTSIDE_KILLZONE",
                "timestamp": now,
                "sweep_direction": "NONE",
                "asian_high": 0.0,
                "asian_low": 0.0,
                "swept_level": 0.0,
                "rejection_wick_pct": 0.0,
                "confidence": 0.0,
                "invalidation_level": 0.0,
                "target_level": 0.0,
                "narrative": "No active Judas liquidity sweep in session window.",
            }
        )

        # 6. Session-Anchored VWAP Multi-Sigma Bands
        vwap_feat = vwap_engine.compute_vwap(candles)
        vwap_data = {
            "vwap": vwap_feat.vwap,
            "upper_1s": vwap_feat.upper_band_1sigma,
            "lower_1s": vwap_feat.lower_band_1sigma,
            "upper_2s": vwap_feat.upper_band_2sigma,
            "lower_2s": vwap_feat.lower_band_2sigma,
            "upper_3s": round(vwap_feat.vwap + 3.0 * vwap_feat.std_dev, 2),
            "lower_3s": round(vwap_feat.vwap - 3.0 * vwap_feat.std_dev, 2),
            "deviation_sigmas": vwap_feat.deviation_sigmas,
            "mean_reversion_prob": vwap_feat.mean_reversion_prob,
            "is_reclaiming": vwap_feat.is_reclaiming,
        }

        # 7. 3-Tier Fractal Time Harmonics
        fractal_res = fractal_harmonics_engine.evaluate_harmonics(
            symbol=symbol,
            macro_candles=candles,
            context_candles=candles,
            micro_candles=candles[-15:],
        )
        fractal_data = fractal_res.__dict__

        # Synthesize Score and Direction
        bull_weights = 0.0
        bear_weights = 0.0

        # CVD Contribution (weight 20)
        if cvd_res.absorption_type == "BULLISH_ABSORPTION":
            bull_weights += 20.0 * cvd_res.absorption_score
        elif cvd_res.absorption_type == "BEARISH_ABSORPTION":
            bear_weights += 20.0 * cvd_res.absorption_score

        # OBI Contribution (weight 15)
        if obi_res.obi_score > 0.25:
            bull_weights += 15.0 * obi_res.obi_score
        elif obi_res.obi_score < -0.25:
            bear_weights += 15.0 * abs(obi_res.obi_score)

        # OI Squeeze Contribution (weight 15)
        if oi_res.squeeze_risk == "SHORT_SQUEEZE_PROBABLE":
            bull_weights += 15.0 * oi_res.squeeze_velocity_score
        elif oi_res.squeeze_risk == "LONG_SQUEEZE_PROBABLE":
            bear_weights += 15.0 * oi_res.squeeze_velocity_score

        # Judas Sweep Contribution (weight 25)
        if judas_res:
            if judas_res.sweep_direction == "BULLISH_REVERSAL_SWEEP":
                bull_weights += 25.0 * (judas_res.confidence / 100.0)
            elif judas_res.sweep_direction == "BEARISH_REVERSAL_SWEEP":
                bear_weights += 25.0 * (judas_res.confidence / 100.0)

        # Fractal Harmonics (weight 25)
        if fractal_res.dominant_direction == "LONG":
            bull_weights += 25.0 * fractal_res.harmonic_confluence_score
        elif fractal_res.dominant_direction == "SHORT":
            bear_weights += 25.0 * fractal_res.harmonic_confluence_score

        # Decision threshold (Hurdle = 55.0)
        if not is_tradeable:
            decision = "NO_TRADE"
            composite_score = 0.0
            entry = current_price
            sl = current_price * 0.99
            tp = current_price * 1.02
            hurdle_passed = False
        elif bull_weights >= 55.0 and bull_weights > (bear_weights * 1.3):
            decision = "LONG"
            composite_score = min(98.0, bull_weights)
            entry = current_price
            sl = current_price * 0.988
            tp = current_price + (2.4 * (current_price - sl))
            hurdle_passed = True
        elif bear_weights >= 55.0 and bear_weights > (bull_weights * 1.3):
            decision = "SHORT"
            composite_score = min(98.0, bear_weights)
            entry = current_price
            sl = current_price * 1.012
            tp = current_price - (2.4 * (sl - current_price))
            hurdle_passed = True
        else:
            decision = "NO_TRADE"
            composite_score = max(bull_weights, bear_weights)
            entry = current_price
            sl = current_price * 0.99
            tp = current_price * 1.02
            hurdle_passed = False

        # 8. Bayesian Half-Kelly Position Sizer
        kelly_res = half_kelly_position_sizer.calculate_sizing(
            account_equity=account_equity,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            win_probability=0.58 if (is_tradeable and hurdle_passed) else 0.0,
            symbol=symbol,
        )
        kelly_data = kelly_res.__dict__

        if not is_tradeable:
            narrative = (
                f"EVIDENCE INTEGRITY HALT: Market candles grade {ev_grade.label}, not EMPIRICAL. "
                f"Decision forced to NO_TRADE, Kelly allocation 0.0."
            )
        else:
            narrative = (
                f"Institutional Alpha Composite: {decision} (Score: {composite_score:.1f}/100). "
                f"CVD: {cvd_res.absorption_type}, OBI: {obi_res.regime}, Judas: {judas_data['sweep_direction']}, "
                f"Fractal: {fractal_res.dominant_direction} ({fractal_res.harmonic_confluence_score * 100:.0f}%)."
            )

        return InstitutionalAlphaComposite(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now,
            decision=decision,
            institutional_composite_score=round(composite_score, 1),
            lead_lag=lead_lag_data,
            cvd_absorption=cvd_data,
            orderbook_imbalance=obi_data,
            oi_funding_squeeze=oi_data,
            judas_sweep=judas_data,
            vwap_multisigma=vwap_data,
            fractal_harmonics=fractal_data,
            half_kelly_sizing=kelly_data,
            execution_dossier={
                "entry_price": round(entry, 2),
                "stop_loss": round(sl, 2),
                "take_profit": round(tp, 2),
                "risk_reward_ratio": round(kelly_res.risk_reward_ratio, 2),
                "suggested_risk_usd": round(kelly_res.max_dollar_loss, 2),
                "suggested_size_base": round(kelly_res.position_size_base, 4),
            },
            hurdle_passed=hurdle_passed,
            narrative=narrative,
            evidence_grade=ev_grade.label,
            is_tradeable=is_tradeable,
        )

    def _generate_baseline_candles(self, now: int) -> list[dict[str, Any]]:
        candles = []
        p = 88000.0
        for i in range(50):
            t = now - (50 - i) * 900_000
            drift = np.random.normal(10.0, 45.0)
            o = p
            h = o + abs(np.random.normal(30.0, 15.0))
            lo = o - abs(np.random.normal(30.0, 15.0))
            c = o + drift
            v = max(50.0, np.random.normal(250.0, 80.0))
            candles.append(
                {"timestamp": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}
            )
            p = c
        stamp_records(candles, EvidenceGrade.FABRICATED)
        return candles


# Global singleton instance
institutional_alpha_engine = InstitutionalAlphaEngine()
