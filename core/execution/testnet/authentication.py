"""
core/execution/testnet/authentication.py
========================================
Milestone 21: Cryptographic Authentication Signers.

Implements exact exchange signature algorithms for:
1. Binance Spot Testnet (HMAC-SHA256 query string & body signing)
2. Bybit V5 Testnet (HMAC-SHA256 headers for REST & WebSocket auth frames)
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode


class AuthenticationError(Exception):
    """Raised when request signing or auth payload generation fails."""


def sign_binance_request(
    api_key: str,
    api_secret: str,
    params: dict[str, str | int | float] | None = None,
    recv_window: int = 5000,
    timestamp_ms: int | None = None,
) -> tuple[dict[str, str], str]:
    """
    Generates Binance HMAC-SHA256 signature and request headers.
    Returns (headers, signed_query_string).
    """
    if not api_key or not api_secret:
        raise AuthenticationError("Binance signing requires non-empty API key and secret")

    now_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    req_params = dict(params or {})
    req_params["timestamp"] = now_ms
    req_params["recvWindow"] = recv_window

    query_str = urlencode(req_params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    signed_query = f"{query_str}&signature={signature}"
    headers = {
        "X-MBX-APIKEY": api_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return headers, signed_query


def sign_bybit_v5_rest(
    api_key: str,
    api_secret: str,
    payload: str = "",
    recv_window: int = 5000,
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """
    Generates Bybit V5 REST authentication headers.
    String to sign: timestamp + api_key + recv_window + payload.
    """
    if not api_key or not api_secret:
        raise AuthenticationError("Bybit V5 signing requires non-empty API key and secret")

    now_ms = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
    recv_str = str(recv_window)

    sign_payload = f"{now_ms}{api_key}{recv_str}{payload}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": now_ms,
        "X-BAPI-SIGN": signature,
        "X-BAPI-RECV-WINDOW": recv_str,
        "Content-Type": "application/json",
    }


def sign_bybit_v5_websocket(
    api_key: str,
    api_secret: str,
    expires_ms: int | None = None,
) -> dict[str, Any]:
    """
    Generates Bybit V5 Private WebSocket authentication message frame.
    Payload: {"op": "auth", "args": [api_key, expires, signature]}.
    Signature input: f"GET/realtime{expires}".
    """
    if not api_key or not api_secret:
        raise AuthenticationError(
            "Bybit V5 WebSocket signing requires non-empty API key and secret"
        )

    now_ms = int(time.time() * 1000)
    expires = expires_ms if expires_ms is not None else (now_ms + 10000)

    val = f"GET/realtime{expires}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        val.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "op": "auth",
        "args": [api_key, expires, signature],
    }
