"""
tests/test_darwinian_arena.py
=============================
Adversarial and functional test battery for the Darwinian Specialist Research Arena (Milestone 21).

Tests:
1. Sandbox Isolation: 10 specialists cannot mutate each other or the main portfolio.
2. Realistic Friction: Fees and slippage correctly deducted on entries and exits.
3. Benchmark Alpha: Buy-and-Hold relative alpha calculation.
4. Survival State Transitions: SURVIVING -> PROBATION -> QUARANTINED.
5. Quarantine Enforced: Quarantined specialist blocked from opening trades.
6. Mastermind Bridge Veto: Quarantined specialist proposals strictly vetoed by Arbiter.
7. Winner Multiplier Invariant: 1.2x multiplier disabled (remains 1.0x).
8. API Endpoints: Leaderboard and specialist detail contracts verified.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import app
from core.arena.arbiter_bridge import ArenaArbiterBridge
from core.arena.benchmark import AssetBenchmarkEngine
from core.arena.engine import DarwinianArenaEngine
from core.arena.ledger import ArenaLedger
from core.arena.models import SpecialistSurvivalStatus
from core.arena.router import set_arena_engine
from core.arena.survival import SurvivalStateMachine
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.mastermind.specialist_base import CandidateProposal, SpecialistArchetype
from core.sky_intelligence.types import DecisionAction


@pytest.fixture
def isolated_ledger(tmp_path: Path) -> ArenaLedger:
    db_file = tmp_path / "test_arena_sandboxes.db"
    return ArenaLedger(db_path=db_file)


@pytest.fixture
def arena_engine(isolated_ledger: ArenaLedger) -> DarwinianArenaEngine:
    return DarwinianArenaEngine(ledger=isolated_ledger, initial_capital_per_specialist=100.0)


# ==============================================================================
# 1. SANDBOX ISOLATION & INITIALIZATION
# ==============================================================================

def test_arena_initializes_10_isolated_specialists_with_100_usd(arena_engine: DarwinianArenaEngine):
    """Verifies that all 10 specialists are initialized with exactly $100 virtual equity."""
    accounts = arena_engine.ledger.get_all_accounts()
    assert len(accounts) == 10

    total_equity = sum(a.current_equity_usd for a in accounts)
    assert total_equity == pytest.approx(1000.0, abs=0.01)

    expected_symbols = {
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
        "LINK/USDT", "DOGE/USDT", "AVAX/USDT", "SUI/USDT", "ZEC/USDT",
    }
    actual_symbols = {a.symbol for a in accounts}
    assert actual_symbols == expected_symbols

    for acc in accounts:
        assert acc.current_cash_usd == 100.0
        assert acc.current_equity_usd == 100.0
        assert acc.peak_equity_usd == 100.0
        assert acc.status == SpecialistSurvivalStatus.SURVIVING
        assert acc.open_position is None


def test_specialist_trading_does_not_mutate_other_specialists(arena_engine: DarwinianArenaEngine):
    """Verifies that trading in BTC sandbox does not mutate ETH or SOL sandboxes."""
    # Open position in BTC
    pos = arena_engine.open_position(
        specialist_id="spec_arena_btc",
        direction="LONG",
        entry_price=60000.0,
        stop_loss=58000.0,
        take_profit=64000.0,
        fraction_of_equity=0.50,
    )
    assert pos is not None

    btc_acc = arena_engine.ledger.get_account("spec_arena_btc")
    eth_acc = arena_engine.ledger.get_account("spec_arena_eth")
    sol_acc = arena_engine.ledger.get_account("spec_arena_sol")

    assert btc_acc.open_position is not None
    assert eth_acc.open_position is None
    assert sol_acc.open_position is None
    assert eth_acc.current_cash_usd == 100.0
    assert sol_acc.current_cash_usd == 100.0


# ==============================================================================
# 2. REALISTIC FRICTION (FEES & SLIPPAGE) & PNL ATTRIBUTION
# ==============================================================================

def test_realistic_friction_applied_on_entry_and_exit(arena_engine: DarwinianArenaEngine):
    """
    Verifies that simulated taker fee (5 bps) and slippage (2 bps)
    are applied on both entry and exit.
    """
    now_ms = int(time.time() * 1000)

    # 1. Open $50 notional position at $100.0
    pos = arena_engine.open_position(
        specialist_id="spec_arena_sol",
        direction="LONG",
        entry_price=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        fraction_of_equity=0.50,
        timestamp_ms=now_ms,
    )
    assert pos is not None
    # Slippage: 100 * (1 + 0.0002) = 100.02
    assert pos.entry_price == pytest.approx(100.02, abs=0.01)

    # 2. Close position at $110.0 (profitable trade)
    trade = arena_engine.close_position(
        specialist_id="spec_arena_sol",
        exit_price=110.0,
        exit_reason="MANUAL_TEST_EXIT",
        timestamp_ms=now_ms + 60000,
    )
    assert trade is not None
    assert trade.fees_usd > 0.0
    assert trade.net_pnl_usd < trade.gross_pnl_usd  # Net PnL must be less than gross due to fees
    assert trade.net_pnl_usd > 0.0  # Still profitable

    sol_acc = arena_engine.ledger.get_account("spec_arena_sol")
    assert sol_acc.total_trades == 1
    assert sol_acc.winning_trades == 1
    assert sol_acc.current_equity_usd > 100.0


# ==============================================================================
# 3. BENCHMARK RELATIVE ALPHA CALCULATION
# ==============================================================================

def test_benchmark_relative_alpha_calculation():
    """
    Verifies that Buy-and-Hold return and relative alpha are calculated mathematically:
    Asset drops -10%, Specialist equity rises +5% -> Alpha = +15%.
    """
    metrics = AssetBenchmarkEngine.calculate(
        initial_price=100.0,
        current_price=90.0,  # Asset dropped -10%
        initial_equity=100.0,
        current_equity=105.0,  # Specialist made +5%
    )
    assert metrics.benchmark_return_pct == -10.0
    assert metrics.specialist_return_pct == 5.0
    assert metrics.alpha_pct == 15.0
    assert metrics.is_outperforming is True


# ==============================================================================
# 4. SURVIVAL STATE MACHINE & ELIMINATION
# ==============================================================================

def test_drawdown_triggers_probation_state(arena_engine: DarwinianArenaEngine):
    """Drawdown >= 10% transitions specialist to PROBATION (sizing halved)."""
    sol_acc = arena_engine.ledger.get_account("spec_arena_sol")
    sol_acc.current_equity_usd = 89.0  # -11% drawdown from $100
    sol_acc.max_drawdown_pct = 11.0
    arena_engine.ledger.upsert_account(sol_acc)

    # Tick market to trigger survival evaluation
    updated = arena_engine.on_market_tick("SOL/USDT", 150.0)
    assert updated is not None
    assert updated.status == SpecialistSurvivalStatus.PROBATION


def test_drawdown_triggers_quarantine_state_and_blocks_trades(arena_engine: DarwinianArenaEngine):
    """Drawdown >= 20% transitions specialist to QUARANTINED and blocks trades."""
    doge_acc = arena_engine.ledger.get_account("spec_arena_doge")
    doge_acc.current_equity_usd = 78.0  # -22% drawdown
    doge_acc.max_drawdown_pct = 22.0
    arena_engine.ledger.upsert_account(doge_acc)

    # Tick market to trigger survival evaluation
    updated = arena_engine.on_market_tick("DOGE/USDT", 0.12)
    assert updated is not None
    assert updated.status == SpecialistSurvivalStatus.QUARANTINED
    assert updated.quarantine_reason is not None

    # Attempt to open trade while quarantined MUST fail
    pos = arena_engine.open_position(
        specialist_id="spec_arena_doge",
        direction="LONG",
        entry_price=0.12,
        stop_loss=0.11,
        take_profit=0.14,
    )
    assert pos is None  # Blocked!


def test_consecutive_losses_trigger_quarantine(arena_engine: DarwinianArenaEngine):
    """5 consecutive losses trigger QUARANTINED state."""
    zec_acc = arena_engine.ledger.get_account("spec_arena_zec")
    zec_acc.consecutive_losses = 5
    arena_engine.ledger.upsert_account(zec_acc)

    updated = arena_engine.on_market_tick("ZEC/USDT", 30.0)
    assert updated is not None
    assert updated.status == SpecialistSurvivalStatus.QUARANTINED
    assert "Consecutive loss streak" in (updated.quarantine_reason or "")


# ==============================================================================
# 5. MASTERMIND ARBITER BRIDGE & VETO PRIMACY
# ==============================================================================

@pytest.mark.asyncio
async def test_arbiter_bridge_vetoes_quarantined_specialist_proposals(arena_engine: DarwinianArenaEngine):
    """
    Verifies that when a specialist is QUARANTINED in the Arena,
    the Mastermind Arbiter Council strictly rejects its proposal
    from the master $10,000 portfolio.
    """
    bridge = ArenaArbiterBridge(arena_engine=arena_engine)

    # Quarantine DOGE specialist
    doge_acc = arena_engine.ledger.get_account("spec_arena_doge")
    doge_acc.status = SpecialistSurvivalStatus.QUARANTINED
    doge_acc.quarantine_reason = "Drawdown >= 20%"
    arena_engine.ledger.upsert_account(doge_acc)

    # Check bridge assessment directly
    assessment = bridge.evaluate_specialist_for_mastermind("DOGE/USDT")
    assert assessment.is_eligible is False
    assert assessment.weight_multiplier == 0.0
    assert "Darwinian Arena Veto" in (assessment.rejection_reason or "")

    # Now verify inside Mastermind Arbiter Council
    arbiter = MastermindArbiterCouncil(
        account_equity_usd=10_000.0,
        arena_bridge=bridge,
    )

    # Mock the Doge specialist to return a LONG proposal
    mock_prop = CandidateProposal(
        proposal_id="prop_doge_test",
        specialist_id="spec_meme_spike",
        archetype=SpecialistArchetype.MEME_MOMENTUM_SPIKE,
        symbol="DOGE/USDT",
        direction=DecisionAction.LONG,
        thesis="Breakout attempt by quarantined specialist",
        entry_price=0.15,
        stop_loss=0.14,
        take_profit=0.18,
        risk_reward_ratio=3.0,
        expected_value_r=1.5,
        confidence_score=0.90,
        invalidation_condition="SL",
        suggested_notional_usd=500.0,
    )

    candles = [{"timestamp": int(time.time() * 1000) - i * 60000, "open": 0.15, "high": 0.16, "low": 0.14, "close": 0.15, "volume": 1000.0} for i in range(25)]
    market_data = {"DOGE/USDT": {"15m": candles}}

    for spec in arbiter.specialists:
        if spec.target_symbol == "DOGE/USDT":
            spec.evaluate_market = AsyncMock(return_value=mock_prop)

    decisions = await arbiter.evaluate_swarm(market_data)
    doge_decisions = [d for d in decisions if d.symbol == "DOGE/USDT"]
    assert len(doge_decisions) >= 1

    dec = doge_decisions[0]
    # Trade MUST be rejected due to Darwinian Arena Veto
    assert dec.is_approved is False
    assert "Darwinian Arena Veto" in dec.rejection_reason


def test_winner_multiplier_is_disabled_and_remains_1_point_0(arena_engine: DarwinianArenaEngine):
    """
    Verifies invariant: An arena winner (PAPER_QUALIFIED with high alpha)
    does NOT receive a 1.2x multiplier. The bridge returns exactly 1.0x.
    """
    bridge = ArenaArbiterBridge(arena_engine=arena_engine)

    btc_acc = arena_engine.ledger.get_account("spec_arena_btc")
    btc_acc.status = SpecialistSurvivalStatus.PAPER_QUALIFIED
    btc_acc.alpha_vs_benchmark_pct = 25.0
    arena_engine.ledger.upsert_account(btc_acc)

    assessment = bridge.evaluate_specialist_for_mastermind("BTC/USDT")
    assert assessment.is_eligible is True
    assert assessment.weight_multiplier == 1.0  # Strictly 1.0, not 1.2!


# ==============================================================================
# 6. REST API LEADERBOARD ENDPOINTS
# ==============================================================================

def test_api_leaderboard_endpoint(arena_engine: DarwinianArenaEngine):
    """Tests /api/arena/leaderboard endpoint contract and data serialization."""
    set_arena_engine(arena_engine)
    client = TestClient(app)

    response = client.get("/api/arena/leaderboard")
    assert response.status_code == 200

    data = response.json()
    assert "total_arena_equity_usd" in data
    assert data["total_arena_equity_usd"] == pytest.approx(1000.0, abs=1.0)
    assert data["master_desk_equity_usd"] == 10000.0
    assert len(data["specialists"]) == 10


def test_api_specialist_detail_endpoint(arena_engine: DarwinianArenaEngine):
    """Tests /api/arena/specialist/{id} endpoint."""
    set_arena_engine(arena_engine)
    client = TestClient(app)

    response = client.get("/api/arena/specialist/spec_arena_eth")
    assert response.status_code == 200
    data = response.json()
    assert data["specialist_id"] == "spec_arena_eth"
    assert data["symbol"] == "ETH/USDT"
    assert data["initial_equity_usd"] == 100.0
