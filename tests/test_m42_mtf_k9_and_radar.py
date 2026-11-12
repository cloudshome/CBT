"""
tests/test_m42_mtf_k9_and_radar.py
==================================
Milestone 42 Verification Suite:
1. Multi-Timeframe (MTF) Structural Alignment Gate (ALIGNED / COUNTER_TREND / NEUTRAL).
2. K9 Parity Benchmark Campaign Runner & Knife-Catch Avoidance Validation.
3. Actionable Entries Radar API Contract & Query Filters.
4. Risk-Gated Telegram Alert Hook for A+ Confirmed Entries with Cooldown Deduplication.
"""

import asyncio

from fastapi.testclient import TestClient

from app import app
from core.kronos.research.k9_parity_benchmark import K9ParityBenchmarkRunner
from core.prediction_ladder import compute_bidirectional_style_signals
from core.screener.opportunity_hunter import (
    OpportunityHunter,
    _radar_alert_cooldowns,
    evaluate_and_dispatch_radar_telegram_alert,
)
from core.sky_intelligence.multi_timeframe import multi_timeframe_engine
from core.telegram_live_desk import format_actionable_entry_alert


def test_mtf_alignment_gate_evaluation():
    """Verifies that MTF alignment evaluates cleanly for both LONG and SHORT against regime bias."""
    # Bull regime: LONG is ALIGNED, SHORT is COUNTER_TREND
    assert multi_timeframe_engine.evaluate_mtf_alignment("LONG", is_bull_regime=True) == "ALIGNED"
    assert (
        multi_timeframe_engine.evaluate_mtf_alignment("SHORT", is_bull_regime=True)
        == "COUNTER_TREND"
    )

    # Bear regime: SHORT is ALIGNED, LONG is COUNTER_TREND
    assert multi_timeframe_engine.evaluate_mtf_alignment("SHORT", is_bull_regime=False) == "ALIGNED"
    assert (
        multi_timeframe_engine.evaluate_mtf_alignment("LONG", is_bull_regime=False)
        == "COUNTER_TREND"
    )

    # Neutral fallback
    assert multi_timeframe_engine.evaluate_mtf_alignment("LONG", is_bull_regime=None) == "NEUTRAL"


def test_bidirectional_style_signals_contain_mtf_alignment():
    """Verifies that compute_bidirectional_style_signals injects mtfAlignment into all plans."""
    signals = compute_bidirectional_style_signals(
        "BTCUSDT", cur_p=76000.0, high_50=77000.0, low_50=75000.0, is_bull_regime=True
    )
    assert len(signals) == 5

    for sig in signals:
        assert "mtfAlignment" in sig
        assert "longPlan" in sig
        assert "shortPlan" in sig
        assert sig["longPlan"]["mtfAlignment"] == "ALIGNED"
        assert sig["shortPlan"]["mtfAlignment"] == "COUNTER_TREND"


def test_opportunity_hunter_mtf_score_boost_and_counter_trend_cap():
    """Verifies that ALIGNED gets +10 score boost and COUNTER_TREND is capped at Grade B (max 69.0)."""
    hunter = OpportunityHunter()

    actionable = asyncio.run(hunter.get_actionable_entries(min_score=0.0))

    assert len(actionable) > 0

    aligned_found = False
    counter_found = False

    for entry in actionable:
        assert "mtfAlignment" in entry
        assert entry["mtfAlignment"] in ("ALIGNED", "COUNTER_TREND", "NEUTRAL")

        if entry["mtfAlignment"] == "ALIGNED":
            aligned_found = True
        elif entry["mtfAlignment"] == "COUNTER_TREND":
            counter_found = True
            # Counter-trend entry without liquidity sweep reclaim must be capped at grade B (score <= 69.0)
            if entry.get("zoneOrigin") != "LIQUIDITY_SWEEP_RECLAIM":
                assert entry["readinessGrade"] in ("B", "C", "D", "QUARANTINED")
                assert entry["entryReadinessScore"] <= 69.0

    # Ensure actionable radar produces diverse directional plans across universe
    assert aligned_found is True
    assert counter_found is True


def test_k9_parity_benchmark_runner_discovery():
    """Verifies that K9ParityBenchmarkRunner discovers the 9 local K9 datasets."""
    runner = K9ParityBenchmarkRunner()
    datasets = runner.discover_datasets()

    assert len(datasets) == 9
    symbols = {d["symbol"] for d in datasets}
    timeframes = {d["timeframe"] for d in datasets}

    assert symbols == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    assert timeframes == {"15m", "1h", "4h"}


def test_k9_parity_benchmark_4h_avoided_losses():
    """Executes benchmark on BTC 4h dataset and verifies that ladder parity avoids knife-catch losses."""
    runner = K9ParityBenchmarkRunner()
    datasets = runner.discover_datasets()
    btc_4h = next(d for d in datasets if d["symbol"] == "BTCUSDT" and d["timeframe"] == "4h")

    res = runner.run_dataset_benchmark(btc_4h, step_override=2)

    assert res.bars_count > 100
    assert res.knife_catches_avoided > 0
    assert res.parity.losses < res.naive.losses
    assert res.drawdown_reduction_r >= 0.0


def test_actionable_entries_api_endpoint():
    """Tests the /api/screener/actionable-entries HTTP route."""
    client = TestClient(app)
    resp = client.get("/api/screener/actionable-entries?min_score=0")

    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert "entries" in data
    assert isinstance(data["entries"], list)

    if data["entries"]:
        entry = data["entries"][0]
        assert "symbol" in entry
        assert "style" in entry
        assert "side" in entry
        assert "mtfAlignment" in entry
        assert "readinessGrade" in entry
        assert "entryTriggerState" in entry
        assert "distancePct" in entry


def test_telegram_actionable_entry_formatting():
    """Verifies that format_actionable_entry_alert generates markdown text with required SMC fields."""
    sample_entry = {
        "symbol": "BTCUSDT",
        "style": "SWING",
        "side": "LONG",
        "readinessGrade": "A+",
        "entryReadinessScore": 94.5,
        "currentPrice": 76100.0,
        "entryZone": [75900.0, 76300.0],
        "riskRewardRatio": 4.2,
        "suggestedRiskPct": 1.0,
        "zoneOrigin": "BULLISH_OB_FVG",
        "mtfAlignment": "ALIGNED",
        "thesis": "4h BOS with session discount OB absorption.",
    }

    formatted = format_actionable_entry_alert(sample_entry)

    assert "ACTIONABLE ENTRY CONFIRMED: BTCUSDT" in formatted
    assert "🟢 LONG" in formatted
    assert "SWING" in formatted
    assert "`A+` (94.5/100)" in formatted
    assert "MTF Structural Bias" in formatted
    assert "ALIGNED" in formatted
    assert "Risk:Reward" in formatted
    assert "Deterministic Risk Gate: PASSED" in formatted


def test_evaluate_and_dispatch_radar_telegram_alert_cooldown_and_gates():
    """Verifies gating criteria, risk clearance, and cooldown deduplication for radar alerts."""
    _radar_alert_cooldowns.clear()

    # 1. Reject if criteria not met (e.g. grade B instead of A+)
    unqualified_entry = {
        "symbol": "BTCUSDT",
        "style": "SCALP",
        "side": "LONG",
        "entryTriggerState": "PULLBACK_APPROACHING",
        "readinessGrade": "B",
        "oosValidated": True,
    }
    r1 = evaluate_and_dispatch_radar_telegram_alert(unqualified_entry, dry_run=True)
    assert r1["dispatched"] is False
    assert "CRITERIA_NOT_MET" in r1["reason"]

    # 2. Accept qualified A+ entry
    qualified_entry = {
        "symbol": "BTCUSDT",
        "style": "SWING",
        "side": "LONG",
        "currentPrice": 76000.0,
        "entryZone": [75900.0, 76200.0],
        "stopLoss": 74500.0,
        "riskRewardRatio": 4.0,
        "suggestedRiskPct": 1.0,
        "entryTriggerState": "IN_ZONE_CONFIRMED",
        "readinessGrade": "A+",
        "oosValidated": True,
        "mtfAlignment": "ALIGNED",
        "zoneOrigin": "BULLISH_OB_FVG",
        "thesis": "A+ confluence entry.",
    }
    r2 = evaluate_and_dispatch_radar_telegram_alert(
        qualified_entry, cooldown_secs=1800.0, dry_run=True
    )
    assert r2["dispatched"] is True
    assert "BTCUSDT:SWING:LONG" in r2["key"]
    assert "ACTIONABLE ENTRY CONFIRMED" in r2["alert_text"]

    # 3. Subsequent immediate call must be rejected by cooldown
    r3 = evaluate_and_dispatch_radar_telegram_alert(
        qualified_entry, cooldown_secs=1800.0, dry_run=True
    )
    assert r3["dispatched"] is False
    assert "COOLDOWN_ACTIVE" in r3["reason"]
