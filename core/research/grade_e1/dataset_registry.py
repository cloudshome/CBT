"""
core/research/grade_e1/dataset_registry.py
==========================================
Grade-E1 Dataset Registry & Cryptographic Loader.

Loads, validates, and transforms frozen K9 research datasets into immutable MarketSnapshot streams.
Strictly checks SHA-256 integrity and flags data gap boundaries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

from core.research.grade_e1.contracts import MarketSnapshot

logger = logging.getLogger("sky.grade_e1.dataset_registry")

TIMEFRAME_STEP_MS: dict[str, int] = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


class GradeE1DatasetRegistry:
    """Loads and cryptographically validates frozen K9 datasets."""

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            self.data_dir = Path("data/research/datasets")
        else:
            self.data_dir = Path(data_dir)
        self.manifest_path = self.data_dir / "manifest_k9.json"

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {self.manifest_path}")
        with open(self.manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def verify_and_load(self, dataset_id: str) -> tuple[dict[str, Any], list[MarketSnapshot]]:
        """
        Loads dataset by ID, validates SHA-256 content hash against manifest,
        and constructs an immutable list of causal MarketSnapshot objects.
        """
        manifest = self.load_manifest()
        if dataset_id not in manifest:
            raise KeyError(f"Dataset {dataset_id} not found in manifest_k9.json")

        entry = manifest[dataset_id]
        file_path = self.data_dir / f"{dataset_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file missing on disk: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        candles = raw_data.get("candles", [])
        if not candles:
            raise ValueError(f"Dataset {dataset_id} contains zero candles")

        # Cryptographic content verification using canonical hashing
        hasher = hashlib.sha256()
        for c in candles:
            ts = int(c.get("timestamp") or c.get("time") or c.get("t", 0))
            o = round(float(c.get("open") or c.get("o", 0.0)), 6)
            h = round(float(c.get("high") or c.get("h", 0.0)), 6)
            lo = round(float(c.get("low") or c.get("l", 0.0)), 6)
            cl = round(float(c.get("close") or c.get("c", 0.0)), 6)
            v = round(float(c.get("volume") or c.get("v", 0.0)), 6)
            row_str = f"{ts}:{o}:{h}:{lo}:{cl}:{v}\n"
            hasher.update(row_str.encode("utf-8"))
        calculated_hash = hasher.hexdigest()

        expected_hash = entry["content_hash"]
        if calculated_hash != expected_hash:
            raise ValueError(
                f"Cryptographic hash mismatch for {dataset_id}: "
                f"expected {expected_hash}, calculated {calculated_hash}"
            )

        timeframe = entry.get("timeframe", "15m")
        step_ms = TIMEFRAME_STEP_MS.get(timeframe, 15 * 60 * 1000)

        snapshots: list[MarketSnapshot] = []
        prev_ts = 0

        for idx, c in enumerate(candles):
            ts = int(c["timestamp"])
            o = float(c["open"])
            h = float(c["high"])
            lo = float(c["low"])
            close = float(c["close"])
            v = float(c["volume"])

            # Check for gap boundary
            is_gap = False
            if prev_ts > 0 and (ts - prev_ts) > (step_ms * 1.5):
                is_gap = True

            # Calculate Parkinson volatility proxy in basis points
            hl_ratio = max(1e-8, h / max(1e-8, lo))
            parkinson_vol_bps = math.sqrt((math.log(hl_ratio) ** 2) / (4 * math.log(2))) * 10000.0

            # Estimate inside spread in bps based on asset and volatility
            # Baseline ~ 1.5 bps for BTC, 2.5 bps for ETH, 4.0 bps for SOL
            asset = entry.get("asset", "BTC")
            base_spread = 1.5 if asset == "BTC" else (2.5 if asset == "ETH" else 4.0)
            spread_bps = max(1.0, base_spread + (parkinson_vol_bps * 0.05))

            snapshot = MarketSnapshot(
                timestamp=ts,
                bar_index=idx,
                open=o,
                high=h,
                low=lo,
                close=close,
                volume=v,
                spread_bps=round(spread_bps, 2),
                volatility_bps=round(parkinson_vol_bps, 2),
                is_gap_boundary=is_gap,
            )
            snapshots.append(snapshot)
            prev_ts = ts

        logger.info(f"Loaded and verified {len(snapshots)} snapshots for {dataset_id}")
        return entry, snapshots


dataset_registry = GradeE1DatasetRegistry()
