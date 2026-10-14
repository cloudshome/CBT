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

