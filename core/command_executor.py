"""
Natural Language Trade Parser & Interactive Order Bridge.
Translates unstructured text/voice trade commands into structured executions:
e.g. "Entered Gold Long at 2675, SL 2668, TP 2695, 0.5 lot"
or "Buy BTCUSDT entry 88000 sl 87200 tp 90500 size 0.15".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from core.portfolio_shadow import portfolio_shadow

logger = logging.getLogger("ai_quant_sentinel.command_executor")


@dataclass
class ParsedTradeCommand:
    raw_command: str
    is_valid_command: bool
    symbol: str
    direction: str  # "LONG", "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    size_units: float
    action_taken: str  # "SHADOW_POSITION_OPENED", "PARSING_FAILED"
    message: str


class CommandExecutor:
    """Parses natural speech/text into deterministic trade orders."""

    def parse_and_execute(self, command_text: str) -> ParsedTradeCommand:
        """
        Regex-based resilient extraction for multi-lingual trade inputs.
        """
        text = command_text.strip()
        text_lower = text.lower()

        # 1. Extract Direction
        if (
            "long" in text_lower
            or "buy" in text_lower
            or "kinlam" in text_lower
            or "entry long" in text_lower
        ):
            direction = "LONG"
        elif (
            "short" in text_lower
            or "sell" in text_lower
            or "bechlam" in text_lower
            or "entry short" in text_lower
        ):
            direction = "SHORT"
        else:
            return self._fail(text, "Could not determine trade direction (Long/Short).")

        # 2. Extract Symbol
        symbol = "BTC/USDT"
        if "gold" in text_lower or "xau" in text_lower:
            symbol = "XAU/USD"
        elif "eth" in text_lower:
            symbol = "ETH/USDT"
        elif "btc" in text_lower:
            symbol = "BTC/USDT"

        # 3. Extract Numerical Levels (Entry, SL, TP, Size)
        # Entry pattern
        entry_match = re.search(r"(?:at|entry|price|@)\s*([0-9]+(?:\.[0-9]+)?)", text_lower)
        sl_match = re.search(r"(?:sl|stop|stoploss)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", text_lower)
        tp_match = re.search(
            r"(?:tp|target|takeprofit)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", text_lower
        )
        size_match = re.search(
            r"(?:size|lot|qty|quantity|units?)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)", text_lower
        )

        # Also check for direct patterns like "buy 0.05 btc" or "0.5 lot"
        if not size_match:
            size_match = re.search(
                r"(?:buy|sell|long|short|kinlam|bechlam)\s+([0-9]+(?:\.[0-9]+)?)\s*(?:btc|eth|gold|xau|lot|units?)?",
                text_lower,
            )
        if not size_match:
            size_match = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:lot|lots|units?|contracts?)", text_lower
            )

        entry = float(entry_match.group(1)) if entry_match else 0.0
        sl = float(sl_match.group(1)) if sl_match else 0.0
        tp = float(tp_match.group(1)) if tp_match else 0.0
        size = float(size_match.group(1)) if size_match else 0.0

        # Fallback to positional parsing only if explicit matches missing
        all_numbers = [float(n) for n in re.findall(r"[0-9]+(?:\.[0-9]+)?", text)]
        used_numbers = {entry, sl, tp, size}
        remaining_numbers = [n for n in all_numbers if n not in used_numbers]

        if entry <= 0:
            entry = remaining_numbers.pop(0) if remaining_numbers else 0.0
        if sl <= 0:
            sl = (
                remaining_numbers.pop(0)
                if remaining_numbers
                else (entry * 0.99 if direction == "LONG" else entry * 1.01)
            )
        if tp <= 0:
            tp = (
                remaining_numbers.pop(0)
                if remaining_numbers
                else (entry * 1.02 if direction == "LONG" else entry * 0.98)
            )
        if size <= 0:
            size = remaining_numbers.pop(0) if remaining_numbers else 0.1

        if entry <= 0:
            return self._fail(text, "Invalid or missing entry price.")

        # Open in Shadow Portfolio
        pos_id = portfolio_shadow.open_position(
            symbol=symbol,
            direction=direction,
            size=size,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
        )

        msg = (
            f"✅ Order Executed Successfully!\n"
            f"• Position ID: `{pos_id}`\n"
            f"• Market: {direction} {size} {symbol}\n"
            f"• Entry: ${entry:,.2f} | SL: ${sl:,.2f} | TP: ${tp:,.2f}\n"
            f"• Status: Shadow Ledger Active with Automated Trailing Stop."
        )

        return ParsedTradeCommand(
            raw_command=text,
            is_valid_command=True,
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            size_units=size,
            action_taken="SHADOW_POSITION_OPENED",
            message=msg,
        )

    def _fail(self, text: str, reason: str) -> ParsedTradeCommand:
        return ParsedTradeCommand(
            raw_command=text,
            is_valid_command=False,
            symbol="UNKNOWN",
            direction="UNKNOWN",
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            size_units=0.0,
            action_taken="PARSING_FAILED",
            message=f"❌ Failed to parse trade command: {reason}",
        )


# Singleton
command_executor = CommandExecutor()
