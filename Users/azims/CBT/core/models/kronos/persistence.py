"""
Forecast persistence and freeze ledger for Kronos predictions in SQLite.
Enables immutable point-in-time logging, research replay, and post-hoc accuracy evaluation.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from core.database import db_manager
from core.models.kronos.schemas import KronosForecast

logger = logging.getLogger("ai_quant_sentinel.kronos.persistence")


def freeze_kronos_forecast(forecast: KronosForecast) -> str:
    """
    Freezes a Kronos prediction into experiment_store.db before any market outcome is known.
    Returns the unique forecast_id.
    """
    forecast_id = f"kf_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    paths_data = [p.to_dict() for p in forecast.paths]

    with db_manager.get_experiment_conn() as conn:
        conn.execute(
            """
            INSERT INTO kronos_forecast_ledger (
                forecast_id, timestamp, symbol, timeframe, model_name,
                lookback_bars, horizon_bars, sample_count, current_price,
                expected_return_pct, median_return_pct, predicted_close_mean,
                path_dispersion_pct, directional_consensus, model_uncertainty,
                directional_bias, paths_json, latency_ms, status, is_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                forecast_id,
                forecast.input_end_time,
                forecast.symbol,
                forecast.timeframe,
                forecast.model_name,
                forecast.lookback_bars,
                forecast.prediction_horizon,
                forecast.sample_count,
                forecast.current_price,
                forecast.expected_return_pct,
                forecast.median_return_pct,
                forecast.predicted_close_mean,
                forecast.path_dispersion_pct,
                forecast.directional_consensus,
                forecast.model_uncertainty,
                forecast.directional_bias,
                json.dumps(paths_data),
                forecast.inference_latency_ms,
                forecast.status.value,
            ),
        )
        conn.commit()

    logger.info(
        f"Frozen Kronos forecast {forecast_id} for {forecast.symbol} ({forecast.timeframe})"
    )
    return forecast_id


def get_kronos_forecasts(
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieves frozen forecast history from experiment_store.db."""
    with db_manager.get_experiment_conn() as conn:
        query = "SELECT * FROM kronos_forecast_ledger"
        params: list[Any] = []
        conditions = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            conditions.append("timeframe = ?")
            params.append(timeframe)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def verify_pending_kronos_forecasts(candles_lookup: dict[str, list[dict[str, Any]]]) -> int:
    """
    Evaluates pending frozen Kronos forecasts against realized future candles.
    Updates directional accuracy and realized return metrics.
    """
    with db_manager.get_experiment_conn() as conn:
        cursor = conn.execute(
            """
            SELECT forecast_id, timestamp, symbol, timeframe, current_price,
                   expected_return_pct, directional_bias
            FROM kronos_forecast_ledger
            WHERE is_verified = 0
            ORDER BY timestamp ASC
            LIMIT 100;
            """
        )
        pending = cursor.fetchall()

    if not pending:
        return 0

    verified_count = 0
    with db_manager.get_experiment_conn() as conn:
        for p in pending:
            f_id = p["forecast_id"]
            sym = p["symbol"]
            entry_price = float(p["current_price"])
            pred_bias = p["directional_bias"]
            forecast_time = int(p["timestamp"])

            candles = candles_lookup.get(sym, [])
            # Find candles subsequent to forecast_time
            future_candles = [c for c in candles if int(c["timestamp"]) > forecast_time]
            if not future_candles:
                continue

            # Evaluate forward outcome
            realized_close = float(future_candles[-1]["close"])
            realized_pnl_pct = (realized_close - entry_price) / entry_price

            if pred_bias == "BULLISH":
                outcome = "WIN" if realized_pnl_pct > 0 else "LOSS"
            elif pred_bias == "BEARISH":
                outcome = "WIN" if realized_pnl_pct < 0 else "LOSS"
            else:
                outcome = "FLAT"

            conn.execute(
                """
                UPDATE kronos_forecast_ledger
                SET is_verified = 1,
                    realized_outcome_5m = ?,
                    realized_pnl_usd = ?
                WHERE forecast_id = ?
                """,
                (outcome, realized_pnl_pct, f_id),
            )
            verified_count += 1

        conn.commit()

    return verified_count
