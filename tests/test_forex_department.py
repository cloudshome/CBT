"""
Unit & Property Tests for CBT Forex & Macro-Metals Trading Department.
Validates session clock, weekend closure, lot calculations, notional leverage capping, and economic lockouts.
"""

from __future__ import annotations

import datetime

from core.forex.economic_calendar import EconomicCalendarFilter
from core.forex.lot_calculator import ForexLotCalculator
from core.forex.service import ForexDepartmentService
from core.forex.session_clock import ForexSessionClock
from core.forex.types import (
    EconomicEvent,
    EconomicImpact,
    ForexSession,
)


class TestForexSessionClock:
    def test_weekend_market_close(self):
        # Saturday 12:00 UTC
        sat = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.UTC)
        st = ForexSessionClock.get_status(sat)
        assert not st.is_market_open
        assert ForexSession.WEEKEND_CLOSED in st.active_sessions
        assert st.liquidity_multiplier == 0.0

    def test_london_ny_overlap_peak_liquidity(self):
        # Wednesday 14:00 UTC (London + NY overlap, NY Open Killzone)
        wed = datetime.datetime(2026, 10, 14, 14, 0, 0, tzinfo=datetime.UTC)
        st = ForexSessionClock.get_status(wed)
        assert st.is_market_open
        assert ForexSession.LONDON in st.active_sessions
        assert ForexSession.NEW_YORK in st.active_sessions
        assert ForexSession.LONDON_NY_OVERLAP in st.active_sessions
        assert st.is_killzone_active
        assert st.killzone_name == "New York Open Killzone"
        assert st.liquidity_multiplier == 2.0

    def test_asian_session(self):
        # Tuesday 02:00 UTC
        tue = datetime.datetime(2026, 10, 13, 2, 0, 0, tzinfo=datetime.UTC)
        st = ForexSessionClock.get_status(tue)
        assert st.is_market_open
        assert ForexSession.ASIAN in st.active_sessions
        assert ForexSession.LONDON not in st.active_sessions


class TestForexLotCalculator:
    def test_eur_usd_standard_lot_calculation(self):
        calc = ForexLotCalculator(max_notional_leverage=3.0, max_risk_pct=0.015)
        # $10,000 Equity, 1.5% Risk = $150
        # Entry 1.0850, SL 1.0820 -> 30 pips distance
        # Pip value per standard lot = 100,000 * 0.0001 = $10 / pip
        # Risk per lot = 30 * $10 = $300
        # Desired lots = 150 / 300 = 0.50 lots
        # Notional = 0.50 * 100,000 * 1.0850 = $54,250 (5.42x leverage)
        # Should be clipped by max_notional_leverage (3.0x -> max $30,000 notional -> ~0.27 lots)
        res = calc.calculate_lot_size(
            symbol="EUR/USD",
            account_equity_usd=10_000.0,
            entry_price=1.0850,
            stop_loss_price=1.0820,
            target_risk_pct=0.015,
        )
        assert res.risk_passed
        assert res.pip_distance == 30.0
        assert res.raw_lots == 0.5
        assert res.clipped_lots < 0.5
        assert res.notional_usd <= 30_000.0
        assert res.notional_to_equity_leverage <= 3.0
        assert res.rejection_reason == "NOTIONAL_LEVERAGE_CAPPED"

    def test_gold_xau_usd_lot_calculation(self):
        calc = ForexLotCalculator(max_notional_leverage=3.0, max_risk_pct=0.015)
        # $10,000 Equity, Risk = $150
        # Entry $2,650.00, SL $2,645.00 -> $5.00 distance (500 points)
        # 1 lot = 100 oz. $5 distance per oz = $500 risk per standard lot.
        # Desired lots = 150 / 500 = 0.30 lots.
        # Notional = 0.30 * 100 oz * 2650 = $79,500 (7.95x leverage).
        # Capped to 3.0x ($30,000) -> 30,000 / (100 * 2650) = 0.11 lots.
        res = calc.calculate_lot_size(
            symbol="XAU/USD",
            account_equity_usd=10_000.0,
            entry_price=2650.0,
            stop_loss_price=2645.0,
            target_risk_pct=0.015,
        )
        assert res.risk_passed
        assert res.raw_lots == 0.3
        assert res.clipped_lots <= 0.12
        assert res.notional_usd <= 30_000.0
        assert res.notional_to_equity_leverage <= 3.0

    def test_invalid_price_zero_sl_fails_closed(self):
        calc = ForexLotCalculator()
        res = calc.calculate_lot_size(
            symbol="EUR/USD",
            account_equity_usd=10_000.0,
            entry_price=1.0850,
            stop_loss_price=1.0850,  # Zero distance
        )
        assert not res.risk_passed
        assert res.clipped_lots == 0.0
        assert res.rejection_reason == "ZERO_STOP_LOSS_DISTANCE"


class TestEconomicCalendarFilter:
    def test_economic_event_lockout(self):
        ef = EconomicCalendarFilter(lockout_window_minutes=30.0)
        now_ms = 1_700_000_000_000
        # Register upcoming US Non-Farm Payrolls in 10 minutes
        event = EconomicEvent(
            event_id="NFP_2026",
            title="Non-Farm Payrolls",
            currency="USD",
            impact=EconomicImpact.CRITICAL,
            scheduled_utc_ms=now_ms + 10 * 60 * 1000,
        )
        ef.register_event(event)

        # EUR/USD should be locked out
        is_locked, reason, ev = ef.evaluate_lockout("EUR/USD", current_time_ms=now_ms)
        assert is_locked
        assert "Non-Farm Payrolls" in (reason or "")
        assert ev == event

        # GBP/JPY (no USD) should NOT be locked out
        is_locked_jpy, _, _ = ef.evaluate_lockout("GBP/JPY", current_time_ms=now_ms)
        assert not is_locked_jpy


class TestForexDepartmentService:
    def test_service_market_status(self):
        svc = ForexDepartmentService()
        status = svc.get_market_status()
        assert "utc_time" in status
        assert "EUR/USD" in status["supported_pairs"]
        assert "XAU/USD" in status["supported_pairs"]

    def test_service_evaluate_order_risk(self):
        svc = ForexDepartmentService()
        # Mock open weekday time:
        svc.session_clock.get_status = lambda *args, **kwargs: ForexSessionClock.get_status(
            datetime.datetime(2026, 10, 14, 13, 0, 0, tzinfo=datetime.UTC)
        )
        res = svc.evaluate_order_risk(
            symbol="EUR/USD",
            account_equity_usd=10_000.0,
            entry_price=1.0850,
            stop_loss_price=1.0800,
        )
        assert res["allowed"] is True
        assert res["sizing"]["recommended_lots"] > 0
        assert res["sizing"]["notional_leverage"] <= 3.0
