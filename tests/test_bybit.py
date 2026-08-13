"""P10.6 — Bybit V5 adapter behind the same normalised schema and transport contract.

Milestone deliverable (docs/DATA_INFRASTRUCTURE_ROADMAP.md §9):
"second exchange behind the same normalised schema — identical assertions
pass for both adapters."

All tests are fully offline and deterministic: HTTP is monkeypatched,
stores are tmp_path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.backfill import FakePagedTransport, backfill
from data.binance_client import BinanceClient
from data.bybit_client import (BYBIT_CATEGORY, BYBIT_INTERVALS,
                               RETCODE_RATE_LIMIT, BybitClient)
from data.store import CandleStore

STEP = 60_000
T0 = 1_750_000_000_000
TF = "1m"
EXCH_BYBIT = "bybit"


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path)


# --------------------------------------------------------------------------- #
# Bybit V5 parsing + routing (HTTP monkeypatched)
# --------------------------------------------------------------------------- #

def _bybit_row(ts: int, close: float) -> list:
    """One V5 kline row: [start, open, high, low, close, volume, turnover]."""
    return [str(ts), str(close - 1), str(close + 10), str(close - 10),
            str(close), "12.5", str(close * 12.5)]


def _bybit_payload(rows, retcode: int = 0, category: str = "linear") -> dict:
    return {"retCode": retcode, "retMsg": "OK" if retcode == 0 else "err",
            "result": {"symbol": "BTCUSDT", "category": category,
                       "list": rows},
            "time": 1_780_000_000_000}


def _patch_bybit(monkeypatch, responder):
    """Patch BybitClient's transport seam; record (hosts, path, params)."""
    calls = []

    def fake(self, hosts, path, params, timeout=None, retries=None):
        calls.append({"hosts": list(hosts), "path": path, "params": params})
        return responder(params)

    monkeypatch.setattr(BybitClient, "_get_page_with_headers", fake)
    return calls


def test_spot_and_perp_route_to_v5_categories(monkeypatch):
    def responder(params):
        return _bybit_payload([_bybit_row(T0, 60_000.0)]), {}, 200

    calls = _patch_bybit(monkeypatch, responder)
    c = BybitClient()
    page = c.klines_page("BTCUSDT", "1m", 10, market="spot")
    assert page.status == 200
    assert calls[0]["path"] == "/v5/market/kline"
    assert calls[0]["params"]["category"] == "spot"
    c.klines_page("BTCUSDT", "1m", 10, market="perp")
    assert calls[1]["params"]["category"] == "linear"
    assert BYBIT_CATEGORY == {"spot": "spot", "perp": "linear"}


def test_interval_mapping_covers_the_master_ladder():
    assert BYBIT_INTERVALS["1m"] == "1"
    assert BYBIT_INTERVALS["5m"] == "5"
    assert BYBIT_INTERVALS["15m"] == "15"
    assert BYBIT_INTERVALS["1h"] == "60"
    assert BYBIT_INTERVALS["4h"] == "240"
    assert BYBIT_INTERVALS["1d"] == "D"


def test_descending_v5_rows_are_reversed_to_ascending(monkeypatch):
    rows = [_bybit_row(T0 + 2 * STEP, 60_002.0),
            _bybit_row(T0 + 1 * STEP, 60_001.0),
            _bybit_row(T0, 60_000.0)]                      # newest first
    _patch_bybit(monkeypatch, lambda p: (_bybit_payload(rows), {}, 200))
    df = BybitClient().klines_page("BTCUSDT", "1m", 10).data
    assert df["ts"].tolist() == [T0, T0 + STEP, T0 + 2 * STEP]
    assert df["ts"].is_monotonic_increasing
    assert df["close"].tolist() == [60_000.0, 60_001.0, 60_002.0]
    assert list(df.columns) == ["ts", "open", "high", "low", "close",
                                "volume", "quote_volume"]
    # string rows parsed to float; turnover carried as quote_volume
    assert df["volume"].dtype == np.float64
    assert df["quote_volume"].iloc[0] == pytest.approx(60_000.0 * 12.5)


def test_start_and_end_params_are_ms(monkeypatch):
    calls = _patch_bybit(
        monkeypatch,
        lambda p: (_bybit_payload([_bybit_row(T0, 1.0)]), {}, 200))
    BybitClient().klines_page("BTCUSDT", "1m", 10,
                              start_time=T0, end_time=T0 + 9 * STEP)
    assert calls[0]["params"]["start"] == T0
    assert calls[0]["params"]["end"] == T0 + 9 * STEP
    assert calls[0]["params"]["interval"] == "1"
    assert calls[0]["params"]["limit"] == 10


def test_rate_limit_retcode_maps_to_429(monkeypatch):
    _patch_bybit(monkeypatch,
                 lambda p: (_bybit_payload([], retcode=RETCODE_RATE_LIMIT),
                            {}, 200))
    page = BybitClient().klines_page("BTCUSDT", "1m", 10)
    assert page.data is None
    assert page.status == 429                       # backfill backoff engages


def test_other_retcode_maps_to_400(monkeypatch):
    _patch_bybit(monkeypatch,
                 lambda p: (_bybit_payload([], retcode=10001), {}, 200))
    page = BybitClient().klines_page("BTCUSDT", "1m", 10)
    assert page.data is None
    assert page.status == 400


def test_geo_block_passes_http_status_through(monkeypatch):
    _patch_bybit(monkeypatch, lambda p: (None, {}, 403))
    page = BybitClient().klines_page("BTCUSDT", "1m", 10)
    assert page.data is None
    assert page.status == 403                       # backfill aborts immediately


def test_network_error_is_none_status(monkeypatch):
    _patch_bybit(monkeypatch, lambda p: (None, None, None))
    page = BybitClient().klines_page("BTCUSDT", "1m", 10)
    assert page.data is None
    assert page.status is None


def test_gold_has_no_bybit_perp(monkeypatch):
    calls = _patch_bybit(monkeypatch, lambda p: (_bybit_payload([]), {}, 200))
    page = BybitClient().klines_page("XAUUSD", "1m", 10, market="perp")
    assert page.data is None
    assert page.status is None
    assert calls == []                              # never even requested


def test_unsupported_timeframe_raises():
    with pytest.raises(ValueError):
        BybitClient().klines_page("BTCUSDT", "7m", 10)


def test_klines_wrapper_raises_connection_error_on_failure(monkeypatch):
    _patch_bybit(monkeypatch,
                 lambda p: (_bybit_payload([], retcode=RETCODE_RATE_LIMIT),
                            {}, 200))
    with pytest.raises(ConnectionError):
        BybitClient().klines("BTCUSDT", "1m", 10)


# --------------------------------------------------------------------------- #
# The milestone's proof: the same contract battery for BOTH adapters
# --------------------------------------------------------------------------- #

def _assert_adapter_contract(client, calls, *, spot_path: str, perp_path: str):
    """Identical assertions for any PageResult-shaped klines transport."""
    # spot page: correct endpoint, 200, ascending ts, numeric OHLCV
    spot = client.klines_page("BTCUSDT", "1m", 10, market="spot")
    assert spot.status == 200
    assert spot.data is not None
    assert calls[0]["path"] == spot_path
    assert list(spot.data.columns)[:6] == [
        "ts", "open", "high", "low", "close", "volume"]
    assert spot.data["ts"].is_monotonic_increasing
    for col in ("open", "high", "low", "close", "volume"):
        assert spot.data[col].dtype == np.float64
    # perp page: the perp endpoint, same shapes
    perp = client.klines_page("BTCUSDT", "1m", 10, market="perp")
    assert perp.status == 200
    assert calls[1]["path"] == perp_path
    assert list(perp.data.columns)[:6] == list(spot.data.columns)[:6]


def _binance_rows(n: int = 3) -> list:
    rows = []
    for i in range(n):
        ts = T0 + i * STEP
        rows.append([
            ts, "60000", "60010", "59990", "60005", "12.5",
            ts + STEP, "750062.5", 42, "6", "375031", "0"])
    return rows


def test_binance_adapter_satisfies_the_contract(monkeypatch):
    calls = []

    def fake(self, hosts, path, params, timeout=None, retries=None):
        calls.append({"hosts": list(hosts), "path": path, "params": params})
        return _binance_rows(), {}, 200

    monkeypatch.setattr(BinanceClient, "_get_first_host_with_headers", fake)
    _assert_adapter_contract(BinanceClient(), calls,
                             spot_path="/api/v3/klines",
                             perp_path="/fapi/v1/klines")


def test_bybit_adapter_satisfies_the_contract(monkeypatch):
    calls = []

    def fake(self, hosts, path, params, timeout=None, retries=None):
        calls.append({"hosts": list(hosts), "path": path, "params": params})
        return _bybit_payload([_bybit_row(T0 + (2 - i) * STEP, 60_000.0 + i)
                               for i in range(3)]), {}, 200

    monkeypatch.setattr(BybitClient, "_get_page_with_headers", fake)
    _assert_adapter_contract(BybitClient(), calls,
                             spot_path="/v5/market/kline",
                             perp_path="/v5/market/kline")
    # venue-specific: perp pages V5's linear category
    assert calls[1]["params"]["category"] == "linear"


# --------------------------------------------------------------------------- #
# End-to-end: bybit series through the real store, separate from binance
# --------------------------------------------------------------------------- #

def test_backfill_bybit_series_lands_in_its_own_partition(store):
    src = FakePagedTransport(start_ts=T0, end_ts=T0 + 119 * STEP)
    result = backfill(
        store=store, symbol="BTCUSDT", timeframe=TF, exchange="bybit",
        market="perp", client=src, start_ts=T0, sleep_s=0.0,
        clock=lambda: T0 + 120 * STEP, resume=False)
    # T0 is not minute-aligned, so the fake's align-up yields 118 candles.
    assert result.rows_added == 118
    df = store.read("bybit", "perp", "BTCUSDT", TF)
    assert len(df) == 118
    assert (df["exchange"] == "bybit").all()
    # the binance series stays untouched and separate
    assert store.count("binance", "perp", "BTCUSDT", TF) == 0
    backfill(
        store=store, symbol="BTCUSDT", timeframe=TF, exchange="binance",
        market="perp", client=FakePagedTransport(
            start_ts=T0, end_ts=T0 + 119 * STEP, seed=11),
        start_ts=T0, sleep_s=0.0, clock=lambda: T0 + 120 * STEP,
        resume=False)
    assert store.count("binance", "perp", "BTCUSDT", TF) == 118
    assert store.count("bybit", "perp", "BTCUSDT", TF) == 118
    listed = store.list_series()
    assert {"binance", "bybit"} == {s["exchange"] for s in listed}


def test_backfill_bybit_rerun_adds_zero_rows(store):
    args = dict(store=store, symbol="BTCUSDT", timeframe=TF,
                exchange="bybit", market="spot",
                client=FakePagedTransport(start_ts=T0, end_ts=T0 + 59 * STEP),
                start_ts=T0, sleep_s=0.0, clock=lambda: T0 + 60 * STEP,
                resume=False)
    first = backfill(**args)
    assert first.rows_added == 58                    # T0 alignment quirk, see above
    second = backfill(**args)
    assert second.rows_added == 0                    # idempotent across venues


def test_cli_backfill_bybit_demo_is_offline_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    from main import main
    start = 1_780_000_000_000
    end = start + 59 * 60_000
    argv = [
        "backfill", "--symbol", "BTCUSDT", "--tf", "1m",
        "--exchange", "bybit", "--market", "spot",
        "--start-ts", str(start), "--end-ts", str(end),
        "--page-limit", "25", "--no-sleep", "--root", str(tmp_path),
    ]
    assert main(argv) == 0
    rc = main(argv)
    assert rc == 0
    store = CandleStore(root=tmp_path)
    assert store.count("bybit", "spot", "BTCUSDT", "1m") == 60
    assert store.count("binance", "spot", "BTCUSDT", "1m") == 0


def test_cli_backfill_rejects_unknown_exchange():
    from main import main
    with pytest.raises(SystemExit) as exc:
        main(["backfill", "--exchange", "kraken"])
    assert exc.value.code == 2                        # argparse invalid choice
