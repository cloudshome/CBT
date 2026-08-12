"""brain/agent.py — the desk agent: health, morning briefing, natural-language ask.

This is the "agent layer" the professional trading mode exposes everywhere:

  * `python main.py agent morning`   — one briefing across the whole watchlist
                                     (desk decisions, risk gate, exposure, queue)
  * `python main.py agent health`    — system health (data feeds, DB, risk gate,
                                     learning store, MCP, LLM)
  * `python main.py agent ask "…"`   — natural-language question to the desk
  * MCP tools and dashboard panels   — /api/health, /api/agents, /api/ask render
                                     exactly the same data

Everything is best-effort: a blocked feed degrades to a note instead of an
error, so a morning briefing never fails because one context source is down.
"""
from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime, timezone

from config import (VERSION, SYMBOLS, TIMEFRAME, BARS, LLM_PROVIDER, DB_PATH,
                    PROGRESSION, PROGRESSION_LEVELS, CALIBRATE_MIN_N,
                    CALIBRATE_MIN_PAPER_N)
from data.symbols import parse_symbol_list
from data.sample_client import maybe_client


# ── health ────────────────────────────────────────────────────────────────

def _data_mode() -> dict:
    if os.getenv("DEMO_MODE", "0") in ("1", "true", "yes"):
        return {"mode": "demo", "provider": "sample client (synthetic/committed data)",
                "live": False,
                "note": "DEMO_MODE=1 — no live market data; set DEMO_MODE=0 for Binance"}
    return {"mode": "live", "provider": "binance", "live": True,
            "note": "live Binance market data"}


def _probe_data(client) -> dict:
    """Best-effort per-symbol data probe with candle-freshness metadata."""
    out: dict[str, dict] = {}
    now_ms = int(time.time() * 1000)
    for symbol in SYMBOLS:
        try:
            df = client.klines(symbol, "15m", 60)
            ok = df is not None and len(df) >= 10
            last_ts = None
            age_seconds = None
            if df is not None and len(df) and "ts" in df:
                raw_ts = int(float(df["ts"].iloc[-1]))
                # Accept seconds as well as the millisecond timestamps used by
                # Binance. Tolerate only tiny negative ages from clock skew;
                # preflight must still detect materially future-dated candles.
                last_ts = raw_ts * 1000 if raw_ts < 1_000_000_000_000 else raw_ts
                raw_age_seconds = (now_ms - last_ts) / 1000
                if -60 <= raw_age_seconds < 0:
                    raw_age_seconds = 0
                age_seconds = round(raw_age_seconds, 1)
            out[symbol] = {
                "ok": bool(ok),
                "bars": 0 if df is None else len(df),
                "last": None if df is None or not len(df) else float(df["close"].iloc[-1]),
                "last_ts": last_ts,
                "age_seconds": age_seconds,
            }
            if not ok:
                out[symbol]["error"] = "too few bars returned"
        except Exception as exc:
            out[symbol] = {"ok": False, "bars": 0, "error": f"{type(exc).__name__}: {exc}"}
    return out


# Public 15m-candle endpoints for the multi-exchange price cross-check
# (BLUEPRINT: "multi-exchange price verification"). No keys required.
_CROSS_EXCHANGES: dict[str, dict] = {
    "kucoin": {
        "url": "https://api.kucoin.com/api/v1/market/candles?type=15min&symbol={sym}",
        "symbols": {"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT",
                    "XAUUSD": "PAXG-USDT"},
        # KuCoin returns candles newest-first:
        # [time, open, close, high, low, volume, turnover].
        "latest_idx": 0,
        "close_idx": 2,
    },
    "okx": {
        "url": "https://www.okx.com/api/v5/market/candles?instId={sym}&bar=15m&limit=1",
        "symbols": {"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT",
                    "XAUUSD": "PAXG-USDT"},
        # OKX also returns newest-first: [ts, o, h, l, c, vol, ...].
        "latest_idx": 0,
        "close_idx": 4,
    },
}


def _cross_exchange_probe(binance_last: dict) -> dict:
    """Best-effort price cross-check: Binance vs KuCoin + OKX (public APIs).

    Flags deviations > 1%. Every exchange call is wrapped — an unreachable
    exchange degrades to a note instead of failing the health report.
    """
    import requests
    out = {"ok": True, "note": "multi-exchange cross-check (KuCoin + OKX public)",
           "threshold_pct": 1.0, "exchanges": {}}
    for name, cfg in _CROSS_EXCHANGES.items():
        ex: dict = {"ok": False, "symbols": {}}
        for our, theirs in cfg["symbols"].items():
            last = binance_last.get(our)
            if last is None:
                continue
            try:
                resp = requests.get(cfg["url"].format(sym=theirs), timeout=6)
                candles = (resp.json() or {}).get("data") or []
                if not candles:
                    ex["symbols"][our] = {"error": "no candles in response"}
                    continue
                price = float(candles[cfg["latest_idx"]][cfg["close_idx"]])
                dev = round((price / last - 1.0) * 100.0, 3)
                ex["symbols"][our] = {"price": round(price, 4),
                                      "deviation_pct": dev,
                                      "flag": abs(dev) > 1.0}
                ex["ok"] = True
            except Exception as exc:
                ex["symbols"][our] = {"error": f"{type(exc).__name__}: {exc}"}
        if not ex["symbols"]:
            ex["note"] = "no symbols compared (no live Binance prices)"
        out["exchanges"][name] = ex
        if not ex["ok"]:
            out["ok"] = False
    return out


def health_report() -> dict:
    """One JSON-able health snapshot used by `agent health`, /api/health, MCP."""
    report: dict = {
        "ok": False,
        "version": VERSION,
        "python": platform.python_version(),
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": _data_mode(),
    }
    try:
        from data.database import SignalDB
        with SignalDB() as db:
            counts = db.conn.execute(
                "SELECT (SELECT COUNT(*) FROM scans) scans,"
                " (SELECT COUNT(*) FROM backtest_results) backtests,"
                " (SELECT COUNT(*) FROM paper_trades) paper,"
                " (SELECT COUNT(*) FROM calibration) calibration_entries"
            ).fetchone()
            report["database"] = {
                "ok": True, "path": str(db.path),
                "scans": counts["scans"], "backtest_samples": counts["backtests"],
                "paper_samples": counts["paper"],
                "calibration_entries": counts["calibration_entries"],
            }
    except Exception as exc:
        report["database"] = {"ok": False, "path": str(DB_PATH),
                              "error": f"{type(exc).__name__}: {exc}"}

    try:
        from brain.risk_gate import evaluate as gate_evaluate
        from brain.risk_gate import progression as progression_info
        with SignalDB() as db:
            gate = gate_evaluate(db)
            report["risk_gate"] = {
                "allowed": gate["allowed"],
                "blocked_by": gate.get("blocked_by", []),
                "progression": progression_info(),
                "details": {k: gate.get("details", {}).get(k) for k in
                            ("daily_weekly", "drawdown", "trader_state",
                             "effective_risk", "enforced")},
            }
    except Exception as exc:
        report["risk_gate"] = {"allowed": False, "blocked_by": [f"unavailable: {exc}"]}

    try:
        from data.database import SignalDB
        with SignalDB() as db:
            report["pending_reviews"] = len(db.pending_reviews())
            calib = db.load_calibration()
        proven = [k for k, v in calib.items() if v.get("proven")]
        report["learning"] = {
            "calibration_entries": len(calib),
            "proven_setups": proven,
        }
    except Exception:
        report["pending_reviews"] = 0
        report["learning"] = {"calibration_entries": 0, "proven_setups": []}

    try:
        client = maybe_client()
        report["data"]["probe"] = _probe_data(client)
        report["data"]["ok"] = any(v.get("ok") for v in report["data"]["probe"].values())
    except Exception as exc:
        report["data"]["probe"] = {}
        report["data"]["ok"] = False
        report["data"]["error"] = f"{type(exc).__name__}: {exc}"

    # Multi-exchange verification only makes sense against real Binance prices.
    if report["data"].get("mode") == "live":
        report["data"]["cross_exchange"] = _cross_exchange_probe({
            sym: v.get("last") for sym, v in report["data"]["probe"].items()
            if v.get("ok")})
    else:
        report["data"]["cross_exchange"] = {
            "ok": False,
            "note": "skipped — demo data (no live Binance prices to compare)"}

    # MCP + LLM availability (informational; neither is required for the engine)
    try:
        import mcp  # noqa: F401
        report["mcp"] = {"available": True, "note": "run `python main.py mcp`"}
    except Exception:
        report["mcp"] = {"available": False,
                         "note": "mcp package not installed (pip install mcp)"}
    report["llm"] = {"provider": LLM_PROVIDER, "enabled": False}
    try:
        from ai.llm_brain import LLMBrain
        report["llm"]["enabled"] = LLMBrain().enabled
    except Exception:
        pass

    report["ok"] = bool(report.get("database", {}).get("ok")) and \
        bool(report.get("data", {}).get("ok"))
    return report


def format_health(report: dict) -> str:
    """Human-readable block for `python main.py agent health` / `health`."""
    lines = ["=" * 66, f"HEALTH — CryptoBrain v{report.get('version')} "
                        f"({report.get('python')})", "-" * 66]
    data = report.get("data", {})
    lines.append(f"  data mode    : {data.get('mode')} — {data.get('provider')}")
    for sym, probe in (data.get("probe") or {}).items():
        if probe.get("ok"):
            age = probe.get("age_seconds")
            age_note = f", age {float(age) / 60:.1f}m" if age is not None else ""
            lines.append(f"    {sym:<10} ok  {probe['bars']} bars, last "
                         f"{probe.get('last'):,.2f}{age_note}" if probe.get("last") is not None
                         else f"    {sym:<10} ok  {probe['bars']} bars{age_note}")
        else:
            lines.append(f"    {sym:<10} ✗  {probe.get('error', 'unreachable')}")
    cross = data.get("cross_exchange") or {}
    if cross.get("exchanges"):
        lines.append(f"  cross-exch    : {cross.get('note', '')} "
                     f"({cross.get('threshold_pct')}% flag threshold)")
        for name, ex in cross.get("exchanges", {}).items():
            bits = []
            for sym, info in ex.get("symbols", {}).items():
                if "deviation_pct" in info:
                    flag = " ⚠" if info.get("flag") else ""
                    bits.append(f"{sym} {info['deviation_pct']:+.2f}%{flag}")
                else:
                    bits.append(f"{sym} {info.get('error', 'unreachable')}")
            lines.append(f"    {name:<10} {'ok  ' if ex.get('ok') else '✗   '}"
                         + " · ".join(bits) if bits else f"    {name:<10} ✗  no data")
    elif cross.get("note"):
        lines.append(f"  cross-exch    : {cross.get('note')}")
    db_ = report.get("database", {})
    if db_.get("ok"):
        lines.append(f"  database     : ok  {db_['path']}")
        lines.append(f"    scans {db_['scans']} · backtest samples {db_['backtest_samples']}"
                     f" · paper samples {db_['paper_samples']}"
                     f" · calibration entries {db_['calibration_entries']}")
    else:
        lines.append(f"  database     : ✗  {db_.get('error', 'unreachable')}")
    gate = report.get("risk_gate", {})
    prog = gate.get("progression", {})
    lines.append(f"  risk gate    : {'OPEN' if gate.get('allowed') else 'CLOSED'}  "
                 f"progression {prog.get('level', '?')} — {prog.get('label', '')}")
    for b in gate.get("blocked_by", []):
        lines.append(f"    ✗ {b}")
    learning = report.get("learning", {})
    lines.append(f"  learning     : {learning.get('calibration_entries', 0)} "
                 f"calibration entries, {len(learning.get('proven_setups', []))} proven")
    lines.append(f"  pending      : {report.get('pending_reviews', 0)} review(s)")
    mcp = report.get("mcp", {})
    lines.append(f"  mcp          : {'ready' if mcp.get('available') else 'not installed'}"
                 f" — {mcp.get('note', '')}")
    llm = report.get("llm", {})
    lines.append(f"  llm          : provider {llm.get('provider')} "
                 f"({'enabled' if llm.get('enabled') else 'off'})")
    lines.append("-" * 66)
    lines.append(f"  VERDICT      : {'OK' if report.get('ok') else 'PROBLEMS FOUND'}")
    return "\n".join(lines)


# ── morning briefing ──────────────────────────────────────────────────────

def morning_briefing(symbols: list[str] | None = None, timeframe: str = TIMEFRAME,
                     bars: int = BARS, save: bool = False) -> dict:
    """The 9am desk run: every watchlist asset, desk decisions, gate, queue."""
    from brain.full_pipeline import analyze_full
    from data.database import SignalDB
    from brain.risk_gate import evaluate as gate_evaluate
    from brain.journal import violation_rate

    symbols = parse_symbol_list(symbols)
    assets = []
    for symbol in symbols:
        entry: dict = {"symbol": symbol, "timeframe": timeframe, "ok": True}
        try:
            payload = analyze_full(symbol, timeframe, bars, with_context=False,
                                   with_memory=True)
            sig = payload.get("signal", {})
            decision = payload.get("decision") or {}
            plans = payload.get("plans", [])
            plan_conf = [int(p.get("confidence") or 0) for p in plans]
            entry.update({
                "action": sig.get("action"),
                "confidence": sig.get("confidence"),
                "confidence_pct": max(plan_conf) if plan_conf else None,
                "n_plans": len(plans),
                "entry": sig.get("entry"),
                "stop_loss": sig.get("stop_loss"),
                "take_profit": sig.get("take_profit"),
                "risk_reward": sig.get("risk_reward"),
                "reason": sig.get("reason"),
                "signal_id": sig.get("signal_id"),
                "price": payload.get("snapshot", {}).get("features", {}).get("price"),
                "desk_action": decision.get("action", sig.get("action")),
                "blocked_by": decision.get("blocked_by", []),
                "playbook": (decision.get("gates") or {}).get("playbook", {}).get("name"),
                "regime": (payload.get("intelligence", {}) or {}).get("chart_read", {})
                          .get("regime", {}).get("label") or
                          payload.get("snapshot", {}).get("features", {}).get("regime_name"),
                "lifecycle": payload.get("lifecycle", {}),
            })
            if save:
                from main import run_scan
                payload = run_scan(symbol, timeframe, bars, save_db=True)
                entry["scan_id"] = payload.get("scan_id")
        except Exception as exc:
            entry.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        assets.append(entry)

    briefing: dict = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timeframe": timeframe,
        "assets": assets,
        "narrative": "",
    }
    try:
        with SignalDB() as db:
            gate = gate_evaluate(db)
            briefing["risk_gate"] = {
                "allowed": gate["allowed"], "blocked_by": gate.get("blocked_by", []),
                "progression": gate.get("details", {}).get("progression", {}),
            }
            briefing["pending_reviews"] = len(db.pending_reviews())
            briefing["open_exposure"] = db.open_exposure()
            briefing["paper_stats"] = db.paper_trade_stats()["overall"]
            try:
                briefing["journal"] = violation_rate(db)
            except Exception:
                briefing["journal"] = {"n": 0, "violations": 0}
            calib = db.load_calibration()
            briefing["learning"] = {
                "entries": len(calib),
                "proven": sorted(k for k, v in calib.items() if v.get("proven")),
            }
    except Exception as exc:
        briefing["risk_gate"] = {"allowed": False,
                                 "blocked_by": [f"gate unavailable: {exc}"]}

    briefing["narrative"] = _briefing_narrative(briefing)
    return briefing


def _briefing_narrative(b: dict) -> str:
    """Rule-based plain-English morning summary (always available offline)."""
    lines = []
    for a in b.get("assets", []):
        if not a.get("ok"):
            lines.append(f"  {a['symbol']}: data feed unavailable — {a.get('error', '')}")
            continue
        pct = a.get("confidence_pct")
        conf = f"{pct}%" if pct else f"{a.get('confidence') or '—'}"
        side = a.get("desk_action", a.get("action"))
        regime = a.get("regime") or "—"
        if side in ("BUY", "SELL"):
            rr = a.get("risk_reward")
            lines.append(f"  {a['symbol']} {a['timeframe']} [{regime}]: {side} {a.get('entry'):,.2f} "
                         f"(conf {conf}, R:R {rr}) — {a.get('reason', '')}")
            if a.get("blocked_by"):
                lines.append(f"    desk vetoed: {'; '.join(a['blocked_by'])}")
        else:
            lines.append(f"  {a['symbol']} {a['timeframe']} [{regime}]: NO TRADE "
                         f"(conf {conf}) — {a.get('reason', '')}")
    gate = b.get("risk_gate") or {}
    prog = gate.get("progression") or {}
    lines.append(f"• Risk gate {'OPEN' if gate.get('allowed') else 'CLOSED'} at "
                 f"progression '{prog.get('level', '?')}'"
                 + (f" — {', '.join(gate['blocked_by'])}" if gate.get("blocked_by") else ""))
    lines.append(f"• {b.get('pending_reviews', 0)} signal(s) awaiting human review.")
    paper = b.get("paper_stats") or {}
    if paper.get("n"):
        lines.append(f"• Paper book: {paper['n']} trades, {paper['wins']}W/{paper['losses']}L, "
                     f"avg {paper.get('avg_rr', 0):+.2f}R.")
    proven = (b.get("learning") or {}).get("proven", [])
    if proven:
        lines.append(f"• Proven setups: {', '.join(proven)}.")
    else:
        lines.append("• No setup proven yet — grind samples with "
                     "`python main.py simulator` (>=100 backtest, >=20 paper per setup).")
    return "\n".join(lines)


def format_briefing(b: dict) -> str:
    lines = ["=" * 66, f"MORNING BRIEFING — {b.get('time')}  ({b.get('timeframe')})",
             "-" * 66]
    for a in b.get("assets", []):
        if not a.get("ok"):
            lines.append(f"  {a['symbol']:<10} ✗ {a.get('error', 'unreachable')}")
            continue
        side = a.get("desk_action", a.get("action"))
        mark = "✓" if side in ("BUY", "SELL") else "·"
        entry = a.get("entry")
        entry_s = f"@{entry:,.2f}" if entry else ""
        pct = a.get("confidence_pct")
        conf = f"{pct}%" if pct else f"{a.get('confidence') or '—'}"
        lines.append(f"  {mark} {a['symbol']:<10} {side:<8} [{a.get('regime') or '—'}] "
                     f"conf={conf} {entry_s}  SL {a.get('stop_loss')}  TP {a.get('take_profit')}")
        if a.get("blocked_by"):
            for reason in a["blocked_by"]:
                lines.append(f"      ✗ {reason}")
        elif a.get("playbook"):
            lines.append(f"      playbook: {a['playbook']}")
    gate = b.get("risk_gate") or {}
    prog = gate.get("progression") or {}
    gate_state = "OPEN — new trades allowed" if gate.get("allowed") \
        else "CLOSED — no new trades"
    lines.append("-" * 66)
    lines.append(f"  RISK GATE: {gate_state}  progression={prog.get('level', '?')}")
    for reason in gate.get("blocked_by", []):
        lines.append(f"      ✗ {reason}")
    lines.append(f"  pending human review: {b.get('pending_reviews', 0)}")
    lines.append(f"  open exposure: {len(b.get('open_exposure', []))} paper trade(s)")
    paper = b.get("paper_stats") or {}
    if paper.get("n"):
        lines.append(f"  paper book: {paper['n']} tracked · {paper['wins']}W/{paper['losses']}L "
                     f"· avg {paper.get('avg_rr', 0):+.2f}R")
    learning = b.get("learning") or {}
    lines.append(f"  learning: {learning.get('entries', 0)} calibration entries · "
                 f"proven: {', '.join(learning.get('proven', [])) or 'none'}")
    lines.append("-" * 66)
    lines.append(b.get("narrative", ""))
    return "\n".join(lines)


# ── ask ───────────────────────────────────────────────────────────────────

_INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    # graduation must be checked first: "ready for micro" also contains
    # the generic "progression"/"micro" words.
    ("graduation", ("graduat", "am i ready", "ready for micro", "micro yet",
                    "real money", "promote me", "ready to trade real",
                    "step 3", "blueprint gate")),
    # desk_status is the one-call advisory; match before generic "risk"/"health".
    ("desk", ("desk status", "what should i do", "what would a professional",
              "stand aside", "what now")),
    ("risk", ("risk", "gate", "limit", "drawdown", "daily", "weekly", "trader state",
              "stop trading", "allowed")),
    ("exposure", ("exposure", "portfolio", "position", "bucket", "correlation", "open trade")),
    ("pending", ("pending", "review", "approve", "queue", "waiting for")),
    ("journal", ("journal", "discipline", "rules", "followed", "violation", "emotion")),
    ("calibration", ("calibrat", "learn", "proven", "setup", "expectancy", "multiplier")),
    ("stats", ("stats", "backtest", "win rate", "learning", "scorecard")),
    ("paper", ("paper", "simulation", "simulated")),
    ("market", ("scan", "market", "price", "signal", "analyze", "trade now", "entry")),
    ("health", ("health", "status", "system", "database", "db", "feed", "up")),
    ("sources", ("source", "news", "trust", "tier", "discord", "telegram")),
    ("progression", ("progression", "level", "micro", "student", "simulator level",
                     "scale", "consistent")),
    ("morning", ("morning", "briefing", "brief", "today")),
]


def _detect_intent(question: str) -> str:
    q = question.lower()
    for intent, words in _INTENT_KEYWORDS:
        if any(w in q for w in words):
            return intent
    return "help"


def ask(question: str, symbol: str | None = None,
        timeframe: str = TIMEFRAME, bars: int = BARS) -> dict:
    """Answer a natural-language question from live DB + engine state."""
    intent = _detect_intent(question)
    from data.database import SignalDB
    with SignalDB() as db:
        if intent == "graduation":
            from brain.journal import violation_rate
            from data.simulator import (format_graduation, graduation_status,
                                        paper_progress)
            j = violation_rate(db)
            compliance = 1.0 - j["violation_rate"] if j["violation_rate"] is not None \
                else None
            g = graduation_status(paper_progress(db), compliance=compliance)
            return {"intent": intent, "question": question,
                    "answer": format_graduation(g).splitlines(),
                    "data": {"graduation": g, "journal": j}}
        if intent == "desk":
            status = desk_status()
            return {"intent": intent, "question": question,
                    "answer": format_desk_status(status).splitlines(),
                    "data": status}
        if intent == "risk":
            from brain.risk_gate import evaluate as gate_evaluate
            from brain.risk_gate import status_text
            gate = gate_evaluate(db)
            return {"intent": intent, "question": question,
                    "answer": status_text(db).splitlines(),
                    "data": {"allowed": gate["allowed"],
                             "blocked_by": gate.get("blocked_by", []),
                             "progression": gate.get("details", {}).get("progression", {})}}
        if intent == "exposure":
            from brain.portfolio import bucket_state
            trades = db.open_exposure()
            lines = [f"Open exposure: {len(trades)} paper trade(s)"]
            buckets = {}
            for t in trades:
                bucket = "gold" if t.get("symbol") == "XAUUSD" else "crypto"
                buckets.setdefault(bucket, []).append(t)
            for bucket, rows in buckets.items():
                state = bucket_state(db, rows[0]["symbol"] or "BTCUSDT")
                lines.append(f"  {bucket} bucket: {state.n_open}/{state.max_trades} "
                             f"trades, directions {state.directions or ['flat']}")
                for t in rows:
                    lines.append(f"    {t.get('symbol')} {t.get('action')} — "
                                 f"{t.get('plan_type') or 'signal'} "
                                 f"({t.get('status', '')})")
            if not trades:
                lines.append("  The book is flat — no correlated risk.")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"trades": trades,
                             "buckets": {k: {"n": len(v)} for k, v in buckets.items()}}}
        if intent == "pending":
            rows = db.pending_reviews()
            lines = [f"Pending human review: {len(rows)}"]
            for r in rows:
                lines.append(f"  #{r['id']} {r['symbol']} {r['action']} conf="
                             f"{r['confidence_label']} entry={r['entry']} — "
                             f"{r['reason'][:70]}")
            if not rows:
                lines.append("  Queue is empty.")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"pending": rows}}
        if intent == "journal":
            from brain.journal import violation_rate
            j = violation_rate(db)
            rate = j["violation_rate"]
            if rate is None:
                lines = ["Journal discipline: no trades recorded yet.",
                         "  `python main.py journal <scan_id> --followed-rules 1 ...`"]
            else:
                lines = [f"Journal discipline: {j['violations']}/{j['n']} trades "
                         f"({rate * 100:.1f}%) violated the system",
                         "  The goal is 0% — a loss with rules followed is an excellent trade."]
            return {"intent": intent, "question": question, "answer": lines,
                    "data": j}
        if intent == "calibration":
            from brain.calibrator import describe
            profile = db.load_calibration()
            lines = describe(profile).splitlines() if profile else [
                "No calibration profile yet — the engine is neutral (all multipliers 1.0).",
                "Grind samples: `python main.py simulator` (>=100 backtest, >=20 paper)."]
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"calibration": profile,
                             "targets": {"backtest": CALIBRATE_MIN_N,
                                         "paper": CALIBRATE_MIN_PAPER_N}}}
        if intent == "stats":
            from brain.metrics import business_metrics
            bt = db.backtest_stats()
            overall = bt["overall"]
            bt_wr = f"{overall['win_rate'] * 100:.1f}%" if overall["win_rate"] is not None \
                else "n/a"
            lines = [f"Backtest learning: {overall['n']} graded | win-rate {bt_wr} "
                     f"| avgR {overall['avg_rr']}"]
            for r in bt["by_type"][:6]:
                wr = f"{r['win_rate'] * 100:.1f}%" if r["win_rate"] is not None else "n/a"
                lines.append(f"  {r['plan_type']:<24} n={r['n']:>4} win {wr} "
                             f"avgR {r['avg_rr']}")
            try:
                m = business_metrics(db)
                lines.append(f"Business scorecard: PF {m.get('profit_factor', 0):.2f}, "
                             f"maxDD {m.get('max_drawdown_pct', 0):.2f}%")
            except Exception:
                pass
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"backtest": bt}}
        if intent == "paper":
            p = db.paper_trade_stats()["overall"]
            lines = [f"Paper trading: {p['n']} tracked | waiting {p.get('waiting', 0)} | "
                     f"open {p.get('open', 0)} | closed {p.get('closed', 0)} | "
                     f"wins/losses {p['wins']}/{p['losses']} | avg "
                     f"{p['avg_rr']:+.2f}R"]
            if not p["n"]:
                lines.append("  Approve a signal, then run `python main.py paper --watch`.")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"paper": p}}
        if intent == "market":
            from main import run_scan
            sym = symbol or SYMBOLS[0]
            payload = run_scan(sym, timeframe, bars, save_db=False)
            sig = payload.get("signal", {})
            decision = payload.get("decision") or {}
            entry = sig.get("entry")
            entry_s = f"@ {entry:,.2f}" if entry else ""
            plan_conf = [int(p.get("confidence") or 0)
                         for p in payload.get("plans", [])]
            conf = f"{max(plan_conf)}%" if plan_conf else \
                str(sig.get("confidence") or "—")
            lines = [f"{sig.get('asset')} {sig.get('timeframe')}: "
                     f"{decision.get('action', sig.get('action'))} "
                     f"conf={conf} {entry_s}",
                     f"  reason: {sig.get('reason')}"]
            for b in decision.get("blocked_by", []):
                lines.append(f"  desk veto: {b}")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"signal": sig, "decision": decision}}
        if intent == "health":
            report = health_report()
            return {"intent": intent, "question": question,
                    "answer": format_health(report).splitlines(), "data": report}
        if intent == "sources":
            from config import SOURCE_TIER_NAMES
            rows = db.load_source_scores()
            lines = [f"Source trust table: {len(rows)} source(s)"]
            for s in rows:
                lines.append(f"  {s['source']:<22} tier {s['tier']} "
                             f"({SOURCE_TIER_NAMES.get(s['tier'], '?')}) trust "
                             f"{s['trust']:.2f} {s.get('note') or ''}")
            if not rows:
                lines.append("  None recorded — `python main.py sourcetrust "
                             "<source> <tier 1-5> <0-1>`")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"sources": rows}}
        if intent == "progression":
            from brain.risk_gate import progression as progression_info
            prog = progression_info()
            order = list(PROGRESSION_LEVELS)
            idx = order.index(prog["level"]) if prog["level"] in order else 0
            lines = [f"Progression: {prog['level']} — {prog['label']}",
                     f"  effective risk {prog['risk_pct']}%/trade · "
                     f"{prog['daily']}%/day · {prog['weekly']}%/week",
                     f"  approve unproven setups: {'yes' if prog['approve_unproven'] else 'no'}"]
            if idx + 1 < len(order):
                nxt = PROGRESSION_LEVELS[order[idx + 1]]
                lines.append(f"  next level: {order[idx + 1]} — {nxt['label']}")
            else:
                lines.append("  you are at the top of the ladder.")
            return {"intent": intent, "question": question, "answer": lines,
                    "data": {"progression": prog, "ladder": order}}
        if intent == "morning":
            b = morning_briefing(symbols=[symbol] if symbol else None,
                                 timeframe=timeframe)
            return {"intent": intent, "question": question,
                    "answer": format_briefing(b).splitlines(), "data": b}

    # help / unknown
    intents = ", ".join(sorted({i for i, _ in _INTENT_KEYWORDS}))
    return {"intent": "help", "question": question,
            "answer": ["I can answer questions about: " + intents,
                       "Try: 'is the risk gate open?', 'what's pending?', "
                       "'how is my journal discipline?', 'scan BTC'."],
            "data": {"intents": intents}}


def graduation_report() -> dict:
    """Graduation gate + per-setup progress, as one JSON-able dict.

    Used by `agent all`, `simulator --json` and the dashboard.
    """
    from data.database import SignalDB
    from data.simulator import graduation_status, paper_progress
    with SignalDB() as db:
        progress = paper_progress(db)
        from brain.journal import violation_rate
        j = violation_rate(db)
        compliance = 1.0 - j["violation_rate"] if j["violation_rate"] is not None \
            else None
    return {"progress": progress,
            "graduation": graduation_status(progress, compliance=compliance),
            "journal": j}


def format_answer(result: dict) -> str:
    return "\n".join(result.get("answer", []))


# ── JSON-safe helpers for MCP / dashboard ─────────────────────────────────

def json_safe(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {k: json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(v) for v in value]
        return str(value)


# ── desk_status (P9 / TODO-4) ─────────────────────────────────────────────

def desk_status() -> dict:
    """Single advisory snapshot: gate + P&L + graduation + next agent + advice.

    The one call an agent (or operator) makes to answer
    "what would a professional do right now?"  Read-only — never
    mutates state, never places an order.
    """
    from data.database import SignalDB

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status: dict = {
        "time": now,
        "version": VERSION,
        "progression": {"level": PROGRESSION},
        "risk_gate": {"open": False, "allowed": False, "blocked_by": ["unavailable"]},
        "pnl": {},
        "scorecard": {"n": 0},
        "graduation": {"ready": False},
        "pending_reviews": 0,
        "open_exposure": 0,
        "next_agent": {"name": "morning_brief", "reason": "unavailable"},
        "advice": {
            "action": "STAND_ASIDE",
            "headline": "desk status unavailable",
            "detail": "could not assemble the snapshot",
            "reasons": [],
        },
    }

    try:
        with SignalDB() as db:
            try:
                from brain.risk_gate import evaluate_risk_gate, progression as progression_info
                gate = evaluate_risk_gate(db)
                details = gate.get("details") or {}
                dws = details.get("daily_weekly") or {}
                dw = details.get("drawdown") or {}
                ts = details.get("trader_state") or {}
                prog = (gate.get("progression") or details.get("progression")
                        or progression_info())
                status["progression"] = {
                    "level": prog.get("level", PROGRESSION),
                    "label": prog.get("label", ""),
                    "risk_pct": prog.get("risk_pct"),
                    "approve_unproven": prog.get("approve_unproven"),
                }
                status["risk_gate"] = {
                    "open": bool(gate.get("open", gate.get("allowed"))),
                    "allowed": bool(gate.get("allowed")),
                    "blocked_by": list(gate.get("blocked_by") or []),
                    "today_pnl_pct": (dws.get("today") or {}).get("pct"),
                    "today_n": (dws.get("today") or {}).get("n"),
                    "week_pnl_pct": (dws.get("week") or {}).get("pct"),
                    "week_n": (dws.get("week") or {}).get("n"),
                    "drawdown_pct": dw.get("max_drawdown_pct"),
                    "drawdown_level": dw.get("level"),
                    "trader_flags": list(ts.get("flags") or []),
                    "enforced": bool(details.get("enforced", True)),
                }
                status["pnl"] = {
                    "today": dws.get("today") or {"n": 0, "pct": 0.0, "r_sum": 0.0},
                    "week": dws.get("week") or {"n": 0, "pct": 0.0, "r_sum": 0.0},
                    "drawdown": {
                        "pct": dw.get("max_drawdown_pct", 0.0),
                        "level": dw.get("level", "normal"),
                        "equity": dw.get("equity"),
                    },
                }
            except Exception as exc:
                status["risk_gate"] = {
                    "open": False, "allowed": False,
                    "blocked_by": [f"unavailable: {type(exc).__name__}: {exc}"],
                    "trader_flags": [],
                }

            try:
                from brain.metrics import business_metrics
                metrics = business_metrics(db)
                overall = metrics.get("overall") or {}
                execution = metrics.get("execution") or {}
                status["scorecard"] = {
                    "n": overall.get("n", 0),
                    "wins": overall.get("wins", 0),
                    "losses": overall.get("losses", 0),
                    "win_rate": overall.get("win_rate"),
                    "expectancy_r": overall.get("expectancy_r"),
                    "profit_factor": overall.get("profit_factor"),
                    "max_drawdown_pct": overall.get("max_drawdown_pct"),
                    "final_equity": overall.get("final_equity"),
                    "violation_rate": execution.get("violation_rate"),
                    "journal_n": execution.get("n", 0),
                }
            except Exception as exc:
                status["scorecard"] = {"n": 0, "error": f"{type(exc).__name__}: {exc}"}

            try:
                from data.simulator import graduation_status, paper_progress
                from brain.journal import violation_rate
                j = violation_rate(db)
                compliance = (1.0 - j["violation_rate"]
                              if j.get("violation_rate") is not None else None)
                status["graduation"] = graduation_status(
                    paper_progress(db), compliance=compliance)
                status["journal"] = {
                    "n": j.get("n", 0),
                    "violations": j.get("violations", 0),
                    "violation_rate": j.get("violation_rate"),
                    "compliance": compliance,
                }
            except Exception as exc:
                status["graduation"] = {
                    "ready": False, "error": f"{type(exc).__name__}: {exc}"}

            try:
                status["pending_reviews"] = len(db.pending_reviews())
            except Exception:
                status["pending_reviews"] = 0
            try:
                status["open_exposure"] = len(db.open_exposure())
            except Exception:
                status["open_exposure"] = 0

            try:
                from brain.agents import next_scheduled_agent
                status["next_agent"] = next_scheduled_agent(db)
            except Exception as exc:
                status["next_agent"] = {
                    "name": "morning_brief",
                    "reason": f"unavailable: {type(exc).__name__}: {exc}",
                }
    except Exception as exc:
        status["advice"] = {
            "action": "STAND_ASIDE",
            "headline": "desk snapshot failed",
            "detail": f"{type(exc).__name__}: {exc}",
            "reasons": [str(exc)],
        }
        return json_safe(status)

    status["advice"] = _desk_advice(status)
    return json_safe(status)


def _desk_advice(status: dict) -> dict:
    """Priority-ordered 'what would a professional do right now?'."""
    gate = status.get("risk_gate") or {}
    flags = list(gate.get("trader_flags") or [])
    blocked = list(gate.get("blocked_by") or [])
    pending = int(status.get("pending_reviews") or 0)
    graduation = status.get("graduation") or {}
    scorecard = status.get("scorecard") or {}
    journal = status.get("journal") or {}
    next_agent = status.get("next_agent") or {}
    level = (status.get("progression") or {}).get("level") or PROGRESSION

    if flags:
        return {
            "action": "CLEAR_STATE",
            "headline": "clear behavioral flags before anything else",
            "detail": ("Trader-state flags are set (" + ", ".join(flags)
                       + "). A professional stands aside until the flags "
                       "are cleared with `python main.py tradestate --clear`."),
            "reasons": [f"trader state: {', '.join(flags)}"],
        }
    if not gate.get("allowed", False):
        why = "; ".join(blocked) if blocked else "risk gate closed"
        return {
            "action": "STAND_ASIDE",
            "headline": "stand aside — the risk gate is closed",
            "detail": (f"No new trades. {why}. Re-check with "
                       "`python main.py risk` after the block lifts."),
            "reasons": blocked or ["risk gate closed"],
        }
    if pending > 0:
        return {
            "action": "REVIEW_QUEUE",
            "headline": f"{pending} signal(s) awaiting human review",
            "detail": ("The machine proposed; you decide. "
                       "`python main.py review` then approve/reject. "
                       "Do not scan for more until the queue is empty."),
            "reasons": [f"{pending} pending review(s)"],
        }
    closed_n = int(scorecard.get("n") or 0)
    journal_n = int(journal.get("n") or scorecard.get("journal_n") or 0)
    if closed_n > 0 and journal_n == 0:
        return {
            "action": "JOURNAL",
            "headline": "journal the closed paper trades",
            "detail": (f"{closed_n} decided paper trade(s) have no journal "
                       "entry. A professional records 'did I follow my "
                       "system?' before looking for the next setup. "
                       "`python main.py journal <scan_id> --followed-rules 1`."),
            "reasons": [f"{closed_n} decided trades, 0 journal entries"],
        }
    if not graduation.get("ready"):
        missing = []
        met = graduation.get("met") or {}
        for name, ok in met.items():
            if not ok:
                missing.append(name)
        # The sample proof can be open for counts OR for expectancy; name
        # exactly which primary setups are short so the advice is actionable.
        gaps = graduation.get("sample_gaps") or []
        if not graduation.get("samples_proven", False):
            for m in gaps:
                missing.append(f"{m.get('plan_type')} sample proof "
                               f"({m.get('missing')})")
        why = ", ".join(missing) if missing else "graduation gate not met"
        return {
            "action": "PAPER_GRIND",
            "headline": "keep paper-trading — not ready for micro",
            "detail": (f"Progression is '{level}'. Graduation still needs: {why}. "
                       "Grind unique samples with `python main.py simulator` "
                       "and keep the paper runner on approved signals."),
            "reasons": missing or ["not graduated"],
        }
    next_name = next_agent.get("name") or "morning_brief"
    return {
        "action": "SCAN",
        "headline": "desk is open — scan the watchlist",
        "detail": (f"Gate OPEN, graduation ready, queue empty. "
                   f"Run `python main.py brief` (or agent '{next_name}') "
                   "and act only on the desk decision, never the raw scan."),
        "reasons": ["risk gate open", "graduation ready", "queue empty"],
    }


def _sample_proof_word(g: dict) -> str:
    """Precise 'why the sample proof is open' label for the desk line.

    The blanket "samples short" was misleading once the grind had tens of
    thousands of samples: the gate can also be open because a primary setup's
    expectancy is still <= 0 even with 100/20 counts.  Distinguish the two
    from `graduation.sample_gaps` (the grind_verdict missing list).
    """
    if g.get("samples_proven"):
        return "proven"
    gaps = [str(m.get("missing") or "") for m in (g.get("sample_gaps") or [])]
    if not gaps:
        return "unproven"
    count_short = any("no samples yet" in m or "backtest" in m or "paper" in m
                      for m in gaps)
    exp_short = any("positive expectancy" in m for m in gaps)
    if count_short and exp_short:
        return "counts+expectancy short"
    if count_short:
        return "counts short"
    if exp_short:
        return "expectancy short"
    return "unproven"


def format_desk_status(status: dict) -> str:
    """Human-readable block for `python main.py desk` / MCP / dashboard."""
    gate = status.get("risk_gate") or {}
    pnl = status.get("pnl") or {}
    today = pnl.get("today") or {}
    week = pnl.get("week") or {}
    dw = pnl.get("drawdown") or {}
    score = status.get("scorecard") or {}
    g = status.get("graduation") or {}
    gstats = g.get("stats") or {}
    next_a = status.get("next_agent") or {}
    advice = status.get("advice") or {}
    prog = status.get("progression") or {}
    flags = gate.get("trader_flags") or []

    gate_word = "OPEN" if gate.get("allowed") else "CLOSED"
    wr = score.get("win_rate")
    wr_s = f"{wr * 100:.1f}%" if wr is not None else "n/a"
    exp = score.get("expectancy_r")
    exp_s = f"{exp:+.3f}R" if exp is not None else "n/a"
    pf = score.get("profit_factor")
    pf_s = f"{pf:.2f}" if pf is not None else "n/a"
    today_pct = today.get("pct")
    today_s = f"{today_pct:+.2f}%" if today_pct is not None else "n/a"
    week_pct = week.get("pct")
    week_s = f"{week_pct:+.2f}%" if week_pct is not None else "n/a"
    dd_pct = dw.get("pct")
    dd_s = f"{dd_pct:.2f}%" if dd_pct is not None else "n/a"

    lines = [
        "=" * 66,
        f"DESK STATUS — CryptoBrain v{status.get('version')}  {status.get('time')}",
        "-" * 66,
        f"  progression  : {prog.get('level', '?')} — {prog.get('label', '')}",
        f"  risk gate    : {gate_word}"
        + (f"  flags={', '.join(flags)}" if flags else "  flags=clear"),
    ]
    for b in gate.get("blocked_by") or []:
        lines.append(f"    ✗ {b}")
    proof_word = _sample_proof_word(g)
    lines.extend([
        f"  today P&L    : {today_s}  ({today.get('n', 0)} trades)",
        f"  week P&L     : {week_s}  ({week.get('n', 0)} trades)",
        f"  drawdown     : {dd_s}  → {dw.get('level', 'normal')}",
        f"  scorecard    : n={score.get('n', 0)}  win {wr_s}  "
        f"exp {exp_s}  PF {pf_s}",
        f"  graduation   : {'READY' if g.get('ready') else 'NOT READY'}  "
        f"(samples {proof_word} · {gstats.get('n', 0)} decided)",
        f"  pending      : {status.get('pending_reviews', 0)} review(s)  ·  "
        f"open exposure {status.get('open_exposure', 0)}",
        f"  next agent   : {next_a.get('name', '?')} — {next_a.get('reason', '')}",
        "-" * 66,
        f"  ADVICE       : {advice.get('action', '?')} — {advice.get('headline', '')}",
    ])
    detail = advice.get("detail")
    if detail:
        lines.append(f"               {detail}")
    return "\n".join(lines)


# ── readiness strip (TODO-1.bis) ─────────────────────────────────────────
# One combined "doctor" verdict across the three independent readiness
# surfaces the desk already reports separately:
#
#   channels  (brain/channels.probe_all)  — can I still see the world?
#   immune    (brain/immune.run_health_check) — is the machine itself sane?
#   risk gate (inside desk_status)        — am I allowed to trade?
#
# The strip does not invent a fourth source of truth: every pillar reads
# the same library function the CLI / MCP / dashboard already read, so no
# surface can drift from another.  Read-only; never places an order.

#: Worst-first severity ladder. Index = how bad; higher wins the rollup.
_READINESS_ORDER = ("ok", "degraded", "blocked", "down")

#: immune.run_health_check() status → readiness level.
_IMMUNE_TO_LEVEL = {"OK": "ok", "WARN": "degraded", "CRITICAL": "down"}

#: channels.Channel.status → readiness level.
_CHANNEL_TO_LEVEL = {"ok": "ok", "degraded": "degraded",
                     "down": "down", "unknown": "degraded"}


def _worst(levels) -> str:
    """Roll a list of readiness levels up to the worst one present."""
    worst = "ok"
    for lvl in levels:
        if _READINESS_ORDER.index(lvl) > _READINESS_ORDER.index(worst):
            worst = lvl
    return worst


def _channels_pillar() -> dict:
    """Channel pillar: how many source channels have a live backend."""
    try:
        from brain.channels import probe_all
        channels = probe_all()
    except Exception as exc:
        return {"name": "channels", "level": "down", "headline": "channels unavailable",
                "detail": f"{type(exc).__name__}: {exc}", "items": []}

    items = []
    for name, ch in channels.items():
        items.append({"name": name,
                      "status": ch.status,
                      "level": _CHANNEL_TO_LEVEL.get(ch.status, "degraded"),
                      "active": ch.active})
    live = [i for i in items if i["status"] == "ok"]
    down = [i for i in items if i["status"] == "down"]

    if down:
        level = "down"
        headline = f"{len(down)} channel(s) down"
    elif not live:
        level = "degraded"
        headline = "no channel has a configured backend"
    elif len(live) < len(items):
        level = "degraded"
        headline = f"{len(live)}/{len(items)} channels live"
    else:
        level = "ok"
        headline = f"{len(live)}/{len(items)} channels live"

    detail = ", ".join(f"{i['name']}={i['active'] or '-'}" for i in items)
    return {"name": "channels", "level": level, "headline": headline,
            "detail": detail, "items": items}


def _immune_pillar() -> dict:
    """Immune pillar: DB integrity, data freshness, risk system, calibration."""
    try:
        from brain.immune import run_health_check
        report = run_health_check()
    except Exception as exc:
        return {"name": "immune", "level": "down", "headline": "immune check failed",
                "detail": f"{type(exc).__name__}: {exc}", "items": []}

    checks = report.get("checks") or []
    items = [{"name": c.get("name", "?"),
              "status": c.get("status", "OK"),
              "level": _IMMUNE_TO_LEVEL.get(c.get("status", "OK"), "degraded"),
              "detail": c.get("detail", "")}
             for c in checks]
    level = _IMMUNE_TO_LEVEL.get(report.get("status", "OK"), "degraded")
    n_crit = int(report.get("critical_count") or 0)
    n_warn = int(report.get("warn_count") or 0)
    if n_crit:
        headline = f"{n_crit} critical check(s)"
    elif n_warn:
        headline = f"{n_warn} warning(s)"
    else:
        headline = f"{len(items)} check(s) ok"
    failing = [i["detail"] for i in items if i["level"] != "ok"]
    return {"name": "immune", "level": level, "headline": headline,
            "detail": "; ".join(failing) if failing else report.get("summary", ""),
            "items": items, "status": report.get("status", "OK")}


def _gate_pillar(status: dict) -> dict:
    """Risk-gate pillar, read straight off an existing desk_status snapshot."""
    gate = status.get("risk_gate") or {}
    blocked = list(gate.get("blocked_by") or [])
    flags = list(gate.get("trader_flags") or [])
    allowed = bool(gate.get("allowed"))

    if allowed and not flags:
        level, headline = "ok", "gate OPEN"
    elif allowed and flags:
        level, headline = "degraded", f"gate OPEN with flags: {', '.join(flags)}"
    else:
        level, headline = "blocked", "gate CLOSED"

    detail = "; ".join(blocked) if blocked else (
        ", ".join(flags) if flags else "no blocks")
    return {"name": "risk_gate", "level": level, "headline": headline,
            "detail": detail, "open": allowed, "blocked_by": blocked,
            "flags": flags}


def readiness_strip(status: dict | None = None) -> dict:
    """Combined channels + immune + risk-gate readiness verdict.

    The single strip the dashboard shows above every tab, and the same
    payload `python main.py doctor --strip` and MCP `readiness` return.
    Pass an existing ``desk_status()`` snapshot to avoid re-computing it.

    Read-only. Never mutates state, never places an order. Every pillar
    is exception-isolated: one broken probe degrades that pillar instead
    of failing the strip.
    """
    if status is None:
        status = desk_status()

    pillars = [_channels_pillar(), _immune_pillar(), _gate_pillar(status)]
    level = _worst(p["level"] for p in pillars)

    advice = status.get("advice") or {}
    if level == "ok":
        headline = "desk ready"
    elif level == "degraded":
        weak = [p["name"] for p in pillars if p["level"] == "degraded"]
        headline = "desk degraded — " + ", ".join(weak)
    elif level == "blocked":
        headline = "desk blocked — risk gate closed"
    else:
        bad = [p["name"] for p in pillars if p["level"] == "down"]
        headline = "desk not ready — " + ", ".join(bad)

    return json_safe({
        "time": status.get("time"),
        "version": status.get("version", VERSION),
        "level": level,
        "ready": level == "ok",
        "headline": headline,
        "pillars": pillars,
        "advice": {"action": advice.get("action"),
                   "headline": advice.get("headline")},
    })


def format_readiness_strip(strip: dict) -> str:
    """One-line-per-pillar text block for `python main.py doctor --strip`."""
    mark = {"ok": "✓", "degraded": "○", "blocked": "!", "down": "✗"}
    lines = [
        "=" * 66,
        f"READINESS — {strip.get('level', '?').upper()}: {strip.get('headline', '')}",
        "-" * 66,
    ]
    for p in strip.get("pillars") or []:
        lines.append(f"  {mark.get(p['level'], '?')} {p['name']:<10} "
                     f"{p['level']:<9} {p.get('headline', '')}")
        if p.get("detail"):
            lines.append(f"      {p['detail']}")
    advice = strip.get("advice") or {}
    if advice.get("action"):
        lines.append("-" * 66)
        lines.append(f"  ADVICE       : {advice['action']} — {advice.get('headline', '')}")
    return "\n".join(lines)
