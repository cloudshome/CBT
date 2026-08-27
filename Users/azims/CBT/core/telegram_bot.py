"""
Telegram Desk Intelligence Copilot & Alert Dispatcher.
Sends real-time event shock alerts, trailing stop notifications, daily morning briefings,
and interactive parameter hot-patch approval requests via Telegram.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
import aiohttp

logger = logging.getLogger("ai_quant_sentinel.telegram_bot")


class TelegramBotDispatcher:
    """Dispatches quantitative signals and briefings to Telegram channels."""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.bot_token or not self.chat_id:
            logger.debug("Telegram credentials not configured; logging message locally.")
            logger.info(f"[TELEGRAM NOTIFICATION]\n{text}")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram dispatch failed: {e}")
            return False

    async def send_morning_briefing(self, briefing_text: str) -> bool:
        header = "🌅 **08:00 AM Institutional Morning Desk Briefing**\n\n"
        return await self.send_message(header + briefing_text)

    async def send_evening_review(self, review_text: str) -> bool:
        header = "🌃 **10:00 PM Daily Performance Review & Loss Autopsy**\n\n"
        return await self.send_message(header + review_text)


# Singleton
telegram_bot = TelegramBotDispatcher()
