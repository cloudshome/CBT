"""
P0-1 regression: synthetic market data must never masquerade as empirical.

The defect these lock down, measured before the fix:

    SyntheticMarketProvider keys: [close, high, low, open, symbol, timeframe,
                                   timestamp, volume]      <- no provenance
    after fetch_external_ohlcv with all providers down:
        is_synthetic values: [0, 0, 0, 0, 0]               <- stamped "real"

A transient outage therefore wrote random walks into ``market_data.db``
labelled as observed market data. Those rows fed ``market_states``, which is
the table the analogue engine trusts to decide ``EMPIRICAL`` — so an outage
silently re-opened the evidence gate.
"""

from __future__ import annotations

import pytest

from core.data_streamer import data_streamer
from core.evidence_integrity import (
    EVIDENCE_KEY,
    EvidenceGrade,
    grade_of,
    stamp_records,
    weakest_grade,
)
from core.market_providers import SyntheticMarketProvider, market_gateway

# ---------------------------------------------------------------------------
# Provenance is immutable at the boundary (downgrade-only ratchet)
# ---------------------------------------------------------------------------


def test_untagged_record_is_fabricated_by_default():
    """Untagged data is untrusted data. The safe default is the strict one."""
    assert grade_of({"close": 1.0}) is EvidenceGrade.FABRICATED


def test_first_stamp_assigns_grade():
    recs = [{"close": 1.0}]
    stamp_records(recs, EvidenceGrade.EMPIRICAL)
    assert recs[0][EVIDENCE_KEY] == "EMPIRICAL"
    assert recs[0]["is_synthetic"] == 0


def test_fabricated_can_never_be_promoted_to_empirical():
    """The core architectural rule — this is the laundering bug in miniature."""
    recs = [{"close": 1.0}]
    stamp_records(recs, EvidenceGrade.FABRICATED)
    stamp_records(recs, EvidenceGrade.EMPIRICAL)  # attempt to launder
    assert recs[0][EVIDENCE_KEY] == "FABRICATED"
    assert recs[0]["is_synthetic"] == 1


def test_legacy_is_synthetic_flag_is_honoured():
    """Rows written before this layer existed must still grade correctly."""
    assert grade_of({"close": 1.0, "is_synthetic": 1}) is EvidenceGrade.FABRICATED
    assert grade_of({"close": 1.0, "is_synthetic": 0}) is EvidenceGrade.EMPIRICAL


def test_weakest_link_across_a_series():
    series = [
        {EVIDENCE_KEY: "EMPIRICAL"},
        {EVIDENCE_KEY: "EMPIRICAL"},
        {EVIDENCE_KEY: "FABRICATED"},
    ]
    assert weakest_grade(series) is EvidenceGrade.FABRICATED


def test_empty_series_is_fabricated_not_empirical():
    """'No data' must never be mistaken for 'clean data'."""
    assert weakest_grade([]) is EvidenceGrade.FABRICATED


# ---------------------------------------------------------------------------
# The sentinel provider fabricates nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sentinel_returns_no_candles():
    candles = await SyntheticMarketProvider().fetch_historical_ohlcv("BTC/USDT", "15m", limit=100)
    assert candles == []


@pytest.mark.asyncio
async def test_sentinel_returns_no_depth():
    ob = await SyntheticMarketProvider().fetch_order_book_depth("BTC/USDT", limit=10)
    assert ob["asks"] == []
    assert ob["bids"] == []


@pytest.mark.asyncio
async def test_sentinel_ticker_declares_unavailability():
    t = await SyntheticMarketProvider().fetch_live_ticker("BTC/USDT")
    assert t["evidence_grade"] == "FABRICATED"
    assert t["data_unavailable"] is True


# ---------------------------------------------------------------------------
# End-to-end: total provider outage cannot produce empirical data
# ---------------------------------------------------------------------------


@pytest.fixture
def all_providers_down():
    """Simulate every real venue being unreachable."""
    original = market_gateway.providers
    market_gateway.providers = []
    try:
        yield
    finally:
        market_gateway.providers = original


@pytest.mark.asyncio
async def test_gateway_returns_empty_when_all_providers_down(all_providers_down):
    data = await market_gateway.get_ohlcv("BTC/USDT", "15m", limit=50)
    assert data == []
    assert weakest_grade(data) is EvidenceGrade.FABRICATED


@pytest.mark.asyncio
async def test_gateway_stamps_every_record_it_returns():
    """No record may escape the gateway without provenance."""
    data = await market_gateway.get_ohlcv("BTC/USDT", "15m", limit=20)
    assert all(EVIDENCE_KEY in c for c in data)


@pytest.mark.asyncio
async def test_outage_never_produces_records_labelled_empirical(all_providers_down):
    """
    THE regression. Previously produced ``is_synthetic == 0`` on random data.
    A record is laundered if it claims to be real while its grade says
    otherwise — there must be zero such records.
    """
    candles = await data_streamer.fetch_external_ohlcv("BTC/USDT", "15m", limit=10)
    laundered = [
        c
        for c in candles
        if c.get("is_synthetic") == 0 and c.get(EVIDENCE_KEY) != EvidenceGrade.EMPIRICAL.label
    ]
    assert laundered == [], f"{len(laundered)} record(s) laundered as empirical"

    # Every returned bar must agree with itself about its own provenance.
    for c in candles:
        expected_flag = 0 if grade_of(c) is EvidenceGrade.EMPIRICAL else 1
        assert c.get("is_synthetic") == expected_flag


def test_synthetic_bootstrap_bars_are_graded_and_filterable():
    """
    Cold-start bootstrap bars may exist for charting, but must carry the
    FABRICATED grade and be excludable from any empirical query.
    """
    bars = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
    assert bars, "generator should still produce bars for explicit opt-in callers"
    assert weakest_grade(bars) is EvidenceGrade.FABRICATED
    assert all(b["is_synthetic"] == 1 for b in bars)

    pure = data_streamer.get_candles("BTC/USDT", "15m", limit=200, exclude_synthetic=True)
    assert all(grade_of(c) is EvidenceGrade.EMPIRICAL for c in pure)


@pytest.mark.asyncio
async def test_streamer_preserves_fabricated_grade_from_gateway(monkeypatch):
    """
    Directly exercise the line that caused the bug.

    ``fetch_external_ohlcv`` used to run ``c["is_synthetic"] = 0`` over every
    record the gateway returned. Here the gateway hands back explicitly
    FABRICATED bars; the streamer must preserve that grade rather than
    overwrite it, and must not persist them.
    """
    fabricated = [
        {
            "timestamp": 1_700_000_000_000 + i * 900_000,
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            EVIDENCE_KEY: EvidenceGrade.FABRICATED.label,
            "is_synthetic": 1,
        }
        for i in range(5)
    ]

    async def fake_get_ohlcv(*_args, **_kwargs):
        return fabricated

    persisted: list = []
    monkeypatch.setattr(market_gateway, "get_ohlcv", fake_get_ohlcv)
    monkeypatch.setattr(data_streamer, "save_candles", lambda *a, **k: persisted.append(a))

    out = await data_streamer.fetch_external_ohlcv("BTC/USDT", "15m", limit=5)

    assert all(c[EVIDENCE_KEY] == "FABRICATED" for c in out), "grade was overwritten"
    assert all(c["is_synthetic"] == 1 for c in out), "legacy flag was laundered to 0"
    assert persisted == [], "fabricated bars must never be persisted as market evidence"


@pytest.mark.asyncio
async def test_streamer_persists_and_keeps_empirical_grade(monkeypatch):
    """The happy path must still work: real bars are graded and persisted."""
    real = [
        {
            "timestamp": 1_700_000_000_000 + i * 900_000,
            "symbol": "BTC/USDT",
            "timeframe": "15m",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            EVIDENCE_KEY: EvidenceGrade.EMPIRICAL.label,
            "is_synthetic": 0,
        }
        for i in range(5)
    ]

    async def fake_get_ohlcv(*_args, **_kwargs):
        return real

    persisted: list = []
    monkeypatch.setattr(market_gateway, "get_ohlcv", fake_get_ohlcv)
    monkeypatch.setattr(data_streamer, "save_candles", lambda *a, **k: persisted.append(a))

    out = await data_streamer.fetch_external_ohlcv("BTC/USDT", "15m", limit=5)

    assert all(c[EVIDENCE_KEY] == "EMPIRICAL" for c in out)
    assert len(persisted) == 1, "empirical bars should be persisted"
