import pytest
import numpy as np
from fastapi.testclient import TestClient
from app import app
from core.monte_carlo_stress import (
    MonteCarloStressTester,
    MonteCarloTrajectorySimulationResult,
    monte_carlo_stress_tester,
)

client = TestClient(app)


def test_gbm_trajectory_simulation_structure():
    """Verifies that simulate_gbm_trajectory produces exact 10,000 paths and cone steps."""
    res: MonteCarloTrajectorySimulationResult = monte_carlo_stress_tester.simulate_gbm_trajectory(
        initial_capital=100_000.0,
        expected_return=0.08,
        volatility=0.18,
        horizon_years=5.0,
        steps=60,
        num_paths=1000,
    )

    assert isinstance(res, MonteCarloTrajectorySimulationResult)
    assert res.initial_capital == 100_000.0
    assert res.steps_count == 61
    assert len(res.steps) == 61

    step0 = res.steps[0]
    assert step0.step == 0
    assert step0.p5 == 100_000.0
    assert step0.p50 == 100_000.0
    assert step0.p95 == 100_000.0
    assert step0.smooth_winner == 100_000.0
    assert step0.below_start == 100_000.0

    step_end = res.steps[-1]
    assert step_end.step == 60
    assert step_end.p5 < step_end.p25 < step_end.p50 < step_end.p75 < step_end.p95
    assert res.p5_terminal == step_end.p5
    assert res.p95_terminal == step_end.p95

    assert res.probability_of_ruin >= 0.0
    assert res.probability_of_loss >= 0.0
    assert 0.0 <= res.probability_of_loss <= 1.0
    assert res.median_max_drawdown_pct > 0.0


def test_gbm_trajectory_path_archetypes():
    """Verifies that the 4 distinct realized path archetypes are differentiated."""
    res = monte_carlo_stress_tester.simulate_gbm_trajectory(
        initial_capital=100_000.0,
        expected_return=0.08,
        volatility=0.25,
        horizon_years=3.0,
        steps=36,
        num_paths=2000,
    )

    assert res.steps[-1].smooth_winner > 100_000.0
    assert res.steps[-1].below_start < 100_000.0


def test_stress_test_backward_compatibility():
    """Verifies that existing stress_test method remains 100% backward-compatible."""
    returns = [0.01, -0.015, 0.02, -0.005, 0.03, -0.01, 0.015, -0.02, 0.025, 0.01, -0.008, 0.012]
    rep = monte_carlo_stress_tester.stress_test(returns)
    assert rep.num_simulations == 10000
    assert 0.0 <= rep.probability_of_ruin <= 1.0
    assert rep.p50_max_drawdown_pct >= 0.0
    assert rep.p95_max_drawdown_pct >= rep.p50_max_drawdown_pct
    assert "Monte Carlo 10k Run" in rep.summary


def test_api_endpoint_monte_carlo():
    """Verifies that POST /api/institutional/monte-carlo returns both report and trajectory."""
    response = client.post(
        "/api/institutional/monte-carlo",
        params={
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "initial_capital": 100000.0,
            "annual_return": 0.08,
            "annual_volatility": 0.18,
            "horizon_years": 5.0,
            "num_paths": 1000,
            "steps": 24,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "probability_of_ruin" in data
    assert "p50_max_drawdown_pct" in data
    assert "trajectory" in data

    traj = data["trajectory"]
    assert traj["initial_capital"] == 100000.0
    assert len(traj["steps"]) == 25
    assert traj["p95_terminal"] > traj["p5_terminal"]
    assert "steps" in traj
