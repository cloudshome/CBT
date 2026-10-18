"""P10.7 — cross-exchange premium/discount + funding spread as a stored series.

Milestone deliverable (docs/DATA_INFRASTRUCTURE_ROADMAP.md §9):
\"premium/discount + funding spread queryable\". The live probe is the
same function health/preflight already call. All tests are fully
offline (FakeVenueTransport + tmp stores + injected clock).
"""

from __future__ import annotations

import pandas as pd
import pytest

from data.cross_exchange import (
    ALL_CROSS_METRICS,
    CROSS_COLUMNS,
    CROSS_PK,
    FUNDING_RATE,
    FUNDING_SPREAD,
    PREMIUM_PCT,
    PRICE,
    VENUES,
    CrossExchangeCollector,
    CrossExchangeStore,
    FakeVenueTransport,
    default_http_get,
    derive_funding_spread,
    derive_premium,
    empty_frame,
    floor_ts,
    snapshot_funding,
    snapshot_prices,
)
from data.derivatives import DerivativesStore, coerce_derivative_frame
from data.store import CandleStore, normalise_klines

EXCH_BYBIT, MARKET, SYMBOL = "bybit", "perp", "BTCUSDT"
START = 1_749_600_000_000  # hour-aligned AND 8h-aligned
HOUR = 3_600_000
STEP_1M = 60_000
FUND_STEP = 8 * HOUR


@pytest.fixture
def store(tmp_path):
    return CrossExchangeStore(root=tmp_path / "cross")


@pytest.fixture
def candles(tmp_path):
    return CandleStore(root=tmp_path / "candles")


@pytest.fixture
def derivs(tmp_path):
    return DerivativesStore(root=tmp_path / "derivs")


def _candles(
    exchange: str, closes: list[float], *, start: int = START, step: int = STEP_1M
) -> pd.DataFrame:
    rows = []
    for i, close in enumerate(closes):
        ts = start + i * step
        rows.append(
            {
                "ts": ts,
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 10.0,
            }
        )
    return normalise_klines(
        pd.DataFrame(rows),
        exchange=exchange,
        market=MARKET,
        symbol=SYMBOL,
        timeframe="1m",
        ingested_at=start,
    )


def _funding_frame(
    exchange: str, rates: list[float], *, start: int = START, step: int = FUND_STEP
) -> pd.DataFrame:
    return coerce_derivative_frame(
        [
            {
                "ts": start + i * step,
                "exchange": exchange,
                "market": "perp",
                "symbol": SYMBOL,
                "metric": "funding_rate",
                "value": rate,
                "ingested_at": start,
            }
            for i, rate in enumerate(rates)
        ]
    )


def collect(
    store,
    *,
    candle_store=None,
    deriv_store=None,
    transport=None,
    since=None,
    until=None,
    snapshot=True,
    dry_run=False,
    binance_last=None,
    binance_funding=None,
    clock=None,
):
    t = (
        transport
        if transport is not None
        else FakeVenueTransport(start_ts=START, end_ts=START + 4 * FUND_STEP)
    )
    return CrossExchangeCollector(
        store,
        candle_store=candle_store,
        deriv_store=deriv_store,
        get=t.get,
        funding_fetch=t.funding_history,
        clock=clock if clock is not None else (lambda: START + 2 * HOUR),
        sleep_s=0.0,
        sleep_fn=lambda _s: None,
    ).collect(
        SYMBOL,
        market=MARKET,
        timeframe="1m",
        since=since,
        until=until,
        snapshot=snapshot,
        dry_run=dry_run,
        binance_last=binance_last if binance_last is not None else {SYMBOL: 60_000.0},
        binance_funding=binance_funding if binance_funding is not None else {SYMBOL: 0.0001},
    )


# --------------------------------------------------------------------------- #
# Schema / derivation
# --------------------------------------------------------------------------- #


def test_empty_frame_matches_derivatives_schema():
    df = empty_frame()
    assert list(df.columns) == CROSS_COLUMNS
    assert CROSS_PK == ["exchange", "market", "symbol", "metric", "ts"]
    assert set(ALL_CROSS_METRICS) == {PRICE, PREMIUM_PCT, FUNDING_RATE, FUNDING_SPREAD}


def test_derive_premium_is_percent_vs_reference():
    ref = pd.DataFrame({"ts": [100, 200, 300], "close": [100.0, 100.0, 200.0]})
    oth = pd.DataFrame({"ts": [100, 200, 300], "close": [101.0, 100.0, 198.0]})
    prem = derive_premium(
        ref, oth, exchange=EXCH_BYBIT, market=MARKET, symbol=SYMBOL, ingested_at=1
    )
    assert prem["metric"].tolist() == [PREMIUM_PCT] * 3
    assert prem["value"].round(6).tolist() == [1.0, 0.0, -1.0]
    assert (prem["exchange"] == EXCH_BYBIT).all()


def test_derive_premium_joins_only_common_ts_and_drops_zero_ref():
    ref = pd.DataFrame({"ts": [100, 200, 300], "close": [100.0, 0.0, 100.0]})
    oth = pd.DataFrame({"ts": [100, 200, 400], "close": [110.0, 1.0, 1.0]})
    prem = derive_premium(ref, oth)
    # 100 is common and non-zero; 200 is zero-ref (dropped); 300/400 unmatched
    assert prem["ts"].tolist() == [100]
    assert float(prem["value"].iloc[0]) == pytest.approx(10.0)


def test_derive_funding_spread_is_other_minus_reference():
    ref = pd.DataFrame({"ts": [100, 200], "funding_rate": [0.0001, 0.0002]})
    oth = pd.DataFrame({"ts": [100, 200], "funding_rate": [0.0003, 0.0002]})
    spr = derive_funding_spread(
        ref, oth, exchange=EXCH_BYBIT, market="perp", symbol=SYMBOL, ingested_at=1
    )
    assert spr["metric"].tolist() == [FUNDING_SPREAD] * 2
    assert spr["value"].round(8).tolist() == [0.0002, 0.0]


# --------------------------------------------------------------------------- #
# The probe (one function, many surfaces)
# --------------------------------------------------------------------------- #


def test_venues_are_kucoin_okx_bybit():
    assert list(VENUES) == ["kucoin", "okx", "bybit"]
    assert "XAUUSD" not in VENUES["bybit"].symbols
    assert "XAUUSD" in VENUES["kucoin"].symbols


def test_snapshot_prices_uses_newest_candle_and_flags():
    t = FakeVenueTransport(
        prices={
            "kucoin": {SYMBOL: 100.0},
            "okx": {SYMBOL: 101.5},  # +1.5% → flag
            "bybit": {SYMBOL: 100.0},
        }
    )
    snap = snapshot_prices({SYMBOL: 100.0}, get=t.get)
    assert snap["ok"] is True  # venues responded; flag ≠ failure
    assert snap["threshold_pct"] == 1.0
    assert snap["exchanges"]["kucoin"]["symbols"][SYMBOL]["flag"] is False
    assert snap["exchanges"]["okx"]["symbols"][SYMBOL]["flag"] is True
    assert snap["exchanges"]["okx"]["symbols"][SYMBOL]["deviation_pct"] == 1.5
    assert snap["exchanges"]["bybit"]["symbols"][SYMBOL]["price"] == 100.0


def test_snapshot_prices_degrades_on_unreachable_venue():
    def boom(url, timeout=6):
        raise ConnectionError("no route")

    snap = snapshot_prices({SYMBOL: 100.0}, get=boom)
    assert snap["ok"] is False
    for name in ("kucoin", "okx", "bybit"):
        err = snap["exchanges"][name]["symbols"][SYMBOL]["error"]
        assert "ConnectionError" in err


def test_snapshot_skips_xau_on_bybit():
    t = FakeVenueTransport()
    snap = snapshot_prices({"XAUUSD": 2300.0}, get=t.get)
    assert "XAUUSD" not in snap["exchanges"]["bybit"]["symbols"]
    assert "XAUUSD" in snap["exchanges"]["kucoin"]["symbols"]


def test_agent_probe_is_snapshot_prices():
    """Invariant: do not write a second probe."""
    from brain.agent import _cross_exchange_probe

    t = FakeVenueTransport(
        prices={
            "kucoin": {SYMBOL: 60_000.0},
            "okx": {SYMBOL: 60_000.0},
            "bybit": {SYMBOL: 60_000.0},
        }
    )
    # Both entry points must agree on the same payload.
    via_mod = snapshot_prices({SYMBOL: 60_000.0}, get=t.get)
    # The agent wrapper uses requests.get; inject the fake there.
    import data.cross_exchange as cx

    original = cx.snapshot_prices

    def wrapped(last, **kw):
        kw.setdefault("get", t.get)
        return original(last, **kw)

    cx.snapshot_prices = wrapped
    try:
        via_agent = _cross_exchange_probe({SYMBOL: 60_000.0})
    finally:
        cx.snapshot_prices = original
    assert via_agent["exchanges"]["bybit"]["symbols"][SYMBOL]["price"] == 60_000.0
    assert via_mod["exchanges"]["kucoin"]["ok"] is True


# --------------------------------------------------------------------------- #
# Store + collector
# --------------------------------------------------------------------------- #


def test_snapshot_persist_is_queryable(store):
    runs = collect(store, snapshot=True, candle_store=None, deriv_store=None)
    # KuCoin/OKX/Bybit each wrote price + premium_pct
    assert store.count("kucoin", "spot", SYMBOL, PREMIUM_PCT) == 1
    assert store.count("okx", "spot", SYMBOL, PREMIUM_PCT) == 1
    assert store.count("bybit", "spot", SYMBOL, PREMIUM_PCT) == 1
    prem = store.read("bybit", "spot", SYMBOL, PREMIUM_PCT)
    assert float(prem["value"].iloc[0]) == pytest.approx(0.2, abs=1e-6)  # 60120/60000-1
    assert any(r.metric == PREMIUM_PCT for r in runs.values())


def test_collect_from_candle_stores_writes_bybit_premium(store, candles):
    candles.write(_candles("binance", [100.0, 100.0, 100.0, 100.0]))
    candles.write(_candles("bybit", [101.0, 102.0, 99.0, 100.0]))
    runs = collect(store, candle_store=candles, snapshot=False)
    key = f"{EXCH_BYBIT}.{MARKET}.{PREMIUM_PCT}"
    assert key in runs
    assert runs[key].rows_new == 4
    prem = store.read(EXCH_BYBIT, MARKET, SYMBOL, PREMIUM_PCT)
    assert prem["value"].round(6).tolist() == [1.0, 2.0, -1.0, 0.0]
    assert prem["ts"].is_unique


def test_collect_funding_spread_is_queryable(store, derivs):
    derivs.write(_funding_frame("binance", [0.0001, 0.0001, 0.0001, 0.0001]))
    t = FakeVenueTransport(
        start_ts=START,
        end_ts=START + 3 * FUND_STEP,
        funding={
            "bybit": {SYMBOL: 0.0003},
            "kucoin": {SYMBOL: 0.0001},
            "okx": {SYMBOL: 0.0001},
        },
    )
    runs = collect(
        store,
        deriv_store=derivs,
        transport=t,
        snapshot=False,
        since=START,
        until=START + 3 * FUND_STEP,
    )
    assert f"{EXCH_BYBIT}.perp.{FUNDING_SPREAD}" in runs
    spr = store.read(EXCH_BYBIT, "perp", SYMBOL, FUNDING_SPREAD)
    assert not spr.empty
    # other (≈0.0003 + noise) − 0.0001 is positive on the common 8h grid
    assert (spr["value"] > 0).all()
    assert spr["ts"].is_unique


def test_rerun_adds_zero_rows(store, candles, derivs):
    candles.write(_candles("binance", [100.0, 100.0, 100.0]))
    candles.write(_candles("bybit", [100.5, 100.5, 100.5]))
    derivs.write(_funding_frame("binance", [0.0001, 0.0001]))
    t = FakeVenueTransport(start_ts=START, end_ts=START + FUND_STEP)
    kwargs = dict(
        candle_store=candles,
        deriv_store=derivs,
        transport=t,
        snapshot=True,
        since=START,
        until=START + FUND_STEP,
    )
    collect(store, **kwargs)
    second = collect(store, **kwargs)
    for key, run in second.items():
        assert run.rows_new == 0, key


def test_dry_run_writes_nothing(store, candles):
    candles.write(_candles("binance", [100.0, 100.0]))
    candles.write(_candles("bybit", [101.0, 101.0]))
    runs = collect(store, candle_store=candles, snapshot=True, dry_run=True)
    assert runs[f"{EXCH_BYBIT}.{MARKET}.{PREMIUM_PCT}"].rows_new == 2
    assert store.list_series() == []


def test_store_isolates_venues_and_metrics(store):
    collect(store, snapshot=True, candle_store=None, deriv_store=None)
    listed = store.list_series()
    venues = {s["exchange"] for s in listed}
    assert {"kucoin", "okx", "bybit"} <= venues
    metrics = {s["metric"] for s in listed}
    assert PREMIUM_PCT in metrics
    assert PRICE in metrics


def test_floor_ts_buckets_snapshots():
    assert floor_ts(START + 899_999, 900_000) == START
    assert floor_ts(START + 900_000, 900_000) == START + 900_000


def test_default_get_is_offline_in_demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    get = default_http_get()
    snap = snapshot_prices({SYMBOL: 60_000.0}, get=get)
    assert snap["exchanges"]["bybit"]["ok"] is True
    # and funding snapshot works on the same transport
    fund = snapshot_funding({SYMBOL: 0.0001}, get=get)
    assert "bybit" in fund["exchanges"]
    assert "funding_rate" in fund["exchanges"]["bybit"]["symbols"][SYMBOL]


def test_cli_cross_demo_is_offline_and_queryable(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main

    root = tmp_path / "cross"
    argv = [
        "cross",
        "collect",
        "--symbol",
        "BTCUSDT",
        "--root",
        str(root),
        "--since",
        str(START),
        "--until",
        str(START + FUND_STEP),
        "--sleep",
        "0",
        "--json",
    ]
    assert main(argv) == 0
    assert main(argv) == 0  # idempotent re-run
    store = CrossExchangeStore(root=root)
    # DEMO snapshot wrote premium for the three venues
    assert store.count("bybit", "spot", SYMBOL, PREMIUM_PCT) == 1
    assert main(["cross", "status", "--symbol", "BTCUSDT", "--root", str(root), "--json"]) == 0


def test_bybit_funding_history_parses_v5(monkeypatch):
    from data.bybit_client import BybitClient

    rows = [
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0002",
            "fundingRateTimestamp": str(START + FUND_STEP),
        },
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0001",
            "fundingRateTimestamp": str(START),
        },
    ]

    def fake(self, hosts, path, params, timeout=None, retries=None):
        assert path == "/v5/market/funding/history"
        assert params["category"] == "linear"
        return {"retCode": 0, "result": {"list": rows}}, {}, 200

    monkeypatch.setattr(BybitClient, "_get_page_with_headers", fake)
    df = BybitClient().funding_history(SYMBOL, START, START + FUND_STEP, 200)
    assert list(df.columns) == ["ts", "funding_rate"]
    assert df["ts"].tolist() == [START, START + FUND_STEP]  # ascending
    assert df["funding_rate"].tolist() == [0.0001, 0.0002]


def test_bybit_funding_history_skips_gold(monkeypatch):
    from data.bybit_client import BybitClient

    calls = []

    def fake(self, hosts, path, params, timeout=None, retries=None):
        calls.append(path)
        return {"retCode": 0, "result": {"list": []}}, {}, 200

    monkeypatch.setattr(BybitClient, "_get_page_with_headers", fake)
    df = BybitClient().funding_history("XAUUSD")
    assert calls == []
    assert df.empty
