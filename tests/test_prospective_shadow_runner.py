"""
tests/test_prospective_shadow_runner.py
=======================================
Unit and integration test suite for Prospective Shadow Runner (Phase 3).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.research.shadow_ledger import ShadowLedgerEngine
from scripts.research.run_prospective_shadow_runner import ProspectiveShadowRunner


def test_shadow_runner_initialization_and_manifest(tmp_path: Path):
    ledger_file = tmp_path / "test_shadow_ledger.jsonl"
    runner = ProspectiveShadowRunner(ledger_path=ledger_file)
    assert runner.ledger_path == ledger_file
    assert runner.engine is not None
    assert isinstance(runner.manifest, dict)


def test_shadow_runner_cycle_and_resolution(tmp_path: Path):
    ledger_file = tmp_path / "test_shadow_ledger.jsonl"
    engine = ShadowLedgerEngine(ledger_file)

    # 1. Precommit long prediction
    rec = engine.precommit_prediction(
        strategy_id="H3_TEST_LONG",
        strategy_fingerprint="fp_test_12345",
        symbol="BTCUSDT",
        timeframe="1h",
        direction="LONG",
        entry_price=80_000.0,
        stop_loss_price=79_000.0,
        take_profit_price=82_000.0,
        risk_unit_usd=1_000.0,
        max_hold_bars=10,
        idempotency_key="TEST_H3_1",
    )
    assert rec is not None
    assert rec.sequence_id == 0
    assert len(engine.active_predictions) == 1

    # 2. Bar update with favorable excursion (reaches 81,500, low 79,500)
    resolved = engine.update_bar(
        symbol="BTCUSDT",
        bar_high=81_500.0,
        bar_low=79_500.0,
        bar_close=81_000.0,
        bar_timestamp_utc="2026-11-08T01:00:00Z",
    )
    assert len(resolved) == 0
    pos = engine.active_predictions[rec.prediction_id]
    assert pos["bars_elapsed"] == 1
    assert pos["mfe_r"] == pytest.approx(1.5, rel=1e-3)
    assert pos["mae_r"] == pytest.approx(0.5, rel=1e-3)

    # 3. Bar update hits take profit (reaches 82,500)
    resolved = engine.update_bar(
        symbol="BTCUSDT",
        bar_high=82_500.0,
        bar_low=80_500.0,
        bar_close=82_200.0,
        bar_timestamp_utc="2026-11-08T02:00:00Z",
    )
    assert len(resolved) == 1
    res_rec = resolved[0]
    assert res_rec.lifecycle_state == "RESOLVED"
    assert res_rec.exit_reason == "TAKE_PROFIT"
    assert res_rec.realized_net_r is not None
    assert res_rec.realized_net_r > 1.90
    assert len(engine.active_predictions) == 0

    # 4. Check cryptographic ledger verification
    is_valid, msg, count = engine.verify_ledger_integrity()
    assert is_valid is True
    assert count == 2  # 1 Precommit + 1 Resolution


def test_shadow_runner_idempotency(tmp_path: Path):
    ledger_file = tmp_path / "test_shadow_ledger.jsonl"
    engine = ShadowLedgerEngine(ledger_file)

    rec1 = engine.precommit_prediction(
        strategy_id="H5_TEST",
        strategy_fingerprint="fp_abc",
        symbol="ETHUSDT",
        timeframe="1h",
        direction="SHORT",
        entry_price=3000.0,
        stop_loss_price=3100.0,
        take_profit_price=2800.0,
        risk_unit_usd=100.0,
        max_hold_bars=24,
        idempotency_key="UNIQUE_IDEMPOTENCY_KEY_123",
    )
    assert rec1 is not None

    # Attempt exact duplicate
    rec2 = engine.precommit_prediction(
        strategy_id="H5_TEST",
        strategy_fingerprint="fp_abc",
        symbol="ETHUSDT",
        timeframe="1h",
        direction="SHORT",
        entry_price=3000.0,
        stop_loss_price=3100.0,
        take_profit_price=2800.0,
        risk_unit_usd=100.0,
        max_hold_bars=24,
        idempotency_key="UNIQUE_IDEMPOTENCY_KEY_123",
    )
    assert rec2 is None, "Duplicate idempotency key must return None"
    assert len(engine.records) == 1


def test_shadow_runner_tamper_fails_closed(tmp_path: Path):
    ledger_file = tmp_path / "test_shadow_ledger.jsonl"
    engine = ShadowLedgerEngine(ledger_file)

    engine.precommit_prediction(
        strategy_id="H5_TEST",
        strategy_fingerprint="fp_abc",
        symbol="ETHUSDT",
        timeframe="1h",
        direction="SHORT",
        entry_price=3000.0,
        stop_loss_price=3100.0,
        take_profit_price=2800.0,
        risk_unit_usd=100.0,
        max_hold_bars=24,
        idempotency_key="KEY_1",
    )

    # Tamper with the file contents
    content = ledger_file.read_text(encoding="utf-8")
    tampered = content.replace("3000.0", "9999.0")
    ledger_file.write_text(tampered, encoding="utf-8")

    # Re-instantiate engine; must detect tamper on boot
    with pytest.raises(ValueError, match="Tamper detected"):
        ShadowLedgerEngine(ledger_file)


def test_shadow_runner_candle_finalization_and_gap_recovery(tmp_path: Path):
    """
    Verifies that:
    1. Unfinalized candles (in-progress bars) are excluded from evaluation.
    2. Finalized candles are processed once closed.
    3. Duplicate executions do not advance positions or re-evaluate bars.
    4. Missed hourly bars are recovered chronologically without silent gaps.
    """
    db_file = tmp_path / "test_market_data.db"
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE candles (
            timestamp BIGINT, symbol TEXT, timeframe TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL, is_synthetic INT,
            PRIMARY KEY (symbol, timeframe, timestamp)
        )
    """)

    # Populate 35 baseline 1h bars for BTCUSDT (30 needed for ATR/SMA indicators)
    base_ts = 1700000000000  # ms
    for i in range(35):
        ts = base_ts + i * 3600000
        conn.execute(
            "INSERT INTO candles VALUES (?, 'BTCUSDT', '1h', 50000.0, 50200.0, 49800.0, 50100.0, 100.0, 0)",
            (ts,),
        )
    conn.commit()
    conn.close()

    ledger_file = tmp_path / "shadow_ledger.jsonl"
    state_file = tmp_path / "runner_state.json"

    runner = ProspectiveShadowRunner(
        ledger_path=ledger_file,
        state_path=state_file,
        db_path=db_file,
    )

    bar34_ts = base_ts + 34 * 3600000
    # 1. Bar 34 started at bar34_ts. It closes at bar34_ts + 3600_000.
    # Set current time to 30 mins into bar 34 (still in progress / unfinalized).
    time_during_bar34 = datetime.fromtimestamp((bar34_ts + 1800000) / 1000, tz=UTC)
    res1 = runner.poll_cycle(now_utc=time_during_bar34)

    # Bar 34 must be excluded; only bar 33 and earlier are finalized
    bar33_ts = base_ts + 33 * 3600000
    assert runner.state["last_processed_candle_ts"]["BTCUSDT"] == bar33_ts

    # 2. Advance time to 1 minute past bar 34 close (now finalized)
    time_after_bar34 = datetime.fromtimestamp((bar34_ts + 3660000) / 1000, tz=UTC)
    res2 = runner.poll_cycle(now_utc=time_after_bar34)
    assert runner.state["last_processed_candle_ts"]["BTCUSDT"] == bar34_ts

    # 3. Deduplication: running again at the same time does not re-process bar 34
    res3 = runner.poll_cycle(now_utc=time_after_bar34)
    assert runner.state["last_processed_candle_ts"]["BTCUSDT"] == bar34_ts
    assert res3["resolved_in_cycle"] == 0
    assert res3["precommitted_in_cycle"] == 0

    # 4. Missed hourly candles (Gap recovery): Insert 3 new bars (35, 36, 37)
    conn = sqlite3.connect(db_file)
    for i in (35, 36, 37):
        ts = base_ts + i * 3600000
        conn.execute(
            "INSERT INTO candles VALUES (?, 'BTCUSDT', '1h', 50100.0, 50300.0, 49900.0, 50200.0, 120.0, 0)",
            (ts,),
        )
    conn.commit()
    conn.close()

    # Time is after bar 37 close (3 hours elapsed without runner)
    bar37_ts = base_ts + 37 * 3600000
    time_after_bar37 = datetime.fromtimestamp((bar37_ts + 3660000) / 1000, tz=UTC)
    res4 = runner.poll_cycle(now_utc=time_after_bar37)

    # All 3 missed bars were recovered chronologically; checkpoint is now bar 37
    assert runner.state["last_processed_candle_ts"]["BTCUSDT"] == bar37_ts
