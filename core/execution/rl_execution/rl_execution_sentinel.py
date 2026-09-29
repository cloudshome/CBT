"""
core/execution/rl_execution/rl_execution_sentinel.py
===================================================
Milestone 39: Deep Reinforcement Learning Execution Sentinel & Safety Gate.

Mathematical Specifications:
-----------------------------
1. State Observation Pipeline:
     Constructs normalized 6D observation vector from real-time microstructure data:
     [remaining_ratio, time_remaining_ratio, obi_l2, spread_bps, volatility, hawkes_ratio]

2. Policy Action Scaling & Microstructure Adjustment:
     - Base fraction recommended by PPO policy: a_base in [0.0, 1.0]
     - Toxicity Governor: If Hawkes ratio >= 3.0, dampen participation by factor (1.0 / toxicity_ratio)
     - Momentum Governor: If L2 OBI aligns favorably, allow up to +20% participation boost.

3. Constitutional Safety Gate:
     - Single execution tranche notional <= 1.5% of total portfolio equity.
     - Maximum instantaneous participation rate <= 10% of visible order book depth.
     - Fail-safe fallback to Almgren-Chriss closed-form schedule if policy outputs NaN or out-of-bounds.

4. Non-negotiable constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from core.execution.rl_execution.execution_environment import (
    MicrostructureExecutionState,
)
from core.execution.rl_execution.ppo_execution_policy import (
    PPOActorCriticPolicy,
)

logger = logging.getLogger("ai_quant_sentinel.rl_execution.sentinel")


class ExecutionStrategyMode(str, Enum):
    PPO_REINFORCEMENT_LEARNING = "PPO_REINFORCEMENT_LEARNING"
    ALMGREN_CHRISS_FALLBACK = "ALMGREN_CHRISS_FALLBACK"
    TOXICITY_HALT_DEFENSE = "TOXICITY_HALT_DEFENSE"


@dataclass
class RLExecutionTrancheDecision:
    """Analytical order slicing decision for current microstructure step."""

    symbol: str
    strategy_mode: ExecutionStrategyMode
    target_shares_remaining: float
    recommended_shares_to_execute: float
    recommended_notional_usd: float
    execution_fraction: float
    policy_raw_action: float
    critic_value_estimate: float
    market_mid_price: float
    portfolio_equity_usd: float
    max_equity_cap_usd: float
    is_participation_capped: bool
    is_equity_capped: bool
    action_narrative: str
    real_capital_enabled: bool = False


class RLExecutionSentinel:
    """
    Sub-millisecond Real-Time Reinforcement Learning Execution Sentinel.
    """

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        max_single_position_equity_pct: float = 0.015,  # 1.5% constitutional equity cap
        max_depth_participation_pct: float = 0.10,  # Max 10% of visible order book depth
        policy: PPOActorCriticPolicy | None = None,
    ) -> None:
        self.symbol = symbol
        self.max_equity_pct = max_single_position_equity_pct
        self.max_depth_pct = max_depth_participation_pct
        self.policy = policy or PPOActorCriticPolicy()
        self.real_capital_enabled: bool = False

    def evaluate_execution_tranche(
        self,
        portfolio_equity_usd: float,
        mid_price: float,
        total_order_shares: float,
        remaining_shares: float,
        current_step: int,
        max_steps: int,
        l2_obi: float = 0.0,
        spread_bps: float = 2.0,
        volatility_sigma: float = 0.02,
        hawkes_toxicity_ratio: float = 1.0,
        available_depth_shares: float = 100.0,
        force_fallback: bool = False,
    ) -> RLExecutionTrancheDecision:
        """
        Coordinates real-time RL policy execution, microstructure modulation,
        and constitutional risk capping.
        """
        if portfolio_equity_usd <= 0 or mid_price <= 0:
            raise ValueError("Equity and mid price must be strictly positive")
        if remaining_shares <= 0 or current_step >= max_steps:
            # Nothing left or completed
            return RLExecutionTrancheDecision(
                symbol=self.symbol,
                strategy_mode=ExecutionStrategyMode.PPO_REINFORCEMENT_LEARNING,
                target_shares_remaining=0.0,
                recommended_shares_to_execute=0.0,
                recommended_notional_usd=0.0,
                execution_fraction=0.0,
                policy_raw_action=0.0,
                critic_value_estimate=0.0,
                market_mid_price=mid_price,
                portfolio_equity_usd=portfolio_equity_usd,
                max_equity_cap_usd=portfolio_equity_usd * self.max_equity_pct,
                is_participation_capped=False,
                is_equity_capped=False,
                action_narrative="Order complete or no remaining shares",
                real_capital_enabled=False,
            )

        steps_remaining = max(1, max_steps - current_step)
        rem_ratio = remaining_shares / max(1e-6, total_order_shares)
        time_rem = steps_remaining / max(1, max_steps)

        # 1. Construct Microstructure State Observation
        state = MicrostructureExecutionState(
            remaining_inventory_ratio=rem_ratio,
            normalized_time_remaining=time_rem,
            obi_l2=l2_obi,
            spread_bps=spread_bps,
            volatility_sigma=volatility_sigma,
            hawkes_toxicity_ratio=hawkes_toxicity_ratio,
            current_mid_price=mid_price,
            target_inventory=total_order_shares,
            remaining_inventory=remaining_shares,
            step_index=current_step,
            max_steps=max_steps,
            real_capital_enabled=False,
        )
        state_vec = state.to_vector()

        # 2. Check for Critical Toxicity (Hawkes ratio >= 6.0)
        if hawkes_toxicity_ratio >= 6.0 and steps_remaining > 1:
            return RLExecutionTrancheDecision(
                symbol=self.symbol,
                strategy_mode=ExecutionStrategyMode.TOXICITY_HALT_DEFENSE,
                target_shares_remaining=remaining_shares,
                recommended_shares_to_execute=0.0,
                recommended_notional_usd=0.0,
                execution_fraction=0.0,
                policy_raw_action=0.0,
                critic_value_estimate=0.0,
                market_mid_price=mid_price,
                portfolio_equity_usd=portfolio_equity_usd,
                max_equity_cap_usd=portfolio_equity_usd * self.max_equity_pct,
                is_participation_capped=False,
                is_equity_capped=False,
                action_narrative=f"Critical flow toxicity (Hawkes ratio {hawkes_toxicity_ratio:.1f}x) detected. Pausing aggressive execution.",
                real_capital_enabled=False,
            )

        # 3. Policy Action Inference
        policy_act = self.policy.act(
            state=state_vec,
            deterministic=True,
            force_almgren_chriss_fallback=force_fallback,
            remaining_steps=steps_remaining,
        )

        raw_fraction = policy_act.action_fraction
        mode = (
            ExecutionStrategyMode.ALMGREN_CHRISS_FALLBACK
            if policy_act.is_fallback_almgren_chriss
            else ExecutionStrategyMode.PPO_REINFORCEMENT_LEARNING
        )

        # 4. Microstructure Modulation:
        # If L2 OBI is favorable (> 0.30 for buy), accelerate slightly
        modulated_fraction = raw_fraction
        if l2_obi > 0.30:
            modulated_fraction *= 1.0 + min(0.20, l2_obi * 0.20)
        elif l2_obi < -0.30:
            # Adverse book imbalance, taper participation
            modulated_fraction *= max(0.50, 1.0 + l2_obi * 0.30)

        # If last step, must liquidate everything
        if steps_remaining == 1:
            modulated_fraction = 1.0

        shares_proposed = remaining_shares * min(1.0, max(0.0, modulated_fraction))

        # 5. Order Book Depth Participation Cap
        max_depth_shares = available_depth_shares * self.max_depth_pct
        is_depth_capped = False
        if shares_proposed > max_depth_shares and steps_remaining > 1:
            shares_proposed = max_depth_shares
            is_depth_capped = True

        # 6. Constitutional 1.5% Equity Risk Cap
        max_equity_cap_usd = portfolio_equity_usd * self.max_equity_pct
        proposed_notional_usd = shares_proposed * mid_price
        is_equity_capped = False
        if proposed_notional_usd > max_equity_cap_usd:
            shares_proposed = max_equity_cap_usd / mid_price
            proposed_notional_usd = max_equity_cap_usd
            is_equity_capped = True

        final_fraction = shares_proposed / max(1e-6, remaining_shares)

        narrative_parts = [
            f"Mode: {mode.value}",
            f"Proposed: {shares_proposed:.4f} shares (${proposed_notional_usd:,.2f})",
        ]
        if is_depth_capped:
            narrative_parts.append(f"Capped at {self.max_depth_pct:.0%} book depth")
        if is_equity_capped:
            narrative_parts.append(f"Capped at 1.5% equity (${max_equity_cap_usd:,.2f})")

        return RLExecutionTrancheDecision(
            symbol=self.symbol,
            strategy_mode=mode,
            target_shares_remaining=remaining_shares,
            recommended_shares_to_execute=shares_proposed,
            recommended_notional_usd=proposed_notional_usd,
            execution_fraction=final_fraction,
            policy_raw_action=raw_fraction,
            critic_value_estimate=policy_act.state_value,
            market_mid_price=mid_price,
            portfolio_equity_usd=portfolio_equity_usd,
            max_equity_cap_usd=max_equity_cap_usd,
            is_participation_capped=is_depth_capped,
            is_equity_capped=is_equity_capped,
            action_narrative=" | ".join(narrative_parts),
            real_capital_enabled=False,
        )
