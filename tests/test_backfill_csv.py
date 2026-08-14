"""P12.3.2 — offline CSV import of real market data (no live socket).

The milestone's done-when: a local Binance-style OHLCV CSV (Vision 6-col
or 12-col klines, plain or gzipped) enters the P10 store through the same
adapter boundary as the REST backfill — ``normalise_klines`` →
``CandleStore.write`` — with a provenance sha256 pin, idempotent re-runs,
duplicate/gap/sanity reporting, and a ``StoreClient`` that lets the
offline walkers (backtest, simulator) read that real series.

All tests are fully offline and deterministic.
"""
from __future__ import annotations

import gzip
import hashlib

import pandas as pd
import pytest

from data.backfill import BackfillError, backfill_from_csv
from data.store import CandleStore, StoreClient

EXCH, MARKET, SYMBOL, TF = "binance", "spot", "BTCUSDT", "1m"
STEP = 60_000
T0 = (1_735_689_600_000 // STEP) * STEP  # 2025-01-01T00:00:00Z, aligned


def vision_csv(n: int = 30, start: int = T0) -> str:
    """Binance Vision export layout (open_time_ms, open, high, low, close, volume)."""
    lines = ["open_time_ms,open,high,low,close,volume"]
    for i in range(n):
        t = start + i * STEP
        p = 93_500.0 + i * 2.5
        lines.append(f"{t},{p},{p + 6},{p - 4},{p + 3},8.21")
    return "\n".join(lines) + "\n"


def klines12_csv(n: int = 30, start: int = T0) -> str:
    """Headerless 12-column raw Binance klines rows."""
    lines = []
    for i in range(n):
        t = start + i * STEP
        p = 93_500.0 + i * 2.5
        lines.append(f"{t},{p},{p + 6},{p - 4},{p + 3},8.21,"
                     f"{t + STEP - 1},770000.0,12,4.1,380000.0,0")
    return "\n".join(lines) + "\n"


@pytest.fixture
def store(tmp_path):
    return CandleStore(root=tmp_path / "store")


def test_vision_csv_imports_with_canonical_schema(store, tmp_path):
    path = tmp_path / "btc.csv"
    path.write_text(vision_csv())
    res = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                            timeframe=TF, exchange=EXCH, market=MARKET)
    assert res["ok"] and res["rows_read"] == 30 and res["rows_added"] == 30
    assert res["first_ts"] == T0 and res["last_ts"] == T0 + 29 * STEP
    assert res["gaps_found"] == 0 and res["duplicates_dropped"] == 0

    df = store.read(EXCH, MARKET, SYMBOL, TF)
    assert len(df) == 30
    assert df["source"].iloc[0] == "csv"
    assert df["exchange"].iloc[0] == EXCH and df["market"].iloc[0] == MARKET
    assert float(df["open"].iloc[0]) == 93_500.0
    assert df["closed"].all()


def test_rerun_is_idempotent(store, tmp_path):
    path = tmp_path / "btc.csv"
    path.write_text(vision_csv())
    first = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                              timeframe=TF, exchange=EXCH, market=MARKET)
    second = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                               timeframe=TF, exchange=EXCH, market=MARKET)
    assert first["rows_added"] == 30
    assert second["rows_added"] == 0
    assert second["rows_after"] == 30


def test_gzipped_csv_imports(store, tmp_path):
    path = tmp_path / "btc.csv.gz"
    with gzip.open(path, "wt") as fh:
        fh.write(vision_csv())
    res = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                            timeframe=TF, exchange=EXCH, market=MARKET)
    assert res["rows_added"] == 30


def test_headerless_12_col_klines_imports(store, tmp_path):
    path = tmp_path / "klines.txt"
    path.write_text(klines12_csv())
    res = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                            timeframe=TF, exchange=EXCH, market=MARKET)
    assert res["rows_added"] == 30
    df = store.read(EXCH, MARKET, SYMBOL, TF)
    assert float(df["close"].iloc[-1]) == 93_500.0 + 29 * 2.5 + 3


def test_sha256_pin_verified_and_enforced(store, tmp_path):
    path = tmp_path / "btc.csv"
    path.write_text(vision_csv())
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    ok = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                           timeframe=TF, exchange=EXCH, market=MARKET,
                           expected_sha256=pin)
    assert ok["sha256_verified"] and ok["sha256"] == pin

    with pytest.raises(BackfillError, match="sha256 mismatch"):
        backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                          timeframe=TF, exchange=EXCH, market=MARKET,
                          expected_sha256="0" * 64)
    # The refused import wrote nothing.
    assert store.count(EXCH, MARKET, SYMBOL, TF) == 30


def test_duplicates_and_gaps_are_reported_not_silently_repaired(store, tmp_path):
    path = tmp_path / "btc.csv"
    body = vision_csv(10)
    # 10 duplicate *data* rows (same timestamps again, appended without a
    # second header — exactly what a careless archive concatenation does).
    path.write_text(body + body.split("\n", 1)[1])
    res = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                            timeframe=TF, exchange=EXCH, market=MARKET)
    assert res["rows_read"] == 20 and res["rows_added"] == 10
    assert res["duplicates_dropped"] == 10

    hole = tmp_path / "hole.csv"
    lines = ["open_time_ms,open,high,low,close,volume"]
    for i in (0, 1, 2, 6, 7):  # missing 3,4,5
        t = T0 + i * STEP
        lines.append(f"{t},{100.0 + i},{100.5 + i},{99.5 + i},{100.1 + i},5.0")
    hole.write_text("\n".join(lines) + "\n")
    # Fresh store so the earlier import doesn't overlap timestamps.
    store2 = CandleStore(root=tmp_path / "store2")
    res2 = backfill_from_csv(store=store2, csv_path=hole, symbol=SYMBOL,
                             timeframe=TF, exchange=EXCH, market=MARKET)
    assert res2["rows_added"] == 5 and res2["gaps_found"] == 1


def test_insane_rows_are_dropped_and_counted(store, tmp_path):
    lines = ["open_time_ms,open,high,low,close,volume",
             f"{T0},100.0,99.0,101.0,100.0,5.0",      # high < low — insane
             f"{T0 + STEP},100.0,101.0,99.0,100.0,-1.0",  # negative volume
             f"{T0 + 2 * STEP},100.0,101.0,99.0,100.0,5.0"]
    path = tmp_path / "insane.csv"
    path.write_text("\n".join(lines) + "\n")
    res = backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                            timeframe=TF, exchange=EXCH, market=MARKET)
    assert res["rows_added"] == 1 and res["sanity_dropped"] == 2


def test_missing_columns_raise_backfill_error(store, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("open_time_ms,open,close\n1,2,3\n")
    with pytest.raises(BackfillError, match="missing required columns"):
        backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                          timeframe=TF, exchange=EXCH, market=MARKET)


def test_store_client_serves_tail_cursors_and_attrs(store, tmp_path):
    path = tmp_path / "btc.csv"
    path.write_text(vision_csv(40))
    backfill_from_csv(store=store, csv_path=path, symbol=SYMBOL,
                      timeframe=TF, exchange=EXCH, market=MARKET)

    client = StoreClient(store=store, exchange=EXCH, market=MARKET)
    df = client.klines(SYMBOL, TF, limit=500)
    assert len(df) == 40
    assert df.attrs["symbol"] == SYMBOL and df.attrs["timeframe"] == TF

    tail = client.klines(SYMBOL, TF, limit=7)
    assert len(tail) == 7 and int(tail["ts"].iloc[0]) == T0 + 33 * STEP

    cur = client.klines(SYMBOL, TF, limit=500, start_time=T0 + 10 * STEP,
                        end_time=T0 + 19 * STEP)
    assert len(cur) == 10 and int(cur["ts"].iloc[0]) == T0 + 10 * STEP

    empty = client.klines("ETHUSDT", TF, limit=500)
    assert empty.empty and empty.attrs["symbol"] == "ETHUSDT"


def test_cli_backfill_from_csv_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    from main import main
    csv = tmp_path / "btc.csv"
    csv.write_text(vision_csv(25))
    root = tmp_path / "store"
    argv = ["backfill", "--from-csv", str(csv), "--symbol", "BTCUSDT",
            "--tf", "1m", "--market", "spot", "--root", str(root), "--json"]
    assert main(argv) == 0
    df = CandleStore(root=root).read(EXCH, MARKET, SYMBOL, TF)
    assert len(df) == 25 and df["source"].iloc[0] == "csv"


def test_cli_from_csv_sha256_pin_refuses_and_exits_1(tmp_path, monkeypatch,
                                                     capsys):
    monkeypatch.setenv("DEMO_MODE", "0")
    from main import main
    csv = tmp_path / "btc.csv"
    csv.write_text(vision_csv(25))
    argv = ["backfill", "--from-csv", str(csv), "--symbol", "BTCUSDT",
            "--tf", "1m", "--market", "spot",
            "--root", str(tmp_path / "store"),
            "--csv-sha256", "0" * 64, "--json"]
    assert main(argv) == 1
    err = capsys.readouterr().err
    assert "sha256 mismatch" in err
