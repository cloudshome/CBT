"""tests/test_m70_desk_trigger_explainer.py — Milestone 70 Verification Suite.

Verifies:
1. start_terminal.sh executable permission.
2. evaluate_p2_rp_snapshot causal explainer fields:
   - ema200_price, donchian48_high, distance_to_ema200_pct, distance_to_breakout_pct
   - s1_status, s2_status, waiting_reason_en, waiting_reason_bn
   - decision_headline_en, decision_headline_bn
   - next_trade_checklist_en, next_trade_checklist_bn
3. GET /api/desk/today returns HTTP 200 with all trigger explainer fields.
4. Constitutional locks: REAL_CAPITAL_ENABLED = False, CAPITAL_MODE = "TIER_0_PAPER".
"""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from core.strategies.p2_risk_parity import (
    CAPITAL_MODE,
    REAL_CAPITAL_ENABLED,
    UNIVERSE,
    evaluate_p2_rp_snapshot,
    load_candles_for_p2_rp,
)


def test_m70_start_terminal_executable_bit():
    """Verify start_terminal.sh has executable bit set."""
    script_path = Path(__file__).resolve().parent.parent / "start_terminal.sh"
    assert script_path.exists(), "start_terminal.sh not found"
    assert os.access(script_path, os.X_OK), "start_terminal.sh must have executable permission (chmod +x)"


def test_m70_snapshot_trigger_explainer_fields():
    """Verify evaluate_p2_rp_snapshot populates all M70 trigger explainer fields causally."""
    dfs, src = load_candles_for_p2_rp(source="parquet")
    assert dfs, "Failed to load candles for test"

    snapshot = evaluate_p2_rp_snapshot(dfs, data_source=src)

    # 1. Headline fields
    assert snapshot.decision_headline_en, "Missing decision_headline_en"
    assert snapshot.decision_headline_bn, "Missing decision_headline_bn"
    assert "CASH" in snapshot.decision_headline_en or "ACTIVE" in snapshot.decision_headline_en

    # 2. Checklist fields
    assert len(snapshot.next_trade_checklist_en) == 3, "Expected top 3 checklist items in EN"
    assert len(snapshot.next_trade_checklist_bn) == 3, "Expected top 3 checklist items in BN"
    for item in snapshot.next_trade_checklist_en:
        assert isinstance(item, str) and len(item) > 10
        assert "$" in item and "%" in item

    for item in snapshot.next_trade_checklist_bn:
        assert isinstance(item, str) and len(item) > 10
        assert "$" in item and "%" in item

    # 3. Per-asset trigger fields
    for sym in UNIVERSE:
        assert sym in snapshot.assets, f"Missing asset {sym}"
        m = snapshot.assets[sym]

        assert m.ema200_price > 0.0, f"Invalid ema200_price for {sym}"
        assert m.donchian48_high > 0.0, f"Invalid donchian48_high for {sym}"
        assert isinstance(m.distance_to_ema200_pct, float)
        assert isinstance(m.distance_to_breakout_pct, float)
        assert m.distance_to_breakout_pct >= 0.0

        assert m.s1_status in ("ACTIVE_LONG", "WAITING_EMA200", "WAITING_BREAKOUT")
        assert m.s2_status in ("SELECTED_TOP2", "NEGATIVE_MOMENTUM", "OUTRANKED")

        assert len(m.waiting_reason_en) > 10
        assert len(m.waiting_reason_bn) > 10
        assert "$" in m.waiting_reason_en
        assert "$" in m.waiting_reason_bn

    # 4. Constitutional safety
    assert snapshot.capital_mode == CAPITAL_MODE == "TIER_0_PAPER"
    assert snapshot.real_capital_enabled is REAL_CAPITAL_ENABLED is False


@pytest.mark.asyncio
async def test_m70_api_desk_today_trigger_explainer_endpoint():
    """Verify GET /api/desk/today?source=parquet delivers trigger explainer fields."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/desk/today?equity=10000&source=parquet")
        assert res.status_code == 200
        data = res.json()

        assert "decision_headline_en" in data
        assert "decision_headline_bn" in data
        assert "next_trade_checklist_en" in data
        assert "next_trade_checklist_bn" in data
        assert len(data["next_trade_checklist_en"]) == 3
        assert len(data["next_trade_checklist_bn"]) == 3

        assets = data["assets"]
        for sym in UNIVERSE:
            assert sym in assets
            a = assets[sym]
            assert "ema200_price" in a
            assert "donchian48_high" in a
            assert "distance_to_ema200_pct" in a
            assert "distance_to_breakout_pct" in a
            assert "s1_status" in a
            assert "s2_status" in a
            assert "waiting_reason_en" in a
            assert "waiting_reason_bn" in a

        assert data["capital_mode"] == "TIER_0_PAPER"
        assert data["real_capital_enabled"] is False
