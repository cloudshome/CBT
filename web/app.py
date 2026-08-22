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
  POST /api/terminal/confirm  terminal ticket → desk approval → enrolled paper position (T3)
  POST /api/terminal/close    terminal manual close of an open paper position → auto-journal (T3)
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
from config import SYMBOL, SYMBOLS, TIMEFRAME, MIN_CONFIDENCE, DASHBOARD_HOST, DASHBOARD_PORT, VERSION
from data.symbols import symbol_choices
from data.sample_client import maybe_client
from web import auth as authmod
from web import api_v1 as apiv1
from web import jobs as jobsmod
# Refactor step 1 (ROADMAP §19): the scan-payload pipeline lives in
# web/payload.py.  Names are re-exported here so every existing import of
# web.app (routes, tests) keeps working unchanged.
from web.payload import (  # noqa: F401 — re-exported for back-compat
    _CACHE, _LAST_GOOD, _SCAN_TIMEOUT,
    _attach_management, _attach_sentiment, _basic_scan, _persist,
    _sanitize_for_json, _scan_row_to_payload, _source_key_param, _sym,
    build_payload, compute_payload,
)


# Keep this a normal triple-quoted string so the lightweight CI extractor can
# read it directly. Embedded JavaScript deliberately uses `nl` below instead
# of a `\n` string escape, which stays correct without a raw Python literal.
# The terminal template (HTML/JS) lives in web/static/terminal.html; loaded at import so the served output is byte-identical to the inline
# literal it replaces (rendered via render_template_string below).
HTML = (Path(__file__).resolve().parent / "static" / "terminal.html").read_text(encoding="utf-8")


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
        if path == "/" or path.startswith("/static/") or path in ("/sw.js", "/manifest.json", "/offline.html", "/offline", "/api/push/vapid-key"):
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

    from web.routes_auth import register as _register_auth
    _register_auth(app, dict(auth=auth, _auth_state=_auth_state,
                            _current_user=_current_user,
                            _client_ip=_client_ip,
                            _client_ua=_client_ua,
                            _audit=_audit))
    from web.routes_scan import register as _register_scan
    _register_scan(app, None)
    from web.routes_paper import register as _register_paper
    _register_paper(app, dict(_audit=_audit))
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

    @app.get("/api/ticket/meta")
    def api_ticket_meta():
        """Honest inputs for the terminal trade ticket (T4).

        The ticket's risk-dollar and fee estimates must never be invented
        client-side. This returns the real account balance (``ACCOUNT_BALANCE``,
        0 when unset — the UI shows ``—`` rather than a fake $100k) and the
        per-symbol cost model (``data.costs.cost_model_for_symbol``) the
        backtester uses, so the fee estimate agrees with the desk's cost
        doctrine: round-trip taker fee + full spread + slippage, no funding on
        gold spot. Read-only; no order path.
        """
        from config import ACCOUNT_BALANCE, RISK_PCT, MAX_RISK_PCT, KELLY_MAX_RISK_PCT
        from data.costs import (SPREADS, DEFAULT_HALF_SPREAD, DEFAULT_HOLDING_HOURS,
                                DEFAULT_FUNDING_RATE_8H, cost_model_for_symbol,
                                is_gold_symbol)
        symbol = _sym(request.args.get("symbol", SYMBOL))
        model = cost_model_for_symbol(symbol)
        is_gold = is_gold_symbol(symbol)
        half_spread = (model.spread_pct if model.spread_pct is not None
                       else SPREADS.get(symbol, DEFAULT_HALF_SPREAD))
        fee_per_side = model.spot_fee_pct if model.market == "spot" else model.taker_fee_pct
        round_trip_cost_pct = round(2.0 * fee_per_side + 2.0 * half_spread
                                    + 2.0 * model.slip_pct, 6)
        return jsonify(_sanitize_for_json({
            "symbol": symbol,
            "market": model.market,
            "account_balance": float(ACCOUNT_BALANCE or 0.0),
            "account_configured": bool(ACCOUNT_BALANCE and ACCOUNT_BALANCE > 0),
            "default_risk_pct": RISK_PCT,
            "max_risk_pct": MAX_RISK_PCT,
            "kelly_max_risk_pct": KELLY_MAX_RISK_PCT,
            "taker_fee_pct": model.taker_fee_pct,
            "spot_fee_pct": model.spot_fee_pct,
            "half_spread_pct": half_spread,
            "slip_pct": model.slip_pct,
            "funding_rate_8h": 0.0 if is_gold else DEFAULT_FUNDING_RATE_8H,
            "holding_hours": DEFAULT_HOLDING_HOURS,
            "round_trip_cost_pct": round_trip_cost_pct,
            "note": (None if ACCOUNT_BALANCE
                     else "Set ACCOUNT_BALANCE in .env to enable position sizing."),
        }))

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

    # ── T3 — Trade Terminal: confirm ticket → desk path → paper position ─
    @app.post("/api/terminal/confirm")
    def api_terminal_confirm():
        """Turn a confirmed terminal ticket into an enrolled paper trade.

        T3 — the product expression of the money path. This does not bypass
        the desk: the ticket becomes a real scan row in the human approval
        queue (``save_scan``, PENDING_REVIEW), the risk & discipline gate is
        freshly evaluated on the server immediately before the APPROVED
        decision, the journal-first discipline (W3.3) applies exactly as in
        ``/api/review``, and the paper runner enrolls + fills the position.
        ``ticket_id`` makes a retried confirm idempotent. Market tickets are
        paper-filled at the confirmed entry; limit/conditional tickets wait
        for the entry level like any conditional desk plan. Still paper-only;
        never an exchange order.
        """
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol"))
        timeframe = str(body.get("timeframe") or TIMEFRAME)
        action = str(body.get("action") or "").upper()
        ticket_type = str(body.get("ticket_type") or "market").lower()
        if action not in ("BUY", "SELL"):
            return jsonify({"error": "action must be BUY or SELL"}), 400
        if ticket_type not in ("market", "limit", "conditional"):
            return jsonify({"error": f"bad ticket_type {ticket_type!r} "
                                     "(market | limit | conditional)"}), 400
        try:
            entry = float(body.get("entry"))
            stop = float(body.get("stop_loss"))
        except (TypeError, ValueError):
            return jsonify({"error": "entry and stop_loss are required numbers"}), 400
        if entry <= 0 or stop <= 0:
            return jsonify({"error": "entry and stop_loss must be positive"}), 400
        # Side sanity — fail closed on an inverted stop, never on a tight one.
        if action == "BUY" and stop >= entry:
            return jsonify({"error": "BUY stop must be below entry"}), 400
        if action == "SELL" and stop <= entry:
            return jsonify({"error": "SELL stop must be above entry"}), 400
        tps = []
        for value in body.get("take_profits") or []:
            try:
                tps.append(float(value))
            except (TypeError, ValueError):
                return jsonify({"error": "take_profits must be numbers"}), 400
        tps = [t for t in tps if t > 0]
        if tps:
            for i in (1, 2):
                if len(tps) > i and tps[i] <= tps[i - 1]:
                    return jsonify({"error": "take_profits must be strictly increasing"}), 400
        tp1 = tps[0] if tps else None
        rr = round(abs(tp1 - entry) / abs(entry - stop), 3) if tp1 is not None else None
        risk_raw = body.get("risk_pct")
        try:
            # `or 0.5` would silently swallow an explicit 0 — fail closed.
            risk_pct = float(risk_raw) if risk_raw not in (None, "") else 0.5
        except (TypeError, ValueError):
            return jsonify({"error": "risk_pct must be a number"}), 400
        if not (0 < risk_pct <= 100):
            return jsonify({"error": "risk_pct must be in (0, 100]"}), 400
        plan_type = (str(body.get("plan_type") or "Manual").strip()[:60]
                     or "Manual")
        conf = body.get("confidence")
        try:
            conf = int(conf) if conf not in (None, "") else None
        except (TypeError, ValueError):
            conf = None
        conf_label = str(body.get("confidence_label") or "").strip()[:20] or None
        reason = str(body.get("reason") or "manual terminal ticket")[:300]
        ticket_id = str(body.get("ticket_id") or "")[:80]
        sentiment = body.get("sentiment") if isinstance(body.get("sentiment"), dict) else {}
        now_ms = int(time.time() * 1000)
        signal_id = (f"terminal_{ticket_id}" if ticket_id
                     else f"terminal_{symbol}_{now_ms}_{secrets.token_hex(3)}")
        from data.database import SignalDB
        from brain.risk_gate import evaluate as gate_evaluate
        from data.paper_trading import PaperTradingRunner
        with SignalDB() as db:
            # Idempotency: a retried confirm reuses the same ticket scan
            # instead of enrolling a second position.
            existing = None
            if ticket_id:
                row = db.conn.execute(
                    "SELECT id, status FROM scans WHERE signal_id=?",
                    (signal_id,)).fetchone()
                if row:
                    existing = dict(row)
            if existing:
                paper = db.paper_trade_for_scan(int(existing["id"]))
                if existing["status"] in ("CLOSED", "REJECTED", "SKIPPED"):
                    return jsonify({"ok": False,
                                    "error": f"ticket already used "
                                             f"(scan #{existing['id']} is "
                                             f"{existing['status']})",
                                    "scan_id": existing["id"],
                                    "status": existing["status"]}), 409
                return jsonify({"ok": True, "duplicate": True,
                                "scan_id": existing["id"],
                                "status": existing["status"],
                                "paper_trade": paper}), 200
            plan = {
                "id": "terminal", "type": plan_type, "action": action,
                "condition": (reason or "manual terminal ticket"),
                "trigger_level": entry, "entry": entry, "stop_loss": stop,
                "take_profits": tps, "risk_reward": rr,
                "confidence": conf, "confidence_label": conf_label,
                # market tickets fill at the confirmed entry; limit and
                # conditional tickets wait for the level, like desk plans.
                "status": "active" if ticket_type == "market" else "waiting",
            }
            payload = {
                "signal": {
                    "signal_id": signal_id, "timestamp": now_ms,
                    "asset": symbol, "timeframe": timeframe, "action": action,
                    "entry": entry, "stop_loss": stop, "take_profit": tp1,
                    "risk_reward": rr, "confidence": conf_label,
                    "reason": reason, "signal_type": "SIGNAL",
                },
                "plans": [plan],
                "snapshot": {"features": {
                    "price": entry, "score_used": conf,
                    "regime_name": str(body.get("regime") or "").strip()[:40],
                }},
                "market_context": {},
                "sentiment": sentiment,
            }
            scan_id = db.save_scan(payload)
            # Fresh server-side gate read immediately before the decision —
            # same evaluation the desk uses, with the ticket's own plan type.
            gate = gate_evaluate(db, symbol=symbol, plan_type=plan_type,
                                 action=action)
            force = bool(body.get("force"))
            if not gate["allowed"] and not force:
                _audit("terminal_confirm", symbol, ok=False,
                       detail={"scan_id": scan_id, "action": action,
                               "plan_type": plan_type,
                               "blocked_by": gate["blocked_by"]})
                return jsonify({
                    "error": "Risk gate CLOSED — " + "; ".join(gate["blocked_by"]),
                    "blocked_by": gate["blocked_by"],
                    "force_available": config.SKY_ALLOW_FORCE_APPROVE,
                }), 409
            if force and not config.SKY_ALLOW_FORCE_APPROVE:
                return jsonify({"error": "force confirm is disabled "
                                         "(SKY_ALLOW_FORCE_APPROVE is not set)"}), 403
            # W3.3 journal-first discipline — same fail-closed population and
            # audited escape as /api/review.
            if not body.get("acknowledge_journal"):
                from brain.weekly import missing_journals
                jg = missing_journals(db)
                if jg["missing"]:
                    return jsonify({
                        "error": (f"Journal-first discipline: {jg['missing']} "
                                  "decided real trade(s) unjournaled — journal "
                                  "them before the next commitment"),
                        "journal_block": jg,
                        "acknowledge_available": True,
                    }), 409
            reviewer = (getattr(g, "user", None) or {}).get("username") or "terminal"
            new_status = db.update_status(
                scan_id, "APPROVED",
                note=(f"terminal confirm: {action} {entry:,.8g} SL {stop:,.8g} "
                      f"TPs {tps} ({plan_type}, {ticket_type}, {risk_pct}% risk)"),
                reviewer=reviewer)
            if new_status is None:
                return jsonify({"error": f"scan #{scan_id} not found"}), 404
            run = PaperTradingRunner(db=db, client=maybe_client()).run_once(
                symbol=symbol).as_dict()
            paper = db.paper_trade_for_scan(scan_id)
            scan = db.get_scan(scan_id)
        _audit("terminal_confirm", symbol,
               detail={"scan_id": scan_id, "action": action, "entry": entry,
                       "stop_loss": stop, "take_profits": tps,
                       "risk_pct": risk_pct, "plan_type": plan_type,
                       "ticket_type": ticket_type, "forced": force,
                       "acknowledged_journal": bool(body.get("acknowledge_journal"))})
        return jsonify(_sanitize_for_json({
            "ok": True, "scan_id": scan_id,
            "status": (scan or {}).get("status"),
            "gate": {"allowed": gate["allowed"],
                     "blocked_by": gate["blocked_by"]},
            "paper_trade": paper, "run": run,
        }))

    @app.post("/api/terminal/close")
    def api_terminal_close():
        """Close one open paper position from the terminal (T3).

        The scan lifecycle advances exactly like the desk close decision, and
        the paper row is closed with the real economic outcome: the existing
        ``TP_HIT`` / ``STOP_LOSS`` buckets (the populations every discipline
        surface — win-rate, journal gate, graduation — already counts), with
        ``close_reason`` recording that this was a manual terminal close and
        the exact exit. A position still ``WAITING_ENTRY`` is cancelled —
        nothing was traded, nothing needs journaling. Paper-only; never an
        exchange order.
        """
        body = request.get_json(silent=True) or {}
        try:
            trade_id = int(body.get("trade_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "trade_id is required"}), 400
        exit_price = body.get("exit_price")
        if exit_price not in (None, ""):
            try:
                exit_price = float(exit_price)
            except (TypeError, ValueError):
                return jsonify({"error": "exit_price must be a number"}), 400
            if exit_price <= 0:
                return jsonify({"error": "exit_price must be positive"}), 400
        from data.database import SignalDB
        from engine.lifecycle import LifecycleError
        reviewer = (getattr(g, "user", None) or {}).get("username") or "terminal"
        now_ms = int(time.time() * 1000)
        with SignalDB() as db:
            trade = db.get_paper_trade(trade_id)
            if trade is None:
                return jsonify({"error": f"paper trade #{trade_id} not found"}), 404
            if trade.get("status") not in ("WAITING_ENTRY", "OPEN"):
                return jsonify({"ok": False,
                                "error": f"paper trade #{trade_id} is already "
                                         f"{trade.get('status')}",
                                "status": trade.get("status")}), 409
            scan = db.get_scan(int(trade["scan_id"]))
            if scan is None:
                return jsonify({"error": f"scan #{trade['scan_id']} not found"}), 404
            scan_status = scan.get("status")

            if trade.get("status") == "WAITING_ENTRY":
                db.cancel_paper_trade(trade_id, reason="terminal close before entry",
                                      closed_ts=now_ms)
                if scan_status == "APPROVED":
                    try:
                        db.update_status(int(trade["scan_id"]), "SKIPPED",
                                         note="terminal close before entry",
                                         reviewer=reviewer)
                    except LifecycleError:
                        pass
                _audit("terminal_close", str(trade.get("symbol")),
                       detail={"trade_id": trade_id, "scan_id": trade["scan_id"],
                               "outcome": "NOT_FILLED"})
                return jsonify({"ok": True, "trade_id": trade_id,
                                "scan_id": trade["scan_id"], "status": "CANCELLED",
                                "outcome": None, "exit_price": None,
                                "rr_achieved": None, "journal_required": False})

            entry = float(trade["entry_price"] or trade["entry"])
            stop = float(trade["stop_loss"])
            risk = abs(entry - stop)
            if exit_price is None:
                exit_price = (float(trade["last_price"])
                              if trade.get("last_price") is not None else None)
            if exit_price is None:
                try:
                    df = maybe_client().klines(trade["symbol"] or SYMBOL,
                                               trade["timeframe"] or TIMEFRAME, 2)
                    exit_price = float(df["close"].iloc[-1])
                except Exception:
                    exit_price = None
            if exit_price is None:
                return jsonify({"error": "no exit price available — pass "
                                         "exit_price or let the paper runner "
                                         "populate last_price first"}), 409
            side = str(trade["action"]).upper()
            rr = round((entry - exit_price) / risk if side == "SELL"
                       else (exit_price - entry) / risk, 3)
            tp = trade.get("take_profit")
            if side == "SELL":
                hit_tp = tp is not None and exit_price <= float(tp)
                hit_sl = exit_price >= stop
            else:
                hit_tp = tp is not None and exit_price >= float(tp)
                hit_sl = exit_price <= stop
            if hit_tp:
                outcome = "TP_HIT"
                reason = "manual terminal close at/through target"
            elif hit_sl:
                outcome = "STOP_LOSS"
                reason = "manual terminal close at/through stop"
            elif rr >= 0:
                outcome = "TP_HIT"
                reason = "manual terminal close in profit before target"
            else:
                outcome = "STOP_LOSS"
                reason = "manual terminal close in loss before stop"
            # Lifecycle: EXECUTED → CLOSED. A trade the runner never advanced
            # past APPROVED is advanced honestly first (fill at its entry).
            try:
                if scan_status == "APPROVED":
                    db.update_status(int(trade["scan_id"]), "EXECUTED",
                                     note=f"terminal close fill at entry {entry:,.8g}",
                                     reviewer=reviewer)
                db.update_status(int(trade["scan_id"]), "CLOSED",
                                 note=(f"terminal manual close at {exit_price:,.8g} "
                                       f"— {outcome} ({rr:+.2f}R) — {reason}"),
                                 reviewer=reviewer)
            except LifecycleError as exc:
                return jsonify({"error": f"scan cannot be closed: {exc.message}"}), 409
            closed = db.close_paper_trade(
                trade_id, outcome=outcome, exit_price=exit_price,
                rr_achieved=rr, close_reason=reason, closed_ts=now_ms,
                last_price=exit_price)
            if not closed:
                return jsonify({"error": "position was closed concurrently "
                                         "(runner or another session)"}), 409
        _audit("terminal_close", str(trade.get("symbol")),
               detail={"trade_id": trade_id, "scan_id": trade["scan_id"],
                       "exit_price": exit_price, "outcome": outcome,
                       "rr_achieved": rr})
        return jsonify({"ok": True, "trade_id": trade_id,
                        "scan_id": trade["scan_id"], "status": "CLOSED",
                        "outcome": outcome, "exit_price": exit_price,
                        "rr_achieved": rr, "journal_required": True})

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
