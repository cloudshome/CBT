"""cli/validation.py — the P12/P13 validation command cluster.

Refactor step 2b of the main.py maintainability debt (ROADMAP §19): the
backtest / validate / edge-validate / xau-evidence / monte commands used to
live inline in ``main.py``; they live here now, byte-identical, and ``main``
re-exports them so the argparse wiring keeps working unchanged.

Every command here is read-only research/validation — none of them moves a
threshold, places an order, or unlocks micro-live.
"""

from __future__ import annotations

import json
import sys
import time

from cli.common import _client, _sym


def cmd_backtest(args) -> int:
    from data.backtester import run_backtest, save_report, print_report
    from data.database import SignalDB

    from data.provenance import (describe_source, is_canonical, is_one_sided,
                                 provenance_of_frame, source_key)

    if args.source == "store":
        from data.store import StoreClient
        client = StoreClient(exchange=args.exchange, market=args.market)
    else:
        client = _client()
    symbol = _sym(args.symbol)
    df = client.klines(symbol, args.tf, args.bars)
    horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
    result = run_backtest(df, symbol=symbol, timeframe=args.tf,
                          horizons=horizons, min_confidence=args.min_conf,
                          step=args.step)
    report = result["report"]
    save_report(report)
    print_report(report)

    # P12.11 — which price series produced these grades. A live/demo REST
    # fetch is the canonical series; a store read carries the store's own
    # stamped provenance (venue, market, and bid/ask side for CSV imports).
    if args.source == "store":
        prov = provenance_of_frame(df, exchange=args.exchange,
                                   market=args.market)
    else:
        prov = provenance_of_frame(df)
    src_key = source_key(*prov)
    if not is_canonical(src_key):
        print(f"\nsource: {describe_source(src_key)}  [key {src_key}]")

    if args.save:
        run_id = time.strftime("%Y%m%d_%H%M%S")
        rows = []
        for g in result["graded"]:
            r = g.as_row()
            r.update({"run_id": run_id, "symbol": symbol,
                      "timeframe": args.tf, "step": args.step,
                      "exchange": prov[0], "market": prov[1],
                      "price_type": prov[2]})
            rows.append(r)
        with SignalDB() as db:
            n = db.save_backtest_rows(rows, run_id)
        print(f"\nSaved {n} graded plans to the signal database (run {run_id}).")
        if src_key:
            print(f"Filed under source '{src_key}' ({describe_source(src_key)}) — "
                  "a separate calibration key from the live series.")
            if is_one_sided(src_key):
                print("This series is one-sided (not an executable round trip): "
                      "research evidence only, never 'proven'.")
        print("Run `python main.py stats` to see what the engine has learned.")
    return 0


def cmd_validate(args) -> int:
    """P12 validation commands: locked protocol and the P12.2 lookahead guard.

    ``validate`` remains the store-only P12.1 protocol.  ``validate
    lookahead`` is a deterministic source scan that never reads market data;
    it fails closed when feature code uses a negative row shift.
    """
    if args.mode == "lookahead":
        from data.validation import print_lookahead, scan_lookahead
        result = scan_lookahead(paths=args.lookahead_paths)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print_lookahead(result)
        return 0 if result.get("ok") else 1

    from data.validation import print_verdict, run_validation_on_store

    horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
    result = run_validation_on_store(
        exchange=args.exchange, market=args.market,
        symbol=_sym(args.symbol), timeframe=args.tf,
        bars=args.bars, horizons=horizons,
        min_bars=args.min_bars, step=args.step,
        min_confidence=args.min_conf,
        train_frac=args.train, val_frac=args.val,
        oos_frac=args.oos, recent_frac=args.recent,
        min_decided=args.min_decided,
        seal_dir=args.seal_dir,
        store_root=args.store_root,
        reseal=args.reseal)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_verdict(result)
    if args.reseal:
        print("\n⚠ RESEAL — the sealed OOS envelope was re-opened on purpose.")
        print("  This run is recorded in the seal history. Do not do this to")
        print("  'improve' the OOS number — that is exactly what the seal forbids.")
    return 0 if result.get("ok") else 1


def cmd_edge_validate(args) -> int:
    """P13 — the honest, regime-aware edge verdict on the sealed OOS + recent
    windows (EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA).

    Read-only: runs the same no-look-ahead grader the desk uses, restricts the
    verdict to the windows the walk never tuned on, and reports the result
    without tuning anything to look green.  It never moves a threshold and
    never places an order.  ``--execution`` selects the fill model
    (``none`` default; ``slip`` / ``impact`` for realistic fills).
    ``--ladder`` (P13.6) pairs the verdict with the canonical live paper book
    in one Backtest → OOS → Paper comparison.
    """
    from engine.edge_validation import (edge_validate_report,
                                        format_compare_ladder,
                                        format_edge_verdict)

    horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
    decisive = tuple(x.strip() for x in args.decisive_windows.split(",")
                     if x.strip())
    symbol = _sym(args.symbol)

    # P13.6 — the canonical live paper book (decided, non-simulator,
    # canonical-live).  Missing DB / empty book → empty rows → the paper rung
    # renders as n/a instead of an invented number.
    paper_rows = None
    if getattr(args, "ladder", False):
        from data.database import SignalDB
        with SignalDB() as db:
            paper_rows = db.live_book_rows()

    # Honest EXECUTION_MODEL control: default 'none' keeps the verdict
    # comparable to the gate; 'slip'/'impact' apply the realistic fill model.
    from data import backtester as _bt_mod
    prev = _bt_mod.EXECUTION_MODEL
    _bt_mod.EXECUTION_MODEL = args.execution
    try:
        if args.source == "store":
            from data.store import StoreClient
            client = StoreClient(exchange=args.exchange, market=args.market)
        else:
            client = _client()
        df = client.klines(symbol, args.tf, args.bars)
        result = edge_validate_report(
            df, symbol=symbol, timeframe=args.tf, horizons=horizons,
            min_bars=args.min_bars, step=args.step,
            min_confidence=args.min_conf,
            min_decided=args.min_decided,
            regime_min_decided=args.regime_min_decided,
            positive_regime_frac=args.positive_regime_frac,
            decisive_windows=decisive,
            train_frac=args.train, val_frac=args.val,
            oos_frac=args.oos, recent_frac=args.recent,
            monte=getattr(args, "monte", False),
            monte_samples=getattr(args, "monte_samples", 2000),
            monte_risk_pct=getattr(args, "monte_risk_pct", 1.0),
            monte_seed=getattr(args, "monte_seed", None),
            paper_rows=paper_rows,
        )
    finally:
        _bt_mod.EXECUTION_MODEL = prev

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    print(format_edge_verdict(result))
    if paper_rows is not None:
        print(format_compare_ladder(result))
    return 0 if result.get("ok") else 1


def cmd_xau_evidence(args) -> int:
    """P12.12 — measure PAXG/XAU basis and inspect sealed promotion evidence.

    This is deliberately read-only. It cannot record approval, alter source
    calibration, unlock micro-live, or place an order.
    """
    from pathlib import Path
    from data.gold_basis import build_xau_evidence_dossier

    try:
        result = build_xau_evidence_dossier(
            store_root=Path(args.store_root),
            seal_dir=Path(args.seal_dir),
            timeframe=args.tf,
            bars=args.bars,
            min_overlap=args.min_overlap,
        )
    except (OSError, ValueError) as exc:
        print(f"[!] XAU evidence audit failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    basis = result["basis_measurement"]
    sealed = result["sealed_oos"]
    decision = result["decision"]
    print("=" * 76)
    print("XAU PROMOTION EVIDENCE — RESEARCH ONLY")
    print("=" * 76)
    print("  sources    binance:spot:PAXGUSDT  vs  dukascopy:spot:XAUUSD")
    print(f"  alignment  exact timestamp only · no fill/resample · {result['timeframe']}")
    print(f"  basis      {basis['status']} · matched {basis['matched_rows']:,} "
          f"(minimum {basis['minimum_overlap']:,})")
    if basis.get("basis"):
        metrics = basis["basis"]
        print(f"             median {metrics['median_bps']} bps · mean {metrics['mean_bps']} bps · "
              f"p05/p95 {metrics['p05_bps']}/{metrics['p95_bps']} bps")
        print(f"             MAD {metrics['mad_bps']} bps · max |basis| {metrics['max_abs_bps']} bps")
        print(f"  period     {basis['start']} → {basis['end']}")
        print(f"  XAU side   {basis['xau']['price_type']} (one-sided research provenance)")
    for error in basis.get("errors", []):
        print(f"  basis gap  {error}")
    print(f"  seal       {sealed['status']} · {sealed['seal_key']}")
    print(f"  history    {sealed['history_entries']} entr{'y' if sealed['history_entries'] == 1 else 'ies'} · "
          f"{sealed['reseal_count']} reseal{'s' if sealed['reseal_count'] != 1 else ''} · "
          f"latest {'RESEALED' if sealed['latest_resealed'] else 'original/absent'}")
    for reason in sealed.get("reasons", []):
        print(f"  seal gap   {reason}")
    print("-" * 76)
    req = result["requirements"]
    print(f"  basis measured                 {'YES' if req['basis_measured_not_assumed'] else 'OPEN'}")
    print(f"  sealed OOS clears current bar  {'YES' if req['sealed_oos_clears_unchanged_bar'] else 'OPEN'}")
    print("  explicit human approval        OPEN")
    print(f"  eligible for human review      {'YES' if decision['eligible_for_human_review'] else 'NO'}")
    print("  XAU tradeable                  NO")
    print("  micro-live unlocked            NO")
    print("=" * 76)
    return 0 if result.get("ok") else 1


def _parse_risk_pcts(s: str | None) -> tuple[float, ...] | None:
    if not s:
        return None
    try:
        return tuple(round(float(x.strip()), 4) for x in s.split(",") if x.strip())
    except ValueError:
        return None


def cmd_monte(args) -> int:
    """Monte Carlo risk-of-ruin table: sweep risk %/trade and read off expected
    drawdown, ruin probability, longest losing streak and time-to-recovery.
    Uses NET realised paper outcomes (costs included)."""
    import json
    from data.database import SignalDB
    from brain.analytics import monte_carlo_ruin_table

    risk_pcts = _parse_risk_pcts(args.risk_pcts)
    with SignalDB() as db:
        result = monte_carlo_ruin_table(
            db,
            risk_percents=risk_pcts or (0.25, 0.5, 1.0, 1.5, 2.0),
            ruin_threshold_pct=args.ruin_threshold,
            samples=args.samples,
            seed=args.seed,
        )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("available") else 1

    if not result.get("available"):
        print("MONTE CARLO RISK TABLE — cannot run")
        print(f"  {result.get('note', 'unknown error')}")
        return 1

    hist = result["historical"]
    print("=" * 96)
    print(f"MONTE CARLO RISK TABLE   start={result['start']:,.0f}   "
          f"ruin threshold={result['ruin_threshold_pct']}%   "
          f"samples={result['samples']}   n_trades={result['n_trades']}")
    print("-" * 96)
    print(f"  historical longest losing streak: {hist['longest_loss_streak']} trade(s)")
    print(f"  historical median time-to-recovery: {hist['median_time_to_recovery_trades']} trade(s)")
    print(f"  historical max drawdown: {hist['max_drawdown_pct']}%")
    print("-" * 96)
    header = (f"  {'risk%':>6} {'exp DD%':>9} {'ruin%':>8} {'below0%':>9} "
              f"{'term median':>12} {'term p5':>11} {'term p95':>11} "
              f"{'loss streak':>11} {'TTR median':>11}")
    print(header)
    for row in result["table"]:
        print(f"  {row['risk_pct']:>6.2f} {row['expected_dd_pct']:>9.2f} "
              f"{row['ruin_prob']*100:>7.1f}% {row['prob_below_start']*100:>7.1f}% "
              f"{row['terminal_median']:>12,.0f} {row['terminal_p5']:>11,.0f} "
              f"{row['terminal_p95']:>11,.0f} {row['max_loss_streak_median']:>11} "
              f"{row['time_to_recovery_median_trades']:>11.1f}")
    print("=" * 96)
    print("exp DD% = expected maximum drawdown; ruin% = prob drawdown >= ruin threshold;")
    print("below0% = prob final equity below start; TTR = trades to recover to prior peak.")
    return 0
