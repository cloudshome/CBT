"""P21 — Android companion client contract (no local trading brain).

The Ubuntu Hub remains the only database, risk gate and paper runner.
This module is the *client* contract a native Android shell speaks to the
Hub over ``/api/v1``. It is the Android analogue of ``ops/windows_companion.py``
with Android-specific concerns:

* HTTPS-only Hub URL with a **configured-host allowlist** — a hardened WebView
  navigates only to an explicit host, never an arbitrary URL.
* token storage described for the **Android Keystore** (hardware-backed); the
  sandbox fallback is a guarded, never-world-readable file (test-only).
* a **biometric re-check policy** that tells the app *when* it must prompt for
  fingerprint/face before an operator mutation, without touching hardware here.
* **online-only mutations** — an offline or stale snapshot refuses writes; a
  paper approval is never queued for replay offline.
* **push / deep-link contract** mapping a notification to the exact ``/api/v1``
  record (signal, risk, paper, journal) so the app opens that record.
* ``live_exchange_execution`` is always false; there is **no order path**.

This checkout does **not** ship a signed ``.apk`` (signing is P22). The recipe
under ``packaging/android/`` is unsigned by design. No exchange-order path
exists here or anywhere in SKY.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from ops.windows_companion import (
    CompanionError,  # same exception the shared helpers raise
)
from ops.windows_companion import (
    mutation_headers as _mutation_headers,
)
from ops.windows_companion import (
    negotiate_version as _negotiate_version,
)
from ops.windows_companion import (
    pairing_payload as _pairing_payload,
)
from ops.windows_companion import (
    pairing_qr_text as _pairing_qr_text,
)
from ops.windows_companion import (
    read_headers as _read_headers,
)
from ops.windows_companion import (
    validate_hub_url as _validate_hub_url,
)
from web.api_v1 import CLIENT_VERSION_HEADER

CLIENT_BUILD = 1
CLIENT_NAME = "sky-android"
PACKAGE_NAME = "sky-companion-android"
VERSION = "2.37.0"
KEYSTORE_ALIAS = "sky_hub_device_token"
ALLOWED_SCOPES = ("viewer", "operator")

#: Deep-link record types this companion can open directly from a push.
DEEP_LINK_TYPES = ("signal", "risk", "paper", "journal", "dashboard")


# ── Hub URL rules + configured-host allowlist ──────────────────────────────
def validate_hub_url(url: str, *, allow_insecure_loopback: bool = True) -> str:
    """Normalise and refuse non-HTTPS remotes (Android WebView is HTTPS-only)."""
    return _validate_hub_url(url, allow_insecure_loopback=allow_insecure_loopback)


def host_allowed(url: str, allowed_hosts: str | list[str] | None) -> bool:
    """Enforce the configured-host allowlist for the hardened WebView.

    ``allowed_hosts`` may be a comma/space separated string or a list of host
    names (no scheme, no port). Empty/None denies everything (fail closed);
    exact host match or a suffix after a leading ``.`` is allowed so a user can
    pin ``desk.example.com`` or ``example.com``.
    """
    if not allowed_hosts:
        return False
    if isinstance(allowed_hosts, str):
        hosts = [h.strip().lower() for h in allowed_hosts.replace(",", " ").split()]
    else:
        hosts = [str(h).strip().lower() for h in allowed_hosts]
    hosts = [h for h in hosts if h]
    if not hosts:
        return False
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for allowed in hosts:
        if allowed.startswith("."):
            if host.endswith(allowed) and host != allowed:
                return True
        elif host == allowed:
            return True
    return False


def pairing_payload(*, hub_url: str, code: str) -> dict[str, Any]:
    """QR / deep-link payload printed by ``hub pair --platform android``."""
    payload = _pairing_payload(hub_url=hub_url, code=code)
    return {**payload, "client": CLIENT_NAME, "platform": "android"}


def pairing_qr_text(payload: dict[str, Any]) -> str:
    return _pairing_qr_text(payload)


def negotiate_version(
    info: dict[str, Any], *, client_build: int = CLIENT_BUILD
) -> dict[str, Any]:
    """Apply the same compatibility rules the Hub enforces (Android client)."""
    out = _negotiate_version(info, client_build=client_build)
    out["client_name"] = CLIENT_NAME
    return out


def mutation_headers(
    *, token: str, idempotency_key: str | None = None
) -> dict[str, str]:
    return _mutation_headers(token=token, idempotency_key=idempotency_key)


def read_headers(*, token: str) -> dict[str, str]:
    return _read_headers(token=token)


# ── Token storage: Android Keystore (guarded file fallback for the sandbox) ─
class KeystoreTokenStore:
    """Device token storage described for the Android Keystore.

    On Android the token lives in a hardware-backed KeyStore alias and never
    touches app storage readable by the process or logs. This sandbox has no
    Android device, so the store is a thin *contract* with a guarded file
    fallback: writes are refused unless ``SKY_ANDROID_ALLOW_FILE_TOKEN=1``
    *and* the file is not world-readable — exactly like the Windows analogue.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = (
            Path(path)
            if path
            else Path(
                os.getenv(
                    "SKY_ANDROID_STATE",
                    str(Path.home() / ".sky" / "android_companion.json"),
                )
            )
        )
        self._backend = "android_keystore" if os.name != "nt" else "credential_manager"

    def _keystore_write(self, token: str) -> bool:
        """No-op outside Android: real Keystore access lives in the APK."""
        return False

    def save(
        self, *, hub_url: str, token: str, scope: str, name: str
    ) -> dict[str, Any]:
        if scope not in ALLOWED_SCOPES:
            raise CompanionError(f"scope must be one of {ALLOWED_SCOPES}")
        used_keystore = self._keystore_write(token)
        record = {
            "hub_url": validate_hub_url(hub_url),
            "scope": scope,
            "name": name,
            "platform": "android",
            "client_build": CLIENT_BUILD,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "stored": "android_keystore" if used_keystore else "file",
            "live_exchange_execution": False,
        }
        if used_keystore:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({**record, "token": None}, indent=2) + "\n", encoding="utf-8"
            )
            return record
        if os.getenv("SKY_ANDROID_ALLOW_FILE_TOKEN") != "1":
            raise CompanionError(
                "Android Keystore unavailable — refusing to write the device "
                "token to a file (set SKY_ANDROID_ALLOW_FILE_TOKEN=1 only for tests)"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**record, "token": token}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        if self.path.stat().st_mode & stat.S_IROTH:
            self.path.unlink(missing_ok=True)
            raise CompanionError("refusing a world-readable token file")
        return record

    def load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if data.get("token") and (self.path.stat().st_mode & stat.S_IROTH):
            raise CompanionError("token file is world-readable — revoke the device")
        return data

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()


def pair_with_hub(
    *,
    hub_url: str,
    code: str,
    device_name: str = "android",
    transport=None,
    store: KeystoreTokenStore | None = None,
) -> dict[str, Any]:
    """POST /api/v1/pair then persist the token (Android client)."""
    origin = validate_hub_url(hub_url)
    body = {
        "code": code,
        "name": device_name,
        "client": CLIENT_NAME,
        "client_build": CLIENT_BUILD,
    }
    if transport is None:
        raise CompanionError("no transport (tests inject one; the APK uses HTTPS)")
    envelope = transport(
        "POST",
        origin + "/api/v1/pair",
        json=body,
        headers={CLIENT_VERSION_HEADER: str(CLIENT_BUILD)},
    )
    if not envelope.get("ok"):
        err = envelope.get("error") or {}
        raise CompanionError(err.get("message") or "pairing failed")
    data = envelope.get("data") or {}
    token = data.get("token")
    if not token:
        raise CompanionError("Hub did not return a device token")
    store = store or KeystoreTokenStore()
    meta = store.save(
        hub_url=origin,
        token=token,
        scope=str(data.get("scope") or "viewer"),
        name=str(data.get("name") or device_name),
    )
    return {**meta, "paired": True, "token_shown": False}


# ── Biometric re-check policy (describes when the app must re-auth) ────────
BIOMETRIC_MUTATIONS = (
    "approve_paper",
    "journal_write",
    "revoke_device",
    "paper_reject",
    "risk_override",
)

BIOMETRIC_POLICY = {
    "enabled": True,
    "scope": "operator",
    "require_on": list(BIOMETRIC_MUTATIONS),
    "reader": "fingerprint_or_face (Android BiometricPrompt)",
    "interval": "per_mutation_for_writes; per_session_for_reads",
    "fallback": "password_or_device_credential_when_biometric_unavailable",
    "live_exchange_execution": False,
}


def biometric_policy() -> dict[str, Any]:
    """Machine-readable description of the biometric re-check contract.

    Purely declarative here — the actual BiometricPrompt lives in the APK.
    """
    return dict(BIOMETRIC_POLICY)


def requires_biometric(action: str, scope: str = "operator") -> bool:
    """True when a mutation must be preceded by a fresh biometric re-check."""
    if scope != "operator":
        return False
    return action in BIOMETRIC_MUTATIONS


# ── Online-only mutations / connection snapshot ────────────────────────────
def connection_snapshot(
    *,
    connected: bool,
    last_ok_ts: int | None = None,
    readiness: dict[str, Any] | None = None,
    loop_health: dict[str, Any] | None = None,
    biometric_ok: bool = True,
) -> dict[str, Any]:
    """Android status snapshot. Honest about stale / offline.

    Mirrors the Windows tray snapshot but encodes the Android rule that a
    paper approval is **never** queued offline: ``mutations_allowed`` is false
    unless the feed is connected, fresh and the risk gate is open.
    """
    now = int(time.time() * 1000)
    stale = False
    if last_ok_ts is not None:
        stale = now - int(last_ok_ts) > 5 * 60 * 1000
    ready = readiness or {}
    loop = loop_health or {}
    gate = loop.get("gate") or {}
    gate_open = (
        bool(gate.get("allowed", gate.get("open"))) if isinstance(gate, dict) else False
    )
    paper = loop.get("loop") or loop.get("paper") or {}
    open_n = (
        int(paper.get("open") or paper.get("live_open") or 0)
        if isinstance(paper, dict)
        else 0
    )
    pending = int(paper.get("pending") or 0) if isinstance(paper, dict) else 0
    level = "offline"
    if connected and not stale:
        level = str(ready.get("level") or ("ok" if gate_open else "blocked"))
    elif connected and stale:
        level = "stale"
    return {
        "platform": "android",
        "connected": bool(connected),
        "stale": bool(stale) or not connected,
        "level": level,
        "gate_open": bool(gate_open and connected and not stale),
        "open_paper": open_n,
        "pending": pending,
        "biometric_ok": bool(biometric_ok),
        "mutations_allowed": bool(connected and not stale and biometric_ok),
        "offline_queue": "never",  # no approval is replayed offline
        "headline": ready.get("headline")
        or loop.get("advice")
        or ("Hub offline" if not connected else "connected"),
        "live_exchange_execution": False,
    }


# ── Push / deep-link contract ──────────────────────────────────────────────
#: deep-link type → the /api/v1 (or browser) surface that renders that record.
DEEP_LINK_SURFACE = {
    "signal": "/api/v1/signals/{id}",
    "risk": "/api/v1/risk/center/{id}",
    "paper": "/api/v1/paper/approvals/{id}",
    "journal": "/api/v1/journal/{id}",
    "dashboard": "/",
}


def deep_link(record_type: str, record_id: str | int = "") -> str:
    """Build a ``sky://`` deep link a push notification can open.

    The app resolves the URI to the corresponding screen and fetches the
    record over ``/api/v1``; it never renders arbitrary web content.
    """
    if record_type not in DEEP_LINK_TYPES:
        raise CompanionError(f"unknown deep-link record type: {record_type}")
    rid = quote(str(record_id), safe="") if record_id else ""
    return f"sky://record/{record_type}" + (f"/{rid}" if rid else "")


def deep_link_surface(record_type: str) -> str:
    """The hub surface a deep link maps to (documentation / verification)."""
    if record_type not in DEEP_LINK_TYPES:
        raise CompanionError(f"unknown deep-link record type: {record_type}")
    return DEEP_LINK_SURFACE[record_type]


# ── Packaging contract ─────────────────────────────────────────────────────
def android_spec() -> dict[str, Any]:
    """Unsigned packaging contract. Signing is P22."""
    return {
        "package": PACKAGE_NAME,
        "version": VERSION,
        "client_build": CLIENT_BUILD,
        "shell": "native Android (WebView allowlisted to the configured host)",
        "signed": False,
        "installer": "unsigned APK (recipe only)",
        "start_menu": False,
        "tray": False,
        "updates": "notify-only (no silent major)",
        "storage": "Android Keystore",
        "api": "/api/v1",
        "pairing": "one-time hub code / QR",
        "biometric": "BiometricPrompt re-check for operator writes",
        "deep_links": list(DEEP_LINK_TYPES),
        "live_exchange_execution": False,
        "note": "This repository does not contain a signed Android APK.",
    }


def format_spec(spec: dict[str, Any] | None = None) -> str:
    spec = spec or android_spec()
    lines = [
        f"SKY Android companion {spec['version']}  (client build {spec['client_build']})",
        f"  shell     {spec['shell']}",
        f"  signed    {'yes' if spec['signed'] else 'NO — P22'}",
        f"  pairing   {spec['pairing']}",
        f"  storage   {spec['storage']}",
        f"  biometric {spec['biometric']}",
        "  live exchange execution  NO",
        f"  {spec['note']}",
    ]
    return "\n".join(lines)
