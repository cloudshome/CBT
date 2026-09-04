"""
Tests for Layer 3: CVD Absorption, Lead-Lag Correlator, Judas Swings & Event Shock Risk.
"""

import time

from core.cvd_absorption import cvd_absorption_engine
from core.data_streamer import data_streamer
from core.event_shock_engine import MacroEvent, event_shock_engine
from core.lead_lag_correlator import lead_lag_correlator
from core.macro_sentinel import macro_sentinel


def test_cvd_absorption_calculation():
    """Verify Cumulative Volume Delta and absorption detection."""
    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
    res = cvd_absorption_engine.analyze_orderflow(candles, "BTC/USDT")
    assert -1.0 <= res.cvd_delta <= 1.0
    assert 0.0 <= res.absorption_score <= 1.0
    assert res.volume_ratio > 0


def test_lead_lag_macro_shocks():
    """Verify Lead-Lag Correlator triggers lead signals on DXY/Yield velocity shocks."""
    lead_lag_correlator.shock_threshold = 0.1
    signals = lead_lag_correlator.process_macro_ticks(dxy_price=110.0, us10y_yield=4.85)
    assert len(signals) >= 1
    assert any(s.target_asset in ["XAU/USD", "BTC/USDT"] for s in signals)
    lead_lag_correlator.shock_threshold = 2.0


def test_event_shock_risk_switcher():
    """Verify EVENT_RISK_MODE activates within 60 mins of high-impact releases."""
    now = int(time.time() * 1000)
    # Add an event scheduled 25 minutes in future
    event = MacroEvent(
        event_id="TEST_CPI",
        title="US CPI Inflation Release",
        impact="CRITICAL",
        scheduled_timestamp_ms=now + (25 * 60 * 1000),
    )
    event_shock_engine.add_event(event)

    state = event_shock_engine.evaluate_risk_state(now)
    assert state.is_event_risk_active
    assert state.ev_hurdle_multiplier == 1.50
    assert state.position_size_multiplier == 0.50
    assert state.mode_name == "EVENT_RISK_MODE"


def test_macro_sentinel_snapshot():
    """Verify global macro vital aggregator."""
    snap = macro_sentinel.get_macro_snapshot()
    assert 0.0 <= snap.global_risk_index <= 100.0
    assert snap.macro_regime in [
        "RISK_ON_EXPANSION",
        "RISK_OFF_FLIGHT_TO_SAFETY",
        "DOLLAR_SQUEEZE",
        "NEUTRAL",
    ]
