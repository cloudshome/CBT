"""
core/kronos/research/research_routes.py
======================================
Milestone K9 API: Read-Only Research & Reproducibility Endpoints.
Exposes tournament scorecards, incremental information deltas, regime breakdowns,
ablation results, friction reports, experiment ledger queries, and reproducibility checks.
Constitutional Invariant: ZERO order dispatch, trade authorization, or execution controls.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.data_streamer import data_streamer
from core.kronos.research.ablation_matrix import ablation_matrix_engine
from core.kronos.research.baseline_registry import baseline_registry
from core.kronos.research.dataset_freeze import dataset_freeze_manager
from core.kronos.research.experiment_ledger import research_experiment_ledger
from core.kronos.research.feature_label_contract import feature_label_validator
from core.kronos.research.forecast_validity import forecast_validity_engine
from core.kronos.research.friction_evaluator import friction_evaluator
from core.kronos.research.orthogonality_tester import orthogonality_tester
from core.kronos.research.promotion_gate import promotion_gate
from core.kronos.research.regime_analyzer import regime_analyzer
from core.kronos.research.reproducibility import reproducibility_engine

logger = logging.getLogger("sky.kronos.research.routes")

research_router = APIRouter(tags=["Kronos Research & Predictive Validity"])


def _get_candles_helper(symbol: str, timeframe: str, count: int = 150) -> list[dict[str, Any]]:
    norm_sym = symbol.replace("USDT", "/USDT") if "/" not in symbol else symbol
    try:
        candles = data_streamer.generate_synthetic_candles(norm_sym, timeframe, count=count)
        if not candles or len(candles) < 30:
            raise ValueError("Insufficient candle history")
        return candles
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load candle history: {e}") from e


@research_router.get("/tournament")
def get_baseline_tournament(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    horizon: int = Query(12, ge=1, le=48),
    lookback: int = Query(100, ge=30, le=300),
) -> dict[str, Any]:
    """
    Executes standardized competitive tournament across all benchmark models on identical observations.
    """
    candles = _get_candles_helper(symbol, timeframe, count=lookback + horizon + 20)
    n_eval = min(lookback, len(candles) - horizon - 1)

    labels: list[int] = []
    eval_indices: list[int] = []

    for i in range(n_eval):
        idx = len(candles) - horizon - 1 - i
        lbl, _, _ = feature_label_validator.construct_causal_binary_label(candles, idx, horizon)
        labels.append(lbl)
        eval_indices.append(idx)

    labels.reverse()
    eval_indices.reverse()

    model_scores: list[dict[str, Any]] = []
    clim_probs: list[float] = []

    # 1. Run Climatology first to get reference base rate
    m_clim = baseline_registry.get("M_CLIM")
    train_slice = candles[: eval_indices[0]]
    train_labels = [
        feature_label_validator.construct_causal_binary_label(candles, j, horizon)[0]
        for j in range(len(train_slice) - horizon)
    ]
    m_clim.fit(train_slice, train_labels)
    clim_probs = [m_clim.predict_probability(candles, idx) for idx in eval_indices]

    for model_meta in baseline_registry.list_models():
        m_id = model_meta["model_id"]
        model = baseline_registry.get(m_id)
        if model_meta["is_trainable"]:
            model.fit(train_slice, train_labels)

        probs = [model.predict_probability(candles, idx) for idx in eval_indices]
        validity = forecast_validity_engine.evaluate_predictions(
            probabilities=probs,
            labels=labels,
            reference_probabilities=clim_probs,
            model_id=m_id,
            horizon_bars=horizon,
            n_bootstraps=50,
        )
        model_scores.append(validity.to_dict())

    # Sort tournament by Brier Skill Score descending
    model_scores.sort(key=lambda x: x["brier_skill_score"], reverse=True)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon_bars": horizon,
        "sample_size": len(labels),
        "rankings": model_scores,
    }


@research_router.get("/incremental")
def get_incremental_information(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    horizon: int = Query(12, ge=1, le=48),
    lookback: int = Query(100, ge=30, le=300),
) -> dict[str, Any]:
    """
    Evaluates out-of-sample incremental information (Delta Brier, Delta LogLoss, Mincer-Zarnowitz regression).
    """
    candles = _get_candles_helper(symbol, timeframe, count=lookback + horizon + 20)
    n_eval = min(lookback, len(candles) - horizon - 1)

    labels: list[int] = []
    eval_indices: list[int] = []

    for i in range(n_eval):
        idx = len(candles) - horizon - 1 - i
        lbl, _, _ = feature_label_validator.construct_causal_binary_label(candles, idx, horizon)
        labels.append(lbl)
        eval_indices.append(idx)

    labels.reverse()
    eval_indices.reverse()

    m_sky = baseline_registry.get("M_SKY_TECH")
    p_sky = [m_sky.predict_probability(candles, idx) for idx in eval_indices]

    # Kronos probability with mild microstructure modulation
    m_smc = baseline_registry.get("M_SKY_SMC")
    p_kronos = [m_smc.predict_probability(candles, idx) for idx in eval_indices]

    report = orthogonality_tester.evaluate_incremental_information(
        base_probabilities=p_sky,
        kronos_probabilities=p_kronos,
        labels=labels,
        base_model_id="M_SKY_TECHNICAL",
        composite_model_id="M_SKY_PLUS_KRONOS",
        horizon_bars=horizon,
    )
    return report.to_dict()


@research_router.get("/regimes")
def get_regime_breakdown(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    horizon: int = Query(12, ge=1, le=48),
    lookback: int = Query(100, ge=40, le=300),
) -> dict[str, Any]:
    """
    Stratifies out-of-sample performance across Volatility, Trend, and Session regimes.
    """
    candles = _get_candles_helper(symbol, timeframe, count=lookback + horizon + 20)
    n_eval = min(lookback, len(candles) - horizon - 1)

    labels: list[int] = []
    eval_indices: list[int] = []

    for i in range(n_eval):
        idx = len(candles) - horizon - 1 - i
        lbl, _, _ = feature_label_validator.construct_causal_binary_label(candles, idx, horizon)
        labels.append(lbl)
        eval_indices.append(idx)

    labels.reverse()
    eval_indices.reverse()

    m_kronos = baseline_registry.get("M_SKY_SMC")
    probs = [m_kronos.predict_probability(candles, idx) for idx in eval_indices]

    reports = regime_analyzer.evaluate_regimes(probs, labels, candles, eval_indices)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "sample_size": len(labels),
        "regime_slices": [r.to_dict() for r in reports],
    }


@research_router.get("/ablation")
def get_ablation_matrix(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    horizon: int = Query(12, ge=1, le=48),
    lookback: int = Query(100, ge=30, le=300),
) -> dict[str, Any]:
    """
    Evaluates 7-way microstructure ablation tournament (Variants A through G).
    """
    candles = _get_candles_helper(symbol, timeframe, count=lookback + horizon + 20)
    n_eval = min(lookback, len(candles) - horizon - 1)

    labels: list[int] = []
    eval_indices: list[int] = []

    for i in range(n_eval):
        idx = len(candles) - horizon - 1 - i
        lbl, _, _ = feature_label_validator.construct_causal_binary_label(candles, idx, horizon)
        labels.append(lbl)
        eval_indices.append(idx)

    labels.reverse()
    eval_indices.reverse()

    # Raw foundation probabilities
    raw_probs = [
        baseline_registry.get("M_MOM").predict_probability(candles, idx) for idx in eval_indices
    ]

    # Synthesize causal microstructure contexts
    contexts: list[dict[str, float]] = []
    for idx in eval_indices:
        c = candles[idx]
        o = float(c.get("open") or c.get("o", 0.0))
        cl = float(c.get("close") or c.get("c", 0.0))
        h = float(c.get("high") or c.get("h", 0.0))
        lo = float(c.get("low") or c.get("l", 0.0))
        rng = max(1e-6, h - lo)
        contexts.append(
            {
                "ofi_norm": (cl - o) / rng,
                "vpin": 0.20,
                "depth_imb": 0.10,
                "resting_wall": (h - max(o, cl) - (min(o, cl) - lo)) / rng,
                "trade_sign": 0.05,
                "mid_return": (cl - o) / o if o > 0 else 0.0,
                "spread_bps": 2.5,
                "vol_clock": 0.015,
            }
        )

    results = ablation_matrix_engine.evaluate_ablation_matrix(raw_probs, contexts, labels)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "sample_size": len(labels),
        "ablation_variants": [r.to_dict() for r in results],
    }


@research_router.get("/promotion-status")
def get_promotion_status(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("15m"),
    horizon: int = Query(12, ge=1, le=48),
    lookback: int = Query(120, ge=100, le=500),
) -> dict[str, Any]:
    """
    Evaluates master research governance scorecard and returns PROMOTE, QUARANTINE, REJECT, or INCONCLUSIVE.
    """
    candles = _get_candles_helper(symbol, timeframe, count=lookback + horizon + 20)
    n_eval = min(lookback, len(candles) - horizon - 1)

    labels: list[int] = []
    returns: list[float] = []
    eval_indices: list[int] = []

    for i in range(n_eval):
        idx = len(candles) - horizon - 1 - i
        lbl, ret, _ = feature_label_validator.construct_causal_binary_label(candles, idx, horizon)
        labels.append(lbl)
        returns.append(ret)
        eval_indices.append(idx)

    labels.reverse()
    returns.reverse()
    eval_indices.reverse()

    m_sky = baseline_registry.get("M_SKY_TECH")
    m_kronos = baseline_registry.get("M_SKY_SMC")
    p_sky = [m_sky.predict_probability(candles, idx) for idx in eval_indices]
    p_kronos = [m_kronos.predict_probability(candles, idx) for idx in eval_indices]

    validity = forecast_validity_engine.evaluate_predictions(
        probabilities=p_kronos,
        labels=labels,
        model_id="KRONOS_MICRO_ADAPTED",
        horizon_bars=horizon,
    )

    incremental = orthogonality_tester.evaluate_incremental_information(
        base_probabilities=p_sky,
        kronos_probabilities=p_kronos,
        labels=labels,
        horizon_bars=horizon,
    )

    friction = friction_evaluator.evaluate_hypothetical_utility(
        probabilities=p_kronos,
        realized_returns=returns,
        cumulative_trials=research_experiment_ledger.get_cumulative_trial_count() + 1,
        model_id="KRONOS_MICRO_ADAPTED",
        horizon_bars=horizon,
    )

    regimes = regime_analyzer.evaluate_regimes(p_kronos, labels, candles, eval_indices)

    report = promotion_gate.evaluate_promotion(validity, incremental, friction, regimes)
    return report.to_dict()


@research_router.get("/experiments")
def list_experiments(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """
    Lists recorded experiments from the immutable SQLite research ledger.
    """
    experiments = research_experiment_ledger.list_experiments(limit=limit)
    return {
        "count": len(experiments),
        "cumulative_trials": research_experiment_ledger.get_cumulative_trial_count(),
        "experiments": experiments,
    }


@research_router.get("/reproducibility")
def verify_reproducibility(experiment_id: str = Query(...)) -> dict[str, Any]:
    """
    Replays an experiment by ID and certifies numerical reproducibility.
    """
    report = reproducibility_engine.replay_experiment(experiment_id)
    return report.to_dict()


@research_router.get("/manifests")
def list_dataset_manifests() -> dict[str, Any]:
    """
    Lists all frozen dataset manifests with cryptographic hashes.
    """
    manifest = dataset_freeze_manager.load_manifest()
    return {
        "dataset_count": len(manifest),
        "manifests": manifest,
    }
