"""
tests/test_opportunity_reserve.py
=================================
Deterministic verification of the Opportunity Reserve Protocol.
Guarantees:
1. Base concurrent capacity (default 6) for standard qualified setups.
2. Preserves existing swing trades without artificial early eviction.
3. Automatically reserves headroom (up to 8) exclusively for Elite / A+ grade setups (>= 85 confluence or >= 1.5R EV).
4. Standard setups (> 6 positions) are throttled until positions close or an elite setup emerges.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

from core.portfolio_shadow import portfolio_shadow
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.mastermind.specialist_base import CandidateProposal, DecisionAction, EpistemicGrade, SpecialistArchetype


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean shadow portfolio state before and after each test."""
    with patch("core.telegram_bot.telegram_bot.notify_trade_entry_sync", return_value=True):
        portfolio_shadow.reset_all_positions()
        yield
        portfolio_shadow.reset_all_positions()


def test_portfolio_shadow_opportunity_reserve():
    """Verifies portfolio_shadow enforces base capacity of 6 and unlocks up to 8 for elite setups."""
    os.environ["MAX_CONCURRENT_POSITIONS"] = "6"
    os.environ["MAX_ELITE_POSITIONS"] = "8"

    # Fill base capacity of 6 positions across allowed tier-1 assets
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XAU/USD", "PAXG/USDT"]
    for i, sym in enumerate(symbols):
        pos_id = portfolio_shadow.open_position(
            symbol=sym,
            direction="LONG",
            size=0.01,
            entry_price=100.0 * (i + 1),
            stop_loss=98.0 * (i + 1),
            take_profit=106.0 * (i + 1),
            entry_reason=f"Standard setup {i+1}",
            confluence_score=75.0,  # Standard setup (< 85)
            style_tag=f"[TAG_{i}]",
            allow_multi_style=True,
            enforce_atomic_limits=True,
        )
        assert pos_id is not None
        assert pos_id.startswith("POS")

    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 6

    # Attempting to open 7th position with standard confluence (75.0) should be rejected
    with pytest.raises(ValueError, match="maximum allowable cap"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.01,
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=106.0,
            entry_reason="7th standard setup",
            confluence_score=75.0,
            style_tag="[TAG_7_STD]",
            allow_multi_style=True,
            enforce_atomic_limits=True,
        )

    # Opening 7th position with ELITE confluence (88.0) MUST succeed via Opportunity Reserve
    elite_pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.01,
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=106.0,
        entry_reason="Elite A+ setup",
        confluence_score=88.0,
        style_tag="[TAG_7_ELITE]",
        allow_multi_style=True,
        enforce_atomic_limits=True,
    )
    assert elite_pos_id is not None
    assert len(portfolio_shadow.get_open_positions()) == 7

    # Opening 8th position with ELITE confluence (92.0) MUST succeed
    elite_pos_id_2 = portfolio_shadow.open_position(
        symbol="ETH/USDT",
        direction="LONG",
        size=0.01,
        entry_price=2000.0,
        stop_loss=1960.0,
        take_profit=2120.0,
        entry_reason="Elite A+ setup 2",
        confluence_score=92.0,
        style_tag="[TAG_8_ELITE]",
        allow_multi_style=True,
        enforce_atomic_limits=True,
    )
    assert elite_pos_id_2 is not None
    assert len(portfolio_shadow.get_open_positions()) == 8

    # 9th position even with ELITE confluence is rejected as hard ceiling (8) is reached
    with pytest.raises(ValueError, match="maximum allowable cap"):
        portfolio_shadow.open_position(
            symbol="SOL/USDT",
            direction="LONG",
            size=0.01,
            entry_price=150.0,
            stop_loss=147.0,
            take_profit=160.0,
            entry_reason="9th elite setup over cap",
            confluence_score=95.0,
            style_tag="[TAG_9_ELITE]",
            allow_multi_style=True,
            enforce_atomic_limits=True,
        )


@pytest.mark.asyncio
async def test_mastermind_arbiter_opportunity_reserve():
    """Verifies that MastermindArbiterCouncil allows elite setups past base cap into reserve."""
    arbiter = MastermindArbiterCouncil(account_equity_usd=10_000.0)

    # Mock 6 existing open positions
    mock_positions = [{"symbol": f"MOCK_{i}/USDT", "position_id": f"P{i}"} for i in range(6)]

    standard_proposal = CandidateProposal(
        proposal_id="prop_test_std",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.LONG,
        thesis="Standard confluence setup",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=63000.0,
        risk_reward_ratio=3.0,
        expected_value_r=0.8,
        confidence_score=0.75,
        invalidation_condition="Break below 59000",
        suggested_notional_usd=1000.0,
        epistemic_grade=EpistemicGrade.HYPOTHESIS,
    )

    elite_proposal = CandidateProposal(
        proposal_id="prop_test_elite",
        specialist_id="spec_btc_macro",
        archetype=SpecialistArchetype.BTC_MACRO_MICROSTRUCTURE,
        symbol="BTC/USDT",
        direction=DecisionAction.LONG,
        thesis="Elite A+ setup",
        entry_price=60000.0,
        stop_loss=59000.0,
        take_profit=63000.0,
        risk_reward_ratio=3.0,
        expected_value_r=1.8,
        confidence_score=0.90,
        invalidation_condition="Break below 59000",
        suggested_notional_usd=1000.0,
        epistemic_grade=EpistemicGrade.HYPOTHESIS,
    )

    candles = [
        {
            "timestamp": 1000 + i * 60000,
            "open": 60000.0,
            "high": 60100.0,
            "low": 59900.0,
            "close": 60000.0,
            "volume": 100.0,
        }
        for i in range(25)
    ]
    market_data = {"BTC/USDT": {"15m": candles, "multi_tf": {"15m": candles}}}

    # Test standard proposal rejection at base cap 6
    with patch("core.mastermind.mastermind_arbiter.portfolio_shadow.get_open_positions", return_value=mock_positions), \
         patch.object(arbiter.specialists[0], "evaluate_market", return_value=standard_proposal):
        decisions_std = await arbiter.evaluate_swarm(market_data)
        assert len(decisions_std) >= 1
        assert decisions_std[0].is_approved is False
        assert "Max portfolio positions" in decisions_std[0].rejection_reason

    # Test elite proposal approval using Opportunity Reserve headroom
    with patch("core.mastermind.mastermind_arbiter.portfolio_shadow.get_open_positions", return_value=mock_positions), \
         patch.object(arbiter.specialists[0], "evaluate_market", return_value=elite_proposal):
        decisions_elite = await arbiter.evaluate_swarm(market_data)
        assert len(decisions_elite) >= 1
        assert decisions_elite[0].is_approved is True

