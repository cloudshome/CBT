"""web/auth.py

P18.1 — authentication & authorization for the SKY workstation.

Security model
--------------
* First-run owner creation with a securely hashed password (PBKDF2-HMAC-SHA256,
  260k iterations — no extra dependencies, stdlib only).
* Two roles: ``viewer`` (read dashboards/evidence/health/paper state) and
  ``operator`` (viewer + explicitly permitted human paper actions). No role
  grants live exchange execution because that capability does not exist.
* Secure cookie sessions for browsers (signed, httpOnly, SameSite=Lax) and
  revocable, scoped bearer tokens for companion clients (Windows/Android).
* CSRF protection for cookie-authenticated mutations, login throttling, session
  expiry, logout-all-devices, and an audit row for every sensitive action.

Activation model
----------------
``SKY_AUTH_MODE`` decides when enforcement is on:

* ``auto`` (default): the very first run has no owner yet, so the dashboard
  stays "simple" long enough for the first visitor to create the owner. The
  moment an owner exists, every private endpoint requires authentication.
* ``required``: enforcement from the start (bare checkout is locked until setup).
* ``disabled``: auth off (development / tests only).

Remote mode (non-loopback bind) refuses to serve without an owner account and
a TLS-terminating reverse proxy (``SKY_TRUSTED_PROXY_IPS``), unless explicitly
overridden. See ``enforce_deployment``.

Tokens are stored hashed (sha256) so a database leak cannot replay a session or
device token; password verifies use constant-time comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

import config

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLES = (ROLE_VIEWER, ROLE_OPERATOR)

# Endpoints a viewer may POST to (read-only computations / queries). Everything
# else that mutates state requires the operator role.
VIEWER_POST_PATHS = {"/api/ask", "/api/position-size", "/api/connections/test"}

PBKDF2_ITERATIONS = 260_000  # OWASP-recommended floor for PBKDF2-HMAC-SHA256
MIN_PASSWORD_LEN = 8
MIN_USERNAME_LEN = 3


def role_rank(role: str) -> int:
    """operator > viewer; unknown roles rank lowest."""
    return 1 if role == ROLE_OPERATOR else 0


def role_allows(role: str, required: str) -> bool:
    return role_rank(role or ROLE_VIEWER) >= role_rank(required)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)`` for a password."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return salt, dk.hex()


def verify_password(password: str, salt: str, expected_hex: str) -> bool:
    """Constant-time password verification."""
    try:
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), expected_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1") or h.startswith("127.")


class AuthManager:
    """All authentication state lives in the signal database (extra tables)."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else Path(config.DB_PATH)

    # ── low-level helpers ────────────────────────────────────────────────
    def _meta_get(self, key: str) -> str | None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute("SELECT value FROM auth_meta WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def _meta_set(self, key: str, value: str) -> None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "INSERT INTO auth_meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            db.conn.commit()

    def _fetch_user(self, db, user_id: int) -> dict | None:
        row = db.conn.execute(
            "SELECT id, username, role, created_ts, last_login_ts FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    # ── session secret (persisted across restarts) ──────────────────────
    def secret_key(self) -> str:
        """Return a stable secret key for Flask session signing."""
        explicit = (config.SKY_SECRET_KEY or "").strip()
        if explicit:
            return explicit
        stored = self._meta_get("secret_key")
        if stored:
            return stored
        generated = secrets.token_hex(32)
        self._meta_set("secret_key", generated)
        return generated

    # ── owner / activation ──────────────────────────────────────────────
    def owner_exists(self) -> bool:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT COUNT(*) n FROM users WHERE role=?", (ROLE_OPERATOR,)
            ).fetchone()
            return bool(row["n"])

    def has_users(self) -> bool:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute("SELECT COUNT(*) n FROM users").fetchone()
            return bool(row["n"])

    def is_enabled(self) -> bool:
        mode = config.SKY_AUTH_MODE
        if mode == "disabled":
            return False
        if mode == "required":
            return True
        return self.owner_exists()

    def create_owner(self, username: str, password: str, role: str = ROLE_OPERATOR) -> dict:
        """First-run owner creation. Refuses if an owner already exists."""
        username = (username or "").strip()
        if len(username) < MIN_USERNAME_LEN:
            raise ValueError(f"username must be at least {MIN_USERNAME_LEN} characters")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
        if role not in ROLES:
            raise ValueError(f"bad role {role!r}")
        if self.owner_exists():
            raise PermissionError("an owner account already exists")
        salt, pwhash = hash_password(password)
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            cur = db.conn.execute(
                "INSERT INTO users(username, password_hash, salt, role, created_ts) "
                "VALUES(?,?,?,?,?)",
                (username, pwhash, salt, role, int(time.time() * 1000)),
            )
            db.conn.commit()
            user_id = cur.lastrowid
        return {"id": user_id, "username": username, "role": role}

    def get_user(self, user_id: int) -> dict | None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            return self._fetch_user(db, user_id)

    def get_user_by_name(self, username: str) -> dict | None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT id, username, role, password_hash, salt, last_login_ts "
                "FROM users WHERE username=?",
                (username,),
            ).fetchone()
            return dict(row) if row else None

    # ── login throttling ────────────────────────────────────────────────
    def _attempt_keys(self, username: str, ip: str) -> list[str]:
        keys = [f"user:{username.lower()}"]
        if ip:
            keys.append(f"ip:{ip}")
        return keys

    def is_locked(self, username: str, ip: str) -> bool:
        now = int(time.time())
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            for key in self._attempt_keys(username, ip):
                row = db.conn.execute(
                    "SELECT lock_until_ts FROM login_attempts WHERE key=?", (key,)
                ).fetchone()
                if row and row["lock_until_ts"] and row["lock_until_ts"] > now:
                    return True
        return False

    def record_failure(self, username: str, ip: str) -> None:
        now = int(time.time())
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            for key in self._attempt_keys(username, ip):
                row = db.conn.execute(
                    "SELECT failures FROM login_attempts WHERE key=?", (key,)
                ).fetchone()
                failures = (row["failures"] if row else 0) + 1
                lock_until = (
                    now + config.SKY_LOGIN_LOCKOUT_SECONDS
                    if failures >= config.SKY_LOGIN_MAX_ATTEMPTS
                    else None
                )
                db.conn.execute(
                    "INSERT INTO login_attempts(key, failures, lock_until_ts, last_ts) "
                    "VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                    "failures=excluded.failures, lock_until_ts=excluded.lock_until_ts, "
                    "last_ts=excluded.last_ts",
                    (key, failures, lock_until, now),
                )
            db.conn.commit()

    def clear_failures(self, username: str, ip: str) -> None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            for key in self._attempt_keys(username, ip):
                db.conn.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            db.conn.commit()

    def authenticate(self, username: str, password: str, ip: str = "") -> dict | None:
        """Return the user dict on success, else None (and record a failure)."""
        user = self.get_user_by_name(username)
        if user is None:
            self.record_failure(username, ip)
            return None
        if not verify_password(password, user["salt"], user["password_hash"]):
            self.record_failure(username, ip)
            return None
        self.clear_failures(username, ip)
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "UPDATE users SET last_login_ts=? WHERE id=?",
                (int(time.time() * 1000), user["id"]),
            )
            db.conn.commit()
        return {"id": user["id"], "username": user["username"], "role": user["role"]}

    def change_password(self, user_id: int, current: str, new: str) -> None:
        if len(new or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT salt, password_hash FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if row is None:
                raise ValueError("user not found")
            if not verify_password(current, row["salt"], row["password_hash"]):
                raise PermissionError("current password is incorrect")
            salt, pwhash = hash_password(new)
            db.conn.execute(
                "UPDATE users SET salt=?, password_hash=? WHERE id=?",
                (salt, pwhash, user_id),
            )
            db.conn.commit()

    # ── sessions (browser cookies) ──────────────────────────────────────
    def create_session(self, user_id: int, ip: str = "", user_agent: str = "") -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time() * 1000)
        ttl_ms = config.SKY_SESSION_TTL_HOURS * 3600 * 1000
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "INSERT INTO sessions(token_hash, user_id, created_ts, expires_ts, "
                "last_seen_ts, ip, user_agent) VALUES(?,?,?,?,?,?,?)",
                (_token_hash(token), user_id, now, now + ttl_ms, now, ip, user_agent),
            )
            db.conn.commit()
        return token

    def resolve_session(self, token: str) -> dict | None:
        """Return the user for a live (non-expired, non-idle) session token."""
        from data.database import SignalDB

        now = int(time.time() * 1000)
        idle_ms = config.SKY_SESSION_IDLE_HOURS * 3600 * 1000
        th = _token_hash(token)
        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT user_id, expires_ts, last_seen_ts FROM sessions WHERE token_hash=?",
                (th,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_ts"] and now > row["expires_ts"]:
                db.conn.execute("DELETE FROM sessions WHERE token_hash=?", (th,))
                db.conn.commit()
                return None
            if row["last_seen_ts"] and now - row["last_seen_ts"] > idle_ms:
                db.conn.execute("DELETE FROM sessions WHERE token_hash=?", (th,))
                db.conn.commit()
                return None
            db.conn.execute("UPDATE sessions SET last_seen_ts=? WHERE token_hash=?", (now, th))
            db.conn.commit()
            return self._fetch_user(db, row["user_id"])

    def revoke_session(self, token: str) -> None:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
            db.conn.commit()

    def revoke_all_sessions(self, user_id: int) -> int:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            cur = db.conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.conn.commit()
            return cur.rowcount

    # ── device tokens (companion clients) ───────────────────────────────
    def create_device_token(self, user_id: int, name: str, scope: str = ROLE_VIEWER) -> str:
        if scope not in ROLES:
            raise ValueError(f"bad scope {scope!r}")
        token = secrets.token_urlsafe(32)
        now = int(time.time() * 1000)
        ttl_ms = config.SKY_DEVICE_TOKEN_TTL_DAYS * 24 * 3600 * 1000
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "INSERT INTO device_tokens(token_hash, user_id, name, scope, "
                "created_ts, expires_ts, revoked) VALUES(?,?,?,?,?,?,0)",
                (
                    _token_hash(token),
                    user_id,
                    (name or "").strip() or "device",
                    scope,
                    now,
                    now + ttl_ms,
                ),
            )
            db.conn.commit()
        return token

    def resolve_device_token(self, token: str) -> dict | None:
        """Return the user + scope for a live device token."""
        from data.database import SignalDB

        now = int(time.time() * 1000)
        th = _token_hash(token)
        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT user_id, scope, expires_ts, revoked FROM device_tokens WHERE token_hash=?",
                (th,),
            ).fetchone()
            if row is None or row["revoked"]:
                return None
            if row["expires_ts"] and now > row["expires_ts"]:
                return None
            db.conn.execute("UPDATE device_tokens SET last_used_ts=? WHERE token_hash=?", (now, th))
            db.conn.commit()
            user = self._fetch_user(db, row["user_id"])
            if user is None:
                return None
            # The token's *scope* is the effective authorization level — a
            # viewer-scoped token must never act as the operator who minted it.
            user["role"] = row["scope"]
            user["scope"] = row["scope"]
            return user

    def list_device_tokens(self, user_id: int) -> list[dict]:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            rows = db.conn.execute(
                "SELECT token_hash, name, scope, created_ts, expires_ts, "
                "last_used_ts, revoked FROM device_tokens WHERE user_id=? "
                "ORDER BY created_ts DESC",
                (user_id,),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["token_hash"][:12],
                    "name": r["name"],
                    "scope": r["scope"],
                    "created_ts": r["created_ts"],
                    "expires_ts": r["expires_ts"],
                    "last_used_ts": r["last_used_ts"],
                    "revoked": bool(r["revoked"]),
                }
            )
        return out

    def revoke_device_token(self, user_id: int, handle: str) -> bool:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT token_hash FROM device_tokens WHERE user_id=? AND "
                "substr(token_hash,1,12)=?",
                (user_id, handle),
            ).fetchone()
            if row is None:
                return False
            db.conn.execute(
                "UPDATE device_tokens SET revoked=1 WHERE token_hash=?",
                (row["token_hash"],),
            )
            db.conn.commit()
            return True

    # ── pairing codes (P20 companion first-run) ────────────────────────
    PAIRING_TTL_SECONDS = 10 * 60
    PAIRING_CODE_LEN = 8

    def create_pairing_code(
        self,
        user_id: int,
        name: str = "windows",
        scope: str = ROLE_VIEWER,
        ttl_seconds: int | None = None,
    ) -> dict:
        """Mint a short-lived one-time pairing code. Raw code shown once."""
        if scope not in ROLES:
            raise ValueError(f"bad scope {scope!r}")
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(self.PAIRING_CODE_LEN))
        display = f"{raw[:4]}-{raw[4:]}"
        now = int(time.time() * 1000)
        ttl = int(ttl_seconds or self.PAIRING_TTL_SECONDS)
        expires = now + ttl * 1000
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "INSERT INTO pairing_codes(code_hash, user_id, name, scope, "
                "created_ts, expires_ts, used_ts) VALUES(?,?,?,?,?,?,NULL)",
                (
                    _token_hash(raw),
                    user_id,
                    (name or "").strip() or "windows",
                    scope,
                    now,
                    expires,
                ),
            )
            db.conn.commit()
        return {
            "code": display,
            "raw": raw,
            "expires_ts": expires,
            "ttl_seconds": ttl,
            "name": (name or "").strip() or "windows",
            "scope": scope,
        }

    def redeem_pairing_code(self, code: str, device_name: str = "windows") -> dict:
        """Exchange a one-time pairing code for a scoped device token.

        Codes are case-insensitive and may include a hyphen. Used and expired
        codes fail closed. The pairing row is marked used atomically.
        """
        cleaned = "".join(ch for ch in (code or "").upper() if ch.isalnum())
        if len(cleaned) != self.PAIRING_CODE_LEN:
            raise ValueError("pairing code must be 8 characters")
        now = int(time.time() * 1000)
        th = _token_hash(cleaned)
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            row = db.conn.execute(
                "SELECT user_id, name, scope, expires_ts, used_ts "
                "FROM pairing_codes WHERE code_hash=?",
                (th,),
            ).fetchone()
            if row is None:
                raise PermissionError("unknown pairing code")
            if row["used_ts"]:
                raise PermissionError("pairing code already used")
            if row["expires_ts"] and now > row["expires_ts"]:
                raise PermissionError("pairing code expired")
            cur = db.conn.execute(
                "UPDATE pairing_codes SET used_ts=? WHERE code_hash=? AND used_ts IS NULL",
                (now, th),
            )
            db.conn.commit()
            if cur.rowcount != 1:
                raise PermissionError("pairing code already used")
            user_id = int(row["user_id"])
            scope = row["scope"] or ROLE_VIEWER
            label = (device_name or row["name"] or "windows").strip()
        token = self.create_device_token(user_id, label, scope=scope)
        return {"token": token, "scope": scope, "name": label, "user_id": user_id}

    def revoke_all_devices(self, user_id: int) -> int:
        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            cur = db.conn.execute(
                "UPDATE device_tokens SET revoked=1 WHERE user_id=? AND revoked=0",
                (user_id,),
            )
            db.conn.commit()
            return cur.rowcount

    # ── audit log ────────────────────────────────────────────────────────
    def audit(
        self,
        action: str,
        target: str = "",
        user: dict | None = None,
        ok: bool = True,
        ip: str = "",
        user_agent: str = "",
        detail: dict | None = None,
    ) -> None:
        import json as _json

        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            db.conn.execute(
                "INSERT INTO audit_log(ts, user_id, username, role, action, target, "
                "ip, user_agent, ok, detail_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    int(time.time() * 1000),
                    user.get("id") if user else None,
                    user.get("username") if user else None,
                    user.get("role") if user else None,
                    action,
                    str(target),
                    ip or "",
                    (user_agent or "")[:200],
                    1 if ok else 0,
                    _json.dumps(detail or {}, default=str),
                ),
            )
            db.conn.commit()

    def recent_audit(self, limit: int = 100) -> list[dict]:
        import json as _json

        from data.database import SignalDB

        with SignalDB(self.db_path) as db:
            rows = db.conn.execute(
                "SELECT ts, username, role, action, target, ip, ok, detail_json "
                "FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = _json.loads(d.get("detail_json") or "{}")
            except Exception:
                d["detail"] = {}
            d.pop("detail_json", None)
            out.append(d)
        return out


def enforce_deployment(host: str) -> None:
    """Refuse to serve remotely without an owner account + HTTPS-aware proxy.

    Local loopback stays simple (still requires auth once an owner exists, via
    the normal request gate). A remote bind is a hard error unless the owner is
    configured and TLS termination is declared, so an accidental
    ``--host 0.0.0.0`` can never expose the desk to plaintext remote users.
    """
    if is_loopback_host(host):
        return
    if config.SKY_ALLOW_REMOTE_NO_TLS:
        return
    mgr = AuthManager()
    if not mgr.owner_exists():
        raise RuntimeError(
            "Refusing to bind the dashboard to a non-loopback host: no owner "
            "account exists. Run first-run setup on localhost (or set "
            "SKY_AUTH_MODE=required and create the owner) before exposing SKY "
            "remotely."
        )
    if not config.SKY_TRUSTED_PROXY_IPS:
        raise RuntimeError(
            "Refusing to bind the dashboard to a non-loopback host: no "
            "TLS-terminating reverse proxy is configured. Set "
            "SKY_TRUSTED_PROXY_IPS (comma-separated proxy IPs) so SKY knows it "
            "sits behind HTTPS, or set SKY_ALLOW_REMOTE_NO_TLS=1 to accept the "
            "risk explicitly."
        )
