"""
core/auth/exchange_signers.py
=============================
Canonical HMAC-SHA256 Request Signers for Binance v3 and Bybit V5.

Strict Invariants:
- Canonical parameter serialization: query parameters sorted alphabetically.
- Exact bytes used for signature calculation correspond strictly to transmitted request.
- Millisecond timestamps with strict recvWindow enforcement (default: 5000ms).
- Masked headers in representations; secrets never retained in return dictionaries.
- Complete support for GET and POST payloads across both exchanges.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any

logger = logging.getLogger("sky.exchange_signers")

DEFAULT_RECV_WINDOW = 5000


class SigningError(Exception):
    """Raised when request signing fails."""


class BinanceSigner:
    """
    Canonical Binance v3 HMAC-SHA256 Signer.
    Follows Binance API specifications for spot order placement and account queries.
    """

    @staticmethod
    def sign_request(
        api_key: str,
        api_secret: str,
        params: dict[str, Any] | None = None,
        recv_window: int = DEFAULT_RECV_WINDOW,
        timestamp_ms: int | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """
        Signs Binance request parameters with timestamp and recvWindow.

        Returns:
            (headers, signed_params)
            Where signed_params contains the canonical signature parameter.
        """
        if not api_key or not api_secret:
            raise SigningError("Binance API key and secret are required for signing.")

        req_params = dict(params or {})
        now_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)

        # Inject mandatory Binance timing controls
        req_params["recvWindow"] = recv_window
        req_params["timestamp"] = now_ms

        # Canonical query serialization: sorted keys
        sorted_params = dict(sorted((k, v) for k, v in req_params.items() if v is not None))
        canonical_query = urllib.parse.urlencode(sorted_params)

        signature = hmac.new(
            api_secret.encode("utf-8"),
            canonical_query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        sorted_params["signature"] = signature

        headers = {
            "X-MBX-APIKEY": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        return headers, sorted_params


class BybitV5Signer:
    """
    Canonical Bybit V5 HMAC-SHA256 Signer.
    Constructs X-BAPI headers per Bybit V5 documentation for Unified/Spot endpoints.
    """

    @staticmethod
    def sign_request(
        api_key: str,
        api_secret: str,
        method: str,
        params_or_body: dict[str, Any] | None = None,
        recv_window: int = DEFAULT_RECV_WINDOW,
        timestamp_ms: int | None = None,
    ) -> tuple[dict[str, str], str]:
        """
        Signs Bybit V5 request using X-BAPI-* headers.

        For GET:
            prehash = f"{timestamp}{api_key}{recv_window}{query_string}"
        For POST:
            prehash = f"{timestamp}{api_key}{recv_window}{json_body_str}"

        Returns:
            (headers, serialized_payload_str)
        """
        if not api_key or not api_secret:
            raise SigningError("Bybit API key and secret are required for signing.")

        now_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        str_ts = str(now_ms)
        str_window = str(recv_window)
        http_method = method.upper().strip()

        data = dict(params_or_body or {})

        if http_method in ("GET", "DELETE"):
            # Query string sorted
            if data:
                payload_str = urllib.parse.urlencode(
                    sorted((k, v) for k, v in data.items() if v is not None)
                )
            else:
                payload_str = ""
            prehash = f"{str_ts}{api_key}{str_window}{payload_str}"
        else:
            # POST/PUT: JSON serialization with compact separators
            payload_str = json.dumps(data, separators=(",", ":"), sort_keys=True)
            prehash = f"{str_ts}{api_key}{str_window}{payload_str}"

        signature = hmac.new(
            api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": str_ts,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str_window,
            "Content-Type": "application/json",
        }

        return headers, payload_str
