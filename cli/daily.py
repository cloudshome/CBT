"""cli/daily.py — the daily desk command cluster (scan/watch/sources/...).

Refactor step 3 of the main.py maintainability debt (ROADMAP §19): the daily
operations commands used to live inline in ``main.py``; they live here now,
byte-identical, and ``main`` re-exports them so the argparse wiring keeps
working unchanged.
"""
from __future__ import annotations

import json
import time
import sys

from config import DASHBOARD_HOST, DASHBOARD_PORT, TIMEFRAME, BARS
from cli.common import _sym, _symbols, run_scan
from output.notifiers import notify_all


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
