"""
Unit tests for Audit Bus, Macro Gold Engine, and Automated Post-Trade Autopsy Pipeline.
"""

import datetime
import pytest
from fastapi.testclient import TestClient

from app import app
from core.audit_bus import AuditBus, audit_bus
from core.macro_gold_engine import GoldMacroRegime, MacroGoldEngine, macro_gold_engine
from core.portfolio_shadow import portfolio_shadow


@pytest.fixture
def client():
    return TestClient(app)


def test_audit_bus_event_emission_and_retrieval():
    bus = AuditBus()
    ev = bus.emit_event(
        event_type="SIGNAL_REJECTED",
        symbol="BTC/USDT",
        reason="Risk limit exceeded: Portfolio heat > 6.0%",
        severity="WARNING",
        details={"risk_pct": 6.4, "max_allowed": 6.0},
    )
    assert ev.event_id.startswith("AUD-")
    assert ev.severity == "WARNING"
    assert ev.symbol == "BTC/USDT"

    # Retrieve events
    events = bus.get_recent_events(limit=10, event_type="SIGNAL_REJECTED")
    assert len(events) >= 1
    assert any(e.event_id == ev.event_id for e in events)


def test_macro_gold_engine_telemetry():
    engine = MacroGoldEngine()
    # Test during London AM Fix (10:30 UTC)
    dt_london_am = datetime.datetime(2026, 8, 29, 10, 30, tzinfo=datetime.timezone.utc)
    telem = engine.evaluate_macro_state(
        gold_price=2650.0,
        paxg_price=2652.5,
        dxy=103.5,
        real_yield_10y=1.85,
        utc_datetime=dt_london_am,
    )
    assert telem.symbol == "XAU/USD"
    assert telem.current_gold_price == 2650.0
    assert telem.synthetic_paxg_basis_bps > 0
    assert telem.active_fixing_session == "LONDON_AM_FIX"
    assert telem.is_in_prime_fixing_window is True
    assert telem.dxy_rolling_correlation_30d < 0
    assert telem.real_yield_beta < 0


def test_macro_gold_regime_classification():
    engine = MacroGoldEngine()
    # Low yield + weak dollar -> Debasement acceleration
    telem_bull = engine.evaluate_macro_state(
        gold_price=2700.0,
        dxy=101.5,
        real_yield_10y=1.20,
    )
    assert telem_bull.macro_regime == GoldMacroRegime.DEBASEMENT_ACCELERATION
    assert telem_bull.macro_bias == "LONG_CONVICTION"

    # High yield + strong dollar -> Bearish real yields headwind
    telem_bear = engine.evaluate_macro_state(
        gold_price=2500.0,
        dxy=106.5,
        real_yield_10y=2.45,
    )
    assert telem_bear.macro_regime == GoldMacroRegime.MACRO_BEARISH_REAL_YIELDS
    assert telem_bear.macro_bias == "SHORT_DEFENSE"


def test_portfolio_shadow_loss_autopsy_integration():
    # 1. Open a shadow position
    pos_id = portfolio_shadow.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        size=1.0,
        entry_price=65000.0,
        stop_loss=64000.0,
        take_profit=68000.0,
    )
    assert pos_id.startswith("POS_")


    # 2. Close position at a loss
    closed = portfolio_shadow.close_position(pos_id, exit_price=63800.0)
    assert closed is True

    # 3. Verify Loss Autopsy Event in Audit Bus
    events = audit_bus.get_recent_events(limit=20, event_type="LOSS_AUTOPSY")
    assert len(events) >= 1
    loss_ev = next((e for e in events if e.details.get("position_id") == pos_id), None)
    assert loss_ev is not None
    assert "autopsy" in loss_ev.details
    assert loss_ev.details["autopsy"]["loss_category"] is not None


def test_api_macro_gold_and_audit_endpoints(client):
    # Test GET /api/macro/gold
    gold_res = client.get("/api/macro/gold?gold_price=2655.0&dxy=103.8&real_yield=1.75")
    assert gold_res.status_code == 200
    gold_data = gold_res.json()
    assert gold_data["symbol"] == "XAU/USD"
    assert "macro_regime" in gold_data
    assert "catalysts" in gold_data

    # Test GET /api/audit/events
    audit_res = client.get("/api/audit/events?limit=10")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert "events" in audit_data
    assert isinstance(audit_data["events"], list)
