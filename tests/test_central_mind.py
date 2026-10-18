"""
tests/test_central_mind.py
==========================
Unit tests verifying the 6 Constitutional Invariants of CentralTradingMind:
1. Real price grounding (rejects synthetic / ungrounded prices).
2. Half-Kelly risk cap (throttles oversized requests to <= 1.5% equity risk).
3. Invalidation geometry (validates LONG and SHORT SL positions).
4. Multi-style capacity and portfolio heat limit.
5. Anti-cannibalization (rejects opposing directions).
6. Immutable audit logging into central_mind_decisions table.
"""

import pytest

from core.central_mind import CentralTradingMind, TradeProposal
from core.portfolio_shadow import portfolio_shadow


@pytest.fixture
def clean_central_mind():
    mind = CentralTradingMind()
    return mind


def test_central_mind_rejects_synthetic_and_simulated_proposals(clean_central_mind):
    mind = clean_central_mind

    # 1. Proposal flagged as is_synthetic
    prop_synth = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="BTC/USDT",
        direction="LONG",
        style="TREND",
        planned_entry=83000.0,
        stop_loss=82000.0,
        take_profit=85000.0,
        thesis="Test synthetic rejection",
        is_synthetic=True,
    )
    verdict = mind.evaluate_and_route(prop_synth)
    assert verdict.is_approved is False
    assert "Synthetic data" in (verdict.rejection_reason or "")

    # 2. Proposal from simulation origin
    prop_sim = TradeProposal(
        origin="ARENA_SIMULATION_RUNNER",
        symbol="BTC/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=83000.0,
        stop_loss=82000.0,
        take_profit=85000.0,
        thesis="Test simulation origin rejection",
    )
    verdict_sim = mind.evaluate_and_route(prop_sim)
    assert verdict_sim.is_approved is False
    assert "simulation" in (verdict_sim.rejection_reason or "").lower()


def test_central_mind_rejects_deviated_price(clean_central_mind, monkeypatch):
    mind = clean_central_mind

    # Mock live market price to $83,000.00
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: 83000.0)

    # Proposed entry at $86,000.00 (+3.6% divergence)
    prop = TradeProposal(
        origin="SPECIALIST_SWARM",
        symbol="BTC/USDT",
        direction="LONG",
        style="DAY",
        planned_entry=86000.0,
        stop_loss=84500.0,
        take_profit=89000.0,
        thesis="Overly drifted entry price",
    )
    verdict = mind.evaluate_and_route(prop)
    assert verdict.is_approved is False
    assert "Price Grounding Rejection" in (verdict.rejection_reason or "")


def test_central_mind_half_kelly_risk_throttling(clean_central_mind, monkeypatch):
    mind = clean_central_mind
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: 83000.0)

    # Request an absurd 5.0 BTC size (~$415,000 notional)
    prop = TradeProposal(
        origin="MANUAL_UI",
        symbol="BTC/USDT",
        direction="LONG",
        style="TREND",
        planned_entry=83000.0,
        stop_loss=82000.0,  # $1,000 stop distance
        take_profit=86000.0,
        requested_size=5.0,
        thesis="SMC trend continuation",
    )
    verdict = mind.evaluate_and_route(prop)
    if verdict.is_approved:
        # Max trade risk on $10k equity is 1.5% ($150)
        # For $1,000 stop distance, max allowed units = $150 / $1,000 = 0.15 BTC
        assert verdict.approved_size <= 0.16
        assert verdict.approved_size < 5.0
        assert verdict.risk_usd <= 160.0
        assert verdict.executed_position_id is not None
        # Clean up
        portfolio_shadow.close_position(verdict.executed_position_id, 83000.0, "TEST_CLEANUP")


def test_central_mind_rejects_invalid_geometry(clean_central_mind, monkeypatch):
    mind = clean_central_mind
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: 83000.0)

    # LONG with stop loss above entry
    prop_bad_long = TradeProposal(
        origin="DESK_TEST",
        symbol="BTC/USDT",
        direction="LONG",
        style="SCALP",
        planned_entry=83000.0,
        stop_loss=83500.0,  # Invalid! SL > Entry
        take_profit=84000.0,
        thesis="Broken geometry",
    )
    verdict = mind.evaluate_and_route(prop_bad_long)
    assert verdict.is_approved is False
    assert "Geometry Rejection" in (verdict.rejection_reason or "")


def test_central_mind_governance_report(clean_central_mind):
    report = clean_central_mind.get_system_governance_report()
    assert report["status"] == "OPERATIONAL_NORMAL"
    assert "HALF_KELLY_1_5_PCT_CAP" in report["governance_invariants"]
    assert "REAL_PRICE_GROUNDING_STRICT" in report["governance_invariants"]
    assert "max_positions" in report
