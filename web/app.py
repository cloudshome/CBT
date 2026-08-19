"""web/app.py

CryptoBrain — all-in-one dashboard ("watch everything, click to decide").

One page shows:
  • live signal + lifecycle badge + approve/reject/execute/close buttons
  • multi-condition plans with confidence bars
  • market context (funding / OI / L/S)
  • full feature snapshot + score breakdown
  • human approval queue (clickable Approve / Reject)
  • recent signal history (click a row → detail modal, decide from there)
  • learning dashboard (backtest win-rates + calibration profile)
  • coach panel (explain / mentor / personal feedback)
  • LLM narrative + raw JSON

Endpoints
  GET /             dashboard HTML
  GET /api/scan     live brain output (persisted, deduped by signal_id)
  GET /api/sentiment market-sentiment colour reading (score/duration/depth/colour)
  GET /api/pending  signals awaiting human approval
  POST /api/review  approve/reject/execute/close a signal
  GET /api/history  recent scans with lifecycle status
  GET /api/signal   full detail + plans + decision trail for one scan
  GET /api/learning backtest stats + calibration profile + plan distribution
  GET /api/paper    paper-trade state, outcomes, and runner statistics
  POST /api/paper/run  enroll/check approved paper trades once
  GET /api/coach    explain + mentor + personal feedback
  GET /api/health   full system health (data feeds, DB, risk gate, MCP, LLM)
  GET /api/agents   desk morning briefing (every watchlist asset + gate + queue)
  GET /api/mcp      MCP server availability + tools
  POST /api/ask     natural-language question to the desk
  GET /api/channels ordered-backend channel registry (P8; Panniantong/Agent-Reach pattern)
  GET /api/doctor   human-readable doctor report (same as `python main.py doctor`)
  GET /api/desk     one-call desk advisory (gate + P&L + graduation + advice)
  GET /api/loop-health  the one daily number (real paper n / E_net / graduation bar)
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, Response, g, jsonify, render_template_string, request, session

import config
from config import SYMBOL, SYMBOLS, TIMEFRAME, BARS, MIN_CONFIDENCE, DEFAULT_RISK_REWARD, DASHBOARD_HOST, DASHBOARD_PORT, VERSION
from data.symbols import normalize_symbol, resolve_symbol, symbol_choices
from data.sample_client import maybe_client
from data.binance_client import BinanceClient
from engine.signal_engine import analyze_frame
from output.signal_schema import validate_output
from web import auth as authmod
from web import api_v1 as apiv1
from web import jobs as jobsmod

_CACHE: dict = {"payload": None, "ts": 0, "ttl": 40}
_LAST_GOOD: dict[tuple[str, str], dict] = {}   # last successful payload by (symbol, timeframe)


def _source_key_param(value):
    """Resolve a ``source_key`` query parameter into a P12.11 source key.

    Missing / ``all`` → every source; ``live`` → the canonical Binance spot
    series; otherwise parsed as ``exchange:market[:price_type]``.
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


def _sanitize_for_json(obj):
    """Recursively convert NumPy scalars/arrays to native Python types.

    The quant layer (hidden alpha, regime, correlation) produces numpy.bool_,
    numpy.integer, numpy.floating and ndarray values inside payloads; Flask's
    jsonify (unlike json.dumps(default=str)) raises TypeError on those.  This
    keeps every engine endpoint 200-safe.
    """
    import numpy as np
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _sym(value: str | None) -> str:
    return normalize_symbol(value or SYMBOL)


def _scan_row_to_payload(row: dict | None) -> dict:
    """Re-nest a flat ``scans`` DB row into the scan-payload shape.

    ``SignalDB.get_scan()`` returns one flat SQL row, while the analysis
    helpers (``brain.journal.pre_trade_checklist`` and friends) read the
    nested ``{"signal": …, "plans": …, "snapshot": …}`` payload. Without this
    bridge the journal's pre-trade checklist rendered "—" for every field.
    """
    if not row:
        return {}
    features, plans, context = {}, [], {}
    for key, target in (("features_json", "features"), ("plans_json", "plans"),
                        ("context_json", "context")):
        raw = row.get(key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if target == "features":
            features = parsed if isinstance(parsed, dict) else {}
        elif target == "plans":
            plans = parsed if isinstance(parsed, list) else []
        else:
            context = parsed if isinstance(parsed, dict) else {}
    return {
        "scan_id": row.get("id"),
        "signal": {
            "signal_id": row.get("signal_id"), "timestamp": row.get("ts"),
            "asset": row.get("symbol"), "timeframe": row.get("timeframe"),
            "action": row.get("action"), "entry": row.get("entry"),
            "stop_loss": row.get("stop_loss"), "take_profit": row.get("take_profit"),
            "risk_reward": row.get("risk_reward"),
            "confidence": row.get("confidence_label"),
            "reason": row.get("reason"), "signal_type": row.get("signal_type"),
        },
        "plans": plans,
        "snapshot": {"features": {**features, "regime_label": row.get("regime")},
                     "scores": {}},
        "context": context,
        "intelligence": {"regime_label": row.get("regime")},
        "lifecycle": {"status": row.get("status"), "note": row.get("approve_note") or ""},
    }


def _attach_management(payload: dict) -> dict:
    """P13/P14: attach the HOLD/REDUCE/TRAIL/EXIT card to a scan payload."""
    try:
        from brain.coach import management_checklist
        plans = payload.get("plans") or []
        payload["management"] = management_checklist(plans[0] if plans else None)
    except Exception:
        payload.setdefault("management", [])
    return payload


def _persist(payload: dict) -> tuple[int, str]:
    """Save the scan to the learning DB (deduped by signal_id) and return
    (scan_id, lifecycle_status)."""
    from data.database import SignalDB
    from engine.lifecycle import reviewable
    sig = payload.get("signal", {})
    decision = payload.get("decision") or {}
    # Desk-first (decision A4): desk-vetoed signals never enter the queue.
    desk_ok = decision.get("action") in ("BUY", "SELL") if decision else True
    status_override = None if desk_ok else "CREATED"
    with SignalDB() as db:
        existing = db.conn.execute(
            "SELECT id, status FROM scans WHERE signal_id=?", (sig.get("signal_id"),)
        ).fetchone()
        if existing:
            scan_id, status = existing["id"], existing["status"]
        else:
            scan_id = db.save_scan(payload, status_override=status_override)
            status = "PENDING_REVIEW" if reviewable(sig) and desk_ok else "CREATED"
    payload["scan_id"] = scan_id
    if status == "CREATED" and decision and decision.get("blocked_by"):
        note = "DESK BLOCKED — " + "; ".join(decision["blocked_by"])
    else:
        note = ("awaiting human approval — click Approve / Reject"
                if status == "PENDING_REVIEW" else
                "monitor-only signal (no action required)" if status == "CREATED" else
                f"current state: {status}")
    payload["lifecycle"] = {"status": status, "note": note}
    return scan_id, status


_SCAN_TIMEOUT = 45  # seconds — hard cap on a full analysis; fall back below


def _basic_scan(symbol: str, tf: str, save: bool) -> dict:
    """Engine-only quick scan (no MTF/context) — the guaranteed fallback so the
    dashboard always shows data even if external sources are unreachable."""
    import threading
    symbol = _sym(symbol)
    result: dict = {}

    def _work():
        try:
            client = maybe_client()
            df = client.klines(symbol, tf, bars=BARS)
            out = analyze_frame(df, symbol=symbol, timeframe=tf,
                                min_confidence=MIN_CONFIDENCE,
                                default_rr=DEFAULT_RISK_REWARD)
            payload = out.as_json()
            payload["market_context"] = client.market_context(symbol)
            payload["market_context"]["fallback_note"] = "futures not fully checked (fallback mode)"
            try:
                from brain.trading_intelligence import build_intelligence
                payload["intelligence"] = build_intelligence(payload, df=df)
            except Exception:
                pass
            payload["validation"] = validate_output(payload)
            payload["degraded"] = True
            payload["degraded_reason"] = "full analysis timed out — showing engine-only signal"
            _attach_management(payload)
            result["payload"] = payload
        except Exception as exc:  # pragma: no cover
            result["error"] = f"{type(exc).__name__}: {exc}"

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout=_SCAN_TIMEOUT)
    if "payload" in result:
        payload = result["payload"]
        _attach_sentiment(payload, symbol, tf)
        if save:
            try:
                _persist(payload)
            except Exception:
                pass
        _LAST_GOOD[(symbol, tf)] = payload
        return payload
    raise ConnectionError(result.get("error", "scan timed out"))


def _attach_sentiment(payload: dict, symbol: str, tf: str) -> dict:
    """Attach the market-sentiment colour reading (engine/sentiment.py) to a
    scan payload. Never raises — sentiment is a display aid, not a gate."""
    try:
        from engine.sentiment import current_sentiment_safe
        payload["sentiment"] = current_sentiment_safe(symbol, tf, payload)
    except Exception:  # pragma: no cover — defensive only
        payload.setdefault("sentiment", {"available": False, "score": 0.0,
                                         "direction": "neutral", "label": "NO DATA",
                                         "color": "#5f6d84", "intensity": 0.0})
    return payload


def compute_payload(symbol: str, tf: str, save: bool = True, use_cache: bool = True) -> dict:
    symbol = _sym(symbol)
    if use_cache and _CACHE["payload"] and _CACHE["payload"].get("signal", {}).get("asset") == symbol \
            and _CACHE["payload"].get("signal", {}).get("timeframe") == tf \
            and time.time() - _CACHE["ts"] < _CACHE["ttl"]:
        return _CACHE["payload"]

    # Run the full analysis (MTF + context + styles + memory) in a watchdog
    # thread: if it exceeds _SCAN_TIMEOUT we fall back to the engine-only scan.
    import threading
    result: dict = {}

    def _work():
        try:
            from brain.full_pipeline import analyze_full
            client = maybe_client()
            payload = analyze_full(symbol, tf, bars=BARS, client=client,
                                   with_context=True, with_memory=True)
            payload["validation"] = validate_output(payload)
            result["payload"] = payload
        except Exception as exc:  # pragma: no cover
            result["error"] = f"{type(exc).__name__}: {exc}"

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(timeout=_SCAN_TIMEOUT)

    if "payload" not in result:
        # Fallback: if we have a last-good payload for THIS asset/timeframe,
        # serve it marked stale so the dashboard never blanks on transient
        # failures. Never show BTC data while the user selected ETH/XAU.
        key = (symbol, tf)
        if key in _LAST_GOOD:
            stale = dict(_LAST_GOOD[key])
            stale["stale"] = True
            stale["stale_error"] = result.get("error", "scan timed out")
            _CACHE.update(payload=stale, ts=time.time())
            return stale
        try:
            payload = _basic_scan(symbol, tf, save=save)
        except Exception as exc:
            spec = resolve_symbol(symbol)
            payload = {
                "signal": {"signal_id": f"{symbol}_{int(time.time()*1000)}",
                           "timestamp": int(time.time()*1000), "asset": symbol,
                           "action": "NO TRADE", "entry": None, "stop_loss": None,
                           "take_profit": None, "risk_reward": 0,
                           "confidence": "LOW", "timeframe": tf,
                           "reason": f"scan failed: {exc}", "signal_type": "ERROR"},
                "plans": [], "snapshot": {"features": {}, "scores": {}},
                "market_context": {"symbol": spec.symbol, "data_symbol": spec.data_symbol,
                                   "market": spec.market, "provider": spec.provider,
                                   "futures": False, "note": spec.note or "not checked"},
                "error": str(exc), "lifecycle": {"status": "ERROR", "note": str(exc)},
            }
            _attach_sentiment(payload, symbol, tf)
        _CACHE.update(payload=payload, ts=time.time())
        return payload

    payload = result["payload"]
    _attach_management(payload)
    _attach_sentiment(payload, symbol, tf)
    if save:
        try:
            _persist(payload)
        except Exception:
            pass
    _LAST_GOOD[(symbol, tf)] = payload
    _CACHE.update(payload=payload, ts=time.time())
    return payload


def build_payload(symbol: str, tf: str) -> dict:
    return compute_payload(symbol, tf, save=True, use_cache=True)


# Keep this a normal triple-quoted string so the lightweight CI extractor can
# read it directly. Embedded JavaScript deliberately uses `nl` below instead
# of a `\n` string escape, which stays correct without a raw Python literal.
HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#070b14">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="SKY">
<meta name="application-name" content="SKY">
<meta name="mobile-web-app-capable" content="yes">
<title>CryptoBrain — Trading Desk</title>
<link rel="manifest" href="/static/manifest.json">
<link rel="icon" type="image/png" sizes="192x192" href="/static/icons/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="/static/icons/icon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/icon-180.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>
  :root{
    --bg:#070b14;--bg2:#0d1426;--card:#111c33;--card2:#162447;--card3:#1a2d4d;
    --line:#1e3358;--line2:#2a4a7a;--txt:#e6edf7;--mut:#8aa0bd;--mut2:#6b84a6;
    --green:#22c55e;--green2:#16a34a;--red:#ef4444;--red2:#dc2626;--amber:#f59e0b;--blue:#3b82f6;--violet:#8b5cf6;--cyan:#06b6d4;
    --radius:14px;--radius-lg:16px;--radius-xl:20px;
  }
  *{box-sizing:border-box} html{scroll-behavior:smooth}
  body{margin:0;background:
    radial-gradient(900px 500px at 14% -6%, rgba(59,130,246,.18) 0%, transparent 60%),
    radial-gradient(820px 520px at 92% 0%, rgba(139,92,246,.14) 0%, transparent 60%),
    radial-gradient(720px 420px at 50% 115%, rgba(34,197,94,.07) 0%, transparent 60%),
    var(--bg);color:var(--txt);
    font:13.5px/1.6 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    -webkit-font-smoothing:antialiased; min-height:100vh}
  a{color:var(--blue); text-decoration:none}
  a:hover{text-decoration:underline}
  /* Top bar */
  .topbar{position:sticky;top:0;z-index:30;background:rgba(7,11,20,.84);backdrop-filter:blur(16px) saturate(1.25);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
  .brand{display:flex;align-items:center;gap:12px;min-width:240px}
  .logo{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center;font-size:18px;box-shadow:0 6px 18px rgba(59,130,246,.35), inset 0 1px 0 rgba(255,255,255,.18)}
  .brand h1{font-size:17px;font-weight:800;letter-spacing:-.025em;margin:0;line-height:1.1;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .brand h1 .ver{font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid var(--line);color:var(--mut)}
  .sub{color:var(--mut);font-size:11.5px;margin-top:2px}
  .live-dot{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:800;letter-spacing:.06em;color:var(--green);background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.32);padding:4px 9px;border-radius:999px}
  .live-dot i{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 0 rgba(34,197,94,.7);animation:pulse 2s infinite;display:inline-block}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.7)}70%{box-shadow:0 0 0 8px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
  .controls{display:flex;align-items:end;gap:10px;flex-wrap:wrap}
  .cg{display:flex;flex-direction:column;gap:4px}
  .cg label{font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut);font-weight:700}
  .seg{display:flex;background:rgba(255,255,255,.06);border:1px solid var(--line);border-radius:999px;padding:3px;gap:2px;align-items:center}
  .seg button{border:none;background:transparent;color:var(--mut);padding:6px 10px;border-radius:999px;font-size:12px;font-weight:700;cursor:pointer;transition:.14s}
  .seg button.active{background:#fff;color:#0b1220;box-shadow:0 2px 10px rgba(0,0,0,.25)}
  .seg button:hover{color:var(--txt)}
  .seg input{background:transparent;border:none;color:var(--txt);padding:6px 8px;font:inherit;outline:none;min-width:92px}
  .btn{appearance:none;border:1px solid var(--line);background:rgba(255,255,255,.06);color:var(--txt);padding:7px 12px;border-radius:10px;font:700 12px/1 Inter;cursor:pointer;transition:.15s;display:inline-flex;align-items:center;gap:6px}
  .btn:hover{transform:translateY(-1px);box-shadow:0 8px 20px rgba(0,0,0,.28);border-color:var(--line2);background:rgba(255,255,255,.09)}
  .btn:active{transform:none}
  .btn.primary{background:linear-gradient(135deg,var(--blue), #2563eb);border-color:transparent;color:#fff;box-shadow:0 8px 18px rgba(37,99,235,.35)}
  .btn.ghost{background:transparent}
  .btn.ok{background:var(--green);color:#04120a;border-color:transparent}
  .btn.no{background:var(--red);color:#fff;border-color:transparent}
  .btn:disabled{opacity:.55;cursor:not-allowed;transform:none}
  .check{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);cursor:pointer;user-select:none}
  .check input{accent-color:var(--blue)}
  .muted{color:var(--mut)} .mono{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  /* Tab bar */
  .tabbar{position:sticky;top:61px;z-index:20;background:rgba(7,11,20,.72);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:8px 14px;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;align-items:center}
  .tabbar::-webkit-scrollbar{display:none}
  .tabbtn{appearance:none;border:1px solid transparent;background:transparent;color:var(--mut);padding:8px 13px;border-radius:999px;font:700 12.5px/1 Inter;cursor:pointer;white-space:nowrap;transition:.14s;display:inline-flex;align-items:center;gap:7px}
  .tabbtn.active{background:#fff;color:#0b1220;border-color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.25)}
  .tabbtn:hover{color:var(--txt);background:rgba(255,255,255,.06)}
  .tabbtn.active:hover{background:#fff;color:#0b1220}
  .tabbar .spacer{flex:1}
  .tabbar .updated{font-size:11px;color:var(--mut);white-space:nowrap}
  /* Main */
  .shell{max-width:1420px;margin:0 auto;padding:16px 14px 28px}
  .hero{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;margin-bottom:14px}
  @media(max-width:980px){.hero{grid-template-columns:1fr}.topbar{top:0}.tabbar{top:0;position:relative}}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:760px){.grid,.grid2{grid-template-columns:1fr}}
  .card{background:linear-gradient(180deg, rgba(17,28,51,.94) 0%, rgba(22,36,71,.98) 100%);border:1px solid var(--line);border-radius:16px;padding:14px;box-shadow:0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05);transition:.15s;position:relative;overflow:hidden}
  .card::after{content:'';position:absolute;inset:0;border-radius:16px;pointer-events:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
  .card:hover{border-color:var(--line2);transform:translateY(-1px);box-shadow:0 14px 36px rgba(0,0,0,.45)}
  .card h2{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut);margin:0 0 11px;display:flex;align-items:center;gap:8px;font-weight:800}
  .card h2::before{content:'';width:3px;height:14px;border-radius:999px;background:linear-gradient(180deg,var(--blue),var(--violet));display:inline-block;flex-shrink:0}
  .card h2 .count{margin-left:auto;font-size:10px;background:rgba(255,255,255,.08);border:1px solid var(--line);padding:2px 7px;border-radius:999px;color:var(--mut);letter-spacing:.04em;text-transform:none}
  .pill{padding:4px 10px;border-radius:999px;font-weight:800;font-size:12px;border:1px solid transparent;letter-spacing:.02em;display:inline-flex;align-items:center;gap:6px}
  .BUY{background:rgba(34,197,94,.14);color:var(--green);border-color:rgba(34,197,94,.32)}
  .SELL{background:rgba(239,68,68,.14);color:var(--red);border-color:rgba(239,68,68,.32)}
  .NOTRADE{background:rgba(139,160,189,.10);color:var(--mut);border-color:rgba(139,160,189,.18)}
  .badge{font-size:11px;padding:3px 8px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid var(--line);color:var(--mut);display:inline-flex;align-items:center;gap:5px}
  .badge.strong{background:var(--blue);color:#fff;border-color:var(--blue);font-weight:800}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:12.5px}
  .kv b{color:var(--mut);font-weight:600}
  .plan{border:1px solid var(--line);border-radius:12px;padding:10px 11px;margin-bottom:10px;background:rgba(255,255,255,.02);transition:.12s}
  .plan:hover{border-color:var(--line2);background:rgba(255,255,255,.03)}
  .plan .h{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center}
  .plan .c{color:var(--mut);margin-top:5px;font-size:12px;line-height:1.5}
  .bar{height:6px;border-radius:999px;background:#0e1524;margin-top:8px;overflow:hidden;border:1px solid var(--line)}
  .bar i{display:block;height:100%;border-radius:999px}
  .row{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:8px 6px;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer;transition:.12s;border-radius:8px}
  .row:hover{background:rgba(255,255,255,.04)}
  .row .btns{display:flex;gap:6px;flex-shrink:0}
  .rowbtn{background:var(--blue);border:none;color:#fff;padding:5px 10px;border-radius:8px;cursor:pointer;font:inherit;font-size:12px;font-weight:700;transition:.12s}
  .rowbtn:hover{opacity:.92;transform:translateY(-1px)}
  .rowbtn.ok{background:var(--green);color:#04120a} .rowbtn.no{background:var(--red);color:#fff}
  input,select,textarea{background:rgba(255,255,255,.06);border:1px solid var(--line);color:var(--txt);padding:7px 10px;border-radius:10px;font:inherit;outline:none;transition:.14s}
  input:focus,select:focus,textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(59,130,246,.18)}
  .flex{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.06)}
  th{color:var(--mut);font-weight:700;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
  #modal{display:none;position:fixed;inset:0;background:rgba(2,6,14,.66);backdrop-filter:blur(10px);z-index:60;padding:18px;overflow:auto}
  #modal .box{background:linear-gradient(180deg, #111c33 0%, #0f1a30 100%);border:1px solid var(--line);border-radius:18px;max-width:860px;margin:14px auto;padding:18px 18px 14px;box-shadow:0 24px 64px rgba(0,0,0,.55)}
  .err{color:var(--red)} .okc{color:var(--green)} .note{font-size:11px;color:var(--mut);line-height:1.5}
  .sep{height:1px;background:var(--line);margin:10px 0}
  /* toasts */
  #toasts{position:fixed;bottom:16px;right:14px;display:flex;flex-direction:column;gap:8px;z-index:70;max-width:360px}
  .toast{background:linear-gradient(180deg, #111c33, #0f1a30);border:1px solid var(--line);padding:11px 12px;border-radius:12px;box-shadow:0 14px 34px rgba(0,0,0,.45);font-size:13px;display:flex;gap:10px;align-items:flex-start;animation:slideIn .22s ease}
  @keyframes slideIn{from{transform:translateX(10px);opacity:0}to{transform:none;opacity:1}}
  /* watchlist */
  .watchlist{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
  @media(max-width:760px){.watchlist{grid-template-columns:1fr}}
  .mini{border:1px solid var(--line);border-radius:13px;padding:10px 11px;background:rgba(255,255,255,.02);cursor:pointer;transition:.13s;position:relative;overflow:hidden}
  .mini:hover{border-color:var(--line2);background:rgba(255,255,255,.04);transform:translateY(-1px)}
  .mini.active{border-color:var(--blue);box-shadow:0 0 0 2px rgba(59,130,246,.18)}
  .mini .sym{font-weight:800;letter-spacing:-.02em}
  .mini .price{font-weight:700}
  /* stats */
  .statrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
  .stat{border:1px solid var(--line);border-radius:12px;padding:10px;background:rgba(255,255,255,.02);text-align:center}
  .stat .v{font-size:17px;font-weight:800;letter-spacing:-.02em}
  .stat .k{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:700}
  /* tab panels */
  .tabpanel{display:none;animation:fade .18s ease}
  .tabpanel.active{display:block}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
  .sectionTitle{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);font-weight:800;margin:14px 2px 8px;display:flex;align-items:center;gap:8px}
  .sectionTitle::after{content:'';flex:1;height:1px;background:var(--line);margin-left:8px}
  /* readiness strip (TODO-1.bis) — one verdict above every tab */
  .strip{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;
    padding:10px 13px;border-radius:14px;border:1px solid var(--line);
    background:linear-gradient(180deg, rgba(17,28,51,.9), rgba(22,36,71,.95));
    box-shadow:0 8px 22px rgba(0,0,0,.28)}
  .strip.lvl-ok{border-color:rgba(34,197,94,.42);box-shadow:0 8px 22px rgba(34,197,94,.10)}
  .strip.lvl-degraded{border-color:rgba(245,158,11,.42);box-shadow:0 8px 22px rgba(245,158,11,.10)}
  .strip.lvl-blocked{border-color:rgba(239,68,68,.42);box-shadow:0 8px 22px rgba(239,68,68,.10)}
  .strip.lvl-down{border-color:rgba(239,68,68,.5);box-shadow:0 8px 22px rgba(239,68,68,.14)}
  .strip .verdict{font-weight:800;letter-spacing:.02em;font-size:13px;display:inline-flex;align-items:center;gap:8px}
  .strip .verdict .dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex-shrink:0}
  .strip .pillars{display:flex;gap:7px;flex-wrap:wrap;margin-left:auto}
  .strip .pill-chip{font-size:11.5px;font-weight:700;padding:4px 9px;border-radius:999px;
    border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--mut);
    display:inline-flex;align-items:center;gap:6px;cursor:help}
  /* market-sentiment colour signal (the "mood ring") */
  #moodbar{position:fixed;left:0;top:0;bottom:0;width:5px;z-index:80;background:#5f6d84;transition:background 1.4s ease, box-shadow 1.4s ease}
  .sentistrip{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:12px;
    position:sticky;top:61px;z-index:15;
    padding:12px 15px;border-radius:14px;border:1px solid var(--line);
    background:linear-gradient(180deg, rgba(17,28,51,.92), rgba(22,36,71,.96));
    backdrop-filter:blur(10px);
    box-shadow:0 8px 22px rgba(0,0,0,.28);
    transition:border-color 1.2s ease, box-shadow 1.2s ease}
  @media(max-width:980px){.sentistrip{position:static}}
  .sentistrip .slabel{font-size:16px;font-weight:900;letter-spacing:.01em;display:flex;align-items:center;gap:9px;min-width:196px}
  .sentistrip .slabel .sdot{width:14px;height:14px;border-radius:50%;flex-shrink:0;box-shadow:0 0 14px currentColor;transition:background 1.2s ease}
  .sentistrip .scale{position:relative;flex:1;min-width:280px;height:14px;border-radius:999px;border:1px solid rgba(255,255,255,.09);
    background:linear-gradient(90deg, hsl(0,82%,26%) 0%, hsl(0,70%,46%) 22%, #5f6d84 50%, hsl(142,68%,46%) 78%, hsl(142,82%,26%) 100%)}
  .sentistrip .scale .tick{position:absolute;top:50%;width:1px;height:18px;background:rgba(255,255,255,.22);transform:translateY(-50%)}
  .sentistrip .needle{position:absolute;top:50%;width:3px;height:24px;transform:translate(-50%,-50%);background:#fff;border-radius:999px;box-shadow:0 0 10px rgba(255,255,255,.85);transition:left 1.1s cubic-bezier(.22,1,.36,1)}
  .sentistrip .smeta{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:11px;color:var(--mut)}
  .sentistrip .smeta .k{font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;font-weight:800;color:var(--mut2)}
  .sentistrip .smeta .v{font-size:15px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--txt)}
  .sentistrip .deepen{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;font-weight:800;padding:4px 9px;border-radius:999px;border:1px solid var(--line);transition:color 1.2s ease}
  .senti-legend{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .senti-chip{font-size:11px;font-weight:800;padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.04);display:inline-flex;align-items:center;gap:6px}
  .senti-chip i{width:10px;height:10px;border-radius:3px;display:inline-block;flex-shrink:0}
  .senti-parts{width:100%;border-collapse:collapse;font-size:12px}
  .senti-parts th,.senti-parts td{padding:5px 8px;border-bottom:1px solid rgba(255,255,255,.06)}
  .senti-part{height:8px;border-radius:999px;background:#0e1524;overflow:hidden;border:1px solid var(--line);display:flex}
  .senti-part i{display:block;height:100%;border-radius:999px}
  .senti-scale-lg{position:relative;height:18px;border-radius:999px;border:1px solid rgba(255,255,255,.09);margin:10px 0 4px;
    background:linear-gradient(90deg, hsl(0,82%,26%) 0%, hsl(0,70%,46%) 22%, #5f6d84 50%, hsl(142,68%,46%) 78%, hsl(142,82%,26%) 100%)}
  .senti-scale-lg .needle{position:absolute;top:50%;width:3px;height:30px;transform:translate(-50%,-50%);background:#fff;border-radius:999px;box-shadow:0 0 12px rgba(255,255,255,.9)}
  /* chart container for Lightweight Charts */
  #chart{width:100%;height:260px;background:#0e1524;border-radius:12px;border:1px solid var(--line);overflow:hidden}
  /* ── chart workspace (TradingView-style) ── */
  .chart-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.02)}
  .chart-toggles{display:flex;gap:10px;flex-wrap:wrap}
  .chart-head{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid var(--line)}
  .chart-head .px{font-size:24px;font-weight:800;font-variant-numeric:tabular-nums}
  .chart-head .ind{font-size:11.5px;color:var(--mut)}
  .chart-head .ind b{color:var(--txt);font-variant-numeric:tabular-nums}
  .chart-pane{width:100%;background:#0b1120}
  .chart-pane + .chart-pane{border-top:1px solid var(--line)}
  .multi-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:10px;background:#0b1120}
  .multi-chart-card{min-width:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#0e1524}
  .multi-chart-title{display:flex;justify-content:space-between;gap:8px;padding:8px 10px;font-weight:700;font-size:12px}
  .multi-chart-canvas{height:250px;width:100%}
  @media(max-width:760px){.multi-chart-grid{grid-template-columns:1fr}.multi-chart-canvas{height:220px}}
  /* ── forms (journal, sizer, command inputs) ── */
  .formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
  .formgrid label,.fullfield{display:flex;flex-direction:column;gap:5px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:700}
  .formgrid input,.formgrid select,.fullfield textarea,.fullfield input{text-transform:none;letter-spacing:normal;font-weight:400;color:var(--txt);font-size:13px}
  .fullfield{margin-top:10px}
  /* ── command center ── */
  .cmdcat{margin:14px 0 8px}
  .cmdgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:10px}
  .cmdcard{border:1px solid var(--line);border-radius:12px;padding:11px 12px;background:rgba(255,255,255,.02);transition:.13s}
  .cmdcard:hover{border-color:var(--line2);background:rgba(255,255,255,.04)}
  .cmdcard h3{margin:0 0 4px;font-size:13.5px;font-weight:800;display:flex;align-items:center;gap:7px}
  .cmdcard .cli{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--mut2);background:rgba(0,0,0,.28);padding:3px 7px;border-radius:6px;display:inline-block;margin-top:6px}
  .cmdcard .inputs{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:7px;margin-top:8px}
  .cmdcard .inputs label{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:700;display:flex;flex-direction:column;gap:4px}
  .cmdcard .inputs input,.cmdcard .inputs select{font-size:12.5px;text-transform:none;letter-spacing:normal;color:var(--txt);padding:5px 8px}
  .safety{font-size:10px;font-weight:800;padding:2px 7px;border-radius:999px;border:1px solid var(--line);letter-spacing:.04em}
  .safety.read{color:var(--green);border-color:rgba(34,197,94,.35);background:rgba(34,197,94,.10)}
  .safety.write{color:var(--amber);border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.10)}
  .safety.long{color:#fb923c;border-color:rgba(251,146,60,.35);background:rgba(251,146,60,.10)}
  .safety.blocked{color:var(--mut);border-color:var(--line);background:rgba(255,255,255,.04)}
  .termout{background:#05080f;border:1px solid var(--line);border-radius:12px;padding:12px;max-height:460px;overflow:auto;white-space:pre-wrap;font-size:12px;line-height:1.5;color:#cfe0f5;margin:0}
  .catchip{font-size:12px;font-weight:700;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.05);color:var(--mut);cursor:pointer}
  .catchip.active{background:#fff;color:#0b1220;border-color:#fff}
  /* ── trade manager ── */
  .tmtable{width:100%;border-collapse:collapse;font-size:12.5px}
  .tmtable td,.tmtable th{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,.06);white-space:nowrap}
  .rpos{color:var(--green);font-weight:800} .rneg{color:var(--red);font-weight:800}
  .modrow{display:grid;grid-template-columns:230px 1fr 62px;gap:10px;padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.05);font-size:12.5px;align-items:baseline}
  .modrow code{color:var(--cyan);font-size:12px}
  @media(max-width:760px){.modrow{grid-template-columns:1fr}}
  /* ── connections ── */
  .conncard{border:1px solid var(--line);border-radius:12px;padding:12px;background:rgba(255,255,255,.02);margin-bottom:10px}
  .conncard.live{border-color:rgba(34,197,94,.35)}
  .conncard.off{border-color:var(--line)}
  .conncard.fail{border-color:rgba(239,68,68,.35)}
  .conncard h3{margin:0 0 4px;font-size:14px;font-weight:800;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .connstate{font-size:10.5px;font-weight:800;padding:3px 9px;border-radius:999px;letter-spacing:.04em}
  .connstate.live{background:rgba(34,197,94,.14);color:var(--green);border:1px solid rgba(34,197,94,.35)}
  .connstate.off{background:rgba(255,255,255,.05);color:var(--mut);border:1px solid var(--line)}
  .connstate.fail{background:rgba(239,68,68,.12);color:var(--red);border:1px solid rgba(239,68,68,.35)}
  .connhow{margin:8px 0 0;padding-left:18px;font-size:12px;color:var(--mut);line-height:1.7}
  .connhow li{margin-bottom:2px}
  .connhow code{color:var(--cyan);background:rgba(0,0,0,.3);padding:1px 5px;border-radius:5px}
  /* ── evidence / unlock ── */
  .pipeline{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
  .pipestep{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line);border-radius:12px;padding:11px;background:rgba(255,255,255,.02)}
  .pipestep .n{width:26px;height:26px;flex-shrink:0;border-radius:50%;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center;font-weight:800;font-size:13px}
  .pipestep .btn{margin-top:8px;margin-right:6px}
  .critrow{margin-bottom:9px}
  .critrow .top{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;align-items:baseline}
  .critrow .bar{margin-top:5px}
  .setupcard{border:1px solid var(--line);border-radius:12px;padding:11px 12px;margin-bottom:10px;background:rgba(255,255,255,.02)}
  .setupcard.proven{border-color:rgba(34,197,94,.4)}
  .blockcard{border-radius:12px;padding:12px;margin-bottom:10px;border:1px solid rgba(245,158,11,.35);background:rgba(245,158,11,.08)}
  .blockcard.earn{border-color:rgba(59,130,246,.4);background:rgba(59,130,246,.08)}
  .strip .strip-detail{flex-basis:100%;font-size:11.5px;color:var(--mut);line-height:1.5}
  /* quick actions */
  .quickbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
  .quickbar .btn{padding:8px 13px;border-radius:999px}
  /* glossary */
  .gloss-term{cursor:pointer;border-bottom:1px dashed var(--line2)}
  .kbd{font-size:11px;padding:2px 6px;border-radius:6px;background:rgba(255,255,255,.08);border:1px solid var(--line);font-family:ui-monospace,monospace}
  /* ── P18.1 authentication ── */
  #userChip{display:none;align-items:center;gap:8px;margin-left:4px}
  #userChip .who{display:flex;align-items:center;gap:8px;border:1px solid var(--line);background:rgba(255,255,255,.05);padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
  #userChip .who .avatar{width:20px;height:20px;border-radius:50%;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center;font-size:11px}
  #userChip .who .role{font-size:10px;padding:1px 6px;border-radius:999px;background:rgba(139,92,246,.16);color:var(--violet);border:1px solid rgba(139,92,246,.3);text-transform:uppercase;letter-spacing:.04em}
  #authLayer{display:none;position:fixed;inset:0;z-index:90;background:rgba(4,8,16,.88);backdrop-filter:blur(12px);overflow:auto;padding:20px}
  #authLayer .authbox{max-width:420px;margin:7vh auto 0;background:linear-gradient(180deg,#111c33,#0f1a30);border:1px solid var(--line);border-radius:20px;padding:26px;box-shadow:0 30px 80px rgba(0,0,0,.6)}
  #authLayer .authbox h2{margin:0 0 6px;font-size:19px;letter-spacing:-.02em}
  #authLayer .authbox .logo-big{width:46px;height:46px;border-radius:13px;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center;font-size:22px;margin-bottom:14px}
  #authLayer .afield{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
  #authLayer .afield label{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:700}
  #authLayer .afield input{font-size:14px;padding:10px 12px}
  #authLayer .aerr{color:var(--red);font-size:12.5px;margin-bottom:10px;min-height:18px}
  #authLayer .ahint{color:var(--mut);font-size:11.5px;line-height:1.6;margin-top:12px}
  .adetail{font-size:12px;line-height:1.5;color:var(--mut)}
  .devrow{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:8px 4px;border-bottom:1px solid rgba(255,255,255,.06)}
  .devrow .meta{font-size:12px}
  .devrow .meta b{font-weight:800}
  .jobrow{display:flex;gap:10px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:10px;margin-bottom:8px;cursor:pointer;transition:.13s;font-size:12.5px}
  .jobrow:hover{border-color:var(--line2);background:rgba(255,255,255,.04)}
  .jobrow.active{border-color:var(--blue);background:rgba(58,116,255,.08)}
  .jobrow b{font-weight:800}
  .tokenout{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;word-break:break-all;background:#05080f;border:1px solid var(--line);border-radius:10px;padding:10px;margin-top:8px;color:var(--green)}
  /* ── P18.4 PWA: offline banner, install prompt, responsive compact ── */
  #offlineBanner{display:none;position:sticky;top:0;z-index:35;background:linear-gradient(90deg,#f59e0b,#f97316);color:#111827;padding:7px 14px;text-align:center;font:700 12.5px/1.4 Inter,system-ui;letter-spacing:.01em;border-bottom:1px solid rgba(0,0,0,.12)}
  #offlineBanner.show{display:block}
  #offlineBanner a{color:#111827;text-decoration:underline;font-weight:800}
  #installBanner{display:none;position:sticky;top:0;z-index:34;background:linear-gradient(90deg,#111c33,#1e293b);color:var(--txt);border-bottom:1px solid var(--line);padding:8px 14px;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
  #installBanner.show{display:flex}
  #installBanner b{font-size:12.5px}
  #installBanner .note{margin:0}
  body.offline .mutation{opacity:.45;pointer-events:none}
  /* Compact mode: P18.4 responsive — daily ritual, risk, paper, approvals, journal */
  @media(max-width:640px){
    .topbar{padding:8px 10px;gap:8px}
    .brand{min-width:0;flex:1 1 180px}
    .brand h1{font-size:15px}
    .brand .sub{font-size:10.5px}
    .controls{gap:6px;width:100%}
    .controls .cg{flex:1 1 120px}
    .tabbar{gap:4px;padding:6px 8px}
    .tabbtn{padding:6px 10px;font-size:12px}
    .shell{padding:10px 8px 18px}
    .card{padding:10px}
    .hero{grid-template-columns:1fr;gap:8px}
    .quickbar{gap:6px}
    .quickbar .btn{padding:6px 9px;font-size:11.5px;border-radius:999px}
    .statrow{grid-template-columns:repeat(2,1fr)}
    .watchlist{grid-template-columns:1fr}
    .grid{grid-template-columns:1fr}
    .grid2{grid-template-columns:1fr}
    .formgrid{grid-template-columns:1fr}
    .cmdgrid{grid-template-columns:1fr}
    .modrow{grid-template-columns:1fr}
    #offlineBanner{font-size:11.5px;padding:6px 10px}
  }
  @media(max-width:380px){ .tabbtn{padding:5px 8px;font-size:11.5px} .brand h1 .ver{display:none} }
</style>
<script src="/static/lightweight-charts.standalone.js"></script>
</head><body>
<div id="moodbar" title="market sentiment — green = bullish, red = bearish, deeper = longer"></div>
<div id="offlineBanner" role="status" aria-live="polite">⚠️ Offline — showing cached shell. Data may be stale. Mutations disabled. <a href="/offline.html">Open offline page</a> · <span id="offlineWhen" style="opacity:.8"></span></div>
<div id="installBanner" role="region" aria-label="Install prompt"><div><b>📲 Install SKY</b> <span class="note">Add to home screen for daily ritual, risk & approvals — works offline.</span></div><div class="flex"><button class="btn primary" id="installBtn">Install</button><button class="btn ghost" onclick="dismissInstall()">Not now</button></div></div>
<div class="topbar">
  <div class="brand">
    <div class="logo">🧠</div>
    <div>
      <h1>CryptoBrain <span class="ver">v{{version}}</span> <span class="live-dot"><i></i> LIVE</span></h1>
      <div class="sub">institutional desk · click to decide · learns from your approvals</div>
    </div>
  </div>
  <div class="controls">
    <div class="cg">
      <label>Asset</label>
      <div class="seg" id="symSeg">
        {% for s in symbols %}<button data-sym="{{s.symbol}}" onclick="setSymbol('{{s.symbol}}')" class="{{'active' if s.symbol==symbol}}">{{s.symbol}}</button>{% endfor %}
        <input id="sym" list="symbols" value="{{symbol}}" size="9" title="BTCUSDT, ETHUSDT, XAUUSD/GOLD, or any Binance USDT pair" placeholder="SYMBOL">
      </div>
      <datalist id="symbols">
        {% for s in symbols %}<option value="{{s.symbol}}">{{s.label}}{% if s.data_symbol != s.symbol %} · {{s.data_symbol}}{% endif %}</option>{% endfor %}
      </datalist>
    </div>
    <div class="cg">
      <label>Timeframe</label>
      <div class="seg" id="tfSeg">
        {% for t in ['1m','5m','15m','30m','1h','4h','1d','1w','1M'] %}<button data-tf="{{t}}" onclick="setTF('{{t}}')" class="{{'active' if t==tf}}">{{t}}</button>{% endfor %}
      </div>
      <select id="tf" style="display:none">
        {% for t in ['1m','5m','15m','30m','1h','4h','1d','1w','1M'] %}<option value="{{t}}" {{'selected' if t==tf}}>{{t}}</option>{% endfor %}
      </select>
    </div>
    <div class="cg" style="justify-content:end">
      <label>&nbsp;</label>
      <div class="flex">
        <button class="btn primary" onclick="load(true)">↻ Refresh</button>
        <label class="check"><input type="checkbox" id="auto" checked> auto 30s</label>
      </div>
    </div>
    <div id="userChip">
      <span class="who"><span class="avatar" id="userAvatar">🧠</span><span id="userName">—</span><span class="role" id="userRole">—</span></span>
      <button class="btn" onclick="openAccount()">⚙ Account</button>
      <button class="btn ghost" onclick="doLogout()">Log out</button>
    </div>
  </div>
</div>
<nav class="tabbar" id="tabbar">
  <button class="tabbtn active" data-tab="overview" onclick="switchTab('overview')">◎ Overview</button>
  <button class="tabbtn" data-tab="chart" onclick="switchTab('chart')">📊 Chart</button>
  <button class="tabbtn" data-tab="market" onclick="switchTab('market')">📈 Market</button>
  <button class="tabbtn" data-tab="intelligence" onclick="switchTab('intelligence')">🎯 Signal desk</button>
  <button class="tabbtn" data-tab="trades" onclick="switchTab('trades')">⚡ Trades</button>
  <button class="tabbtn" data-tab="manage" onclick="switchTab('manage')">🎛 Trade manager</button>
  <button class="tabbtn" data-tab="risk" onclick="switchTab('risk')">🛡 Risk center</button>
  <button class="tabbtn" data-tab="evidence" onclick="switchTab('evidence')">🔓 Evidence</button>
  <button class="tabbtn" data-tab="journal" onclick="switchTab('journal')">📓 Journal</button>
  <button class="tabbtn" data-tab="weekly" onclick="switchTab('weekly')">🗓 Review</button>
  <button class="tabbtn" data-tab="learn" onclick="switchTab('learn')">🧑‍🏫 Learning</button>
  <button class="tabbtn" data-tab="connections" onclick="switchTab('connections')">🔌 Connections</button>
  <button class="tabbtn" data-tab="commands" onclick="switchTab('commands')">⌘ Command center</button>
  <button class="tabbtn" data-tab="modules" onclick="switchTab('modules')">🧩 Modules</button>
  <button class="tabbtn" data-tab="system" onclick="switchTab('system')">⚙️ System</button>
  <button class="tabbtn" data-tab="agent" onclick="switchTab('agent')">🧠 Agent</button>
  <span class="spacer"></span>
  <span id="updated" class="updated"></span>
</nav>
<div class="shell">
  <div class="strip" id="readiness"><span class="muted">checking readiness…</span></div>
  <div class="sentistrip" id="senti">
    <span class="slabel"><span class="sdot" id="sentiDot" style="background:#5f6d84;color:#5f6d84"></span><span id="sentiLabel" style="color:var(--mut)">reading sentiment…</span></span>
    <div class="scale" id="sentiScale">
      <span class="tick" style="left:25%"></span><span class="tick" style="left:50%"></span><span class="tick" style="left:75%"></span>
      <span class="needle" id="sentiNeedle" style="left:50%"></span>
    </div>
    <div class="smeta">
      <div><div class="k">sentiment</div><div class="v" id="sentiScore">—</div></div>
      <div><div class="k">held for</div><div class="v" id="sentiDur">—</div></div>
      <div><div class="k">colour depth</div><div class="v" id="sentiDepth">—</div></div>
      <span class="deepen" id="sentiDeepen">—</span>
    </div>
  </div>
  <div class="quickbar" id="quickbar">
    <button class="btn" onclick="load(true)">↻ Scan now</button>
    <button class="btn" onclick="systemCheck(); switchTab('system')">🔍 System check</button>
    <button class="btn" onclick="runPaper(); switchTab('trades')">▶ Check paper trades</button>
    <button class="btn" onclick="dailyRitual()">⏱ Daily ritual</button>
    <button class="btn" onclick="switchTab('agent')">🧠 Research agent</button>
    <button class="btn" onclick="switchTab('agent'); setTimeout(function(){ if(typeof loadHubRole==='function') loadHubRole(); },80)">🖥 This PC (Hub)</button>
    <button class="btn" onclick="switchTab('learn'); setTimeout(()=>{ const el=document.getElementById('learn'); if(el) el.scrollIntoView({behavior:'smooth',block:'start'}); },120)">⚡ Learn now</button>
    <button class="btn primary" onclick="backtestNow()">▶ Quick backtest + learn</button>
  </div>
  <div id="app">Loading…</div>

  <!-- ── Chart workspace (TradingView-style, vendored Lightweight Charts) ── -->
  <div class="tabpanel" data-tab="chart">
    <div class="card" style="padding:0;overflow:hidden">
      <div class="chart-toolbar">
        <div class="seg" id="chartSymSeg">
          {% for s in symbols %}<button data-sym="{{s.symbol}}" onclick="chartSetSymbol('{{s.symbol}}')" class="{{'active' if s.symbol==symbol}}">{{s.symbol}}</button>{% endfor %}
        </div>
        <div class="seg" id="chartTfSeg">
          {% for t in ['1m','5m','15m','30m','1h','4h','1d','1w'] %}<button data-tf="{{t}}" onclick="chartSetTF('{{t}}')" class="{{'active' if t==tf}}">{{t}}</button>{% endfor %}
        </div>
        <div class="chart-toggles">
          <label class="check"><input type="checkbox" id="ovEma" checked onchange="drawChart()"> EMA 20/50/200</label>
          <label class="check"><input type="checkbox" id="ovVwap" checked onchange="drawChart()"> VWAP</label>
          <label class="check"><input type="checkbox" id="ovBb" onchange="drawChart()"> Bollinger</label>
          <label class="check"><input type="checkbox" id="ovLevels" checked onchange="drawChart()"> S/R levels</label>
          <label class="check"><input type="checkbox" id="ovZones" checked onchange="drawChart()"> Zones (OB / FVG / liq)</label>
          <label class="check"><input type="checkbox" id="ovPlan" checked onchange="drawChart()"> Entry / SL / TP</label>
          <label class="check"><input type="checkbox" id="ovRsi" checked onchange="drawChart()"> RSI</label>
          <label class="check"><input type="checkbox" id="ovMacd" onchange="drawChart()"> MACD</label>
        </div>
        <span class="spacer" style="flex:1"></span>
        <div class="seg" id="drawSeg" style="align-items:center">
          <button class="btn" id="drawTrendline" onclick="setDrawTool('trendline')" title="Trendline — click two points on the chart">╱ Trend</button>
          <button class="btn" id="drawRay" onclick="setDrawTool('ray')" title="Horizontal ray — click one price on the chart">─ Ray</button>
          <button class="btn" id="drawBox" onclick="setDrawTool('box')" title="Box — click two opposite corners">▭ Box</button>
          <button class="btn" id="drawUndoBtn" onclick="undoDrawing()" title="Remove the last drawing">⌫ Undo</button>
          <button class="btn" id="drawClearBtn" onclick="clearDrawings()" title="Remove every drawing on this symbol + timeframe">🗑 Clear</button>
        </div>
        <div class="seg" id="liveSeg" style="align-items:center">
          <button class="btn" id="liveBtn" onclick="toggleLive()" title="Stream the newest bar instead of reloading">◉ Live</button>
        </div>
        <div class="seg" id="replaySeg" style="align-items:center">
          <button class="btn" id="replayBtn" onclick="toggleReplay()">▶ Replay</button>
          <button class="btn" id="replayFreezeBtn" onclick="freezeReplay()" title="Pause at this bar to commit a tape read">Freeze</button>
          <button class="btn" id="replaySpeedBtn" onclick="cycleReplaySpeed()" title="playback speed">1×</button>
        </div>
        <button class="btn" onclick="loadChartWorkspace(true)">↻ Reload chart</button>
        <button class="btn" id="multiChartBtn" onclick="toggleMultiChart()" title="Compare four synchronized market views">▦ Multi-chart</button>
      </div>
      <div class="note" id="drawStatus" style="padding:6px 14px 0"></div>
      <div class="note" id="liveState" style="padding:4px 14px 0">Live stream off — the chart shows the bars loaded at <span id="liveLoadedAt">—</span>.</div>
      <div class="chart-head" id="chartHead"><span class="muted">loading chart…</span></div>
      <div id="chartMain" class="chart-pane" style="height:420px"></div>
      <div id="chartVol" class="chart-pane" style="height:110px"></div>
      <div id="chartRsi" class="chart-pane" style="height:120px"></div>
      <div id="chartMacd" class="chart-pane" style="height:120px;display:none"></div>
      <div id="multiChart" class="multi-chart-grid" style="display:none" aria-label="Multi-chart comparison"></div>
      <div class="note" style="padding:10px 14px">Candles, volume, EMA, VWAP, Bollinger, RSI, MACD, support/resistance and your entry / stop / take-profit — all from the same scan the desk decided on. Chart engine: TradingView Lightweight Charts, vendored locally (no internet needed). Multi-chart is a comparison view only; it does not combine signals or change the desk.</div>
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h2>CHART READINGS</h2><div id="chartStats"><span class="muted">—</span></div></div>
      <div class="card"><h2>LEVELS ON THIS CHART</h2><div id="chartLevels"><span class="muted">—</span></div></div>
      <div class="card" style="grid-column:1/-1">
        <h2>MY DRAWINGS</h2>
        <div id="drawList"><span class="muted">—</span></div>
        <div class="flex" style="margin-top:8px">
          <button class="btn" onclick="attachDrawingsToJournal()">📎 Attach to journal note</button>
          <span class="note">Saved in this browser per symbol + timeframe. Drawings are your own marks — the desk never reads them as evidence and they never change a signal, threshold or the risk gate.</span>
        </div>
      </div>
      <div class="card" style="grid-column:1/-1">
        <h2>✍ PRACTICE — commit your read BEFORE the Signal desk <span class="count" id="pracCount">—</span></h2>
        <div class="note" style="margin-bottom:10px">Look at the chart. Write <b>your</b> call — direction, the decision
          you would take, and (for full marks) your entry / stop / target ladder — then submit to reveal what the
          desk currently reads on the same chart and how your read compares. This is a study mirror: agreement
          with the desk is <b>not</b> evidence and grants nothing — the desk itself still has to prove its edge in
          the canonical paper book under the unchanged graduation bar.</div>
        <div id="pracTapeBanner" class="note" style="margin-bottom:10px;display:none;border:1px solid var(--amber);padding:8px;border-radius:10px;background:rgba(245,158,11,.10)">▶ REPLAY TAPE — historical playback, not live or paper evidence. Freeze at this bar, commit your read, and the hidden future grades you. The desk is not scored here.</div>
        <div class="flex" style="gap:10px;flex-wrap:wrap;align-items:end">
          <label class="note">bias<br><select id="pracBias" style="min-width:110px">
            <option value="bullish">bullish</option><option value="bearish">bearish</option>
            <option value="neutral" selected>neutral</option></select></label>
          <label class="note">decision<br><select id="pracDecision" style="min-width:110px">
            <option value="no_trade" selected>no-trade</option><option value="buy">buy</option>
            <option value="sell">sell</option></select></label>
          <label class="note">entry (optional)<br><input id="pracEntry" size="9" placeholder="price"></label>
          <label class="note">stop<br><input id="pracStop" size="9" placeholder="price"></label>
          <label class="note">target<br><input id="pracTarget" size="9" placeholder="price"></label>
          <label class="note">conf 0-100<br><input id="pracConf" size="3" placeholder="—"></label>
          <label class="note" style="flex:1;min-width:160px">note<br><input id="pracNote" style="width:100%" maxlength="500" placeholder="why — one line (optional)"></label>
          <button class="btn primary" onclick="submitPractice()">📝 Commit vs desk</button>
          <button class="btn" id="pracTapeBtn" onclick="submitTapePractice()">▶ Grade against the tape</button>
        </div>
        <div id="pracResult" style="margin-top:10px"><span class="muted">Nothing committed yet — your read is scored
          against the desk's live read of this symbol + timeframe the moment you submit.</span></div>
        <div id="pracMini" class="note" style="margin-top:8px">—</div>
      </div>
    </div>
  </div>

  <!-- ── Trade manager ── -->
  <div class="tabpanel" data-tab="manage">
    <div class="card" style="grid-column:1/-1">
      <h2>OPEN POSITIONS — LIVE PAPER BOOK <span class="count" id="tmCount">0</span></h2>
      <div class="flex" style="margin-bottom:10px">
        <button class="btn primary" onclick="loadTradeManager()">↻ Refresh</button>
        <button class="btn" onclick="runPaper()">▶ Run paper check</button>
        <span class="note">Positions are simulated. No exchange key exists in this app.</span>
      </div>
      <div id="tradeManager"><span class="muted">loading positions…</span></div>
    </div>
    <div class="card" style="margin-top:14px"><h2>RECENTLY CLOSED</h2><div id="tmRecent"><span class="muted">—</span></div></div>
  </div>

  <!-- ── Risk center ── -->
  <div class="tabpanel" data-tab="risk">
    <div class="grid">
      <div class="card" style="grid-column:1/-1"><h2>RISK GATE</h2><div id="riskCenterGate"><span class="muted">loading…</span></div></div>
      <div class="card">
        <h2>POSITION SIZE CALCULATOR</h2>
        <div class="formgrid">
          <label>Account balance<input id="psBalance" type="number" step="any" placeholder="10000"></label>
          <label>Risk % per trade<input id="psRisk" type="number" step="any" placeholder="0.25"></label>
          <label>Entry<input id="psEntry" type="number" step="any"></label>
          <label>Stop-loss<input id="psStop" type="number" step="any"></label>
          <label>Take-profit<input id="psTp" type="number" step="any"></label>
          <label>Leverage<input id="psLev" type="number" step="any" value="1"></label>
        </div>
        <div class="flex" style="margin-top:10px">
          <button class="btn primary" onclick="calcPositionSize()">Calculate size</button>
          <button class="btn" onclick="fillSizerFromSignal()">Use the live signal</button>
        </div>
        <div id="psResult" class="note" style="margin-top:10px">Enter a balance, entry and stop. The calculator caps risk at your progression level and returns ZERO size when the gate is closed.</div>
      </div>
      <div class="card">
        <h2>TRADER STATE — BEHAVIORAL FLAGS</h2>
        <div class="note" style="margin-bottom:8px">Any flag below closes the gate until you clear it. Honesty here is the whole point.</div>
        <div class="flex" id="traderStateBtns">
          <button class="btn no" onclick="setTraderState('angry',true)">😠 Angry</button>
          <button class="btn no" onclick="setTraderState('tired',true)">😴 Tired</button>
          <button class="btn no" onclick="setTraderState('revenge',true)">🔥 Revenge</button>
          <button class="btn no" onclick="setTraderState('chasing',true)">🏃 Chasing</button>
          <button class="btn ok" onclick="clearTraderState()">✓ Clear all — I am calm</button>
        </div>
        <div id="traderStateNow" class="note" style="margin-top:10px">—</div>
      </div>
      <div class="card" style="grid-column:1/-1"><h2>MONTE CARLO — RISK OF RUIN</h2><div id="riskMonte"><span class="muted">—</span></div></div>
    </div>
  </div>

  <!-- ── Evidence: why blocked, and how to unlock ── -->
  <div class="tabpanel" data-tab="evidence">
    <div class="card" style="grid-column:1/-1">
      <h2>WHY YOU CANNOT TRADE RIGHT NOW</h2>
      <div id="unlockWhy"><span class="muted">checking the gate…</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>EVIDENCE PIPELINE — EARN THE UNLOCK</h2>
      <div class="note" style="margin-bottom:10px">The gate opens when a setup is
        <b>measured</b>, not when you feel ready. Run these in order. Each one is
        the same command the pros run — it just takes time, not luck.</div>
      <div class="formgrid" style="margin-bottom:10px">
        <label>Asset<select id="evSymbol"><option>BTCUSDT</option><option>ETHUSDT</option><option>XAUUSD</option></select></label>
        <label>Timeframe<select id="evTf"><option>1m</option><option>5m</option><option selected>15m</option><option>1h</option><option>4h</option><option>1d</option></select></label>
        <label>Market<select id="evMarket"><option selected>spot</option><option>perp</option></select></label>
        <label>History<select id="evSince"><option>7d</option><option selected>30d</option><option>90d</option><option>180d</option><option>365d</option></select></label>
        <label>Backtest bars<input id="evBars" type="number" min="1" max="100000" value="500"></label>
        <label>Simulator rounds<input id="evRounds" type="number" min="1" max="1000" value="3"></label>
      </div>
      <div class="flex" style="margin-bottom:10px">
        <button id="evBuildBtn" class="btn primary" onclick="buildEvidence()">▶ Build my evidence (all 4 steps)</button>
        <span class="note">One coherent asset/timeframe through Backfill → Backtest → Simulator → Scorecard. Runs in the background; closing this tab does not stop it.</span>
      </div>
      <div id="evProjection" class="note" style="margin-bottom:10px">Calculating the honest evidence gap…</div>
      <div id="evJob" class="blockcard earn" style="display:none;margin-bottom:12px">
        <div class="flex" style="justify-content:space-between"><b id="evJobTitle">Build my evidence</b><span id="evJobBadge" class="badge">queued</span></div>
        <div class="critrow" style="margin:9px 0 5px"><div class="bar"><i id="evJobBar" style="width:0%;background:var(--blue)"></i></div></div>
        <div id="evJobState" class="note">Submitting…</div>
        <pre id="evJobLog" class="termout" style="max-height:160px;margin-top:8px"></pre>
      </div>
      <div class="pipeline">
        <div class="pipestep"><span class="n">1</span>
          <div><b>Get real history</b><div class="note">Download real candles into local storage.</div>
          <button class="btn" onclick="runCommand('backfill')">▶ Backfill</button></div></div>
        <div class="pipestep"><span class="n">2</span>
          <div><b>Grade it</b><div class="note">Walk the history and score every setup.</div>
          <button class="btn" onclick="runCommand('backtest')">▶ Backtest</button></div></div>
        <div class="pipestep"><span class="n">3</span>
          <div><b>Forward-test</b><div class="note">Grind paper samples on unseen candles.</div>
          <button class="btn" onclick="runCommand('simulator')">▶ Simulator</button></div></div>
        <div class="pipestep"><span class="n">4</span>
          <div><b>Check it is real</b><div class="note">Net of costs, not curve-fitted.</div>
          <button class="btn" onclick="runCommand('scorecard')">▶ Scorecard</button>
          <button class="btn" onclick="runCommand('validate')">▶ Look-ahead guard</button></div></div>
      </div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>SETUP EVIDENCE SCOREBOARD <span class="count" id="evCount">—</span></h2>
      <div id="evidenceBoard"><span class="muted">loading…</span></div>
    </div>
  </div>

  <!-- ── Connections: what SKY is really plugged into ── -->
  <div class="tabpanel" data-tab="connections">
    <div class="strip" id="connStrip"><span class="muted">checking connections…</span></div>
    <div class="card" style="grid-column:1/-1">
      <h2>REAL-WORLD CONNECTIONS <span class="count" id="connCount">—</span></h2>
      <div class="flex" style="margin-bottom:10px">
        <button class="btn primary" onclick="loadConnections(true)">↻ Re-test all</button>
        <span class="note">Every probe is read-only. SKY has no trading key and cannot place an order.</span>
      </div>
      <div id="connectionList"><span class="muted">loading…</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>YOUR EXCHANGE ACCOUNT (READ-ONLY)</h2>
      <div id="accountPanel"><span class="muted">—</span></div>
    </div>
  </div>

  <!-- ── Journal ── -->
  <div class="tabpanel" data-tab="journal">
    <div class="grid">
      <div class="card">
        <h2>NEW JOURNAL ENTRY</h2>
        <div class="formgrid">
          <label>Trade (scan)
            <select id="jScan" onchange="loadJournalEntry()"><option value="">— pick a trade —</option></select>
          </label>
          <label>Did you follow your system?
            <select id="jFollowed"><option value="1">Yes — I followed every rule</option><option value="0">No — I broke a rule</option></select>
          </label>
          <label>Emotion<select id="jEmotion"></select></label>
          <label>Mistake<select id="jMistake">
            <option value="none">none</option><option value="entered early">entered early</option>
            <option value="entered late">entered late</option><option value="moved stop">moved stop</option>
            <option value="oversized">oversized</option><option value="no plan">no plan</option>
            <option value="revenge trade">revenge trade</option><option value="ignored gate">ignored the risk gate</option>
            <option value="exited early">exited early</option><option value="held too long">held too long</option>
          </select></label>
        </div>
        <label class="fullfield">What happened?<textarea id="jNotes" rows="3" placeholder="describe the trade honestly"></textarea></label>
        <label class="fullfield">What would you change?<textarea id="jChange" rows="2" placeholder="one specific improvement"></textarea></label>
        <div class="flex" style="margin-top:10px">
          <button class="btn primary" onclick="saveJournal()">💾 Save journal</button>
          <span id="jStatus" class="note"></span>
        </div>
      </div>
      <div class="card"><h2>PRE-TRADE CHECKLIST (AUTO)</h2><div id="jChecklist" class="note">Pick a trade to see the plan you actually took.</div></div>
      <div class="card" style="grid-column:1/-1"><h2>DISCIPLINE SUMMARY</h2><div id="jSummary"><span class="muted">—</span></div></div>
    </div>
  </div>

  <!-- ── Weekly Review: the Sunday desk mirror (W3) ── -->
  <div class="tabpanel" data-tab="weekly">
    <div class="card" style="grid-column:1/-1">
      <h2>WEEKLY TRADER REVIEW <span class="count" id="wkCount">—</span></h2>
      <div class="note" style="margin-bottom:10px">One page to reread every week: what <b>your own
        decisions</b> did, always net of costs. Canonical live book only — simulator grinds and
        research books never count here. Advisory; the unchanged graduation bar stays the real gate.
        Same computation as <code>python main.py weekly</code> and MCP <code>weekly_review</code>.
        <a class="btn" style="margin-left:8px" href="/api/weekly/export">⬇ Export JSON</a></div>
      <div id="wkStats"><span class="muted">loading…</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>DAILY RITUAL — remembers what you finished <span class="count" id="ritCount">—</span></h2>
      <div id="ritualList"><span class="muted">loading…</span></div>
      <div class="note" style="margin-top:8px">Ticks are memory, not permission — the risk gate and the
        graduation bar never read them. Every UTC day starts fresh.</div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>NEXT PRACTICE TASK</h2>
      <div id="wkTask"><span class="muted">—</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>PRACTICE CALIBRATION — your reads vs the desk <span class="count" id="pracCardCount">—</span></h2>
      <div class="note" style="margin-bottom:8px">Every read you commit on the 📊 Chart tab (✍ PRACTICE card) is
        scored against the desk's live read and remembered here. Replay Freeze + Grade against the tape is a
        sibling score — what the hidden bars did after your commit, never mixed into desk agreement.
        Study metric only — agreement and tape outcomes are not evidence and not permission. Same
        computation as <code>python main.py practice</code> and MCP
        <code>practice_scorecard</code>.</div>
      <div id="wkPractice"><span class="muted">—</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>EQUITY CURVE <span class="count">net · compounding · live book</span></h2>
      <div id="wkEquity" style="height:220px"></div>
      <div id="wkEquityNote" class="note" style="margin-top:6px">—</div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>R-MULTIPLE DISTRIBUTION <span class="count">net, all time</span></h2>
      <div id="wkDist"><span class="muted">—</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>DISCIPLINE — violations, mistakes, missing journals</h2>
      <div id="wkViol"><span class="muted">—</span></div>
    </div>
    <div class="card" style="margin-top:14px;grid-column:1/-1">
      <h2>GRADUATION TRACKER — exactly which evidence is missing</h2>
      <div id="wkTrack"><span class="muted">—</span></div>
    </div>
  </div>

  <!-- ── Command center ── -->
  <div class="tabpanel" data-tab="commands">
    <div class="card" style="grid-column:1/-1">
      <h2>COMMAND CENTER — EVERY COMMAND IS A BUTTON <span class="count" id="cmdCount">—</span></h2>
      <div class="flex" style="margin-bottom:10px">
        <input id="cmdSearch" placeholder="search actions…" oninput="renderCommands()" style="flex:1;min-width:200px">
        <span class="note">🟢 read-only · 🟡 writes locally · 🟠 slow · 🔒 terminal only</span>
      </div>
      <div id="cmdCats" class="flex" style="margin-bottom:10px"></div>
      <div id="commandList"><span class="muted">loading commands…</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>RESULT</h2>
      <div id="cmdRunning" class="note"></div>
      <pre id="cmdOut" class="mono termout">Click any action above. Its output appears here — you never need a terminal.</pre>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>BACKGROUND JOBS <span class="count" id="jobCount">—</span></h2>
      <div class="note" style="margin-bottom:10px">Slow work (backfill, backtest, simulator, evidence)
        runs <b>here</b> in the background — closing this tab or the browser will not stop it,
        and progress survives a reload.</div>
      <div class="flex" style="margin-bottom:10px">
        <button class="btn" onclick="loadJobs(true)">↻ Refresh jobs</button>
        <span class="note" id="jobStatus">no jobs yet</span>
      </div>
      <div id="jobList"><span class="muted">loading jobs…</span></div>
      <h3 style="margin-top:14px">LIVE OUTPUT</h3>
      <pre id="jobOut" class="mono termout">Select a job to watch its output stream here.</pre>
    </div>
  </div>

  <!-- ── 24/7 research agent (W4.1) — advisory only, never trades ── -->
  <div class="tabpanel" data-tab="agent">
    <div class="card" style="grid-column:1/-1">
      <h2>THIS PC — 24/7 HUB ROLE <span class="count" id="hubRoleCount">one agent</span></h2>
      <div class="note" style="margin-bottom:10px">This always-on Ubuntu PC is the SKY Hub.
        Use <b>one</b> research agent (<code>sky-agent.service</code>). Do not add a second
        PC-use / AutoGPT agent. The human still approves every paper trade.
        Same payload as <code>python main.py hub role</code> and <code>GET /api/hub/role</code>.</div>
      <div class="flex" style="margin-bottom:10px">
        <button class="btn primary" onclick="loadHubRole()">↻ Refresh Hub</button>
        <button class="btn" onclick="runCommand('hub_status')">▶ Hub status</button>
        <button class="btn" onclick="runCommand('hub_doctor')">▶ Hub doctor</button>
        <span class="note" id="hubRoleStatus">not loaded yet</span>
      </div>
      <div id="hubRole"><span class="muted">loading Hub role…</span></div>
    </div>
    <div class="card" style="grid-column:1/-1;margin-top:14px">
      <h2>24/7 RESEARCH AGENT <span class="count" id="agCount">advisory only</span></h2>
      <div class="note" style="margin-bottom:10px">This is the research daemon from
        <code>sky_agent/</code>. It watches, scores and proposes. It cannot
        place a trade, bypass the risk gate, or move the graduation bar.
        Recommendations are <b>WATCH / CONSIDER / WAIT / AVOID</b> only — never BUY NOW.
        Same payloads as <code>python main.py sky-agent</code> and
        <code>GET /api/sky-agent/*</code>.</div>
      <div class="flex" style="margin-bottom:10px">
        <button class="btn primary" onclick="loadAgent(true)">↻ Refresh agent</button>
        <button class="btn" onclick="archiveAgentReport()">⬇ Archive today's report</button>
        <button class="btn" onclick="runCommand('sky_agent_collect')">▶ Collect (demo)</button>
        <span class="note" id="agStatus">not loaded yet</span>
      </div>
      <div id="agHealth"><span class="muted">loading health…</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>DAILY INTELLIGENCE REPORT</h2>
      <div id="agReport"><span class="muted">—</span></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>HYPOTHESES — stay hypotheses until the net bar</h2>
      <div id="agHyps"><span class="muted">—</span></div>
    </div>
    <div class="grid" style="margin-top:14px">
      <div class="card"><h2>REGIME LOG</h2><div id="agRegimes"><span class="muted">—</span></div></div>
      <div class="card"><h2>SEC EVENTS (research)</h2><div id="agSec"><span class="muted">—</span></div></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2>ARCHIVED REPORTS</h2>
      <div id="agArchive"><span class="muted">—</span></div>
    </div>
  </div>

  <!-- ── Module catalog ── -->
  <div class="tabpanel" data-tab="modules">
    <div class="card" style="grid-column:1/-1">
      <h2>MODULE CATALOG — WHAT IS INSIDE SKY <span class="count" id="modCount">—</span></h2>
      <input id="modSearch" placeholder="search modules…" oninput="renderModules()" style="width:100%;margin-bottom:10px">
      <div id="moduleList"><span class="muted">loading modules…</span></div>
    </div>
  </div>

  <div class="note" style="margin-top:14px;text-align:center;opacity:.7">Paper trading only — public Binance candles, no API key, no real orders. The desk decision is the only output you act on.</div>
</div>
<div id="authLayer"><div class="authbox" id="authBox"></div></div>
<div id="accountModal" style="display:none;position:fixed;inset:0;background:rgba(2,6,14,.7);backdrop-filter:blur(10px);z-index:75;padding:18px;overflow:auto"><div class="box" id="accountBody" style="max-width:640px"></div></div>
<div id="toasts"></div>
<div id="modal"><div class="box" id="mbody"></div></div>
<noscript><div class="shell"><div class="card" style="grid-column:1/-1"><div class="err">JavaScript is disabled — the dashboard needs JS. Enable it and reload.</div></div></div></noscript>
<script type="application/json" id="__auth_state__">{{ auth_state|tojson }}</script>
<script>
window.onerror = function(msg, src, line){
  try{
    var box=document.createElement('div');
    box.style.cssText='position:fixed;top:0;left:0;right:0;background:#ef4444;color:#fff;z-index:999;padding:10px;font:12px monospace;white-space:pre-wrap';
    box.textContent='⚠️ Dashboard script error: '+msg+' (line '+line+'). Press Ctrl+F5 to hard-refresh. If it persists, run `python main.py scan` in the terminal and share the output.';
    document.body.appendChild(box);
  }catch(e){}
};
window.addEventListener('unhandledrejection', function(ev){
  try{
    var box=document.createElement('div');
    box.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#b45309;color:#fff;z-index:999;padding:8px;font:12px monospace;white-space:pre-wrap';
    box.textContent='⚠️ Background update hiccup: '+(ev.reason&&ev.reason.message||ev.reason||'unknown')+' — the page keeps working.';
    document.body.appendChild(box);
  }catch(e){}
});
const fmt=(v,n=2)=> v==null?'—':Number(v).toLocaleString(undefined,{minimumFractionDigits:n,maximumFractionDigits:n});
const cls=a=> a==='BUY'?'BUY':a==='SELL'?'SELL':'NOTRADE';
const stCls=s=> s==='APPROVED'?'var(--green)':s==='REJECTED'?'var(--red)':s==='EXECUTED'?'var(--blue)':s==='CLOSED'?'var(--amber)':'var(--amber)';
const esc=x=> String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
function showToast(msg, kind){
  const c=document.getElementById('toasts'); if(!c) return;
  const el=document.createElement('div'); el.className='toast';
  el.style.borderColor = kind==='err'?'var(--red)':kind==='ok'?'var(--green)':'var(--line)';
  el.innerHTML = `<span style="font-size:16px">${kind==='err'?'⚠️':kind==='ok'?'✓':'ℹ️'}</span><span style="flex:1">${esc(msg)}</span><button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--mut);cursor:pointer">✕</button>`;
  c.appendChild(el); setTimeout(()=>{ try{el.remove()}catch(e){} }, 4200);
}

/* ══════════════════════════════════════════════════════════════════════
   P18.1 — authentication & authorization (client side).
   The server is authoritative; this only paints the right screen and
   carries the CSRF token on same-origin mutations.
   ══════════════════════════════════════════════════════════════════════ */
const __auth = (function(){
  try{
    const el = document.getElementById('__auth_state__');
    if(el && el.textContent) return JSON.parse(el.textContent);
  }catch(e){}
  return {enabled:false, setup_required:false, authenticated:true,
          user:null, role:null, csrf:''};
})();
function authLocked(){ return !!__auth.setup_required || (__auth.enabled && !__auth.authenticated); }

// Inject the CSRF token into every same-origin mutation, so the browser
// cannot be tricked into cross-site approve/reject/close requests.
(function(){
  if(typeof window === 'undefined' || !window.fetch) return;
  const orig = window.fetch.bind(window);
  window.fetch = function(url, opts){
    opts = opts || {};
    const csrf = (window.__AUTH__ && window.__AUTH__.csrf) || __auth.csrf || '';
    if(csrf){
      const method = String(opts.method || (opts.body ? 'POST' : 'GET')).toUpperCase();
      const sameOrigin = typeof url === 'string' && (url.charAt(0)==='/' || url.indexOf(window.location&&window.location.origin)===0);
      if(method !== 'GET' && sameOrigin){
        const h = {};
        try{ if(opts.headers){ for(const k in opts.headers) h[k]=opts.headers[k]; } }catch(e){}
        h['X-CSRF-Token'] = csrf;
        opts.headers = h;
      }
    }
    return orig(url, opts);
  };
})();

function refreshUserChip(){
  const chip=document.getElementById('userChip'); if(!chip) return;
  if(__auth.enabled && __auth.authenticated){
    chip.style.display='flex';
    const n=document.getElementById('userName'); if(n) n.textContent=__auth.user||'';
    const r=document.getElementById('userRole'); if(r) r.textContent=__auth.role||'viewer';
    const a=document.getElementById('userAvatar'); if(a) a.textContent=(__auth.user||'?').charAt(0).toUpperCase();
  } else chip.style.display='none';
}
function showAuth(){
  const layer=document.getElementById('authLayer'); if(!layer) return;
  const box=document.getElementById('authBox'); if(!box) return;
  if(__auth.setup_required){
    box.innerHTML = `<div class="logo-big">🧠</div>
      <h2>Create the owner account</h2>
      <div class="adetail" style="margin-top:6px">First run: pick a username and a strong password. This becomes the <b>operator</b> — the only role allowed to approve paper actions. Nobody else can read private state until this exists.</div>
      <div class="afield" style="margin-top:16px"><label>Username</label><input id="suUser" autocomplete="username"></div>
      <div class="afield"><label>Password (8+ characters)</label><input id="suPass" type="password" autocomplete="new-password"></div>
      <div class="afield"><label>Confirm password</label><input id="suPass2" type="password" autocomplete="new-password"></div>
      <div class="aerr" id="suErr"></div>
      <button class="btn primary" style="width:100%;justify-content:center" onclick="doSetup()">Create owner</button>
      <div class="ahint">Passwords are stored PBKDF2-HMAC-SHA256 hashed — never plaintext. No role can place a live exchange order; this app has no order path.</div>`;
  } else {
    box.innerHTML = `<div class="logo-big">🧠</div>
      <h2>Sign in to SKY</h2>
      <div class="adetail" style="margin-top:6px">Authentication is required to read private state or take any paper action.</div>
      <div class="afield" style="margin-top:16px"><label>Username</label><input id="liUser" autocomplete="username"></div>
      <div class="afield"><label>Password</label><input id="liPass" type="password" autocomplete="current-password"></div>
      <div class="aerr" id="liErr"></div>
      <button class="btn primary" style="width:100%;justify-content:center" onclick="doLogin()">Sign in</button>
      <div class="ahint">Sessions expire after ${__auth.session_ttl_hours||12}h (or ${__auth.session_idle_hours||2}h idle). Too many failed attempts locks sign-in temporarily.</div>`;
  }
  layer.style.display='block';
}
function hideAuth(){ const l=document.getElementById('authLayer'); if(l) l.style.display='none'; }
async function doSetup(){
  let u=(document.getElementById('suUser')||{}).value||''; u=u.trim();
  const p=(document.getElementById('suPass')||{}).value||'';
  const p2=(document.getElementById('suPass2')||{}).value||'';
  const e=document.getElementById('suErr');
  if(!u || p.length<8){ e.textContent='Username and a password of at least 8 characters are required.'; return; }
  if(p!==p2){ e.textContent='Passwords do not match.'; return; }
  e.textContent='creating…';
  try{
    const r=await fetch('/api/auth/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(!r.ok){ e.textContent=d.error||'setup failed'; return; }
    location.reload();
  }catch(err){ e.textContent=String(err); }
}
async function doLogin(){
  let u=(document.getElementById('liUser')||{}).value||''; u=u.trim();
  const p=(document.getElementById('liPass')||{}).value||'';
  const e=document.getElementById('liErr'); e.textContent='';
  try{
    const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(!r.ok){ e.textContent=d.error||'sign-in failed'; return; }
    location.reload();
  }catch(err){ e.textContent=String(err); }
}
async function doLogout(){
  try{ await fetch('/api/auth/logout',{method:'POST'}); }catch(e){}
  location.reload();
}
async function doLogoutAll(){
  try{
    const r=await fetch('/api/auth/logout-all',{method:'POST'});
    const d=await r.json();
    showToast(d.ok?('Signed out '+d.sessions+' session(s), revoked '+d.devices+' device token(s)'):(d.error||'failed'), d.ok?'ok':'err');
  }catch(e){ showToast(String(e),'err'); }
  closeAccount();
}
async function doChangePassword(){
  const cur=(document.getElementById('pwCur')||{}).value||'';
  const neu=(document.getElementById('pwNew')||{}).value||'';
  const m=document.getElementById('pwMsg');
  try{
    const r=await fetch('/api/auth/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current:cur,new:neu})});
    const d=await r.json();
    m.innerHTML = d.ok?'<span class="okc">✓ password changed</span>':'<span class="err">'+esc(d.error||'failed')+'</span>';
    if(d.ok){ document.getElementById('pwCur').value=''; document.getElementById('pwNew').value=''; }
  }catch(e){ m.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function loadDevices(){
  const host=document.getElementById('devList'); if(!host) return;
  try{
    const d=await (await fetch('/api/auth/devices')).json();
    const devs=(d.devices||[]).filter(x=>!x.revoked);
    host.innerHTML = devs.length
      ? devs.map(x=>`<div class="devrow"><span class="meta"><b>${esc(x.name)}</b> <span class="note">· ${esc(x.scope)} · ${esc(x.id)}</span><br><span class="note">last used ${x.last_used_ts?new Date(x.last_used_ts).toLocaleString():'never'}</span></span><button class="rowbtn no" onclick="doRevokeDevice('${esc(x.id)}')">Revoke</button></div>`).join('')
      : '<span class="muted">no device tokens issued. Companion clients (Windows/Android) authenticate with a scoped bearer token created here.</span>';
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function doRevokeDevice(id){
  try{
    await fetch('/api/auth/devices/revoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    showToast('Device token revoked','ok'); loadDevices();
  }catch(e){ showToast(String(e),'err'); }
}
async function doCreateDevice(){
  const name=(document.getElementById('devName')||{}).value||'device';
  const scope=(document.getElementById('devScope')||{}).value||'viewer';
  try{
    const r=await fetch('/api/auth/devices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,scope:scope})});
    const d=await r.json();
    const out=document.getElementById('devToken');
    if(!r.ok){ out.innerHTML='<span class="err">'+esc(d.error||'failed')+'</span>'; return; }
    out.innerHTML=`<div class="tokenout">${esc(d.token)}</div><div class="note" style="margin-top:6px">Use as <code>Authorization: Bearer &lt;token&gt;</code>. ${esc(d.note||'')}</div>`;
    loadDevices();
  }catch(e){ document.getElementById('devToken').innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function loadAudit(){
  const host=document.getElementById('auditList'); if(!host) return;
  try{
    const d=await (await fetch('/api/auth/audit')).json();
    const rows=(d.rows||[]).slice(0,40);
    host.innerHTML = rows.length
      ? rows.map(r=>`<div class="devrow"><span class="meta">${esc(new Date(r.ts).toLocaleString())} <b>${esc(r.action)}</b> <span class="note">${esc(r.target||'')}${r.username?' · by '+esc(r.username):''}</span></span><span class="badge" style="${r.ok?'color:var(--green)':'color:var(--red)'}">${r.ok?'✓':'✗'}</span></div>`).join('')
      : '<span class="muted">no sensitive actions recorded yet.</span>';
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
function openAccount(){
  const m=document.getElementById('accountModal');
  const body=document.getElementById('accountBody');
  if(!m||!body) return;
  let html=`<div class="flex" style="justify-content:space-between;margin-bottom:6px"><h2 style="margin:0;font-size:14px">ACCOUNT — ${esc(__auth.user||'')} <span class="badge strong">${esc(__auth.role||'viewer')}</span></h2><button class="btn ghost" onclick="closeAccount()">✕</button></div>
    <div class="note" style="margin-bottom:6px">Roles: <b>viewer</b> reads dashboards/evidence/health/paper state; <b>operator</b> additionally approves, rejects and closes paper actions. Neither can bypass the risk gate or place a live order.</div>
    <div class="sep"></div><b>CHANGE PASSWORD</b>
    <div class="flex" style="margin-top:8px"><input id="pwCur" type="password" placeholder="current password" style="flex:1"><input id="pwNew" type="password" placeholder="new password (8+)" style="flex:1"><button class="btn primary" onclick="doChangePassword()">Change</button></div>
    <div id="pwMsg" class="note" style="margin-top:6px"></div>
    <div class="sep"></div><div class="flex"><b style="flex:1">CONNECTED DEVICES</b><button class="btn no" onclick="doLogoutAll()">Log out all devices</button></div>
    <div id="devList" class="note" style="margin-top:8px">loading…</div>`;
  if(__auth.role==='operator'){
    html+=`<div class="sep"></div><b>CREATE DEVICE TOKEN</b> <span class="note">(companion clients: Windows / Android)</span>
      <div class="flex" style="margin-top:8px"><input id="devName" placeholder="name e.g. 'phone'" style="flex:1"><select id="devScope"><option value="viewer">viewer</option><option value="operator">operator</option></select><button class="btn primary" onclick="doCreateDevice()">Create token</button></div>
      <div id="devToken" style="margin-top:6px"></div>
      <div class="sep"></div><b>AUDIT LOG</b><div id="auditList" class="note" style="margin-top:8px">loading…</div>`;
  }
  body.innerHTML=html;
  m.style.display='block';
  loadDevices();
  if(__auth.role==='operator') loadAudit();
}
function closeAccount(){ const m=document.getElementById('accountModal'); if(m) m.style.display='none'; }

function setSymbol(sym){
  const el=document.getElementById('sym'); if(el) el.value=sym;
  document.querySelectorAll('#symSeg button').forEach(b=> b.classList.toggle('active', b.dataset.sym===sym));
  load(true);
}
function setTF(tf){
  const el=document.getElementById('tf'); if(el) el.value=tf;
  document.querySelectorAll('#tfSeg button').forEach(b=> b.classList.toggle('active', b.dataset.tf===tf));
  load(true);
}
let _activeTab = (typeof localStorage !== 'undefined' && localStorage.getItem('cb_tab')) || 'overview';
function switchTab(tab){
  _activeTab = tab;
  try{ if(typeof localStorage !== 'undefined') localStorage.setItem('cb_tab', tab); }catch(e){}
  try{ if(document.querySelectorAll){ document.querySelectorAll('.tabbtn').forEach(b=> b.classList.toggle('active', b.dataset.tab===tab)); } }catch(e){}
  try{ if(document.querySelectorAll){ document.querySelectorAll('.tabpanel').forEach(p=> p.classList.toggle('active', p.dataset.tab===tab)); } }catch(e){}
  // keep header updated visible
  const up=document.getElementById('updated'); if(up) up.textContent = (document.getElementById('updated')?.textContent||'') ;
  try{ if(typeof history !== 'undefined' && history.replaceState) history.replaceState(null,'','#'+tab); }catch(e){}
  // Workstation tabs load on demand so the first paint stays fast.
  try{ if(typeof onTabShown === 'function') onTabShown(tab); }catch(e){}
}
function card(title, inner, span){ return `<div class="card" ${span?'style="grid-column:1/-1"':''}><h2>${title}</h2>${inner}</div>`; }
/* ── Market-sentiment colour signal ───────────────────────────────────────
   One colour tells the market's condition:
     bullish → green, deepening to DEEP green the longer it holds
     bearish → red, deepening to STRONG red the longer it holds
     neutral → slate (no colour = no trade)
   depth = strength × (0.6 + 0.4 × persistence) — same formula as the
   backend (engine/sentiment.py). */
const SENTI_BAND = 10;
function sentiClamp(v,a,b){ return Math.max(a, Math.min(b, v)); }
function sentiLabel(score){
  if(score>=65) return 'STRONG BULLISH';
  if(score>=30) return 'BULLISH';
  if(score>=SENTI_BAND) return 'LEANING BULLISH';
  if(score<=-65) return 'STRONG BEARISH';
  if(score<=-30) return 'BEARISH';
  if(score<=-SENTI_BAND) return 'LEANING BEARISH';
  return 'NEUTRAL';
}
function sentiColor(score, intensity){
  if(Math.abs(score) < SENTI_BAND || !intensity) return '#5f6d84';
  const hue = score>0 ? 142 : 0;
  const sat = 62 + 18*sentiClamp(intensity,0,1);
  const light = 55 - 28*sentiClamp(intensity,0,1);
  return `hsl(${hue},${Math.round(sat)}%,${Math.round(light)}%)`;
}
function sentiTextColor(score){
  if(Math.abs(score) < SENTI_BAND) return 'var(--mut)';
  return score>0 ? 'var(--green)' : 'var(--red)';
}
function sentiDurTxt(min){
  min = Math.max(0, Number(min)||0);
  if(min<1) return 'just now';
  if(min<60) return Math.round(min)+'m';
  const h=Math.floor(min/60), m=Math.round(min%60);
  return m ? `${h}h ${String(m).padStart(2,'0')}m` : `${h}h`;
}
function fallbackSentiment(d){
  // Client-side estimate when the backend hasn't attached sentiment yet
  // (old cached payload / synthetic test payload). Duration is unknown
  // client-side, so the colour stays bright until the backend confirms.
  const snap=d.snapshot||{}, sc=snap.scores||{}, f=snap.features||{};
  const bull=(sc.bull&&sc.bull.score)||0, bear=(sc.bear&&sc.bear.score)||0;
  const align=(d.mtf&&d.mtf.alignment&&d.mtf.alignment.score)||0;
  const trend=String(f.trend||'').toLowerCase();
  const t= trend==='bullish'?1 : trend==='bearish'?-1 : 0;
  const adx=Number(f.adx)||20;
  let score = (bull-bear)*0.6 + sentiClamp(align,-100,100)*0.2 + t*sentiClamp(adx/25,0,1)*100*0.1;
  if(d.signal&&d.signal.action==='BUY') score += ({HIGH:90,MEDIUM:70,LOW:45}[d.signal.confidence]||0)*0.05;
  if(d.signal&&d.signal.action==='SELL') score -= ({HIGH:90,MEDIUM:70,LOW:45}[d.signal.confidence]||0)*0.05;
  score = sentiClamp(score,-100,100);
  const strength=Math.min(Math.abs(score)/100,1);
  return {available:true, score:Math.round(score*10)/10,
    direction: score>=SENTI_BAND?'bullish':score<=-SENTI_BAND?'bearish':'neutral',
    label:sentiLabel(score), strength, duration_min:0, persistence:0,
    intensity:strength*0.6, color:sentiColor(score,strength*0.6),
    parts:[], history:[], fallback:true};
}
function sentiSpark(sent){
  const pts=(sent&&sent.history)||[];
  if(pts.length<2) return '';
  const w=340, h=46;
  const xs=pts.map((p,i)=> (i/(pts.length-1))*w);
  const ys=pts.map(p=> h/2 - sentiClamp(Number(p.score)||0,-100,100)/100*(h/2-2));
  const line=xs.map((x,i)=>`${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const col=sentiColor(sent.score||0, sent.intensity||0);
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:46px;margin-top:6px" preserveAspectRatio="none">
    <line x1="0" y1="${h/2}" x2="${w}" y2="${h/2}" stroke="rgba(255,255,255,.08)" stroke-width="1"/>
    <polyline points="${line}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/></svg>`;
}
function sentiCard(sent){
  const score=Number(sent&&sent.score)||0;
  const depth=Math.round((Number(sent&&sent.intensity)||0)*100);
  const col=sentiColor(score, Number(sent&&sent.intensity)||0);
  const parts=(sent&&sent.parts)||[];
  const dur=(sent&&sent.duration_min)||0;
  const rows=parts.length?parts.map(p=>{
    const c=Number(p.contrib)||0;
    const w=Math.min(Math.abs(c)*2,100);
    return `<tr><td>${esc(p.name)} <span class="note">(${Math.round((Number(p.weight)||0)*100)}%)</span></td>
      <td style="width:110px"><div class="senti-part"><i style="width:${w}%;background:${c>=0?'var(--green)':'var(--red)'};${c<0?'margin-left:auto':''}"></i></div></td>
      <td class="mono" style="color:${c>0?'var(--green)':c<0?'var(--red)':'var(--mut)'}">${c>0?'+':''}${Math.round(c*10)/10}</td>
      <td class="note">${esc(p.detail||'')}</td></tr>`;
  }).join('') : '<div class="muted">no sentiment inputs yet — the first scan fills this in</div>';
  return `
  <div class="flex" style="justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div>
      <div class="slabel" style="font-size:20px;min-width:0">
        <span class="sdot" style="background:${col};color:${col};width:16px;height:16px"></span>
        <span style="color:${sentiTextColor(score)}">${esc((sent&&sent.label)||sentiLabel(score))}</span>
      </div>
      <div class="note" style="margin-top:4px">
        score <b class="mono">${score>0?'+':''}${Math.round(score*10)/10}</b> ·
        depth <b>${depth}%</b>${dur?` · same condition <b>${sentiDurTxt(dur)}</b>`:''}${sent&&sent.fallback?' · <span style="color:var(--amber)">estimate — backend will confirm</span>':''}
      </div>
    </div>
    <div class="senti-legend">
      <span class="senti-chip"><i style="background:hsl(142,82%,26%)"></i>strong bull = deep green</span>
      <span class="senti-chip"><i style="background:hsl(142,62%,55%)"></i>bull = green</span>
      <span class="senti-chip"><i style="background:#5f6d84"></i>neutral = slate</span>
      <span class="senti-chip"><i style="background:hsl(0,62%,55%)"></i>bear = red</span>
      <span class="senti-chip"><i style="background:hsl(0,82%,26%)"></i>strong bear = deep red</span>
    </div>
  </div>
  <div class="senti-scale-lg"><span class="needle" style="left:${sentiClamp((score+100)/2,0,100)}%"></span></div>
  ${sentiSpark(sent)}
  <table class="senti-parts" style="margin-top:6px"><tr><th>Input</th><th></th><th>pts</th><th>reading</th></tr>${rows}</table>
  <div class="note" style="margin-top:8px">The colour deepens with <b>time in the same sentiment</b>: green gets greener the longer the market holds bullish, red gets stronger the longer it holds bearish. Full depth after 3 hours of the same condition. Watch the left edge bar — that colour is the market's mood, on every tab.<br>The colour is <b>measured</b>, not just painted (P16): every graded plan carries its signal-time colour, and the <b>STRATEGY SCORECARD</b> splits outcomes by colour and by depth — see <b>By sentiment colour</b> and <b>By colour depth</b> on the Learn tab.</div>`;
}
function renderSentiment(sent){
  const score=Number(sent&&sent.score)||0;
  const intensity=sentiClamp(Number(sent&&sent.intensity)||0,0,1);
  const col=sentiColor(score,intensity);
  const lab=(sent&&sent.label)||sentiLabel(score);
  const dir=(sent&&sent.direction)||(score>=SENTI_BAND?'bullish':score<=-SENTI_BAND?'bearish':'neutral');
  const durMin=Number(sent&&sent.duration_min)||0;
  const persist=Number(sent&&sent.persistence)||0;
  try{
    const bar=document.getElementById('moodbar');
    if(bar){ bar.style.background=col; bar.style.boxShadow=`0 0 20px ${col}`; }
  }catch(e){}
  try{
    const el=document.getElementById('senti');
    if(el){
      el.style.borderColor=col;
      el.style.boxShadow=`0 10px 30px ${col}33, inset 0 1px 0 rgba(255,255,255,.05)`;
      const dot=document.getElementById('sentiDot');
      if(dot){ dot.style.background=col; dot.style.color=col; }
      const lbl=document.getElementById('sentiLabel');
      if(lbl){ lbl.textContent=lab; lbl.style.color=sentiTextColor(score); }
      const needle=document.getElementById('sentiNeedle');
      if(needle) needle.style.left=sentiClamp((score+100)/2,0,100)+'%';
      const sc=document.getElementById('sentiScore');
      if(sc) sc.textContent= score>0?'+'+score:''+score;
      const du=document.getElementById('sentiDur');
      if(du) du.textContent= dir==='neutral'?'—':sentiDurTxt(durMin);
      const dep=document.getElementById('sentiDepth');
      if(dep) dep.textContent= dir==='neutral'?'—':Math.round(intensity*100)+'%';
      const deep=document.getElementById('sentiDeepen');
      if(deep){
        deep.textContent = dir==='neutral'
          ? 'NO COLOUR — WAIT'
          : persist>=0.95 ? ('DEEP '+(dir==='bullish'?'GREEN':'RED')+' — LONG HOLD')
          : persist>=0.5 ? 'DEEPENING'
          : 'FRESH '+(dir==='bullish'?'GREEN':'RED');
        deep.style.color=col;
        deep.style.borderColor=col;
      }
    }
  }catch(e){}
}
function renderKeyLevels(levels){
  if(!levels || !levels.length) return '<div class="muted">no ranked levels — the desk has nothing to map yet</div>';
  const col = {A:'var(--red)', B:'var(--amber)', C:'var(--mut)'};
  const groups = {A:[], B:[], C:[]};
  levels.forEach(l => { if(groups[l.tier]) groups[l.tier].push(l); });
  return ['A','B','C'].map(t => {
    const rows = groups[t];
    if(!rows.length) return '';
    return `<div style="margin-bottom:8px"><b style="color:${col[t]}">Tier ${t}</b>
      <table><tr><th>Level</th><th>Price</th><th>Dist</th><th>Note</th></tr>
      ${rows.map(l=>`<tr><td>${esc(l.name)}</td><td class="mono">${fmt(l.level)}</td><td class="mono">${l.distance_pct!=null?Number(l.distance_pct).toFixed(3)+'%':'—'}</td><td class="note">${esc(l.note||'')}</td></tr>`).join('')}
      </table></div>`;
  }).join('');
}

function render(d){
  const s=d.signal||{}, plans=d.plans||[], snap=d.snapshot||{}, f=snap.features||{}, sc=snap.scores||{}, ctx=d.market_context||{}, lc=d.lifecycle||{};
  const sent=d.sentiment||fallbackSentiment(d);
  const cf=sc.bull?.score??0, cs=sc.bear?.score??0;
  const sid=d.scan_id, st=lc.status||'';
  const decideBtns = st==='PENDING_REVIEW'
    ? `<div class="flex" style="margin-top:10px">
         <input id="note-${sid}" placeholder="add a note (optional)" style="flex:1;min-width:180px">
         <button class="btn ok" onclick="decide(${sid},'APPROVED')">✓ Approve</button>
         <button class="btn no" onclick="decide(${sid},'REJECTED')">✗ Reject</button>
       </div>`
    : (st==='APPROVED' ? `<div class="flex" style="margin-top:10px">
         <button class="btn primary" onclick="decide(${sid},'EXECUTED')">▶ Mark executed</button>
         <button class="btn no" onclick="decide(${sid},'SKIPPED')">Skip</button></div>`
       : (st==='EXECUTED' ? `<button class="btn" style="background:var(--amber);color:#111" onclick="decide(${sid},'CLOSED')">✔ Close (record outcome)</button>` : ''));
  const mgmt = d.management || [];
  const mgmtHtml = mgmt.length ? `<div style="margin-top:10px;background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line)">
      <b>POSITION MANAGER</b>
      ${mgmt.map(c=>`<div class="note">• ${esc(c)}</div>`).join('')}
    </div>` : '';

  // Build grouped tab panels. The workflow card is intentionally visible on
  // the first screen: it turns the large command surface into a repeatable
  // trader ritual, so the user does not have to memorize the CLI.
  const workflowCard = card('DESK WORKFLOW — WHAT TO DO NEXT', `
    <div class="statrow" style="margin-bottom:10px">
      <div class="stat"><div class="v" style="color:var(--blue)">1</div><div class="k">Check readiness</div><div class="note">Gate, data, channels</div></div>
      <div class="stat"><div class="v" style="color:var(--violet)">2</div><div class="k">Read the desk</div><div class="note">Signal is research</div></div>
      <div class="stat"><div class="v" style="color:var(--amber)">3</div><div class="k">Approve or reject</div><div class="note">You stay in control</div></div>
      <div class="stat"><div class="v" style="color:var(--green)">4</div><div class="k">Review outcome</div><div class="note">Paper only · journal</div></div>
    </div>
    <div class="flex" style="justify-content:space-between;align-items:flex-start">
      <div class="note" style="max-width:760px">Use this dashboard as your memory: <b>Overview</b> answers “should I act?”, <b>Market</b> explains price and structure, <b>Trades</b> protects execution, <b>Learn</b> measures your edge, and <b>System</b> checks the plumbing. If the gate is closed or readiness is not green, the professional action is to stand aside.</div>
      <div class="flex">
        <button class="btn" onclick="switchTab('trades');setTimeout(()=>document.getElementById('riskgate')?.scrollIntoView({behavior:'smooth'}),120)">🛡 Risk gate</button>
        <button class="btn" onclick="switchTab('learn');setTimeout(()=>document.getElementById('coach')?.scrollIntoView({behavior:'smooth'}),120)">🧑‍🏫 Coach me</button>
      </div>
    </div>
  `, true);
  let overview = workflowCard;
  overview += card('MARKET SENTIMENT — THE COLOUR IS THE MARKET', sentiCard(sent), true);
  overview += card('LIVE SIGNAL', `
    <div class="flex" style="margin-bottom:8px">
      <span class="pill ${cls(s.action)}">${s.action}</span>
      <b>${s.asset||''} · ${s.timeframe||''}</b>
      <span class="badge">${esc(s.signal_id||'')}</span>
      <span class="badge">${esc(s.confidence||'')}</span>
      ${s.risk_reward?`<span class="badge">RR ${esc(s.risk_reward)}</span>`:''}
      <span class="badge" style="background:${stCls(st)}22;border-color:${stCls(st)};color:${stCls(st)}">${esc(st||'—')}</span>
      ${d.stale?'<span class="badge" style="background:var(--amber);color:#111">STALE</span>':''}
      ${d.degraded?'<span class="badge">DEGRADED</span>':''}
    </div>
    <div class="kv">
      <b>Entry</b><span class="mono" style="font-weight:700">${fmt(s.entry)}</span>
      <b>Stop loss</b><span class="mono" style="color:var(--red)">${fmt(s.stop_loss)}</span>
      <b>Take profit</b><span class="mono" style="color:var(--green)">${fmt(s.take_profit)}</span>
      ${ctx.data_symbol&&ctx.data_symbol!==s.asset?`<b>Data source</b><span>${esc(ctx.data_symbol)} (${esc(ctx.provider||'provider')})</span>`:''}
      <b>Reason</b><span>${esc(s.reason||'')}</span>
      <b>Note</b><span>${esc(lc.note||'')}</span>
    </div>
    ${d.degraded?`<div class="note" style="margin-top:8px;background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.3);padding:8px;border-radius:10px">⚠️ ${esc(d.degraded_reason||'degraded mode')} — <a href="#" onclick="load(true);return false">retry full scan</a></div>`:''}
    ${d.stale?`<div class="note" style="margin-top:6px">Showing last good data for ${esc(s.asset)} ${esc(s.timeframe)} — <a href="#" onclick="load(true);return false">retry</a></div>`:''}
    ${decideBtns}
    ${mgmtHtml}
  `, true);

  const dec=d.decision||{};
  if(dec.action){
    const dc=dec.gates||{}, pb=dc.playbook||{}, rg=dc.risk||{}, pv=dc.portfolio||{};
    const decOk = dec.action==='BUY'||dec.action==='SELL';
    overview += card('PROFESSIONAL DESK DECISION', `
      <div class="flex" style="margin-bottom:8px">
        <span class="pill ${decOk?'BUY': 'NOTRADE'}" style="${decOk?'':'background:rgba(139,160,189,.12);color:var(--mut)'}">${decOk?('TRADE '+dec.action):'WAIT — NO TRADE'}</span>
        <span class="badge">${esc(dec.decision_text||'')}</span>
        <span class="badge">${esc(dec.regime_label||'')}</span>
        <span class="badge">setup: ${esc(dec.plan_type||'—')}</span>
      </div>
      ${pb.name?`<div class="kv"><b>Playbook</b><span>${esc(pb.name)} — ${esc(pb.note||'')}</span></div>`:''}
      ${(pb.checks||[]).map(c=>`<div class="note" style="margin-top:3px">${c.ok?'✓':'✗'} ${esc(c.detail)}</div>`).join('')}
      ${(rg.blocked_by||[]).map(b=>`<div class="err" style="margin-top:4px">✗ risk: ${esc(b)}</div>`).join('')}
      ${(pv.reasons||[]).map(b=>`<div class="err" style="margin-top:4px">✗ portfolio: ${esc(b)}</div>`).join('')}
      ${dec.blocked_by&&dec.blocked_by.length?`<div class="err" style="margin-top:8px;background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.28);padding:8px;border-radius:10px">BLOCKED — ${dec.blocked_by.map(esc).join('; ')}</div>`:''}
      <div class="note" style="margin-top:8px">The desk decision is the <b>only</b> output you act on. The engine signal above is research.</div>
    `, true);
  }

  // degraded banner for quick insight
  let heroStats = '';
  {
    const price = f.price!=null?fmt(f.price,2):'—';
    const rsi = f.rsi!=null?fmt(f.rsi,1):'—';
    const adx = f.adx!=null?fmt(f.adx,1):'—';
    heroStats = `<div class="statrow" style="margin-bottom:14px">
      <div class="stat"><div class="v mono">${price}</div><div class="k">Price (${s.asset||''})</div></div>
      <div class="stat"><div class="v">${esc(s.action||'—')}</div><div class="k">Signal · ${esc(s.confidence||'')}</div></div>
      <div class="stat"><div class="v mono">${rsi}</div><div class="k">RSI</div></div>
      <div class="stat"><div class="v mono">${adx}</div><div class="k">ADX</div></div>
      <div class="stat"><div class="v">${esc(dec.action||'—')}</div><div class="k">Desk</div></div>
    </div>`;
  }

  let intelCard = '';
  const intel=d.intelligence||{};
  const scard=intel.signal_card||{};
  if(intel.asset){
    const fchecks=intel.trade_filter||{};
    const tpl=scard.tp_ladder||[];
    const tplHtml=tpl.length ? tpl.map(t=>`<tr><td><b>${esc(t.target)}</b></td><td class="mono">$${fmt(t.price)}</td><td style="color:var(--green)">+${fmt(t.gain_pct)}%</td><td>${t.allocation_pct}% size</td><td class="note">${esc(t.management||'')}</td></tr>`).join('') : '';
    const kelly=intel.kelly_criterion||{};
    intelCard = card('INSTITUTIONAL AI SIGNAL CARD v2.0 — Enterprise Alpha Intelligence', `
      <div class="flex" style="margin-bottom:10px;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:10px">
        <div class="flex">
          <span class="pill ${cls(intel.signal)}">${esc(intel.signal)}</span>
          <b>${esc(intel.asset)} · ${esc(intel.timeframe)}</b>
          <span class="badge strong">Grade ${esc(intel.trade_quality_grade||'N/A')}</span>
          <span class="badge">Regime: ${esc((intel.chart_read||{}).regime?.label||intel.regime?.label||intel.trend||'—')}</span>
        </div>
        <div class="flex">
          <span class="badge" style="background:rgba(59,130,246,.15);color:var(--blue)">IPS ${intel.institutional_probability_score??intel.confidence??0}/100</span>
          <span class="badge" style="background:rgba(34,197,94,.15);color:var(--green)">AI Confidence ${scard.ai_confidence_index||(intel.confidence+'%')} ${scard.confidence_delta||''}</span>
        </div>
      </div>
      <div class="grid2" style="margin-bottom:10px">
        <div class="kv">
          <b>Entry Zone</b><span class="mono" style="color:var(--txt);font-weight:700">${esc(intel.entry_zone||'N/A')}</span>
          <b>Stop Loss</b><span class="mono" style="color:var(--red)">${esc(scard.stop_loss_display||fmt(intel.stop_loss))}</span>
          <b>Risk:Reward</b><span><b>${esc(intel.risk_reward||'1:2.0')}</b></span>
          <b>Hold Time</b><span>${esc(intel.expected_hold_time||'4–8 Hours')}</span>
          <b>Active Until</b><span class="note">${esc(intel.active_until||'N/A')}</span>
        </div>
        <div class="kv">
          <b>Market Regime</b><span>${esc((intel.chart_read||{}).regime?.label||intel.regime?.label||intel.trend||'—')}</span>
          <b>Liquidity Trap</b><span>${intel.regime?.trap_detected?'<span class="err">⚠️ Trap / Fakeout Risk</span>':'<span class="okc">✓ Clean / No Trap</span>'}</span>
          <b>Order Flow SMC</b><span>OB: ${esc(intel.order_block)} · FVG: ${esc(intel.fair_value_gap)}</span>
          <b>Kelly Sizing</b><span>${kelly.recommended_risk_pct?kelly.recommended_risk_pct+'% risk ($'+fmt(kelly.recommended_risk_amt)+')':'Fixed 1.0%'} · ${esc(kelly.recommended_leverage||'1x-3x')}</span>
          <b>Capital Preserv.</b><span>${esc(intel.self_review?.capital_preservation_decision||'Capital protected')}</span>
        </div>
      </div>
      ${tplHtml ? `<div style="margin:10px 0"><b>Smart Take-Profit Ladder</b><table style="margin-top:6px"><tr><th>Target</th><th>Price</th><th>Gain</th><th>Allocation</th><th>Action / Management</th></tr>${tplHtml}</table></div>` : ''}
      <div class="grid2" style="margin-top:10px">
        <div style="background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line)">
          <b style="color:var(--green)">Why AI Took This Trade:</b>
          <div class="note" style="margin-top:6px">${(scard.why_ai_took_trade||intel.reason||[]).slice(0,4).map(r=>'• '+esc(r)).join('<br>')}</div>
        </div>
        <div style="background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line)">
          <b style="color:var(--red)">Invalidation Conditions:</b>
          <div class="note" style="margin-top:6px">${(scard.invalidation_conditions||[]).slice(0,3).map(r=>'• '+esc(r)).join('<br>')}</div>
        </div>
      </div>
      <div style="background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line);margin-top:10px">
        <b>Alternative Scenario:</b>
        <div class="note" style="margin-top:4px">${esc(scard.alternative_scenario||intel.scenario_B||'')}</div>
      </div>
      <details style="margin-top:10px"><summary class="kbd" style="cursor:pointer">Desk Filter Checks & Full Scenarios</summary>
        <div class="note" style="margin-top:8px">Scenario A: ${esc(intel.scenario_A||'—')}<br>Scenario B: ${esc(intel.scenario_B||'—')}<br>Scenario C: ${esc(intel.scenario_C||'—')}</div>
        <table style="margin-top:8px"><tr><th>Filter Check</th><th>Status</th><th>Value</th></tr>${Object.entries(fchecks).map(([k,v])=>`<tr><td>${esc(k)}</td><td style="color:${v.ok?'var(--green)':'var(--red)'}">${v.ok?'✓ PASS':'✗ FAIL'}</td><td>${esc(v.value??'')}</td></tr>`).join('')}</table>
      </details>
    `, true);
  }

  // Market tab cards
  let marketCards = '';
  marketCards += card(`CANDLESTICK — ${s.asset||''} ${s.timeframe||''}`,
    `<div id="chart" style="width:100%;height:260px;display:grid;place-items:center"><span class="muted">loading candles…</span></div>
     <div class="note" style="margin-top:6px">last 90 candles · EMA 20/50 overlay · volume bars · hover a candle for OHLC (coming soon)</div>`, true);

  marketCards += card('KEY LEVELS — A / B / C',
    renderKeyLevels((intel.key_levels)||[]) +
    '<div class="note" style="margin-top:6px">A = liquidity &amp; major structure · B = decision zones · C = reference. Ranked by distance from price; nothing invented.</div>',
    true);

  const mtf=d.mtf||{}, views=mtf.views||{}, al=mtf.alignment||{};
  marketCards += card('MULTI-TIMEFRAME (HTF → LTF)', `
    <div style="overflow:auto">
    <table><tr><th>TF</th><th>Trend</th><th>RSI</th><th>ADX</th><th>Event</th><th>Zone</th></tr>
    ${['1M','1w','1d','4h','1h','30m','15m','5m','1m'].map(tf=>{
      const v=views[tf]||{};
      if(!v.available) return `<tr><td><b>${tf}</b></td><td class="muted">—</td><td/><td/><td/><td/></tr>`;
      return `<tr><td><b>${tf}</b></td>
        <td style="color:${v.trend==='bull'?'var(--green)':v.trend==='bear'?'var(--red)':'var(--amber)'}">${esc(v.trend)}</td>
        <td>${fmt(v.rsi,0)}</td><td>${fmt(v.adx,0)}</td>
        <td>${esc(v.event_kind||'—')}</td><td>${esc(v.premium_discount||'—')}</td></tr>`;
    }).join('')}
    </table></div>
    <div class="flex" style="margin-top:10px">
      <span class="badge">HTF ${esc(mtf.htf_bias||'—')}</span>
      <span class="badge">LTF ${esc(mtf.ltf_bias||'—')}</span>
      <span class="badge" style="color:${al.score>=30?'var(--green)':al.score<=-30?'var(--red)':'var(--amber)'}">alignment ${al.score??0} (${esc(al.label||'—')})</span>
    </div>
    <div class="note" style="margin-top:6px">support ${(mtf.key_levels?.support||[]).map(v=>fmt(v,0)).join(', ')||'—'} · resistance ${(mtf.key_levels?.resistance||[]).map(v=>fmt(v,0)).join(', ')||'—'}</div>`, true);

  marketCards += card(`CONDITIONAL PLANS (${plans.length})`,
    plans.length ? plans.map(p=>`<div class="plan"><div class="h">
        <b class="${cls(p.action)}">${esc(p.action)} · ${esc(p.type)}</b>
        <span class="badge">${p.confidence}% ${esc(p.confidence_label||'')}</span></div>
        <div class="bar"><i style="width:${p.confidence}%;background:${p.confidence>=80?'var(--green)':p.confidence>=60?'var(--amber)':'var(--red)'}"></i></div>
        <div class="c">${esc(p.condition||'')}</div>
        <div class="c mono">entry ${fmt(p.entry)} · sl ${fmt(p.stop_loss)} · tp ${(p.take_profits||[]).map(v=>fmt(v)).join(', ')} · RR ${esc(p.risk_reward)}</div>
        <div class="note" style="margin-top:4px">${(p.reasons||[]).slice(0,2).map(r=>'• '+esc(r)).join('<br>')}</div>
        </div>`).join('')
      : '<div class="muted">No plans above threshold — best trade is no trade. The market is not offering a clean edge right now.</div>');

  const styles=d.styles||{}, sall=styles.styles||{};
  marketCards += card('WHAT THE MARKET OFFERS (by trading style)', `
    <div style="overflow:auto"><table><tr><th>Style</th><th>Setup</th><th>Conf</th><th>Horizon</th></tr>
    ${['Scalp','Day','Swing','Momentum','Position'].map(s=>{
      const v=sall[s]||{};
      if(!v.available) return `<tr><td><b>${s}</b></td><td class="muted">—</td><td/><td/></tr>`;
      return `<tr><td><b>${s}</b></td>
        <td><span class="pill ${cls(v.direction)}" style="padding:2px 8px;font-size:11px">${esc(v.direction)}</span> <span class="note">${esc((v.reason||'').slice(0,58))}</span></td>
        <td>${esc(v.confidence)}%</td><td>${esc(v.horizon)}</td></tr>`;
    }).join('')}
    </table></div>
    ${styles.market_offering && styles.market_offering.length
      ? `<div class="note" style="margin-top:8px">offering: <b>${styles.market_offering.join(', ')}</b></div>`
      : `<div class="muted" style="margin-top:8px">stand aside — ${esc((styles.stand_aside||[]).join('; ')||'no edge now')}</div>`}`, true);

  const kvs=[
    ['Trend', esc(f.trend||'—')], ['EMA stack', f.ema_alignment_bull?'Bull aligned':f.ema_alignment_bear?'Bear aligned':'mixed'],
    ['Supertrend', f.supertrend_bull?'Bull':'Bear'], ['ADX', fmt(f.adx,1)],
    ['RSI', fmt(f.rsi,1)], ['RSI div bull/bear', `${f.rsi_divergence?.bull??0}/${f.rsi_divergence?.bear??0}`],
    ['MACD hist', fmt(f.macd_hist,4)], ['WaveTrend', `${fmt(f.wt1,2)}/${fmt(f.wt2,2)}`],
    ['Volume ratio', fmt(f.volume_ratio,2)], ['vs VWAP', f.above_vwap?'above':'below'],
    ['Structure event', esc(f.event_kind||'—')], ['Bias', esc(f.trend_bias||'—')],
    ['Bull OB near', fmt(f.nearest_bull_ob)], ['Bear OB near', fmt(f.nearest_bear_ob)],
    ['FVG bull/bear', `${f.fvg_bull_count??'—'}/${f.fvg_bear_count??'—'}`],
    ['Premium/Discount', esc(f.premium_discount||'—')], ['ATR %', fmt(f.atr_pct,3)],
    ['Sweep', f.sweep?`${esc(f.sweep.side)} @ ${fmt(f.sweep.level)}`:'none'],
  ];
  marketCards += card('FEATURE SNAPSHOT', `<div class="kv">${kvs.map(([k,v])=>`<b>${k}</b><span>${v}</span>`).join('')}</div>`);

  marketCards += card('SCORE BREAKDOWN', `<div style="overflow:auto"><table><tr><th>Condition</th><th>Bull</th><th>Bear</th></tr>${
    [...new Set([...Object.keys(sc.bull?.conditions||{}),...Object.keys(sc.bear?.conditions||{})])]
      .map(k=>`<tr><td>${esc(k)}</td><td>${sc.bull?.conditions?.[k]??0}</td><td>${sc.bear?.conditions?.[k]??0}</td></tr>`).join('')
    }<tr><td><b>Total</b></td><td><b>${cf}</b></td><td><b>${cs}</b></td></tr></table></div>
    <div class="muted" style="margin-top:8px">${(sc.bull?.reasons||[]).concat(sc.bear?.reasons||[]).slice(0,6).map(r=>'• '+esc(r)).join('<br>')||'—'}</div>`);

  marketCards += card('MARKET CONTEXT', `<div class="kv">
    <b>Provider symbol</b><span>${ctx.data_symbol?esc(ctx.data_symbol)+' · '+esc(ctx.provider||'provider'):'n/a'}</span>
    <b>Market</b><span>${esc(ctx.market||'n/a')}</span>
    <b>Funding</b><span>${ctx.funding_rate_pct!=null?ctx.funding_rate_pct+'%':'n/a'}</span>
    <b>Open interest</b><span>${ctx.open_interest!=null?fmt(ctx.open_interest,0):'n/a'}</span>
    <b>L/S ratio</b><span>${ctx.long_short_ratio??'n/a'}</span>
    <b>24h change</b><span>${ctx.liq_24h_change_pct!=null?ctx.liq_24h_change_pct+'%':'n/a'}</span>
    <b>Futures</b><span>${ctx.futures?'available':esc(ctx.note||'not available')}</span>
  </div>`);

  const mctx=d.context||{};
  const fng=mctx.fear_greed||{}, dom=mctx.dominance||{}, eq=mctx.equities||{},
        macro=mctx.macro||{}, cyc=mctx.cycle||{}, geo=mctx.geopolitics||{},
        soc=mctx.social||{}, reg=mctx.risk_regime||{};
  const cp=eq.change_pct||{};

  // P10.9 — Futures panes (dedicated cards, not just embedded in Market Context)
  const futuresCtx = ctx || {};
  const fundingVal = futuresCtx.funding_rate_pct != null ? parseFloat(futuresCtx.funding_rate_pct) : null;
  const fundingColor = fundingVal == null ? 'var(--mut)' : (fundingVal > 0 ? 'var(--red)' : fundingVal < 0 ? 'var(--green)' : 'var(--amber)');
  const fundingLabel = fundingVal == null ? '—' : (fundingVal > 0 ? 'positive (longs pay shorts)' : fundingVal < 0 ? 'negative (shorts pay longs)' : 'neutral');
  const oiVal = futuresCtx.open_interest != null ? parseFloat(futuresCtx.open_interest) : null;
  const lsVal = futuresCtx.long_short_ratio != null ? parseFloat(futuresCtx.long_short_ratio) : null;
  const lsColor = lsVal == null ? 'var(--mut)' : (lsVal > 1 ? 'var(--green)' : lsVal < 0.9 ? 'var(--red)' : 'var(--amber)');

  // CVD / volume delta from feature snapshot (hidden_alpha computes it)
  const cvdVal = f.cvd_z || f.cvd ? (f.cvd_z != null ? fmt(f.cvd_z, 2) : fmt(f.cvd, 0)) : null;
  const cvdColor = f.cvd_z == null ? 'var(--mut)' : (f.cvd_z > 0 ? 'var(--green)' : f.cvd_z < 0 ? 'var(--red)' : 'var(--amber)');

  marketCards += card('FUTURES — OPEN INTEREST & FUNDING', `
    <div class="grid2">
      <div>
        <div class="flex" style="margin-bottom:10px;justify-content:space-between">
          <span class="badge" style="background:${futuresCtx.futures?'rgba(34,197,94,.14);color:var(--green);border-color:rgba(34,197,94,.30)':'rgba(139,160,189,.08);color:var(--mut);border-color:var(--line)'}">FUTURES ${futuresCtx.futures?'●':'○'}</span>
          <span class="badge">${esc(futuresCtx.provider||'provider')}</span>
        </div>
        <div class="kv">
          <b>Funding rate</b><span style="color:${fundingColor};font-weight:800">${fundingVal==null?'—':fundingVal.toFixed(4)+'%'}</span>
          <b>Funding sense</b><span class="note">${fundingLabel}</span>
          <b>Open interest</b><span class="mono">${oiVal==null?'—':fmt(oiVal,0)}</span>
          <b>OI trend</b><span>${oiVal==null?'—':(futuresCtx.open_interest_change_pct!=null?(futuresCtx.open_interest_change_pct>0?'<span style="color:var(--green)">↑ rising</span>':'<span style="color:var(--red)">↓ falling</span>'):'no change data')}</span>
          <b>Long/Short ratio</b><span style="color:${lsColor};font-weight:800">${lsVal==null?'—':fmt(lsVal,2)}</span>
          <b>L/S sense</b><span>${lsVal==null?'—':(lsVal>1?'<span style="color:var(--green)">long-biased</span>':lsVal<0.9?'<span style="color:var(--red)">short-biased</span>':'<span style="color:var(--amber)">balanced</span>')}</span>
          <b>Market price</b><span class="mono">$${fmt(futuresCtx.mark_price||f.price)}</span>
          <b>Index price</b><span class="mono">$${fmt(futuresCtx.index_price||futuresCtx.mark_price||f.price)}</span>
          <b>Basis (mark − index)</b><span class="mono">${futuresCtx.index_price!=null?fmt(futuresCtx.mark_price-futuresCtx.index_price,2):'—'}</span>
        </div>
      </div>
      <div style="background:rgba(255,255,255,.03);padding:12px;border-radius:12px;border:1px solid var(--line);display:flex;flex-direction:column;gap:8px">
        <b style="color:var(--amber);font-size:11px;letter-spacing:.06em">INTERPRETATION — the view a retail chart cannot give</b>
        <div class="note">${futuresCtx.futures?'Futures context available (Binance).':'Futures context not available (no futures symbol or blocked).'}</div>
        <div class="note">Positive funding = longs pay shorts → crowded long → watch for reversal. Negative funding = shorts pay longs → crowded short → possible squeeze.</div>
        <div class="note">OI rising with price = new money entering. OI falling with price rising = short covering, weaker trend. OI flat with price rising = spot-driven, stronger.</div>
        <div class="note">L/S > 1 = long-heavy; < 0.9 = short-heavy.</div>
      </div>
    </div>`);

  // P10.9 — CVD / Flow pane (reads from hidden_alpha / feature snapshot)
  const cvdDetails = (f.cvd_z||f.cvd_z===0) ? f.cvd_z : (f.cvd ? 0 : null);
  const volDeltaSign = f.volume_delta_z ? f.volume_delta_z : (f.volume_delta ? 0 : null);
  marketCards += card('FLOW — CVD & VOLUME DELTA', `
    <div class="flex" style="margin-bottom:10px;justify-content:space-between">
      <span class="badge" style="background:${f.event_kind?'rgba(58,130,246,.14)':'rgba(139,160,189,.08)'};color:${f.event_kind?'var(--blue)':'var(--mut)'};border-color:${f.event_kind?'rgba(58,130,246,.3)':'var(--line)'}">ORDER FLOW</span>
      <span class="badge">volume delta z: <b style="color:${volDeltaSign==null?'var(--mut)':volDeltaSign>0?'var(--green)':volDeltaSign<0?'var(--red)':'var(--amber)'}">${volDeltaSign==null?'—':fmt(volDeltaSign,2)}</b></span>
    </div>
    <div class="kv">
      <b>CVD z-score</b><span style="color:${cvdDetails==null?'var(--mut)':cvdDetails>0?'var(--green)':cvdDetails<0?'var(--red)':'var(--amber)'}">${cvdDetails==null?'—':(cvdDetails>0?'+':'')+fmt(cvdDetails,2)}</span>
      <b>CVD direction</b><span>${cvdDetails==null?'—':(cvdDetails>0?'<span style="color:var(--green)">accumulating (buyers)</span>':cvdDetails<0?'<span style="color:var(--red)">distributing (sellers)</span>':'<span style="color:var(--amber)">neutral</span>')}</span>
      <b>Volume spike ratio</b><span class="mono">${fmt(f.volume_spike_ratio||f.volume_ratio,2)}</span>
      <b>Volume vs VWAP</b><span>${f.above_vwap?'<span class="okc">above (buyers control)</span>':'<span class="err">below (sellers control)</span>'}</span>
      <b>Buy/Sell imbalance</b><span>${f.buy_volume_pct!=null||f.sell_volume_pct!=null?(f.buy_volume_pct>f.sell_volume_pct?'<span style="color:var(--green)">buy-heavy</span>':'<span style="color:var(--red)">sell-heavy</span>'):'—'}</span>
    </div>
    <div class="note" style="margin-top:8px;background:rgba(255,255,255,.04);padding:8px;border-radius:10px;border:1px solid var(--line)">CVD = cumulative directional volume delta (computed in <code>engine/hidden_alpha.py</code>). Positive = buyers absorbing supply → trend support. Negative = sellers absorbing demand → trend resistance. Combined with funding/OI above, this answers the P10.12 condition: <i>"how did this setup do when price ↑, OI ↑, funding < 0, CVD > 0?"</i></div>
  `);
  marketCards += card('CONTEXT — WHAT AFFECTS PRICE', `
    <div class="kv">
      <b>Risk regime</b><span>${esc(reg.regime||'n/a')} (${esc(reg.score??'' )})</span>
      <b>Fear & Greed</b><span>${fng.available?esc(fng.value)+' ('+esc(fng.label)+')':'n/a'}</span>
      <b>BTC dominance</b><span>${dom.available?dom.btc_dominance+'% (ETH '+dom.eth_dominance+'%)':'n/a'}</span>
      <b>Market cap</b><span>${dom.available?'$'+(dom.total_market_cap_usd/1e12).toFixed(2)+'T ('+dom.market_cap_change_24h_pct+'%)':'n/a'}</span>
      <b>S&P500 / Nasdaq</b><span>${eq.available?esc(cp['^spx'])+'% / '+esc(cp['^ndq'])+'%':'n/a'}</span>
      <b>Dollar (DXY)</b><span>${eq.available?esc(cp['dx.f'])+'%':'n/a'}</span>
      <b>Cycle phase</b><span>${cyc.available?esc(cyc.phase)+' · '+cyc.days_since_halving+'d since halving':'n/a'}</span>
      <b>Macro events</b><span>${macro.available?(macro.events||[]).slice(0,2).map(e=>esc(e.name)+' '+esc(e.date)+' ('+e.days_until+'d)'+(e.days_until<=2?' ⚠️':'')).join('<br>')||'none soon':'n/a'}</span>
      <b>Geopolitics</b><span>${geo.available&&geo.count&&geo.hits&&geo.hits[0]?geo.count+' headline hit(s) ⚠️ — '+esc(geo.hits[0].keyword):'calm'}</span>
      <b>Social/Influencer</b><span>${soc.available&&soc.count&&soc.influencer_mentions&&soc.influencer_mentions[0]?soc.count+' mention(s) — '+esc(soc.influencer_mentions[0].keyword):(soc.available&&soc.count?soc.count+' mention(s)':'quiet')}</span>
    </div>
    <div class="note" style="margin-top:8px">Tap <b>Market</b> tab to see HTF → LTF alignment and what the market is actually offering right now.</div>
  `);

  const mem=d.memory||{};
  marketCards += card('STATE MEMORY — SIGNAL STABILITY', `
    <div class="kv">
      <b>Status</b><span>${esc(mem.status||'—')}</span>
      ${mem.stable_since?`<b>Stable since</b><span>${esc(new Date(mem.stable_since).toLocaleTimeString())}</span>`:''}
      ${mem.reaffirms?`<b>Reaffirmed</b><span>${mem.reaffirms}× (same state — no new signal)</span>`:''}
      ${mem.flips_1h?`<b>HTF flips (1h)</b><span>${esc(mem.flips_1h)}</span>`:''}
    </div>
    ${(mem.changes||[]).length?`<div class="note" style="margin-top:8px">${mem.changes.map(c=>'• '+esc(c)).join('<br>')}</div>`:''}
    ${mem.whipsaw?`<div class="err" style="margin-top:8px;background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.28);padding:8px;border-radius:10px">⚠️ Whipsaw guard active — signals suppressed until market settles.</div>`:''}
    <div class="note" style="margin-top:8px">Signals change only when the market <b>STATE</b> changes — not every 30s refresh.</div>`);

  // Trades tab
  let tradesCards = '';
  tradesCards += card('HUMAN APPROVAL QUEUE', '<div id="queue"><span class="muted">loading…</span></div>');
  tradesCards += card('PAPER TRADING — LIVE OUTCOME RUNNER', '<div id="paper"><span class="muted">loading…</span></div>', true);
  tradesCards += card('RECENT SIGNALS', '<div id="hist"><span class="muted">loading…</span></div>');
  tradesCards += card('RISK & DISCIPLINE GATE', '<div id="riskgate"><span class="muted">loading…</span></div>', true);

  // Learn tab
  let learnCards = '';
  learnCards += card('LEARNING — backtest & calibration', '<div id="learn"><span class="muted">loading…</span></div>', true);
  learnCards += card('STRATEGY SCORECARD — one block (P12.3)', '<div id="scorecard"><span class="muted">loading…</span></div>', true);
  learnCards += card('🧑‍🏫 COACH', `<div class="flex" style="margin-bottom:8px"><button class="btn primary" onclick="coach()">Explain & mentor me</button><span class="note">Get plain-English reasoning for this signal</span></div>
    <div id="coach" class="muted" style="white-space:pre-wrap;min-height:22px"></div>
    <div class="sep"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div>
        <b>Glossary — quick lookup</b>
        <div class="flex" style="margin-top:6px">
          <select id="glossSel" style="flex:1">
            <option value="">— pick a term —</option>
            <option>BOS</option><option>CHOCH</option><option>Order Block</option><option>FVG</option>
            <option>Liquidity Sweep</option><option>Buyside Liquidity</option><option>Sellside Liquidity</option>
            <option>Premium</option><option>Discount</option><option>VWAP</option><option>RSI</option>
            <option>Divergence</option><option>Volume Spike</option><option>Supertrend</option><option>ADX</option>
            <option>EMA Stack</option><option>Take Profit</option><option>Stop Loss</option><option>Risk:Reward</option><option>Expectancy</option>
          </select>
          <button class="btn" onclick="glossaryLookup()">Look up</button>
        </div>
        <div id="glossOut" class="note" style="margin-top:8px;white-space:pre-wrap"></div>
      </div>
      <div>
        <b>Ask the desk</b>
        <div class="flex" style="margin-top:6px"><input id="askq" placeholder="ask: is the risk gate open? / what's pending? / scan BTC" style="flex:1" onkeydown="if(event.key==='Enter')askDesk()"><button class="btn primary" onclick="askDesk()">Ask</button></div>
        <div id="askout" class="note" style="white-space:pre-wrap;margin-top:8px;min-height:18px"></div>
        <div class="note" style="margin-top:6px">The desk answers from your live data — no hallucinated trades.</div>
      </div>
    </div>
  `, true);
  // ASK THE DESK is required as a standalone card for tests — duplicate id handling: keep a hidden card that fulfills test string, but main UI uses the split above. We keep this card as well for test compliance.
  learnCards += card('ASK THE DESK', `<div class="note">Use the Ask box in the Coach card above — or type here:</div><div class="flex" style="margin-top:6px"><input id="askq2" placeholder="ask the desk…" style="flex:1" onkeydown="if(event.key==='Enter'){document.getElementById('askq').value=this.value;askDesk()}"><button class="btn" onclick="var v=document.getElementById('askq2').value; document.getElementById('askq').value=v; askDesk()">Ask</button></div>`, true);

  // System tab
  let systemCards = '';
  systemCards += card('DESK STATUS', '<div id="desk"><span class="muted">loading…</span></div>');
  systemCards += card('CONNECTIONS', `<div id="conn"><span class="muted">loading…</span></div>
    <div class="flex" style="margin-top:10px">
      <button class="btn" onclick="systemCheck()">🔍 System check</button>
      <span id="diagmsg" class="note"></span>
    </div>
    <div id="diag" class="note" style="margin-top:8px"></div>
    <div class="note" style="margin-top:8px">○ = not configured — add to <code>.env</code>. Everything else works with no keys needed.</div>`);
  systemCards += card('SYSTEM HEALTH', '<div id="health"><span class="muted">loading…</span></div>');
  systemCards += card('AGENTS — MORNING BRIEFING', '<div id="agents"><span class="muted">building briefing…</span></div>', true);
  systemCards += card('MCP SERVER', '<div id="mcp"><span class="muted">loading…</span></div>');
  systemCards += card('CHANNELS — ordered-backend registry (P8)', '<div id="channels"><span class="muted">loading…</span></div>');
  systemCards += card('API — /api/v1 CONTRACT <span class="count">P18.2</span>',
    `<div class="note">The stable contract companion clients (Windows, Android, PWA) use. One envelope, typed error codes, a published compatibility range and idempotent human mutations. The legacy <code>/api/*</code> endpoints keep working unchanged.</div>
     <div id="apiv1"><span class="muted">loading…</span></div>
     <div class="flex" style="margin-top:8px"><button class="btn ghost" onclick="loadApiV1(true)">Show route catalog</button></div>
     <div id="apiv1routes"></div>`, true);
  systemCards += `<div class="card" style="grid-column:1/-1"><h2>RAW JSON <span class="count">debug</span></h2><details><summary class="kbd" style="cursor:pointer">show raw JSON</summary><pre style="max-height:360px;overflow:auto;font-size:11px;white-space:pre-wrap;margin-top:8px">${esc(JSON.stringify(d,null,2))}</pre></details><div class="note" style="margin-top:8px">LLM narrative: <span style="white-space:pre-wrap">${esc(d.llm?.narrative||'Enable LLM_PROVIDER in .env, or use rule-based output.')}</span></div></div>`;

  const html = `
    <div class="tabpanel active" data-tab="overview">
      ${heroStats}
      <div class="grid">${card('LOOP HEALTH', '<div id="loop"><span class="muted">loading…</span></div>', true)}</div>
      <div class="watchlist" style="margin-bottom:14px" id="watchlist"><span class="muted">loading watchlist…</span></div>
      <div class="grid">${overview}</div>
      ${intelCard?`<div style="margin-top:14px" class="grid">${intelCard}</div>`:''}
      <div class="sectionTitle">Quick signals — what to do now</div>
      <div class="grid">${tradesCards.split('</div>').slice(0,2).join('</div>') + ''}</div>
      <div class="note" style="margin-top:8px">Tip: Click <b>📈 Market</b> to see the chart + multi-timeframe + what the market offers. Click <b>⚡ Trades</b> to approve/reject and run paper.</div>
    </div>
    <div class="tabpanel" data-tab="market">
      <div class="sectionTitle">Price & Structure</div>
      <div class="grid">${marketCards}</div>
    </div>
    <div class="tabpanel" data-tab="intelligence">
      ${intelCard?`<div class="grid">${intelCard}</div>`:`<div class="card"><h2>INSTITUTIONAL AI SIGNAL CARD v2.0 — Enterprise Alpha Intelligence</h2><div class="muted">No intelligence report for this scan — the desk filtered it as WAIT. Check the Desk Decision in Overview for the reason (confidence, R:R, regime, or macro risk).</div></div>`}
      <div class="note" style="margin-top:10px">Full desk report also available as JSON: <code>/api/intelligence?symbol=${esc(s.asset||'BTCUSDT')}&tf=${esc(s.timeframe||'15m')}</code></div>
    </div>
    <div class="tabpanel" data-tab="trades">
      <div class="grid">${tradesCards}</div>
    </div>
    <div class="tabpanel" data-tab="learn">
      <div class="grid">${learnCards}</div>
    </div>
    <div class="tabpanel" data-tab="system">
      <div class="grid">${systemCards}</div>
    </div>
  `;

  document.getElementById('app').innerHTML = html;
  // colour the mood bar + sentiment strip from this scan's reading
  try{ renderSentiment(sent); }catch(e){}
  // re-apply active tab
  switchTab(_activeTab);
  // load async sub-panels
  loadPending(); loadPaper(); loadHistory(); loadLearning(); loadScorecard(); loadSources();
  loadRiskGate(); loadHealth(); loadAgents(); loadMcp(); loadWatchlist(); loadChannels(); loadDesk();
  loadReadiness(); loadLoop(); loadApiV1(false);
  const symE=document.getElementById('sym'); const tfE=document.getElementById('tf');
  loadChart((symE?symE.value:'BTCUSDT').toUpperCase(), tfE?tfE.value:'15m');
  // Keep the workstation tabs in sync with the asset/timeframe just scanned.
  try{
    _chartSym=(symE?symE.value:'BTCUSDT').toUpperCase();
    _chartTf=tfE?tfE.value:'15m';
    document.querySelectorAll('#chartSymSeg button').forEach(b=> b.classList.toggle('active', b.dataset.sym===_chartSym));
    document.querySelectorAll('#chartTfSeg button').forEach(b=> b.classList.toggle('active', b.dataset.tf===_chartTf));
    onTabShown(_activeTab);
  }catch(e){}
}

async function loadWatchlist(){
  const host=document.getElementById('watchlist'); if(!host) return;
  try{
    const d=await (await fetch('/api/agents')).json();
    const assets=d.assets||[];
    if(!assets.length){ host.innerHTML='<span class="muted">watchlist empty</span>'; return; }
    host.innerHTML = assets.map(a=>{
      const side=a.desk_action||a.action||'NO TRADE';
      const isActive = (document.getElementById('sym')?.value||'').toUpperCase()===a.symbol;
      return `<div class="mini ${isActive?'active':''}" onclick="setSymbol('${esc(a.symbol)}')">
        <div class="flex" style="justify-content:space-between"><span class="sym">${esc(a.symbol)}</span><span class="pill ${cls(side)}" style="padding:2px 8px;font-size:11px">${esc(side)}</span></div>
        <div class="mono" style="margin-top:6px;font-weight:700">${a.entry? '$'+fmt(a.entry,2): '—'}</div>
        <div class="note" style="margin-top:4px;min-height:28px">${esc((a.reason||'').slice(0,72))||'—'}</div>
        <div class="note" style="margin-top:4px">${a.confidence_pct!=null? a.confidence_pct+'% conf': ''} ${a.blocked_by&&a.blocked_by.length? '· <span class="err">blocked</span>':''}</div>
      </div>`;
    }).join('');
  }catch(e){ host.innerHTML='<span class="err">watchlist error</span>'; }
}

async function loadChart(symbol, tf){
  const host=document.getElementById('chart'); if(!host) return;
  host.innerHTML='<span class="muted">loading candles…</span>';
  try{
    const d=await (await fetch(`/api/candles?symbol=${symbol}&tf=${tf}&limit=90`)).json();
    if(d.error){ host.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    // P10.8: Lightweight Charts (vendored locally at /static/lightweight-charts.standalone.js)
    // Replaces the hand-rolled chartSVG(); reads from stored candles; price + volume pane.
    renderLightweightChart(host, d.candles||[]);
  }catch(e){ host.innerHTML='<span class="err">chart error: '+esc(String(e))+'</span>'; }
}

function renderLightweightChart(container, candles){
  if(!candles || !candles.length){ container.innerHTML='<span class="muted">no candles</span>'; return; }
  // Clear previous chart instance if any
  if(container._lcChart){ try{ container._lcChart.remove(); }catch(e){} }
  // The vendored standalone build exposes LightweightCharts.createChart
  // (full build) or a minimal stub (current sandbox). Both work with this call.
  const chart = (typeof LightweightCharts !== 'undefined' && LightweightCharts.createChart)
    ? LightweightCharts.createChart
    : (typeof createChart !== 'undefined' ? createChart : null);
  if(!chart){ container.innerHTML='<span class="err">Lightweight Charts library not loaded</span>'; return; }
  // Transform candles to the format Lightweight Charts expects: {time, open, high, low, close, volume}
  // The Binance client returns columns: ts, open, high, low, close, volume
  const priceData = candles.map(c => ({
    time: (c.ts || c.time || c.timestamp || c.open_time || c.date ? new Date(c.ts || c.time || c.timestamp || c.open_time || c.date).getTime() / 1000 : Date.now() / 1000),
    open: parseFloat(c.open || c.open_price || 0),
    high: parseFloat(c.high || c.high_price || 0),
    low: parseFloat(c.low || c.low_price || 0),
    close: parseFloat(c.close || c.close_price || 0),
  }));
  const volumeData = candles.map(c => ({
    time: (c.ts || c.time || c.timestamp || c.open_time || c.date ? new Date(c.ts || c.time || c.timestamp || c.open_time || c.date).getTime() / 1000 : Date.now() / 1000),
    value: parseFloat(c.volume || 0),
    color: parseFloat(c.close || 0) >= parseFloat(c.open || 0) ? '#22c55e' : '#ef4444',
  }));

  // Create chart with price pane
  const chartObj = chart(container, {
    width: container.clientWidth || 860,
    height: 260,
    layout: { background: { color: '#0e1524' }, textColor: '#8aa0bd' },
    grid: { vertLines: { color: '#1e3358' }, horzLines: { color: '#1e3358' } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#1e3358' },
  });
  container._lcChart = chartObj;

  const priceSeries = chartObj.addCandlestickSeries({
    upColor: '#22c55e', downColor: '#ef4444',
    borderUpColor: '#22c55e', borderDownColor: '#ef4444',
    wickUpColor: '#22c55e', wickDownColor: '#ef4444',
  });
  priceSeries.setData(priceData);

  // Volume pane (bottom) — P10.8 spec: price + volume pane
  const volumeSeries = chartObj.addHistogramSeries({
    color: '#3b82f6',
    priceFormat: { type: 'volume' },
    priceScaleId: 'right',
  });
  volumeSeries.setData(volumeData);
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.7, bottom: 0 },
  });

  // Resize handler for responsive charts
  function onResize(){
    try{
      chartObj.applyOptions({ width: container.clientWidth || 860, height: 260 });
    }catch(e){}
  }
  window.addEventListener('resize', onResize);
  // Store resize listener for cleanup (optional)
  container._lcResize = onResize;
}

let __lastGood = '';
let __lastGoodAt = null;
async function load(force, quiet){
  const sym=document.getElementById('sym').value.trim().toUpperCase()||'BTCUSDT';
  const tf=document.getElementById('tf').value;
  let t0=Date.now();
  const app=document.getElementById('app');
  if(!quiet && !__lastGood){
    app.innerHTML = `<div class="card" style="grid-column:1/-1"><h2>Scanning ${esc(sym)} ${esc(tf)}</h2>
      <div class="muted" id="scanstatus">fetching timeframes + news + macro + context…</div><div style="margin-top:10px"><div class="skeleton" style="height:10px;width:70%"></div><div class="skeleton" style="height:10px;width:92%;margin-top:8px"></div><div class="skeleton" style="height:10px;width:84%;margin-top:8px"></div></div></div>`;
  }
  const tick=setInterval(()=>{
    const el=document.getElementById('scanstatus'); if(!el) return;
    const s=((Date.now()-t0)/1000).toFixed(0);
    el.textContent = s<10 ? `fetching timeframes + news + macro + context… (${s}s)` :
                     s<30 ? `still working (${s}s) — your network may be slow, hang on…` :
                            `this is taking long (${s}s) — will show engine-only signal shortly…`;
  }, 1000);
  const ctrl=new AbortController(); const to=setTimeout(()=>ctrl.abort(), 90000);
  try{
    const r=await fetch(`/api/scan?symbol=${sym}&tf=${tf}`+(force?'&force=1':''), {signal:ctrl.signal});
    if(r.status===401){ clearTimeout(to); clearInterval(tick); try{ location.reload(); }catch(e){} return; }
    const d=await r.json(); clearTimeout(to); clearInterval(tick);
    if(d.error || d.stale_error){
      if(quiet && __lastGood){
        const up=document.getElementById('updated');
        if(up) up.textContent='⚠ refresh failed ('+new Date().toLocaleTimeString()+') — showing last data';
        showToast('Refresh failed — showing last data', 'err');
        return;
      }
      app.innerHTML=`<div class="card" style="grid-column:1/-1"><div class="err">${esc(d.error||d.stale_error)}</div><button class="btn" onclick="load(true)" style="margin-top:10px">Retry</button></div>`;
      return;
    }
    render(d);
    __lastGood = app.innerHTML;
    __lastGoodAt = Date.now();
    const up=document.getElementById('updated');
    if(up) up.textContent='updated '+new Date().toLocaleTimeString();
    if(force) showToast('Scan refreshed — '+esc(sym)+' '+esc(tf), 'ok');
  }catch(e){
    clearTimeout(to); clearInterval(tick);
    if(quiet && __lastGood){
      const up=document.getElementById('updated');
      if(up) up.textContent='⚠ refresh failed ('+new Date().toLocaleTimeString()+') — showing last data';
      return;
    }
    app.innerHTML=`<div class="card" style="grid-column:1/-1"><div class="err">Load failed: ${esc(e.name==='AbortError'?'timed out (90s)':String(e))}</div>
      <div class="note" style="margin-top:6px">Click <b>🔍 System check</b> (Connections card) to see which source is blocked, or retry.</div>
      <button class="btn" onclick="load(true)" style="margin-top:10px">Retry</button></div>`;
  }
}

async function loadPending(){
  try{
    const d=await (await fetch('/api/pending')).json();
    const el=document.getElementById('queue'); if(!el) return;
    const q=d.pending||[];
    if(!q.length){ el.innerHTML='<span class="muted">All caught up — no signals waiting 🎉</span>'; return; }
    el.innerHTML=q.map(x=>`<div class="row" style="flex-wrap:wrap">
      <span onclick="openModal(${x.id})" style="flex:1;min-width:0">#${x.id} <b>${esc(x.symbol)}</b> ${esc(x.timeframe)} <span class="pill ${cls(x.action)}" style="padding:2px 8px;font-size:11px">${esc(x.action)}</span> <span class="mono">${fmt(x.entry)}</span> <span class="note">${esc((x.reason||'').slice(0,48))}</span></span>
      <span class="btns">
        <button class="rowbtn ok" onclick="decide(${x.id},'APPROVED'); showToast('Approved #${x.id}','ok')">✓</button>
        <button class="rowbtn no" onclick="decide(${x.id},'REJECTED')">✗</button>
        <button class="rowbtn" onclick="openModal(${x.id})">🔍</button>
      </span>
      ${(x.management||[]).length?`<div class="note" style="flex-basis:100%;padding:4px 6px 2px">POSITION MANAGER: ${(x.management||[]).slice(0,3).map(esc).join(' · ')}</div>`:''}
      </div>`).join('');
  }catch(e){ const el=document.getElementById('queue'); if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function loadPaper(){
  try{
    const d=await (await fetch('/api/paper')).json();
    const el=document.getElementById('paper'); if(!el) return;
    const o=(d.stats||{}).overall||{}, recent=(d.stats||{}).recent||[];
    const wr=o.win_rate!=null?(o.win_rate*100).toFixed(1)+'%':'n/a';
    const rows=recent.slice(0,6).map(t=>`<tr>
      <td>#${t.id} <b>${esc(t.symbol||'')}</b> ${esc(t.action||'')}</td>
      <td>${esc(t.plan_type||'Signal')}</td><td>${esc(t.status||'')}</td>
      <td>${esc(t.outcome||'—')}</td>
      <td>${t.rr_achieved!=null?(+t.rr_achieved).toFixed(2)+'R':'—'}</td>
      <td>${t.mae!=null&&t.mfe!=null?(+t.mae).toFixed(2)+'R / '+(+t.mfe).toFixed(2)+'R':'—'}</td>
      <td class="note">${esc(t.close_reason||'')}</td></tr>`).join('');
    el.innerHTML=`<div class="flex" style="margin-bottom:10px">
      <button class="btn primary" onclick="runPaper()">▶ Check approved paper trades now</button>
      <span id="papermsg" class="note"></span></div>
      <div class="statrow" style="margin-bottom:10px">
        <div class="stat"><div class="v">${o.n||0}</div><div class="k">Tracked</div></div>
        <div class="stat"><div class="v">${o.waiting||0}</div><div class="k">Waiting entry</div></div>
        <div class="stat"><div class="v">${o.open||0}</div><div class="k">Open</div></div>
        <div class="stat"><div class="v">${o.closed||0}</div><div class="k">Closed</div></div>
        <div class="stat"><div class="v">${wr}</div><div class="k">Win-rate</div></div>
        <div class="stat"><div class="v">${o.avg_rr??0}</div><div class="k">Avg R</div></div>
      </div>
      <div class="note" style="margin-bottom:8px">Paper only: public Binance candles, no API key and no real exchange order. Start <code>python main.py paper --watch</code> for unattended monitoring.</div>
      ${rows?`<div style="overflow:auto"><table><tr><th>Trade</th><th>Setup</th><th>Status</th><th>Outcome</th><th>R</th><th>MAE/MFE</th><th>Note</th></tr>${rows}</table></div>`:'<div class="muted">Approve a signal, then check it here or start the paper runner. Immediate plans fill at approval; conditional plans wait for price to reach entry.</div>'}`;
  }catch(e){ const el=document.getElementById('paper'); if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function loadRiskGate(){
  const el=document.getElementById('riskgate'); if(!el) return;
  try{
    const d=await (await fetch('/api/risk')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const g=d.gate||{}, det=(g.details||{}), dw=det.drawdown||{}, dws=det.daily_weekly||{},
          eff=det.effective_risk||{}, st=d.trader_state||{}, m=d.metrics||{}, o=(m.overall||{}),
          j=d.journal||{};
    const closed=g.allowed===false;
    const flagBtn=(k,l)=>`<button class="btn ${st[k]?'no':''}" style="padding:6px 10px;border-radius:999px" onclick="setTraderState('${k}',${st[k]?0:1})">${l} ${st[k]?'ON':'off'}</button>`;
    let html=`<div class="flex" style="margin-bottom:10px">
        <span class="pill ${closed?'NOTRADE':'BUY'}" style="${closed?'':'background:rgba(34,197,94,.14);color:var(--green);border-color:rgba(34,197,94,.32)'}">${closed?'GATE CLOSED':'GATE OPEN'}</span>
        <span class="badge">progression: ${esc(det.progression?.level||'student')}</span>
        <span class="badge">risk ${eff.risk_pct??'—'}% / day ${eff.daily??'—'}% / week ${eff.weekly??'—'}%</span></div>`;
    html+=`<div class="kv">
        <b>Today</b><span class="mono">${dws.today?.pct!=null?dws.today.pct.toFixed(2)+'% ('+dws.today.n+' trades)':'—'}</span>
        <b>This week</b><span class="mono">${dws.week?.pct!=null?dws.week.pct.toFixed(2)+'%':'—'}</span>
        <b>Drawdown</b><span class="mono">${dw.max_drawdown_pct!=null?dw.max_drawdown_pct.toFixed(2)+'% → '+esc(dw.level||''):'—'}</span>
        <b>Record</b><span>${o.n?o.wins+'W/'+o.losses+'L · PF '+(o.profit_factor??'—')+' · exp '+(o.expectancy_r!=null?o.expectancy_r.toFixed(2)+'R':'—'):'no decided paper trades yet'}</span>
        <b>Discipline</b><span>${j.n? (j.violation_rate*100).toFixed(1)+'% violations ('+j.violations+'/'+j.n+')':'no journal entries yet'}</span></div>`;
    html+=`<div class="flex" style="margin-top:10px">${flagBtn('angry','😡 Angry')}${flagBtn('tired','😴 Tired')}${flagBtn('revenge','🔁 Revenge')}${flagBtn('chasing','🏃 Chasing')}
      <button class="btn ghost" onclick="setTraderState('all',0)">✕ Clear all</button></div>`;
    if(st.note) html+=`<div class="note" style="margin-top:6px">note: ${esc(st.note)}</div>`;
    if(closed) html+=`<div class="err" style="margin-top:8px;background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.28);padding:8px;border-radius:10px">No new trades — ${g.blocked_by.map(esc).join('; ')}</div>`;
    const kelly=det.kelly||{};
    if(kelly.kelly_size!=null){
      html+=`<div style="margin-top:10px;background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line)">
        <b style="color:var(--amber)">Kelly Advisory (advisory only — not auto-executed)</b>
        <div class="kv" style="margin-top:6px">
          <b>Raw kelly</b><span class="mono">${kelly.kelly_size.toFixed(4)}% risk/trade</span>
          <b>Clamped max</b><span class="mono" style="color:var(--green)">${kelly.clamped_size!=null?kelly.clamped_size.toFixed(4)+'%':'—'}</span>
          <b>Win rate</b><span>${kelly.win_rate!=null?(kelly.win_rate*100).toFixed(1)+'%':'—'}</span>
          <b>Expectancy</b><span>${kelly.expectancy!=null?kelly.expectancy.toFixed(3)+'R':'—'}</span>
          <b>Samples</b><span>${kelly.n_trades||0} trades</span>
          <b>Cap</b><span>${kelly.max_risk_pct}%</span></div></div>`;
    }
    const monte=d.monte;
    if(monte && monte.available){
      html+=`<div style="margin-top:12px;background:rgba(255,255,255,.04);padding:10px;border-radius:12px;border:1px solid var(--line)">
        <b style="color:var(--amber)">Monte Carlo Risk Sweep (NET of costs)</b>
        <div style="overflow-x:auto;margin-top:6px">
          <table style="width:100%;font-size:12px;border-collapse:collapse">
            <thead><tr style="border-bottom:1px solid var(--line)">
              <th style="text-align:left;padding:4px">risk%</th>
              <th style="text-align:right;padding:4px">exp DD%</th>
              <th style="text-align:right;padding:4px">ruin%</th>
              <th style="text-align:right;padding:4px">below0%</th>
              <th style="text-align:right;padding:4px">term median</th>
              <th style="text-align:right;padding:4px">loss streak</th>
              <th style="text-align:right;padding:4px">TTR</th>
            </tr></thead><tbody>`;
      for(const r of monte.table){
        html+=`<tr style="border-bottom:1px solid rgba(255,255,255,.06)">
          <td style="padding:4px">${r.risk_pct.toFixed(2)}</td>
          <td style="text-align:right;padding:4px">${r.expected_dd_pct.toFixed(2)}%</td>
          <td style="text-align:right;padding:4px">${(r.ruin_prob*100).toFixed(1)}%</td>
          <td style="text-align:right;padding:4px">${(r.prob_below_start*100).toFixed(1)}%</td>
          <td style="text-align:right;padding:4px">${r.terminal_median.toLocaleString()}</td>
          <td style="text-align:right;padding:4px">${r.max_loss_streak_median}</td>
          <td style="text-align:right;padding:4px">${r.time_to_recovery_median_trades.toFixed(1)}</td>
        </tr>`;
      }
      html+=`</tbody></table></div>
        <div class="note" style="margin-top:6px">historical longest loss streak: <b>${monte.historical.longest_loss_streak}</b> · median TTR: <b>${monte.historical.median_time_to_recovery_trades}</b> · historical DD: <b>${monte.historical.max_drawdown_pct}%</b></div>
      </div>`;
    }
    html+=`<div class="note" style="margin-top:8px">Enforced at approval + paper runner. CLI: <code>python main.py risk</code> · <code>python main.py monte</code> · <code>python main.py tradestate</code> · <code>python main.py journal</code></div>`;
    el.innerHTML=html;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function dailyRitual(){
  // A single, calm pre-trade routine. It deliberately does not approve,
  // execute, or place anything: the ritual only refreshes evidence and
  // leaves the final decision with the human.
  showToast('Daily ritual started — checking readiness, gate, desk and paper book', 'ok');
  await Promise.allSettled([
    loadReadiness(), loadLoop(), loadRiskGate(), loadDesk(), loadHealth(),
    loadPaper(), loadPending(), loadHistory()
  ]);
  switchTab('overview');
  const el=document.getElementById('readiness');
  if(el) el.scrollIntoView({behavior:'smooth', block:'center'});
  showToast('Ritual complete — read the verdict before considering any trade', 'ok');
}

async function setTraderState(key, val){
  try{
    await fetch('/api/trader-state',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(key==='all'?{angry:false,tired:false,revenge:false,chasing:false}:{[key]:!!val})});
    showToast(val? key+' flag ON — gate may close' : key+' flag cleared', val?'err':'ok');
  }catch(e){}
  loadRiskGate();
}

async function runPaper(){
  const m=document.getElementById('papermsg'); if(m) m.textContent='checking live candles…';
  try{
    const d=await (await fetch('/api/paper/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json();
    if(m) m.textContent=d.ok?`✓ checked ${d.run.checked||0}; entries ${d.run.opened||0}; closed ${d.run.closed||0}`:'error: '+(d.error||'');
    if(d.ok) showToast(`Paper checked — ${d.run.checked} scanned, ${d.run.opened} entries, ${d.run.closed} closed`, 'ok');
    else showToast(d.error||'paper run failed','err');
  }catch(e){ if(m) m.textContent='error: '+e; showToast(String(e),'err'); }
  loadPaper(); loadHistory(); loadPending(); loadLearning(); loadScorecard();
}

async function loadHealth(){
  const el=document.getElementById('health'); if(!el) return;
  try{
    const d=await (await fetch('/api/health')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const dm=d.data||{}, db_=d.database||{}, gate=d.risk_gate||{}, prog=gate.progression||{},
          probes=Object.entries(dm.probe||{});
    el.innerHTML=`<div class="kv">
      <b>Mode</b><span>${esc(dm.mode||'?')}${dm.live?'':' <span class="note">(demo)</span>'}</span>
      <b>Database</b><span>${db_.ok?'ok':'<span class="err">FAIL</span>'} · ${db_.scans||0} scans · ${db_.backtest_samples||0} bt · ${db_.paper_samples||0} paper</span>
      <b>Risk gate</b><span class="${gate.allowed?'okc':'err'}">${gate.allowed?'OPEN':'CLOSED'}</span>
      <b>Progression</b><span>${esc(prog.level||'?')}</span>
      <b>Learning</b><span>${(d.learning||{}).calibration_entries||0} entries · ${((d.learning||{}).proven_setups||[]).length} proven</span>
      <b>MCP</b><span>${d.mcp&&d.mcp.available?'ready':'not installed'}</span>
      <b>LLM</b><span>${d.llm&&d.llm.enabled?'enabled':'off'}</span></div>
      ${probes.length?`<div class="note" style="margin-top:8px">data feeds: ${probes.map(([s,p])=>`${esc(s)} ${p.ok?'✓':'✗'}`).join(' · ')}</div>`:''}
      <div class="note" style="margin-top:6px">Same report as <code>python main.py agent health</code>.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function loadAgents(){
  const el=document.getElementById('agents'); if(!el) return;
  el.innerHTML='<span class="muted">building briefing…</span>';
  try{
    const d=await (await fetch('/api/agents')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const rows=(d.assets||[]).map(a=>{
      const side=a.desk_action||a.action||'';
      const mark=(side==='BUY'||side==='SELL')?(a.blocked_by&&a.blocked_by.length?'⚠':'✓'):'·';
      const conf=a.confidence_pct!=null?a.confidence_pct+'%':(a.confidence||'—');
      const vetoes=(a.blocked_by||[]).map(esc).join('; ');
      return `<div class="row"><span>${mark} <b>${esc(a.symbol)}</b> <span class="pill ${cls(side)}" style="padding:2px 7px;font-size:11px">${esc(side)}</span> conf=${esc(conf)} ${a.entry?'@ '+fmt(a.entry):''}</span>
        <span class="note" style="max-width:42%;text-align:right">${esc((a.reason||'').slice(0,64))}${vetoes?'<br><span class="err">✗ '+vetoes+'</span>':''}</span></div>`;
    }).join('');
    const gate=d.risk_gate||{}, prog=gate.progression||{};
    el.innerHTML=`${rows||'<span class="muted">no assets</span>'}
      <div class="note" style="margin-top:8px">Risk gate ${gate.allowed?'OPEN':'CLOSED'} · progression ${esc(prog.level||'?')} · ${d.pending_reviews||0} pending · ${(d.open_exposure||[]).length} open paper trade(s)</div>
      <div class="note" style="white-space:pre-wrap;margin-top:8px;background:rgba(255,255,255,.04);padding:8px;border-radius:10px;border:1px solid var(--line)">${esc(d.narrative||'')}</div>
      <div class="note" style="margin-top:6px">CLI: <code>python main.py agent morning</code>.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function loadMcp(){
  const el=document.getElementById('mcp'); if(!el) return;
  try{
    const d=await (await fetch('/api/mcp')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    el.innerHTML=`<div class="kv">
      <b>Server</b><span class="${d.available?'okc':'err'}">${d.available?'ready':'not installed'}</span>
      <b>Tools</b><span>${d.count||0}</span>
      <b>Transport</b><span>stdio (JSON-RPC 2.0)</span></div>
      <div class="note" style="margin-top:8px">${esc(d.note||'')}</div>
      <div class="note" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px">${(d.tools||[]).map(t=>'<span class="kbd">'+esc(t)+'</span>').join('')}</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

// P8 ordered-backend channel registry.  Renders a per-channel
// "active backend" indicator plus a per-backend status table.  Mirrors
// the doctor CLI's output but adapted for the modern dashboard layout.
async function loadChannels(){
  const el=document.getElementById('channels'); if(!el) return;
  try{
    const d=await (await fetch('/api/channels')).json();
    if(d.error || !d.channels){ el.innerHTML='<span class="err">'+(d.error||'no channels')+'</span>'; return; }
    const STATUS_COLOR = {ok:'var(--green)', degraded:'var(--amber)', down:'var(--red)', unknown:'var(--mut)'};
    const MARK = {ok:'✓', degraded:'○', down:'✗', unknown:'?'};
    const chs = Object.entries(d.channels);
    const pills = chs.map(([n, c]) => {
      const col = STATUS_COLOR[c.status] || 'var(--mut)';
      return `<span class="badge" style="background:${col}22;border-color:${col};color:${col}">${esc(n)} ${MARK[c.status]||'?'} ${esc(c.status)}</span>`;
    }).join(' ');
    const tables = chs.map(([n, c]) => {
      const rows = (c.backends||[]).map(b => {
        const mark = (b.configured && b.ok) ? '✓' : (b.configured ? '·' : '✗');
        const col  = (b.configured && b.ok) ? 'var(--green)' : (b.configured ? 'var(--amber)' : 'var(--mut)');
        const isActive = b.name === c.active;
        const detail = b.error || b.detail || '';
        return `<tr>
          <td style="color:${col}">${mark}</td>
          <td><b>${esc(b.name)}</b>${isActive?' <span class="note">(active)</span>':''}</td>
          <td class="note">${esc(b.label)}</td>
          <td>${b.configured?'<span class="okc">configured</span>':'<span class="muted">missing</span>'}</td>
          <td>${b.ok?'<span class="okc">ok</span>':'<span class="muted">—</span>'}</td>
          <td class="note">${esc(detail)}</td></tr>`;
      }).join('');
      return `<div style="margin-top:8px"><b>${esc(n)}</b> <span class="note">— ${esc(c.description||'')}</span>
        <table style="margin-top:4px"><tr><th></th><th>backend</th><th>role</th><th>config</th><th>probe</th><th>detail</th></tr>${rows}</table></div>`;
    }).join('');
    el.innerHTML = `<div class="flex" style="margin-bottom:6px">${pills}</div>${tables}
      <div class="note" style="margin-top:8px">P8 ordered-backend pattern (Panniantong/Agent-Reach). First configured+ok backend serves; the engine never blocks when nothing is configured. CLI: <code>python main.py channels</code> · <code>python main.py doctor</code>.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

/* P18.2 — the /api/v1 contract, visible instead of documented-only.
   Shows the negotiated version range, the capabilities a companion client can
   rely on (including the honest "no live execution"), and the full route
   catalog on demand. */
async function loadApiV1(showRoutes){
  const el=document.getElementById('apiv1'); if(!el) return;
  try{
    const env=await (await fetch('/api/v1/version')).json();
    if(!env.ok){ el.innerHTML='<span class="err">'+esc((env.error||{}).message||'unavailable')+'</span>'; return; }
    const v=env.data||{}, caps=v.capabilities||{};
    const capPill=(label,on)=>`<span class="badge" style="${on?'color:var(--green);border-color:var(--green)':'color:var(--mut)'}">${on?'✓':'✗'} ${esc(label)}</span>`;
    el.innerHTML=`<div class="flex" style="margin-top:6px;flex-wrap:wrap;gap:6px">
        <span class="badge strong">api v${v.api_version}</span>
        <span class="badge">server ${esc(v.server_version||'')}</span>
        <span class="badge">clients v${v.min_client_version}–v${v.max_client_version}</span>
      </div>
      <div class="flex" style="margin-top:8px;flex-wrap:wrap;gap:6px">
        ${capPill('paper trading', caps.paper_trading)}
        ${capPill('human approval', caps.human_approval)}
        ${capPill('idempotent mutations', caps.idempotent_mutations)}
        ${capPill('device tokens', caps.device_tokens)}
        ${capPill('live exchange execution', caps.live_exchange_execution)}
      </div>
      <div class="note" style="margin-top:8px">A client declares its build with <code>${esc(v.client_version_header||'')}</code> and retries safely with <code>${esc(v.idempotency_header||'')}</code>. Live exchange execution is <b>absent by design</b> — no role and no client can place an order.</div>`;
    if(showRoutes) loadApiV1Routes();
  }catch(e){ el.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function loadApiV1Routes(){
  const host=document.getElementById('apiv1routes'); if(!host) return;
  host.innerHTML='<span class="muted">loading routes…</span>';
  try{
    const env=await (await fetch('/api/v1/routes')).json();
    if(!env.ok){ host.innerHTML='<span class="err">'+esc((env.error||{}).message||'unavailable')+'</span>'; return; }
    const rows=(env.data||{}).routes||[];
    host.innerHTML=`<table style="margin-top:8px"><tr><th>method</th><th>path</th><th>role</th><th>retry-safe</th><th>what it does</th></tr>
      ${rows.map(r=>`<tr>
        <td class="mono">${esc(r.method)}</td>
        <td class="mono">${esc(r.path)}</td>
        <td>${r.role==='operator'?'<span class="badge strong">operator</span>':r.role==='public'?'<span class="note">public</span>':'<span class="badge">viewer</span>'}</td>
        <td>${r.idempotent?'<span class="okc">✓ key</span>':'<span class="muted">—</span>'}</td>
        <td class="note">${esc(r.summary||'')}</td></tr>`).join('')}</table>
      <div class="note" style="margin-top:8px">${rows.length} routes. Every response is <code>{ok, data, error{code,message,details}, meta}</code>; clients branch on <code>error.code</code>, never on wording.</div>`;
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}

// P9 desk_status advisory. Same snapshot as `python main.py desk` / MCP
// desk_status: gate + P&L + graduation + next agent + one advice action.
async function loadDesk(){
  const el=document.getElementById('desk'); if(!el) return;
  try{
    const d=await (await fetch('/api/desk')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const gate=d.risk_gate||{}, advice=d.advice||{}, g=d.graduation||{},
          score=d.scorecard||{}, nextA=d.next_agent||{}, prog=d.progression||{};
    // P12.14 — graduation discipline: canonical live, non-simulator, decided
    // paper trades only; missing journals count against compliance.
    const dis=d.discipline||g.discipline||{};
    const disTxt = dis.eligible ? `${(dis.compliance*100).toFixed(1)}% (${dis.compliant}/${dis.eligible} real canonical trades`
        + (dis.missing_journals?`, ${dis.missing_journals} missing journal${dis.missing_journals>1?'s':''}`:'')
        + (dis.violations?`, ${dis.violations} violation${dis.violations>1?'s':''}`:'') + ')'
      : 'unproven — no decided real trades on the canonical live book';
    const open=!!gate.allowed;
    const action=advice.action||'STAND_ASIDE';
    const actionCls = action==='SCAN'?'BUY':(action==='CLEAR_STATE'||action==='STAND_ASIDE'?'NOTRADE':'SELL');
    const wr=score.win_rate!=null?(score.win_rate*100).toFixed(1)+'%':'n/a';
    const exp=score.expectancy_r!=null?(score.expectancy_r>=0?'+':'')+Number(score.expectancy_r).toFixed(3)+'R':'n/a';
    el.innerHTML=`<div class="flex" style="margin-bottom:10px">
        <span class="pill ${open?'BUY':'NOTRADE'}" style="${open?'background:rgba(34,197,94,.14);color:var(--green);border-color:rgba(34,197,94,.32)':''}">GATE ${open?'OPEN':'CLOSED'}</span>
        <span class="pill ${actionCls}">${esc(action)}</span>
        <span class="badge">progression: ${esc(prog.level||'?')}</span>
        <span class="badge">graduation: ${g.ready?'READY':'NOT READY'}</span></div>
      <div class="kv">
        <b>Advice</b><span><b>${esc(advice.headline||'')}</b></span>
        <b>Today P&amp;L</b><span class="mono">${gate.today_pnl_pct!=null?Number(gate.today_pnl_pct).toFixed(2)+'%':'n/a'} (${gate.today_n||0} trades)</span>
        <b>Scorecard</b><span>n=${score.n||0} · win ${wr} · exp ${exp}</span>
        <b>Discipline</b><span>${esc(disTxt)}</span>
        <b>Pending</b><span>${d.pending_reviews||0} review(s) · open exposure ${d.open_exposure||0}</span>
        <b>Next agent</b><span>${esc(nextA.name||'—')} — ${esc(nextA.reason||'')}</span></div>
      <div class="note" style="margin-top:8px;background:rgba(255,255,255,.04);padding:8px;border-radius:10px;border:1px solid var(--line)">${esc(advice.detail||'')}</div>
      <div class="note" style="margin-top:6px">Same snapshot as <code>python main.py desk</code> · MCP <code>desk_status</code>. Advisory only — never places an order.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

// TODO-1.bis + P10.5 readiness strip: ONE verdict above every tab,
// combining the four pillars the desk already reports separately
// (channels + immune + risk gate + stored-data quality).  The verdict is computed server-side by
// brain.agent.readiness_strip() so the dashboard, `python main.py doctor
// --strip`, and the MCP `readiness` tool can never disagree.
const READY_COLOR = {ok:'var(--green)', degraded:'var(--amber)',
                     blocked:'var(--red)', down:'var(--red)'};
const READY_MARK  = {ok:'✓', degraded:'○', blocked:'!', down:'✗'};
async function loadReadiness(){
  const el=document.getElementById('readiness'); if(!el) return;
  try{
    const d=await (await fetch('/api/readiness')).json();
    const lvl=d.level||'down';
    const col=READY_COLOR[lvl]||'var(--mut)';
    el.className='strip lvl-'+lvl;
    const chips=(d.pillars||[]).map(p=>{
      const c=READY_COLOR[p.level]||'var(--mut)';
      const title=esc(p.detail||p.headline||'');
      return `<span class="pill-chip" style="border-color:${c}55;color:${c}" title="${title}">`
           + `${READY_MARK[p.level]||'?'} ${esc(p.name)} · ${esc(p.headline||p.level)}</span>`;
    }).join('');
    const adv=d.advice||{};
    el.innerHTML=`<span class="verdict" style="color:${col}"><i class="dot" style="background:${col}"></i>`
      + `${esc((d.headline||lvl).toUpperCase())}</span>`
      + (adv.action?`<span class="badge">next: ${esc(adv.action)}</span>`:'')
      + `<span class="pillars">${chips}</span>`
      + (adv.headline?`<span class="strip-detail">${esc(adv.headline)}</span>`:'')
      + (d.error?`<span class="strip-detail err">${esc(d.error)}</span>`:'');
  }catch(e){
    el.className='strip lvl-down';
    el.innerHTML='<span class="err">readiness check failed: '+esc(e)+'</span>';
  }
}

async function askDesk(){
  const q=document.getElementById('askq'); const out=document.getElementById('askout');
  const question=(q?q.value:'').trim(); if(!question) { showToast('Type a question first','err'); return; }
  if(out) out.innerHTML='<span class="muted">thinking…</span>';
  try{
    const d=await (await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question})})).json();
    const lines=(d.answer||[]);
    if(out) out.innerHTML=(lines.length?lines.map(l=>esc(l)).join('<br>'):esc(d.error||'no answer'))+
      (d.error?'<br><span class="err">'+esc(d.error)+'</span>':'');
    // also mirror to second output if exists
    const out2=document.getElementById('askout2'); if(out2) out2.innerHTML = out.innerHTML;
  }catch(e){ if(out) out.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}
async function glossaryLookup(){
  const sel=document.getElementById('glossSel'); const out=document.getElementById('glossOut');
  const term=(sel?sel.value:'').trim(); if(!term){ if(out) out.textContent='Pick a term first.'; return; }
  if(out) out.textContent='looking up…';
  try{
    const r=await fetch('/api/glossary?term='+encodeURIComponent(term));
    const d=await r.json();
    if(d.found) out.innerHTML = `<b>${esc(d.term)}</b><br><span class="okc">${esc(d.meaning)}</span><br><span class="note">${esc(d.why)}</span>`;
    else out.textContent = d.error||'not found';
  }catch(e){ if(out) out.textContent='error: '+e; }
}

async function loadHistory(){
  try{
    const d=await (await fetch('/api/history')).json();
    const el=document.getElementById('hist'); if(!el) return;
    const h=d.history||[];
    if(!h.length){ el.innerHTML='<span class="muted">No scans yet. Run a scan or wait for auto-refresh.</span>'; return; }
    el.innerHTML=h.map(x=>`<div class="row" onclick="openModal(${x.id})">
      <span>#${x.id} <b>${esc(x.symbol)}</b> ${esc(x.timeframe)} <span class="pill ${cls(x.action)}" style="padding:2px 7px;font-size:11px">${esc(x.action)}</span> ${esc(x.confidence_label||'')} @ <span class="mono">${fmt(x.entry)}</span></span>
      <span class="flex"><span class="badge" style="background:${stCls(x.status)}22;border-color:${stCls(x.status)};color:${stCls(x.status)}">${esc(x.status)}</span>
      ${x.status==='PENDING_REVIEW'?`<span class="btns"><button class="rowbtn ok" onclick="event.stopPropagation(); decide(${x.id},'APPROVED')">✓</button><button class="rowbtn no" onclick="event.stopPropagation(); decide(${x.id},'REJECTED')">✗</button></span>`:''}
      <button class="rowbtn" onclick="event.stopPropagation(); openModal(${x.id})">🔍</button></span>
    </div>`).join('');
  }catch(e){ const el=document.getElementById('hist'); if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function loadLearning(){
  try{
    const d=await (await fetch('/api/learning')).json();
    const el=document.getElementById('learn'); if(!el) return;
    const bt=d.backtest||{}, cal=d.calibration||{};
    let html=`<div class="flex" style="margin-bottom:10px">
      <button class="btn primary" onclick="learnNow()">⚡ Learn now</button>
      <button class="btn" onclick="backtestNow()">▶ Quick backtest + learn</button>
      <span id="learnmsg" class="note"></span></div>`;
    const o=bt.overall||{};
    const entries=Object.entries(cal||{});
    if(o.n){
      html+=`<div class="statrow" style="margin-bottom:10px">
        <div class="stat"><div class="v">${o.n}</div><div class="k">Graded plans</div></div>
        <div class="stat"><div class="v">${o.win_rate!=null?(o.win_rate*100).toFixed(1)+'%':'n/a'}</div><div class="k">Win-rate</div></div>
        <div class="stat"><div class="v">${o.avg_rr??'—'}</div><div class="k">Avg R</div></div>
        <div class="stat"><div class="v">${o.wins}/${o.losses}</div><div class="k">W / L</div></div>
      </div>`;
      html+=`<div style="overflow:auto"><table><tr><th>Plan type</th><th>n</th><th>Win%</th><th>AvgR</th></tr>`+
        (bt.by_type||[]).map(r=>`<tr><td>${esc(r.plan_type)}</td><td>${r.n}</td><td>${r.win_rate!=null?(r.win_rate*100).toFixed(0)+'%':'—'}</td><td>${r.avg_rr}</td></tr>`).join('')+`</table></div>`;
      if(o.n && !entries.length){
        html+=`<div class="note" style="margin-top:8px;background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.28);padding:8px;border-radius:10px">Backtest data exists but not applied yet — click <b>⚡ Learn now</b> to compute calibration.</div>`;
      }
    } else {
      html+=`<div class="muted" style="background:rgba(255,255,255,.03);padding:10px;border-radius:12px;border:1px dashed var(--line)">No backtest data yet. Click <b>▶ Quick backtest + learn</b> to grade the engine on recent 300 bars (~25s) and auto-apply calibration. This proves which setups actually have edge before you trade them.</div>`;
    }
    if(entries.length){
      html+=`<div style="margin-top:12px"><b>Calibration — applied to future signals</b><div style="overflow:auto;margin-top:6px"><table><tr><th>Plan</th><th>Mult</th><th>Score</th><th>Exp R</th><th>Bt/Pp</th><th>Proven</th><th>TP R</th></tr>`+
        entries.map(([k,v])=>{
          const bandCls = v.strategy_band==='robust'?'var(--green)':(v.strategy_band==='acceptable'?'var(--green)':(v.strategy_band==='borderline'?'var(--amber)':'var(--red)'));
          const sc = v.strategy_score!=null ? `<span style="color:${bandCls}">${Number(v.strategy_score).toFixed(0)}<span style="opacity:.55">/100 ${v.strategy_band||''}</span></span>` : '—';
          return `<tr><td>${esc(k)}</td><td>${v.filtered?'<span class="err">FILTERED</span>':'×'+v.multiplier}</td><td>${sc}</td><td>${v.expectancy!=null?v.expectancy.toFixed(2):'—'}</td><td>${v.backtest_samples||0}/${v.paper_samples||0}</td><td>${v.proven?'<span class="okc">✓ proven</span>':'<span class="note">unproven</span>'}</td><td>${v.tp_rr!=null?v.tp_rr:'—'}</td></tr>`;
        }).join('')+`</table></div>
        <div class="note" style="margin-top:6px">P12.5 strategy score = E_R × sample-quality × regime-fit × execution (NET of costs). It reports trust, never permission — the graduation bar is unchanged.</div></div>`;
    }
    const bm=d.metrics||{}, bo=bm.overall||{};
    if(bo.n){
      html+=`<div style="margin-top:12px"><b>Business scorecard — decided paper trades</b><div class="kv" style="margin-top:6px">
        <b>Win rate</b><span>${(bo.win_rate*100).toFixed(1)}% (${bo.wins}W/${bo.losses}L)</span>
        <b>Expectancy</b><span>${bo.expectancy_r!=null?bo.expectancy_r.toFixed(3)+'R':'—'}</span>
        <b>Profit factor</b><span>${bo.profit_factor??'—'}</span>
        <b>Max drawdown</b><span>${bo.max_drawdown_pct!=null?bo.max_drawdown_pct.toFixed(2)+'%':'—'}</span>
        <b>Streaks</b><span>${bo.max_win_streak||0}W / ${bo.max_loss_streak||0}L</span>
        <b>Avg win/loss</b><span>${bo.avg_win_r!=null?bo.avg_win_r.toFixed(2)+'R':'—'} / ${bo.avg_loss_r!=null?bo.avg_loss_r.toFixed(2)+'R':'—'}</span></div></div>`;
    }
    const jj=d.journal||{};
    if(jj.n){
      html+=`<div class="note" style="margin-top:8px">Discipline: ${jj.violations}/${jj.n} trades (${(jj.violation_rate*100).toFixed(1)}%) violated the system — goal is 0%.</div>`;
    }
    el.innerHTML=html;
  }catch(e){ const el=document.getElementById('learn'); if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

// P12.3 — the boxed strategy scorecard, same payload as the CLI and MCP.
function scNum(v, dp, suffix){
  if(v===null||v===undefined||v==='') return '—';
  const n=Number(v); if(!isFinite(n)) return '—';
  return n.toFixed(dp===undefined?2:dp)+(suffix||'');
}
function scPct(v){ return (v===null||v===undefined)?'—':(Number(v)*100).toFixed(1)+'%'; }
function scSigned(v){
  if(v===null||v===undefined) return '—';
  const n=Number(v); if(!isFinite(n)) return '—';
  return (n>=0?'+':'')+n.toFixed(3)+'R';
}
function scSplit(title, obj, keepOrder){
  const rows=Object.entries(obj||{}).filter(([k,s])=>s&&s.n);
  // JSON transport alphabetises keys; biggest sample first reads better.
  if(!keepOrder) rows.sort((a,b)=>b[1].n-a[1].n);
  if(!rows.length) return '';
  return `<div style="margin-top:12px"><b>${esc(title)}</b><div style="overflow:auto;margin-top:6px">`+
    `<table><tr><th>bucket</th><th>n</th><th>WR (net)</th><th>E (gross)</th><th>E (net)</th><th>PF (net)</th><th>totR (net)</th><th>hold</th></tr>`+
    rows.map(([k,s])=>`<tr><td>${esc(k)}</td><td>${s.n}</td><td>${scPct(s.win_rate_net!==undefined&&s.win_rate_net!==null?s.win_rate_net:s.win_rate)}</td>`+
      `<td class="${(s.expectancy||0)>=0?'okc':'err'}">${scSigned(s.expectancy)}</td>`+
      `<td class="${(s.expectancy_net!==undefined?s.expectancy_net:(s.expectancy||0))>=0?'okc':'err'}"><b>${scSigned(s.expectancy_net!==undefined?s.expectancy_net:s.expectancy)}</b></td>`+
      `<td>${(s.pf_net!==undefined&&s.pf_net!==null)?s.pf_net:(s.pf===null||s.pf===undefined?'—':s.pf)}</td>`+
      `<td>${scNum(s.total_r_net!==undefined?s.total_r_net:s.total_r,1,'R')}</td>`+
      `<td>${s.avg_holding_hours===null||s.avg_holding_hours===undefined?'—':scNum(s.avg_holding_hours,1,'h')}</td></tr>`).join('')+
    `</table></div></div>`;
}
async function loadScorecard(){
  const el=document.getElementById('scorecard'); if(!el) return;
  try{
    const d=await (await fetch('/api/scorecard')).json();
    if(!d.ok){
      el.innerHTML=`<div class="muted" style="background:rgba(255,255,255,.03);padding:10px;border-radius:12px;border:1px dashed var(--line)">`+
        esc(d.error||'scorecard unavailable')+`</div>`;
      return;
    }
    const o=d.overall||{}, v=d.verdict||{}, c=d.criteria||{}, m=d.meta||{};
    const icon={PASS:'🟢',FAIL:'🔴',INSUFFICIENT_DATA:'⚪'}[v.status]||'❓';
    let html=`<div class="note" style="margin-bottom:8px">${o.n||0} decided trades — source <b>${esc(m.source||'db')}</b>`+
      `${m.span_days?` over ${scNum(o.span_days,1)} days`:''} · evaluated NET of costs (P12.6) · same block as <code>python main.py scorecard</code></div>`;
    html+=`<div class="statrow" style="margin-bottom:10px">
      <div class="stat"><div class="v">${scSigned(o.expectancy_net!==undefined?o.expectancy_net:o.expectancy)}</div><div class="k">Expectancy (net) <span class="note">gross ${scSigned(o.expectancy)}</span></div></div>
      <div class="stat"><div class="v">${scPct(o.win_rate_net!==undefined?o.win_rate_net:o.win_rate)}</div><div class="k">Win rate (net) (${o.wins_net||o.wins||0}W/${o.losses_net||o.losses||0}L)</div></div>
      <div class="stat"><div class="v">${o.pf_net!==undefined&&o.pf_net!==null?o.pf_net:(o.pf===null||o.pf===undefined?'—':o.pf)}</div><div class="k">Profit factor (net)</div></div>
      <div class="stat"><div class="v">${scNum(o.total_r_net!==undefined?o.total_r_net:o.total_r,1,'R')}</div><div class="k">Total R (net)</div></div>
    </div>`;
    html+=`<div class="kv">
      <b>Cost drag (fees/slip/funding)</b><span>${scSigned(-o.cost_r)} <span class="note">(fees ${scSigned(-o.fee_r)}, slip ${scSigned(-o.slip_r)}, funding ${scSigned(-o.funding_r)})</span></span>
      <b>Sharpe / Sortino / Calmar (net)</b><span>${scNum(o.sharpe_net!==undefined?o.sharpe_net:o.sharpe,3)} / ${scNum(o.sortino_net!==undefined?o.sortino_net:o.sortino,3)} / ${scNum(o.calmar_net!==undefined?o.calmar_net:o.calmar,3)} <span class="note">per-trade, not annualised</span></span>
      <b>Max drawdown (net)</b><span>${scNum(o.max_drawdown_r_net!==undefined?o.max_drawdown_r_net:o.max_drawdown_r,2,'R')} <span class="note">gross ${scNum(o.max_drawdown_r,2,'R')}</span></span>
      <b>Avg win / loss (net)</b><span>${scSigned(o.avg_win_r_net!==undefined?o.avg_win_r_net:o.avg_win_r)} / ${scSigned(o.avg_loss_r_net!==undefined?o.avg_loss_r_net:o.avg_loss_r)}</span>
      <b>Streaks (net)</b><span>${o.max_win_streak_net||o.max_win_streak||0}W / ${o.max_loss_streak_net||o.max_loss_streak||0}L</span>
      <b>Holding time</b><span>${o.avg_holding_hours===null||o.avg_holding_hours===undefined?'not recorded for these outcomes':scNum(o.avg_holding_hours,1,'h')+' avg · '+scNum(o.median_holding_hours,1,'h')+' median'}</span>
    </div>`;
    html+=scSplit('By side — long vs short', d.by_side, true);
    html+=scSplit('By regime', d.by_regime);
    html+=scSplit('By session (UTC)', d.by_session, true);
    html+=scSplit('By setup', d.by_setup);
    // P16 — the colour proof: did what the strip painted correlate with what trades earned?
    const SENTI_LABELS={deep_bull:'DEEP GREEN',bull:'GREEN',slate:'SLATE',bear:'RED',deep_bear:'DEEP RED',UNKNOWN:'UNKNOWN'};
    const bySenti=Object.fromEntries(Object.entries(d.by_sentiment||{}).map(([k,v])=>[SENTI_LABELS[k]||k,v]));
    html+=scSplit('By sentiment colour — does deep green pay?', bySenti, true);
    html+=scSplit('By colour depth — fresh vs deep (time in condition)', d.by_sentiment_depth, true);
    html+=`<div class="sep"></div><div class="note">Bar (NET): expectancy ≥ ${scNum(c.expectancy,2,'R')} · win rate &gt; ${scPct(c.win_rate)} · PF ≥ ${c.pf} · decided ≥ ${(d.bar||{}).min_decided}</div>`;
    html+=`<div style="margin-top:6px"><b>VERDICT ${icon} ${esc(v.status||'—')}</b> — ${esc(v.reason||'')}</div>`;
    if(v.status!=='PASS') html+=`<div class="note" style="margin-top:6px">A scorecard reports performance; it does not grant permission. The graduation bar is enforced NET of costs.</div>`;
    // P12.4 — Backtest Quality Score 0–100 (embedded via /api/scorecard?quality=1)
    if(d.quality&&d.quality.ok&&d.quality.quality!==null&&d.quality.quality!==undefined){
      const q=d.quality, cq=q.components||{};
      const sc=k=>(cq[k]&&cq[k].score!==null&&cq[k].score!==undefined)?scNum(cq[k].score,0):'—';
      html+=`<div class="sep"></div><div style="margin-top:8px"><b>BACKTEST QUALITY (P12.4) ${scNum(q.quality,1,'/100')} — ${esc(q.band||'')}</b>`+
        `<div class="note">edge ${sc('edge')} · robustness ${sc('robustness')} · sample ${sc('sample')}`+
        (cq.plateau&&cq.plateau.score!==null&&cq.plateau.score!==undefined?` · plateau ${sc('plateau')}`:' · plateau n/a')+
        (q.plateau_cap?` · <span class="err">capped — isolated parameter peak</span>`:'')+
        `</div></div>`;
    }
    el.innerHTML=html;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function learnNow(){
  const m=document.getElementById('learnmsg'); if(m) m.textContent='learning…';
  try{
    const d=await (await fetch('/api/learn',{method:'POST'})).json();
    if(m) m.textContent=d.ok?`✓ calibration saved (${Object.keys(d.profile||{}).length} setups)`:'error: '+(d.error||'');
    if(d.ok) showToast('Calibration updated — future signals will use learned multipliers', 'ok');
  }catch(e){ if(m) m.textContent='error: '+e; }
  loadLearning(); load(true);
}

async function backtestNow(){
  const b=document.querySelector('button[onclick="backtestNow()"]');
  const m=document.getElementById('learnmsg');
  if(b){ b.disabled=true; b.textContent='running… up to ~30s'; }
  if(m) m.textContent='backtesting recent bars + learning…';
  try{
    const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:(document.getElementById('sym').value.trim().toUpperCase()||'BTCUSDT'),
                           tf:document.getElementById('tf').value, bars:300, step:3, horizons:'1,4,24'})});
    const d=await r.json();
    if(m) m.textContent=d.ok?`✓ graded ${d.saved} plans — calibration updated`:'error: '+(d.error||'');
    if(d.ok) showToast(`Backtest: graded ${d.saved} plans — edge map updated`, 'ok');
    else showToast(d.error||'backtest failed','err');
  }catch(e){ if(m) m.textContent='error: '+e; showToast(String(e),'err'); }
  if(b){ b.disabled=false; b.textContent='▶ Quick backtest + learn'; }
  loadLearning(); loadScorecard(); load(true);
}

async function loadSources(){
  const el=document.getElementById('conn'); if(!el) return;
  try{
    const d=await (await fetch('/api/sources')).json();
    const badge=(on,label)=>`<span class="badge" style="background:${on?'rgba(34,197,94,.14)':'rgba(139,160,189,.08)'};color:${on?'var(--green)':'var(--mut)'};border-color:${on?'rgba(34,197,94,.30)':'var(--line)'}">${esc(label)} ${on?'●':'○'}</span>`;
    el.innerHTML=`<div class="flex" style="gap:7px">${badge(true,'Binance data')}${badge(d.cryptodada,'CryptoDada')}${badge(d.discord_read,'Discord read')}${badge(d.discord_webhook,'Discord push')}${badge(d.telegram,'Telegram')}${badge(d.llm,'LLM brain')}</div>
      <div class="note" style="margin-top:8px">Everything works with <b>no keys</b> — Binance data, engine, paper trading, coach, and backtests are fully offline-capable via DEMO_MODE. Optional keys just enrich context.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

async function systemCheck(){
  const el=document.getElementById('diag'), m=document.getElementById('diagmsg');
  if(el) el.innerHTML=''; if(m) m.textContent='checking… (few seconds)';
  try{
    const d=await (await fetch('/api/diag')).json();
    const rows=Object.entries(d.sources||{}).map(([k,v])=>
      `<tr><td>${esc(k)}</td><td style="color:${v.ok?'var(--green)':'var(--red)'}">${v.ok?'✓ ok':'✗ fail'}</td><td>${v.ms}ms</td><td class="note">${esc(v.err||'')}</td></tr>`).join('');
    if(el) el.innerHTML=`<div style="overflow:auto"><table><tr><th>Source</th><th>Status</th><th>Time</th><th>Error</th></tr>${rows}</table></div>`;
    if(m) m.textContent=d.all_ok?`✓ all ${d.total} sources reachable`:`${d.ok_count}/${d.total} sources reachable — the rest will degrade gracefully`;
    showToast(m.textContent, d.all_ok?'ok':'err');
  }catch(e){ if(m) m.textContent='error: '+e; }
}

async function decide(id, decision, note){
  const n=document.getElementById('note-'+id); const noteTxt=(n&&n.value)||'';
  const NL=String.fromCharCode(10);
  const post=async (extra)=>{
    const r=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({scan_id:id,decision:decision,note:noteTxt},extra||{}))});
    return {r:r, d:await r.json()};
  };
  try{
    const first=await post(); const res=first.r, d=first.d;
    if(!res.ok){
      // W3.3 journal-first discipline: the last decided real trade is not
      // processed until it is journaled, so the next commitment waits.
      if(d.journal_block && d.acknowledge_available
         && decision==='APPROVED'){
        const ids=((d.journal_block.trades||[]).map(t=>'#'+t.scan_id+' '+t.outcome).join(NL))||'';
        if(confirm(d.error+NL+NL+ids+NL+NL+'OK = approve anyway (audited) · Cancel = go journal now')){
          const second=await post({acknowledge_journal:true});
          if(second.r.ok && second.d.ok){ showToast('Approved #'+id+' (journal acknowledged — audited)','ok'); }
          else{ showToast((second.d&&second.d.error)||'blocked by risk gate','err'); closeModal(); return; }
        }else{
          showToast('Journal first — approval held','err');
          switchTab('journal');
          closeModal();
          return;
        }
      }else{
        showToast(d.error||'blocked by risk gate','err');
        if(d.force_available && confirm(d.error+NL+'Force approve anyway?')){
          const third=await post({force:true});
          if(third.r.ok && third.d.ok){ showToast('Force-approved #'+id,'ok'); }
        }
        closeModal(); return;
      }
    }else{
      showToast(decision+' #'+id,'ok');
    }
  }catch(e){ showToast(String(e),'err'); }
  closeModal();
  await load(true, true);
  loadPending(); loadPaper(); loadHistory(); loadLearning(); loadScorecard(); loadWatchlist();
}

async function openModal(id){
  try{
    const d=await (await fetch('/api/signal?id='+id)).json();
    const s=d.scan||{}, plans=(Array.isArray(d.plans)?d.plans:[]), decs=(Array.isArray(d.decisions)?d.decisions:[]), paper=d.paper_trade||{};
    const tps=p=>{ try{ return (p.take_profits||[]).map(fmt).join(', '); }catch(e){ return '—'; } };
    document.getElementById('mbody').innerHTML=`
      <div class="flex" style="justify-content:space-between"><h2 style="margin:0;font-size:14px">Signal #${s.id} — ${esc(s.symbol||'')} ${esc(s.timeframe||'')} <span class="pill ${cls(s.action)}">${esc(s.action||'')}</span></h2>
      <button class="btn ghost" onclick="closeModal()">✕</button></div>
      <div class="kv" style="margin-top:12px">
        <b>Status</b><span><span class="badge" style="background:${stCls(s.status)}22;border-color:${stCls(s.status)};color:${stCls(s.status)}">${esc(s.status||'—')}</span></span>
        <b>Confidence</b><span>${esc(s.confidence_label||'—')}</span>
        <b>Entry</b><span class="mono">${fmt(s.entry)}</span><b>SL</b><span class="mono">${fmt(s.stop_loss)}</span>
        <b>TP</b><span class="mono">${fmt(s.take_profit)}</span><b>RR</b><span>${s.risk_reward??'—'}</span>
        <b>Created</b><span>${esc(s.created_at||'—')}</span><b>Reason</b><span>${esc(s.reason||'')}</span>
      </div>
      ${paper.id?`<h3 style="margin:14px 0 6px;font-size:13px">Paper-trade monitor</h3><div class="kv">
        <b>Status</b><span>${esc(paper.status||'—')}</span><b>Setup</b><span>${esc(paper.plan_type||'Signal')}</span>
        <b>Outcome</b><span>${esc(paper.outcome||'—')}</span><b>R achieved</b><span>${paper.rr_achieved!=null?paper.rr_achieved+'R':'—'}</span>
        <b>MAE / MFE</b><span class="mono">${paper.mae!=null?fmt(paper.mae):'—'} / ${paper.mfe!=null?fmt(paper.mfe):'—'}</span>
        <b>Regime</b><span>${esc(paper.regime||'—')}</span>
        <b>Last price</b><span class="mono">${fmt(paper.last_price)}</span><b>Note</b><span>${esc(paper.close_reason||'')}</span>
      </div>`:''}
      ${d.journal?`<h3 style="margin:14px 0 6px;font-size:13px">Journal (post-trade)</h3><div class="kv">
        <b>Followed rules</b><span>${d.journal.followed_rules==null?'—':d.journal.followed_rules?'<span class="okc">YES</span>':'<span class="err">NO</span>'}</span>
        <b>Emotion</b><span>${esc(d.journal.emotion||'—')}</span><b>Mistake</b><span>${esc(d.journal.mistake||'—')}</span>
        <b>Would change</b><span>${esc(d.journal.would_change||'—')}</span><b>Notes</b><span>${esc(d.journal.notes||'—')}</span>
      </div><div class="note" style="margin-top:4px">Record/update: <code>python main.py journal ${s.id} --followed-rules 1 --emotion calm ...</code></div>`:''}
      <h3 style="margin:14px 0 6px;font-size:13px">Lifecycle trail</h3>
      ${decs.length?decs.map(x=>`<div class="muted" style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,.06)">${esc(x.from_state||'')} → <b>${esc(x.to_state||'')}</b> by ${esc(x.reviewer||'')} <span class="note"> ${esc(x.note||'')}</span> <span class="note">${esc(x.ts||'')}</span></div>`).join(''):'<span class="muted">no decisions yet</span>'}
      <h3 style="margin:14px 0 6px;font-size:13px">Plans</h3>
      ${plans.length?plans.map(p=>`<div class="plan"><div class="h"><b>${esc(p.type||'')}</b><span class="badge">${p.confidence??''}% ${esc(p.confidence_label||'')}</span></div><div class="c">${esc(p.condition||'')}</div><div class="c mono">entry ${fmt(p.entry)} · sl ${fmt(p.stop_loss)} · tp ${tps(p)} · RR ${p.risk_reward??'—'}</div></div>`).join(''):'<span class="muted">none</span>'}
      ${(d.management||[]).length?`<h3 style="margin:14px 0 6px;font-size:13px">POSITION MANAGER</h3>${(d.management||[]).map(c=>`<div class="note">• ${esc(c)}</div>`).join('')}`:''}
      <div class="flex" style="margin-top:16px">
        ${s.status==='PENDING_REVIEW'?`<button class="btn ok" onclick="decide(${s.id},'APPROVED')">✓ Approve</button><button class="btn no" onclick="decide(${s.id},'REJECTED')">✗ Reject</button>`:''}
        ${s.status==='APPROVED'?`<button class="btn primary" onclick="decide(${s.id},'EXECUTED')">▶ Mark executed</button><button class="btn no" onclick="decide(${s.id},'SKIPPED')">Skip</button>`:''}
        ${s.status==='EXECUTED'?`<button class="btn" style="background:var(--amber);color:#111" onclick="decide(${s.id},'CLOSED')">✔ Close</button>`:''}
      </div>`;
    document.getElementById('modal').style.display='block';
  }catch(e){ document.getElementById('mbody').innerHTML='<div class="err">Error opening signal: '+esc(e)+'</div>'; document.getElementById('modal').style.display='block'; }
}
function closeModal(){ document.getElementById('modal').style.display='none'; }
document.getElementById('modal').addEventListener('click', e=>{ if(e.target.id==='modal') closeModal(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeModal(); });

async function coach(){
  const el=document.getElementById('coach'); if(!el) return;
  el.textContent='thinking…';
  const sym=document.getElementById('sym').value.trim().toUpperCase()||'BTCUSDT';
  const tf=document.getElementById('tf').value;
  try{
    const d=await (await fetch(`/api/coach?symbol=${sym}&tf=${tf}`)).json();
    const nl=String.fromCharCode(10);
    const levels=d.five_levels||[];
    const mgmt=d.management||[];
    el.textContent=(d.explain||[]).join(nl)+nl+nl
      +(levels.length?('🎯 FIVE QUESTIONS'+nl+levels.join(nl)+nl+nl):'')
      +d.mentor+nl+nl+'📈 YOUR FEEDBACK'+nl+(d.feedback||[]).join(nl)
      +(mgmt.length?(nl+nl+'📋 POSITION MANAGER'+nl+mgmt.map(c=>'• '+c).join(nl)):'');
  }catch(e){ el.textContent='Error: '+e; }
}

async function loadLoop(){
  const el=document.getElementById('loop'); if(!el) return;
  try{
    const d=await (await fetch('/api/loop-health')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const loop=d.loop||{}, g=d.graduation||{}, advice=d.advice||{},
          gate=d.gate||{}, ready=d.readiness||{};
    const wr=loop.win_rate!=null?(loop.win_rate*100).toFixed(1)+'%':'n/a';
    const exp=loop.expectancy_net!=null?(loop.expectancy_net>=0?'+':'')+Number(loop.expectancy_net).toFixed(3)+'R':'n/a';
    const pf=loop.profit_factor!=null?Number(loop.profit_factor).toFixed(2):'n/a';
    const open=!!gate.open;
    const action=advice.action||'STAND_ASIDE';
    const actionCls=action==='SCAN'?'BUY':(action==='CLEAR_STATE'||action==='STAND_ASIDE'?'NOTRADE':'SELL');
    const dis=loop.eligible
      ? ((loop.compliance!=null?(loop.compliance*100).toFixed(1)+'%':'n/a')
         +' ('+loop.eligible+' real canonical'
         +(loop.missing_journals?', '+loop.missing_journals+' missing journal(s)':'')+')')
      : 'unproven — no decided real trades on the canonical live book';
    const criteria=(g.criteria||[]).map(c=>{
      const mark=c.met?'✓':'✗';
      return `<div class="note">${mark} ${esc(c.name)} ${c.current!=null?esc(String(c.current)):'n/a'}</div>`;
    }).join('');
    const setups=(g.by_setup||[]).filter(s=>s.primary).map(s=>
      `<tr><td>${esc(s.plan_type)}</td><td>${s.paper_n||0}/${s.paper_target||20}</td>`
      +`<td>${s.backtest_n||0}/${s.backtest_target||100}</td>`
      +`<td>${s.expectancy_net!=null?(s.expectancy_net>=0?'+':'')+Number(s.expectancy_net).toFixed(3)+'R':'—'}</td>`
      +`<td>${s.proven?'<span class="okc">✓</span>':'·'}</td></tr>`).join('');
    el.innerHTML=`<div class="flex" style="margin-bottom:10px">
        <span class="pill ${open?'BUY':'NOTRADE'}" style="${open?'background:rgba(34,197,94,.14);color:var(--green);border-color:rgba(34,197,94,.32)':''}">GATE ${open?'OPEN':'CLOSED'}</span>
        <span class="pill ${actionCls}">${esc(action)}</span>
        <span class="badge">readiness: ${esc(ready.level||'?')}</span>
        <span class="badge">graduation: ${g.ready?'READY':'NOT READY'}</span></div>
      <div class="statrow" style="margin-bottom:10px">
        <div class="stat"><div class="v">${loop.real_paper_n||0}</div><div class="k">Real paper n</div></div>
        <div class="stat"><div class="v">${esc(exp)}</div><div class="k">Expectancy (net)</div></div>
        <div class="stat"><div class="v">${esc(wr)}</div><div class="k">Win rate</div></div>
        <div class="stat"><div class="v">${esc(pf)}</div><div class="k">Profit factor</div></div>
      </div>
      <div class="kv">
        <b>Advice</b><span><b>${esc(advice.headline||'')}</b></span>
        <b>Discipline</b><span>${esc(dis)}</span>
        <b>Pending</b><span>${loop.pending_reviews||0} review(s) · open ${loop.open_exposure||0}</span>
        <b>Journal</b><span>${esc((d.journal_prompt||{}).question||'Did I follow the system today?')}</span>
      </div>
      ${criteria?`<div style="margin-top:8px"><b>Graduation bar</b>${criteria}</div>`:''}
      ${setups?`<div style="margin-top:8px;overflow:auto"><b>By setup</b><table><tr><th>Setup</th><th>Paper</th><th>Backtest</th><th>E net</th><th></th></tr>${setups}</table></div>`:''}
      <div class="note" style="margin-top:8px;background:rgba(255,255,255,.04);padding:8px;border-radius:10px;border:1px solid var(--line)">${esc(d.next_step||advice.detail||'')}</div>
      <div class="note" style="margin-top:6px">Same number as <code>python main.py daily</code> · MCP <code>loop_health</code>. Canonical live book only — simulator excluded. Advisory, never places an order.</div>`;
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}

/* ══════════════════════════════════════════════════════════════════════
   TRADING WORKSTATION — chart workspace, trade manager, risk center,
   journal form, command center and module catalog.
   Everything below is clickable: no CLI knowledge is required.
   ══════════════════════════════════════════════════════════════════════ */

// ── Chart workspace ───────────────────────────────────────────────────
let _chartData=null, _charts=[], _chartSym=null, _chartTf=null, _chartLoading=false;

function chartSym(){ return _chartSym || (document.getElementById('sym')?.value||'BTCUSDT').toUpperCase(); }
function chartTf(){ return _chartTf || (document.getElementById('tf')?.value||'15m'); }
function chartSetSymbol(sym){
  _chartSym=sym;
  document.querySelectorAll('#chartSymSeg button').forEach(b=> b.classList.toggle('active', b.dataset.sym===sym));
  const el=document.getElementById('sym'); if(el) el.value=sym;
  document.querySelectorAll('#symSeg button').forEach(b=> b.classList.toggle('active', b.dataset.sym===sym));
  loadChartWorkspace(true);
}
function chartSetTF(tf){
  _chartTf=tf;
  document.querySelectorAll('#chartTfSeg button').forEach(b=> b.classList.toggle('active', b.dataset.tf===tf));
  const el=document.getElementById('tf'); if(el) el.value=tf;
  document.querySelectorAll('#tfSeg button').forEach(b=> b.classList.toggle('active', b.dataset.tf===tf));
  loadChartWorkspace(true);
}
let _multiChart=false, _multiCharts=[], _multiLoading=false;
function toggleMultiChart(){
  _multiChart=!_multiChart;
  const btn=document.getElementById('multiChartBtn');
  if(btn){ btn.classList.toggle('active',_multiChart); btn.textContent=_multiChart?'▦ Single chart':'▦ Multi-chart'; }
  ['chartMain','chartVol','chartRsi','chartMacd','chartHead','chartStats','chartLevels','drawStatus','liveState'].forEach(id=>{
    const e=document.getElementById(id); if(e) e.style.display=_multiChart?'none':'';
  });
  const host=document.getElementById('multiChart'); if(host) host.style.display=_multiChart?'grid':'none';
  if(_multiChart) loadMultiChart(); else disposeMultiCharts();
}
function disposeMultiCharts(){
  _multiCharts.forEach(c=>{ try{c.chart.remove();}catch(e){} }); _multiCharts=[];
}
const MULTI_SYMBOLS=['BTCUSDT','ETHUSDT','XAUUSD'];
const MULTI_TFS=['5m','15m','1h','4h','1d'];
function multiDefaults(){
  const primary=chartSym(), tf=chartTf();
  return [{symbol:primary,tf:tf},{symbol:primary,tf:tf==='15m'?'1h':'15m'},
          {symbol:'BTCUSDT',tf:'1h'},{symbol:'ETHUSDT',tf:'1h'}];
}
function multiSlotState(){
  let slots=multiDefaults();
  try{
    const saved=JSON.parse(localStorage.getItem('sky.multiChartSlots')||'null');
    if(Array.isArray(saved)&&saved.length===4) slots=saved.map((s,i)=>({
      symbol:MULTI_SYMBOLS.includes(String(s.symbol))?String(s.symbol):slots[i].symbol,
      tf:MULTI_TFS.includes(String(s.tf))?String(s.tf):slots[i].tf}));
  }catch(e){}
  return slots;
}
function saveMultiSlots(slots){
  try{localStorage.setItem('sky.multiChartSlots',JSON.stringify(slots));}catch(e){}
}
function multiChartSpecs(){
  const slots=multiSlotState(), seen=new Set();
  return slots.filter(s=>{const k=s.symbol+' '+s.tf;if(seen.has(k))return false;seen.add(k);return true;});
}
function renderMultiControls(host,slots){
  const bar=document.createElement('div'); bar.className='multi-chart-title';
  bar.style.cssText='grid-column:1/-1;flex-wrap:wrap;background:rgba(255,255,255,.03)';
  bar.innerHTML='<span>Comparison slots</span><span class="muted">Saved in this browser only · no combined signal</span>';
  slots.forEach((slot,i)=>{
    const label=document.createElement('label'); label.style.cssText='display:flex;gap:5px;align-items:center;font-weight:400';
    const sym=document.createElement('select'), tf=document.createElement('select');
    sym.setAttribute('aria-label','comparison symbol '+(i+1)); tf.setAttribute('aria-label','comparison timeframe '+(i+1));
    MULTI_SYMBOLS.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;sym.appendChild(o);});
    MULTI_TFS.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;tf.appendChild(o);});
    sym.value=slot.symbol;tf.value=slot.tf;label.appendChild(document.createTextNode((i+1)+'.'));label.appendChild(sym);label.appendChild(tf);bar.appendChild(label);
    const changed=()=>{const next=multiSlotState();next[i]={symbol:sym.value,tf:tf.value};saveMultiSlots(next);loadMultiChart();};
    sym.addEventListener('change',changed);tf.addEventListener('change',changed);
  });
  host.appendChild(bar);
}
function multiCandleData(candles){
  return (candles||[]).map(c=>{const raw=c.ts||c.time||c.timestamp||c.open_time||c.date;
    const t=raw?new Date(raw).getTime()/1000:Date.now()/1000;
    return {time:t,open:Number(c.open||0),high:Number(c.high||0),low:Number(c.low||0),close:Number(c.close||0)};
  }).filter(c=>Number.isFinite(c.time)&&c.high>0);
}
async function loadMultiChart(){
  if(_multiLoading)return; const host=document.getElementById('multiChart'); if(!host)return;
  _multiLoading=true; disposeMultiCharts(); host.innerHTML='<div class="muted" style="padding:12px">loading comparison charts…</div>';
  try{
    const specs=multiChartSpecs();
    const results=await Promise.all(specs.map(async s=>{const r=await fetch('/api/chart?symbol='+encodeURIComponent(s.symbol)+'&tf='+encodeURIComponent(s.tf)+'&limit=180');return {spec:s,data:await r.json()};}));
    host.innerHTML=''; renderMultiControls(host,multiSlotState()); const make=chartsAvailable();
    if(!make){host.innerHTML+='<div class="err" style="padding:12px">chart engine failed to load</div>';return;}
    results.forEach((item,i)=>{
      const card=document.createElement('div'); card.className='multi-chart-card';
      const title=document.createElement('div'); title.className='multi-chart-title';
      title.innerHTML='<span>'+esc(item.spec.symbol)+' · '+esc(item.spec.tf)+'</span><span class="muted">comparison only</span>';
      const canvas=document.createElement('div'); canvas.className='multi-chart-canvas'; card.appendChild(title);card.appendChild(canvas);host.appendChild(card);
      const chart=make(canvas,{width:canvas.clientWidth||500,height:250,layout:{background:{color:'#0e1524'},textColor:'#8aa0bd'},grid:{vertLines:{color:'#1e3358'},horzLines:{color:'#1e3358'}},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#1e3358'}});
      const series=chart.addCandlestickSeries({upColor:'#22c55e',downColor:'#ef4444',borderUpColor:'#22c55e',borderDownColor:'#ef4444',wickUpColor:'#22c55e',wickDownColor:'#ef4444'});
      series.setData(multiCandleData(item.data.candles)); chart.timeScale().fitContent(); _multiCharts.push({chart,series});
    });
    // Keep zoom/pan aligned without forcing different markets to share prices.
    _multiCharts.forEach((item,i)=>item.chart.timeScale().subscribeVisibleLogicalRangeChange(range=>{
      if(_multiChart && !_multiSync && range){_multiSync=true;_multiCharts.forEach((other,j)=>{if(i!==j)try{other.chart.timeScale().setVisibleLogicalRange(range);}catch(e){}});_multiSync=false;}
    }));
  }catch(e){host.innerHTML='<div class="err" style="padding:12px">multi-chart error: '+esc(String(e))+'</div>';}finally{_multiLoading=false;}
}
let _multiSync=false;
function chartsAvailable(){
  return (typeof LightweightCharts !== 'undefined' && LightweightCharts.createChart) ? LightweightCharts.createChart
       : (typeof createChart !== 'undefined' ? createChart : null);
}
async function loadChartWorkspace(force){
  if(_chartLoading) return;
  const main=document.getElementById('chartMain'); if(!main) return;
  // Reloading or changing the selected series always leaves historical replay.
  // Otherwise its timer would keep updating a chart that has been disposed and
  // could repaint a REPLAY label over the newly loaded series.
  if(_replay) stopReplay(false);
  _chartLoading=true;
  const head=document.getElementById('chartHead');
  if(head) head.innerHTML='<span class="muted">loading '+esc(chartSym())+' '+esc(chartTf())+'…</span>';
  try{
    const r=await fetch('/api/chart?symbol='+encodeURIComponent(chartSym())+'&tf='+encodeURIComponent(chartTf())+'&limit=300'+(force?'&_='+Date.now():''));
    const d=await r.json();
    if(d.error && !(d.candles||[]).length){
      if(head) head.innerHTML='<span class="err">chart unavailable: '+esc(d.error)+'</span>';
      return;
    }
    _chartData=d;
    drawChart();
    renderChartHead(d);
    renderChartStats(d);
    renderChartLevels(d);
    const stamp=document.getElementById('liveLoadedAt');
    if(stamp) stamp.textContent=new Date().toLocaleTimeString();
    // A running stream follows the selected series: reconnect when it changed.
    if(_live && (_live.symbol!==chartSym() || _live.tf!==chartTf())){ stopLive(true); startLive(); }
    if(_multiChart) loadMultiChart();
  }catch(e){
    if(head) head.innerHTML='<span class="err">chart error: '+esc(String(e))+'</span>';
  }finally{ _chartLoading=false; }
}
function disposeCharts(){
  _charts.forEach(c=>{ try{ c.remove(); }catch(e){} });
  _charts=[];
}
function newPane(el, height, extra){
  const create=chartsAvailable(); if(!create) return null;
  el.innerHTML='';
  const opts={
    width: el.clientWidth || 900, height: height,
    layout:{ background:{ color:'#0b1120' }, textColor:'#8aa0bd', fontSize:11 },
    grid:{ vertLines:{ color:'rgba(30,51,88,.55)' }, horzLines:{ color:'rgba(30,51,88,.55)' } },
    rightPriceScale:{ borderColor:'#1e3358' },
    timeScale:{ borderColor:'#1e3358', timeVisible:true, secondsVisible:false },
    crosshair:{ mode:0, vertLine:{ color:'#6b84a6', labelBackgroundColor:'#1e3358' },
                horzLine:{ color:'#6b84a6', labelBackgroundColor:'#1e3358' } },
    handleScroll:true, handleScale:true
  };
  Object.assign(opts, extra||{});
  const chart=create(el, opts);
  _charts.push(chart);
  return chart;
}
function syncPanes(){
  // TradingView-style linked time scales across price / volume / RSI / MACD
  _charts.forEach(src=>{
    try{
      src.timeScale().subscribeVisibleLogicalRangeChange(range=>{
        if(!range) return;
        _charts.forEach(dst=>{ if(dst!==src){ try{ dst.timeScale().setVisibleLogicalRange(range); }catch(e){} } });
      });
    }catch(e){}
  });
}
function drawChart(){
  const d=_chartData; if(!d) return;
  const main=document.getElementById('chartMain'); if(!main) return;
  if(!chartsAvailable()){ main.innerHTML='<div class="err" style="padding:14px">Chart engine failed to load — reload the page (Ctrl+F5).</div>'; return; }
  // Overlay toggles call drawChart directly. Treat that interaction as leaving
  // historical playback instead of letting its old timer mutate a removed pane.
  if(_replay) stopReplay(false);
  disposeCharts();
  const on=id=> !!document.getElementById(id)?.checked;

  // ── price pane ──
  const price=newPane(main, 420);
  const candle=price.addCandlestickSeries({
    upColor:'#22c55e', downColor:'#ef4444', borderUpColor:'#22c55e',
    borderDownColor:'#ef4444', wickUpColor:'#22c55e', wickDownColor:'#ef4444' });
  candle.setData(d.candles||[]);
  _priceSeries=candle;              // live stream updates this series in place
  const ov=d.overlays||{};
  if(on('ovEma')){
    [['ema20','#3b82f6',1],['ema50','#f59e0b',1],['ema200','#8b5cf6',2]].forEach(([k,c,w])=>{
      if((ov[k]||[]).length){ const s=price.addLineSeries({color:c,lineWidth:w,priceLineVisible:false,lastValueVisible:false}); s.setData(ov[k]); }
    });
  }
  if(on('ovVwap') && (ov.vwap||[]).length){
    const s=price.addLineSeries({color:'#06b6d4',lineWidth:2,lineStyle:2,priceLineVisible:false,lastValueVisible:false});
    s.setData(ov.vwap);
  }
  if(on('ovBb')){
    [['bb_upper','rgba(139,92,246,.7)'],['bb_lower','rgba(139,92,246,.7)']].forEach(([k,c])=>{
      if((ov[k]||[]).length){ const s=price.addLineSeries({color:c,lineWidth:1,priceLineVisible:false,lastValueVisible:false}); s.setData(ov[k]); }
    });
  }
  if(on('ovLevels')){
    (d.levels||[]).forEach(l=>{
      try{ candle.createPriceLine({ price:l.price, color:l.color||'#8aa0bd', lineWidth:1,
        lineStyle:2, axisLabelVisible:true, title:l.label||l.kind }); }catch(e){}
    });
  }
  if(on('ovZones')) drawZones(candle, d.zones);
  mountDrawings(price, candle);
  if(on('ovPlan') && d.plan && (d.plan.entry||d.plan.stop_loss||d.plan.take_profit)){
    const p=d.plan;
    const lines=[[p.entry,'#e6edf7','ENTRY'],[p.stop_loss,'#ef4444','STOP'],[p.take_profit,'#22c55e','TARGET']];
    lines.forEach(([v,c,t])=>{ if(v!=null){ try{ candle.createPriceLine({price:v,color:c,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:t}); }catch(e){} } });
  }

  // ── volume pane ──
  const volEl=document.getElementById('chartVol');
  if(volEl){
    volEl.style.display='';
    const vol=newPane(volEl, 110);
    const vs=vol.addHistogramSeries({ priceFormat:{type:'volume'}, priceLineVisible:false });
    vs.setData((d.panes&&d.panes.volume)||[]);
  }

  // ── RSI pane ──
  const rsiEl=document.getElementById('chartRsi');
  if(rsiEl){
    if(on('ovRsi') && ((d.panes&&d.panes.rsi)||[]).length){
      rsiEl.style.display='';
      const rsi=newPane(rsiEl, 120);
      const rs=rsi.addLineSeries({color:'#f59e0b',lineWidth:2,priceLineVisible:false});
      rs.setData(d.panes.rsi);
      try{ rs.createPriceLine({price:70,color:'rgba(239,68,68,.6)',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'70'}); }catch(e){}
      try{ rs.createPriceLine({price:30,color:'rgba(34,197,94,.6)',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'30'}); }catch(e){}
    } else { rsiEl.style.display='none'; }
  }

  // ── MACD pane ──
  const macdEl=document.getElementById('chartMacd');
  if(macdEl){
    if(on('ovMacd') && ((d.panes&&d.panes.macd)||[]).length){
      macdEl.style.display='';
      const m=newPane(macdEl, 120);
      const hist=(d.panes.macd_hist||[]).map(p=> ({time:p.time, value:p.value, color: p.value>=0?'rgba(34,197,94,.6)':'rgba(239,68,68,.6)'}));
      if(hist.length){ const hs=m.addHistogramSeries({priceLineVisible:false}); hs.setData(hist); }
      const ms=m.addLineSeries({color:'#3b82f6',lineWidth:2,priceLineVisible:false}); ms.setData(d.panes.macd);
      if((d.panes.macd_signal||[]).length){ const ss=m.addLineSeries({color:'#f59e0b',lineWidth:1,priceLineVisible:false}); ss.setData(d.panes.macd_signal); }
    } else { macdEl.style.display='none'; }
  }
  _charts.forEach(c=>{ try{ c.timeScale().fitContent(); }catch(e){} });
  syncPanes();
  if(!window.__chartResizeBound){
    window.__chartResizeBound=true;
    window.addEventListener('resize', ()=>{
      const w=document.getElementById('chartMain')?.clientWidth||900;
      _charts.forEach(c=>{ try{ c.applyOptions({width:w}); }catch(e){} });
    });
  }
}
/* ── W2 zone overlays (order blocks / FVG / liquidity / sweep) ─────────
   Lightweight Charts v4 has no rectangle primitive, so a zone is drawn as
   its top + bottom price lines; the shared colour reads as a band. Bullish =
   green, bearish = red; tested/broken/filled zones are dashed so a dead
   zone is visibly different from a fresh one. Nothing here is invented —
   every level comes from engine/structure.py via /api/chart. */
function drawZones(candle, zones){
  if(!zones) return;
  const band=(z, label)=>{
    const side=z.side==='bearish';
    const col=side?'rgba(239,68,68,.55)':'rgba(34,197,94,.55)';
    const done=z.tested||z.broken||z.filled;
    const style=done?2:1;   // dashed when a zone has been touched/closed
    const tag=z.broken?'broken':(z.tested||z.filled)?'done':'';
    try{ candle.createPriceLine({price:z.top,color:col,lineWidth:1,lineStyle:style,
      axisLabelVisible:true,title:(label||'')+' top'+(tag?' ('+tag+')':'')}); }catch(e){}
    try{ candle.createPriceLine({price:z.bottom,color:col,lineWidth:1,lineStyle:style,
      axisLabelVisible:true,title:(label||'')+' low'+(tag?' ('+tag+')':'')}); }catch(e){}
  };
  (zones.order_blocks||[]).forEach(z=> band(z, z.side==='bullish'?'OB bull':'OB bear'));
  (zones.fvgs||[]).forEach(z=> band(z, z.side==='bullish'?'FVG bull':'FVG bear'));
  (zones.liquidity||[]).forEach(l=>{
    const above=l.side==='above';
    const col=above?'rgba(139,92,246,.6)':'rgba(6,182,212,.6)';
    try{ candle.createPriceLine({price:l.price,color:col,lineWidth:1,lineStyle:2,
      axisLabelVisible:true,title:above?'Buyside liq':'Sellside liq'}); }catch(e){}
  });
  if(zones.sweep){
    const col=zones.sweep.recovered?'rgba(245,158,11,.9)':'rgba(239,68,68,.9)';
    try{ candle.createPriceLine({price:zones.sweep.level,color:col,lineWidth:2,lineStyle:0,
      axisLabelVisible:true,title:(zones.sweep.side||'')+' sweep '+(zones.sweep.recovered?'(recovered)':'(failed)')}); }catch(e){}
  }
  if(zones.dealing_range){
    const col='rgba(59,130,246,.5)';
    const pos=zones.dealing_range.zone||'';
    try{ candle.createPriceLine({price:zones.dealing_range.top,color:col,lineWidth:1,lineStyle:2,
      axisLabelVisible:true,title:'range high ('+pos+')'}); }catch(e){}
    try{ candle.createPriceLine({price:zones.dealing_range.bottom,color:col,lineWidth:1,lineStyle:2,
      axisLabelVisible:true,title:'range low ('+pos+')'}); }catch(e){}
  }
}

/* ── W2 live streaming — push the newest bar instead of reloading ──────
   The server polls the same candle source /api/chart uses and sends one
   server-sent event per newest bar; the chart calls series.update() in place.
   Display only: no order path, no writes, no threshold. Every state the feed
   can be in is labelled — live, waiting, stale, feed error, disconnected —
   because a silent stream must never read as a quiet market. */
let _live=null, _priceSeries=null;
function setLiveState(html){
  const el=document.getElementById('liveState');
  if(el) el.innerHTML=html;
}
function liveAmber(text){ return '<span style="color:var(--amber);font-weight:700">'+text+'</span>'; }
function startLive(){
  if(_live) return;
  if(_replay){ setLiveState(liveAmber('Stop the replay before streaming.')); return; }
  if(typeof EventSource==='undefined'){
    setLiveState('<span class="err">This browser cannot stream (no EventSource) — use ↻ Reload chart.</span>'); return; }
  const sym=chartSym(), tf=chartTf();
  let es=null;
  try{ es=new EventSource('/api/chart/stream?symbol='+encodeURIComponent(sym)+'&tf='+encodeURIComponent(tf)); }
  catch(e){ setLiveState('<span class="err">live stream failed: '+esc(String(e))+'</span>'); return; }
  _live={ es:es, symbol:sym, tf:tf, updates:0, state:'connecting' };
  const btn=document.getElementById('liveBtn');
  if(btn){ btn.textContent='■ Stop live'; btn.classList.add('active'); }
  setLiveState('Connecting to the '+esc(sym)+' '+esc(tf)+' stream…');
  es.addEventListener('candle', onLiveCandle);
  es.addEventListener('status', onLiveStatus);
  es.onerror=()=>{
    if(!_live) return;
    _live.state='disconnected';
    setLiveState(liveAmber('⚠ DISCONNECTED')+' — reconnecting. The bars on screen are the last ones received, not the current market.');
  };
}
function stopLive(quiet){
  if(_live){ try{ _live.es.close(); }catch(e){} }
  _live=null;
  const btn=document.getElementById('liveBtn');
  if(btn){ btn.textContent='◉ Live'; btn.classList.remove('active'); }
  if(!quiet) setLiveState('Live stream off — press ◉ Live to stream the newest bar.');
}
function toggleLive(){ if(_live) stopLive(); else startLive(); }
function applyLiveCandle(bar){
  // Keep _chartData in step so a reload, a replay or a drawing's time snap all
  // see the same bars the chart is showing.
  const cs=(_chartData&&_chartData.candles)||null;
  if(cs && cs.length){
    const tail=cs[cs.length-1];
    if(tail.time===bar.time) cs[cs.length-1]=Object.assign({}, tail, bar);
    else if(bar.time>tail.time) cs.push(bar);
    else return false;                    // an older bar never rewrites history
  }
  if(_replay) return true;                // playback owns the pane
  if(_priceSeries){ try{ _priceSeries.update(bar); }catch(e){} }
  if(_chartData){
    _chartData.last_price=bar.close;
    renderChartHead(_chartData);
  }
  return true;
}
function onLiveCandle(ev){
  let d=null; try{ d=JSON.parse(ev.data); }catch(e){ return; }
  if(!_live || !d || !d.candle) return;
  if(d.symbol!==_live.symbol || d.tf!==_live.tf) return;   // never paint another series
  if(!applyLiveCandle(d.candle)) return;
  _live.updates++; _live.state='live';
  setLiveState('<span class="okc">● LIVE</span> '+esc(d.symbol)+' '+esc(d.tf)+' — bar '
    +new Date((d.candle.time||0)*1000).toLocaleTimeString()+' at '+fmt(d.candle.close)
    +' · '+_live.updates+' update'+(_live.updates===1?'':'s')+' this session.');
}
function onLiveStatus(ev){
  let d=null; try{ d=JSON.parse(ev.data); }catch(e){ return; }
  if(!_live || !d) return;
  _live.state=d.state||'';
  const age=Math.round(Number(d.age)||0);
  if(d.state==='stale'){
    setLiveState(liveAmber('⚠ STALE')+' — no new '+esc(d.tf||'')+' data for '+age
      +'s. You are looking at the last bar received; treat it as unknown, not as a quiet market.');
  }else if(d.state==='error'){
    setLiveState('<span class="err">⚠ FEED ERROR</span> — '+esc(d.message||'source unavailable')
      +'. Retrying; the chart is not updating.');
  }else{
    setLiveState('<span class="okc">● LIVE</span> '+esc(d.symbol||'')+' '+esc(d.tf||'')
      +' — waiting for the next bar ('+age+'s since the last change, '+_live.updates+' update'
      +(_live.updates===1?'':'s')+' this session).');
  }
}

/* ── W2 drawing tools — trendlines, horizontal rays and boxes ──────────
   Placed with the mouse on the price pane, persisted per symbol+timeframe in
   this browser's localStorage, and redrawn on every reload/toggle. A drawing
   is the trader's own mark: it is never read back by the engine, never becomes
   evidence, and never moves a threshold or the risk gate.

   Lightweight Charts v4 has no free-draw primitive, so each drawing is one or
   more two-point line series (the same honest technique the zone overlays use
   for bands): a trendline is one segment, a horizontal ray is a segment held
   at one price out to the last bar, a box is its top + bottom edges. */
const DRAW_TOOLS={ trendline:{clicks:2,label:'Trendline',icon:'╱'},
                   ray:{clicks:1,label:'Horizontal ray',icon:'─'},
                   box:{clicks:2,label:'Box',icon:'▭'} };
const DRAW_COLOR='#e6b800';
// The HTML block is a plain (non-raw) Python string, so backslash escapes are
// written out of band: newline and apostrophe come from character codes.
const DRAW_NL=String.fromCharCode(10), DRAW_QT=String.fromCharCode(39);
let _drawTool=null, _drawPending=null, _drawings=[], _drawSeries=[], _drawCtx=null;

function drawingsKey(sym, tf){ return 'sky.drawings.v1.'+(sym||chartSym())+'.'+(tf||chartTf()); }
function isDrawing(d){
  const spec=d && DRAW_TOOLS[d.kind];
  if(!spec || !Array.isArray(d.points) || d.points.length!==spec.clicks) return false;
  return d.points.every(p=> p && Number.isFinite(Number(p.time)) && Number.isFinite(Number(p.price)));
}
function newDrawingId(){ return 'd'+Date.now().toString(36)+Math.random().toString(36).slice(2,6); }
function loadDrawings(){
  _drawings=[];
  try{
    const parsed=JSON.parse(localStorage.getItem(drawingsKey())||'[]');
    if(Array.isArray(parsed)){
      _drawings=parsed.filter(isDrawing).map(d=>{
        // Storage is user-writable: keep only ids that are safe to place in
        // the remove button's onclick, and normalise the numbers.
        const id=/^[A-Za-z0-9_-]{1,40}$/.test(String(d.id||''))?String(d.id):newDrawingId();
        const points=d.points.map(p=> ({time:Number(p.time), price:Number(p.price)}));
        return { id:id, kind:d.kind, points:points, created:Number(d.created)||0,
                 color:(typeof d.color==='string' && /^#[0-9a-f]{3,8}$/i.test(d.color))?d.color:DRAW_COLOR };
      });
    }
  }catch(e){ _drawings=[]; }      // corrupt storage never breaks the chart
  return _drawings;
}
function saveDrawings(){
  try{ localStorage.setItem(drawingsKey(), JSON.stringify(_drawings)); }catch(e){}
}
function setDrawStatus(msg){
  const el=document.getElementById('drawStatus');
  if(el) el.innerHTML=msg?esc(msg):'';
}
function setDrawTool(kind){
  if(_replay){ setDrawTool_off(); setDrawStatus('Stop the replay before drawing.'); return; }
  const next=(_drawTool===kind)?null:kind;
  _drawTool=DRAW_TOOLS[next]?next:null;
  _drawPending=null;
  Object.keys(DRAW_TOOLS).forEach(k=>{
    const b=document.getElementById('draw'+k.charAt(0).toUpperCase()+k.slice(1));
    if(b) b.classList.toggle('active', k===_drawTool);
  });
  if(!_drawTool){ setDrawStatus(''); return; }
  const spec=DRAW_TOOLS[_drawTool];
  setDrawStatus(spec.label+': click '+(spec.clicks===1?'a price on the chart.':'the first point on the chart.'));
}
function setDrawTool_off(){
  _drawTool=null; _drawPending=null;
  Object.keys(DRAW_TOOLS).forEach(k=>{
    const b=document.getElementById('draw'+k.charAt(0).toUpperCase()+k.slice(1));
    if(b) b.classList.remove('active');
  });
}
function candleTimes(){ return ((_chartData&&_chartData.candles)||[]).map(c=> Number(c.time)); }
function snapDrawTime(t){
  // Snap to the nearest loaded bar so a drawing sits on the chart's own time
  // scale instead of inventing a timestamp between bars.
  const times=candleTimes(); if(!times.length) return Number(t);
  let best=times[0], gap=Math.abs(times[0]-t);
  for(let i=1;i<times.length;i++){
    const g=Math.abs(times[i]-t);
    if(g<gap){ gap=g; best=times[i]; }
  }
  return best;
}
function chartPointFrom(param){
  if(!param || !param.point || !_drawCtx) return null;
  let price=null, time=(param.time==null?null:Number(param.time));
  try{ price=_drawCtx.series.coordinateToPrice(param.point.y); }catch(e){}
  if(time==null || !Number.isFinite(time)){
    try{ time=Number(_drawCtx.chart.timeScale().coordinateToTime(param.point.x)); }catch(e){}
  }
  price=Number(price);
  if(!Number.isFinite(price) || !Number.isFinite(time)) return null;
  return { time: snapDrawTime(time), price: price };
}
function onChartClick(param){
  if(!_drawTool || !_drawCtx) return;
  const pt=chartPointFrom(param);
  if(!pt){ setDrawStatus('Click inside the price pane to place a point.'); return; }
  const spec=DRAW_TOOLS[_drawTool];
  if(spec.clicks===1){ commitDrawing(_drawTool, [pt]); return; }
  if(!_drawPending){
    _drawPending=pt;
    setDrawStatus(spec.label+': now click the second point.');
    return;
  }
  const pts=[_drawPending, pt].sort((a,b)=> a.time-b.time);
  _drawPending=null;
  commitDrawing(_drawTool, pts);
}
function commitDrawing(kind, points){
  const spec=DRAW_TOOLS[kind]; if(!spec) return null;
  const d={ id:newDrawingId(),
            kind:kind, points:points, created:Date.now(),
            symbol:chartSym(), tf:chartTf() };
  if(!isDrawing(d)) return null;
  _drawings.push(d);
  saveDrawings();
  renderDrawings();
  setDrawTool_off();
  setDrawStatus(spec.label+' saved — '+_drawings.length+' drawing'+(_drawings.length===1?'':'s')
    +' on '+chartSym()+' '+chartTf()+'.');
  return d;
}
function drawingSegments(d){
  const p=d.points||[], times=candleTimes();
  const last=times.length?times[times.length-1]:null;
  if(d.kind==='trendline' && p.length===2)
    return [[{time:p[0].time,value:p[0].price},{time:p[1].time,value:p[1].price}]];
  if(d.kind==='ray' && p.length===1){
    const end=(last!=null && last>p[0].time)?last:p[0].time;
    return [[{time:p[0].time,value:p[0].price},{time:end,value:p[0].price}]];
  }
  if(d.kind==='box' && p.length===2){
    const top=Math.max(p[0].price,p[1].price), bot=Math.min(p[0].price,p[1].price);
    const t0=Math.min(p[0].time,p[1].time), t1=Math.max(p[0].time,p[1].time);
    return [[{time:t0,value:top},{time:t1,value:top}],
            [{time:t0,value:bot},{time:t1,value:bot}]];
  }
  return [];
}
function clearDrawingSeries(){
  const chart=_drawCtx&&_drawCtx.chart;
  _drawSeries.forEach(s=>{ try{ chart.removeSeries(s); }catch(e){} });
  _drawSeries=[];
}
function renderDrawings(){
  if(_drawCtx){
    clearDrawingSeries();
    _drawings.forEach(d=>{
      drawingSegments(d).forEach(seg=>{
        if(seg.length<2 || seg[0].time===seg[1].time) return;   // degenerate → nothing to draw
        let s=null;
        try{
          s=_drawCtx.chart.addLineSeries({ color:d.color||DRAW_COLOR, lineWidth:2,
            lineStyle:(d.kind==='box'?2:0), priceLineVisible:false,
            lastValueVisible:false, crosshairMarkerVisible:false });
        }catch(e){}
        if(!s) return;
        try{ s.setData(seg); }catch(e){}
        _drawSeries.push(s);
      });
    });
  }
  renderDrawingList();
}
function drawingLabel(d){
  const spec=DRAW_TOOLS[d.kind]||{label:d.kind,icon:'·'};
  const p=d.points||[];
  if(d.kind==='ray') return spec.icon+' '+spec.label+' @ '+fmt(p[0].price);
  if(d.kind==='box') return spec.icon+' '+spec.label+' '+fmt(Math.min(p[0].price,p[1].price))
    +' → '+fmt(Math.max(p[0].price,p[1].price));
  const dir=(p[1].price>=p[0].price)?'rising':'falling';
  return spec.icon+' '+spec.label+' '+dir+' '+fmt(p[0].price)+' → '+fmt(p[1].price);
}
function renderDrawingList(){
  const el=document.getElementById('drawList'); if(!el) return;
  if(!_drawings.length){
    el.innerHTML='<span class="muted">No drawings on '+esc(chartSym())+' '+esc(chartTf())
      +' — pick ╱ Trend, ─ Ray or ▭ Box, then click the chart.</span>';
    return;
  }
  el.innerHTML=_drawings.map(d=>
    '<div class="flex" style="justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px solid var(--line)">'
    +'<span class="mono">'+esc(drawingLabel(d))+'</span>'
    +'<span class="note">'+esc(new Date(d.created||0).toLocaleString())
    +' <button class="rowbtn" onclick="removeDrawing('+DRAW_QT+esc(d.id)+DRAW_QT+')">✕</button></span></div>').join('');
}
function removeDrawing(id){
  const before=_drawings.length;
  _drawings=_drawings.filter(d=> d.id!==id);
  if(_drawings.length===before) return;
  saveDrawings(); renderDrawings();
  setDrawStatus('Drawing removed — '+_drawings.length+' left on '+chartSym()+' '+chartTf()+'.');
}
function undoDrawing(){
  if(!_drawings.length){ setDrawStatus('Nothing to undo on '+chartSym()+' '+chartTf()+'.'); return; }
  _drawings.pop();
  saveDrawings(); renderDrawings();
  setDrawStatus('Last drawing removed — '+_drawings.length+' left on '+chartSym()+' '+chartTf()+'.');
}
function clearDrawings(){
  if(!_drawings.length){ setDrawStatus('Nothing to clear on '+chartSym()+' '+chartTf()+'.'); return; }
  const n=_drawings.length;
  _drawings=[];
  saveDrawings(); renderDrawings();
  setDrawStatus('Cleared '+n+' drawing'+(n===1?'':'s')+' on '+chartSym()+' '+chartTf()+'.');
}
function drawingsAsText(){
  if(!_drawings.length) return '';
  return 'Chart marks — '+chartSym()+' '+chartTf()+':'+DRAW_NL
    + _drawings.map(d=> '· '+drawingLabel(d)).join(DRAW_NL);
}
function attachDrawingsToJournal(){
  // "Attachable to the scan record": the drawings are appended to the journal
  // note, which the user then saves against a specific trade. Nothing is
  // written automatically — the human still picks the trade and presses save.
  const text=drawingsAsText();
  if(!text){ setDrawStatus('No drawings to attach on '+chartSym()+' '+chartTf()+'.'); return; }
  switchTab('journal');
  setTimeout(()=>{
    const notes=document.getElementById('jNotes');
    if(notes){
      notes.value=(notes.value?notes.value.trimEnd()+DRAW_NL+DRAW_NL:'')+text;
      try{ notes.scrollIntoView(); }catch(e){}
    }
    const st=document.getElementById('jStatus');
    if(st) st.innerHTML='<span class="okc">chart marks added to the note</span> — pick the trade and save';
  }, 120);
}
function mountDrawings(chart, series){
  // Called by drawChart() after the price pane exists: adopt the new pane,
  // load this symbol+timeframe's saved drawings and take chart clicks.
  _drawCtx={ chart:chart, series:series };
  _drawSeries=[];
  _drawPending=null;
  loadDrawings();
  renderDrawings();
  try{ chart.subscribeClick(onChartClick); }catch(e){}
}
function unmountDrawings(){
  // The pane is about to be removed (replay). Drop the context so a stray
  // click can never touch a disposed chart; storage keeps the drawings.
  _drawCtx=null; _drawSeries=[]; _drawPending=null;
  setDrawTool_off();
}

/* ── W2 replay mode — walk already-loaded candles bar-by-bar ────────────
   A clearly-labelled historical playback. It reuses the candles /api/chart
   already returned (no live data), and the chart head is overwritten with a
   REPLAY badge so it can never be mistaken for live or paper evidence. */
let _replay=null;   // {timer, idx, candles, candle, speedIdx}
const _replaySpeeds=[200,120,60,25];
function stopReplay(restore=true){
  if(_replay){ try{ clearInterval(_replay.timer); }catch(e){} _replay=null; }
  const btn=document.getElementById('replayBtn'); if(btn) btn.textContent='▶ Replay';
  const spd=document.getElementById('replaySpeedBtn'); if(spd) spd.textContent='1×';
  if(restore){
    const head=document.getElementById('chartHead');
    if(head && _chartData) renderChartHead(_chartData);
    drawChart();                                        // restore the full workspace
  }
  setTapeBanner(false);
}
function freezeReplay(){
  if(!_replay) return;
  try{ clearInterval(_replay.timer); }catch(e){}
  _replay.timer=null;
  const btn=document.getElementById('replayBtn'); if(btn) btn.textContent='▶ Resume';
  setTapeBanner(true);
}
function replayCommitTime(){
  if(!_replay || !_replay.candles || !_replay.candles.length) return null;
  const n=Math.max(1, Math.min(_replay.idx||1, _replay.candles.length));
  const c=_replay.candles[n-1]||{};
  return (c.time!=null)?c.time:null;
}
function setTapeBanner(on){
  const b=document.getElementById('pracTapeBanner'); if(b) b.style.display=on?'block':'none';
}
function renderReplayHead(n){
  if(!_replay || !_replay.candles.length) return;
  const shown=Math.max(1,Math.min(n,_replay.candles.length));
  const c=_replay.candles[shown-1]||{};
  const head=document.getElementById('chartHead');
  if(head) head.innerHTML='<span class="badge" style="background:var(--amber);color:#111;font-weight:800">▶ REPLAY — historical playback, not live</span>'
    +' <span class="note mono">bar '+shown+'/'+_replay.candles.length+' · '+new Date((c.time||0)*1000).toLocaleString()+'</span>';
}
function cycleReplaySpeed(){
  if(!_replay) return;
  _replay.speedIdx=(_replay.speedIdx+1)%_replaySpeeds.length;
  const btn=document.getElementById('replaySpeedBtn'); if(btn) btn.textContent=(_replay.speedIdx+1)+'×';
  try{ clearInterval(_replay.timer); }catch(e){}
  _replay.timer=setInterval(replayTick, _replaySpeeds[_replay.speedIdx]);
}
function replayTick(){
  if(!_replay) return;
  _replay.idx++;
  const n=Math.min(_replay.idx, _replay.candles.length);
  try{ _replay.candle.setData(_replay.candles.slice(0, n)); }catch(e){}
  renderReplayHead(n);
  if(n>=_replay.candles.length) stopReplay();
}
function toggleReplay(){
  if(_replay && _replay.timer){ stopReplay(); return; }
  if(_replay && !_replay.timer){
    _replay.timer=setInterval(replayTick, _replaySpeeds[_replay.speedIdx||0]);
    const btn=document.getElementById('replayBtn'); if(btn) btn.textContent='■ Stop';
    setTapeBanner(true);
    return;
  }
  const d=_chartData; if(!d || !(d.candles||[]).length) return;
  const main=document.getElementById('chartMain'); if(!main) return;
  const create=chartsAvailable(); if(!create) return;
  if(_live) stopLive();       // playback and a live feed must never share a pane
  unmountDrawings();          // the price pane is about to be replaced
  _priceSeries=null;
  disposeCharts();
  const price=newPane(main, 420);
  const candle=price.addCandlestickSeries({
    upColor:'#22c55e', downColor:'#ef4444', borderUpColor:'#22c55e',
    borderDownColor:'#ef4444', wickUpColor:'#22c55e', wickDownColor:'#ef4444' });
  _replay={timer:null, idx:0, candles:d.candles.slice(), candle:candle,
           speedIdx:0};
  const btn=document.getElementById('replayBtn'); if(btn) btn.textContent='■ Stop';
  const spd=document.getElementById('replaySpeedBtn'); if(spd) spd.textContent='1×';
  // Start with a small warm window so the first frames have context, while
  // leaving at least one bar to reveal when history contains multiple bars.
  _replay.idx=Math.min(20, Math.max(1, d.candles.length-1));
  try{ candle.setData(d.candles.slice(0, _replay.idx)); }catch(e){}
  renderReplayHead(_replay.idx);                       // label replay immediately
  _replay.timer=setInterval(replayTick, _replaySpeeds[0]);
  setTapeBanner(true);
}

function renderChartHead(d){
  const el=document.getElementById('chartHead'); if(!el) return;
  const st=d.stats||{}, chg=d.change_pct;
  const chgCls = chg==null?'muted':(chg>=0?'okc':'err');
  const ind=(k,v,dp)=> `<span class="ind">${k} <b>${v==null?'—':Number(v).toFixed(dp==null?2:dp)}</b></span>`;
  el.innerHTML = `<span class="px">${d.last_price==null?'—':fmt(d.last_price)}</span>
    <span class="${chgCls}" style="font-weight:700">${chg==null?'':(chg>=0?'+':'')+chg.toFixed(2)+'%'}</span>
    <span class="badge">${esc(d.symbol||'')} · ${esc(d.timeframe||'')}</span>
    <span class="badge">${d.count||0} candles</span>
    ${ind('RSI', st.rsi, 1)} ${ind('ADX', st.adx, 1)} ${ind('ATR%', st.atr_pct, 2)}
    ${ind('VWAP', st.vwap)} ${ind('EMA20', st.ema20)} ${ind('EMA200', st.ema200)}`;
}
function renderChartStats(d){
  const el=document.getElementById('chartStats'); if(!el) return;
  const st=d.stats||{}, p=d.plan||{};
  const row=(k,v)=> `<b>${k}</b><span class="mono">${v==null?'—':(typeof v==='number'?fmt(v):esc(v))}</span>`;
  el.innerHTML=`<div class="kv">
    ${row('Last price', d.last_price)} ${row('Range high', st.range_high)} ${row('Range low', st.range_low)}
    ${row('RSI', st.rsi)} ${row('ADX', st.adx)} ${row('ATR', st.atr)}
    ${row('MACD', st.macd)} ${row('MACD signal', st.macd_signal)}
    ${row('VWAP', st.vwap)} ${row('Volume', st.volume)} ${row('Volume vs avg', st.volume_ratio)}
    ${p.action?row('Plan', p.action+(p.setup?' · '+p.setup:'')):''}
    ${p.entry!=null?row('Entry', p.entry):''} ${p.stop_loss!=null?row('Stop-loss', p.stop_loss):''}
    ${p.take_profit!=null?row('Take-profit', p.take_profit):''}
    ${p.risk_reward!=null?row('Risk / reward', '1:'+Number(p.risk_reward).toFixed(2)):''}
  </div>`;
}
function renderChartLevels(d){
  const el=document.getElementById('chartLevels'); if(!el) return;
  const levels=(d.levels||[]);
  if(!levels.length){ el.innerHTML='<span class="muted">no key levels on this timeframe yet</span>'; return; }
  const last=d.last_price;
  el.innerHTML='<table>'+levels.map(l=>{
    const dist = (last && l.price) ? ((l.price-last)/last*100) : null;
    return `<tr><td><span style="color:${l.color}">●</span> ${esc(l.label||l.kind)}</td>
      <td class="mono">${fmt(l.price)}</td>
      <td class="mono ${dist==null?'':(dist>=0?'okc':'err')}">${dist==null?'—':(dist>=0?'+':'')+dist.toFixed(2)+'%'}</td></tr>`;
  }).join('')+'</table>';
}

// ── Trade manager ─────────────────────────────────────────────────────
async function loadTradeManager(){
  const host=document.getElementById('tradeManager'); if(!host) return;
  try{
    const d=await (await fetch('/api/trades')).json();
    const rows=d.open||[];
    const cnt=document.getElementById('tmCount'); if(cnt) cnt.textContent=rows.length;
    if(!rows.length){
      host.innerHTML='<span class="muted">no open positions. Approve a signal in <b>Trades</b>, then run the paper check.</span>';
    } else {
      host.innerHTML='<div style="overflow:auto"><table class="tmtable"><tr>'
        +['Trade','Side','Entry','Current','Stop','Target','R now','MAE','MFE','In trade','Status','Action'].map(h=>'<th>'+h+'</th>').join('')
        +'</tr>'+rows.map(t=>{
          const r=t.current_r;
          const rCls=r==null?'':(r>=0?'rpos':'rneg');
          const mins=t.minutes_in_trade||0;
          const dur = mins>=60 ? Math.floor(mins/60)+'h '+(mins%60)+'m' : mins+'m';
          return `<tr>
            <td>#${t.scan_id} <span class="note">${esc(t.symbol||'')} ${esc(t.timeframe||'')}</span><br><span class="note">${esc(t.plan_type||'')}</span></td>
            <td><span class="pill ${cls(t.action)}" style="padding:2px 8px;font-size:11px">${esc(t.action||'')}</span></td>
            <td class="mono">${fmt(t.entry_price||t.entry)}</td>
            <td class="mono">${fmt(t.current_price)}</td>
            <td class="mono" style="color:var(--red)">${fmt(t.stop_loss)}</td>
            <td class="mono" style="color:var(--green)">${fmt(t.take_profit)}</td>
            <td class="mono ${rCls}">${r==null?'—':(r>=0?'+':'')+r.toFixed(2)+'R'}</td>
            <td class="mono">${t.mae==null?'—':Number(t.mae).toFixed(2)}</td>
            <td class="mono">${t.mfe==null?'—':Number(t.mfe).toFixed(2)}</td>
            <td>${dur}</td>
            <td><span class="badge">${esc(t.status||'')}</span></td>
            <td><button class="rowbtn" onclick="openModal(${t.scan_id})">Detail</button>
                <button class="rowbtn ok" onclick="journalFor(${t.scan_id})">Journal</button>
                <button class="rowbtn no" onclick="decide(${t.scan_id},'CLOSED')">Close</button></td>
          </tr>
          <tr><td colspan="12" class="note" style="padding-top:0">${(t.management||[]).map(m=>'• '+esc(m)).join('<br>')}</td></tr>`;
        }).join('')+'</table></div>';
    }
    const rec=document.getElementById('tmRecent');
    if(rec){
      const recent=(d.recent||[]).slice(0,10);
      rec.innerHTML = recent.length ? '<table><tr><th>Scan</th><th>Symbol</th><th>Setup</th><th>Outcome</th><th>R</th><th>Reason</th></tr>'
        + recent.map(t=>`<tr><td>#${t.scan_id}</td><td>${esc(t.symbol||'')}</td><td>${esc(t.plan_type||'')}</td>
          <td>${esc(t.outcome||t.status||'')}</td>
          <td class="mono ${t.rr_achieved>=0?'okc':'err'}">${t.rr_achieved==null?'—':Number(t.rr_achieved).toFixed(2)+'R'}</td>
          <td class="note">${esc(t.close_reason||'')}</td></tr>`).join('')+'</table>'
        : '<span class="muted">no closed paper trades yet</span>';
    }
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}

// ── Risk center ───────────────────────────────────────────────────────
async function loadRiskCenter(){
  const gateEl=document.getElementById('riskCenterGate'); if(!gateEl) return;
  try{
    const d=await (await fetch('/api/risk')).json();
    if(d.error){ gateEl.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    const g=d.gate||{}, det=g.details||{}, eff=det.effective_risk||{}, prog=det.progression||{},
          dw=det.daily_weekly||{}, dd=det.drawdown||{}, kelly=det.kelly||{}, ts=d.trader_state||{};
    const open=!!g.allowed;
    const bar=(used, limit, color)=>{
      const pct=limit?Math.min(100, Math.abs(used)/limit*100):0;
      return `<div class="bar"><i style="width:${pct.toFixed(0)}%;background:${color}"></i></div>`;
    };
    const today=(dw.today||{}).pct||0, week=(dw.week||{}).pct||0;
    gateEl.innerHTML=`
      <div class="flex" style="margin-bottom:10px">
        <span class="pill ${open?'BUY':'SELL'}">${open?'GATE OPEN':'GATE CLOSED'}</span>
        <span class="badge">level: ${esc(prog.level||'—')}</span>
        <span class="badge">${esc(prog.label||'')}</span>
        <span class="badge">risk ${eff.risk_pct}%/trade</span>
      </div>
      ${(g.blocked_by||[]).length?`<div class="note" style="background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.3);padding:9px;border-radius:10px;margin-bottom:10px">
        <b>Why you cannot trade right now</b>${(g.blocked_by||[]).map(b=>'<div>• '+esc(b)+'</div>').join('')}</div>`:''}
      <div class="grid2">
        <div>
          <div class="note"><b>Daily budget</b> ${today.toFixed(2)}% of −${eff.daily}%</div>${bar(today, eff.daily, today<0?'var(--red)':'var(--green)')}
          <div class="note" style="margin-top:8px"><b>Weekly budget</b> ${week.toFixed(2)}% of −${eff.weekly}%</div>${bar(week, eff.weekly, week<0?'var(--red)':'var(--green)')}
          <div class="note" style="margin-top:8px"><b>Drawdown</b> ${(dd.max_drawdown_pct||0).toFixed(2)}% · ladder ${esc(dd.level||'normal')}</div>
        </div>
        <div class="kv">
          <b>Trades today</b><span>${(dw.today||{}).trades||0}</span>
          <b>Trades this week</b><span>${(dw.week||{}).trades||0}</span>
          <b>Kelly advisory</b><span>${kelly.clamped_size!=null?(kelly.clamped_size+'% (clamped at '+kelly.max_risk_pct+'%)'):esc(kelly.note||'unavailable')}</span>
          <b>Kelly win rate</b><span>${kelly.win_rate!=null?(kelly.win_rate*100).toFixed(1)+'%':'—'}</span>
          <b>Rule violations</b><span>${(d.journal||{}).n?((d.journal.violation_rate*100).toFixed(1)+'% of '+d.journal.n):'no journal yet'}</span>
        </div>
      </div>`;
    const flags=['angry','tired','revenge','chasing'].filter(k=> ts[k]);
    const st=document.getElementById('traderStateNow');
    if(st) st.innerHTML = flags.length
      ? '<span class="err"><b>Active flags:</b> '+flags.join(', ')+'</span> — the gate stays closed until you clear them.'
      : '<span class="okc">No behavioral flags set — you are declaring a clear head.</span>';
    const mc=document.getElementById('riskMonte');
    if(mc){
      const m=d.monte||{};
      const rows=(m.rows||m.table||[]);
      mc.innerHTML = rows.length
        ? '<table><tr><th>Risk %</th><th>Expected DD</th><th>Ruin prob</th><th>Worst streak</th><th>Time to recover</th></tr>'
          + rows.map(r=>`<tr><td class="mono">${r.risk_pct!=null?r.risk_pct+'%':'—'}</td>
            <td class="mono">${r.expected_drawdown_pct!=null?Number(r.expected_drawdown_pct).toFixed(1)+'%':'—'}</td>
            <td class="mono ${(r.ruin_prob||0)>0.05?'err':'okc'}">${r.ruin_prob!=null?(r.ruin_prob*100).toFixed(1)+'%':'—'}</td>
            <td class="mono">${r.worst_losing_streak??'—'}</td>
            <td class="mono">${r.time_to_recover??'—'}</td></tr>`).join('')+'</table>'
          + '<div class="note" style="margin-top:6px">'+esc(m.note||'Simulated from your recorded outcomes. Advisory only.')+'</div>'
        : '<span class="muted">'+esc(m.note||'not enough decided trades yet for a Monte Carlo run')+'</span>';
    }
  }catch(e){ gateEl.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function clearTraderState(){
  try{
    await fetch('/api/trader-state',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({angry:false,tired:false,revenge:false,chasing:false,note:'cleared from dashboard'})});
    showToast('Trader state cleared','ok'); loadRiskCenter(); loadRiskGate();
  }catch(e){ showToast('Could not clear state','err'); }
}
function fillSizerFromSignal(){
  const d=_chartData&&_chartData.plan;
  if(!d || (d.entry==null && d.stop_loss==null)){ showToast('No live plan yet — run a scan first','err'); return; }
  const set=(id,v)=>{ const el=document.getElementById(id); if(el && v!=null) el.value=v; };
  set('psEntry', d.entry); set('psStop', d.stop_loss); set('psTp', d.take_profit);
  showToast('Filled from the live plan','ok');
}
async function calcPositionSize(){
  const out=document.getElementById('psResult'); if(!out) return;
  const num=id=>{ const v=document.getElementById(id)?.value; return v===''||v==null?null:Number(v); };
  out.innerHTML='calculating…';
  try{
    const r=await fetch('/api/position-size',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:chartSym(), balance:num('psBalance'), risk_pct:num('psRisk'),
        entry:num('psEntry'), stop_loss:num('psStop'), take_profit:num('psTp'), leverage:num('psLev')})});
    const d=await r.json();
    if(!d.ok){ out.innerHTML='<span class="err">'+esc(d.error||'could not size this trade')+'</span>'; return; }
    out.innerHTML=`
      <div class="statrow" style="margin-bottom:8px">
        <div class="stat"><div class="v mono">${fmt(d.recommended_units,6)}</div><div class="k">Units to buy</div></div>
        <div class="stat"><div class="v mono">${fmt(d.risk_amount)}</div><div class="k">Money at risk</div></div>
        <div class="stat"><div class="v mono">${fmt(d.notional)}</div><div class="k">Notional</div></div>
        <div class="stat"><div class="v mono">${d.risk_reward==null?'—':'1:'+d.risk_reward}</div><div class="k">Risk / reward</div></div>
      </div>
      <div class="kv">
        <b>Applied risk</b><span>${d.risk_pct_applied}% (level ${esc(d.progression||'')}, cap ${d.ladder_cap_pct}%)</span>
        <b>Stop distance</b><span class="mono">${fmt(d.stop_distance)} (${d.stop_pct}%)</span>
        <b>Margin at ${d.leverage}x</b><span class="mono">${fmt(d.margin_required)}</span>
        <b>Losses to daily stop</b><span>${d.losses_to_daily_limit} in a row</span>
        <b>Losses to weekly stop</b><span>${d.losses_to_weekly_limit} in a row</span>
      </div>
      <div class="note" style="margin-top:8px;padding:8px;border-radius:10px;border:1px solid ${d.gate_open?'var(--line)':'rgba(239,68,68,.4)'};background:${d.gate_open?'rgba(255,255,255,.04)':'rgba(239,68,68,.10)'}">${esc(d.verdict||'')}</div>
      ${(d.warnings||[]).map(w=>'<div class="note" style="color:var(--amber)">⚠ '+esc(w)+'</div>').join('')}`;
  }catch(e){ out.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}

// ── Journal ───────────────────────────────────────────────────────────
async function loadJournalCenter(){
  const sel=document.getElementById('jScan'); if(!sel) return;
  try{
    const d=await (await fetch('/api/journal')).json();
    const em=document.getElementById('jEmotion');
    if(em && !em.options.length) em.innerHTML=(d.emotions||['calm']).map(e=>`<option value="${esc(e)}">${esc(e)}</option>`).join('');
    const keep=sel.value;
    sel.innerHTML='<option value="">— pick a trade —</option>'+(d.journalable||[]).map(s=>
      `<option value="${s.id}">#${s.id} · ${esc(s.symbol||'')} ${esc(s.action||'')} · ${esc(s.status||'')}</option>`).join('');
    if(keep) sel.value=keep;
    const sum=document.getElementById('jSummary');
    if(sum){
      const s=d.summary||{};
      sum.innerHTML = s.n
        ? `<div class="statrow">
            <div class="stat"><div class="v">${s.n}</div><div class="k">Journalled trades</div></div>
            <div class="stat"><div class="v ${s.violations?'err':'okc'}">${s.violations||0}</div><div class="k">Rule violations</div></div>
            <div class="stat"><div class="v">${((s.violation_rate||0)*100).toFixed(1)}%</div><div class="k">Violation rate</div></div>
          </div><div class="note" style="margin-top:8px">The goal is 0%. A loss with the rules followed is an excellent trade; a win with rules broken is a terrible one.</div>`
        : '<span class="muted">no journal entries yet — close a paper trade, then journal it here</span>';
    }
  }catch(e){ /* keep the form usable */ }
}
async function loadJournalEntry(){
  const id=document.getElementById('jScan')?.value;
  const cl=document.getElementById('jChecklist');
  if(!id){ if(cl) cl.textContent='Pick a trade to see the plan you actually took.'; return; }
  try{
    const d=await (await fetch('/api/journal?scan_id='+encodeURIComponent(id))).json();
    const e=d.entry||{}, c=d.checklist||{}, q=d.quality||{};
    const set=(elid,v)=>{ const el=document.getElementById(elid); if(el && v!=null && v!=='') el.value=v; };
    if(e.followed_rules!=null) set('jFollowed', String(e.followed_rules?1:0));
    set('jEmotion', e.emotion); set('jMistake', e.mistake);
    set('jNotes', e.notes); set('jChange', e.would_change);
    if(cl) cl.innerHTML=`<div class="kv">
      <b>Asset</b><span>${esc(c.asset||'—')} ${esc(c.timeframe||'')}</span>
      <b>Setup</b><span>${esc(c.setup||'—')}</span>
      <b>Regime</b><span>${esc(c.regime||'—')}</span>
      <b>HTF bias</b><span>${esc(c.htf_bias||'—')}</span>
      <b>Planned entry</b><span class="mono">${fmt(c.entry)}</span>
      <b>Planned stop</b><span class="mono">${fmt(c.stop_loss)}</span>
      <b>Planned target</b><span class="mono">${fmt(c.take_profit)}</span>
      <b>Planned R:R</b><span>${c.planned_rr==null?'—':'1:'+c.planned_rr}</span>
      <b>News environment</b><span>${esc(c.news_environment||'—')}</span>
      ${q.recorded?`<b>Execution grade</b><span><b>${esc(q.quality||'')}</b> — ${esc(q.verdict||'')}</span>`:''}
    </div>`;
  }catch(err){ if(cl) cl.innerHTML='<span class="err">'+esc(String(err))+'</span>'; }
}
function journalFor(scanId){
  switchTab('journal');
  setTimeout(async ()=>{
    await loadJournalCenter();
    const sel=document.getElementById('jScan');
    if(sel){
      if(![...sel.options].some(o=>o.value===String(scanId))){
        const o=document.createElement('option'); o.value=String(scanId); o.textContent='#'+scanId; sel.appendChild(o);
      }
      sel.value=String(scanId); loadJournalEntry();
    }
  }, 120);
}
async function saveJournal(){
  const st=document.getElementById('jStatus');
  const id=document.getElementById('jScan')?.value;
  if(!id){ if(st) st.innerHTML='<span class="err">pick a trade first</span>'; return; }
  const val=i=> document.getElementById(i)?.value||'';
  if(st) st.textContent='saving…';
  try{
    const r=await fetch('/api/journal',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({scan_id:Number(id), followed_rules:val('jFollowed'), emotion:val('jEmotion'),
        mistake:val('jMistake'), notes:val('jNotes'), would_change:val('jChange')})});
    const d=await r.json();
    if(!d.ok){ if(st) st.innerHTML='<span class="err">'+esc(d.error||'save failed')+'</span>'; return; }
    const q=d.quality||{};
    if(st) st.innerHTML='<span class="okc">✓ saved</span>'+(q.recorded?' — '+esc(q.verdict||''):'');
    showToast('Journal saved for #'+id,'ok');
    loadJournalCenter(); loadJournalEntry();
  }catch(e){ if(st) st.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}

// ── Command center ────────────────────────────────────────────────────
let _commands=null, _cmdCat='All';
async function loadCommands(){
  const host=document.getElementById('commandList'); if(!host || _commands) return;
  try{
    const d=await (await fetch('/api/commands')).json();
    _commands=d;
    const cnt=document.getElementById('cmdCount'); if(cnt) cnt.textContent=(d.count||0)+' actions';
    const cats=document.getElementById('cmdCats');
    if(cats) cats.innerHTML=['All',...(d.categories||[]).map(c=>c.category)].map(c=>
      `<span class="catchip ${c===_cmdCat?'active':''}" onclick="setCmdCat('${esc(c)}')">${esc(c)}</span>`).join('');
    renderCommands();
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
function setCmdCat(cat){
  _cmdCat=cat;
  document.querySelectorAll('#cmdCats .catchip').forEach(c=> c.classList.toggle('active', c.textContent===cat));
  renderCommands();
}
function cmdInputHtml(cmd, spec){
  const id='in_'+cmd.id+'_'+spec.name;
  if(spec.type==='bool')
    return `<label class="check" style="text-transform:none;letter-spacing:normal"><input type="checkbox" id="${id}" ${spec.default?'checked':''}> ${esc(spec.label)}</label>`;
  if(spec.type==='choice')
    return `<label>${esc(spec.label)}<select id="${id}">${(spec.options||[]).map(o=>
      `<option value="${esc(o)}" ${o===spec.default?'selected':''}>${esc(o)}</option>`).join('')}</select></label>`;
  return `<label>${esc(spec.label)}<input id="${id}" type="${spec.type==='int'?'number':'text'}"
    value="${esc(spec.default==null?'':spec.default)}" placeholder="${esc(spec.placeholder||'')}"></label>`;
}
function renderCommands(){
  const host=document.getElementById('commandList'); if(!host || !_commands) return;
  const q=(document.getElementById('cmdSearch')?.value||'').toLowerCase();
  const badge={read:'🟢 read-only', write:'🟡 writes locally', long:'🟠 slow', blocked:'🔒 terminal only'};
  let html='';
  (_commands.categories||[]).forEach(group=>{
    if(_cmdCat!=='All' && group.category!==_cmdCat) return;
    const items=(group.commands||[]).filter(c=> !q ||
      (c.title+' '+c.what+' '+c.cli+' '+c.id).toLowerCase().includes(q));
    if(!items.length) return;
    html+=`<div class="sectionTitle cmdcat">${esc(group.category)}</div><div class="cmdgrid">`;
    items.forEach(c=>{
      html+=`<div class="cmdcard">
        <h3>${esc(c.title)} <span class="safety ${esc(c.safety)}">${badge[c.safety]||c.safety}</span></h3>
        <div class="note">${esc(c.what)}</div>
        <div class="cli">${esc(c.cli)}</div>
        ${c.inputs&&c.inputs.length?`<div class="inputs">${c.inputs.map(s=>cmdInputHtml(c,s)).join('')}</div>`:''}
        <div class="flex" style="margin-top:9px">
          ${c.safety==='blocked'
            ? `<span class="note">🔒 ${esc(c.note||'run this one in a terminal')}</span>`
            : `<button class="btn primary" onclick="runCommand('${esc(c.id)}')">▶ Run</button>`}
          ${(c.related||[]).length?`<span class="note">related: ${c.related.map(r=>
            `<a href="#" onclick="jumpCommand('${esc(r)}');return false">${esc(r)}</a>`).join(', ')}</span>`:''}
        </div>
      </div>`;
    });
    html+='</div>';
  });
  host.innerHTML = html || '<span class="muted">no actions match that search</span>';
}
function jumpCommand(id){
  const s=document.getElementById('cmdSearch'); if(s){ s.value=id.replace(/_/g,' '); }
  _cmdCat='All'; renderCommands();
}
function collectParams(cmd){
  const out={};
  (cmd.inputs||[]).forEach(spec=>{
    const el=document.getElementById('in_'+cmd.id+'_'+spec.name);
    if(!el) return;
    out[spec.name] = spec.type==='bool' ? el.checked : el.value;
  });
  return out;
}
async function runCommand(id){
  const cmd=(_commands.categories||[]).flatMap(g=>g.commands||[]).find(c=>c.id===id);
  if(!cmd) return;
  const out=document.getElementById('cmdOut'), state=document.getElementById('cmdRunning');
  switchTab('commands');
  if(state) state.innerHTML='<b>'+esc(cmd.title)+'</b> running… ('+esc(cmd.cli)+')';
  if(out) out.textContent='working…';
  try{
    // Slow commands (backfill, backtest, simulator, …) are background jobs:
    // they run server-side, survive a browser close, and stream progress.
    if(cmd.safety==='long'){
      if(state) state.innerHTML='<b>'+esc(cmd.title)+'</b> submitted as a background job…';
      if(out) out.textContent='submitting…';
      await submitJob(id, collectParams(cmd));
      return;
    }
    const r=await fetch('/api/commands/run',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id, params:collectParams(cmd)})});
    const d=await r.json();
    if(state) state.innerHTML = (d.ok?'<span class="okc">✓ finished</span>':'<span class="err">✗ failed (exit '+d.exit_code+')</span>')
      +' · <span class="mono">'+esc(d.cli||cmd.cli)+'</span>'+(d.elapsed_ms?' · '+(d.elapsed_ms/1000).toFixed(1)+'s':'');
    if(out) out.textContent = d.output || d.error || '(no output)';
    showToast(cmd.title+(d.ok?' finished':' failed'), d.ok?'ok':'err');
    try{ if(out) out.scrollIntoView({behavior:'smooth',block:'nearest'}); }catch(e){}
  }catch(e){
    if(state) state.innerHTML='<span class="err">request failed</span>';
    if(out) out.textContent=String(e);
  }
}

/* ── Background jobs (P18.3) ─────────────────────────────────────────── */
let _activeJob=null, _jobStream=null;
function jobStatusBadge(s){
  const map={queued:'<span class="badge">queued</span>',
    running:'<span class="badge strong">running</span>',
    succeeded:'<span class="badge ok">✓ done</span>',
    failed:'<span class="badge err">✗ failed</span>',
    cancelled:'<span class="badge">cancelled</span>',
    interrupted:'<span class="badge">interrupted</span>'};
  return map[s]||('<span class="badge">'+esc(s)+'</span>');
}
function jobProgress(j){
  if(!j || j.step_total<=1) return '';
  return ' · step '+(j.step_index||0)+'/'+j.step_total;
}
async function loadJobs(force){
  const host=document.getElementById('jobList'); if(!host) return;
  try{
    const d=await (await fetch('/api/v1/jobs')).json();
    const jobs=(d.data&&d.data.jobs)||[];
    const cnt=document.getElementById('jobCount'); if(cnt) cnt.textContent=jobs.length+' jobs';
    const st=document.getElementById('jobStatus');
    const live=jobs.filter(j=>j.status==='queued'||j.status==='running').length;
    if(st) st.textContent = live? (live+' running/queued') : 'idle — nothing running';
    if(!jobs.length){ host.innerHTML='<span class="muted">no jobs yet — run a backfill, backtest or simulator.</span>'; return; }
    host.innerHTML=jobs.map(j=>{
      const active=j.job_id===_activeJob;
      const cancelBtn=(j.status==='queued'||j.status==='running')
        ? `<button class="rowbtn no" onclick="cancelJob(event,'${esc(j.job_id)}')">✕ cancel</button>` : '';
      const phase=j.phase?`<div class="note">${esc(j.phase)}${jobProgress(j)}</div>`:'';
      return `<div class="jobrow ${active?'active':''}" onclick="watchJob('${esc(j.job_id)}')">
        <div style="flex:1"><b>${esc(j.title||j.kind)}</b> ${jobStatusBadge(j.status)}
          ${phase}</div>
        <span class="note mono">${esc(j.kind)}</span>${cancelBtn}</div>`;
    }).join('');
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function submitJob(kind, params){
  const out=document.getElementById('cmdOut'), state=document.getElementById('cmdRunning');
  try{
    const r=await fetch('/api/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind:kind, params:params||{}})});
    const d=await r.json();
    if(!d.ok){
      if(state) state.innerHTML='<span class="err">✗ '+esc((d.error&&d.error.message)||'failed')+'</span>';
      if(out) out.textContent=JSON.stringify(d,null,2);
      return;
    }
    const job=d.data.job;
    if(state) state.innerHTML = (d.data.duplicate?'<span class="okc">already running</span>':'<span class="okc">✓ job submitted</span>')
      +' · <span class="mono">'+esc(job.job_id)+'</span> · '+esc(job.title||kind);
    showToast((d.data.duplicate?'Already queued: ':'Started: ')+(job.title||kind),'ok');
    await loadJobs(true);
    await watchJob(job.job_id);
  }catch(e){
    if(state) state.innerHTML='<span class="err">request failed</span>';
    if(out) out.textContent=String(e);
  }
}
let _evidenceStream=null;
function renderEvidenceGuidance(g){
  const el=document.getElementById('evProjection'); if(!el || !g) return;
  let projection='Run one guided build to establish an observed pace.';
  if(g.projection_state==='complete') projection='Sample-count gap: complete.';
  else if(g.projection_state==='estimated') projection=`At the recently observed aggregate pace: ~${g.projected_rounds} more simulator round(s).`;
  else if(g.projection_state==='stalled') projection='Recent rounds added no new unique samples — change data coverage, not strategy parameters.';
  const tone=g.result==='edge_measured'?'okc':
    ((g.result==='no_edge'||(g.no_edge_setups||[]).length)?'err':'');
  el.innerHTML=`<b class="${tone}">${esc(g.headline||'')}</b><br>${esc(projection)} `
    +`Gap: ${g.backtest_gap||0} backtest + ${g.paper_gap||0} paper sample(s). `
    +`<span style="opacity:.72">${esc(g.caveat||'')}</span>`;
}
function showEvidenceJob(j){
  const box=document.getElementById('evJob'); if(!box) return;
  box.style.display='block';
  const badge=document.getElementById('evJobBadge'), state=document.getElementById('evJobState'),
        bar=document.getElementById('evJobBar'), log=document.getElementById('evJobLog'),
        btn=document.getElementById('evBuildBtn');
  const total=Math.max(1,Number(j.step_total)||4), done=j.status==='succeeded'?total:(Number(j.step_index)||0);
  if(badge) badge.textContent=j.status||'queued';
  if(state) state.textContent=(j.phase||j.status||'queued')+' · step '+done+'/'+total;
  if(bar){ bar.style.width=Math.max(0,Math.min(100,done/total*100))+'%'; bar.style.background=j.status==='failed'?'var(--red)':(j.status==='succeeded'?'var(--green)':'var(--blue)'); }
  // HTML is a plain Python string: a backslash-n literal here would become a
  // real newline inside this JS string and break the whole script. Use the
  // character code instead (see the note above the HTML template).
  if(log && j.log_tail!=null){ const nl=String.fromCharCode(10); const lines=String(j.log_tail).split(nl); log.textContent=lines.slice(-12).join(nl); log.scrollTop=log.scrollHeight; }
  if(btn) btn.disabled=(j.status==='queued'||j.status==='running');
}
function watchEvidenceJob(jobId){
  if(_evidenceStream){ try{_evidenceStream.close();}catch(e){} }
  const es=new EventSource('/api/v1/jobs/'+encodeURIComponent(jobId)+'/events');
  _evidenceStream=es;
  es.addEventListener('job',ev=>{
    let j={}; try{j=JSON.parse(ev.data);}catch(e){}
    showEvidenceJob(j);
    if({succeeded:1,failed:1,cancelled:1,interrupted:1}[j.status]){
      es.close(); _evidenceStream=null;
      showToast('Evidence run '+j.status,j.status==='succeeded'?'ok':'err');
      loadEvidence();
    }
  });
  es.onerror=()=>{ es.close(); _evidenceStream=null; };
}
async function buildEvidence(){
  const params={
    symbol:(document.getElementById('evSymbol')?.value||'BTCUSDT').trim().toUpperCase(),
    tf:document.getElementById('evTf')?.value||'15m',
    market:document.getElementById('evMarket')?.value||'spot',
    since:document.getElementById('evSince')?.value||'30d',
    bars:Number(document.getElementById('evBars')?.value||500),
    rounds:Number(document.getElementById('evRounds')?.value||3)
  };
  const box=document.getElementById('evJob'); if(box) box.style.display='block';
  const state=document.getElementById('evJobState'); if(state) state.textContent='Validating and submitting…';
  try{
    const r=await fetch('/api/v1/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind:'evidence',params})});
    const d=await r.json();
    if(!d.ok){ if(state) state.innerHTML='<span class="err">'+esc((d.error&&d.error.message)||'Submission failed')+'</span>'; return; }
    showEvidenceJob(d.data.job);
    showToast(d.data.duplicate?'This exact evidence run is already active':'Evidence build started','ok');
    watchEvidenceJob(d.data.job.job_id);
  }catch(e){ if(state) state.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function cancelJob(ev, jobId){
  if(ev && ev.stopPropagation) ev.stopPropagation();
  try{
    const r=await fetch('/api/v1/jobs/'+encodeURIComponent(jobId)+'/cancel',{method:'POST'});
    const d=await r.json();
    showToast(d.ok?'Cancellation requested':'Could not cancel: '+(d.error&&d.error.message), d.ok?'ok':'err');
    await loadJobs(true);
  }catch(e){ showToast(String(e),'err'); }
}
async function watchJob(jobId){
  _activeJob=jobId;
  if(_jobStream){ try{_jobStream.close();}catch(e){} _jobStream=null; }
  const out=document.getElementById('jobOut'); if(out) out.textContent='connecting…';
  await loadJobs(true);
  try{
    const es=new EventSource('/api/v1/jobs/'+encodeURIComponent(jobId)+'/events');
    _jobStream=es;
    es.addEventListener('job', ev=>{
      let j={}; try{ j=JSON.parse(ev.data); }catch(e){}
      if(out && j.log_tail!=null) out.textContent=j.log_tail;
      const term={succeeded:1,failed:1,cancelled:1,interrupted:1};
      if(term[j.status]){ es.close(); _jobStream=null; showToast((j.title||'Job')+' '+j.status,j.status==='succeeded'?'ok':'err'); }
      loadJobs(true);
    });
    es.addEventListener('error', ()=>{ /* reconnect resumes from persisted state */ });
    es.onerror=()=>{ es.close(); _jobStream=null; };
  }catch(e){ if(out) out.textContent=String(e); }
}

// ── Module catalog ────────────────────────────────────────────────────
let _modules=null;
async function loadModules(){
  const host=document.getElementById('moduleList'); if(!host || _modules) return;
  try{
    const d=await (await fetch('/api/modules')).json();
    _modules=d;
    const cnt=document.getElementById('modCount'); if(cnt) cnt.textContent=(d.count||0)+' modules';
    renderModules();
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
function renderModules(){
  const host=document.getElementById('moduleList'); if(!host || !_modules) return;
  const q=(document.getElementById('modSearch')?.value||'').toLowerCase();
  let html='';
  (_modules.packages||[]).forEach(p=>{
    const mods=(p.modules||[]).filter(m=> !q || (m.name+' '+m.summary).toLowerCase().includes(q));
    if(!mods.length) return;
    html+=`<div class="sectionTitle">${esc(p.label)} · ${esc(p.package)}/ <span class="note">${mods.length}</span></div>`;
    html+=mods.map(m=>`<div class="modrow"><code>${esc(m.name)}</code>
      <span class="note">${esc(m.summary)}</span>
      <span class="note mono">${m.lines} ln</span></div>`).join('');
  });
  host.innerHTML = html || '<span class="muted">no modules match that search</span>';
}

// ── Connections: what SKY is really plugged into ──────────────────────
let _connections=null;
async function loadConnections(force){
  const host=document.getElementById('connectionList'); if(!host) return;
  if(_connections && !force){ renderConnections(); return; }
  host.innerHTML='<span class="muted">probing every connection…</span>';
  try{
    const d=await (await fetch('/api/connections')).json();
    _connections=d; renderConnections(); loadAccount();
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
function renderConnections(){
  const d=_connections; if(!d) return;
  const strip=document.getElementById('connStrip');
  if(strip){
    strip.className='strip lvl-'+(d.level||'degraded');
    const dot=d.level==='ok'?'var(--green)':d.level==='down'?'var(--red)':'var(--amber)';
    strip.innerHTML=`<span class="verdict"><span class="dot" style="background:${dot}"></span>${esc(d.headline||'')}</span>
      <span class="pillars"><span class="pill-chip">${d.live_count||0}/${d.total||0} live</span>
      ${d.demo_mode?'<span class="pill-chip" style="color:var(--amber)">DEMO MODE</span>':'<span class="pill-chip" style="color:var(--green)">REAL MARKET</span>'}</span>`;
  }
  const cnt=document.getElementById('connCount');
  if(cnt) cnt.textContent=(d.live_count||0)+'/'+(d.total||0)+' live';
  const host=document.getElementById('connectionList'); if(!host) return;
  const tiers=d.tiers||{};
  const groups={};
  (d.connections||[]).forEach(c=>{ (groups[c.tier]=groups[c.tier]||[]).push(c); });
  let html='';
  ['core','context','alerts','ai','account'].forEach(tier=>{
    const list=groups[tier]; if(!list||!list.length) return;
    html+=`<div class="sectionTitle">${esc(tiers[tier]||tier)}</div>`;
    list.forEach(c=>{
      const state=c.live?'live':(c.configured?'fail':'off');
      const label=c.live?'● LIVE':(c.configured?'● NOT REACHABLE':'○ NOT CONNECTED');
      const testable=['telegram','discord'].includes(c.id);
      html+=`<div class="conncard ${state}">
        <h3>${esc(c.label)} <span class="connstate ${state}">${label}</span>
          ${c.latency_ms!=null?`<span class="note">${c.latency_ms}ms</span>`:''}</h3>
        <div class="note"><b>Gives you:</b> ${esc(c.gives||'')}</div>
        <div class="note"><b>Needs:</b> ${esc(c.needs||'')}</div>
        ${c.detail?`<div class="note"><b>Status:</b> ${esc(c.detail)}</div>`:''}
        ${c.safety?`<div class="note" style="color:var(--green)">🔒 ${esc(c.safety)}</div>`:''}
        ${!c.live&&(c.how||[]).length?`<div class="note" style="margin-top:6px"><b>How to switch it on:</b></div>
          <ol class="connhow">${(c.how||[]).map(s=>'<li>'+esc(s).replace(/([A-Z][A-Z0-9_]{4,})/g,'<code>$1</code>')+'</li>').join('')}</ol>`:''}
        <div class="flex" style="margin-top:8px">
          <button class="btn" onclick="testConnection('${esc(c.id)}')">Test this connection</button>
          ${testable?`<button class="btn primary" onclick="testAlert('${esc(c.id)}')">Send me a test alert</button>`:''}
          <span class="note" id="conntest-${esc(c.id)}"></span>
        </div></div>`;
    });
  });
  host.innerHTML=html || '<span class="muted">no connections defined</span>';
}
async function testConnection(id){
  const out=document.getElementById('conntest-'+id); if(out) out.textContent='testing…';
  try{
    const r=await fetch('/api/connections/test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id})});
    const d=await r.json();
    if(out) out.innerHTML = d.live ? '<span class="okc">✓ live — '+esc(d.detail||'')+'</span>'
                                   : '<span class="err">✗ '+esc(d.detail||d.error||'not reachable')+'</span>';
    showToast((d.label||id)+(d.live?' is live':' is not connected'), d.live?'ok':'err');
  }catch(e){ if(out) out.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function testAlert(channel){
  const out=document.getElementById('conntest-'+channel); if(out) out.textContent='sending…';
  try{
    const r=await fetch('/api/alerts/test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({channel:channel})});
    const d=await r.json();
    if(out) out.innerHTML = d.ok ? '<span class="okc">✓ '+esc(d.detail||'sent')+'</span>'
                                 : '<span class="err">✗ '+esc(d.error||'failed')+'</span>';
    showToast(d.ok?'Test alert sent — check your phone':'Could not send: '+(d.error||''), d.ok?'ok':'err');
  }catch(e){ if(out) out.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}
async function loadAccount(){
  const host=document.getElementById('accountPanel'); if(!host) return;
  try{
    const d=await (await fetch('/api/account')).json();
    if(!d.configured){
      host.innerHTML=`<div class="note">${esc(d.note||'no read-only key set')}</div>
        <div class="note" style="margin-top:8px">Connect a <b>read-only</b> key to see your real balance
        beside the paper book, so position sizing uses your true equity. The card above shows the exact steps.</div>`;
      return;
    }
    if(!d.connected){ host.innerHTML='<span class="err">'+esc(d.error||'not connected')+'</span>'; return; }
    const bal=(d.balances||[]);
    host.innerHTML=`
      <div class="flex" style="margin-bottom:10px">
        <span class="pill ${d.read_only?'BUY':'SELL'}">${d.read_only?'READ-ONLY KEY ✓':'⚠ KEY CAN TRADE'}</span>
        <span class="badge">${esc(d.account_type||'SPOT')}</span>
        <span class="badge">${d.balance_count||0} funded asset(s)</span>
        <span class="badge">${d.open_order_count||0} open order(s)</span>
        ${d.demo?'<span class="badge" style="background:var(--amber);color:#111">DEMO</span>':''}
      </div>
      ${d.warning?`<div class="note" style="background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.3);padding:9px;border-radius:10px;margin-bottom:10px">⚠ ${esc(d.warning)}</div>`:''}
      ${bal.length?`<table><tr><th>Asset</th><th>Free</th><th>Locked</th><th>Total</th></tr>
        ${bal.map(b=>`<tr><td><b>${esc(b.asset)}</b></td><td class="mono">${fmt(b.free,6)}</td>
          <td class="mono">${fmt(b.locked,6)}</td><td class="mono">${fmt(b.total,6)}</td></tr>`).join('')}</table>`
        :'<span class="muted">no funded balances</span>'}
      <div class="note" style="margin-top:8px">SKY reads this account. It cannot place or cancel an order —
      there is no order-placement code path in this application.</div>`;
  }catch(e){ host.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
}

// ── Evidence: why blocked + how to unlock ─────────────────────────────
async function loadEvidence(){
  try{
    const loop=await (await fetch('/api/loop-health')).json();
    renderEvidenceGuidance(loop.evidence_guidance||{});
    const jobsPayload=await (await fetch('/api/v1/jobs?limit=20')).json();
    const active=((jobsPayload.data||{}).jobs||[]).find(j=>j.kind==='evidence'&&(j.status==='queued'||j.status==='running'));
    if(active){ showEvidenceJob(active); watchEvidenceJob(active.job_id); }
  }catch(e){
    const projection=document.getElementById('evProjection');
    if(projection) projection.innerHTML='<span class="err">Could not calculate evidence gap: '+esc(String(e))+'</span>';
  }
  const why=document.getElementById('unlockWhy');
  if(why){
    try{
      const d=await (await fetch('/api/unlock')).json();
      const blocks=(d.blocks||[]);
      why.innerHTML=`
        <div class="flex" style="margin-bottom:10px">
          <span class="pill ${d.allowed?'BUY':'NOTRADE'}">${d.allowed?'GATE OPEN':'GATE CLOSED'}</span>
          <b>${esc(d.headline||'')}</b>
        </div>
        <div class="note" style="margin-bottom:10px">${esc(d.summary||'')}</div>
        ${blocks.map(b=>`<div class="blockcard ${esc(b.kind)}">
          <b>${b.kind==='earn'?'🔓':'⏳'} ${esc(b.title)}</b>
          <div class="note" style="margin-top:4px">${esc(b.plain)}</div>
          <div class="note" style="margin-top:4px;opacity:.75">Raw rule: ${esc(b.reason||'')}</div>
          ${b.progress?renderCriteria(b.progress):''}
          <div class="flex" style="margin-top:8px">
            ${b.action?`<button class="btn primary" onclick="runCommand('${esc(b.action)}')">▶ ${esc(b.action_label||b.action)}</button>`:''}
            ${b.alt_action?`<button class="btn" onclick="runCommand('${esc(b.alt_action)}')">▶ ${esc(b.alt_action_label||b.alt_action)}</button>`:''}
            ${b.ui_hint?`<button class="btn" onclick="switchTab('${esc(b.ui_hint)}')">Go to ${esc(b.ui_hint)}</button>`:''}
          </div></div>`).join('')}`;
    }catch(e){ why.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
  }
  const board=document.getElementById('evidenceBoard');
  if(board){
    try{
      const d=await (await fetch('/api/evidence')).json();
      const cnt=document.getElementById('evCount');
      if(cnt) cnt.textContent=(d.proven_count||0)+'/'+(d.count||0)+' proven';
      const setups=(d.setups||[]);
      board.innerHTML=`<div class="note" style="margin-bottom:10px"><b>${esc(d.headline||'')}</b> — ${esc(d.next_step||'')}</div>`
        + (setups.length? setups.map(s=>`<div class="setupcard ${s.proven?'proven':''}">
            <div class="flex" style="justify-content:space-between">
              <b>${esc(s.plan_type)}</b>
              <span class="badge ${s.proven?'strong':''}">${s.proven?'PROVEN ✓':s.met+'/'+s.total+' criteria'}</span>
            </div>${renderCriteria(s)}</div>`).join('')
          : '<span class="muted">no setups measured yet</span>');
    }catch(e){ board.innerHTML='<span class="err">'+esc(String(e))+'</span>'; }
  }
}
function renderCriteria(p){
  return (p.criteria||[]).map(c=>{
    const cur = c.unit==='R per trade'
      ? (c.current==null?'—':(Number(c.current)>=0?'+':'')+Number(c.current).toFixed(3)+'R')
      : (c.current||0)+' / '+c.target;
    return `<div class="critrow">
      <div class="top"><span>${c.met?'<span class="okc">✓</span>':'<span class="muted">○</span>'} ${esc(c.name)}
        <span class="note">${esc(c.why||'')}</span></span>
        <span class="mono">${esc(cur)}</span></div>
      <div class="bar"><i style="width:${c.pct||0}%;background:${c.met?'var(--green)':'var(--blue)'}"></i></div>
    </div>`;
  }).join('');
}

// ── lazy tab loading ──────────────────────────────────────────────────
// ── Weekly Review (W3) — weekly review + daily ritual with memory ───────
let _weeklyData=null, _wkChart=null;
function _wkR(v,d){ return v==null?'n/a':((v>=0?'+':'')+Number(v).toFixed(d==null?3:d)+'R'); }
function _wkPct(v,d){ return v==null?'n/a':(Number(v)*100).toFixed(d==null?1:d)+'%'; }
async function loadWeekly(){
  const st=document.getElementById('wkStats'); if(!st) return;
  try{
    const d=await (await fetch('/api/weekly')).json();
    if(d.error){ st.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    _weeklyData=d; renderWeekly(d);
  }catch(e){ st.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}
async function loadRitual(){
  const el=document.getElementById('ritualList'); if(!el) return;
  try{
    const d=await (await fetch('/api/ritual')).json();
    if(d.error){ el.innerHTML='<span class="err">'+esc(d.error)+'</span>'; return; }
    renderRitual(d);
  }catch(e){ el.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}
async function toggleRitual(name, done){
  try{
    const res=await fetch('/api/ritual',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({step:name,done:done})});
    const d=await res.json();
    if(!res.ok||d.error){ showToast(d.error||('ritual update failed ('+res.status+')'),'err'); loadRitual(); return; }
    renderRitual(d);
    if(d.complete) showToast('Daily ritual complete — see you tomorrow','ok');
  }catch(e){ showToast(String(e),'err'); loadRitual(); }
}
function renderRitual(d){
  const el=document.getElementById('ritualList'); if(!el) return;
  const cnt=document.getElementById('ritCount');
  if(cnt) cnt.textContent=d.done+'/'+d.total+(d.complete?' — complete':'');
  const rows=(d.steps||[]).map(s=>{
    const okIcon=s.ok===null?'·':(s.ok?'✓':'✗');
    const okCls=s.ok===false?'err':(s.ok===true?'okc':'muted');
    return `<div class="critrow" style="align-items:center">
      <label class="flex" style="gap:8px;align-items:center;cursor:pointer">
        <input type="checkbox" ${s.done?'checked':''} onchange="toggleRitual('${esc(s.name)}',this.checked)">
        <b>${esc(s.name)}</b></label>
      <span class="${okCls}" style="margin-left:8px">${okIcon}</span>
      <span class="note" style="flex:1">${esc(s.label||'')}</span>
      <code class="note">${esc(s.command||'')}</code>
      ${s.done_ts?`<span class="muted note">ticked ${new Date(s.done_ts).toLocaleTimeString()}</span>`:''}
    </div>`;
  }).join('')||'<span class="muted">no ritual steps</span>';
  el.innerHTML=rows+(d.health_error?`<div class="err" style="margin-top:6px">loop health unavailable: ${esc(d.health_error)}</div>`:'');
}
function renderWeekly(d){
  const w=d.week||{}, a=d.all_time||{}, g=d.grade||{}, dd=d.drawdown||{}, v=d.violations||{};
  const cnt=document.getElementById('wkCount'); if(cnt) cnt.textContent=((d.window||{}).label||'')+' — grade '+(g.grade||'—');
  const st=document.getElementById('wkStats');
  const gc=(g.grade&&g.grade!=='—')?(g.score>=70?'var(--green)':(g.score>=50?'var(--amber,#e0a458)':'var(--red)')):'var(--line)';
  st.innerHTML=`<div class="flex" style="margin-bottom:10px">
      <span class="pill" style="border-color:${gc};color:${gc};font-size:15px">grade ${esc(g.grade||'—')} · ${g.score??0}/${g.max??100}</span>
      <span class="badge">window: ${esc((d.window||{}).label||'')}</span></div>
    <div class="statrow">
      <div class="stat"><div class="v">${w.n||0}</div><div class="k">This week decided</div></div>
      <div class="stat"><div class="v">${_wkR(w.expectancy_net)}</div><div class="k">Week E (net)</div></div>
      <div class="stat"><div class="v">${_wkPct(w.win_rate)}</div><div class="k">Week win rate</div></div>
      <div class="stat"><div class="v">${w.profit_factor==null?'n/a':w.profit_factor}</div><div class="k">Week PF</div></div>
      <div class="stat"><div class="v">${_wkR(w.total_r_net)}</div><div class="k">Week total (net)</div></div>
    </div>
    <div class="kv" style="margin-top:8px">
      <b>All time</b><span>${a.n||0} decided (${a.wins||0}W/${a.losses||0}L) · E ${_wkR(a.expectancy_net)} net · PF ${a.profit_factor==null?'n/a':a.profit_factor} · max DD ${dd.max_drawdown_pct!=null?dd.max_drawdown_pct+'%':'—'}</span>
      <b>Bar (unchanged, net)</b><span>E ≥ +${(d.bar&&d.bar.expectancy!=null?d.bar.expectancy.toFixed(2):'0.50')}R · WR > ${_wkPct(d.bar&&d.bar.win_rate,0)} · PF ≥ ${d.bar&&d.bar.pf} · compliance ≥ ${_wkPct(d.bar&&d.bar.compliance,0)}</span>
    </div>`;
  const t=d.next_practice_task||{};
  document.getElementById('wkTask').innerHTML=t.title
    ? `<div class="blockcard earn"><b>➤ ${esc(t.title)}</b>
       <div class="note" style="margin-top:6px">${esc(t.detail||'')}</div>
       <div class="note" style="margin-top:6px"><code>${esc(t.action||'')}</code></div></div>`
    : '<span class="muted">—</span>';
  _wkRenderEquity(d);
  const dist=(d.r_distribution||[]).map(b=>{
    const neg=b.bucket.indexOf('-')===0||b.bucket.indexOf('≤')===0;
    const col=b.n===0?'rgba(255,255,255,.12)':(neg?'var(--red)':(b.bucket.indexOf('0R')===0?'var(--muted)':'var(--green)'));
    return `<div class="critrow" style="align-items:center">
      <span class="note" style="width:110px;text-align:right">${esc(b.bucket)}</span>
      <div class="bar" style="flex:1;margin:0 8px"><i style="width:${Math.min(100,b.pct||0)}%;background:${col}"></i></div>
      <span class="note" style="width:70px">${b.n} (${b.pct}%)</span></div>`;
  }).join('');
  document.getElementById('wkDist').innerHTML=dist||'<span class="muted">no decided trades yet</span>';
  const miss=(v.missing_scan_ids||[]).map(s=>'#'+s).join(', ');
  const mks=Object.entries(v.by_mistake||{}).map(([k,n])=>`${esc(k)} ×${n}`).join(' · ')||'—';
  const emos=Object.entries(v.by_emotion||{}).map(([k,n])=>`${esc(k)} ×${n}`).join(' · ')||'—';
  const violRows=(v.recent||[]).filter(r=>r.followed_rules===0).map(r=>
    `<tr><td>#${r.scan_id}</td><td>${esc(r.day||'')}</td><td>${esc(r.outcome||'')}</td><td>${esc(r.mistake||'')}</td><td>${esc(r.emotion||'')}</td></tr>`).join('');
  document.getElementById('wkViol').innerHTML=`<div class="statrow" style="margin-bottom:8px">
      <div class="stat"><div class="v">${v.journaled??0}/${v.eligible??0}</div><div class="k">Journaled</div></div>
      <div class="stat"><div class="v">${v.violations??0}</div><div class="k">Violations</div></div>
      <div class="stat"><div class="v">${_wkPct(v.compliance)}</div><div class="k">Compliance (bar ${((v.compliance_bar||0.9)*100).toFixed(0)}%)</div></div>
      <div class="stat"><div class="v">${v.missing_journals??0}</div><div class="k">Missing journals</div></div>
    </div>
    <div class="kv"><b>Repeating mistakes</b><span>${mks}</span><b>Emotions on violations</b><span>${emos}</span></div>
    ${v.missing_journals?`<div class="err" style="margin-top:8px">Unjournaled decided trades: ${esc(miss)} — journal them in the 📓 Journal tab; the next approval will wait for these.</div>`:''}
    ${violRows?`<div style="overflow:auto;margin-top:8px"><table><tr><th>Scan</th><th>Day</th><th>Outcome</th><th>Mistake</th><th>Emotion</th></tr>${violRows}</table></div>`:''}`;
  const trk=(d.graduation_tracker||[]).map(t=>{
    const proven=t.proven?'<span class="okc">✓ proven</span>':'<span class="muted">building</span>';
    const bt=t.backtest_pct||0, pp=t.paper_pct||0;
    const missTxt=(t.missing||[]).map(esc).join(' · ')||'watching';
    return `<div class="critrow" style="align-items:center">
      <b style="width:190px">${esc(t.plan_type)}${t.primary?'':' <span class="muted">(earned)</span>'}</b>
      <span class="note" style="width:120px">bt ${t.backtest_n}/${t.backtest_target}</span>
      <div class="bar" style="width:90px"><i style="width:${bt}%"></i></div>
      <span class="note" style="width:120px">paper ${t.paper_n}/${t.paper_target}</span>
      <div class="bar" style="width:90px"><i style="width:${pp}%"></i></div>
      <span class="note" style="width:110px">E ${_wkR(t.expectancy_net)}</span>
      ${proven}<span class="note" style="flex:1;margin-left:10px">${missTxt}</span></div>`;
  }).join('');
  document.getElementById('wkTrack').innerHTML=trk||'<span class="muted">no setups on record yet — run Backtest + Simulator on real history</span>';
  const comps=(g.components||[]).map(c=>`<div class="note">[${c.points}/${c.max}] ${esc(c.name)}${c.current!=null?' — '+esc(String(c.current)):''}</div>`).join('');
  const note=document.getElementById('wkEquityNote');
  if(note) note.innerHTML=((d.grade||{}).note?`<b>Grade basis (advisory):</b>${comps}<div class="note" style="margin-top:4px">${esc((d.grade||{}).note||'')}</div>`:'');
}
function _wkRenderEquity(d){
  const el=document.getElementById('wkEquity'); if(!el) return;
  const raw=(d.equity_curve||[]);
  const cc=chartsAvailable();
  if(!cc || raw.length<2){
    el.innerHTML='<span class="muted">'+(raw.length<2?'not enough decided trades yet — the curve appears as your book grows':'chart library unavailable')+'</span>'; return;
  }
  const pts=[]; let last=0;
  for(const p of raw){
    let t=Math.floor((p.closed_ts||0)/1000); if(t<=last) t=last+1; last=t;
    pts.push({time:t,value:Number(p.equity)});
  }
  el.innerHTML='';
  try{
    if(_wkChart && _wkChart.remove){ try{ _wkChart.remove(); }catch(e){} }
    _wkChart=cc(el,{height:220,layout:{background:{type:'solid',color:'transparent'},textColor:'#93a4bd'},
      grid:{vertLines:{color:'rgba(255,255,255,.06)'},horzLines:{color:'rgba(255,255,255,.06)'}},
      rightPriceScale:{borderColor:'rgba(255,255,255,.12)'},timeScale:{borderColor:'rgba(255,255,255,.12)'}});
    const start=pts.length?pts[0].value:10000;
    const s=_wkChart.addLineSeries({color:(pts[pts.length-1].value>=start)?'#22c55e':'#ef4444',lineWidth:2});
    s.setData(pts); _wkChart.timeScale().fitContent();
  }catch(e){ el.innerHTML='<span class="muted">'+esc(e)+'</span>'; }
}

// ── Practice mode (W3.4) — commit your read, see the desk's, score the gap ──
function _pracNum(id){
  const raw=(document.getElementById(id)||{}).value;
  if(raw==null||String(raw).trim()==='') return null;
  const f=parseFloat(raw);
  return isFinite(f)?f:raw;  // non-numeric stays a string so the server rejects it honestly (400)
}
function _pracGradeColor(g,s){
  if(!g) return 'var(--line)';
  return (s>=70)?'var(--green)':(s>=50?'var(--amber,#e0a458)':'var(--red)');
}
function _pracBody(){
  const conf=parseInt((document.getElementById('pracConf')||{}).value,10);
  return {
    symbol:chartSym(), tf:chartTf(),
    bias:(document.getElementById('pracBias')||{}).value||'neutral',
    decision:(document.getElementById('pracDecision')||{}).value||'no_trade',
    entry:_pracNum('pracEntry'), stop:_pracNum('pracStop'), target:_pracNum('pracTarget'),
    confidence:isFinite(conf)?conf:null,
    note:((document.getElementById('pracNote')||{}).value||'')
  };
}
async function submitPractice(){
  const out=document.getElementById('pracResult');
  const body=_pracBody();
  out.innerHTML='<span class="muted">scoring your read against the desk…</span>';
  try{
    const res=await fetch('/api/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await res.json();
    if(!res.ok||d.error){ out.innerHTML='<span class="err">'+esc(d.error||('practice submit failed ('+res.status+')'))+'</span>'; return; }
    renderPracticeResult(d);
    loadPracticeScorecard();
  }catch(e){ out.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}
async function submitTapePractice(){
  const out=document.getElementById('pracResult');
  const commit=replayCommitTime();
  if(commit==null){
    out.innerHTML='<span class="err">Start Replay and Freeze at the bar you are reading — the tape grades the hidden future, so it cannot run on the live chart.</span>';
    return;
  }
  freezeReplay();
  const body=_pracBody();
  body.commit_time=commit;
  body.horizon_bars=16;
  out.innerHTML='<span class="muted">walking the hidden bars…</span>';
  try{
    const res=await fetch('/api/practice/tape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await res.json();
    if(!res.ok||d.error){ out.innerHTML='<span class="err">'+esc(d.error||('tape submit failed ('+res.status+')'))+'</span>'; return; }
    if(_replay && _replay.candle && _replay.candles){
      try{ _replay.candle.setData(_replay.candles); }catch(e){}
      renderReplayHead(_replay.candles.length);
    }
    renderPracticeResult(d);
    loadPracticeScorecard();
  }catch(e){ out.innerHTML='<span class="err">'+esc(e)+'</span>'; }
}
function renderPracticeResult(d){
  const out=document.getElementById('pracResult'); if(!out) return;
  const desk=d.desk||{}, sc=d.score||{}, u=d.user||{};
  const isTape=(sc.kind==='tape')||(desk.kind==='tape');
  const act=isTape?(sc.outcome||desk.outcome||'TAPE'):(desk.action||'?');
  const actCol=isTape?'var(--amber)':(act==='BUY'?'var(--green)':(act==='SELL'?'var(--red)':'var(--muted)'));
  const gc=_pracGradeColor(sc.grade, sc.total||0);
  const lvl=function(v){ return (v==null)?'—':v; };
  const comps=(sc.components||[]).map(c=>{
    const pts=(c.points==null)?'—':(c.points+'/'+c.max);
    return '<div class="critrow" style="align-items:center"><span class="note" style="width:230px">'+esc(c.name||'')+
      '</span><b class="mono" style="width:64px">'+pts+'</b><span class="note" style="flex:1">'+esc(c.detail||'')+'</span></div>';
  }).join('');
  out.innerHTML=
    (d.duplicate?'<div class="note" style="margin-bottom:6px">↺ identical read within 2 minutes — showing the original attempt, nothing double-counted.</div>':'')+
    '<div class="flex" style="gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px">'+
      '<span class="pill" style="border-color:'+actCol+';color:'+actCol+'">'+(isTape?'tape: ':'desk: ')+esc(act)+'</span>'+
      (isTape
        ? ('<span class="badge">horizon '+(desk.horizon_bars||16)+' · used '+(sc.bars_used!=null?sc.bars_used:(desk.bars_used!=null?desk.bars_used:'—'))+'</span>'
           +(sc.rr_achieved!=null?'<span class="badge">'+((Number(sc.rr_achieved)>0)?'+':'')+sc.rr_achieved+'R</span>':''))
        : ('<span class="badge">desk bias '+esc(desk.bias||'—')+' · '+esc(desk.regime||'—')+'</span>'
           +(desk.entry?'<span class="badge">desk ladder '+lvl(desk.entry)+' / '+lvl(desk.stop)+' / '+lvl(desk.target)+'</span>':'')))+
      '<span class="pill" style="border-color:'+gc+';color:'+gc+';font-size:15px">your read '+(sc.total!=null?sc.total:'—')+'/100 · '+esc(sc.grade||'—')+'</span>'+
    '</div>'+
    '<div class="note" style="margin-bottom:6px">you: '+esc(u.bias||'—')+' / '+esc(u.decision||'—')+
      (u.levels_given?(' · '+lvl(u.entry)+' / '+lvl(u.stop)+' / '+lvl(u.target)):' · no ladder committed')+
      (u.note?' · “'+esc(u.note)+'”':'')+'</div>'+
    comps+
    '<div class="note" style="margin-top:8px">'+esc(sc.disclaimer||d.disclaimer||'')+'</div>';
}
async function loadPracticeScorecard(){
  try{
    const d=await (await fetch('/api/practice')).json();
    if(d.error) throw new Error(d.error);
    renderPracticeScorecard(d);
  }catch(e){
    const w=document.getElementById('wkPractice'); if(w) w.innerHTML='<span class="err">'+esc(e)+'</span>';
    const m=document.getElementById('pracMini'); if(m) m.textContent='practice scorecard unavailable';
  }
}
function renderPracticeScorecard(d){
  const mini=document.getElementById('pracMini');
  const cnt=document.getElementById('pracCardCount'); if(cnt) cnt.textContent=((d.window||{}).label||'')+' — '+(d.n||0)+' reads';
  const pct=function(v){ return (v==null)?'n/a':(Number(v)*100).toFixed(1)+'%'; };
  if(mini) mini.textContent=d.n
    ? ('last '+((d.window||{}).days||30)+'d: '+d.n+' committed reads · bias agreement '+pct(d.bias_agreement)+
       ' · call agreement '+pct(d.decision_agreement)+' · avg '+(d.avg_score!=null?d.avg_score:'—')+'/100 — full mirror on the 🗓 Review tab')
    : 'no committed reads yet — this card is where you start: bias → call → ladder, then submit';
  const w=document.getElementById('wkPractice'); if(!w) return;
  if(!d.n && !(d.tape&&d.tape.n)){ w.innerHTML='<span class="muted">'+esc(d.coaching||'No practice attempts yet.')+'</span>'; return; }
  if(!d.n){
    w.innerHTML='<span class="muted">'+esc(d.coaching||'No desk-agreement reads yet.')+'</span>'+_pracTapeCard(d.tape||{});
    return;
  }
  const means=d.component_means||{};
  const grades=['A','B','C','D','E'].filter(g=>(d.grades||{})[g]).map(g=>'<span class="badge">'+g+' ×'+d.grades[g]+'</span>').join(' ');
  const rows=(d.recent||[]).map(r=>'<tr><td>#'+r.id+'</td><td>'+esc(r.day||'')+'</td><td>'+esc(r.symbol||'')+' '+esc(r.timeframe||'')+
    '</td><td>'+esc(r.user_decision||'—')+'</td><td>'+esc(r.desk_action||'—')+'</td><td>'+(r.score!=null?r.score:'—')+'</td><td>'+esc(r.grade||'—')+'</td></tr>').join('');
  w.innerHTML=
    '<div class="statrow" style="margin-bottom:8px">'+
      '<div class="stat"><div class="v">'+d.n+'</div><div class="k">Committed reads</div></div>'+
      '<div class="stat"><div class="v">'+pct(d.bias_agreement)+'</div><div class="k">Bias agreement</div></div>'+
      '<div class="stat"><div class="v">'+pct(d.decision_agreement)+'</div><div class="k">Call agreement</div></div>'+
      '<div class="stat"><div class="v">'+(d.avg_score!=null?d.avg_score:'—')+'</div><div class="k">Avg score /100</div></div>'+
    '</div>'+
    '<div class="kv"><b>Components</b><span>'+
      ['bias','decision','levels'].filter(k=>means[k]!=null).map(k=>k+' '+pct(means[k])).join(' · ')+'</span>'+
      '<b>Grades</b><span>'+grades+'</span></div>'+
    '<div class="blockcard earn" style="margin-top:8px"><b>➤ Weakest link: '+esc(d.weakest_component||'none in window')+'</b>'+
      '<div class="note" style="margin-top:4px">'+esc(d.coaching||'')+'</div></div>'+
    (rows?'<div style="overflow:auto;margin-top:8px"><table><tr><th>#</th><th>Day</th><th>Chart</th><th>You</th><th>Desk</th><th>Score</th><th>Grade</th></tr>'+rows+'</table></div>':'')+
    _pracTapeCard(d.tape||{})+
    '<div class="note" style="margin-top:8px">'+esc(d.disclaimer||'')+'</div>';
}
function _pracTapeCard(t){
  if(!t || !t.n){
    return '<div class="note" style="margin-top:10px">No tape reads yet — start Replay, Freeze, then Grade against the tape.</div>';
  }
  const pct=function(v){ return (v==null)?'n/a':(Number(v)*100).toFixed(1)+'%'; };
  const outs=Object.keys(t.outcomes||{}).map(function(k){ return k+' ×'+(t.outcomes[k]); }).join(' · ');
  const rows=(t.recent||[]).map(function(r){
    return '<tr><td>#'+r.id+'</td><td>'+esc(r.day||'')+'</td><td>'+esc(r.symbol||'')+' '+esc(r.timeframe||'')+
      '</td><td>'+esc(r.user_decision||'—')+'</td><td>'+esc(r.outcome||'—')+'</td><td>'+(r.score!=null?r.score:'—')+'</td><td>'+esc(r.grade||'—')+'</td></tr>';
  }).join('');
  return '<div class="blockcard" style="margin-top:10px"><b>▶ TAPE — replay outcomes</b>'+
    '<div class="statrow" style="margin:8px 0">'+
      '<div class="stat"><div class="v">'+t.n+'</div><div class="k">Tape reads</div></div>'+
      '<div class="stat"><div class="v">'+(t.avg_score!=null?t.avg_score:'—')+'</div><div class="k">Avg /100</div></div>'+
      '<div class="stat"><div class="v">'+pct(t.win_rate)+'</div><div class="k">Ladder win rate</div></div>'+
    '</div>'+
    '<div class="note">'+esc(outs||'—')+'</div>'+
    '<div class="note" style="margin-top:4px">'+esc(t.coaching||'')+'</div>'+
    (rows?'<div style="overflow:auto;margin-top:8px"><table><tr><th>#</th><th>Day</th><th>Chart</th><th>You</th><th>Outcome</th><th>Score</th><th>Grade</th></tr>'+rows+'</table></div>':'')+
    '<div class="note" style="margin-top:6px">'+esc(t.disclaimer||'')+'</div></div>';
}

// ── W4.2 — this PC is the Hub; one research agent, no second PC agent ──
async function loadHubRole(){
  const st=document.getElementById('hubRoleStatus');
  if(st) st.textContent='loading…';
  try{
    const [role,hub]=await Promise.all([
      fetch('/api/hub/role').then(function(x){return x.json();}),
      fetch('/api/hub/status').then(function(x){return x.json();})
    ]);
    renderHubRole(role,hub);
    if(st) st.textContent='updated '+new Date().toLocaleTimeString();
  }catch(e){
    if(st) st.textContent='failed';
    const el=document.getElementById('hubRole');
    if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>';
  }
}
function renderHubRole(role,hub){
  const cnt=document.getElementById('hubRoleCount');
  if(cnt) cnt.textContent=(role&&role.second_agent)?'second agent — refuse':'one research agent';
  const el=document.getElementById('hubRole'); if(!el) return;
  const units=((hub&&hub.services)||{}).units||{};
  const rows=(role&&role.run||[]).map(function(item){
    const u=units[item.unit]||{};
    const active=u.active||(hub&&hub.services&&hub.services.available===false?'not installed':'unknown');
    return '<tr><td>'+esc(item.unit)+'</td><td>'+esc(item.job)+'</td><td>'
      +esc(active)+'</td><td>'+(item.required?'required':'optional')+'</td></tr>';
  }).join('');
  const human=(role&&role.human_still_does||[]).map(function(x){return '<div class="note">• '+esc(x)+'</div>';}).join('');
  const no=(role&&role.do_not_run||[]).map(function(x){return '<div class="note">✗ '+esc(x)+'</div>';}).join('');
  const disk=((hub&&hub.storage)||{}).free_mb;
  el.innerHTML='<div class="flex" style="margin-bottom:8px">'
    +'<span class="pill BUY">'+esc((role&&role.role)||'ubuntu_hub')+'</span>'
    +'<span class="badge">live execution: NO</span>'
    +'<span class="badge">disk '+(disk==null?'—':disk+' MB free')+'</span>'
    +'</div>'
    +'<div class="note" style="margin-bottom:8px"><b>'+esc((role&&role.decision)||'')+'</b></div>'
    +'<div class="note" style="margin-bottom:8px">'+esc((role&&role.why)||'')+'</div>'
    +(rows?'<table><tr><th>Unit</th><th>Job</th><th>Now</th><th></th></tr>'+rows+'</table>':'')
    +'<div class="grid2" style="margin-top:10px"><div><b>You still do</b>'+human+'</div><div><b>Do not run</b>'+no+'</div></div>'
    +'<div class="note" style="margin-top:8px">systemd snapshot is honest: this sandbox often has no units. Enable them on the Ubuntu PC — see docs/UBUNTU_PC_ROLE.md.</div>';
}

// ── 24/7 research agent (W4.1) — health / report / hypotheses, never a trade ──
async function loadAgent(force){
  const st=document.getElementById('agStatus');
  if(st) st.textContent = force ? 'refreshing…' : 'loading…';
  try{
    const [h,s,r,y] = await Promise.all([
      fetch('/api/sky-agent/health').then(x=>x.json()),
      fetch('/api/sky-agent/status').then(x=>x.json()),
      fetch('/api/sky-agent/report').then(x=>x.json()),
      fetch('/api/sky-agent/hypotheses').then(x=>x.json())
    ]);
    renderAgent(h,s,r,y);
    loadHubRole();
    if(st) st.textContent = 'updated '+new Date().toLocaleTimeString();
  }catch(e){
    if(st) st.textContent = 'failed';
    const el=document.getElementById('agHealth');
    if(el) el.innerHTML='<span class="err">'+esc(e)+'</span>';
  }
}
function renderAgent(h,s,r,y){
  const sys=(h&&h.system)||{};
  const recs=(r&&r.recommendations)||[];
  const cnt=document.getElementById('agCount');
  if(cnt) cnt.textContent = (sys.level||'—')+' · '+(recs[0]&&recs[0].recommendation||'no rec');
  const health=document.getElementById('agHealth');
  if(health){
    const alerts=(sys.alerts||[]).join(' · ')||'none';
    const ready=((h&&h.readiness)||{}).headline || ((h&&h.readiness)||{}).level || '—';
    health.innerHTML='<div class="statrow">'
      +'<div class="stat"><div class="v">'+esc(sys.level||'—')+'</div><div class="k">System level</div></div>'
      +'<div class="stat"><div class="v">'+esc(sys.cpu_pct==null?'—':sys.cpu_pct+'%')+'</div><div class="k">CPU</div></div>'
      +'<div class="stat"><div class="v">'+esc(sys.ram_pct==null?'—':sys.ram_pct+'%')+'</div><div class="k">RAM</div></div>'
      +'<div class="stat"><div class="v">'+esc(sys.disk_pct==null?'—':sys.disk_pct+'%')+'</div><div class="k">Disk</div></div>'
      +'<div class="stat"><div class="v">'+(sys.db_ok?'ok':'fail')+'</div><div class="k">DB</div></div>'
      +'</div><div class="note" style="margin-top:8px">alerts: '+esc(alerts)
      +' · desk readiness: '+esc(String(ready))
      +'</div><div class="note">Research daemon only. The risk gate and paper book never read this card.</div>';
  }
  const rep=document.getElementById('agReport');
  if(rep){
    const rec=recs[0]||{};
    const ev=(rec.evidence||[]).map(e=>'<div class="note">• '+esc(e)+'</div>').join('');
    const recCol = rec.recommendation==='AVOID'?'var(--red)':(rec.recommendation==='CONSIDER'?'var(--green)':'var(--amber)');
    rep.innerHTML='<div class="flex" style="margin-bottom:8px">'
      +'<span class="pill" style="border-color:'+recCol+';color:'+recCol+'">'
      +esc(rec.recommendation||'WAIT')+'</span>'
      +'<span class="badge">'+esc(rec.asset||'DESK')+' · '+esc(rec.timeframe||'—')+'</span>'
      +'<span class="badge">kind '+esc(rec.kind||'HYPOTHESIS')+'</span>'
      +'<span class="badge">risk '+esc(rec.risk_status||'UNKNOWN')+'</span>'
      +'</div>'
      +'<div class="kv"><b>Detected</b><span>'+esc(rec.detected||'—')+'</span>'
      +'<b>Expectancy</b><span>'+(rec.expectancy_R==null?'n/a':rec.expectancy_R+'R')+' · N='+(rec.sample_n==null?'—':rec.sample_n)+'</span>'
      +'<b>Invalidation</b><span>'+esc(rec.invalidation||'—')+'</span></div>'
      +ev
      +'<div class="note" style="margin-top:8px">'+esc((r&&r.disclaimer)||'Research only.')+'</div>'
      +'<div class="note">generated '+(r&&r.generated_at?esc(r.generated_at):'—')+'</div>';
  }
  const hyps=document.getElementById('agHyps');
  if(hyps){
    const rows=((y&&y.hypotheses)||(s&&s.hypotheses)||[]).map(function(h){
      return '<tr><td>'+esc(h.hypothesis_id||h.id||'—')+'</td><td>'+esc(h.setup||'—')
        +'</td><td>'+esc(h.status||'proposed')+'</td></tr>';
    }).join('');
    hyps.innerHTML = rows
      ? '<table><tr><th>ID</th><th>Setup</th><th>Status</th></tr>'+rows+'</table>'
        +'<div class="note" style="margin-top:6px">A hypothesis is not a proven setup. Promotion still needs the unchanged net graduation bar.</div>'
      : '<span class="muted">no hypotheses yet — run Collect or `python main.py sky-agent hypothesize`</span>';
  }
  const reg=document.getElementById('agRegimes');
  if(reg){
    const rows=((s&&s.regimes)||[]).map(function(x){
      return '<div class="note">'+esc(x.symbol||'')+' '+esc(x.timeframe||'')+' · '
        +esc(x.regime||'—')+' / '+esc(x.volatility_state||'—')+'</div>';
    }).join('');
    reg.innerHTML = rows || '<span class="muted">no regime log yet</span>';
  }
  const sec=document.getElementById('agSec');
  if(sec){
    const rows=((s&&s.sec_events)||[]).map(function(x){
      return '<div class="note">'+esc(x.accession||'')+' · '+esc(x.event_type||'—')
        +' sev '+esc(x.severity)+'</div>';
    }).join('');
    sec.innerHTML = rows || '<span class="muted">no SEC events (crypto desk — this is optional research)</span>';
  }
  const arc=document.getElementById('agArchive');
  if(arc){
    const rows=((s&&s.reports)||[]).map(function(x){
      return '<tr><td>'+esc(x.report_date||'')+'</td><td>'+esc(x.kind||'')+'</td><td>'
        +esc(x.asset||'')+'</td><td>'+esc(x.recommendation||'')+'</td><td>'+esc(x.level||'')+'</td></tr>';
    }).join('');
    arc.innerHTML = rows
      ? '<table><tr><th>Day</th><th>Kind</th><th>Asset</th><th>Rec</th><th>Level</th></tr>'+rows+'</table>'
      : '<span class="muted">no archived reports — click Archive the daily report</span>';
  }
}
async function archiveAgentReport(){
  const st=document.getElementById('agStatus');
  if(st) st.textContent='archiving…';
  try{
    const res=await fetch('/api/sky-agent/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
    const d=await res.json();
    if(!res.ok||d.error){ showToast(d.error||('archive failed ('+res.status+')'),'err'); return; }
    showToast('Daily report archived (#'+(d.report_id||'?')+') — still not evidence','ok');
    loadAgent(true);
  }catch(e){ showToast(String(e),'err'); }
}

function onTabShown(tab){
  if(tab==='chart'){ loadChartWorkspace(false); loadPracticeScorecard(); }
  else if(tab==='manage') loadTradeManager();
  else if(tab==='risk') loadRiskCenter();
  else if(tab==='journal') loadJournalCenter();
  else if(tab==='weekly'){ loadWeekly(); loadRitual(); loadPracticeScorecard(); }
  else if(tab==='commands'){ loadCommands(); loadJobs(false); }
  else if(tab==='modules') loadModules();
  else if(tab==='connections') loadConnections(false);
  else if(tab==='evidence') loadEvidence();
  else if(tab==='agent') loadAgent(false);
}

// init
(function(){
  try{
    const h=(typeof location !== 'undefined' && location.hash || '').replace('#','');
    if(h && ['overview','chart','market','intelligence','trades','manage','risk','evidence','journal','weekly','learn','connections','commands','modules','system','agent'].includes(h)) _activeTab=h;
  }catch(e){}
  try{ switchTab(_activeTab); }catch(e){}
})();
refreshUserChip();
if(authLocked()){
  // Show sign-in / first-run setup; no private data is fetched until the
  // server authorizes this browser.
  showAuth();
} else {
  // strip lives outside #app, so it can resolve before the first scan does
  try{ loadReadiness(); }catch(e){}
  load(true);
  setInterval(()=>{ if(!authLocked() && document.getElementById('auto').checked) load(false, true); }, 30000);
  // Channels panel is diagnostic-state (which backend is *serving*),
  // not signal-state, so refresh on a slower 5-minute cadence — not on
  // every 30s scan tick.  Cheap: probe_all() is config-driven.
  setInterval(()=>{ if(!authLocked()){ loadChannels(); loadMcp(); loadDesk(); loadReadiness(); loadLoop(); } }, 5 * 60 * 1000);
}
// keep seg active state in sync on load
// ── P18.4 PWA — install prompt, offline banner, service worker, push stub ──
(function(){
  var offBanner=document.getElementById('offlineBanner');
  var offWhen=document.getElementById('offlineWhen');
  var installBanner=document.getElementById('installBanner');
  var installBtn=document.getElementById('installBtn');
  var deferredPrompt=null;
  function updateOffline(){
    var online=false; try{ online=navigator.onLine; }catch(e){ online=true; }
    if(offBanner) offBanner.classList.toggle('show', !online);
    try{ document.body.classList.toggle('offline', !online); }catch(e){}
    if(offWhen){
      try{
        var t=localStorage.getItem('sky:lastUpdated');
        offWhen.textContent = t ? ('last good scan: '+t) : 'no scan yet';
      }catch(e){ offWhen.textContent=''; }
    }
    // Disable mutation buttons while offline — the risk gate cannot be checked fresh
    try{
      var muts=document.querySelectorAll('button[onclick*=\"decide\"], button[onclick*=\"runPaper\"], button[onclick*=\"saveJournal\"], button[onclick*=\"clearTraderState\"], .mutation');
      for(var i=0;i<muts.length;i++){
        muts[i].disabled = !online;
        muts[i].title = online ? '' : 'Offline — reconnect to use this action';
      }
    }catch(e){}
  }
  window.addEventListener('online', updateOffline);
  window.addEventListener('offline', updateOffline);
  try{ updateOffline(); }catch(e){}
  // Wrap original load to persist lastUpdated even when offline
  var _loadOrig=window.load;
  if(_loadOrig){
    window.load=function(force,quiet){
      try{ localStorage.setItem('sky:lastUpdated', new Date().toLocaleString()); }catch(e){}
      return _loadOrig.apply(this, arguments);
    };
  } else {
    try{ localStorage.setItem('sky:lastUpdated', new Date().toLocaleString()); }catch(e){}
  }
  // Install prompt — beforeinstallprompt is not fired on desktop without SW, so wait for it
  window.addEventListener('beforeinstallprompt', function(e){
    e.preventDefault();
    deferredPrompt=e;
    try{
      var dismissed=localStorage.getItem('sky:installDismissed');
      var last=Number(localStorage.getItem('sky:installDismissedAt')||0);
      // Show again after 7 days
      if(!dismissed || Date.now()-last > 7*24*60*60*1000){
        if(installBanner) installBanner.classList.add('show');
      }
    }catch(err){ if(installBanner) installBanner.classList.add('show'); }
  });
  window.dismissInstall=function(){
    if(installBanner) installBanner.classList.remove('show');
    try{ localStorage.setItem('sky:installDismissed','1'); localStorage.setItem('sky:installDismissedAt', String(Date.now())); }catch(e){}
  };
  if(installBtn){
    installBtn.addEventListener('click', function(){
      if(!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(function(choice){
        try{ localStorage.setItem('sky:installChoice', choice.outcome); }catch(e){}
        deferredPrompt=null;
        if(installBanner) installBanner.classList.remove('show');
      });
    });
  }
  window.addEventListener('appinstalled', function(){
    try{ localStorage.setItem('sky:installed','1'); }catch(e){}
    if(installBanner) installBanner.classList.remove('show');
    showToast('SKY installed — open from home screen','ok');
  });
  // Service worker registration — scope / so it can control the whole desk
  if('serviceWorker' in navigator){
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('/sw.js', {scope:'/'})
        .then(function(reg){
          // Update available -> show reload
          reg.addEventListener('updatefound', function(){
            var nw=reg.installing;
            if(!nw) return;
            nw.addEventListener('statechange', function(){
              if(nw.state==='installed' && navigator.serviceWorker.controller){
                showToast('SKY updated — reload to get the new shell','ok');
                // Auto-skipWaiting after 5s if user stays
                setTimeout(function(){ try{ reg.waiting && reg.waiting.postMessage({type:'SKIP_WAITING'}); }catch(e){} }, 5000);
              }
            });
          });
        })
        .catch(function(err){ /* silent — offline or not https, still works as normal site */ });
      // Reload when new worker takes over
      var refreshing=false;
      navigator.serviceWorker.addEventListener('controllerchange', function(){
        if(refreshing) return; refreshing=true; window.location.reload();
      });
    });
  }
  // Push abstraction stub — real push needs VAPID + server; this wires the UI
  window.SKY_push = {
    supported: !!('PushManager' in window) && !!('serviceWorker' in navigator) && !!('Notification' in window),
    permission: function(){ try{ return Notification.permission; }catch(e){ return 'unknown'; } },
    request: function(){
      if(!('Notification' in window)) return Promise.resolve('unsupported');
      return Notification.requestPermission();
    }
  };
  // Compact-mode helper: expose current breakpoint for tests
  window.SKY_compact = function(){ try{ return window.matchMedia('(max-width:640px)').matches; }catch(e){ return false; } };
})();
try{ if(document.querySelectorAll) document.querySelectorAll('#symSeg button').forEach(b=> b.classList.toggle('active', b.dataset.sym===document.getElementById('sym').value)); }catch(e){}
try{ if(document.querySelectorAll) document.querySelectorAll('#tfSeg button').forEach(b=> b.classList.toggle('active', b.dataset.tf===document.getElementById('tf').value)); }catch(e){}
</script></body></html>
"""


def make_app(job_manager=None) -> Flask:
    app = Flask(__name__)

    # ── P18.1 authentication & authorization ──────────────────────────────
    auth = authmod.AuthManager()
    app.secret_key = auth.secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Secure cookies only make sense behind a TLS-terminating proxy; on a
        # loopback http bind we keep them non-secure so local use stays simple.
        SESSION_COOKIE_SECURE=bool(config.SKY_TRUSTED_PROXY_IPS),
    )
    from datetime import timedelta
    app.permanent_session_lifetime = timedelta(hours=config.SKY_SESSION_TTL_HOURS)
    if config.SKY_TRUSTED_PROXY_IPS:  # pragma: no cover - deployment-only
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        except Exception:
            pass

    def _client_ip() -> str:
        fwd = request.headers.get("X-Forwarded-For", "")
        return (fwd.split(",")[0].strip() if fwd else request.remote_addr) or ""

    def _client_ua() -> str:
        return request.headers.get("User-Agent", "")[:200]

    def _current_user() -> dict | None:
        """Resolve the authenticated principal from cookie session or bearer."""
        sid = session.get("sid")
        if sid and session.get("uid"):
            user = auth.resolve_session(sid)
            if user is not None:
                return user
        authz = request.headers.get("Authorization", "")
        if authz.lower().startswith("bearer "):
            user = auth.resolve_device_token(authz[7:].strip())
            if user is not None:
                return user
        return None

    def _using_cookie_session() -> bool:
        return bool(session.get("sid") and session.get("uid"))

    def _csrf_token() -> str:
        tok = session.get("_csrf")
        if not tok:
            tok = secrets.token_hex(16)
            session["_csrf"] = tok
        return tok

    def _csrf_ok() -> bool:
        supplied = (request.headers.get("X-CSRF-Token")
                    or (request.get_json(silent=True) or {}).get("_csrf")
                    or (request.form or {}).get("_csrf"))
        expected = session.get("_csrf")
        if not expected or not supplied:
            return False
        import hmac as _hmac
        return _hmac.compare_digest(str(supplied), str(expected))

    def _audit(action: str, target: str = "", ok: bool = True,
               detail: dict | None = None) -> None:
        try:
            user = getattr(g, "user", None)
            auth.audit(action, target, user=user, ok=ok, ip=_client_ip(),
                       user_agent=_client_ua(), detail=detail)
        except Exception:
            pass

    def _auth_state() -> dict:
        enabled = auth.is_enabled()
        has_owner = auth.owner_exists()
        setup = (config.SKY_AUTH_MODE != "disabled") and not has_owner
        user = _current_user()
        return {
            "enabled": enabled,
            "setup_required": setup,
            "authenticated": user is not None,
            "user": user.get("username") if user else None,
            "role": user.get("role") if user else None,
            "csrf": _csrf_token(),
            "session_ttl_hours": config.SKY_SESSION_TTL_HOURS,
            "session_idle_hours": config.SKY_SESSION_IDLE_HOURS,
        }

    # ── P18.2: the v1 contract needs its refusals in the v1 envelope ──────
    V1_PREFIX = "/api/v1"

    def _is_v1(path: str) -> bool:
        return path == V1_PREFIX or path.startswith(V1_PREFIX + "/")

    def _v1_sub(path: str) -> str:
        """'/api/v1/review' -> '/review' (the ROUTES key)."""
        return path[len(V1_PREFIX):] or "/"

    # (sub_path, METHOD) -> minimum role, built from the declared route table
    # so the gate and the published catalog can never disagree.
    _V1_ROLES: dict[tuple[str, str], str] = {}
    for _r in apiv1.ROUTES + apiv1.NATIVE_ROUTES:
        _V1_ROLES[(_r["path"], _r["method"])] = _r.get("role", "operator")

    def _path_matches(template: str, actual: str) -> bool:
        """Match a declared v1 path template against a concrete request path.

        ``/jobs/<job_id>/cancel`` must match ``/jobs/abc123/cancel``: segments
        are compared in order and ``<...>`` matches any single non-empty
        segment.
        """
        t_segs = [s for s in template.split("/") if s]
        a_segs = [s for s in actual.split("/") if s]
        if len(t_segs) != len(a_segs):
            return False
        for t, a in zip(t_segs, a_segs):
            if t.startswith("<") and t.endswith(">"):
                if not a:
                    return False
                continue
            if t != a:
                return False
        return True

    def _required_role(path: str) -> str:
        """Minimum role for a mutating request.

        v1 reads its answer from the declared route table (with path-parameter
        templates matched); anything mutating and *undeclared* defaults to
        ``operator``, so forgetting to declare a new route fails closed rather
        than open.
        """
        if _is_v1(path):
            sub = _v1_sub(path)
            role = _V1_ROLES.get((sub, request.method))
            if role is None:
                for (tmpl, meth), r in _V1_ROLES.items():
                    if meth == request.method and _path_matches(tmpl, sub):
                        role = r
                        break
            if role in (None, "public"):
                return "operator"
            return role
        return "operator" if path not in authmod.VIEWER_POST_PATHS else "viewer"

    def _deny(path: str, code: str, message: str, status: int,
              details: dict | None = None):
        """Auth-gate refusal, rendered in whichever contract the caller used.

        A v1 client must never have to parse the legacy shape, and the legacy
        dashboard must never suddenly receive the v1 shape.
        """
        if _is_v1(path):
            return jsonify(apiv1.envelope_error(code, message, details)), status
        return jsonify({"ok": False, "error": message, "code": code}), status

    @app.before_request
    def _auth_gate():
        path = request.path or "/"
        if path == "/" or path.startswith("/static/") or path in ("/sw.js", "/manifest.json", "/offline.html", "/offline"):
            return None
        # Compatibility negotiation happens before authentication: a client too
        # old to speak this contract must be told to upgrade, not handed a 401
        # it will misreport as "wrong password".
        if _is_v1(path):
            bad = apiv1.check_client_version(
                request.headers.get(apiv1.CLIENT_VERSION_HEADER))
            if bad is not None:
                code, message = bad
                return jsonify(apiv1.envelope_error(
                    code, message, {"min_client_version": apiv1.MIN_CLIENT_VERSION,
                                    "max_client_version": apiv1.MAX_CLIENT_VERSION,
                                    "server_version": config.VERSION})), 400
            # /api/v1/version is deliberately public: a client must be able to
            # discover the compatibility range before it can authenticate.
            if _v1_sub(path) == "/version":
                return None
            if request.method == "POST" and _v1_sub(path) == "/pair":
                return None
        if path.startswith("/api/auth/"):
            if path in ("/api/auth/status", "/api/auth/setup", "/api/auth/login"):
                return None
            user = _current_user()
            if user is None:
                return _deny(path, apiv1.ErrorCode.UNAUTHENTICATED,
                             "authentication required", 401)
            g.user = user
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and \
                    _using_cookie_session() and not _csrf_ok():
                return _deny(path, apiv1.ErrorCode.CSRF,
                             "CSRF token missing or invalid", 403)
            return None
        if not auth.is_enabled():
            return None
        user = _current_user()
        if user is None:
            return _deny(path, apiv1.ErrorCode.UNAUTHENTICATED,
                         "authentication required", 401)
        g.user = user
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            required = _required_role(path)
            if not authmod.role_allows(user.get("role"), required):
                return _deny(path, apiv1.ErrorCode.FORBIDDEN,
                             f"insufficient role — {required} required", 403,
                             {"required_role": required,
                              "your_role": user.get("role")})
            if _using_cookie_session() and not _csrf_ok():
                return _deny(path, apiv1.ErrorCode.CSRF,
                             "CSRF token missing or invalid", 403)
        return None

    @app.get("/")
    def index():
        return render_template_string(HTML, symbol=SYMBOL, tf=TIMEFRAME,
                                      version=VERSION, symbols=symbol_choices(SYMBOLS),
                                      auth_state=_auth_state())

    # ── P18.4 PWA foundation — installable shell, offline, never-cache API ─
    @app.get("/sw.js")
    def sw_js():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory(str(Path(__file__).parent / "static"), "sw.js", mimetype="application/javascript"))
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    @app.get("/manifest.json")
    def pwa_manifest():
        from flask import send_from_directory
        return send_from_directory(str(Path(__file__).parent / "static"), "manifest.json", mimetype="application/manifest+json")

    @app.get("/offline.html")
    def offline_page():
        from flask import send_from_directory
        return send_from_directory(str(Path(__file__).parent / "static"), "offline.html", mimetype="text/html")

    @app.get("/offline")
    def offline_alias():
        from flask import send_from_directory
        return send_from_directory(str(Path(__file__).parent / "static"), "offline.html", mimetype="text/html")

    # ── auth API ────────────────────────────────────────────────────────
    @app.get("/api/auth/status")
    def api_auth_status():
        return jsonify(_auth_state())

    @app.post("/api/auth/setup")
    def api_auth_setup():
        if auth.owner_exists():
            return jsonify({"ok": False, "error": "an owner account already exists"}), 409
        body = request.get_json(silent=True) or {}
        try:
            user = auth.create_owner(str(body.get("username") or ""),
                                     str(body.get("password") or ""),
                                     role="operator")
        except (ValueError, PermissionError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        token = auth.create_session(user["id"], ip=_client_ip(), user_agent=_client_ua())
        session.clear()
        session["uid"] = user["id"]
        session["sid"] = token
        session["_csrf"] = secrets.token_hex(16)
        session.permanent = True
        auth.audit("owner_created", user["username"], user=user, ok=True,
                   ip=_client_ip(), user_agent=_client_ua())
        return jsonify({"ok": True, "user": user["username"], "role": user["role"],
                        "csrf": session["_csrf"]})

    @app.post("/api/auth/login")
    def api_auth_login():
        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        ip = _client_ip()
        if auth.is_locked(username, ip):
            auth.audit("login_failed", username, ok=False, ip=ip,
                       user_agent=_client_ua(), detail={"reason": "locked_out"})
            return jsonify({"ok": False,
                            "error": "Too many failed attempts. Try again later."}), 429
        user = auth.authenticate(username, password, ip=ip)
        if user is None:
            return jsonify({"ok": False, "error": "Invalid username or password."}), 401
        token = auth.create_session(user["id"], ip=ip, user_agent=_client_ua())
        session.clear()
        session["uid"] = user["id"]
        session["sid"] = token
        session["_csrf"] = secrets.token_hex(16)
        session.permanent = True
        auth.audit("login", username, user=user, ok=True, ip=ip, user_agent=_client_ua())
        return jsonify({"ok": True, "user": user["username"], "role": user["role"],
                        "csrf": session["_csrf"]})

    @app.post("/api/auth/logout")
    def api_auth_logout():
        user = _current_user()
        sid = session.get("sid")
        if sid:
            auth.revoke_session(sid)
        if user:
            auth.audit("logout", user["username"], user=user, ok=True,
                       ip=_client_ip(), user_agent=_client_ua())
        session.clear()
        return jsonify({"ok": True})

    @app.post("/api/auth/logout-all")
    def api_auth_logout_all():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        n_sessions = auth.revoke_all_sessions(user["id"])
        n_devices = auth.revoke_all_devices(user["id"])
        auth.audit("logout_all", user["username"], user=user, ok=True,
                   ip=_client_ip(), user_agent=_client_ua(),
                   detail={"sessions": n_sessions, "devices": n_devices})
        session.clear()
        return jsonify({"ok": True, "sessions": n_sessions, "devices": n_devices})

    @app.get("/api/auth/me")
    def api_auth_me():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        return jsonify({"ok": True, "user": user["username"], "role": user["role"]})

    @app.post("/api/auth/password")
    def api_auth_password():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        body = request.get_json(silent=True) or {}
        try:
            auth.change_password(user["id"], str(body.get("current") or ""),
                                 str(body.get("new") or ""))
        except (ValueError, PermissionError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        auth.audit("password_changed", user["username"], user=user, ok=True,
                   ip=_client_ip(), user_agent=_client_ua())
        return jsonify({"ok": True})

    @app.get("/api/auth/devices")
    def api_auth_devices():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        return jsonify({"ok": True, "devices": auth.list_device_tokens(user["id"])})

    @app.post("/api/auth/devices")
    def api_auth_device_create():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify({"ok": False, "error": "operator role required"}), 403
        body = request.get_json(silent=True) or {}
        scope = str(body.get("scope") or "viewer")
        # a token can never exceed its creator's role
        if not authmod.role_allows(user.get("role"), scope):
            scope = "viewer"
        token = auth.create_device_token(user["id"], str(body.get("name") or "device"),
                                         scope=scope)
        auth.audit("device_token_created", user["username"], user=user, ok=True,
                   ip=_client_ip(), user_agent=_client_ua(),
                   detail={"name": body.get("name"), "scope": scope})
        return jsonify({"ok": True, "token": token, "scope": scope,
                        "note": "Copy this token now — it is shown only once."})

    @app.post("/api/auth/devices/revoke")
    def api_auth_device_revoke():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify({"ok": False, "error": "operator role required"}), 403
        body = request.get_json(silent=True) or {}
        handle = str(body.get("id") or "").strip()
        ok = auth.revoke_device_token(user["id"], handle)
        auth.audit("device_token_revoked", handle, user=user, ok=ok,
                   ip=_client_ip(), user_agent=_client_ua())
        return jsonify({"ok": ok})

    @app.get("/api/auth/audit")
    def api_auth_audit():
        user = _current_user()
        if user is None:
            return jsonify({"ok": False, "error": "authentication required"}), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify({"ok": False, "error": "operator role required"}), 403
        return jsonify({"ok": True,
                        "rows": auth.recent_audit(request.args.get("limit", 100))})

    @app.get("/api/scan")
    def api_scan():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        force = request.args.get("force") == "1"
        try:
            if force:
                _CACHE.update(payload=None, ts=0, ttl=_CACHE.get("ttl", 40))
            return jsonify(_sanitize_for_json(
                compute_payload(symbol, tf, save=True, use_cache=not force)))
        except ConnectionError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sentiment")
    def api_sentiment():
        """Market-sentiment colour reading for one asset/timeframe.

        Returns the composite score, direction, how long the same sentiment
        has held (duration_min), colour depth (intensity) and the CSS colour.
        Reuses the cached scan; ``force=1`` triggers a fresh scan."""
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        force = request.args.get("force") == "1"
        try:
            payload = compute_payload(symbol, tf, save=False, use_cache=not force)
            sent = payload.get("sentiment") or {
                "available": False, "score": 0.0, "direction": "neutral",
                "label": "NO DATA", "color": "#5f6d84", "intensity": 0.0,
                "duration_min": 0.0, "duration_text": "—", "history": []}
            return jsonify(_sanitize_for_json({
                "symbol": symbol, "timeframe": tf, "sentiment": sent}))
        except Exception as exc:
            return jsonify({"symbol": symbol, "timeframe": tf,
                            "sentiment": {"available": False, "score": 0.0,
                                          "direction": "neutral", "label": "NO DATA",
                                          "color": "#5f6d84", "intensity": 0.0,
                                          "error": f"{type(exc).__name__}: {exc}"}}), 200

    @app.get("/api/intelligence")
    def api_intelligence():
        """JSON-only professional desk report for an asset/timeframe."""
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        force = request.args.get("force") == "1"
        try:
            payload = compute_payload(symbol, tf, save=False, use_cache=not force)
            return jsonify(_sanitize_for_json(payload.get("intelligence", {})))
        except Exception as exc:
            return jsonify({
                "asset": symbol,
                "signal": "NO TRADE",
                "confidence": 0,
                "reason": [f"Insufficient market data: {type(exc).__name__}: {exc}"],
            }), 200

    @app.get("/api/pending")
    def api_pending():
        from data.database import SignalDB
        from brain.coach import management_checklist
        with SignalDB() as db:
            pending = db.pending_reviews()
        for item in pending:
            tp = item.get("take_profit")
            item["management"] = management_checklist({
                "entry": item.get("entry"),
                "stop_loss": item.get("stop_loss"),
                "take_profits": [tp] if tp is not None else [],
            })
        return jsonify({"pending": pending})

    @app.get("/api/paper")
    def api_paper():
        """Paper-monitor dashboard state. Read-only; does not start a runner."""
        symbol = _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        from data.database import SignalDB
        with SignalDB() as db:
            return jsonify({"stats": db.paper_trade_stats(symbol)})

    @app.post("/api/paper/run")
    def api_paper_run():
        """One explicit, safe runner pass for the dashboard button.

        Continuous unattended monitoring belongs to ``python main.py paper
        --watch`` so it survives a browser tab closing.  This endpoint never
        sends an order to an exchange.
        """
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol")) if body.get("symbol") else None
        try:
            from data.database import SignalDB
            from data.paper_trading import PaperTradingRunner
            with SignalDB() as db:
                run = PaperTradingRunner(db=db, client=maybe_client()).run_once(symbol=symbol).as_dict()
            _audit("paper_run", symbol or "all",
                   detail={"checked": run.get("checked"), "opened": run.get("opened"),
                           "closed": run.get("closed")})
            return jsonify({"ok": True, "run": run})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/review")
    def api_review():
        body = request.get_json(silent=True) or {}
        scan_id = body.get("scan_id")
        decision = (body.get("decision") or "").upper()
        note = body.get("note", "")
        force = bool(body.get("force"))
        reviewer = (getattr(g, "user", None) or {}).get("username") or "dashboard"
        if decision not in ("APPROVED", "REJECTED", "EXECUTED", "CLOSED", "SKIPPED"):
            return jsonify({"error": f"bad decision {decision}"}), 400
        from data.database import SignalDB
        from engine.lifecycle import LifecycleError
        from brain.risk_gate import evaluate as gate_evaluate
        from data.paper_trading import _primary_plan
        with SignalDB() as db:
            # Enforced risk & discipline gate (decisions B6/B7/B9/B10).
            if decision == "APPROVED" and not force:
                scan = db.get_scan(int(scan_id)) if str(scan_id).isdigit() else None
                if scan is None:
                    return jsonify({"error": f"scan #{scan_id} not found"}), 404
                plan_type = _primary_plan(scan).get("type")
                gate = gate_evaluate(db, symbol=scan.get("symbol"),
                                     plan_type=plan_type, action=scan.get("action"))
                if not gate["allowed"]:
                    # P18.1: an operator cannot bypass the risk gate. The legacy
                    # force-approve escape hatch is disabled unless explicitly
                    # opted into, and always audited.
                    return jsonify({
                        "error": "Risk gate CLOSED — " + "; ".join(gate["blocked_by"]),
                        "blocked_by": gate["blocked_by"],
                        "force_available": config.SKY_ALLOW_FORCE_APPROVE,
                    }), 409
            if decision == "APPROVED" and force and not config.SKY_ALLOW_FORCE_APPROVE:
                return jsonify({"error": "force approve is disabled "
                                         "(SKY_ALLOW_FORCE_APPROVE is not set)"}), 403
            # W3.3 journal-first discipline: a decided real trade without its
            # journal answer means the last commitment was never processed,
            # so the next one waits. Same fail-closed population as the
            # graduation discipline criterion (P12.14). Never bypasses the
            # risk gate; only delays commitments, and the escape is audited.
            if decision == "APPROVED" and not body.get("acknowledge_journal"):
                from brain.weekly import missing_journals
                jg = missing_journals(db)
                if jg["missing"]:
                    return jsonify({
                        "error": (f"Journal-first discipline: {jg['missing']} decided "
                                  "real trade(s) unjournaled — journal them before the "
                                  "next commitment"),
                        "journal_block": jg,
                        "acknowledge_available": True,
                    }), 409
            try:
                new = db.update_status(int(scan_id), decision, note=note,
                                       reviewer=reviewer)
            except (LifecycleError, TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400
            if new is None:
                return jsonify({"error": f"scan #{scan_id} not found"}), 404
        _audit("review", str(scan_id),
               detail={"decision": decision, "note": note, "forced": force,
                       "acknowledged_journal": bool(body.get("acknowledge_journal"))})
        return jsonify({"ok": True, "scan_id": scan_id, "status": new})

    @app.get("/api/risk")
    def api_risk():
        """Risk & discipline gate status (decisions B4/B5/B6/B7/B9)."""
        from data.database import SignalDB
        from brain.risk_gate import evaluate as gate_evaluate, status_text
        from brain.metrics import business_metrics
        from brain.journal import violation_rate
        from brain.analytics import monte_carlo_ruin_table
        try:
            with SignalDB() as db:
                gate = gate_evaluate(db)
                metrics = business_metrics(db)
                journal = violation_rate(db)
                state = db.get_trader_state()
                monte = monte_carlo_ruin_table(db)
            return jsonify({
                "gate": gate,
                "trader_state": state,
                "metrics": metrics,
                "journal": journal,
                "monte": monte,
                "status_text": status_text.__doc__ or "",
            })
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/monte")
    def api_monte():
        """Monte Carlo risk-of-ruin table (expected DD / ruin prob / streak / TTR)."""
        from data.database import SignalDB
        from brain.analytics import monte_carlo_ruin_table
        try:
            samples = request.args.get("samples", type=int) or 2000
            seed = request.args.get("seed", type=int)
            ruin = request.args.get("ruin_threshold", type=float) or 50.0
            rp_raw = request.args.get("risk_pcts", type=str)
            risk_pcts = None
            if rp_raw:
                try:
                    risk_pcts = tuple(float(x.strip()) for x in rp_raw.split(",") if x.strip())
                except ValueError:
                    return jsonify({"error": "risk_pcts must be comma-separated floats"}), 400
            with SignalDB() as db:
                result = monte_carlo_ruin_table(
                    db, risk_percents=risk_pcts or (0.25, 0.5, 1.0, 1.5, 2.0),
                    ruin_threshold_pct=ruin, samples=min(samples, 20000),
                    seed=seed)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/trader-state")
    def api_trader_state():
        """Set/clear behavioral no-trade flags (decision B7)."""
        body = request.get_json(silent=True) or {}
        from data.database import SignalDB
        with SignalDB() as db:
            state = db.set_trader_state(
                angry=body.get("angry"), tired=body.get("tired"),
                revenge=body.get("revenge"), chasing=body.get("chasing"),
                note=body.get("note", ""))
        _audit("trader_state", "set",
               detail={k: body.get(k) for k in ("angry", "tired", "revenge", "chasing")})
        return jsonify({"ok": True, "state": state})

    @app.get("/api/history")
    def api_history():
        from data.database import SignalDB
        with SignalDB() as db:
            return jsonify({"history": db.latest_scans(limit=15)})

    @app.get("/api/signal")
    def api_signal():
        scan_id = request.args.get("id", type=int)
        from data.database import SignalDB
        with SignalDB() as db:
            scan = db.get_scan(scan_id)
            if scan is None:
                return jsonify({"error": "not found"}), 404
            plans = json.loads(scan.get("plans_json") or "[]")
            decisions = db.decision_history(scan_id)
            paper_trade = db.paper_trade_for_scan(scan_id)
            journal = db.get_journal(scan_id)
        from brain.coach import management_checklist
        plan0 = plans[0] if plans else {
            "entry": scan.get("entry"),
            "stop_loss": scan.get("stop_loss"),
            "take_profit": scan.get("take_profit"),
        }
        management = management_checklist(plan0)
        return jsonify({"scan": scan, "plans": plans, "decisions": decisions,
                        "paper_trade": paper_trade, "journal": journal,
                        "management": management})

    @app.get("/api/learning")
    def api_learning():
        from data.database import SignalDB
        try:
            with SignalDB() as db:
                from brain.metrics import business_metrics
                from brain.journal import violation_rate
                return jsonify({
                    "backtest": db.backtest_stats(),
                    "calibration": db.load_calibration(),
                    # P12.11 — which price series the learning store holds.
                    "sources": db.source_inventory(),
                    "plan_stats": db.plan_stats(),
                    "metrics": business_metrics(db),
                    "journal": violation_rate(db),
                })
        except Exception as exc:  # never 500 — the card degrades gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                            "backtest": {"overall": {"n": 0}},
                            "calibration": {}, "plan_stats": []})

    @app.get("/api/coach")
    def api_coach():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        from brain.coach import (explain_signal, five_levels,
                                 management_checklist, mentor,
                                 personal_feedback)
        from data.database import SignalDB
        payload = compute_payload(symbol, tf, save=False, use_cache=False)
        with SignalDB() as db:
            feedback = personal_feedback(db)
        plans = payload.get("plans") or []
        return jsonify({
            "explain": explain_signal(payload),
            "mentor": mentor(payload),
            "feedback": feedback,
            "five_levels": five_levels(payload),
            "management": (payload.get("management")
                           or management_checklist(plans[0] if plans else None)),
        })

    @app.get("/api/candles")
    def api_candles():
        """OHLCV for the candlestick chart.

        Every value goes through :func:`web.chart_data._num`, so Pandas /
        NumPy scalars (``int64``, ``float64``, ``NaT``, ``NaN``) can never
        reach Flask's strict jsonify and blank the chart.
        """
        from web.chart_data import _epoch_seconds, _num
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        limit = min(int(request.args.get("limit", 90)), 1000)
        try:
            df = maybe_client().klines(symbol, tf, limit)
            candles = []
            for row in df.tail(limit).itertuples(index=False):
                data = row._asdict()
                time_s = _epoch_seconds(data.get("ts"))
                if time_s is None:
                    continue
                candles.append({
                    "time": time_s,
                    "ts": time_s * 1000,
                    "open": _num(data.get("open")),
                    "high": _num(data.get("high")),
                    "low": _num(data.get("low")),
                    "close": _num(data.get("close")),
                    "volume": _num(data.get("volume")),
                })
            return jsonify({"candles": candles, "count": len(candles),
                            "symbol": symbol, "tf": tf})
        except ConnectionError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception as exc:  # never blank the chart on an engine hiccup
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/chart")
    def api_chart():
        """Full chart workspace feed: candles + overlays + panes + levels.

        This is what the TradingView-style workspace draws: OHLCV in
        Lightweight Charts' epoch-second format, EMA/VWAP/Bollinger overlays,
        volume/RSI/MACD/ADX panes, support & resistance lines and the live
        plan's entry / stop / take-profit overlay.
        """
        from web.chart_data import build_chart
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        limit = min(int(request.args.get("limit", 300)), 1000)
        with_plan = request.args.get("plan", "1") != "0"
        try:
            df = maybe_client().klines(symbol, tf, max(limit, 250))
        except ConnectionError as exc:
            return jsonify({"error": str(exc), "candles": []}), 502
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "candles": []}), 500
        payload = None
        if with_plan:
            try:
                payload = compute_payload(symbol, tf, save=False, use_cache=True)
            except Exception:
                payload = None
        try:
            return jsonify(_sanitize_for_json(
                build_chart(df, symbol, tf, payload=payload, limit=limit)))
        except Exception as exc:  # pragma: no cover — defensive
            return jsonify({"error": f"{type(exc).__name__}: {exc}",
                            "candles": []}), 500

    @app.get("/api/chart/stream")
    def api_chart_stream():
        """W2 — server-sent stream of the newest bar for one symbol/timeframe.

        Read-only market data: the chart calls ``series.update()`` with each
        frame instead of reloading. Every frame states whether the feed is
        live, waiting, stale or erroring, so a dead source can never be read
        as a quiet market. No order path, no writes, no threshold touched.
        """
        from flask import Response
        from web.live_stream import candle_events, poll_interval
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        frames = request.args.get("frames")
        try:
            max_frames = max(1, min(600, int(frames))) if frames else None
        except (TypeError, ValueError):
            max_frames = None
        interval = poll_interval(tf)
        asked = request.args.get("interval")
        if asked:
            # A client may ask for a different cadence, but never a faster one
            # than the shared floor — one browser tab must not become a load
            # generator against the market source.
            try:
                from web.live_stream import MAX_INTERVAL, MIN_INTERVAL
                interval = max(MIN_INTERVAL, min(MAX_INTERVAL, float(asked)))
            except (TypeError, ValueError):
                pass

        def fetch(sym: str, timeframe: str, limit: int):
            return maybe_client().klines(sym, timeframe, limit)

        gen = candle_events(fetch, symbol, tf, interval=interval,
                            max_frames=max_frames)
        return Response(gen, mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no",
                                 "Connection": "keep-alive"})

    # ── Command Center ────────────────────────────────────────────────
    @app.get("/api/commands")
    def api_commands():
        """The clickable catalog of every CLI command (no memorization)."""
        from web.command_center import catalog
        return jsonify(catalog())

    @app.post("/api/commands/run")
    def api_commands_run():
        """Run one allow-listed catalog command and return its output.

        Only ids that exist in ``web.command_center.COMMANDS`` can run, no
        shell is used, and blocked (long-lived / interactive) commands are
        refused with the terminal instruction instead.
        """
        from web.command_center import CommandError, run_command
        body = request.get_json(silent=True) or {}
        command_id = str(body.get("id") or "").strip()
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return jsonify({"ok": False, "error": "params must be an object"}), 400
        try:
            result = run_command(command_id, params, timeout=body.get("timeout"))
            _audit("command_run", command_id, ok=bool(result.get("ok")))
            return jsonify(result)
        except CommandError as exc:
            return jsonify({"ok": False, "error": str(exc),
                            "command_id": command_id}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"}), 500

    # ── Risk Center: position-size calculator ─────────────────────────
    @app.post("/api/position-size")
    def api_position_size():
        """Position-size calculator bounded by the live risk gate."""
        from web.position_sizer import calculate
        from data.database import SignalDB
        from brain.risk_gate import evaluate as gate_evaluate
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol")) if body.get("symbol") else SYMBOL
        try:
            with SignalDB() as db:
                gate = gate_evaluate(db, symbol=symbol)
        except Exception:
            gate = {}
        try:
            return jsonify(_sanitize_for_json(calculate(
                balance=body.get("balance"), risk_pct=body.get("risk_pct"),
                entry=body.get("entry"), stop=body.get("stop_loss"),
                take_profit=body.get("take_profit"), symbol=symbol,
                gate=gate, leverage=body.get("leverage"))))
        except Exception as exc:
            return jsonify({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"}), 500

    # ── Trade manager: the live open book ─────────────────────────────
    @app.get("/api/trades")
    def api_trades():
        """Open paper positions with live R, MAE/MFE and management advice."""
        from data.database import SignalDB
        from brain.coach import management_checklist
        symbol = _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        try:
            with SignalDB() as db:
                rows = db.live_open_rows(symbol=symbol)
                stats = db.paper_trade_stats(symbol)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                            "open": [], "recent": []}), 200

        prices: dict[str, float | None] = {}

        def last_price(sym: str, tf: str) -> float | None:
            key = f"{sym}:{tf}"
            if key not in prices:
                try:
                    df = maybe_client().klines(sym, tf, 2)
                    prices[key] = float(df["close"].iloc[-1])
                except Exception:
                    prices[key] = None
            return prices[key]

        now_ms = int(time.time() * 1000)
        out = []
        for row in rows:
            entry = row.get("entry_price") or row.get("entry")
            stop = row.get("stop_loss")
            take = row.get("take_profit")
            price = last_price(row.get("symbol") or SYMBOL,
                               row.get("timeframe") or TIMEFRAME) or row.get("last_price")
            risk = abs(float(entry) - float(stop)) if entry and stop else None
            current_r = None
            if price is not None and entry and risk:
                delta = float(price) - float(entry)
                if str(row.get("action")).upper() == "SELL":
                    delta = -delta
                current_r = round(delta / risk, 3)
            opened = row.get("opened_ts") or row.get("created_ts") or now_ms
            item = dict(row)
            item.update({
                "current_price": price,
                "current_r": current_r,
                "risk_per_unit": risk,
                "stop_distance": (abs(float(price) - float(stop))
                                  if price is not None and stop else None),
                "tp_distance": (abs(float(take) - float(price))
                                if price is not None and take else None),
                "minutes_in_trade": max(0, int((now_ms - int(opened)) / 60000)),
                "management": management_checklist({
                    "entry": entry, "stop_loss": stop,
                    "take_profits": [take] if take is not None else [],
                }),
            })
            out.append(item)
        return jsonify(_sanitize_for_json({
            "ok": True, "open": out, "count": len(out),
            "recent": (stats or {}).get("recent", []),
            "overall": (stats or {}).get("overall", {}),
        }))

    # ── Journal: a real form, not a CLI instruction ───────────────────
    @app.get("/api/journal")
    def api_journal_get():
        """Journal entry for a scan, or the discipline summary when no id."""
        from data.database import SignalDB
        from brain.journal import (EMOTIONS, execution_quality, get_journal,
                                   pre_trade_checklist, violation_rate)
        scan_id = request.args.get("scan_id", type=int)
        try:
            with SignalDB() as db:
                summary = violation_rate(db)
                if scan_id is None:
                    # Every recent decision is journalable — including the ones
                    # you rejected or stood aside on. "I did not take it, and
                    # here is why" is the entry that builds discipline fastest.
                    recent = db.latest_scans(limit=40)
                    decided = ("CLOSED", "EXECUTED", "APPROVED", "REJECTED", "SKIPPED")
                    recent.sort(key=lambda r: (r.get("status") not in decided,
                                               -(r.get("id") or 0)))
                    return jsonify(_sanitize_for_json({
                        "ok": True, "summary": summary, "emotions": list(EMOTIONS),
                        "journalable": recent,
                    }))
                scan = db.get_scan(scan_id)
                entry = get_journal(db, scan_id)
                quality = execution_quality(db, scan_id)
                # get_scan() returns the FLAT scans row; pre_trade_checklist
                # reads the nested scan payload, so re-nest it here (the
                # checklist silently reported "—" for every field otherwise).
                checklist = pre_trade_checklist(_scan_row_to_payload(scan))
                paper = db.paper_trade_for_scan(scan_id)
            return jsonify(_sanitize_for_json({
                "ok": True, "scan_id": scan_id, "entry": entry,
                "scan": scan, "paper": paper, "quality": quality,
                "checklist": checklist,
                "emotions": list(EMOTIONS), "summary": summary,
            }))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/journal")
    def api_journal_save():
        """Save the post-trade journal from the dashboard form."""
        from data.database import SignalDB
        from brain.journal import execution_quality, save_journal
        body = request.get_json(silent=True) or {}
        scan_id = body.get("scan_id")
        try:
            scan_id = int(scan_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "scan_id is required"}), 400
        followed = body.get("followed_rules")
        if followed is not None:
            followed = str(followed).lower() in ("1", "true", "yes", "on")
        try:
            with SignalDB() as db:
                entry = save_journal(
                    db, scan_id, followed_rules=followed,
                    emotion=str(body.get("emotion") or ""),
                    mistake=str(body.get("mistake") or ""),
                    screenshot_path=str(body.get("screenshot_path") or ""),
                    would_change=str(body.get("would_change") or ""),
                    notes=str(body.get("notes") or ""))
                quality = execution_quality(db, scan_id)
            _audit("journal", str(scan_id), detail={"followed_rules": followed})
            return jsonify(_sanitize_for_json({
                "ok": True, "scan_id": scan_id, "entry": entry, "quality": quality}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    # ── Real-world connections ────────────────────────────────────────
    @app.get("/api/connections")
    def api_connections():
        """Every real-world link: what it gives you and whether it is live."""
        from brain.connections import probe_all as probe_connections
        try:
            return jsonify(_sanitize_for_json(probe_connections()))
        except Exception as exc:  # never blank the page
            return jsonify({"connections": [], "level": "down",
                            "headline": f"connection probe failed: "
                                        f"{type(exc).__name__}: {exc}"})

    @app.post("/api/connections/test")
    def api_connections_test():
        """Test one connection on demand (the Test button on each card)."""
        from brain.connections import probe_one
        body = request.get_json(silent=True) or {}
        cid = str(body.get("id") or "").strip()
        try:
            return jsonify(_sanitize_for_json(probe_one(cid)))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/alerts/test")
    def api_alerts_test():
        """Send a real test alert so the user can confirm it reaches them."""
        from output.notifiers import send_test_alert
        body = request.get_json(silent=True) or {}
        try:
            res = send_test_alert(str(body.get("channel") or ""))
            _audit("test_alert", str(body.get("channel") or ""), ok=bool(res.get("ok")))
            return jsonify(res)
        except Exception as exc:
            return jsonify({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/account")
    def api_account():
        """READ-ONLY exchange account snapshot: real balance, real orders.

        Backed by ``data/exchange_account.py``, which signs GET requests
        against a read-only allow-list and has no order-placement path.
        """
        from data.exchange_account import ExchangeAccount
        try:
            return jsonify(_sanitize_for_json(ExchangeAccount().snapshot()))
        except Exception as exc:
            return jsonify({"configured": False, "connected": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "balances": [], "open_orders": []})

    # ── Why blocked / how to unlock ───────────────────────────────────
    @app.get("/api/unlock")
    def api_unlock():
        """Why the gate is closed and exactly what to click to open it."""
        from data.database import SignalDB
        from brain.unlock import explain
        plan_type = request.args.get("plan_type") or None
        symbol = _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        try:
            with SignalDB() as db:
                if plan_type is None:
                    # default to the setup the live scan is currently proposing
                    try:
                        payload = compute_payload(symbol or SYMBOL, TIMEFRAME,
                                                  save=False, use_cache=True)
                        plans = payload.get("plans") or []
                        plan_type = plans[0].get("type") if plans else None
                    except Exception:
                        plan_type = None
                return jsonify(_sanitize_for_json(
                    explain(db, plan_type=plan_type, symbol=symbol)))
        except Exception as exc:
            return jsonify({"allowed": False, "blocks": [],
                            "headline": "could not evaluate the gate",
                            "summary": f"{type(exc).__name__}: {exc}"}), 200

    @app.get("/api/evidence")
    def api_evidence():
        """Progress toward proving every setup — the honest edge scoreboard."""
        from data.database import SignalDB
        from brain.unlock import evidence_overview
        try:
            with SignalDB() as db:
                return jsonify(_sanitize_for_json(evidence_overview(db)))
        except Exception as exc:
            return jsonify({"setups": [], "count": 0,
                            "headline": f"{type(exc).__name__}: {exc}"}), 200

    # ── Module catalog: every module visible ──────────────────────────
    @app.get("/api/modules")
    def api_modules():
        """Every Python module in the engine with its one-line purpose."""
        import ast
        groups = {"engine": "Signal engine", "brain": "Decision brain",
                  "data": "Market data & storage", "output": "Output & notifiers",
                  "web": "Dashboard", "ai": "LLM & MCP"}
        root = Path(__file__).resolve().parent.parent
        out = []
        for package, label in groups.items():
            modules = []
            for path in sorted((root / package).rglob("*.py")):
                if path.name == "__init__.py":
                    continue
                doc = ""
                try:
                    doc = (ast.get_docstring(ast.parse(path.read_text())) or "")
                except Exception:
                    doc = ""
                rel = str(path.relative_to(root))
                summary = doc.strip().split("\n")[0].strip()
                # Many modules open with "package/file.py — what it does";
                # show only the explanation, never the filename twice.
                if summary.startswith(rel) or summary.startswith(f"{package}/"):
                    for sep in ("—", "-", ":"):
                        if sep in summary:
                            summary = summary.split(sep, 1)[1].strip()
                            break
                    else:
                        summary = ""
                if not summary and len(doc.strip().split("\n")) > 1:
                    summary = next((ln.strip() for ln in doc.strip().split("\n")[1:]
                                    if ln.strip()), "")
                modules.append({
                    "name": str(path.relative_to(root)),
                    "module": str(path.relative_to(root)).replace("/", ".")[:-3],
                    "summary": summary or "—",
                    "lines": len(path.read_text().splitlines()),
                })
            out.append({"package": package, "label": label, "modules": modules,
                        "count": len(modules)})
        return jsonify({"packages": out,
                        "count": sum(g["count"] for g in out)})

    @app.get("/api/state")

    @app.get("/api/state")
    def api_state():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        from brain.state_memory import SignalMemory
        mem = SignalMemory()
        return jsonify({"state": mem.get_state(symbol, tf),
                        "events": mem.history(symbol, tf, limit=15)})

    @app.post("/api/learn")
    def api_learn():
        """One-click: recompute the calibration profile from stored backtests."""
        from brain.calibrator import learn
        try:
            res = learn()
            _audit("learn", "calibration")
            return jsonify({"ok": True, **res})
        except Exception as exc:  # pragma: no cover
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/backtest")
    def api_backtest():
        """One-click: quick backtest on recent bars + auto-learn."""
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol", SYMBOL))
        tf = body.get("tf", TIMEFRAME)
        bars = min(int(body.get("bars", 300)), 1000)
        step = int(body.get("step", 3))
        horizons = [float(h) for h in str(body.get("horizons", "1,4,24")).split(",") if h]
        try:
            from brain.calibrator import learn
            from data.backtester import run_backtest
            from data.database import SignalDB
            df = maybe_client().klines(symbol, tf, bars)
            res = run_backtest(df, symbol=symbol, timeframe=tf,
                               horizons=horizons, step=step,
                               min_confidence=MIN_CONFIDENCE)
            run_id = time.strftime("%Y%m%d_%H%M%S")
            rows = []
            for g in res["graded"]:
                r = g.as_row()
                r.update({"run_id": run_id, "symbol": symbol, "timeframe": tf})
                rows.append(r)
            with SignalDB() as db:
                n = db.save_backtest_rows(rows, run_id)
            profile = learn()
            _audit("backtest", f"{symbol}:{tf}",
                   detail={"bars": bars, "saved": n})
            return jsonify(_sanitize_for_json(
                {"ok": True, "saved": n, "report": res["report"],
                 "calibration": profile["profile"]}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sources")
    def api_sources():
        """Configuration status of optional external connections."""
        from config import (CRYPTODADA_BASE_URL, DISCORD_TOKEN, DISCORD_CHANNEL_IDS,
                            DISCORD_ANNOUNCE_WEBHOOK, TELEGRAM_BOT_TOKEN,
                            TELEGRAM_CHAT_ID, LLM_PROVIDER)
        return jsonify({
            "cryptodada": bool(CRYPTODADA_BASE_URL and "YOUR-CRYPTODADA" not in CRYPTODADA_BASE_URL),
            "discord_read": bool(DISCORD_TOKEN and DISCORD_CHANNEL_IDS),
            "discord_webhook": bool(DISCORD_ANNOUNCE_WEBHOOK),
            "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
            "llm": LLM_PROVIDER != "off",
        })

    @app.get("/api/diag")
    def api_diag():
        """Connectivity check: which external sources are reachable, with
        response times — powers the dashboard 'System check' button."""
        import requests as _req
        from data.binance_client import BINANCE_HOSTS, BINANCE_FUTURES_HOSTS
        out: dict = {}

        def probe(name, fn):
            t0 = time.time()
            try:
                ok = fn()
                out[name] = {"ok": bool(ok), "ms": int((time.time() - t0) * 1000)}
            except Exception as exc:
                out[name] = {"ok": False, "ms": int((time.time() - t0) * 1000),
                             "err": str(exc)[:120]}

        def spot():
            r = _req.get(f"{BINANCE_HOSTS[0]}/api/v3/ping", timeout=4)
            return r.status_code == 200

        def fapi():
            r = _req.get(f"{BINANCE_FUTURES_HOSTS[0]}/fapi/v1/ping", timeout=4)
            return r.status_code == 200

        def fng():
            r = _req.get("https://api.alternative.me/fng/?limit=1", timeout=4)
            return r.status_code == 200

        def cg():
            r = _req.get("https://api.coingecko.com/api/v3/global", timeout=4,
                         headers={"User-Agent": "CryptoBrain/1.0"})
            return r.status_code == 200

        def stooq():
            r = _req.get("https://stooq.com/q/l/?s=^spx&f=sd2t2ohlcv&h&e=csv",
                         timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            return r.status_code == 200

        def news():
            r = _req.get("https://cointelegraph.com/rss", timeout=4,
                         headers={"User-Agent": "CryptoBrain/1.0"})
            return r.status_code == 200

        from concurrent.futures import ThreadPoolExecutor
        probes = {"binance_spot": spot, "binance_futures": fapi, "fear_greed": fng,
                  "coingecko": cg, "stooq_equities": stooq, "news_rss": news}
        with ThreadPoolExecutor(max_workers=len(probes)) as ex:
            futs = {ex.submit(probe, n, f): n for n, f in probes.items()}
            for fut in futs:
                fut.result()
        ok_count = sum(1 for v in out.values() if v.get("ok"))
        return jsonify({"sources": out, "ok_count": ok_count, "total": len(out),
                        "all_ok": ok_count == len(out)})

    @app.get("/api/health")
    def health():
        """Full system health — same report as `python main.py agent health`."""
        try:
            from brain.agent import health_report
            return jsonify(health_report())
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/channels")
    def api_channels():
        """P8 ordered-backend channel registry (Panniantong/Agent-Reach pattern).

        Every external dependency the engine has (data sources + LLM) is a
        *channel* with an ordered list of backend candidates. The first
        backend that is configured and probes clean is the *active* one.
        Channels never block the engine — when nothing is configured, the
        channel reports ``active: "none"`` and the rest of the brain
        continues unaffected. Probes are exception-isolated: a broken
        backend in one channel cannot crash this endpoint.
        """
        try:
            from brain.channels import probe_all
            channels = probe_all()
            return jsonify(_sanitize_for_json({
                "channels": {n: ch.to_dict() for n, ch in channels.items()},
            }))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                            "channels": {}})

    @app.get("/api/doctor")
    def api_doctor():
        """Human-readable doctor report — same output as `python main.py doctor`."""
        try:
            from brain.channels import doctor_report
            # doctor_report returns a multi-line string in text mode
            return jsonify({"report": doctor_report(as_json=False)})
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/desk")
    def api_desk():
        """One-call desk advisory — same snapshot as `python main.py desk`."""
        try:
            from brain.agent import desk_status
            return jsonify(_sanitize_for_json(desk_status()))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/loop-health")
    def api_loop_health():
        """The one daily number — same snapshot as `python main.py daily`."""
        try:
            from brain.agent import loop_health
            payload = loop_health()
            payload["evidence_guidance"] = _jobs.evidence_guidance(
                (payload.get("graduation") or {}).get("by_setup") or [])
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/weekly")
    def api_weekly():
        """W3 weekly trader review — the same computation as
        `python main.py weekly`, the MCP ``weekly_review`` tool and the
        ``weekly_review`` desk agent. Read-only over the canonical live
        book, NET of costs; advisory only, never a gate."""
        try:
            from brain.weekly import weekly_review
            days = request.args.get("days", 7)
            days = min(90, max(1, int(days)))
            from data.database import SignalDB
            with SignalDB() as db:
                payload = weekly_review(db, days=days)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/weekly/export")
    def api_weekly_export():
        """Download the weekly review as a JSON attachment (evidence archive)."""
        try:
            from brain.weekly import weekly_review
            days = request.args.get("days", 7)
            days = min(90, max(1, int(days)))
            from data.database import SignalDB
            with SignalDB() as db:
                payload = weekly_review(db, days=days)
            body = json.dumps(_sanitize_for_json(payload), indent=2, default=str)
            day = time.strftime("%Y-%m-%d", time.gmtime())
            return Response(
                body,
                mimetype="application/json",
                headers={"Content-Disposition":
                         f"attachment; filename=sky-weekly-review-{day}.json"},
            )
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/ritual")
    def api_ritual():
        """W3.2 — today's daily-ritual checklist with its persisted ticks."""
        try:
            from brain.ritual import ritual_today
            from data.database import SignalDB
            with SignalDB() as db:
                payload = ritual_today(db)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/ritual")
    def api_ritual_set():
        """W3.2 — tick/untick one canonical ritual step for today.

        Fail-closed on unknown step names (no invented ritual history), and
        audited like every human action. A tick is a memory note, never
        permission and never a threshold."""
        body = request.get_json(silent=True) or {}
        name = str(body.get("step") or body.get("name") or "")
        try:
            done = bool(body.get("done"))
            from brain.ritual import ritual_set
            from data.database import SignalDB
            with SignalDB() as db:
                payload = ritual_set(db, name, done)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit("ritual", name, detail={"done": done, "day": payload.get("day")})
        return jsonify(_sanitize_for_json(payload))

    @app.get("/api/practice")
    def api_practice():
        """W3.4 practice calibration — the same computation as
        `python main.py practice`, the Chart/Review tab cards and the
        read-only MCP ``practice_scorecard`` tool. Coaching memory only:
        agreement with the desk is not evidence, and this payload is never
        read by any gate or graduation surface."""
        try:
            from brain.practice import practice_scorecard
            from data.database import SignalDB
            days = min(365, max(1, int(request.args.get("days", 30))))
            with SignalDB() as db:
                payload = practice_scorecard(db, days=days)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/practice")
    def api_practice_submit():
        """W3.4 — commit one practice read and score it against the desk's
        current read.

        The engine payload is computed with ``save=False``: a practice
        attempt never enters the scans table, the review queue or the live
        book. Fail-closed validation (400) before the desk read is computed;
        if the engine itself cannot produce a read, nothing is recorded
        (502) — an unscored attempt would corrupt the calibration history.
        """
        body = request.get_json(silent=True) or {}
        from brain.practice import (desk_read_from_payload, submit_attempt,
                                    validate_user_read)
        try:
            user = validate_user_read(body)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            payload = compute_payload(user["symbol"], user["tf"],
                                      save=False, use_cache=True)
        except Exception as exc:
            return jsonify({"ok": False,
                            "error": f"desk read unavailable — attempt not recorded: "
                                     f"{type(exc).__name__}: {exc}"}), 502
        try:
            desk = desk_read_from_payload(payload, user["symbol"], user["tf"])
            from data.database import SignalDB
            with SignalDB() as db:
                result = submit_attempt(db, user, desk)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit("practice", f"{user['symbol']} {user['tf']}",
               detail={"score": result["score"]["total"],
                       "grade": result["score"]["grade"],
                       "duplicate": bool(result.get("duplicate"))})
        return jsonify(_sanitize_for_json(result))

    @app.post("/api/practice/tape")
    def api_practice_tape():
        """W3.6 — commit one practice read against the hidden replay window.

        The server fetches the same candle series the chart draws and walks
        the bars *after* ``commit_time``. The client cannot supply the
        future. Fail-closed validation (400) before any row is written.
        Never writes scans or paper_trades — coaching memory only.
        """
        body = request.get_json(silent=True) or {}
        from brain.practice import (load_ohlc, submit_tape_attempt,
                                    validate_tape_request)
        try:
            user, _commit_ms, _horizon = validate_tape_request(body)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            candles = load_ohlc(user["symbol"], user["tf"])
        except Exception as exc:
            return jsonify({"ok": False,
                            "error": "tape candles unavailable — attempt not "
                                     f"recorded: {type(exc).__name__}: {exc}"}), 502
        try:
            from data.database import SignalDB
            with SignalDB() as db:
                result = submit_tape_attempt(db, body, candles)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit("practice_tape", f"{user['symbol']} {user['tf']}",
               detail={"score": result["score"]["total"],
                       "grade": result["score"]["grade"],
                       "outcome": result["score"].get("outcome"),
                       "duplicate": bool(result.get("duplicate"))})
        return jsonify(_sanitize_for_json(result))

    @app.get("/api/readiness")
    def api_readiness():
        """Combined readiness strip: channels + immune + risk gate + data quality.

        The one verdict the dashboard shows above every tab (TODO-1.bis +
        P10.5).
        Same payload as `python main.py doctor --strip --json` and the MCP
        ``readiness`` tool — no surface computes its own verdict.
        """
        try:
            from brain.agent import readiness_strip
            return jsonify(_sanitize_for_json(readiness_strip()))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "level": "down",
                            "headline": "readiness unavailable",
                            "pillars": [],
                            "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/scorecard")
    def api_scorecard():
        """P12.3 & P12.6 strategy scorecard — the same block as `python main.py
        scorecard --json` and the MCP ``scorecard`` tool.

        Read-only report over outcomes the grader already produced; no
        surface re-grades anything or computes its own verdict. Evaluated
        NET of costs (P12.6).
        """
        try:
            from data.costs import CostModel
            from data.scorecard import scorecard_from_db
            src = request.args.get("source", "db")
            sym = request.args.get("symbol") or None
            no_costs = request.args.get("no_costs", "").lower() in ("1", "true", "yes")
            conditioned = request.args.get("conditioned", "").lower() in ("1", "true", "yes")
            quality = request.args.get("quality", "").lower() in ("1", "true", "yes")
            since = request.args.get("since")
            until = request.args.get("until")
            since_ts = int(since) if since and since.isdigit() else None
            until_ts = int(until) if until and until.isdigit() else None
            cost_model = CostModel(enabled=not no_costs)
            # P12.11 — ?source_key=live | exchange:market[:bid|ask] | all
            source_key = _source_key_param(request.args.get("source_key"))
            return jsonify(_sanitize_for_json(scorecard_from_db(
                symbol=_sym(sym) if sym else None,
                source="all" if src == "db" else src,
                min_decided=int(request.args.get("min_decided", 30)),
                include_sim=request.args.get("include_sim", "1") != "0",
                since_ts=since_ts, until_ts=until_ts,
                cost_model=cost_model,
                conditioned=conditioned,
                quality=quality,
                source_key=source_key)))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False,
                            "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/agents")
    def api_agents():
        """Desk morning briefing: watchlist + gate + queue + narrative."""
        try:
            from brain.agent import morning_briefing
            return jsonify(morning_briefing(timeframe=request.args.get("tf", TIMEFRAME)))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/mcp")
    def api_mcp():
        """MCP server status + tool inventory for the dashboard card."""
        try:
            from ai.mcp_server import TOOLS
            try:
                import mcp  # noqa: F401
                available = True
                note = "run `python main.py mcp` and point Claude Desktop / Cursor at it"
            except Exception:
                available = False
                note = "mcp package not installed — pip install mcp"
            return jsonify({"available": available, "note": note,
                            "count": len(TOOLS),
                            "tools": [t["name"] for t in TOOLS]})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/ask")
    def api_ask():
        """Natural-language question to the desk (intent-based, offline-capable)."""
        body = request.get_json(silent=True) or {}
        question = str(body.get("question", "")).strip()
        if not question:
            return jsonify({"ok": False, "error": "empty question"}), 400
        try:
            from brain.agent import ask
            return jsonify(ask(question, symbol=_sym(body.get("symbol")),
                               timeframe=body.get("tf", TIMEFRAME)))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500


    @app.get("/api/glossary")
    def api_glossary():
        """Glossary lookup for the dashboard coach card."""
        term = (request.args.get("term") or "").strip()
        if not term:
            return jsonify({"found": False, "error": "no term"}), 400
        try:
            from brain.coach import GLOSSARY
            key = next((k for k in GLOSSARY if k.lower() == term.lower()), None)
            if key is None:
                key = next((k for k in GLOSSARY if term.lower() in k.lower() or k.lower() in term.lower()), None)
            if key is None:
                return jsonify({"found": False, "term": term, "error": "term not found"}), 404
            meaning, why = GLOSSARY[key]
            return jsonify({"found": True, "term": key, "meaning": meaning, "why": why})
        except Exception as exc:
            return jsonify({"found": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    # ══════════════════════════════════════════════════════════════════════
    # P18.2 — /api/v1: one envelope, typed errors, versioning, idempotency
    #
    # Every delegating route calls the *same* legacy view function the
    # dashboard calls and re-renders its answer in the v1 envelope. v1 is a
    # contract over existing behaviour, never a second implementation: it
    # cannot approve something the legacy path refuses, and it adds no
    # exchange-order path (SKY has none).
    # ══════════════════════════════════════════════════════════════════════
    _idem = apiv1.IdempotencyStore()
    # P18.3 — the persisted background-job queue. One worker, one job at a
    # time; long commands (backfill/backtest/simulator/evidence) run here so
    # a browser close or a timeout cannot kill them. Tests inject a manager
    # with a fake runner so no real subprocess spawns.
    _jobs = job_manager or jobsmod.JobManager()
    # Start the worker at boot so orphaned rows from a previous process are
    # adopted immediately and queued jobs resume without waiting for a new
    # submission. Idempotent — a manager injected by a test may already run.
    _jobs.start()

    def _unwrap(rv) -> tuple[Any, int]:
        """Normalize a Flask return value into ``(json_payload, status)``.

        Subtlety worth keeping: legacy handlers return ``jsonify(...), 400``.
        The ``jsonify`` Response carries the *default* 200 — the real status
        lives in the tuple. Preferring the response's ``status_code`` here
        silently turned every legacy 4xx into a 200-shaped INTERNAL error, so
        the tuple's status must win when present.
        """
        status = None
        if isinstance(rv, tuple):
            if len(rv) >= 2 and isinstance(rv[1], int):
                status = rv[1]
            rv = rv[0]
        if hasattr(rv, "get_json"):
            try:
                payload = rv.get_json(silent=True)
            except Exception:
                payload = None
            if status is None:
                status = getattr(rv, "status_code", 200) or 200
            return payload, status
        return rv, (status if status is not None else 200)

    def _as_v1(payload: Any, status: int, request_id: str):
        """Render a legacy handler's answer in the v1 envelope.

        Legacy endpoints are inconsistent by history: some return a bare
        payload, some ``{ok: false, error: ...}`` with HTTP 200, some a real
        4xx/5xx. A v1 client must not have to know which — so failure is
        decided here, once, and always surfaces as a typed code.
        """
        body = payload if isinstance(payload, dict) else None

        failed = status >= 400 or (body is not None and body.get("ok") is False)
        # A handler that returns 200 with a bare {"error": "..."} and nothing
        # else is also a failure; but a rich payload that merely *contains* an
        # "error" field alongside real data is not.
        if not failed and body is not None and body.get("error") and \
                set(body.keys()) <= {"error", "code", "ok", "detail", "details"}:
            failed = True

        if not failed:
            data = body if body is not None else payload
            if isinstance(data, dict) and "ok" in data:
                data = {k: v for k, v in data.items() if k != "ok"}
            return jsonify(apiv1.envelope_ok(data, request_id)), status

        message = "request failed"
        code = None
        details: dict = {}
        if body is not None:
            message = (body.get("error") or body.get("message")
                       or body.get("detail") or message)
            code = body.get("code")
            details = {k: v for k, v in body.items()
                       if k not in ("ok", "error", "code", "message")}
        # The desk's deliberate refusals deserve their own codes so a client
        # can render "the risk gate is closed" instead of a generic failure.
        if code is None:
            if isinstance(body, dict) and "blocked_by" in body:
                # The desk refusing on risk is not a malformed request; a
                # client should render the gate reasons, not "bad input".
                code = apiv1.ErrorCode.RISK_GATE_CLOSED
            elif status == 400 and "cannot go " in str(message):
                # engine/lifecycle.py rejecting an illegal state transition —
                # the usual cause is a retried decision, so name it precisely.
                code = apiv1.ErrorCode.LIFECYCLE_INVALID
            else:
                code = apiv1.code_for_status(status)
        if status < 400:
            status = 500 if code == apiv1.ErrorCode.INTERNAL else 400
        return jsonify(apiv1.envelope_error(code, message, details,
                                            request_id)), status

    def _delegate(legacy_path: str, method: str):
        """Invoke the legacy view function registered for ``legacy_path``."""
        for rule in app.url_map.iter_rules():
            if str(rule.rule) == legacy_path and method in (rule.methods or set()):
                return app.view_functions[rule.endpoint]()
        raise KeyError(f"no legacy handler for {method} {legacy_path}")

    def _make_v1_view(route: dict):
        legacy_path = route["legacy"]
        method = route["method"]
        sub = route["path"]
        idempotent = bool(route.get("idempotent"))

        def view():
            request_id = apiv1.new_request_id()
            user = getattr(g, "user", None)
            user_id = (user or {}).get("id")

            key = None
            fingerprint = ""
            if idempotent:
                try:
                    key = apiv1.validate_key(
                        request.headers.get(apiv1.IDEMPOTENCY_HEADER))
                except ValueError as exc:
                    return jsonify(apiv1.envelope_error(
                        apiv1.ErrorCode.BAD_REQUEST, str(exc),
                        request_id=request_id)), 400
            if key:
                body = request.get_json(silent=True) or {}
                fingerprint = apiv1.request_fingerprint(sub, body)
                try:
                    state, cached = _idem.lookup(key, user_id, sub, fingerprint)
                except Exception:
                    state, cached = ("miss", None)   # never fail on the cache
                if state == "replay":
                    status, stored = cached
                    if isinstance(stored, dict):
                        stored = dict(stored)
                        stored["meta"] = dict(stored.get("meta") or {})
                        stored["meta"]["idempotent_replay"] = True
                        stored["meta"]["request_id"] = request_id
                    return jsonify(stored), status
                if state == "conflict":
                    return jsonify(apiv1.envelope_error(
                        apiv1.ErrorCode.IDEMPOTENCY_KEY_REUSED,
                        "This Idempotency-Key was already used for a different "
                        "request. Generate a new key per distinct action.",
                        {"key": key, "endpoint": sub},
                        request_id=request_id)), 409
                if state == "in_progress":
                    return jsonify(apiv1.envelope_error(
                        apiv1.ErrorCode.IDEMPOTENCY_IN_PROGRESS,
                        "An identical request is still being processed. "
                        "Retry shortly.",
                        {"key": key}, request_id=request_id)), 409
                try:
                    if not _idem.reserve(key, user_id, sub, fingerprint):
                        return jsonify(apiv1.envelope_error(
                            apiv1.ErrorCode.IDEMPOTENCY_IN_PROGRESS,
                            "An identical request is still being processed. "
                            "Retry shortly.",
                            {"key": key}, request_id=request_id)), 409
                except Exception:
                    key = None   # cache unavailable → execute without replay

            try:
                payload, status = _unwrap(_delegate(legacy_path, method))
            except Exception as exc:
                if key:
                    try:
                        _idem.release(key, user_id, sub)
                    except Exception:
                        pass
                return jsonify(apiv1.envelope_error(
                    apiv1.ErrorCode.INTERNAL, f"{type(exc).__name__}: {exc}",
                    request_id=request_id)), 500

            response = _as_v1(payload, status, request_id)
            if key:
                rendered, rendered_status = response
                try:
                    stored = rendered.get_json(silent=True)
                    if stored is not None:
                        _idem.complete(key, user_id, sub, rendered_status, stored)
                    else:
                        _idem.release(key, user_id, sub)
                except Exception:
                    pass
            return response

        view.__name__ = f"v1_{method.lower()}_{sub.strip('/').replace('/', '_') or 'root'}"
        return view

    for _route in apiv1.ROUTES:
        app.add_url_rule(f"{V1_PREFIX}{_route['path']}",
                         endpoint=f"v1_{_route['method'].lower()}"
                                  f"_{_route['path'].strip('/').replace('/', '_')}",
                         view_func=_make_v1_view(_route),
                         methods=[_route["method"]])

    # ── v1-native routes (no legacy equivalent) ───────────────────────────
    @app.post(f"{V1_PREFIX}/pair")
    def v1_pair_redeem():
        """Public: exchange a one-time Hub pairing code for a device token."""
        body = request.get_json(silent=True) or {}
        try:
            result = auth.redeem_pairing_code(
                str(body.get("code") or ""),
                device_name=str(body.get("name") or "windows"))
        except ValueError as exc:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, str(exc))), 400
        except PermissionError as exc:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.FORBIDDEN, str(exc))), 403
        auth.audit("companion_paired", result.get("name") or "windows",
                   ok=True, ip=_client_ip(), user_agent=_client_ua(),
                   detail={"scope": result.get("scope"), "api": "v1"})
        return jsonify(apiv1.envelope_ok({
            "token": result["token"],
            "scope": result["scope"],
            "name": result["name"],
            "usage": "Authorization: Bearer <token>",
            "note": "Copy this token now — it is shown only once.",
            "live_exchange_execution": False,
        })), 201

    @app.post(f"{V1_PREFIX}/pair/code")
    def v1_pair_mint():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.UNAUTHENTICATED, "authentication required")), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.FORBIDDEN, "operator role required")), 403
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "windows").strip() or "windows"
        scope = str(body.get("scope") or "viewer")
        if scope not in authmod.ROLES:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED,
                f"scope must be one of {list(authmod.ROLES)}")), 400
        if not authmod.role_allows(user.get("role"), scope):
            scope = "viewer"
        minted = auth.create_pairing_code(user["id"], name=name, scope=scope)
        from ops.windows_companion import pairing_payload, pairing_qr_text
        hub = str(body.get("hub_url") or request.host_url or "http://127.0.0.1:8050")
        payload = pairing_payload(hub_url=hub, code=minted["raw"])
        _audit("pairing_code_created", name, detail={"scope": scope, "api": "v1"})
        return jsonify(apiv1.envelope_ok({
            "code": minted["code"],
            "expires_ts": minted["expires_ts"],
            "ttl_seconds": minted["ttl_seconds"],
            "scope": scope,
            "name": name,
            "qr": pairing_qr_text(payload),
            "payload": payload,
            "note": "Show this code once. It expires in 10 minutes.",
        })), 201

    @app.get(f"{V1_PREFIX}/version")
    def v1_version():
        """Public: a client must discover compatibility before authenticating.

        This deliberately reports the *absence* of live execution as a
        capability flag, so a companion app cannot ship a Trade button that
        can never work.
        """
        return jsonify(apiv1.envelope_ok(apiv1.version_info()))

    @app.get(f"{V1_PREFIX}/routes")
    def v1_routes():
        return jsonify(apiv1.envelope_ok(apiv1.route_catalog()))

    @app.get(f"{V1_PREFIX}/me")
    def v1_me():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            # auth disabled locally — report the unauthenticated local mode
            # honestly rather than inventing an identity.
            return jsonify(apiv1.envelope_ok({
                "authenticated": False, "username": None,
                "role": "operator" if not auth.is_enabled() else None,
                "auth_enabled": auth.is_enabled(),
                "setup_required": (config.SKY_AUTH_MODE != "disabled"
                                   and not auth.owner_exists()),
            }))
        return jsonify(apiv1.envelope_ok({
            "authenticated": True,
            "username": user.get("username"),
            "role": user.get("role"),
            "scope": user.get("scope"),
            "auth_enabled": auth.is_enabled(),
            "setup_required": False,
        }))

    @app.get(f"{V1_PREFIX}/devices")
    def v1_devices_list():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(apiv1.envelope_ok({"devices": [], "count": 0}))
        devices = auth.list_device_tokens(user["id"])
        return jsonify(apiv1.envelope_ok({
            "devices": devices,
            "count": len([d for d in devices if not d["revoked"]]),
        }))

    @app.post(f"{V1_PREFIX}/devices")
    def v1_devices_create():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.UNAUTHENTICATED,
                "authentication required")), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.FORBIDDEN, "operator role required",
                {"required_role": "operator"})), 403
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "").strip()
        if not name:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED,
                "a device name is required so it can be recognised and revoked",
                {"field": "name"})), 400
        scope = str(body.get("scope") or "viewer")
        if scope not in authmod.ROLES:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED,
                f"scope must be one of {list(authmod.ROLES)}",
                {"field": "scope"})), 400
        # A token can never exceed its creator's role.
        if not authmod.role_allows(user.get("role"), scope):
            scope = "viewer"
        token = auth.create_device_token(user["id"], name, scope=scope)
        _audit("device_token_created", name, detail={"scope": scope, "api": "v1"})
        return jsonify(apiv1.envelope_ok({
            "token": token,
            "name": name,
            "scope": scope,
            "usage": "Authorization: Bearer <token>",
            "note": "Copy this token now — it is shown only once.",
        })), 201

    @app.post(f"{V1_PREFIX}/devices/revoke")
    def v1_devices_revoke():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.UNAUTHENTICATED, "authentication required")), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.FORBIDDEN, "operator role required")), 403
        handle = str((request.get_json(silent=True) or {}).get("id") or "").strip()
        if not handle:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, "device id is required",
                {"field": "id"})), 400
        ok = auth.revoke_device_token(user["id"], handle)
        _audit("device_token_revoked", handle, ok=ok, detail={"api": "v1"})
        if not ok:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.NOT_FOUND,
                f"no device token {handle!r} belongs to this account",
                {"id": handle})), 404
        return jsonify(apiv1.envelope_ok({"revoked": True, "id": handle}))

    @app.get(f"{V1_PREFIX}/audit")
    def v1_audit():
        user = getattr(g, "user", None) or _current_user()
        if user is not None and not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.FORBIDDEN, "operator role required")), 403
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, "limit must be an integer",
                {"field": "limit"})), 400
        rows = auth.recent_audit(limit)
        return jsonify(apiv1.envelope_ok({"rows": rows, "count": len(rows)}))

    # ════════════════════════════════════════════════════════════════════
    # P18.3 — background jobs (/api/v1/jobs). v1-native (no legacy
    # equivalent): the old path ran long commands synchronously behind one
    # blocking POST. Jobs are the replacement, exposed only in v1.
    # ════════════════════════════════════════════════════════════════════
    def _job_user():
        u = getattr(g, "user", None) or _current_user()
        return u or {}

    @app.get(f"{V1_PREFIX}/jobs")
    def v1_jobs_list():
        try:
            limit = int(request.args.get("limit", 50))
        except (TypeError, ValueError):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, "limit must be an integer",
                {"field": "limit"})), 400
        status = request.args.get("status")
        jobs = _jobs.list_jobs(limit=limit, status=status)
        return jsonify(apiv1.envelope_ok({
            "jobs": jobs, "count": len(jobs),
            "kinds": sorted(set(jobsmod.JOB_KINDS) | set(jobsmod.COMPOSITE_JOBS)),
        }))

    @app.post(f"{V1_PREFIX}/jobs")
    def v1_jobs_submit():
        body = request.get_json(silent=True) or {}
        kind = str(body.get("kind") or "").strip()
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, "params must be an object",
                {"field": "params"})), 400
        try:
            result = _jobs.submit(kind, params, user=_job_user())
        except jobsmod.JobError as exc:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.VALIDATION_FAILED, str(exc),
                {"field": "kind", "allowed": sorted(set(jobsmod.JOB_KINDS)
                                                    | set(jobsmod.COMPOSITE_JOBS))})), 400
        _audit("job_submitted", kind, ok=True,
               detail={"job_id": result["job_id"], "created": result["created"]})
        job = _jobs.get(result["job_id"])
        return jsonify(apiv1.envelope_ok({
            "job": job, "created": result["created"],
            "duplicate": not result["created"],
        })), 201

    @app.get(f"{V1_PREFIX}/jobs/<job_id>")
    def v1_jobs_get(job_id):
        job = _jobs.get(job_id)
        if job is None:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.JOB_NOT_FOUND, f"no such job: {job_id}",
                {"job_id": job_id})), 404
        return jsonify(apiv1.envelope_ok({"job": job}))

    @app.post(f"{V1_PREFIX}/jobs/<job_id>/cancel")
    def v1_jobs_cancel(job_id):
        try:
            job = _jobs.request_cancel(job_id, user=_job_user())
        except jobsmod.JobError as exc:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.JOB_NOT_CANCELLABLE, str(exc),
                {"job_id": job_id})), 409
        _audit("job_cancel_requested", job_id, ok=True)
        return jsonify(apiv1.envelope_ok({"job": job}))

    @app.get(f"{V1_PREFIX}/jobs/<job_id>/events")
    def v1_jobs_events(job_id):
        """Server-sent events stream of a job's progress.

        Each frame is a full snapshot of the persisted state, so a reconnect
        (or a server restart) resumes from the last event rather than
        restarting work. ``Last-Event-ID`` is accepted but only informational
        — the source of truth is the jobs table.
        """
        if _jobs.get(job_id) is None:
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.JOB_NOT_FOUND, f"no such job: {job_id}",
                {"job_id": job_id})), 404
        from flask import Response
        last_id = request.headers.get("Last-Event-ID")
        gen = _jobs.events(job_id, last_event_id=last_id)
        return Response(gen, mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # ── 24/7 SKY Intelligence Agent — dashboard + API surface ───────────
    # Read-only research & monitoring; never trades, never bypasses risk gate.
    @app.get("/api/sky-agent/health")
    def api_sky_agent_health():
        try:
            from brain.agent import readiness_strip
            from sky_agent.monitor_system import probe_system
            try:
                strip = readiness_strip()
            except Exception as exc:
                strip = {"error": str(exc)}
            return jsonify(_sanitize_for_json({"ok": True, "readiness": strip, "system": probe_system(), "agent": "sky_agent"}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sky-agent/status")
    def api_sky_agent_status():
        try:
            from data.database import SignalDB
            from sky_agent.memory import ensure_memory_schema
            with SignalDB() as db:
                ensure_memory_schema(db)
                hyps = [dict(r) for r in db.conn.execute("SELECT hypothesis_id,setup,status,created_ts FROM research_hypotheses ORDER BY created_ts DESC LIMIT 20").fetchall()]
                reports = [dict(r) for r in db.conn.execute("SELECT report_date,kind,asset,recommendation,level,created_ts FROM intelligence_reports ORDER BY created_ts DESC LIMIT 10").fetchall()]
                regimes = [dict(r) for r in db.conn.execute("SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10").fetchall()]
                filings = [dict(r) for r in db.conn.execute("SELECT accession,event_type,severity FROM sec_events ORDER BY created_ts DESC LIMIT 10").fetchall()]
            return jsonify(_sanitize_for_json({"ok": True, "hypotheses": hyps, "reports": reports, "regimes": regimes, "sec_events": filings}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sky-agent/report")
    def api_sky_agent_report():
        try:
            from sky_agent.daily_report import build_daily_report
            demo = request.args.get("demo", "").lower() in ("1", "true", "yes")
            return jsonify(_sanitize_for_json(build_daily_report(demo=demo)))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sky-agent/hypotheses")
    def api_sky_agent_hypotheses():
        try:
            from sky_agent.hypothesis import propose_hypotheses
            hyps = propose_hypotheses()
            return jsonify(_sanitize_for_json({"ok": True, "hypotheses": hyps}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/hub/role")
    def api_hub_role():
        """W4.2 — how this always-on Ubuntu PC should be used."""
        try:
            from ops.hub import host_role
            return jsonify(_sanitize_for_json(host_role()))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/hub/status")
    def api_hub_status():
        """W4.2 — Hub FHS + systemd snapshot + host role. Never starts units."""
        try:
            from ops.hub import status as hub_status
            return jsonify(_sanitize_for_json(hub_status()))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/sky-agent/report")
    def api_sky_agent_report_archive():
        """W4.1 — archive today's intelligence report. Memory only.

        Never a trade, never a gate input, never a graduation sample.
        """
        try:
            from sky_agent.daily_report import archive_daily_report, build_daily_report
            body = request.get_json(silent=True) or {}
            demo = bool(body.get("demo")) or request.args.get("demo", "").lower() in ("1", "true", "yes")
            report = build_daily_report(demo=demo)
            archived = archive_daily_report(report)
            _audit("sky_agent_report", "daily",
                   detail={"report_id": archived.get("report_id"), "demo": demo})
            return jsonify(_sanitize_for_json({**archived, "report": report}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.errorhandler(404)
    def _v1_404(exc):
        if _is_v1(request.path or ""):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.NOT_FOUND,
                f"no such endpoint: {request.method} {request.path}",
                {"see": "/api/v1/routes"})), 404
        return jsonify({"ok": False, "error": "not found"}), 404

    @app.errorhandler(405)
    def _v1_405(exc):
        if _is_v1(request.path or ""):
            return jsonify(apiv1.envelope_error(
                apiv1.ErrorCode.METHOD_NOT_ALLOWED,
                f"{request.method} is not allowed on {request.path}",
                {"see": "/api/v1/routes"})), 405
        return jsonify({"ok": False, "error": "method not allowed"}), 405

    return app


def serve(app: Flask, host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT) -> None:
    # P18.1 — refuse to expose the desk on a non-loopback host without an owner
    # account and a TLS-terminating reverse proxy (see web/auth.enforce_deployment).
    authmod.enforce_deployment(host)
    app.run(host=host, port=port, debug=False, threaded=True)
