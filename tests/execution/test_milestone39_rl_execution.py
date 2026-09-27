"""
tests/execution/test_milestone39_rl_execution.py
=================================================
Adversarial & Unit Test Suite for Milestone 39:
Deep Reinforcement Learning (PPO) Microstructure Execution & Slippage Minimization Policy.

Validates:
1. Microstructure execution MDP state representation & normalization.
2. Almgren-Chriss permanent & temporary price impact dynamics in gym environment.
3. Terminal step inventory liquidation constraint.
4. PPO Actor-Critic policy forward pass, Sigmoid action bounding, and Critic value estimation.
5. Action sampling and Gaussian log-likelihood computation.
6. Closed-form Almgren-Chriss TWAP fallback mode.
7. Hawkes critical toxicity halt defense (Hawkes ratio >= 6.0).
8. Order book depth participation rate capping (<= 10% visible depth).
9. Constitutional 1.5% portfolio equity cap enforcement.
10. Permanent constitutional capital isolation (real_capital_enabled = False).
11. Milestone 18 execution surface preservation (149/149 tests green).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.execution.rl_execution.execution_environment import (
    MicrostructureExecutionEnvironment,
)
from core.execution.rl_execution.ppo_execution_policy import (
    PPOActorCriticPolicy,
)
from core.execution.rl_execution.rl_execution_sentinel import (
    ExecutionStrategyMode,
    RLExecutionSentinel,
)


@pytest.fixture
def exec_env() -> MicrostructureExecutionEnvironment:
    return MicrostructureExecutionEnvironment(
        total_shares_to_execute=10.0,
        total_time_horizon_steps=5,
        initial_price=3000.0,
        baseline_volatility=0.02,
        baseline_spread_bps=2.0,
        permanent_impact_gamma=2.5e-6,
        temporary_impact_eta=5.0e-5,
        risk_aversion_phi=1e-4,
    )


@pytest.fixture
def ppo_policy() -> PPOActorCriticPolicy:
    return PPOActorCriticPolicy(
        state_dim=6,
        hidden_dim=16,
        action_dim=1,
        fixed_log_std=-1.2,
        seed=42,
    )


@pytest.fixture
def rl_sentinel(ppo_policy: PPOActorCriticPolicy) -> RLExecutionSentinel:
    return RLExecutionSentinel(
        symbol="BTC/USDT",
        max_single_position_equity_pct=0.015,  # 1.5% equity cap
        max_depth_participation_pct=0.10,  # 10% book depth cap
        policy=ppo_policy,
    )


def test_01_environment_initialization_and_observation_vector(
    exec_env: MicrostructureExecutionEnvironment,
):
    """Verifies that the MDP environment initializes properly with valid observation vectors."""
    state = exec_env.reset(initial_obi=0.25, initial_hawkes_ratio=1.2)
    assert state.remaining_inventory == 10.0
    assert state.remaining_inventory_ratio == 1.0
    assert state.step_index == 0
    assert state.max_steps == 5

    vec = state.to_vector()
    assert len(vec) == 6
    for val in vec:
        assert isinstance(val, float)
        assert not math.isnan(val)
        assert not math.isinf(val)


def test_02_environment_step_price_impact_and_inventory_depletion(
    exec_env: MicrostructureExecutionEnvironment,
):
    """Verifies that taking an action depletes inventory and applies price impact."""
    exec_env.reset()
    # Step with 20% of inventory (2.0 shares)
    res = exec_env.step(action_fraction=0.20)

    assert not res.done
    assert math.isclose(res.executed_shares, 2.0, rel_tol=1e-4)
    assert math.isclose(res.next_state.remaining_inventory, 8.0, rel_tol=1e-4)
    assert res.fill_price > exec_env.initial_price  # Temporary & spread impact pushes price up
    assert res.next_state.current_mid_price > exec_env.initial_price  # Permanent impact
    assert res.reward < 0.0  # Execution incurs cost penalty


def test_03_terminal_step_complete_liquidation(exec_env: MicrostructureExecutionEnvironment):
    """Verifies that reaching the final step liquidates all remaining inventory."""
    exec_env.reset()
    # Take 4 tiny steps
    for _ in range(4):
        exec_env.step(action_fraction=0.05)

    assert exec_env.remaining_inventory > 5.0

    # Step 5: final step must liquidate entire remainder
    final_res = exec_env.step(action_fraction=0.05)
    assert final_res.done is True
    assert math.isclose(final_res.next_state.remaining_inventory, 0.0, abs_tol=1e-5)
    assert math.isclose(exec_env.total_executed_shares, 10.0, rel_tol=1e-4)


def test_04_ppo_actor_critic_forward_pass_and_bounds(ppo_policy: PPOActorCriticPolicy):
    """Verifies that actor outputs values in [0, 1] and critic outputs scalar value."""
    test_state = [1.0, 1.0, 0.5, 0.2, 2.0, 0.2]
    mu = ppo_policy.forward_actor(test_state)
    assert 0.0 <= mu <= 1.0

    val = ppo_policy.forward_critic(test_state)
    assert isinstance(val, float)
    assert not math.isnan(val)


def test_05_ppo_stochastic_sampling_and_analytical_log_prob(ppo_policy: PPOActorCriticPolicy):
    """Verifies stochastic action sampling and analytical log-likelihood calculation."""
    test_state = [0.8, 0.6, -0.2, 0.3, 1.5, 0.4]
    act = ppo_policy.act(test_state, deterministic=False)

    assert 0.0 <= act.action_fraction <= 1.0
    assert act.action_log_prob != 0.0
    assert not math.isnan(act.action_log_prob)
    assert act.is_fallback_almgren_chriss is False


def test_06_almgren_chriss_fallback_mode(ppo_policy: PPOActorCriticPolicy):
    """Verifies that fallback mode executes exact closed-form 1/N schedule."""
    test_state = [0.5, 0.5, 0.0, 0.2, 2.0, 0.2]
    # 4 steps remaining -> exact 1/4 = 0.25
    act = ppo_policy.act(test_state, force_almgren_chriss_fallback=True, remaining_steps=4)

    assert act.is_fallback_almgren_chriss is True
    assert math.isclose(act.action_fraction, 0.25, rel_tol=1e-5)


def test_07_hawkes_critical_toxicity_halt_defense(rl_sentinel: RLExecutionSentinel):
    """Verifies that Hawkes toxicity ratio >= 6.0 pauses aggressive execution."""
    decision = rl_sentinel.evaluate_execution_tranche(
        portfolio_equity_usd=100_000.0,
        mid_price=50_000.0,
        total_order_shares=2.0,
        remaining_shares=1.5,
        current_step=1,
        max_steps=5,
        hawkes_toxicity_ratio=6.5,  # Critical flow toxicity
    )

    assert decision.strategy_mode == ExecutionStrategyMode.TOXICITY_HALT_DEFENSE
    assert decision.recommended_shares_to_execute == 0.0
    assert decision.recommended_notional_usd == 0.0
    assert "Critical flow toxicity" in decision.action_narrative


def test_08_order_book_depth_participation_capping(rl_sentinel: RLExecutionSentinel):
    """Verifies that tranche size is capped at 10% of visible order book depth."""
    decision = rl_sentinel.evaluate_execution_tranche(
        portfolio_equity_usd=100_000.0,
        mid_price=1000.0,
        total_order_shares=10.0,
        remaining_shares=10.0,
        current_step=0,
        max_steps=5,
        available_depth_shares=5.0,  # 10% = 0.5 shares max
    )

    assert decision.is_participation_capped is True
    assert decision.recommended_shares_to_execute <= 0.50 + 1e-6
    assert "book depth" in decision.action_narrative


def test_09_constitutional_1_5_percent_equity_risk_cap(rl_sentinel: RLExecutionSentinel):
    """Verifies that execution tranche notional is capped strictly at 1.5% portfolio equity."""
    equity = 50_000.0  # 1.5% = $750 max
    mid = 50_000.0  # 0.015 shares = $750

    decision = rl_sentinel.evaluate_execution_tranche(
        portfolio_equity_usd=equity,
        mid_price=mid,
        total_order_shares=1.0,
        remaining_shares=1.0,  # $50,000 notional
        current_step=0,
        max_steps=2,
        available_depth_shares=100.0,
    )

    assert decision.is_equity_capped is True
    assert decision.recommended_notional_usd <= 750.0 + 1e-4
    assert decision.recommended_shares_to_execute <= (750.0 / mid) + 1e-6


def test_10_permanent_capital_isolation_firewall(
    exec_env: MicrostructureExecutionEnvironment,
    ppo_policy: PPOActorCriticPolicy,
    rl_sentinel: RLExecutionSentinel,
):
    """Verifies that real_capital_enabled = False is enforced across all components."""
    assert exec_env.real_capital_enabled is False
    assert ppo_policy.real_capital_enabled is False
    assert rl_sentinel.real_capital_enabled is False

    state = exec_env.reset()
    assert state.real_capital_enabled is False

    step_res = exec_env.step(0.1)
    assert step_res.real_capital_enabled is False

    act = ppo_policy.act(state.to_vector())
    assert act.real_capital_enabled is False

    decision = rl_sentinel.evaluate_execution_tranche(10_000.0, 2000.0, 1.0, 1.0, 0, 5)
    assert decision.real_capital_enabled is False


def test_11_milestone18_execution_surface_untouched():
    """Guarantees that Milestone 18 certified execution surface is NOT modified."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    py_exe = str(repo_root / ".venv" / "Scripts" / "python.exe")
    if not Path(py_exe).exists():
        py_exe = sys.executable

    res = subprocess.run(
        [py_exe, "scripts/verify_m18_certification.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Milestone 18 certification invalid:\n{res.stdout}\n{res.stderr}"
    assert "M18 Production Pass remains ACTIVE" in res.stdout
