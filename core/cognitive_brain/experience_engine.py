"""
core/cognitive_brain/experience_engine.py
========================================
Unified Cognitive Experience Engine for SKY / CBT.

Coordinates the end-to-end cognitive loop:
1. Observe market state & record directional forecast / disciplined NO_TRADE.
2. Freeze experience record into CognitivePredictionLedger before future unfolds.
3. Pass proposal through deterministic risk governance (never bypassing Guard 1).
4. Resolve forward outcomes objectively (MFE, MAE, Brier score, log-loss, net PnL).
5. Expose empirical calibration statistics with strict sample-size transparency.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from core.cognitive_brain.outcome_resolver import DeterministicOutcomeResolver
from core.cognitive_brain.prediction_ledger import CognitivePredictionLedger
from core.cognitive_brain.schema import (
    ExecutionPayload,
    ForecastPayload,
    GovernancePayload,
    MarketObservationPayload,
    ObservationType,
    ProposalPayload,
    TradingExperienceRecord,
)

logger = logging.getLogger("ai_quant_sentinel.cognitive_brain.experience_engine")


class TradingExperienceEngine:
    """
    Coordinates immutable prediction freezing, outcome resolution, and calibration tracking.
    """

    def __init__(
        self,
        ledger: CognitivePredictionLedger | None = None,
        resolver: DeterministicOutcomeResolver | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.ledger = ledger or CognitivePredictionLedger(db_path=db_path)
        self.resolver = resolver or DeterministicOutcomeResolver()

    def record_observation(
        self,
        asset: str,
        timeframe: str,
        entry_reference_price: float,
        observation_type: ObservationType,
        forecast: ForecastPayload,
        proposal: ProposalPayload | None = None,
        governance: GovernancePayload | None = None,
        execution: ExecutionPayload | None = None,
        features: dict[str, Any] | None = None,
        state_vector_hash: str = "",
        observation_timestamp_ms: int | None = None,
    ) -> TradingExperienceRecord:
        """
        Creates and durably commits a frozen TradingExperienceRecord before outcome resolution.
        """
        now_ms = observation_timestamp_ms or int(time.time() * 1000)
        exp_id = f"exp_{asset.replace('/', '_').lower()}_{now_ms}_{uuid.uuid4().hex[:6]}"

        obs_payload = MarketObservationPayload(
            asset=asset,
            timeframe=timeframe,
            entry_reference_price=entry_reference_price,
            observation_timestamp_ms=now_ms,
            state_vector_hash=state_vector_hash,
            features=features or {},
        )

        record = TradingExperienceRecord(
            experience_id=exp_id,
            observation_type=observation_type,
            created_at_ms=now_ms,
            observation=obs_payload,
            forecast=forecast,
            proposal=proposal,
            governance=governance,
            execution=execution,
        )

        # Durable point-in-time freeze (raises PersistenceError if disk write fails)
        self.ledger.freeze_experience(record)
        return record

    def resolve_pending(
        self,
        candles_by_asset: dict[str, list[dict[str, Any]]],
        before_ts_ms: int | None = None,
    ) -> list[TradingExperienceRecord]:
        """
        Scans unverified experiences and resolves them against provided future candles.
        """
        pending = self.ledger.get_pending_experiences(before_ts_ms=before_ts_ms)
        resolved_records: list[TradingExperienceRecord] = []

        for exp in pending:
            candles = candles_by_asset.get(exp.observation.asset, [])
            if not candles:
                continue

            outcome = self.resolver.resolve_experience(exp, candles)
            if outcome.status.value != "PENDING":
                self.ledger.update_resolved_outcome(exp.experience_id, outcome)
                exp.outcome = outcome
                exp.is_resolved = True
                resolved_records.append(exp)

        return resolved_records

    def get_calibration_metrics(
        self, asset: str | None = None, min_samples: int = 10
    ) -> dict[str, Any]:
        """
        Evaluates Brier score and log-loss calibration with denominator transparency.
        Returns INSUFFICIENT_SAMPLES when resolved sample count < min_samples.
        """
        with self.ledger._get_connection() as conn:
            query = """
                SELECT brier_score, log_loss, mfe_bps, mae_bps, realized_net_pnl_bps,
                       counterfactual_net_pnl_bps, resolution_status, diagnostic_category
                FROM cognitive_experience_ledger
                WHERE resolution_status != 'PENDING' AND brier_score IS NOT NULL
            """
            params: list[Any] = []
            if asset:
                query += " AND asset = ?"
                params.append(asset)

            rows = conn.execute(query, tuple(params)).fetchall()

        n = len(rows)
        if n < min_samples:
            return {
                "status": "INSUFFICIENT_SAMPLES",
                "sample_size_n": n,
                "required_n": min_samples,
                "mean_brier_score": None,
                "mean_log_loss": None,
                "notes": f"Evaluation requires N >= {min_samples} resolved experiences.",
            }

        brier_scores = [r["brier_score"] for r in rows if r["brier_score"] is not None]
        log_losses = [r["log_loss"] for r in rows if r["log_loss"] is not None]

        mean_brier = sum(brier_scores) / len(brier_scores) if brier_scores else None
        mean_ll = sum(log_losses) / len(log_losses) if log_losses else None

        return {
            "status": "VALIDATED",
            "sample_size_n": n,
            "mean_brier_score": round(mean_brier, 4) if mean_brier is not None else None,
            "mean_log_loss": round(mean_ll, 4) if mean_ll is not None else None,
            "calibration_grade": "WELL_CALIBRATED" if mean_brier and mean_brier < 0.20 else "DEGRADED",
        }
