"""P10.4 — derivatives as time series (funding / OI / mark / index / basis).

Milestone deliverable (docs/DATA_INFRASTRUCTURE_ROADMAP.md §9): "series
queryable; liquidations() proxy renamed honestly". All tests are fully
offline and deterministic (FakeDerivativesTransport + injected clock).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.binance_client import BinanceClient
from data.derivatives import (
    ALL_METRICS,
    BASIS,
    DERIVATIVE_COLUMNS,
    DERIVATIVE_PK,
    FUNDING_RATE,
    INDEX_PRICE,
    MARK_PRICE,
    OPEN_INTEREST,
    OPEN_INTEREST_VALUE,
    BinanceDerivativesTransport,
    DerivativesCollector,
    DerivativesStore,
    DerivativesTransportError,
    FakeDerivativesTransport,
    coerce_derivative_frame,
    default_derivatives_transport,
    derive_basis,
    empty_frame,
)

EXCH, MARKET, SYMBOL = "binance", "perp", "BTCUSDT"
START = 1_749_600_000_000  # aligned to hour AND 8h
HOUR = 3_600_000
WINDOW = 60 * HOUR  # 60 hours of hourly mark/index/OI


@pytest.fixture
def store(tmp_path):
    return DerivativesStore(root=tmp_path)


def make_transport(**kw) -> FakeDerivativesTransport:
    kw.setdefault("start_ts", START)
    kw.setdefault("end_ts", START + WINDOW + HOUR)  # exclusive fake end
    return FakeDerivativesTransport(**kw)


def collect(
    store,
    transport,
    *,
    since=None,
    until=None,
    metrics=None,
    dry_run=False,
    sleep_s=0.0,
    clock=None,
):
    return DerivativesCollector(
        store,
        transport,
        sleep_s=sleep_s,
        clock=clock if clock is not None else (lambda: START + WINDOW),
        sleep_fn=lambda _s: None,
    ).collect(
        SYMBOL,
        market=MARKET,
        since=since,
        until=until,
        metrics=metrics,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# Schema / store
# --------------------------------------------------------------------------- #


def test_empty_frame_has_canonical_columns_and_dtypes():
    df = empty_frame()
    assert list(df.columns) == DERIVATIVE_COLUMNS
    assert df["ts"].dtype == np.int64
    assert df["value"].dtype == np.float64
    assert df["metric"].dtype.name in ("str", "string")


def test_primary_key_is_the_upsert_key():
    assert DERIVATIVE_PK == ["exchange", "market", "symbol", "metric", "ts"]


def test_coerce_fills_missing_fields():
    df = coerce_derivative_frame([{"ts": 1_750_000_000_000, "value": 1.5}])
    assert df.loc[0, "exchange"] == ""
    assert df.loc[0, "metric"] == ""
    assert int(df.loc[0, "ingested_at"]) == 0


def test_store_round_trip_and_upsert(store):
    rows = coerce_derivative_frame(
        [
            {
                "ts": START,
                "exchange": EXCH,
                "market": MARKET,
                "symbol": SYMBOL,
                "metric": FUNDING_RATE,
                "value": 0.0001,
                "ingested_at": 1_760_000_000_000,
            }
        ]
    )
    assert store.write(rows) == 1
    assert store.count(EXCH, MARKET, SYMBOL, FUNDING_RATE) == 1
    # rewrite (venue revision) — upsert, no duplicate
    rows["value"] = 0.0002
    store.write(rows)
    back = store.read(EXCH, MARKET, SYMBOL, FUNDING_RATE)
    assert len(back) == 1
    assert float(back["value"].iloc[0]) == 0.0002


def test_store_isolates_metrics(store):
    a = coerce_derivative_frame(
        [
            {
                "ts": START,
                "exchange": EXCH,
                "market": MARKET,
                "symbol": SYMBOL,
                "metric": FUNDING_RATE,
                "value": 0.1,
            }
        ]
    )
    b = coerce_derivative_frame(
        [
            {
                "ts": START,
                "exchange": EXCH,
                "market": MARKET,
                "symbol": SYMBOL,
                "metric": OPEN_INTEREST,
                "value": 5.0,
            }
        ]
    )
    store.write(a)
    store.write(b)
    assert store.count(EXCH, MARKET, SYMBOL, FUNDING_RATE) == 1
    assert store.count(EXCH, MARKET, SYMBOL, OPEN_INTEREST) == 1
    assert store.metrics(EXCH, MARKET, SYMBOL) == [FUNDING_RATE, OPEN_INTEREST]


# --------------------------------------------------------------------------- #
# Basis derivation
# --------------------------------------------------------------------------- #


def test_derive_basis_is_mark_minus_index():
    mark = pd.DataFrame({"ts": [100, 200, 300], "mark_price": [10.0, 12.0, 14.0]})
    index = pd.DataFrame({"ts": [100, 200, 300], "index_price": [9.5, 12.0, 13.0]})
    basis = derive_basis(
        mark,
        index,
        exchange=EXCH,
        market=MARKET,
        symbol=SYMBOL,
        ingested_at=1_760_000_000_000,
    )
    assert basis["metric"].tolist() == [BASIS] * 3
    assert basis["value"].round(6).tolist() == [0.5, 0.0, 1.0]
    assert basis["ts"].tolist() == [100, 200, 300]


def test_derive_basis_joins_only_common_ts():
    mark = pd.DataFrame({"ts": [100, 200, 300], "mark_price": [10.0, 11.0, 12.0]})
    index = pd.DataFrame({"ts": [100, 300], "index_price": [9.0, 11.0]})
    basis = derive_basis(mark, index)
    assert basis["ts"].tolist() == [100, 300]


# --------------------------------------------------------------------------- #
# Fake transport
# --------------------------------------------------------------------------- #


def test_fake_transport_pages_are_well_shaped():
    t = make_transport()
    f = t.funding_rate_page(SYMBOL, START, START + WINDOW, 1000)
    assert list(f.columns) == ["ts", "funding_rate", "mark_price"]
    assert f["ts"].is_monotonic_increasing and f["ts"].is_unique
    oi = t.open_interest_page(SYMBOL, START, START + WINDOW, 500)
    assert list(oi.columns) == ["ts", "open_interest", "open_interest_value"]
    mk = t.mark_price_page(SYMBOL, START, START + WINDOW, 1000)
    idx = t.index_price_page(SYMBOL, START, START + WINDOW, 1000)
    assert list(mk.columns) == ["ts", "mark_price"]
    assert list(idx.columns) == ["ts", "index_price"]


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #


def test_collect_all_metrics_writes_queryable_series(store):
    runs = collect(store, make_transport())
    assert set(runs) == set(ALL_METRICS)
    assert runs[FUNDING_RATE].rows_new > 0
    assert runs[OPEN_INTEREST].rows_new > 0
    assert runs[OPEN_INTEREST_VALUE].rows_new > 0
    assert runs[MARK_PRICE].rows_new > 0
    assert runs[INDEX_PRICE].rows_new > 0
    assert runs[BASIS].rows_new > 0
    # basis rows must align with mark/index ts
    basis = store.read(EXCH, MARKET, SYMBOL, BASIS)
    mark = store.read(EXCH, MARKET, SYMBOL, MARK_PRICE)
    assert len(basis) == len(mark)
    # series are queryable and deduplicated
    for metric in ALL_METRICS:
        df = store.read(EXCH, MARKET, SYMBOL, metric)
        assert not df.empty
        assert df["ts"].is_unique


def test_rerun_adds_zero_rows(store):
    transport = make_transport()
    collect(store, transport)
    second = collect(store, transport)
    for metric, run in second.items():
        assert run.rows_new == 0, metric


def test_collect_resumes_from_last_stored_ts(store):
    transport = make_transport()
    first = collect(store, transport, until=START + 30 * HOUR)
    assert store.count(EXCH, MARKET, SYMBOL, MARK_PRICE) == 31  # 0..30h inclusive
    second = collect(store, transport)
    assert second[MARK_PRICE].rows_new == 30  # resumes at 31h; 31..60h inclusive
    assert store.count(EXCH, MARKET, SYMBOL, MARK_PRICE) == 61


def test_collect_only_requested_metrics(store):
    runs = collect(store, make_transport(), metrics=[FUNDING_RATE])
    assert set(runs) == {FUNDING_RATE}
    assert store.count(EXCH, MARKET, SYMBOL, OPEN_INTEREST) == 0


def test_collect_basis_implies_mark_and_index(store):
    runs = collect(store, make_transport(), metrics=[BASIS])
    assert set(runs) == {MARK_PRICE, INDEX_PRICE, BASIS}
    assert store.count(EXCH, MARKET, SYMBOL, BASIS) > 0


def test_dry_run_writes_nothing(store):
    transport = make_transport()
    runs = collect(store, transport, dry_run=True)
    assert runs[MARK_PRICE].rows_new > 0
    for metric in store.metrics(EXCH, MARKET, SYMBOL):
        assert store.count(EXCH, MARKET, SYMBOL, metric) == 0


def test_gold_perp_is_rejected(store):
    with pytest.raises(DerivativesTransportError, match="no Binance perp market"):
        DerivativesCollector(store, make_transport(), sleep_s=0.0).collect(
            "XAUUSD", market="perp"
        )


def test_unknown_metric_rejected(store):
    with pytest.raises(DerivativesTransportError, match="unknown metrics"):
        collect(store, make_transport(), metrics=["not_a_metric"])


# --------------------------------------------------------------------------- #
# Transport robustness
# --------------------------------------------------------------------------- #


def test_fake_fault_is_retried(store):
    from data.derivatives import DerivativesTransportError as DTE

    t = make_transport(faults={1: DTE("blip")})
    runs = collect(store, t, metrics=[FUNDING_RATE])
    assert runs[FUNDING_RATE].rows_new > 0  # retry succeeded


def test_binance_transport_maps_none_to_honest_error():
    class DownClient:
        def funding_rate_history(self, *a, **k):
            return None

    t = BinanceDerivativesTransport(
        DownClient(), backoff_attempts=1, sleep_fn=lambda _s: None
    )
    with pytest.raises(DerivativesTransportError, match="geo-blocked|unreachable"):
        t.funding_rate_page(SYMBOL, None, None, 1000)


def test_default_transport_is_offline_in_demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    t = default_derivatives_transport()
    assert isinstance(t, BinanceDerivativesTransport)
    df = t.funding_rate_page(SYMBOL, START, START + 8 * HOUR, 100)
    assert not df.empty
    assert "funding_rate" in df.columns


# --------------------------------------------------------------------------- #
# Honest liquidations rename (P10.4 done-when)
# --------------------------------------------------------------------------- #


def test_liquidations_proxy_renamed_honestly():
    client = BinanceClient()
    assert hasattr(client, "liquidation_stats_proxy")
    assert not hasattr(client, "liquidations")  # no misleading alias
    doc = client.liquidation_stats_proxy.__doc__ or ""
    assert "not liquidation data" in doc or "proxy" in doc
