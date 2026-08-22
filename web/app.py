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
    from web.routes_chart import register as _register_chart
    _register_chart(app, dict(_audit=_audit))
    from web.routes_system import register as _register_system
    _jobs = _register_system(app, dict(_audit=_audit,
                                      job_manager=job_manager,
                                      V1_PREFIX=V1_PREFIX))
    from web.routes_v1 import register as _register_v1
    _register_v1(app, dict(auth=auth, _audit=_audit,
                          _client_ip=_client_ip, _client_ua=_client_ua,
                          _current_user=_current_user, _is_v1=_is_v1,
                          _jobs=_jobs, V1_PREFIX=V1_PREFIX))
    return app


def serve(app: Flask, host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT) -> None:
    # P18.1 — refuse to expose the desk on a non-loopback host without an owner
    # account and a TLS-terminating reverse proxy (see web/auth.enforce_deployment).
    authmod.enforce_deployment(host)
    app.run(host=host, port=port, debug=False, threaded=True)
