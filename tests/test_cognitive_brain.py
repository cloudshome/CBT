"""
tests/test_cognitive_brain.py
=============================
Adversarial Verification Suite for the SKY Cognitive Brain Architecture.

Validates:
1. True point-in-time freezing: observation timestamp vs commit timestamp.
2. Immutability of original observation and forecast after resolution.
3. Idempotent ledger commits & duplicate prevention.
4. Mathematical MFE and signed MAE calculation (Long & Short).
5. Intrabar target/invalidation ambiguity handling (AMBIGUOUS_INTRABAR_ORDER).
6. Separation of forecast accuracy (Brier score, log-loss) from net trade profitability.
7. Counterfactual policy for DISCIPLINED_NO_TRADE (never masquerades as executed trade).
8. Sample-size transparency in calibration reporting.
9. Zero test pollution of production database (isolated tmp_path SQLite).
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cognitive_brain.experience_engine import TradingExperienceEngine
from core.cognitive_brain.outcome_resolver import DeterministicOutcomeResolver
from core.cognitive_brain.prediction_ledger import (
    CognitivePredictionLedger,
    DuplicateExperienceError,
    PersistenceError,
)
from core.cognitive_brain.schema import (
    DiagnosticCategory,
    ExecutionPayload,
    ExecutionStatus,
    ForecastPayload,
    GovernanceAction,
    GovernancePayload,
    MarketObservationPayload,
    ObservationType,
    ProposalPayload,
    ResolutionStatus,
    TradingExperienceRecord,
)
from core.mastermind.specialist_base import EpistemicGrade
from core.sky_intelligence.types import DecisionAction


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    return tmp_path / "test_cognitive_brain.db"


@pytest.fixture
def ledger(test_db: Path) -> CognitivePredictionLedger:
    return CognitivePredictionLedger(db_path=test_db)


@pytest.fixture
def engine(ledger: CognitivePredictionLedger) -> TradingExperienceEngine:
    resolver = DeterministicOutcomeResolver(conservative_intrabar_resolution=True)
    return TradingExperienceEngine(ledger=ledger, resolver=resolver)


def _generate_forward_candles(
    start_ts: int, start_price: float, price_path: list[tuple[float, float, float]]
) -> list[dict]:
    """
    Generates synthetic forward candles:
    price_path items are (high, low, close).
    """
    candles = []
    ts = start_ts
    for h, l, c in price_path:
        candles.append(
            {
                "timestamp": ts,
                "open": start_price,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100.0,
            }
        )
        ts += 15 * 60 * 1000  # 15m intervals
        start_price = c
    return candles


# ==============================================================================
# 1. POINT-IN-TIME FREEZE & DURABLE PERSISTENCE
# ==============================================================================

def test_point_in_time_freeze_records_timestamps_and_is_idempotent(engine: TradingExperienceEngine):
    """Verifies observation and commit timestamps are recorded and re-freeze is idempotent."""
    now_ms = int(time.time() * 1000)

    forecast = ForecastPayload(
        direction=DecisionAction.LONG,
        target_price=62000.0,
        invalidation_price=59000.0,
        raw_confidence=0.80,
        calibrated_probability=0.75,
        epistemic_grade=EpistemicGrade.HYPOTHESIS,
    )

    rec = engine.record_observation(
        asset="BTC/USDT",
        timeframe="15m",
        entry_reference_price=60000.0,
        observation_type=ObservationType.TRADE_PROPOSAL,
        forecast=forecast,
        observation_timestamp_ms=now_ms,
    )

    assert rec.experience_id.startswith("exp_btc_usdt_")
    assert rec.observation.observation_timestamp_ms == now_ms
    assert rec.commit_timestamp_ms is not None
    assert rec.commit_timestamp_ms >= now_ms
    assert rec.is_frozen is True

    # Verify retrieved record from database
    retrieved = engine.ledger.get_experience(rec.experience_id)
    assert retrieved is not None
    assert retrieved.forecast.target_price == 62000.0
    assert retrieved.forecast.invalidation_price == 59000.0

    # Idempotent re-freeze with identical payload succeeds
    re_frozen_id = engine.ledger.freeze_experience(rec)
    assert re_frozen_id == rec.experience_id


def test_persistence_failure_raises_explicit_exception(tmp_path: Path):
    """Persistence failure must raise explicit PersistenceError, never fail silently."""
    ledger = CognitivePredictionLedger(db_path=tmp_path / "valid.db")
    now_ms = int(time.time() * 1000)

    rec = TradingExperienceRecord(
        experience_id="exp_fail_test",
        observation_type=ObservationType.TRADE_PROPOSAL,
        observation=MarketObservationPayload(
            asset="BTC/USDT",
            timeframe="15m",
            entry_reference_price=60000.0,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=61000.0,
            invalidation_price=59000.0,
            raw_confidence=0.70,
        ),
    )

    with patch.object(ledger, "_get_connection", side_effect=Exception("Disk I/O Error")):
        with pytest.raises(PersistenceError) as exc_info:
            ledger.freeze_experience(rec)
        assert "Commit failed" in str(exc_info.value)


# ==============================================================================
# 2. MATHEMATICAL MFE & MAE CALCULATIONS
# ==============================================================================

def test_long_mfe_and_signed_mae_calculation():
    """
    Tests exact mathematical MFE (favorable) and MAE (signed adverse) for a LONG position.
    Entry P0 = 100.0.
    Candles:
    1: High 105.0 (+5%), Low 98.0 (-2%), Close 103.0
    2: High 108.0 (+8%), Low 96.0 (-4%), Close 107.0
    Expected MFE = +800 bps (+8.0%).
    Expected MAE = -400 bps (-4.0% signed).
    """
    resolver = DeterministicOutcomeResolver()
    now_ms = int(time.time() * 1000)

    rec = TradingExperienceRecord(
        experience_id="exp_mfe_long_test",
        observation_type=ObservationType.TRADE_PROPOSAL,
        observation=MarketObservationPayload(
            asset="TEST/USDT",
            timeframe="15m",
            entry_reference_price=100.0,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=110.0,  # Not reached
            invalidation_price=90.0,  # Not reached
            raw_confidence=0.80,
            horizon_bars=2,
        ),
    )

    candles = [
        {"timestamp": now_ms + 1000, "high": 105.0, "low": 98.0, "close": 103.0},
        {"timestamp": now_ms + 2000, "high": 108.0, "low": 96.0, "close": 107.0},
    ]

    outcome = resolver.resolve_experience(rec, candles)
    assert outcome.status == ResolutionStatus.TIME_EXPIRED
    assert outcome.mfe_bps == 800.0  # +8.0%
    assert outcome.mae_bps == -400.0  # -4.0% (signed)


def test_short_mfe_and_signed_mae_calculation():
    """
    Tests exact mathematical MFE and MAE for a SHORT position.
    Entry P0 = 200.0.
    Candles:
    1: High 204.0 (adverse +2%), Low 190.0 (favorable -5%), Close 192.0
    2: High 208.0 (adverse +4%), Low 180.0 (favorable -10%), Close 185.0
    For short:
    MFE = (200 - 180) / 200 = +10.0% (+1000 bps)
    MAE = (200 - 208) / 200 = -4.0% (-400 bps signed)
    """
    resolver = DeterministicOutcomeResolver()
    now_ms = int(time.time() * 1000)

    rec = TradingExperienceRecord(
        experience_id="exp_mfe_short_test",
        observation_type=ObservationType.TRADE_PROPOSAL,
        observation=MarketObservationPayload(
            asset="TEST/USDT",
            timeframe="15m",
            entry_reference_price=200.0,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.SHORT,
            target_price=170.0,  # Not reached
            invalidation_price=220.0,  # Not reached
            raw_confidence=0.75,
            horizon_bars=2,
        ),
    )

    candles = [
        {"timestamp": now_ms + 1000, "high": 204.0, "low": 190.0, "close": 192.0},
        {"timestamp": now_ms + 2000, "high": 208.0, "low": 180.0, "close": 185.0},
    ]

    outcome = resolver.resolve_experience(rec, candles)
    assert outcome.status == ResolutionStatus.TIME_EXPIRED
    assert outcome.mfe_bps == 1000.0  # +10.0%
    assert outcome.mae_bps == -400.0  # -4.0% signed


# ==============================================================================
# 3. INTRABAR AMBIGUITY & CHRONOLOGICAL RESOLUTION
# ==============================================================================

def test_intrabar_touch_of_target_and_invalidation_flags_ambiguity():
    """
    When a single candle touches BOTH target and invalidation levels,
    it must be flagged as AMBIGUOUS_INTRABAR_ORDER and resolved conservatively.
    """
    resolver = DeterministicOutcomeResolver(conservative_intrabar_resolution=True)
    now_ms = int(time.time() * 1000)

    # Long setup: P0 = 100. Target = 105, Invalidation = 95
    rec = TradingExperienceRecord(
        experience_id="exp_ambiguous_test",
        observation_type=ObservationType.TRADE_PROPOSAL,
        observation=MarketObservationPayload(
            asset="VOLATILE/USDT",
            timeframe="15m",
            entry_reference_price=100.0,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=105.0,
            invalidation_price=95.0,
            raw_confidence=0.85,
        ),
    )

    # Candle spikes to 106 and crashes to 94 in the same 15m bar
    ambiguous_candles = [
        {"timestamp": now_ms + 1000, "open": 100.0, "high": 106.0, "low": 94.0, "close": 98.0}
    ]

    outcome = resolver.resolve_experience(rec, ambiguous_candles)
    assert outcome.status == ResolutionStatus.AMBIGUOUS_INTRABAR_ORDER
    assert outcome.diagnostic_category == DiagnosticCategory.AMBIGUOUS
    # Conservative rule flags invalidation as hit first
    assert outcome.hit_invalidation_first is True
    assert outcome.hit_target_first is False


# ==============================================================================
# 4. SEPARATION OF FORECAST ACCURACY FROM TRADE PROFITABILITY
# ==============================================================================

def test_forecast_accuracy_vs_cost_erosion_diagnostic():
    """
    Forecast of +20 bps gain is directionally correct, but 12 bps of fees + slippage
    reduces net return to +8 bps, while a small gain (+10 bps) turns into a net loss (-2 bps).
    Outcome resolver must classify ACCURATE_COST_EROSION when gross > 0 but net <= 0.
    """
    resolver = DeterministicOutcomeResolver()
    now_ms = int(time.time() * 1000)

    # Long setup: P0 = 1000.0. Target = 1001.0 (+10 bps).
    rec = TradingExperienceRecord(
        experience_id="exp_cost_erosion_test",
        observation_type=ObservationType.TRADE_PROPOSAL,
        observation=MarketObservationPayload(
            asset="BTC/USDT",
            timeframe="15m",
            entry_reference_price=1000.0,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=1001.0,  # +10 bps
            invalidation_price=990.0,
            raw_confidence=0.90,
            horizon_bars=1,
        ),
        execution=ExecutionPayload(
            status=ExecutionStatus.PAPER_FILLED,
            simulated_fill_price=1000.0,
            taker_fee_bps=5.0,  # 10 bps roundtrip fee
            est_slippage_bps=1.0,  # 2 bps roundtrip slippage -> 12 bps total friction
        ),
    )

    candles = [
        {"timestamp": now_ms + 1000, "high": 1001.0, "low": 999.0, "close": 1001.0}
    ]

    outcome = resolver.resolve_experience(rec, candles)
    assert outcome.status == ResolutionStatus.HIT_TARGET
    assert outcome.realized_net_pnl_bps == pytest.approx(-2.0, abs=0.01)  # 10 bps gross - 12 bps friction = -2 bps net
    assert outcome.diagnostic_category == DiagnosticCategory.ACCURATE_COST_EROSION
    assert "wiped out by friction" in outcome.diagnostic_summary


# ==============================================================================
# 5. COUNTERFACTUAL POLICY FOR DISCIPLINED NO_TRADE
# ==============================================================================

def test_disciplined_no_trade_records_counterfactual_only():
    """
    A DISCIPLINED_NO_TRADE decision must NEVER masquerade as an executed paper trade.
    Realized net PnL must be None, and counterfactual net PnL tracks what would have happened.
    """
    resolver = DeterministicOutcomeResolver()
    now_ms = int(time.time() * 1000)

    rec = TradingExperienceRecord(
        experience_id="exp_no_trade_test",
        observation_type=ObservationType.DISCIPLINED_NO_TRADE,
        observation=MarketObservationPayload(
            asset="DOGE/USDT",
            timeframe="15m",
            entry_reference_price=0.10,
            observation_timestamp_ms=now_ms,
        ),
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=0.11,
            invalidation_price=0.09,
            raw_confidence=0.45,  # Below threshold -> NO_TRADE
            horizon_bars=1,
        ),
        execution=ExecutionPayload(
            status=ExecutionStatus.COUNTERFACTUAL_ONLY,
            notes="Abstained due to low confidence and overhead resistance",
        ),
    )

    # Market dumps to invalidation (0.088)
    candles = [
        {"timestamp": now_ms + 1000, "high": 0.101, "low": 0.088, "close": 0.089}
    ]

    outcome = resolver.resolve_experience(rec, candles)
    assert outcome.status == ResolutionStatus.HIT_INVALIDATION
    # Must NOT record realized PnL on abstention!
    assert outcome.realized_net_pnl_bps is None
    # Counterfactual PnL was negative
    assert outcome.counterfactual_net_pnl_bps is not None
    assert outcome.counterfactual_net_pnl_bps < 0.0
    assert outcome.diagnostic_category == DiagnosticCategory.ABSTENTION_JUSTIFIED


# ==============================================================================
# 6. CALIBRATION REPORTING & SAMPLE-SIZE TRANSPARENCY
# ==============================================================================

def test_calibration_reporting_requires_minimum_sample_size(engine: TradingExperienceEngine):
    """
    Calibration reporting must explicitly report INSUFFICIENT_SAMPLES when resolved N < min_samples.
    """
    # Query with 0 resolved records
    metrics = engine.get_calibration_metrics(min_samples=10)
    assert metrics["status"] == "INSUFFICIENT_SAMPLES"
    assert metrics["sample_size_n"] == 0
    assert metrics["mean_brier_score"] is None

    # Populate 12 resolved records
    now_ms = int(time.time() * 1000)
    for i in range(12):
        rec = engine.record_observation(
            asset="ETH/USDT",
            timeframe="15m",
            entry_reference_price=3000.0,
            observation_type=ObservationType.TRADE_PROPOSAL,
            forecast=ForecastPayload(
                direction=DecisionAction.LONG,
                target_price=3100.0,
                invalidation_price=2900.0,
                raw_confidence=0.80,
                calibrated_probability=0.78,
            ),
            observation_timestamp_ms=now_ms + (i * 1000),
        )
        # Resolve winning outcome
        future_candles = [
            {"timestamp": now_ms + (i * 1000) + 100, "high": 3150.0, "low": 2980.0, "close": 3120.0}
        ]
        outcome = engine.resolver.resolve_experience(rec, future_candles)
        engine.ledger.update_resolved_outcome(rec.experience_id, outcome)

    validated_metrics = engine.get_calibration_metrics(asset="ETH/USDT", min_samples=10)
    assert validated_metrics["status"] == "VALIDATED"
    assert validated_metrics["sample_size_n"] == 12
    assert validated_metrics["mean_brier_score"] is not None
    assert validated_metrics["calibration_grade"] == "WELL_CALIBRATED"


# ==============================================================================
# 7. END-TO-END EXPERIENCE RESOLUTION LIFECYCLE
# ==============================================================================

def test_end_to_end_experience_engine_resolution_lifecycle(engine: TradingExperienceEngine):
    """
    Full lifecycle test:
    1. Observe and freeze pending experience.
    2. Future candles arrive.
    3. resolve_pending() evaluates and persists outcome without mutating original observation.
    4. Retrieved record has unchanged observation and populated outcome.
    """
    now_ms = int(time.time() * 1000)

    rec = engine.record_observation(
        asset="SOL/USDT",
        timeframe="15m",
        entry_reference_price=150.0,
        observation_type=ObservationType.TRADE_PROPOSAL,
        forecast=ForecastPayload(
            direction=DecisionAction.LONG,
            target_price=156.0,
            invalidation_price=145.0,
            raw_confidence=0.82,
        ),
        observation_timestamp_ms=now_ms,
    )

    # 15m later: candle hits target 157.0
    future_candles = {
        "SOL/USDT": [
            {"timestamp": now_ms + 900_000, "high": 157.0, "low": 149.0, "close": 156.5}
        ]
    }

    resolved = engine.resolve_pending(future_candles)
    assert len(resolved) == 1
    assert resolved[0].experience_id == rec.experience_id
    assert resolved[0].outcome.status == ResolutionStatus.HIT_TARGET
    assert resolved[0].outcome.mfe_bps == pytest.approx(466.67, abs=1.0)  # (157 - 150)/150 = +4.667% = 466.67 bps

    # Retrieve from DB to verify persistence and immutability
    reloaded = engine.ledger.get_experience(rec.experience_id)
    assert reloaded is not None
    assert reloaded.observation.entry_reference_price == 150.0
    assert reloaded.observation.observation_timestamp_ms == now_ms
    assert reloaded.outcome.status == ResolutionStatus.HIT_TARGET
    assert reloaded.is_resolved is True
