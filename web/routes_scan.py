"""web/routes_scan.py — scan/sentiment/intelligence/pending routes (extracted from web/app.py).

Refactor step 4 (ROADMAP §19): these handlers used to live inline inside
``make_app``; they live here now.  They need no make_app closures — the
payload pipeline is imported directly from ``web.payload``.  ``register``
keeps the uniform (app, ctx) shape used by every routes_* module.
"""

from __future__ import annotations

from flask import jsonify, request

from config import SYMBOL, TIMEFRAME
from web.payload import _CACHE, _sanitize_for_json, _sym, compute_payload


def register(app, ctx):
    @app.get("/api/scan")
    def api_scan():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        force = request.args.get("force") == "1"
        try:
            if force:
                _CACHE.update(payload=None, ts=0, ttl=_CACHE.get("ttl", 40))
            return jsonify(
                _sanitize_for_json(compute_payload(symbol, tf, save=True, use_cache=not force))
            )
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
                "available": False,
                "score": 0.0,
                "direction": "neutral",
                "label": "NO DATA",
                "color": "#5f6d84",
                "intensity": 0.0,
                "duration_min": 0.0,
                "duration_text": "—",
                "history": [],
            }
            return jsonify(
                _sanitize_for_json({"symbol": symbol, "timeframe": tf, "sentiment": sent})
            )
        except Exception as exc:
            return jsonify(
                {
                    "symbol": symbol,
                    "timeframe": tf,
                    "sentiment": {
                        "available": False,
                        "score": 0.0,
                        "direction": "neutral",
                        "label": "NO DATA",
                        "color": "#5f6d84",
                        "intensity": 0.0,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }
            ), 200

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
            return jsonify(
                {
                    "asset": symbol,
                    "signal": "NO TRADE",
                    "confidence": 0,
                    "reason": [f"Insufficient market data: {type(exc).__name__}: {exc}"],
                }
            ), 200

    @app.get("/api/pending")
    def api_pending():
        from brain.coach import management_checklist
        from data.database import SignalDB

        with SignalDB() as db:
            pending = db.pending_reviews()
        for item in pending:
            tp = item.get("take_profit")
            item["management"] = management_checklist(
                {
                    "entry": item.get("entry"),
                    "stop_loss": item.get("stop_loss"),
                    "take_profits": [tp] if tp is not None else [],
                }
            )
        return jsonify({"pending": pending})
