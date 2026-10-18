"""web/routes_v1.py — v1-native routes + 24/7 SKY agent surface (extracted from web/app.py).

Refactor step 4 (ROADMAP §19): the v1-native endpoints (pair/version/routes/
me/devices/audit/jobs), the job-user helper and the sky-agent/hub handlers
used to live inline inside ``make_app``; they live here now.  Handler bodies
are semantically identical to the original (exact string match).  The
before-request auth gate stays in ``make_app``.
"""

from __future__ import annotations

from flask import g, jsonify, request

import config
from web import api_v1 as apiv1
from web import auth as authmod
from web import jobs as jobsmod
from web.payload import _sanitize_for_json


def register(app, ctx):
    auth = ctx["auth"]
    _audit = ctx["_audit"]
    _client_ip = ctx["_client_ip"]
    _client_ua = ctx["_client_ua"]
    _current_user = ctx["_current_user"]
    _is_v1 = ctx["_is_v1"]
    _jobs = ctx["_jobs"]
    V1_PREFIX = ctx["V1_PREFIX"]

    # ── v1-native routes (no legacy equivalent) ───────────────────────────
    @app.post(f"{V1_PREFIX}/pair")
    def v1_pair_redeem():
        """Public: exchange a one-time Hub pairing code for a device token."""
        body = request.get_json(silent=True) or {}
        try:
            result = auth.redeem_pairing_code(
                str(body.get("code") or ""),
                device_name=str(body.get("name") or "windows"),
            )
        except ValueError as exc:
            return jsonify(apiv1.envelope_error(apiv1.ErrorCode.VALIDATION_FAILED, str(exc))), 400
        except PermissionError as exc:
            return jsonify(apiv1.envelope_error(apiv1.ErrorCode.FORBIDDEN, str(exc))), 403
        auth.audit(
            "companion_paired",
            result.get("name") or "windows",
            ok=True,
            ip=_client_ip(),
            user_agent=_client_ua(),
            detail={"scope": result.get("scope"), "api": "v1"},
        )
        return jsonify(
            apiv1.envelope_ok(
                {
                    "token": result["token"],
                    "scope": result["scope"],
                    "name": result["name"],
                    "usage": "Authorization: Bearer <token>",
                    "note": "Copy this token now — it is shown only once.",
                    "live_exchange_execution": False,
                }
            )
        ), 201

    @app.post(f"{V1_PREFIX}/pair/code")
    def v1_pair_mint():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.UNAUTHENTICATED, "authentication required")
            ), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.FORBIDDEN, "operator role required")
            ), 403
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "windows").strip() or "windows"
        scope = str(body.get("scope") or "viewer")
        if scope not in authmod.ROLES:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    f"scope must be one of {list(authmod.ROLES)}",
                )
            ), 400
        if not authmod.role_allows(user.get("role"), scope):
            scope = "viewer"
        minted = auth.create_pairing_code(user["id"], name=name, scope=scope)
        from ops.windows_companion import pairing_payload, pairing_qr_text

        hub = str(body.get("hub_url") or request.host_url or "http://127.0.0.1:8050")
        payload = pairing_payload(hub_url=hub, code=minted["raw"])
        _audit("pairing_code_created", name, detail={"scope": scope, "api": "v1"})
        return jsonify(
            apiv1.envelope_ok(
                {
                    "code": minted["code"],
                    "expires_ts": minted["expires_ts"],
                    "ttl_seconds": minted["ttl_seconds"],
                    "scope": scope,
                    "name": name,
                    "qr": pairing_qr_text(payload),
                    "payload": payload,
                    "note": "Show this code once. It expires in 10 minutes.",
                }
            )
        ), 201

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
            return jsonify(
                apiv1.envelope_ok(
                    {
                        "authenticated": False,
                        "username": None,
                        "role": "operator" if not auth.is_enabled() else None,
                        "auth_enabled": auth.is_enabled(),
                        "setup_required": (
                            config.SKY_AUTH_MODE != "disabled" and not auth.owner_exists()
                        ),
                    }
                )
            )
        return jsonify(
            apiv1.envelope_ok(
                {
                    "authenticated": True,
                    "username": user.get("username"),
                    "role": user.get("role"),
                    "scope": user.get("scope"),
                    "auth_enabled": auth.is_enabled(),
                    "setup_required": False,
                }
            )
        )

    @app.get(f"{V1_PREFIX}/devices")
    def v1_devices_list():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(apiv1.envelope_ok({"devices": [], "count": 0}))
        devices = auth.list_device_tokens(user["id"])
        return jsonify(
            apiv1.envelope_ok(
                {
                    "devices": devices,
                    "count": len([d for d in devices if not d["revoked"]]),
                }
            )
        )

    @app.post(f"{V1_PREFIX}/devices")
    def v1_devices_create():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.UNAUTHENTICATED, "authentication required")
            ), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.FORBIDDEN,
                    "operator role required",
                    {"required_role": "operator"},
                )
            ), 403
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "").strip()
        if not name:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    "a device name is required so it can be recognised and revoked",
                    {"field": "name"},
                )
            ), 400
        scope = str(body.get("scope") or "viewer")
        if scope not in authmod.ROLES:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    f"scope must be one of {list(authmod.ROLES)}",
                    {"field": "scope"},
                )
            ), 400
        # A token can never exceed its creator's role.
        if not authmod.role_allows(user.get("role"), scope):
            scope = "viewer"
        token = auth.create_device_token(user["id"], name, scope=scope)
        _audit("device_token_created", name, detail={"scope": scope, "api": "v1"})
        return jsonify(
            apiv1.envelope_ok(
                {
                    "token": token,
                    "name": name,
                    "scope": scope,
                    "usage": "Authorization: Bearer <token>",
                    "note": "Copy this token now — it is shown only once.",
                }
            )
        ), 201

    @app.post(f"{V1_PREFIX}/devices/revoke")
    def v1_devices_revoke():
        user = getattr(g, "user", None) or _current_user()
        if user is None:
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.UNAUTHENTICATED, "authentication required")
            ), 401
        if not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.FORBIDDEN, "operator role required")
            ), 403
        handle = str((request.get_json(silent=True) or {}).get("id") or "").strip()
        if not handle:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    "device id is required",
                    {"field": "id"},
                )
            ), 400
        ok = auth.revoke_device_token(user["id"], handle)
        _audit("device_token_revoked", handle, ok=ok, detail={"api": "v1"})
        if not ok:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.NOT_FOUND,
                    f"no device token {handle!r} belongs to this account",
                    {"id": handle},
                )
            ), 404
        return jsonify(apiv1.envelope_ok({"revoked": True, "id": handle}))

    @app.get(f"{V1_PREFIX}/audit")
    def v1_audit():
        user = getattr(g, "user", None) or _current_user()
        if user is not None and not authmod.role_allows(user.get("role"), "operator"):
            return jsonify(
                apiv1.envelope_error(apiv1.ErrorCode.FORBIDDEN, "operator role required")
            ), 403
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    "limit must be an integer",
                    {"field": "limit"},
                )
            ), 400
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
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    "limit must be an integer",
                    {"field": "limit"},
                )
            ), 400
        status = request.args.get("status")
        jobs = _jobs.list_jobs(limit=limit, status=status)
        return jsonify(
            apiv1.envelope_ok(
                {
                    "jobs": jobs,
                    "count": len(jobs),
                    "kinds": sorted(set(jobsmod.JOB_KINDS) | set(jobsmod.COMPOSITE_JOBS)),
                }
            )
        )

    @app.post(f"{V1_PREFIX}/jobs")
    def v1_jobs_submit():
        body = request.get_json(silent=True) or {}
        kind = str(body.get("kind") or "").strip()
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    "params must be an object",
                    {"field": "params"},
                )
            ), 400
        try:
            result = _jobs.submit(kind, params, user=_job_user())
        except jobsmod.JobError as exc:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.VALIDATION_FAILED,
                    str(exc),
                    {
                        "field": "kind",
                        "allowed": sorted(set(jobsmod.JOB_KINDS) | set(jobsmod.COMPOSITE_JOBS)),
                    },
                )
            ), 400
        _audit(
            "job_submitted",
            kind,
            ok=True,
            detail={"job_id": result["job_id"], "created": result["created"]},
        )
        job = _jobs.get(result["job_id"])
        return jsonify(
            apiv1.envelope_ok(
                {
                    "job": job,
                    "created": result["created"],
                    "duplicate": not result["created"],
                }
            )
        ), 201

    @app.get(f"{V1_PREFIX}/jobs/<job_id>")
    def v1_jobs_get(job_id):
        job = _jobs.get(job_id)
        if job is None:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.JOB_NOT_FOUND,
                    f"no such job: {job_id}",
                    {"job_id": job_id},
                )
            ), 404
        return jsonify(apiv1.envelope_ok({"job": job}))

    @app.post(f"{V1_PREFIX}/jobs/<job_id>/cancel")
    def v1_jobs_cancel(job_id):
        try:
            job = _jobs.request_cancel(job_id, user=_job_user())
        except jobsmod.JobError as exc:
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.JOB_NOT_CANCELLABLE, str(exc), {"job_id": job_id}
                )
            ), 409
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
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.JOB_NOT_FOUND,
                    f"no such job: {job_id}",
                    {"job_id": job_id},
                )
            ), 404
        from flask import Response

        last_id = request.headers.get("Last-Event-ID")
        gen = _jobs.events(job_id, last_event_id=last_id)
        return Response(
            gen,
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
            return jsonify(
                _sanitize_for_json(
                    {
                        "ok": True,
                        "readiness": strip,
                        "system": probe_system(),
                        "agent": "sky_agent",
                    }
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sky-agent/status")
    def api_sky_agent_status():
        try:
            from data.database import SignalDB
            from sky_agent.memory import ensure_memory_schema

            with SignalDB() as db:
                ensure_memory_schema(db)
                hyps = [
                    dict(r)
                    for r in db.conn.execute(
                        "SELECT hypothesis_id,setup,status,created_ts FROM research_hypotheses ORDER BY created_ts DESC LIMIT 20"
                    ).fetchall()
                ]
                reports = [
                    dict(r)
                    for r in db.conn.execute(
                        "SELECT report_date,kind,asset,recommendation,level,created_ts FROM intelligence_reports ORDER BY created_ts DESC LIMIT 10"
                    ).fetchall()
                ]
                regimes = [
                    dict(r)
                    for r in db.conn.execute(
                        "SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10"
                    ).fetchall()
                ]
                filings = [
                    dict(r)
                    for r in db.conn.execute(
                        "SELECT accession,event_type,severity FROM sec_events ORDER BY created_ts DESC LIMIT 10"
                    ).fetchall()
                ]
            return jsonify(
                _sanitize_for_json(
                    {
                        "ok": True,
                        "hypotheses": hyps,
                        "reports": reports,
                        "regimes": regimes,
                        "sec_events": filings,
                    }
                )
            )
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
            demo = bool(body.get("demo")) or request.args.get("demo", "").lower() in (
                "1",
                "true",
                "yes",
            )
            report = build_daily_report(demo=demo)
            archived = archive_daily_report(report)
            _audit(
                "sky_agent_report",
                "daily",
                detail={"report_id": archived.get("report_id"), "demo": demo},
            )
            return jsonify(_sanitize_for_json({**archived, "report": report}))
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.errorhandler(404)
    def _v1_404(exc):
        if _is_v1(request.path or ""):
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.NOT_FOUND,
                    f"no such endpoint: {request.method} {request.path}",
                    {"see": "/api/v1/routes"},
                )
            ), 404
        return jsonify({"ok": False, "error": "not found"}), 404

    @app.errorhandler(405)
    def _v1_405(exc):
        if _is_v1(request.path or ""):
            return jsonify(
                apiv1.envelope_error(
                    apiv1.ErrorCode.METHOD_NOT_ALLOWED,
                    f"{request.method} is not allowed on {request.path}",
                    {"see": "/api/v1/routes"},
                )
            ), 405
        return jsonify({"ok": False, "error": "method not allowed"}), 405
