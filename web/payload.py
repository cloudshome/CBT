"""web/payload.py — scan-payload computation helpers (extracted from web/app.py).

The dashboard's payload pipeline used to live inline in ``web/app.py``; this
module owns it so the web layer's route file stays about routes.  Behaviour is
byte-identical to the pre-extraction code — the functions here are the same
functions, moved without edits (refactor step 1 of the app.py/main.py
maintainability debt, ROADMAP §19).

Design notes
------------
* ``compute_payload`` runs the full analysis (MTF + context + styles + memory)
  in a watchdog thread with a hard ``_SCAN_TIMEOUT``; on timeout it falls back
  to the last-good payload for that exact (symbol, timeframe) or the
  engine-only ``_basic_scan`` — never a payload for the wrong market.
* ``_persist`` saves the scan to the learning DB deduped by ``signal_id`` and
  applies the desk-first (decision A4) status logic.
* Everything here is presentation/orchestration — no threshold moves, no
  order path.
"""

from __future__ import annotations

import json
import time

import config
from config import BARS, DEFAULT_RISK_REWARD, MIN_CONFIDENCE, SYMBOL
from data.sample_client import maybe_client
from data.symbols import normalize_symbol, resolve_symbol
from engine.signal_engine import analyze_frame
from output.signal_schema import validate_output

_CACHE: dict = {"payload": None, "ts": 0, "ttl": 40}
_LAST_GOOD: dict[tuple[str, str], dict] = {}   # last successful payload by (symbol, timeframe)

_SCAN_TIMEOUT = 45  # seconds — hard cap on a full analysis; fall back below


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
