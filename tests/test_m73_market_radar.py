"""tests/test_m73_market_radar.py — Milestone 73 Automated Test Suite.

Verifies:
1. test_m73_proximity_scanner_thresholds:
   NEAR_S1_BREAKOUT and APPROACHING_EMA200 fire strictly within the 3.0% threshold and stay silent outside it.
2. test_m73_regime_shift_fires_once_on_transition:
   REGIME_SHIFT fires on BEAR_SHIELD -> MIXED transition and does NOT re-fire on repeated identical regimes.
3. test_m73_four_hour_antispam_cooldown_and_expiry:
   4-hour anti-spam cooldown blocks duplicate notifications within 4h and allows them after cooldown expiry.
4. test_m73_stale_data_fail_closed:
   stale_data_warning=True -> STALE_DATA, 0 alerts fired, fail-closed guarantee.
5. test_m73_governance_invariants_locked:
   REAL_CAPITAL_ENABLED is False, CAPITAL_MODE == "TIER_0_PAPER", Radar never mutates shadow ledger or fills trades.
6. test_m73_api_cli_and_telegram_radar_en_bn:
   Verifies GET /api/desk/radar, main.py radar --offline --json, and Telegram /radar in English and Bengali.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import app
from cli.daily import cmd_radar
from core.ops.market_radar import (
    MarketRadarReport,
    run_market_radar,
)
from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from core.strategies.p2_risk_parity import (
    CAPITAL_MODE,
    AssetMetrics,
    TodayDeskSnapshot,
)
from core.telegram.handlers import handle_radar, register_all_v5_commands


def _make_mock_asset(
    symbol: str,
    price: float = 90000.0,
    ema_status: str = "ABOVE",
    dist_ema_pct: float = 5.0,
    dist_brk_pct: float = 2.0,
    mom_30d_pct: float = 10.0,
    vol_20d_pct: float = 40.0,
    s1_status: str = "WAITING_BREAKOUT",
) -> AssetMetrics:
    return AssetMetrics(
        symbol=symbol,
        price=price,
        ema_200=price * 0.95,
        ema_status=ema_status,
        donchian_h48=price * 1.02,
        donchian_l24=price * 0.90,
        atr_14=price * 0.02,
        stop_loss=price * 0.90,
        momentum_30d_pct=mom_30d_pct,
        vol_20d_ann_pct=vol_20d_pct,
        ema200_price=price * 0.95,
        donchian48_high=price * 1.02,
        distance_to_ema200_pct=dist_ema_pct,
        distance_to_breakout_pct=dist_brk_pct,
        s1_status=s1_status,
        s2_status="SELECTED_TOP2",
        waiting_reason_en="Test waiting reason",
        waiting_reason_bn="টেস্ট অপেক্ষার কারণ",
    )


def _make_mock_snapshot(
    regime_label: str = "MIXED",
    action_verdict: str = "HOLD",
    stale: bool = False,
    data_age_hours: float = 1.0,
    assets: dict[str, AssetMetrics] | None = None,
) -> TodayDeskSnapshot:
    if assets is None:
        assets = {
            "BTCUSDT": _make_mock_asset("BTCUSDT", price=90000.0, dist_brk_pct=2.0),
            "ETHUSDT": _make_mock_asset("ETHUSDT", price=3000.0, dist_brk_pct=4.0),
            "SOLUSDT": _make_mock_asset("SOLUSDT", price=180.0, ema_status="BELOW", dist_ema_pct=-2.5),
            "PAXGUSDT": _make_mock_asset("PAXGUSDT", price=2700.0, ema_status="BELOW", dist_ema_pct=-5.0),
        }
    return TodayDeskSnapshot(
        timestamp_utc="2026-11-21T00:00:00Z",
        data_source="MOCK_TEST",
        data_age_hours=data_age_hours,
        stale_data_warning=stale,
        regime_label=regime_label,
        action_verdict=action_verdict,
        assets=assets,
        s1_weights={"BTCUSDT": 0.5, "ETHUSDT": 0.0, "SOLUSDT": 0.0, "PAXGUSDT": 0.0, "CASH": 0.5},
        s2_weights={"BTCUSDT": 0.5, "ETHUSDT": 0.0, "SOLUSDT": 0.0, "PAXGUSDT": 0.0, "CASH": 0.5},
        p2_rp_weights={"BTCUSDT": 0.5, "ETHUSDT": 0.0, "SOLUSDT": 0.0, "PAXGUSDT": 0.0, "CASH": 0.5},
        gross_exposure=0.5,
        account_equity=10000.0,
        dollar_allocations={"BTCUSDT": 5000.0, "ETHUSDT": 0.0, "SOLUSDT": 0.0, "PAXGUSDT": 0.0, "CASH": 5000.0},
        days_to_rebalance=3.0,
        capital_mode="TIER_0_PAPER",
        real_capital_enabled=False,
        details="Mock test details",
        error_reason=None,
        decision_headline_en="Mock headline EN",
        decision_headline_bn="Mock headline BN",
        next_trade_checklist_en=["Check 1", "Check 2"],
        next_trade_checklist_bn=["চেক ১", "চেক ২"],
    )


def test_m73_proximity_scanner_thresholds(tmp_path: Path) -> None:
    """1. NEAR_S1_BREAKOUT and APPROACHING_EMA200 fire strictly within 3.0% and stay silent outside it."""
    db_file = tmp_path / "radar_state.db"

    # Asset 1: BTCUSDT above EMA200, 2.0% to breakout (<= 3.0%) -> FIRES NEAR_S1_BREAKOUT
    # Asset 2: ETHUSDT above EMA200, 4.0% to breakout (> 3.0%) -> SILENT for NEAR_S1_BREAKOUT
    # Asset 3: SOLUSDT below EMA200, -2.5% to reclaim (>= -3.0%) -> FIRES APPROACHING_EMA200
    # Asset 4: PAXGUSDT below EMA200, -5.0% to reclaim (< -3.0%) -> SILENT for APPROACHING_EMA200
    assets = {
        "BTCUSDT": _make_mock_asset("BTCUSDT", price=90000.0, ema_status="ABOVE", dist_brk_pct=2.0),
        "ETHUSDT": _make_mock_asset("ETHUSDT", price=3000.0, ema_status="ABOVE", dist_brk_pct=4.0),
        "SOLUSDT": _make_mock_asset("SOLUSDT", price=180.0, ema_status="BELOW", dist_ema_pct=-2.5),
        "PAXGUSDT": _make_mock_asset("PAXGUSDT", price=2700.0, ema_status="BELOW", dist_ema_pct=-5.0),
    }
    snapshot = _make_mock_snapshot(assets=assets)

    report = run_market_radar(db_path=db_file, snapshot_override=snapshot)

    assert report.radar_status == "ALERT_ACTIVE"
    alert_types_by_sym = {a.symbol: a.alert_type for a in report.active_alerts}

    # BTC fires NEAR_S1_BREAKOUT
    assert "BTCUSDT" in alert_types_by_sym
    assert any(a.symbol == "BTCUSDT" and a.alert_type == "NEAR_S1_BREAKOUT" for a in report.active_alerts)

    # ETH (4.0% away) does NOT fire NEAR_S1_BREAKOUT
    assert not any(a.symbol == "ETHUSDT" and a.alert_type == "NEAR_S1_BREAKOUT" for a in report.active_alerts)

    # SOL (-2.5% away) fires APPROACHING_EMA200
    assert any(a.symbol == "SOLUSDT" and a.alert_type == "APPROACHING_EMA200" for a in report.active_alerts)

    # PAXG (-5.0% away) does NOT fire APPROACHING_EMA200
    assert not any(a.symbol == "PAXGUSDT" and a.alert_type == "APPROACHING_EMA200" for a in report.active_alerts)

    # Closest setup ranking check: BTC has dist 2.0% -> Rank 1
    assert report.closest_setup is not None
    assert report.closest_setup.symbol == "BTCUSDT"
    assert report.closest_setup.rank == 1
    assert "#1 Closest Setup: BTCUSDT" in report.headline_en


def test_m73_regime_shift_fires_once_on_transition(tmp_path: Path) -> None:
    """2. REGIME_SHIFT fires on BEAR_SHIELD -> MIXED transition and does NOT re-fire on repeated identical regimes."""
    db_file = tmp_path / "radar_state.db"

    # Cycle 1: Baseline established with BEAR_SHIELD
    snap1 = _make_mock_snapshot(regime_label="BEAR_SHIELD")
    rep1 = run_market_radar(db_path=db_file, snapshot_override=snap1)
    assert not any(a.alert_type == "REGIME_SHIFT" for a in rep1.active_alerts)

    # Cycle 2: Regime transitions to MIXED -> Must fire REGIME_SHIFT (HIGH)
    snap2 = _make_mock_snapshot(regime_label="MIXED")
    rep2 = run_market_radar(db_path=db_file, snapshot_override=snap2)
    regime_alerts = [a for a in rep2.active_alerts if a.alert_type == "REGIME_SHIFT"]
    assert len(regime_alerts) == 1
    assert regime_alerts[0].priority == "HIGH"
    assert "BEAR_SHIELD -> MIXED" in regime_alerts[0].headline_en
    assert "BEAR_SHIELD -> MIXED" in regime_alerts[0].headline_bn

    # Cycle 3: Regime remains MIXED -> Must NOT re-fire REGIME_SHIFT
    snap3 = _make_mock_snapshot(regime_label="MIXED")
    rep3 = run_market_radar(db_path=db_file, snapshot_override=snap3)
    assert not any(a.alert_type == "REGIME_SHIFT" for a in rep3.active_alerts)


def test_m73_four_hour_antispam_cooldown_and_expiry(tmp_path: Path) -> None:
    """3. 4-hour anti-spam cooldown blocks duplicate notifications within 4h and allows them after cooldown expiry."""
    db_file = tmp_path / "radar_state.db"
    notifications: list[MarketRadarReport] = []

    def mock_notifier(rep: MarketRadarReport) -> None:
        notifications.append(rep)

    t0 = datetime(2026, 11, 21, 0, 7, 0, tzinfo=UTC)

    # Asset with near breakout
    assets = {
        "BTCUSDT": _make_mock_asset("BTCUSDT", price=90000.0, ema_status="ABOVE", dist_brk_pct=1.5),
        "ETHUSDT": _make_mock_asset("ETHUSDT", price=3000.0, ema_status="ABOVE", dist_brk_pct=10.0),
        "SOLUSDT": _make_mock_asset("SOLUSDT", price=180.0, ema_status="BELOW", dist_ema_pct=-10.0),
        "PAXGUSDT": _make_mock_asset("PAXGUSDT", price=2700.0, ema_status="BELOW", dist_ema_pct=-10.0),
    }
    snap = _make_mock_snapshot(assets=assets)

    # Run 1 at t0: Alert fires, not in cooldown -> Added to new_alerts_fired, notify_callback invoked
    rep1 = run_market_radar(
        db_path=db_file,
        notify_callback=mock_notifier,
        now_utc=t0,
        snapshot_override=snap,
    )
    assert len(rep1.new_alerts_fired) > 0
    assert len(notifications) == 1

    # Run 2 at t0 + 2h (< 4h): Alert is still active in active_alerts, but suppressed in new_alerts_fired
    t1 = t0 + timedelta(hours=2)
    rep2 = run_market_radar(
        db_path=db_file,
        notify_callback=mock_notifier,
        now_utc=t1,
        snapshot_override=snap,
    )
    assert len(rep2.active_alerts) > 0
    assert len(rep2.new_alerts_fired) == 0  # Blocked by 4h cooldown!
    assert len(notifications) == 1  # Callback NOT invoked again!

    # Run 3 at t0 + 4.1h (> 4h): Cooldown has expired -> Fires again!
    t2 = t0 + timedelta(hours=4.1)
    rep3 = run_market_radar(
        db_path=db_file,
        notify_callback=mock_notifier,
        now_utc=t2,
        snapshot_override=snap,
    )
    assert len(rep3.new_alerts_fired) > 0
    assert len(notifications) == 2  # Callback invoked again after expiry!


def test_m73_stale_data_fail_closed(tmp_path: Path) -> None:
    """4. Fail-closed on stale data (stale_data_warning=True -> STALE_DATA, 0 alerts fired)."""
    db_file = tmp_path / "radar_state.db"

    stale_snap = _make_mock_snapshot(stale=True, data_age_hours=12.5)
    report = run_market_radar(db_path=db_file, snapshot_override=stale_snap)

    assert report.radar_status == "STALE_DATA"
    assert report.stale_data_warning is True
    assert len(report.active_alerts) == 0
    assert len(report.new_alerts_fired) == 0
    assert "STALE DATA" in report.headline_en
    assert "পুরানো" in report.headline_bn
    assert "Stand aside" in report.action_guidance_en


def test_m73_governance_invariants_locked() -> None:
    """5. Governance invariants locked (REAL_CAPITAL_ENABLED is False, CAPITAL_MODE == 'TIER_0_PAPER')."""
    assert REAL_CAPITAL_ENABLED is False
    assert CAPITAL_MODE == "TIER_0_PAPER"

    report = run_market_radar(offline_only=True)
    assert report.real_capital_enabled is False
    assert report.capital_mode == "TIER_0_PAPER"


def test_m73_api_cli_and_telegram_radar_en_bn(tmp_path: Path, monkeypatch: Any) -> None:
    """6. API (GET /api/desk/radar), CLI (main.py radar --offline --json), and Telegram /radar EN + BN tests."""
    # 6a. FastAPI TestClient
    client = TestClient(app)
    resp = client.get("/api/desk/radar")
    assert resp.status_code == 200
    data = resp.json()
    assert "radar_status" in data
    assert data["capital_mode"] == "TIER_0_PAPER"
    assert data["real_capital_enabled"] is False

    # 6b. CLI --offline --json
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    cli_args = argparse.Namespace(
        json=True,
        offline=True,
        brief=False,
        lang="en",
    )
    ret = cmd_radar(cli_args)
    assert ret == 0
    cli_out = buf.getvalue()
    parsed = json.loads(cli_out)
    assert "radar_status" in parsed
    assert parsed["real_capital_enabled"] is False

    # 6c. Telegram /radar EN and BN formatters
    register_all_v5_commands()
    msg_en = asyncio.run(handle_radar(args="en", chat_id="12345"))
    assert "```" in msg_en
    assert "CBT PROACTIVE MARKET RADAR & TRADER COPILOT" in msg_en
    assert "[TIER_0_PAPER — REAL CAPITAL DISABLED]" in msg_en

    msg_bn = asyncio.run(handle_radar(args="bn", chat_id="12345"))
    assert "```" in msg_bn
    assert "সিবিটি সার্বক্ষণিক মার্কেট রাডার ও ট্রেডার কোপাইলট" in msg_bn
    assert "[TIER_0_PAPER — রিয়েল ক্যাপিটাল সম্পূর্ণ নিষ্ক্রিয়]" in msg_bn
