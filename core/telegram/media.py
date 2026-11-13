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
            summary_msg = bot_dispatcher._format_research_summary_telegram(
                res, title_override=title
            )
            await bot_dispatcher.send_message(summary_msg, chat_id=chat_id)
            return res

        except Exception as e:
            logger.error(f"Error in async research ingestion: {e}")
            if job_id:
                job_manager.update_job(job_id, status="FAILED", error=str(e))
            await bot_dispatcher.send_message(f"⚠️ Research ingestion failed: {e}", chat_id=chat_id)
            return {"status": "FAILED", "error": str(e)}


    @staticmethod
    def inspect_chart_image(
        image_bytes: bytes,
        caption: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        """
        Lightweight native OCR & structural candlestick analyzer for chart screenshots.
        Extracts symbol, timeframe, price scale, and candlestick color bias without external cloud LLMs.
        """
        import re

        detected_sym = ""
        detected_tf = ""
        visual_bias = "NEUTRAL"
        ocr_text = ""

        # 1. Search caption & filename first
        combined_text = f"{caption} {filename}".strip()

        sym_map = {
            r"\b(btc|bitcoin|btcusdt|btcusd)\b": "BTC/USDT",
            r"\b(eth|ethereum|ethusdt|ethusd)\b": "ETH/USDT",
            r"\b(sol|solana|solusdt|solusd)\b": "SOL/USDT",
            r"\b(xau|gold|xauusd)\b": "XAU/USD",
            r"\b(bnb|bnbusdt)\b": "BNB/USDT",
            r"\b(ada|cardano)\b": "ADA/USDT",
            r"\b(doge|dogecoin)\b": "DOGE/USDT",
            r"\b(xrp|ripple)\b": "XRP/USDT",
        }
        for pat, sym in sym_map.items():
            if re.search(pat, combined_text, re.IGNORECASE):
                detected_sym = sym
                break

        tf_map = {
            r"\b(1m|1min|1-min)\b": "1m",
            r"\b(5m|5min|5-min)\b": "5m",
            r"\b(15m|15min|15-min)\b": "15m",
            r"\b(1h|60m|hourly|1-hour)\b": "1h",
            r"\b(4h|4-hour|240m)\b": "4h",
            r"\b(1d|daily|1-day)\b": "1d",
            r"\b(1w|weekly|1-week)\b": "1w",
            r"\b(1mo|monthly|1-month)\b": "1M",
        }
        for pat, tf in tf_map.items():
            if re.search(pat, combined_text, re.IGNORECASE):
                detected_tf = tf
                break

        # 2. Local OCR / header analysis via PIL and pytesseract (if available)
        try:
            import io
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size

            # Check if pytesseract is available
            try:
                import pytesseract

                # Crop top 22% of image where exchange/TradingView header sits
                header_crop = img.crop((0, 0, w, int(h * 0.22)))
                extracted = pytesseract.image_to_string(header_crop)
                if extracted:
                    ocr_text = extracted.strip()
                    for pat, sym in sym_map.items():
                        if not detected_sym and re.search(pat, extracted, re.IGNORECASE):
                            detected_sym = sym
                    for pat, tf in tf_map.items():
                        if not detected_tf and re.search(pat, extracted, re.IGNORECASE):
                            detected_tf = tf
            except Exception:
                pass

            # 3. Candlestick visual color distribution (RGB sampling in chart body)
            body_crop = img.crop((int(w * 0.1), int(h * 0.2), int(w * 0.9), int(h * 0.8))).convert("RGB")
            thumb = body_crop.resize((64, 64))
            pixels = thumb.getdata()
            green_count = 0
            red_count = 0
            for r, g, b in pixels:
                if g > r + 25 and g > b + 15:
                    green_count += 1
                elif r > g + 25 and r > b + 15:
                    red_count += 1

            if red_count > green_count * 1.3:
                visual_bias = "BEARISH"
            elif green_count > red_count * 1.3:
                visual_bias = "BULLISH"
            else:
                visual_bias = "NEUTRAL"

        except Exception as e:
            logger.debug(f"[TelegramMedia] Local image inspection error: {e}")

        final_sym = detected_sym or "BTC/USDT"
        final_tf = detected_tf or "15m"

        return {
            "symbol": final_sym,
            "timeframe": final_tf,
            "detected": bool(detected_sym or detected_tf),
            "visual_bias": visual_bias,
            "ocr_text": ocr_text,
            "caption": caption,
        }


telegram_media = TelegramMediaHandler()
