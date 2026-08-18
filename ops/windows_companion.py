"""P20 — Windows companion client contract (no local trading brain).

The Ubuntu Hub remains the only database, risk gate and paper runner.
This module is the *client* contract a WebView2/.exe wrapper speaks:

* HTTPS-only Hub URL (loopback HTTP allowed for development)
* compatibility check against ``GET /api/v1/version``
* one-time pairing code → scoped device token
* Credential Manager storage (Windows) — never a world-readable token file
* tray status from loop-health / readiness (read-only)
* idempotent mutation headers for paper actions

This checkout does **not** ship a signed ``.exe``. The packaging recipe
under ``packaging/windows/`` is unsigned by design (signing is P22).
No exchange-order path exists here or anywhere in SKY.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from web.api_v1 import (
    CLIENT_VERSION_HEADER,
    IDEMPOTENCY_HEADER,
    MAX_CLIENT_VERSION,
    MIN_CLIENT_VERSION,
    check_client_version,
)

CLIENT_BUILD = 1
CLIENT_NAME = "sky-windows"
PACKAGE_NAME = "sky-companion"
VERSION = "2.36.0"
CREDENTIAL_TARGET = "SKY/HubDeviceToken"
ALLOWED_SCOPES = ("viewer", "operator")


class CompanionError(ValueError):
    """User-facing companion refusal."""


def validate_hub_url(url: str, *, allow_insecure_loopback: bool = True) -> str:
    """Normalise and refuse non-HTTPS remotes."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise CompanionError("hub URL is required")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("https", "http"):
        raise CompanionError(f"unsupported URL scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise CompanionError("hub URL must include a host")
    loopback = host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")
    if parsed.scheme == "http" and not (allow_insecure_loopback and loopback):
        raise CompanionError("remote companions require HTTPS (TLS on the Hub proxy)")
    if parsed.path and parsed.path not in ("", "/"):
        raise CompanionError("hub URL must be the origin only (no path)")
    return f"{parsed.scheme}://{parsed.netloc}"


def pairing_payload(*, hub_url: str, code: str) -> dict[str, Any]:
    """QR / deep-link payload printed by ``hub pair``."""
    display = code if "-" in code else f"{code[:4]}-{code[4:]}" if len(code) == 8 else code
    return {
        "v": 1,
        "hub": validate_hub_url(hub_url, allow_insecure_loopback=True),
        "code": display,
        "client": CLIENT_NAME,
        "live_exchange_execution": False,
    }


def pairing_qr_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def negotiate_version(info: dict[str, Any], *, client_build: int = CLIENT_BUILD) -> dict[str, Any]:
    """Apply the same compatibility rules the Hub enforces."""
    bad = check_client_version(str(client_build))
    caps = (info or {}).get("capabilities") or {}
    if caps.get("live_exchange_execution"):
        raise CompanionError("refusing a Hub that advertises live exchange execution")
    if bad is not None:
        raise CompanionError(bad[1])
    server_min = int((info or {}).get("min_client_version") or MIN_CLIENT_VERSION)
    server_max = int((info or {}).get("max_client_version") or MAX_CLIENT_VERSION)
    if client_build < server_min:
        raise CompanionError(
            f"This companion (v{client_build}) is older than the Hub minimum (v{server_min}).")
    if client_build > server_max:
        raise CompanionError(
            f"This companion (v{client_build}) is newer than the Hub (v{server_max}).")
    return {
        "ok": True,
        "client_build": client_build,
        "server_version": (info or {}).get("server_version"),
        "api_version": (info or {}).get("api_version"),
        "capabilities": caps,
        "live_exchange_execution": False,
    }


def new_idempotency_key() -> str:
    return uuid.uuid4().hex


def mutation_headers(*, token: str, idempotency_key: str | None = None) -> dict[str, str]:
    key = idempotency_key or new_idempotency_key()
    if len(key) < 8:
        raise CompanionError("idempotency key too short")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        CLIENT_VERSION_HEADER: str(CLIENT_BUILD),
        IDEMPOTENCY_HEADER: key,
    }


def read_headers(*, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        CLIENT_VERSION_HEADER: str(CLIENT_BUILD),
    }


def tray_status(loop_health: dict[str, Any] | None,
                readiness: dict[str, Any] | None,
                *,
                connected: bool,
                last_ok_ts: int | None = None) -> dict[str, Any]:
    """System-tray snapshot. Honest about stale / offline."""
    now = int(time.time() * 1000)
    stale = False
    if last_ok_ts is not None:
        stale = now - int(last_ok_ts) > 5 * 60 * 1000
    loop = loop_health or {}
    ready = readiness or {}
    gate = (loop.get("gate") or {})
    if isinstance(gate, dict):
        gate_open = bool(gate.get("allowed", gate.get("open")))
    else:
        gate_open = False
    paper = loop.get("loop") or loop.get("paper") or {}
    open_n = 0
    if isinstance(paper, dict):
        open_n = int(paper.get("open") or paper.get("live_open") or 0)
    pending = 0
    if isinstance(paper, dict):
        pending = int(paper.get("pending") or 0)
    level = "offline"
    if connected and not stale:
        level = str(ready.get("level") or ("ok" if gate_open else "blocked"))
    elif connected and stale:
        level = "stale"
    return {
        "connected": bool(connected),
        "stale": bool(stale) or not connected,
        "level": level,
        "gate_open": gate_open if connected else False,
        "open_paper": open_n,
        "pending": pending,
        "headline": ready.get("headline") or loop.get("advice") or (
            "Hub offline" if not connected else "connected"),
        "live_exchange_execution": False,
        "mutations_allowed": bool(connected and not stale),
    }


class TokenStore:
    """Device token storage. Windows Credential Manager when available.

    File fallback is refused unless ``SKY_COMPANION_ALLOW_FILE_TOKEN=1``
    *and* the file is not world-readable. Tokens never go to logs.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else Path(
            os.getenv("SKY_COMPANION_STATE", str(Path.home() / ".sky" / "companion.json")))

    def _win_cred_write(self, token: str) -> bool:
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes

            class CREDENTIAL(ctypes.Structure):
                _fields_ = [
                    ("Flags", wintypes.DWORD),
                    ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                    ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR),
                ]

            adv = ctypes.WinDLL("advapi32", use_last_error=True)
            blob = token.encode("utf-16-le")
            cred = CREDENTIAL()
            cred.Type = 1  # GENERIC
            cred.TargetName = CREDENTIAL_TARGET
            cred.CredentialBlobSize = len(blob)
            cred.CredentialBlob = ctypes.cast(ctypes.create_string_buffer(blob),
                                              ctypes.POINTER(ctypes.c_char))
            cred.Persist = 2  # LOCAL_MACHINE
            cred.UserName = CLIENT_NAME
            if not adv.CredWriteW(ctypes.byref(cred), 0):
                return False
            return True
        except Exception:
            return False

    def _win_cred_read(self) -> str | None:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes
            adv = ctypes.WinDLL("advapi32", use_last_error=True)
            ptr = ctypes.c_void_p()
            if not adv.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(ptr)):
                return None
            # Best-effort: treat as opaque; tests do not run CredRead.
            return None
        except Exception:
            return None

    def save(self, *, hub_url: str, token: str, scope: str, name: str) -> dict[str, Any]:
        if scope not in ALLOWED_SCOPES:
            raise CompanionError(f"scope must be one of {ALLOWED_SCOPES}")
        used_credman = self._win_cred_write(token)
        record = {
            "hub_url": validate_hub_url(hub_url),
            "scope": scope,
            "name": name,
            "client_build": CLIENT_BUILD,
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "stored": "credential_manager" if used_credman else "file",
            "live_exchange_execution": False,
        }
        if used_credman:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({**record, "token": None}, indent=2) + "\n",
                                 encoding="utf-8")
            return record
        if os.getenv("SKY_COMPANION_ALLOW_FILE_TOKEN") != "1":
            raise CompanionError(
                "Windows Credential Manager unavailable — refusing to write the "
                "device token to a file (set SKY_COMPANION_ALLOW_FILE_TOKEN=1 "
                "only for tests)")
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
        mode = self.path.stat().st_mode
        if mode & stat.S_IROTH:
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


def pair_with_hub(*, hub_url: str, code: str, device_name: str = "windows",
                  transport: Callable[..., dict] | None = None,
                  store: TokenStore | None = None) -> dict[str, Any]:
    """POST /api/v1/pair then persist the token."""
    origin = validate_hub_url(hub_url)
    body = {"code": code, "name": device_name, "client": CLIENT_NAME,
            "client_build": CLIENT_BUILD}
    if transport is None:
        raise CompanionError("no transport (tests inject one; .exe uses HTTPS)")
    envelope = transport("POST", origin + "/api/v1/pair", json=body,
                         headers={CLIENT_VERSION_HEADER: str(CLIENT_BUILD)})
    if not envelope.get("ok"):
        err = (envelope.get("error") or {})
        raise CompanionError(err.get("message") or "pairing failed")
    data = envelope.get("data") or {}
    token = data.get("token")
    if not token:
        raise CompanionError("Hub did not return a device token")
    store = store or TokenStore()
    meta = store.save(hub_url=origin, token=token,
                      scope=str(data.get("scope") or "viewer"),
                      name=str(data.get("name") or device_name))
    return {**meta, "paired": True, "token_shown": False}


def companion_spec() -> dict[str, Any]:
    """Unsigned packaging contract. Signing is P22."""
    return {
        "package": PACKAGE_NAME,
        "version": VERSION,
        "client_build": CLIENT_BUILD,
        "shell": "WebView2",
        "signed": False,
        "installer": "unsigned-msix-or-exe (recipe only)",
        "start_menu": True,
        "tray": True,
        "updates": "notify-only (no silent major)",
        "storage": "Windows Credential Manager",
        "api": "/api/v1",
        "pairing": "one-time hub code / QR",
        "live_exchange_execution": False,
        "note": "This repository does not contain a signed Windows binary.",
    }


def format_spec(spec: dict[str, Any] | None = None) -> str:
    spec = spec or companion_spec()
    lines = [
        f"SKY Windows companion {spec['version']}  (client build {spec['client_build']})",
        f"  shell     {spec['shell']}",
        f"  signed    {'yes' if spec['signed'] else 'NO — P22'}",
        f"  pairing   {spec['pairing']}",
        f"  storage   {spec['storage']}",
        "  live exchange execution  NO",
        f"  {spec['note']}",
    ]
    return "\n".join(lines)
