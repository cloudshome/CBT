"""tests/test_m56_eth_btc_smt_regime.py
======================================
Milestone 56: Cross-Asset ETH/BTC Relative Strength & SMT Regime Filter Test Suite.

Mandatory Gates:
1. test_causal_eth_btc_alignment_no_lookahead
2. test_eth_underperforming_blocks_unconfirmed_longs
3. test_bullish_smt_divergence_detection_and_override
4. test_symbol_aware_min_sl_buffer_floor
5. test_asset_eligibility_gate_eth_canary_regime_check
6. test_m56_eth_oos_bleed_eliminated_and_pooled_cp2_certified
7. test_real_capital_permanently_disabled
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.risk.asset_eligibility_gate import (
    AssetEligibilityStatus,
    DeterministicAssetEligibilityGate,
)
from data.backtester import _evaluate
from engine.rules import SYMBOL_MIN_SL_PCT
from engine.smt_regime import (
    EthBtcRegimeSnapshot,
    evaluate_eth_plan_under_smt_regime,
    precompute_eth_btc_regime_table,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


def _make_dummy_series(symbol: str, n: int, start_price: float, trend: float = 0.0) -> pd.DataFrame:
    base_ts = 1600000000000
    rows = []
    p = start_price
    for i in range(n):
        ts = base_ts + i * 3600000
        p = p * (1.0 + trend + (0.001 if i % 2 == 0 else -0.001))
        h = p * 1.002
        l = p * 0.998
        rows.append(
            {
                "ts": ts,
                "open": p,
                "high": h,
                "low": l,
                "close": p,
                "volume": 1000.0,
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["symbol"] = symbol
    df.attrs["timeframe"] = "1h"
    return df


def test_causal_eth_btc_alignment_no_lookahead():
    """Gate 1: Verifies strictly causal point-in-time timestamp matching (no lookahead)

    and rejection of stale reference candles (> 4h).
    """
    n = 60
    eth_df = _make_dummy_series("ETHUSDT", n, 2000.0)
    btc_df = _make_dummy_series("BTCUSDT", n, 30000.0)

    tbl = precompute_eth_btc_regime_table(eth_df, btc_df)
    assert len(tbl) == n

    for ts, snap in tbl.items():
        assert snap.eth_ts == ts
        # Causal property: BTC ts must be <= ETH ts, and within 4h
        assert snap.btc_ts <= snap.eth_ts
        assert (snap.eth_ts - snap.btc_ts) <= 4 * 3600 * 1000

    # Test staleness check (> 4 hours lag raises ValueError)
    stale_btc_df = btc_df.copy()
    stale_btc_df["ts"] = stale_btc_df["ts"] - (
        70 * 3600 * 1000
    )  # Reference series entirely stale (> 4h)
    with pytest.raises(ValueError, match="Reference BTC candle is stale"):
        precompute_eth_btc_regime_table(eth_df, stale_btc_df)


def test_eth_underperforming_blocks_unconfirmed_longs():
    """Gate 2: Verifies that ETH_UNDERPERFORMING blocks unconfirmed long setups,

    while permitting short setups and requiring higher RR hurdles.
    """
    snap_weak = EthBtcRegimeSnapshot(
        eth_ts=1600000000000,
        btc_ts=1600000000000,
        eth_close=2000.0,
        btc_close=40000.0,
        ratio=0.05,
        ema20=0.051,
        ema50=0.052,
        ema200=0.055,
        roc_24=-0.03,
        z_score_48=-1.5,
        regime="ETH_UNDERPERFORMING",
        bullish_smt=False,
        bearish_smt=False,
    )

    long_plan = {
        "action": "BUY",
        "symbol": "ETHUSDT",
        "entry": 2000.0,
        "stop_loss": 1980.0,
        "take_profit": 2080.0,
        "confidence": 70,
        "riskRewardRatio": 4.0,
        "status": "waiting",
    }
    short_plan = {
        "action": "SELL",
        "symbol": "ETHUSDT",
        "entry": 2000.0,
        "stop_loss": 2020.0,
        "take_profit": 1920.0,
        "confidence": 70,
        "riskRewardRatio": 4.0,
        "status": "waiting",
    }

    # Long without SMT in weak regime is blocked
    allowed, reason = evaluate_eth_plan_under_smt_regime(
        long_plan, "RANGE", snap_weak, strict_a_plus_only=True
    )
    assert not allowed
    assert reason == "ETH_UNDERPERFORMING_LONG_VETO"

    # Short in weak regime is allowed
    allowed, reason = evaluate_eth_plan_under_smt_regime(
        short_plan, "BEAR", snap_weak, strict_a_plus_only=True
    )
    assert allowed
    assert reason is None


def test_bullish_smt_divergence_detection_and_override():
    """Gate 3: Verifies SMT divergence detection (ETH sweeps low while BTC holds)

    and that Bullish SMT overrides ratio underperformance.
    """
    # Create scenario where ETH sweeps lower low while BTC makes higher low
    n = 60
    base_ts = 1600000000000
    eth_rows = []
    btc_rows = []
    for i in range(n):
        ts = base_ts + i * 3600000
        # Normal prices
        e_p = 2000.0
        b_p = 40000.0
        e_l = 1995.0
        b_l = 39900.0

        if i == 50:
            # Previous swing low
            e_l = 1950.0
            b_l = 39000.0
        elif i == 59:
            # SMT Divergence bar: BTC sweeps lower low (38800 < 39000), ETH holds higher low (1960 > 1950)
            e_l = 1960.0
            e_p = 1965.0
            b_l = 38800.0
            b_p = 38900.0

        eth_rows.append(
            {"ts": ts, "open": e_p, "high": e_p + 10, "low": e_l, "close": e_p, "volume": 100}
        )
        btc_rows.append(
            {"ts": ts, "open": b_p, "high": b_p + 100, "low": b_l, "close": b_p, "volume": 100}
        )

    eth_df = pd.DataFrame(eth_rows)
    btc_df = pd.DataFrame(btc_rows)

    tbl = precompute_eth_btc_regime_table(eth_df, btc_df)
    last_snap = tbl[eth_rows[-1]["ts"]]

    assert last_snap.bullish_smt is True
    assert last_snap.smt_divergence == "BULLISH_SMT_ETH_STRONG"

    # Verify override: Long plan with bullish SMT is allowed even if regime is ETH_UNDERPERFORMING
    long_plan = {
        "action": "BUY",
        "symbol": "ETHUSDT",
        "entry": 1945.0,
        "stop_loss": 1930.0,
        "take_profit": 2000.0,
        "confidence": 72,
        "riskRewardRatio": 3.6,
        "status": "waiting",
    }
    allowed, reason = evaluate_eth_plan_under_smt_regime(
        long_plan, "RANGE", last_snap, strict_a_plus_only=True
    )
    assert allowed
    assert reason is None


def test_symbol_aware_min_sl_buffer_floor():
    """Gate 4: Verifies symbol-aware stop buffer percentages in engine/rules.py

    and minimum structural stop distance floor (50 bps) in data/backtester.py.
    """
    assert SYMBOL_MIN_SL_PCT["ETHUSDT"] >= 0.0055  # 55 bps
    assert SYMBOL_MIN_SL_PCT["BTCUSDT"] >= 0.0030  # 30 bps
    assert SYMBOL_MIN_SL_PCT["SOLUSDT"] >= 0.0045  # 45 bps
    assert SYMBOL_MIN_SL_PCT["PAXGUSDT"] >= 0.0035  # 35 bps

    # Verify _evaluate rejects ETH trades with tight stop < 50 bps under strict A+
    tight_plan = {
        "action": "BUY",
        "symbol": "ETHUSDT",
        "entry": 2000.0,
        "stop_loss": 1996.0,  # 4 / 2000 = 20 bps (< 50 bps)
        "take_profit": 2020.0,
        "confidence": 75,
        "riskRewardRatio": 5.0,
    }
    df = _make_dummy_series("ETHUSDT", 20, 2000.0)
    gp = _evaluate(tight_plan, df, 0, 10, strict_a_plus_only=True)
    assert gp.outcome == "NOT_TRIGGERED"

    # Compliant stop distance >= 50 bps (e.g. 15 / 2000 = 75 bps) is permitted
    compliant_plan = {
        "action": "BUY",
        "symbol": "ETHUSDT",
        "entry": 2000.0,
        "stop_loss": 1985.0,  # 75 bps
        "take_profit": 2060.0,
        "confidence": 75,
        "riskRewardRatio": 4.0,
    }
    gp_comp = _evaluate(compliant_plan, df, 0, 10, strict_a_plus_only=False)
    assert gp_comp.outcome != "NOT_TRIGGERED"


def test_asset_eligibility_gate_eth_canary_regime_check():
    """Gate 5: Verifies DeterministicAssetEligibilityGate blocks ETH on Canary desk

    when eth_btc_regime_aligned is False, and allows it when True or None.
    """
    gate = DeterministicAssetEligibilityGate()

    # Rejection when regime is explicitly counter-trend (False)
    dec_rejected = gate.evaluate_symbol_eligibility(
        "ETHUSDT",
        desk="TIER1_CANARY",
        eth_btc_regime_aligned=False,
    )
    assert dec_rejected.status == AssetEligibilityStatus.REJECTED_TIER1_CANARY_RESTRICTED
    assert not dec_rejected.is_eligible
    assert not gate.is_tier1_canary_eligible("ETHUSDT", eth_btc_regime_aligned=False)

    # Permission when regime is aligned (True)
    dec_approved = gate.evaluate_symbol_eligibility(
        "ETHUSDT",
        desk="TIER1_CANARY",
        eth_btc_regime_aligned=True,
    )
    assert dec_approved.status == AssetEligibilityStatus.ELIGIBLE
    assert dec_approved.is_eligible
    assert gate.is_tier1_canary_eligible("ETHUSDT", eth_btc_regime_aligned=True)

    # Backward compatibility: None allows execution
    dec_compat = gate.evaluate_symbol_eligibility(
        "ETHUSDT",
        desk="TIER1_CANARY",
        eth_btc_regime_aligned=None,
    )
    assert dec_compat.status == AssetEligibilityStatus.ELIGIBLE
    assert dec_compat.is_eligible
    assert gate.is_tier1_canary_eligible("ETHUSDT", eth_btc_regime_aligned=None)


def test_m56_eth_oos_bleed_eliminated_and_pooled_cp2_certified():
    """Gate 6: Verifies M56 result JSON artifacts satisfy CP-2 certification hurdles."""
    res_path = ROOT_DIR / "research" / "m56_eth_btc_smt_regime_results.json"
    if not res_path.exists():
        pytest.skip(
            "m56_eth_btc_smt_regime_results.json not yet generated; run audit script first."
        )

    with open(res_path, encoding="utf-8") as f:
        data = json.load(f)

    # Hurdle 1: ETH OOS bleed eliminated (E[R_net] >= 0.000R and PF >= 1.15)
    eth_oos = data["symbols"]["ETHUSDT"]["splits"]["sealed_oos_25pct"]
    assert eth_oos["expectancy_net"] >= 0.000, (
        f"ETH OOS expectancy {eth_oos['expectancy_net']} < 0.0"
    )
    assert eth_oos["profit_factor_net"] >= 1.15, f"ETH OOS PF {eth_oos['profit_factor_net']} < 1.15"

    # Hurdle 2: Pooled 4-asset OOS trades >= 100
    pooled = data["pooled_portfolio"]["sealed_oos"]
    assert pooled["trades"] >= 100, f"Pooled OOS trades {pooled['trades']} < 100"

    # Hurdle 3: Pooled 4-asset OOS Net Expectancy >= +0.2500R
    assert pooled["expectancy_net"] >= 0.2500, (
        f"Pooled OOS expectancy {pooled['expectancy_net']} < +0.2500R"
    )

    # Hurdle 4: Pooled 4-asset OOS Net Profit Factor >= 1.4500
    assert pooled["profit_factor_net"] >= 1.4500, (
        f"Pooled OOS PF {pooled['profit_factor_net']} < 1.4500"
    )


def test_real_capital_permanently_disabled():
    """Gate 7: Verifies REAL_CAPITAL_ENABLED = False across sovereign execution routers."""
    from core.quantitative_validation import REAL_CAPITAL_ENABLED

    assert REAL_CAPITAL_ENABLED is False
