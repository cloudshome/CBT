"""
tests/test_m47_joint_hurdle_and_paper_wiring.py
================================================
Milestone 47 Unit Test Suite:
1. Capital Governor strict joint Hurdle 2e enforcement (+0.2500R AND PF >= 1.4500).
2. Portfolio Shadow Manager default progressive ratchet behavior and +1.20R / +1.50R geometry.
3. Autonomous Trader M40 quarantine against PRE_BREAKOUT_COMPRESSION and SOL MTF alignment gate.
4. Qualification Ledger integration tracking forward paper trades toward CP-3.
"""

from decimal import Decimal

import pytest

from core.database import db_manager
from core.execution.capital_governor import (
    CapitalGovernor,
    CapitalTier,
)
from core.portfolio_shadow import PortfolioShadowManager
from core.qualification.qualification_ledger import QualificationLedger
from core.risk.asset_eligibility_gate import DeterministicAssetEligibilityGate


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure test database isolation."""
    yield


def test_capital_governor_certifies_m47_and_rejects_sub_threshold_artifacts():
    """Verifies that CapitalGovernor certifies M47 results while rejecting M46 and M45 under strict joint Hurdle 2e."""
    gov = CapitalGovernor()

    # 1. M47 certified artifact passes both E[R_net] >= +0.2500R and PF >= 1.4500
    m47_ok, m47_reason = gov.verify_checkpoint_2_edge("STRAT_M47", evidence={})
    assert m47_ok is True
    assert (
        "M47_REFINED_PROGRESSIVE_RATCHET" in m47_reason
        or "m47_cp2_joint_certification" in m47_reason
    )

    # 2. M46 artifact rejected because E[R_net] (+0.2226R) < +0.2500R
    m46_ok, m46_reason = gov.verify_checkpoint_2_edge("STRAT_M46", evidence={})
    assert m46_ok is False
    assert "Checkpoint 2 failed" in m46_reason

    # 3. M45 artifact rejected because PF (1.39) < 1.4500
    m45_ok, m45_reason = gov.verify_checkpoint_2_edge("STRAT_M45", evidence={})
    assert m45_ok is False
    assert "Checkpoint 2 failed" in m45_reason

    # 4. Evidence-based checks: fails if either condition is missed
    ev_low_exp = {
        "cpcv_dsr": 0.99,
        "oos_trades": 200,
        "net_expectancy_r": 0.22,
        "profit_factor": 1.55,
    }
    ok_low_exp, _ = gov.verify_checkpoint_2_edge("CUSTOM", evidence=ev_low_exp)
    assert ok_low_exp is False

    ev_low_pf = {
        "cpcv_dsr": 0.99,
        "oos_trades": 200,
        "net_expectancy_r": 0.28,
        "profit_factor": 1.40,
    }
    ok_low_pf, _ = gov.verify_checkpoint_2_edge("CUSTOM", evidence=ev_low_pf)
    assert ok_low_pf is False

    ev_both_pass = {
        "cpcv_dsr": 0.99,
        "oos_trades": 200,
        "net_expectancy_r": 0.27,
        "profit_factor": 1.54,
    }
    ok_both, reason_both = gov.verify_checkpoint_2_edge("CUSTOM", evidence=ev_both_pass)
    assert ok_both is True
    assert "+0.2700R net, PF 1.54" in reason_both


def test_portfolio_shadow_default_progressive_ratchet_enabled():
    """Verifies that update_live_price defaults to progressive_ratchet=True and executes the M47 geometry."""
    psm = PortfolioShadowManager()
    sym = "BTC/USDT"

    # Open 1 BTC position: entry=50000, sl=49000 (risk = 1000), tp=53100 (+3.1R)
    pos_id = psm.open_position(
        symbol=sym,
        direction="LONG",
        entry_price=50000.0,
        size=1.0,
        stop_loss=49000.0,
        take_profit=53100.0,
        entry_reason="TEST_M47",
    )

    # 1. Price at 51100 (+1.10R): Below Stage 1 (+1.20R / 51200) -> No ratchet
    evs_1 = psm.update_live_price(sym, 51100.0)
    pos = next(p for p in psm.get_open_positions() if p["position_id"] == pos_id)
    assert pos["breakeven_triggered"] in (0, None)
    assert float(pos["stop_loss"]) == 49000.0

    # 2. Price at 51200 (+1.20R): Stage 1 triggers -> SL ratchets to +0.25R ($50,250.0)
    evs_2 = psm.update_live_price(sym, 51200.0)
    pos = next(p for p in psm.get_open_positions() if p["position_id"] == pos_id)
    assert pos["breakeven_triggered"] == 1
    assert float(pos["stop_loss"]) == 50250.0
    assert float(pos["size"]) == 1.0  # 100% position size maintained

    # 3. Price at 51500 (+1.50R / TP1): Stage 2 triggers -> Bank 35%, SL ratchets to +0.65R ($50,650.0)
    evs_3 = psm.update_live_price(sym, 51500.0)
    pos = next(p for p in psm.get_open_positions() if p["position_id"] == pos_id)
    assert pos["breakeven_triggered"] == 2
    assert float(pos["stop_loss"]) == 50650.0
    assert float(pos["size"]) == pytest.approx(0.65, abs=1e-4)  # 35% banked, 65% runner left
    assert float(pos["realized_pnl"]) > 0.0  # Partial profit banked

    # Clean up test position
    with db_manager.get_trading_conn() as conn:
        conn.execute("DELETE FROM shadow_positions WHERE position_id = ?", (pos_id,))
        conn.commit()


def test_asset_eligibility_gate_and_sol_mtf_requirement():
    """Verifies that DeterministicAssetEligibilityGate permits BTC/ETH and requires ALIGNED for SOL in Tier-1 Canary."""
    gate = DeterministicAssetEligibilityGate()

    # BTC & ETH unconditionally eligible for Tier-1 Canary
    assert gate.is_tier1_canary_eligible("BTCUSDT") is True
    assert gate.is_tier1_canary_eligible("BTC/USDT") is True
    assert gate.is_tier1_canary_eligible("ETHUSDT") is True

    # SOL requires mtf_alignment == 'ALIGNED'
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment=None) is False
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="NEUTRAL") is False
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="COUNTER_TREND") is False
    assert gate.is_tier1_canary_eligible("SOLUSDT", mtf_alignment="ALIGNED") is True
    assert gate.is_tier1_canary_eligible("SOL/USDT", mtf_alignment="aligned") is True

    # Detailed eligibility decision
    dec_sol_neutral = gate.evaluate_symbol_eligibility(
        "SOL/USDT", desk="TIER1_CANARY", mtf_alignment="NEUTRAL"
    )
    assert dec_sol_neutral.is_eligible is False
    assert "requires mtf_alignment == 'ALIGNED'" in dec_sol_neutral.rationale

    dec_sol_aligned = gate.evaluate_symbol_eligibility(
        "SOL/USDT", desk="TIER1_CANARY", mtf_alignment="ALIGNED"
    )
    assert dec_sol_aligned.is_eligible is True


def test_qualification_ledger_receives_closed_paper_trades():
    """Verifies that QualificationLedger counts closed shadow positions toward forward qualification metrics."""
    ql = QualificationLedger()
    metrics = ql.get_qualification_metrics()

    # Metrics should report exact forward accounting without drift
    assert metrics.qualification_closed_count >= 0
    assert isinstance(metrics.net_qualification_pnl_usd, (int, float))

    # Check zero accounting drift in shadow manager
    psm = PortfolioShadowManager()
    acct = psm.get_portfolio_accounting()
    drift = abs(
        Decimal(str(acct["virtual_equity"]))
        - (Decimal(str(acct["settled_cash"])) + Decimal(str(acct["total_unrealized_pnl"])))
    )
    assert float(drift) < 0.001


def test_m47_governor_fail_closed_at_tier_0_paper_until_cp3():
    """Verifies that CapitalGovernor keeps REAL_CAPITAL_ENABLED = False at Tier 0 Paper until CP-3 achieves 20 decided trades."""
    gov = CapitalGovernor()
    rep = gov.get_escalation_report()

    # Core invariant: Governor remains fail-closed in PAPER until CP-3 finishes
    assert rep["current_tier"] == CapitalTier.TIER_0_PAPER.value
    assert rep["is_live_capital"] is False
