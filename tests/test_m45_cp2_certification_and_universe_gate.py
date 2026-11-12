"""
tests/test_m45_cp2_certification_and_universe_gate.py
====================================================
Milestone 45: Verification Suite for:
1. Maker-Reclaim Limit-Order Execution & 2-bar timeout skip in backtester.
2. Fee-Covered Breakeven (+0.10R) Ratchet & 100% Full-Runner Preservation in Shadow Ledger.
3. Tier-1 Canary Universe Eligibility Gate (BTC/ETH whitelisted, SOL paper-observation).
4. Capital Governor CP-2 Inspection prioritizing M45 Final Certification Results.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from core.database import db_manager
from core.execution.capital_governor import capital_governor
from core.portfolio_shadow import portfolio_shadow
from core.risk.asset_eligibility_gate import (
    AssetEligibilityStatus,
    DeterministicAssetEligibilityGate,
)
from data.backtester import _evaluate, calculate_trade_cost


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean shadow ledger before each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


# ============================================================================
# 1. MAKER-RECLAIM EXECUTION & TIMEOUT IN BACKTESTER
# ============================================================================


def test_maker_reclaim_fill_within_two_bars():
    """
    Verifies that with maker_reclaim=True, a limit entry fills when price
    penetrates within 2 bars, utilizing maker fee schedule.
    """
    # 5 bars: bar 0 signal, bar 1 penetrates entry price
    df = pd.DataFrame(
        {
            "ts": [1700000000000 + i * 3600000 for i in range(5)],
            "open": [100.0, 101.0, 103.0, 107.0, 110.0],
            "high": [102.0, 102.0, 106.0, 112.0, 115.0],
            "low": [99.0, 99.5, 101.0, 105.0, 108.0],
            "close": [101.0, 100.5, 105.0, 110.0, 112.0],
            "volume": [1000.0] * 5,
            "cvd": [50.0] * 5,
        }
    )

    plan = {
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 96.0,
        "take_profits": [106.0, 112.4],  # TP1: +1.5R (106.0), TP2: +3.1R (112.4)
        "status": "waiting",
        "entryZone": [99.5, 100.5],
        "confidence": 75,
    }

    gp = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=4,
        ladder_parity=True,
        strict_a_plus_only=False,
        payoff_asymmetry=True,
        maker_reclaim=True,
    )

    # Should fill at bar 1 (since low=99.5 <= 100.0) and reach TP2
    assert gp.outcome in ("FULL_WIN", "PARTIAL_WIN", "TAKE_PROFIT_2") or gp.rr_achieved > 0
    assert gp.holding_bars is not None and gp.holding_bars >= 1

    # Cost calculation for maker entry + maker exit
    cost_maker = calculate_trade_cost(
        entry=100.0,
        stop_loss=96.0,
        execution_type="maker",
    )
    cost_taker = calculate_trade_cost(
        entry=100.0,
        stop_loss=96.0,
        execution_type="taker",
    )
    assert cost_maker.total_cost_r < cost_taker.total_cost_r
    assert cost_maker.slip_r == 0.0  # Zero spread crossing on passive limit maker


def test_maker_reclaim_unfilled_timeout_skip():
    """
    Verifies that with maker_reclaim=True, if price never reaches the entry limit
    price within 2 bars, the trade is marked NOT_TRIGGERED.
    """
    # Price runs away immediately without touching entry limit (lows never drop below 104.0)
    df = pd.DataFrame(
        {
            "ts": [1700000000000 + i * 3600000 for i in range(5)],
            "open": [105.0, 106.0, 107.0, 108.0, 109.0],
            "high": [106.0, 107.0, 108.0, 109.0, 110.0],
            "low": [104.0, 105.0, 106.0, 107.0, 108.0],
            "close": [106.0, 107.0, 108.0, 109.0, 110.0],
            "volume": [1000.0] * 5,
            "cvd": [50.0] * 5,
        }
    )

    plan = {
        "action": "BUY",
        "entry": 100.0,  # Limit at 100.0
        "stop_loss": 96.0,
        "take_profits": [106.0, 112.4],
        "status": "waiting",
        "entryZone": [99.5, 100.5],
        "confidence": 75,
    }

    gp = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=4,
        ladder_parity=True,
        strict_a_plus_only=False,
        payoff_asymmetry=True,
        maker_reclaim=True,
    )

    assert gp.outcome == "NOT_TRIGGERED"


# ============================================================================
# 2. PAYOFF ASYMMETRY: FEE-COVERED BREAKEVEN & 100% RUNNER PRESERVATION
# ============================================================================


def test_portfolio_shadow_fee_covered_breakeven_preserve_full_size_long():
    """
    Verifies that with preserve_full_runner=True:
    1. Reaching +1.5R ratchets SL to Fee-Covered Breakeven (entry + 0.10 * risk).
    2. Size remains 100% open (remaining_size == original_size).
    3. Event specifies riding to TP2/runner.
    """
    sym = "BTC/USDT"
    # Entry: 80,000, SL: 76,000 (risk = 4,000), TP: 92,000 (+3.0R)
    # +1.5R threshold = 80,000 + (1.5 * 4,000) = 86,000
    # Fee-covered breakeven = 80,000 + (0.10 * 4,000) = 80,400
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="LONG",
        size=0.5,
        entry_price=80000.0,
        stop_loss=76000.0,
        take_profit=92000.0,
        entry_reason="M45_TEST_PAYOFF_ASYMMETRY",
    )

    # Price hits 86,500 (> +1.5R)
    events = portfolio_shadow.update_live_price(
        sym, current_price=86500.0, preserve_full_runner=True
    )

    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    event = be_events[0]
    assert event["position_id"] == pos_id
    assert event["new_stop_loss"] == pytest.approx(80400.0, abs=1.0)
    assert event["remaining_size"] == 0.5  # 100% preserved
    assert "100% size" in event["message"]
    assert "riding to TP2/runner" in event["message"]

    # Verify DB persistence
    with db_manager.get_trading_conn() as conn:
        row = conn.execute(
            "SELECT * FROM shadow_positions WHERE position_id = ?", (pos_id,)
        ).fetchone()
        assert row["stop_loss"] == pytest.approx(80400.0, abs=1.0)
        assert row["size"] == 0.5
        assert row["breakeven_triggered"] == 1


def test_portfolio_shadow_fee_covered_breakeven_preserve_full_size_short():
    """
    Verifies that for a SHORT position, +1.5R ratchets SL to entry - 0.10 * risk.
    """
    sym = "ETH/USDT"
    # Entry: 3,000, SL: 3,200 (risk = 200), TP: 2,400 (+3.0R)
    # +1.5R threshold = 3,000 - (1.5 * 200) = 2,700
    # Fee-covered breakeven = 3,000 - (0.10 * 200) = 2,980
    pos_id = portfolio_shadow.open_position(
        symbol=sym,
        direction="SHORT",
        size=2.0,
        entry_price=3000.0,
        stop_loss=3200.0,
        take_profit=2400.0,
        entry_reason="M45_TEST_SHORT_ASYMMETRY",
    )

    events = portfolio_shadow.update_live_price(
        sym, current_price=2680.0, preserve_full_runner=True
    )

    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    event = be_events[0]
    assert event["position_id"] == pos_id
    assert event["new_stop_loss"] == pytest.approx(2980.0, abs=1.0)
    assert event["remaining_size"] == 2.0  # 100% preserved


# ============================================================================
# 3. ASSET UNIVERSE ELIGIBILITY GATE: TIER-1 CANARY RESTRICTION
# ============================================================================


def test_asset_eligibility_gate_tier1_canary_whitelist():
    """
    Verifies that BTC and ETH are whitelisted for Tier-1 Canary, while SOL is restricted.
    """
    gate = DeterministicAssetEligibilityGate()

    # Direct helper test
    assert gate.is_tier1_canary_eligible("BTC/USDT") is True
    assert gate.is_tier1_canary_eligible("BTCUSDT") is True
    assert gate.is_tier1_canary_eligible("ETH/USDT") is True
    assert gate.is_tier1_canary_eligible("ETHUSDT") is True
    assert gate.is_tier1_canary_eligible("SOL/USDT") is False
    assert gate.is_tier1_canary_eligible("SOLUSDT") is False
    assert gate.is_tier1_canary_eligible("DOGE/USDT") is False

    # Evaluation with desk="TIER1_CANARY"
    eval_btc = gate.evaluate_symbol_eligibility("BTCUSDT", desk="TIER1_CANARY")
    assert eval_btc.status == AssetEligibilityStatus.ELIGIBLE
    assert eval_btc.is_eligible is True

    eval_sol = gate.evaluate_symbol_eligibility("SOLUSDT", desk="TIER1_CANARY")
    assert eval_sol.status == AssetEligibilityStatus.REJECTED_TIER1_CANARY_RESTRICTED
    assert eval_sol.is_eligible is False
    assert "restricted to PAPER_ONLY_OBSERVATION" in eval_sol.rationale


# ============================================================================
# 4. CAPITAL GOVERNOR CP-2 INSPECTION (M45 RESULTS)
# ============================================================================


def test_capital_governor_prioritizes_m45_results_fail_closed():
    """
    Verifies that CapitalGovernor.verify_checkpoint_2_edge prioritizes
    m45_cp2_certification_results.json and remains fail-closed.
    """
    certified, reason = capital_governor.verify_checkpoint_2_edge(
        strategy_id="M45_FINAL", evidence={}
    )

    # In strict fail-closed governance, CP-2 is False until all hurdles green
    assert certified is False
    assert "Checkpoint 2" in reason


def test_capital_governor_m45_certified_recognition():
    """
    Verifies that CapitalGovernor recognizes CP-2 CERTIFIED status from M45 artifact.
    """
    mock_m45_data = {
        "governance_decision": {
            "checkpoint_2_status": "CERTIFIED",
            "reason": "All 5 CP-2 hurdles passed under M45 Maker-Reclaim",
        }
    }

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "read_text", return_value=json.dumps(mock_m45_data)):
            certified, reason = capital_governor.verify_checkpoint_2_edge(
                strategy_id="M45_FINAL", evidence={}
            )
            assert certified is True
            assert "m45_cp2_certification_results.json" in reason
