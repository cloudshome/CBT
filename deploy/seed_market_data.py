#!/usr/bin/env python3
"""
SKY / CTB — Historical Market Data Seed Script.

Pre-populates local SQLite market_data.db with valid historical OHLCV data
for primary trading pairs across standard institutional timeframes.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import db_manager
from core.data_streamer import data_streamer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt_seed")

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT", "ADA/USDT", "AVAX/USDT"]
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


def seed_market_data(symbols=None, timeframes=None, candle_count: int = 200) -> int:
    symbols = symbols or DEFAULT_SYMBOLS
    timeframes = timeframes or DEFAULT_TIMEFRAMES
    total_seeded = 0

    logger.info(f"Seeding market data for {len(symbols)} symbols across {len(timeframes)} timeframes...")

    for symbol in symbols:
        for tf in timeframes:
            existing = data_streamer.get_candles(symbol, tf, limit=10)
            if len(existing) >= 50:
                logger.info(f"Already populated: {symbol} ({tf}) with {len(existing)} candles.")
                continue

            generated = data_streamer.generate_synthetic_candles(symbol, tf, count=candle_count)
            data_streamer.save_candles(symbol, tf, generated)
            total_seeded += len(generated)
            logger.info(f"Seeded {len(generated)} candles for {symbol} ({tf}).")

    logger.info(f"Market data seeding completed. Total candles inserted: {total_seeded}")
    return total_seeded


def main():
    parser = argparse.ArgumentParser(description="Seed SKY market databases with baseline candles.")
    parser.add_argument("--count", type=int, default=200, help="Number of candles per timeframe")
    args = parser.parse_args()

    count = seed_market_data(candle_count=args.count)
    print(f"Successfully seeded {count} candles.")


if __name__ == "__main__":
    main()
