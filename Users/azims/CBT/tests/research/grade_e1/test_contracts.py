"""
tests/research/grade_e1/test_contracts.py
=========================================
Unit tests for Grade-E1 Type Contracts, Enums, and Dataclasses.
"""

from __future__ import annotations

import dataclasses

import pytest

from core.research.grade_e1.contracts import (
    EVIDENCE_GRADE,
    ExperimentConfig,
    ExperimentResult,
    FillEngineType,
    FillEvent,
    HypotheticalOrder,
    LatencyModelType,
    LiquidityRole,
    MarketSnapshot,
    OrderSide,
    OrderStatus,
    QueueModelType,
)


def test_evidence_grade_invariant() -> None:
    assert EVIDENCE_GRADE == "GRADE-E1: OHLCV_APPROXIMATION"
    assert "L2" not in EVIDENCE_GRADE


def test_market_snapshot_contract() -> None:
    snapshot = MarketSnapshot(
        timestamp=1787428800000,
        bar_index=10,
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        volume=500.0,
        spread_bps=2.5,
        volatility_bps=12.0,
        is_gap_boundary=False,
    )
    data = snapshot.to_dict()
    assert data["bar_index"] == 10
    assert data["spread_bps"] == 2.5
    assert data["close"] == 102.0


def test_hypothetical_order_lifecycle_contract() -> None:
    order = HypotheticalOrder(
        order_id="ORD_001",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        limit_price=60000.0,
        quantity=1.5,
        post_only=True,
    )
    assert order.status == OrderStatus.SUBMITTED
    assert order.remaining_qty == 1.5
    assert order.filled_qty == 0.0

    d = order.to_dict()
    assert d["side"] == "BUY"
    assert d["quantity"] == 1.5


def test_fill_event_immutability() -> None:
    fill = FillEvent(
        fill_id="FILL_001",
        order_id="ORD_001",
        bar_index=15,
        timestamp=1787430000000,
        side=OrderSide.BUY,
        fill_price=60000.0,
        fill_qty=1.5,
        fee_bps=2.0,
        role=LiquidityRole.MAKER,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        fill.fill_price = 60100.0  # type: ignore[misc]


def test_experiment_config_and_result_hash() -> None:
    config = ExperimentConfig(
        experiment_id="EXP_001",
        dataset_id="K9_BTCUSDT_15m_464d2ff4",
        queue_model=QueueModelType.Q1_VOLUME_CLOCK,
        latency_model=LatencyModelType.L1_FIXED_50MS,
        fill_engine=FillEngineType.F1_CONSERVATIVE,
    )
    result = ExperimentResult(
        config=config,
        total_orders=100,
        filled_orders=80,
        unfilled_orders=20,
        fill_rate_pct=80.0,
    )
    h1 = result.compute_hash()
    assert len(h1) == 64
    d = result.to_dict()
    assert d["evidence_hash"] == h1
    assert d["evidence_grade"] == EVIDENCE_GRADE
