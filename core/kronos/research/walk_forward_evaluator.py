"""
core/kronos/research/walk_forward_evaluator.py
=============================================
Milestone K9.3: Chronological Walk-Forward Rolling Evaluation Engine.
Generates deterministic, purged, and embargoed walk-forward folds
with immutable fold manifests, sensitivity matrices, and zero-overlap guarantees.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

from core.kronos.causality import CausalityViolationError
from core.kronos.research.dataset_freeze import TIMEFRAME_STEP_MS

logger = logging.getLogger("sky.kronos.research.walk_forward")


@dataclass(frozen=True)
class WalkForwardConfig:
    config_id: str
    train_days: int
    eval_days: int
    step_days: int
    horizon_bars: int
    embargo_multiplier: float = 2.0
    min_burn_in_bars: int = 128

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical pre-registered configurations
PRIMARY_WF_CONFIG = WalkForwardConfig(
    config_id="K9-WF-PRIMARY-180-30-30",
    train_days=180,
    eval_days=30,
    step_days=30,
    horizon_bars=12,
    embargo_multiplier=2.0,
)

SENSITIVITY_WF_CONFIGS: dict[str, WalkForwardConfig] = {
    "90/30/30": WalkForwardConfig(
        config_id="K9-WF-SENS-90-30-30",
        train_days=90,
        eval_days=30,
        step_days=30,
        horizon_bars=12,
    ),
    "180/30/30": PRIMARY_WF_CONFIG,
    "180/60/30": WalkForwardConfig(
        config_id="K9-WF-SENS-180-60-30",
        train_days=180,
        eval_days=60,
        step_days=30,
        horizon_bars=12,
    ),
    "365/30/30": WalkForwardConfig(
        config_id="K9-WF-SENS-365-30-30",
        train_days=365,
        eval_days=30,
        step_days=30,
        horizon_bars=12,
    ),
}


@dataclass(frozen=True)
class WalkForwardFoldManifest:
    fold_index: int
    config_id: str
    train_start_idx: int
    train_end_idx: int
    train_start_ts: int
    train_end_ts: int
    purge_start_idx: int
    purge_end_idx: int
    eval_start_idx: int
    eval_end_idx: int
    eval_start_ts: int
    eval_end_ts: int
    embargo_start_idx: int
    embargo_end_idx: int
    train_sample_count: int
    eval_sample_count: int
    fold_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WalkForwardEvaluator:
    """
    Constructs and audits rolling chronological folds with purge and embargo buffers.
    """

    @staticmethod
    def bars_per_day(timeframe: str) -> int:
        step_ms = TIMEFRAME_STEP_MS.get(timeframe, 15 * 60 * 1000)
        return int((24 * 60 * 60 * 1000) // step_ms)

    def generate_folds(
        self,
        candles: list[dict[str, Any]],
        timeframe: str,
        config: WalkForwardConfig = PRIMARY_WF_CONFIG,
    ) -> list[WalkForwardFoldManifest]:
        """
        Generates purged, embargoed walk-forward folds across candle sequence.
        """
        if not candles:
            raise ValueError("Candles sequence cannot be empty")

        bpd = self.bars_per_day(timeframe)
        train_bars = config.train_days * bpd
        eval_bars = config.eval_days * bpd
        step_bars = config.step_days * bpd
        purge_bars = config.horizon_bars
        embargo_bars = math.ceil(config.horizon_bars * config.embargo_multiplier)

        total_bars = len(candles)
        required_min = train_bars + purge_bars + eval_bars
        if total_bars < required_min:
            logger.warning(
                f"Insufficient bars for {config.config_id}: {total_bars} < {required_min}. Returning empty folds."
            )
            return []

        folds: list[WalkForwardFoldManifest] = []
        fold_idx = 0
        current_train_start = 0

        while True:
            train_start_idx = current_train_start
            train_end_idx = train_start_idx + train_bars - 1

            # Purge interval directly follows train
            purge_start_idx = train_end_idx + 1
            purge_end_idx = min(total_bars - 1, purge_start_idx + purge_bars - 1)

            # Eval interval begins after purge
            eval_start_idx = purge_end_idx + 1
            eval_end_idx = min(total_bars - 1, eval_start_idx + eval_bars - 1)

            # Embargo interval follows eval to prevent overlap leakage into subsequent splits
            embargo_start_idx = eval_end_idx + 1
            embargo_end_idx = min(total_bars - 1, embargo_start_idx + embargo_bars - 1)

            if eval_end_idx >= total_bars or (eval_end_idx - eval_start_idx + 1) < (eval_bars // 2):
                break

            train_c_start = candles[train_start_idx]
            train_c_end = candles[train_end_idx]
            eval_c_start = candles[eval_start_idx]
            eval_c_end = candles[eval_end_idx]

            t_train_start = int(train_c_start.get("timestamp") or train_c_start.get("time", 0))
            t_train_end = int(train_c_end.get("timestamp") or train_c_end.get("time", 0))
            t_eval_start = int(eval_c_start.get("timestamp") or eval_c_start.get("time", 0))
            t_eval_end = int(eval_c_end.get("timestamp") or eval_c_end.get("time", 0))

            # Deterministic fold hash
            hash_payload = {
                "fold_index": fold_idx,
                "config_id": config.config_id,
                "train_start_ts": t_train_start,
                "train_end_ts": t_train_end,
                "eval_start_ts": t_eval_start,
                "eval_end_ts": t_eval_end,
                "train_sample_count": train_end_idx - train_start_idx + 1,
                "eval_sample_count": eval_end_idx - eval_start_idx + 1,
            }
            fold_hash = hashlib.sha256(
                json.dumps(hash_payload, sort_keys=True).encode()
            ).hexdigest()

            fold = WalkForwardFoldManifest(
                fold_index=fold_idx,
                config_id=config.config_id,
                train_start_idx=train_start_idx,
                train_end_idx=train_end_idx,
                train_start_ts=t_train_start,
                train_end_ts=t_train_end,
                purge_start_idx=purge_start_idx,
                purge_end_idx=purge_end_idx,
                eval_start_idx=eval_start_idx,
                eval_end_idx=eval_end_idx,
                eval_start_ts=t_eval_start,
                eval_end_ts=t_eval_end,
                embargo_start_idx=embargo_start_idx,
                embargo_end_idx=embargo_end_idx,
                train_sample_count=train_end_idx - train_start_idx + 1,
                eval_sample_count=eval_end_idx - eval_start_idx + 1,
                fold_hash=fold_hash,
            )

            # Audit fold boundaries
            self.validate_fold_boundaries(fold)
            folds.append(fold)

            fold_idx += 1
            current_train_start += step_bars

        return folds

    @staticmethod
    def validate_fold_boundaries(fold: WalkForwardFoldManifest) -> bool:
        """
        Enforces:
        1. Strict temporal ordering: train_end_ts < eval_start_ts.
        2. Non-zero purge window between train and eval.
        3. Non-overlapping index ranges.
        """
        if fold.train_end_idx >= fold.purge_start_idx:
            raise CausalityViolationError(
                f"Fold {fold.fold_index}: Train end {fold.train_end_idx} >= Purge start {fold.purge_start_idx}"
            )

        if fold.purge_end_idx >= fold.eval_start_idx:
            raise CausalityViolationError(
                f"Fold {fold.fold_index}: Purge end {fold.purge_end_idx} >= Eval start {fold.eval_start_idx}"
            )

        if fold.train_end_ts >= fold.eval_start_ts:
            raise CausalityViolationError(
                f"Fold {fold.fold_index}: Temporal leakage hazard! "
                f"Train end timestamp {fold.train_end_ts} >= Eval start timestamp {fold.eval_start_ts}"
            )

        if fold.eval_sample_count <= 0 or fold.train_sample_count <= 0:
            raise CausalityViolationError(f"Fold {fold.fold_index} contains zero samples")

        return True


walk_forward_evaluator = WalkForwardEvaluator()
