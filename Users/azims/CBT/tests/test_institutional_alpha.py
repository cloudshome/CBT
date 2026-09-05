"""
Unit and Integration Tests for Institutional Alpha & Microstructure Quant Engine.
Tests all 8 high-conviction quantitative mechanics:
  1. Lead-Lag Latency Correlator
  2. CVD Hidden Absorption
  3. L2 Order Book Imbalance (OBI) & VPIN
  4. OI Squeeze & Funding Divergence
  5. Session Open Liquidity Sweep (Judas Swing)
  6. Multi-Sigma VWAP
  7. 3-Tier Fractal Harmonics
  8. Bayesian Half-Kelly Position Sizer
"""

import time

from core.fractal_harmonics import fractal_harmonics_engine
from core.half_kelly_sizer import half_kelly_position_sizer
from core.institutional_alpha import institutional_alpha_engine
from core.oi_funding_squeeze import oi_funding_squeeze_engine
from core.orderbook_imbalance import orderbook_imbalance_engine


def test_orderbook_imbalance_and_vpin():
    bids = [(88500.0 - i * 5, 2.5 + i * 0.5) for i in range(15)]
    asks = [(88505.0 + i * 5, 1.0 + i * 0.1) for i in range(15)]

    res = orderbook_imbalance_engine.compute_imbalance(bids, asks, symbol="BTC/USDT")
    assert res.obi_score > 0.0, "Bids outweigh asks, OBI should be positive"
    assert res.top_level_imbalance > 0.0
    assert 0.0 <= res.flow_toxicity_vpin <= 1.0
    assert res.bid_depth_total_usd > res.ask_depth_total_usd


def test_deterministic_vpin_reproducibility():
    """Verify VPIN calculation is 100% deterministic with zero random noise."""
    bids = [(88500.0 - i * 5, 2.0) for i in range(10)]
    asks = [(88505.0 + i * 5, 1.0) for i in range(10)]

    res1 = orderbook_imbalance_engine.compute_imbalance(bids, asks, symbol="BTC/USDT")
    res2 = orderbook_imbalance_engine.compute_imbalance(bids, asks, symbol="BTC/USDT")

    assert res1.flow_toxicity_vpin == res2.flow_toxicity_vpin
    assert res1.obi_score == res2.obi_score


def test_oi_funding_squeeze_detection():
    # Test short squeeze scenario: Negative funding + expanding OI
    res = oi_funding_squeeze_engine.analyze_positioning(
        symbol="BTC/USDT",
        current_oi_usd=2_600_000_000.0,
        historical_oi_1h_ago=2_500_000_000.0,
        funding_rate_8h=-0.0003,  # -0.03%
    )
    assert res.squeeze_risk == "SHORT_SQUEEZE_PROBABLE"
    assert res.funding_zscore < 0.0
    assert res.oi_change_1h_pct > 0.0


def test_fractal_harmonics_alignment():
    # Test 3-tier bullish alignment
    macro = [
        {"close": 88000 + i * 100, "high": 88100 + i * 100, "low": 87900 + i * 100}
        for i in range(10)
    ]
    context = [
        {"close": 88500 + i * 50, "high": 88550 + i * 50, "low": 88450 + i * 50} for i in range(10)
    ]
    micro = [
        {"close": 88900 + i * 10, "high": 88920 + i * 10, "low": 88890 + i * 10} for i in range(10)
    ]

    res = fractal_harmonics_engine.evaluate_harmonics("BTC/USDT", macro, context, micro)
    assert res.is_aligned is True
    assert res.dominant_direction == "LONG"
    assert res.harmonic_confluence_score >= 0.7


def test_bayesian_half_kelly_position_sizer():
    res = half_kelly_position_sizer.calculate_sizing(
        account_equity=10000.0,
        entry_price=88500.0,
        stop_loss=87500.0,  # 1000 risk distance (~1.13%)
        take_profit=90900.0,  # 2400 reward distance (2.4 R:R)
        win_probability=0.55,
        historical_sample_size=60,
    )
    assert res.hurdle_passed is True
    assert res.risk_reward_ratio == 2.4
    assert res.position_size_usd > 0.0
    assert res.max_dollar_loss <= 250.0  # Max 2.5% risk cap


def test_master_institutional_alpha_composite():
    now = int(time.time() * 1000)
    candles = []
    p = 88000.0
    for i in range(40):
        t = now - (40 - i) * 900_000
        candles.append(
            {
                "timestamp": t,
                "open": p,
                "high": p + 50,
                "low": p - 40,
                "close": p + 20,
                "volume": 300.0,
            }
        )
        p += 20

    res = institutional_alpha_engine.evaluate_alpha(
        symbol="BTC/USDT",
        timeframe="15m",
        candles=candles,
        macro_dxy=104.2,
        macro_us10y=4.20,
        account_equity=10000.0,
        timestamp_ms=now,
    )
    assert res.symbol == "BTC/USDT"
    assert res.decision in ["LONG", "SHORT", "WATCH", "NO_TRADE"]
    assert 0.0 <= res.institutional_composite_score <= 100.0
    assert "signals" in res.lead_lag
    assert "current_cvd" in res.cvd_absorption
    assert "obi_score" in res.orderbook_imbalance
    assert "squeeze_risk" in res.oi_funding_squeeze
    assert "sweep_direction" in res.judas_sweep
    assert "vwap" in res.vwap_multisigma
    assert "harmonic_confluence_score" in res.fractal_harmonics
    assert "half_kelly_fraction" in res.half_kelly_sizing


def test_institutional_alpha_evidence_integrity_gate():
    """Verify that absent or fabricated candles force NO_TRADE with zero capital sizing."""
    res_cold = institutional_alpha_engine.evaluate_alpha(candles=None)
    assert res_cold.decision == "NO_TRADE"
    assert res_cold.is_tradeable is False
    assert res_cold.evidence_grade == "FABRICATED"
    assert res_cold.execution_dossier["suggested_size_base"] == 0.0
    assert "EVIDENCE INTEGRITY HALT" in res_cold.narrative

    # Stamped empirical candles should be tradeable
    from core.evidence_integrity import EvidenceGrade, stamp_records

    now = int(time.time() * 1000)
    empirical_candles = [
        {"timestamp": now - (50 - i) * 60000, "open": 88000.0, "high": 88100.0, "low": 87900.0, "close": 88050.0, "volume": 100.0}
        for i in range(50)
    ]
    stamp_records(empirical_candles, EvidenceGrade.EMPIRICAL)
    res_empirical = institutional_alpha_engine.evaluate_alpha(candles=empirical_candles)
    assert res_empirical.is_tradeable is True
    assert res_empirical.evidence_grade == "EMPIRICAL"
