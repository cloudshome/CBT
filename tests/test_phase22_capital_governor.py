"""
tests/test_phase22_capital_governor.py
======================================
Milestone 22.3 Verification Suite:
- Task 22.3: 24/7 Autonomous Institutional Capital Governance & Walk-Forward Escalation
- Dual-Constraint Risk Budget & Notional Verification
- Contextual DSR with Multi-Testing Trials Count (Bailey & López de Prado, 2014)
- 8-State Lifecycle with Intermediate *_ELIGIBLE Boundaries
- Demotion State Machine with Hysteresis & 24h Cooldown
- Downward-Only Manual Clamping (Rejection of Upward Overrides)
- Cryptographic HMAC Boundary on Tier 8 (Production)
- Immutable Decision Ledger in SQLite trading_logs.db
- Gate 7 Live Execution Gatekeeper Integration
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from unittest.mock import patch

import pytest

from core.auth.credential_vault import credential_vault
from core.execution.account_probe import ExchangeAccountStatus, account_probe
from core.execution.capital_governor import (
    CapitalGovernor,
    CapitalTier,
    compute_contextual_dsr,
)
from core.execution.kill_switch import live_kill_switch
from core.execution.live_gatekeeper import LiveExecutionGatekeeper


@pytest.fixture
def gov(tmp_path):
    """Isolated test instance of CapitalGovernor."""
    strat_id = f"STRAT_TEST_{int(time.time() * 1000)}"
    return CapitalGovernor(default_strategy_id=strat_id)


# ==============================================================================
# 1. TIER INITIALIZATION & DUAL-CONSTRAINT RISK TESTS
# ==============================================================================


def test_capital_tier_initialization(gov):
    """Default strategy state is TIER_0_PAPER with zero real capital exposure."""
    report = gov.get_escalation_report()
    assert report["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert report["is_live_capital"] is False
    assert report["policy"]["max_notional_usd"] == 0.0
    assert report["policy"]["max_risk_budget_usd"] == 0.0


def test_dual_constraint_rejection_when_paper_tier(gov):
    """Orders with notional > 0 in PAPER tier are strictly rejected."""
    clearance = gov.evaluate_order_risk(
        requested_notional_usd=20.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        current_equity=1000.0,
    )
    assert clearance.passed is False
    assert any(
        "real-money live execution is prohibited" in r.lower() for r in clearance.rejection_reasons
    )


def test_dual_constraint_canary_bounds(gov):
    """In CANARY tier: notional must be <= $25 and risk <= $1.00."""
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_1_CANARY.value
    gov._save_strategy_state(state)

    # 1. Valid Canary Order ($10 notional, 1% stop = $0.10 risk) -> PASS
    c_valid = gov.evaluate_order_risk(
        requested_notional_usd=10.0,
        entry_price=100.0,
        stop_loss_price=99.0,
        current_equity=1000.0,
    )
    assert c_valid.passed is True
    assert c_valid.max_notional_cap_usd == 25.0
    assert c_valid.max_risk_budget_usd == 1.00

    # 2. Breaches Notional Cap ($30 > $25) -> FAIL
    c_notional_fail = gov.evaluate_order_risk(
        requested_notional_usd=30.0,
        entry_price=100.0,
        stop_loss_price=99.0,
        current_equity=1000.0,
    )
    assert c_notional_fail.passed is False
    assert any(
        "breaches canary sandbox cap" in r.lower() for r in c_notional_fail.rejection_reasons
    )

    # 3. Breaches Risk Budget ($20 notional with wide 10% stop = $2.00 risk > $1.00 budget) -> FAIL
    c_risk_fail = gov.evaluate_order_risk(
        requested_notional_usd=20.0,
        entry_price=100.0,
        stop_loss_price=90.0,  # 10% stop distance -> risk = 0.20 * 10 = $2.00
        current_equity=1000.0,
    )
    assert c_risk_fail.passed is False
    assert any("breaches effective budget" in r.lower() for r in c_risk_fail.rejection_reasons)
    # Effective allowed quantity capped by risk budget
    assert c_risk_fail.effective_allowed_qty == pytest.approx(1.0 / 10.0, abs=1e-5)


def test_regime_mismatch_dampener(gov):
    """Regime dislocation (HIGH_VOLATILITY_EXPANSION) cuts notional cap and risk budget by 50%."""
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_2_MICRO_LIVE.value  # Base: $100 notional, $5 risk
    gov._save_strategy_state(state)

    clearance = gov.evaluate_order_risk(
        requested_notional_usd=80.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        current_equity=5000.0,
        active_market_regime="HIGH_VOLATILITY_EXPANSION",
    )
    # Under 50% dampener: max notional becomes $50.0, max risk becomes $2.50
    assert clearance.max_notional_cap_usd == 50.0
    assert clearance.max_risk_budget_usd == 2.50
    assert clearance.regime_dampener == 0.50
    assert clearance.passed is False
    assert any(
        "breaches micro live cap of $50.00" in r.lower() for r in clearance.rejection_reasons
    )


# ==============================================================================
# 2. CONTEXTUAL DEFLATED SHARPE RATIO (DSR) & MULTI-TESTING TESTS
# ==============================================================================


def test_contextual_dsr_single_trial():
    """Single trial (M=1) has SR0=0.0."""
    dsr_1 = compute_contextual_dsr(sharpe=1.8, trade_count=50, trials_count=1)
    assert dsr_1 > 0.95


def test_contextual_dsr_multi_testing_penalty():
    """Increasing trials count M raises the required hurdle SR0, penalizing DSR."""
    # Strategy with Sharpe=1.5 and 40 trades
    dsr_m1 = compute_contextual_dsr(sharpe=1.5, trade_count=40, trials_count=1)
    dsr_m10 = compute_contextual_dsr(sharpe=1.5, trade_count=40, trials_count=10)
    dsr_m100 = compute_contextual_dsr(sharpe=1.5, trade_count=40, trials_count=100)

    # Multi-testing penalty strictly monotonic: DSR(M=1) > DSR(M=10) > DSR(M=100)
    assert dsr_m1 > dsr_m10 > dsr_m100
    assert dsr_m100 < 0.85  # Fails 0.95 threshold due to selection bias correction


# ==============================================================================
# 3. 8-STATE LIFECYCLE & *_ELIGIBLE BOUNDARY TESTS
# ==============================================================================


def test_walk_forward_promotion_to_eligible(gov):
    """Statistical evidence promotes strictly to *_ELIGIBLE (never automatic live capital)."""
    # 1. Advance from PAPER to CANARY_ELIGIBLE
    res_canary = gov.evaluate_escalation(
        evidence={
            "sharpe": 1.4,
            "trade_count": 35,
            "trials_count": 5,
            "max_drawdown": 0.03,
            "slippage_bps": 5.0,
        }
    )
    assert res_canary["action"] == "PROMOTED_TO_ELIGIBLE"
    assert res_canary["current_tier"] == CapitalTier.TIER_1_CANARY_ELIGIBLE.value

    # Check that live execution is still blocked in CANARY_ELIGIBLE
    clearance = gov.evaluate_order_risk(
        requested_notional_usd=10.0,
        entry_price=100.0,
        stop_loss_price=98.0,
        current_equity=1000.0,
    )
    assert clearance.passed is False
    assert any("prohibited" in r.lower() for r in clearance.rejection_reasons)


def test_operator_activation_lifecycle(gov):
    """Transition from *_ELIGIBLE to live tier requires explicit operator authorization."""
    # Put into CANARY_ELIGIBLE
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_1_CANARY_ELIGIBLE.value
    gov._save_strategy_state(state)

    # Activate
    act_res = gov.activate_eligible_tier(operator="HEAD_QUANT")
    assert act_res["status"] == "ACTIVATED"
    assert act_res["current_tier"] == CapitalTier.TIER_1_CANARY.value

    # Attempting to activate again raises ValueError
    with pytest.raises(ValueError, match="not an activatable"):
        gov.activate_eligible_tier(operator="HEAD_QUANT")


# ==============================================================================
# 4. DEMOTION STATE MACHINE, HYSTERESIS & CIRCUIT BREAKERS
# ==============================================================================


def test_demotion_daily_drawdown_circuit_breaker(gov):
    """Daily drawdown breach demotes strategy with 24-hour cooldown and freeze flag."""
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_2_MICRO_LIVE.value
    gov._save_strategy_state(state)

    dem_res = gov.trigger_demotion(
        triggering_metric="DAILY_DRAWDOWN",
        metric_value=0.024,
        threshold_value=0.020,
    )
    assert dem_res["demoted_tier"] == CapitalTier.TIER_1_CANARY.value
    assert dem_res["cooldown_until_ms"] > int(time.time() * 1000)

    # Verify state persistence
    post_state = gov.get_strategy_state()
    assert post_state["current_tier"] == CapitalTier.TIER_1_CANARY.value
    assert post_state["is_frozen"] is True
    assert post_state["demotion"]["is_demoted"] is True

    # Evaluation during cooldown returns COOLDOWN_ACTIVE
    eval_during_cooldown = gov.evaluate_escalation(evidence={"sharpe": 2.5, "trade_count": 100})
    assert eval_during_cooldown["action"] == "COOLDOWN_ACTIVE"


def test_demotion_master_kill_switch_resets_to_paper(gov):
    """Master kill switch trips immediately reset tier to TIER_0_PAPER and require human reauth."""
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_3_SCALED_LIVE.value
    gov._save_strategy_state(state)

    gov.trigger_demotion(
        triggering_metric="KILL_SWITCH",
        metric_value=1.0,
        threshold_value=0.0,
    )
    post_state = gov.get_strategy_state()
    assert post_state["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert post_state["demotion"]["requires_human_reauth"] is True


# ==============================================================================
# 5. DOWNWARD-ONLY CLAMP & CRYPTOGRAPHIC TIER 8 BOUNDARY
# ==============================================================================


def test_downward_only_clamp_enforcement(gov):
    """Manual clamp strictly moves downward; upward clamp raises MANUAL_PROMOTION_FORBIDDEN."""
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_2_MICRO_LIVE.value  # rank 4
    gov._save_strategy_state(state)

    # 1. Downward clamp to CANARY (rank 2) succeeds
    clamp_res = gov.clamp_tier_downward(
        target_tier_str=CapitalTier.TIER_1_CANARY.value,
        reason="Elevated exchange latency observed",
        operator="RISK_DESK",
    )
    assert clamp_res["status"] == "CLAMPED"
    assert clamp_res["current_tier"] == CapitalTier.TIER_1_CANARY.value

    # 2. Upward clamp from CANARY (rank 2) to SCALED_LIVE (rank 6) is strictly REJECTED
    with pytest.raises(ValueError, match="MANUAL_PROMOTION_FORBIDDEN"):
        gov.clamp_tier_downward(
            target_tier_str=CapitalTier.TIER_3_SCALED_LIVE.value,
            reason="Attempting unauthorized promotion",
            operator="ROGUE_ACTOR",
        )


def test_cryptographic_production_authorization(gov):
    """Tier 8 (Production) requires valid HMAC-SHA256 signature and PRODUCTION_ELIGIBLE state."""
    sid = gov.default_strategy_id
    secret = "SUPER_SECURE_COLD_OPERATOR_KEY_999"

    # Must be in PRODUCTION_ELIGIBLE
    state = gov.get_strategy_state()
    state["current_tier"] = CapitalTier.TIER_4_PRODUCTION_ELIGIBLE.value
    gov._save_strategy_state(state)

    now_ms = int(time.time() * 1000)
    auth_payload = "ALLOCATE_PROD_TIER_2026"
    msg = f"{sid}:{auth_payload}:{now_ms}".encode()
    valid_sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    # 1. Valid Signature -> Promoted to PRODUCTION
    auth_res = gov.authorize_production_tier(
        strategy_id=sid,
        hmac_signature=valid_sig,
        auth_payload=auth_payload,
        secret_key=secret,
        timestamp_ms=now_ms,
    )
    assert auth_res["status"] == "PRODUCTION_AUTHORIZED"
    assert auth_res["current_tier"] == CapitalTier.TIER_4_PRODUCTION.value

    # 2. Invalid Signature -> REJECT
    with pytest.raises(ValueError, match="Invalid cryptographic HMAC signature"):
        gov.authorize_production_tier(
            strategy_id=sid,
            hmac_signature="deadbeef00001111",
            auth_payload=auth_payload,
            secret_key=secret,
            timestamp_ms=now_ms,
        )


# ==============================================================================
# 6. DECISION LEDGER PERSISTENCE & GATEKEEPER INTEGRATION
# ==============================================================================


def test_immutable_decision_ledger_persistence(gov):
    """All decisions are durably written to capital_escalation_decisions table."""
    sid = gov.default_strategy_id
    dec_id = gov.record_decision(
        strategy_id=sid,
        previous_tier="TIER_0_PAPER",
        requested_tier="TIER_1_CANARY_ELIGIBLE",
        approved_tier="TIER_1_CANARY_ELIGIBLE",
        decision_type="TEST_DECISION",
        reason_codes=["Smoke pass confirmed"],
        metrics={"sharpe": 1.8, "dsr": 0.96, "trade_count": 35},
    )
    assert dec_id.startswith("DEC_")

    report = gov.get_escalation_report(sid)
    assert len(report["recent_decisions"]) > 0
    assert report["recent_decisions"][0]["decision_id"] == dec_id


@pytest.mark.asyncio
async def test_live_gatekeeper_gate_7_integration():
    """Verifies Gate 7 is evaluated in LiveExecutionGatekeeper when strategy_id is passed."""
    gatekeeper = LiveExecutionGatekeeper()
    mock_status = ExchangeAccountStatus(
        exchange="BINANCE",
        environment="PRODUCTION",
        is_connected=True,
        latency_ms=30.0,
        total_equity_usd=2000.0,
        free_cash_usd=2000.0,
        locked_margin_usd=0.0,
    )

    # Test strategy in TIER_0_PAPER -> Gate 7 must reject real live order
    test_strat = f"STRAT_GATE7_TEST_{int(time.time() * 1000)}"

    with (
        patch.object(credential_vault, "is_unlocked", return_value=True),
        patch.object(live_kill_switch, "is_active", return_value=False),
        patch.object(account_probe, "probe_exchange", return_value=mock_status),
        patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}),
    ):
        verdict = await gatekeeper.evaluate_order_clearance(
            exchange="BINANCE",
            order_notional_usd=15.0,
            strategy_id=test_strat,
        )
        assert not verdict.passed
        assert "capital_governor_cleared" in verdict.checks
        assert verdict.checks["capital_governor_cleared"] is False
        assert any(
            "real-money live execution is prohibited" in r.lower()
            for r in verdict.rejection_reasons
        )
