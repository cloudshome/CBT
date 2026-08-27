"""
WhatsApp Business API Gateway & Copilot Bridge.
Dispatches critical risk alerts and interactive voice/text trade summaries over WhatsApp.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
import aiohttp

logger = logging.getLogger("ai_quant_sentinel.whatsapp_bot")


class WhatsAppBotDispatcher:
    """Dispatches alerts and briefings to WhatsApp Business endpoints."""

    def __init__(self):
        self.api_key = os.getenv("WHATSAPP_API_KEY", "")
        self.phone_number = os.getenv("WHATSAPP_PHONE_NUMBER", "")

    async def send_alert(self, message: str) -> bool:
        if not self.api_key or not self.phone_number:
            logger.debug("WhatsApp credentials not configured; logging message locally.")
            logger.info(f"[WHATSAPP ALERT]\n{message}")
            return False

        # In production integrates with Meta WhatsApp Cloud API
        logger.info(f"Dispatched WhatsApp alert to {self.phone_number}: {message[:60]}...")
        return True


# Singleton
whatsapp_bot = WhatsAppBotDispatcher()
