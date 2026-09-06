"""cli/market.py — the market-data command cluster (backfill/store/doctor/...).

Refactor step 3 of the main.py maintainability debt (ROADMAP §19): the P10
market-history commands (backfill, store, doctor, channels, derivatives,
cross, correlation) used to live inline in ``main.py``; they live here now,
byte-identical, and ``main`` re-exports them so the argparse wiring keeps
working unchanged.
"""

from __future__ import annotations

import json
import os
import sys
import time

from cli.common import _client, _sym, _symbols


def cmd_backfill(args) -> int:
    """P10.2/P10.3/P10.6/P12.3.2 — market-data backfill + gap repair / rollup.

    Resumable (re-runs continue at the last stored candle), idempotent
    (a completed re-run adds zero rows), rate-limit aware: paced pages
    (--sleep), exponential backoff on 429/network errors, weight-header
    pacing, geo-block abort, --max-requests cap. ``--market perp`` pages
    the perp endpoint — spot candles are never labelled ``market=perp``.
    ``--exchange bybit`` (P10.6) pages Bybit V5 klines behind the same
    contract. ``DEMO_MODE=1`` uses the offline demo fetcher (offline).

    ``--from-csv PATH`` (P12.3.2) skips the REST transport entirely and
    imports a local Binance-style OHLCV CSV through the same adapter
    boundary (``normalise_klines`` → ``CandleStore.write``), so real
    market data can enter the store on a machine with no exchange
    egress. ``--csv-sha256`` pins the provenance before anything is
    written; ``--rollup`` still composes on top of the imported 1m.
    """
    from data.backfill import BackfillError, backfill, fmt_ts, parse_ts
    from data.gaps import detect_gaps, repair_gaps, rollup
    from data.store import CandleStore

    store = CandleStore(root=args.root) if args.root else CandleStore()

    # P12.3.2 — offline CSV import (never touches a network socket).
    if args.from_csv:
        from data.backfill import backfill_from_csv

        # dukascopy-node is an optional external acquisition tool, not a SKY
        # runtime dependency. Its CSV enters through our existing validation
        # boundary and receives its own series/provenance identity.
        csv_source = getattr(args, "csv_source", "binance")
        csv_exchange = "dukascopy" if csv_source == "dukascopy" else args.exchange
        csv_market = "spot" if csv_source == "dukascopy" else args.market
        price_type = (
            getattr(args, "price_type", "") if csv_source == "dukascopy" else ""
        )
        source_tag = "dukascopy_csv" if csv_source == "dukascopy" else "csv"
        try:
            payload = backfill_from_csv(
                store=store,
                csv_path=args.from_csv,
                symbol=_sym(args.symbol),
                timeframe=args.tf,
                exchange=csv_exchange,
                market=csv_market,
                expected_sha256=args.csv_sha256,
                source=source_tag,
                price_type=price_type,
            )
            if args.rollup:
                payload["rollup"] = rollup(
                    store,
                    exchange=csv_exchange,
                    market=csv_market,
                    symbol=_sym(args.symbol),
                )
            from data.calendar import calendar_for

            csv_cal = calendar_for(csv_exchange, csv_market, _sym(args.symbol))
            payload["gaps_remaining"] = len(
                detect_gaps(
                    store.read(csv_exchange, csv_market, _sym(args.symbol), args.tf),
                    args.tf,
                    csv_cal,
                )
            )
        except BackfillError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"csv import  {payload['exchange']}/{payload['market']}/"
                f"{payload['symbol']}/{payload['timeframe']}"
            )
            print(
                f"  sha256 {payload['sha256']}"
                f"{'  ✓ pin verified' if payload['sha256_verified'] else ''}"
            )
            print(
                f"  rows read {payload['rows_read']:,}  added "
                f"{payload['rows_added']:,}  (store now "
                f"{payload['rows_after']:,})"
            )
            if payload["duplicates_dropped"]:
                print(f"  duplicates dropped {payload['duplicates_dropped']:,}")
            if payload["sanity_dropped"]:
                print(f"  sanity dropped {payload['sanity_dropped']:,}")
            if payload["misaligned_ts"]:
                print(f"  misaligned ts {payload['misaligned_ts']:,}")
            print(
                f"  span {payload['span_days']} days  gaps "
                f"{payload['gaps_found']}  gaps_remaining "
                f"{payload['gaps_remaining']}"
            )
            print(
                f"  calendar {payload['calendar']}"
                + (
                    f"  closed-session bars skipped {payload['closed_session_bars']:,}"
                    if payload.get("closed_session_bars")
                    else ""
                )
            )
            if payload["rows_added"] == 0:
                print("  ✓ idempotent re-run — zero rows added")
            if args.rollup:
                print(f"  rollup: {payload['rollup']}")
        return 0

    now_ms = int(time.time() * 1000)
    try:
        start_ts = parse_ts(args.since, now_ms=now_ms) if args.since else args.start_ts
        end_ts = parse_ts(args.until, now_ms=now_ms) if args.until else args.end_ts
    except BackfillError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 2

    # P10.6: --exchange bybit routes to the Bybit V5 transport behind the
    # same klines_page contract. DEMO_MODE stays on the offline demo
    # fetcher regardless of --exchange (synthetic data, labelled with the
    # requested exchange — same convention the binance demo already uses).
    client = None
    demo = os.getenv("DEMO_MODE", "0") in ("1", "true", "yes")
    if not demo and args.exchange == "bybit":
        from data.bybit_client import BybitClient

        client = BybitClient()

    try:
        result = backfill(
            store=store,
            symbol=_sym(args.symbol),
            timeframe=args.tf,
            exchange=args.exchange,
            market=args.market,
            client=client,
            start_ts=start_ts,
            end_ts=end_ts,
            page_limit=args.page_limit,
            sleep_s=0.0 if args.no_sleep else args.sleep,
            resume=not args.no_resume,
            max_requests=args.max_requests,
            dry_run=args.dry_run,
        )
    except BackfillError as exc:
        print(f"[!] backfill aborted: {exc}", file=sys.stderr)
        return 1

    payload = result.as_dict()
    if args.repair:
        if client is not None:  # live BybitClient (its klines() has market)

            def fetch(start_time=None, end_time=None, limit=1000):
                return client.klines(
                    _sym(args.symbol),
                    args.tf,
                    limit=limit,
                    start_time=start_time,
                    end_time=end_time,
                    market=args.market,
                )
        else:  # demo or live Binance
            from data.sample_client import maybe_client

            client = maybe_client()

            def fetch(start_time=None, end_time=None, limit=1000):
                return client.klines(
                    _sym(args.symbol),
                    args.tf,
                    limit=limit,
                    start_time=start_time,
                    end_time=end_time,
                )

        payload["repair"] = repair_gaps(
            store,
            fetch,
            exchange=args.exchange,
            market=args.market,
            symbol=_sym(args.symbol),
            timeframe=args.tf,
        )
    if args.rollup:
        payload["rollup"] = rollup(
            store,
            exchange=args.exchange,
            market=args.market,
            symbol=_sym(args.symbol),
        )
    remaining = detect_gaps(
        store.read(args.exchange, args.market, _sym(args.symbol), args.tf),
        args.tf,
    )
    payload["gaps_remaining"] = len(remaining)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            f"backfill {result.exchange}/{result.market}/{result.symbol}/{result.timeframe}"
        )
        print(
            f"  pages {result.pages}  before {result.rows_before}  "
            f"after {result.rows_after}  added {result.rows_added}"
        )
        if result.resumed_from is not None:
            print(f"  resumed from {fmt_ts(result.resumed_from)} UTC")
        if result.forming_skipped:
            print(f"  forming skipped {result.forming_skipped} (picked up next run)")
        if result.rate_limit_stalls or result.retries:
            print(
                f"  transport  {result.rate_limit_stalls} rate-limit stalls · "
                f"{result.retries} retries · {result.requests} requests"
            )
        if args.repair:
            print(f"  repair: {payload['repair']}")
        if args.rollup:
            print(f"  rollup: {payload['rollup']}")
        print(f"  gaps remaining: {payload['gaps_remaining']}")
        if result.rows_added == 0 and result.resumed_from is not None:
            print("  ✓ idempotent re-run — zero rows added")
        if args.dry_run:
            print("  (dry-run — nothing written)")
    return 0


def cmd_store(args) -> int:
    """Inspect the P10 Parquet candle store (count, span, partitions)."""
    from data.backfill import DEMO_STORE_ROOT, fmt_ts
    from data.store import CandleStore
    from data.symbols import resolve_symbol

    demo = os.getenv("DEMO_MODE", "0") in ("1", "true", "yes") or args.demo
    symbol = resolve_symbol(args.symbol).symbol
    root = args.root if args.root else (DEMO_STORE_ROOT if demo else None)
    store = CandleStore(root=root)
    df = store.read(args.exchange, args.market, symbol, args.tf)
    parts = store.series(args.exchange, args.market, symbol, args.tf)

    if df.empty:
        print(f"store: no candles for {args.exchange}/{args.market}/{symbol}/{args.tf}")
        print(f"  root: {store.parquet_dir}")
        print("  run:  python main.py backfill --symbol BTCUSDT --market perp --tf 1m")
        return 0

    payload = {
        "exchange": args.exchange,
        "market": args.market,
        "symbol": symbol,
        "timeframe": args.tf,
        "count": len(df),
        "first_ts": int(df["ts"].iloc[0]),
        "last_ts": int(df["ts"].iloc[-1]),
        "first": fmt_ts(int(df["ts"].iloc[0])),
        "last": fmt_ts(int(df["ts"].iloc[-1])),
        "span_days": round((df["ts"].iloc[-1] - df["ts"].iloc[0]) / 86_400_000, 1),
        "partitions": parts,
        "root": str(store.parquet_dir),
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            f"store: {payload['count']:,} candles · {payload['first']} → "
            f"{payload['last']} UTC · {payload['span_days']} days"
        )
        print(
            f"  series: {payload['exchange']}/{payload['market']}/{payload['symbol']} "
            f"{payload['timeframe']}  ·  {len(parts)} year/month partitions"
        )
        print(f"  root:   {payload['root']}")
    return 0


def cmd_doctor(args) -> int:
    """Non-mutating readiness report.

    Layers the per-channel backend registry (P8) on top of the existing
    immune system (`brain/immune.run_health_check`). Always exit 0 if
    at least one channel has a healthy active backend and the risk
    gate is open; otherwise exit 1.
    """
    from brain.channels import doctor_report, probe_all
    from brain.immune import run_health_check

    # --strip: the combined one-line-per-pillar verdict (TODO-1.bis).
    # Same payload the dashboard strip and MCP `readiness` tool render.
    if getattr(args, "strip", False):
        from brain.agent import format_readiness_strip, readiness_strip

        strip = readiness_strip()
        if args.json:
            print(json.dumps(strip, indent=2, default=str))
        else:
            print(format_readiness_strip(strip))
        return 0

    if args.json:
        channels = probe_all()
        try:
            immune = run_health_check()
        except Exception as exc:  # pragma: no cover - defensive
            immune = {
                "error": f"immune.run_health_check() failed: {type(exc).__name__}: {exc}"
            }
        try:
            from brain.agent import readiness_strip

            strip = readiness_strip()
        except Exception as exc:  # pragma: no cover - defensive
            strip = {"error": f"readiness_strip() failed: {type(exc).__name__}: {exc}"}
        payload = {
            "channels": {n: ch.to_dict() for n, ch in channels.items()},
            "immune": immune,
            "readiness": strip,
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    # Lead with the combined strip so the operator sees one verdict before
    # the per-channel detail, then the existing full report.
    try:
        from brain.agent import format_readiness_strip, readiness_strip

        print(format_readiness_strip(readiness_strip()))
        print()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"readiness strip unavailable: {type(exc).__name__}: {exc}\n")

    print(doctor_report(as_json=False))
    print()
    print("─" * 60)
    print("Immune system:")
    print("─" * 60)
    try:
        from brain.immune import run_health_check

        immune = run_health_check()
        if isinstance(immune, dict):
            for k, v in immune.items():
                print(f"  {k}: {v}")
        else:
            print(immune)
    except Exception as exc:
        print(f"  immune system unavailable: {type(exc).__name__}: {exc}")
    return 0


def cmd_channels(args) -> int:
    """List every channel with active backend, status, and configured/ok count."""
    from brain.channels import list_channels, probe_all

    if args.json:
        channels = probe_all()
        print(
            json.dumps(
                {n: ch.to_dict() for n, ch in channels.items()}, indent=2, default=str
            )
        )
        return 0
    print(list_channels(as_json=False))
    return 0


def cmd_derivatives(args) -> int:
    """P10.4: collect / inspect derivatives time series (funding, OI,
    mark, index, basis). Resumable, idempotent, rate-limit aware.
    DEMO_MODE=1 uses SampleClient (offline)."""
    from data.backfill import fmt_ts
    from data.derivatives import (
        ALL_METRICS,
        DerivativesCollector,
        DerivativesStore,
        DerivativesTransportError,
    )
    from data.symbols import resolve_symbol

    store = DerivativesStore()
    symbol = resolve_symbol(args.symbol).symbol

    if args.subcmd == "collect":
        metrics = None
        if getattr(args, "metrics", None):
            metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
        try:
            collector = DerivativesCollector(store, sleep_s=args.sleep)
            runs = collector.collect(
                symbol,
                market=args.market,
                since=args.since,
                until=args.until,
                metrics=metrics,
                dry_run=args.dry_run,
            )
        except DerivativesTransportError as exc:
            print(f"[!] derivatives collect aborted: {exc}", file=sys.stderr)
            return 1
        payload = {m: r.as_dict() for m, r in runs.items()}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"derivatives {symbol}/{args.market} "
                f"({'dry-run — nothing written' if args.dry_run else 'written to ' + str(store.root)})"
            )
            for metric, r in runs.items():
                print(
                    f"  {metric:<22} pages {r.pages:>3}  fetched {r.rows_fetched:>7}  "
                    f"new {r.rows_new:>7}  {fmt_ts(r.first_ts)} → {fmt_ts(r.last_ts)} UTC"
                )
        return 0

    # status
    rows = []
    for metric in ALL_METRICS:
        df = store.read("binance", args.market, symbol, metric)
        if df.empty:
            continue
        rows.append(
            {
                "metric": metric,
                "count": len(df),
                "first_ts": int(df["ts"].iloc[0]),
                "last_ts": int(df["ts"].iloc[-1]),
                "first": fmt_ts(int(df["ts"].iloc[0])),
                "last": fmt_ts(int(df["ts"].iloc[-1])),
            }
        )
    if args.json:
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "market": args.market,
                    "root": str(store.root),
                    "series": rows,
                },
                indent=2,
                default=str,
            )
        )
    else:
        if not rows:
            print(f"derivatives: nothing stored for {symbol}/{args.market}")
            print(f"  run:  python main.py derivatives collect --symbol {symbol}")
            return 0
        print(f"derivatives {symbol}/{args.market} — {len(rows)} metrics stored")
        for r in rows:
            print(
                f"  {r['metric']:<22} {r['count']:>9,} rows  {r['first']} → {r['last']} UTC"
            )
    return 0


def cmd_cross(args) -> int:
    """P10.7: collect / inspect cross-exchange premium + funding spread.

    Generalises the live health probe into a stored series. DEMO_MODE=1
    uses FakeVenueTransport (offline). Historical Binance-vs-Bybit
    premium is derived from the candle store when both venues exist.
    """
    from data.backfill import fmt_ts
    from data.cross_exchange import (
        CrossExchangeCollector,
        CrossExchangeError,
        CrossExchangeStore,
    )
    from data.derivatives import DerivativesStore
    from data.store import CandleStore
    from data.symbols import resolve_symbol

    store = (
        CrossExchangeStore(root=args.root)
        if getattr(args, "root", None)
        else CrossExchangeStore()
    )
    symbol = resolve_symbol(args.symbol).symbol

    if args.subcmd == "collect":
        candle_root = getattr(args, "candle_root", None)
        deriv_root = getattr(args, "deriv_root", None)
        candle_store = CandleStore(root=candle_root) if candle_root else CandleStore()
        deriv_store = (
            DerivativesStore(root=deriv_root) if deriv_root else DerivativesStore()
        )
        try:
            collector = CrossExchangeCollector(
                store,
                candle_store=candle_store,
                deriv_store=deriv_store,
                sleep_s=getattr(args, "sleep", 0.0),
            )
            runs = collector.collect(
                symbol,
                market=args.market,
                timeframe=args.tf,
                since=args.since,
                until=args.until,
                snapshot=not getattr(args, "no_snapshot", False),
                dry_run=args.dry_run,
            )
        except CrossExchangeError as exc:
            print(f"[!] cross collect aborted: {exc}", file=sys.stderr)
            return 1
        payload = {k: r.as_dict() for k, r in runs.items()}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            dest = (
                "dry-run — nothing written"
                if args.dry_run
                else "written to " + str(store.root)
            )
            print(f"cross {symbol}/{args.market} ({dest})")
            if not runs:
                print(
                    "  (nothing collected — backfill both venues or rely on the snapshot)"
                )
            for key, r in runs.items():
                print(
                    f"  {key:<28} fetched {r.rows_fetched:>5}  "
                    f"new {r.rows_new:>5}  "
                    f"{fmt_ts(r.first_ts)} → {fmt_ts(r.last_ts)} UTC  "
                    f"[{r.source}]"
                )
        return 0

    rows = []
    for series in store.list_series():
        if series["symbol"] != symbol:
            continue
        df = store.read(
            series["exchange"], series["market"], series["symbol"], series["metric"]
        )
        if df.empty:
            continue
        rows.append(
            {
                "exchange": series["exchange"],
                "market": series["market"],
                "metric": series["metric"],
                "count": len(df),
                "first_ts": int(df["ts"].iloc[0]),
                "last_ts": int(df["ts"].iloc[-1]),
                "first": fmt_ts(int(df["ts"].iloc[0])),
                "last": fmt_ts(int(df["ts"].iloc[-1])),
                "last_value": float(df["value"].iloc[-1]),
            }
        )
    if args.json:
        print(
            json.dumps(
                {"symbol": symbol, "root": str(store.root), "series": rows},
                indent=2,
                default=str,
            )
        )
    else:
        if not rows:
            print(f"cross: nothing stored for {symbol}")
            print(f"  run:  python main.py cross collect --symbol {symbol}")
            return 0
        print(f"cross {symbol} — {len(rows)} series stored")
        for r in rows:
            print(
                f"  {r['exchange']:<8} {r['market']:<5} {r['metric']:<16} "
                f"{r['count']:>7,} rows  {r['first']} → {r['last']} UTC  "
                f"last={r['last_value']}"
            )
    return 0


def cmd_correlation(args) -> int:
    """Measured cross-asset correlation matrix + ETH/BTC beta (read-only)."""
    from engine.correlation import fetch_report, format_correlation

    client = _client()
    symbols = _symbols(args.symbols) if getattr(args, "symbols", None) else None
    res = fetch_report(
        client, symbols=symbols, timeframe=args.tf, bars=args.bars, window=args.window
    )
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print(format_correlation(res))
    return 0 if res.get("available") else 1
