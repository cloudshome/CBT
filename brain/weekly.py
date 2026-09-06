"""brain/weekly.py — W3: the weekly trader review (one computation, many surfaces).

The Sunday desk mirror. Turns the canonical live paper book into the one page
a developing trader rereads every week:

* what actually happened this week vs all time (net of costs, always);
* the equity curve and the R-multiple distribution of every decision;
* rule violations, counting the mistake types that repeat;
* the graduation tracker per setup — exactly which evidence is missing;
* one next practice task, derived from the weakest link; and
* an honest grade, clearly advisory — the unchanged graduation bar remains
  the only authoritative gate (P12.13/P12.14).

Safety invariants held here:

* the population is always the canonical live book
  (:func:`SignalDB.live_book_rows` / :func:`SignalDB.discipline_rows`,
  P12.15/P12.14) — simulator walk-forward rows and research-book
  (``source_key``) trades are never silently pooled;
* every expectancy/win/PF judgement is NET of costs (P12.18); a win is a
  net win;
* read-only. No threshold is moved, nothing is approved, nothing is traded.
  This module *reports* the bar; it never lowers it.

Surfaces: ``python main.py weekly``, ``GET /api/weekly`` (+ ``/export``),
the dashboard Review tab, the ``weekly_review`` MCP tool, and the
``WeeklyReviewAgent`` payload. Same computation everywhere (invariant #10).
"""

from __future__ import annotations

import time
from collections import Counter

from brain.journal import graduation_discipline
from data.costs import net_r_of_row
from data.database import SignalDB
from data.simulator import GRADUATION_CRITERIA, paper_progress

# The journal-first approval gate (W3.3) uses this population and this label.
JOURNAL_GATE_LABEL = "journal-first discipline"


def _day_key(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


def _book_stats(rows: list[dict]) -> dict:
    """Net-anchored R statistics over one list of live-book rows.

    Mirrors ``brain.metrics._metrics`` judgement: wins are NET wins, the
    profit factor is computed on net R, and a cost-free book (``rr_net ==
    rr_achieved``) behaves exactly like the pre-cost books did.
    """
    if not rows:
        return {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "expectancy_net": None,
            "expectancy_gross": None,
            "profit_factor": None,
            "total_r_net": 0.0,
            "avg_win_r": None,
            "avg_loss_r": None,
            "best_r": None,
            "worst_r": None,
        }
    net = [net_r_of_row(r) for r in rows]
    gross = [float(r.get("rr_achieved") or 0.0) for r in rows]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    n = len(net)
    wr = len(wins) / n if n else None
    gw = sum(wins)
    gl = abs(sum(losses))
    pf = round(gw / gl, 3) if gl > 0 else (99.0 if gw > 0 else None)
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 4) if wr is not None else None,
        "expectancy_net": round(sum(net) / n, 4),
        "expectancy_gross": round(sum(gross) / n, 4),
        "profit_factor": pf,
        "total_r_net": round(sum(net), 3),
        "avg_win_r": round(gw / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
        "best_r": round(max(net), 3),
        "worst_r": round(min(net), 3),
    }


# R-multiple histogram buckets: (label, low_exclusive_or_None, high_inclusive)
_R_BUCKETS: tuple[tuple[str, float | None, float | None], ...] = (
    ("≤ -2R", None, -2.0),
    ("(-2R,-1R]", -2.0, -1.0),
    ("(-1R,-0.5R]", -1.0, -0.5),
    ("(-0.5R,0R)", -0.5, 0.0),
    ("0R breakeven", 0.0, 0.0),
    ("(0R,+0.5R]", 0.0, 0.5),
    ("(+0.5R,+1R]", 0.5, 1.0),
    ("(+1R,+2R]", 1.0, 2.0),
    ("> +2R", 2.0, None),
)


def _r_distribution(rows: list[dict]) -> list[dict]:
    """Net-R histogram — the shape of the book, not just its mean."""
    nets = [net_r_of_row(r) for r in rows]
    out = []
    for label, lo, hi in _R_BUCKETS:
        if label == "0R breakeven":
            n = sum(1 for x in nets if x == 0.0)
        elif lo is None:
            n = sum(1 for x in nets if x <= (hi or 0.0))
        elif hi is None:
            n = sum(1 for x in nets if x > lo)
        else:
            n = sum(1 for x in nets if lo < x <= hi)
        out.append(
            {
                "bucket": label,
                "n": n,
                "pct": round(100.0 * n / len(nets), 1) if nets else 0.0,
            }
        )
    return out


def _violations(db: SignalDB, since_ts_ms: int) -> dict:
    """Rule violations over the canonical live book, with the mistake breakdown.

    Joins decided live paper trades to their journal answers — same predicate
    as :func:`graduation_discipline` (P12.14) — then counts the human mistake
    taxonomy the journal form already records.
    """
    discipline = graduation_discipline(db)
    rows = db.conn.execute(
        """SELECT p.scan_id AS scan_id, p.outcome AS outcome,
                  COALESCE(p.closed_ts, p.opened_ts, p.created_ts) AS ts,
                  j.followed_rules AS followed_rules,
                  COALESCE(j.mistake, '') AS mistake,
                  COALESCE(j.emotion, '') AS emotion
           FROM paper_trades p
           LEFT JOIN journal_entries j ON j.scan_id = p.scan_id
           WHERE p.outcome IN ('TP_HIT','STOP_LOSS')
             AND p.sim_key IS NULL
             AND COALESCE(p.source_key,'')=''
           ORDER BY ts ASC"""
    ).fetchall()
    by_mistake: Counter = Counter()
    by_emotion: Counter = Counter()
    recent: list[dict] = []
    missing_ids: list[int] = []
    for r in rows:
        fr = r["followed_rules"]
        if fr is None:
            missing_ids.append(int(r["scan_id"]))
            continue
        if fr == 0:
            mk = r["mistake"] or "unspecified"
            em = r["emotion"] or "unspecified"
            by_mistake[mk] += 1
            by_emotion[em] += 1
            recent.append(
                {
                    "scan_id": int(r["scan_id"]),
                    "ts": int(r["ts"] or 0),
                    "day": _day_key(int(r["ts"] or 0)),
                    "outcome": r["outcome"],
                    "mistake": mk,
                    "emotion": em,
                    "in_window": int(r["ts"] or 0) >= since_ts_ms,
                }
            )
    return {
        "eligible": discipline["eligible"],
        "journaled": discipline["journaled"],
        "missing_journals": discipline["missing_journals"],
        "missing_scan_ids": missing_ids,
        "violations": discipline["violations"],
        "compliance": discipline["compliance"],
        "compliance_bar": GRADUATION_CRITERIA["compliance"],
        "by_mistake": dict(by_mistake.most_common()),
        "by_emotion": dict(by_emotion.most_common()),
        "recent": recent[-12:],
        "in_window": sum(1 for r in recent if r["in_window"]),
        "source": discipline["source"],
    }


def missing_journals(db: SignalDB) -> dict:
    """The journal-first approval gate (W3.3): decided real trades still
    waiting for their journal answer.

    Same population and fail-closed semantics as
    :func:`brain.journal.graduation_discipline` (P12.14): decided, non-sim,
    canonical-live paper trades whose ``followed_rules`` is NULL. This never
    blocks *learning* (rejects, closes, skips are unaffected) — it only
    delays the next *commitment* until the last one has been processed.
    """
    rows = db.discipline_rows(source_key="")
    missing = [r for r in rows if r.get("followed_rules") is None]
    return {
        "missing": len(missing),
        "scan_ids": [int(r["scan_id"]) for r in missing][-10:],
        "trades": [
            {
                "scan_id": int(r["scan_id"]),
                "day": _day_key(int(r.get("ts") or 0)),
                "plan_type": r.get("plan_type"),
                "outcome": r.get("outcome"),
            }
            for r in missing
        ][-10:],
    }


def _graduation_tracker(db: SignalDB) -> list[dict]:
    """Per-setup evidence tracker — exactly what is still missing.

    Uses the canonical-live :func:`data.simulator.paper_progress` (P12.13)
    and names the gap in plain language. No threshold is moved; the targets
    are the stored progress payload's own targets and the unchanged bars of
    :data:`GRADUATION_CRITERIA`.
    """
    try:
        progress = paper_progress(db)
    except Exception:
        return []
    try:
        from data.simulator import primary_plan_types

        primary = set(primary_plan_types())
    except Exception:
        primary = set()
    bar_e = GRADUATION_CRITERIA["expectancy"]
    tracker = []
    for p in progress:
        is_primary = p["plan_type"] in primary or (p.get("paper_n") or 0) > 0
        if not is_primary:
            continue
        bt_n, bt_t = int(p.get("backtest_n") or 0), int(p.get("backtest_target") or 100)
        pp_n, pp_t = int(p.get("paper_n") or 0), int(p.get("paper_target") or 20)
        e_net = p.get("expectancy_net")
        missing: list[str] = []
        if bt_n < bt_t:
            missing.append(
                f"{bt_t - bt_n} more unique backtest samples ({bt_n}/{bt_t})"
            )
        if pp_n < pp_t:
            missing.append(f"{pp_t - pp_n} more real paper samples ({pp_n}/{pp_t})")
        if bt_n >= bt_t and pp_n >= pp_t and (e_net is None or e_net < bar_e):
            shown = "n/a" if e_net is None else f"{e_net:+.3f}R"
            missing.append(f"net expectancy {shown} < {bar_e:+.2f}R bar")
        tracker.append(
            {
                "plan_type": p["plan_type"],
                "primary": p["plan_type"] in primary,
                "backtest_n": bt_n,
                "backtest_target": bt_t,
                "backtest_pct": round(100.0 * min(bt_n, bt_t) / bt_t, 1),
                "paper_n": pp_n,
                "paper_target": pp_t,
                "paper_pct": round(100.0 * min(pp_n, pp_t) / pp_t, 1),
                "expectancy_net": e_net,
                "win_rate_net": p.get("win_rate_net"),
                "proven": bool(p.get("proven")),
                "missing": missing,
            }
        )
    tracker.sort(key=lambda r: (not r["primary"], r["plan_type"]))
    return tracker


def _next_task(review: dict) -> dict:
    """One practice task from the weakest link — deterministic, never tuned.

    Ordered like the desk itself: journals before new commitments, discipline
    before more samples, samples before expectancy. This is a coaching hint,
    not a rule — it changes no threshold and blocks nothing by itself.
    """
    v = review["violations"]
    week = review["week"]
    tracker = review["graduation_tracker"]
    if v["missing_journals"]:
        return {
            "name": "journal_first",
            "title": f"Journal {v['missing_journals']} unjournaled trade(s) before anything else",
            "detail": (
                "Every decided real trade needs its 'did you follow the "
                "system?' answer. Missing journals lower graduation "
                "compliance exactly like violations (P12.14) — and the "
                "journal-first gate (W3.3) will hold your next approval "
                "until this is done."
            ),
            "action": "unjournaled scans: "
            + ", ".join(f"#{s}" for s in v["missing_scan_ids"])
            if v["missing_scan_ids"]
            else "open the Journal tab",
        }
    if (
        v["compliance"] is not None
        and v["compliance"] < GRADUATION_CRITERIA["compliance"]
    ):
        top = next(iter(v["by_mistake"]), None)
        return {
            "name": "discipline",
            "title": f"Compliance {v['compliance'] * 100:.0f}% is below the 90% bar",
            "detail": (
                "You broke your own rules on "
                f"{v['violations']} decided trade(s)"
                + (f" — most repeated mistake: '{top}'." if top else ".")
                + " One bad habit repeated is the lesson for next week; "
                "size down until the journal is clean."
            ),
            "action": "review the violations card, then write one rule you will not break twice",
        }
    unproven = [t for t in tracker if t["primary"] and not t["proven"] and t["missing"]]
    if unproven:
        t = unproven[0]
        return {
            "name": "build_evidence",
            "title": f"Finish the {t['plan_type']} evidence",
            "detail": (
                "The graduation bar is earned setup by setup. "
                f"{t['plan_type']} still needs: " + "; ".join(t["missing"]) + "."
            ),
            "action": "run the Evidence pipeline for this setup, then keep the paper monitor on",
        }
    if week["n"] == 0:
        return {
            "name": "no_activity",
            "title": "No real paper decisions closed this week",
            "detail": (
                "The review is only honest when your own decisions are "
                "in it. Keep the paper monitor running, approve or "
                "reject real candidates, and journal every outcome."
            ),
            "action": "python main.py paper --watch",
        }
    if week["expectancy_net"] is not None and week["expectancy_net"] <= 0:
        return {
            "name": "protect_capital",
            "title": "Week closed below breakeven (net) — study, don't chase",
            "detail": (
                f"This week printed {week['expectancy_net']:+.3f}R net per trade. "
                "The losing R-multiples in the distribution are the "
                "teacher: replay them, find the shared mistake, and "
                "stand aside until you could explain what changes."
            ),
            "action": "open the R-distribution card and re-read the worst 3 trades in the Journal",
        }
    return {
        "name": "maintain",
        "title": "Keep doing the boring things — they are the edge",
        "detail": (
            "Discipline is holding above the bar and the book is net "
            "positive this week. The riskiest trade now is the "
            "overconfident one: keep risk per trade unchanged."
        ),
        "action": "python main.py daily — same ritual tomorrow",
    }


def _grade(review: dict) -> dict:
    """Deterministic advisory grade. Honest about what it is NOT: it is not
    the graduation bar, not a profitability promise, and it cannot open any
    gate. The components are visible so nobody has to trust the letter."""
    comps: list[dict] = []
    v = review["violations"]
    week = review["week"]
    score = 0
    # 1. compliance vs 90% bar (30%)
    c = v["compliance"]
    pts = (
        30
        if (c is not None and c >= GRADUATION_CRITERIA["compliance"])
        else (15 if (c is not None and c >= 0.75) else 0)
    )
    score += pts
    comps.append(
        {
            "name": "rule compliance ≥ 90%",
            "current": None if c is None else round(c * 100, 1),
            "points": pts,
            "max": 30,
        }
    )
    # 2. journals complete (20%)
    pts = (
        20
        if v["eligible"] and not v["missing_journals"]
        else (10 if v["eligible"] == 0 else max(0, 20 - 5 * v["missing_journals"]))
    )
    score += pts
    comps.append(
        {
            "name": "every decided trade journaled",
            "current": f"{v['journaled']}/{v['eligible']}",
            "points": pts,
            "max": 20,
        }
    )
    # 3. week activity (10%)
    pts = 10 if week["n"] >= 1 else 0
    score += pts
    comps.append(
        {
            "name": "≥1 real paper decision closed this week",
            "current": week["n"],
            "points": pts,
            "max": 10,
        }
    )
    # 4. week net expectancy > 0 (25%)
    e = week["expectancy_net"]
    pts = 25 if (e is not None and e > 0) else (12 if e == 0 else 0)
    score += pts
    comps.append(
        {"name": "week net expectancy > 0R", "current": e, "points": pts, "max": 25}
    )
    # 5. expectancy trend not degrading vs all-time (15%)
    all_e = review["all_time"]["expectancy_net"]
    pts = 15 if (e is None or all_e is None or e >= all_e) else 0
    score += pts
    comps.append(
        {
            "name": "week not below its all-time net expectancy",
            "current": None if e is None else f"{e:+.3f}R",
            "points": pts,
            "max": 15,
        }
    )
    grade = (
        "A"
        if score >= 85
        else "B"
        if score >= 70
        else "C"
        if score >= 50
        else "D"
        if score >= 30
        else "E"
    )
    if review["all_time"]["n"] == 0 and week["n"] == 0:
        grade = "—"
    return {
        "grade": grade,
        "score": score,
        "max": 100,
        "components": comps,
        "note": (
            "advisory self-review only — the unchanged graduation "
            "bar is the only authoritative gate; a good week is not "
            "a proven edge"
        ),
    }


def weekly_review(db: SignalDB, days: int = 7, now_ms: int | None = None) -> dict:
    """The weekly trader review over the canonical live paper book.

    ``days`` is the review window (default 7). ``now_ms`` injects "now" so
    tests are deterministic. Read-only; returns a JSON-safe dict.
    """
    days = max(1, int(days))
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    since_ts = now_ms - days * 86_400_000

    rows = db.live_book_rows()  # decided, non-sim, canonical live (P12.15)
    week_rows = [r for r in rows if int(r.get("closed_ts") or 0) >= since_ts]

    review: dict = {
        "window": {
            "days": days,
            "since_ts": since_ts,
            "until_ts": now_ms,
            "label": f"{_day_key(since_ts)} → {_day_key(now_ms)}",
        },
        "week": _book_stats(week_rows),
        "all_time": _book_stats(rows),
        "r_distribution": _r_distribution(rows),
        "r_distribution_week": _r_distribution(week_rows),
        "source": "canonical live book (simulator excluded, research books excluded)",
    }

    # Equity curve + drawdown — reuse the exact business-metrics computation
    # so the page can never disagree with the Risk center (invariant #10).
    from brain.metrics import business_metrics

    metrics = business_metrics(db)
    review["equity_curve"] = metrics.get("equity_curve") or []
    review["drawdown"] = (
        review.get("equity_curve")
        and {
            "max_drawdown_pct": (metrics.get("overall") or {}).get("max_drawdown_pct"),
            "final_equity": (metrics.get("overall") or {}).get("final_equity"),
        }
    ) or {"max_drawdown_pct": 0.0, "final_equity": 10_000.0}

    review["violations"] = _violations(db, since_ts)
    review["journal_gate"] = missing_journals(db)
    review["graduation_tracker"] = _graduation_tracker(db)
    review["next_practice_task"] = _next_task(review)
    review["grade"] = _grade(review)
    review["bar"] = {
        "expectancy": GRADUATION_CRITERIA["expectancy"],
        "win_rate": GRADUATION_CRITERIA["win_rate"],
        "pf": GRADUATION_CRITERIA["pf"],
        "compliance": GRADUATION_CRITERIA["compliance"],
        "note": "bars are unchanged and NET of costs; this review never moves them",
    }
    review["generated_ts"] = int(time.time())
    return review


def format_weekly_review(review: dict) -> str:
    """Boxed human report — the text twin of the Review tab (`main.py weekly`)."""
    w, a = review["week"], review["all_time"]
    v, g = review["violations"], review["grade"]
    bar = review["bar"]

    def _f(vv, fmt="{:+.3f}", suffix="R"):
        return (fmt.format(vv) + suffix) if isinstance(vv, (int, float)) else "n/a"

    lines = [
        "=" * 74,
        f"WEEKLY TRADER REVIEW — {review['window']['label']}  (grade {g['grade']}, {g['score']}/{g['max']})",
        "-" * 74,
        f"  this week      {w['n']} decided  ({w['wins']}W / {w['losses']}L)   "
        f"E {_f(w['expectancy_net'])} net  |  PF {_f(w['profit_factor'], '{:.2f}', '')}  |  "
        f"total {_f(w['total_r_net'])}",
        f"  all time       {a['n']} decided  ({a['wins']}W / {a['losses']}L)   "
        f"E {_f(a['expectancy_net'])} net  |  PF {_f(a['profit_factor'], '{:.2f}', '')}  |  "
        f"total {_f(a['total_r_net'])}",
        f"  graduation bar (unchanged, net): E ≥ {bar['expectancy']:+.2f}R · "
        f"WR > {bar['win_rate']:.0%} · PF ≥ {bar['pf']} · compliance ≥ {bar['compliance']:.0%}",
        "-" * 74,
    ]
    if w["n"] == 0 and a["n"] == 0:
        lines.append("  No decided real paper trades yet — approve candidates, let the")
        lines.append("  paper runner close them, and journal every outcome. This page")
        lines.append(
            "  fills in as your own decisions land. Simulator rows never count."
        )
    dd = review["drawdown"]
    lines.append(
        f"  drawdown       {dd.get('max_drawdown_pct', 0.0):.2f}% max   "
        f"final equity {dd.get('final_equity', 10_000.0):,.2f} (net, compounding)"
    )
    # R distribution (all time)
    if a["n"]:
        lines.append("  R distribution (all time, net):")
        widest = max(b["n"] for b in review["r_distribution"]) or 1
        for b in review["r_distribution"]:
            bars_n = int(round(24 * b["n"] / widest))
            lines.append(f"    {b['bucket']:<14} {'█' * bars_n or '·'} {b['n']}")
    # Discipline
    c = v["compliance"]
    lines += [
        "-" * 74,
        f"  discipline     {v['journaled']}/{v['eligible']} journaled · {v['violations']} violations · "
        f"compliance {_f(c * 100 if c is not None else None, '{:.1f}', '%')}"
        + (
            f" — {v['missing_journals']} missing journal(s): "
            + ", ".join(f"#{s}" for s in v["missing_scan_ids"])
            if v["missing_journals"]
            else ""
        ),
    ]
    if v["by_mistake"]:
        top = ", ".join(f"{k} ×{n}" for k, n in list(v["by_mistake"].items())[:4])
        lines.append(f"  mistakes       {top}")
    # Graduation tracker
    if review["graduation_tracker"]:
        lines.append("  graduation tracker (per setup, canonical live only):")
        for t in review["graduation_tracker"]:
            mark = (
                "✓ proven"
                if t["proven"]
                else "· " + ("; ".join(t["missing"]) or "watching")
            )
            lines.append(
                f"    {t['plan_type']:<26} bt {t['backtest_n']}/{t['backtest_target']}"
                f"  paper {t['paper_n']}/{t['paper_target']}  {mark}"
            )
    # Task + grade breakdown
    task = review["next_practice_task"]
    lines += [
        "-" * 74,
        f"  NEXT PRACTICE TASK → {task['title']}",
        f"     {task['detail']}",
        f"     → {task['action']}",
        "-" * 74,
        "  grade components (advisory):",
    ]
    for c_ in g["components"]:
        cur = c_["current"]
        lines.append(
            f"    [{c_['points']:>2}/{c_['max']:<2}] {c_['name']}"
            + (f"  ({cur})" if cur is not None else "")
        )
    lines.append(f"  {g['note']}")
    lines.append("=" * 74)
    return "\n".join(lines)
