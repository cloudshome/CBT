"""
tests/test_agent_concept_arena.py
=================================
Unit tests for AgentConceptArena and Mastermind Tournament:
1. Verifies tournament execution across 5 specialized agent personas.
2. Checks rank assignment, win rate, and Net R scoring.
3. Tests leader paper trade deployment into portfolio_shadow.
"""

from pathlib import Path
import tempfile
import pytest

from core.research.agent_concept_arena import AgentConceptArena


@pytest.fixture
def temp_arena_env(tmp_path: Path):
    state_file = tmp_path / "test_arena_state.json"
    arena = AgentConceptArena(state_path=state_file)
    return arena


def test_agent_concept_arena_tournament(temp_arena_env):
    arena = temp_arena_env

    # Run competitive tournament round without real capital
    round_result = arena.run_tournament_round(bars_count=250, deploy_to_paper=False)

    assert round_result.round_id.startswith("ARENA_RND_")
    assert len(round_result.leaderboard) == 5

    # Check ranking order
    ranks = [e.rank for e in round_result.leaderboard]
    assert ranks == [1, 2, 3, 4, 5]

    # Verify score ordering (descending)
    scores = [e.tournament_score for e in round_result.leaderboard]
    assert scores == sorted(scores, reverse=True)

    # Leaderboard status retrieval
    status = arena.get_leaderboard()
    assert status["status"] == "ACTIVE"
    assert status["total_agents"] == 5
    assert len(status["leaderboard"]) == 5


def test_agent_concept_arena_paper_deployment_risk_invariants(temp_arena_env):
    arena = temp_arena_env

    # 1. deploy_to_paper defaults to False
    res_default = arena.run_tournament_round(bars_count=200)
    assert res_default.paper_trades_deployed == 0

    # 2. When deploy_to_paper=True, verify size is Half-Kelly risk bounded (NOT hardcoded 1.0)
    res_deployed = arena.run_tournament_round(bars_count=200, deploy_to_paper=True, symbol="ETH/USDT")
    from core.portfolio_shadow import portfolio_shadow
    positions = portfolio_shadow.get_open_positions()
    arena_pos = [p for p in positions if "Arena Leader" in (p.get("entry_reason") or "")]
    if arena_pos:
        pos = arena_pos[0]
        # Must be dynamically risk-sized rather than hardcoded 1.0
        assert pos["size"] != 1.0
        assert pos["size"] > 0.0
        # Invalidation must be positive and non-zero
        assert pos["entry_price"] > 0
        assert pos["stop_loss"] < pos["entry_price"]
        # Max loss (stop_dist * size) must strictly respect 1.5% equity risk cap ($150)
        stop_dist = abs(pos["entry_price"] - pos["stop_loss"])
        max_loss = stop_dist * pos["size"]
        assert max_loss <= 150.0
        # Clean up test position
        portfolio_shadow.close_position(pos["position_id"], pos["entry_price"], "TEST_CLEANUP")



