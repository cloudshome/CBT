"""
tests/intelligence/test_milestone31_forward_validation.py
==========================================================
Adversarial Verification Suite for Milestone 31: Continuous Forward Validation,
Paper Execution & Microstructure Markout Research League.

Categories Covered in Phase 1:
- Category A: Strategy Admission & Parameter Immutability (Tests 1-4)
- Category F: Strategy Health, State Transitions & Anti-Survivorship Bias (Tests 5-7)
- Category G: Constitutional Capital Isolation (Test 8)
"""

from __future__ import annotations

import pytest

from core.intelligence.forward_validation import (
    AdmissionStatus,
    BacktestBaselineExpectations,
    DriftStatus,
    DuplicateAdmissionError,
    EvaluationMode,
    FeedIntegrityError,
    FeedQualityState,
    ForwardPerformanceLedger,
    HumanApprovalRequiredError,
    LiveMarketDataGateway,
    MarketEventTimestamps,
    MicrostructureMarkoutEngine,
    MultiDimensionalDriftDetector,
    MultiDimensionalDriftReport,
    OrderBookSnapshot,
    OrderSide,
    OrderType,
    PaperFill,
    ParameterImmutabilityError,
    RealisticPaperFillSimulator,
    StrategyAdmission,
    StrategyForwardScorecard,
    StrategyLeagueRegistry,
    StrategyNotFoundError,
    SuspensionController,
    SuspensionPolicy,
)


def _make_test_admission(
    genome_id: str = "MEC_MOMENTUM_EXP_v1",
    params: dict | None = None,
    human_ref: str = "SIG-OPERATOR-AZIM-2026-KEY-A1B2",
) -> StrategyAdmission:
    parameters = params or {"lookback": 20, "threshold_pct": 1.5, "stop_loss_pct": 0.8}
    return StrategyAdmission.create(
        dossier_id="data/research_dossiers/PLAN-1700000000-abc12345.md",
        hypothesis_id="HYP-1700000000-1234",
        plan_id="PLAN-1700000000-abc12345",
        strategy_genome_id=genome_id,
        research_protocol_hash="a" * 64,
        frozen_parameters=parameters,
        dataset_hash="b" * 64,
        human_approval_reference=human_ref,
        evaluation_window_days=14,
        market_universe=["BTCUSDT", "ETHUSDT"],
        timeframe="1m",
        expected_holding_period_sec=300.0,
        evaluation_mode=EvaluationMode.PAPER_EXECUTION,
    )


def test_01_admission_requires_human_approval_token():
    """Verifies that strategy admission without explicit human operator signature fails closed."""
    # Blank or dummy approval references must raise HumanApprovalRequiredError
    for invalid_ref in ["", "   ", "NONE", "NULL", "UNAPPROVED", "auto"]:
        with pytest.raises(HumanApprovalRequiredError):
            _make_test_admission(human_ref=invalid_ref)

    # Valid human signature passes
    admission = _make_test_admission(human_ref="SIG-HUMAN-OPERATOR-VERIFIED")
    assert admission.human_approval_reference == "SIG-HUMAN-OPERATOR-VERIFIED"
    assert admission.status == AdmissionStatus.ADMITTED


def test_02_parameter_hash_integrity_and_immutability():
    """Verifies cryptographic parameter hash calculation and immutability checks."""
    params = {"k_period": 14, "smooth": 3}
    admission = _make_test_admission(params=params)

    # Correct hash matches
    expected_hash = StrategyAdmission.compute_parameter_hash(params)
    assert admission.parameter_hash == expected_hash

    # Registry immutability check passes for matching parameters
    registry = StrategyLeagueRegistry(":memory:")
    registry.admit_strategy(admission)
    assert (
        registry.check_parameter_immutability(admission.admission_id, {"smooth": 3, "k_period": 14})
        is True
    )

    # Mutated parameter dictionary raises ParameterImmutabilityError
    altered_params = {"k_period": 15, "smooth": 3}
    with pytest.raises(ParameterImmutabilityError):
        registry.check_parameter_immutability(admission.admission_id, altered_params)


def test_03_admit_strategy_creates_registry_and_transition_records():
    """Verifies strategy registration, zero-initialized metrics, and initial audit trail."""
    registry = StrategyLeagueRegistry(":memory:")
    admission = _make_test_admission()
    admitted = registry.admit_strategy(admission)

    # Record exists in registry
    record = registry.get_strategy(admitted.admission_id)
    assert record is not None
    assert record.strategy_genome_id == "MEC_MOMENTUM_EXP_v1"
    assert record.total_observations == 0
    assert record.win_rate == 0.0
    assert record.gross_pnl_bps == 0.0
    assert record.net_pnl_bps == 0.0
    assert record.is_active is True

    # Raw admission contract retrieved cleanly
    contract = registry.get_admission(admitted.admission_id)
    assert contract is not None
    assert contract.dossier_id == admission.dossier_id


def test_04_duplicate_active_admission_rejected():
    """Verifies that an identical strategy cannot be admitted twice concurrently."""
    registry = StrategyLeagueRegistry(":memory:")
    admission1 = _make_test_admission()
    registry.admit_strategy(admission1)

    # Creating another admission for the same genome and identical parameters
    admission2 = _make_test_admission()
    with pytest.raises(DuplicateAdmissionError):
        registry.admit_strategy(admission2)


def test_05_anti_survivorship_bias_historical_visibility():
    """
    CRITICAL TEST: Verifies that underperforming, suspended, and failed strategies
    remain permanently visible in the registry (Zero Survivorship Bias).
    """
    registry = StrategyLeagueRegistry(":memory:")

    # Admit 3 distinct strategies
    _adm1 = registry.admit_strategy(_make_test_admission(genome_id="STRAT_ALPHA", params={"x": 1}))
    adm2 = registry.admit_strategy(_make_test_admission(genome_id="STRAT_BETA", params={"x": 2}))
    adm3 = registry.admit_strategy(_make_test_admission(genome_id="STRAT_GAMMA", params={"x": 3}))

    # Transition STRAT_BETA to SUSPENDED, STRAT_GAMMA to FAILED
    registry.update_strategy_status(
        adm2.admission_id, AdmissionStatus.SUSPENDED, "Cost erosion exceeded 50%"
    )
    registry.update_strategy_status(
        adm3.admission_id, AdmissionStatus.FAILED, "Net markout collapsed"
    )

    # Anti-survivorship guarantee: default list_strategies() returns ALL 3 strategies
    all_strats = registry.list_strategies()
    assert len(all_strats) == 3
    statuses = {s.strategy_genome_id: s.status for s in all_strats}
    assert statuses["STRAT_ALPHA"] == AdmissionStatus.ADMITTED
    assert statuses["STRAT_BETA"] == AdmissionStatus.SUSPENDED
    assert statuses["STRAT_GAMMA"] == AdmissionStatus.FAILED

    # Check reason preserved
    beta_record = registry.get_strategy(adm2.admission_id)
    assert beta_record is not None
    assert beta_record.suspension_reason == "Cost erosion exceeded 50%"


def test_06_observation_update_recalculates_metrics_atomically():
    """Verifies running calculation of PnL, drawdowns, and incremental markout averages."""
    registry = StrategyLeagueRegistry(":memory:")
    adm = registry.admit_strategy(_make_test_admission())

    # Trade 1: Win (+20 bps gross, +15 bps net, 5s markout +12 bps)
    registry.record_observation_update(
        adm.admission_id,
        trade_gross_pnl_bps=20.0,
        trade_net_pnl_bps=15.0,
        is_win=True,
        markout_5s_bps=12.0,
    )
    r1 = registry.get_strategy(adm.admission_id)
    assert r1.total_observations == 1
    assert r1.winning_observations == 1
    assert r1.win_rate == 1.0
    assert r1.net_pnl_bps == 15.0
    assert r1.high_water_mark_bps == 15.0
    assert r1.max_drawdown_bps == 0.0
    assert r1.avg_markout_5s_bps == 12.0

    # Trade 2: Loss (-10 bps gross, -15 bps net, 5s markout -8 bps)
    registry.record_observation_update(
        adm.admission_id,
        trade_gross_pnl_bps=-10.0,
        trade_net_pnl_bps=-15.0,
        is_win=False,
        markout_5s_bps=-8.0,
    )
    r2 = registry.get_strategy(adm.admission_id)
    assert r2.total_observations == 2
    assert r2.winning_observations == 1
    assert r2.losing_observations == 1
    assert r2.win_rate == 0.50
    assert r2.net_pnl_bps == 0.0
    assert r2.high_water_mark_bps == 15.0
    assert r2.max_drawdown_bps == 15.0  # 15.0 - 0.0 = 15.0 bps drawdown
    assert r2.avg_markout_5s_bps == (12.0 - 8.0) / 2  # 2.0 bps


def test_07_status_transitions_and_suspension_logging():
    """Verifies audit logging for circuit-breaker suspension events."""
    registry = StrategyLeagueRegistry(":memory:")
    adm = registry.admit_strategy(_make_test_admission())

    registry.log_suspension(
        admission_id=adm.admission_id,
        trigger_name="MAX_DRAWDOWN_BREACH",
        threshold_val=200.0,
        observed_val=245.5,
        details="Net drawdown in paper league breached 200 bps limit",
    )
    registry.update_strategy_status(
        admission_id=adm.admission_id,
        new_status=AdmissionStatus.SUSPENDED,
        reason="MAX_DRAWDOWN_BREACH: observed 245.5 bps > 200.0 bps",
        operator_or_system="CIRCUIT_BREAKER_DAEMON",
    )

    strat = registry.get_strategy(adm.admission_id)
    assert strat.status == AdmissionStatus.SUSPENDED
    assert "MAX_DRAWDOWN_BREACH" in strat.suspension_reason


def test_08_constitutional_real_capital_enabled_permanently_false():
    """Verifies that real_capital_enabled is permanently False across all admission representations."""
    admission = _make_test_admission()
    assert admission.real_capital_enabled is False
    assert admission.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"

    registry = StrategyLeagueRegistry(":memory:")
    registry.admit_strategy(admission)
    stored = registry.get_admission(admission.admission_id)
    assert stored.real_capital_enabled is False
    assert stored.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"

    # get_strategy returns None on nonexistent ID
    assert registry.get_strategy("NONEXISTENT_ID") is None

    # StrategyNotFoundError on nonexistent ID when attempting status update or parameter check
    with pytest.raises(StrategyNotFoundError):
        registry.check_parameter_immutability("NONEXISTENT_ID", {"x": 1})


# ============================================================================
# Category B: Live Market Data Gateway & Feed Integrity (Tests 9-16)
# ============================================================================


def test_09_market_event_6_tier_timestamp_attribution():
    """Verifies that market event timestamps record all 6 causal audit horizons."""
    t_event = 1700000000.123
    t_tx = 1700000000.125
    t_recv = 1700000000.130

    ts = MarketEventTimestamps.create(
        exchange_event_utc=t_event,
        exchange_tx_utc=t_tx,
        local_recv_utc=t_recv,
    )
    assert ts.exchange_event_time_utc == t_event
    assert ts.exchange_transaction_time_utc == t_tx
    assert ts.local_receive_time_utc == t_recv
    assert ts.processing_time_utc >= t_recv
    assert ts.feature_available_time_utc >= ts.processing_time_utc
    assert ts.decision_time_utc is None


def test_10_orderbook_snapshot_depth_and_spread_calculation():
    """Verifies order book top-of-book metrics, spread in bps, and cumulative depth queries."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    bids = [(50000.0, 1.5), (49990.0, 2.0), (49950.0, 5.0)]
    asks = [(50010.0, 1.0), (50020.0, 3.0), (50060.0, 4.0)]
    ts = MarketEventTimestamps.create(1700000000.0)

    snap = book.apply_snapshot(bids=bids, asks=asks, sequence_id=100, timestamps=ts)

    assert snap.best_bid == 50000.0
    assert snap.best_ask == 50010.0
    assert snap.mid_price == 50005.0
    assert snap.is_crossed is False
    assert snap.spread_bps == pytest.approx((10.0 / 50005.0) * 10000.0, rel=1e-4)

    # Liquidity available within 5 bps of best ask (max price 50010 * 1.0005 = 50035.0)
    # Includes level 50010.0 (size 1.0) and 50020.0 (size 3.0) -> cumulative 4.0
    assert snap.depth_within_bps(5.0, "ask") == 4.0

    # Liquidity available within 2 bps of best bid (min price 50000 * 0.9998 = 49990.0)
    # Includes level 50000.0 (size 1.5) and 49990.0 (size 2.0) -> cumulative 3.5
    assert snap.depth_within_bps(2.0, "bid") == 3.5


def test_11_crossed_book_detection_quarantines_feed():
    """Verifies that an inverted/crossed book (best_bid >= best_ask) triggers CROSSED_BOOK and un-tradable state."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    # Inverted: Bid at 50020, Ask at 50010
    bids = [(50020.0, 1.0)]
    asks = [(50010.0, 1.0)]
    ts = MarketEventTimestamps.create(1700000000.0)

    snap = book.apply_snapshot(bids=bids, asks=asks, sequence_id=101, timestamps=ts)
    assert snap.is_crossed is True
    assert snap.quality == FeedQualityState.CROSSED_BOOK
    assert gateway.is_feed_tradable("BTCUSDT", "BINANCE") is False


def test_12_sequence_gap_detection_flags_degraded():
    """Verifies that receiving non-monotonic updates with a missing sequence flags SEQUENCE_GAP."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    book.apply_snapshot(
        bids=[(50000.0, 1.0)], asks=[(50010.0, 1.0)], sequence_id=100, timestamps=ts
    )

    # Next update arrives with prev_sequence_id = 95 != 100 (gap detected)
    snap = book.apply_delta(
        bid_deltas=[(50000.0, 1.2)],
        ask_deltas=[],
        sequence_id=105,
        prev_sequence_id=95,
        timestamps=ts,
    )
    assert snap.quality == FeedQualityState.SEQUENCE_GAP
    assert gateway.is_feed_tradable("BTCUSDT", "BINANCE") is False


def test_13_stale_feed_detection():
    """Verifies that feeds with no updates for > max_stale_sec transition to STALE_FEED."""
    gateway = LiveMarketDataGateway(max_stale_sec=1.0)
    book = gateway.get_or_create_book("ETHUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    book.apply_snapshot(bids=[(3000.0, 10.0)], asks=[(3005.0, 10.0)], sequence_id=1, timestamps=ts)
    assert book.quality == FeedQualityState.HEALTHY

    # Artificially age the update timestamp by 5 seconds
    book.last_update_utc -= 5.0
    status = book.check_health(max_stale_sec=1.0)
    assert status == FeedQualityState.STALE_FEED
    assert gateway.is_feed_tradable("ETHUSDT", "BINANCE") is False


def test_14_binance_depth_update_normalization():
    """Verifies normalization of raw Binance depthUpdate payloads."""
    gateway = LiveMarketDataGateway()
    raw_payload = {
        "e": "depthUpdate",
        "E": 1690000000123,
        "T": 1690000000125,
        "s": "BTCUSDT",
        "u": 500,
        "pu": None,
        "b": [["60000.0", "2.5"], ["59990.0", "3.0"]],
        "a": [["60005.0", "1.8"], ["60010.0", "4.0"]],
    }
    snap = gateway.ingest_raw_message(
        venue="BINANCE",
        symbol="BTCUSDT",
        msg_type="BINANCE_DEPTH",
        payload=raw_payload,
        local_recv_utc=1690000000.130,
    )

    assert snap.venue == "BINANCE"
    assert snap.symbol == "BTCUSDT"
    assert snap.sequence_id == 500
    assert snap.best_bid == 60000.0
    assert snap.best_ask == 60005.0
    assert snap.quality == FeedQualityState.HEALTHY
    assert snap.timestamps.exchange_event_time_utc == pytest.approx(1690000000.123)


def test_15_hyperliquid_l2_book_normalization():
    """Verifies normalization of raw Hyperliquid l2Book payloads."""
    gateway = LiveMarketDataGateway()
    raw_payload = {
        "coin": "SOL",
        "time": 1690000000500,
        "levels": [
            [{"px": "150.0", "sz": "20.0", "n": 2}, {"px": "149.8", "sz": "50.0", "n": 4}],
            [{"px": "150.2", "sz": "15.0", "n": 1}, {"px": "150.5", "sz": "30.0", "n": 3}],
        ],
    }
    snap = gateway.ingest_raw_message(
        venue="HYPERLIQUID",
        symbol="SOL",
        msg_type="HYPERLIQUID_L2",
        payload=raw_payload,
    )

    assert snap.venue == "HYPERLIQUID"
    assert snap.symbol == "SOL"
    assert snap.best_bid == 150.0
    assert snap.best_ask == 150.2
    assert snap.mid_price == 150.1
    assert snap.quality == FeedQualityState.HEALTHY


def test_16_duplicate_or_out_of_order_sequence_ignored():
    """Verifies that duplicate sequence updates are safely ignored without corrupting depth."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    book.apply_snapshot(
        bids=[(50000.0, 1.0)], asks=[(50010.0, 1.0)], sequence_id=200, timestamps=ts
    )

    # Send delta with sequence 199 <= 200 (stale/out-of-order)
    snap = book.apply_delta(
        bid_deltas=[(50000.0, 999.0)],
        ask_deltas=[],
        sequence_id=199,
        prev_sequence_id=None,
        timestamps=ts,
    )
    # Price level 50000.0 must remain at size 1.0, not overwritten with 999.0
    assert snap.bids[0].size == 1.0
    assert snap.sequence_id == 200


# ============================================================================
# Category C: Realistic Paper Fill Simulation (Tests 17-22)
# ============================================================================


def test_17_market_order_depth_walking_and_vwap():
    """Verifies that market orders walk discrete order book levels to compute realistic VWAP + slippage."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    # Asks: 1.0 @ 50000.0, 2.0 @ 50010.0, 5.0 @ 50020.0
    asks = [(50000.0, 1.0), (50010.0, 2.0), (50020.0, 5.0)]
    bids = [(49990.0, 5.0)]
    snap = book.apply_snapshot(bids=bids, asks=asks, sequence_id=1, timestamps=ts)

    sim = RealisticPaperFillSimulator(taker_fee_bps=5.0)

    # Buy 3.0 BTC: consumes 1.0 @ 50000 + 2.0 @ 50010 -> Raw VWAP = (50000 + 100020) / 3 = 50006.67
    fill = sim.simulate_market_order(
        admission_id="ADM-TEST-01",
        book=snap,
        side=OrderSide.BUY,
        quantity=3.0,
    )

    assert fill.filled_quantity == 3.0
    assert fill.is_partial is False
    assert fill.fill_price > 50006.66  # Must reflect VWAP + adverse slippage
    assert fill.fill_price > 50000.0  # Strictly higher than best ask
    assert fill.slippage_bps > 0.0
    assert fill.fee_bps == 5.0
    assert fill.fee_usd > 0.0


def test_18_market_order_partial_fill_on_insufficient_depth():
    """Verifies that requesting more liquidity than available within slippage tolerance executes partial fill."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    # Total ask depth is only 2.5 BTC within 10 bps
    asks = [(50000.0, 1.0), (50002.0, 1.5), (55000.0, 10.0)]  # 55000 is 1000 bps away!
    bids = [(49990.0, 5.0)]
    snap = book.apply_snapshot(bids=bids, asks=asks, sequence_id=1, timestamps=ts)

    sim = RealisticPaperFillSimulator()

    # Request 10.0 BTC with max_slippage_bps = 50.0 bps
    fill = sim.simulate_market_order(
        admission_id="ADM-TEST-02",
        book=snap,
        side=OrderSide.BUY,
        quantity=10.0,
        max_slippage_bps=50.0,
    )

    assert fill.filled_quantity == 2.5
    assert fill.is_partial is True
    assert fill.requested_quantity == 10.0


def test_19_market_order_rejected_on_corrupted_feed():
    """Verifies that market orders are rejected with FeedIntegrityError if book is crossed or stale."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    # Crossed book
    snap = book.apply_snapshot(
        bids=[(50020.0, 1.0)], asks=[(50010.0, 1.0)], sequence_id=1, timestamps=ts
    )

    sim = RealisticPaperFillSimulator()
    with pytest.raises(FeedIntegrityError):
        sim.simulate_market_order(
            admission_id="ADM-TEST-03",
            book=snap,
            side=OrderSide.BUY,
            quantity=1.0,
        )


def test_20_limit_order_queue_position_and_trade_through():
    """
    Verifies that resting limit orders honor queue position and require
    cumulative trade-through volume before filling.
    """
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    # Existing resting liquidity at 50000.0 is 2.0 BTC
    bids = [(50000.0, 2.0), (49990.0, 5.0)]
    asks = [(50010.0, 2.0)]
    snap = book.apply_snapshot(bids=bids, asks=asks, sequence_id=1, timestamps=ts)

    sim = RealisticPaperFillSimulator(maker_fee_bps=2.0)

    # Place Buy Limit order at 50000.0 for 1.0 BTC (Queue ahead: 2.0 BTC)
    _order_id = sim.place_limit_order(
        admission_id="ADM-TEST-04",
        book=snap,
        side=OrderSide.BUY,
        price=50000.0,
        quantity=1.0,
        placement_utc=1700000000.0,
    )

    # Tick 1: Trade prints at 50000.0 for 1.5 BTC -> Not enough to pass queue ahead (1.5 <= 2.0)
    fills1 = sim.process_trade_tick(
        "BTCUSDT", "BINANCE", trade_price=50000.0, trade_size=1.5, tick_time_utc=1700000001.0
    )
    assert len(fills1) == 0

    # Tick 2: Trade prints at 50000.0 for 1.0 BTC -> Total volume 2.5 > 2.0 -> Excess 0.5 fills 0.5 partially!
    fills2 = sim.process_trade_tick(
        "BTCUSDT", "BINANCE", trade_price=50000.0, trade_size=1.0, tick_time_utc=1700000002.0
    )
    assert len(fills2) == 1
    f2 = fills2[0]
    assert f2.filled_quantity == 0.5
    assert f2.is_partial is True
    assert f2.fill_price == 50000.0
    assert f2.fee_bps == 2.0

    # Tick 3: Trade prints at 49999.0 (traded through!) for 1.0 BTC -> Fills remaining 0.5!
    fills3 = sim.process_trade_tick(
        "BTCUSDT", "BINANCE", trade_price=49999.0, trade_size=1.0, tick_time_utc=1700000003.0
    )
    assert len(fills3) == 1
    f3 = fills3[0]
    assert f3.filled_quantity == 0.5
    assert f3.is_partial is False


def test_21_resting_limit_order_cancellation():
    """Verifies that cancelled resting limit orders do not execute on subsequent trade prints."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")

    ts = MarketEventTimestamps.create(1700000000.0)
    snap = book.apply_snapshot(
        bids=[(50000.0, 1.0)], asks=[(50010.0, 1.0)], sequence_id=1, timestamps=ts
    )

    sim = RealisticPaperFillSimulator()
    order_id = sim.place_limit_order("ADM-TEST-05", snap, OrderSide.BUY, 50000.0, 1.0)

    # Cancel order
    assert sim.cancel_limit_order(order_id) is True
    assert sim.cancel_limit_order("NONEXISTENT") is False

    # Trade prints should produce zero fills
    fills = sim.process_trade_tick("BTCUSDT", "BINANCE", 50000.0, 10.0, 1700000005.0)
    assert len(fills) == 0


def test_22_constitutional_paper_fill_simulation_only_true():
    """Verifies that all PaperFill instances strictly enforce simulation_only=True and zero capital."""
    gateway = LiveMarketDataGateway()
    book = gateway.get_or_create_book("BTCUSDT", "BINANCE")
    ts = MarketEventTimestamps.create(1700000000.0)
    snap = book.apply_snapshot(
        bids=[(50000.0, 1.0)], asks=[(50010.0, 1.0)], sequence_id=1, timestamps=ts
    )

    sim = RealisticPaperFillSimulator()
    fill = sim.simulate_market_order("ADM-TEST-06", snap, OrderSide.BUY, 0.5)

    assert fill.simulation_only is True
    assert fill.real_capital_enabled is False
    assert fill.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"


# ============================================================================
# Category D: Microstructure Markout Engine (Tests 23-27)
# ============================================================================


def test_23_three_tier_markout_taxonomy_calculation():
    """
    Verifies that the three-tier markout taxonomy accurately distinguishes:
    1. Mid-Price Markout (M_mid)
    2. Executable Markout (M_exec)
    3. Net Markout (M_net, after fees and slippage)
    """
    engine = MicrostructureMarkoutEngine()

    fill = PaperFill(
        fill_id="PFILL-TEST-01",
        admission_id="ADM-01",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=5.0,
        fee_usd=25.0,
        slippage_bps=1.0,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.050,
    )

    # Future book at t + 100ms (1700000000.150)
    # best_bid = 50020.0, best_ask = 50022.0, mid = 50021.0
    future_ts = MarketEventTimestamps.create(1700000000.150)
    future_snap = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50020.0, "size": 1.0}],
        asks=[{"price": 50022.0, "size": 1.0}],
        sequence_id=2,
        timestamps=future_ts,
    )

    obs = engine.compute_markout(fill, future_snap, horizon_ms=100)

    assert obs.is_valid is True
    assert obs.data_quality == FeedQualityState.HEALTHY
    assert obs.future_mid_price == 50021.0
    assert obs.future_executable_price == 50020.0  # Liquidation bid

    # M_mid = (50021 - 50000) / 50000 * 10000 = +4.2 bps
    assert obs.gross_mid_markout_bps == pytest.approx(4.2, rel=1e-3)

    # M_exec = (50020 - 50000) / 50000 * 10000 = +4.0 bps
    assert obs.gross_exec_markout_bps == pytest.approx(4.0, rel=1e-3)

    # M_net = M_exec - (fee_bps 5.0 + slippage_bps 1.0) = 4.0 - 6.0 = -2.0 bps
    assert obs.estimated_cost_bps == 6.0
    assert obs.net_markout_bps == pytest.approx(-2.0, rel=1e-3)
    # Notice: Positive gross markout (+4.0 bps) converts to negative net markout (-2.0 bps)


def test_24_sell_side_markout_calculation():
    """Verifies that SELL side markouts correctly measure downward movement and liquidation at ask."""
    engine = MicrostructureMarkoutEngine()

    fill = PaperFill(
        fill_id="PFILL-TEST-02",
        admission_id="ADM-01",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=4.0,
        fee_usd=20.0,
        slippage_bps=0.5,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.050,
    )

    # Future book at t + 1000ms: price dropped!
    # best_bid = 49950.0, best_ask = 49952.0, mid = 49951.0
    future_ts = MarketEventTimestamps.create(1700000001.050)
    future_snap = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 49950.0, "size": 1.0}],
        asks=[{"price": 49952.0, "size": 1.0}],
        sequence_id=5,
        timestamps=future_ts,
    )

    obs = engine.compute_markout(fill, future_snap, horizon_ms=1000)

    assert obs.is_valid is True
    # For SELL: M_exec = (fill_price 50000 - future_ask 49952) / 50000 * 10000 = +9.6 bps
    assert obs.gross_exec_markout_bps == pytest.approx(9.6, rel=1e-3)
    # Total costs = 4.0 fee + 0.5 slippage = 4.5 bps
    # M_net = 9.6 - 4.5 = +5.1 bps
    assert obs.net_markout_bps == pytest.approx(5.1, rel=1e-3)


def test_25_multi_horizon_tracking_100ms_to_30s():
    """Verifies that MicrostructureMarkoutEngine registers and evaluates all 4 standard horizons."""
    engine = MicrostructureMarkoutEngine()
    fill = PaperFill(
        fill_id="PFILL-TEST-03",
        admission_id="ADM-01",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=0.5,
        filled_quantity=0.5,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=5.0,
        fee_usd=12.5,
        slippage_bps=0.0,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.0,
    )

    engine.register_fill(fill)
    assert engine.get_pending_count() == 1

    # Arriving book at t + 100ms (1700000000.100) -> Triggers 100ms horizon
    snap_100ms = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50005.0, "size": 1.0}],
        asks=[{"price": 50015.0, "size": 1.0}],
        sequence_id=2,
        timestamps=MarketEventTimestamps.create(1700000000.100),
    )
    obs_list1 = engine.process_book_update(snap_100ms)
    assert len(obs_list1) == 1
    assert obs_list1[0].horizon_ms == 100

    # Arriving book at t + 1000ms (1700000001.000) -> Triggers 1000ms horizon
    snap_1s = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50010.0, "size": 1.0}],
        asks=[{"price": 50020.0, "size": 1.0}],
        sequence_id=3,
        timestamps=MarketEventTimestamps.create(1700000001.000),
    )
    obs_list2 = engine.process_book_update(snap_1s)
    assert len(obs_list2) == 1
    assert obs_list2[0].horizon_ms == 1000

    # Arriving book at t + 35000ms (1700000035.000) -> Triggers both 5000ms and 30000ms!
    snap_35s = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50050.0, "size": 1.0}],
        asks=[{"price": 50060.0, "size": 1.0}],
        sequence_id=4,
        timestamps=MarketEventTimestamps.create(1700000035.000),
    )
    obs_list3 = engine.process_book_update(snap_35s)
    assert len(obs_list3) == 2
    horizons = {o.horizon_ms for o in obs_list3}
    assert horizons == {5000, 30000}

    # All 4 horizons processed -> Pending fill is automatically evicted
    assert engine.get_pending_count() == 0


def test_26_stale_or_crossed_future_book_invalidates_markout():
    """Verifies that an uncrossed or corrupt future book produces is_valid=False and preserves error state."""
    engine = MicrostructureMarkoutEngine()
    fill = PaperFill(
        fill_id="PFILL-TEST-04",
        admission_id="ADM-01",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=5.0,
        fee_usd=25.0,
        slippage_bps=0.0,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.0,
    )

    # Future book is crossed: bid 50030 > ask 50020
    corrupt_book = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50030.0, "size": 1.0}],
        asks=[{"price": 50020.0, "size": 1.0}],
        sequence_id=10,
        timestamps=MarketEventTimestamps.create(1700000000.100),
        quality=FeedQualityState.CROSSED_BOOK,
    )

    obs = engine.compute_markout(fill, corrupt_book, horizon_ms=100)
    assert obs.is_valid is False
    assert obs.data_quality == FeedQualityState.CROSSED_BOOK
    assert obs.net_markout_bps is None


def test_27_excessive_clock_skew_invalidates_markout():
    """Verifies that snapshot arriving too far from expected horizon is rejected as skewed/stale."""
    engine = MicrostructureMarkoutEngine(max_clock_skew_ms=100.0)
    fill = PaperFill(
        fill_id="PFILL-TEST-05",
        admission_id="ADM-01",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=5.0,
        fee_usd=25.0,
        slippage_bps=0.0,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.0,
    )

    # Expected at t + 100ms = 1700000000.100
    # Actual snapshot timestamp has skew of 500ms (1700000000.600 > max_clock_skew_ms 100ms)
    skewed_book = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50010.0, "size": 1.0}],
        asks=[{"price": 50020.0, "size": 1.0}],
        sequence_id=12,
        timestamps=MarketEventTimestamps.create(1700000000.600),
    )

    obs = engine.compute_markout(fill, skewed_book, horizon_ms=100)
    assert obs.is_valid is False
    assert obs.data_quality == FeedQualityState.STALE_FEED


# =====================================================================
# Phase 5: Forward Performance & Execution Ledger (Tests 28-31)
# =====================================================================


def test_28_ledger_persists_trades_and_markouts():
    """Verifies that simulated paper trades and microstructure markouts roundtrip through SQLite WAL."""
    ledger = ForwardPerformanceLedger(":memory:")

    fill = PaperFill(
        fill_id="PFILL-LEDGER-01",
        admission_id="ADM-LEDGER-TEST",
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=5.0,
        fee_usd=25.0,
        slippage_bps=0.5,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.010,
        queue_delay_ms=10.0,
        is_partial=False,
        fill_model_version="1.0.0",
    )
    ledger.record_trade(fill)

    engine = MicrostructureMarkoutEngine()
    future_snap = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50020.0, "size": 1.0}],
        asks=[{"price": 50022.0, "size": 1.0}],
        sequence_id=2,
        timestamps=MarketEventTimestamps.create(1700000000.110),
    )
    markout = engine.compute_markout(fill, future_snap, horizon_ms=100)
    ledger.record_markout(markout)

    trades = ledger.get_strategy_trades("ADM-LEDGER-TEST")
    assert len(trades) == 1
    t = trades[0]
    assert t.fill_id == "PFILL-LEDGER-01"
    assert t.simulation_only is True
    assert t.real_capital_enabled is False
    assert t.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    assert t.fill_price == 50000.0


def test_29_denominator_transparency_and_confidence_interval():
    """Verifies that performance reporting requires sample size N, standard error, and 95% confidence bounds."""
    ledger = ForwardPerformanceLedger(":memory:")
    engine = MicrostructureMarkoutEngine()

    admission_id = "ADM-SIGNIFICANT-ALPHA"
    # Generate 35 trades with steady positive net markouts
    for i in range(35):
        fill_ts = 1700000000.0 + (i * 60)
        fill = PaperFill(
            fill_id=f"PFILL-SIG-{i:03d}",
            admission_id=admission_id,
            symbol="BTCUSDT",
            venue="BINANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=1.0,
            filled_quantity=1.0,
            fill_price=50000.0,
            benchmark_mid_price=50000.0,
            fee_bps=2.0,
            fee_usd=10.0,
            slippage_bps=0.5,
            decision_timestamp_utc=fill_ts - 0.05,
            fill_timestamp_utc=fill_ts,
            queue_delay_ms=50.0,
            is_partial=False,
            fill_model_version="1.0.0",
        )
        ledger.record_trade(fill)

        # Future book at t + 30s has price increase: bid=50050, ask=50052
        future_ts = fill_ts + 30.0
        future_snap = OrderBookSnapshot(
            symbol="BTCUSDT",
            venue="BINANCE",
            bids=[{"price": 50050.0, "size": 1.0}],
            asks=[{"price": 50052.0, "size": 1.0}],
            sequence_id=i + 1,
            timestamps=MarketEventTimestamps.create(future_ts),
        )
        obs = engine.compute_markout(fill, future_snap, horizon_ms=30000)
        ledger.record_markout(obs)

    scorecard = ledger.get_strategy_scorecard(admission_id)
    assert scorecard is not None
    assert isinstance(scorecard, StrategyForwardScorecard)
    assert scorecard.total_trades == 35
    assert scorecard.winning_trades == 35
    assert scorecard.win_rate == 1.0

    # Verify standard error and confidence interval exist and are calculated correctly
    assert scorecard.standard_error_bps >= 0.0
    assert scorecard.ci_95_lower_bps == pytest.approx(
        scorecard.mean_trade_net_bps - (1.96 * scorecard.standard_error_bps), rel=1e-2
    )
    assert scorecard.ci_95_upper_bps == pytest.approx(
        scorecard.mean_trade_net_bps + (1.96 * scorecard.standard_error_bps), rel=1e-2
    )
    # With N=35 and all positive markouts (~7.5 bps net), lower CI > 0 -> statistically significant positive
    assert scorecard.is_statistically_significant_positive is True


def test_30_markout_curve_aggregation():
    """Verifies that the scorecard aggregates the markout curve across 100ms, 1s, 5s, and 30s horizons."""
    ledger = ForwardPerformanceLedger(":memory:")
    engine = MicrostructureMarkoutEngine()
    admission_id = "ADM-CURVE-TEST"

    fill = PaperFill(
        fill_id="PFILL-CURVE-01",
        admission_id=admission_id,
        symbol="BTCUSDT",
        venue="BINANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        requested_quantity=1.0,
        filled_quantity=1.0,
        fill_price=50000.0,
        benchmark_mid_price=50000.0,
        fee_bps=2.0,
        fee_usd=10.0,
        slippage_bps=0.0,
        decision_timestamp_utc=1700000000.0,
        fill_timestamp_utc=1700000000.0,
    )
    ledger.record_trade(fill)

    # 100ms: bid 50010 (+2.0 bps gross - 2.0 fee = 0.0 net)
    snap_100ms = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50010.0, "size": 1.0}],
        asks=[{"price": 50012.0, "size": 1.0}],
        sequence_id=2,
        timestamps=MarketEventTimestamps.create(1700000000.100),
    )
    obs_100ms = engine.compute_markout(fill, snap_100ms, horizon_ms=100)
    ledger.record_markout(obs_100ms)

    # 1s: bid 50020 (+4.0 bps gross - 2.0 fee = +2.0 net)
    snap_1s = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50020.0, "size": 1.0}],
        asks=[{"price": 50022.0, "size": 1.0}],
        sequence_id=3,
        timestamps=MarketEventTimestamps.create(1700000001.000),
    )
    obs_1s = engine.compute_markout(fill, snap_1s, horizon_ms=1000)
    ledger.record_markout(obs_1s)

    # 5s: bid 50030 (+6.0 bps gross - 2.0 fee = +4.0 net)
    snap_5s = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 50030.0, "size": 1.0}],
        asks=[{"price": 50032.0, "size": 1.0}],
        sequence_id=4,
        timestamps=MarketEventTimestamps.create(1700000005.000),
    )
    obs_5s = engine.compute_markout(fill, snap_5s, horizon_ms=5000)
    ledger.record_markout(obs_5s)

    scorecard = ledger.get_strategy_scorecard(admission_id)
    assert scorecard is not None
    assert 100 in scorecard.markout_curve_bps
    assert 1000 in scorecard.markout_curve_bps
    assert 5000 in scorecard.markout_curve_bps
    assert scorecard.markout_curve_bps[100] == pytest.approx(0.0, abs=0.1)
    assert scorecard.markout_curve_bps[1000] == pytest.approx(2.0, abs=0.1)
    assert scorecard.markout_curve_bps[5000] == pytest.approx(4.0, abs=0.1)


def test_31_nonexistent_strategy_scorecard_returns_none():
    """Verifies that requesting a scorecard for an unregistered or unexecuted admission returns None."""
    ledger = ForwardPerformanceLedger(":memory:")
    assert ledger.get_strategy_scorecard("ADM-DOES-NOT-EXIST") is None
    assert ledger.get_strategy_trades("ADM-DOES-NOT-EXIST") == []


# =====================================================================
# Phase 6: Multi-Dimensional Drift Detector (Tests 32-36)
# =====================================================================


def test_32_drift_detector_inconclusive_on_small_sample_size():
    """Verifies that sample size N < 30 returns INCONCLUSIVE per denominator transparency directives."""
    detector = MultiDimensionalDriftDetector(min_sample_size=30)
    scorecard = StrategyForwardScorecard(
        admission_id="ADM-DRIFT-01",
        total_trades=15,  # N < 30
        winning_trades=10,
        losing_trades=5,
        win_rate=0.67,
        gross_pnl_bps=50.0,
        net_pnl_bps=35.0,
        mean_trade_net_bps=2.33,
        std_dev_bps=4.0,
        standard_error_bps=1.03,
        ci_95_lower_bps=0.31,
        ci_95_upper_bps=4.35,
        max_drawdown_bps=5.0,
        high_water_mark_bps=35.0,
        avg_slippage_bps=0.4,
        avg_fee_bps=1.0,
        markout_curve_bps={100: 0.5, 1000: 1.0, 5000: 2.0, 30000: 2.5},
    )

    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=2.5,
        expected_std_dev_bps=4.0,
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=2.5,
        backtest_trade_returns_bps=[2.0, 2.5, 3.0, 1.5, 2.2] * 10,
    )

    report = detector.evaluate_drift(scorecard=scorecard, baseline=baseline)
    assert report.overall_status == DriftStatus.INCONCLUSIVE
    assert "Insufficient sample size" in report.drift_summary
    assert report.axes["return_distribution"].status == DriftStatus.INCONCLUSIVE


def test_33_drift_detector_normal_when_aligned_with_backtest():
    """Verifies that forward validation well within backtest statistical bounds evaluates to NORMAL."""
    detector = MultiDimensionalDriftDetector(min_sample_size=30)
    backtest_returns = [1.5, 2.0, 2.5, 3.0, 1.8, 2.2, 2.1, 2.9, 1.7, 2.3] * 5

    scorecard = StrategyForwardScorecard(
        admission_id="ADM-DRIFT-02",
        total_trades=50,
        winning_trades=40,
        losing_trades=10,
        win_rate=0.80,
        gross_pnl_bps=120.0,
        net_pnl_bps=105.0,
        mean_trade_net_bps=2.1,
        std_dev_bps=0.5,
        standard_error_bps=0.07,
        ci_95_lower_bps=1.96,
        ci_95_upper_bps=2.24,
        max_drawdown_bps=2.0,
        high_water_mark_bps=105.0,
        avg_slippage_bps=0.5,
        avg_fee_bps=1.0,
        markout_curve_bps={100: 0.5, 1000: 1.2, 5000: 1.8, 30000: 2.2},
    )

    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=2.1,
        expected_std_dev_bps=0.5,
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=2.2,
        backtest_trade_returns_bps=backtest_returns,
        primary_regime="TRENDING",
    )

    report = detector.evaluate_drift(
        scorecard=scorecard,
        baseline=baseline,
        current_regime="TRENDING",
    )
    assert report.overall_status == DriftStatus.NORMAL
    assert report.axes["return_distribution"].status == DriftStatus.NORMAL
    assert report.axes["volatility_shift"].status == DriftStatus.NORMAL
    assert report.axes["markout_decay"].status == DriftStatus.NORMAL
    assert report.axes["slippage_drift"].status == DriftStatus.NORMAL
    assert report.axes["regime_shift"].status == DriftStatus.NORMAL


def test_34_drift_detector_flags_adverse_selection_on_steep_negative_markout_slope():
    """Verifies that severe post-trade markout decay triggers adverse selection flag."""
    detector = MultiDimensionalDriftDetector(min_sample_size=30)
    scorecard = StrategyForwardScorecard(
        admission_id="ADM-DRIFT-03",
        total_trades=40,
        winning_trades=20,
        losing_trades=20,
        win_rate=0.50,
        gross_pnl_bps=10.0,
        net_pnl_bps=-20.0,
        mean_trade_net_bps=-0.5,
        std_dev_bps=3.0,
        standard_error_bps=0.47,
        ci_95_lower_bps=-1.42,
        ci_95_upper_bps=0.42,
        max_drawdown_bps=25.0,
        high_water_mark_bps=10.0,
        avg_slippage_bps=0.6,
        avg_fee_bps=1.0,
        # Sharp adverse selection: fill has positive 100ms markout (+1.0), but drops to -8.5 bps at 30s!
        markout_curve_bps={100: 1.0, 1000: -1.0, 5000: -4.0, 30000: -8.5},
    )

    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=2.0,
        expected_std_dev_bps=3.0,
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=2.0,
        backtest_trade_returns_bps=[1.0, 2.0, 3.0] * 15,
    )

    report = detector.evaluate_drift(scorecard=scorecard, baseline=baseline)
    assert report.axes["markout_decay"].status == DriftStatus.SEVERE
    assert report.overall_status == DriftStatus.SEVERE
    assert "adverse selection" in report.axes["markout_decay"].warning_message.lower()


def test_35_drift_detector_flags_volatility_explosion():
    """Verifies that extreme live volatility deviation (e.g. 3.2x backtest expected) triggers SEVERE status."""
    detector = MultiDimensionalDriftDetector(min_sample_size=30)
    scorecard = StrategyForwardScorecard(
        admission_id="ADM-DRIFT-04",
        total_trades=45,
        winning_trades=25,
        losing_trades=20,
        win_rate=0.55,
        gross_pnl_bps=30.0,
        net_pnl_bps=15.0,
        mean_trade_net_bps=0.33,
        std_dev_bps=16.0,  # 3.2x expected (5.0)
        standard_error_bps=2.38,
        ci_95_lower_bps=-4.33,
        ci_95_upper_bps=5.0,
        max_drawdown_bps=40.0,
        high_water_mark_bps=20.0,
        avg_slippage_bps=0.5,
        avg_fee_bps=1.0,
        markout_curve_bps={100: 0.2, 1000: 0.5, 5000: 0.8, 30000: 1.0},
    )

    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=0.5,
        expected_std_dev_bps=5.0,  # Expected 5.0 vs live 16.0
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=1.0,
        backtest_trade_returns_bps=[0.5] * 45,
    )

    report = detector.evaluate_drift(scorecard=scorecard, baseline=baseline)
    assert report.axes["volatility_shift"].status == DriftStatus.SEVERE
    assert report.overall_status == DriftStatus.SEVERE
    assert report.axes["volatility_shift"].statistic == pytest.approx(3.2, rel=1e-2)


def test_36_drift_detector_flags_severe_distribution_divergence_ks_test():
    """Verifies that distribution shift between backtest and live trade returns triggers KS divergence."""
    detector = MultiDimensionalDriftDetector(min_sample_size=30)
    # Baseline returns centered at +20 bps
    backtest_returns = [18.0, 19.0, 20.0, 21.0, 22.0] * 10

    # Live scorecard centered at -20 bps with small variance
    scorecard = StrategyForwardScorecard(
        admission_id="ADM-DRIFT-05",
        total_trades=50,
        winning_trades=5,
        losing_trades=45,
        win_rate=0.10,
        gross_pnl_bps=-900.0,
        net_pnl_bps=-1000.0,
        mean_trade_net_bps=-20.0,
        std_dev_bps=1.0,
        standard_error_bps=0.14,
        ci_95_lower_bps=-20.27,
        ci_95_upper_bps=-19.73,
        max_drawdown_bps=1000.0,
        high_water_mark_bps=0.0,
        avg_slippage_bps=0.5,
        avg_fee_bps=1.0,
        markout_curve_bps={100: -5.0, 1000: -10.0, 5000: -15.0, 30000: -20.0},
    )

    baseline = BacktestBaselineExpectations(
        expected_mean_return_bps=20.0,
        expected_std_dev_bps=1.4,
        expected_slippage_bps=0.5,
        expected_markout_30s_bps=20.0,
        backtest_trade_returns_bps=backtest_returns,
    )

    report = detector.evaluate_drift(scorecard=scorecard, baseline=baseline)
    assert report.axes["return_distribution"].status == DriftStatus.SEVERE
    assert report.axes["return_distribution"].p_value < 0.001


# =====================================================================
# Phase 7: Strategy Health & Predefined Suspension Controller (Tests 37-40)
# =====================================================================


def test_37_max_drawdown_breach_triggers_suspension_and_cancels_resting_orders():
    """Verifies that max drawdown breach triggers automated suspension and cancels all resting orders."""
    registry = StrategyLeagueRegistry(":memory:")
    adm = _make_test_admission(genome_id="MEC_SUSP_01")
    registry.admit_strategy(adm)
    registry.transition_status(
        adm.admission_id, AdmissionStatus.ACTIVE, "Activated for live paper testing"
    )

    sim = RealisticPaperFillSimulator()
    # Place a resting limit order
    snap = OrderBookSnapshot(
        symbol="BTCUSDT",
        venue="BINANCE",
        bids=[{"price": 49990.0, "size": 2.0}],
        asks=[{"price": 50010.0, "size": 2.0}],
        sequence_id=1,
        timestamps=MarketEventTimestamps.create(1700000000.0),
    )
    order_id = sim.place_limit_order(
        admission_id=adm.admission_id,
        book=snap,
        side=OrderSide.BUY,
        price=49990.0,
        quantity=1.0,
        placement_utc=1700000000.0,
    )
    assert order_id in sim._resting_limit_orders

    policy = SuspensionPolicy(max_drawdown_bps=200.0, auto_cancel_resting_orders=True)
    controller = SuspensionController(registry=registry, policy=policy, fill_simulator=sim)

    # Below limit: 150 bps -> returns False
    suspended = controller.check_drawdown(adm.admission_id, 150.0)
    assert suspended is False
    assert registry.get_strategy(adm.admission_id).status == AdmissionStatus.ACTIVE
    assert order_id in sim._resting_limit_orders

    # At or above limit: 210 bps -> returns True, transitions to SUSPENDED, cancels order
    suspended = controller.check_drawdown(adm.admission_id, 210.0)
    assert suspended is True
    rec = registry.get_strategy(adm.admission_id)
    assert rec.status == AdmissionStatus.SUSPENDED
    assert "Max drawdown breached" in (rec.suspension_reason or "")
    assert order_id not in sim._resting_limit_orders

    # Verify suspension log
    logs = registry.get_suspension_logs(adm.admission_id)
    assert len(logs) == 1
    assert logs[0]["trigger_name"] == "MAX_DRAWDOWN_BREACH"
    assert logs[0]["threshold_val"] == 200.0
    assert logs[0]["observed_val"] == 210.0


def test_38_consecutive_negative_markouts_trigger_quarantine():
    """Verifies that consecutive negative execution quality markouts trigger QUARANTINED state."""
    registry = StrategyLeagueRegistry(":memory:")
    adm = _make_test_admission(genome_id="MEC_SUSP_02")
    registry.admit_strategy(adm)
    registry.transition_status(adm.admission_id, AdmissionStatus.ACTIVE, "Activated")

    policy = SuspensionPolicy(consecutive_negative_markouts_limit=3)
    controller = SuspensionController(registry=registry, policy=policy)

    # 1st negative markout
    assert controller.check_markout_feedback(adm.admission_id, -1.5) is False
    assert registry.get_strategy(adm.admission_id).status == AdmissionStatus.ACTIVE

    # 2nd negative markout
    assert controller.check_markout_feedback(adm.admission_id, -2.0) is False
    assert registry.get_strategy(adm.admission_id).status == AdmissionStatus.ACTIVE

    # 3rd negative markout -> triggers QUARANTINED
    assert controller.check_markout_feedback(adm.admission_id, -0.8) is True
    rec = registry.get_strategy(adm.admission_id)
    assert rec.status == AdmissionStatus.QUARANTINED
    assert "Persistent negative execution quality" in (rec.suspension_reason or "")


def test_39_severe_multi_axis_drift_triggers_suspension_with_immutable_reason():
    """Verifies that severe 5-axis statistical drift automatically triggers suspension."""
    registry = StrategyLeagueRegistry(":memory:")
    adm = _make_test_admission(genome_id="MEC_SUSP_03")
    registry.admit_strategy(adm)
    registry.transition_status(adm.admission_id, AdmissionStatus.ACTIVE, "Activated")

    controller = SuspensionController(registry=registry)

    # Create severe drift report
    report = MultiDimensionalDriftReport(
        admission_id=adm.admission_id,
        sample_size_n=50,
        overall_status=DriftStatus.SEVERE,
        axes={},
        drift_summary="Severe adverse selection and toxic markout collapse detected",
    )

    suspended = controller.check_drift_report(adm.admission_id, report)
    assert suspended is True
    rec = registry.get_strategy(adm.admission_id)
    assert rec.status == AdmissionStatus.SUSPENDED
    assert "Severe statistical drift" in (rec.suspension_reason or "")


def test_40_anti_survivorship_suspended_strategy_remains_permanently_queryable():
    """Verifies that suspended and quarantined strategies remain permanently visible in league queries."""
    registry = StrategyLeagueRegistry(":memory:")
    adm1 = _make_test_admission(genome_id="MEC_PERM_01")
    adm2 = _make_test_admission(genome_id="MEC_PERM_02")
    registry.admit_strategy(adm1)
    registry.admit_strategy(adm2)
    registry.transition_status(adm1.admission_id, AdmissionStatus.ACTIVE, "Active")
    registry.transition_status(adm2.admission_id, AdmissionStatus.ACTIVE, "Active")

    # Suspend adm1
    controller = SuspensionController(registry=registry)
    controller.check_drawdown(adm1.admission_id, 500.0)

    # List all strategies with anti-survivorship bias guarantee (include_historical=True)
    all_strategies = registry.list_strategies(include_historical=True)
    assert len(all_strategies) == 2
    strat_ids = {s.admission_id for s in all_strategies}
    assert adm1.admission_id in strat_ids
    assert adm2.admission_id in strat_ids

    # Querying adm1 returns complete autopsy status
    s1 = registry.get_strategy(adm1.admission_id)
    assert s1 is not None
    assert s1.status == AdmissionStatus.SUSPENDED
    assert s1.suspension_reason is not None
