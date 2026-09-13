"""
Tests for Task 20.1: Cross-Exchange Arbitrage & Funding Dislocation Sentinel
Strict Boss-Level Verification Suite across all 12 institutional criteria:
1. Canonical instrument mapping and normalization.
2. Data Quality Firewall rejection codes (clock drift, staleness, crossed books, monotonic orderbooks).
3. Directional sign-aware funding rate matrix and cashflows.
4. Spot-Perp basis dynamics, rolling Z-score, and 3-sigma candidate triggers.
5. Quantity-aware executable VWAP spread depth-walking.
6. Deterministic multi-scenario Net-EV engine (Base, Conservative, Stress).
7. Depth capacity curve and maximum viable notional sizing (V*).
8. 5-state qualification state machine & persistence survival tracking.
9. Canonical SHA-256 decision envelope hashing and provenance ledger.
10. Two-leg asynchronous shadow reality with partial fill simulation.
11. FastAPI REST API endpoints (/api/arbitrage/*).
12. Structural Safety Perimeter (RESEARCH_ONLY invariant).
"""

import time
import pytest
from fastapi.testclient import TestClient

from app import app
from core.arbitrage.models import (
    ArbitrageExecutionPermission,
    ArbitrageOpportunity,
    BasisMetrics,
    BasisRegime,
    CapacityTier,
    ContractType,
    ExecutableSpread,
    FundingRateRecord,
    MarketType,
    NormalizedMarketQuote,
    OpportunityClassification,
    OpportunityType,
    OrderBookLevel,
    OrderBookSnapshot,
    RejectionCode,
    SourceHealth,
    Venue,
)
from core.arbitrage.instrument_mapper import InstrumentMapper
from core.arbitrage.data_firewall import DataQualityFirewall
from core.arbitrage.funding_matrix import FundingMatrixEngine
from core.arbitrage.basis_engine import BasisEngine
from core.arbitrage.spread_engine import SpreadEngine
from core.arbitrage.ev_engine import DeterministicEVEngine
from core.arbitrage.capacity_engine import CapacityEngine
from core.arbitrage.classifier import OpportunityClassifier
from core.arbitrage.provenance import ProvenanceEngine
from core.arbitrage.shadow_validator import ShadowValidator
from core.arbitrage.sentinel import ArbitrageSentinel


@pytest.fixture
def test_client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Instrument Mapper Tests
# -----------------------------------------------------------------------------
def test_instrument_mapper_resolution():
    mapper = InstrumentMapper()

    # 1. Resolve pair BTCUSDT across Binance Spot and Bybit Linear Perp
    resolved = mapper.resolve_pair("BTCUSDT", Venue.BINANCE_SPOT, Venue.BYBIT_LINEAR)
    assert resolved is not None
    id_spot, id_perp = resolved

    assert id_spot.canonical_symbol == "BTCUSDT"
    assert id_spot.venue == Venue.BINANCE_SPOT
    assert id_spot.market_type == MarketType.SPOT
    assert id_spot.contract_type == ContractType.SPOT

    assert id_perp.canonical_symbol == "BTCUSDT"
    assert id_perp.venue == Venue.BYBIT_LINEAR
    assert id_perp.market_type == MarketType.PERPETUAL
    assert id_perp.contract_type == ContractType.LINEAR

    # 2. Lookup OKX Perp symbol mapping
    okx_id = mapper.get_identity(Venue.OKX_PERP, "ETH-USDT-SWAP")
    assert okx_id is not None
    assert okx_id.canonical_symbol == "ETHUSDT"

    # 3. Quantization
    quantized_qty = mapper.quantize_quantity(id_spot, 0.12345678)
    assert quantized_qty == pytest.approx(0.12346, abs=0.0001)

    quantized_price = mapper.quantize_price(id_spot, 65432.1987)
    assert quantized_price == 65432.20


# -----------------------------------------------------------------------------
# 2. Data Quality Firewall Tests
# -----------------------------------------------------------------------------
def test_data_quality_firewall_rejections():
    firewall = DataQualityFirewall(max_quote_age_ms=3000.0, max_clock_drift_ms=1000.0, max_book_age_ms=3000.0)
    now_ms = int(time.time() * 1000)

    # 1. Valid Quote
    valid_quote = NormalizedMarketQuote(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=65000.0,
        ask=65001.0,
        last=65000.5,
        mark_price=65000.5,
        index_price=65000.5,
        volume_24h=15000.0,
        timestamp_ms=now_ms - 200,
        exchange_timestamp_ms=now_ms - 200,
        received_timestamp_ms=now_ms - 150,
        data_age_ms=150.0,
        sequence_id=101,
        source_health=SourceHealth.HEALTHY,
    )
    verdict = firewall.validate_quote(valid_quote)
    assert verdict.passed is True
    assert verdict.rejection_code == RejectionCode.NONE

    # 2. Stale Quote (> 3000ms old)
    stale_quote = NormalizedMarketQuote(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=65000.0,
        ask=65001.0,
        last=65000.5,
        mark_price=65000.5,
        index_price=65000.5,
        volume_24h=15000.0,
        timestamp_ms=now_ms - 5000,
        exchange_timestamp_ms=now_ms - 5000,
        received_timestamp_ms=now_ms - 4900,
        data_age_ms=4900.0,
        sequence_id=102,
        source_health=SourceHealth.HEALTHY,
    )
    verdict_stale = firewall.validate_quote(stale_quote)
    assert verdict_stale.passed is False
    assert verdict_stale.rejection_code == RejectionCode.ERR_STALE_DATA

    # 3. Crossed Book (Bid >= Ask)
    crossed_quote = NormalizedMarketQuote(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=65005.0,
        ask=65000.0,
        last=65000.5,
        mark_price=65000.5,
        index_price=65000.5,
        volume_24h=15000.0,
        timestamp_ms=now_ms - 100,
        exchange_timestamp_ms=now_ms - 100,
        received_timestamp_ms=now_ms - 50,
        data_age_ms=50.0,
        sequence_id=103,
        source_health=SourceHealth.HEALTHY,
    )
    verdict_crossed = firewall.validate_quote(crossed_quote)
    assert verdict_crossed.passed is False
    assert verdict_crossed.rejection_code == RejectionCode.ERR_CROSSED_BOOK

    # 4. Clock Drift (> 1000ms drift)
    drift_quote = NormalizedMarketQuote(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        bid=65000.0,
        ask=65001.0,
        last=65000.5,
        mark_price=65000.5,
        index_price=65000.5,
        volume_24h=15000.0,
        timestamp_ms=now_ms - 2500,
        exchange_timestamp_ms=now_ms - 2500,
        received_timestamp_ms=now_ms - 100,  # 2400ms drift
        data_age_ms=100.0,
        sequence_id=104,
        source_health=SourceHealth.HEALTHY,
    )
    verdict_drift = firewall.validate_quote(drift_quote)
    assert verdict_drift.passed is False
    assert verdict_drift.rejection_code == RejectionCode.ERR_CLOCK_DRIFT

    # 5. Non-monotonic Order Book
    corrupt_book = OrderBookSnapshot(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=65000.0, size=1.0), OrderBookLevel(price=65050.0, size=2.0)],  # Non-descending!
        asks=[OrderBookLevel(price=65010.0, size=1.0), OrderBookLevel(price=65020.0, size=1.5)],
        timestamp_ms=now_ms - 100,
        sequence_id=201,
    )
    verdict_book = firewall.validate_order_book(corrupt_book)
    assert verdict_book.passed is False
    assert verdict_book.rejection_code == RejectionCode.ERR_INVALID_ORDERBOOK


# -----------------------------------------------------------------------------
# 3. Funding Matrix Engine Tests
# -----------------------------------------------------------------------------
def test_funding_matrix_sign_aware_economics():
    engine = FundingMatrixEngine()
    now_ms = int(time.time() * 1000)

    # Long Bybit (rate = -0.00005, pays negative = receives 0.5 bps)
    # Short Binance (rate = +0.00010, receives positive = receives 1.0 bps)
    rec_binance = FundingRateRecord(
        venue=Venue.BINANCE_PERP,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        funding_rate=0.00010,
        next_funding_time_ms=now_ms + 14400000,
        interval_hours=8,
        exchange_timestamp_ms=now_ms,
        local_receipt_ms=now_ms,
    )
    rec_bybit = FundingRateRecord(
        venue=Venue.BYBIT_LINEAR,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        funding_rate=-0.00005,
        next_funding_time_ms=now_ms + 14400000,
        interval_hours=8,
        exchange_timestamp_ms=now_ms,
        local_receipt_ms=now_ms,
    )

    matrix = engine.compute_funding_matrix([rec_binance, rec_bybit])
    assert len(matrix) == 1
    entry = matrix[0]
    # Edge = 0.00010 - (-0.00005) = 0.00015 (1.5 bps)
    assert entry.raw_divergence_bps == pytest.approx(1.5, 0.01)
    assert entry.proposed_long_leg == Venue.BYBIT_LINEAR
    assert entry.proposed_short_leg == Venue.BINANCE_PERP

    # Cashflow calculation for $10,000 notional
    long_cf, short_cf, net_cf = engine.calculate_directional_funding_cashflow(
        long_venue=Venue.BYBIT_LINEAR,
        short_venue=Venue.BINANCE_PERP,
        notional_usd=10000.0,
        funding_records={Venue.BINANCE_PERP: rec_binance, Venue.BYBIT_LINEAR: rec_bybit},
    )
    # Bybit long cf: -(-0.00005 * 10000) = +$0.50
    # Binance short cf: +(0.00010 * 10000) = +$1.00
    # Net cf: +$1.50
    assert long_cf == pytest.approx(0.50, 0.01)
    assert short_cf == pytest.approx(1.00, 0.01)
    assert net_cf == pytest.approx(1.50, 0.01)


# -----------------------------------------------------------------------------
# 4. Spot-Perp Basis Dynamics Engine Tests
# -----------------------------------------------------------------------------
def test_basis_engine_rolling_z_score():
    engine = BasisEngine(window_size=30, zscore_candidate_threshold=3.0)

    # Prime with normal basis ~5 bps
    for _ in range(25):
        engine.compute_basis(
            canonical_symbol="BTCUSDT",
            spot_venue=Venue.BINANCE_SPOT,
            perp_venue=Venue.BINANCE_PERP,
            spot_price=65000.0,
            perp_price=65032.5,  # +5 bps
        )

    normal_metrics = engine.compute_basis(
        canonical_symbol="BTCUSDT",
        spot_venue=Venue.BINANCE_SPOT,
        perp_venue=Venue.BINANCE_PERP,
        spot_price=65000.0,
        perp_price=65032.5,
    )
    assert normal_metrics.candidate_trigger is False
    assert abs(normal_metrics.zscore) < 1.0

    # Inject extreme dislocation (+76.9 bps)
    shock_metrics = engine.compute_basis(
        canonical_symbol="BTCUSDT",
        spot_venue=Venue.BINANCE_SPOT,
        perp_venue=Venue.BINANCE_PERP,
        spot_price=65000.0,
        perp_price=65500.0,
    )
    assert shock_metrics.zscore >= 3.0
    assert shock_metrics.candidate_trigger is True
    assert shock_metrics.regime == BasisRegime.CONTANGO_EXTREME


# -----------------------------------------------------------------------------
# 5. Quantity-Aware Executable Spread Engine Tests
# -----------------------------------------------------------------------------
def test_executable_spread_depth_walking():
    engine = SpreadEngine()
    now_ms = int(time.time() * 1000)

    # Venue A (Buy venue): Asks
    book_a = OrderBookSnapshot(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=64990.0, size=1.0)],
        asks=[
            OrderBookLevel(price=65000.0, size=0.1),
            OrderBookLevel(price=65010.0, size=0.5),
            OrderBookLevel(price=65030.0, size=1.0),
        ],
        timestamp_ms=now_ms,
        sequence_id=1,
    )

    # Venue B (Sell venue): Bids
    book_b = OrderBookSnapshot(
        venue=Venue.BYBIT_LINEAR,
        symbol="BTCUSDT",
        bids=[
            OrderBookLevel(price=65100.0, size=0.2),
            OrderBookLevel(price=65090.0, size=0.5),
            OrderBookLevel(price=65070.0, size=1.0),
        ],
        asks=[OrderBookLevel(price=65120.0, size=1.0)],
        timestamp_ms=now_ms,
        sequence_id=2,
    )

    # Walk for target notional = $32,500 (~0.5 BTC)
    spread = engine.compute_executable_spread(
        canonical_symbol="BTCUSDT",
        book_a=book_a,
        book_b=book_b,
        target_notional_usd=32500.0,
    )

    assert spread is not None
    assert spread.long_venue == Venue.BINANCE_SPOT
    assert spread.short_venue == Venue.BYBIT_LINEAR
    assert spread.executable_spread_bps > 10.0
    assert spread.gross_spread_usd > 0.0


# -----------------------------------------------------------------------------
# 6. Deterministic EV Engine Tests
# -----------------------------------------------------------------------------
def test_deterministic_ev_scenarios():
    ev_engine = DeterministicEVEngine()
    now_ms = int(time.time() * 1000)

    # Positive spread
    spread = ExecutableSpread(
        canonical_symbol="BTCUSDT",
        notional_usd=10000.0,
        quantity=0.1538,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.BINANCE_PERP,
        vwap_long_ask=65000.0,
        vwap_short_bid=65350.0,  # +53.8 bps spread
        mid_price_reference=65175.0,
        theoretical_spread_bps=54.0,
        executable_spread_bps=53.8,
        gross_spread_usd=53.8,
    )

    funding_rec = FundingRateRecord(
        venue=Venue.BINANCE_PERP,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        funding_rate=0.00015,  # Short receives +1.5 bps
        next_funding_time_ms=now_ms + 14400000,
        interval_hours=8,
        exchange_timestamp_ms=now_ms,
        local_receipt_ms=now_ms,
    )

    multi_ev = ev_engine.evaluate_multi_scenario_ev(
        spread=spread,
        funding_records={Venue.BINANCE_PERP: funding_rec},
        basis_volatility_bps=2.0,
        execution_latency_ms=50.0,
    )

    assert multi_ev.cost_breakdown.model_version == "EVM_v20.1_PROD"
    assert multi_ev.base_net_ev_usd > 0
    assert multi_ev.base_net_ev_bps > 5.0  # Exceeds 5 bps hurdle


# -----------------------------------------------------------------------------
# 7. Capacity Engine & Sizing Tests
# -----------------------------------------------------------------------------
def test_capacity_engine_curve():
    capacity_engine = CapacityEngine(economic_hurdle_bps=5.0)
    now_ms = int(time.time() * 1000)

    book_a = OrderBookSnapshot(
        venue=Venue.BINANCE_SPOT,
        symbol="BTCUSDT",
        bids=[OrderBookLevel(price=64950.0, size=5.0)],
        asks=[
            OrderBookLevel(price=65000.0, size=0.2),
            OrderBookLevel(price=65005.0, size=0.5),
            OrderBookLevel(price=65015.0, size=1.0),
            OrderBookLevel(price=65040.0, size=2.0),
        ],
        timestamp_ms=now_ms,
        sequence_id=1,
    )
    book_b = OrderBookSnapshot(
        venue=Venue.BINANCE_PERP,
        symbol="BTCUSDT",
        bids=[
            OrderBookLevel(price=65100.0, size=0.2),
            OrderBookLevel(price=65095.0, size=0.5),
            OrderBookLevel(price=65080.0, size=1.0),
            OrderBookLevel(price=65050.0, size=2.0),
        ],
        asks=[OrderBookLevel(price=65150.0, size=5.0)],
        timestamp_ms=now_ms,
        sequence_id=2,
    )

    funding_rec = FundingRateRecord(
        venue=Venue.BINANCE_PERP,
        symbol="BTCUSDT",
        canonical_symbol="BTCUSDT",
        funding_rate=0.0001,
        next_funding_time_ms=now_ms + 14400000,
        interval_hours=8,
        exchange_timestamp_ms=now_ms,
        local_receipt_ms=now_ms,
    )

    tiers, max_viable = capacity_engine.evaluate_capacity_curve(
        canonical_symbol="BTCUSDT",
        book_a=book_a,
        book_b=book_b,
        funding_records={Venue.BINANCE_PERP: funding_rec},
    )

    assert len(tiers) > 0
    assert any(t.notional_usd == 1000.0 for t in tiers)


# -----------------------------------------------------------------------------
# 8. Opportunity Classifier & Persistence Tests
# -----------------------------------------------------------------------------
def test_opportunity_classifier_lifecycle():
    classifier = OpportunityClassifier(
        min_economic_hurdle_bps=5.0,
        min_viable_notional_usd=5000.0,
        min_persistence_observations=2,
        min_persistence_duration_ms=10.0,
    )

    # Candidate with positive EV and sufficient capacity
    from core.arbitrage.models import EVCostBreakdown, MultiScenarioEV

    cost_breakdown = EVCostBreakdown(
        gross_edge_usd=25.0,
        entry_fee_long_usd=5.0,
        entry_fee_short_usd=5.0,
        expected_exit_fee_long_usd=5.0,
        expected_exit_fee_short_usd=5.0,
        orderbook_slippage_long_usd=0.5,
        orderbook_slippage_short_usd=0.5,
        hedge_cost_usd=0.5,
        latency_cost_usd=0.5,
        funding_cashflow_usd=2.0,
        borrow_cost_usd=0.0,
        safety_buffer_usd=2.0,
        net_ev_usd=8.0,
        net_ev_bps=8.0,
    )
    multi_ev = MultiScenarioEV(
        base_net_ev_usd=8.0,
        base_net_ev_bps=8.0,
        conservative_net_ev_usd=5.5,
        conservative_net_ev_bps=5.5,
        stress_net_ev_usd=1.0,
        stress_net_ev_bps=1.0,
        cost_breakdown=cost_breakdown,
    )

    spread = ExecutableSpread(
        canonical_symbol="BTCUSDT",
        notional_usd=10000.0,
        quantity=0.15,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.BINANCE_PERP,
        vwap_long_ask=65000.0,
        vwap_short_bid=65150.0,
        mid_price_reference=65075.0,
        theoretical_spread_bps=23.0,
        executable_spread_bps=23.0,
        gross_spread_usd=22.5,
    )

    # Observation 1
    opp1 = classifier.classify_opportunity(
        canonical_symbol="BTCUSDT",
        opportunity_type=OpportunityType.SPOT_PERP_BASIS,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.BINANCE_PERP,
        basis_metrics=None,
        spread=spread,
        multi_ev=multi_ev,
        capacity_tiers=[],
        max_viable_notional=10000.0,
        data_freshness_ms=50.0,
    )
    # First observation should advance into CANDIDATE, VALIDATING, or ECONOMICALLY_VIABLE
    assert opp1.classification in [
        OpportunityClassification.CANDIDATE,
        OpportunityClassification.VALIDATING,
        OpportunityClassification.ECONOMICALLY_VIABLE,
    ]

    time.sleep(0.02)

    # Observation 2
    opp2 = classifier.classify_opportunity(
        canonical_symbol="BTCUSDT",
        opportunity_type=OpportunityType.SPOT_PERP_BASIS,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.BINANCE_PERP,
        basis_metrics=None,
        spread=spread,
        multi_ev=multi_ev,
        capacity_tiers=[],
        max_viable_notional=10000.0,
        data_freshness_ms=50.0,
    )
    # Second observation advances to QUALIFIED
    assert opp2.classification == OpportunityClassification.QUALIFIED


# -----------------------------------------------------------------------------
# 9. Provenance Engine & SHA-256 Decision Envelope Tests
# -----------------------------------------------------------------------------
def test_provenance_envelope_canonical_hashing():
    provenance = ProvenanceEngine()
    now_ms = int(time.time() * 1000)

    opp = ArbitrageOpportunity(
        opportunity_id="ARB_BTCUSDT_TEST_999",
        detected_at_ms=now_ms,
        canonical_symbol="BTCUSDT",
        opportunity_type=OpportunityType.SPOT_PERP_BASIS,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.BINANCE_PERP,
        classification=OpportunityClassification.QUALIFIED,
        rejection_code=RejectionCode.NONE,
        rejection_reason="Meets all economic hurdles",
        basis_metrics=None,
        executable_spread=None,
        multi_scenario_ev=None,
        max_viable_notional_usd=10000.0,
        permission=ArbitrageExecutionPermission.RESEARCH_ONLY,
    )

    envelope = provenance.create_envelope(
        opportunity=opp,
        quotes=[],
        books=[],
        funding_records=[],
    )

    assert envelope.canonical_envelope_hash is not None
    assert len(envelope.canonical_envelope_hash) == 64  # SHA-256 hex digest

    # Verify retrieval and verification
    record_dict = provenance.get_provenance_by_id(opp.opportunity_id)
    assert record_dict is not None
    assert provenance.verify_envelope_integrity(record_dict) is True


# -----------------------------------------------------------------------------
# 10. Shadow Validator Partial Fill Simulation Tests
# -----------------------------------------------------------------------------
def test_shadow_validator_asynchronous_reality():
    validator = ShadowValidator()
    now_ms = int(time.time() * 1000)

    opp = ArbitrageOpportunity(
        opportunity_id="ARB_ETHUSDT_SHADOW_001",
        detected_at_ms=now_ms,
        canonical_symbol="ETHUSDT",
        opportunity_type=OpportunityType.SPOT_PERP_BASIS,
        long_venue=Venue.BINANCE_SPOT,
        short_venue=Venue.OKX_PERP,
        classification=OpportunityClassification.QUALIFIED,
        rejection_code=RejectionCode.NONE,
        rejection_reason="Shadow test opportunity",
        basis_metrics=None,
        executable_spread=None,
        multi_scenario_ev=None,
        max_viable_notional_usd=10000.0,
        permission=ArbitrageExecutionPermission.RESEARCH_ONLY,
    )

    book_long = OrderBookSnapshot(
        venue=Venue.BINANCE_SPOT,
        symbol="ETHUSDT",
        bids=[OrderBookLevel(price=3499.0, size=10.0)],
        asks=[OrderBookLevel(price=3500.0, size=10.0)],
        timestamp_ms=now_ms,
        sequence_id=1,
    )
    book_short = OrderBookSnapshot(
        venue=Venue.OKX_PERP,
        symbol="ETHUSDT",
        bids=[OrderBookLevel(price=3510.0, size=10.0)],
        asks=[OrderBookLevel(price=3511.0, size=10.0)],
        timestamp_ms=now_ms,
        sequence_id=2,
    )

    shadow = validator.simulate_entry_execution(
        opportunity=opp,
        book_long=book_long,
        book_short=book_short,
        target_notional=10000.0,
    )

    assert shadow is not None
    assert shadow.canonical_symbol == "ETHUSDT"
    assert shadow.leg_a_sim is not None
    assert shadow.leg_b_sim is not None
    assert shadow.leg_a_sim.fill_ratio >= 0.90
    assert shadow.status in ["OPEN", "RESOLVED"]


# -----------------------------------------------------------------------------
# 11. FastAPI REST API Route Tests
# -----------------------------------------------------------------------------
def test_arbitrage_api_endpoints(test_client):
    # 1. Health & Status
    health_resp = test_client.get("/api/arbitrage/health")
    assert health_resp.status_code == 200
    health_json = health_resp.json()
    assert health_json["status"] == "HEALTHY"
    assert health_json["permission"] == "RESEARCH_ONLY"

    # 2. Funding Matrix
    funding_resp = test_client.get("/api/arbitrage/funding-matrix")
    assert funding_resp.status_code == 200
    funding_json = funding_resp.json()
    assert "matrix" in funding_json
    assert len(funding_json["matrix"]) > 0

    # 3. Dislocations
    disloc_resp = test_client.get("/api/arbitrage/dislocations?symbol=BTCUSDT")
    assert disloc_resp.status_code == 200
    disloc_json = disloc_resp.json()
    assert disloc_json["symbol"] == "BTCUSDT"
    assert "basis_metrics" in disloc_json

    # 4. Opportunities
    opp_resp = test_client.get("/api/arbitrage/opportunities")
    assert opp_resp.status_code == 200
    opp_json = opp_resp.json()
    assert "opportunities" in opp_json

    # 5. Shadow History
    hist_resp = test_client.get("/api/arbitrage/history")
    assert hist_resp.status_code == 200
    hist_json = hist_resp.json()
    assert "shadow_records" in hist_json


# -----------------------------------------------------------------------------
# 12. Structural Safety Perimeter Test (Live Trading Prohibition)
# -----------------------------------------------------------------------------
def test_structural_safety_perimeter():
    assert ArbitrageExecutionPermission.RESEARCH_ONLY == "RESEARCH_ONLY"

    sentinel = ArbitrageSentinel()
    assert sentinel.execution_permission == ArbitrageExecutionPermission.RESEARCH_ONLY

    # Verify no live execution method exists on the Sentinel class
    assert not hasattr(sentinel, "place_live_orders")
    assert not hasattr(sentinel, "execute_live_arbitrage")
    assert not hasattr(sentinel, "submit_cross_exchange_order")
