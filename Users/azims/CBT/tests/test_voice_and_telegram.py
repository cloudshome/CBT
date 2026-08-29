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
async def test_telegram_bot_local_logging():
    # Without credentials, logs locally and returns False
    sent = await telegram_bot.send_message("Test message")
    assert sent is False


@pytest.mark.asyncio
async def test_telegram_position_alert():
    alert_sent = await telegram_bot.send_position_alert(
        "TAKE_PROFIT_TRIGGERED",
        {"symbol": "BTC/USDT", "price": 89500.0, "pnl_usd": 1420.50}
    )
    assert alert_sent is False  # Safe offline fallback


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


def test_api_telegram_status_endpoint(client):
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "registered_commands" in data
    assert "/status" in data["registered_commands"]


def test_api_telegram_broadcast_endpoint(client):
    resp = client.post("/api/telegram/broadcast", json={"text": "Test broadcast from terminal"})
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


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
