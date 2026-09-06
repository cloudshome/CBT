"""P12.12 tests for the read-only PAXG/XAU promotion-evidence dossier."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from data.gold_basis import (
    PAXG_SOURCE,
    XAU_SOURCE,
    build_xau_evidence_dossier,
    inspect_sealed_oos,
    measure_gold_basis,
)
from data.store import CandleStore, normalise_klines
from data.validation import GRADUATION_CRITERIA, write_seal
from main import main


def _prices(ts, closes, price_type=None):
    frame = pd.DataFrame({"ts": ts, "close": closes})
    if price_type is not None:
        frame["price_type"] = price_type
    return frame


def _candles(ts, closes, *, exchange, symbol, price_type=""):
    raw = pd.DataFrame(
        {
            "ts": ts,
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1.0] * len(ts),
        }
    )
    return normalise_klines(
        raw,
        exchange=exchange,
        market="spot",
        symbol=symbol,
        timeframe="15m",
        source="test_fixture",
        price_type=price_type,
        ingested_at=1,
    )


def _write_seal(
    directory: Path, *, pass_bar=True, criteria=None, fingerprint="sealed-1"
):
    directory.mkdir(parents=True, exist_ok=True)
    criteria = criteria or dict(GRADUATION_CRITERIA)
    windows = {
        name: {"bar_met": bool(pass_bar)} for name in ("train", "val", "oos", "recent")
    }
    payload = {
        "ok": True,
        "seal": {
            "path": str(directory / "dukascopy_spot_XAUUSD_15m.json"),
            "fingerprint": fingerprint,
            "resealed": False,
        },
        "meta": {"criteria": criteria, "symbol": "XAUUSD", "timeframe": "15m"},
        "windows": windows,
        "verdicts": {
            "ALL": {
                "status": "PASS" if pass_bar else "FAIL",
                "oos_met": bool(pass_bar),
                "recent_met": bool(pass_bar),
            }
        },
    }
    return write_seal(
        directory,
        "dukascopy_spot_XAUUSD_15m",
        fingerprint,
        payload,
        reseal=False,
    )


def test_basis_uses_exact_timestamp_overlap_only():
    paxg = _prices([0, 60_000, 120_000], [2010.0, 9999.0, 2020.0])
    xau = _prices([0, 120_000], [2000.0, 2000.0], price_type="bid")

    report = measure_gold_basis(paxg, xau, min_overlap=2)

    assert report["ok"] is True
    assert report["matched_rows"] == 2
    assert report["alignment"] == "exact_timestamp_inner_join"
    assert report["forward_filled"] is False
    assert report["resampled"] is False
    assert report["basis"]["median_usd"] == 15.0
    assert report["coverage"]["paxg_unmatched_rows"] == 1


def test_basis_statistics_are_measured_not_assumed():
    xau = _prices([0, 1, 2, 3], [2000.0] * 4, price_type="bid")
    paxg = _prices([0, 1, 2, 3], [2010.0] * 4)

    report = measure_gold_basis(paxg, xau, min_overlap=4)

    assert report["basis"]["mean_bps"] == pytest.approx(50.0)
    assert report["basis"]["median_bps"] == pytest.approx(50.0)
    assert report["basis"]["std_bps"] == pytest.approx(0.0)
    assert report["basis"]["formula"].startswith("(PAXGUSDT_close")
    assert len(report["data_fingerprint_sha256"]) == 64
    assert report["research_only"] is True


def test_insufficient_overlap_fails_closed_but_exposes_observed_metrics():
    paxg = _prices([0, 1], [2010.0, 2011.0])
    xau = _prices([0, 1], [2000.0, 2001.0], price_type="bid")

    report = measure_gold_basis(paxg, xau, min_overlap=3)

    assert report["ok"] is False
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["basis"] is not None
    assert "below required minimum" in report["errors"][-1]


def test_no_overlap_does_not_invent_a_basis():
    report = measure_gold_basis(
        _prices([0], [2010.0]),
        _prices([1], [2000.0], price_type="bid"),
        min_overlap=1,
    )
    assert report["ok"] is False
    assert report["matched_rows"] == 0
    assert report["basis"] is None
    assert report["data_fingerprint_sha256"] is None


def test_mixed_xau_price_sides_are_rejected_as_ambiguous():
    paxg = _prices([0, 1], [2010.0, 2011.0])
    xau = _prices([0, 1], [2000.0, 2001.0], price_type=["bid", "ask"])

    report = measure_gold_basis(paxg, xau, min_overlap=2)

    assert report["ok"] is False
    assert any("mixes price types" in error for error in report["errors"])


def test_missing_xau_price_side_fails_closed():
    report = measure_gold_basis(
        _prices([0, 1], [2010.0, 2011.0]),
        _prices([0, 1], [2000.0, 2001.0]),
        min_overlap=2,
    )
    assert report["ok"] is False
    assert any("bid or ask provenance" in error for error in report["errors"])


def test_partially_missing_xau_price_side_fails_closed():
    report = measure_gold_basis(
        _prices([0, 1], [2010.0, 2011.0]),
        _prices([0, 1], [2000.0, 2001.0], price_type=["bid", None]),
        min_overlap=2,
    )
    assert report["ok"] is False
    assert report["xau"]["price_type"] == "bid"
    assert report["xau"]["missing_price_type_rows"] == 1
    assert any("without price_type provenance" in error for error in report["errors"])


def test_invalid_and_duplicate_rows_are_audited():
    paxg = _prices([0, 0, 1, 2], [2001.0, 2010.0, -1.0, 2020.0])
    xau = _prices([0, 2], [2000.0, 2000.0], price_type="bid")

    report = measure_gold_basis(paxg, xau, min_overlap=2)

    assert report["ok"] is True
    assert report["paxg"]["invalid_rows"] == 1
    assert report["paxg"]["duplicate_timestamps_removed"] == 1
    assert report["matched_rows"] == 2


def test_missing_seal_is_open_not_approved(tmp_path):
    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")
    assert report["available"] is False
    assert report["clears_unchanged_bar"] is False
    assert report["status"] == "MISSING"


def test_sealed_oos_must_clear_every_window_under_current_criteria(tmp_path):
    _write_seal(tmp_path)
    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")
    assert report["available"] is True
    assert report["criteria_match"] is True
    assert report["source_match"] is True
    assert report["seal_key_match"] is True
    assert report["envelope_integrity"] is True
    assert report["clears_unchanged_bar"] is True
    assert report["reseal_count"] == 0
    assert report["ever_resealed"] is False
    assert report["latest_created_at"]
    assert report["status"] == "CLEARS_BAR"


def test_stale_or_changed_graduation_criteria_do_not_clear(tmp_path):
    changed = dict(GRADUATION_CRITERIA)
    changed["pf"] = 1.0
    _write_seal(tmp_path, criteria=changed)

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["available"] is True
    assert report["criteria_match"] is False
    assert report["clears_unchanged_bar"] is False
    assert any("unchanged graduation bar" in reason for reason in report["reasons"])


def test_near_but_not_exact_graduation_criteria_do_not_clear(tmp_path):
    changed = dict(GRADUATION_CRITERIA)
    changed["expectancy"] += 1e-10
    _write_seal(tmp_path, criteria=changed)

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["criteria_match"] is False
    assert report["clears_unchanged_bar"] is False


def test_fingerprint_mismatch_invalidates_envelope(tmp_path):
    path = _write_seal(tmp_path)
    body = json.loads(path.read_text())
    body["history"][-1]["payload"]["seal"]["fingerprint"] = "copied-payload"
    path.write_text(json.dumps(body))

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["available"] is True
    assert report["envelope_integrity"] is False
    assert report["clears_unchanged_bar"] is False
    assert report["status"] == "INVALID"


def test_envelope_for_another_seal_key_is_invalid(tmp_path):
    path = _write_seal(tmp_path)
    body = json.loads(path.read_text())
    body["seal_key"] = "some_other_series_15m"
    path.write_text(json.dumps(body))

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["seal_key_match"] is False
    assert report["clears_unchanged_bar"] is False
    assert report["status"] == "INVALID"


def test_reseal_history_is_exposed_for_human_review(tmp_path):
    path = _write_seal(tmp_path)
    body = json.loads(path.read_text())
    resealed = json.loads(json.dumps(body["history"][-1]))
    resealed["at"] = "2026-08-16T01:00:00Z"
    resealed["reseal"] = True
    resealed["payload"]["seal"]["resealed"] = True
    body["history"].append(resealed)
    path.write_text(json.dumps(body))

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["clears_unchanged_bar"] is True
    assert report["history_entries"] == 2
    assert report["reseal_count"] == 1
    assert report["ever_resealed"] is True
    assert report["latest_resealed"] is True
    assert report["latest_created_at"] == "2026-08-16T01:00:00Z"


def test_seal_for_another_series_cannot_clear_xau_gate(tmp_path):
    path = _write_seal(tmp_path)
    body = json.loads(path.read_text())
    body["history"][-1]["payload"]["meta"]["symbol"] = "BTCUSDT"
    path.write_text(json.dumps(body))

    report = inspect_sealed_oos(tmp_path, "dukascopy_spot_XAUUSD_15m")

    assert report["source_match"] is False
    assert report["clears_unchanged_bar"] is False
    assert any("symbol/timeframe" in reason for reason in report["reasons"])


def test_dossier_reads_separate_store_keys_and_never_promotes(tmp_path):
    store_root = tmp_path / "store"
    seal_dir = tmp_path / "seals"
    store = CandleStore(root=store_root)
    ts = [1_700_000_000_000 + i * 900_000 for i in range(4)]
    store.write(_candles(ts, [2010.0] * 4, exchange="binance", symbol="PAXGUSDT"))
    store.write(
        _candles(
            ts, [2000.0] * 4, exchange="dukascopy", symbol="XAUUSD", price_type="bid"
        )
    )
    _write_seal(seal_dir)

    dossier = build_xau_evidence_dossier(
        store_root=store_root,
        seal_dir=seal_dir,
        timeframe="15m",
        bars=10,
        min_overlap=4,
    )

    assert dossier["ok"] is True
    assert dossier["requirements"]["basis_measured_not_assumed"] is True
    assert dossier["requirements"]["sealed_oos_clears_unchanged_bar"] is True
    assert dossier["decision"]["eligible_for_human_review"] is True
    assert dossier["decision"]["human_approval"] == "OPEN"
    assert dossier["decision"]["xau_tradeable"] is False
    assert dossier["decision"]["micro_live_unlocked"] is False
    assert dossier["basis_measurement"]["paxg"]["source"] == PAXG_SOURCE
    assert dossier["basis_measurement"]["xau"]["source"] == XAU_SOURCE
    assert dossier["basis_measurement"]["xau"]["price_type"] == "bid"


def test_failed_oos_keeps_human_review_closed(tmp_path):
    store_root = tmp_path / "store"
    seal_dir = tmp_path / "seals"
    store = CandleStore(root=store_root)
    ts = [1_700_000_000_000 + i * 900_000 for i in range(2)]
    store.write(_candles(ts, [2010.0, 2011.0], exchange="binance", symbol="PAXGUSDT"))
    store.write(
        _candles(
            ts,
            [2000.0, 2001.0],
            exchange="dukascopy",
            symbol="XAUUSD",
            price_type="bid",
        )
    )
    _write_seal(seal_dir, pass_bar=False)

    dossier = build_xau_evidence_dossier(
        store_root=store_root, seal_dir=seal_dir, bars=10, min_overlap=2
    )

    assert dossier["ok"] is True  # measurement succeeded; promotion did not
    assert dossier["sealed_oos"]["clears_unchanged_bar"] is False
    assert dossier["decision"]["eligible_for_human_review"] is False
    assert dossier["decision"]["xau_tradeable"] is False


def test_cli_clean_checkout_fails_without_manufacturing_evidence(tmp_path, capsys):
    store_root = tmp_path / "absent-store"
    seal_dir = tmp_path / "absent-seals"

    rc = main(
        [
            "xau-evidence",
            "--store-root",
            str(store_root),
            "--seal-dir",
            str(seal_dir),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["ok"] is False
    assert payload["status"] == "RESEARCH_ONLY"
    assert payload["basis_measurement"]["matched_rows"] == 0
    assert payload["requirements"]["explicit_human_approval"] is False
    assert payload["decision"]["xau_tradeable"] is False
    assert not store_root.exists()
    assert not seal_dir.exists()
