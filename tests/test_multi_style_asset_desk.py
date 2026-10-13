"""
tests/test_multi_style_asset_desk.py
====================================
Quantitative unit & integration tests for Multi-Style Asset Trading Intelligence (BTC Desk).
Covers:
1. Trading style classification across all 5 archetypes (SCALP, DAY, TREND, RANGE, SWING).
2. Anti-Cannibalization Guard (Deterministic Fail-Closed on opposing directions).
3. Concurrent multi-style sub-book execution in the same asset direction.
4. Same-style duplicate sub-book rejection.
5. Cumulative asset risk limit enforcement (Half-Kelly envelope, <= 1.5% cap).
6. Institutional desk attribution in paper trading position reporting.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock

from core.autonomous_trader import classify_trading_style
from core.portfolio_shadow import portfolio_shadow
from core.sky_intelligence.types import DecisionAction, SetupType, SKYSetup


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean shadow portfolio state before and after each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


def test_classify_trading_style_all_archetypes():
    """Verifies that all 5 quantitative trading styles map to their designated institutional desk."""
    # 1. Scalp: VWAP Reclaim
    setup_scalp = MagicMock(spec=SKYSetup)
    setup_scalp.setup_type = SetupType.SETUP_E_VWAP_RECLAIM
    style, desk = classify_trading_style("BTC/USDT", setup_scalp, entry_price=70000.0, stop_loss=69500.0, timeframe="15m")
    assert style == "SCALP"
    assert desk == "BTC Desk (Scalp Specialist)"

    # 2. Day Trading: Sweep + MSS
    setup_day = MagicMock(spec=SKYSetup)
    setup_day.setup_type = SetupType.SETUP_A_SWEEP_MSS
    style, desk = classify_trading_style("BTC/USDT", setup_day, entry_price=70000.0, stop_loss=69000.0, timeframe="15m")
    assert style == "DAY"
    assert desk == "BTC Desk (Intraday SMC)"

    # 3. Trend Trading: Pullback + FVG & Breakout + Expansion
    setup_trend_fvg = MagicMock(spec=SKYSetup)
    setup_trend_fvg.setup_type = SetupType.SETUP_B_PULLBACK_FVG
    style, desk = classify_trading_style("BTC/USDT", setup_trend_fvg, entry_price=70000.0, stop_loss=68500.0, timeframe="15m")
    assert style == "TREND"
    assert desk == "BTC Desk (Trend Hunter)"

    setup_trend_bo = MagicMock(spec=SKYSetup)
    setup_trend_bo.setup_type = SetupType.SETUP_C_BREAKOUT_EXPANSION
    style, desk = classify_trading_style("ETH/USDT", setup_trend_bo, entry_price=2500.0, stop_loss=2450.0, timeframe="15m")
    assert style == "TREND"
    assert desk == "ETH Desk (Trend Hunter)"

    # 4. Range Trading: Range Sweep & Reclaim
    setup_range = MagicMock(spec=SKYSetup)
    setup_range.setup_type = SetupType.SETUP_D_RANGE_SWEEP_RECLAIM
    style, desk = classify_trading_style("SOL/USDT", setup_range, entry_price=150.0, stop_loss=147.0, timeframe="15m")
    assert style == "RANGE"
    assert desk == "SOL Desk (Range Specialist)"

    # 5. Swing Trading: HTF (4h) or wide stop distance (>= 3.5%)
    style_htf, desk_htf = classify_trading_style("BTC/USDT", setup_day, entry_price=70000.0, stop_loss=69000.0, timeframe="4h")
    assert style_htf == "SWING"
    assert desk_htf == "BTC Desk (Macro Swing)"

    style_wide_sl, desk_wide_sl = classify_trading_style("BTC/USDT", None, entry_price=70000.0, stop_loss=67000.0, timeframe="15m")
    assert style_wide_sl == "SWING"
    assert desk_wide_sl == "BTC Desk (Macro Swing)"


def test_anti_cannibalization_guard_rejects_opposing_positions():
    """Invariant: Opposing positions (LONG vs SHORT) on the same asset are strictly blocked."""
    # Open initial LONG position on BTC
    pos1 = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.1,
        entry_price=70000.0,
        stop_loss=69000.0,
        take_profit=73000.0,
        entry_reason="[BTC_DAY] Sweep + MSS (LONG)",
        style_tag="[BTC_DAY]",
        allow_multi_style=True,
    )
    assert pos1.startswith("POS_BTC_USDT")

    # Attempt to open opposing SHORT position on BTC -> MUST FAIL-CLOSED
    with pytest.raises(ValueError, match="Cannibalization detected"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="SHORT",
            size=0.1,
            entry_price=70000.0,
            stop_loss=71000.0,
            take_profit=68000.0,
            entry_reason="[BTC_SCALP] VWAP Deviation (SHORT)",
            style_tag="[BTC_SCALP]",
            allow_multi_style=True,
        )


def test_multi_style_same_direction_concurrent_execution():
    """Invariant: Multiple distinct trading styles in the same direction can safely co-exist."""
    # 1. Open Swing Long on BTC
    pos_swing = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=70000.0,
        stop_loss=67000.0,
        take_profit=78000.0,
        entry_reason="[BTC_SWING] Macro Structural Expansion (LONG)",
        style_tag="[BTC_SWING]",
        prevent_duplicate_symbol=True,
        allow_multi_style=True,
    )

    # 2. Open Scalp Long on BTC (same direction, different style)
    pos_scalp = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.02,
        entry_price=70500.0,
        stop_loss=70100.0,
        take_profit=71200.0,
        entry_reason="[BTC_SCALP] VWAP Reclaim (LONG)",
        style_tag="[BTC_SCALP]",
        prevent_duplicate_symbol=True,
        allow_multi_style=True,
    )

    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 2
    ids = {p["position_id"] for p in open_pos}
    assert pos_swing in ids
    assert pos_scalp in ids


def test_same_style_duplicate_sub_book_rejection():
    """Invariant: Two trades of the exact same style on the same asset are blocked as duplicates."""
    # Open first Scalp
    portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.02,
        entry_price=70000.0,
        stop_loss=69700.0,
        take_profit=70500.0,
        entry_reason="[BTC_SCALP] VWAP Reclaim (LONG)",
        style_tag="[BTC_SCALP]",
        prevent_duplicate_symbol=True,
        allow_multi_style=True,
    )

    # Attempt to open second Scalp on BTC
    with pytest.raises(ValueError, match="already exists"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.02,
            entry_price=70100.0,
            stop_loss=69800.0,
            take_profit=70600.0,
            entry_reason="[BTC_SCALP] VWAP Reclaim 2 (LONG)",
            style_tag="[BTC_SCALP]",
            prevent_duplicate_symbol=True,
            allow_multi_style=True,
        )


def test_cumulative_asset_risk_cap_enforcement():
    """Invariant: Combined risk across active styles on one asset cannot exceed max_risk_usd."""
    # Max risk allowed on BTC: $150.00
    max_cap = 150.0

    # Trade 1 risk: 0.1 * (70000 - 69000) = $100.00
    portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.1,
        entry_price=70000.0,
        stop_loss=69000.0,
        take_profit=73000.0,
        entry_reason="[BTC_DAY] Setup A (LONG)",
        style_tag="[BTC_DAY]",
        enforce_atomic_limits=True,
        max_risk_usd=max_cap,
        prevent_duplicate_symbol=True,
        allow_multi_style=True,
    )

    # Trade 2 risk: 0.1 * (70000 - 69400) = $60.00 -> Total risk would be $160.00 > $150.00
    with pytest.raises(ValueError, match="cumulative BTC/USDT risk"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.1,
            entry_price=70000.0,
            stop_loss=69400.0,
            take_profit=71000.0,
            entry_reason="[BTC_SCALP] Setup E (LONG)",
            style_tag="[BTC_SCALP]",
            enforce_atomic_limits=True,
            max_risk_usd=max_cap,
            prevent_duplicate_symbol=True,
            allow_multi_style=True,
        )


@pytest.mark.asyncio
async def test_paper_routes_desk_overview_formatting():
    """Verifies that paper_routes correctly formats positions into institutional desks."""
    from unittest.mock import patch
    from core.execution.paper_routes import get_paper_positions

    # Open a multi-style position
    portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=0.05,
        entry_price=70000.0,
        stop_loss=69500.0,
        take_profit=71500.0,
        entry_reason="[BTC_SCALP] VWAP Mean Reversion (LONG)",
        style_tag="[BTC_SCALP]",
        allow_multi_style=True,
    )

    with patch("core.execution.paper_routes.portfolio_shadow.get_portfolio_accounting", return_value={"portfolio_equity": 10000.0}):
        result = await get_paper_positions()
        positions = result["positions"]
        assert len(positions) == 1
        pos = positions[0]
        assert pos["horizon"] == "SCALP"
        assert pos["agentManager"] == "BTC Desk (Scalp Specialist)"
        assert pos["strategyName"] == "BTC Scalp Execution"

