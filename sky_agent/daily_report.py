"""sky_agent.daily_report — daily intelligence report builder (05:00 UTC).

Sections: Market / Regime / Strategies / Research / Risk / Recommendations
Only evidence-backed suggestions; no BUY NOW.
"""
from __future__ import annotations

import time
from typing import Any


def build_daily_report(*, demo: bool = False) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    # Pull from existing SKY surfaces (best-effort, never crash report)
    market: dict[str, Any] = {}
    try:
        from brain.agent import desk_status  # type: ignore
        market["desk"] = desk_status()
    except Exception as exc:
        market["desk_error"] = str(exc)[:200]

    try:
        from brain.agent import loop_health  # type: ignore
        market["loop"] = loop_health()
    except Exception:
        pass

    # Regime snapshot (last log rows)
    regimes = []
    try:
        from data.database import SignalDB
        from sky_agent.memory import ensure_memory_schema
        with SignalDB() as db:
            ensure_memory_schema(db)
            rows = db.conn.execute("SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10").fetchall()
            for r in rows:
                regimes.append(dict(r))
    except Exception:
        pass

    # Recent scored hypotheses
    hyps = []
    try:
        from data.database import SignalDB
        with SignalDB() as db:
            rows = db.conn.execute("SELECT hypothesis_id,setup,status FROM research_hypotheses ORDER BY created_ts DESC LIMIT 5").fetchall()
            for r in rows:
                hyps.append(dict(r))
    except Exception:
        pass

    # Recent SEC events
    sec_events = []
    try:
        from data.database import SignalDB
        with SignalDB() as db:
            rows = db.conn.execute("SELECT accession,event_type,severity,direction FROM sec_events ORDER BY created_ts DESC LIMIT 5").fetchall()
            for r in rows:
                sec_events.append(dict(r))
    except Exception:
        pass

    recommendations = []
    # One placeholder recommendation that demonstrates the shape (CONSIDER only if evidence)
    try:
        from sky_agent.recommendation import build_recommendation
        rec = build_recommendation(
            asset="BTCUSDT",
            timeframe="1H/4H",
            regime="bullish" if demo else (regimes[0]["regime"] if regimes else "unknown"),
            detected="Buy Pullback approaching validation area (demo)" if demo else "No high-confidence setup at report time",
            evidence=["4H trend bullish (demo)", "1H structure bullish (demo)", "volatility acceptable"] if demo else ["no high-scoring event in window"],
            expectancy_R=0.31 if demo else None,
            sample_n=412 if demo else None,
            risk_status="PASS" if demo else "UNKNOWN",
            confidence="MEDIUM",
            kind="HYPOTHESIS",
            invalidation="Break below order block or funding flip",
            sources=["SKY store", "SEC EDGAR (demo)"],
        )
        recommendations.append(rec)
    except Exception:
        pass

    report = {
        "generated_at": now,
        "market": market,
        "regimes": regimes,
        "hypotheses": hyps,
        "sec_events": sec_events,
        "recommendations": recommendations,
        "risk": {"note": "Risk gate is authoritative — this report never bypasses it."},
        "disclaimer": "Research & decision-support only. No live trades. You make the final decision.",
    }
    return report


def format_report_md(report: dict[str, Any]) -> str:
    lines = [f"# SKY Daily Intelligence Report — {report.get('generated_at')}", ""]
    lines += ["## Market", f"```json\n{report.get('market')}\n```", ""]
    lines += ["## Regime (last 10)", ""]
    for r in report.get("regimes", [])[:10]:
        lines.append(f"- {r.get('symbol')} {r.get('timeframe')}: {r.get('regime')} / {r.get('volatility_state')}")
    if not report.get("regimes"):
        lines.append("- (no regime log yet — run `python main.py agent collect --demo`)")
    lines += ["", "## Research Hypotheses", ""]
    for h in report.get("hypotheses", []):
        lines.append(f"- {h.get('hypothesis_id')}: {h.get('setup')} [{h.get('status')}]")
    if not report.get("hypotheses"):
        lines.append("- (none yet)")
    lines += ["", "## SEC Recent Events", ""]
    for e in report.get("sec_events", []):
        lines.append(f"- {e.get('accession')} {e.get('event_type')} severity {e.get('severity')} {e.get('direction')}")
    if not report.get("sec_events"):
        lines.append("- (none yet)")
    lines += ["", "## Recommendations", ""]
    for rec in report.get("recommendations", []):
        from sky_agent.recommendation import format_alert
        lines.append("```\n" + format_alert(rec) + "\n```")
    lines += ["", f"> {report.get('disclaimer')}"]
    return "\n".join(lines)
