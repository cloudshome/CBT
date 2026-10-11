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

        return CandidateProposal(
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
            telemetry={"kelly_fraction": decision.kelly_fraction, "regime": str(setup.regime if setup else "UNKNOWN")},
        )


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

        return CandidateProposal(
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

        return CandidateProposal(
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

            return CandidateProposal(
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

        return CandidateProposal(
            proposal_id=f"prop_meme_{uuid.uuid4().hex[:8]}",
            specialist_id=self.specialist_id,
            archetype=self.archetype,
            symbol=self.target_symbol,
            direction=DecisionAction.NO_TRADE,
            thesis=f"Normal meme activity: volume ratio {vol_ratio:.2f}x below 2.5x threshold.",
            entry_price=cur_price,
            stop_loss=cur_price * 0.95,
            take_profit=cur_price * 1.10,
            risk_reward_ratio=2.0,
            expected_value_r=0.0,
            confidence_score=0.15,
            invalidation_condition="Volume threshold not reached.",
            suggested_notional_usd=0.0,
            telemetry={"vol_ratio": vol_ratio},
        )


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
            return CandidateProposal(
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
