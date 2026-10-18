"""cli/analytics.py — the evidence/analytics command cluster (scorecard/calendar/quality).

Refactor step 3 of the main.py maintainability debt (ROADMAP §19): the
scorecard, calendar and quality commands used to live inline in ``main.py``;
they live here now, byte-identical, and ``main`` re-exports them so the
argparse wiring keeps working unchanged.  Read-only analytics.
"""

from __future__ import annotations

import json
import sys
import time

from cli.common import _source_key_arg, _sym
from config import SYMBOL


def cmd_scorecard(args) -> int:
    """P12.3 & P12.6 — the single boxed strategy scorecard & net expectancy.

    Reads outcomes that already exist. ``--source db|backtest|paper`` reads
    what has been graded and stored; ``--source store`` runs one fresh
    walk-forward grade over the stored series and scores that. Evaluated
    NET of costs (fees, slip, funding) per P12.6.
    """
    from data.costs import CostModel
    from data.scorecard import print_scorecard, scorecard_from_db, scorecard_from_store

    cost_model = CostModel(
        execution_type="maker" if getattr(args, "maker", False) else "taker",
        enabled=not getattr(args, "no_costs", False),
    )
    conditioned = getattr(args, "conditioned", False)
    quality = getattr(args, "quality", False)

    if args.source == "store":
        horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
        report = scorecard_from_store(
            exchange=args.exchange,
            market=args.market,
            symbol=_sym(args.symbol or SYMBOL),
            timeframe=args.tf,
            bars=args.bars,
            horizons=horizons,
            min_bars=args.min_bars,
            step=args.step,
            min_confidence=args.min_conf,
            min_decided=args.min_decided,
            cost_model=cost_model,
            conditioned=conditioned,
            quality=quality,
        )
    else:
        from data.backfill import BackfillError, parse_ts

        now_ms = int(time.time() * 1000)
        try:
            since_ts = parse_ts(args.since, now_ms=now_ms) if args.since else None
            until_ts = parse_ts(args.until, now_ms=now_ms) if args.until else None
        except BackfillError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 2
        source = "all" if args.source == "db" else args.source
        report = scorecard_from_db(
            source_key=_source_key_arg(getattr(args, "source_key", None)),
            symbol=_sym(args.symbol) if args.symbol else None,
            source=source,
            min_decided=args.min_decided,
            include_sim=not args.exclude_sim,
            since_ts=since_ts,
            until_ts=until_ts,
            cost_model=cost_model,
            conditioned=conditioned,
            quality=quality,
            step=args.step,
        )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_scorecard(report)
    return 0 if report.get("ok") else 1


def cmd_calendar(args) -> int:
    """P12.9 — inspect a venue's trading calendar and its stored series.

    Crypto is 24/7 and unchanged; spot gold (Dukascopy XAUUSD) follows the
    OTC week, so scheduled closures stop being read as missing data. This
    command answers two operator questions offline: *is the venue open right
    now?* and *how much of a stored series' span was scheduled closure?*
    """
    from data.backfill import fmt_ts
    from data.calendar import (
        calendar_for,
        closed_bar_count,
        describe,
        expected_bars,
        get_calendar,
    )
    from data.gaps import step_ms

    symbol = _sym(args.symbol) if args.symbol else "XAUUSD"
    cal = (
        get_calendar(args.calendar)
        if args.calendar
        else calendar_for(args.exchange, args.market, symbol)
    )
    now_ms = args.at if args.at is not None else int(time.time() * 1000)

    payload = {
        "ok": True,
        "exchange": args.exchange,
        "market": args.market,
        "symbol": symbol,
        "timeframe": args.tf,
        "calendar": describe(cal),
        "at_ms": now_ms,
        "open_now": bool(cal.is_open(now_ms)),
    }

    if args.series:
        from data.quality import series_health, verdict_for
        from data.store import CandleStore

        store = CandleStore(root=args.root) if args.root else CandleStore()
        health = series_health(
            store,
            args.exchange,
            args.market,
            symbol,
            args.tf,
            now_ms=now_ms,
            calendar=cal,
        )
        verdict = verdict_for(health)
        step = step_ms(args.tf)
        first, last = health.get("first_ts"), health.get("last_ts")
        payload["series"] = {
            "candles": health["candles"],
            "first_ts": first,
            "last_ts": last,
            "expected_open_bars": (
                expected_bars(first, last, step, cal) if first is not None else 0
            ),
            "closed_session_bars": (
                closed_bar_count(first, last, step, cal) if first is not None else 0
            ),
            "missing": health["missing"],
            "gap_fraction": health["gap_fraction"],
            "age_bars": health["age_mult"],
            "level": verdict["level"],
            "headline": verdict["headline"],
            "detail": verdict["detail"],
        }

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    name = payload["calendar"]["name"]
    print(f"calendar    {name}{'  (always open)' if payload['calendar']['always_open'] else ''}")
    print(f"  series    {args.exchange}/{args.market}/{symbol}/{args.tf}")
    print(f"  at        {fmt_ts(now_ms)} UTC")
    print(f"  open now  {'YES' if payload['open_now'] else 'no — venue shut'}")
    ser = payload.get("series")
    if ser:
        print(
            f"  stored    {ser['candles']:,} candles  "
            f"expected-open {ser['expected_open_bars']:,}  "
            f"closed-session {ser['closed_session_bars']:,}"
        )
        print(
            f"  missing   {ser['missing']:,} "
            f"({ser['gap_fraction']:.2%})  age {ser['age_bars']} bars"
        )
        print(f"  verdict   {ser['level']} — {ser['headline']}")
        if ser["detail"]:
            print(f"            {ser['detail']}")
    return 0


def cmd_quality(args) -> int:
    """P12.4 — Backtest Quality Score 0–100 with the parameter-plateau sweep.

    Re-grades the stored series at every point of a strategy-parameter
    neighbourhood (min_confidence ± 5 by default — the engine gate that
    decides which plans exist) and scores the base book against that
    evidence. A setup that only wins at one isolated parameter point is
    capped at 50/100: an isolated peak is a fit, not an edge (BT5).
    Store-only, exactly like the locked P12.1 protocol.
    """
    from data.costs import CostModel
    from data.quality_score import print_quality, run_quality_sweep

    cost_model = CostModel(
        execution_type="maker" if getattr(args, "maker", False) else "taker",
        enabled=not getattr(args, "no_costs", False),
    )
    horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
    report = run_quality_sweep(
        exchange=args.exchange,
        market=args.market,
        symbol=_sym(args.symbol or SYMBOL),
        timeframe=args.tf,
        bars=args.bars,
        horizons=horizons,
        min_bars=args.min_bars,
        step=args.step,
        min_confidence=args.min_conf,
        min_decided=args.min_decided,
        cost_model=cost_model,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_quality(report)
    return 0 if report.get("ok") else 1
