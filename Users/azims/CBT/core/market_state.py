"""
Standardized & Versioned Market State Vector (S_t) Compiler.
Compiles multi-timeframe price action, orderflow, volatility, macro, and sentiment
into a normalized numerical state vector with SHA-256 state hashing and feature schema guarantees.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.database import db_manager
from research.feature_registry import feature_registry

logger = logging.getLogger("ai_quant_sentinel.market_state")


@dataclass
class MarketStateVector:
    schema_version: str
    asset: str
    timestamp: int
    trend_scores: Dict[str, float]      # {"1d", "4h", "1h", "15m", "5m"} [-1.0, 1.0]
    structure: Dict[str, Any]           # {"bos_state", "choch_state", "liquidity_pool_pressure", "fvg_bias", "order_block_proximity"}
    orderflow: Dict[str, float]         # {"cvd_delta", "absorption_score", "oi_delta", "funding_zscore"}
    volatility: Dict[str, Any]          # {"atr_percentile", "bb_width_percentile", "squeeze_state"}
    macro_alignment: Dict[str, Any]     # {"dxy_correlation", "yield_beta", "event_risk_mode"}
    sentiment: Dict[str, float]         # {"nlp_news_score", "fear_greed_norm"}
    state_hash: str = field(default="")

    def __post_init__(self):
        if not self.state_hash:
            self.state_hash = self.compute_hash()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def compute_hash(self) -> str:
        """Calculates deterministic SHA-256 hash of the state vector contents."""
        raw_dict = {
            "schema_version": self.schema_version,
            "asset": self.asset,
            "timestamp": self.timestamp,
            "trend_scores": self.trend_scores,
            "structure": self.structure,
            "orderflow": self.orderflow,
            "volatility": self.volatility,
            "macro_alignment": self.macro_alignment,
            "sentiment": self.sentiment,
        }
        serialized = json.dumps(raw_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_flat_vector(self) -> np.ndarray:
        """Converts numerical features into a flattened 1D NumPy array for fast KNN and ML."""
        features = [
            self.trend_scores.get("1d", 0.0),
            self.trend_scores.get("4h", 0.0),
            self.trend_scores.get("1h", 0.0),
            self.trend_scores.get("15m", 0.0),
            self.trend_scores.get("5m", 0.0),
            float(self.structure.get("bos_state", 0)),
            float(self.structure.get("choch_state", 0)),
            float(self.structure.get("liquidity_pool_pressure", 0.5)),
            float(self.structure.get("fvg_bias", 0.0)),
            float(self.structure.get("order_block_proximity", 0.5)),
            float(self.orderflow.get("cvd_delta", 0.0)),
            float(self.orderflow.get("absorption_score", 0.0)),
            float(self.orderflow.get("oi_delta", 0.0)),
            float(self.orderflow.get("funding_zscore", 0.0)),
            float(self.volatility.get("atr_percentile", 0.5)),
            float(self.volatility.get("bb_width_percentile", 0.5)),
            1.0 if self.volatility.get("squeeze_state", False) else 0.0,
            float(self.macro_alignment.get("dxy_correlation", 0.0)),
            float(self.macro_alignment.get("yield_beta", 0.0)),
            1.0 if self.macro_alignment.get("event_risk_mode", False) else 0.0,
            float(self.sentiment.get("nlp_news_score", 0.0)),
            float(self.sentiment.get("fear_greed_norm", 0.5)),
        ]
        return np.array(features, dtype=np.float32)


class MarketStateCompiler:
    """Compiles multi-source real-time features into validated versioned state vectors."""

    def __init__(self, schema_version: str = "v2.1.0"):
        self.schema_version = schema_version

    def compile_state(
        self,
        asset: str,
        timestamp: Optional[int] = None,
        candles_by_tf: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        orderflow_data: Optional[Dict[str, Any]] = None,
        macro_data: Optional[Dict[str, Any]] = None,
        sentiment_data: Optional[Dict[str, Any]] = None,
    ) -> MarketStateVector:
        """
        Compiles all current market observations into a standard state vector S_t.
        """
        t_ms = timestamp or int(time.time() * 1000)
        candles_map = candles_by_tf or {}

        # 1. Multi-Timeframe Trend Scores [-1.0, 1.0]
        trend_scores = {}
        for tf in ["1d", "4h", "1h", "15m", "5m"]:
            c_list = candles_map.get(tf, [])
            trend_scores[tf] = self._compute_trend_score(c_list)

        # 2. Market Structure
        c_15m = candles_map.get("15m", candles_map.get("1h", []))
        structure = self._compute_structure_features(c_15m)

        # 3. Volatility Features
        volatility = self._compute_volatility_features(c_15m)

        # 4. Orderflow Features
        of = orderflow_data or {}
        orderflow = {
            "cvd_delta": float(np.clip(of.get("cvd_delta", 0.0), -1.0, 1.0)),
            "absorption_score": float(np.clip(of.get("absorption_score", 0.5), 0.0, 1.0)),
            "oi_delta": float(np.clip(of.get("oi_delta", 0.0), -1.0, 1.0)),
            "funding_zscore": float(np.clip(of.get("funding_zscore", 0.0), -3.0, 3.0)),
        }

        # 5. Macro Alignment Features
        macro = macro_data or {}
        macro_alignment = {
            "dxy_correlation": float(np.clip(macro.get("dxy_correlation", -0.5), -1.0, 1.0)),
            "yield_beta": float(np.clip(macro.get("yield_beta", -0.2), -2.0, 2.0)),
            "event_risk_mode": bool(macro.get("event_risk_mode", False)),
        }

        # 6. Sentiment Features
        sent = sentiment_data or {}
        sentiment = {
            "nlp_news_score": float(np.clip(sent.get("nlp_news_score", 0.1), -1.0, 1.0)),
            "fear_greed_norm": float(np.clip(sent.get("fear_greed_norm", 0.5), 0.0, 1.0)),
        }

        state_vector = MarketStateVector(
            schema_version=self.schema_version,
            asset=asset,
            timestamp=t_ms,
            trend_scores=trend_scores,
            structure=structure,
            orderflow=orderflow,
            volatility=volatility,
            macro_alignment=macro_alignment,
            sentiment=sentiment,
        )

        # Validate against schema
        is_valid, errors = feature_registry.validate_state_vector(state_vector.to_dict(), self.schema_version)
        if not is_valid:
            logger.warning(f"State vector validation warnings for {asset}: {errors}")

        return state_vector

    def _compute_trend_score(self, candles: List[Dict[str, Any]]) -> float:
        if len(candles) < 20:
            return 0.0
        closes = np.array([c["close"] for c in candles], dtype=np.float64)
        ema_fast = float(np.mean(closes[-8:]))
        ema_slow = float(np.mean(closes[-21:]))
        slope = (ema_fast - ema_slow) / ema_slow * 100.0
        return float(np.clip(np.tanh(slope * 2.0), -1.0, 1.0))

    def _compute_structure_features(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(candles) < 30:
            return {
                "bos_state": 0,
                "choch_state": 0,
                "liquidity_pool_pressure": 0.5,
                "fvg_bias": 0.0,
                "order_block_proximity": 0.5,
            }

        highs = np.array([c["high"] for c in candles], dtype=np.float64)
        lows = np.array([c["low"] for c in candles], dtype=np.float64)
        closes = np.array([c["close"] for c in candles], dtype=np.float64)

        recent_high = np.max(highs[-10:])
        prior_high = np.max(highs[-25:-10])
        recent_low = np.min(lows[-10:])
        prior_low = np.min(lows[-25:-10])

        bos_state = 0
        if recent_high > prior_high and closes[-1] > prior_high:
            bos_state = 1
        elif recent_low < prior_low and closes[-1] < prior_low:
            bos_state = -1

        choch_state = 0
        if bos_state == 1 and closes[-1] < np.mean(lows[-5:]):
            choch_state = -1
        elif bos_state == -1 and closes[-1] > np.mean(highs[-5:]):
            choch_state = 1

        range_span = max(0.01, recent_high - recent_low)
        cur_price = closes[-1]
        dist_to_high = (recent_high - cur_price) / range_span
        dist_to_low = (cur_price - recent_low) / range_span
        liq_pressure = float(np.clip(dist_to_low / (dist_to_high + dist_to_low + 1e-5), 0.0, 1.0))

        return {
            "bos_state": bos_state,
            "choch_state": choch_state,
            "liquidity_pool_pressure": round(liq_pressure, 3),
            "fvg_bias": round(float(np.tanh((closes[-1] - np.mean(closes[-10:])) / (np.std(closes[-10:]) + 1e-5))), 3),
            "order_block_proximity": round(float(np.clip(1.0 - abs(cur_price - np.mean(closes[-5:])) / range_span, 0.0, 1.0)), 3),
        }

    def _compute_volatility_features(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(candles) < 20:
            return {"atr_percentile": 0.5, "bb_width_percentile": 0.5, "squeeze_state": False}

        highs = np.array([c["high"] for c in candles], dtype=np.float64)
        lows = np.array([c["low"] for c in candles], dtype=np.float64)
        closes = np.array([c["close"] for c in candles], dtype=np.float64)

        # True Range
        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        rolling_atr = np.convolve(tr, np.ones(14) / 14, mode="valid")
        current_atr = rolling_atr[-1] if len(rolling_atr) > 0 else tr[-1]
        atr_rank = float(np.mean(rolling_atr <= current_atr)) if len(rolling_atr) > 1 else 0.5

        # Bollinger Bands Width
        sma20 = np.mean(closes[-20:])
        std20 = np.std(closes[-20:])
        bb_width = (2.0 * std20) / (sma20 + 1e-5)
        bb_rank = float(np.clip(bb_width * 50.0, 0.0, 1.0))

        squeeze_state = bool(bb_width < 0.015 or atr_rank < 0.20)

        return {
            "atr_percentile": round(atr_rank, 3),
            "bb_width_percentile": round(bb_rank, 3),
            "squeeze_state": squeeze_state,
        }

    def save_state_to_db(self, state: MarketStateVector, forward_outcomes: Optional[Dict[str, Any]] = None) -> None:
        state_id = f"STATE_{state.asset.replace('/', '_')}_{state.timestamp}"
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO market_states (state_id, timestamp, symbol, timeframe, schema_version, state_vector_json, forward_outcomes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_id) DO UPDATE SET
                    state_vector_json=excluded.state_vector_json,
                    forward_outcomes_json=excluded.forward_outcomes_json;
                """,
                (
                    state_id,
                    state.timestamp,
                    state.asset,
                    "15m",
                    state.schema_version,
                    json.dumps(state.to_dict()),
                    json.dumps(forward_outcomes or {}),
                ),
            )
            conn.commit()


# Singleton
market_state_compiler = MarketStateCompiler()
