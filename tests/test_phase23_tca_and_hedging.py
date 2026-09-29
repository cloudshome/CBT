"""
tests/test_phase23_tca_and_hedging.py
======================================
Comprehensive Institutional & Adversarial Test Suite for Phase 23:
Scaled Multi-Venue Execution, Dynamic Slippage TCA & Automated Delta Hedging.

Governance Class: Class E (Trading Logic) & Class G (Risk Desk & Sizing)
Quality Gates:
1. Transaction Cost Analysis (Perold Implementation Shortfall decomposition + signed conventions + 5-horizon markouts)
2. Automated Cross-Venue Delta & Basis Hedger (Consolidated delta + tolerance band + zero-bypass risk gating + timeout defense)
3. Cross-Venue Collateral Governor (Multi-venue margin monitoring + 4-tier risk states + freshness fail-closed + recommendations only)
4. SOR Dynamic Slicing Failover & VPIN Flow Toxicity Protection (Position-aware remainder + latency failover + VPIN circuit breaker)
5. Phase 23 FastAPI Endpoints & Two-Phase Confirmation Verification
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.database import db_manager
from core.execution.collateral_governor import (
    CollateralGovernor,
    CollateralState,
)
from core.execution.delta_hedger import (
    DeltaHedger,
    HedgeState,
    PositionDeltaLeg,
)
from core.execution.sor_failover import (
    ChildSliceStatus,
    ChildSliceTracking,
    SORFailoverEngine,
)
from core.execution.tca_engine import (
    TCAEngine,
    TCAExecutionContext,
)
from core.mbo.feed_adapter import ToxicityRegime

# ===========================================================================
# 1. TRANSACTION COST ANALYSIS (TCA) ENGINE TESTS
# ===========================================================================


def test_tca_buy_order_implementation_shortfall_decomposition() -> None:
    """Verifies complete Perold (1988) Implementation Shortfall decomposition for BUY order."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_tca_buy_01",
        client_order_id="cid_buy_01",
        symbol="BTC/USDT",
        side="BUY",
        venue="BINANCE",
        strategy_id="TWAP_ALPHA",
        provenance="LIVE",
        decision_price=65000.0,
        arrival_price=65010.0,
        benchmark_price=65010.0,
        executed_vwap=65025.0,
        best_bid=65008.0,
        best_ask=65012.0,  # spread = 4.0, half spread = 2.0
        requested_qty=1.0,
        filled_qty=1.0,
        fee_paid_usd=6.50,
        rebate_earned_usd=0.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    future_prices = {
        "1s": 65030.0,
        "5s": 65035.0,
        "30s": 65040.0,
        "60s": 65050.0,
        "300s": 65060.0,
    }

    res = engine.analyze_execution(ctx, future_prices=future_prices)

    # Verifications
    assert res.execution_id == "exec_tca_buy_01"
    # Delay cost: (65010 - 65000) / 65000 * 10000 = +1.538 bps
    assert res.attribution.delay_cost_bps == pytest.approx(1.538, rel=1e-2)
    # Market impact: (65025 - 65010) / 65010 * 10000 = +2.307 bps
    assert res.attribution.market_impact_bps == pytest.approx(2.307, rel=1e-2)
    # Half spread: (2.0 / 65010) * 10000 = +0.307 bps
    assert res.attribution.spread_cost_bps == pytest.approx(0.307, rel=1e-2)
    # Fee bps: 6.50 / (1.0 * 65025) * 10000 = +1.000 bps
    assert res.attribution.fee_cost_bps == pytest.approx(1.0, rel=1e-2)
    # Total IS: (65025 - 65000) / 65000 * 10000 + fee_bps = +3.846 + 1.0 = +4.846 bps
    assert res.attribution.total_shortfall_bps == pytest.approx(4.846, rel=1e-2)
    assert res.attribution.is_adverse_selection is True


def test_tca_sell_order_signed_cost_conventions() -> None:
    """Verifies signed cost convention for SELL order (adverse = selling below benchmark)."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_tca_sell_01",
        client_order_id="cid_sell_01",
        symbol="BTC/USDT",
        side="SELL",
        venue="BYBIT",
        strategy_id="VWAP_ALPHA",
        provenance="LIVE",
        decision_price=65000.0,
        arrival_price=64990.0,
        benchmark_price=64990.0,
        executed_vwap=64970.0,  # Sold lower than arrival -> adverse
        best_bid=64988.0,
        best_ask=64992.0,
        requested_qty=2.0,
        filled_qty=2.0,
        fee_paid_usd=12.0,
        rebate_earned_usd=0.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    res = engine.analyze_execution(ctx)

    # Delay cost: side_sign(-1) * (64990 - 65000) / 65000 * 10000 = +1.538 bps (cost)
    assert res.attribution.delay_cost_bps == pytest.approx(1.538, rel=1e-2)
    # Market impact: side_sign(-1) * (64970 - 64990) / 64990 * 10000 = +3.077 bps (cost)
    assert res.attribution.market_impact_bps == pytest.approx(3.077, rel=1e-2)
    assert res.attribution.total_shortfall_bps > 0
    assert res.attribution.is_adverse_selection is True


def test_tca_zero_cost_baseline() -> None:
    """Verifies that an execution executed exactly at decision price with 0 fees has 0.0 bps cost."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_tca_zero_01",
        client_order_id="cid_zero_01",
        symbol="BTC/USDT",
        side="BUY",
        venue="BINANCE",
        decision_price=65000.0,
        arrival_price=65000.0,
        benchmark_price=65000.0,
        executed_vwap=65000.0,
        best_bid=65000.0,
        best_ask=65000.0,
        requested_qty=1.0,
        filled_qty=1.0,
        fee_paid_usd=0.0,
        rebate_earned_usd=0.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    res = engine.analyze_execution(ctx)
    assert res.attribution.total_shortfall_bps == pytest.approx(0.0, abs=1e-5)
    assert res.attribution.slippage_bps == pytest.approx(0.0, abs=1e-5)
    assert res.attribution.delay_cost_bps == pytest.approx(0.0, abs=1e-5)
    assert res.attribution.market_impact_bps == pytest.approx(0.0, abs=1e-5)


def test_tca_favorable_price_improvement() -> None:
    """Verifies that executing at a better price yields negative shortfall bps (price improvement)."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_tca_imprv_01",
        client_order_id="cid_imprv_01",
        symbol="BTC/USDT",
        side="BUY",
        venue="BINANCE",
        decision_price=65000.0,
        arrival_price=65000.0,
        benchmark_price=65000.0,
        executed_vwap=64950.0,  # Bought 50 dollars cheaper!
        best_bid=64998.0,
        best_ask=65002.0,
        requested_qty=1.0,
        filled_qty=1.0,
        fee_paid_usd=0.0,
        rebate_earned_usd=0.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    res = engine.analyze_execution(ctx)
    assert res.attribution.total_shortfall_bps < 0
    assert res.attribution.is_price_improvement is True
    assert res.attribution.is_adverse_selection is False


def test_tca_markout_horizons_calculation() -> None:
    """Verifies all 5 post-trade markout horizons (+1s, +5s, +30s, +60s, +300s)."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_markout_01",
        client_order_id="cid_markout_01",
        symbol="BTC/USDT",
        side="BUY",
        executed_vwap=60000.0,
        requested_qty=1.0,
        filled_qty=1.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    future_prices = {
        "1s": 60006.0,  # (60006 - 60000)/60000 * 10000 = +1.0 bps
        "5s": 60012.0,  # +2.0 bps
        "30s": 60030.0,  # +5.0 bps
        "60s": 59988.0,  # -2.0 bps (favorable price decline post buy)
        "300s": 60060.0,  # +10.0 bps
    }

    res = engine.analyze_execution(ctx, future_prices=future_prices)
    m = res.markout

    assert m.markout_1s_bps == pytest.approx(1.0, rel=1e-2)
    assert m.markout_5s_bps == pytest.approx(2.0, rel=1e-2)
    assert m.markout_30s_bps == pytest.approx(5.0, rel=1e-2)
    assert m.markout_60s_bps == pytest.approx(-2.0, rel=1e-2)
    assert m.markout_300s_bps == pytest.approx(10.0, rel=1e-2)


def test_tca_markout_missing_horizons() -> None:
    """Verifies that missing horizon prices default safely to None without errors."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_markout_partial_01",
        client_order_id="cid_markout_partial_01",
        executed_vwap=50000.0,
        requested_qty=1.0,
        filled_qty=1.0,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )

    res = engine.analyze_execution(ctx, future_prices={"1s": 50005.0})
    assert res.markout.markout_1s_bps == pytest.approx(1.0, rel=1e-2)
    assert res.markout.markout_5s_bps is None
    assert res.markout.markout_30s_bps is None
    assert res.markout.markout_60s_bps is None
    assert res.markout.markout_300s_bps is None


def test_tca_sqlite_persistence_and_retrieval() -> None:
    """Verifies that analyzed TCA executions are persisted to SQLite ledger and retrievable."""
    engine = TCAEngine()
    ctx = TCAExecutionContext(
        execution_id="exec_persist_01",
        client_order_id="cid_persist_01",
        symbol="BTC/USDT",
        side="BUY",
        executed_vwap=62000.0,
        requested_qty=0.5,
        filled_qty=0.5,
        decision_monotonic_ns=1000000,
        completion_monotonic_ns=2000000,
    )
    engine.analyze_execution(ctx)

    records = engine.get_recent_records(limit=10)
    assert len(records) >= 1
    found = any(r["execution_id"] == "exec_persist_01" for r in records)
    assert found is True


def test_tca_aggregate_kpis() -> None:
    """Verifies aggregate TCA KPI calculations across multiple stored executions."""
    engine = TCAEngine()
    for i in range(3):
        ctx = TCAExecutionContext(
            execution_id=f"exec_agg_{i}",
            client_order_id=f"cid_agg_{i}",
            symbol="BTC/USDT",
            side="BUY",
            decision_price=60000.0,
            arrival_price=60000.0,
            executed_vwap=60000.0 + (i * 10),
            requested_qty=1.0,
            filled_qty=1.0,
            fee_paid_usd=6.0,
            decision_monotonic_ns=1000000,
            completion_monotonic_ns=2000000,
        )
        engine.analyze_execution(ctx)

    summary = engine.get_aggregate_summary(symbol="BTC/USDT")
    assert summary["total_trades"] >= 3
    assert "avg_shortfall_bps" in summary


# ===========================================================================
# 2. AUTOMATED CROSS-VENUE DELTA & BASIS HEDGER TESTS
# ===========================================================================


def test_delta_hedger_spot_exposure_aggregation() -> None:
    """Verifies calculation of net delta for spot holdings."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=1.25,
            side="LONG",
            mark_price=60000.0,
        ),
        PositionDeltaLeg(
            venue="BYBIT",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.50,
            side="LONG",
            mark_price=60000.0,
        ),
    ]

    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    assert exposure.net_delta == pytest.approx(1.75, rel=1e-5)
    assert exposure.net_notional_usd == pytest.approx(105000.0, rel=1e-5)
    assert exposure.is_breached is True  # > 0.05 BTC tolerance


def test_delta_hedger_multi_venue_aggregation() -> None:
    """Verifies that multi-venue long and short legs net together correctly: Delta_net = sum(w_i * Delta_i)."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=2.0,
            side="LONG",
            mark_price=65000.0,
        ),
        PositionDeltaLeg(
            venue="BYBIT",
            symbol="BTCUSDT",
            instrument_type="PERP_LINEAR",
            raw_quantity=1.98,
            side="SHORT",
            mark_price=65000.0,
        ),
    ]

    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    # Long 2.0 + Short 1.98 = Net Long 0.02 BTC
    assert exposure.net_delta == pytest.approx(0.02, abs=1e-4)
    assert exposure.net_notional_usd == pytest.approx(1300.0, rel=1e-3)
    # 0.02 BTC <= 0.05 BTC tolerance band -> in-band
    assert exposure.is_breached is False


def test_delta_hedger_perp_linear_and_inverse_delta() -> None:
    """Verifies linear perp and inverse coin-margined perp delta calculation."""
    # Linear perp short
    leg_linear = PositionDeltaLeg(
        venue="BINANCE",
        symbol="BTCUSDT",
        instrument_type="PERP_LINEAR",
        raw_quantity=1.0,
        side="SHORT",
        mark_price=60000.0,
    )
    assert leg_linear.base_delta == pytest.approx(-1.0, rel=1e-5)

    # Inverse perp long: 60,000 contracts of $1 each = 1.0 BTC
    leg_inverse = PositionDeltaLeg(
        venue="BYBIT",
        symbol="BTCUSD",
        instrument_type="PERP_INVERSE",
        raw_quantity=60000.0,
        side="LONG",
        mark_price=60000.0,
        is_inverse=True,
    )
    assert leg_inverse.base_delta == pytest.approx(1.0, rel=1e-5)


def test_delta_hedger_tolerance_band_in_band() -> None:
    """Verifies that delta within tolerance band (+-0.05 BTC) returns neutral proposed order."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.04,  # <= 0.05 BTC tolerance
            side="LONG",
            mark_price=65000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=65000.0)

    assert proposed.state == HedgeState.NEUTRAL
    assert proposed.proposed_qty == 0.0


def test_delta_hedger_tolerance_band_breach() -> None:
    """Verifies that delta exceeding tolerance band proposes neutralizing order with Q_hedge = -Delta_net."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.35,  # > 0.05 BTC tolerance
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    assert proposed.state == HedgeState.HEDGE_PROPOSED
    assert proposed.side == "SELL"
    assert proposed.proposed_qty == pytest.approx(0.35, rel=1e-3)
    assert proposed.notional_usd > 0


def test_delta_hedger_quantization_and_min_notional() -> None:
    """Verifies that proposed hedge sizes are quantized to step size and respect min notional."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.0812345,
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    assert proposed.state == HedgeState.HEDGE_PROPOSED
    assert proposed.quantized_qty > 0


def test_delta_hedger_spot_perp_basis_and_funding() -> None:
    """Verifies basis spread and annualized carry calculation."""
    hedger = DeltaHedger()
    metric = hedger.calculate_basis_and_funding(
        venue="BINANCE",
        spot_price=65000.0,
        perp_price=65065.0,  # +65 dollars premium = +10 bps
        funding_rate=0.0001,  # 0.01% per 8h
        spot_symbol="BTC/USDT",
        perp_symbol="BTCUSDT",
    )

    assert metric.basis_spread_bps == pytest.approx(10.0, rel=1e-2)
    assert metric.annualized_funding_yield_pct == pytest.approx(10.95, rel=1e-2)


@pytest.mark.asyncio
async def test_delta_hedger_risk_gating_kill_switch_rejection() -> None:
    """Verifies that active Master Kill Switch strictly rejects hedge dispatch."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.20,
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    with patch("core.execution.kill_switch.live_kill_switch.is_active", return_value=True):
        cleared, reasons = await hedger.validate_and_authorize_hedge(
            proposed, current_equity=50000.0, environment="PRODUCTION"
        )
        assert cleared is False
        assert any("kill switch" in r.lower() for r in reasons)
        assert proposed.state == HedgeState.HEDGE_RISK_BLOCKED


@pytest.mark.asyncio
async def test_delta_hedger_risk_gating_equity_cap_rejection() -> None:
    """Verifies that hedge orders exceeding the 1.5% equity cap are blocked."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.50,  # 0.50 * 60,000 = $30,000
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    # Equity = $50,000; 1.5% cap = $750. Notional $30,000 far exceeds cap!
    with patch("core.execution.kill_switch.live_kill_switch.is_active", return_value=False):
        cleared, reasons = await hedger.validate_and_authorize_hedge(
            proposed, current_equity=50000.0, environment="PRODUCTION"
        )
        assert cleared is False
        assert any("1.5% equity cap" in r for r in reasons)
        assert proposed.state == HedgeState.HEDGE_RISK_BLOCKED


@pytest.mark.asyncio
async def test_delta_hedger_risk_gating_gatekeeper_rejection() -> None:
    """Verifies that hedge is blocked if Live Gatekeeper fails preflight."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.08,
            side="LONG",
            mark_price=6000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=6000.0)

    mock_gatekeeper = MagicMock()
    mock_gatekeeper.evaluate_order_clearance = AsyncMock(
        return_value=MagicMock(passed=False, rejection_reasons=["Account unverified"])
    )

    with (
        patch("core.execution.kill_switch.live_kill_switch.is_active", return_value=False),
        patch("core.execution.live_gatekeeper.live_gatekeeper", mock_gatekeeper),
    ):
        cleared, reasons = await hedger.validate_and_authorize_hedge(
            proposed, current_equity=100000.0, environment="PRODUCTION"
        )
        assert cleared is False
        assert any("GATEKEEPER_REJECTED" in r for r in reasons)
        assert proposed.state == HedgeState.HEDGE_RISK_BLOCKED


def test_delta_hedger_unknown_execution_state_on_timeout() -> None:
    """Verifies that an execution timeout triggers HEDGE_UNKNOWN_EXECUTION with zero blind retry."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.10,
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    hedger.record_execution_timeout(proposed, timeout_ms=5000.0)
    assert proposed.state == HedgeState.HEDGE_UNKNOWN_EXECUTION


def test_delta_hedger_sqlite_persistence() -> None:
    """Verifies that delta hedge events are recorded in SQLite."""
    hedger = DeltaHedger()
    legs = [
        PositionDeltaLeg(
            venue="BINANCE",
            symbol="BTC/USDT",
            instrument_type="SPOT",
            raw_quantity=0.10,
            side="LONG",
            mark_price=60000.0,
        )
    ]
    exposure = hedger.compute_net_delta(asset="BTC", legs=legs)
    proposed = hedger.propose_hedge(exposure, reference_price=60000.0)

    # Check that row is inserted into delta_hedge_events
    with db_manager.get_trading_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hedge_id, asset, state FROM delta_hedge_events WHERE hedge_id = ?",
            (proposed.hedge_id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == proposed.hedge_id
        assert rows[0][1] == "BTC"
        assert rows[0][2] == "HEDGE_PROPOSED"


# ===========================================================================
# 3. CROSS-VENUE COLLATERAL GOVERNOR TESTS
# ===========================================================================


def test_collateral_normal_state() -> None:
    """Verifies NORMAL state when utilization < 65% and buffer >= 2.5x."""
    gov = CollateralGovernor()
    snap = gov.evaluate_venue_snapshot(
        venue="BINANCE",
        total_equity_usd=100000.0,
        available_balance_usd=80000.0,
        initial_margin_usd=20000.0,
        maintenance_margin_usd=10000.0,
        unrealized_pnl_usd=500.0,
    )

    assert snap.risk_state == CollateralState.NORMAL
    assert snap.margin_utilization_ratio == pytest.approx(0.20, rel=1e-3)
    assert snap.liquidation_buffer_ratio == pytest.approx(10.0, rel=1e-3)


def test_collateral_caution_state() -> None:
    """Verifies CAUTION state when margin utilization >= 65%."""
    gov = CollateralGovernor()
    snap = gov.evaluate_venue_snapshot(
        venue="BINANCE",
        total_equity_usd=100000.0,
        available_balance_usd=30000.0,
        initial_margin_usd=70000.0,
        maintenance_margin_usd=20000.0,
    )

    assert snap.risk_state == CollateralState.CAUTION
    assert snap.margin_utilization_ratio == pytest.approx(0.70, rel=1e-3)


def test_collateral_danger_state() -> None:
    """Verifies DANGER state when margin utilization >= 80%."""
    gov = CollateralGovernor()
    snap = gov.evaluate_venue_snapshot(
        venue="BYBIT",
        total_equity_usd=50000.0,
        available_balance_usd=8000.0,
        initial_margin_usd=42000.0,
        maintenance_margin_usd=15000.0,
    )

    assert snap.risk_state == CollateralState.DANGER
    assert snap.margin_utilization_ratio == pytest.approx(0.84, rel=1e-3)


def test_collateral_liquidation_risk_state() -> None:
    """Verifies LIQUIDATION_RISK state when liquidation buffer < 1.5x."""
    gov = CollateralGovernor()
    snap = gov.evaluate_venue_snapshot(
        venue="BYBIT",
        total_equity_usd=20000.0,
        available_balance_usd=2000.0,
        initial_margin_usd=18000.0,
        maintenance_margin_usd=15000.0,  # Buffer = 20,000 / 15,000 = 1.33x
    )

    assert snap.risk_state == CollateralState.LIQUIDATION_RISK
    assert snap.liquidation_buffer_ratio == pytest.approx(1.333, rel=1e-2)


def test_collateral_stale_data_fail_closed() -> None:
    """Verifies that snapshot older than 30 seconds triggers STALE risk state."""
    gov = CollateralGovernor()
    snap = gov.evaluate_venue_snapshot(
        venue="BINANCE",
        total_equity_usd=100000.0,
        available_balance_usd=80000.0,
        observation_timestamp_ms=int((time.time() - 45.0) * 1000),  # 45 seconds old
    )

    assert snap.risk_state == CollateralState.STALE
    assert snap.data_age_seconds >= 45.0


def test_collateral_systemic_aggregate_reporting() -> None:
    """Verifies systemic multi-venue report with worst-of status aggregation."""
    gov = CollateralGovernor()
    gov.evaluate_venue_snapshot(
        venue="BINANCE",
        total_equity_usd=60000.0,
        available_balance_usd=50000.0,
        initial_margin_usd=10000.0,
        maintenance_margin_usd=5000.0,
    )
    gov.evaluate_venue_snapshot(
        venue="BYBIT",
        total_equity_usd=40000.0,
        available_balance_usd=5000.0,
        initial_margin_usd=35000.0,  # DANGER (87.5%)
        maintenance_margin_usd=10000.0,
    )

    report = gov.get_system_collateral_report()
    assert report.total_equity_usd == pytest.approx(100000.0, rel=1e-3)
    assert report.systemic_risk_state == CollateralState.DANGER
    assert "BYBIT" in report.venues_in_danger
    assert report.freshness_ok is True


def test_collateral_governor_recommendation_only_invariant() -> None:
    """Verifies Governor Rule: recommendations only; zero automated transfer authority."""
    gov = CollateralGovernor()
    assert not hasattr(gov, "transfer_funds")
    assert not hasattr(gov, "execute_transfer")
    assert not hasattr(gov, "rebalance_collateral_automatically")


def test_collateral_sqlite_snapshot_persistence() -> None:
    """Verifies collateral snapshot recording in SQLite."""
    gov = CollateralGovernor()
    gov.evaluate_venue_snapshot(
        venue="BINANCE",
        total_equity_usd=75000.0,
        available_balance_usd=60000.0,
        initial_margin_usd=15000.0,
    )

    with db_manager.get_trading_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT venue, total_equity_usd, state FROM collateral_snapshots WHERE venue = 'BINANCE' ORDER BY created_at_ms DESC"
        )
        rows = cursor.fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == "BINANCE"
        assert rows[0][1] == 75000.0


# ===========================================================================
# 4. SOR FAILOVER & VPIN PROTECTION TESTS
# ===========================================================================


def test_sor_position_aware_remaining_qty() -> None:
    """Verifies Q_rem calculation via open_qty."""
    tracking = ChildSliceTracking(
        child_order_id="c_01",
        parent_order_id="p_01",
        venue="BINANCE",
        symbol="BTCUSDT",
        side="BUY",
        allocated_qty=10.0,
        filled_qty=4.0,
    )

    assert tracking.open_qty == pytest.approx(6.0, rel=1e-5)


def test_sor_latency_degradation_failover() -> None:
    """Verifies venue is marked degraded when ACK latency > 1,000ms."""
    engine = SORFailoverEngine()
    engine.record_slice_latency("BINANCE", latency_ms=1250.0, success=True)

    health = engine.get_venue_health()["BINANCE"]
    assert health["state"] == "DEGRADED"
    assert health["last_ack_latency_ms"] == 1250.0


def test_sor_consecutive_failures_failover() -> None:
    """Verifies venue is marked degraded after 3 consecutive failures."""
    engine = SORFailoverEngine()
    for _ in range(3):
        engine.record_slice_latency("BYBIT", latency_ms=50.0, success=False)

    health = engine.get_venue_health()["BYBIT"]
    assert health["state"] == "DEGRADED"
    assert health["consecutive_failures"] == 3


def test_sor_halt_on_unknown_child_state() -> None:
    """Verifies failover halts if any child slice is in UNKNOWN state."""
    engine = SORFailoverEngine()
    engine.register_child_slice(
        ChildSliceTracking(
            child_order_id="c_unknown_01",
            parent_order_id="p_order_unknown",
            venue="BINANCE",
            symbol="BTCUSDT",
            side="BUY",
            allocated_qty=5.0,
            filled_qty=2.0,
            status=ChildSliceStatus.UNKNOWN,
        )
    )

    decision = engine.evaluate_parent_failover(
        parent_order_id="p_order_unknown",
        parent_target_qty=5.0,
        degraded_venue="BINANCE",
        healthy_target_venue="BYBIT",
    )

    assert decision.requires_reconciliation is True
    assert decision.status == "HALTED_UNKNOWN_STATE"
    assert decision.reallocated_qty == 0.0


def test_sor_vpin_circuit_breaker_pause() -> None:
    """Verifies that VPIN >= 0.70 (TOXIC regime) halts discretionary child slices."""
    engine = SORFailoverEngine()

    mock_feed = MagicMock()
    mock_feed.calculate_toxic_flow = MagicMock(
        return_value=MagicMock(
            toxicity_regime=ToxicityRegime.TOXIC, vpin_mbo=0.78, cancel_to_trade_ratio=3.5
        )
    )

    with patch("core.execution.sor_failover.mbo_feed_adapter", mock_feed):
        is_paused, reason = engine.check_vpin_toxicity(symbol="BTCUSDT", venue="BINANCE")
        assert is_paused is True
        assert "VPIN" in reason


def test_sor_vpin_circuit_breaker_preserves_stops() -> None:
    """Verifies that stop-loss and protection orders are NOT paused during high VPIN."""
    engine = SORFailoverEngine()

    # Discretionary slice is paused
    assert engine.should_pause_slice(is_protection_order=False, vpin=0.85) is True
    # Protective stop loss is NEVER paused
    assert engine.should_pause_slice(is_protection_order=True, vpin=0.85) is False


def test_sor_failover_sqlite_persistence() -> None:
    """Verifies SOR failover event recorded in SQLite."""
    engine = SORFailoverEngine()
    engine.record_slice_latency("BINANCE", latency_ms=1500.0, success=True)

    with db_manager.get_trading_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT venue, state FROM venue_health_events WHERE venue = 'BINANCE'")
        rows = cursor.fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == "BINANCE"
        assert rows[0][1] == "DEGRADED"


# ===========================================================================
# 5. PHASE 23 FASTAPI ENDPOINTS & TWO-PHASE CONFIRMATION TESTS
# ===========================================================================


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_auth_required(client: TestClient) -> None:
    """Verifies API endpoints require valid X-API-Key when API_KEY is configured."""
    with patch("core.auth.API_KEY", "configured_secret_token"):
        res = client.get("/api/execution/tca/summary")
        assert res.status_code in (401, 403)


def test_api_tca_analyze_endpoint(client: TestClient) -> None:
    """Verifies POST /api/execution/tca/analyze endpoint."""
    payload = {
        "execution_id": "api_exec_01",
        "client_order_id": "api_cid_01",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "venue": "BINANCE",
        "decision_price": 65000.0,
        "arrival_price": 65000.0,
        "benchmark_price": 65000.0,
        "executed_vwap": 65010.0,
        "requested_qty": 1.0,
        "filled_qty": 1.0,
        "fee_paid_usd": 6.5,
    }
    res = client.post("/api/execution/tca/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "tca_result" in data


def test_api_delta_exposure_endpoint(client: TestClient) -> None:
    """Verifies GET /api/execution/delta/exposure endpoint."""
    res = client.get("/api/execution/delta/exposure?asset=BTC")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "exposure" in data
    assert "basis_metric" in data


def test_api_delta_propose_and_execute_2phase(client: TestClient) -> None:
    """Verifies 2-phase confirmation on POST /api/execution/delta/execute."""
    # 1. Propose hedge
    prop_res = client.post(
        "/api/execution/delta/propose",
        json={"asset": "BTC", "reference_price": 65000.0},
    )
    assert prop_res.status_code == 200
    hedge_id = prop_res.json()["proposed_hedge"]["hedge_id"]

    # 2. Try to execute with incorrect confirmation phrase -> 400
    bad_res = client.post(
        "/api/execution/delta/execute",
        json={
            "hedge_id": hedge_id,
            "confirmation_phrase": "WRONG_PHRASE",
            "environment": "TESTNET",
        },
    )
    assert bad_res.status_code == 400

    # 3. Execute with correct 2-phase phrase
    good_res = client.post(
        "/api/execution/delta/execute",
        json={
            "hedge_id": hedge_id,
            "confirmation_phrase": "EXECUTE_AUTHORIZED_HEDGE",
            "environment": "TESTNET",
        },
    )
    assert good_res.status_code == 200
    assert good_res.json()["status"] in ("AUTHORIZED", "RISK_BLOCKED")


def test_api_collateral_report_endpoint(client: TestClient) -> None:
    """Verifies GET /api/execution/collateral/report endpoint."""
    res = client.get("/api/execution/collateral/report")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "collateral_report" in data


def test_api_sor_failover_status_endpoint(client: TestClient) -> None:
    """Verifies GET /api/execution/sor/failover-status endpoint."""
    res = client.get("/api/execution/sor/failover-status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "venues" in data
    assert "vpin_circuit_breaker" in data


def test_api_emergency_abort_slicers(client: TestClient) -> None:
    """Verifies POST /api/execution/sor/abort-slicers endpoint."""
    res = client.post("/api/execution/sor/abort-slicers")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SLICERS_ABORTED"


def test_api_emergency_flatten_delta_2phase(client: TestClient) -> None:
    """Verifies 2-phase confirmation on POST /api/execution/delta/flatten."""
    # Bad confirmation code
    bad_res = client.post(
        "/api/execution/delta/flatten",
        json={"asset": "BTC", "confirmation_code": "WRONG_CODE"},
    )
    assert bad_res.status_code == 400

    # Correct confirmation code
    good_res = client.post(
        "/api/execution/delta/flatten",
        json={"asset": "BTC", "confirmation_code": "FLATTEN_DELTA_CONFIRMED"},
    )
    assert good_res.status_code == 200
    assert good_res.json()["status"] == "FLATTEN_DISPATCHED"
