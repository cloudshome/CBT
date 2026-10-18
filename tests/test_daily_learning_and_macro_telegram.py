"""
Test Suite for Daily Learning Reporter, Macro Event Sentinel,
Bangladesh Time Aligned Briefings, and Telegram Command Handlers.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from core.daily_learning_reporter import daily_learning_reporter
from core.macro_event_reporter import MacroEventRelease, macro_event_reporter
from core.telegram.commands import command_registry
from core.telegram.handlers import (
    handle_learned,
    handle_macro,
    handle_schedule,
    register_all_v5_commands,
)
from core.telegram_bot import BD_TZ, SmartBrainNotificationEngine


@pytest.fixture(autouse=True)
def setup_commands():
    register_all_v5_commands()
    macro_event_reporter._ensure_table_exists()
    macro_event_reporter._seed_default_macro_releases()


# ==============================================================================
# 1. DAILY LEARNING REPORTER TESTS
# ==============================================================================


def test_generate_what_ai_learned_today_report():
    """Verifies that the daily learning report compiles multi-source research into an institutional dossier."""
    report = daily_learning_reporter.generate_what_ai_learned_today_report(lookback_hours=48)
    assert isinstance(report, str)
    assert "WHAT AI LEARNED TODAY" in report
    assert "BANGLADESH TIME" in report or "BD Time" in report
    assert "RESEARCH LITERATURE & MEDIA PROVENANCE" in report
    assert "YOUTUBE V5 AUTONOMOUS RESEARCH DECONSTRUCTION" in report
    assert "KEY EXTRACTED CONCEPTS & SYSTEMIC CLAIMS" in report
    assert "CONTRADICTIONS & FALSIFICATION RADAR" in report
    assert "TODAY'S PAPER DESK PERFORMANCE" in report
    assert "INSTITUTIONAL QUANTITATIVE SYNTHESIS" in report


def test_daily_learning_reporter_metrics_computation():
    """Verifies computation of learning delta metrics."""
    metrics = daily_learning_reporter.get_daily_learning_metrics(lookback_hours=72)
    assert "new_sources_count" in metrics
    assert "new_claims_count" in metrics
    assert "new_concepts_count" in metrics
    assert "youtube_videos_count" in metrics
    assert "paper_trades_count" in metrics
    assert "lookback_hours" in metrics


# ==============================================================================
# 2. MACRO EVENT REPORTER TESTS
# ==============================================================================


def test_macro_event_reporter_dovish_cpi():
    """Verifies macro flash formatting when CPI comes in cooler than expected (dovish/bullish crypto)."""
    event = MacroEventRelease(
        event_id="TEST_CPI_DOVISH",
        event_name="US Consumer Price Index (CPI YoY)",
        currency="USD",
        release_time_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        actual=2.9,
        forecast=3.1,
        previous=3.2,
        unit="%",
        impact_tier="HIGH",
    )
    report = macro_event_reporter.format_event_flash_report(event)
    assert "MACRO CATALYST FLASH" in report
    assert "US Consumer Price Index (CPI YoY)" in report
    assert "**Actual:** `2.9%`" in report
    assert "**Forecast:** `3.1%`" in report
    assert "COOLER THAN EXPECTED" in report or "DOVISH" in report
    assert "Price Displacement:" in report
    assert "IV Crush (Implied Volatility):" in report
    assert "Fair Value Gap (FVG) Liquidity Zone:" in report
    assert "Desk Directives & Kelly Allocation:" in report


def test_macro_event_reporter_hawkish_cpi():
    """Verifies macro flash formatting when CPI comes in hotter than expected (hawkish/bearish crypto)."""
    event = MacroEventRelease(
        event_id="TEST_CPI_HAWKISH",
        event_name="US Core CPI (MoM)",
        currency="USD",
        release_time_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        actual=0.4,
        forecast=0.2,
        previous=0.2,
        unit="%",
        impact_tier="HIGH",
    )
    report = macro_event_reporter.format_event_flash_report(event)
    assert "HOTTER THAN EXPECTED" in report or "HAWKISH" in report
    assert "**Actual:** `0.4%`" in report
    assert "**Forecast:** `0.2%`" in report


def test_macro_event_record_and_query():
    """Verifies SQLite persistence of macro event releases."""
    unique_id = f"TEST_RECORD_{int(datetime.datetime.now().timestamp())}"
    macro_event_reporter.record_release(
        event_id=unique_id,
        event_name="FOMC Interest Rate Decision",
        release_time_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        actual=5.25,
        forecast=5.25,
        previous=5.50,
        unit="%",
        impact_tier="CRITICAL",
        currency="USD",
    )
    recent = macro_event_reporter.get_recent_releases(limit=10)
    found = any(r["event_id"] == unique_id for r in recent)
    assert found is True


def test_macro_event_pending_and_marking():
    """Verifies checking pending releases and marking them dispatched to prevent duplicate alerts."""
    unique_id = f"TEST_PENDING_{int(datetime.datetime.now().timestamp())}"
    macro_event_reporter.record_release(
        event_id=unique_id,
        event_name="US Non-Farm Payrolls (NFP)",
        release_time_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        actual=142.0,
        forecast=165.0,
        previous=114.0,
        unit="K",
        impact_tier="HIGH",
        currency="USD",
    )
    pending = macro_event_reporter.check_and_generate_pending_releases()
    matching = [p for p in pending if p["event_id"] == unique_id]
    assert len(matching) == 1

    # Mark as notified
    macro_event_reporter.mark_notified(unique_id)
    pending_after = macro_event_reporter.check_and_generate_pending_releases()
    matching_after = [p for p in pending_after if p["event_id"] == unique_id]
    assert len(matching_after) == 0


# ==============================================================================
# 3. BANGLADESH TIME BRIEFING SCHEDULING TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_smart_notifier_bd_time_briefings():
    """Verifies that SmartBrainNotificationEngine fires briefings strictly according to BD Time (BST = UTC+6)."""
    mock_bot = AsyncMock()
    notifier = SmartBrainNotificationEngine(mock_bot)
    notifier.bot.send_morning_briefing = AsyncMock(return_value=True)
    notifier.bot.send_midday_pulse = AsyncMock(return_value=True)
    notifier.bot.send_us_session_watch = AsyncMock(return_value=True)
    notifier.bot.send_what_ai_learned_today = AsyncMock(return_value=True)

    # 1. Simulate 08:00 AM BD Time (02:00 UTC)
    mock_0800_bd = datetime.datetime(2026, 9, 13, 8, 5, 0, tzinfo=BD_TZ)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            mock_0800_bd if tz == BD_TZ else mock_0800_bd.astimezone(datetime.UTC)
        )
        await notifier.check_scheduled_briefings()
        notifier.bot.send_morning_briefing.assert_called_once()
        assert notifier._last_morning_date == "2026-09-13"

    # 2. Simulate 02:00 PM BD Time (08:00 UTC)
    mock_1400_bd = datetime.datetime(2026, 9, 13, 14, 2, 0, tzinfo=BD_TZ)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            mock_1400_bd if tz == BD_TZ else mock_1400_bd.astimezone(datetime.UTC)
        )
        await notifier.check_scheduled_briefings()
        notifier.bot.send_midday_pulse.assert_called_once()
        assert notifier._last_midday_date == "2026-09-13"

    # 3. Simulate 08:00 PM BD Time (14:00 UTC)
    mock_2000_bd = datetime.datetime(2026, 9, 13, 20, 10, 0, tzinfo=BD_TZ)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            mock_2000_bd if tz == BD_TZ else mock_2000_bd.astimezone(datetime.UTC)
        )
        await notifier.check_scheduled_briefings()
        notifier.bot.send_us_session_watch.assert_called_once()
        assert notifier._last_us_session_date == "2026-09-13"

    # 4. Simulate 10:00 PM BD Time (16:00 UTC)
    mock_2200_bd = datetime.datetime(2026, 9, 13, 22, 1, 0, tzinfo=BD_TZ)
    with patch("datetime.datetime") as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: (
            mock_2200_bd if tz == BD_TZ else mock_2200_bd.astimezone(datetime.UTC)
        )
        await notifier.check_scheduled_briefings()
        notifier.bot.send_what_ai_learned_today.assert_called_once()
        assert notifier._last_evening_date == "2026-09-13"


@pytest.mark.asyncio
async def test_macro_event_release_auto_dispatch():
    """Verifies that unnotified macro releases trigger an instant telegram dispatch."""
    mock_bot = AsyncMock()
    notifier = SmartBrainNotificationEngine(mock_bot)
    notifier.bot.send_message = AsyncMock(return_value=True)

    unique_event_id = f"CPI_AUTO_DISPATCH_{int(datetime.datetime.now().timestamp())}"
    macro_event_reporter.record_release(
        event_id=unique_event_id,
        event_name="US CPI YoY",
        release_time_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        actual=2.8,
        forecast=3.0,
        previous=3.1,
        unit="%",
        impact_tier="HIGH",
        currency="USD",
    )

    await notifier.check_macro_event_releases()
    notifier.bot.send_message.assert_called()
    assert f"MACRO_EVENT_RELEASE_{unique_event_id}" in notifier._notified_milestones


# ==============================================================================
# 4. TELEGRAM COMMAND HANDLERS TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_handle_learned():
    """Verifies /learned handler returns the full What AI Learned Today report."""
    res = await handle_learned("")
    assert "WHAT AI LEARNED TODAY" in res
    assert "RESEARCH LITERATURE & MEDIA PROVENANCE" in res


@pytest.mark.asyncio
async def test_handle_macro():
    """Verifies /macro handler returns a formatted macroeconomic impact report."""
    res = await handle_macro("CPI")
    assert "MACRO CATALYST FLASH" in res
    assert "Actual:" in res
    assert "Forecast:" in res


@pytest.mark.asyncio
async def test_handle_schedule():
    """Verifies /schedule handler returns Bangladesh time and 4 daily briefing windows."""
    res = await handle_schedule("")
    assert "BANGLADESH TIME (UTC+6)" in res
    assert "08:00 AM BST" in res
    assert "02:00 PM BST" in res
    assert "08:00 PM BST" in res
    assert "10:00 PM BST" in res
    assert "What AI Learned Today" in res


def test_command_registration_and_aliases():
    """Verifies that /learned, /macro, /schedule and their aliases are properly registered."""
    assert command_registry.get("/learned") is not None
    assert command_registry.get("/daily") is not None
    assert command_registry.get("/macro") is not None
    assert command_registry.get("/cpi") is not None
    assert command_registry.get("/schedule") is not None
    assert command_registry.get("/sessions") is not None
    assert command_registry.get("/bdtime") is not None


def test_unreleased_pending_event_never_dispatched_and_no_mock_prices():
    """
    Verifies that unreleased / upcoming catalysts (actual='TBD')
    maintain released_timestamp_ms=None, zero price displacements,
    and are NEVER dispatched by check_and_generate_pending_releases.
    """
    import time

    from core.macro_event_reporter import MacroReleaseRecord, macro_event_reporter

    pending_rec = MacroReleaseRecord(
        event_id="TEST_PENDING_CATALYST_ISOLATION",
        title="FOMC Interest Rate Decision (Pending)",
        country="US",
        category="CENTRAL_BANK",
        scheduled_timestamp_ms=int(time.time() * 1000) + 3600000,
        released_timestamp_ms=None,
        actual="TBD",
        forecast="5.25%",
        previous="5.50%",
        actual_num=None,
        forecast_num=5.25,
        previous_num=5.50,
        surprise_direction="PENDING",
        btc_price_before=0.0,
        btc_price_after=0.0,
        is_dispatched=False,
    )

    assert pending_rec.released_timestamp_ms is None
    assert pending_rec.btc_price_before == 0.0
    assert pending_rec.btc_price_after == 0.0

    report = macro_event_reporter.format_event_flash_report(pending_rec)
    assert "PENDING OFFICIAL RELEASE" in report
    assert "IN-LINE WITH CONSENSUS" not in report

    pending_list = macro_event_reporter.check_and_generate_pending_releases()
    matching = [p for p in pending_list if p.get("event_id") == "TEST_PENDING_CATALYST_ISOLATION"]
    assert len(matching) == 0
