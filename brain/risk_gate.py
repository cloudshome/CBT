"""brain/risk_gate.py — the enforced risk & discipline gate (decisions B6, B7,
B9, B10).

Your roadmap's Phase 12-13: professionals have rules for *not* trading.
Previously the daily/weekly/drawdown limits were advisory text.  Now they are
enforced at the two places a trade can start:

  * the human approval queue (CLI ``approve`` / dashboard button), and
  * the paper runner (it will not enroll new trades while the gate is shut).

The gate combines:

  B6  daily loss limit → hard block;  weekly limit → reduced-activity flag;
      drawdown ladder → -5% reduce / -8% stop & review / -10% full review
  B7  trader state (angry / tired / revenge / chasing) → hard block
  B9  progression level → effective risk caps and unproven-setup approvals
  B10 setup-proven gate → unproven setups are research-only at the
      student/researcher levels

``evaluate()`` is a pure read of the DB + config; nothing here mutates state.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from config import (PROGRESSION, PROGRESSION_LEVELS, ENFORCE_RISK_LIMITS,
                    TRADER_STATE_BLOCK, DRAWDOWN_REDUCE_PCT, DRAWDOWN_STOP_PCT,
                    DRAWDOWN_REVIEW_PCT, RISK_PCT, MAX_DAILY_LOSS_PCT,
                    MAX_WEEKLY_LOSS_PCT, ACCOUNT_BALANCE, KELLY_MAX_RISK_PCT)
from data.costs import net_r_of_row
from data.database import SignalDB
from data.provenance import LIVE_SOURCE_KEY


def progression() -> dict:
    """Effective caps for the current progression level (decision B9)."""
    level = PROGRESSION_LEVELS.get(PROGRESSION, PROGRESSION_LEVELS["student"])
    return {
        "level": PROGRESSION,
        "label": level["label"],
        "risk_pct": level["risk_pct"],
        "daily": level["daily"],
        "weekly": level["weekly"],
        "approve_unproven": level["approve_unproven"],
    }


def effective_risk() -> dict:
    """The risk numbers actually used for sizing/enforcement: progression wins
    over the generic env defaults when a progression level is active."""
    prog = progression()
    return {
        "risk_pct": prog["risk_pct"],
        "daily": prog["daily"],
        "weekly": prog["weekly"],
        "source": "progression",
        "env": {"risk_pct": RISK_PCT, "daily": MAX_DAILY_LOSS_PCT,
                "weekly": MAX_WEEKLY_LOSS_PCT},
    }


def _day_start_utc(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def _week_start_utc(now: datetime | None = None) -> int:
    """Monday 00:00 UTC of the current week, in epoch milliseconds.

    Subtract the weekday as a **timedelta**, never via ``replace(day=...)``:
    ``replace`` cannot cross a month boundary, so the previous
    ``start.replace(day=start.day - start.weekday())`` raised
    ``ValueError: day is out of range for month`` for every week that began in
    the previous month (38 days of 2026). The weekly loss limit is a hard B6
    control, so on those dates the whole risk gate raised instead of answering.
    """
    now = now or datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((start - timedelta(days=start.weekday())).timestamp() * 1000)


def closed_pnl(db: SignalDB, since_ts: int, risk_pct: float) -> dict:
    """Sum of decided paper results since a timestamp, in R and in % equity.

    The live risk book is :func:`SignalDB.live_book_rows` (P12.15): decided,
    non-simulator, canonical-live only. Simulator walk-forward samples are
    historical calibration evidence with backdated timestamps, and research
    books (non-canonical ``source_key``) are not this desk's trading — a
    research win must not offset a real loss past the daily limit, and a
    research loss must not trip a limit the live book never hit.

    P12.18: the sum is **net of costs**. P12.6 restated the desk's numbers as
    ``E_net`` and P12.8 set the rule that a measurement only matters where
    something acts on it — the daily/weekly limits act harder than anything
    else here, so they judge the same number the scorecard reports. The live
    runner writes ``rr_achieved`` only (``rr_net IS NULL``), so costs are
    computed on read from the row's own levels and holding time. A book that
    is past its loss limit once fees are paid now blocks, instead of reading
    comfortably inside the limit gross.
    """
    rows = db.live_book_rows(since_ts=since_ts)
    r_sum = round(sum(net_r_of_row(r) for r in rows), 3)
    gross_sum = round(sum(float(r["rr_achieved"] or 0.0) for r in rows), 3)
    return {"n": len(rows), "r_sum": r_sum,
            "pct": round(r_sum * risk_pct, 3),
            # Kept visible so a reviewer can see the cost drag explicitly.
            "gross_r_sum": gross_sum,
            "gross_pct": round(gross_sum * risk_pct, 3),
            "cost_r": round(gross_sum - r_sum, 3)}


def daily_weekly(db: SignalDB) -> dict:
    """Today's and this week's P&L from decided paper trades (B6)."""
    risk = effective_risk()
    today = closed_pnl(db, _day_start_utc(), risk["risk_pct"])
    week = closed_pnl(db, _week_start_utc(), risk["risk_pct"])
    daily_blocked = ENFORCE_RISK_LIMITS and today["pct"] <= -risk["daily"]
    weekly_blocked = ENFORCE_RISK_LIMITS and week["pct"] <= -risk["weekly"]
    return {
        "today": today,
        "week": week,
        "daily_limit": risk["daily"],
        "weekly_limit": risk["weekly"],
        "daily_blocked": daily_blocked,
        "weekly_blocked": weekly_blocked,
        "reduced_activity": weekly_blocked,
    }


def drawdown(db: SignalDB) -> dict:
    """Equity-curve drawdown from decided paper trades (B6 ladder).

    Equity starts at the configured account balance (or $10,000) and applies
    each decided trade's **net** R (``data.costs.net_r_of_row``) times
    ``risk_pct`` in chronological order (P12.18 — the ladder is a hard control,
    so it judges the same net anchor the scorecard reports).
    The population is :func:`SignalDB.live_book_rows` (P12.15): simulator
    samples are historical walk-forward rows, and research-book trades are
    another price series entirely — a research win interleaved into the
    sequence would refill equity and hide a real losing streak from the
    ladder, and research losses would deepen a drawdown the live desk never
    took. Neither may move a live risk control.
    """
    rows = db.live_book_rows()
    balance = ACCOUNT_BALANCE or 10_000.0
    risk = effective_risk()
    equity = balance
    peak = balance
    max_dd = 0.0
    for r in rows:
        # P12.18 — the ladder walks the NET equity curve. A drawdown measured
        # before costs is not the drawdown the account actually suffered, and
        # under-reporting it parks the desk a rung lower than reality.
        equity += balance * (net_r_of_row(r) * risk["risk_pct"] / 100.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100.0 if peak else 0.0)
    if max_dd >= DRAWDOWN_REVIEW_PCT:
        level, blocked = "full_review", ENFORCE_RISK_LIMITS
    elif max_dd >= DRAWDOWN_STOP_PCT:
        level, blocked = "stop_and_review", ENFORCE_RISK_LIMITS
    elif max_dd >= DRAWDOWN_REDUCE_PCT:
        level, blocked = "reduce_risk", ENFORCE_RISK_LIMITS
    else:
        level, blocked = "normal", False
    return {
        "equity": round(equity, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "level": level,
        "blocked": blocked,
        "ladder": {"reduce": DRAWDOWN_REDUCE_PCT, "stop": DRAWDOWN_STOP_PCT,
                   "review": DRAWDOWN_REVIEW_PCT},
    }


def trader_state_blocked(db: SignalDB) -> dict:
    """Behavioral no-trade gate (decision B7)."""
    st = db.get_trader_state()
    if not TRADER_STATE_BLOCK:
        return {"blocked": False, "state": st, "flags": []}
    flags = [k for k in ("angry", "tired", "revenge", "chasing") if st.get(k)]
    return {"blocked": bool(flags), "state": st, "flags": flags}


def setup_proven(db: SignalDB, plan_type: str,
                 source_key: str | None = LIVE_SOURCE_KEY) -> dict:
    """Setup-proven gate (decisions A6/B10): >=100 backtest samples AND >=20
    decided paper samples AND positive expectancy.

    **P12.8** — "positive expectancy" now means positive **net of costs**
    wherever the net column is populated (P12.6), falling back to gross only
    when it is not. A setup that only makes money before fees was never
    proven; it was mismeasured. The sample floors are unchanged.

    **P12.11** — the evidence is counted on **one price series**, defaulting
    to the canonical live series the desk actually trades. A Dukascopy XAU
    bid-only research book can no longer contribute samples toward proving a
    setup for live trading. Pass ``source_key=None`` to count every source
    (reporting only), or an explicit key to audit one research series.
    Strictly tighter, never looser: the floors and the bar are unchanged.
    """
    st = db.setup_stats(plan_type or "", source_key=source_key)
    bt_e = (st["backtest_expectancy"] if st.get("backtest_expectancy_net") is None
            else st["backtest_expectancy_net"])
    pp_e = (st["paper_expectancy"] if st.get("paper_expectancy_net") is None
            else st["paper_expectancy_net"])
    proven = bool(st["backtest_n"] >= 100 and st["paper_n"] >= 20 and
                  pp_e > 0 and bt_e > 0)
    return {"proven": proven, "source_key": source_key,
            "proven_on": "net" if (
        st.get("backtest_expectancy_net") is not None
        or st.get("paper_expectancy_net") is not None) else "gross", **st}


def evaluate(db: SignalDB, symbol: str | None = None, plan_type: str | None = None,
             action: str | None = None) -> dict:
    """Full gate evaluation. ``allowed=False`` means: do not open a new trade.

    Returns everything the CLI/dashboard need to explain *why*.
    """
    prog = progression()
    risk = effective_risk()
    dw = drawdown(db)
    dws = daily_weekly(db)
    ts = trader_state_blocked(db)
    blocked_by: list[str] = []
    details: dict = {}

    if dws["daily_blocked"]:
        blocked_by.append(
            f"daily loss limit reached ({dws['today']['pct']:.2f}% ≤ -{risk['daily']}%)")
    if dws["weekly_blocked"]:
        blocked_by.append(
            f"weekly loss limit reached ({dws['week']['pct']:.2f}% ≤ -{risk['weekly']}%) — reduced activity")
    if dw["blocked"]:
        blocked_by.append(
            f"drawdown ladder: {dw['level']} at {dw['max_drawdown_pct']:.2f}% drawdown")
    if ts["blocked"]:
        blocked_by.append("trader state: " + ", ".join(ts["flags"]) +
                          " — no trading while these flags are set")

    proven_check = None
    if plan_type:
        proven_check = setup_proven(db, plan_type)
        details["setup_proven"] = proven_check
        if not proven_check["proven"] and not prog["approve_unproven"]:
            # P12.8 — say *which* condition failed. When the sample floors are
            # met, the setup is unproven because it does not make money net of
            # costs, and reporting only the counts would read as a bug.
            floors_met = (proven_check["backtest_n"] >= 100
                          and proven_check["paper_n"] >= 20)
            if floors_met:
                bt_e = (proven_check["backtest_expectancy"]
                        if proven_check.get("backtest_expectancy_net") is None
                        else proven_check["backtest_expectancy_net"])
                pp_e = (proven_check["paper_expectancy"]
                        if proven_check.get("paper_expectancy_net") is None
                        else proven_check["paper_expectancy_net"])
                reason = (f"expectancy {proven_check['proven_on']} "
                          f"(backtest {bt_e:+.3f}R / paper {pp_e:+.3f}R) "
                          f"is not positive")
            else:
                reason = (f"{proven_check['backtest_n']} backtest / "
                          f"{proven_check['paper_n']} paper samples")
            blocked_by.append(
                f"setup unproven ({plan_type}): {reason} — research only at "
                f"'{prog['level']}' level")

    details.update({
        "progression": prog,
        "effective_risk": risk,
        "daily_weekly": dws,
        "drawdown": dw,
        "trader_state": ts,
        "enforced": ENFORCE_RISK_LIMITS,
    })

    # ── kelly advisory (hidden_alpha; advisory-only, never auto-executes) ──
    # P12.15: this used to call kelly_from_progress() on raw paper_trades
    # rows — a shape mismatch (KeyError 'wins') that the blanket except
    # silently turned into a permanent "unavailable" whenever the book held
    # data. kelly_from_rows() accepts the live book's actual rows, judges NET
    # of costs where recorded (P12.8), and reads canonical-live trades only.
    try:
        from engine.hidden_alpha import kelly_from_rows

        kelly = kelly_from_rows(db.live_book_rows())
        ks = kelly.get("kelly_size")
        clamped = round(min(ks, KELLY_MAX_RISK_PCT), 4) if ks is not None else None
        details["kelly"] = {
            "kelly_size": ks,
            "clamped_size": clamped,
            "win_rate": kelly.get("win_rate"),
            "expectancy": kelly.get("expectancy"),
            "max_risk_pct": KELLY_MAX_RISK_PCT,
            "n_trades": kelly.get("n_trades"),
            "note": "advisory only — the risk gate never auto-executes on kelly",
        }
    except Exception:
        details["kelly"] = {"note": "unavailable"}

    allowed = not blocked_by
    return {
        "allowed": allowed,
        # "open"/"progression" are first-class aliases: the desk agents,
        # immune diagnostics and the root MCP server read the gate through
        # these keys, while the CLI/dashboard use "allowed"/"details".
        "open": allowed,
        "blocked_by": blocked_by,
        "details": details,
        "progression": prog,
    }


def evaluate_risk_gate(db: SignalDB, symbol: str | None = None,
                       plan_type: str | None = None,
                       action: str | None = None) -> dict:
    """Convenience alias for evaluate (used by agents / immune / MCP)."""
    return evaluate(db, symbol=symbol, plan_type=plan_type, action=action)


def gate_message(gate: dict) -> str:
    if gate["allowed"]:
        return "Risk gate OPEN — trade allowed"
    return "Risk gate CLOSED — " + "; ".join(gate["blocked_by"])


def status_text(db: SignalDB) -> str:
    """Human-readable status block for `python main.py risk`."""
    g = evaluate(db)
    d = g["details"]
    risk = d["effective_risk"]
    dw = d["drawdown"]
    dws = d["daily_weekly"]
    ts = d["trader_state"]
    prog = d["progression"]
    lines = [
        "=" * 66,
        f"RISK & DISCIPLINE GATE   progression={prog['level']}  ({prog['label']})",
        "-" * 66,
        f"  effective risk      {risk['risk_pct']}%/trade   {risk['daily']}%/day   {risk['weekly']}%/week",
        # P12.18 — these percentages are NET of costs; show the drag when
        # there is any, so the number is never mistaken for a gross read.
        f"  today  {dws['today']['n']:>3} trades  {dws['today']['pct']:+.2f}%   (limit {risk['daily']}%)"
        + (f"   [gross {dws['today']['gross_pct']:+.2f}%, costs {dws['today']['cost_r']:.2f}R]"
           if dws['today'].get('cost_r') else ""),
        f"  week   {dws['week']['n']:>3} trades  {dws['week']['pct']:+.2f}%   (limit {risk['weekly']}%)"
        + (f"   [gross {dws['week']['gross_pct']:+.2f}%, costs {dws['week']['cost_r']:.2f}R]"
           if dws['week'].get('cost_r') else ""),
        f"  drawdown           {dw['max_drawdown_pct']:.2f}%  -> {dw['level']}   equity {dw['equity']:,.2f}",
        f"  trader state       {', '.join(ts['flags']) if ts['flags'] else 'clear'}",
        f"  enforced           {'yes' if d['enforced'] else 'no (advisory only)'}",
        "-" * 66,
        f"  GATE: {'OPEN — new trades allowed' if g['allowed'] else 'CLOSED — no new trades'}",
    ]
    if g["blocked_by"]:
        for b in g["blocked_by"]:
            lines.append(f"    ✗ {b}")
    if not g["allowed"] and ts["state"].get("note"):
        lines.append(f"    note: {ts['state']['note']}")
    return "\n".join(lines)
