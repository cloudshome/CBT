"""data/push_notifications.py — PWA Web Push (VAPID) notification manager.

Provides standard RFC 8292 Web Push notifications using ECDSA (SECP256R1)
VAPID keys without requiring external third-party services.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

import os

VAPID_KEY_FILE = Path(os.getenv("SKY_STORE_ROOT", Path(__file__).parent / "store")) / "vapid_keys.json"


def _b64url(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def get_or_create_vapid_keys(key_path: Path | None = None) -> tuple[ec.EllipticCurvePrivateKey, str]:
    """Load or generate SECP256R1 VAPID keys.

    Returns (private_key_obj, urlsafe_b64_public_key_point).
    """
    path = key_path or VAPID_KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            priv_pem = data["private_key_pem"].encode("utf-8")
            priv_key = serialization.load_pem_private_key(priv_pem, password=None)
            pub_b64 = data["public_key_b64"]
            if isinstance(priv_key, ec.EllipticCurvePrivateKey):
                return priv_key, pub_b64
        except Exception:
            pass  # regenerate if corrupt

    # Generate new SECP256R1 keypair
    priv_key = ec.generate_private_key(ec.SECP256R1())
    pub_key = priv_key.public_key()

    priv_pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Uncompressed SECP256R1 point format (65 bytes, starting 0x04)
    raw_pub = pub_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = _b64url(raw_pub)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "private_key_pem": priv_pem,
            "public_key_b64": pub_b64,
            "created_ts": int(time.time()),
        }, f, indent=2)

    return priv_key, pub_b64


def get_vapid_public_key(key_path: Path | None = None) -> str:
    """Return the base64url uncompressed public key for browser push registration."""
    _, pub_b64 = get_or_create_vapid_keys(key_path)
    return pub_b64


def create_vapid_jwt(endpoint: str, key_path: Path | None = None,
                     sub: str = "mailto:owner@sky.local", ttl: int = 43200) -> str:
    """Generate RFC 8292 VAPID JWT for a target push service endpoint."""
    parsed = urlparse(endpoint)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    priv_key, _ = get_or_create_vapid_keys(key_path)

    header = {"alg": "ES256", "typ": "JWT"}
    claims = {
        "aud": origin,
        "exp": int(time.time()) + ttl,
        "sub": sub,
    }

    sig_input = f"{_b64url(json.dumps(header))}.{_b64url(json.dumps(claims))}".encode("ascii")
    der_sig = priv_key.sign(sig_input, ec.ECDSA(hashes.SHA256()))

    # Convert DER signature to IEEE P1363 (64 bytes raw r + s)
    r, s = utils.decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    return f"{sig_input.decode('ascii')}.{_b64url(raw_sig)}"


def send_web_push(endpoint: str, p256dh: str, auth: str, payload: dict,
                  key_path: Path | None = None, timeout: int = 5) -> tuple[bool, int, str]:
    """Send a VAPID web push notification to a browser subscription endpoint."""
    jwt = create_vapid_jwt(endpoint, key_path=key_path)
    _, pub_b64 = get_or_create_vapid_keys(key_path)

    headers = {
        "Authorization": f"vapid t={jwt}, k={pub_b64}",
        "TTL": "86400",
        "Content-Type": "application/json",
    }

    body = json.dumps(payload)
    try:
        resp = requests.post(endpoint, data=body, headers=headers, timeout=timeout)
        ok = resp.status_code in (200, 201, 202)
        return ok, resp.status_code, resp.text
    except Exception as exc:
        return False, 0, str(exc)


def broadcast_push_notification(db, title: str, body: str,
                                icon: str = "/static/icons/icon-192.png",
                                url: str = "/", data: dict | None = None,
                                key_path: Path | None = None) -> dict:
    """Broadcast a push notification to all stored device subscriptions."""
    subs = db.list_push_subscriptions() if hasattr(db, "list_push_subscriptions") else []
    if not subs:
        return {"sent": 0, "succeeded": 0, "failed": 0, "removed": 0}

    payload = {
        "title": title,
        "body": body,
        "icon": icon,
        "url": url,
        "data": data or {},
        "timestamp": int(time.time()),
    }

    sent = len(subs)
    succeeded = 0
    failed = 0
    removed = 0

    for sub in subs:
        ep = sub.get("endpoint")
        p256dh = sub.get("p256dh")
        auth_key = sub.get("auth")
        if not ep:
            continue

        ok, status, _ = send_web_push(ep, p256dh, auth_key, payload, key_path=key_path)
        if ok:
            succeeded += 1
        else:
            failed += 1
            # Auto-remove expired / gone subscriptions (HTTP 404 / 410)
            if status in (404, 410) and hasattr(db, "remove_push_subscription"):
                db.remove_push_subscription(ep)
                removed += 1

    return {
        "sent": sent,
        "succeeded": succeeded,
        "failed": failed,
        "removed": removed,
    }
