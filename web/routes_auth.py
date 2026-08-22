"""web/routes_auth.py — PWA push + auth API routes (extracted from web/app.py).

Refactor step 4 (ROADMAP §19): the push/auth route handlers used to live
inline inside ``make_app``; they live here now.  ``register(app, ctx)``
unpacks the shared make_app closures as locals so every handler body is
semantically identical to the original (verified by dedent-diff).  The
before-request auth gate stays in ``make_app`` — this module only owns the
endpoints themselves.
"""

from __future__ import annotations

import secrets

from flask import jsonify, request, session

from web import auth as authmod


def register(app, ctx):
    auth = ctx["auth"]
    _auth_state = ctx["_auth_state"]
    _current_user = ctx["_current_user"]
    _client_ip = ctx["_client_ip"]
    _client_ua = ctx["_client_ua"]
    _audit = ctx["_audit"]

    # ── PWA Web Push (VAPID) API ──────────────────────────────────────────
    @app.get("/api/push/vapid-key")
    def api_push_vapid_key():
        from data.push_notifications import get_vapid_public_key
        pub = get_vapid_public_key()
        return jsonify({"ok": True, "public_key": pub})

    @app.post("/api/push/subscribe")
    def api_push_subscribe():
        from data.database import SignalDB
        body = request.get_json(silent=True) or {}
        endpoint = body.get("endpoint")
        keys = body.get("keys") or {}
        p256dh = keys.get("p256dh")
        auth_key = keys.get("auth")
        if not endpoint or not p256dh or not auth_key:
            return jsonify({"ok": False, "error": "missing endpoint or subscription keys"}), 400
        ua = request.headers.get("User-Agent", "")
        user = _current_user()
        uid = user.get("id") if user else None
        with SignalDB() as db:
            res = db.save_push_subscription(endpoint, p256dh, auth_key, user_id=uid, user_agent=ua)
        return jsonify({"ok": True, "registered": res})

    @app.post("/api/push/unsubscribe")
    def api_push_unsubscribe():
        from data.database import SignalDB
        body = request.get_json(silent=True) or {}
        endpoint = body.get("endpoint")
        if not endpoint:
            return jsonify({"ok": False, "error": "missing endpoint"}), 400
        with SignalDB() as db:
            removed = db.remove_push_subscription(endpoint)
        return jsonify({"ok": True, "removed": removed})

    @app.post("/api/push/test")
    def api_push_test():
        from data.database import SignalDB
        from data.push_notifications import broadcast_push_notification
        with SignalDB() as db:
            res = broadcast_push_notification(
                db,
                title="SKY Trading Desk",
                body="Web Push notification connected and active!",
                icon="/static/icons/icon-192.png",
                url="/",
            )
        return jsonify({"ok": True, "broadcast": res})

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

