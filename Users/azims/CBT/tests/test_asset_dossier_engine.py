"""
Comprehensive Verification Test Suite for the 8-Pillar Universal Asset Intelligence Dossier Engine.
Tests all 8 pillars, mathematical composite scoring bounds [0, 100], and adversarial debate ingestion.
"""

import time
import pytest
from core.institutional_flows import institutional_flows_engine
from core.derivatives_options import derivatives_options_engine
from core.valuation_cost_basis import valuation_cost_basis_engine
from core.stablecoin_velocity import stablecoin_velocity_engine
from core.seasonality_cyclical_dna import seasonality_cyclical_engine
from core.macro_liquidity_beta import macro_liquidity_beta_engine
from core.volatility_profile_regime import volatility_profile_engine
from core.physical_supply_shock import physical_supply_shock_engine
from core.composite_scorer import composite_scorer
from core.asset_dossier_engine import asset_dossier_engine
from core.debate_committee import debate_committee
from core.market_state import MarketStateVector
from core.ev_engine import NetEVResult
from core.uncertainty_engine import UncertaintyBudget


def test_pillar_1_institutional_flows():
    """Verify Pillar 1 for BTC, ETH, and Gold."""
    btc_snap = institutional_flows_engine.analyze("BTCUSDT", 77500.0)
    assert btc_snap.etf_net_inflow_24h_usd > 0
    assert -3.0 <= btc_snap.z_score <= 3.0

    eth_snap = institutional_flows_engine.analyze("ETHUSDT", 2430.0)
    assert eth_snap.etf_net_inflow_24h_usd > 0
    assert -3.0 <= eth_snap.z_score <= 3.0

    gold_snap = institutional_flows_engine.analyze("PAXGUSDT", 4450.0)
    assert gold_snap.sovereign_central_bank_net_tons_quarterly > 0
    assert -3.0 <= gold_snap.z_score <= 3.0


def test_pillar_2_derivatives_options():
    """Verify Pillar 2 Options GEX & Funding Rates."""
    snap = derivatives_options_engine.analyze("BTCUSDT", 77500.0)
    assert snap.funding_rate_annualized_pct > 0
    assert snap.options_max_pain_strike > 0
    assert "short_squeeze_target" in snap.primary_liquidation_pools
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_3_valuation_cost_basis():
    """Verify Pillar 3 Realized Price and Cost Basis."""
    snap = valuation_cost_basis_engine.analyze("BTCUSDT", 77500.0)
    assert snap.sth_realized_price < 77500.0
    assert snap.lth_realized_price < snap.sth_realized_price
    assert snap.mvrv_z_score > 0
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_4_stablecoin_velocity():
    """Verify Pillar 4 SSR and USDT/USDC minting."""
    snap = stablecoin_velocity_engine.analyze("BTCUSDT", 77500.0)
    assert snap.ssr_ratio > 0
    assert snap.net_minting_velocity_24h_usd > 0
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_5_seasonality_cyclical_dna():
    """Verify Pillar 5 4-year halving cycle and real yields."""
    snap = seasonality_cyclical_engine.analyze("BTCUSDT", 77500.0)
    assert snap.days_post_halving > 0
    assert snap.historical_day_win_rate_pct > 0
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_6_macro_liquidity_beta():
    """Verify Pillar 6 DXY beta and M2 expansion."""
    snap = macro_liquidity_beta_engine.analyze("BTCUSDT", 77500.0)
    assert snap.dxy_correlation_30d < 0  # Inverse correlation
    assert snap.global_m2_expansion_rate_pct > 0
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_7_volatility_profile():
    """Verify Pillar 7 Squeeze and VPOC/VAH/VAL levels."""
    snap = volatility_profile_engine.analyze("BTCUSDT", 77500.0)
    assert snap.value_area_high > 77500.0
    assert snap.value_area_low < 77500.0
    assert -3.0 <= snap.z_score <= 3.0


def test_pillar_8_physical_supply_shock():
    """Verify Pillar 8 exchange outflows and COMEX vault depletion."""
    snap = physical_supply_shock_engine.analyze("BTCUSDT", 77500.0)
    assert "BTC" in snap.exchange_reserve_delta_24h
    assert snap.exchange_net_flow_units < 0
    assert -3.0 <= snap.z_score <= 3.0

    gold_snap = physical_supply_shock_engine.analyze("PAXGUSDT", 4450.0)
    assert gold_snap.comex_registered_vault_delta_pct < 0
    assert gold_snap.shanghai_gold_exchange_premium_usd > 0


def test_composite_scorer_mathematical_bounds():
    """Verify Mathematical Composite Score S in [0.0, 100.0] under extreme bounds."""
    # Extreme Bullish (+3.0 across all 8 pillars)
    max_score, max_regime = composite_scorer.compute_score("BTC", [3.0] * 8)
    assert 90.0 <= max_score <= 100.0
    assert max_regime == "ULTRA_BULLISH_STRUCTURAL"

    # Extreme Bearish (-3.0 across all 8 pillars)
    min_score, min_regime = composite_scorer.compute_score("BTC", [-3.0] * 8)
    assert 0.0 <= min_score <= 15.0
    assert min_regime == "MACRO_CAPITULATION_RISK"

    # Neutral (0.0 across all 8 pillars)
    mid_score, mid_regime = composite_scorer.compute_score("BTC", [0.0] * 8)
    assert 48.0 <= mid_score <= 52.0
    assert mid_regime == "NEUTRAL_RANGING"


def test_asset_dossier_engine_execution_speed_and_schema():
    """Verify 8-Pillar Universal Asset Dossier schema and execution latency <= 500ms."""
    start = time.perf_counter()
    dossier = asset_dossier_engine.compile_dossier("BTCUSDT", 77500.0)
    latency_ms = (time.perf_counter() - start) * 1000.0

    assert latency_ms < 500.0, f"Dossier compilation took {latency_ms:.2f}ms (Target: <500ms)"
    assert dossier.symbol == "BTCUSDT"
    assert 0.0 <= dossier.composite_health_score <= 100.0
    assert len(dossier.pillar_z_scores) == 8
    assert "confluence" in dossier.actionable_quant_verdict.lower() or "sth" in dossier.actionable_quant_verdict.lower()

    # Dictionary representation completeness
    d_dict = dossier.to_dict()
    assert "pillar_1_institutional_flows" in d_dict
    assert "pillar_8_physical_supply_shock" in d_dict


def test_debate_committee_dossier_ingestion():
    """Verify Adversarial Debate Council incorporates 8-Pillar Asset Dossier."""
    dossier = asset_dossier_engine.compile_dossier("BTCUSDT", 77500.0)

    state = MarketStateVector(
        schema_version="1.0",
        asset="BTC/USDT",
        timestamp=int(time.time() * 1000),
        trend_scores={"1h": 0.35, "15m": 0.20},
        structure={},
        orderflow={"cvd_delta": 0.25, "absorption_score": 0.75},
        volatility={"vol_regime": "NORMAL"},
        macro_alignment={},
        sentiment={},
    )
    ev_res = NetEVResult(
        raw_ev_r=1.2,
        net_ev_r=0.95,
        win_probability=0.65,
        loss_probability=0.35,
        reward_to_risk_ratio=2.0,
        taker_fee_penalty_r=0.05,
        slippage_penalty_r=0.05,
        funding_penalty_r=0.05,
        uncertainty_deduction_r=0.10,
        is_tradable=True,
        min_hurdle_r=0.30,
        decision_verdict="PROCEED_TO_ALLOCATION",
        rationale="Positive Net EV clearing hurdle.",
    )
    u_budget = UncertaintyBudget(
        composite_uncertainty_u=0.20,
        data_quality_uncertainty=0.05,
        analogue_sample_uncertainty=0.10,
        model_disagreement_entropy=0.10,
        regime_transition_uncertainty=0.10,
        event_shock_uncertainty=0.05,
        penalty_factor=0.90,
        uncertainty_level="LOW",
    )

    decision = debate_committee.convene_council(
        symbol="BTCUSDT",
        state=state,
        ev_result=ev_res,
        uncertainty=u_budget,
        macro_regime="LIQUIDITY_EXPANSION",
        dossier=dossier,
    )

    assert decision.final_decision in ["LONG", "SHORT", "NO_TRADE"]
    assert any("etf" in p.lower() or "inflow" in p.lower() for p in decision.bull_argument.core_premises)
