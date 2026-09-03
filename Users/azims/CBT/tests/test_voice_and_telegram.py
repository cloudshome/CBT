"""
Unit & Integration Tests for Phase 16 (Voice Interface), Phase 17 (Telegram Bot),
and Continuous Empirical Accumulator.
"""

import base64
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app import app
from core.voice_interface import voice_interface
from core.telegram_bot import telegram_bot
from core.empirical_accumulator import empirical_accumulator


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# PHASE 16: VOICE INTERFACE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_voice_interface_transcription_bytes():
    sample_bytes = b"RIFF....WAVEfmt ...."
    transcript = await voice_interface.transcribe_audio_bytes(sample_bytes, "test.wav")
    assert transcript is not None
    assert len(transcript) > 0


@pytest.mark.asyncio
async def test_voice_interface_speech_synthesis(tmp_path):
    voice_interface.audio_dir = tmp_path
    out_file = await voice_interface.generate_speech("Testing desk intelligence", "test_brief.mp3")
    assert out_file.exists()
    assert out_file.stat().st_size > 0


def test_api_voice_transcribe_endpoint(client):
    audio_base64 = base64.b64encode(b"RIFFdummydata").decode("utf-8")
    resp = client.post("/api/voice/transcribe", json={"audio_base64": audio_base64, "filename": "memo.webm"})
    assert resp.status_code == 200
    data = resp.json()
    assert "transcript" in data
    assert "is_trade_command" in data
    assert "parsed_command" in data


def test_api_voice_synthesize_endpoint(client, tmp_path):
    voice_interface.audio_dir = tmp_path
    resp = client.post("/api/voice/synthesize", json={"text": "Market briefing for BTC", "filename": "test_brief.mp3"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"


# ==============================================================================
# PHASE 17: TELEGRAM BOT TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_telegram_bot_local_logging(monkeypatch):
    # Without credentials, logs locally and returns False
    monkeypatch.setattr(telegram_bot, "bot_token", "")
    monkeypatch.setattr(telegram_bot, "chat_id", "")
    sent = await telegram_bot.send_message("Test message")
    assert sent is False


@pytest.mark.asyncio
async def test_telegram_position_alert(monkeypatch):
    monkeypatch.setattr(telegram_bot, "bot_token", "")
    monkeypatch.setattr(telegram_bot, "chat_id", "")
    alert_sent = await telegram_bot.send_position_alert(
        "TAKE_PROFIT_TRIGGERED",
        {"symbol": "BTC/USDT", "price": 89500.0, "pnl_usd": 1420.50}
    )
    assert alert_sent is False  # Safe offline fallback


@pytest.mark.asyncio
async def test_telegram_intelligence_generators():
    sig = await telegram_bot.generate_live_signal("BTC/USDT")
    assert sig["symbol"] == "BTC/USDT"
    assert "entry_price" in sig
    assert "stop_loss" in sig
    assert "tp1" in sig

    m = await telegram_bot.generate_market_update()
    assert "btc_price" in m
    assert "gri" in m

    plan = await telegram_bot.generate_trading_plan("BTC/USDT")
    assert "pdh" in plan
    assert "bull_scenario" in plan

    ev = telegram_bot.generate_event_shock_status()
    assert "title" in ev
    assert "impact" in ev

    news = telegram_bot.generate_news_digest()
    assert len(news) > 0
    assert "headline" in news[0]


@pytest.mark.asyncio
async def test_telegram_webhook_command_routing():
    update = {
        "message": {
            "text": "/status",
            "chat": {"id": 12345678}
        }
    }
    res = await telegram_bot.handle_webhook_update(update)
    assert res["status"] == "EXECUTED"
    assert res["command"] == "/status"
    assert "SKY Terminal Operational" in res["response"]


@pytest.mark.asyncio
async def test_telegram_signal_command_routing():
    update = {
        "message": {
            "text": "/signal BTC",
            "chat": {"id": 12345678}
        }
    }
    res = await telegram_bot.handle_webhook_update(update)
    assert res["status"] == "EXECUTED"
    assert "QUANTITATIVE TRADE SIGNAL" in res["response"]


@pytest.mark.asyncio
async def test_desk_state_mind_paper_execution():
    from core.portfolio_shadow import portfolio_shadow

    # Reset positions for clean test
    portfolio_shadow.reset_all_positions()

    sig = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry_price": 89000.0,
        "stop_loss": 88000.0,
        "tp1": 91000.0,
        "kelly_allocation_pct": 2.0,
    }

    # 1. First execution should succeed
    res1 = telegram_bot.state_mind.auto_execute_paper_trade(sig)
    assert res1["status"] == "EXECUTED"
    assert "position_id" in res1
    assert res1["size"] > 0

    # 2. Immediate duplicate execution on same symbol should be safely skipped
    res2 = telegram_bot.state_mind.auto_execute_paper_trade(sig)
    assert res2["status"] == "SKIPPED"
    assert res2["position_id"] == res1["position_id"]

    # 3. Report should show the active trade
    report = telegram_bot.state_mind.get_positions_report()
    assert "BTC/USDT" in report
    assert "ACTIVE PAPER PRACTICE POSITIONS" in report

    # 4. Close the trade via symbol
    close_msg = telegram_bot.state_mind.close_position_by_symbol("BTC/USDT")
    assert "POSITION CLOSED FROM TELEGRAM" in close_msg


@pytest.mark.asyncio
async def test_telegram_debate_and_conversational_routing():
    # 1. Debate Council
    debate_res = await telegram_bot.handle_webhook_update({
        "message": {"text": "/debate BTC", "chat": {"id": 12345678}}
    })
    assert debate_res["status"] == "EXECUTED"
    assert "ADVERSARIAL DEBATE COUNCIL" in debate_res["response"]

    # 2. Conversational Natural Language Query (non-slash)
    chat_res = await telegram_bot.handle_webhook_update({
        "message": {"text": "What is our current market risk?", "chat": {"id": 12345678}}
    })
    assert chat_res["status"] == "AI_CONVERSATION_EXECUTED"
    assert len(chat_res["response"]) > 0


def test_api_telegram_status_endpoint(client):
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "registered_commands" in data
    assert "/status" in data["registered_commands"]
    assert "/signal" in data["registered_commands"]
    assert "/positions" in data["registered_commands"]
    assert "/debate" in data["registered_commands"]


def test_api_telegram_broadcast_endpoint(client):
    resp = client.post("/api/telegram/broadcast", json={"text": "Test broadcast from terminal"})
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_smart_brain_notification_engine():
    from core.telegram_bot import telegram_bot
    notifier = telegram_bot.smart_notifier

    # 1. Deduplication suppression check
    test_headline = "Whale accumulation reaches multi-year peak"
    assert not notifier.is_suppressed("test_alert", test_headline, cooldown_seconds=3600)
    # Immediate repeat of same content must be suppressed
    assert notifier.is_suppressed("test_alert", test_headline, cooldown_seconds=3600)

    # 2. Distant macro events (>60m away) must never produce unsolicited alerts
    initial_milestones = set(notifier._notified_milestones)
    await notifier.check_macro_milestones()
    # FOMC is >1000m away, so no new milestone should be added
    assert notifier._notified_milestones == initial_milestones

    # 3. Position alerts format correctly
    assert await telegram_bot.send_position_alert("BREAKEVEN_TRIGGERED", {"symbol": "BTC/USDT", "price": 89500.0})
    assert await telegram_bot.send_position_alert("TAKE_PROFIT_HIT", {"symbol": "BTC/USDT", "price": 91000.0, "pnl_usd": 150.0})




# ==============================================================================
# EMPIRICAL ACCUMULATOR TESTS
# ==============================================================================

def test_empirical_accumulator_store_and_retrieve(tmp_path):
    db_file = tmp_path / "test_experiments.db"
    acc = type(empirical_accumulator)(db_path=db_file, target_samples=5)
    
    # Store test samples
    acc.store_sample("BTC/USDT", "15m", "TRENDING_BULL", "SETUP_A_SWEEP_MSS", 2.5, 88000, 89500, 1000, 2000, 1500)
    acc.store_sample("BTC/USDT", "15m", "TRENDING_BULL", "SETUP_A_SWEEP_MSS", -1.0, 88000, 87500, 2000, 3000, -500)
    
    samples = acc.get_samples_for_regime("TRENDING_BULL", "SETUP_A_SWEEP_MSS")
    assert len(samples) == 2
    assert samples == [2.5, -1.0]

    report = acc.get_status_report("SETUP_A_SWEEP_MSS")
    assert report.total_samples_collected == 2
    assert report.regimes["TRENDING_BULL"].total_samples == 2
    assert report.regimes["TRENDING_BULL"].status_label == "INSUFFICIENT DATA"


def test_api_empirical_status_endpoint(client):
    resp = client.get("/api/lab/empirical-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_samples_collected" in data
    assert "regimes" in data
    assert "TRENDING_BULL" in data["regimes"]
