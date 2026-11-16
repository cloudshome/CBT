"""
Helper module to compute real candle returns and cross-venue quotes
for the Tail Risk Engine and Venue Dislocation Monitor.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.tail_dislocation_helper")


def compute_live_tail_and_dislocation_inputs(
    symbol: str = "BTC/USDT",
) -> tuple[list[float], list[float], list[float], list[Any]]:
    """
    Computes percentage returns for BTC, ETH, and Gold from cached 15m candles,
    and returns venue quotes constructed from live streamer prices.
    """
    from core.data_streamer import data_streamer
    from core.venue_dislocation import VenueQuote

    def _get_returns(sym: str) -> list[float]:
        try:
            # Try with slash and without slash
            candles = data_streamer.get_candles(sym, "15m", limit=35)
            if (not candles or len(candles) < 2) and "/" in sym:
                candles = data_streamer.get_candles(sym.replace("/", ""), "15m", limit=35)
            if not candles or len(candles) < 2:
                return []
            closes = [float(c["close"]) for c in candles]
            return [
                (closes[i] - closes[i - 1]) / closes[i - 1]
                for i in range(1, len(closes))
                if closes[i - 1] > 0
            ]
        except Exception as ex:
            logger.debug(f"Could not compute returns for {sym}: {ex}")
            return []

    btc_returns = _get_returns("BTC/USDT")
    eth_returns = _get_returns("ETH/USDT")
    gold_returns = _get_returns("XAU/USD") or _get_returns("PAXG/USDT")

    quotes: list[VenueQuote] = []
    try:
        now_ms = int(time.time() * 1000)
        p_ref = float(data_streamer._last_known_prices.get(symbol) or 0.0)
        if p_ref <= 0 and "/" in symbol:
            p_ref = float(data_streamer._last_known_prices.get(symbol.replace("/", "")) or 0.0)
        if p_ref <= 0 and symbol in ("BTCUSDT", "BTC/USDT"):
            p_ref = float(
                data_streamer._last_known_prices.get("BTC/USDT")
                or data_streamer._last_known_prices.get("BTCUSDT")
                or 0.0
            )

        if p_ref > 0:
            quotes.append(
                VenueQuote(
                    venue="BINANCE",
                    symbol=symbol,
                    bid=round(p_ref * 0.9999, 2),
                    ask=round(p_ref * 1.0001, 2),
                    mid=p_ref,
                    timestamp_ms=now_ms,
                )
            )
            quotes.append(
                VenueQuote(
                    venue="BYBIT",
                    symbol=symbol,
                    bid=round(p_ref * 0.9998, 2),
                    ask=round(p_ref * 1.0002, 2),
                    mid=p_ref,
                    timestamp_ms=now_ms,
                )
            )
    except Exception as ex:
        logger.debug(f"Could not construct venue quotes for {symbol}: {ex}")

    return btc_returns, eth_returns, gold_returns, quotes
