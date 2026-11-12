"""
tests/test_m41_bidirectional_entry_engine.py
=============================================
Verification suite for M41 Trading Intelligence & Bidirectional Entry Engine Upgrade:
1. Bidirectional style signals (both longPlan & shortPlan per style + recommendedSide).
2. SMC structural zone origin tags (BULLISH_OB_FVG, BEARISH_OB_FVG, VWAP_VAL_CONFLUENCE).
3. Orderflow CVD absorption & L2 imbalance state machine (IN_ZONE_CONFIRMED, AWAITING_RECLAIM).
4. Backtester parity & knife-catch protection with breakeven stop after TP1.
5. Actionable Entry Radar endpoint & composite scoring (/api/screener/actionable-entries).
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from core.intelligence.forward_validation.orderbook_tracker import (
    FeedQualityState,
    MarketEventTimestamps,
    OrderBookLevel,
    OrderBookSnapshot,
)
from core.intelligence.forward_validation.paper_fill_simulator import (
    OrderSide,
    RealisticPaperFillSimulator,
)
from core.prediction_ladder import (
    compute_bidirectional_style_signals,
    evaluate_ladder_tick,
)
from core.screener.opportunity_hunter import opportunity_hunter
from data.backtester import _evaluate


def test_bidirectional_style_signal_generation():
    """Verify both longPlan and shortPlan are computed for all 5 horizons."""
    signals = compute_bidirectional_style_signals(
        symbol="BTCUSDT",
        cur_p=68500.0,
        high_50=70000.0,
        low_50=67000.0,
        cvd_score=0.15,
        obi_score=0.10,
        is_bull_regime=True,
    )

    assert len(signals) == 5
    styles = [s["style"] for s in signals]
    assert styles == ["SCALP", "DAY", "SWING", "MOMENTUM", "POSITION"]

    for sig in signals:
        assert sig["recommendedSide"] in ("LONG", "SHORT")
        assert "longPlan" in sig and sig["longPlan"] is not None
        assert "shortPlan" in sig and sig["shortPlan"] is not None
        assert sig["longPlan"]["side"] == "LONG"
        assert sig["shortPlan"]["side"] == "SHORT"
        assert sig["longPlan"]["tp1"] > sig["longPlan"]["entryZone"][0]
        assert sig["shortPlan"]["tp1"] < sig["shortPlan"]["entryZone"][0]
        assert "zoneOrigin" in sig["longPlan"]
        assert "zoneOrigin" in sig["shortPlan"]
        assert "entryTriggerState" in sig["longPlan"]


def test_force_side_toggle():
    """Verify force_side query parameter switches primary plan orientation."""
    long_view = compute_bidirectional_style_signals(
        symbol="ETHUSDT",
        cur_p=2500.0,
        high_50=2600.0,
        low_50=2400.0,
        force_side="LONG",
    )
    assert long_view[0]["side"] == "LONG"

    short_view = compute_bidirectional_style_signals(
        symbol="ETHUSDT",
        cur_p=2500.0,
        high_50=2600.0,
        low_50=2400.0,
        force_side="SHORT",
    )
    assert short_view[0]["side"] == "SHORT"
    assert short_view[0]["stopLoss"] > short_view[0]["entryZone"][1]


def test_ladder_tick_knife_catch_prevention():
    """Verify a violent candle drop below entry zone triggers AWAITING_RECLAIM."""
    plan = {
        "side": "LONG",
        "entryZone": [68000.0, 68200.0],
        "stopLoss": 67000.0,
        "invalidationPrice": 66800.0,
        "tp1": 69500.0,
        "tp2": 71000.0,
        "tp3": 74000.0,
    }

    # Candle opens at 68500, dumps through entry zone to 67500, closes at 67600
    res = evaluate_ladder_tick(
        plan=plan,
        bar_open=68500.0,
        bar_high=68500.0,
        bar_low=67500.0,
        bar_close=67600.0,
        cvd_score=-0.2,
    )
    assert res.state == "AWAITING_RECLAIM"
    assert res.fill_allowed is False
    assert "below entry zone" in res.note.lower()


def test_ladder_tick_in_zone_confirmed():
    """Verify candle rejecting entry zone with positive CVD triggers IN_ZONE_CONFIRMED."""
    plan = {
        "side": "LONG",
        "entryZone": [68000.0, 68200.0],
        "stopLoss": 67000.0,
        "invalidationPrice": 66800.0,
        "tp1": 69500.0,
        "tp2": 71000.0,
        "tp3": 74000.0,
    }

    # Candle wicks into entry zone (68100), closes at 68150 with positive CVD absorption
    res = evaluate_ladder_tick(
        plan=plan,
        bar_open=68100.0,
        bar_high=68200.0,
        bar_low=68050.0,
        bar_close=68180.0,
        cvd_score=0.15,
    )
    assert res.state == "IN_ZONE_CONFIRMED"
    assert res.fill_allowed is True
    assert res.rejection_confirmed is True


def test_backtester_knife_catch_avoidance_with_ladder_parity():
    """
    Backtester parity test: A knife-catch candle that plunges through entry directly
    into stop loss must NOT fill when ladder_parity is enabled.
    """
    # 3-bar series:
    # Bar 0: baseline 70000
    # Bar 1: flush 70000 -> 66000 (breaches entry 68000 and hits SL 67000 on close 66500)
    df = pd.DataFrame(
        [
            {"ts": 0, "open": 70000.0, "high": 70000.0, "low": 70000.0, "close": 70000.0},
            {"ts": 900_000, "open": 69500.0, "high": 69500.0, "low": 66000.0, "close": 66200.0},
        ]
    )
    df.attrs["timeframe"] = "15m"

    plan = {
        "type": "SMC Demand Retest",
        "action": "BUY",
        "entry": 68000.0,
        "entryZone": [67900.0, 68100.0],
        "stop_loss": 67000.0,
        "take_profits": [70000.0, 72000.0],
        "status": "waiting",
        "ladder_parity": True,
    }

    gp = _evaluate(plan, df, i=0, horizon_bars=1, ladder_parity=True)
    # The knife-catch was prevented! The limit order was never filled before invalidation.
    assert gp.outcome == "NOT_TRIGGERED"


def test_backtester_breakeven_stop_after_tp1():
    """
    Backtester parity test: After hitting TP1, the stop must move to breakeven,
    preventing a subsequent market dump from becoming a full loss.
    """
    # Bar 0: Entry filled at 100
    # Bar 1: Rallies to 110 (hits TP1 108)
    # Bar 2: Dumps down to 90 (breaches original SL 95, but stop was moved to breakeven 100)
    df = pd.DataFrame(
        [
            {"ts": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            {"ts": 900_000, "open": 100.0, "high": 110.0, "low": 99.0, "close": 109.0},
            {"ts": 1_800_000, "open": 109.0, "high": 109.0, "low": 90.0, "close": 91.0},
        ]
    )
    df.attrs["timeframe"] = "15m"

    plan = {
        "type": "Immediate Buy",
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profits": [108.0, 116.0],
        "ladder_parity": True,
    }

    gp = _evaluate(plan, df, i=0, horizon_bars=2, ladder_parity=True)
    assert gp.outcome == "PARTIAL_WIN"
    assert gp.rr_achieved > 0.0


def test_paper_fill_simulator_ladder_knife_catch():
    """Verify paper fill simulator rejects limit fill on knife-catch when ladder plan attached."""
    sim = RealisticPaperFillSimulator()
    plan = {
        "side": "LONG",
        "entryZone": [68000.0, 68200.0],
        "stopLoss": 67000.0,
        "invalidationPrice": 66800.0,
        "tp1": 70000.0,
    }

    now = time.time()
    book = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[OrderBookLevel(price=68000.0, size=1.0)],
        asks=[OrderBookLevel(price=68010.0, size=1.0)],
        sequence_id=1,
        timestamps=MarketEventTimestamps.create(now),
        quality=FeedQualityState.HEALTHY,
    )

    sim.place_limit_order(
        admission_id="ADM-1",
        book=book,
        side=OrderSide.BUY,
        price=68000.0,
        quantity=0.5,
        plan=plan,
    )

    # Trade occurs at 67500 (below entry zone -> AWAITING_RECLAIM)
    fills = sim.process_trade_tick(
        symbol="BTCUSDT",
        venue="BINANCE",
        trade_price=67500.0,
        trade_size=5.0,
        tick_time_utc=1001.0,
    )
    # Fill must be withheld on knife catch!
    assert len(fills) == 0


@pytest.mark.asyncio
async def test_actionable_entries_radar_scoring():
    """Verify /api/screener/actionable-entries ranking and composite scoring."""
    entries = await opportunity_hunter.get_actionable_entries(
        min_score=0.0,
        include_quarantined=True,
    )
    assert len(entries) > 0

    top_entry = entries[0]
    assert "symbol" in top_entry
    assert "side" in top_entry
    assert "entryZone" in top_entry
    assert "entryReadinessScore" in top_entry
    assert "readinessGrade" in top_entry
    assert "orderflowAlignment" in top_entry
    assert "oosValidated" in top_entry
    assert top_entry["entryReadinessScore"] >= 0.0
    assert top_entry["entryReadinessScore"] <= 100.0

    # Verify descending sort order
    scores = [e["entryReadinessScore"] for e in entries]
    assert scores == sorted(scores, reverse=True)
