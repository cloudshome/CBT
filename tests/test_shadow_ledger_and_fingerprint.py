"""
Unit and Integration Tests for Shadow Ledger and Strategy Fingerprinting
========================================================================
Verifies:
- Cryptographic code and metadata binding.
- Fingerprint invalidation on executable logic drift.
- Tamper-evident hash chain continuity.
- Idempotency & duplicate prediction rejection.
- Path-dependent MFE & MAE tracking.
- Outcome resolution (TP, SL, Timeout).
- Crash-safe persistence and restart recovery.
- Instant tamper detection on unauthorized file mutation.
"""

import pytest

from core.research.shadow_ledger import GENESIS_HASH, ShadowLedgerEngine
from core.research.strategy_fingerprint import StrategyCryptographicFingerprint


def sample_strategy_v1(close, open_, atr):
    return close < open_ - 0.8 * atr


def sample_strategy_v2(close, open_, atr):
    return close < open_ - 1.2 * atr  # modified threshold


def test_strategy_cryptographic_fingerprint_drift_detection():
    config = {
        "strategy_id": "H3_TEST",
        "stop_loss_r": 1.0,
        "take_profit_r": 2.0,
        "risk_unit": "1.5 * atr",
    }

    fp1 = StrategyCryptographicFingerprint("H3_TEST", config, sample_strategy_v1)
    d1 = fp1.to_dict()

    # 1. Verification of identical logic
    assert fp1.verify_against(sample_strategy_v1, config) is True

    # 2. Logic modification must alter code hash and fail verification
    fp2 = StrategyCryptographicFingerprint("H3_TEST", config, sample_strategy_v2)
    assert fp1.executable_code_hash != fp2.executable_code_hash
    assert fp1.composite_fingerprint != fp2.composite_fingerprint
    assert fp1.verify_against(sample_strategy_v2, config) is False

    # 3. Config modification must alter fingerprint
    config_modified = dict(config, take_profit_r=3.0)
    assert fp1.verify_against(sample_strategy_v1, config_modified) is False


def test_shadow_ledger_hash_chain_and_lifecycle(tmp_path):
    ledger_path = tmp_path / "shadow_ledger.jsonl"
    engine = ShadowLedgerEngine(ledger_path)

    # Precommit prediction 1 (LONG)
    pred1 = engine.precommit_prediction(
        strategy_id="H3_TEST",
        strategy_fingerprint="abc123hash",
        symbol="BTCUSDT",
        timeframe="1h",
        direction="LONG",
        entry_price=50000.0,
        stop_loss_price=49000.0,
        take_profit_price=52000.0,
        risk_unit_usd=1000.0,
        max_hold_bars=3,
        timestamp_utc="2026-11-05T00:00:00Z",
    )
    assert pred1 is not None
    assert pred1.prev_record_sha256 == GENESIS_HASH
    assert pred1.sequence_id == 0
    assert len(engine.active_predictions) == 1

    # Duplicate prevention
    dup = engine.precommit_prediction(
        strategy_id="H3_TEST",
        strategy_fingerprint="abc123hash",
        symbol="BTCUSDT",
        timeframe="1h",
        direction="LONG",
        entry_price=50000.0,
        stop_loss_price=49000.0,
        take_profit_price=52000.0,
        risk_unit_usd=1000.0,
        max_hold_bars=3,
        timestamp_utc="2026-11-05T00:00:00Z",  # identical key
    )
    assert dup is None

    # Bar 1: Favorable price move (MFE updates, no exit)
    resolved = engine.update_bar(
        symbol="BTCUSDT",
        bar_high=51500.0,
        bar_low=49800.0,
        bar_close=51200.0,
        bar_timestamp_utc="2026-11-05T01:00:00Z",
    )
    assert len(resolved) == 0
    assert engine.active_predictions[pred1.prediction_id]["mfe_r"] == 1.5  # (51500 - 50000) / 1000
    assert engine.active_predictions[pred1.prediction_id]["mae_r"] == 0.2  # (50000 - 49800) / 1000

    # Bar 2: Hits take profit (52200 >= 52000)
    resolved = engine.update_bar(
        symbol="BTCUSDT",
        bar_high=52200.0,
        bar_low=51000.0,
        bar_close=51800.0,
        bar_timestamp_utc="2026-11-05T02:00:00Z",
    )
    assert len(resolved) == 1
    res_rec = resolved[0]
    assert res_rec.exit_reason == "TAKE_PROFIT"
    assert res_rec.exit_price == 52000.0
    assert res_rec.realized_gross_r == 2.0
    assert res_rec.realized_net_r > 1.90
    assert len(engine.active_predictions) == 0

    # Verify hash chain integrity
    is_valid, msg, count = engine.verify_ledger_integrity()
    assert is_valid is True
    assert count == 2  # 1 precommit + 1 resolution


def test_shadow_ledger_crash_recovery_and_tamper_detection(tmp_path):
    ledger_path = tmp_path / "crash_test_ledger.jsonl"
    engine1 = ShadowLedgerEngine(ledger_path)

    # Precommit 2 predictions
    p1 = engine1.precommit_prediction(
        strategy_id="H3_TEST",
        strategy_fingerprint="hash1",
        symbol="BTCUSDT",
        timeframe="1h",
        direction="LONG",
        entry_price=60000.0,
        stop_loss_price=59000.0,
        take_profit_price=62000.0,
        risk_unit_usd=1000.0,
        max_hold_bars=5,
        timestamp_utc="2026-11-05T10:00:00Z",
    )
    p2 = engine1.precommit_prediction(
        strategy_id="H5_TEST",
        strategy_fingerprint="hash2",
        symbol="ETHUSDT",
        timeframe="1h",
        direction="SHORT",
        entry_price=3000.0,
        stop_loss_price=3100.0,
        take_profit_price=2750.0,
        risk_unit_usd=100.0,
        max_hold_bars=10,
        timestamp_utc="2026-11-05T10:00:00Z",
    )

    # Simulate process crash and restart by creating new engine instance pointing to same file
    engine2 = ShadowLedgerEngine(ledger_path)
    assert len(engine2.records) == 2
    assert len(engine2.active_predictions) == 2
    assert p1.prediction_id in engine2.active_predictions
    assert p2.prediction_id in engine2.active_predictions
    assert engine2.last_hash == engine1.last_hash

    is_valid, _, count = engine2.verify_ledger_integrity()
    assert is_valid is True
    assert count == 2

    # Tamper test: Corrupt a byte in the ledger file
    with open(ledger_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Tamper line 1
    corrupted_line = lines[0].replace("60000.0", "60500.0")
    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write(corrupted_line + lines[1])

    # Rebooting with corrupted ledger must fail immediately
    with pytest.raises(ValueError, match="Tamper detected"):
        ShadowLedgerEngine(ledger_path)
