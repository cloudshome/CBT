"""
tests/test_prospective_shadow_runner.py
=======================================
Unit and integration test suite for Prospective Shadow Runner (Phase 3).
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

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
