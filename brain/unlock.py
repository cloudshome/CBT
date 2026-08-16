"""brain/unlock.py — why the gate is closed, and exactly how to open it.

The risk gate refusing almost every trade is **correct behaviour** for a
system with no measured edge — but "blocked" with no path forward reads like a
broken app. This module turns every block into a progress bar with a named
next action.

For each blocking reason it answers three questions:

1. **Why** am I blocked, in plain language?
2. **How far** am I from clearing it (current vs target, as a percentage)?
3. **What do I click** to make progress — a real Command-center action id.

Two classes of block exist and they are deliberately treated differently:

``earn``     evidence you must accumulate (backtest / paper samples,
             positive expectancy). The unlock is *work*, and this module
             tells you how much is left.
``wait``     protective states that clear on their own or by choice — a
             daily loss limit resets tomorrow, a trader-state flag clears
             when you are calm again.

Nothing here can open a gate. It only explains and measures.
"""
from __future__ import annotations

from typing import Optional

from data.database import SignalDB

BACKTEST_TARGET = 100
PAPER_TARGET = 20


def _pct(current: float, target: float) -> float:
    if target <= 0:
        return 100.0
    return round(min(100.0, max(0.0, current / target * 100.0)), 1)


def setup_progress(db: SignalDB, plan_type: str) -> dict:
    """Evidence progress for one setup, as bars the dashboard can draw."""
    from brain.risk_gate import setup_proven
    st = setup_proven(db, plan_type)
    bt_n, pp_n = int(st.get("backtest_n") or 0), int(st.get("paper_n") or 0)
    bt_e = (st.get("backtest_expectancy") if st.get("backtest_expectancy_net") is None
            else st.get("backtest_expectancy_net"))
    pp_e = (st.get("paper_expectancy") if st.get("paper_expectancy_net") is None
            else st.get("paper_expectancy_net"))
    criteria = [
        {"name": "Backtest samples", "current": bt_n, "target": BACKTEST_TARGET,
         "pct": _pct(bt_n, BACKTEST_TARGET), "met": bt_n >= BACKTEST_TARGET,
         "unit": "samples",
         "action": "backtest", "action_label": "Run a backtest",
         "why": "The setup must be graded over enough history to be more than "
                "a lucky streak."},
        {"name": "Paper samples", "current": pp_n, "target": PAPER_TARGET,
         "pct": _pct(pp_n, PAPER_TARGET), "met": pp_n >= PAPER_TARGET,
         "unit": "decided trades",
         "action": "simulator", "action_label": "Grind paper samples",
         "why": "Backtests are optimistic. The setup must also survive "
                "forward, on candles it never saw."},
        {"name": "Backtest expectancy", "current": bt_e, "target": 0.0,
         "pct": 100.0 if (bt_e or 0) > 0 else 0.0, "met": (bt_e or 0) > 0,
         "unit": "R per trade",
         "action": "scorecard", "action_label": "Inspect the scorecard",
         "why": "It must make money net of fees and slippage — not before them."},
        {"name": "Paper expectancy", "current": pp_e, "target": 0.0,
         "pct": 100.0 if (pp_e or 0) > 0 else 0.0, "met": (pp_e or 0) > 0,
         "unit": "R per trade",
         "action": "scorecard", "action_label": "Inspect the scorecard",
         "why": "Forward results must be positive too, or the backtest was "
                "curve-fitted."},
    ]
    met = sum(1 for c in criteria if c["met"])
    return {
        "plan_type": plan_type,
        "proven": bool(st.get("proven")),
        "proven_on": st.get("proven_on"),
        "criteria": criteria,
        "met": met,
        "total": len(criteria),
        "pct": round(sum(c["pct"] for c in criteria) / len(criteria), 1),
        "next_action": next((c for c in criteria if not c["met"]), None),
    }


def _classify(reason: str) -> dict:
    """Map a raw ``blocked_by`` string to a human explanation + next click."""
    text = reason.lower()
    if "setup unproven" in text:
        return {
            "kind": "earn",
            "title": "This setup has not proven itself yet",
            "plain": "SKY will not risk money on a pattern it has never "
                     "measured. It needs 100 graded backtest trades, 20 decided "
                     "paper trades, and positive expectancy after costs.",
            "action": "backtest", "action_label": "Run a backtest",
            "alt_action": "simulator", "alt_action_label": "Grind paper samples",
        }
    if "daily loss limit" in text:
        return {
            "kind": "wait",
            "title": "You hit today's loss limit",
            "plain": "The day is over for trading. This is the rule that keeps "
                     "one bad session from becoming a bad month. It resets at "
                     "00:00 UTC.",
            "action": "daily", "action_label": "Review today",
        }
    if "weekly loss limit" in text:
        return {
            "kind": "wait",
            "title": "You hit this week's loss limit",
            "plain": "Step back until the week rolls over. Use the time to "
                     "review what the losing trades had in common.",
            "action": "agent_weekly", "action_label": "Run the weekly review",
        }
    if "drawdown" in text:
        return {
            "kind": "wait",
            "title": "Drawdown protection engaged",
            "plain": "Your equity is far enough below its peak that the ladder "
                     "reduced or stopped trading. Size comes back as the curve "
                     "recovers.",
            "action": "risk", "action_label": "See the risk status",
        }
    if "trader state" in text:
        return {
            "kind": "wait",
            "title": "You told SKY you are not in a fit state",
            "plain": "Angry, tired, revenge or chasing — you set one of these "
                     "flags. Clear it in the Risk center when it is honestly "
                     "no longer true.",
            "action": None, "action_label": None,
            "ui_hint": "risk",
        }
    if "portfolio" in text or "exposure" in text or "correlated" in text:
        return {
            "kind": "wait",
            "title": "Too much correlated exposure already open",
            "plain": "BTC and ETH move together. Taking both is one bet at "
                     "double size, so the desk caps the bucket.",
            "action": None, "action_label": None, "ui_hint": "manage",
        }
    if "desk" in text:
        return {
            "kind": "wait",
            "title": "The desk filter said no trade",
            "plain": "Confidence, risk/reward or structure did not clear the "
                     "institutional bar. Most hours are genuinely not tradeable.",
            "action": "intelligence", "action_label": "Read the desk report",
        }
    return {
        "kind": "wait", "title": "Blocked", "plain": reason,
        "action": "risk", "action_label": "See the risk status",
    }


def explain(db: SignalDB, plan_type: Optional[str] = None,
            symbol: Optional[str] = None) -> dict:
    """Full 'why am I blocked and what do I do' report for the dashboard."""
    from brain.risk_gate import evaluate, progression

    gate = evaluate(db, symbol=symbol, plan_type=plan_type)
    prog = progression()
    blocks = []
    for reason in gate.get("blocked_by", []):
        entry = _classify(reason)
        entry["reason"] = reason
        if entry["kind"] == "earn" and plan_type:
            entry["progress"] = setup_progress(db, plan_type)
        blocks.append(entry)

    earn = [b for b in blocks if b["kind"] == "earn"]
    if gate.get("allowed"):
        headline = "The gate is OPEN — a qualifying signal can be approved."
        summary = ("Everything the desk checks is currently satisfied. It will "
                   "still only produce a signal when the market actually offers "
                   "a setup.")
    elif earn:
        headline = "Blocked because SKY has not yet proven this setup makes money."
        summary = ("This is the system protecting you, not a bug. Every "
                   "profitable trader earns the right to size up with evidence "
                   "first. The bars below show exactly how much is left.")
    elif blocks:
        headline = blocks[0]["title"]
        summary = blocks[0]["plain"]
    else:
        headline = "No signal to act on right now."
        summary = ("Nothing is blocking you — the market simply is not offering "
                   "a setup that meets the desk's standard.")

    return {
        "allowed": bool(gate.get("allowed")),
        "headline": headline,
        "summary": summary,
        "blocks": blocks,
        "progression": prog,
        "plan_type": plan_type,
        "has_earnable": bool(earn),
    }


def evidence_overview(db: SignalDB, limit: int = 12) -> dict:
    """Progress for every setup the engine knows, best-progressed first.

    This is the Evidence tab: the honest answer to "how close is SKY to
    actually being allowed to trade anything?"
    """
    from config import PRIMARY_FAMILIES, PRIMARY_SETUP_FAMILY

    seen: list[str] = []
    try:
        rows = db.conn.execute(
            "SELECT DISTINCT plan_type FROM backtest_results "
            "WHERE plan_type IS NOT NULL AND plan_type != ''").fetchall()
        seen.extend(r[0] for r in rows)
        rows = db.conn.execute(
            "SELECT DISTINCT plan_type FROM paper_trades "
            "WHERE plan_type IS NOT NULL AND plan_type != ''").fetchall()
        seen.extend(r[0] for r in rows)
        rows = db.conn.execute(
            "SELECT DISTINCT type FROM plans "
            "WHERE type IS NOT NULL AND type != ''").fetchall()
        seen.extend(r[0] for r in rows)
    except Exception:
        pass

    family = PRIMARY_FAMILIES.get(PRIMARY_SETUP_FAMILY)
    if family:
        seen.extend(family)
    unique = sorted({s for s in seen if s})

    setups = [setup_progress(db, name) for name in unique]
    setups.sort(key=lambda s: (-s["pct"], s["plan_type"]))
    proven = [s for s in setups if s["proven"]]
    return {
        "setups": setups[:limit],
        "count": len(setups),
        "proven_count": len(proven),
        "primary_family": PRIMARY_SETUP_FAMILY,
        "primary_setups": sorted(family) if family else [],
        "headline": (
            f"{len(proven)} of {len(setups)} setups proven"
            if setups else "no setups measured yet — run a backtest to begin"),
        "next_step": (
            "Every setup is still unproven. Start with: Backfill real history → "
            "Backtest → Simulator. The Evidence pipeline button does all three."
            if not proven else
            "At least one setup is proven. Keep paper-trading it; do not add "
            "new setups until this one holds up."),
    }
