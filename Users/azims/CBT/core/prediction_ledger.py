"""
P0 Immutable Prediction Freeze & Verification Ledger.
Freezes complete forecast records in data/brain_memory.db BEFORE the future unfolds.
Provides automated background verification against resolving candles and computes realization Brier scores.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.database import db_manager
from core.market_state import MarketStateVector

logger = logging.getLogger("ai_quant_sentinel.prediction_ledger")


@dataclass
class FrozenPrediction:
    prediction_id: str
    timestamp: int
    symbol: str
    timeframe: str
    state_vector_hash: str
    forecast_horizons: Dict[str, Any]
    expected_path: Dict[str, Any]
    invalidation_price: float
    target_prices: Dict[str, float]
    confidence: float
    outcome_5m: Optional[str] = None
    outcome_1h: Optional[str] = None
    outcome_4h: Optional[str] = None
    is_verified: bool = False
    brier_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PredictionLedger:
    """Manages immutable pre-outcome forecast storage and post-hoc outcome verification."""

    def freeze_prediction(
        self,
        symbol: str,
        timeframe: str,
        state: MarketStateVector,
        forecast_ladder: Dict[str, Any],
        expected_path: Dict[str, Any],
        invalidation_price: float,
        target_prices: Dict[str, float],
        confidence: float,
    ) -> str:
        """
        Freezes the forecast into the ledger BEFORE the future candle closes.
        """
        now = state.timestamp
        pred_id = f"PRED_{symbol.replace('/', '_')}_{now}"

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT INTO prediction_ledger (
                    prediction_id, timestamp, symbol, timeframe, state_vector_hash,
                    forecast_horizons_json, expected_path_json, invalidation_price,
                    target_prices_json, confidence, outcome_5m, outcome_1h, outcome_4h,
                    is_verified, brier_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL)
                ON CONFLICT(prediction_id) DO NOTHING;
                """,
                (
                    pred_id,
                    now,
                    symbol,
                    timeframe,
                    state.state_hash,
                    json.dumps(forecast_ladder),
                    json.dumps(expected_path),
                    float(invalidation_price),
                    json.dumps(target_prices),
                    float(confidence),
                ),
            )
            conn.commit()

        logger.info(f"Frozen prediction {pred_id} in ledger before future resolution.")
        return pred_id

    def verify_pending_predictions(self, current_time_ms: Optional[int] = None) -> int:
        """
        Scans unverified predictions in the ledger and verifies their outcomes
        against subsequent actual price action.
        """
        now = current_time_ms or int(time.time() * 1000)
        verified_count = 0

        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                """
                SELECT prediction_id, timestamp, symbol, timeframe, target_prices_json,
                       invalidation_price, confidence
                FROM prediction_ledger
                WHERE is_verified = 0 AND timestamp <= (? - 3600 * 1000);
                """,
                (now,),
            )
            pending_rows = cursor.fetchall()

        for r in pending_rows:
            pred_id = r["prediction_id"]
            p_time = r["timestamp"]
            symbol = r["symbol"]
            tf = r["timeframe"]
            conf = r["confidence"]
            inval_p = r["invalidation_price"]
            targets = json.loads(r["target_prices_json"])
            tp1 = targets.get("tp1", inval_p * 1.02)

            # Query forward candles from market database
            with db_manager.get_market_conn() as m_conn:
                m_cur = m_conn.execute(
                    """
                    SELECT timestamp, high, low, close
                    FROM candles
                    WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= (? + 4 * 3600 * 1000)
                    ORDER BY timestamp ASC;
                    """,
                    (symbol, tf, p_time, p_time),
                )
                forward_candles = m_cur.fetchall()

            if not forward_candles:
                continue

            # Determine outcomes
            is_long = tp1 > inval_p
            outcome_5m = "CHOP"
            outcome_1h = "CHOP"
            outcome_4h = "CHOP"

            for c in forward_candles:
                dt_mins = (c["timestamp"] - p_time) / 60000.0
                if is_long:
                    if c["high"] >= tp1:
                        if dt_mins <= 5:
                            outcome_5m = "WIN"
                        if dt_mins <= 60:
                            outcome_1h = "WIN"
                        outcome_4h = "WIN"
                        break
                    elif c["low"] <= inval_p:
                        if dt_mins <= 5:
                            outcome_5m = "LOSS"
                        if dt_mins <= 60:
                            outcome_1h = "LOSS"
                        outcome_4h = "LOSS"
                        break
                else:
                    if c["low"] <= tp1:
                        if dt_mins <= 5:
                            outcome_5m = "WIN"
                        if dt_mins <= 60:
                            outcome_1h = "WIN"
                        outcome_4h = "WIN"
                        break
                    elif c["high"] >= inval_p:
                        if dt_mins <= 5:
                            outcome_5m = "LOSS"
                        if dt_mins <= 60:
                            outcome_1h = "LOSS"
                        outcome_4h = "LOSS"
                        break

            # Calculate individual Brier Score
            binary_outcome = 1.0 if outcome_1h == "WIN" else 0.0
            brier = float((conf - binary_outcome) ** 2)

            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    UPDATE prediction_ledger SET
                        outcome_5m = ?,
                        outcome_1h = ?,
                        outcome_4h = ?,
                        is_verified = 1,
                        brier_score = ?
                    WHERE prediction_id = ?;
                    """,
                    (outcome_5m, outcome_1h, outcome_4h, brier, pred_id),
                )
                conn.commit()
            verified_count += 1

        return verified_count

    def get_recent_ledger(self, limit: int = 50) -> List[Dict[str, Any]]:
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM prediction_ledger
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]


# Singleton
prediction_ledger = PredictionLedger()
