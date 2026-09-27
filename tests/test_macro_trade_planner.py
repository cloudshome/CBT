"""
Tests for MacroTradePlanner.
Verifies confluence evaluation, Half-Kelly sizing dampening on macro headwind,
multi-pair dynamic trading plan generation, and risk primacy invariants.
"""

import pytest

from core.macro_cognitive_engine import macro_cognitive_engine
from core.macro_trade_planner import (
    MacroTradePlanner,
)


@pytest.fixture
def trade_planner():
    return MacroTradePlanner()


def test_confluent_dovish_long(trade_planner):
    """When macro regime is DOVISH/EXPANDING and technical bias is LONG -> CONFLUENT (1.0x sizing)."""
    # Feed dovish transcript to memory
    dovish_text = """
    Chairman Powell announces the start of an aggressive rate cutting cycle.
    Inflation has dropped back to target, and the Fed is easing policy.
    Liquidity is expanding rapidly across the global system.
    Expect massive capital inflows into Bitcoin and Ethereum.
    """
    macro_cognitive_engine.analyze_macro_content(
        text=dovish_text,
        title="Dovish Cut Show",
        author="Fed Watcher",
    )

    eval_result = trade_planner.evaluate_macro_confluence(
        symbol="BTC/USDT",
        technical_direction="LONG",
    )

    assert eval_result["alignment"] == "CONFLUENT"
    assert eval_result["risk_multiplier"] == 1.0
    assert "confluent" in eval_result["advisory"].lower()


def test_caution_dampened_hawkish_long(trade_planner):
    """When macro regime is HAWKISH/CONTRACTING and technical bias is LONG -> CAUTION_DAMPENED (0.5x Half-Kelly sizing)."""
    hawkish_text = """
    Fed announces that rate hikes are back on the table.
    Sticky inflation and surging commodity prices are forcing aggressive quantitative tightening.
    The dollar index is rallying violently and global liquidity is contracting.
    Equities and crypto face severe downside risks.
    """
    macro_cognitive_engine.analyze_macro_content(
        text=hawkish_text,
        title="Hawkish Shock Talk Show",
        author="Macro Bear",
    )

    eval_result = trade_planner.evaluate_macro_confluence(
        symbol="BTC/USDT",
        technical_direction="LONG",
    )

    assert eval_result["alignment"] == "CAUTION_DAMPENED"
    assert eval_result["risk_multiplier"] == 0.50
    assert (
        "dampener" in eval_result["advisory"].lower()
        or "warning" in eval_result["advisory"].lower()
    )


def test_confluent_hawkish_short(trade_planner):
    """When macro regime is HAWKISH/CONTRACTING and technical bias is SHORT -> CONFLUENT (1.0x sizing)."""
    hawkish_text = """
    Hawkish policy shock: The Fed is tightening monetary policy and maintaining higher for longer rates.
    Rate hike possibilities are increasing. The liquidity drain is accelerating, creating severe downside risk for crypto.
    """
    macro_cognitive_engine.analyze_macro_content(
        text=hawkish_text,
        title="Liquidity Drain Panel",
        author="Fed Analyst",
    )

    eval_result = trade_planner.evaluate_macro_confluence(
        symbol="ETH/USDT",
        technical_direction="SHORT",
    )

    assert eval_result["alignment"] == "CONFLUENT"
    assert eval_result["risk_multiplier"] == 1.0


def test_generate_live_trading_plans_multi_pair(trade_planner):
    """Verifies generation of dynamic trading plans across BTC/USDT, ETH/USDT, SOL/USDT."""
    plans = trade_planner.generate_live_trading_plans()

    assert len(plans) >= 3
    symbols = [p["symbol"] for p in plans]
    assert "BTC/USDT" in symbols
    assert "ETH/USDT" in symbols
    assert "SOL/USDT" in symbols

    btc_plan = next(p for p in plans if p["symbol"] == "BTC/USDT")
    assert btc_plan["currentPrice"] > 0
    assert btc_plan["pdh"] > 0
    assert btc_plan["pdl"] > 0
    assert len(btc_plan["fvgZone"]) > 0
    assert len(btc_plan["orderBlock"]) > 0
    assert len(btc_plan["bullPath"]) > 0
    assert len(btc_plan["bearPath"]) > 0
    assert btc_plan["macroAlignment"] in ("CONFLUENT", "NEUTRAL", "CAUTION_DAMPENED")
