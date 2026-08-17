"""web/api_v1.py

P18.2 — the stable application API contract.

Why this module exists
----------------------
P18.1 secured the workstation; P18.2 makes it *addressable by clients that are
not this dashboard*. The Windows and Android companions from P20/P21 cannot be
built against ~55 ad-hoc endpoints whose only shared convention is "returns
some JSON, sometimes with ``ok``, sometimes with ``error``, sometimes a bare
payload, and occasionally a 200 carrying a failure". A companion client that
has to pattern-match prose (or worse, terminal text) breaks on every wording
change.

So this module defines four things and nothing else:

1. **One envelope.** Every ``/api/v1`` response is
   ``{ok, data, error{code,message,details}, meta{...}}``. ``data`` is null on
   failure, ``error`` is null on success, and ``meta`` always carries the
   server/api version and a request id. There is no third shape.
2. **Typed error codes.** :class:`ErrorCode` is a closed vocabulary. Clients
   branch on ``error.code``; ``error.message`` is for humans only and may be
   reworded at any time without it being a breaking change.
3. **Compatibility negotiation.** ``/api/v1/version`` publishes
   ``api_version``, ``min_client_version`` and ``max_client_version``, and a
   client may declare itself with ``X-SKY-Client-Version``. A client older
   than the supported floor gets a single, unambiguous ``CLIENT_TOO_OLD``
   instead of corrupt behaviour.
4. **Idempotent mutations.** Human decisions (review / journal / paper run /
   trader-state) accept an ``Idempotency-Key``. The first call executes and its
   response is stored; a retry with the same key replays that exact response
   without re-executing. Reusing one key with a *different* body is a client
   bug and is rejected with ``IDEMPOTENCY_KEY_REUSED``.

Deliberate non-goals
--------------------
* **No new capability.** Every v1 route delegates to the same handler the
  legacy ``/api/*`` route uses. v1 is a *contract*, not a second brain: it
  cannot approve a trade the legacy path would refuse, cannot loosen the risk
  gate, and adds no exchange-order path (none exists anywhere in SKY).
* **No legacy break.** ``/api/*`` keeps working unchanged so the shipped
  dashboard does not break mid-migration.
* **Security is inherited, not re-implemented.** The P18.1 ``before_request``
  gate already covers ``/api/`` — which includes ``/api/v1/`` — so v1 is
  authenticated, role-checked and CSRF-protected by the same code path. This
  module must never introduce its own bypass.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Callable, Optional

import config

# ── contract versions ─────────────────────────────────────────────────────
#: The API contract version. Bump only for a *breaking* change to the
#: envelope, an error code's meaning, or a route's semantics.
API_VERSION = 1

#: Oldest client build this server still answers. Raise this only when a
#: client below it genuinely cannot work — every raise strands installed apps.
MIN_CLIENT_VERSION = 1

#: Newest client build this server understands. A client above it is told to
#: expect a degraded/unknown surface rather than being silently mis-served.
MAX_CLIENT_VERSION = 1

#: Header a companion client uses to declare its build number.
CLIENT_VERSION_HEADER = "X-SKY-Client-Version"

#: Header carrying the client-generated idempotency key for mutations.
IDEMPOTENCY_HEADER = "Idempotency-Key"

#: How long a stored idempotent result stays replayable.
IDEMPOTENCY_TTL_SECONDS = 24 * 3600

MAX_IDEMPOTENCY_KEY_LEN = 200
MIN_IDEMPOTENCY_KEY_LEN = 8


class ErrorCode:
    """Closed vocabulary of machine-readable error codes.

    Clients branch on these strings. Adding a code is backward compatible;
    removing or repurposing one is a breaking change and requires an
    ``API_VERSION`` bump.
    """

    # authentication / authorization (mirrors the P18.1 gate)
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    CSRF = "CSRF"
    RATE_LIMITED = "RATE_LIMITED"

    # request shape
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"

    # idempotency / compatibility
    IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
    IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
    CLIENT_TOO_OLD = "CLIENT_TOO_OLD"
    CLIENT_TOO_NEW = "CLIENT_TOO_NEW"

    # domain refusals — the desk saying "no" on purpose
    RISK_GATE_CLOSED = "RISK_GATE_CLOSED"
    LIFECYCLE_INVALID = "LIFECYCLE_INVALID"
    CONFLICT = "CONFLICT"

    # infrastructure
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    INTERNAL = "INTERNAL"


#: Legacy handlers signal failures with an HTTP status and loose prose. This
#: maps a status to the typed code when the handler did not supply one, so a
#: v1 client always gets a code even from an un-migrated endpoint.
_STATUS_TO_CODE = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    502: ErrorCode.UPSTREAM_UNAVAILABLE,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
    504: ErrorCode.UPSTREAM_UNAVAILABLE,
}


def code_for_status(status: int) -> str:
    """Typed error code for an HTTP status produced by a legacy handler."""
    return _STATUS_TO_CODE.get(int(status), ErrorCode.INTERNAL)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def meta(request_id: Optional[str] = None, **extra: Any) -> dict:
    """The ``meta`` block every v1 response carries."""
    out = {
        "api_version": API_VERSION,
        "server_version": config.VERSION,
        "request_id": request_id or new_request_id(),
        "ts": int(time.time() * 1000),
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def envelope_ok(data: Any, request_id: Optional[str] = None, **extra_meta: Any) -> dict:
    """Success envelope. ``error`` is always present and always null."""
    return {"ok": True, "data": data, "error": None,
            "meta": meta(request_id, **extra_meta)}


def envelope_error(code: str, message: str, details: Any = None,
                   request_id: Optional[str] = None, **extra_meta: Any) -> dict:
    """Failure envelope. ``data`` is always present and always null."""
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": str(message),
                  "details": details if details is not None else {}},
        "meta": meta(request_id, **extra_meta),
    }


# ── client compatibility ──────────────────────────────────────────────────
def version_info() -> dict:
    """Payload of ``GET /api/v1/version`` — the compatibility contract."""
    return {
        "api_version": API_VERSION,
        "server_version": config.VERSION,
        "min_client_version": MIN_CLIENT_VERSION,
        "max_client_version": MAX_CLIENT_VERSION,
        "client_version_header": CLIENT_VERSION_HEADER,
        "idempotency_header": IDEMPOTENCY_HEADER,
        # Honest capability advertisement: a companion client must be able to
        # discover that this server cannot place an exchange order, rather
        # than shipping a "Trade" button that can never work.
        "capabilities": {
            "live_exchange_execution": False,
            "paper_trading": True,
            "human_approval": True,
            "idempotent_mutations": True,
            "device_tokens": True,
            "roles": ["viewer", "operator"],
        },
    }


def check_client_version(raw: Optional[str]) -> Optional[tuple[str, str]]:
    """Validate a declared client version.

    Returns ``None`` when the client is compatible (or did not declare a
    version — declaring is optional), else ``(code, message)``.
    """
    if raw is None or str(raw).strip() == "":
        return None
    try:
        version = int(str(raw).strip())
    except (TypeError, ValueError):
        return (ErrorCode.BAD_REQUEST,
                f"{CLIENT_VERSION_HEADER} must be an integer build number, "
                f"got {raw!r}")
    if version < MIN_CLIENT_VERSION:
        return (ErrorCode.CLIENT_TOO_OLD,
                f"This client (v{version}) is older than the minimum supported "
                f"version (v{MIN_CLIENT_VERSION}). Please update the app.")
    if version > MAX_CLIENT_VERSION:
        return (ErrorCode.CLIENT_TOO_NEW,
                f"This client (v{version}) is newer than this server supports "
                f"(v{MAX_CLIENT_VERSION}). Please update the SKY Hub.")
    return None


# ── idempotency ───────────────────────────────────────────────────────────
def request_fingerprint(endpoint: str, body: Any) -> str:
    """Stable hash of the request a key was first used with."""
    try:
        canonical = json.dumps(body, sort_keys=True, default=str)
    except Exception:
        canonical = repr(body)
    return hashlib.sha256(f"{endpoint}\n{canonical}".encode("utf-8")).hexdigest()


def validate_key(raw: Optional[str]) -> Optional[str]:
    """Return a clean idempotency key, or ``None`` when absent.

    Raises ``ValueError`` for a supplied-but-unusable key: a client that sends
    a 2-character key believes it has retry safety it does not have, and
    silently ignoring it is the dangerous option.
    """
    if raw is None:
        return None
    key = str(raw).strip()
    if not key:
        return None
    if len(key) < MIN_IDEMPOTENCY_KEY_LEN:
        raise ValueError(
            f"{IDEMPOTENCY_HEADER} must be at least {MIN_IDEMPOTENCY_KEY_LEN} "
            "characters (use a UUID)")
    if len(key) > MAX_IDEMPOTENCY_KEY_LEN:
        raise ValueError(
            f"{IDEMPOTENCY_HEADER} must be at most {MAX_IDEMPOTENCY_KEY_LEN} "
            "characters")
    return key


class IdempotencyStore:
    """Persisted replay cache for human mutations.

    Backed by the signal database so a retry survives a server restart — the
    Android client reconnecting after a crash is exactly the case this exists
    for. The stored value is the *rendered response*, so a replay is
    byte-identical to what the first call returned.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _db(self):
        from data.database import SignalDB
        return SignalDB(self.db_path) if self.db_path else SignalDB()

    def lookup(self, key: str, user_id: Optional[int], endpoint: str,
               fingerprint: str) -> tuple[str, Any]:
        """Resolve a key.

        Returns one of:
        * ``("miss", None)``     — first use; caller should execute.
        * ``("replay", (status, payload))`` — same request seen before.
        * ``("conflict", None)`` — key reused with a different request body.
        * ``("in_progress", None)`` — reserved but not yet completed.
        """
        cutoff = int(time.time()) - IDEMPOTENCY_TTL_SECONDS
        with self._db() as db:
            row = db.conn.execute(
                "SELECT request_hash, status_code, response_json, created_ts "
                "FROM idempotency_keys WHERE key=? AND user_id IS ? AND endpoint=?",
                (key, user_id, endpoint)).fetchone()
            if row is None:
                return ("miss", None)
            if (row["created_ts"] or 0) < cutoff:
                db.conn.execute(
                    "DELETE FROM idempotency_keys WHERE key=? AND user_id IS ? "
                    "AND endpoint=?", (key, user_id, endpoint))
                db.conn.commit()
                return ("miss", None)
            if row["request_hash"] != fingerprint:
                return ("conflict", None)
            if row["response_json"] is None:
                return ("in_progress", None)
            try:
                payload = json.loads(row["response_json"])
            except Exception:
                return ("miss", None)
            return ("replay", (int(row["status_code"] or 200), payload))

    def reserve(self, key: str, user_id: Optional[int], endpoint: str,
                fingerprint: str) -> bool:
        """Claim a key before executing. False if someone else already has it."""
        import sqlite3
        with self._db() as db:
            try:
                db.conn.execute(
                    "INSERT INTO idempotency_keys(key, user_id, endpoint, "
                    "request_hash, status_code, response_json, created_ts) "
                    "VALUES(?,?,?,?,NULL,NULL,?)",
                    (key, user_id, endpoint, fingerprint, int(time.time())))
                db.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def complete(self, key: str, user_id: Optional[int], endpoint: str,
                 status: int, payload: Any) -> None:
        """Store the rendered response so retries replay it."""
        with self._db() as db:
            db.conn.execute(
                "UPDATE idempotency_keys SET status_code=?, response_json=?, "
                "created_ts=? WHERE key=? AND user_id IS ? AND endpoint=?",
                (int(status), json.dumps(payload, default=str),
                 int(time.time()), key, user_id, endpoint))
            db.conn.commit()

    def release(self, key: str, user_id: Optional[int], endpoint: str) -> None:
        """Drop a reservation whose handler raised, so a retry can proceed."""
        with self._db() as db:
            db.conn.execute(
                "DELETE FROM idempotency_keys WHERE key=? AND user_id IS ? "
                "AND endpoint=? AND response_json IS NULL",
                (key, user_id, endpoint))
            db.conn.commit()

    def purge_expired(self) -> int:
        cutoff = int(time.time()) - IDEMPOTENCY_TTL_SECONDS
        with self._db() as db:
            cur = db.conn.execute(
                "DELETE FROM idempotency_keys WHERE created_ts < ?", (cutoff,))
            db.conn.commit()
            return cur.rowcount


# ── the route table ───────────────────────────────────────────────────────
#: Every v1 route, declared as data so it can be *tested* as data and
#: published to clients at ``GET /api/v1/routes``. ``legacy`` names the
#: handler this route delegates to, which is what keeps v1 from becoming a
#: divergent second implementation.
#:
#: ``role`` is the minimum role required; ``idempotent`` marks the human
#: mutations that accept an ``Idempotency-Key``.
ROUTES: tuple[dict, ...] = (
    # ── read: market & signal ─────────────────────────────────────────
    {"path": "/scan", "method": "GET", "legacy": "/api/scan", "role": "viewer",
     "summary": "Live engine scan for one symbol/timeframe."},
    {"path": "/sentiment", "method": "GET", "legacy": "/api/sentiment",
     "role": "viewer", "summary": "Market-sentiment colour reading."},
    {"path": "/intelligence", "method": "GET", "legacy": "/api/intelligence",
     "role": "viewer", "summary": "Institutional desk report."},
    {"path": "/candles", "method": "GET", "legacy": "/api/candles",
     "role": "viewer", "summary": "OHLCV candles for charting."},
    {"path": "/chart", "method": "GET", "legacy": "/api/chart", "role": "viewer",
     "summary": "Chart payload: candles plus overlays and levels."},
    {"path": "/history", "method": "GET", "legacy": "/api/history",
     "role": "viewer", "summary": "Recent scans with lifecycle status."},
    {"path": "/signal", "method": "GET", "legacy": "/api/signal", "role": "viewer",
     "summary": "Full detail, plans and decision trail for one scan."},
    {"path": "/state", "method": "GET", "legacy": "/api/state", "role": "viewer",
     "summary": "Signal state memory and change events."},

    # ── read: desk, risk & evidence ───────────────────────────────────
    {"path": "/pending", "method": "GET", "legacy": "/api/pending",
     "role": "viewer", "summary": "Signals awaiting human approval."},
    {"path": "/risk", "method": "GET", "legacy": "/api/risk", "role": "viewer",
     "summary": "Risk & discipline gate status."},
    {"path": "/desk", "method": "GET", "legacy": "/api/desk", "role": "viewer",
     "summary": "One-call desk advisory."},
    {"path": "/loop-health", "method": "GET", "legacy": "/api/loop-health",
     "role": "viewer", "summary": "The one daily loop-health number."},
    {"path": "/readiness", "method": "GET", "legacy": "/api/readiness",
     "role": "viewer", "summary": "Four-pillar readiness verdict."},
    {"path": "/doctor", "method": "GET", "legacy": "/api/doctor", "role": "viewer",
     "summary": "Readiness verdict in human-readable form."},
    {"path": "/scorecard", "method": "GET", "legacy": "/api/scorecard",
     "role": "viewer", "summary": "Business scorecard."},
    {"path": "/unlock", "method": "GET", "legacy": "/api/unlock", "role": "viewer",
     "summary": "Why the desk is blocked and how to unblock it."},
    {"path": "/evidence", "method": "GET", "legacy": "/api/evidence",
     "role": "viewer", "summary": "Per-setup evidence scoreboard."},
    {"path": "/learning", "method": "GET", "legacy": "/api/learning",
     "role": "viewer", "summary": "Backtest stats and calibration profile."},
    {"path": "/coach", "method": "GET", "legacy": "/api/coach", "role": "viewer",
     "summary": "Explain / mentor / personal feedback."},
    {"path": "/monte", "method": "GET", "legacy": "/api/monte", "role": "viewer",
     "summary": "Monte-Carlo risk-of-ruin table."},

    # ── read: book & journal ──────────────────────────────────────────
    {"path": "/paper", "method": "GET", "legacy": "/api/paper", "role": "viewer",
     "summary": "Paper-trade state and runner statistics."},
    {"path": "/trades", "method": "GET", "legacy": "/api/trades", "role": "viewer",
     "summary": "Live open book with R / MAE / MFE."},
    {"path": "/journal", "method": "GET", "legacy": "/api/journal",
     "role": "viewer", "summary": "Journal entries and discipline summary."},

    # ── read: system ──────────────────────────────────────────────────
    {"path": "/health", "method": "GET", "legacy": "/api/health", "role": "viewer",
     "summary": "Full system health report."},
    {"path": "/channels", "method": "GET", "legacy": "/api/channels",
     "role": "viewer", "summary": "Ordered-backend channel registry."},
    {"path": "/sources", "method": "GET", "legacy": "/api/sources",
     "role": "viewer", "summary": "Source trust scores."},
    {"path": "/connections", "method": "GET", "legacy": "/api/connections",
     "role": "viewer", "summary": "Real-world connection registry."},
    {"path": "/account", "method": "GET", "legacy": "/api/account", "role": "viewer",
     "summary": "Read-only exchange account snapshot."},
    {"path": "/modules", "method": "GET", "legacy": "/api/modules", "role": "viewer",
     "summary": "Every module in the codebase."},
    {"path": "/commands", "method": "GET", "legacy": "/api/commands",
     "role": "viewer", "summary": "Allow-listed CLI command catalog."},
    {"path": "/agents", "method": "GET", "legacy": "/api/agents", "role": "viewer",
     "summary": "Desk morning briefing."},
    {"path": "/glossary", "method": "GET", "legacy": "/api/glossary",
     "role": "viewer", "summary": "Glossary lookup."},

    # ── viewer-safe computations (POST but read-only) ─────────────────
    {"path": "/ask", "method": "POST", "legacy": "/api/ask", "role": "viewer",
     "summary": "Natural-language question to the desk."},
    {"path": "/position-size", "method": "POST", "legacy": "/api/position-size",
     "role": "viewer", "summary": "Position-size calculator bounded by the gate."},
    {"path": "/connections/test", "method": "POST", "legacy": "/api/connections/test",
     "role": "viewer", "summary": "Probe one real-world connection."},

    # ── human mutations (operator + idempotency) ──────────────────────
    {"path": "/review", "method": "POST", "legacy": "/api/review", "role": "operator",
     "idempotent": True,
     "summary": "Approve / reject / execute / close a signal."},
    {"path": "/journal", "method": "POST", "legacy": "/api/journal",
     "role": "operator", "idempotent": True,
     "summary": "Save a post-trade journal entry."},
    {"path": "/paper/run", "method": "POST", "legacy": "/api/paper/run",
     "role": "operator", "idempotent": True,
     "summary": "One explicit paper-runner pass. Never places an order."},
    {"path": "/trader-state", "method": "POST", "legacy": "/api/trader-state",
     "role": "operator", "idempotent": True,
     "summary": "Set or clear behavioral no-trade flags."},

    # ── operator actions without idempotency (safely repeatable) ──────
    {"path": "/commands/run", "method": "POST", "legacy": "/api/commands/run",
     "role": "operator", "summary": "Run one allow-listed catalog command."},
    {"path": "/learn", "method": "POST", "legacy": "/api/learn", "role": "operator",
     "summary": "Recompute the calibration profile."},
    {"path": "/backtest", "method": "POST", "legacy": "/api/backtest",
     "role": "operator", "summary": "Run a backtest pass."},
    {"path": "/alerts/test", "method": "POST", "legacy": "/api/alerts/test",
     "role": "operator", "summary": "Send a test alert to configured notifiers."},
)

#: Routes exposed under ``/api/v1/devices`` etc. are declared separately
#: because they are implemented natively in v1 (they surface P18.1 state as a
#: stable contract) rather than delegating to a legacy handler.
NATIVE_ROUTES: tuple[dict, ...] = (
    {"path": "/version", "method": "GET", "role": "public",
     "summary": "API version and compatibility range."},
    {"path": "/routes", "method": "GET", "role": "viewer",
     "summary": "Machine-readable route catalog."},
    {"path": "/me", "method": "GET", "role": "viewer",
     "summary": "The authenticated principal and its role."},
    {"path": "/devices", "method": "GET", "role": "viewer",
     "summary": "Connected companion devices."},
    {"path": "/devices", "method": "POST", "role": "operator",
     "summary": "Register a companion device; returns a scoped token once."},
    {"path": "/devices/revoke", "method": "POST", "role": "operator",
     "summary": "Revoke one device token."},
    {"path": "/audit", "method": "GET", "role": "operator",
     "summary": "Recent sensitive-action audit rows."},
)


def route_catalog() -> dict:
    """Machine-readable catalog for ``GET /api/v1/routes``."""
    def _entry(r: dict, native: bool) -> dict:
        return {
            "path": f"/api/v1{r['path']}",
            "method": r["method"],
            "role": r.get("role", "viewer"),
            "idempotent": bool(r.get("idempotent")),
            "native": native,
            "legacy": r.get("legacy"),
            "summary": r.get("summary", ""),
        }
    rows = [_entry(r, False) for r in ROUTES] + [_entry(r, True) for r in NATIVE_ROUTES]
    return {
        "count": len(rows),
        "routes": sorted(rows, key=lambda r: (r["path"], r["method"])),
        "envelope": {
            "ok": "bool — request succeeded",
            "data": "object|array|null — payload on success",
            "error": "null on success, else {code, message, details}",
            "meta": "{api_version, server_version, request_id, ts}",
        },
        "error_codes": sorted(
            v for k, v in vars(ErrorCode).items() if not k.startswith("_")),
    }


def idempotent_paths() -> set[str]:
    return {r["path"] for r in ROUTES if r.get("idempotent")}


__all__ = [
    "API_VERSION", "MIN_CLIENT_VERSION", "MAX_CLIENT_VERSION",
    "CLIENT_VERSION_HEADER", "IDEMPOTENCY_HEADER", "IDEMPOTENCY_TTL_SECONDS",
    "ErrorCode", "code_for_status", "envelope_ok", "envelope_error", "meta",
    "new_request_id", "version_info", "check_client_version",
    "request_fingerprint", "validate_key", "IdempotencyStore",
    "ROUTES", "NATIVE_ROUTES", "route_catalog", "idempotent_paths",
]
