"""brain/journal.py — the professional trading journal (decision B5).

Your roadmap's most important journal field: **"Did I follow my system?"**

    A losing trade can be an excellent trade.
    A profitable trade can be a terrible trade.

This module stores the post-trade fields per scan, derives the pre-trade
checklist automatically from the payload, scores execution quality, and feeds
the violation rate into the business metrics (decision B4).

Pre-trade (auto-derived, nothing to type): regime, HTF bias, setup, entry/SL/TP,
planned R:R, risk %, news environment.
Post-trade (you record): followed_rules, emotion, mistake, screenshot,
would_change, notes.
"""
from __future__ import annotations

from typing import Optional

from data.database import SignalDB
from data.provenance import LIVE_SOURCE_KEY, describe_source

POST_TRADE_FIELDS = ("followed_rules", "emotion", "mistake", "screenshot_path",
                     "would_change", "notes")

EMOTIONS = ("calm", "anxious", "euphoric", "fearful", "frustrated", "greedy",
            "revengeful", "bored", "confident")


def pre_trade_checklist(payload: dict) -> dict:
    """Auto-derived checklist from a scan payload (the pre-trade half)."""
    sig = payload.get("signal") or {}
    features = (payload.get("snapshot") or {}).get("features") or {}
    mtf = payload.get("mtf") or {}
    ctx = payload.get("context") or {}
    intel = payload.get("intelligence") or {}
    return {
        "asset": sig.get("asset") or features.get("symbol"),
        "timeframe": sig.get("timeframe"),
        "regime": features.get("regime_label") or intel.get("regime_label"),
        "htf_bias": (mtf.get("htf_bias") or {}).get("label") if isinstance(mtf.get("htf_bias"), dict) else mtf.get("htf_bias"),
        "setup": (payload.get("plans") or [{}])[0].get("type") if payload.get("plans") else None,
        "action": sig.get("action"),
        "entry": sig.get("entry"),
        "stop_loss": sig.get("stop_loss"),
        "take_profit": sig.get("take_profit"),
        "planned_rr": sig.get("risk_reward"),
        "news_environment": (ctx.get("macro") or {}).get("label")
                            or ("high-impact event imminent" if (ctx.get("macro") or {}).get("high_impact_imminent") else "normal"),
        "trade_quality_grade": intel.get("trade_quality_grade"),
    }


def get_journal(db: SignalDB, scan_id: int) -> Optional[dict]:
    """Read a scan's stored journal entry (None when not recorded)."""
    return db.get_journal(scan_id)


def save_journal(db: SignalDB, scan_id: int, *, followed_rules: Optional[bool] = None,
                 emotion: str = "", mistake: str = "", screenshot_path: str = "",
                 would_change: str = "", notes: str = "") -> dict:
    """Record post-trade journal fields; returns the stored entry."""
    db.save_journal(
        scan_id,
        followed_rules=(1 if followed_rules else 0) if followed_rules is not None else None,
        emotion=emotion, mistake=mistake, screenshot_path=screenshot_path,
        would_change=would_change, notes=notes)
    return db.get_journal(scan_id)


def execution_quality(db: SignalDB, scan_id: int) -> dict:
    """Score one closed trade: rule-following + P&L → verdict (B5)."""
    entry = db.get_journal(scan_id)
    scan = db.get_scan(scan_id)
    if not entry:
        return {"recorded": False}
    paper = db.paper_trade_for_scan(scan_id)
    r = float((paper or {}).get("rr_achieved") or 0.0) if paper else 0.0
    followed = bool(entry.get("followed_rules"))
    if followed and r > 0:
        verdict, quality = "Excellent trade — followed the system and won", "A+"
    elif followed and r <= 0:
        verdict, quality = "Excellent trade — followed the system; the loss was a predefined unit of risk", "B+"
    elif not followed and r > 0:
        verdict, quality = "Terrible trade — rules broken and profit was luck, not skill", "D"
    else:
        verdict, quality = "Terrible trade — rules broken and the loss was deserved", "F"
    return {
        "recorded": True,
        "followed_rules": followed,
        "outcome_r": r,
        "verdict": verdict,
        "quality": quality,
        "emotion": entry.get("emotion"),
        "mistake": entry.get("mistake"),
    }


def violation_rate(db: SignalDB) -> dict:
    """Execution discipline across all recorded trades (feeds B4 metrics).

    This is the **general journal report**: every journal row the human ever
    wrote, whatever produced the trade. It is the right number for the
    scorecard, the risk card and the weekly review — and the *wrong* number
    for a permission decision. The graduation gate must use
    :func:`graduation_discipline` instead (P12.14).
    """
    stats = db.journal_stats()
    return {
        "n": stats["n"],
        "violations": stats["violations"],
        "violation_rate": stats["violation_rate"],
    }


def graduation_discipline(db: SignalDB, source_key: str = LIVE_SOURCE_KEY) -> dict:
    """P12.14 — the discipline criterion of the graduation gate.

    P12.13 isolated graduation *performance* evidence by source. Discipline
    was still derived from ``violation_rate(db)``, i.e. from every row of
    ``journal_entries`` with no join and no provenance filter. Four ways that
    let the 90% criterion pass without a real, fully journaled book:

    * simulator samples auto-write ``followed_rules=1``, so a machine grind
      alone read as 100% compliance;
    * research-book journals (e.g. ``dukascopy:spot:bid``) outvoted the
      canonical live trades they have no authority over;
    * ``followed_rules IS NULL`` — a journal saved with no answer — counted as
      a non-violation;
    * unjournaled trades were invisible, because the denominator was journal
      rows rather than trades that *should* have been journaled. Missing
      journals therefore failed **open**.

    This computation fails closed on all four. The eligible population is
    decided, non-simulator paper trades on the canonical live series
    (:func:`SignalDB.discipline_rows`); a trade counts as journaled only when
    ``followed_rules`` is exactly 0 or 1; and compliance is measured against
    **eligible**, not against journaled::

        compliance = compliant / eligible          # None when eligible == 0

    so every missing journal lowers compliance exactly like a violation. An
    empty book yields ``None``, which :func:`data.simulator.graduation_status`
    already treats as unproven — never a pass.

    Deliberately *not* filtered by plan family: discipline is a property of
    the trader across the whole canonical real paper book, and restricting it
    to the primary family would let an undisciplined book hide outside it.
    """
    rows = db.discipline_rows(source_key=source_key)
    eligible = len(rows)
    violations = sum(1 for r in rows if r.get("followed_rules") == 0)
    compliant = sum(1 for r in rows if r.get("followed_rules") == 1)
    journaled = violations + compliant
    return {
        "eligible": eligible,
        "journaled": journaled,
        "missing_journals": eligible - journaled,
        "violations": violations,
        "compliant": compliant,
        "compliance": round(compliant / eligible, 4) if eligible else None,
        "source_key": source_key,
        "source": describe_source(source_key),
    }


def describe_discipline(d: dict) -> str:
    """One-line human summary of a :func:`graduation_discipline` payload."""
    if not d or not d.get("eligible"):
        return ("discipline: unproven — no decided real paper trades on the "
                "canonical live book yet")
    pct = f"{d['compliance'] * 100:.1f}%"
    line = (f"discipline: {pct} compliance "
            f"({d['compliant']}/{d['eligible']} real canonical trades)")
    if d.get("missing_journals"):
        line += f" — {d['missing_journals']} missing journal(s) count against you"
    if d.get("violations"):
        line += f", {d['violations']} violation(s)"
    return line


def describe_entry(entry: dict) -> str:
    if not entry:
        return "No journal entry recorded for this trade yet."
    fr = entry.get("followed_rules")
    lines = [
        f"followed rules : {'YES' if fr else 'NO' if fr == 0 else 'not recorded'}",
        f"emotion        : {entry.get('emotion') or '-'}",
        f"mistake        : {entry.get('mistake') or '-'}",
        f"screenshot     : {entry.get('screenshot_path') or '-'}",
        f"would change   : {entry.get('would_change') or '-'}",
        f"notes          : {entry.get('notes') or '-'}",
    ]
    return "\n".join(lines)
