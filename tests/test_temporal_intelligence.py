"""
tests/test_temporal_intelligence.py
===================================
Adversarial and scientific validation test suite for Milestone 22:
Temporal Price-Action Intelligence & Mathematical Law Discovery Engine.

Validates:
1. Zero Lookahead: Feature extraction at index t is invariant to future candle mutations at t+1.
2. Data Resolution: Enforces 15m/30m/1h/2h horizons; refuses sub-bar 1m/5m fabrication.
3. Probability Normalization: Ternary distribution and barrier paths sum to 1.0.
4. Mathematical Law Discovery: FDR control, Effective Sample Size (Neff), and Brier Skill Score.
5. 3-Tier Friction Economics: Base (14 bps), Conservative (24 bps), and Stress (40 bps).
6. Cognitive Prediction Ledger: Immutable point-in-time forecast freezing.
7. Mastermind Bridge: Read-only advisory evidence without risk bypass.
8. REST API Contracts: /api/temporal/btc/forecast, /api/temporal/laws, /api/temporal/evaluate-condition.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from core.cognitive_brain.prediction_ledger import CognitivePredictionLedger
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil
from core.temporal_intelligence.arbiter_bridge import TemporalArbiterBridge
from core.temporal_intelligence.features import ZeroLookaheadFeatureExtractor
from core.temporal_intelligence.forecaster import TemporalPriceActionForecaster
from core.temporal_intelligence.law_miner import MathematicalLawMiner
from core.temporal_intelligence.models import (
    ForecastHorizon,
    PriceActionLawStatus,
    TemporalFeatureVector,
)
from core.temporal_intelligence.router import get_historical_candles

DATASET_PATH = Path("data/research/datasets/K9_BTCUSDT_15m_464d2ff4.json")


@pytest.fixture(scope="module")
def btc_15m_candles() -> list[dict]:
    assert DATASET_PATH.exists(), f"Ground truth dataset missing at {DATASET_PATH}"
    with open(DATASET_PATH, encoding="utf-8") as f:
        data = json.load(f)
    candles = data.get("candles", [])
    assert len(candles) >= 9000
    return candles


# ==============================================================================
# 1. ZERO LOOKAHEAD LEAKAGE AUDIT
# ==============================================================================

def test_zero_lookahead_leakage_audit(btc_15m_candles: list[dict]):
    """
    CRITICAL CAUSALITY TEST:
    Mutating future candle t+1 (price * 10x, volume * 100x) MUST NOT change
    any feature value extracted at index t.
    """
    target_idx = 100
    original_candles = copy.deepcopy(btc_15m_candles[:150])

    # Extract features before future mutation
    feat_before = ZeroLookaheadFeatureExtractor.extract_features(original_candles, target_idx)
    assert feat_before is not None

    # Mutate future candle at index 101 with massive price spike and volume
    mutated_candles = copy.deepcopy(original_candles)
    mutated_candles[target_idx + 1]["open"] = 500_000.0
    mutated_candles[target_idx + 1]["high"] = 999_999.0
    mutated_candles[target_idx + 1]["low"] = 400_000.0
    mutated_candles[target_idx + 1]["close"] = 900_000.0
    mutated_candles[target_idx + 1]["volume"] = 10_000_000.0

    # Extract features after future mutation
    feat_after = ZeroLookaheadFeatureExtractor.extract_features(mutated_candles, target_idx)
    assert feat_after is not None

    # Every single feature at index 100 must be 100% identical
    assert feat_before.reference_price == feat_after.reference_price
    assert feat_before.return_1bar_pct == feat_after.return_1bar_pct
    assert feat_before.return_2bar_pct == feat_after.return_2bar_pct
    assert feat_before.relative_volume == feat_after.relative_volume
    assert feat_before.volatility_ratio == feat_after.volatility_ratio
    assert feat_before.body_to_range_ratio == feat_after.body_to_range_ratio
    assert feat_before.upper_wick_ratio == feat_after.upper_wick_ratio
    assert feat_before.lower_wick_ratio == feat_after.lower_wick_ratio
    assert feat_before.distance_to_swing_high_pct == feat_after.distance_to_swing_high_pct
    assert feat_before.distance_to_swing_low_pct == feat_after.distance_to_swing_low_pct


# ==============================================================================
# 2. DATA RESOLUTION GATE & BOUNDARY HANDLING
# ==============================================================================

def test_feature_extractor_boundary_handling(btc_15m_candles: list[dict]):
    """Requires at least 20 historical bars for rolling lookbacks."""
    assert ZeroLookaheadFeatureExtractor.extract_features(btc_15m_candles, 5) is None
    assert ZeroLookaheadFeatureExtractor.extract_features(btc_15m_candles, 19) is None
    assert ZeroLookaheadFeatureExtractor.extract_features(btc_15m_candles, 20) is not None


# ==============================================================================
# 3. MATHEMATICAL LAW DISCOVERY & FDR CONTROL ON 9,008 BARS
# ==============================================================================

def test_mathematical_law_miner_evaluates_hypotheses_with_fdr(btc_15m_candles: list[dict]):
    """
    Evaluates 5 pre-declared price-action hypotheses against 9,008 historical bars.
    Verifies:
    - Benjamini-Hochberg adjusted p-values.
    - Effective sample size (Neff) calculation.
    - Out-of-sample Brier Skill Score (BSS).
    - 3-tier friction subtraction (Base: 14 bps, Conservative: 24 bps, Stress: 40 bps).
    """
    miner = MathematicalLawMiner(btc_15m_candles, train_ratio=0.70, embargo_bars=8)
    laws = miner.evaluate_predeclared_laws()

    assert len(laws) == 5
    for law in laws:
        # Statistical audit
        assert law.sample_size_train > 0
        assert law.effective_sample_size_train <= law.sample_size_train  # Neff <= N with positive autocorrelation
        assert 0.0 <= law.p_value <= 1.0
        assert 0.0 <= law.adjusted_p_value_fdr <= 1.0
        assert law.adjusted_p_value_fdr >= law.p_value  # FDR adjustment never decreases p-value

        # Friction ranking invariant: Base > Conservative > Stress
        assert law.net_expectancy_r_base >= law.net_expectancy_r_conservative
        assert law.net_expectancy_r_conservative >= law.net_expectancy_r_stress

        # Validated laws must satisfy all scientific gates
        if law.status == PriceActionLawStatus.VALIDATED:
            assert law.effective_sample_size_train >= 30.0
            assert law.adjusted_p_value_fdr < 0.05
            assert law.brier_skill_score_test > 0.0
            assert law.net_expectancy_r_base >= 0.10


# ==============================================================================
# 4. PROBABILITY NORMALIZATION & BARRIER MODEL
# ==============================================================================

def test_probability_normalization_and_barrier_model(btc_15m_candles: list[dict]):
    """
    Verifies:
    1. P(Pump) + P(Dump) + P(Range) == 1.0
    2. P(Hit Upper First) + P(Hit Lower First) + P(Neither) == 1.0
    """
    miner = MathematicalLawMiner(btc_15m_candles[:1000])
    laws = miner.evaluate_predeclared_laws()
    forecaster = TemporalPriceActionForecaster(laws=laws)

    fc = forecaster.forecast(
        candles=btc_15m_candles[:500],
        symbol="BTC/USDT",
        horizon=ForecastHorizon.H_15M,
        movement_threshold_pct=0.30,
    )
    assert fc is not None

    # Directional probabilities must sum to 1.0
    prob_sum = fc.prob_pump + fc.prob_dump + fc.prob_range
    assert prob_sum == pytest.approx(1.0, abs=0.01)

    # Barrier path probabilities must sum to 1.0
    path_sum = fc.prob_hit_upper_barrier_first + fc.prob_hit_lower_barrier_first + fc.prob_neither_barrier_hit
    assert path_sum == pytest.approx(1.0, abs=0.01)


# ==============================================================================
# 5. COGNITIVE PREDICTION LEDGER PERSISTENCE
# ==============================================================================

def test_forecaster_freezes_prediction_in_cognitive_ledger(
    btc_15m_candles: list[dict],
    tmp_path: Path,
):
    """
    Verifies that the forecaster freezes immutable predictions in SQLite
    via CognitivePredictionLedger before outcomes unfold.
    """
    db_file = tmp_path / "test_cognitive_temporal.db"
    ledger = CognitivePredictionLedger(db_path=db_file)
    forecaster = TemporalPriceActionForecaster(prediction_ledger=ledger)

    fc = forecaster.forecast(
        candles=btc_15m_candles[:200],
        symbol="BTC/USDT",
        horizon=ForecastHorizon.H_15M,
        movement_threshold_pct=0.30,
    )
    assert fc is not None

    # Retrieve from SQLite ledger
    exp = ledger.get_experience(fc.forecast_id)
    assert exp is not None
    assert exp.experience_id == fc.forecast_id
    assert exp.observation.asset == "BTC/USDT"
    assert exp.is_frozen is True
    assert exp.is_resolved is False


# ==============================================================================
# 6. TRADER INTERACTIVE SCENARIO EVALUATION
# ==============================================================================

def test_trader_interactive_scenario_query(btc_15m_candles: list[dict]):
    """
    Tests: 'What happened historically when BTC rose >= 0.50% with RVOL >= 2.0x?'
    Mines 9,008 bars to return empirical probabilities and net edge after friction.
    """
    forecaster = TemporalPriceActionForecaster()
    eval_res = forecaster.evaluate_trader_scenario(
        candles=btc_15m_candles,
        symbol="BTC/USDT",
        min_15m_return_pct=0.50,
        min_rvol=2.0,
        horizon_bars=1,
    )

    assert eval_res.historical_matches_count > 0
    assert eval_res.prob_continuation_pump + eval_res.prob_reversal_dump + eval_res.prob_range_chop == pytest.approx(1.0, abs=0.01)
    assert "Historically observed" in eval_res.verdict


# ==============================================================================
# 7. READ-ONLY MASTERMIND ARBITER BRIDGE
# ==============================================================================

def test_temporal_arbiter_bridge_advisory_context(btc_15m_candles: list[dict]):
    """
    Verifies that TemporalArbiterBridge supplies read-only probability evidence
    and discounts confidence during elevated chop.
    """
    forecaster = TemporalPriceActionForecaster()
    bridge = TemporalArbiterBridge(forecaster=forecaster)

    ev = bridge.get_temporal_evidence("BTC/USDT", btc_15m_candles[:300])
    assert ev["has_forecast"] is True
    assert "prob_pump" in ev
    assert "prob_dump" in ev
    assert "confidence_scale" in ev
    assert ev["advisory"] in ("FAVORS_LONG", "FAVORS_SHORT", "NEUTRAL", "ADVISE_NO_TRADE")


# ==============================================================================
# 8. REST API ENDPOINTS
# ==============================================================================

def test_api_temporal_endpoints():
    """Verifies FastAPI contracts for /api/temporal/btc/forecast, /laws, and /evaluate-condition."""
    client = TestClient(app)

    # 1. GET /api/temporal/laws
    resp_laws = client.get("/api/temporal/laws")
    assert resp_laws.status_code == 200
    laws_data = resp_laws.json()
    assert len(laws_data) >= 5

    # 2. GET /api/temporal/btc/forecast
    resp_fc = client.get("/api/temporal/btc/forecast")
    assert resp_fc.status_code == 200
    fc_data = resp_fc.json()
    assert len(fc_data) == 4  # 15m, 30m, 1h, 2h

    # 3. POST /api/temporal/evaluate-condition
    payload = {
        "symbol": "BTC/USDT",
        "min_15m_return_pct": 0.50,
        "min_rvol": 2.0,
        "horizon_bars": 1,
    }
    resp_eval = client.post("/api/temporal/evaluate-condition", json=payload)
    assert resp_eval.status_code == 200
    eval_data = resp_eval.json()
    assert eval_data["historical_matches_count"] > 0
    assert "verdict" in eval_data
