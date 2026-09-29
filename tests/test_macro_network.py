"""
Unit tests for core/macro_network.py.
Verifies multi-asset cross-correlation matrix, PCA absorption ratio,
Lead-Lag Granger Causality, and Systemic Macro Fragility Index.
"""

import numpy as np

from core.macro_network import (
    MacroNetworkAnalysis,
    MacroNetworkEngine,
    macro_network_engine,
)


def test_macro_network_empty_returns():
    res = macro_network_engine.analyze(asset_returns={})
    assert isinstance(res, MacroNetworkAnalysis)
    assert res.macro_transmission_regime == "NEUTRAL_BALANCED"
    assert res.systemic_fragility_index > 0


def test_macro_network_correlation_and_pca():
    engine = MacroNetworkEngine()
    np.random.seed(42)

    # Generate synthetic correlated returns: Common factor + idiosyncratic noise
    n = 100
    common_factor = np.random.normal(0, 0.02, n)
    btc_returns = common_factor + np.random.normal(0, 0.005, n)
    eth_returns = 1.2 * common_factor + np.random.normal(0, 0.008, n)
    sol_returns = 1.5 * common_factor + np.random.normal(0, 0.012, n)
    gold_returns = -0.3 * common_factor + np.random.normal(0, 0.004, n)

    data = {
        "BTC/USDT": list(btc_returns),
        "ETH/USDT": list(eth_returns),
        "SOL/USDT": list(sol_returns),
        "PAXG/USDT": list(gold_returns),
    }

    res = engine.analyze(asset_returns=data)

    assert len(res.assets) == 4
    assert res.correlation_network.average_correlation != 0.0
    assert len(res.pca_absorption.eigenvalues) == 4
    # High common factor should yield high top 2 absorption ratio
    assert res.pca_absorption.absorption_ratio_top2 > 0.60
    assert res.pca_absorption.market_synchronization_regime in [
        "MODERATE_CO-MOVEMENT",
        "HIGH_SYSTEMIC_SYNCHRONIZATION",
    ]


def test_macro_network_lead_lag_granger_causality():
    engine = MacroNetworkEngine(significance_alpha=0.05, max_lag=2)
    np.random.seed(42)

    # Simulate clear lead-lag: BTC leads ALT with a 1-period lag
    n = 120
    btc = np.random.normal(0, 0.02, n)
    alt = np.zeros(n)
    for t in range(1, n):
        alt[t] = 0.8 * btc[t - 1] + np.random.normal(0, 0.005)

    data = {
        "BTC/USDT": list(btc),
        "ALT/USDT": list(alt),
    }

    res = engine.analyze(asset_returns=data)

    # Check causal link from BTC to ALT
    btc_to_alt = [
        link
        for link in res.lead_lag_links
        if link.leader == "BTC/USDT" and link.follower == "ALT/USDT"
    ]
    assert len(btc_to_alt) > 0
    assert btc_to_alt[0].optimal_lag_periods == 1
    assert btc_to_alt[0].is_statistically_significant is True
    assert btc_to_alt[0].granger_f_stat > 3.84


def test_macro_network_fragility_and_gold_regime():
    engine = MacroNetworkEngine()
    np.random.seed(42)

    # Simulate strong gold lead in risk-off environment
    n = 80
    gold = np.random.normal(0, 0.015, n)
    btc = np.zeros(n)
    eth = np.zeros(n)
    for t in range(1, n):
        btc[t] = -0.6 * gold[t - 1] + np.random.normal(0, 0.01)
        eth[t] = -0.7 * gold[t - 1] + np.random.normal(0, 0.01)

    data = {
        "PAXG/USDT": list(gold),
        "BTC/USDT": list(btc),
        "ETH/USDT": list(eth),
    }

    res = engine.analyze(asset_returns=data)
    assert res.primary_driver_asset == "PAXG/USDT"
    assert res.macro_transmission_regime in ["FLIGHT_TO_SAFETY", "RISK_OFF_CONTAGION"]
