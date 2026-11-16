"""M55 / M37 / M49 Ingest Monthly Candles from data.binance.vision (2020 to Present)
=============================================================================
Ingests historical monthly klines spanning 2020-01-01 to current UTC date
for BTCUSDT, ETHUSDT, SOLUSDT, PAXGUSDT, and XAUUSD across 15m, 1h, 4h, and 1d intervals.
Supports market="perp" (futures/um) and market="spot", with fallback.
Normalizes timestamps: if ts > 1e14 (microseconds), converts to milliseconds (// 1000).
Enforces canonical 16-column CandleStore schema via normalise_klines() with closed=True.
Mirrors PAXGUSDT under XAUUSD in CandleStore and XAUUSD / XAU/USD in SQLite market_data.db.
"""

from __future__ import annotations

import argparse
import datetime
import io
import logging
import sqlite3
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
import requests

from data.store import CandleStore, normalise_klines

MARKET_DATA_DB = ROOT_DIR / "data" / "market_data.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spot_monthly_ingest")

START_TS_2020 = 1577836800000  # 2020-01-01 00:00:00 UTC
SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT", "XAUUSD"]
SUPPORTED_TIMEFRAMES = ["15m", "1h", "4h", "1d"]


def get_months(start_year: int = 2020) -> list[str]:
    """Dynamically computes all months from start_year through current UTC month."""
    now = datetime.datetime.now(datetime.UTC)
    current_year = now.year
    current_month = now.month

    months = []
    for yr in range(start_year, current_year + 1):
        max_m = current_month if yr == current_year else 12
        for mo in range(1, max_m + 1):
            months.append(f"{yr}-{mo:02d}")
    return months


def parse_kline_zip(
    content_bytes: bytes,
    symbol: str,
    timeframe: str,
    market: str = "perp",
    exchange: str = "binance",
) -> pd.DataFrame:
    """Unzips, normalizes microseconds, and coerces to 16 canonical CandleStore columns."""
    z = zipfile.ZipFile(io.BytesIO(content_bytes))
    csv_name = z.namelist()[0]
    df = pd.read_csv(z.open(csv_name), header=None)
    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "count",
        "taker_buy_vol",
        "taker_buy_quote_vol",
        "ignore",
    ]
    df.columns = cols[: len(df.columns)]
    try:
        float(df.iloc[0]["open_time"])
    except (ValueError, TypeError):
        df = df.iloc[1:].copy()
    df["ts"] = df["open_time"].astype(int)
    # Normalize microseconds to milliseconds if needed
    df.loc[df["ts"] > 100000000000000, "ts"] = df.loc[df["ts"] > 100000000000000, "ts"] // 1000

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    if "quote_volume" in df.columns:
        df["quote_volume"] = df["quote_volume"].astype(float)
    if "count" in df.columns:
        df["trades"] = df["count"].astype(int)

    # Coerce to canonical schema via normalise_klines with closed=True
    canon = normalise_klines(
        df,
        exchange=exchange,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        source="binance_vision_archive",
    )
    canon["closed"] = True
    return canon


def fetch_month(symbol: str, timeframe: str, ym: str, market: str = "perp"):
    """Fetches and unzips a single monthly kline zip archive from data.binance.vision.
    Falls back between perp and spot if needed (e.g. PAXGUSDT is spot only).
    """
    actual_sym = "PAXGUSDT" if symbol.upper() in ("XAUUSD", "XAU/USD") else symbol
    urls = []
    if market == "perp" and actual_sym.upper() not in ("PAXGUSDT", "XAUUSD"):
        urls.append(
            (
                f"https://data.binance.vision/data/futures/um/monthly/klines/{actual_sym}/{timeframe}/{actual_sym}-{timeframe}-{ym}.zip",
                "perp",
            )
        )
        urls.append(
            (
                f"https://data.binance.vision/data/spot/monthly/klines/{actual_sym}/{timeframe}/{actual_sym}-{timeframe}-{ym}.zip",
                "spot",
            )
        )
    else:
        urls.append(
            (
                f"https://data.binance.vision/data/spot/monthly/klines/{actual_sym}/{timeframe}/{actual_sym}-{timeframe}-{ym}.zip",
                "spot",
            )
        )

    for url, mkt in urls:
        try:
            r = requests.get(url, timeout=12)
            if r.status_code == 200 and len(r.content) > 100:
                canon_df = parse_kline_zip(r.content, actual_sym, timeframe, market=mkt)
                return symbol, timeframe, ym, True, canon_df, mkt
        except Exception:
            continue
    return symbol, timeframe, ym, False, None, market


def fetch_spot_month(symbol: str, timeframe: str, ym: str):
    """Backward-compatible fetch_spot_month function."""
    sym, tf, ym_out, ok, df, _ = fetch_month(symbol, timeframe, ym, market="spot")
    return sym, tf, ym_out, ok, df


def sync_candles_to_sqlite(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    db_path: Path | str | None = None,
) -> int:
    """Upserts candles into SQLite market_data.db under standard and slash symbols."""
    if df.empty:
        return 0
    db = Path(db_path) if db_path else MARKET_DATA_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                timestamp BIGINT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                is_synthetic INTEGER DEFAULT 0,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles (symbol, timeframe, timestamp DESC)"
        )

        symbols_to_record = [symbol]
        # Form slash symbol e.g. BTCUSDT -> BTC/USDT, PAXGUSDT -> PAXG/USDT
        if symbol.endswith("USDT") and len(symbol) > 4:
            base = symbol[:-4]
            symbols_to_record.append(f"{base}/USDT")

        # Mirror Gold PAXGUSDT -> XAUUSD and XAU/USD
        if symbol.upper() in ("PAXGUSDT", "PAXG/USDT"):
            symbols_to_record.extend(["XAUUSD", "XAU/USD"])
        elif symbol.upper() in ("XAUUSD", "XAU/USD"):
            symbols_to_record.extend(["PAXGUSDT", "PAXG/USDT"])

        unique_syms = list(dict.fromkeys(symbols_to_record))
        total_rows = 0

        for sym_lbl in unique_syms:
            rows = [
                (
                    int(r["ts"]),
                    sym_lbl,
                    timeframe,
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                    float(r.get("volume", 0.0)),
                    0,  # is_synthetic = 0 (strictly empirical)
                )
                for _, r in df.iterrows()
            ]
            cur.executemany(
                """
                INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume, is_synthetic)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    is_synthetic=0
                """,
                rows,
            )
            total_rows += len(rows)
        conn.commit()
        return total_rows
    finally:
        conn.close()


def ingest_candles(
    symbol: str,
    timeframe: str = "1h",
    start_year: int = 2020,
    market: str = "perp",
    sync_sqlite: bool = True,
    max_workers: int = 16,
) -> int:
    """Ingests and stores all historical monthly candles for symbol and timeframe."""
    months = get_months(start_year=start_year)
    logger.info(
        f"Ingesting {market} {timeframe} klines for {symbol}: {len(months)} months ({months[0]} to {months[-1]})..."
    )
    store = CandleStore(ROOT_DIR / "data" / "store")
    all_dfs = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(fetch_month, symbol, timeframe, ym, market) for ym in months]
        for fut in futures:
            sym, tf, ym, ok, df, mkt_used = fut.result()
            if ok and df is not None and not df.empty:
                store.write(df)
                if sym.upper() in ("PAXGUSDT", "PAXG/USDT"):
                    # Mirror Gold under XAUUSD in CandleStore
                    gold_df = df.copy()
                    gold_df["symbol"] = "XAUUSD"
                    store.write(gold_df)
                all_dfs.append(df)

    if not all_dfs:
        logger.warning(f"Zero candles ingested for {symbol} {timeframe}.")
        return 0

    full_df = (
        pd.concat(all_dfs, ignore_index=True)
        .drop_duplicates(subset=["ts"])
        .sort_values("ts")
        .reset_index(drop=True)
    )
    if sync_sqlite:
        sync_candles_to_sqlite(full_df, symbol, timeframe)

    logger.info(
        f"Successfully ingested {len(full_df)} candles for {symbol} {timeframe} across {len(all_dfs)} monthly archives."
    )
    return len(full_df)


def ingest_spot(symbol: str, timeframe: str = "1h", start_year: int = 2020) -> int:
    """Backward-compatible ingest_spot function."""
    return ingest_candles(
        symbol,
        timeframe=timeframe,
        start_year=start_year,
        market="spot",
        sync_sqlite=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Ingest monthly klines from data.binance.vision (2020-present)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"],
        help="Symbols to ingest",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1h", "4h", "1d", "15m"],
        help="Timeframes to ingest",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2020,
        help="Start year (default: 2020)",
    )
    parser.add_argument(
        "--market",
        default="perp",
        choices=["perp", "spot"],
        help="Target market partition",
    )
    parser.add_argument(
        "--sync-sqlite",
        action="store_true",
        default=True,
        help="Sync to data/market_data.db",
    )
    args = parser.parse_args()

    for sym in args.symbols:
        for tf in args.timeframes:
            ingest_candles(
                sym,
                timeframe=tf,
                start_year=args.start_year,
                market=args.market,
                sync_sqlite=args.sync_sqlite,
            )
    logger.info("Multi-year 2020-present historical ingestion completed successfully.")


if __name__ == "__main__":
    main()
