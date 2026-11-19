"""scripts/data/ingest_binance_funding_rates.py — Real Historical 8h Funding Rate Ingestion.

Milestone 67: Ingests real historical Binance Futures 8h perpetual funding rates for
BTCUSDT, ETHUSDT, and SOLUSDT (Sept 14, 2020 – Oct 31, 2026) directly from Binance
Futures public API (/fapi/v1/fundingRate) into the local Parquet store.

Strict Invariants:
1. Pure real historical data only. Zero synthetic, fabricated, or simulated values.
2. Canonical schema: ts, exchange, market, symbol, metric, value, ingested_at.
3. Hive-partitioned in data/store/derivatives/ and compiled in data/store/funding_rates_8h_2020_2026.parquet.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from data.binance_client import BinanceClient
from data.derivatives import DerivativesStore, empty_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_funding")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
START_TS = 1599000000000  # Sept 2, 2020 (before Sept 14 start)
END_TS = 1793476800000  # Oct 31, 2026 20:00:00 UTC


def fetch_symbol_funding_history(
    client: BinanceClient,
    symbol: str,
    start_ts: int = START_TS,
    end_ts: int = END_TS,
) -> pd.DataFrame:
    """Fetches real historical 8h funding rates with pagination from Binance Futures."""
    logger.info(f"Fetching historical 8h funding rates for {symbol} from {start_ts} to {end_ts}...")
    cur_start = start_ts
    pages: list[pd.DataFrame] = []
    total_rows = 0

    while True:
        df = client.funding_rate_history(symbol, start_time=cur_start, limit=1000)
        if df is None or df.empty:
            logger.info(f"No further records returned for {symbol} at start_time={cur_start}.")
            break

        pages.append(df)
        count = len(df)
        total_rows += count
        max_ts = int(df["ts"].max())
        max_dt = pd.to_datetime(max_ts, unit="ms", utc=True)
        logger.info(
            f"  [{symbol}] Fetched {count} rows (batch max: {max_dt}). Cumulative: {total_rows}"
        )

        if max_ts >= end_ts or count < 1000:
            break

        cur_start = max_ts + 1
        time.sleep(0.05)

    if not pages:
        logger.warning(f"No funding records found for {symbol}.")
        return empty_frame()

    combined = pd.concat(pages, ignore_index=True)
    combined = combined.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    logger.info(f"Completed {symbol}: {len(combined)} unique 8h settlements.")
    return combined


def ingest_all_funding_rates(
    store_dir: Path | str | None = None,
) -> dict[str, pd.DataFrame]:
    """Ingests real funding rates for BTC, ETH, SOL into DerivativesStore and saves consolidated parquet."""
    client = BinanceClient()
    store = DerivativesStore(store_dir)
    now_ms = int(time.time() * 1000)
    all_symbol_frames: dict[str, pd.DataFrame] = {}
    consolidated_rows: list[dict] = []

    for sym in SYMBOLS:
        raw_df = fetch_symbol_funding_history(client, sym)
        if raw_df.empty:
            raise RuntimeError(f"Failed to fetch real historical funding rates for {sym}!")

        # Format into canonical schema
        canon_df = pd.DataFrame(
            {
                "ts": raw_df["ts"].astype("int64"),
                "exchange": "binance",
                "market": "perp",
                "symbol": sym,
                "metric": "funding_rate",
                "value": raw_df["funding_rate"].astype(float),
                "ingested_at": now_ms,
            }
        )

        written = store.write(canon_df)
        logger.info(f"Written {written} rows to DerivativesStore for {sym}.")
        all_symbol_frames[sym] = canon_df

        for _, row in raw_df.iterrows():
            consolidated_rows.append(
                {
                    "ts": int(row["ts"]),
                    "symbol": sym,
                    "funding_rate": float(row["funding_rate"]),
                    "mark_price": float(row.get("mark_price", 0.0)),
                    "ingested_at": now_ms,
                }
            )

    # Save consolidated dataset for fast research loading
    df_consolidated = (
        pd.DataFrame(consolidated_rows).sort_values(["ts", "symbol"]).reset_index(drop=True)
    )
    out_dir = Path(store_dir) if store_dir else Path("data/store")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "funding_rates_8h_2020_2026.parquet"
    df_consolidated.to_parquet(out_path, index=False)
    logger.info(
        f"Saved consolidated funding rate dataset to {out_path} ({len(df_consolidated)} total records)."
    )

    return all_symbol_frames


if __name__ == "__main__":
    ingest_all_funding_rates()
