"""
Telegram Desk Intelligence Copilot & Alert Dispatcher.
Sends real-time event shock alerts, trailing stop notifications, daily morning briefings,
and interactive parameter hot-patch approval requests via Telegram.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional
import aiohttp

logger = logging.getLogger("ai_quant_sentinel.telegram_bot")


class TelegramBotDispatcher:
    """Dispatches quantitative signals and briefings to Telegram channels and handles webhook commands."""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._command_handlers: Dict[str, Callable[..., Any]] = {}

    def register_command(self, command: str, handler: Callable[..., Any]) -> None:
        """Registers a command handler (e.g. '/status', '/decision')."""
        self._command_handlers[command.lower().strip()] = handler

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Dispatches text message to the configured Telegram chat."""
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

    async def send_position_alert(self, event_type: str, details: Dict[str, Any]) -> bool:
        """Dispatches an institutional position alert (TP/SL/Trailing Stop/Risk Violation)."""
        sym = details.get("symbol", "N/A")
        price = details.get("price", 0.0)
        pnl = details.get("pnl_usd", 0.0)
        pnl_sign = "+" if pnl >= 0 else ""

        emoji = "🎯" if "TP" in event_type else "🛑" if "SL" in event_type else "⚡"
        msg = (
            f"{emoji} **SKY DESK ALERT: {event_type}**\n"
            f"• **Asset:** `{sym}`\n"
            f"• **Fill Price:** `${price:,.2f}`\n"
            f"• **Realized PnL:** `{pnl_sign}${pnl:,.2f}`\n"
            f"• **Timestamp:** `Auto-Recorded in SQLite Audit Log`"
        )
        return await self.send_message(msg)

    async def send_morning_briefing(self, briefing_text: str) -> bool:
        header = "🌅 **08:00 AM Institutional Morning Desk Briefing**\n\n"
        return await self.send_message(header + briefing_text)

    async def send_evening_review(self, review_text: str) -> bool:
        header = "🌃 **10:00 PM Daily Performance Review & Loss Autopsy**\n\n"
        return await self.send_message(header + review_text)

    async def handle_webhook_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses an incoming Telegram update webhook object and routes to the registered command.
        """
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")

        if not text:
            return {"status": "IGNORED", "reason": "No text content"}

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in self._command_handlers:
            try:
                import asyncio
                handler = self._command_handlers[cmd]
                if asyncio.iscoroutinefunction(handler):
                    response_text = await handler(args, chat_id=chat_id)
                else:
                    response_text = handler(args, chat_id=chat_id)

                if response_text and str(chat_id) == str(self.chat_id):
                    await self.send_message(response_text)
                return {"status": "EXECUTED", "command": cmd, "response": response_text}
            except Exception as e:
                logger.error(f"Error handling Telegram command '{cmd}': {e}")
                return {"status": "ERROR", "command": cmd, "error": str(e)}

        default_reply = (
            f"🤖 **SKY Institutional Trading Terminal Bot**\n\n"
            f"Available Commands:\n"
            f"• `/status` — System health & drift metrics\n"
            f"• `/decision <symbol>` — Live 12-stage SKY decision\n"
            f"• `/brief` — Daily morning desk briefing\n"
            f"• `/risk` — Risk gate & exposure report\n"
            f"• `/approve <id>` — Sign-off on parameter governance patch"
        )
        if chat_id:
            await self.send_message(default_reply)
        return {"status": "HELP_RETURNED", "text": default_reply}


# Singleton
telegram_bot = TelegramBotDispatcher()
