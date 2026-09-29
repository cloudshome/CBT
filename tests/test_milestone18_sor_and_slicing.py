"""
tests/test_milestone18_sor_and_slicing.py
=========================================
Comprehensive Test Suite for Milestone 18:
  - Multi-Venue Smart Order Routing (SOR) Engine
  - Almgren-Chriss (2000) Optimal Trajectory Slicer
  - High-Frequency Fill Reconciliation & Forensic Slippage Ledger
  - REST API Endpoints & Pre-Trade Invariants
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from core.audit_bus import audit_bus
from core.execution.almgren_chriss import (
    AlmgrenChrissSchedule,
    AlmgrenChrissSlicer,
    InvalidSlicingParametersError,
)
from core.execution.live_router import LiveExecutionReceipt
from core.execution.reconciliation_ledger import (
    ReconciliationLedger,
)
from core.execution.smart_order_router import (
    InsufficientLiquidityError,
    InvalidOrderParametersError,
    L2DepthLevel,
    SmartOrderRouteQuote,
    SmartOrderRouter,
    VenueDegradedError,
    VenueFeeSchedule,
    VenueOrderBook,
    VenueSplitQuote,
)

# =============================================================================
# 1. SMART ORDER ROUTER (SOR) TESTS
# =============================================================================


class TestSmartOrderRouter:
    """Tests multi-venue depth walking, cost minimization, and fail-closed safety."""

    def test_sor_invalid_parameters_rejected(self):
        """Verifies rejection of non-positive quantities, NaN, and invalid order sides."""
        router = SmartOrderRouter()
        books = {"BINANCE": VenueOrderBook(exchange="BINANCE", symbol="BTC/USDT")}

        with pytest.raises(InvalidOrderParametersError, match="Invalid order side"):
            router.calculate_optimal_split("BTC/USDT", "HOLD", 1.0, books)

        with pytest.raises(InvalidOrderParametersError, match="total_qty"):
            router.calculate_optimal_split("BTC/USDT", "BUY", -0.5, books)

        with pytest.raises(InvalidOrderParametersError, match="total_qty"):
            router.calculate_optimal_split("BTC/USDT", "BUY", float("nan"), books)

        with pytest.raises(InvalidOrderParametersError, match="total_qty"):
            router.calculate_optimal_split("BTC/USDT", "BUY", float("inf"), books)

    def test_sor_single_venue_execution(self):
        """Verifies routing 100% to the single available venue."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            bids=[L2DepthLevel(price=59900.0, size=2.0), L2DepthLevel(price=59800.0, size=5.0)],
            asks=[L2DepthLevel(price=60100.0, size=2.0), L2DepthLevel(price=60200.0, size=5.0)],
            timestamp_ms=now_ms,
        )

        quote = router.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=1.5,
            venue_books={"BINANCE": book},
        )

        assert isinstance(quote, SmartOrderRouteQuote)
        assert len(quote.splits) == 1
        assert quote.splits[0].exchange == "BINANCE"
        assert quote.splits[0].percentage == 100.0
        assert quote.splits[0].allocated_qty == 1.5
        assert quote.splits[0].expected_vwap == 60100.0
        assert quote.total_fee_usd > 0.0

    def test_sor_optimal_split_cost_minimization(self):
        """
        Verifies that SOR splits parent order between Binance and Bybit
        to achieve a lower total cost than either venue alone.
        """
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        # Venue 1: Cheap initial liquidity, then steep ladder
        # Venue 2: Slightly higher base price, but deep liquidity
        binance_book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            asks=[
                L2DepthLevel(price=60000.0, size=1.0),
                L2DepthLevel(price=60500.0, size=1.0),
                L2DepthLevel(price=61000.0, size=5.0),
            ],
            bids=[L2DepthLevel(price=59900.0, size=5.0)],
            timestamp_ms=now_ms,
        )

        bybit_book = VenueOrderBook(
            exchange="BYBIT",
            symbol="BTC/USDT",
            asks=[
                L2DepthLevel(price=60050.0, size=2.0),
                L2DepthLevel(price=60150.0, size=3.0),
            ],
            bids=[L2DepthLevel(price=59900.0, size=5.0)],
            timestamp_ms=now_ms,
        )

        books = {"BINANCE": binance_book, "BYBIT": bybit_book}
        total_qty = 2.5

        quote = router.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=total_qty,
            venue_books=books,
        )

        # Best execution should take 1.0 from Binance at 60000, and 1.5 from Bybit at 60050
        # Instead of taking the 60500 level on Binance!
        assert len(quote.splits) == 2
        splits_by_ex = {s.exchange: s for s in quote.splits}

        assert "BINANCE" in splits_by_ex
        assert "BYBIT" in splits_by_ex
        assert splits_by_ex["BINANCE"].allocated_qty == pytest.approx(1.0, abs=0.05)
        assert splits_by_ex["BYBIT"].allocated_qty == pytest.approx(1.5, abs=0.05)
        assert quote.weighted_vwap < 60100.0

    def test_sor_degraded_and_stale_venue_isolation(self):
        """Verifies that degraded or stale venues are isolated and excluded."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        # Binance is marked degraded
        binance_book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            asks=[L2DepthLevel(price=60000.0, size=5.0)],
            timestamp_ms=now_ms,
            is_degraded=True,
        )

        # Bybit is healthy
        bybit_book = VenueOrderBook(
            exchange="BYBIT",
            symbol="BTC/USDT",
            asks=[L2DepthLevel(price=60050.0, size=5.0)],
            timestamp_ms=now_ms,
            is_degraded=False,
        )

        quote = router.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=2.0,
            venue_books={"BINANCE": binance_book, "BYBIT": bybit_book},
            current_time_ms=now_ms,
        )

        assert len(quote.splits) == 1
        assert quote.splits[0].exchange == "BYBIT"
        assert quote.splits[0].percentage == 100.0

    def test_sor_all_venues_degraded_fails_closed(self):
        """Verifies fail-closed exception when all venues are degraded."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        books = {
            "BINANCE": VenueOrderBook(exchange="BINANCE", symbol="BTC/USDT", is_degraded=True),
            "BYBIT": VenueOrderBook(exchange="BYBIT", symbol="BTC/USDT", is_degraded=True),
        }

        with pytest.raises(VenueDegradedError, match="All venues are degraded"):
            router.calculate_optimal_split("BTC/USDT", "BUY", 1.0, books, current_time_ms=now_ms)

    def test_sor_insufficient_liquidity_fails_closed(self):
        """Verifies fail-closed when book depth cannot satisfy order size."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            asks=[L2DepthLevel(price=60000.0, size=1.0)],
            timestamp_ms=now_ms,
        )

        with pytest.raises(InsufficientLiquidityError, match="insufficient"):
            router.calculate_optimal_split(
                "BTC/USDT", "BUY", 10.0, {"BINANCE": book}, current_time_ms=now_ms
            )

    def test_sor_slippage_tolerance_breach_fails_closed(self):
        """Verifies fail-closed when execution causes slippage to exceed threshold."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        book = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            bids=[L2DepthLevel(price=60000.0, size=1.0)],
            asks=[
                L2DepthLevel(price=60000.0, size=0.1),
                L2DepthLevel(price=65000.0, size=5.0),  # Huge jump (~8.3% slippage)
            ],
            timestamp_ms=now_ms,
        )

        with pytest.raises(InsufficientLiquidityError, match="exceeds tolerance"):
            router.calculate_optimal_split(
                "BTC/USDT",
                "BUY",
                2.0,
                {"BINANCE": book},
                max_slippage_bps=50.0,
                current_time_ms=now_ms,
            )

    @pytest.mark.asyncio
    async def test_sor_execute_smart_order_multi_leg(self):
        """Verifies multi-leg dispatch via LiveExecutionRouter."""
        router = SmartOrderRouter()

        quote = SmartOrderRouteQuote(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=2.0,
            reference_mid_price=60000.0,
            weighted_vwap=60025.0,
            total_fee_usd=12.0,
            total_effective_cost_usd=120062.0,
            total_slippage_bps=4.1,
            splits=[
                VenueSplitQuote(
                    exchange="BINANCE",
                    allocated_qty=1.0,
                    allocated_notional=60000.0,
                    expected_vwap=60000.0,
                    expected_fee_usd=6.0,
                    expected_slippage_bps=0.0,
                    percentage=50.0,
                ),
                VenueSplitQuote(
                    exchange="BYBIT",
                    allocated_qty=1.0,
                    allocated_notional=60050.0,
                    expected_vwap=60050.0,
                    expected_fee_usd=6.0,
                    expected_slippage_bps=8.3,
                    percentage=50.0,
                ),
            ],
            routing_reason="Optimal 50/50 split",
        )

        mock_receipt = LiveExecutionReceipt(
            success=True,
            status="FILLED",
            client_order_id="CID_MOCK",
            exchange_order_id="EX_MOCK",
            exchange="BINANCE",
            environment="TESTNET",
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            requested_qty=1.0,
            executed_qty=1.0,
            executed_price=60000.0,
            cumulative_quote_qty=60000.0,
            latency_ms=15.0,
            audit_event_id="AUD_MOCK",
            message="OK",
        )

        with patch(
            "core.execution.smart_order_router.live_execution_router.execute_live_order",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = mock_receipt
            receipts = await router.execute_smart_order(quote, environment="TESTNET")
            assert len(receipts) == 2
            assert mock_exec.call_count == 2


# =============================================================================
# 2. ALMGREN-CHRISS OPTIMAL SLICER TESTS
# =============================================================================


class TestAlmgrenChrissSlicer:
    """Tests Almgren-Chriss (2000) optimal trajectory mathematical properties."""

    def test_almgren_chriss_invalid_parameters(self):
        """Verifies rejection of invalid inputs."""
        slicer = AlmgrenChrissSlicer()

        with pytest.raises(InvalidSlicingParametersError, match="Invalid side"):
            slicer.generate_execution_schedule("BTC/USDT", "INVALID", 1.0, 60000.0)

        with pytest.raises(InvalidSlicingParametersError, match="total_qty"):
            slicer.generate_execution_schedule("BTC/USDT", "BUY", -1.0, 60000.0)

        with pytest.raises(InvalidSlicingParametersError, match="current_price"):
            slicer.generate_execution_schedule("BTC/USDT", "BUY", 1.0, -100.0)

        with pytest.raises(InvalidSlicingParametersError, match="time_horizon_sec"):
            slicer.generate_execution_schedule("BTC/USDT", "BUY", 1.0, 60000.0, time_horizon_sec=0)

        with pytest.raises(InvalidSlicingParametersError, match="num_intervals"):
            slicer.generate_execution_schedule("BTC/USDT", "BUY", 1.0, 60000.0, num_intervals=0)

        with pytest.raises(InvalidSlicingParametersError, match="risk_aversion_lambda"):
            slicer.generate_execution_schedule(
                "BTC/USDT", "BUY", 1.0, 60000.0, risk_aversion_lambda=-0.1
            )

    def test_almgren_chriss_linear_twap_when_lambda_zero(self):
        """
        When lambda = 0 (risk-neutral), the Almgren-Chriss trajectory
        must collapse exactly to linear TWAP with equal-sized slices.
        """
        slicer = AlmgrenChrissSlicer()
        total_qty = 10.0
        num_intervals = 5

        schedule = slicer.generate_execution_schedule(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=total_qty,
            current_price=60000.0,
            time_horizon_sec=500.0,
            num_intervals=num_intervals,
            risk_aversion_lambda=0.0,
        )

        assert isinstance(schedule, AlmgrenChrissSchedule)
        assert schedule.is_linear_twap is True
        assert len(schedule.slices) == num_intervals

        # Slices must each equal 10.0 / 5 = 2.0
        expected_slice_size = total_qty / num_intervals
        for s in schedule.slices:
            assert s.slice_qty == pytest.approx(expected_slice_size, abs=1e-5)
            assert s.fraction_of_total == pytest.approx(1.0 / num_intervals, abs=1e-5)

        # Final remaining quantity after last slice must be 0
        assert schedule.slices[-1].remaining_qty_after == pytest.approx(0.0, abs=1e-5)

    def test_almgren_chriss_front_loaded_when_lambda_positive(self):
        """
        When lambda > 0 (risk-averse), the trajectory must be front-loaded:
        earlier slices must be strictly larger than later slices to reduce inventory risk.
        """
        slicer = AlmgrenChrissSlicer()
        schedule = slicer.generate_execution_schedule(
            symbol="BTC/USDT",
            side="SELL",
            total_qty=10.0,
            current_price=60000.0,
            time_horizon_sec=600.0,
            num_intervals=6,
            risk_aversion_lambda=1e-4,  # Meaningful risk aversion
        )

        assert schedule.is_linear_twap is False
        assert len(schedule.slices) == 6

        slice_sizes = [s.slice_qty for s in schedule.slices]

        # Earlier slices must be larger than later slices
        for i in range(len(slice_sizes) - 1):
            assert slice_sizes[i] >= slice_sizes[i + 1]

        # First slice significantly larger than last slice
        assert slice_sizes[0] > slice_sizes[-1]

    def test_almgren_chriss_conservation_of_quantity(self):
        """Verifies that the sum of discrete slices matches total_qty exactly."""
        slicer = AlmgrenChrissSlicer()
        total_qty = 7.34567

        schedule = slicer.generate_execution_schedule(
            symbol="ETH/USDT",
            side="BUY",
            total_qty=total_qty,
            current_price=3000.0,
            num_intervals=12,
            risk_aversion_lambda=2e-5,
        )

        sum_slices = sum(s.slice_qty for s in schedule.slices)
        assert sum_slices == pytest.approx(total_qty, abs=1e-5)

    def test_almgren_chriss_cost_and_variance_tradeoff(self):
        """
        Verifies the fundamental Almgren-Chriss trade-off:
        Higher lambda decreases variance V[x] while increasing expected cost E[x].
        """
        slicer = AlmgrenChrissSlicer()

        # Risk-neutral
        sched_neutral = slicer.generate_execution_schedule(
            symbol="SOL/USDT",
            side="BUY",
            total_qty=100.0,
            current_price=150.0,
            risk_aversion_lambda=0.0,
        )

        # Risk-averse
        sched_averse = slicer.generate_execution_schedule(
            symbol="SOL/USDT",
            side="BUY",
            total_qty=100.0,
            current_price=150.0,
            risk_aversion_lambda=1e-3,
        )

        # Higher lambda front-loads, increasing impact cost
        assert sched_averse.expected_total_cost_usd > sched_neutral.expected_total_cost_usd
        # But significantly decreases inventory risk variance
        assert sched_averse.variance_cost_usd < sched_neutral.variance_cost_usd

    def test_almgren_chriss_nonlinear_impact_square_root_law(self):
        """Verifies square-root law: quadrupling slice notional doubles impact."""
        slicer = AlmgrenChrissSlicer()
        adv = 100_000_000.0
        vol = 0.65

        impact_1 = slicer.calculate_nonlinear_price_impact(100_000.0, adv, vol)
        impact_4 = slicer.calculate_nonlinear_price_impact(400_000.0, adv, vol)

        # Quadrupled notional -> sqrt(4) = 2x impact
        assert impact_4 == pytest.approx(impact_1 * 2.0, rel=1e-3)


# =============================================================================
# 3. RECONCILIATION LEDGER TESTS
# =============================================================================


class TestReconciliationLedger:
    """Tests sub-millisecond fill recording, slippage bps, and forensic queries."""

    def test_reconciliation_slippage_calculation(self):
        """Verifies directional slippage in basis points."""
        ledger = ReconciliationLedger()

        # BUY: Expected $60,000, Executed $59,940 (Price improvement of $60 = +10 bps)
        slip_buy_fav = ledger.calculate_slippage_bps("BUY", 60000.0, 59940.0)
        assert slip_buy_fav == pytest.approx(10.0, abs=0.01)

        # BUY: Expected $60,000, Executed $60,120 (Adverse slippage of $120 = -20 bps)
        slip_buy_adv = ledger.calculate_slippage_bps("BUY", 60000.0, 60120.0)
        assert slip_buy_adv == pytest.approx(-20.0, abs=0.01)

        # SELL: Expected $60,000, Executed $60,060 (Price improvement = +10 bps)
        slip_sell_fav = ledger.calculate_slippage_bps("SELL", 60000.0, 60060.0)
        assert slip_sell_fav == pytest.approx(10.0, abs=0.01)

        # SELL: Expected $60,000, Executed $59,880 (Adverse slippage = -20 bps)
        slip_sell_adv = ledger.calculate_slippage_bps("SELL", 60000.0, 59880.0)
        assert slip_sell_adv == pytest.approx(-20.0, abs=0.01)

    def test_reconciliation_status_classification(self):
        """Verifies classification of MATCHED, PARTIAL_FILL, OVERFILL, and SLIPPAGE_BREACH."""
        ledger = ReconciliationLedger()

        # Normal matched fill
        rec_matched = ledger.record_fill(
            parent_order_id="P1",
            client_order_id="C1",
            exchange_order_id="E1",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            requested_qty=1.0,
            executed_qty=1.0,
            expected_price=60000.0,
            executed_price=60005.0,
        )
        assert rec_matched.reconciliation_status == "MATCHED"

        # Partial fill
        rec_partial = ledger.record_fill(
            parent_order_id="P2",
            client_order_id="C2",
            exchange_order_id="E2",
            exchange="BYBIT",
            symbol="BTC/USDT",
            side="BUY",
            requested_qty=2.0,
            executed_qty=0.5,
            expected_price=60000.0,
            executed_price=60000.0,
        )
        assert rec_partial.reconciliation_status == "PARTIAL_FILL"

        # Slippage breach
        rec_breach = ledger.record_fill(
            parent_order_id="P3",
            client_order_id="C3",
            exchange_order_id="E3",
            exchange="BINANCE",
            symbol="BTC/USDT",
            side="BUY",
            requested_qty=1.0,
            executed_qty=1.0,
            expected_price=60000.0,
            executed_price=61000.0,  # ~166.7 bps adverse slippage
            max_allowed_slippage_bps=50.0,
        )
        assert rec_breach.reconciliation_status == "SLIPPAGE_BREACH"

    def test_reconciliation_persistence_and_querying(self):
        """Verifies SQLite storage and retrieval with forensic filters."""
        ledger = ReconciliationLedger()
        sym = "TEST_BTC/USDT"

        rec = ledger.record_fill(
            parent_order_id="P_PERSIST",
            client_order_id="C_PERSIST",
            exchange_order_id="E_PERSIST",
            exchange="BINANCE",
            symbol=sym,
            side="BUY",
            requested_qty=0.5,
            executed_qty=0.5,
            expected_price=50000.0,
            executed_price=50000.0,
            fee_paid_usd=2.5,
            route_venue="BINANCE",
            total_roundtrip_ms=12.5,
        )

        records = ledger.list_records(limit=10, symbol=sym)
        assert len(records) >= 1
        found = next(r for r in records if r["reconciliation_id"] == rec.reconciliation_id)
        assert found["symbol"] == sym
        assert found["requested_qty"] == 0.5
        assert found["fee_paid_usd"] == 2.5
        assert found["total_roundtrip_ms"] == 12.5

    def test_reconciliation_summary_statistics(self):
        """Verifies aggregated metrics over the evaluation window."""
        ledger = ReconciliationLedger()
        sym = "TEST_ETH/USDT"

        # Insert a matched fill and a partial fill
        ledger.record_fill(
            "P_SUM1",
            "C_SUM1",
            "E_SUM1",
            "BYBIT",
            sym,
            "BUY",
            10.0,
            10.0,
            3000.0,
            3000.0,
            fee_paid_usd=3.0,
        )
        ledger.record_fill(
            "P_SUM2",
            "C_SUM2",
            "E_SUM2",
            "BYBIT",
            sym,
            "BUY",
            10.0,
            5.0,
            3000.0,
            3000.0,
            fee_paid_usd=1.5,
        )

        summary = ledger.get_reconciliation_summary(symbol=sym, window_hours=1)
        assert summary["total_reconciled_orders"] >= 2
        assert summary["total_fees_usd"] >= 4.5
        assert "BYBIT" in summary["venue_distribution"]


# =============================================================================
# 4. REST API ENDPOINT TESTS
# =============================================================================


class TestMilestone18RestApi:
    """Verifies HTTP endpoints for SOR quotes, Almgren-Chriss schedules, and reports."""

    def test_api_sor_route_quote(self):
        """Verifies POST /api/execution/sor/route-quote."""
        client = TestClient(app)
        res = client.post(
            "/api/execution/sor/route-quote",
            json={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "total_qty": 1.0,
                "max_slippage_bps": 150.0,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "quote" in data
        assert data["quote"]["symbol"] == "BTC/USDT"
        assert data["quote"]["total_qty"] == 1.0
        assert len(data["quote"]["splits"]) >= 1

    def test_api_almgren_chriss_schedule(self):
        """Verifies POST /api/execution/slicer/almgren-chriss."""
        client = TestClient(app)
        res = client.post(
            "/api/execution/slicer/almgren-chriss",
            json={
                "symbol": "BTC/USDT",
                "side": "BUY",
                "total_qty": 5.0,
                "current_price": 60000.0,
                "time_horizon_sec": 600.0,
                "num_intervals": 6,
                "risk_aversion_lambda": 1e-5,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "schedule" in data
        assert len(data["schedule"]["slices"]) == 6
        assert data["schedule"]["total_qty"] == 5.0

    def test_api_reconciliation_report_and_records(self):
        """Verifies GET /api/execution/reconciliation/report and /records."""
        client = TestClient(app)

        # GET Report
        res_rep = client.get("/api/execution/reconciliation/report")
        assert res_rep.status_code == 200
        data_rep = res_rep.json()
        assert data_rep["status"] == "SUCCESS"
        assert "report" in data_rep
        assert "fill_rate_pct" in data_rep["report"]

        # GET Records
        res_rec = client.get("/api/execution/reconciliation/records?limit=10")
        assert res_rec.status_code == 200
        data_rec = res_rec.json()
        assert data_rec["status"] == "SUCCESS"
        assert isinstance(data_rec["records"], list)

    def test_sor_fee_tier_crossover(self):
        """Verifies that favorable VIP fee tiers shift order split toward the discounted venue."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        # Equal price and depth on both venues
        book_a = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            asks=[L2DepthLevel(price=60000.0, size=5.0)],
            timestamp_ms=now_ms,
        )
        book_b = VenueOrderBook(
            exchange="BYBIT",
            symbol="BTC/USDT",
            asks=[L2DepthLevel(price=60000.0, size=5.0)],
            timestamp_ms=now_ms,
        )

        # Bybit has much cheaper fee tier (2 bps taker vs Binance 10 bps taker)
        fees = {
            "BINANCE": VenueFeeSchedule(exchange="BINANCE", taker_fee_bps=10.0),
            "BYBIT": VenueFeeSchedule(exchange="BYBIT", taker_fee_bps=2.0),
        }

        quote = router.calculate_optimal_split(
            symbol="BTC/USDT",
            side="BUY",
            total_qty=2.0,
            venue_books={"BINANCE": book_a, "BYBIT": book_b},
            venue_fees=fees,
            current_time_ms=now_ms,
        )

        # All 2.0 BTC must route to Bybit due to fee dominance
        bybit_split = next(s for s in quote.splits if s.exchange == "BYBIT")
        assert bybit_split.percentage == 100.0

    def test_sor_sell_optimal_split(self):
        """Verifies that SELL side optimization maximizes net proceeds across venues."""
        router = SmartOrderRouter()
        now_ms = int(time.time() * 1000)

        # Binance bids: 60000 (1.0), 59500 (2.0)
        # Bybit bids: 59950 (2.0)
        book_binance = VenueOrderBook(
            exchange="BINANCE",
            symbol="BTC/USDT",
            bids=[L2DepthLevel(price=60000.0, size=1.0), L2DepthLevel(price=59500.0, size=2.0)],
            timestamp_ms=now_ms,
        )
        book_bybit = VenueOrderBook(
            exchange="BYBIT",
            symbol="BTC/USDT",
            bids=[L2DepthLevel(price=59950.0, size=2.0)],
            timestamp_ms=now_ms,
        )

        quote = router.calculate_optimal_split(
            symbol="BTC/USDT",
            side="SELL",
            total_qty=2.0,
            venue_books={"BINANCE": book_binance, "BYBIT": book_bybit},
            current_time_ms=now_ms,
        )

        # Best execution for selling 2.0: 1.0 on Binance at 60000, 1.0 on Bybit at 59950
        splits_by_ex = {s.exchange: s for s in quote.splits}
        assert splits_by_ex["BINANCE"].allocated_qty == pytest.approx(1.0, abs=0.05)
        assert splits_by_ex["BYBIT"].allocated_qty == pytest.approx(1.0, abs=0.05)

    def test_almgren_chriss_buy_vs_sell_directionality(self):
        """Verifies expected price increases for BUY (adverse impact) and decreases for SELL."""
        slicer = AlmgrenChrissSlicer()
        base_price = 50000.0

        sched_buy = slicer.generate_execution_schedule(
            "BTC/USDT", "BUY", 5.0, base_price, num_intervals=4
        )
        sched_sell = slicer.generate_execution_schedule(
            "BTC/USDT", "SELL", 5.0, base_price, num_intervals=4
        )

        for s in sched_buy.slices:
            assert s.expected_slice_price >= base_price

        for s in sched_sell.slices:
            assert s.expected_slice_price <= base_price

    def test_almgren_chriss_single_slice_interval(self):
        """When num_intervals = 1, exactly one slice must execute 100% of the quantity."""
        slicer = AlmgrenChrissSlicer()
        sched = slicer.generate_execution_schedule("BTC/USDT", "BUY", 3.0, 50000.0, num_intervals=1)

        assert len(sched.slices) == 1
        assert sched.slices[0].slice_qty == 3.0
        assert sched.slices[0].fraction_of_total == 1.0
        assert sched.slices[0].remaining_qty_after == 0.0

    def test_reconciliation_anomaly_audit_bus_emission(self):
        """Verifies audit_bus event emission upon slippage breach anomaly."""
        ledger = ReconciliationLedger()

        with patch.object(audit_bus, "emit_event") as mock_emit:
            ledger.record_fill(
                parent_order_id="P_BREACH",
                client_order_id="C_BREACH",
                exchange_order_id="E_BREACH",
                exchange="BINANCE",
                symbol="BTC/USDT",
                side="BUY",
                requested_qty=1.0,
                executed_qty=1.0,
                expected_price=60000.0,
                executed_price=61000.0,  # Extreme breach (~166.7 bps adverse)
                max_allowed_slippage_bps=20.0,
            )
            assert mock_emit.called
            call_kwargs = mock_emit.call_args[1]
            assert call_kwargs["event_type"] == "EXECUTION_RECONCILIATION_ANOMALY"
            assert call_kwargs["severity"] in ("WARNING", "ERROR")

    def test_reconciliation_overfill_status(self):
        """Verifies OVERFILL classification when executed exceeds requested beyond tolerance."""
        ledger = ReconciliationLedger()
        rec = ledger.record_fill(
            parent_order_id="P_OVER",
            client_order_id="C_OVER",
            exchange_order_id="E_OVER",
            exchange="BYBIT",
            symbol="BTC/USDT",
            side="BUY",
            requested_qty=1.0,
            executed_qty=1.5,  # 50% overfill
            expected_price=60000.0,
            executed_price=60000.0,
        )
        assert rec.reconciliation_status == "OVERFILL"
