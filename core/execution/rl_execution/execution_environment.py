"""
core/execution/rl_execution/execution_environment.py
===================================================
Milestone 39: Microstructure Execution Markov Decision Process (MDP) Environment.

Formulates optimal trade execution as an MDP:
1. State Space S_t:
     [remaining_inventory_ratio, normalized_time_remaining, obi_l2, spread_bps, volatility_sigma, hawkes_ratio]
2. Action Space A_t:
     Continuous execution intensity a_t in [0.0, 1.0]: fraction of remaining target to execute.
3. Reward Function:
     R_t = -Implementation_Shortfall_bps - Risk_Aversion * inventory_q^2 * sigma^2 * dt - Terminal_Unfilled_Penalty
4. Constitutional Capital Isolation: real_capital_enabled = False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MicrostructureExecutionState:
    """State observation vector for RL execution agent."""

    remaining_inventory_ratio: float  # q_t / Q_0 in [0.0, 1.0]
    normalized_time_remaining: float  # (T - t) / T in [0.0, 1.0]
    obi_l2: float  # Order Book Imbalance in [-1.0, 1.0]
    spread_bps: float  # Bid-Ask spread in bps
    volatility_sigma: float  # Instantaneous volatility estimate
    hawkes_toxicity_ratio: float  # lambda(t) / mu flow intensity ratio
    current_mid_price: float
    target_inventory: float
    remaining_inventory: float
    step_index: int
    max_steps: int
    real_capital_enabled: bool = False

    def to_vector(self) -> list[float]:
        """Returns 6-dimensional normalized observation vector."""
        return [
            float(max(0.0, min(1.0, self.remaining_inventory_ratio))),
            float(max(0.0, min(1.0, self.normalized_time_remaining))),
            float(max(-1.0, min(1.0, self.obi_l2))),
            float(max(0.1, min(50.0, self.spread_bps)) / 10.0),
            float(max(0.0001, min(0.10, self.volatility_sigma)) * 100.0),
            float(max(0.5, min(10.0, self.hawkes_toxicity_ratio)) / 5.0),
        ]


@dataclass
class ExecutionStepResult:
    """Result of taking an execution action in the MDP environment."""

    next_state: MicrostructureExecutionState
    reward: float
    done: bool
    executed_shares: float
    fill_price: float
    step_slippage_bps: float
    implementation_shortfall_bps: float
    info: dict[str, Any]
    real_capital_enabled: bool = False


class MicrostructureExecutionEnvironment:
    """
    Simulation gym for training and evaluating RL optimal execution policies.
    """

    def __init__(
        self,
        total_shares_to_execute: float = 10.0,
        total_time_horizon_steps: int = 10,
        initial_price: float = 3000.0,
        baseline_volatility: float = 0.02,
        baseline_spread_bps: float = 2.0,
        permanent_impact_gamma: float = 2.5e-6,
        temporary_impact_eta: float = 5.0e-5,
        risk_aversion_phi: float = 1e-4,
    ) -> None:
        if total_shares_to_execute <= 0 or total_time_horizon_steps <= 0:
            raise ValueError("Shares and steps must be strictly positive")

        self.total_shares = total_shares_to_execute
        self.max_steps = total_time_horizon_steps
        self.initial_price = initial_price
        self.volatility = baseline_volatility
        self.baseline_spread_bps = baseline_spread_bps
        self.gamma = permanent_impact_gamma
        self.eta = temporary_impact_eta
        self.phi = risk_aversion_phi
        self.real_capital_enabled: bool = False

        self.reset()

    def reset(
        self,
        initial_obi: float = 0.0,
        initial_hawkes_ratio: float = 1.0,
    ) -> MicrostructureExecutionState:
        """Resets environment to starting state."""
        self.current_step = 0
        self.remaining_inventory = self.total_shares
        self.current_mid = self.initial_price
        self.arrival_price = self.initial_price
        self.total_cost_usd = 0.0
        self.total_executed_shares = 0.0
        self.current_obi = initial_obi
        self.current_hawkes = initial_hawkes_ratio

        return self._get_state()

    def _get_state(self) -> MicrostructureExecutionState:
        rem_ratio = self.remaining_inventory / self.total_shares
        time_rem = (self.max_steps - self.current_step) / self.max_steps
        return MicrostructureExecutionState(
            remaining_inventory_ratio=rem_ratio,
            normalized_time_remaining=time_rem,
            obi_l2=self.current_obi,
            spread_bps=self.baseline_spread_bps,
            volatility_sigma=self.volatility,
            hawkes_toxicity_ratio=self.current_hawkes,
            current_mid_price=self.current_mid,
            target_inventory=self.total_shares,
            remaining_inventory=self.remaining_inventory,
            step_index=self.current_step,
            max_steps=self.max_steps,
            real_capital_enabled=False,
        )

    def step(self, action_fraction: float) -> ExecutionStepResult:
        """
        Executes action_fraction of remaining inventory.
        Calculates Almgren-Chriss permanent & temporary price impact.
        """
        if self.current_step >= self.max_steps or self.remaining_inventory <= 1e-6:
            # Already terminal
            state = self._get_state()
            return ExecutionStepResult(
                next_state=state,
                reward=0.0,
                done=True,
                executed_shares=0.0,
                fill_price=self.current_mid,
                step_slippage_bps=0.0,
                implementation_shortfall_bps=0.0,
                info={"terminal": True},
                real_capital_enabled=False,
            )

        # Clamping action fraction to [0.0, 1.0]
        action_clamped = max(0.0, min(1.0, float(action_fraction)))

        # Terminal step forces complete liquidation
        is_last_step = self.current_step == self.max_steps - 1
        if is_last_step:
            shares_to_execute = self.remaining_inventory
        else:
            shares_to_execute = self.remaining_inventory * action_clamped

        # Almgren-Chriss Price Dynamics:
        # Temporary impact: g(v) = eta * v
        # Permanent impact: h(v) = gamma * v
        temp_impact = self.eta * shares_to_execute
        perm_impact = self.gamma * shares_to_execute

        # Microstructure half-spread cost
        half_spread_usd = self.current_mid * (self.baseline_spread_bps / 20_000.0)

        # Execution Fill Price (for buying: pushes price up)
        fill_price = self.current_mid + half_spread_usd + temp_impact
        # Update mid price with permanent impact
        self.current_mid += perm_impact

        # Update inventory
        self.remaining_inventory -= shares_to_execute
        self.total_executed_shares += shares_to_execute
        self.total_cost_usd += shares_to_execute * fill_price
        self.current_step += 1

        # Calculate Slippage and Implementation Shortfall
        _step_slippage_usd = (fill_price - self.arrival_price) * shares_to_execute
        step_slippage_bps = (
            ((fill_price - self.arrival_price) / self.arrival_price) * 10_000.0
            if shares_to_execute > 0
            else 0.0
        )

        # Cumulative Implementation Shortfall (IS)
        avg_cost = self.total_cost_usd / max(1e-6, self.total_executed_shares)
        total_is_bps = ((avg_cost - self.arrival_price) / self.arrival_price) * 10_000.0

        # Inventory variance penalty (CARA utility term)
        var_penalty = self.phi * (self.remaining_inventory**2) * (self.volatility**2)

        # Reward = negative slippage cost minus inventory risk
        step_cost_penalty = step_slippage_bps * 0.1
        reward = -(step_cost_penalty + var_penalty)

        # Terminal penalty if unfilled
        done = (self.current_step >= self.max_steps) or (self.remaining_inventory <= 1e-6)
        if done and self.remaining_inventory > 1e-4:
            unfilled_penalty = (self.remaining_inventory / self.total_shares) * 50.0
            reward -= unfilled_penalty

        next_state = self._get_state()

        return ExecutionStepResult(
            next_state=next_state,
            reward=reward,
            done=done,
            executed_shares=shares_to_execute,
            fill_price=fill_price,
            step_slippage_bps=step_slippage_bps,
            implementation_shortfall_bps=total_is_bps,
            info={
                "remaining_inventory": self.remaining_inventory,
                "step": self.current_step,
                "total_executed": self.total_executed_shares,
            },
            real_capital_enabled=False,
        )
