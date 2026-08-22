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
