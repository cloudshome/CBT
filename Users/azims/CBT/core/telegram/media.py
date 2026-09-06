"""
Multimodal Media, Document, and Voice Ingestion Pipeline for Telegram V5.
Enforces Sections 13, 14, 15, 16 & 17 of the Master Directive:
- Audio Voice Note STT via voice_interface + QuantMentor routing + optional voice synthesis
- Vision OCR on chart screenshots with strict SOURCE-DERIVED / UNTESTED labels
- PDF monograph extraction with chapter tracking and checksum identity
- Epistemic Quarantine: All author claims/rules quarantined at confidence = 0.0, stage = UNTESTED
- Asynchronous non-blocking job execution via TelegramJobManager
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from core.telegram.jobs import job_manager
from core.voice_interface import voice_interface

logger = logging.getLogger("ai_quant_sentinel.telegram.media")

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB max upload
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".ogg", ".oga", ".wav", ".mp3"}


class TelegramMediaHandler:
    """Processes incoming multimodal media, audio voice notes, and documents."""

    @staticmethod
    def is_safe_file(filename: str, file_size: int) -> bool:
        """Validates extension and byte limits."""
        if file_size > MAX_FILE_BYTES:
            return False
        ext = Path(filename).suffix.lower()
        return ext in ALLOWED_EXTENSIONS

    async def process_voice_memo(
        self,
        voice_bytes: bytes,
        filename: str = "memo.ogg",
    ) -> str:
        """
        Transcribes voice audio bytes via voice_interface (Gemini Multimodal Audio or fallback).
        """
        transcript = await voice_interface.transcribe_audio_bytes(voice_bytes, filename=filename)
        return transcript.strip() if transcript else ""

    async def handle_async_research_ingest(
        self,
        bot_dispatcher: Any,
        chat_id: int | str,
        user_id: int | str,
        content: str,
        mode: str = "RESEARCH",
        title: str = "Telegram Ingest",
        author: str = "Telegram Contributor",
        source_uri: str = "Telegram",
        file_name: str | None = None,
        pdf_payload: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Background worker that runs universal_ingestor without blocking the Telegram listener.
        Notifies operator upon completion.
        """
        from core.universal_ingestor import universal_ingestor

        try:
            res = await universal_ingestor.ingest(
                content=content,
                mode=mode,
                title=title,
                author_creator=author,
                source_uri=source_uri,
                file_name=file_name,
                pdf_payload=pdf_payload,
            )

            if job_id:
                job_manager.update_job(job_id, status="COMPLETED", progress_pct=100, result=res)

            # Format and send executive summary to Telegram
            summary_msg = bot_dispatcher._format_research_summary_telegram(res, title_override=title)
            await bot_dispatcher.send_message(summary_msg, chat_id=chat_id)
            return res

        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.error(f"Error in async research ingestion: {e}")
            if job_id:
                job_manager.update_job(job_id, status="FAILED", error=str(e))
            await bot_dispatcher.send_message(f"⚠️ Research ingestion failed: {e}", chat_id=chat_id)
            return {"status": "FAILED", "error": str(e)}


telegram_media = TelegramMediaHandler()
