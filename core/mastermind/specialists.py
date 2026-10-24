"""
core/mastermind/specialists.py
==============================
Concrete Specialist Agents for the SKY Mastermind Swarm:
1. BtcMacroSpecialist: Macro regime + Order Flow Imbalance.
2. EthSpecialist: Structural ETH/BTC trend + Gas/Staking dynamics.
3. SolSpecialist: High-velocity momentum + volume acceleration.
4. MemeMomentumSpecialist: Volume spike anomalies + rapid social volatility breakout (e.g. DOGE, PEPE).
5. LowCapBreakoutSpecialist: Order book depth exhaustion + structural liquidity reclaims.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.mastermind.specialist_base import (
    BaseSpecialistAgent,
    CandidateProposal,
    SpecialistArchetype,
)
from core.sky_intelligence.orchestrator import sky_orchestrator
from core.sky_intelligence.types import DecisionAction

logger = logging.getLogger("sky.mastermind.specialists")


class BtcMacroSpecialist(BaseSpecialistAgent):
    """Specialist dedicated to Bitcoin macro structure and institutional flows."""

    def __init__(self, target_symbol: str = "BTC/USDT") -> None:
        super().__init__(
            specialist_id="spec_btc_macro",
            archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
            target_symbol=target_symbol,
        )

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        decision = sky_orchestrator.analyze_market(
            symbol=self.target_symbol,
            timeframe="15m",
            candles=candles_15m,
            candles_by_tf=multi_tf_candles,
            account_equity_usd=10_000.0,
        )

        cur_price = float(candles_15m[-1]["close"]) if candles_15m else 0.0
        setup = decision.setup_qualified

        if setup and decision.decision in (DecisionAction.LONG, DecisionAction.SHORT):
            sl = setup.invalidation_sl
            tp = setup.target_tp
            rr = setup.risk_reward_ratio
            thesis = f"BTC Macro Structure ({decision.decision.value}): High-timeframe confluence, Net-EV {decision.net_ev_r:.2f}R"
            conf = min(0.95, max(0.40, setup.confluence_score))
        else:
            sl = cur_price * 0.98
            tp = cur_price * 1.04
            rr = 2.0
            thesis = "BTC Macro in consolidation; no high-conviction institutional imbalance."
            conf = 0.20

        prop = CandidateProposal(
            proposal_id=f"prop_btc_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=decision.decision,
            thesis=thesis,
            entry_price=cur_price,
            stop_loss=sl,
            take_profit=tp,
            risk_reward_ratio=rr,
            expected_value_r=decision.net_ev_r,
            confidence_score=conf,
            invalidation_condition="HTF MSS failure or contrary liquidity pool sweep.",
            suggested_notional_usd=decision.suggested_position_size_usd,
            telemetry={
                "kelly_fraction": decision.kelly_fraction,
                "regime": str(setup.regime if setup else "UNKNOWN"),
            },
        )
        return self.apply_adversarial_review(prop, candles_15m, order_book)


class EthSpecialist(BaseSpecialistAgent):
    """Specialist dedicated to Ethereum structural liquidity and smart contract ecosystem flows."""

    def __init__(self, target_symbol: str = "ETH/USDT") -> None:
        super().__init__(
            specialist_id="spec_eth_structural",
            archetype=SpecialistArchetype.ETH_DEFI_STRUCTURAL,
            target_symbol=target_symbol,
        )

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        decision = sky_orchestrator.analyze_market(
            symbol=self.target_symbol,
            timeframe="15m",
            candles=candles_15m,
            candles_by_tf=multi_tf_candles,
            account_equity_usd=10_000.0,
        )

        cur_price = float(candles_15m[-1]["close"]) if candles_15m else 0.0
        setup = decision.setup_qualified

        if setup and decision.decision in (DecisionAction.LONG, DecisionAction.SHORT):
            sl = setup.invalidation_sl
            tp = setup.target_tp
            rr = setup.risk_reward_ratio
            thesis = f"ETH Structural ({decision.decision.value}): FVG mitigation & range reclaim, Net-EV {decision.net_ev_r:.2f}R"
            conf = min(0.90, max(0.40, setup.confluence_score))
        else:
            sl = cur_price * 0.98
            tp = cur_price * 1.04
            rr = 2.0
            thesis = "ETH structural setup neutral."
            conf = 0.20

        prop = CandidateProposal(
            proposal_id=f"prop_eth_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=decision.decision,
            thesis=thesis,
            entry_price=cur_price,
            stop_loss=sl,
            take_profit=tp,
            risk_reward_ratio=rr,
            expected_value_r=decision.net_ev_r,
            confidence_score=conf,
            invalidation_condition="Key FVG breached without mitigation absorption.",
            suggested_notional_usd=decision.suggested_position_size_usd,
            telemetry={"kelly_fraction": decision.kelly_fraction},
        )
        return self.apply_adversarial_review(prop, candles_15m, order_book)


class SolSpecialist(BaseSpecialistAgent):
    """Specialist dedicated to Solana high-velocity trend continuation."""

    def __init__(self, target_symbol: str = "SOL/USDT") -> None:
        super().__init__(
            specialist_id="spec_sol_velocity",
            archetype=SpecialistArchetype.SOL_HIGH_VELOCITY,
            target_symbol=target_symbol,
        )

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        decision = sky_orchestrator.analyze_market(
            symbol=self.target_symbol,
            timeframe="15m",
            candles=candles_15m,
            candles_by_tf=multi_tf_candles,
            account_equity_usd=10_000.0,
        )

        cur_price = float(candles_15m[-1]["close"]) if candles_15m else 0.0
        setup = decision.setup_qualified

        if setup and decision.decision in (DecisionAction.LONG, DecisionAction.SHORT):
            sl = setup.invalidation_sl
            tp = setup.target_tp
            rr = setup.risk_reward_ratio
            thesis = f"SOL High-Velocity ({decision.decision.value}): Displacement impulse, Net-EV {decision.net_ev_r:.2f}R"
            conf = min(0.92, max(0.40, setup.confluence_score))
        else:
            sl = cur_price * 0.97
            tp = cur_price * 1.06
            rr = 2.0
            thesis = "SOL velocity momentum flat."
            conf = 0.20

        prop = CandidateProposal(
            proposal_id=f"prop_sol_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=decision.decision,
            thesis=thesis,
            entry_price=cur_price,
            stop_loss=sl,
            take_profit=tp,
            risk_reward_ratio=rr,
            expected_value_r=decision.net_ev_r,
            confidence_score=conf,
            invalidation_condition="Velocity impulse rejected with heavy sell wick.",
            suggested_notional_usd=decision.suggested_position_size_usd,
            telemetry={"kelly_fraction": decision.kelly_fraction},
        )
        return self.apply_adversarial_review(prop, candles_15m, order_book)


class MemeMomentumSpecialist(BaseSpecialistAgent):
    """
    Specialist dedicated to high-beta Meme assets (e.g. DOGE, PEPE, SHIB).
    Looks for explosive 3x volume spikes combined with tight consolidation breakouts.
    """

    def __init__(self, target_symbol: str = "DOGE/USDT") -> None:
        super().__init__(
            specialist_id="spec_meme_momentum",
            archetype=SpecialistArchetype.MEME_MOMENTUM_SPIKE,
            target_symbol=target_symbol,
        )

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        if not candles_15m or len(candles_15m) < 20:
            return CandidateProposal(
                proposal_id=f"prop_meme_{uuid.uuid4().hex[:8]}",
                specialist_id=self.specialist_id,
                archetype=self.archetype,
                symbol=self.target_symbol,
                direction=DecisionAction.NO_TRADE,
                thesis="Insufficient candle history for meme volatility profiling.",
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                expected_value_r=0.0,
                confidence_score=0.0,
                invalidation_condition="N/A",
                suggested_notional_usd=0.0,
            )

        cur_price = float(candles_15m[-1]["close"])
        volumes = [float(c.get("volume", 0.0)) for c in candles_15m[-20:-1]]
        avg_vol = sum(volumes) / max(1, len(volumes))
        latest_vol = float(candles_15m[-1].get("volume", 0.0))
        vol_ratio = latest_vol / max(1e-6, avg_vol)

        prev_high = max(float(c["high"]) for c in candles_15m[-10:-1])
        prev_low = min(float(c["low"]) for c in candles_15m[-10:-1])

        # Volume spike > 2.5x with breakout above recent 10-bar high
        if vol_ratio >= 2.5 and cur_price > prev_high:
            sl = prev_low
            risk_dist = max(1e-6, cur_price - sl)
            tp = cur_price + 2.5 * risk_dist
            rr = (tp - cur_price) / risk_dist

            prop = CandidateProposal(
                proposal_id=f"prop_meme_{uuid.uuid4().hex[:8]}",
                specialist_id=self.specialist_id,
                archetype=self.archetype,
                symbol=self.target_symbol,
                direction=DecisionAction.LONG,
                thesis=f"Meme Volume Spike ({vol_ratio:.1f}x avg vol): Bullish momentum expansion breakout.",
                entry_price=cur_price,
                stop_loss=sl,
                take_profit=tp,
                risk_reward_ratio=rr,
                expected_value_r=1.25,
                confidence_score=0.68,
                invalidation_condition="Breakout bar retraced completely below volume trigger level.",
                suggested_notional_usd=150.0,
                telemetry={"vol_ratio": vol_ratio, "avg_vol": avg_vol, "latest_vol": latest_vol},
            )
            return self.apply_adversarial_review(prop, candles_15m, order_book)

        no_trade_thesis = (
            f"Meme volume spike ({vol_ratio:.1f}x) failed to break previous high ${prev_high:.4f}."
            if vol_ratio > 2.5
            else f"Normal meme activity: volume ratio {vol_ratio:.2f}x below 2.5x threshold."
        )
        prop = CandidateProposal(
            proposal_id=f"prop_meme_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=DecisionAction.NO_TRADE,
            thesis=no_trade_thesis,
            entry_price=cur_price,
            stop_loss=cur_price * 0.95,
            take_profit=cur_price * 1.10,
            risk_reward_ratio=2.0,
            expected_value_r=0.0,
            confidence_score=0.15,
            invalidation_condition="Volume threshold or breakout price not reached.",
            suggested_notional_usd=0.0,
            telemetry={"vol_ratio": vol_ratio},
        )
        return self.apply_adversarial_review(prop, candles_15m, order_book)


class LowCapBreakoutSpecialist(BaseSpecialistAgent):
    """
    Specialist dedicated to lower market-cap assets.
    Detects order book ask-side exhaustion and structural range breakout.
    """

    def __init__(self, target_symbol: str = "PEPE/USDT") -> None:
        super().__init__(
            specialist_id="spec_lowcap_breakout",
            archetype=SpecialistArchetype.LOW_CAP_BREAKOUT,
            target_symbol=target_symbol,
        )

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        if not candles_15m or len(candles_15m) < 15:
            return CandidateProposal(
                proposal_id=f"prop_lowcap_{uuid.uuid4().hex[:8]}",
                specialist_id=self.specialist_id,
                archetype=self.archetype,
                symbol=self.target_symbol,
                direction=DecisionAction.NO_TRADE,
                thesis="Insufficient candle history.",
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward_ratio=0.0,
                expected_value_r=0.0,
                confidence_score=0.0,
                invalidation_condition="N/A",
                suggested_notional_usd=0.0,
            )

        cur_price = float(candles_15m[-1]["close"])
        # Check orderbook imbalance if provided
        obi = 0.0
        if order_book:
            bids = sum(b[1] for b in order_book.get("bids", [])[:5])
            asks = sum(a[1] for a in order_book.get("asks", [])[:5])
            if (bids + asks) > 0:
                obi = (bids - asks) / (bids + asks)

        if obi > 0.40:
            sl = cur_price * 0.96
            tp = cur_price * 1.10
            prop = CandidateProposal(
                proposal_id=f"prop_lowcap_{uuid.uuid4().hex[:8]}",
                specialist_id=self.specialist_id,
                archetype=self.archetype,
                symbol=self.target_symbol,
                direction=DecisionAction.LONG,
                thesis=f"Low-Cap Liquidity Imbalance: Bid-side skew +{obi:.1%} indicates ask exhaustion.",
                entry_price=cur_price,
                stop_loss=sl,
                take_profit=tp,
                risk_reward_ratio=(tp - cur_price) / (cur_price - sl),
                expected_value_r=1.10,
                confidence_score=0.65,
                invalidation_condition="Order book bid depth collapses.",
                suggested_notional_usd=100.0,
                telemetry={"obi": obi},
            )
            return self.apply_adversarial_review(prop, candles_15m, order_book)

        return CandidateProposal(
            proposal_id=f"prop_lowcap_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=DecisionAction.NO_TRADE,
            thesis=f"Low-Cap neutral: OBI {obi:.2f} within balanced corridor.",
            entry_price=cur_price,
            stop_loss=cur_price * 0.96,
            take_profit=cur_price * 1.08,
            risk_reward_ratio=2.0,
            expected_value_r=0.0,
            confidence_score=0.20,
            invalidation_condition="No depth skew detected.",
            suggested_notional_usd=0.0,
            telemetry={"obi": obi},
        )


class DynamicOpportunitySpecialist(BaseSpecialistAgent):
    """
    Autonomous Specialist Agent dynamically tracking high-momentum breakouts,
    pre-spike compression, and blow-off exhaustion reversals discovered across
    the 700+ coin universe by the Opportunity Hunter.
    """

    def __init__(
        self,
        target_symbol: str,
        category: str = "CONFIRMED_BREAKOUT",
        recommended_direction: str = "LONG",
        invalidation_level: float | None = None,
        primary_rationale: str = "",
        market_attention_score: float = 75.0,
        timing_stage: str = "ACTIVE",
    ) -> None:
        clean_id = target_symbol.replace("/", "_").lower()
        super().__init__(
            specialist_id=f"spec_opp_{clean_id}",
            archetype=SpecialistArchetype.DYNAMIC_OPPORTUNITY_HUNTER,
            target_symbol=target_symbol,
        )
        self.category = category
        self.recommended_direction = recommended_direction.upper()
        self.invalidation_level = invalidation_level
        self.primary_rationale = primary_rationale
        self.market_attention_score = market_attention_score
        self.timing_stage = timing_stage

    async def evaluate_market(
        self,
        candles_15m: list[dict[str, Any]],
        multi_tf_candles: dict[str, list[dict[str, Any]]],
        order_book: dict[str, Any] | None = None,
        macro_context: dict[str, Any] | None = None,
    ) -> CandidateProposal:
        if not candles_15m:
            cur_price = 1.0
        else:
            cur_price = float(candles_15m[-1]["close"])

        # Determine direction
        if self.recommended_direction == "SHORT":
            direction = DecisionAction.SHORT
            # Exhaustion / Breakdown SHORT
            # Bound SL distance to institutional boundary (max 3.5%)
            raw_sl = (
                self.invalidation_level
                if (self.invalidation_level and self.invalidation_level > cur_price)
                else round(cur_price * 1.035, 6)
            )
            max_sl = round(cur_price * 1.035, 6)
            sl = min(raw_sl, max_sl)
            risk = max(abs(sl - cur_price), cur_price * 0.01)
            # TP must be structural, strictly positive, and provide at least 2.2R
            tp = round(max(cur_price * 0.85, cur_price - (risk * 2.2)), 6)
            if tp >= cur_price:
                tp = round(cur_price * 0.95, 6)
            rr = round((cur_price - tp) / risk, 2) if risk > 0 else 2.2
            conf = min(0.90, max(0.55, self.market_attention_score / 100.0))
            ev = round(0.35 + (conf * 0.4), 2)
            thesis = f"Opportunity Hunter [{self.category}]: {self.primary_rationale or 'Exhaustion/Breakdown short setup'}"
        elif self.recommended_direction == "LONG":
            direction = DecisionAction.LONG
            # Pre-Breakout / Momentum / Capitulation Reclaim LONG
            raw_sl = (
                self.invalidation_level
                if (self.invalidation_level and 0 < self.invalidation_level < cur_price)
                else round(cur_price * 0.965, 6)
            )
            min_sl = round(cur_price * 0.965, 6)
            sl = max(raw_sl, min_sl)
            risk = max(abs(cur_price - sl), cur_price * 0.01)
            tp = round(cur_price + (risk * 2.2), 6)
            rr = round((tp - cur_price) / risk, 2) if risk > 0 else 2.2
            conf = min(0.92, max(0.55, self.market_attention_score / 100.0))
            ev = round(0.40 + (conf * 0.45), 2)
            thesis = f"Opportunity Hunter [{self.category}]: {self.primary_rationale or 'Pre-breakout/Momentum long setup'}"
        else:
            direction = DecisionAction.NO_TRADE
            sl = cur_price * 0.98
            tp = cur_price * 1.04
            rr = 2.0
            conf = 0.25
            ev = 0.0
            thesis = f"Opportunity Hunter [{self.category}]: Monitoring in progress (Watch state)."

        prop = CandidateProposal(
            proposal_id=f"prop_opp_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=direction,
            thesis=thesis,
            entry_price=cur_price,
            stop_loss=sl,
            take_profit=tp,
            risk_reward_ratio=rr,
            expected_value_r=ev,
            confidence_score=conf,
            invalidation_condition=f"Price crosses invalidation boundary ${sl:.6f} or volume exhaustion.",
            suggested_notional_usd=250.0,
            telemetry={
                "category": self.category,
                "attention_score": self.market_attention_score,
                "timing_stage": self.timing_stage,
                "invalidation_level": self.invalidation_level,
            },
        )
        return self.apply_adversarial_review(prop, candles_15m, order_book)

