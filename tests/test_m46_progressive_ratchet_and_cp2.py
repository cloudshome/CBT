"""
tests/test_m46_progressive_ratchet_and_cp2.py
=============================================
Milestone 46: Verification Suite for:
1. Stage 1 Defensive Ratchet at +1.0R (SL moves to fee-covered breakeven +0.10R, 100% size kept).
2. Stage 2 Profit-Lock Ratchet at +1.5R (25% size banked, remaining 75% runner's SL moved to +0.60R).
3. Conditional Tier-1 Canary Universe Gating for SOL (ALIGNED only vs COUNTER_TREND / None).
4. Capital Governor CP-2 Inspection recognizing M46 Progressive Ratchet Artifact.
5. Backtester loss denominator compression under Progressive Ratchet.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from core.execution.capital_governor import capital_governor
from core.portfolio_shadow import portfolio_shadow
from core.risk.asset_eligibility_gate import (
    AssetEligibilityStatus,
    DeterministicAssetEligibilityGate,
)
from data.backtester import _evaluate


@pytest.fixture(autouse=True)
def clean_shadow_portfolio():
    """Ensure clean shadow ledger before each test."""
    portfolio_shadow.reset_all_positions()
    yield
    portfolio_shadow.reset_all_positions()


# ============================================================================
# 1. SHADOW PORTFOLIO PROGRESSIVE RATCHET (STAGE 1 & STAGE 2)
# ============================================================================


def test_m46_stage1_defensive_ratchet_long():
    """
    Verifies that for a LONG position under progressive_ratchet=True:
    Reaching +1.0R triggers Stage 1:
    - SL ratchets from original stop to Fee-Covered Breakeven (+0.10R).
    - 100% position size is retained (zero partial scale-out).
    - breakeven_triggered is set to 1.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        stop_loss=90.0,  # risk_dist = 10.0
        take_profit=130.0,
        size=1.0,
        entry_reason="M46_TEST_STAGE1_LONG",
    )

    # Price at 108.0 (+0.8R) -> Stage 1 not yet triggered
    events_sub = portfolio_shadow.update_live_price("BTCUSDT", 108.0, progressive_ratchet=True)
    assert not any(e.get("event") == "BREAKEVEN_TRIGGERED" for e in events_sub)
    open_positions = portfolio_shadow.get_open_positions()
    pos = next(p for p in open_positions if p["position_id"] == pos_id)
    assert pos["stop_loss"] == 90.0
    assert pos["breakeven_triggered"] in (0, None)

    # Price at 110.0 (+1.0R) -> Triggers Stage 1 Defensive Ratchet
    events_1r = portfolio_shadow.update_live_price("BTCUSDT", 110.0, progressive_ratchet=True)
    be_events = [e for e in events_1r if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["stage"] == 1
    assert be_events[0]["new_stop_loss"] == 101.0  # 100.0 + 0.10 * 10.0

    open_positions = portfolio_shadow.get_open_positions()
    pos_after = next(p for p in open_positions if p["position_id"] == pos_id)
    assert pos_after["stop_loss"] == 101.0
    assert pos_after["size"] == 1.0  # 100% size preserved
    assert pos_after["breakeven_triggered"] == 1


def test_m46_stage1_defensive_ratchet_short():
    """
    Verifies that for a SHORT position under progressive_ratchet=True:
    Reaching +1.0R triggers Stage 1:
    - SL ratchets from original stop (110.0) to Fee-Covered Breakeven (99.0 = 100 - 0.10*10).
    - 100% position size is retained.
    - breakeven_triggered is set to 1.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="ETHUSDT",
        direction="SHORT",
        entry_price=100.0,
        stop_loss=110.0,  # risk_dist = 10.0
        take_profit=70.0,
        size=2.0,
        entry_reason="M46_TEST_STAGE1_SHORT",
    )

    # Price at 90.0 (+1.0R in short direction)
    events = portfolio_shadow.update_live_price("ETHUSDT", 90.0, progressive_ratchet=True)
    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["stage"] == 1
    assert be_events[0]["new_stop_loss"] == 99.0  # 100.0 - 0.10 * 10.0

    open_positions = portfolio_shadow.get_open_positions()
    pos = next(p for p in open_positions if p["position_id"] == pos_id)
    assert pos["stop_loss"] == 99.0
    assert pos["size"] == 2.0
    assert pos["breakeven_triggered"] == 1


def test_m46_stage2_profit_lock_ratchet_long():
    """
    Verifies that for a LONG position under progressive_ratchet=True:
    Reaching +1.5R triggers Stage 2:
    - 25% of position is banked into realized PnL.
    - Remaining 75% runner's SL is ratcheted to +0.60R (106.0).
    - breakeven_triggered is set to 2.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        stop_loss=90.0,  # risk_dist = 10.0
        take_profit=130.0,
        size=1.0,
        entry_reason="M46_TEST_STAGE2_LONG",
    )

    # First hit +1.0R (Stage 1)
    portfolio_shadow.update_live_price("BTCUSDT", 110.0, progressive_ratchet=True)

    # Then hit +1.5R (Stage 2)
    events_1_5r = portfolio_shadow.update_live_price("BTCUSDT", 115.0, progressive_ratchet=True)
    be_events = [e for e in events_1_5r if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["stage"] == 2
    assert be_events[0]["new_stop_loss"] == 106.0  # 100.0 + 0.60 * 10.0
    assert be_events[0]["remaining_size"] == 0.75

    open_positions = portfolio_shadow.get_open_positions()
    pos = next(p for p in open_positions if p["position_id"] == pos_id)
    assert pos["stop_loss"] == 106.0
    assert pos["size"] == 0.75
    assert pos["breakeven_triggered"] == 2
    assert float(pos["realized_pnl"]) > 0.0


def test_m46_stage2_profit_lock_ratchet_short():
    """
    Verifies that for a SHORT position under progressive_ratchet=True:
    Reaching +1.5R triggers Stage 2:
    - 25% of position is banked.
    - Remaining 75% runner's SL is ratcheted to +0.60R (94.0 = 100.0 - 0.60*10.0).
    - breakeven_triggered is set to 2.
    """
    pos_id = portfolio_shadow.open_position(
        symbol="ETHUSDT",
        direction="SHORT",
        entry_price=100.0,
        stop_loss=110.0,  # risk_dist = 10.0
        take_profit=70.0,
        size=10.0,
        entry_reason="M46_TEST_STAGE2_SHORT",
    )

    events = portfolio_shadow.update_live_price("ETHUSDT", 85.0, progressive_ratchet=True)
    be_events = [e for e in events if e.get("event") == "BREAKEVEN_TRIGGERED"]
    assert len(be_events) == 1
    assert be_events[0]["stage"] == 2
    assert be_events[0]["new_stop_loss"] == 94.0
    assert be_events[0]["remaining_size"] == 7.5

    open_positions = portfolio_shadow.get_open_positions()
    pos = next(p for p in open_positions if p["position_id"] == pos_id)
    assert pos["stop_loss"] == 94.0
    assert pos["size"] == 7.5
    assert pos["breakeven_triggered"] == 2


# ============================================================================
# 2. CONDITIONAL ASSET ELIGIBILITY GATE (ALIGNED SOL)
# ============================================================================


def test_m46_asset_eligibility_gate_conditional_sol():
    """
    Verifies that SOL is conditionally whitelisted for Tier-1 Canary execution
    strictly when mtf_alignment == 'ALIGNED', and rejected otherwise.
    BTC and ETH remain unconditionally eligible.
    """
    gate = DeterministicAssetEligibilityGate()

    # Unconditional assets
    assert gate.is_tier1_canary_eligible("BTCUSDT") is True
    assert gate.is_tier1_canary_eligible("ETHUSDT") is True

    # SOL conditional tests
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="ALIGNED") is True
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="aligned") is True
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="COUNTER_TREND") is False
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment=None) is False
    assert gate.is_tier1_canary_eligible("SOL/USDT", mtf_alignment="ALIGNED") is True

    # Evaluation with desk="TIER1_CANARY"
    eval_sol_aligned = gate.evaluate_symbol_eligibility(
        "SOLUSDT", desk="TIER1_CANARY", mtf_alignment="ALIGNED"
    )
    assert eval_sol_aligned.status == AssetEligibilityStatus.ELIGIBLE
    assert eval_sol_aligned.is_eligible is True

    eval_sol_counter = gate.evaluate_symbol_eligibility(
        "SOLUSDT", desk="TIER1_CANARY", mtf_alignment="COUNTER_TREND"
    )
    assert eval_sol_counter.status == AssetEligibilityStatus.REJECTED_TIER1_CANARY_RESTRICTED
    assert eval_sol_counter.is_eligible is False
    assert "requires mtf_alignment == 'ALIGNED'" in eval_sol_counter.rationale


# ============================================================================
# 3. CAPITAL GOVERNOR RECOGNITION OF M46 ARTIFACT
# ============================================================================


def test_m46_capital_governor_recognizes_m46_certified():
    """
    Verifies that CapitalGovernor prioritizes and recognizes CP-2 CERTIFIED
    status from research/m46_cp2_certification_results.json.
    """
    mock_m46_data = {
        "meta": {"eval_engine": "M46_PROGRESSIVE_RATCHET"},
        "governance_decision": {
            "checkpoint_2_status": "CERTIFIED",
            "reason": "All 5 CP-2 hurdles passed under M46 Progressive Ratchet",
        },
    }

    with patch.object(Path, "exists", return_value=True):
        with patch.object(Path, "read_text", return_value=json.dumps(mock_m46_data)):
            certified, reason = capital_governor.verify_checkpoint_2_edge(
                strategy_id="M46_PROGRESSIVE_RATCHET", evidence={}
            )
            assert certified is True
            assert "M46" in reason


# ============================================================================
# 4. BACKTESTER LOSS DENOMINATOR COMPRESSION UNDER PROGRESSIVE RATCHET
# ============================================================================


def test_m46_backtester_progressive_ratchet_prevents_full_loss():
    """
    Verifies that in _evaluate with progressive_ratchet=True:
    When a trade reaches +1.0R and subsequently reverses to the original stop loss,
    it exits as PARTIAL_WIN at +0.10R rather than suffering a full -1.0R loss.
    """
    # 6 bars:
    # bar 0: signal bar (low=99.5, close=100.2)
    # bar 1: entry fills at 100.0 (high=101.0, low=99.5, close=100.2 inside [99.5, 100.5])
    # bar 2: advances to 104.5 (touching +1.0R=104.0, high=104.5, low=100.5)
    # bar 3: reverses sharply down to 94.0 (penetrating ratcheted SL 100.4)
    df = pd.DataFrame(
        {
            "ts": [1700000000000 + i * 3600000 for i in range(6)],
            "open": [100.0, 100.5, 100.5, 104.0, 95.0, 94.0],
            "high": [101.0, 101.0, 104.5, 104.0, 96.0, 95.0],
            "low": [99.5, 99.5, 100.5, 94.0, 93.0, 92.0],
            "close": [100.2, 100.2, 104.0, 95.0, 94.0, 93.0],
            "volume": [1000.0] * 6,
            "cvd": [50.0] * 6,
        }
    )

    plan = {
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 96.0,  # risk = 4.0, +1.0R target = 104.0
        "take_profits": [106.0, 112.4],
        "status": "waiting",
        "entryZone": [99.5, 100.5],
        "confidence": 75,
    }

    # Under progressive_ratchet=True:
    gp_progressive = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=5,
        ladder_parity=True,
        strict_a_plus_only=False,
        payoff_asymmetry=True,
        maker_reclaim=True,
        progressive_ratchet=True,
    )

    assert gp_progressive.outcome == "PARTIAL_WIN"
    assert gp_progressive.rr_achieved == pytest.approx(0.10, abs=0.01)
    assert gp_progressive.rr_net > 0.05
