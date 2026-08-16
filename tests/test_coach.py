"""Tests for the Coach teaching layer."""
from __future__ import annotations

from brain.coach import (GLOSSARY, _expand, explain_signal, mentor,
                         personal_feedback, five_levels, management_checklist)
from data.database import SignalDB


def _payload() -> dict:
    return {
        "signal": {"signal_id": "BTCUSDT_20260804_1452", "action": "BUY",
                   "asset": "BTCUSDT", "timeframe": "15m", "confidence": "HIGH",
                   "reason": "Bullish BOS + volume spike above VWAP + bullish RSI divergence"},
        "plans": [
            {"type": "Buy Pullback", "action": "BUY", "confidence": 84,
             "condition": "IF price pulls back to bullish Order Block near 61000.00 AND shows rejection",
             "entry": 61000.0, "stop_loss": 60600.0,
             "take_profits": [61900.0, 62800.0], "risk_reward": 2.2,
             "status": "waiting", "reasons": ["Bullish structure (bos_up)",
                                               "Unfilled bullish fair value gap"]},
        ],
        "snapshot": {"features": {"trend": "bullish", "ema_alignment_bull": True,
                                  "supertrend_bull": True, "adx": 28, "rsi": 58,
                                  "volume_spike": True, "volume_ratio": 2.4,
                                  "above_vwap": True, "close_vs_vwap_pct": 0.4,
                                  "event_kind": "bos_up", "trend_bias": "bullish",
                                  "premium_discount": "discount",
                                  "premium_discount_position": 0.3,
                                  "sweep": {"side": "sellside", "level": 60500.0},
                                  "rsi_divergence": {"bull": 2, "bear": 0}}},
    }


def test_glossary_has_core_terms():
    for term in ("BOS", "CHOCH", "FVG", "Order Block", "Liquidity Sweep", "VWAP",
                 "Risk:Reward", "Expectancy"):
        assert term in GLOSSARY


def test_expand_annotates_terms():
    out = _expand("IF price pulls back to bullish Order Block near 61000 AND shows rejection")
    assert "Order Block" in out and "footprint" in out


def test_explain_signal_speaks_plain():
    lines = explain_signal(_payload())
    joined = "\n".join(lines).lower()
    assert "trend is bullish" in joined
    assert "rsi 58.0" in joined
    assert "volume is 2.4x" in joined
    assert "sl = where you're wrong" in joined  # the safety reminder


def test_mentor_walks_through():
    out = mentor(_payload())
    assert "1." in out and "Entry" in out and "Stop at" in out
    assert "Take profits" in out
    assert "Risk:reward" in out


def test_mentor_no_plans():
    out = mentor({"signal": {"action": "NO TRADE"}, "plans": [],
                  "snapshot": {"features": {"trend": "mixed", "price": 60000.0,
                                            "trend_bias": "neutral"}}})
    assert "best trade is no trade" in out.lower()


def test_management_checklist_has_position_manager_steps():
    plan = {"type": "Buy Pullback", "take_profits": [61900.0, 62800.0],
            "entry": 61000.0, "stop_loss": 60600.0, "risk_reward": 2.2}
    out = management_checklist(plan)
    joined = "\n".join(out)
    assert "HOLD" in joined and "REDUCE" in joined and "TRAIL" in joined
    assert "EXIT" in joined
    assert "TP1 61,900.00" in joined  # formatted target from the ladder
    assert "no martingale" in joined.lower()  # the P13 invariant
    assert "ADD to a losing trade" in joined


def test_management_checklist_no_plan():
    out = management_checklist(None)
    assert "no active plan" in "\n".join(out).lower()


def test_five_levels_has_all_five_ladders():
    joined = "\n".join(five_levels(_payload()))
    for level in ("LEVEL 1 — OBSERVATION", "LEVEL 2 — INTERPRETATION",
                  "LEVEL 3 — OPPORTUNITY", "LEVEL 4 — DECISION",
                  "LEVEL 5 — ACTION"):
        assert level in joined
    # interpretation explains the structure, not just reports it
    assert "Structural bias is bullish" in joined
    # score ≠ permission, using the plan's own confidence (no intelligence
    # payload needed)
    assert "Score ≠ permission — confidence 84%" in joined


def test_five_levels_action_lists_entry_stop_targets():
    joined = "\n".join(five_levels(_payload()))
    assert "Entry 61,000.00" in joined
    assert "Stop 60,600.00" in joined
    assert "Targets 61,900.00, 62,800.00" in joined
    assert "Homework: write the plan BEFORE price moves" in joined


def test_five_levels_decision_reflects_desk_block():
    payload = _payload()
    payload["decision"] = {"action": "NO TRADE",
                           "blocked_by": ["risk(daily_loss_limit)"],
                           "decision_text": "WAIT — no trade"}
    joined = "\n".join(five_levels(payload))
    assert "Desk decision: NO TRADE" in joined
    assert "risk(daily_loss_limit)" in joined
    assert "watch-item" in joined  # plan ≠ permission when the desk says no


def test_five_levels_no_plans_teaches_waiting():
    payload = {"signal": {"action": "NO TRADE"}, "plans": [],
               "snapshot": {"features": {"trend": "mixed", "price": 60000.0,
                                         "trend_bias": "neutral"}}}
    joined = "\n".join(five_levels(payload))
    assert "No plan above the confidence threshold" in joined
    assert "Stand aside" in joined


def test_five_levels_measured_evidence_from_db(tmp_path):
    db = SignalDB(tmp_path / "t.db")
    joined = "\n".join(five_levels(_payload(), db=db))
    assert "Measured evidence" in joined
    assert "paper-trade" in joined.lower()
    db.close()


def test_personal_feedback_empty(tmp_path):
    db = SignalDB(tmp_path / "t.db")
    fb = personal_feedback(db)
    assert isinstance(fb, list)
    db.close()


def test_personal_feedback_with_activity(tmp_path):
    db = SignalDB(tmp_path / "t.db")
    from tests.test_database import _payload as mk
    sid = db.save_scan(mk())
    db.update_status(sid, "APPROVED", note="strong setup")
    fb = personal_feedback(db)
    assert any("approved" in f for f in fb)
    db.close()
