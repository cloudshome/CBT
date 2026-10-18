"""
core/kronos/research/dataset_freeze.py
======================================
Milestone K9.1: Canonical Immutable Dataset Freeze & Data Provenance Protocol.
Manages strict chronological dataset validation, missing-bar detection,
cryptographic SHA-256 manifest generation, and post-freeze mutation detection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.kronos.research.dataset_freeze")

TIMEFRAME_STEP_MS: dict[str, int] = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


class DatasetQualityStatus(StrEnum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class DatasetCorruptionError(ValueError):
    """Raised when frozen dataset content hash diverges from manifest or schema is violated."""

    pass


@dataclass
class DatasetManifestEntry:
    dataset_id: str
    asset: str
    venue: str
    market_type: str
    symbol: str
    timeframe: str
    start_timestamp: int
    end_timestamp: int
    row_count: int
    missing_intervals_count: int
    missing_intervals: list[dict[str, int]]
    schema_hash: str
    content_hash: str
    source: str
    generation_timestamp: int
    methodology_version: str
    status: str
    quality_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DatasetFreezeManager:
    """
    Manages generation, validation, and immutable manifest persistence
    for Milestone K9 canonical research datasets.
    """

    METHODOLOGY_VERSION = "K9_DATASET_V1.0"
    DEFAULT_STORAGE_DIR = Path("data/research/datasets")
    DEFAULT_MANIFEST_PATH = Path("data/research/datasets/manifest_k9.json")

    def __init__(
        self,
        storage_dir: Path | str = DEFAULT_STORAGE_DIR,
        manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
    ):
        self.storage_dir = Path(storage_dir)
        self.manifest_path = Path(manifest_path)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_schema_hash() -> str:
        """Schema fingerprint for canonical 5-column OHLCV format."""
        schema_def = {
            "columns": ["timestamp", "open", "high", "low", "close", "volume"],
            "types": ["int64", "float64", "float64", "float64", "float64", "float64"],
            "version": "1.0.0",
        }
        return hashlib.sha256(json.dumps(schema_def, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def compute_content_hash(candles: list[dict[str, Any]]) -> str:
        """Computes deterministic SHA-256 content hash across all candles."""
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
        return hasher.hexdigest()

    def validate_and_diagnose(
        self,
        candles: list[dict[str, Any]],
        timeframe: str,
        min_rows: int = 50,
    ) -> tuple[DatasetQualityStatus, list[dict[str, int]], list[str]]:
        """
        Thoroughly validates candle series:
        - Timestamp monotonicity (no backwards steps)
        - Duplicate detection
        - Missing interval diagnostics
        - Price geometry checks
        """
        notes: list[str] = []
        missing_intervals: list[dict[str, int]] = []

        if not candles or len(candles) < min_rows:
            notes.append(f"Insufficient row count: {len(candles) if candles else 0} < {min_rows}")
            return DatasetQualityStatus.INSUFFICIENT_SAMPLE, missing_intervals, notes

        step_ms = TIMEFRAME_STEP_MS.get(timeframe)
        if not step_ms:
            notes.append(f"Unsupported timeframe for interval verification: {timeframe}")
            return DatasetQualityStatus.INVALID, missing_intervals, notes

        prev_ts = -1
        has_geometry_error = False
        has_inversion_error = False

        for idx, c in enumerate(candles):
            ts_raw = c.get("timestamp") or c.get("time") or c.get("t")
            if ts_raw is None:
                notes.append(f"Row {idx} missing timestamp")
                return DatasetQualityStatus.INVALID, missing_intervals, notes

            ts = int(ts_raw)
            if idx > 0:
                if ts == prev_ts:
                    notes.append(f"Duplicate timestamp detected at index {idx}: {ts}")
                    has_inversion_error = True
                elif ts < prev_ts:
                    notes.append(
                        f"Timestamp inversion detected at index {idx}: {ts} < previous {prev_ts}"
                    )
                    has_inversion_error = True
                elif ts > prev_ts + step_ms:
                    # Gap detected
                    gap_count = int((ts - prev_ts) // step_ms) - 1
                    missing_intervals.append(
                        {
                            "from_ts": prev_ts,
                            "to_ts": ts,
                            "missing_bars": gap_count,
                        }
                    )

            prev_ts = ts

            # Check prices
            try:
                o = float(c.get("open") or c.get("o", 0.0))
                h = float(c.get("high") or c.get("h", 0.0))
                lo = float(c.get("low") or c.get("l", 0.0))
                cl = float(c.get("close") or c.get("c", 0.0))
                v = float(c.get("volume") or c.get("v", 0.0))
            except (ValueError, TypeError):
                notes.append(f"Non-numeric value in row {idx}")
                has_geometry_error = True
                continue

            for name, val in [("open", o), ("high", h), ("low", lo), ("close", cl), ("volume", v)]:
                if not math.isfinite(val):
                    notes.append(f"Non-finite {name} in row {idx}: {val}")
                    has_geometry_error = True

            if o <= 0 or h <= 0 or lo <= 0 or cl <= 0 or v < 0:
                notes.append(f"Non-positive price or negative volume in row {idx}")
                has_geometry_error = True

            if h < lo or h < max(o, cl) or lo > min(o, cl):
                notes.append(f"Price geometry breached in row {idx}: O={o}, H={h}, L={lo}, C={cl}")
                has_geometry_error = True

        if has_inversion_error or has_geometry_error:
            return DatasetQualityStatus.INVALID, missing_intervals, notes

        if len(missing_intervals) > 0:
            total_missing = sum(item["missing_bars"] for item in missing_intervals)
            missing_ratio = total_missing / (len(candles) + total_missing)
            notes.append(
                f"Missing {total_missing} intervals across {len(missing_intervals)} gaps (missing ratio {missing_ratio:.2%})"
            )
            if missing_ratio > 0.05:
                return DatasetQualityStatus.DEGRADED, missing_intervals, notes

        return DatasetQualityStatus.VALID, missing_intervals, notes

    def freeze_dataset(
        self,
        candles: list[dict[str, Any]],
        symbol: str,
        timeframe: str,
        venue: str = "BINANCE",
        market_type: str = "SPOT",
        source: str = "HISTORICAL_REST_ARCHIVE",
        dataset_id: str | None = None,
    ) -> DatasetManifestEntry:
        """
        Freezes a dataset:
        1. Validates chronological consistency and geometry.
        2. Computes hashes.
        3. Persists JSON payload to storage_dir.
        4. Updates manifest_k9.json immutably.
        """
        clean_sym = symbol.replace("/", "").upper()
        norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
        asset = norm_sym.split("/")[0]

        status, missing_intervals, notes = self.validate_and_diagnose(candles, timeframe)

        if status == DatasetQualityStatus.INVALID:
            raise DatasetCorruptionError(
                f"Cannot freeze invalid dataset for {symbol} {timeframe}: {'; '.join(notes[:3])}"
            )

        timestamps = [int(c.get("timestamp") or c.get("time") or c.get("t", 0)) for c in candles]
        start_ts = timestamps[0]
        end_ts = timestamps[-1]

        schema_hash = self.compute_schema_hash()
        content_hash = self.compute_content_hash(candles)

        if dataset_id is None:
            dataset_id = f"K9_{clean_sym}_{timeframe}_{content_hash[:8]}"

        entry = DatasetManifestEntry(
            dataset_id=dataset_id,
            asset=asset,
            venue=venue,
            market_type=market_type,
            symbol=norm_sym,
            timeframe=timeframe,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            row_count=len(candles),
            missing_intervals_count=len(missing_intervals),
            missing_intervals=missing_intervals,
            schema_hash=schema_hash,
            content_hash=content_hash,
            source=source,
            generation_timestamp=int(timestamps[-1]),
            methodology_version=self.METHODOLOGY_VERSION,
            status=status.value,
            quality_notes=notes,
        )

        # Save dataset file
        file_path = self.storage_dir / f"{dataset_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "manifest": entry.to_dict(),
                    "candles": candles,
                },
                f,
                indent=2,
            )

        # Update global manifest
        self._update_manifest(entry)
        logger.info(
            f"Frozen dataset {dataset_id} ({status.value}) with content hash {content_hash[:16]}"
        )
        return entry

    def verify_dataset_integrity(self, dataset_id: str) -> bool:
        """
        Checks that the on-disk dataset exists, matches its recorded content hash,
        and has not mutated since being frozen.
        """
        manifest = self.load_manifest()
        if dataset_id not in manifest:
            raise DatasetCorruptionError(f"Dataset {dataset_id} not found in manifest")

        entry = manifest[dataset_id]
        file_path = self.storage_dir / f"{dataset_id}.json"
        if not file_path.exists():
            raise DatasetCorruptionError(f"Dataset file {file_path} missing on disk")

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        candles = data.get("candles", [])
        actual_hash = self.compute_content_hash(candles)
        expected_hash = entry.get("content_hash")

        if actual_hash != expected_hash:
            raise DatasetCorruptionError(
                f"Mutation detected in dataset {dataset_id}! "
                f"Expected hash {expected_hash}, actual hash {actual_hash}"
            )
        return True

    def load_frozen_dataset(
        self, dataset_id: str
    ) -> tuple[DatasetManifestEntry, list[dict[str, Any]]]:
        """Loads and cryptographically verifies a frozen dataset."""
        self.verify_dataset_integrity(dataset_id)
        file_path = self.storage_dir / f"{dataset_id}.json"
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        raw_manifest = data["manifest"]
        entry = DatasetManifestEntry(**raw_manifest)
        return entry, data["candles"]

    def load_manifest(self) -> dict[str, dict[str, Any]]:
        """Loads manifest file or returns empty dictionary if absent."""
        if not self.manifest_path.exists():
            return {}
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _update_manifest(self, entry: DatasetManifestEntry) -> None:
        manifest = self.load_manifest()
        manifest[entry.dataset_id] = entry.to_dict()
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)


dataset_freeze_manager = DatasetFreezeManager()
