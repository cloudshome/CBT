"""brain/agents.py — Autonomous desk agents (Morning brief, Watchdog, Paper reviewer, Weekly review).

Runs periodic, specialized desk workflows and logs all actions into the SQLite
`agent_runs` store.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from data.database import SignalDB
from brain.brief import generate_morning_brief, post_trade_review
from brain.risk_gate import evaluate_risk_gate
from brain.metrics import compute_business_metrics


class BaseAgent:
    name: str = "base"

    def __init__(self, db: Optional[SignalDB] = None):
        self.db = db

    def run(self) -> dict:
        raise NotImplementedError


class MorningBriefAgent(BaseAgent):
    name = "morning_brief"

    def run(self) -> dict:
        brief = generate_morning_brief(db=self.db)
        summary = f"{brief.get('bias_summary', 'Neutral')} — {brief.get('risk_summary', '')}"
        if brief.get("notes"):
            summary += f" ({'; '.join(brief['notes'])})"

        if self.db:
            self.db.record_agent_run(self.name, "COMPLETED", summary=summary, payload=brief)

        return {
            "agent": self.name,
            "status": "COMPLETED",
            "summary": summary,
            "data": brief,
            "ts": int(time.time()),
        }


class WatchdogAgent(BaseAgent):
    name = "watchdog"

    def run(self) -> dict:
        close_db = False
        db = self.db
        if db is None:
            db = SignalDB()
            close_db = True

        try:
            # Check open paper trades and risk gate.
            # P12.16: the watchdog reports the *live* book — raw SQL here used
            # to count simulator orphans and research-book rows as active desk
            # positions and raise stale-entry alerts about them.
            open_trades = db.live_open_rows()
            rg = evaluate_risk_gate(db)

            issues = []
            if not rg.get("open"):
                issues.append("Risk gate closed: " + "; ".join(rg.get("blocked_by", [])))

            stale_count = 0
            now = int(time.time())
            for t in open_trades:
                created = t["created_ts"] or now
                if t["status"] == "WAITING_ENTRY" and (now - created) > 48 * 3600:
                    stale_count += 1

            if stale_count > 0:
                issues.append(f"{stale_count} stale pending trades awaiting entry >48h")

            status = "WARN" if issues else "COMPLETED"
            summary = f"Monitored {len(open_trades)} active paper trades. Risk gate: {'OPEN' if rg.get('open') else 'HALTED'}."
            if issues:
                summary += f" Alerts: {'; '.join(issues)}"

            payload = {
                "active_trades_count": len(open_trades),
                "stale_trades_count": stale_count,
                "risk_gate_open": rg.get("open"),
                "issues": issues,
            }

            db.record_agent_run(self.name, status, summary=summary, payload=payload)

            return {
                "agent": self.name,
                "status": status,
                "summary": summary,
                "data": payload,
                "ts": int(time.time()),
            }
        finally:
            if close_db:
                db.close()


class PaperReviewerAgent(BaseAgent):
    name = "paper_reviewer"

    def run(self) -> dict:
        close_db = False
        db = self.db
        if db is None:
            db = SignalDB()
            close_db = True

        try:
            # Query recent closed trades
            closed = db.conn.execute(
                "SELECT * FROM paper_trades WHERE status='CLOSED' ORDER BY closed_ts DESC LIMIT 10").fetchall()

            reviews = []
            for r in closed:
                scan_id = r["scan_id"]
                rev = post_trade_review(scan_id, db=db)
                reviews.append({
                    "scan_id": scan_id,
                    "symbol": r["symbol"],
                    "outcome": r["outcome"],
                    "rr_achieved": r["rr_achieved"],
                    "headline": rev.get("headline"),
                })

            summary = f"Reviewed {len(reviews)} closed paper trades."
            if reviews:
                wins = sum(1 for r in reviews if r["outcome"] in ("WIN", "FULL_WIN", "TP_HIT"))
                summary += f" Win rate: {wins}/{len(reviews)} ({int(wins/len(reviews)*100)}%)."

            payload = {"reviewed_count": len(reviews), "reviews": reviews}
            db.record_agent_run(self.name, "COMPLETED", summary=summary, payload=payload)

            return {
                "agent": self.name,
                "status": "COMPLETED",
                "summary": summary,
                "data": payload,
                "ts": int(time.time()),
            }
        finally:
            if close_db:
                db.close()


class WeeklyReviewAgent(BaseAgent):
    name = "weekly_review"

    def run(self) -> dict:
        close_db = False
        db = self.db
        if db is None:
            db = SignalDB()
            close_db = True

        try:
            metrics = compute_business_metrics(db=db)
            o = metrics.get("overall", {})
            e = metrics.get("execution", {})
            pf = o.get("profit_factor") or 0.0
            n_trades = o.get("n", 0)
            viol_rate = e.get("violation_rate", 0.0)
            rule_rate = int((1.0 - viol_rate) * 100) if viol_rate is not None else 100

            change_note = "Expectancy & discipline stable."
            if rule_rate < 80:
                change_note = "Warning: Rule compliance below 80% threshold."

            summary = (f"Weekly review: {n_trades} trades, PF {pf:.2f}, "
                       f"Rule compliance {rule_rate}%. {change_note}")

            payload = {"metrics": metrics, "change_detection": change_note}
            db.record_agent_run(self.name, "COMPLETED", summary=summary, payload=payload)

            return {
                "agent": self.name,
                "status": "COMPLETED",
                "summary": summary,
                "data": payload,
                "ts": int(time.time()),
            }
        finally:
            if close_db:
                db.close()


AGENTS = {
    "morning_brief": MorningBriefAgent,
    "morning": MorningBriefAgent,
    "watchdog": WatchdogAgent,
    "paper_reviewer": PaperReviewerAgent,
    "paper_review": PaperReviewerAgent,
    "weekly_review": WeeklyReviewAgent,
    "weekly": WeeklyReviewAgent,
}

# Canonical autonomous-agent cadence. Used by desk_status() to answer
# "which agent should run next?" without inventing a scheduler.
CORE_AGENTS: tuple[str, ...] = (
    "morning_brief", "watchdog", "paper_reviewer", "weekly_review",
)
AGENT_CADENCE_HOURS: dict[str, float] = {
    "morning_brief": 24.0,     # once per UTC day
    "watchdog": 4.0,           # a few times a day
    "paper_reviewer": 24.0,    # after the session
    "weekly_review": 168.0,    # once a week
}


def run_agent(name: str, db: Optional[SignalDB] = None) -> dict:
    """Run an agent by name."""
    cls = AGENTS.get(name.lower().replace("-", "_"))
    if not cls:
        return {
            "agent": name,
            "status": "ERROR",
            "summary": f"Unknown agent '{name}'. Available: {', '.join(sorted(set(AGENTS.keys())))}",
            "ts": int(time.time()),
        }
    return cls(db=db).run()


def run_all_agents(db: Optional[SignalDB] = None) -> dict:
    """Run all core desk agents."""
    results = {}
    for name, cls in (("morning_brief", MorningBriefAgent),
                      ("watchdog", WatchdogAgent),
                      ("paper_reviewer", PaperReviewerAgent),
                      ("weekly_review", WeeklyReviewAgent)):
        results[name] = cls(db=db).run()
    return {
        "status": "COMPLETED",
        "agents": results,
        "ts": int(time.time()),
    }


def next_scheduled_agent(db: Optional[SignalDB] = None) -> dict:
    """Which autonomous desk agent is most overdue.

    Looks at last-run timestamps in ``agent_runs`` and compares them
    against :data:`AGENT_CADENCE_HOURS`. Returns a small advisory dict
    — never starts an agent. Used by ``desk_status()``.

    If nothing has ever run, recommend ``morning_brief`` (the cheapest
    first desk action).
    """
    close_db = False
    if db is None:
        db = SignalDB()
        close_db = True
    try:
        now = int(time.time())
        last_by_name: dict[str, dict] = {}
        for name in CORE_AGENTS:
            rows = db.latest_agent_runs(limit=1, agent=name)
            if rows:
                last_by_name[name] = rows[0]

        candidates: list[dict] = []
        for name in CORE_AGENTS:
            cadence = AGENT_CADENCE_HOURS[name]
            last = last_by_name.get(name)
            last_ts = int(last["ts"]) if last and last.get("ts") else None
            age_hours = None if last_ts is None else max(0.0, (now - last_ts) / 3600.0)
            overdue_hours = cadence if last_ts is None else max(0.0, age_hours - cadence)
            never_run = last_ts is None
            candidates.append({
                "name": name,
                "cadence_hours": cadence,
                "last_run_ts": last_ts,
                "age_hours": None if age_hours is None else round(age_hours, 2),
                "overdue_hours": round(overdue_hours, 2),
                "never_run": never_run,
                "last_status": (last or {}).get("status"),
            })

        # If nothing has ever run, start with morning_brief (cheapest first
        # desk action). Otherwise pick the most overdue agent.
        if all(c["never_run"] for c in candidates):
            pick = next(c for c in candidates if c["name"] == "morning_brief")
        else:
            candidates.sort(key=lambda c: (-c["overdue_hours"], c["name"]))
            pick = candidates[0]
        if pick["never_run"]:
            reason = (f"{pick['name']} has never run — start the desk with "
                      f"`python main.py agent {pick['name'].replace('_', '-')}`")
        elif pick["overdue_hours"] > 0:
            reason = (f"{pick['name']} is {pick['overdue_hours']:.1f}h overdue "
                      f"(cadence {pick['cadence_hours']:.0f}h)")
        else:
            reason = (f"all agents are within cadence; next up is "
                      f"{pick['name']} (last run {pick['age_hours']:.1f}h ago)")
        return {
            "name": pick["name"],
            "overdue_hours": pick["overdue_hours"],
            "age_hours": pick["age_hours"],
            "cadence_hours": pick["cadence_hours"],
            "last_run_ts": pick["last_run_ts"],
            "never_run": pick["never_run"],
            "reason": reason,
            "candidates": candidates,
        }
    finally:
        if close_db:
            db.close()
