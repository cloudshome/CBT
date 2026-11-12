"""
Binance USD-M Perpetual Derivatives Ingestion Engine (M36.1)
===========================================================
Acquires and stores canonical derivatives time series:
- Historical Funding Rates (/fapi/v1/fundingRate)
- Historical Open Interest (/futures/data/openInterestHist)
For BTCUSDT and ETHUSDT.

Stores partitions under data/store/derivatives/ with schema:
(ts, exchange, market, symbol, metric, value, ingested_at)
Emits cryptographic manifest research/m36_1_derivatives_data_manifest.json
"""

import hashlib
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.binance_client import BinanceClient
from data.derivatives import DerivativesStore, FUNDING_RATE, OPEN_INTEREST, OPEN_INTEREST_VALUE, MARK_PRICE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("derivatives_ingest")


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def ingest_derivatives():
    logger.info("Initializing Derivatives Data Acquisition...")
    client = BinanceClient()
    store = DerivativesStore(root=ROOT_DIR / "data" / "store" / "derivatives")

    symbols = ["BTCUSDT", "ETHUSDT"]
    manifest_records = {}

    for sym in symbols:
        logger.info(f"--- Ingesting Derivatives for {sym} ---")
        now_ms = int(time.time() * 1000)

        # 1. Funding Rate History (limit 1,000 observations per request)
        # 1,000 8-hour observations covers ~333 days of funding history (~1 year)
        logger.info(f"Fetching funding rate history for {sym}...")
        df_fr = client.funding_rate_history(symbol=sym, limit=1000)
        
        if df_fr is not None and not df_fr.empty:
            logger.info(f"Retrieved {len(df_fr)} funding rate records for {sym}.")
            # Format into canonical schema
            # ts, exchange, market, symbol, metric, value, ingested_at
            rows_fr = []
            rows_mp = []
            for _, r in df_fr.iterrows():
                t = int(r["ts"])
                fr_val = float(r["funding_rate"])
                mp_val = float(r["mark_price"])
                rows_fr.append({
                    "ts": t,
                    "exchange": "binance",
                    "market": "perp",
                    "symbol": sym,
                    "metric": FUNDING_RATE,
                    "value": fr_val,
                    "ingested_at": now_ms,
                })
                rows_mp.append({
                    "ts": t,
                    "exchange": "binance",
                    "market": "perp",
                    "symbol": sym,
                    "metric": MARK_PRICE,
                    "value": mp_val,
                    "ingested_at": now_ms,
                })
            
            w_fr = store.write(rows_fr)
            w_mp = store.write(rows_mp)
            logger.info(f"Stored {w_fr} funding rate and {w_mp} mark price records.")

        # 2. Open Interest History (hourly, limit 500 observations)
        # Binance limits /futures/data/openInterestHist to max 500 observations per call, covering ~21 days of 1h history
        logger.info(f"Fetching open interest history (1h) for {sym}...")
        df_oi = client.open_interest_history(symbol=sym, period="1h", limit=500)
        
        if df_oi is not None and not df_oi.empty:
            logger.info(f"Retrieved {len(df_oi)} open interest records for {sym}.")
            rows_oi = []
            rows_oiv = []
            for _, r in df_oi.iterrows():
                t = int(r["ts"])
                oi_val = float(r["open_interest"])
                oiv_val = float(r["open_interest_value"])
                rows_oi.append({
                    "ts": t,
                    "exchange": "binance",
                    "market": "perp",
                    "symbol": sym,
                    "metric": OPEN_INTEREST,
                    "value": oi_val,
                    "ingested_at": now_ms,
                })
                rows_oiv.append({
                    "ts": t,
                    "exchange": "binance",
                    "market": "perp",
                    "symbol": sym,
                    "metric": OPEN_INTEREST_VALUE,
                    "value": oiv_val,
                    "ingested_at": now_ms,
                })
            
            w_oi = store.write(rows_oi)
            w_oiv = store.write(rows_oiv)
            logger.info(f"Stored {w_oi} open interest and {w_oiv} open interest value records.")

    # Generate Manifest for stored derivative partitions
    derivatives_root = ROOT_DIR / "data" / "store" / "derivatives"
    all_parquet_files = sorted(list(derivatives_root.rglob("*.parquet")))
    
    file_manifests = []
    total_bytes = 0
    total_rows = 0

    for p in all_parquet_files:
        df_part = pd.read_parquet(p)
        f_size = p.stat().st_size
        sha = compute_file_sha256(p)
        total_bytes += f_size
        total_rows += len(df_part)
        
        file_manifests.append({
            "relative_path": str(p.relative_to(ROOT_DIR)).replace("\\", "/"),
            "size_bytes": f_size,
            "sha256": sha,
            "rows": len(df_part),
            "min_ts": int(df_part["ts"].min()),
            "max_ts": int(df_part["ts"].max()),
            "min_datetime_utc": datetime.fromtimestamp(df_part["ts"].min() / 1000, tz=timezone.utc).isoformat(),
            "max_datetime_utc": datetime.fromtimestamp(df_part["ts"].max() / 1000, tz=timezone.utc).isoformat(),
            "metric": str(df_part["metric"].iloc[0]),
            "symbol": str(df_part["symbol"].iloc[0]),
        })

    manifest_output = {
        "manifest_version": "M36.1-DERIVATIVES-INGESTION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "exchange": "binance",
        "market": "perp",
        "total_files": len(file_manifests),
        "total_size_bytes": total_bytes,
        "total_records_stored": total_rows,
        "api_limitations": {
            "funding_rate_endpoint": "/fapi/v1/fundingRate (Returns max 1,000 8h intervals, ~333 days per fetch)",
            "open_interest_endpoint": "/futures/data/openInterestHist (Returns max 500 records per call, max lookback ~30 days via REST API)",
            "historical_archive_requirement": "Multi-year Open Interest (2022-2026) requires batch-downloading Binance Monthly Data Archives (data.binance.vision) because public REST API caps historical OI pagination to recent 30 days."
        },
        "point_in_time_semantics": {
            "funding_rate": "Published and settled every 8 hours at 00:00, 08:00, 16:00 UTC. Causal decision at bar t can reference only funding settlements where ts <= t.",
            "open_interest": "Sampled at 5m or 1h intervals. In hourly trading, the open interest snapshot at hour h is final only when hour h closes."
        },
        "partitions": file_manifests,
    }

    out_manifest = ROOT_DIR / "research" / "m36_1_derivatives_data_manifest.json"
    with open(out_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest_output, f, indent=2)

    logger.info(f"Saved derivatives manifest to {out_manifest}.")
    print("M36.1 DERIVATIVES INGESTION COMPLETED.")


if __name__ == "__main__":
    ingest_derivatives()

