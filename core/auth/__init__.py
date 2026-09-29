"""
API Key Authentication & Credential Security Package for FastAPI

Provides:
  - API Key dependency: require_api_key, API_KEY
  - Credential Vault: CredentialVault, credential_vault, ExchangeCredential
  - Secret sanitization & masking: mask_secret, sanitize_text, sanitize_dict, zeroize_bytes
  - Exchange Signers: BinanceSigner, BybitV5Signer
"""

import hmac
import os

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from core.auth.credential_vault import (
    CredentialVault,
    ExchangeCredential,
    VaultConfigurationError,
    VaultDecryptionError,
    VaultError,
    VaultIntegrityError,
    credential_vault,
    mask_secret,
    sanitize_dict,
    sanitize_text,
    zeroize_bytes,
)
from core.auth.exchange_signers import (
    BinanceSigner,
    BybitV5Signer,
    SigningError,
)

# Read once at import so tests can monkeypatch `core.auth.API_KEY` and services
# resolve the key from the environment before process start.
API_KEY = os.getenv("API_KEY", "")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _extract_api_key(request: Request, x_api_key: str | None) -> str | None:
    """Extract API key from Authorization header or X-API-Key header."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    if x_api_key and x_api_key.strip():
        return x_api_key.strip()

    return None


async def require_api_key(
    request: Request,
    x_api_key: str | None = Depends(_api_key_header),
) -> None:
    """
    FastAPI dependency that enforces API key authentication.
    When API_KEY is not configured, all requests pass through in dev/test.
    In production, missing API_KEY raises a 500 error to prevent accidental open access.
    """
    env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    current_key = globals().get("API_KEY", "")
    if not current_key:
        if env == "production":
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Production Security Misconfiguration: API_KEY must be configured in production."
                },
            )
        return

    provided_key = _extract_api_key(request, x_api_key)

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Authentication required",
                "message": "Provide API key via Authorization: Bearer <key> or X-API-Key header",
            },
        )

    if not hmac.compare_digest(provided_key.encode(), current_key.encode()):
        raise HTTPException(
            status_code=403,
            detail={"error": "Invalid API key"},
        )


__all__ = [
    "API_KEY",
    "BinanceSigner",
    "BybitV5Signer",
    "CredentialVault",
    "ExchangeCredential",
    "SigningError",
    "VaultConfigurationError",
    "VaultDecryptionError",
    "VaultError",
    "VaultIntegrityError",
    "credential_vault",
    "mask_secret",
    "require_api_key",
    "sanitize_dict",
    "sanitize_text",
    "zeroize_bytes",
]
