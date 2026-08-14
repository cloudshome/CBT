"""data/scorecard.py — P12.3: the single boxed strategy scorecard.

One command, one block.  This is a **report layer**, not a second grader:
it reads outcomes that already exist (graded plans from `data/backtester.py`,
`backtest_results` and decided `paper_trades` from `data/database.py`) and
prints the numbers a discretionary desk actually needs before it risks money:

  * expectancy R, win rate, profit factor, total R
  * risk-adjusted: Sharpe / Sortino / Calmar (trade-level, documented below)
  * max drawdown in R, longest win/loss streak
  * holding time (hours) — how long the money is exposed
  * the same block split by **side** (long/short), **regime**, **session**
    and **setup**

Design rules (deliberate, do not "improve" away):

  * No new math engine and no new dependency — the R values are the ones the
    existing grader produced (BUY R = (exit-entry)/risk,
    SELL R = (entry-exit)/risk).
  * No second grader.  `data/backtester.py` stays the only thing that decides
    WIN / LOSS.  This file never touches OHLCV.
  * The pass/fail bar is the existing graduation bar, imported from
    `data.validation` (which imports it from `data.simulator`).  It is not
    redefined and not loosened here.
  * Every metric degrades to ``None`` rather than to a guess when the sample
    cannot support it.  Silence is not an edge.

Risk-adjusted metrics are **per decided trade**, not annualised returns:

  Sharpe   = mean(R) / stdev(R)                 (sample stdev, ddof=1)
  Sortino  = mean(R) / sqrt(mean(min(R,0)^2))   (downside deviation about 0)
  Calmar   = total R / max drawdown R           (both in R units)

These are deliberately **not** annualised.  A walk-forward grade steps through
history every few bars, so its "trades" overlap heavily; multiplying by
sqrt(trades per year) would turn a Sharpe of 0.27 into a Sharpe of 36 and that
number would be a lie.  The sample span and trades-per-day are reported as
plain context instead, so the reader can judge frequency themselves.
"""
from __future__ import annotations

import math
import statistics
import time
from typing import Iterable, Optional

from config import GOLD_LONDON_WINDOW, GOLD_NY_WINDOW
from data.backtester import WIN_SET
from data.validation import DEFAULT_MIN_DECIDED, VALIDATION_CRITERIA, meets_bar

DECIDED_BACKTEST = set(WIN_SET) | {"LOSS"}
DECIDED_PAPER = {"TP_HIT", "STOP_LOSS"}

# Session buckets in UTC hours.  Derived from the gold playbook windows in
# config (GOLD_LONDON_WINDOW=(7,16), GOLD_NY_WINDOW=(12,21)) so the desk reads
# one definition of "London" everywhere.  The London/NY overlap is attributed
# to New York (that is where the volume prints), and everything outside both
# windows is the Asia / off-window bucket.
SESSION_ASIA = "asia"
SESSION_LONDON = "london"
SESSION_NEWYORK = "newyork"
SESSION_NAMES = (SESSION_ASIA, SESSION_LONDON, SESSION_NEWYORK)
SESSION_LABELS = {
    SESSION_ASIA: f"Asia / off-window (outside {GOLD_LONDON_WINDOW[0]:02d}:00–"
                  f"{GOLD_NY_WINDOW[1]:02d}:00 UTC)",
    SESSION_LONDON: f"London ({GOLD_LONDON_WINDOW[0]:02d}:00–"
                    f"{GOLD_NY_WINDOW[0]:02d}:00 UTC)",
    SESSION_NEWYORK: f"New York ({GOLD_NY_WINDOW[0]:02d}:00–"
                     f"{GOLD_NY_WINDOW[1]:02d}:00 UTC)",
}

MS_PER_HOUR = 3_600_000
SIDES = ("BUY", "SELL")


# ──────────────────────────────────────────────────────────────────────────
# Session bucketing
# ──────────────────────────────────────────────────────────────────────────
def session_of_hour(hour: int) -> str:
    """UTC hour → session bucket (overlap counted as New York)."""
    hour = int(hour) % 24
    if GOLD_NY_WINDOW[0] <= hour < GOLD_NY_WINDOW[1]:
        return SESSION_NEWYORK
    if GOLD_LONDON_WINDOW[0] <= hour < GOLD_NY_WINDOW[0]:
        return SESSION_LONDON
    return SESSION_ASIA


def session_of_ts(ts_ms: Optional[int]) -> Optional[str]:
    """Epoch-milliseconds → session bucket; ``None`` when there is no clock."""
    if ts_ms is None:
        return None
    try:
        hour = int((int(ts_ms) // MS_PER_HOUR) % 24)
    except (TypeError, ValueError):
        return None
    return session_of_hour(hour)


# ──────────────────────────────────────────────────────────────────────────
# Row adapters — every source is flattened to one honest row shape
# ──────────────────────────────────────────────────────────────────────────
def _row(ts, side, setup, regime, r, outcome, holding_hours,
         symbol="", timeframe="", source="") -> dict:
    return {
        "ts": int(ts) if ts is not None else None,
        "side": (side or "?").upper(),
        "setup": setup or "?",
        "regime": regime or "UNKNOWN",
        "r": float(r),
        "outcome": outcome or "",
        "holding_hours": (round(float(holding_hours), 3)
                          if holding_hours is not None else None),
        "symbol": symbol or "",
        "timeframe": timeframe or "",
        "source": source,
        "session": session_of_ts(ts),
    }


def rows_from_graded(graded: Iterable, symbol: str = "", timeframe: str = "",
                     horizon_hours: Optional[float] = None) -> list[dict]:
    """Decided rows from in-memory `GradedPlan` objects (the grader's output).

    ``horizon_hours`` filters to one horizon so a multi-horizon backtest is
    not counted three times.  Defaults to the shortest horizon present.
    """
    graded = list(graded)
    if horizon_hours is None:
        horizons = {g.horizon_hours for g in graded}
        horizon_hours = min(horizons) if horizons else None
    rows = []
    for g in graded:
        if horizon_hours is not None and g.horizon_hours != horizon_hours:
            continue
        if g.outcome not in DECIDED_BACKTEST:
            continue
        rows.append(_row(g.ts, g.action, g.plan_type, g.regime, g.rr_achieved,
                         g.outcome, getattr(g, "holding_hours", None),
                         symbol, timeframe, "backtest"))
    rows.sort(key=lambda r: (r["ts"] is None, r["ts"]))
    return rows


def rows_from_backtest_db(db, symbol: Optional[str] = None,
                          include_sim: bool = True,
                          since_ts: Optional[int] = None,
                          until_ts: Optional[int] = None) -> list[dict]:
    """Decided rows from the stored `backtest_results` table.

    ``since_ts`` / ``until_ts`` bound the signal bar (inclusive) so one
    book can hold several data eras (e.g. the old synthetic samples vs.
    the P12.3.2 real-market rows) without mixing them.
    """
    q = ("SELECT ts, symbol, timeframe, plan_type, action, outcome, "
         "rr_achieved, regime, holding_hours, horizon_hours "
         "FROM backtest_results WHERE outcome IN "
         f"({','.join('?' * len(DECIDED_BACKTEST))})")
    args: list = sorted(DECIDED_BACKTEST)
    if symbol:
        q += " AND symbol=?"
        args.append(symbol)
    if since_ts is not None:
        q += " AND ts>=?"
        args.append(int(since_ts))
    if until_ts is not None:
        q += " AND ts<=?"
        args.append(int(until_ts))
    if not include_sim:
        q += " AND sim_key IS NULL"
    q += " ORDER BY ts ASC"
    out = []
    for r in db.conn.execute(q, args).fetchall():
        d = dict(r)
        out.append(_row(d.get("ts"), d.get("action"), d.get("plan_type"),
                        d.get("regime"), d.get("rr_achieved") or 0.0,
                        d.get("outcome"), d.get("holding_hours"),
                        d.get("symbol"), d.get("timeframe"), "backtest"))
    return out


def rows_from_paper_db(db, symbol: Optional[str] = None,
                       include_sim: bool = False,
                       since_ts: Optional[int] = None) -> list[dict]:
    """Decided rows from the real paper book (TP_HIT / STOP_LOSS).

    Holding time here is measured, not assumed: ``closed_ts - opened_ts``.
    ``since_ts`` bounds ``closed_ts`` (the same era-separation the
    backtest book uses, on the column paper trades actually close on).
    """
    rows = db.decided_paper_rows(symbol=symbol, exclude_sim=not include_sim,
                                 since_ts=since_ts)
    out = []
    for d in rows:
        opened = d.get("opened_ts")
        closed = d.get("closed_ts")
        hold = None
        if opened and closed and closed >= opened:
            hold = (closed - opened) / MS_PER_HOUR
        ts = closed or opened or d.get("created_ts")
        out.append(_row(ts, d.get("action"), d.get("plan_type"),
                        d.get("regime"), d.get("rr_achieved") or 0.0,
                        d.get("outcome"), hold, d.get("symbol"),
                        d.get("timeframe"), "paper"))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Metrics — one block, computed the same way for every split
# ──────────────────────────────────────────────────────────────────────────
def _empty_stats() -> dict:
    return {"n": 0, "wins": 0, "losses": 0, "win_rate": None,
            "expectancy": 0.0, "avg_win_r": None, "avg_loss_r": None,
            "pf": None, "total_r": 0.0, "max_drawdown_r": 0.0,
            "sharpe": None, "sortino": None, "calmar": None,
            "stdev_r": None, "best_r": None, "worst_r": None,
            "max_win_streak": 0, "max_loss_streak": 0,
            "avg_holding_hours": None, "median_holding_hours": None,
            "holding_samples": 0, "decided": 0}


def max_drawdown_r(r_values: list[float]) -> float:
    """Peak-to-trough drawdown of the cumulative R curve, in R units."""
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for r in r_values:
        equity += r
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(abs(worst), 3)


def _streaks(r_values: list[float]) -> tuple[int, int]:
    cur_w = cur_l = max_w = max_l = 0
    for r in r_values:
        if r > 0:
            cur_w += 1
            cur_l = 0
            max_w = max(max_w, cur_w)
        elif r < 0:
            cur_l += 1
            cur_w = 0
            max_l = max(max_l, cur_l)
    return max_w, max_l


def trade_stats(rows: list[dict]) -> dict:
    """The scorecard block for one set of decided trades."""
    if not rows:
        return _empty_stats()
    rows = sorted(rows, key=lambda r: (r["ts"] is None, r["ts"]))
    r_values = [float(r["r"]) for r in rows]
    n = len(r_values)
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (round(gross_win / gross_loss, 3) if gross_loss > 0
          else (99.0 if gross_win > 0 else None))
    mean_r = sum(r_values) / n
    stdev = statistics.stdev(r_values) if n > 1 else None
    sharpe = (round(mean_r / stdev, 3) if stdev else None)
    # Downside deviation about a 0R target — the textbook Sortino denominator.
    # (Using the stdev of the losing trades instead would report "n/a" for any
    # book whose losses are all a clean -1R, which is most of them.)
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in r_values) / n)
    sortino = (round(mean_r / downside, 3) if downside > 0 else None)
    dd = max_drawdown_r(r_values)
    total_r = round(sum(r_values), 3)
    calmar = round(total_r / dd, 3) if dd > 0 else None
    max_w, max_l = _streaks(r_values)
    holds = [r["holding_hours"] for r in rows if r.get("holding_hours") is not None]

    return {
        "n": n,
        "decided": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 3),
        "expectancy": round(mean_r, 3),
        "avg_win_r": round(gross_win / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
        "pf": pf,
        "total_r": total_r,
        "max_drawdown_r": dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "stdev_r": round(stdev, 3) if stdev is not None else None,
        "best_r": round(max(r_values), 3),
        "worst_r": round(min(r_values), 3),
        "max_win_streak": max_w,
        "max_loss_streak": max_l,
        "avg_holding_hours": round(sum(holds) / len(holds), 2) if holds else None,
        "median_holding_hours": (round(statistics.median(holds), 2)
                                 if holds else None),
        "holding_samples": len(holds),
    }


def _span(rows: list[dict]) -> dict:
    """Sample span and trade frequency — context, not a risk metric."""
    ts = [r["ts"] for r in rows if r.get("ts")]
    if len(ts) < 2:
        return {}
    span_ms = max(ts) - min(ts)
    if span_ms <= 0:
        return {}
    days = span_ms / (24 * MS_PER_HOUR)
    return {"span_days": round(days, 1),
            "trades_per_day": round(len(ts) / days, 2) if days else None}


def _split(rows: list[dict], key: str, order: Optional[tuple] = None) -> dict:
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        k = r.get(key) or "UNKNOWN"
        buckets.setdefault(str(k), []).append(r)
    keys = list(order) if order else sorted(buckets,
                                            key=lambda k: -len(buckets[k]))
    return {k: trade_stats(buckets.get(k, [])) for k in keys
            if order or buckets.get(k)}


# ──────────────────────────────────────────────────────────────────────────
# The scorecard
# ──────────────────────────────────────────────────────────────────────────
def build_scorecard(rows: list[dict], *, symbol: str = "", timeframe: str = "",
                    source: str = "", min_decided: int = DEFAULT_MIN_DECIDED,
                    criteria: Optional[dict] = None,
                    note: str = "") -> dict:
    """Assemble the boxed report from already-graded rows.

    Pure: same rows in → same report out.  Never raises on an empty sample;
    an empty book is reported as INSUFFICIENT_DATA, which is the truth.
    """
    criteria = criteria or VALIDATION_CRITERIA
    rows = [r for r in rows if r.get("r") is not None]
    overall = trade_stats(rows)
    overall.update(_span(rows))

    bar_met, bar_unmet = meets_bar(overall, min_decided=min_decided,
                                   criteria=criteria)
    if overall["n"] < min_decided:
        status = "INSUFFICIENT_DATA"
        reason = (f"{overall['n']} decided trades < min {min_decided} — "
                  f"not enough evidence to judge the edge")
    elif bar_met:
        status = "PASS"
        reason = (f"expectancy {overall['expectancy']:+.3f}R, "
                  f"WR {overall['win_rate']:.1%}, PF {overall['pf']} — "
                  f"clears the graduation bar")
    else:
        status = "FAIL"
        reason = "; ".join(bar_unmet) or "below the graduation bar"

    symbols = sorted({r["symbol"] for r in rows if r.get("symbol")})
    sources = sorted({r["source"] for r in rows if r.get("source")})

    return {
        "ok": True,
        "meta": {
            "symbol": symbol or (symbols[0] if len(symbols) == 1 else "ALL"),
            "symbols": symbols,
            "timeframe": timeframe,
            "source": source or "+".join(sources),
            "sources": sources,
            "rows": len(rows),
            "min_decided": min_decided,
            "generated_ts": int(time.time() * 1000),
            "note": note,
            "first_ts": min((r["ts"] for r in rows if r.get("ts")), default=None),
            "last_ts": max((r["ts"] for r in rows if r.get("ts")), default=None),
        },
        "overall": overall,
        "by_side": _split(rows, "side", order=SIDES),
        "by_regime": _split(rows, "regime"),
        "by_session": _split(rows, "session", order=SESSION_NAMES),
        "by_setup": _split(rows, "setup"),
        "criteria": dict(criteria),
        "bar": {"met": bool(bar_met), "unmet": bar_unmet,
                "min_decided": min_decided},
        "verdict": {"status": status, "reason": reason},
    }


def scorecard_from_db(symbol: Optional[str] = None, source: str = "all",
                      min_decided: int = DEFAULT_MIN_DECIDED,
                      include_sim: bool = True, db=None,
                      since_ts: Optional[int] = None,
                      until_ts: Optional[int] = None) -> dict:
    """Scorecard over what the desk has already graded and stored.

    ``source``: ``backtest`` | ``paper`` | ``all`` (both books combined).
    Paper trades exclude simulator samples unless ``include_sim`` — the live
    book and the walk-forward evidence are not the same thing.
    ``since_ts`` / ``until_ts`` bound the signal bar for era-separated runs.
    """
    if source not in ("backtest", "paper", "all"):
        return {"ok": False,
                "error": f"unknown source {source!r} (backtest|paper|all)"}

    from data.database import SignalDB
    owned = db is None
    db = db or SignalDB()
    try:
        rows: list[dict] = []
        if source in ("backtest", "all"):
            rows += rows_from_backtest_db(db, symbol=symbol,
                                          include_sim=include_sim,
                                          since_ts=since_ts, until_ts=until_ts)
        if source in ("paper", "all"):
            rows += rows_from_paper_db(db, symbol=symbol,
                                       include_sim=include_sim,
                                       since_ts=since_ts)
    finally:
        if owned:
            db.close()

    if not rows:
        return {"ok": False,
                "error": ("No decided outcomes stored yet — run "
                          "`python main.py backtest --save` (or the paper "
                          "runner) first, then re-run the scorecard."),
                "source": source, "rows": 0}
    return build_scorecard(rows, symbol=symbol or "", source=source,
                           min_decided=min_decided,
                           note="stored outcomes (no re-grading)")


def scorecard_from_store(exchange: str = "binance", market: str = "perp",
                         symbol: str = "BTCUSDT", timeframe: str = "15m",
                         bars: int = 1000, horizons: Optional[list] = None,
                         min_bars: Optional[int] = None,
                         step: int = 3, min_confidence: Optional[int] = None,
                         min_decided: int = DEFAULT_MIN_DECIDED) -> dict:
    """Scorecard over a fresh walk-forward grade of the stored series.

    Delegates every grading decision to `data.backtester.run_backtest_on_store`
    — this function only summarises what that grader returned.
    """
    from config import BACKTEST_MIN_BARS, MIN_CONFIDENCE
    from data.backtester import run_backtest_on_store

    result = run_backtest_on_store(
        exchange=exchange, market=market, symbol=symbol, timeframe=timeframe,
        bars=bars, horizons=horizons,
        min_bars=BACKTEST_MIN_BARS if min_bars is None else min_bars,
        step=step,
        min_confidence=MIN_CONFIDENCE if min_confidence is None else min_confidence)
    if not result.get("ok", True) or result.get("error"):
        return {"ok": False, "error": result.get("error", "backtest failed"),
                "source": "store"}

    primary = (result.get("report", {}).get("meta", {})
               .get("horizons_hours") or [None])[0]
    rows = rows_from_graded(result.get("graded", []), symbol=symbol,
                            timeframe=timeframe)
    if not rows:
        return {"ok": False,
                "error": (f"Graded {len(result.get('graded', []))} plans but "
                          f"none reached a decision (all OPEN or "
                          f"NOT_TRIGGERED) — widen --bars or --horizons."),
                "source": "store"}
    card = build_scorecard(rows, symbol=symbol, timeframe=timeframe,
                           source="store", min_decided=min_decided,
                           note=f"fresh walk-forward grade, primary horizon "
                                f"{primary}h")
    card["meta"]["bars_read"] = result.get("bars_read")
    card["meta"]["store_path"] = result.get("store_path")
    card["meta"]["primary_horizon_hours"] = primary
    return card


# ──────────────────────────────────────────────────────────────────────────
# Boxed printer — one command, one block
# ──────────────────────────────────────────────────────────────────────────
W = 78


def _fmt_pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "n/a"


def _fmt(v, spec: str = "+.3f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) else "n/a"


def _fmt_hours(v) -> str:
    return f"{v:.1f}h" if isinstance(v, (int, float)) else "n/a"


def _split_line(label: str, s: dict) -> str:
    pf = str(s["pf"]) if s["pf"] is not None else "n/a"
    hold = _fmt_hours(s["avg_holding_hours"])
    return (f"  {label:<18} {s['n']:>5} {_fmt_pct(s['win_rate']):>7} "
            f"{_fmt(s['expectancy']):>8} {pf:>7} "
            f"{_fmt(s['total_r'], '+.1f'):>8} {hold:>8}")


def _split_header(title: str) -> str:
    return (f"{title}\n"
            f"  {'':<18} {'n':>5} {'WR':>7} {'E':>8} {'PF':>7} {'totR':>8} "
            f"{'hold':>8}")


def print_scorecard(report: dict) -> None:
    """The boxed block.  Everything a review needs, nothing it does not."""
    if not report.get("ok"):
        print("STRATEGY SCORECARD — cannot run")
        print(f"  {report.get('error', 'unknown error')}")
        return

    m, o = report["meta"], report["overall"]
    print("=" * W)
    print(f"STRATEGY SCORECARD  {m['symbol']}"
          f"{' ' + m['timeframe'] if m['timeframe'] else ''}"
          f"   source: {m['source']}")
    span = ""
    if m.get("span_days") or o.get("span_days"):
        span = f"   span {o.get('span_days')}d"
    print(f"decided trades {o['n']}   min_decided {m['min_decided']}{span}"
          f"{'   ' + m['note'] if m.get('note') else ''}")
    print("-" * W)
    print(f"  expectancy   {_fmt(o['expectancy'])}R      "
          f"win rate  {_fmt_pct(o['win_rate'])} "
          f"({o['wins']}W/{o['losses']}L)")
    print(f"  profit factor {(str(o['pf']) if o['pf'] is not None else 'n/a'):<9}  "
          f"total R   {_fmt(o['total_r'], '+.2f')}R")
    print(f"  avg win      {_fmt(o['avg_win_r'])}R      "
          f"avg loss  {_fmt(o['avg_loss_r'])}R")
    print(f"  max drawdown {o['max_drawdown_r']:.2f}R      "
          f"streaks   {o['max_win_streak']}W / {o['max_loss_streak']}L")
    sharpe_extra = (f"   ({o['trades_per_day']} trades/day — per-trade, "
                    f"NOT annualised)"
                    if o.get("trades_per_day") is not None else
                    "   (per-trade, not annualised)")
    print(f"  Sharpe {(str(o['sharpe']) if o['sharpe'] is not None else 'n/a'):<7} "
          f"Sortino {(str(o['sortino']) if o['sortino'] is not None else 'n/a'):<7} "
          f"Calmar {(str(o['calmar']) if o['calmar'] is not None else 'n/a'):<7}"
          f"{sharpe_extra}")
    hold = o.get("avg_holding_hours")
    if hold is not None:
        print(f"  holding time avg {hold:.1f}h   median "
              f"{o['median_holding_hours']:.1f}h   "
              f"({o['holding_samples']}/{o['n']} trades timed)")
    else:
        print("  holding time n/a — these outcomes were graded before "
              "holding time was recorded")
    print("-" * W)
    print(_split_header("by side (long / short):"))
    for side in SIDES:
        s = report["by_side"].get(side)
        if s:
            print(_split_line(side, s))
    print(_split_header("by regime:"))
    for name, s in report["by_regime"].items():
        print(_split_line(name[:18], s))
    print(_split_header("by session (UTC):"))
    for name in SESSION_NAMES:
        s = report["by_session"].get(name)
        if s:
            print(_split_line(name, s))
    print(_split_header("by setup:"))
    for name, s in report["by_setup"].items():
        print(_split_line(name[:18], s))
    print("-" * W)
    c = report["criteria"]
    v = report["verdict"]
    icon = {"PASS": "🟢", "FAIL": "🔴", "INSUFFICIENT_DATA": "⚪"}.get(
        v["status"], "❓")
    print(f"bar: expectancy >= {c['expectancy']:+.2f}R   "
          f"win rate > {c['win_rate']:.0%}   PF >= {c['pf']}   "
          f"decided >= {report['bar']['min_decided']}")
    print(f"VERDICT  {icon} {v['status']}  —  {v['reason']}")
    if v["status"] != "PASS":
        print("  This is a scorecard, not permission. The graduation bar is "
              "unchanged.")
    print("=" * W)
