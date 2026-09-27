"""
Microstructure Feature Tokenizer and Sequence Adapter for Kronos.
Transforms raw market events and OHLCV bars into causal Kronos-compatible input tensors
accompanied by validated 8-vector microstructure context.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.kronos.causality import ZeroLookaheadValidator
from core.kronos.feature_schema import FeatureSchema


@dataclass
class TokenizedKronosInput:
    symbol: str
    timeframe: str
    as_of_timestamp: int
    lookback_bars: int
    primary_sequence: np.ndarray  # Shape: (lookback, 5) -> Open, High, Low, Close, Volume
    microstructure_context: dict[str, float]  # 8 validated features at step t
    input_hash: str
    feature_schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of_timestamp": self.as_of_timestamp,
            "lookback_bars": self.lookback_bars,
            "microstructure_context": self.microstructure_context,
            "input_hash": self.input_hash,
            "feature_schema_version": self.feature_schema_version,
            "primary_shape": list(self.primary_sequence.shape),
        }


class FeatureTokenizer:
    """
    Constructs point-in-time input tensors for Kronos inference.
    Guarantees that feature calculation at bar k never observes bars k+1..N.
    """

    def __init__(self):
        self.schema = FeatureSchema()

    def tokenize(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        lookback_bars: int = 128,
        as_of_ts: int | None = None,
        extra_microstructure: dict[str, float] | None = None,
    ) -> TokenizedKronosInput:
        """
        Processes candle sequence, computes causal microstructure features, and encodes inputs.
        """
        # 1. Zero-Lookahead Validation
        ZeroLookaheadValidator.validate_ohlcv_sequence(candles, as_of_ts=as_of_ts, min_bars=10)

        # Slice to requested lookback
        target_candles = candles[-lookback_bars:] if len(candles) > lookback_bars else candles
        n_bars = len(target_candles)

        # Extract timestamps
        timestamps = [
            int(c.get("timestamp") or c.get("time") or c.get("t", 0)) for c in target_candles
        ]
        actual_as_of = timestamps[-1]

        # 2. Extract Primary OHLCV Sequence
        opens = [float(c.get("open") or c.get("o", 0.0)) for c in target_candles]
        highs = [float(c.get("high") or c.get("h", 0.0)) for c in target_candles]
        lows = [float(c.get("low") or c.get("l", 0.0)) for c in target_candles]
        closes = [float(c.get("close") or c.get("c", 0.0)) for c in target_candles]
        volumes = [float(c.get("volume") or c.get("v", 0.0)) for c in target_candles]

        # 3. Causal Microstructure Derivations from Candle History
        # Returns
        log_returns = [0.0]
        for i in range(1, n_bars):
            prev_c = closes[i - 1]
            curr_c = closes[i]
            r = math.log(curr_c / prev_c) if prev_c > 0 and curr_c > 0 else 0.0
            log_returns.append(r)

        # Volatility clock: rolling 20-bar return std
        vol_clock_val = float(np.std(log_returns[-20:])) if len(log_returns) >= 5 else 0.01

        # Normalized mid return
        mid_return_val = float(log_returns[-1])

        # Synthesize base microstructure context (can be enriched by live L2/L3 order book if passed)
        micro_raw: dict[str, float] = {
            "ofi_norm": 0.0,
            "vpin": 0.15,
            "mid_return": mid_return_val,
            "spread_bps": 2.5,
            "depth_imb": 0.0,
            "trade_sign": 0.0,
            "vol_clock": vol_clock_val,
            "resting_wall": 0.0,
        }

        # If external microstructure (from L2 heatmap / resting wall sentinel) is provided, merge causally
        if extra_microstructure:
            for k, v in extra_microstructure.items():
                if k in micro_raw and math.isfinite(v):
                    micro_raw[k] = float(v)

        # 4. Validate through FeatureSchema
        validated_micro = self.schema.validate_vector(micro_raw)

        # 5. Build Primary Array: (N, 5)
        primary_arr = np.column_stack([opens, highs, lows, closes, volumes])

        # 6. Compute Deterministic Input Hash (sha256 of primary array + validated micro)
        hash_payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "as_of_ts": actual_as_of,
            "shape": list(primary_arr.shape),
            "first_close": round(closes[0], 4),
            "last_close": round(closes[-1], 4),
            "micro": validated_micro,
        }
        input_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return TokenizedKronosInput(
            symbol=symbol,
            timeframe=timeframe,
            as_of_timestamp=actual_as_of,
            lookback_bars=n_bars,
            primary_sequence=primary_arr,
            microstructure_context=validated_micro,
            input_hash=input_hash,
            feature_schema_version=self.schema.SCHEMA_VERSION,
        )


feature_tokenizer = FeatureTokenizer()
