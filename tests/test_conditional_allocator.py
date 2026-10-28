"""
tests/test_conditional_allocator.py
===================================
Comprehensive verification of the CBT Conditional Portfolio Capital Allocator.

Covers:
1. Primary Core Anchors (BTC, ETH, GOLD) Priority & Immutability.
2. Conditional Capacity Expansion ("+ coin + coin...").
3. Trailed Stop Breakeven Risk Release (moves SL to entry, freeing risk budget).
4. Saturated Risk Gate Enforcement ($200 / 2.0% aggregate stop risk ceiling).
5. Elite Replacement Protocol: Weak/stagnant satellite coin replaced by an elite candidate,
   while Core Anchors (BTC, ETH, GOLD) remain strictly protected.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from core.central_mind import CentralTradingMind, PortfolioAction, TradeProposal
from core.portfolio_shadow import is_core_anchor, portfolio_shadow


@pytest.fixture(autouse=True)
def clean_shadow_state():
    """Ensure completely clean shadow portfolio before and after each test."""
    with patch("core.telegram_bot.telegram_bot.notify_trade_entry_sync", return_value=True), \
         patch("core.telegram_bot.telegram_bot.notify_trade_exit_sync", return_value=True):
        portfolio_shadow.reset_all_positions()
        yield
        portfolio_shadow.reset_all_positions()


def test_core_anchor_identification():
    """Verifies that BTC, ETH, and GOLD are identified as the 3 Primary Core Anchors."""
    assert is_core_anchor("BTC/USDT") is True
    assert is_core_anchor("BTCUSDT") is True
    assert is_core_anchor("ETH/USDT") is True
    assert is_core_anchor("ETHUSDT") is True
    assert is_core_anchor("XAU/USD") is True
    assert is_core_anchor("XAUUSD") is True
    assert is_core_anchor("PAXG/USDT") is True
    assert is_core_anchor("GOLD") is True

    # Satellite coins are not core anchors
    assert is_core_anchor("SOL/USDT") is False
    assert is_core_anchor("BNB/USDT") is False
    assert is_core_anchor("DOGE/USDT") is False


def test_breakeven_trailed_stop_releases_risk_budget():
    """Verifies that when stops trail to breakeven, remaining risk drops to $0 and budget is released."""
    os.environ["MAX_AGGREGATE_RISK_PCT"] = "2.0"

    # 1. Open a BTC trade with initial $40 stop risk (Entry: 80,000, SL: 76,000, Size: 0.01)
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.01,
        entry_price=80000.0,
        stop_loss=76000.0,  # $40 risk
        take_profit=88000.0,
        entry_reason="BTC Core Anchor",
        allow_multi_style=True,
    )
    assert pos_id is not None

    budget = portfolio_shadow.calculate_aggregate_risk_budget(
        book_id="MAIN_SOVEREIGN", account_equity_usd=10000.0, max_aggregate_risk_pct=2.0
    )
    assert budget["aggregate_stop_risk_usd"] == 40.0
    assert budget["available_risk_budget_usd"] == 160.0
    assert budget["released_risk_usd"] == 0.0

    # 2. Update stop loss to breakeven (80,000.0)
    portfolio_shadow.update_stop_loss(pos_id, new_stop_loss=80000.0)

    # 3. Recalculate risk budget: remaining risk must drop to $0.00 and budget fully available!
    budget_after = portfolio_shadow.calculate_aggregate_risk_budget(
        book_id="MAIN_SOVEREIGN", account_equity_usd=10000.0, max_aggregate_risk_pct=2.0
    )
    assert budget_after["aggregate_stop_risk_usd"] == 0.0
    assert budget_after["available_risk_budget_usd"] == 200.0


def test_conditional_expansion_btc_eth_plus_coins(monkeypatch):
    """
    Verifies the user's workflow:
    Running Core Anchors (BTC, ETH) and conditionally expanding with satellite opportunities
    (e.g., BTC + ETH + coin + coin...) as long as aggregate stop risk <= $200.
    """
    mind = CentralTradingMind()
    # Mock live prices to match entries
    prices = {
        "BTC/USDT": 80000.0,
        "ETH/USDT": 3000.0,
        "SOL/USDT": 150.0,
        "BNB/USDT": 600.0,
    }
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: prices.get(sym, 100.0))

    # 1. Open BTC (Core Anchor) - $40 risk
    prop_btc = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="BTC/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=80000.0,
        stop_loss=76000.0,
        take_profit=88000.0,
        requested_size=0.01,  # 0.01 * 4000 = $40 risk
        thesis="BTC Anchor",
        confluence_score=85.0,
    )
    v_btc = mind.evaluate_and_route(prop_btc)
    assert v_btc.is_approved is True
    assert v_btc.portfolio_action == PortfolioAction.OPEN.value

    # 2. Open ETH (Core Anchor) - $50 risk
    prop_eth = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="ETH/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=3000.0,
        stop_loss=2750.0,
        take_profit=3500.0,
        requested_size=0.20,  # 0.20 * 250 = $50 risk
        thesis="ETH Anchor",
        confluence_score=85.0,
    )
    v_eth = mind.evaluate_and_route(prop_eth)
    assert v_eth.is_approved is True
    assert v_eth.portfolio_action == PortfolioAction.OPEN.value

    # 3. Add Satellite Coin 1 (SOL) - High Confluence (82.0) - $30 risk
    prop_sol = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="SOL/USDT",
        direction="LONG",
        style="DAY",
        planned_entry=150.0,
        stop_loss=140.0,
        take_profit=170.0,
        requested_size=3.0,  # 3 * 10 = $30 risk
        thesis="SOL Momentum Breakout",
        confluence_score=82.0,
    )
    v_sol = mind.evaluate_and_route(prop_sol)
    assert v_sol.is_approved is True
    assert v_sol.portfolio_action == PortfolioAction.OPEN.value

    # Portfolio now has 3 positions: BTC + ETH + SOL (Total Risk = $40 + $50 + $30 = $120 / $200)

    # 4. Add Satellite Coin 2 (BNB) - Expansion past 3 into 4th position! Confluence 84.0 - $40 risk
    prop_bnb = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="BNB/USDT",
        direction="LONG",
        style="TREND",
        planned_entry=600.0,
        stop_loss=580.0,
        take_profit=650.0,
        requested_size=2.0,  # 2 * 20 = $40 risk
        thesis="BNB Breakout Continuation",
        confluence_score=84.0,
    )
    v_bnb = mind.evaluate_and_route(prop_bnb)
    assert v_bnb.is_approved is True
    assert v_bnb.portfolio_action == PortfolioAction.OPEN.value

    # Portfolio now has 4 concurrent positions running: BTC + ETH + SOL + BNB!
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 4
    symbols = {p["symbol"] for p in open_pos}
    assert symbols == {"BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"}


def test_low_confluence_satellite_rejected_from_expansion(monkeypatch):
    """Verifies that an opportunistic satellite coin with low confluence (< 80) is rejected from expanding past 3."""
    mind = CentralTradingMind()
    prices = {"BTC/USDT": 80000.0, "ETH/USDT": 3000.0, "XAU/USD": 2700.0, "SOL/USDT": 150.0}
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: prices.get(sym, 100.0))

    # Fill 3 core positions
    for sym, entry, sl, tp in [
        ("BTC/USDT", 80000.0, 78000.0, 84000.0),
        ("ETH/USDT", 3000.0, 2900.0, 3200.0),
        ("XAU/USD", 2700.0, 2650.0, 2800.0),
    ]:
        prop = TradeProposal(
            origin="AUTONOMOUS_TRADER",
            symbol=sym,
            direction="LONG",
            style="SWING",
            planned_entry=entry,
            stop_loss=sl,
            take_profit=tp,
            requested_size=0.01,
            thesis=f"{sym} Core",
            confluence_score=85.0,
        )
        assert mind.evaluate_and_route(prop).is_approved is True

    assert len(portfolio_shadow.get_open_positions()) == 3

    # Attempt to add satellite coin with weak confluence (72.0 < 80.0)
    prop_weak_sol = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="SOL/USDT",
        direction="LONG",
        style="SCALP",
        planned_entry=150.0,
        stop_loss=147.0,
        take_profit=156.0,
        requested_size=1.0,
        thesis="Weak Scalp Attempt",
        confluence_score=72.0,  # Below 80 hurdle
    )
    v_weak = mind.evaluate_and_route(prop_weak_sol)
    assert v_weak.is_approved is False
    assert "Opportunity Hurdle" in (v_weak.rejection_reason or "")


def test_replace_protocol_closes_stagnant_satellite_for_elite_opportunity(monkeypatch):
    """
    Verifies that when positions or risk reach limits:
    An Elite setup (confluence >= 85, EV >= 1.5R) replaces the weakest satellite coin,
    while Core Anchors (BTC, ETH) are NEVER replaced.
    """
    mind = CentralTradingMind()
    prices = {
        "BTC/USDT": 80000.0,
        "ETH/USDT": 3000.0,
        "SOL/USDT": 150.0,
        "BNB/USDT": 600.0,
        "XAU/USD": 2700.0,
        "PAXG/USDT": 2700.0,
    }
    monkeypatch.setattr(mind, "get_live_market_price", lambda sym: prices.get(sym, 100.0))

    # Artificially set max concurrent positions to 3 for deterministic replace test
    monkeypatch.setattr(mind, "MAX_CONCURRENT_POSITIONS", 3)
    os.environ["MAX_ELITE_POSITIONS"] = "3"

    # 1. Open BTC (Core Anchor)
    mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="BTC/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=80000.0,
        stop_loss=78000.0,
        take_profit=84000.0,
        requested_size=0.01,
        thesis="BTC Anchor",
        confluence_score=85.0,
    ))

    # 2. Open ETH (Core Anchor)
    mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="ETH/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=3000.0,
        stop_loss=2900.0,
        take_profit=3200.0,
        requested_size=0.1,
        thesis="ETH Anchor",
        confluence_score=85.0,
    ))

    # 3. Open SOL (Satellite coin)
    mind.evaluate_and_route(TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="SOL/USDT",
        direction="LONG",
        style="DAY",
        planned_entry=150.0,
        stop_loss=140.0,
        take_profit=160.0,
        requested_size=1.0,
        thesis="SOL Satellite",
        confluence_score=82.0,
    ))

    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 3
    sol_pos = [p for p in open_pos if p["symbol"] == "SOL/USDT"][0]

    # Simulate price drop on SOL to show unrealized loss (-$2.00, well above stop loss 140.0)
    portfolio_shadow.update_live_price("SOL/USDT", 148.0)

    # 4. An ELITE A+ opportunity appears on Gold (PAXG/USDT) with Confluence 92.0 and EV 1.8R
    prop_elite_gold = TradeProposal(
        origin="AUTONOMOUS_TRADER",
        symbol="PAXG/USDT",
        direction="LONG",
        style="TREND",
        planned_entry=2700.0,
        stop_loss=2660.0,
        take_profit=2800.0,
        requested_size=0.5,
        thesis="Elite Gold Breakout",
        confluence_score=92.0,
        expected_value_r=1.8,
    )

    verdict_elite = mind.evaluate_and_route(prop_elite_gold)

    # Should execute REPLACE: close SOL and open Gold!
    assert verdict_elite.is_approved is True
    assert verdict_elite.portfolio_action == PortfolioAction.REPLACE.value
    assert verdict_elite.replaced_position_id == sol_pos["position_id"]

    # Active positions must now be BTC, ETH, and PAXG (Gold) - SOL was successfully replaced!
    active_symbols = {p["symbol"] for p in portfolio_shadow.get_open_positions()}
    assert "SOL/USDT" not in active_symbols
    assert "PAXG/USDT" in active_symbols
    assert "BTC/USDT" in active_symbols
    assert "ETH/USDT" in active_symbols
