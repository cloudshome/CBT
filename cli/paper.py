"""cli/paper.py — the review + paper-trading command cluster.

Refactor step 3 of the main.py maintainability debt (ROADMAP §19): the human
review loop (review/approve/reject/execute/close) and the paper-trading
commands (paper/simulator) used to live inline in ``main.py``; they live here
now, byte-identical, and ``main`` re-exports them so the argparse wiring
keeps working unchanged.  Still paper-only — no exchange order path.
"""
from __future__ import annotations

import json
import time
import sys

from cli.common import _client, _sym, _symbols


def _print_review_row(r: dict) -> None:
    print(f"  #{r['id']:<5} {r['symbol']:<10} {r['timeframe']:<4} {r['action']:<5} "
          f"conf={r['confidence_label']:<7} entry={r['entry']}  "
          f"plans={r['n_plans']}  {r['reason'][:60]}")


def cmd_review(args) -> int:
    from data.database import SignalDB
    with SignalDB() as db:
        rows = db.pending_reviews(_sym(args.symbol) if args.symbol else None)
    print(f"Pending human approval: {len(rows)}")
    for r in rows:
        _print_review_row(r)
    print("\nApprove:  python main.py approve <id> [--note ...]")
    print("Reject:   python main.py reject <id> [--note ...]")
    print("Details:  python main.py signal <id>")
    return 0


def _decide(args, to_state: str) -> int:
    from data.database import SignalDB
    from engine.lifecycle import LifecycleError
    with SignalDB() as db:
        try:
            new = db.update_status(args.scan_id, to_state, note=args.note or "")
        except LifecycleError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if new is None:
            print(f"[!] scan #{args.scan_id} not found", file=sys.stderr)
            return 1
        sig = db.get_scan(args.scan_id)
    print(f"scan #{args.scan_id} → {new}  ({sig['symbol']} {sig['action']} "
          f"{sig['entry']})  note: {args.note or '—'}")
    return 0


def cmd_approve(args) -> int:
    """Human approval — but the risk & discipline gate is ENFORCED here
    (decisions B6/B7/B9/B10).  `--force` is the explicit escape hatch."""
    from data.database import SignalDB
    from brain.risk_gate import evaluate as gate_evaluate, gate_message
    from brain.coach import management_checklist
    from data.paper_trading import _primary_plan
    from brain.weekly import missing_journals
    with SignalDB() as db:
        scan = db.get_scan(args.scan_id)
        if scan is None:
            print(f"[!] scan #{args.scan_id} not found", file=sys.stderr)
            return 1
        plan = _primary_plan(scan)
        plan_type = plan.get("type")
        gate = gate_evaluate(db, symbol=scan.get("symbol"), plan_type=plan_type,
                             action=scan.get("action"))
        journal_gate = missing_journals(db)
    if not gate["allowed"] and not args.force:
        print("[!] Approval blocked by the risk & discipline gate.", file=sys.stderr)
        for b in gate["blocked_by"]:
            print(f"    ✗ {b}", file=sys.stderr)
        print("    (re-run with --force to override consciously)", file=sys.stderr)
        return 2
    # W3.3 journal-first discipline: a decided real trade without its
    # journal answer means the last commitment was never processed — the
    # next one waits. P12.14 already counts every missing journal against
    # the graduation 90% compliance bar; this is the trainer-side prompt.
    # Strictly tighter only on the human. Never loosens the risk gate.
    if journal_gate["missing"] and not getattr(args, "acknowledge_journal", False):
        print("[!] Approve held — journal-first discipline (W3.3).", file=sys.stderr)
        print(f"    {journal_gate['missing']} decided real trade(s) still have no "
              f"journal answer:", file=sys.stderr)
        for t in journal_gate["trades"]:
            print(f"    ✗ scan #{t['scan_id']}  {t['day']}  {t['plan_type']}  {t['outcome']}",
                  file=sys.stderr)
        print("    Journal them first:  python main.py journal <scan_id> --followed-rules 1",
              file=sys.stderr)
        print("    or re-run with --acknowledge-journal to commit consciously (audited).",
              file=sys.stderr)
        return 2
    # P13: position-manager card — see how the trade will be managed
    # (HOLD / REDUCE / TRAIL / EXIT) BEFORE you commit to it.
    print("   📋 POSITION MANAGER — how this trade will be managed:")
    for c in management_checklist(plan):
        print(f"      {c}")
    rc = _decide(args, "APPROVED")
    if rc == 0 and not gate["allowed"]:
        print(f"    ⚠️ overridden with --force: {gate_message(gate)}")
    return rc


def cmd_reject(args) -> int:
    return _decide(args, "REJECTED")


def cmd_execute(args) -> int:
    return _decide(args, "EXECUTED")


def cmd_close(args) -> int:
    return _decide(args, "CLOSED")


def _print_paper_run(result: dict) -> None:
    """Human-readable summary for one safe paper-monitoring pass."""
    print("=" * 72)
    print("PAPER TRADING RUNNER — public market data only; no exchange orders")
    print(f"  enrolled {result.get('enrolled', 0)} | checked {result.get('checked', 0)} | "
          f"entries {result.get('opened', 0)} | closed {result.get('closed', 0)} | "
          f"cancelled {result.get('cancelled', 0)}")
    for event in result.get("events", []):
        extra = event.get("reason", "")
        if event.get("outcome"):
            extra = f"{event['outcome']} {event.get('rr_achieved', 0):+.2f}R — {extra}"
        if event.get("price") is not None:
            extra = f"@ {event['price']:,.8g} — {extra}"
        print(f"  #{event.get('trade_id', '?'):<4} {event.get('symbol', '?'):<10} "
              f"{event.get('action', '?'):<4} {event.get('event', '?'):<14} {extra}")
    for error in result.get("errors", []):
        print(f"  [!] {error.get('symbol', 'paper')} #{error.get('trade_id', error.get('scan_id', '?'))}: "
              f"{error.get('error')}", file=sys.stderr)


def cmd_paper(args) -> int:
    """Run the approved-signal paper monitor once, or keep it running."""
    from data.database import SignalDB
    from data.paper_trading import PaperTradingRunner

    client = _client()
    symbol = _sym(args.symbol) if args.symbol else None

    def one_pass() -> dict:
        with SignalDB() as db:
            runner = PaperTradingRunner(db=db, client=client)
            return runner.run_once(symbol=symbol, enroll=not args.no_enroll).as_dict()

    if args.watch:
        # Unattended monitoring fails closed.  Demo data can be used only when
        # the operator explicitly labels the run as a rehearsal.
        from brain.preflight import format_preflight, preflight_report
        preflight = preflight_report(allow_demo=bool(getattr(args, "allow_demo", False)))
        if args.json:
            print(json.dumps({"event": "preflight", **preflight}, default=str))
        else:
            print(format_preflight(preflight))
        if not preflight["ready"]:
            print("[!] paper watcher not started: preflight failed", file=sys.stderr)
            return 2

        print(f"Paper runner watching {symbol or 'all approved symbols'} every "
              f"{args.interval}s — Ctrl+C to stop")
        try:
            while True:
                try:
                    result = one_pass()
                    if args.json:
                        print(json.dumps(result, default=str))
                    else:
                        _print_paper_run(result)
                except Exception as exc:  # keep unattended paper monitoring alive
                    print(f"[!] paper runner pass failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                time.sleep(max(10, args.interval))
        except KeyboardInterrupt:
            print("\nPaper runner stopped.")
        return 0

    try:
        result = one_pass()
    except Exception as exc:
        print(f"[!] paper runner failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_paper_run(result)
        from data.database import SignalDB
        with SignalDB() as db:
            stats = db.paper_trade_stats(symbol)["overall"]
        print(f"  total paper trades {stats['n']} | waiting {stats.get('waiting', 0)} | "
              f"open {stats.get('open', 0)} | wins/losses {stats['wins']}/{stats['losses']} | "
              f"avg R {stats['avg_rr']}")
        # P12.16 — say how much of that open count is the live book when the
        # store also holds simulator samples or research-book positions.
        _active = (stats.get("waiting", 0) or 0) + (stats.get("open", 0) or 0)
        if _active != stats.get("live_open", _active):
            print(f"  live open positions {stats['live_open']} "
                  f"(of {_active} active rows — the rest are simulator/research)")
    return 0


def cmd_simulator(args) -> int:
    """The paper-sample grind: unique backtest + paper samples per setup.

    ``--source store`` walks the stored Parquet series (P12.3.2 real
    data) instead of a live/demo client — same grind, same dedupe keys.
    """
    from data.database import SignalDB
    from data.simulator import (format_graduation, format_progress,
                                graduation_status, grind_verdict,
                                paper_progress, simulate_round)

    client = None
    if args.source == "store":
        from data.store import StoreClient
        client = StoreClient(exchange=args.exchange, market=args.market)

    symbols = _symbols(args.symbols) if args.symbols else None
    total_bt = total_pp = 0
    rounds = []
    for r in range(max(1, args.rounds)):
        res = simulate_round(symbols=symbols, timeframe=args.tf, bars=args.bars,
                             step=args.step, min_confidence=args.min_conf,
                             horizons=[float(h) for h in args.horizons.split(",") if h],
                             save=not args.dry_run, client=client)
        rounds.append(res)
        total_bt += res["backtest_added"]
        total_pp += res["paper_added"]
        if not args.json:
            for s in res["symbols"]:
                if s.get("error"):
                    print(f"[!] {s['symbol']}: {s['error']}", file=sys.stderr)
            print(f"round {r + 1}: +{res['backtest_added']} backtest samples, "
                  f"+{res['paper_added']} paper samples (run {res['run_id']})")
        if args.dry_run:
            break  # dry-run: one pass, nothing stored

    with SignalDB() as db:
        progress = paper_progress(db)
        verdict = grind_verdict(progress)
        # P12.14 — discipline is read from the canonical live, non-simulator,
        # decided paper book only; missing journals fail closed.
        from brain.journal import graduation_discipline, violation_rate
        j = violation_rate(db)                       # general journal report
        discipline = graduation_discipline(db)       # graduation criterion
        gate = graduation_status(progress, compliance=discipline["compliance"],
                                 discipline=discipline)
    if args.json:
        print(json.dumps({"rounds": rounds, "totals": {"backtest_added": total_bt,
                                                       "paper_added": total_pp},
                          "progress": progress, "verdict": verdict,
                          "graduation": gate, "journal": j,
                          "discipline": discipline},
                         indent=2, default=str))
    else:
        print()
        print(format_progress(progress, verdict))
        print()
        print(format_graduation(gate))
        print("\n(dry-run: nothing was stored)" if args.dry_run else "")
    return 0
