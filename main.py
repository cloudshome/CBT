#!/usr/bin/env python3
"""CryptoBrain — AI trading-brain signal engine.

Usage:
  python main.py scan --symbol BTCUSDT --tf 15m --json
  python main.py scan --symbols BTCUSDT,ETHUSDT,XAUUSD
  python main.py intelligence --symbol XAUUSD --tf 15m      # JSON-only desk report
  python main.py watch --symbol ETH --interval 120          # continuous loop
  python main.py web                                         # dashboard
  python main.py paper --watch                               # live-market paper monitor
  python main.py sources                                     # CryptoDada + Discord + news
  python main.py brief                                       # daily desk briefing (alias)
  python main.py agent morning                               # desk morning briefing
  python main.py agent ask "is the risk gate open?"          # natural-language question
  python main.py agent ask "am i ready for micro?"           # graduation gate
  python main.py agent all                                   # health + briefing + graduation
  python main.py health                                      # system health (+ KuCoin/OKX/Bybit cross-check)
  python main.py desk                                        # one-call desk advisory (gate + P&L + graduation + advice)
  python main.py daily                                       # 10-minute daily ritual (readiness + loop health + gate + journal)
  python main.py preflight                                   # strict live-paper operations gate
  python main.py simulator                                   # grind 100/20 sample proof
  python main.py backfill --symbol BTCUSDT --market perp     # P10.2: paginated Binance history → Parquet store
  python main.py derivatives collect --symbol BTCUSDT   # P10.4: funding/OI/mark/index/basis → Parquet store
  python main.py cross collect --symbol BTCUSDT         # P10.7: premium/discount + funding spread
  python main.py store --market perp                         # inspect the stored candle history
  python main.py validate lookahead                          # P12.2 future-shift guard
  python main.py xau-evidence --tf 15m                       # P12.12 PAXG/XAU basis dossier
  python main.py mcp                                         # MCP server for Claude/Cursor
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import importlib.util
import subprocess
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _ensure_runtime():
    """Make ``python main.py`` a genuine one-command launcher.

    Normal installations already have the dependencies and this is a cheap
    import check. On a fresh checkout, install the pinned project requirements
    once, then continue into the same dashboard process. Set
    ``SKY_NO_AUTO_INSTALL=1`` for locked-down/CI environments.
    """
    required = {"flask": "flask", "dotenv": "python-dotenv", "numpy": "numpy",
                "pandas": "pandas", "requests": "requests"}
    missing = [package for module, package in required.items()
               if importlib.util.find_spec(module) is None]
    if not missing or os.getenv("SKY_NO_AUTO_INSTALL") == "1":
        if missing:
            raise RuntimeError("Missing dependencies: " + ", ".join(missing)
                               + ". Run: python -m pip install -r requirements.txt")
        return
    print("SKY: first run detected — preparing an isolated environment…", flush=True)
    # Ubuntu/Debian enforce PEP 668 and reject system-wide pip installs.
    # Create a project-local virtualenv and transparently re-launch the same
    # command inside it, so the user still only runs `python3 main.py`.
    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix) and os.getenv("SKY_IN_VENV") != "1":
        try:
            subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
            vpy = os.path.join(venv_dir, "bin", "python")
            env = os.environ.copy()
            env["SKY_IN_VENV"] = "1"
            os.execve(vpy, [vpy, os.path.abspath(__file__), *sys.argv[1:]], env)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise RuntimeError(
                "Could not create .venv. Run: sudo apt install -y python3-venv "
                "then retry python3 main.py") from exc
    print("SKY: installing dashboard dependencies in .venv…", flush=True)
    # Minimal Ubuntu images often ship python3 without pip. Try the standard
    # library bootstrap first; if the distro disables it, report the exact
    # one-time package command instead of exposing a cryptic pip traceback.
    if importlib.util.find_spec("pip") is None:
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "pip is not installed. Run: sudo apt update && "
                "sudo apt install -y python3-pip python3-venv, then rerun: "
                "python3 main.py")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


try:
    _ensure_runtime()
except (RuntimeError, subprocess.CalledProcessError) as exc:
    print(f"SKY cannot start: {exc}", file=sys.stderr)
    sys.exit(1)

from config import (SYMBOL, SYMBOLS, TIMEFRAME, BARS, MIN_CONFIDENCE, DEFAULT_RISK_REWARD,
                    DASHBOARD_HOST, DASHBOARD_PORT, PAPER_POLL_SECONDS, VERSION,
                    BACKTEST_MIN_BARS, BACKTEST_STEP, ROOT)

from data.symbols import normalize_symbol, parse_symbol_list
from data.binance_client import BinanceClient
from data.sample_client import maybe_client
from engine.signal_engine import analyze_frame
from output.signal_schema import validate_output
from output.notifiers import notify_all


def _client() -> BinanceClient:
    return maybe_client()


def _sym(value: str | None) -> str:
    """Normalize BTC/ETH/XAU aliases before storing or filtering signals."""
    return normalize_symbol(value or SYMBOL)


def _symbols(value: str | None) -> list[str]:
    """Parse comma-separated assets using the configured BTC/ETH/XAU watchlist."""
    return parse_symbol_list(value, default=SYMBOLS)


def _source_key_arg(value: str | None) -> str | None:
    """Resolve a ``--source-key`` CLI value into a P12.11 source key.

    ``None``/``all``  → every source (pooled, and the report says so)
    ``live``/``canonical`` → the canonical live Binance spot series (``""``)
    anything else     → parsed as ``exchange:market[:price_type]``
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("", "all", "any", "*"):
        return None
    if text in ("live", "canonical", "binance", "default"):
        from data.provenance import LIVE_SOURCE_KEY
        return LIVE_SOURCE_KEY
    from data.provenance import parse_source_key, source_key
    return source_key(*parse_source_key(text))


def _load_calibration() -> dict:
    """Load the self-improvement profile from the DB (empty dict when unused)."""
    try:
        from data.database import SignalDB
        with SignalDB() as db:
            return db.load_calibration()
    except Exception:
        return {}


def run_scan(symbol: str, timeframe: str, bars: int, with_context: bool = True,
             with_llm: bool = False, save_db: bool = True,
             auto_approve: bool = False) -> dict:
    from brain.full_pipeline import analyze_full
    symbol = _sym(symbol)
    payload = analyze_full(symbol, timeframe, bars,
                           with_context=with_context, with_memory=True)

    if with_llm:
        from ai.llm_brain import LLMBrain
        payload["llm"] = LLMBrain().generate(payload)

    payload["validation"] = validate_output(payload)

    # P15/P16 — the sentiment colour reading rides on every scan path (CLI,
    # web, MCP) so the learning store always holds the signal-time colour.
    try:
        from engine.sentiment import current_sentiment_safe
        payload["sentiment"] = current_sentiment_safe(symbol, timeframe, payload)
    except Exception:  # pragma: no cover — sentiment is a display/learning aid
        pass

    if save_db:
        from data.database import SignalDB
        from engine.lifecycle import reviewable
        with SignalDB() as db:
            sig = payload.get("signal", {})
            decision = payload.get("decision") or {}
            # Desk-first (decision A4): a signal the desk vetoed never enters
            # the human approval queue — it is recorded as a research scan.
            desk_ok = decision.get("action") in ("BUY", "SELL")
            status_override = None if desk_ok else "CREATED"
            existing = db.conn.execute(
                "SELECT id, status FROM scans WHERE signal_id=?",
                (sig.get("signal_id"),)).fetchone()
            if existing:
                scan_id = existing["id"]
                status = existing["status"]
            else:
                scan_id = db.save_scan(payload, status_override=status_override)
                status = "PENDING_REVIEW" if reviewable(sig) and desk_ok else "CREATED"
            payload["scan_id"] = scan_id
            if auto_approve and reviewable(sig) and desk_ok:
                db.update_status(scan_id, "APPROVED", note="auto-approve", reviewer="auto")
                payload["lifecycle"] = {"status": "APPROVED",
                                        "note": "auto-approved (--auto-approve)"}
            else:
                payload["lifecycle"] = {
                    "status": status,
                    "note": ("awaiting human approval — `python main.py review`"
                             if status == "PENDING_REVIEW" else
                             "monitor-only signal (no action required)" if status == "CREATED"
                             and not decision.get("blocked_by") else
                             "DESK BLOCKED — " + "; ".join(decision.get("blocked_by", []))
                             if status == "CREATED" and decision.get("blocked_by") else
                             f"current state: {status}"),
                }
    return payload


def cmd_scan(args) -> int:
    symbols = _symbols(args.symbols)
    all_payloads = []
    for sym in symbols:
        try:
            payload = run_scan(sym, args.tf, args.bars, with_llm=args.llm,
                               save_db=not args.no_save, auto_approve=args.auto_approve)
            all_payloads.append(payload)
            if not args.json:
                _print_human(payload)
        except ConnectionError as exc:
            print(f"[!] {sym}: {exc}", file=sys.stderr)
    if args.json:
        body = all_payloads[0] if len(all_payloads) == 1 else all_payloads
        print(json.dumps(body, indent=2, default=str))
    return 0 if all_payloads else 1


def _print_human(payload: dict) -> None:
    sig = payload["signal"]
    decision = payload.get("decision") or {}
    print("=" * 72)
    d = decision.get("action", sig.get("action"))
    if d != sig.get("action"):
        print(f"{'NO TRADE':>10}  {sig['asset']}  [{sig['timeframe']}]  "
              f"conf={sig['confidence']:<7} {sig['signal_id']}   ← DESK VETOED engine {sig['action']}")
        for b in decision.get("blocked_by", []):
            print(f"   ✗ {b}")
    else:
        print(f"{sig['action']:>10}  {sig['asset']}  [{sig['timeframe']}]  "
              f"conf={sig['confidence']:<7} {sig['signal_id']}")
    if sig.get("entry"):
        print(f"   entry {sig['entry']:>12,.2f}   SL {sig['stop_loss']:>10,.2f}   "
              f"TP {sig['take_profit']:>12,.2f}   RR {sig['risk_reward']:.2f}")
    print(f"   reason: {sig['reason']}")
    if decision:
        gates = decision.get("gates") or {}
        play = gates.get("playbook") or {}
        if play.get("name"):
            print(f"   playbook: {play['name']} — {play.get('note', '')}")
        for c in play.get("checks", []):
            mark = "✓" if c.get("ok") else ("✗" if c.get("blocking") else "·")
            print(f"     {mark} {c['detail']}")
        rg = gates.get("risk") or {}
        for b in rg.get("blocked_by", []):
            print(f"     ✗ risk: {b}")
        pv = gates.get("portfolio") or {}
        for r in pv.get("reasons", []):
            print(f"     ✗ portfolio: {r}")

    # Styles summary (what the market is offering)
    styles = payload.get("styles") or {}
    if styles:
        print("-" * 72)
        print("   STYLES:")
        for s in ("Scalp", "Day", "Swing", "Momentum", "Position"):
            v = styles.get("styles", {}).get(s, {})
            if v and v.get("available"):
                print(f"     ✓ {s:<10} {v.get('direction')} {v.get('confidence')}%  "
                      f"({v.get('horizon')})  {v.get('reason', '')[:70]}")
        if styles.get("stand_aside"):
            print(f"     · stand aside: {'; '.join(styles['stand_aside'])}")

    # Memory / stability
    mem = payload.get("memory") or {}
    if mem:
        st = mem.get("status")
        print("-" * 72)
        print(f"   STATE MEMORY: {st}" + (f"  (stable, reaffirmed ×{mem.get('reaffirms', 0)})" if st == "SAME" else ""))
        for c in mem.get("changes", [])[:4]:
            print(f"     · {c}")
        if mem.get("whipsaw"):
            print("     ⚠️ whipsaw guard active — signals suppressed")

    print("-" * 72)
    for p in payload.get("plans", []):
        print(f"   [{p['confidence']:>3}% {p['confidence_label']:<6}] {p['type']:<22} "
              f"{p['condition'][:80]}")
    scores = payload.get("snapshot", {}).get("scores", {})
    if scores:
        print(f"   scores → bull {scores.get('bull', {}).get('score', 0)}  |  "
              f"bear {scores.get('bear', {}).get('score', 0)}")

    mtf = payload.get("mtf") or {}
    if mtf:
        print("-" * 72)
        views = mtf.get("views", {})
        print("   MTF: " + "  ".join(
            f"{tf}:{v.get('trend', '?')[:1].upper()}" if v.get("available") else f"{tf}:—"
            for tf, v in views.items()))
        a = mtf.get("alignment", {})
        print(f"   HTF {mtf.get('htf_bias')} | LTF {mtf.get('ltf_bias')} | "
              f"alignment {a.get('score')} ({a.get('label')})")
        kl = mtf.get("key_levels", {})
        print(f"   support {kl.get('support', [])}  resistance {kl.get('resistance', [])}")

    ctx = payload.get("market_context", {})
    if ctx.get("data_symbol") and ctx.get("data_symbol") != sig.get("asset"):
        print(f"   data source {ctx.get('data_symbol')} ({ctx.get('provider')})")
    if ctx.get("futures"):
        print(f"   funding {ctx['funding_rate_pct']}%  OI {ctx['open_interest']:,.0f}  "
              f"L/S {ctx['long_short_ratio']:.2f}")
    else:
        print(f"   futures context unavailable — {ctx.get('note', 'not available')}")
    lc = payload.get("lifecycle")
    if lc:
        print(f"   lifecycle: {lc.get('status')} — {lc.get('note')}")
    print()


def cmd_watch(args) -> int:
    symbol = _sym(args.symbol)
    print(f"Watching {symbol} {args.tf} every {args.interval}s — Ctrl+C to stop")
    last_sig = None
    while True:
        try:
            payload = run_scan(symbol, args.tf, args.bars,
                               save_db=not args.no_save, auto_approve=args.auto_approve)
            sig = payload["signal"]
            if sig["action"] != "NO TRADE" and sig.get("signal_id") != last_sig:
                last_sig = sig.get("signal_id")
                _print_human(payload)
                if args.notify:
                    res = notify_all(sig, payload.get("plans"))
                    print(f"   notified: {res}")
            else:
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] {sig['asset']} {sig['action']} conf={sig['confidence']} "
                      f"(score {sig.get('confidence')})")
        except Exception as exc:  # keep the loop alive
            print(f"[!] {exc}", file=sys.stderr)
        time.sleep(max(10, args.interval))


def cmd_sources(args) -> int:
    from data.sources.cryptodada_website import CryptoDadaConnector, summarize_cryptodada
    from data.sources.discord_reader import DiscordReader, summarize_discord
    from data.sources.news import fetch_news

    result = {}
    cd = CryptoDadaConnector()
    result["cryptodada"] = summarize_cryptodada(cd.fetch()) if cd.configured else {
        "configured": False, "message": "Set CRYPTODADA_* in .env"}
    dr = DiscordReader()
    result["discord"] = summarize_discord(dr.read_all()) if dr.can_read else {
        "configured": False, "message": "Set DISCORD_TOKEN + DISCORD_CHANNEL_IDS in .env"}
    result["news"] = fetch_news(limit=12)
    # Information hierarchy (decision A5): tier + trust per source.
    from data.database import SignalDB
    from config import SOURCE_TIER_NAMES
    with SignalDB() as db:
        result["source_trust"] = [
            {**s, "tier_name": SOURCE_TIER_NAMES.get(s["tier"], "?")}
            for s in db.load_source_scores()]
    if not result["source_trust"]:
        result["source_trust_note"] = (
            "No source scores yet — `python main.py sourcetrust <source> <tier 1-5> <0-1> "
            "[note]` (tier 5 = private signals, never auto-actionable)")
    print(json.dumps(result, indent=2, default=str))
    return 0


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
    """
    from engine.edge_validation import edge_validate_report, format_edge_verdict

    horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
    decisive = tuple(x.strip() for x in args.decisive_windows.split(",")
                     if x.strip())
    symbol = _sym(args.symbol)

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
        )
    finally:
        _bt_mod.EXECUTION_MODEL = prev

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1

    print(format_edge_verdict(result))
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


def cmd_scorecard(args) -> int:
    """P12.3 & P12.6 — the single boxed strategy scorecard & net expectancy.

    Reads outcomes that already exist. ``--source db|backtest|paper`` reads
    what has been graded and stored; ``--source store`` runs one fresh
    walk-forward grade over the stored series and scores that. Evaluated
    NET of costs (fees, slip, funding) per P12.6.
    """
    from data.costs import CostModel
    from data.scorecard import (print_scorecard, scorecard_from_db,
                                scorecard_from_store)

    cost_model = CostModel(
        execution_type="maker" if getattr(args, "maker", False) else "taker",
        enabled=not getattr(args, "no_costs", False),
    )
    conditioned = getattr(args, "conditioned", False)
    quality = getattr(args, "quality", False)

    if args.source == "store":
        horizons = [float(h) for h in args.horizons.split(",") if h.strip()]
        report = scorecard_from_store(
            exchange=args.exchange, market=args.market,
            symbol=_sym(args.symbol or SYMBOL), timeframe=args.tf,
            bars=args.bars,
            horizons=horizons, min_bars=args.min_bars, step=args.step,
            min_confidence=args.min_conf, min_decided=args.min_decided,
            cost_model=cost_model, conditioned=conditioned,
            quality=quality)
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
            source=source, min_decided=args.min_decided,
            include_sim=not args.exclude_sim,
            since_ts=since_ts, until_ts=until_ts,
            cost_model=cost_model, conditioned=conditioned,
            quality=quality, step=args.step)

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
    from data.calendar import (calendar_for, closed_bar_count, describe,
                               expected_bars, get_calendar)
    from data.backfill import fmt_ts
    from data.gaps import step_ms

    symbol = _sym(args.symbol) if args.symbol else "XAUUSD"
    cal = (get_calendar(args.calendar) if args.calendar
           else calendar_for(args.exchange, args.market, symbol))
    now_ms = args.at if args.at is not None else int(time.time() * 1000)

    payload = {
        "ok": True,
        "exchange": args.exchange, "market": args.market,
        "symbol": symbol, "timeframe": args.tf,
        "calendar": describe(cal),
        "at_ms": now_ms,
        "open_now": bool(cal.is_open(now_ms)),
    }

    if args.series:
        from data.quality import series_health, verdict_for
        from data.store import CandleStore

        store = CandleStore(root=args.root) if args.root else CandleStore()
        health = series_health(store, args.exchange, args.market, symbol,
                               args.tf, now_ms=now_ms, calendar=cal)
        verdict = verdict_for(health)
        step = step_ms(args.tf)
        first, last = health.get("first_ts"), health.get("last_ts")
        payload["series"] = {
            "candles": health["candles"],
            "first_ts": first, "last_ts": last,
            "expected_open_bars": (expected_bars(first, last, step, cal)
                                   if first is not None else 0),
            "closed_session_bars": (closed_bar_count(first, last, step, cal)
                                    if first is not None else 0),
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
    print(f"calendar    {name}"
          f"{'  (always open)' if payload['calendar']['always_open'] else ''}")
    print(f"  series    {args.exchange}/{args.market}/{symbol}/{args.tf}")
    print(f"  at        {fmt_ts(now_ms)} UTC")
    print(f"  open now  {'YES' if payload['open_now'] else 'no — venue shut'}")
    ser = payload.get("series")
    if ser:
        print(f"  stored    {ser['candles']:,} candles  "
              f"expected-open {ser['expected_open_bars']:,}  "
              f"closed-session {ser['closed_session_bars']:,}")
        print(f"  missing   {ser['missing']:,} "
              f"({ser['gap_fraction']:.2%})  age {ser['age_bars']} bars")
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
        exchange=args.exchange, market=args.market,
        symbol=_sym(args.symbol or SYMBOL), timeframe=args.tf,
        bars=args.bars, horizons=horizons,
        min_bars=args.min_bars, step=args.step,
        min_confidence=args.min_conf, min_decided=args.min_decided,
        cost_model=cost_model)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_quality(report)
    return 0 if report.get("ok") else 1


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


def cmd_signal(args) -> int:
    from data.database import SignalDB
    import json as _json
    with SignalDB() as db:
        scan = db.get_scan(args.scan_id)
        if scan is None:
            print(f"[!] scan #{args.scan_id} not found", file=sys.stderr)
            return 1
        history = db.decision_history(args.scan_id)
    print(f"scan #{scan['id']} — {scan['symbol']} {scan['timeframe']} {scan['action']} "
          f"({scan['created_at']})")
    print(f"  status: {scan['status']}  conf: {scan['confidence_label']}  "
          f"entry: {scan['entry']}  SL: {scan['stop_loss']}  TP: {scan['take_profit']}")
    print(f"  reason: {scan['reason']}")
    print("  lifecycle:")
    for h in history:
        print(f"    {h['from_state']} → {h['to_state']}  by {h['reviewer']}  "
              f"note: {h['note'] or '—'}")
    if scan.get("plans_json"):
        plans = _json.loads(scan["plans_json"])
        print(f"  plans ({len(plans)}):")
        for p in plans[:5]:
            print(f"    [{p['confidence']}%] {p['type']} — {p['condition'][:80]}")
    return 0


def cmd_learn(args) -> int:
    from brain.calibrator import learn, describe
    result = learn()
    print(describe(result["profile"]))

    # P12.11 — name the price series the learning store holds, so a reviewer
    # can see whether research imports are present before trusting a profile.
    from data.database import SignalDB
    from data.provenance import describe_source
    try:
        with SignalDB() as db:
            inv = db.source_inventory()
    except Exception:
        inv = {}
    if inv.get("keys") and not inv.get("canonical_only", True):
        print("\nsource series in the learning store (P12.11):")
        for k in inv["keys"]:
            c = inv["counts"][k]
            flag = "  ← research only (one-sided)" if k in inv.get("one_sided", []) else ""
            print(f"  {describe_source(k):<44} bt={c['backtest']} pp={c['paper']}{flag}")
        print("  calibration keys are per source — a research series cannot "
              "move live confidence.")

    if args.json:
        import json as _json
        print(_json.dumps({"profile": result["profile"], "sources": inv},
                          indent=2, default=str))
    return 0


def cmd_coach(args) -> int:
    from data.database import SignalDB
    from brain.coach import (explain_signal, mentor, personal_feedback,
                             five_levels, GLOSSARY)

    # 1) teach from the current market (fresh scan, no DB save)
    payload = run_scan(args.symbol, args.tf, args.bars, save_db=False)
    print("=" * 70)
    print("🧑‍🏫 COACH — what's happening right now")
    print("=" * 70)
    for line in explain_signal(payload):
        print(" ", line)
    print()
    print(mentor(payload))

    # 2) the five-question ladder — observation → interpretation →
    #    opportunity → decision → action (P13)
    with SignalDB() as db:
        print()
        print("🎯 THE FIVE QUESTIONS — the professional decision ladder")
        for line in five_levels(payload, db=db):
            print(" ", line)

        # 3) personal feedback from decision history
        fb = personal_feedback(db)
    print()
    print("📈 YOUR TRADING FEEDBACK")
    for f in fb:
        print(" ", f)

    # 3) optional glossary deep-dive
    if args.term:
        term = next((k for k in GLOSSARY if k.lower() == args.term.lower()), None)
        if term:
            meaning, why = GLOSSARY[term]
            print(f"\n📖 {term}: {meaning}\n   Why it matters: {why}")
        else:
            print(f"\n[!] unknown term '{args.term}' — try: {', '.join(GLOSSARY)}")
    return 0


def cmd_glossary(args) -> int:
    from brain.coach import GLOSSARY
    if args.term:
        term = next((k for k in GLOSSARY if k.lower() == args.term.lower()), None)
        if term:
            meaning, why = GLOSSARY[term]
            print(f"{term}: {meaning}\n  Why it matters: {why}")
        else:
            print(f"unknown term '{args.term}'")
        return 0
    for term, (meaning, why) in GLOSSARY.items():
        print(f"{term:<18} {meaning}")
    return 0


def _print_context(ctx: dict) -> None:
    print("   CONTEXT (what affects the market):")
    fng = ctx.get("fear_greed") or {}
    if fng.get("available"):
        print(f"     fear&greed: {fng['value']} ({fng['label']})")
    dom = ctx.get("dominance") or {}
    if dom.get("available"):
        print(f"     BTC dom {dom['btc_dominance']}% · ETH {dom['eth_dominance']}% · "
              f"total cap ${dom['total_market_cap_usd']/1e12:.2f}T "
              f"({dom['market_cap_change_24h_pct']:+.2f}% 24h)")
    eq = ctx.get("equities") or {}
    if eq.get("available"):
        cp = eq.get("change_pct", {})
        print(f"     S&P500 {cp.get('^spx')}% · Nasdaq {cp.get('^ndq')}% · "
              f"DXY {cp.get('dx.f')}% · Gold {cp.get('xauusd')}%")
    macro = ctx.get("macro") or {}
    if macro.get("available"):
        for e in macro.get("events", [])[:4]:
            flag = " ⚠️" if e.get("days_until", 99) <= 2 else ""
            print(f"     {e['date']} {e['name']} (in {e['days_until']}d){flag}")
    cyc = ctx.get("cycle") or {}
    if cyc.get("available"):
        print(f"     cycle: {cyc['phase']} · {cyc['days_since_halving']}d since halving · "
              f"{cyc.get('position_vs_200d')}")
    geo = ctx.get("geopolitics") or {}
    if geo.get("available") and geo.get("count"):
        print(f"     ⚠️ geopolitics: {geo['count']} headline hit(s) — {geo['hits'][0]['keyword']}")
    social = ctx.get("social") or {}
    if social.get("available") and social.get("count"):
        print(f"     social/influencer mentions: {social['count']} — "
              f"{social['hits'][0]['keyword']}")
    reg = ctx.get("risk_regime") or {}
    if reg.get("regime"):
        print(f"     risk regime: {reg['regime']} ({reg.get('score')}) — "
              f"{' · '.join(reg.get('parts', [])[:5])}")


def cmd_intelligence(args) -> int:
    """Strict professional desk report."""
    from brain.full_pipeline import analyze_full
    from output.signal_card import format_signal_card
    symbol = _sym(args.symbol)
    payload = analyze_full(symbol, args.tf, args.bars, with_context=True)
    intel = payload.get("intelligence", {})
    if getattr(args, "card", False):
        print(format_signal_card(intel))
    else:
        print(json.dumps(intel, indent=2, default=str))
    return 0


def cmd_card(args) -> int:
    """Print the Institutional AI Signal Card v2.0."""
    from brain.full_pipeline import analyze_full
    from output.signal_card import format_signal_card
    symbol = _sym(args.symbol)
    payload = analyze_full(symbol, args.tf, args.bars, with_context=True)
    intel = payload.get("intelligence", {})
    if args.json:
        print(json.dumps(intel.get("signal_card", intel), indent=2, default=str))
    else:
        print(format_signal_card(intel))
    return 0


def cmd_analyze(args) -> int:
    """Full 'human trader' analysis: MTF + context + styles + memory."""
    from brain.full_pipeline import analyze_full
    symbol = _sym(args.symbol)
    payload = analyze_full(symbol, args.tf, args.bars, with_context=True)
    sig = payload["signal"]
    print("=" * 72)
    print(f"🧠 FULL ANALYSIS — {symbol} {args.tf}")
    print(f"   {sig['action']} {sig['confidence']} — {sig['reason']}")
    mtf = payload.get("mtf", {})
    a = mtf.get("alignment", {})
    print(f"   HTF {mtf.get('htf_bias')} | LTF {mtf.get('ltf_bias')} | "
          f"alignment {a.get('score')} ({a.get('label')})")
    kl = mtf.get("key_levels", {})
    print(f"   support {kl.get('support')}  resistance {kl.get('resistance')}")
    print("-" * 72)
    _print_context(payload.get("context", {}))
    print("-" * 72)
    styles = payload.get("styles", {})
    print("   WHAT THE MARKET OFFERS:")
    if styles.get("market_offering"):
        for s in styles["market_offering"]:
            v = styles["styles"][s]
            print(f"     ✓ {s}: {v['direction']} {v['confidence']}% — {v['reason']}")
    else:
        print("     nothing clean right now — " + "; ".join(styles.get("stand_aside", [])))
    mem = payload.get("memory", {})
    if mem:
        print("-" * 72)
        print(f"   STATE MEMORY: {mem.get('status')}" +
              (f" — stable since {time.strftime('%H:%M', time.localtime(mem.get('stable_since', 0)/1000))}" if mem.get('stable_since') else ""))
        for c in mem.get("changes", [])[:5]:
            print(f"     · {c}")
    if args.json:
        import json as _json
        print(_json.dumps(payload, indent=2, default=str))
    return 0


def cmd_state(args) -> int:
    """Show the AI's remembered market state + event log."""
    from brain.state_memory import SignalMemory
    symbol = _sym(args.symbol)
    mem = SignalMemory()
    row = mem.get_state(symbol, args.tf)
    print("=" * 66)
    print(f"STATE MEMORY — {symbol} {args.tf}")
    if not row:
        print("No state recorded yet. Run `python main.py analyze` or `scan` first.")
        return 0
    print(f"  htf_bias     : {row['htf_bias']}")
    print(f"  alignment    : {row['alignment']}")
    print(f"  last event   : {row['last_event']}")
    print(f"  price        : {row['price']:,.2f}")
    print(f"  state hash   : {row['state_hash']}")
    print(f"  reaffirms    : {row['reaffirms']} (same-state refreshes)")
    print(f"  flips (1h)   : {row['flips_1h']}")
    print(f"  updated      : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['updated_at']/1000))}")
    try:
        import json as _json
        st = _json.loads(row.get("styles_json") or "{}")
        print("  style memory :")
        for s in ("Scalp", "Day", "Swing", "Momentum", "Position"):
            v = st.get(s) or {}
            since = v.get("since_ts")
            print(f"    {s:<10} since={time.strftime('%H:%M', time.localtime(since/1000)) if since else '—'}  "
                  f"cooldown={v.get('cooldown_min', '?')}m")
    except Exception:
        pass
    print("-" * 66)
    print("  recent state events:")
    for e in mem.history(symbol, args.tf, limit=10):
        print(f"    {time.strftime('%m-%d %H:%M', time.localtime(e['ts']/1000))}  "
              f"{e['kind']:<8} {e['detail'][:80]}")
    return 0


def cmd_stats(args) -> int:
    from data.database import SignalDB

    symbol = _sym(args.symbol) if args.symbol else None
    with SignalDB() as db:
        scans = db.latest_scans(symbol, limit=15)
        plan_stats = db.plan_stats()
        bt = db.backtest_stats()
        paper = db.paper_trade_stats(symbol)

    print("=" * 66)
    print("SIGNAL DATABASE — learning store")
    if not scans:
        print("No scans recorded yet. Run `python main.py scan` (saves by default).")
        return 0
    print(f"latest {len(scans)} scans:")
    for s in scans:
        print(f"  {s['symbol']:<10} {s['timeframe']:<4} {s['action']:<8} "
              f"conf={s['confidence_label']:<7} entry={s['entry']}  {s['created_at']}")
    print("-" * 66)
    print("plan-type distribution (live scans):")
    for p in plan_stats:
        print(f"  {p['type']:<24} n={p['n']:>4} avgConf={p['avg_conf']}  avgRR={p['avg_rr']}")

    overall = bt["overall"]
    print("-" * 66)
    print("BACKTEST learning:")
    if overall["n"]:
        wr = overall["win_rate"]
        print(f"  overall: {overall['n']} graded | win-rate "
              f"{f'{wr*100:.1f}%' if wr is not None else 'n/a'} | "
              f"avgR {overall['avg_rr']} | wins {overall['wins']} losses {overall['losses']}")
        print("  by plan type:")
        for r in bt["by_type"]:
            wr = r["win_rate"]
            print(f"    {r['plan_type']:<24} n={r['n']:>4} win "
                  f"{f'{wr*100:.1f}%' if wr is not None else 'n/a'}  avgR {r['avg_rr']}")
        print("  by confidence bucket:")
        for r in bt["by_confidence"]:
            wr = r["win_rate"]
            print(f"    {r['bucket']:<8} n={r['n']:>4} win "
                  f"{f'{wr*100:.1f}%' if wr is not None else 'n/a'}  avgR {r['avg_rr']}")
    else:
        print("  none yet — run `python main.py backtest --save` to start learning.")

    p = paper["overall"]
    print("-" * 66)
    print("PAPER trading (approved live-market simulations):")
    if p["n"]:
        wr = p["win_rate"]
        print(f"  tracked {p['n']} | waiting {p.get('waiting', 0)} | open {p.get('open', 0)} | "
              f"closed {p.get('closed', 0)} | win-rate "
              f"{f'{wr*100:.1f}%' if wr is not None else 'n/a'} | avgR {p['avg_rr']}")
    else:
        print("  none yet — approve a signal, then run `python main.py paper --watch`.")

    # Business scorecard (decision B4) + regime learning (B3) + journal (B5)
    try:
        from brain.metrics import business_metrics, format_metrics
        with SignalDB() as db:
            metrics = business_metrics(db)
            print()
            print(format_metrics(metrics))
    except Exception as exc:  # never break stats on a metrics hiccup
        print(f"  (business metrics unavailable: {exc})")

    if bt.get("by_regime"):
        print("-" * 66)
        print("BACKTEST learning by regime (strategy = setup × regime × asset):")
        for r in bt["by_regime"]:
            wr = r["win_rate"]
            print(f"  {r['regime'] or 'UNKNOWN':<22} n={r['n']:>4} win "
                  f"{f'{wr*100:.1f}%' if wr is not None else 'n/a'}  avgR {r['avg_rr']}")

    try:
        from brain.journal import violation_rate
        with SignalDB() as db:
            j = violation_rate(db)
        if j["n"]:
            print("-" * 66)
            print(f"JOURNAL discipline: {j['violations']}/{j['n']} trades "
                  f"({j['violation_rate']*100:.1f}%) violated the system")
    except Exception:
        pass
    return 0


def cmd_web(args) -> int:
    from web.app import make_app, serve
    host = args.host or DASHBOARD_HOST
    port = args.port or DASHBOARD_PORT
    serve(make_app(), host, port)
    return 0


def cmd_sourcetrust(args) -> int:
    """Record/update a source's information tier (1-5) and trust (0-1)
    (decision A5).  Tier 5 = private signals: context only, never a trigger."""
    from data.database import SignalDB
    from config import SOURCE_TIER_NAMES
    with SignalDB() as db:
        db.save_source_score(args.source, args.tier, args.trust, note=args.note or "")
        rows = db.load_source_scores()
    print("source trust table:")
    for s in rows:
        print(f"  {s['source']:<22} tier {s['tier']} ({SOURCE_TIER_NAMES.get(s['tier'], '?')})  "
              f"trust {s['trust']:.2f}  {s['note'] or ''}")
    return 0


def cmd_risk(args) -> int:
    """Risk & discipline gate status: daily/weekly limits, drawdown ladder,
    trader state, progression level (decisions B6/B7/B9/B10)."""
    from brain.risk_gate import status_text
    from data.database import SignalDB
    with SignalDB() as db:
        print(status_text(db))
        print()
        print("Run `python main.py monte` for the risk-of-ruin table.")
    return 0


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


def cmd_tradestate(args) -> int:
    """Set/clear the behavioral no-trade flags (decision B7)."""
    from data.database import SignalDB
    from brain.risk_gate import trader_state_blocked
    with SignalDB() as db:
        if any(v is not None for v in (args.angry, args.tired, args.revenge, args.chasing)) \
                or args.clear or args.note:
            if args.clear:
                db.set_trader_state(angry=False, tired=False, revenge=False,
                                    chasing=False, note=args.note or "cleared")
            else:
                db.set_trader_state(angry=args.angry, tired=args.tired,
                                    revenge=args.revenge, chasing=args.chasing,
                                    note=args.note or "")
            print("trader state updated:")
        st = db.get_trader_state()
        g = trader_state_blocked(db)
    for k in ("angry", "tired", "revenge", "chasing"):
        print(f"  {k:<8} {'✗ BLOCKED' if st.get(k) else 'clear'}")
    if st.get("note"):
        print(f"  note: {st['note']}")
    print(f"  gate: {'CLOSED — no new trades until cleared' if g['blocked'] else 'OPEN'}")
    return 0


def cmd_journal(args) -> int:
    """Professional trading journal (decision B5): record/view post-trade
    fields and execution quality for a closed scan."""
    from brain.journal import (save_journal, get_journal, execution_quality,
                               pre_trade_checklist, describe_entry,
                               violation_rate)
    from data.database import SignalDB
    with SignalDB() as db:
        if args.scan_id is not None:
            if args.followed_rules is not None or args.emotion or args.mistake \
                    or args.screenshot or args.would_change or args.notes:
                entry = save_journal(
                    db, args.scan_id,
                    followed_rules=args.followed_rules,
                    emotion=args.emotion, mistake=args.mistake,
                    screenshot_path=args.screenshot, would_change=args.would_change,
                    notes=args.notes)
                print(f"journal saved for scan #{args.scan_id}:")
                print(describe_entry(entry))
                q = execution_quality(db, args.scan_id)
                if q.get("recorded"):
                    print(f"  → {q['verdict']} (quality {q['quality']}, {q['outcome_r']:+.2f}R)")
            else:
                entry = get_journal(db, args.scan_id)
                print(f"journal for scan #{args.scan_id}:")
                print(describe_entry(entry))
                q = execution_quality(db, args.scan_id)
                if q.get("recorded"):
                    print(f"  → {q['verdict']} (quality {q['quality']})")
        else:
            stats = violation_rate(db)
            print("=" * 66)
            print("JOURNAL — execution discipline")
            print(f"  recorded trades   {stats['n']}")
            if stats["n"]:
                print(f"  rule violations   {stats['violations']} "
                      f"({stats['violation_rate']*100:.1f}%)")
                print("  (the goal is 0% — a loss with rules followed is an excellent trade)")
            else:
                print("  none yet — `python main.py journal <scan_id> --followed-rules 1 ...`")
    return 0


def cmd_ask(args) -> int:
    """Grounded RAG question over the trading library (with citations).

    Distinct from `agent ask`: this answers knowledge questions ("what are the
    loss limits?", "which setups have positive expectancy in ranging
    markets?", "what is the ETH playbook rule?") from the indexed knowledge
    base with strict source citations, optionally narrated by the LLM.
    """
    from brain.ask import ask as rag_ask
    result = rag_ask(args.question, top_k=args.top_k, use_llm=args.llm)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result["answer"])
        if result.get("citations"):
            print("- citations: " + ", ".join(result["citations"]))
    return 0


def cmd_postreview(args) -> int:
    """Post-trade review for a closed scan: outcome, R, MAE/MFE, discipline."""
    from brain.brief import post_trade_review
    review = post_trade_review(args.scan_id)
    if args.json:
        print(json.dumps(review, indent=2, default=str))
    else:
        if review.get("error"):
            print(f"[!] {review['error']}", file=sys.stderr)
            return 1
        print(f"POST-TRADE REVIEW — scan #{review['scan_id']} "
              f"({review.get('symbol')} {review.get('action')})")
        print(f"  {review['headline']}")
        for t in review.get("takeaways", []):
            print(f"  • {t}")
    return 0


def cmd_agent(args) -> int:
    """Desk agent: morning briefing / health / natural-language ask / all /
    autonomous desk agents (watchdog, paper-reviewer, weekly-review)."""
    from brain.agent import (ask, format_answer, format_briefing, format_health,
                             health_report, morning_briefing)
    if args.action in ("watchdog", "paper-reviewer", "weekly-review",
                       "paper_reviewer", "weekly_review"):
        from brain.agents import run_agent
        result = run_agent(args.action.replace("-", "_"))
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"[{result['status']}] {result['agent']}: {result['summary']}")
            if result.get("data"):
                print(json.dumps(result["data"], indent=2, default=str))
        return 0
    if args.action == "morning":
        briefing = morning_briefing(symbols=args.symbols, timeframe=args.tf,
                                    bars=args.bars, save=args.save)
        if args.json:
            print(json.dumps(briefing, indent=2, default=str))
        else:
            print(format_briefing(briefing))
        return 0
    if args.action == "health":
        report = health_report()
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_health(report))
        return 0
    if args.action == "ask":
        result = ask(args.question, symbol=args.symbol, timeframe=args.tf,
                     bars=args.bars)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_answer(result))
        return 0
    if args.action == "all":
        # One desk run: health + morning briefing + graduation gate.
        from brain.agent import graduation_report
        from data.simulator import format_graduation
        report = health_report()
        briefing = morning_briefing(symbols=args.symbols, timeframe=args.tf,
                                    bars=args.bars, save=args.save)
        gate = graduation_report()
        if args.json:
            print(json.dumps({"health": report, "briefing": briefing,
                              "graduation": gate}, indent=2, default=str))
        else:
            print(format_health(report))
            print()
            print(format_briefing(briefing))
            print()
            print(format_graduation(gate["graduation"]))
        return 0
    print(f"[!] unknown agent action: {args.action}", file=sys.stderr)
    return 1


def cmd_brief(args) -> int:
    """Daily desk briefing — alias for `agent morning` (BLUEPRINT ready-to-run)."""
    from brain.agent import format_briefing, morning_briefing
    briefing = morning_briefing(symbols=args.symbols, timeframe=args.tf,
                                bars=args.bars, save=args.save)
    if args.json:
        print(json.dumps(briefing, indent=2, default=str))
    else:
        print(format_briefing(briefing))
    return 0


def cmd_health(args) -> int:
    """System health: data feeds, database, risk gate, learning, MCP, LLM."""
    from brain.agent import format_health, health_report
    report = health_report()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_health(report))
    return 0 if report.get("ok") else 1


def cmd_desk(args) -> int:
    """One-call desk advisory: gate + today's P&L + graduation + next agent.

    Read-only. Answers 'what would a professional do right now?' without
    placing an order or mutating state. Same data as MCP ``desk_status``
    and ``GET /api/desk``.
    """
    from brain.agent import desk_status, format_desk_status
    status = desk_status()
    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        print(format_desk_status(status))
    return 0


def cmd_daily(args) -> int:
    """10-minute daily ritual: readiness → loop health → gate → journal.

    The one command that operates the paper→graduation loop. Composes
    ``loop_health()`` (itself desk_status + readiness_strip + paper_progress).
    Does not scan the market unless ``--brief`` is passed. Read-only.
    Same payload as ``GET /api/loop-health`` and MCP ``loop_health``.
    """
    from brain.agent import format_loop_health, loop_health
    health = loop_health()
    if args.json:
        payload: dict = health
        if getattr(args, "brief", False):
            from brain.agent import morning_briefing
            payload = {"loop": health,
                       "briefing": morning_briefing(
                           timeframe=getattr(args, "tf", TIMEFRAME),
                           bars=getattr(args, "bars", BARS))}
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(format_loop_health(health))
    if getattr(args, "brief", False):
        from brain.agent import format_briefing, morning_briefing
        print()
        print(format_briefing(morning_briefing(
            timeframe=getattr(args, "tf", TIMEFRAME),
            bars=getattr(args, "bars", BARS))))
    return 0


def cmd_weekly(args) -> int:
    """W3 — the weekly trader review: one page a developing trader rereads
    every Sunday. Same computation as ``GET /api/weekly``, the dashboard
    Review tab, MCP ``weekly_review`` and the ``weekly_review`` agent
    payload. Read-only over the canonical live book; NET of costs; no
    threshold moved.
    """
    from brain.weekly import format_weekly_review, weekly_review
    from data.database import SignalDB
    with SignalDB() as db:
        review = weekly_review(db, days=getattr(args, "days", 7))
    export = getattr(args, "export", None)
    if export:
        with open(export, "w", encoding="utf-8") as fh:
            json.dump(review, fh, indent=2, default=str)
        print(f"[weekly] exported → {export}")
    if args.json:
        print(json.dumps(review, indent=2, default=str))
        return 0
    print(format_weekly_review(review))
    return 0


def cmd_practice(args) -> int:
    """W3.4+W3.6 — practice calibration: desk-agreement plus a sibling
    tape block of replay outcomes. Same computation as ``GET /api/practice``,
    the Chart-tab ✍ PRACTICE card, the Review-tab PRACTICE CALIBRATION card
    and the read-only MCP ``practice_scorecard`` tool. Coaching memory only —
    agreement and tape outcomes are not evidence and never feed any gate.
    """
    from brain.practice import format_practice_scorecard, practice_scorecard
    from data.database import SignalDB
    with SignalDB() as db:
        card = practice_scorecard(db, days=getattr(args, "days", 30))
    if args.json:
        print(json.dumps(card, indent=2, default=str))
        return 0
    print(format_practice_scorecard(card))
    return 0


# ── Agent-Reach-inspired CLI surface (P7/P8, additive) ─────────────────
# These three commands are the install/doctor/SKILL trio borrowed from
# Panniantong/Agent-Reach, scoped to CryptoBrain's read-only safety
# posture.  They never place exchange orders; they only read.

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
        price_type = getattr(args, "price_type", "") if csv_source == "dukascopy" else ""
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
                    store, exchange=csv_exchange, market=csv_market,
                    symbol=_sym(args.symbol),
                )
            from data.calendar import calendar_for
            csv_cal = calendar_for(csv_exchange, csv_market, _sym(args.symbol))
            payload["gaps_remaining"] = len(detect_gaps(
                store.read(csv_exchange, csv_market,
                           _sym(args.symbol), args.tf), args.tf, csv_cal))
        except BackfillError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"csv import  {payload['exchange']}/{payload['market']}/"
                  f"{payload['symbol']}/{payload['timeframe']}")
            print(f"  sha256 {payload['sha256']}"
                  f"{'  ✓ pin verified' if payload['sha256_verified'] else ''}")
            print(f"  rows read {payload['rows_read']:,}  added "
                  f"{payload['rows_added']:,}  (store now "
                  f"{payload['rows_after']:,})")
            if payload["duplicates_dropped"]:
                print(f"  duplicates dropped {payload['duplicates_dropped']:,}")
            if payload["sanity_dropped"]:
                print(f"  sanity dropped {payload['sanity_dropped']:,}")
            if payload["misaligned_ts"]:
                print(f"  misaligned ts {payload['misaligned_ts']:,}")
            print(f"  span {payload['span_days']} days  gaps "
                  f"{payload['gaps_found']}  gaps_remaining "
                  f"{payload['gaps_remaining']}")
            print(f"  calendar {payload['calendar']}"
                  + (f"  closed-session bars skipped "
                     f"{payload['closed_session_bars']:,}"
                     if payload.get("closed_session_bars") else ""))
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
        if client is not None:      # live BybitClient (its klines() has market)
            def fetch(start_time=None, end_time=None, limit=1000):
                return client.klines(
                    _sym(args.symbol), args.tf, limit=limit,
                    start_time=start_time, end_time=end_time,
                    market=args.market)
        else:                       # demo or live Binance
            from data.sample_client import maybe_client
            client = maybe_client()

            def fetch(start_time=None, end_time=None, limit=1000):
                return client.klines(
                    _sym(args.symbol), args.tf, limit=limit,
                    start_time=start_time, end_time=end_time,
                )

        payload["repair"] = repair_gaps(
            store, fetch, exchange=args.exchange, market=args.market,
            symbol=_sym(args.symbol), timeframe=args.tf,
        )
    if args.rollup:
        payload["rollup"] = rollup(
            store, exchange=args.exchange, market=args.market,
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
        print(f"backfill {result.exchange}/{result.market}/{result.symbol}/{result.timeframe}")
        print(f"  pages {result.pages}  before {result.rows_before}  "
              f"after {result.rows_after}  added {result.rows_added}")
        if result.resumed_from is not None:
            print(f"  resumed from {fmt_ts(result.resumed_from)} UTC")
        if result.forming_skipped:
            print(f"  forming skipped {result.forming_skipped} (picked up next run)")
        if result.rate_limit_stalls or result.retries:
            print(f"  transport  {result.rate_limit_stalls} rate-limit stalls · "
                  f"{result.retries} retries · {result.requests} requests")
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
        "exchange": args.exchange, "market": args.market, "symbol": symbol,
        "timeframe": args.tf, "count": len(df),
        "first_ts": int(df["ts"].iloc[0]), "last_ts": int(df["ts"].iloc[-1]),
        "first": fmt_ts(int(df["ts"].iloc[0])), "last": fmt_ts(int(df["ts"].iloc[-1])),
        "span_days": round((df["ts"].iloc[-1] - df["ts"].iloc[0]) / 86_400_000, 1),
        "partitions": parts, "root": str(store.parquet_dir),
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"store: {payload['count']:,} candles · {payload['first']} → "
              f"{payload['last']} UTC · {payload['span_days']} days")
        print(f"  series: {payload['exchange']}/{payload['market']}/{payload['symbol']} "
              f"{payload['timeframe']}  ·  {len(parts)} year/month partitions")
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
            immune = {"error": f"immune.run_health_check() failed: {type(exc).__name__}: {exc}"}
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
        print(json.dumps(
            {n: ch.to_dict() for n, ch in channels.items()},
            indent=2, default=str))
        return 0
    print(list_channels(as_json=False))
    return 0


def cmd_skill(args) -> int:
    """Print or install the agent-facing SKILL.md.

    Default behaviour: print the SKILL to stdout (read-only, never
    writes anywhere). With --install --system, copy the SKILL to
    ``~/.claude/skills/cryptobrain/SKILL.md`` (the directory layout
    Claude Code, Cursor, and Arena all recognise). --dry-run previews
    the path without touching the filesystem.
    """
    from pathlib import Path

    skill_path = Path(__file__).parent / "SKILL.md"
    if not skill_path.exists():
        print(f"SKILL.md not found at {skill_path}", file=sys.stderr)
        return 1

    # Default / --print: just dump it to stdout
    if not args.install and not args.uninstall:
        sys.stdout.write(skill_path.read_text(encoding="utf-8"))
        return 0

    # Mutating paths require --system (matches Agent-Reach's stance)
    if not args.system:
        print(
            "Refusing to write under $HOME without --system.\n"
            "Default is inspect-only. Re-run with --system to permit "
            "filesystem writes, or add --dry-run to preview.",
            file=sys.stderr,
        )
        return 2

    target_dir = (
        Path(args.target_dir).expanduser()
        if args.target_dir
        else Path.home() / ".claude" / "skills" / "cryptobrain"
    )
    target_path = target_dir / "SKILL.md"

    if args.uninstall:
        if args.dry_run:
            print(f"[dry-run] would remove {target_path}")
            return 0
        try:
            if target_path.is_symlink():
                target_path.unlink()
            elif target_path.exists():
                target_path.unlink()
            # Best-effort: remove the now-empty parent dir
            try:
                target_dir.rmdir()
            except OSError:
                pass
            print(f"removed {target_path}")
        except FileNotFoundError:
            print(f"not installed at {target_path} (no-op)")
        return 0

    # --install
    if args.dry_run:
        print(f"[dry-run] would write {len(skill_path.read_text(encoding='utf-8'))} bytes "
              f"to {target_path}")
        return 0

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"could not create {target_dir}: {exc}", file=sys.stderr)
        return 1
    try:
        # Atomic-ish write: write to .tmp then rename
        tmp = target_path.with_suffix(".md.tmp")
        tmp.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.replace(target_path)
    except OSError as exc:
        print(f"could not write {target_path}: {exc}", file=sys.stderr)
        return 1
    print(f"installed {target_path}")
    return 0


def cmd_preflight(args) -> int:
    """Strict readiness gate for unattended live-data paper operations."""
    from brain.preflight import format_preflight, preflight_report
    report = preflight_report(allow_demo=args.allow_demo)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_preflight(report))
    return 0 if report["ready"] else 2


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


def cmd_derivatives(args) -> int:
    """P10.4: collect / inspect derivatives time series (funding, OI,
    mark, index, basis). Resumable, idempotent, rate-limit aware.
    DEMO_MODE=1 uses SampleClient (offline)."""
    from data.backfill import fmt_ts
    from data.derivatives import (ALL_METRICS, DerivativesCollector,
                                  DerivativesStore, DerivativesTransportError,
                                  default_derivatives_transport)
    from data.symbols import resolve_symbol

    store = DerivativesStore()
    symbol = resolve_symbol(args.symbol).symbol

    if args.subcmd == "collect":
        metrics = None
        if getattr(args, "metrics", None):
            metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
        try:
            collector = DerivativesCollector(store, sleep_s=args.sleep)
            runs = collector.collect(symbol, market=args.market, since=args.since,
                                     until=args.until, metrics=metrics,
                                     dry_run=args.dry_run)
        except DerivativesTransportError as exc:
            print(f"[!] derivatives collect aborted: {exc}", file=sys.stderr)
            return 1
        payload = {m: r.as_dict() for m, r in runs.items()}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"derivatives {symbol}/{args.market} "
                  f"({'dry-run — nothing written' if args.dry_run else 'written to ' + str(store.root)})")
            for metric, r in runs.items():
                print(f"  {metric:<22} pages {r.pages:>3}  fetched {r.rows_fetched:>7}  "
                      f"new {r.rows_new:>7}  {fmt_ts(r.first_ts)} → {fmt_ts(r.last_ts)} UTC")
        return 0

    # status
    rows = []
    for metric in ALL_METRICS:
        df = store.read("binance", args.market, symbol, metric)
        if df.empty:
            continue
        rows.append({
            "metric": metric,
            "count": len(df),
            "first_ts": int(df["ts"].iloc[0]),
            "last_ts": int(df["ts"].iloc[-1]),
            "first": fmt_ts(int(df["ts"].iloc[0])),
            "last": fmt_ts(int(df["ts"].iloc[-1])),
        })
    if args.json:
        print(json.dumps({"symbol": symbol, "market": args.market,
                          "root": str(store.root), "series": rows},
                         indent=2, default=str))
    else:
        if not rows:
            print(f"derivatives: nothing stored for {symbol}/{args.market}")
            print(f"  run:  python main.py derivatives collect --symbol {symbol}")
            return 0
        print(f"derivatives {symbol}/{args.market} — {len(rows)} metrics stored")
        for r in rows:
            print(f"  {r['metric']:<22} {r['count']:>9,} rows  {r['first']} → {r['last']} UTC")
    return 0


def cmd_cross(args) -> int:
    """P10.7: collect / inspect cross-exchange premium + funding spread.

    Generalises the live health probe into a stored series. DEMO_MODE=1
    uses FakeVenueTransport (offline). Historical Binance-vs-Bybit
    premium is derived from the candle store when both venues exist.
    """
    from data.backfill import fmt_ts
    from data.cross_exchange import (CrossExchangeCollector,
                                     CrossExchangeError, CrossExchangeStore)
    from data.store import CandleStore
    from data.derivatives import DerivativesStore
    from data.symbols import resolve_symbol

    store = (CrossExchangeStore(root=args.root)
             if getattr(args, "root", None) else CrossExchangeStore())
    symbol = resolve_symbol(args.symbol).symbol

    if args.subcmd == "collect":
        candle_root = getattr(args, "candle_root", None)
        deriv_root = getattr(args, "deriv_root", None)
        candle_store = (CandleStore(root=candle_root) if candle_root
                        else CandleStore())
        deriv_store = (DerivativesStore(root=deriv_root) if deriv_root
                       else DerivativesStore())
        try:
            collector = CrossExchangeCollector(
                store, candle_store=candle_store, deriv_store=deriv_store,
                sleep_s=getattr(args, "sleep", 0.0))
            runs = collector.collect(
                symbol, market=args.market, timeframe=args.tf,
                since=args.since, until=args.until,
                snapshot=not getattr(args, "no_snapshot", False),
                dry_run=args.dry_run)
        except CrossExchangeError as exc:
            print(f"[!] cross collect aborted: {exc}", file=sys.stderr)
            return 1
        payload = {k: r.as_dict() for k, r in runs.items()}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            dest = ("dry-run — nothing written" if args.dry_run
                    else "written to " + str(store.root))
            print(f"cross {symbol}/{args.market} ({dest})")
            if not runs:
                print("  (nothing collected — backfill both venues or rely on the snapshot)")
            for key, r in runs.items():
                print(f"  {key:<28} fetched {r.rows_fetched:>5}  "
                      f"new {r.rows_new:>5}  "
                      f"{fmt_ts(r.first_ts)} → {fmt_ts(r.last_ts)} UTC  "
                      f"[{r.source}]")
        return 0

    rows = []
    for series in store.list_series():
        if series["symbol"] != symbol:
            continue
        df = store.read(series["exchange"], series["market"],
                        series["symbol"], series["metric"])
        if df.empty:
            continue
        rows.append({
            "exchange": series["exchange"], "market": series["market"],
            "metric": series["metric"], "count": len(df),
            "first_ts": int(df["ts"].iloc[0]),
            "last_ts": int(df["ts"].iloc[-1]),
            "first": fmt_ts(int(df["ts"].iloc[0])),
            "last": fmt_ts(int(df["ts"].iloc[-1])),
            "last_value": float(df["value"].iloc[-1]),
        })
    if args.json:
        print(json.dumps({"symbol": symbol, "root": str(store.root),
                          "series": rows}, indent=2, default=str))
    else:
        if not rows:
            print(f"cross: nothing stored for {symbol}")
            print(f"  run:  python main.py cross collect --symbol {symbol}")
            return 0
        print(f"cross {symbol} — {len(rows)} series stored")
        for r in rows:
            print(f"  {r['exchange']:<8} {r['market']:<5} {r['metric']:<16} "
                  f"{r['count']:>7,} rows  {r['first']} → {r['last']} UTC  "
                  f"last={r['last_value']}")
    return 0


def cmd_mcp(args) -> int:
    """Run the Model Context Protocol server (stdio) for MCP clients."""
    from ai.mcp_server import run as mcp_run
    return mcp_run()


def cmd_correlation(args) -> int:
    """Measured cross-asset correlation matrix + ETH/BTC beta (read-only)."""
    from engine.correlation import fetch_report, format_correlation

    client = _client()
    symbols = _symbols(args.symbols) if getattr(args, "symbols", None) else None
    res = fetch_report(client, symbols=symbols, timeframe=args.tf,
                       bars=args.bars, window=args.window)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print(format_correlation(res))
    return 0 if res.get("available") else 1


def cmd_sky_agent(args) -> int:
    """24/7 SKY Intelligence Agent — research & monitoring (never trades).

    Subcommands:
      health   — readiness + system probe (cheap, runs in <1s)
      status   — agent memory / recent reports / hypotheses
      collect  — one polling pass (market / edgar / news / system)
      report   — daily intelligence report (markdown or json)
      run      — daemon loop (systemd ExecStart; --demo for offline)
      hypothesize — propose/test trading hypotheses
    """
    action = getattr(args, "sky_agent_action", "health")
    is_json = getattr(args, "json", False)

    if action == "health":
        from sky_agent.monitor_system import probe_system
        from brain.agent import readiness_strip
        try:
            strip = readiness_strip()
        except Exception as exc:
            strip = {"error": str(exc)}
        sys_probe = probe_system()
        payload = {"readiness": strip, "system": sys_probe, "agent": "sky_agent", "ok": sys_probe.get("level") not in ("HIGH", "CRITICAL") or not sys_probe.get("alerts")}
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"SKY Agent health — system level {sys_probe.get('level')}  alerts: {sys_probe.get('alerts') or 'none'}")
            print(f"  cpu {sys_probe.get('cpu_pct')}%  ram {sys_probe.get('ram_pct')}%  disk {sys_probe.get('disk_pct')}%")
            print(f"  db_ok={sys_probe.get('db_ok')}")
            if strip.get("readiness") or strip.get("error"):
                print(f"  readiness: {str(strip)[:400]}")
        return 0

    if action == "status":
        from data.database import SignalDB
        from sky_agent.memory import ensure_memory_schema
        with SignalDB() as db:
            ensure_memory_schema(db)
            hyps = db.conn.execute("SELECT hypothesis_id,setup,status,created_ts FROM research_hypotheses ORDER BY created_ts DESC LIMIT 20").fetchall()
            reports = db.conn.execute("SELECT report_date,kind,asset,recommendation,level,created_ts FROM intelligence_reports ORDER BY created_ts DESC LIMIT 10").fetchall()
            regimes = db.conn.execute("SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10").fetchall()
            filings = db.conn.execute("SELECT accession,event_type,severity FROM sec_events ORDER BY created_ts DESC LIMIT 10").fetchall()
        payload = {"hypotheses": [dict(r) for r in hyps], "reports": [dict(r) for r in reports], "regimes": [dict(r) for r in regimes], "sec_events": [dict(r) for r in filings]}
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"hypotheses: {len(hyps)}  reports: {len(reports)}  regimes: {len(regimes)}  sec_events: {len(filings)}")
            for r in hyps[:5]:
                print(f"  {r['hypothesis_id']} {r['setup']} [{r['status']}]")
            for r in reports[:5]:
                print(f"  report {r['report_date']} {r['kind']} {r['asset']} → {r['recommendation']} [{r['level']}]")
        return 0

    if action == "collect":
        demo = bool(getattr(args, "demo", False))
        target = getattr(args, "target", "all")
        results: dict = {}
        if target in ("all", "market"):
            from sky_agent.monitor_market import scan_market_snapshot
            results["market"] = {"events": len(scan_market_snapshot(demo=demo))}
        if target in ("all", "system"):
            from sky_agent.monitor_system import probe_system
            results["system"] = probe_system()
        if target in ("all", "edgar"):
            from sky_agent.collectors.edgar import ingest_recent_filings, upsert_filings
            rows = ingest_recent_filings(demo=demo)
            results["edgar"] = {"filings": upsert_filings(rows)}
        if target in ("all", "news"):
            from sky_agent.collectors.news import collect_news
            results["news"] = {"items": len(collect_news(limit=10))}
        if is_json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(json.dumps(results, indent=2, default=str))
        return 0

    if action == "report":
        demo = bool(getattr(args, "demo", False))
        from sky_agent.daily_report import build_daily_report, format_report_md
        report = build_daily_report(demo=demo)
        if is_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_report_md(report))
        return 0

    if action == "run":
        demo = bool(getattr(args, "demo", False))
        max_ticks = getattr(args, "max_ticks", None)
        from sky_agent.daemon import run_forever
        result = run_forever(demo=demo, max_ticks=max_ticks)
        if is_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(json.dumps(result, indent=2, default=str))
        return 0

    if action == "hypothesize":
        demo = bool(getattr(args, "demo", False))
        from sky_agent.hypothesis import propose_hypotheses, run_hypothesis_backtest
        hyps = propose_hypotheses()
        target = getattr(args, "hypothesis_id", None)
        payload: dict = {"proposed": hyps}
        if target:
            payload["backtest"] = run_hypothesis_backtest(target, symbol=getattr(args, "symbol", "BTCUSDT"), timeframe=getattr(args, "tf", "15m"))
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"[!] unknown sky-agent action: {action}", file=sys.stderr)
    return 1


def cmd_release(args) -> int:
    """P22.3 signing + clean-target drill catalog / evidence check."""
    from ops.release_drills import (DrillError, evaluate_file, format_catalog,
                                    p22_status)
    action = getattr(args, "release_action", "drills")
    if action in ("drills", "sign-plan", "status"):
        payload = p22_status(getattr(args, "evidence_dir", None))
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(format_catalog(payload))
        return 0
    if action == "check":
        try:
            verdict = evaluate_file(args.drill, args.evidence)
        except DrillError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(verdict, indent=2, default=str))
        else:
            print(f"{verdict['drill']}: {verdict['note']}")
            if verdict["missing"]:
                print("  missing: " + ", ".join(verdict["missing"]))
        return 0 if verdict["passed"] else 1
    print(f"[!] unknown release action {action}", file=sys.stderr)
    return 1


def cmd_companion(args) -> int:
    """P20/P21 contracts + P22.2 native project lint (unsigned)."""
    platform = getattr(args, "platform", "windows")
    action = getattr(args, "companion_action", "spec")
    if action == "lint":
        from ops.native_projects import format_status, native_status
        payload = native_status()
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(format_status(payload))
        return 0 if payload.get("ok") else 1
    if action == "spec":
        if platform == "android":
            from ops.android_companion import android_spec, format_spec
        else:
            from ops.windows_companion import companion_spec, format_spec
        spec = android_spec() if platform == "android" else companion_spec()
        if args.json:
            print(json.dumps(spec, indent=2))
        else:
            print(format_spec(spec))
        return 0
    if action == "validate-url":
        try:
            if platform == "android":
                from ops.android_companion import CompanionError, validate_hub_url
            else:
                from ops.windows_companion import CompanionError, validate_hub_url
            url = validate_hub_url(args.hub)
        except CompanionError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        print(url)
        return 0
    if action == "status":
        if platform == "android":
            from ops.android_companion import KeystoreTokenStore as TokenStore
        else:
            from ops.windows_companion import TokenStore
        store = TokenStore(args.state)
        rec = store.load()
        if rec is None:
            print("not paired")
            return 1
        rec = {k: v for k, v in rec.items() if k != "token"}
        if args.json:
            print(json.dumps(rec, indent=2, default=str))
        else:
            print(f"paired to {rec.get('hub_url')}  scope={rec.get('scope')}")
        return 0
    print(f"[!] unknown companion action {action}", file=sys.stderr)
    return 1


def cmd_hub(args) -> int:
    """Ubuntu Hub operations, including the P22 redacted support bundle."""
    from ops.hub import dispatch, format_doctor, format_status

    action = args.hub_action
    try:
        payload = dispatch(
            action,
            prefix=getattr(args, "prefix", None),
            mode=getattr(args, "mode", "local"),
            owner=getattr(args, "owner", "") or "",
            archive=getattr(args, "archive", None),
            overwrite=bool(getattr(args, "overwrite", False)),
            purge=bool(getattr(args, "purge", False)),
            include_store=not bool(getattr(args, "no_store", False)),
            retention_days=int(getattr(args, "retention_days", 14) or 14),
            unit=getattr(args, "unit", "sky-dashboard.service"),
            lines=int(getattr(args, "lines", 80) or 80),
            platform=getattr(args, "platform", "windows"),
        )
    except (ValueError, FileNotFoundError, FileExistsError, PermissionError) as exc:
        print(f"[!] hub {action}: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    elif action == "status":
        print(format_status(payload))
    elif action == "doctor":
        print(format_doctor(payload))
    elif action == "logs":
        for line in payload.get("lines") or []:
            print(line)
        if not payload.get("ok"):
            print(payload.get("error") or "journalctl unavailable", file=sys.stderr)
            return 1
    elif action in ("first-night", "first_night", "guide"):
        print(payload.get("guide") or "")
    elif action in ("role", "host-role", "pc"):
        print(f"SKY Hub role: {payload.get('role')}")
        print(f"  {payload.get('decision')}")
        print(f"  {payload.get('why')}")
        print("  run on this PC:")
        for item in payload.get("run") or []:
            mark = "*" if item.get("required") else "-"
            print(f"    {mark} {item.get('unit')}: {item.get('job')}")
        print("  human still does: " + "; ".join(payload.get("human_still_does") or []))
        print("  do not run: " + "; ".join(payload.get("do_not_run") or []))
        print("  live exchange execution  NO")
    else:
        print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok", True) else 1


def cmd_hidden(args) -> int:
    """Hidden alpha CLI: regime + CVD + kelly + MAE/MFE + Monte Carlo.

    Usage:
      python main.py hidden chart_read [SYMBOL]        # HMM regime + CVD + kelly
      python main.py hidden analytics mae [SYMBOL]     # MAE/MFE summary from DB
      python main.py hidden analytics mc [SYMBOL]      # Monte Carlo equity dist
    """
    from data.database import SignalDB
    from engine.hidden_alpha import hidden_alpha_report, format_hidden
    from brain.analytics import mae_mfe_summary, monte_carlo_equity

    # Subparser positional "symbol" overwrites parent --symbol; fall back to default
    symbol = _sym(args.symbol or SYMBOL)
    tf = args.tf

    if args.subcmd in (None, "chart_read"):
        client = _client()
        df = client.klines(symbol, tf, args.bars)
        report = hidden_alpha_report(df, symbol, tf)
        print(format_hidden(report))
        return 0

    if args.subcmd == "analytics":
        with SignalDB() as db:
            if args.analytics_subcmd == "mae":
                r = mae_mfe_summary(db, plan_type=args.plan_type)
            elif args.analytics_subcmd == "mc":
                r = monte_carlo_equity(
                    db, samples=args.samples, seed=args.seed)
            else:
                print(f"[!] unknown analytics subcommand: {args.analytics_subcmd}",
                      file=sys.stderr)
                return 1
            print(json.dumps(r, indent=2, default=str))
        return 0

    print(f"[!] unknown hidden subcommand: {args.subcmd}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CryptoBrain — AI trading-brain signal engine")
    sub = ap.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="one-shot signal scan")
    p_scan.add_argument("--symbol", default=SYMBOL, help="single asset (aliases: BTC, ETH, XAU/GOLD)")
    p_scan.add_argument("--symbols", default=None,
                        help=f"comma-separated watchlist (e.g. {','.join(SYMBOLS)}); overrides --symbol")
    p_scan.add_argument("--tf", default=TIMEFRAME)
    p_scan.add_argument("--bars", type=int, default=BARS)
    p_scan.add_argument("--json", action="store_true", help="raw JSON output")
    p_scan.add_argument("--llm", action="store_true", help="attach LLM narrative if configured")
    p_scan.add_argument("--no-save", action="store_true", help="do not write the scan to the signal database")
    p_scan.add_argument("--auto-approve", action="store_true",
                        help="skip the human approval gate (unattended mode)")
    p_scan.set_defaults(func=cmd_scan)

    p_watch = sub.add_parser("watch", help="continuous monitor loop")
    p_watch.add_argument("--symbol", default=SYMBOL, help="asset to watch (aliases: BTC, ETH, XAU/GOLD)")
    p_watch.add_argument("--tf", default=TIMEFRAME)
    p_watch.add_argument("--bars", type=int, default=BARS)
    p_watch.add_argument("--interval", type=int, default=120)
    p_watch.add_argument("--notify", action="store_true", help="push signals to Telegram/Discord")
    p_watch.add_argument("--no-save", action="store_true", help="do not write scans to the signal database")
    p_watch.add_argument("--auto-approve", action="store_true",
                        help="approve signals automatically (unattended mode)")
    p_watch.set_defaults(func=cmd_watch)

    p_paper = sub.add_parser("paper", help="monitor approved paper trades; never sends exchange orders")
    p_paper.add_argument("--symbol", default=None, help="optional symbol filter, e.g. BTCUSDT, ETH, XAUUSD")
    p_paper.add_argument("--watch", action="store_true", help="keep monitoring until Ctrl+C")
    p_paper.add_argument("--interval", type=int, default=PAPER_POLL_SECONDS,
                         help="seconds between checks in --watch mode")
    p_paper.add_argument("--no-enroll", action="store_true",
                         help="only check existing paper trades; do not enroll new approvals")
    p_paper.add_argument("--json", action="store_true", help="machine-readable run summary")
    p_paper.add_argument(
        "--allow-demo", action="store_true",
        help="allow DEMO_MODE=1 for a rehearsal; never counts as live paper evidence",
    )
    p_paper.set_defaults(func=cmd_paper)

    p_src = sub.add_parser("sources", help="pull CryptoDada + Discord + news")
    p_src.set_defaults(func=cmd_sources)

    p_bt = sub.add_parser("backtest", help="walk-forward grade of engine plans")
    p_bt.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_bt.add_argument("--tf", default=TIMEFRAME)
    p_bt.add_argument("--bars", type=int, default=BARS)
    p_bt.add_argument("--horizons", default="1,4,24", help="comma-separated hours, e.g. 1,4,24")
    p_bt.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_bt.add_argument("--step", type=int, default=BACKTEST_STEP,
                      help="walk-forward bar step (1 = every bar)")
    p_bt.add_argument("--save", action="store_true", help="store graded outcomes in the signal database")
    p_bt.add_argument("--source", default="auto", choices=("auto", "store"),
                      help="auto = live (or demo) client; store = the P10 Parquet "
                           "series (offline, P12.3.2 real data)")
    p_bt.add_argument("--exchange", default="binance",
                      help="store venue (binance|bybit|dukascopy)")
    p_bt.add_argument("--market", default="spot", choices=("spot", "perp"),
                      help="store series market label (used with --source store)")
    p_bt.set_defaults(func=cmd_backtest)

    p_val = sub.add_parser(
        "validate",
        help="P12 validation: locked protocol or `lookahead` source guard")
    p_val.add_argument("mode", nargs="?", choices=("lookahead",), default=None,
                       help="lookahead = P12.2 negative-shift guard; omit for P12.1 protocol")
    p_val.add_argument("--path", dest="lookahead_paths", action="append", default=None,
                       help="lookahead file/directory to scan (repeatable; default: engine, brain, data)")
    p_val.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_val.add_argument("--tf", default=TIMEFRAME)
    p_val.add_argument("--exchange", default="binance", help="stored series venue (binance|bybit)")
    p_val.add_argument("--market", default="perp", help="spot or perp series")
    p_val.add_argument("--bars", type=int, default=2000,
                       help="most-recent bars from the store to validate over")
    p_val.add_argument("--step", type=int, default=3,
                       help="bar step for the walk-forward scan (1 = every bar)")
    p_val.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                       help="engine warm-up bars (belong to no window)")
    p_val.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_val.add_argument("--min-decided", type=int, default=30,
                       help="minimum decided trades per window for a bar check")
    p_val.add_argument("--horizons", default="1,4,24",
                       help="comma-separated hours; verdicts use the first (primary)")
    p_val.add_argument("--train", type=float, default=0.60,
                       help="train window fraction (earliest)")
    p_val.add_argument("--val", type=float, default=0.15,
                       help="validation window fraction")
    p_val.add_argument("--oos", type=float, default=0.15,
                       help="sealed OOS window fraction")
    p_val.add_argument("--recent", type=float, default=0.10,
                       help="sealed recent window fraction (newest)")
    p_val.add_argument("--json", action="store_true",
                       help="machine-readable result")
    p_val.add_argument("--store-root", default=None,
                       help="store root override (default data/store; mirrors backfill --root)")
    p_val.add_argument("--seal-dir", default=None,
                       help="sealed-OOS envelope directory override")
    p_val.add_argument("--reseal", action="store_true",
                       help="re-open the sealed OOS envelope (recorded in seal history)")
    p_val.set_defaults(func=cmd_validate)

    p_edge = sub.add_parser(
        "edge-validate",
        help="P13: honest regime-aware edge verdict on the sealed OOS + recent "
             "windows (EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA)")
    p_edge.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_edge.add_argument("--tf", default=TIMEFRAME)
    p_edge.add_argument("--bars", type=int, default=2000,
                        help="most-recent bars to validate over")
    p_edge.add_argument("--horizons", default="1", help="comma-separated hours; verdict uses the primary")
    p_edge.add_argument("--step", type=int, default=3,
                        help="bar step for the walk-forward scan (1 = every bar)")
    p_edge.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                        help="engine warm-up bars (belong to no window)")
    p_edge.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_edge.add_argument("--min-decided", type=int, default=30,
                        help="minimum decided trades on decisive windows for a claim")
    p_edge.add_argument("--regime-min-decided", type=int, default=10,
                        help="decided trades a regime needs to count as well-sampled")
    p_edge.add_argument("--positive-regime-frac", type=float, default=0.5,
                        help="fraction of well-sampled regimes that must be net-positive")
    p_edge.add_argument("--decisive-windows", default="oos,recent",
                        help="comma-separated windows that count as untouched evidence")
    p_edge.add_argument("--execution", default="none", choices=("none", "slip", "impact"),
                        help="fill model for the walk (none = raw close fill; "
                             "slip/impact = realistic slippage)")
    p_edge.add_argument("--source", default="auto", choices=("auto", "store"),
                        help="auto = live (or demo) client; store = the P10 Parquet series")
    p_edge.add_argument("--exchange", default="binance", help="store venue (binance|bybit|dukascopy)")
    p_edge.add_argument("--market", default="perp", choices=("spot", "perp"),
                        help="store series market label (used with --source store)")
    p_edge.add_argument("--train", type=float, default=0.60)
    p_edge.add_argument("--val", type=float, default=0.15)
    p_edge.add_argument("--oos", type=float, default=0.15)
    p_edge.add_argument("--recent", type=float, default=0.10)
    p_edge.add_argument("--json", action="store_true", help="machine-readable result")
    p_edge.set_defaults(func=cmd_edge_validate)

    p_xau = sub.add_parser(
        "xau-evidence",
        help="P12.12: read-only PAXG-vs-XAU basis + sealed-OOS promotion dossier")
    p_xau.add_argument("--tf", default="15m",
                       help="timeframe stored for both series (default 15m)")
    p_xau.add_argument("--bars", type=int, default=12000,
                       help="most-recent rows read independently from each series")
    p_xau.add_argument("--min-overlap", type=int, default=100,
                       help="minimum exact-time matched bars for a measured basis")
    p_xau.add_argument("--store-root", default=str(ROOT / "data" / "store"),
                       help="CandleStore root containing separately keyed series")
    p_xau.add_argument("--seal-dir", default=str(ROOT / "data" / "store" / "validation"),
                       help="directory holding the Dukascopy XAU validation seal")
    p_xau.add_argument("--json", action="store_true",
                       help="machine-readable research dossier")
    p_xau.set_defaults(func=cmd_xau_evidence)

    p_score = sub.add_parser(
        "scorecard",
        help="P12.3 strategy scorecard — one boxed block (side/regime/session, "
             "Sharpe/Sortino/Calmar, holding time)")
    p_score.add_argument("--source", default="db",
                         choices=("db", "backtest", "paper", "store"),
                         help="db = stored backtest+paper outcomes (default); "
                              "backtest/paper = one book; store = fresh "
                              "walk-forward grade of the stored series")
    p_score.add_argument("--symbol", default=None,
                         help="asset filter / store symbol (BTC, ETH, XAU/GOLD)")
    p_score.add_argument("--tf", default=TIMEFRAME, help="store timeframe")
    p_score.add_argument("--exchange", default="binance",
                         help="stored series venue (binance|bybit)")
    p_score.add_argument("--market", default="perp", help="spot or perp series")
    p_score.add_argument("--bars", type=int, default=1000,
                         help="--source store: most-recent bars to grade")
    p_score.add_argument("--horizons", default="4",
                         help="--source store: comma-separated hours; the "
                              "first is scored")
    p_score.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                         help="--source store: engine warm-up bars")
    p_score.add_argument("--step", type=int, default=3,
                         help="walk-forward bar step used to grade backtest "
                              "rows (overlap correction, P12.3.3)")
    p_score.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_score.add_argument("--min-decided", type=int, default=30,
                         help="minimum decided trades before a verdict is given")
    p_score.add_argument("--exclude-sim", action="store_true",
                         help="drop simulator walk-forward samples (real book only)")
    p_score.add_argument("--since", default=None,
                         help="db sources: score rows at/after this signal bar "
                              "(epoch ms or YYYY-MM-DD) — separates data eras")
    p_score.add_argument("--until", default=None,
                         help="db backtest rows: score rows at/before this "
                              "signal bar (epoch ms or YYYY-MM-DD)")
    p_score.add_argument("--no-costs", action="store_true",
                         help="disable cost modeling (score gross outcomes only)")
    p_score.add_argument("--maker", action="store_true",
                         help="model maker fees instead of default taker fees")
    p_score.add_argument("--conditioned", action="store_true",
                         help="include conditioned splits by funding and CVD order flow")
    p_score.add_argument("--quality", action="store_true",
                         help="P12.4: embed the Backtest Quality Score 0–100 "
                              "for the same book")
    p_score.add_argument("--source-key", default=None,
                         help="P12.11: score ONE price series only — "
                              "'live' (canonical Binance spot), "
                              "'exchange:market[:bid|ask]' e.g. "
                              "dukascopy:spot:bid, or 'all' (default) to pool "
                              "every source and report the mix")
    p_score.add_argument("--json", action="store_true",
                         help="machine-readable result")
    p_score.set_defaults(func=cmd_scorecard)

    p_quality = sub.add_parser(
        "quality",
        help="P12.4 Backtest Quality Score 0–100 with the parameter-plateau "
             "sweep (store-only): re-grades min_confidence ±5 and caps an "
             "isolated-peak edge at 50")
    p_quality.add_argument("--symbol", default=None,
                           help="asset symbol (BTC, ETH, XAU/GOLD)")
    p_quality.add_argument("--tf", default=TIMEFRAME, help="store timeframe")
    p_quality.add_argument("--exchange", default="binance",
                           help="stored series venue (binance|bybit)")
    p_quality.add_argument("--market", default="perp", help="spot or perp series")
    p_quality.add_argument("--bars", type=int, default=1000,
                           help="most-recent bars to grade")
    p_quality.add_argument("--horizons", default="4",
                           help="comma-separated hours; the first is scored")
    p_quality.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                           help="engine warm-up bars")
    p_quality.add_argument("--step", type=int, default=3,
                           help="walk-forward bar step (overlap correction, P12.3.3)")
    p_quality.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE,
                           help="base strategy parameter; swept at ±5")
    p_quality.add_argument("--min-decided", type=int, default=30,
                           help="minimum decided trades before a verdict is given")
    p_quality.add_argument("--no-costs", action="store_true",
                           help="disable cost modeling (score gross outcomes only)")
    p_quality.add_argument("--maker", action="store_true",
                           help="model maker fees instead of default taker fees")
    p_quality.add_argument("--json", action="store_true",
                           help="machine-readable result")
    p_quality.set_defaults(func=cmd_quality)

    p_cal = sub.add_parser(
        "calendar",
        help="P12.9: venue trading calendar — is the market open, and how "
             "much of a stored series' span was scheduled closure?")
    p_cal.add_argument("--symbol", default=None,
                       help="asset symbol (default XAUUSD)")
    p_cal.add_argument("--tf", default="1m", help="store timeframe")
    p_cal.add_argument("--exchange", default="dukascopy",
                       help="stored series venue (binance|bybit|dukascopy)")
    p_cal.add_argument("--market", default="spot", help="spot or perp series")
    p_cal.add_argument("--calendar", default=None,
                       help="force a calendar by name (crypto-24x7|xau-otc)")
    p_cal.add_argument("--at", type=int, default=None,
                       help="UTC epoch ms to evaluate (default: now)")
    p_cal.add_argument("--series", action="store_true",
                       help="also read the stored series and report its "
                            "calendar-aware health")
    p_cal.add_argument("--root", default=None, help="store root override")
    p_cal.add_argument("--json", action="store_true",
                       help="machine-readable result")
    p_cal.set_defaults(func=cmd_calendar)

    p_stats = sub.add_parser("stats", help="what the engine has learned (DB + backtests)")
    p_stats.add_argument("--symbol", default=None, help="optional asset filter (BTC, ETH, XAU/GOLD)")
    p_stats.set_defaults(func=cmd_stats)

    p_rev = sub.add_parser("review", help="list signals awaiting human approval")
    p_rev.add_argument("--symbol", default=None, help="optional asset filter (BTC, ETH, XAU/GOLD)")
    p_rev.set_defaults(func=cmd_review)

    p_app = sub.add_parser("approve", help="approve a pending signal (risk gate enforced)")
    p_app.add_argument("scan_id", type=int)
    p_app.add_argument("--note", default="")
    p_app.add_argument("--force", action="store_true",
                       help="override a closed risk gate consciously")
    p_app.add_argument("--acknowledge-journal", action="store_true",
                       help="approve even though decided real trades are "
                            "unjournaled (W3.3; audited; journal them after)")
    p_app.set_defaults(func=cmd_approve)

    p_rej = sub.add_parser("reject", help="reject a pending signal")
    p_rej.add_argument("scan_id", type=int)
    p_rej.add_argument("--note", default="")
    p_rej.set_defaults(func=cmd_reject)

    p_exec = sub.add_parser("execute", help="mark an approved signal as executed")
    p_exec.add_argument("scan_id", type=int)
    p_exec.add_argument("--note", default="")
    p_exec.set_defaults(func=cmd_execute)

    p_close = sub.add_parser("close", help="close an executed signal (outcome recorded)")
    p_close.add_argument("scan_id", type=int)
    p_close.add_argument("--note", default="")
    p_close.set_defaults(func=cmd_close)

    p_sig = sub.add_parser("signal", help="show a signal's full detail + lifecycle")
    p_sig.add_argument("scan_id", type=int)
    p_sig.set_defaults(func=cmd_signal)

    p_learn = sub.add_parser("learn", help="recompute the self-improvement calibration profile")
    p_learn.add_argument("--json", action="store_true")
    p_learn.set_defaults(func=cmd_learn)

    p_coach = sub.add_parser("coach", help="teaching mode: explain + mentor + personal feedback")
    p_coach.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_coach.add_argument("--tf", default=TIMEFRAME)
    p_coach.add_argument("--bars", type=int, default=BARS)
    p_coach.add_argument("--term", default=None, help="explain a glossary term (e.g. FVG)")
    p_coach.set_defaults(func=cmd_coach)

    p_gl = sub.add_parser("glossary", help="list trading terms used by the engine")
    p_gl.add_argument("term", nargs="?", default=None)
    p_gl.set_defaults(func=cmd_glossary)

    p_intel = sub.add_parser("intelligence", help="professional AI trading desk report (JSON or card)")
    p_intel.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_intel.add_argument("--tf", default=TIMEFRAME)
    p_intel.add_argument("--bars", type=int, default=BARS)
    p_intel.add_argument("--card", action="store_true", help="render institutional terminal signal card")
    p_intel.set_defaults(func=cmd_intelligence)

    p_card = sub.add_parser("card", help="render Institutional AI Signal Card v2.0")
    p_card.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_card.add_argument("--tf", default=TIMEFRAME)
    p_card.add_argument("--bars", type=int, default=BARS)
    p_card.add_argument("--json", action="store_true", help="output card as raw JSON")
    p_card.set_defaults(func=cmd_card)

    p_an = sub.add_parser("analyze", help="full human-trader analysis (MTF + context + styles + memory)")
    p_an.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_an.add_argument("--tf", default=TIMEFRAME)
    p_an.add_argument("--bars", type=int, default=BARS)
    p_an.add_argument("--json", action="store_true")
    p_an.set_defaults(func=cmd_analyze)

    p_st = sub.add_parser("state", help="show the AI's remembered market state + event log")
    p_st.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_st.add_argument("--tf", default=TIMEFRAME)
    p_st.set_defaults(func=cmd_state)

    p_risk = sub.add_parser("risk", help="risk & discipline gate status (daily/weekly/drawdown/progression)")
    p_risk.set_defaults(func=cmd_risk)

    p_monte = sub.add_parser("monte", help="Monte Carlo risk-of-ruin table (expected DD / ruin prob / streak / TTR)")
    p_monte.add_argument("--risk-pcts", default="0.25,0.5,1.0,1.5,2.0",
                         help="comma-separated risk percentages per trade to sweep")
    p_monte.add_argument("--ruin-threshold", type=float, default=50.0,
                         help="drawdown %% that counts as ruin (default 50)")
    p_monte.add_argument("--samples", type=int, default=2000,
                         help="Monte Carlo samples (default 2000)")
    p_monte.add_argument("--seed", type=int, default=None,
                         help="RNG seed for reproducible output")
    p_monte.add_argument("--json", action="store_true", help="raw JSON output")
    p_monte.set_defaults(func=cmd_monte)

    p_st2 = sub.add_parser("sourcetrust", help="record a source's information tier (1-5) + trust (0-1)")
    p_st2.add_argument("source")
    p_st2.add_argument("tier", type=int, choices=(1, 2, 3, 4, 5))
    p_st2.add_argument("trust", type=float)
    p_st2.add_argument("--note", default="")
    p_st2.set_defaults(func=cmd_sourcetrust)

    p_ts = sub.add_parser("tradestate", help="set/clear behavioral no-trade flags (angry/tired/revenge/chasing)")
    p_ts.add_argument("--angry", action="store_true", default=None)
    p_ts.add_argument("--tired", action="store_true", default=None)
    p_ts.add_argument("--revenge", action="store_true", default=None)
    p_ts.add_argument("--chasing", action="store_true", default=None)
    p_ts.add_argument("--clear", action="store_true", help="clear all flags")
    p_ts.add_argument("--note", default="")
    p_ts.set_defaults(func=cmd_tradestate)

    p_j = sub.add_parser("journal", help="professional trading journal (post-trade fields + execution quality)")
    p_j.add_argument("scan_id", nargs="?", type=int, default=None)
    p_j.add_argument("--followed-rules", type=int, choices=(0, 1), default=None,
                     help="1 = followed the system, 0 = broke the rules (the headline field)")
    p_j.add_argument("--emotion", default="", help="calm/anxious/euphoric/fearful/frustrated/greedy/...")
    p_j.add_argument("--mistake", default="")
    p_j.add_argument("--screenshot", default="", help="path to chart screenshot")
    p_j.add_argument("--would-change", default="")
    p_j.add_argument("--notes", default="")
    p_j.set_defaults(func=cmd_journal)

    p_web = sub.add_parser("web", help="run the web dashboard")
    p_web.add_argument("--host", default=None)
    p_web.add_argument("--port", type=int, default=None)
    p_web.set_defaults(func=cmd_web)

    p_ask = sub.add_parser("ask", help="grounded RAG question over the trading library (with citations)")
    p_ask.add_argument("question")
    p_ask.add_argument("--top-k", type=int, default=3)
    p_ask.add_argument("--llm", action="store_true",
                       help="narrate the grounded answer with the LLM (if configured)")
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    p_pr = sub.add_parser("postreview", help="post-trade review for a closed scan (R, MAE/MFE, discipline)")
    p_pr.add_argument("scan_id", type=int)
    p_pr.add_argument("--json", action="store_true")
    p_pr.set_defaults(func=cmd_postreview)

    p_agent = sub.add_parser("agent", help="desk agent: morning, health, ask, all, watchdog, paper-reviewer, weekly-review")
    p_agent.set_defaults(func=cmd_agent)
    a_sub = p_agent.add_subparsers(dest="action", required=True)
    p_morning = a_sub.add_parser("morning", help="morning briefing across the watchlist")
    p_morning.add_argument("--symbols", default=None,
                           help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_morning.add_argument("--tf", default=TIMEFRAME)
    p_morning.add_argument("--bars", type=int, default=BARS)
    p_morning.add_argument("--save", action="store_true",
                           help="also persist each scan to the signal database")
    p_morning.add_argument("--json", action="store_true")
    p_health_a = a_sub.add_parser("health", help="system health report")
    p_health_a.add_argument("--json", action="store_true")
    p_ask_a = a_sub.add_parser("ask", help="ask the desk a natural-language question")
    p_ask_a.add_argument("question")
    p_ask_a.add_argument("--symbol", default=None, help="asset context (BTC, ETH, GOLD)")
    p_ask_a.add_argument("--tf", default=TIMEFRAME)
    p_ask_a.add_argument("--bars", type=int, default=BARS)
    p_ask_a.add_argument("--json", action="store_true")
    p_all_a = a_sub.add_parser("all", help="one desk run: health + briefing + graduation")
    p_all_a.add_argument("--symbols", default=None,
                         help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_all_a.add_argument("--tf", default=TIMEFRAME)
    p_all_a.add_argument("--bars", type=int, default=BARS)
    p_all_a.add_argument("--save", action="store_true",
                         help="also persist each scan to the signal database")
    p_all_a.add_argument("--json", action="store_true")
    # Autonomous desk agents (brain/agents.py) — audit-logged to agent_runs
    for name, helptext in (
            ("watchdog", "paper-trade monitoring + stale-cleanup alarms"),
            ("paper-reviewer", "post-mortem aggregation over closed paper trades"),
            ("weekly-review", "metrics, rule-compliance and change detection")):
        p_auto = a_sub.add_parser(name, help=helptext)
        p_auto.add_argument("--json", action="store_true")

    p_brief = sub.add_parser("brief", help="daily desk briefing (alias for `agent morning`)")
    p_brief.add_argument("--symbols", default=None,
                         help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_brief.add_argument("--tf", default=TIMEFRAME)
    p_brief.add_argument("--bars", type=int, default=BARS)
    p_brief.add_argument("--save", action="store_true",
                         help="also persist each scan to the signal database")
    p_brief.add_argument("--json", action="store_true")
    p_brief.set_defaults(func=cmd_brief)

    p_health = sub.add_parser("health", help="system health (data feeds, DB, risk gate, MCP)")
    p_health.add_argument("--json", action="store_true")
    p_health.set_defaults(func=cmd_health)

    p_desk = sub.add_parser(
        "desk",
        help="one-call desk advisory: risk gate + P&L + graduation + next agent + advice",
    )
    p_desk.add_argument("--json", action="store_true")
    p_desk.set_defaults(func=cmd_desk)

    p_daily = sub.add_parser(
        "daily",
        help="10-minute daily ritual: readiness + loop health + gate + journal prompt",
    )
    p_daily.add_argument("--json", action="store_true")
    p_daily.add_argument("--brief", action="store_true",
                         help="also run the morning briefing (scans the watchlist)")
    p_daily.add_argument("--tf", default=TIMEFRAME)
    p_daily.add_argument("--bars", type=int, default=BARS)
    p_daily.set_defaults(func=cmd_daily)

    p_loop = sub.add_parser(
        "loop-health",
        help="alias for `daily` — the one loop-health number",
    )
    p_loop.add_argument("--json", action="store_true")
    p_loop.add_argument("--brief", action="store_true",
                        help="also run the morning briefing (scans the watchlist)")
    p_loop.add_argument("--tf", default=TIMEFRAME)
    p_loop.add_argument("--bars", type=int, default=BARS)
    p_loop.set_defaults(func=cmd_daily)

    p_wk = sub.add_parser(
        "weekly",
        help="weekly trader review: this week vs all time, R distribution, "
             "violations, graduation tracker, next practice task",
    )
    p_wk.add_argument("--json", action="store_true")
    p_wk.add_argument("--days", type=int, default=7,
                      help="review window in days (default 7)")
    p_wk.add_argument("--export", default=None,
                      help="also write the full JSON review to this path")
    p_wk.set_defaults(func=cmd_weekly)

    p_pr = sub.add_parser(
        "practice",
        help="practice calibration: desk-agreement plus replay-tape outcomes, "
             "agreement rates, weakest component, one coaching takeaway",
    )
    p_pr.add_argument("--json", action="store_true")
    p_pr.add_argument("--days", type=int, default=30,
                      help="window in days (default 30)")
    p_pr.set_defaults(func=cmd_practice)

    p_preflight = sub.add_parser(
        "preflight",
        help="strict safety/readiness gate before unattended live paper trading",
    )
    p_preflight.add_argument("--json", action="store_true")
    p_preflight.add_argument(
        "--allow-demo", action="store_true",
        help="allow sample/synthetic data for a rehearsal (not live evidence)",
    )
    p_preflight.set_defaults(func=cmd_preflight)

    p_sim = sub.add_parser("simulator",
                           help="grind unique backtest + paper samples per setup (A6/B10)")
    p_sim.add_argument("--rounds", type=int, default=1, help="rounds to run (default 1)")
    p_sim.add_argument("--symbols", default=None,
                       help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_sim.add_argument("--tf", default=TIMEFRAME)
    p_sim.add_argument("--bars", type=int, default=600, help="history bars per symbol")
    p_sim.add_argument("--step", type=int, default=3, help="window step (1 = every bar)")
    p_sim.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_sim.add_argument("--horizons", default="1,4,24",
                       help="comma-separated forward horizons in hours")
    p_sim.add_argument("--source", default="auto", choices=("auto", "store"),
                       help="auto = live (or demo) client; store = the P10 Parquet "
                            "series (offline, P12.3.2 real data)")
    p_sim.add_argument("--exchange", default="binance",
                       help="store venue (binance|bybit|dukascopy)")
    p_sim.add_argument("--market", default="spot", choices=("spot", "perp"),
                       help="store series market label (used with --source store)")
    p_sim.add_argument("--dry-run", action="store_true",
                       help="compute what WOULD be added without storing anything")
    p_sim.add_argument("--json", action="store_true")
    p_sim.set_defaults(func=cmd_simulator)

    p_bf = sub.add_parser(
        "backfill",
        help="P10: paginated REST candle backfill into the Parquet store "
             "(resumable, rate-limit aware, idempotent)")
    p_bf.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_bf.add_argument("--tf", default="1m")
    p_bf.add_argument("--exchange", default="binance", choices=("binance", "bybit"),
                      help="venue to backfill (P10.6: bybit pages the V5 klines endpoint)")
    p_bf.add_argument("--market", default="perp", choices=("spot", "perp"),
                      help="spot (/api/v3/klines or V5 spot) or perp (/fapi/v1/klines or V5 linear)")
    p_bf.add_argument("--start-ts", type=int, default=None,
                      help="inclusive candle OPEN (UTC epoch ms)")
    p_bf.add_argument("--end-ts", type=int, default=None,
                      help="stop at this candle OPEN (UTC epoch ms)")
    p_bf.add_argument("--since", default=None,
                      help="alternative to --start-ts: epoch ms, YYYY-MM-DD, or Nd (e.g. 90d)")
    p_bf.add_argument("--until", default=None,
                      help="alternative to --end-ts: epoch ms, YYYY-MM-DD, or Nd")
    p_bf.add_argument("--page-limit", type=int, default=1000)
    p_bf.add_argument("--sleep", type=float, default=0.2,
                      help="seconds between pages (rate-limit courtesy)")
    p_bf.add_argument("--no-sleep", action="store_true")
    p_bf.add_argument("--no-resume", action="store_true",
                      help="ignore already-stored tail; re-walk the range")
    p_bf.add_argument("--max-requests", type=int, default=5000,
                      help="safety cap on requests per run; 0 = unlimited. "
                           "An interrupted run resumes on re-run")
    p_bf.add_argument("--dry-run", action="store_true",
                      help="fetch + count only; write nothing")
    p_bf.add_argument("--repair", action="store_true",
                      help="P10.3: detect + fetch missing 1m holes")
    p_bf.add_argument("--rollup", action="store_true",
                      help="P10.3: aggregate stored 1m → 5m/15m/1h/4h/1d")
    p_bf.add_argument("--from-csv", default=None, metavar="PATH",
                      help="import local OHLCV CSV(.gz) through validation — "
                           "Binance Vision/klines or dukascopy-node format")
    p_bf.add_argument("--csv-source", default="binance",
                      choices=("binance", "dukascopy"),
                      help="CSV provenance; dukascopy stores a separate "
                           "dukascopy/spot series (never relabelled Binance)")
    p_bf.add_argument("--price-type", default="bid", choices=("bid", "ask"),
                      help="dukascopy-node candle side (default bid; ignored "
                           "for Binance CSV)")
    p_bf.add_argument("--csv-sha256", default=None, metavar="HEX",
                      help="provenance pin: refuse to import unless the "
                           "decompressed CSV matches this sha256")
    p_bf.add_argument("--root", default=None, help="CandleStore root (tests)")
    p_bf.add_argument("--json", action="store_true")
    p_bf.set_defaults(func=cmd_backfill)

    p_der = sub.add_parser(
        "derivatives",
        help="P10.4: collect/inspect derivatives time series (funding / OI / mark / index / basis)")
    der_sub = p_der.add_subparsers(dest="subcmd", required=True)
    p_der_c = der_sub.add_parser("collect", help="paginated derivatives history into the Parquet store")
    p_der_c.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_der_c.add_argument("--market", default="perp", choices=("perp",),
                         help="derivatives exist for perp markets only")
    p_der_c.add_argument("--since", type=int, default=None,
                         help="first record (UTC epoch ms); default: resume after the last stored one")
    p_der_c.add_argument("--until", type=int, default=None,
                         help="last record (UTC epoch ms); default: now")
    p_der_c.add_argument("--metrics", default=None,
                         help="comma-separated: funding_rate,open_interest,open_interest_value,"
                              "mark_price,index_price,basis (default: all)")
    p_der_c.add_argument("--sleep", type=float, default=0.2,
                         help="seconds between pages (rate-limit courtesy)")
    p_der_c.add_argument("--dry-run", action="store_true", help="fetch + count only")
    p_der_c.add_argument("--json", action="store_true")
    p_der_c.set_defaults(func=cmd_derivatives)
    p_der_s = der_sub.add_parser("status", help="what derivatives series are stored")
    p_der_s.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_der_s.add_argument("--market", default="perp", choices=("perp",))
    p_der_s.add_argument("--json", action="store_true")
    p_der_s.set_defaults(func=cmd_derivatives)

    p_cross = sub.add_parser(
        "cross",
        help="P10.7: collect/inspect cross-exchange premium/discount + funding spread")
    cross_sub = p_cross.add_subparsers(dest="subcmd", required=True)
    p_cross_c = cross_sub.add_parser(
        "collect", help="persist the probe snapshot + derive Binance-vs-Bybit series")
    p_cross_c.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_cross_c.add_argument("--market", default="perp", choices=("spot", "perp"),
                           help="candle-store market used for historical premium")
    p_cross_c.add_argument("--tf", default="1m",
                           help="candle timeframe used for historical premium")
    p_cross_c.add_argument("--since", type=int, default=None,
                           help="first record (UTC epoch ms)")
    p_cross_c.add_argument("--until", type=int, default=None,
                           help="last record (UTC epoch ms); default: now")
    p_cross_c.add_argument("--sleep", type=float, default=0.2,
                           help="seconds between Bybit funding pages")
    p_cross_c.add_argument("--no-snapshot", action="store_true",
                           help="skip the live/fake probe snapshot; derive only")
    p_cross_c.add_argument("--dry-run", action="store_true",
                           help="compute only; write nothing")
    p_cross_c.add_argument("--root", default=None, help="CrossExchangeStore root (tests)")
    p_cross_c.add_argument("--candle-root", default=None, help="CandleStore root override")
    p_cross_c.add_argument("--deriv-root", default=None, help="DerivativesStore root override")
    p_cross_c.add_argument("--json", action="store_true")
    p_cross_c.set_defaults(func=cmd_cross)
    p_cross_s = cross_sub.add_parser("status", help="what cross-exchange series are stored")
    p_cross_s.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_cross_s.add_argument("--root", default=None, help="CrossExchangeStore root (tests)")
    p_cross_s.add_argument("--json", action="store_true")
    p_cross_s.set_defaults(func=cmd_cross)

    p_st = sub.add_parser("store", help="inspect the P10 Parquet candle store (count/span/partitions)")
    p_st.add_argument("--exchange", default="binance")
    p_st.add_argument("--market", default="perp", choices=("spot", "perp"))
    p_st.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_st.add_argument("--tf", default="1m", help="timeframe")
    p_st.add_argument("--demo", action="store_true",
                      help="inspect the demo store (data/store_demo) instead of the real one")
    p_st.add_argument("--root", default=None, help="CandleStore root override")
    p_st.add_argument("--json", action="store_true")
    p_st.set_defaults(func=cmd_store)

    p_mcp = sub.add_parser("mcp", help="run the Model Context Protocol server (stdio)")
    p_mcp.set_defaults(func=cmd_mcp)

    p_corr = sub.add_parser(
        "correlation",
        help="measured BTC/ETH/GOLD correlation matrix + ETH/BTC beta (read-only)")
    p_corr.add_argument("--symbols", default=None,
                        help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_corr.add_argument("--tf", default="1h")
    p_corr.add_argument("--bars", type=int, default=300)
    p_corr.add_argument("--window", type=int, default=60,
                        help="rolling window of aligned returns")
    p_corr.add_argument("--json", action="store_true")
    p_corr.set_defaults(func=cmd_correlation)

    # ── Agent-Reach-inspired surface (P7/P8, additive) ────────────────
    # `doctor` is a non-mutating readiness report: data feeds, DB, risk
    # gate, MCP, and the per-channel backend registry.  Default inspect
    # only; --json is machine-readable; --fix is reserved for future
    # opt-in prescription execution (currently a no-op).
    p_doc = sub.add_parser(
        "doctor",
        help="non-mutating readiness report (channels + immune + risk gate + data quality)")
    p_doc.add_argument("--json", action="store_true")
    p_doc.add_argument("--strip", action="store_true",
                       help="print only the combined readiness strip "
                            "(one line per pillar) instead of the full report")
    p_doc.set_defaults(func=cmd_doctor)

    # `channels` lists the per-source backend registry + active backend.
    # Read-only; never mutates anything.
    p_ch = sub.add_parser(
        "channels",
        help="per-source backend registry (cryptodada / discord / news / llm) with active backend")
    p_ch.add_argument("--json", action="store_true")
    p_ch.set_defaults(func=cmd_channels)

    # `skill` exposes SKILL.md to agents and agent runtimes.
    # Default is inspect-only: prints the SKILL to stdout.  --install /
    # --uninstall require --system (matches Agent-Reach's safety posture:
    # never write under $HOME without explicit operator consent).
    p_skill = sub.add_parser(
        "skill",
        help="print or install the agent-facing SKILL.md (default: print to stdout)")
    p_skill.add_argument("--print", action="store_true", default=True,
                         help="print the SKILL.md to stdout (default behaviour)")
    p_skill.add_argument("--install", action="store_true",
                         help="install SKILL.md into the local agent skills dir (requires --system)")
    p_skill.add_argument("--uninstall", action="store_true",
                         help="remove a previously installed SKILL.md (requires --system)")
    p_skill.add_argument("--system", action="store_true",
                         help="permit writing under $HOME; required for --install / --uninstall")
    p_skill.add_argument("--dry-run", action="store_true",
                         help="preview install/uninstall without writing")
    p_skill.add_argument("--target-dir", default=None,
                         help="override the install directory (default: ~/.claude/skills/cryptobrain)")
    p_skill.set_defaults(func=cmd_skill)

    # ── P19 Ubuntu Hub ────────────────────────────────────────────────
    p_rel = sub.add_parser(
        "release",
        help="P22.3 signing + clean-target drills (catalog / evidence check)")
    p_rel.set_defaults(func=cmd_release)
    p_rel.add_argument("release_action", nargs="?", default="drills",
                       choices=("drills", "sign-plan", "status", "check"))
    p_rel.add_argument("--drill", default="",
                       help="check: drill id from the catalog")
    p_rel.add_argument("--evidence", default="",
                       help="check: path to operator evidence JSON")
    p_rel.add_argument("--evidence-dir", default=None,
                       help="directory of <drill-id>.json files")
    p_rel.add_argument("--json", action="store_true")

    p_comp = sub.add_parser(
        "companion",
        help="P20 Windows / P21 Android companion: spec, validate-url, status (unsigned recipe)")
    p_comp.set_defaults(func=cmd_companion)
    p_comp.add_argument("companion_action", nargs="?", default="spec",
                        choices=("spec", "validate-url", "status", "lint"))
    p_comp.add_argument("--platform", choices=("windows", "android"), default="windows",
                        help="which companion contract to report (default: windows)")
    p_comp.add_argument("--hub", default="https://127.0.0.1")
    p_comp.add_argument("--state", default=None)
    p_comp.add_argument("--json", action="store_true")

    p_hub = sub.add_parser(
        "hub",
        help="Ubuntu Hub: setup, status, backup/restore, doctor, diagnostics, uninstall")
    p_hub.set_defaults(func=cmd_hub)
    p_hub.add_argument("hub_action",
                       choices=("setup", "status", "logs", "backup",
                                "restore", "doctor", "diagnostics", "uninstall",
                                "first-night", "pair"),
                       help="hub subcommand")
    p_hub.add_argument("--mode", choices=("local", "remote"), default="local",
                       help="setup: local-only or remote-behind-TLS")
    p_hub.add_argument("--owner", default="",
                       help="setup: owner hint (password still created in the UI)")
    p_hub.add_argument("--prefix", default=None,
                       help="sandbox FHS prefix (tests / dry hosts)")
    p_hub.add_argument("--archive", default=None,
                       help="restore input, or diagnostics output .tar.gz path")
    p_hub.add_argument("--overwrite", action="store_true",
                       help="setup: rewrite env; restore: replace existing data")
    p_hub.add_argument("--purge", action="store_true",
                       help="uninstall: also delete /etc/sky and /var/lib/sky")
    p_hub.add_argument("--no-store", action="store_true",
                       help="backup: skip the Parquet store")
    p_hub.add_argument("--platform", choices=("windows", "android"), default="windows",
                       help="pair: which companion client the code is for (default: windows)")
    p_hub.add_argument("--retention-days", type=int, default=14)
    p_hub.add_argument("--unit", default="sky-dashboard.service")
    p_hub.add_argument("--lines", type=int, default=80)
    p_hub.add_argument("--json", action="store_true")

    # ── hidden alpha CLI (regime + CVD + kelly + MAE/MFE + Monte Carlo) ──
    p_hidden = sub.add_parser(
        "hidden", help="hidden alpha layer: regime, CVD, kelly, MAE/MFE, Monte Carlo")
    # ── 24/7 SKY Intelligence Agent (research & monitoring, never trades) ──
    p_sa = sub.add_parser("sky-agent", help="24/7 SKY Intelligence & Research Agent (discovery doc: docs/DISCOVERY_2026-08-19_AGENT.md)")
    p_sa.set_defaults(func=cmd_sky_agent)
    p_sa.add_argument("sky_agent_action", nargs="?", default="health", choices=("health", "status", "collect", "report", "run", "hypothesize"), help="health|status|collect|report|run|hypothesize")
    p_sa.add_argument("--json", action="store_true", help="machine-readable JSON")
    p_sa.add_argument("--demo", action="store_true", help="offline deterministic demo (no network)")
    p_sa.add_argument("--target", default="all", choices=("all", "market", "system", "edgar", "news"), help="collect: which poller")
    p_sa.add_argument("--hypothesis-id", default=None, help="hypothesize: which H-XXX to backtest")
    p_sa.add_argument("--symbol", default=SYMBOL, help="hypothesis symbol")
    p_sa.add_argument("--tf", default=TIMEFRAME, help="hypothesis timeframe")
    p_sa.add_argument("--max-ticks", type=int, default=None, help="run: cap ticks (tests)")

    p_hidden.set_defaults(func=cmd_hidden)
    p_hidden.add_argument("--symbol", default=SYMBOL,
                          help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_hidden.add_argument("--tf", default=TIMEFRAME)
    p_hidden.add_argument("--bars", type=int, default=BARS)
    h_sub = p_hidden.add_subparsers(dest="subcmd", required=False)
    # hidden chart_read [SYMBOL]
    p_cr = h_sub.add_parser("chart_read", help="HMM regime + CVD + kelly (advisory)")
    p_cr.add_argument("symbol", nargs="?", default=None,
                      help="asset (defaults to configured symbol)")
    p_cr.add_argument("--tf", default=TIMEFRAME, help="timeframe")
    p_cr.add_argument("--bars", type=int, default=BARS, help="number of bars")
    # hidden analytics mae|mc [SYMBOL]
    p_an = h_sub.add_parser("analytics", help="MAE/MFE summary or Monte Carlo equity")
    p_an.add_argument("analytics_subcmd", choices=["mae", "mc"],
                      help="mae | mc")
    p_an.add_argument("symbol", nargs="?", default=None,
                      help="asset (defaults to configured symbol)")
    p_an.add_argument("--tf", default=TIMEFRAME, help="timeframe (unused for analytics)")
    p_an.add_argument("--plan-type", default=None,
                      help="filter MAE/MFE summary by plan type")
    p_an.add_argument("--samples", type=int, default=2000,
                      help="Monte Carlo samples (analytics mc only)")
    p_an.add_argument("--seed", type=int, default=None,
                      help="Monte Carlo RNG seed")

    args = ap.parse_args(argv)
    if args.cmd == "scan" and args.symbols is None:
        args.symbols = args.symbol
    if args.cmd is None:
        # Default: open the all-in-one dashboard (watch everything + click to approve)
        from web.app import make_app, serve
        print("=" * 62)
        print(f"🧠 SKY v{VERSION} — Trading Workstation")
        print(f"   open  http://localhost:{DASHBOARD_PORT}")
        print("")
        print("   Everything is clickable in the browser — no command to memorize:")
        print("     📊 Chart          candles, EMA/VWAP/Bollinger, RSI, MACD, S/R, entry/SL/TP")
        print("     🎯 Signal desk    BUY / SELL / NO TRADE with the reason and invalidation")
        print("     ⚡ Trades         approve · reject · execute · close (paper only)")
        print("     🎛 Trade manager  open positions, live R, MAE/MFE, management steps")
        print("     🛡 Risk center    gate, loss budgets, trader state, position-size calculator")
        print("     📓 Journal        a real form: rules, emotion, mistake, what to change")
        print("     🧑‍🏫 Learning       backtest, calibrate, scorecard, simulator")
        print("     ⌘ Command center EVERY CLI command as a button, with its output")
        print("     🧩 Modules        what every part of the engine does")
        print("     ⚙️ System         data health, channels, doctor, MCP")
        print("")
        print("   The desk is advisory. You approve every trade. Paper only —")
        print("   no exchange key exists in this app, so no real order can be sent.")
        print("=" * 62)
        serve(make_app(), DASHBOARD_HOST, DASHBOARD_PORT)
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
