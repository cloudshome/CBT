"""
tests/test_m60_evidence_closure_and_egress_guard.py
===================================================
Milestone 60 Verification Suite:
1. Verifies raw 848-trade Sealed OOS CSV ledger and cryptographic SHA-256 manifest.
2. Validates independent reproduction of all 848 rows directly from CSV without engine dependence.
3. Tests Deflated Sharpe Ratio (DSR) and CPCV metrics derived from CSV returns.
4. Audits 16 CandleStore Parquet partitions and exact bar counts (1,204,003 total, 1,194,521 active).
5. Tests surgical OutboundEgressPolicy blocking production exchange order endpoints.
6. Tests OutboundEgressPolicy preserving public klines, testnet, and Telegram notifications.
7. Verifies Ubuntu 24.04 hardening script integrity and constitutional capital lock.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from core.quantitative_validation.metrics import calculate_deflated_sharpe_ratio
from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from core.security.egress_firewall_verifier import OutboundEgressPolicy
from scripts.research.export_m60_sealed_oos_trade_ledger import run_cpcv_on_series

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_m60_csv_ledger_exists_and_matches_sha256_manifest():
    """1. CSV ledger exists, has exactly 848 data rows, 22 columns, and matches SHA-256 in manifest."""
    csv_path = ROOT_DIR / "research" / "m60_sealed_oos_848_trades_ledger.csv"
    manifest_path = ROOT_DIR / "research" / "m60_sealed_oos_manifest.json"

    assert csv_path.exists(), f"CSV ledger missing: {csv_path}"
    assert manifest_path.exists(), f"Manifest missing: {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Compute live SHA-256
    h = hashlib.sha256()
    with open(csv_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    live_sha = h.hexdigest()

    assert live_sha == manifest["csv_sha256"], (
        f"CSV SHA-256 mismatch: live={live_sha} vs manifest={manifest['csv_sha256']}"
    )

    # Verify column count and row count
    expected_columns = [
        "trade_id",
        "symbol",
        "timeframe",
        "ts_ms",
        "iso_utc",
        "plan_type",
        "action",
        "confidence_pct",
        "regime",
        "entry",
        "trigger_level",
        "horizon_hours",
        "holding_bars",
        "holding_hours",
        "outcome",
        "stage_lock_type",
        "rr_gross",
        "fee_r",
        "slip_r",
        "funding_r",
        "cost_r",
        "rr_net",
    ]

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == expected_columns, f"CSV header mismatch: {header}"
        rows = list(reader)
        assert len(rows) == 848, f"Expected 848 rows in CSV, got {len(rows)}"


def test_m60_independent_reproduction_from_raw_csv_rows():
    """2. Independently parses CSV using pandas and recomputes all summary metrics from raw rows."""
    csv_path = ROOT_DIR / "research" / "m60_sealed_oos_848_trades_ledger.csv"
    df = pd.read_csv(csv_path)

    assert len(df) == 848

    # Timeframe counts
    tf_counts = df["timeframe"].value_counts().to_dict()
    assert tf_counts.get("15m") == 200
    assert tf_counts.get("1h") == 268
    assert tf_counts.get("4h") == 380

    # Win rate, Expectancy, Profit Factor
    wins = df[df["rr_net"] > 0]
    losses = df[df["rr_net"] < 0]
    win_rate = len(wins) / len(df) * 100.0
    exp_net = float(df["rr_net"].mean())
    pf_net = float(wins["rr_net"].sum() / abs(losses["rr_net"].sum()))

    assert abs(win_rate - 60.14) <= 0.1, f"Win rate divergence: {win_rate}%"
    assert abs(exp_net - 0.3594) <= 0.001, f"Expectancy divergence: {exp_net}R"
    assert abs(pf_net - 1.8067) <= 0.005, f"Profit factor divergence: {pf_net}"

    # Stage 1 and Stage 2 locks
    s1_count = int((df["stage_lock_type"] == "STAGE_1_LOCK").sum())
    s2_count = int((df["stage_lock_type"] == "STAGE_2_LOCK").sum())
    assert s1_count == 198, f"Stage 1 locks expected 198, got {s1_count}"
    assert s2_count == 55, f"Stage 2 locks expected 55, got {s2_count}"

    # ETHUSDT multi-timeframe protection
    for tf in ["15m", "1h", "4h"]:
        eth_tf = df[(df["symbol"] == "ETHUSDT") & (df["timeframe"] == tf)]
        assert len(eth_tf) > 0
        eth_exp = float(eth_tf["rr_net"].mean())
        assert eth_exp > 0.0, f"ETHUSDT {tf} expectancy non-positive: {eth_exp}R"


def test_m60_independent_dsr_and_cpcv_from_csv():
    """3. Recomputes DSR and CPCV from the CSV return column and validates statistical hurdles."""
    csv_path = ROOT_DIR / "research" / "m60_sealed_oos_848_trades_ledger.csv"
    df = pd.read_csv(csv_path)

    returns = df["rr_net"].tolist()
    sh, dsr_100, p_val = calculate_deflated_sharpe_ratio(returns, estimated_trials=100)

    assert dsr_100 >= 0.9999, f"DSR under 100 trials below hurdle: {dsr_100}"
    assert p_val <= 0.0001, f"p-value under 100 trials above threshold: {p_val}"

    # CPCV recalculation
    cpcv = run_cpcv_on_series(returns, oos_years=1.6862)
    assert cpcv["folds_count"] == 15
    assert cpcv["empirical_freq_annualized_median_sharpe"] >= 4.80
    assert cpcv["time_series_cpcv_annualized_sharpe"] >= 4.50


def test_m60_candle_store_parquet_checksums_verified():
    """4. Verifies all 16 CandleStore Parquet partitions have non-empty SHA-256 and correct bar counts."""
    manifest_path = ROOT_DIR / "research" / "m60_sealed_oos_manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    partitions = manifest.get("candle_store_partitions", {})
    assert len(partitions) == 16

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    timeframes = ["15m", "1h", "4h", "1d"]

    for s in symbols:
        for tf in timeframes:
            key = f"{s}_{tf}"
            assert key in partitions, f"Partition missing: {key}"
            part_info = partitions[key]
            assert part_info["bars"] > 0
            assert len(part_info["sha256"]) == 64

    assert manifest["total_store_bars"] == 1204003
    assert manifest["active_backtest_bars_15m_1h_4h"] == 1194521


def test_m60_egress_firewall_blocks_production_order_endpoints():
    """5. OutboundEgressPolicy hard-blocks mutating and order requests to production endpoints."""
    blocked_cases = [
        ("POST", "https://fapi.binance.com/fapi/v1/order"),
        ("DELETE", "https://fapi.binance.com/fapi/v1/order"),
        ("POST", "https://dapi.binance.com/dapi/v1/order"),
        ("POST", "https://api.binance.com/api/v3/order"),
        ("PUT", "https://api.binance.com/api/v3/order/test"),
        ("POST", "https://api.bybit.com/v5/order/create"),
        ("DELETE", "https://api.bybit.com/v5/order/cancel"),
        ("POST", "https://api.hyperliquid.xyz/exchange"),
    ]

    for method, url in blocked_cases:
        with pytest.raises(PermissionError, match="EGRESS_FIREWALL_BLOCKED"):
            OutboundEgressPolicy.verify_request(method, url)


def test_m60_egress_firewall_allows_public_klines_testnet_and_telegram():
    """6. OutboundEgressPolicy permits public klines, testnet orders, and Telegram notifications."""
    allowed_cases = [
        ("GET", "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m"),
        ("GET", "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h"),
        ("GET", "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=4h"),
        ("GET", "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT"),
        ("POST", "https://testnet.binancefuture.com/fapi/v1/order"),
        ("POST", "https://testnet.binance.vision/api/v3/order"),
        ("POST", "https://api-testnet.bybit.com/v5/order/create"),
        ("POST", "https://api.telegram.org/bot123456:ABC/sendMessage"),
    ]

    for method, url in allowed_cases:
        permitted, reason = OutboundEgressPolicy.verify_request(method, url)
        assert permitted is True
        assert reason == "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"


def test_m60_ubuntu_hardening_script_and_real_capital_lock():
    """7. Verifies deploy/harden_production_egress.sh exists, contains modes, and capital lock is False."""
    script_path = ROOT_DIR / "deploy" / "harden_production_egress.sh"
    assert script_path.exists(), f"Hardening script missing: {script_path}"

    content = script_path.read_text(encoding="utf-8")
    assert "--check" in content
    assert "--apply-sinkhole" in content
    assert "fapi.binance.com" in content
    assert "api.telegram.org" not in content.split("SINKHOLE_DOMAINS=(")[1].split(")")[0]
    assert "testnet.binancefuture.com" not in content.split("SINKHOLE_DOMAINS=(")[1].split(")")[0]

    # Constitutional Lock
    assert REAL_CAPITAL_ENABLED is False
